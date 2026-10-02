# Autoplay: infrastructure planner (`autoplay/`)

Part of the [AI cheatsheet](../AI_CHEATSHEET.md). Code lives in `autoplay/`, outside the tiered `scripts/` tree; `autoplay/lib/` modules import `scripts/` lib modules, never the reverse.

## §11 Map geometry (`autoplay/lib/grid_geom.py`)

| Fact | Value |
| :--- | :--- |
| Tile size `TILE_M` | 10 m; utility lanes run through tile centres (`…5`) |
| Utility piece | one straight 10 m segment between two neighbouring tile centres; 1 segment item each (`gas_pipe_segment`, `liquid_pipe_segment`, `power_line_segment`) |
| Job `position` of a pipe / power-line piece | segment midpoint, on a tile edge: `(10,-5)` = tiles `(0,-1)`+`(1,-1)` |
| Bridge | 3 tiles along its axis; job `position` = centre tile; 1 `*_bridge` item; job has no axis field |
| Bridge spacing | bridges may not share a tile; one may start on the tile right after another's end. Two neighbouring lines (one free lane between) are crossed by landing, stepping one tile sideways and bridging again |
| Connection rule | same-medium pieces connect only when they share a tile; parallel neighbour lanes stay separate, also inside footprints |
| Layers | gas, liquid and power are independent; power crosses pipes freely |
| Footprint `FOOTPRINT_TILES` | 4×4 tiles (40×40 m) for outposts and field extractors |
| Outpost anchor | `outpost.x/.y` = top-left (outpost at 0,0 covers 0..40) |
| Extractor anchor | centre on its site (site at 50,50 covers 30..70) |
| Clearance | outpost 40 m, POI 20 m (structure placement only; pipes and lines may cross) |
| `plan_pipe` | no L-routing: send axis-aligned runs only, check the job count (= tiles − 1) |
| `plan_power_line` | L-routes off-axis requests itself |

Tiles are packed into one int (`tile_key()`), neighbour = key ± `1` (y) or ± `1<<16` (x).

**Router** (`route_init` / `route_seed` / `route_step` / `route_path`, A* with a goal-bounding-box heuristic): sources cost 0 (an existing network is reused), `blocked` tiles are walls, a `bridgeable` wall tile may be hopped by a 3-tile bridge when both end tiles are free and neither is the previous bridge's landing tile, `soft` tiles cost extra. Search nodes are `tile * 2 + landed`, so a tile reached by a landing and the same tile reached on foot are kept apart (only the latter may start a bridge). `path_plan()` turns a path into `("run", a, b)` / `("bridge", middle, axis)` build steps.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `STEP_COST` | 1 | per tile |
| `BRIDGE_COST` | 6 | per bridge hop (instead of 2 steps) |
| `SOFT_TILE_COST` | 4 | extra per soft tile (another site's footprint) |
| `ROUTE_MAX_NODES` | 20000 | expanded tiles before giving up |
| `ROUTE_STEP_NODES` | 10 | search nodes per atomic `route_step()` (~375 operations each) |
| `SEED_CHUNK` | 40 | source tiles per atomic `route_seed()` |

## §11a Occupancy (`autoplay/lib/infra_topology.py`)

`Topology` lives for the whole planner run: the first `read()` reads every pipe; later reads read only pipes with a new id (`new_pipe_slice()`, atomic) and drop vanished ids, and every `FULL_REFRESH_PASSES` reads it re-reads all pipes, because an existing pipe's `contents()` can change without a new id. The pipe occupancy (`pipe_occupancy()`) is rebuilt only when pipes or `autoplay.networks` changed; job ghosts are overlaid every read (`overlay_jobs()`). `read()` builds `occ = {layer: {tile: label}}` from `list_pipes()`, the pending/active/paused construction jobs and `autoplay.networks`. Label = the piece's `contents()`; else the planner's own fluid for that tile; else `FOREIGN` (`"?"`). Conflicted pieces and tiles claimed by two labels are `FOREIGN`. Power-line ghosts are `POWER`; completed power lines have no list API (subnets via `power_control.grids()`).

`walls(layer, fluid)` = every tile with another label; `held(layer, fluid)` = tiles of that fluid. `footprint_ports(footprint, layer, fluid)` → `held` / `free` / `others`; the footprint is full for that medium when `held` and `free` are both empty. Gas fluids: `GAS_FLUIDS` (steam, ammonia, swamp_gas, raw/refined sulfur gas and chlorine); every other fluid is a liquid.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `PIPE_CHUNK` | 16 | pipes per atomic read slice (~190 operations each) |
| `JOB_CHUNK` | 20 | jobs per atomic read slice |
| `PIPE_PROGRESS_EVERY` | 500 | pipes between map-read progress lines (debug) |
| `ID_CHUNK` | 200 | pipes per atomic new-id check (`new_pipe_slice()`) |
| `FULL_REFRESH_PASSES` | 30 | incremental reads between full pipe re-reads |

Archive: `autoplay.networks` = `{fluid: [[x1, y1, x2, y2], ...]}` (straight runs, tile centres) the planner laid.

Atomic slice costs are measured in `tests/test_autoplay_geom.py` / `tests/test_autoplay_topology.py` against `construction_plan.ATOMIC_STEP_BUDGET`.

## §11b Power pass (`autoplay/lib/power_plan.py`)

Joins every power subnet into one grid. Components = `power_control.grids()`, placed on the map by their members' footprints (`grid_geom.outpost_box()` / `extractor_box()`, inclusive tile boxes):

| Member | Position source |
| :--- | :--- |
| Outpost | `outpost_network.outposts()` `.x/.y` (top-left) |
| Water / oil pump | surveyed `WaterWell`/`OilWell` whose `pump_id()` is the machine |
| Thermal / exotic cap, spring tap | surveyed `ThermalVent`/`ExoticDeposit` whose `cap_id()` is the machine |
| Mining drill | `drill.positions` archive (`lib/drill_sites.py`; drills expose no position) |

A grid with no placeable member is skipped (debug log). Links = Kruskal MST over the nearest-tile distance between footprints of different components (`edge_slice()` in atomic batches of `PAIR_CHUNK` box pairs, `pair_segments()`). **No grid hangs on a field structure**: a field structure in a grid with other placed members is a *shared* end. A link ending there also wires that footprint's perimeter (`ring_legs()`, `RING_PIECES` = 12 pieces). Every line feeding the structure crosses a perimeter tile, so deconstructing the structure keeps the grid whole. The ring pieces count into the link's MST cost, so an outpost wins unless the shared structure is more than 12 tiles nearer. A lone field structure (its own grid) is a leaf: no ring. Existing lines end on a footprint edge or corner tile (confirmed in the save: `exotic_gas_cap_8`, centre tile (-69,-64), line on (-68,-63)), so edge tiles connect.

Each pass queues the cheapest missing links as `plan_power_line()` between the two nearest footprint tiles (tile centres), plus the ring legs, as one all-or-nothing route; on `blocked`/`invalid_route` the two explicit L elbows are tried (two legs, all-or-nothing: a rejected second leg cancels the first). A link the game rejects, or that creates no job while the grids stay apart, is not retried until the script restarts. A link needs `power_line_segment` ≥ its cost (tile distance + ring pieces) in the Inventory. Completed power lines are not visible to scripts (no list API; `list_pipes()` covers gas/liquid only); the ledger (§11d) supplies them. Ledger tiles are assigned to a grid by flooding over 4-neighbouring power tiles from the power tiles inside each grid's footprints (`flood_init()`/`flood_step()`, atomic in `FLOOD_STEP_TILES` slices); a tile two grids reach is contested and dropped, an unreached one ignored. Each grid's tiles become horizontal 1×n run boxes (`line_runs()`, member `line`, never ringed), so a link prefers ending on an existing line. `pair_segments()` pairs only boxes of different grids.

The pass waits while any power-line job is open: completed lines have no list API, so grids only show the link once it is built.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `MAX_LINKS_PER_PASS` | 1 | power links queued per pass |
| `RING_PIECES` | 12 | pieces around a 4×4 footprint perimeter; extra MST cost of a shared field-structure end |
| `PAIR_CHUNK` | 50 | footprint pairs per atomic edge batch (~3,500 operations worst) |
| `FLOOD_STEP_TILES` | 30 | ledger tiles per atomic `flood_step()` (~3,100 operations worst) |
| `PASS_SLEEP_S` (`planner_loop.py`) | 60 | seconds between passes while work is open |

Run loop (`autoplay/lib/planner_loop.py`, entrypoint `autoplay/infra_planner_automation.py`): read `Topology`, prune `autoplay.planned`, ledger upkeep (§11d), power pass, fluid pass (§11e); each phase ends with a debug `Pass: <phase> (<sim s>)` line; the script ends once the power pass reports one placed grid and the fluid pass `done`.

## §11c Blueprint queue (`autoplay/lib/blueprint_queue.py`)

The planner's only writer of blueprints: `queue_power_route()` (power legs) and `queue_pipe_route()` (§11e). Archive `autoplay.planned` = `{blueprint_id: {"k": kind, "f": fluid | "power" | None, "p": prio, "seg": [x1, y1, x2, y2] | None, "site": id | None}}`; entries are dropped once their job is no longer pending/active/paused (skipped when a job list could not be read). Jobs with a prio other than `construction_plan.DEFAULT_PRIORITY` also get a `construction.priority` entry.

## §11d Power-line ledger (`autoplay/lib/power_survey.py`, `construction.power_tiles`)

Scripts cannot list completed power lines. Their tiles live in `construction.power_tiles` (format in [archive_ipc.md](archive_ipc.md)); three sources keep it whole:

| State of a piece | Source |
| :--- | :--- |
| Built before the ledger existed | one-off full survey (`run_full()`), when `surveyed` is None |
| Built later (by anyone) | the Pioneer that finished the job (`note_power_job()`, [vehicles_drones.md](vehicles_drones.md)) |
| Planned / under construction | not in the ledger: `pending/active/paused_constructions()`, read every pass; the power pass waits while any power job is open |
| Finished but not recorded (Pioneer crashed after `execute()`) | `track_jobs()`: `autoplay.power_jobs` `{job_id: {"k", "t"}}` of open power jobs; a vanished line job whose tiles are missing, or any vanished deconstruct/bridge job, marks its tiles dirty |

**Probe** = `construction_blueprint.mark_deconstruct(x, y, "power")` on a tile centre (simworker: every completed power piece touching the tile matches):

| Status | Meaning | Side effect |
| :--- | :--- | :--- |
| `nothing_here` | no piece | none |
| `ambiguous_target` | 2+ pieces (line interior, junction) | none |
| `ok` | 1 piece (line end) or power bridge centre | one unpaid deconstruct job, cancelled at once (`Prober`; a failed cancel is retried after the walk) |
| `already_queued` | a deconstruct job exists already | none (still a power tile) |
| `locked` | no Constructor research | survey aborted; links use footprints only |

`run_full()` probes all 180×180 map tiles (`MAP_MIN_TILE..MAP_MAX_TILE` = −90..89) with `construction.hold` on `deconstruct` (refreshed every `SURVEY_CHUNK` probes, deleted in `finally`), then writes the found tiles plus tiles Pioneers added during the walk, keeping `dirty`. `reprobe_dirty()` probes only dirty tiles. **Ledger writes and the 10,000-step updater cap** (`archive.transaction` updaters run as one callback, dev_workflow.md §1d-1): Pioneer updates (`note_power_job()`) edit only the runs of the touched rows (`power_rows_add()`/`power_rows_remove()`, worst ~3,000 operations on a 60-run row) and append to `dirty` with native list membership; whole-ledger rewrites (survey result, dirty re-probe) are built outside and stored by `construction_plan.swap_power_ledger()` (compare-and-swap, read-back check, up to 3 attempts when a Pioneer wrote in between). Measured on this save: 745 power tiles, 29 line ends (probe jobs), the rest ambiguous.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `SURVEY_CHUNK` | 400 | probes between hold refreshes |
| `SURVEY_PROGRESS_EVERY` | 2000 | probes between survey progress lines (debug: count, %, power tiles, cancelled jobs, sim s) |
| `HOLD_STALE_TICKS` (`construction_plan`) | 600 | a hold older than this no longer counts |
| `POWER_DIRTY_MAX` (`construction_plan`) | 400 | dirty tiles kept before a full re-survey is requested |

## §11e Fluid pass (`autoplay/lib/fluid_plan.py`)

One pipe network per fluid, joining the fluid's producers to the outposts whose roles take it (§11f).

**Game facts this rests on.** Pipes have no fluid of their own: `plan_pipe(fluid_id, …)` keeps only the medium (simworker `tre()`), and a component's contents come from the `connect()` relationships routed through it (set by the pump/cap/consumer scripts, not the planner). The planner's fluid for its own ghosts and not-yet-connected pipes lives in `autoplay.networks`. Between two locations the game splits the fluids over the components reaching both; one more fluid than components there is a conflict on `connect()`. So a network touches only its own fluid's terminals:

| Wall for fluid F (same medium layer) | Crossing |
| :--- | :--- |
| tiles of any other label (other fluids, `FOREIGN`) | 3-tile bridge (`plan_bridge`) |
| footprints of every outpost and field structure that is not a terminal of F (outposts, sited pumps/caps, known drills) | never |

Gas and liquid layers ignore each other.

**Terminals.** Producers = extractors on surveyed sites (water/oil pumps `pump_id()`, thermal caps for steam, exotic caps/taps by deposit `fluid()`) and outposts whose roles list the fluid under `"out"` (condenser water, Refiner outputs). Consumers = outposts whose roles list it under `"in"`; an outpost on both sides is one producer terminal. Only fluids some outpost takes are routed; one without any producer is skipped (`no producer` debug line). A terminal is connected when one of its footprint tiles carries the fluid.

**Route.** Per pass at most `MAX_ROUTES_PER_PASS` routes, fluids in `FLUID_ORDER` then by name. A* from every tile carrying the fluid (reused for free) to the free footprint tiles of all unconnected terminals; the route stops on the first footprint tile it reaches, so it takes one port. With no network yet, the first producer (by id) with a free tile is the source and only consumer outposts are goals. `path_plan()` steps go out via `blueprint_queue.queue_pipe_route()` (§11c). A route the game rejects, or a search that finds no path, marks its terminals failed until the script restarts. Stock gate: `<medium>_pipe_segment` ≥ route pieces and `<medium>_pipe_bridge` ≥ bridges, else the pass reports `waiting`.

**Ports.** A footprint with no free tile on a medium is *full* for it (logged, skipped). An outpost keeps its last free tiles for earlier fluids of its role order that still need a port and have a producer (*reserved*). `autoplay.port_status` = `{outpost_id: {"gas": [labels], "liquid": [labels], "full": [media]}}` for consumer outposts, rewritten only on change.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `MAX_ROUTES_PER_PASS` | 1 | fluid routes queued per pass |
| `LABEL_CHUNK` | 200 | occupancy tiles per atomic `label_slice()` (~3,400 operations worst) |
| `FLUID_ORDER` | water, oil, steam | routing order; other fluids follow by name |

The run loop ends once the power pass reports one grid and the fluid pass reports `done`.

`queue_pipe_route()` (§11c): one `plan_pipe` per straight run, one `plan_bridge` per bridge, all or nothing. A run that creates fewer jobs than its pieces minus `reusable_pieces()` (consecutive tile pairs both already carrying the fluid) is treated as `short` and the whole route is cancelled. On success, the runs are appended to `autoplay.networks[fluid]`; for a bridge, only its two end tiles are stored (as one-tile runs), because the middle tile belongs to the line it crosses.

## §11f Outpost roles (`autoplay/lib/autoplay_roles.py`)

| Key | Shape | Writer |
| :--- | :--- | :--- |
| `autoplay.role_presets` | `{role: {"in": [fluid, ...], "out": [fluid, ...]}}` (a plain list = `"in"` only) | seeded with `DEFAULT_ROLE_PRESETS` when missing; operator-editable |
| `autoplay.outpost_roles` | `{outpost_id: role \| [role, ...]}` | operator; entries of gone outposts pruned each pass |

Default presets (in → out): `factory` water, oil, steam · `terraform` water, steam · `power` steam, oil · `farm` water · `condenser` steam → water · `reactor` water · `drone_service` oil · `bio_caster` steam, water · `biomass_mixer` the five essences · `refinery` the four raw exotics → sulfur_gas, chlorine, cryofluid, quicksilver · `wildlife` ammonia, swamp_gas, sulfur_gas, chlorine, brine, cryofluid, quicksilver. One-fluid sub-roles: `refinery_<fluid>` (`refinery_quicksilver` = raw_quicksilver → quicksilver) and `wildlife_<fluid>` spread exotics over outposts; `liquifier_<biome>` → `<biome>_essence` (an Essence Liquifier makes its outpost biome's essence); `storage_<fluid>` = that fluid in and out (tanks; the outpost becomes a producer terminal on that network). Waste Processors have no role (generic sink, wire locally). The home outpost always has `HOME_ROLES` (`farm`: the Harvester field is there) after its own roles. An outpost's fluid order (roles in order, each role's in before its out, duplicates dropped) is its port service order. Example: `{"home": ["wildlife_ammonia"], "outpost_3": ["factory", "refinery_chlorine"]}`.
