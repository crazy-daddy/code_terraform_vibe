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
| Footprint `FOOTPRINT_TILES` | 4×4 tiles (40×40 m) for outposts and field extractors: the utility area where pipes and power lines connect, centred on the structure (simworker `Fx()`). Structures block each other only by their placement square |
| Outpost anchor | `outpost.x/.y` = top-left corner of the 20×20 placement square (y grows north): square x..x+20, y-20..y, centre (x+10, y-10) (`grid_geom.outpost_centre()`); utility footprint x-10..x+30, y-30..y+10 |
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
| `SOFT_TILE_COST` | 4 | extra per soft tile (another site's footprint; a tile beside another network's pipe, `fluid_plan.find_route()`) |
| `ROUTE_MAX_NODES` | 20000 | expanded tiles before giving up |
| `ROUTE_STEP_NODES` | 10 | search nodes per atomic `route_step()` (~375 operations each) |
| `SEED_CHUNK` | 40 | source tiles per atomic `route_seed()` |

## §11a Occupancy (`autoplay/lib/infra_topology.py`)

`Topology` lives for the whole planner run: the first `read()` reads every pipe; later reads read only pipes with a new id (`new_pipe_slice()`, atomic) and drop vanished ids, and every `FULL_REFRESH_PASSES` reads it re-reads all pipes, because an existing pipe's `contents()` can change without a new id. The pipe occupancy (`pipe_occupancy()`) is rebuilt only when pipes or `autoplay.networks` changed; job ghosts are overlaid every read (`overlay_jobs()`). `read()` builds `occ = {layer: {tile: label}}` from `list_pipes()`, the pending/active/paused construction jobs and `autoplay.networks`. Label = the piece's `contents()`; else the planner's own fluid for that tile; else `FOREIGN` (`"?"`). Extractor jobs (`EXTRACTOR_KINDS`: thermal/exotic caps, spring tap, water/oil pump, the three drills) land in `Topology.structure_rows` (`{id, kind, x, y}`, position = the site); the fluid pass treats their footprints as walls, the extractor pass as claimed sites. Conflicted pieces and tiles claimed by two labels are `FOREIGN`. Power-line ghosts are `POWER`; completed power lines have no list API (subnets via `power_control.grids()`).

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
| Mining drill | surveyed `MiningSite` whose `drill_id()` is the machine |

A grid with no placeable member is skipped (debug log). Links = Kruskal MST over the nearest-tile distance between footprints of different components (`edge_slice()` in atomic batches of `PAIR_CHUNK` box pairs, `pair_segments()`). **No grid hangs on a field structure**: a field structure in a grid with other placed members is a *shared* end. A link ending there also wires that footprint's perimeter (`ring_legs()`, `RING_PIECES` = 12 pieces). Every line feeding the structure crosses a perimeter tile, so deconstructing the structure keeps the grid whole. The ring pieces count into the link's MST cost, so an outpost wins unless the shared structure is more than 12 tiles nearer. A lone field structure (its own grid) is a leaf: no ring. Existing lines end on a footprint edge or corner tile (confirmed in the save: `exotic_gas_cap_8`, centre tile (-69,-64), line on (-68,-63)), so edge tiles connect.

Each pass queues the cheapest missing links as `plan_power_line()` between the two nearest footprint tiles (tile centres), plus the ring legs, as one all-or-nothing route; on `blocked`/`invalid_route` the two explicit L elbows are tried (two legs, all-or-nothing: a rejected second leg cancels the first). A link the game rejects, or that creates no job while the grids stay apart, is not retried until the script restarts. A link needs `power_line_segment` ≥ its cost (tile distance + ring pieces) in the Inventory. Completed power lines are not visible to scripts (no list API; `list_pipes()` covers gas/liquid only); the ledger (§11d) supplies them. Ledger tiles are assigned to a grid by flooding over 4-neighbouring power tiles from the power tiles inside each grid's footprints (`flood_init()`/`flood_step()`, atomic in `FLOOD_STEP_TILES` slices); a tile two grids reach is contested and dropped, an unreached one ignored. Each grid's tiles become horizontal 1×n run boxes (`line_runs()`, member `line`, never ringed), so a link prefers ending on an existing line. `pair_segments()` pairs only boxes of different grids.

The pass waits while any power-line job is open: completed lines have no list API, so grids only show the link once it is built. Plan-ahead lines of ours (`autoplay.planned` prio `PLAN_AHEAD_PRIO`) are the exception: they do not hold up urgent links.

**Urgent vs plan-ahead links** (§11g). A grid whose every member is a built fluid extractor that `supply_tiers.urgent_producers()` leaves out is *deferred*. `split_links()`: the MST over the other grids gives the urgent links (minus links rejected this run); only when none is left, the MST over all grids gives the plan-ahead links. One plan-ahead link at a time, at `PLAN_AHEAD_PRIO`, needing its pieces plus `PLAN_AHEAD_RESERVE` in stock: whole when its cost fits `PLAN_AHEAD_MAX_PIECES`, else the first `PLAN_AHEAD_MAX_PIECES` pieces of an L from the non-deferred end (`grid_geom.capped_l_routes()`, x-first then y-first). Once built and recorded in the ledger, that stub belongs to the grid and the next chunk starts from it. An urgent link that costs more than the stock (the construction stock target can be lower than one link) is built the same way: when no urgent link fits, the first one short on stock gets an L chunk of everything in stock at normal priority, once the stock reaches the link's cost or the construction stock target (`site_supply.construction_stock_levels()`), whichever is lower. So the Constructor is not sent out for the few pieces crafted since the last link. While it waits, the missing pieces are a rush (`site_supply.set_construction_rush()`): the need level rises to that bar, so Fabricators craft them at `NEED`, not in idle time. Pass outcomes: `queued` (urgent link), `ahead` (plan-ahead chunk), `waiting`, `joined` (nothing urgent to join; plan-ahead blocked by stock counts as joined), `error`.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `MAX_LINKS_PER_PASS` | 1 | power links queued per pass |
| `RING_PIECES` | 12 | pieces around a 4×4 footprint perimeter; extra MST cost of a shared field-structure end |
| `PAIR_CHUNK` | 50 | footprint pairs per atomic edge batch (~3,500 operations worst) |
| `FLOOD_STEP_TILES` | 30 | ledger tiles per atomic `flood_step()` (~3,100 operations worst) |
| `PASS_SLEEP_S` (`planner_loop.py`) | 60 | seconds between passes while work is open |
| `FIRST_PASS_DELAY_S` (`planner_loop.py`) | 1 | one yield before the first pass: a fresh script's start runs as one capped execution, and the first pass is the heaviest |

Run loop (`autoplay/lib/planner_loop.py`, entrypoint `autoplay/infra_planner_automation.py`): founding pass (§11j), building pass (§11l), read `Topology`, prune `autoplay.planned`, ledger upkeep (§11d), power pass, fluid pass (§11e, plan-ahead only when power is `joined`), extractor pass (§11g, plan-ahead only when power is `joined` and fluid `done`); each phase ends with a debug `Pass: <phase> (<sim s>)` line; the loop never ends: once power reports `joined`, fluid `done` and extractors `done` it runs only the founding pass (marker reads; a full pass every `REPLAN_TICKS`) and the building pass every `WATCH_SLEEP_S` = 300 s, and the infrastructure passes again after a designation was written (`changed`).

## §11c Blueprint queue (`autoplay/lib/blueprint_queue.py`)

The planner's only writer of blueprints: `queue_power_route()` (power legs), `queue_pipe_route()` (§11e) and `queue_structure()` (one extractor, `"site"` = its site id, `"seg"` = `[x, y, x, y]`). `job_need(id)` reads an open job's `required_item`/`required_count`; `open_planned(kinds, prio)` filters `autoplay.planned`. `cancel()` also drops the jobs' `construction.priority` entries. Archive `autoplay.planned` = `{blueprint_id: {"k": kind, "f": fluid | "power" | None, "p": prio, "seg": [x1, y1, x2, y2] | None, "site": id | None}}`; entries are dropped once their job is no longer pending/active/paused (skipped when a job list could not be read). Jobs with a prio other than `construction_plan.DEFAULT_PRIORITY` also get a `construction.priority` entry.

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

**Terminals.** Producers = extractors on surveyed sites (water/oil pumps `pump_id()`, thermal caps for steam, exotic caps/taps by deposit `fluid()`) and outposts whose roles list the fluid under `"out"` (condenser water, Refiner outputs). Consumers = outposts whose roles list it under `"in"`; an outpost on both sides is one producer terminal. **Planned producers** (`fluid_outlook.planned_producers()`) are terminals too, so plan-ahead routes reach a site before its extractor stands: discovered fluid sites (`journal.discovered_sites()`, surveyed or not, fluid known) with no extractor (named `ghost:<id>` when an extractor ghost is on it, else `site:<id>`), and unresolved sonar contacts in `survey.unsupported_targets` that `contact_inference` types as exactly one of water, oil or thermal (biome at the contact is a hard rule; `contact:<x>_<y>`, skipped within `MATCH_TILES` of a discovered site). They are walls for every other fluid like any extractor footprint, and always plan-ahead. Producers sort built first, then planned by footprint gap to the nearest consumer of their fluid. **Observed fluid roles** (`OBSERVED_FLUID_ROLES` = `biomass_mixer`): an outpost where that role's building stands takes its fluids even without the designation, so `liquifier_<biome>` outposts get piped to the Mixer's outpost; `autoplay.outpost_roles` is not changed. Only fluids some outpost takes are routed; one without any producer, built or planned, is skipped (`no producer` debug line). A terminal is connected when one of its footprint tiles carries the fluid.

**Fluid priority** (`fluid_outlook.fluid_priority()`). Per fluid F: need = consumer outposts whose role taking F is built (`autoplay_roles.observed()`; a role outside `ROLE_CATALOG` always counts as built) + `FORECAST_WEIGHT` × consumers designated only; supply = built field producers + outposts supplying F; score = phase weight × need / (1 + supply). Highest first, ties in `FLUID_ORDER`, then by name. Phase = `early` before the mining-drill phase (`upgrade_phase_reached()`), else `late`; weights in `PHASE_FLUID_WEIGHTS` (default 1.0 per fluid). The order is in the `order [...]` debug line.

**Route.** Per pass at most `MAX_ROUTES_PER_PASS` routes, fluids in priority order. A* from every tile carrying the fluid (reused for free) to the free footprint tiles of all unconnected terminals; the route stops on the first footprint tile it reaches, so it takes one port. With no network yet, the first producer (by id) with a free tile is the source and only consumer outposts are goals. `path_plan()` steps go out via `blueprint_queue.queue_pipe_route()` (§11c). A route the game rejects, or a search that finds no path, marks its terminals failed until the script restarts. Stock gate: `<medium>_pipe_segment` ≥ route pieces and `<medium>_pipe_bridge` ≥ bridges, else the pass reports `waiting`.

**Walls and soft tiles.** Other networks of the medium are walls (bridgeable). Footprints of other outposts, drills and ghosts are walls; an extractor footprint (built or planned producer) is a wall only for pipes of its fluid's medium: gas passes a water/oil pump, liquid a thermal cap (no fluid collision; `foreign_footprints(..., medium, media)`). **Contact hazards** (`fluid_outlook.read_hazards()`) are walls the same way: unscanned map contacts (`points_of_interest()`, not `scanned`, not on a discovered site) whose kinds (`possible_kinds()` of their `survey.unsupported_targets` entry, else the biome's fluid kind in `BIOME_KINDS`) may hold a fluid (`KIND_MEDIA`: thermal gas, water/oil liquid, exotic both), and discovered exotic deposits with no cap and no known fluid (`site_hazards()`: the site's `medium()`, else both). The reads run in atomic slices (`TAKEN_CHUNK` site rows, `POINT_CHUNK` contacts, `HAZARD_CHUNK` = 5 classified contacts at ~650 operations each, `SITE_HAZARD_CHUNK` sites); `foreign_footprints()`, `beside_tiles()` and the rings too (`FOREIGN_CHUNK`, `BESIDE_CHUNK`, `RING_CHUNK`). Soft (`SOFT_TILE_COST`): the outer ring of every outpost footprint and the ring just outside it (`grid_geom.outpost_rings()`: connection points and their way in), so a route goes straight in rather than along or around them; and the tiles beside another network (pipe spacing below).

**Ports.** A footprint with no free tile on a medium is *full* for it (logged, skipped). An outpost keeps its last free tiles for earlier fluids of its role order that still need a port and have a producer (*reserved*). `autoplay.port_status` = `{outpost_id: {"gas": [labels], "liquid": [labels], "full": [media]}}` for consumer outposts, rewritten only on change.

**Storage buffer.** An outpost designated a `STORAGE_BUFFER_ROLES` role (`storage`; `autoplay_roles.keeps_buffer()`) takes many fluids, each on its own lane. The tiles within `STORAGE_BUFFER_TILES` = 4 of its footprint (`storage_buffer_tiles()`, every structure footprint left out) are walls for a fluid that outpost does not take, and soft tiles (`SOFT_TILE_COST`) for one it takes (`buffer_split()`). When the walled buffer leaves no route (a producer stands inside it), the route is searched again without the walls (debug line).

**Pipe spacing.** `find_route()` makes the tiles beside another network's pipe of the same medium (`grid_geom.beside_tiles()`) soft, so a new line keeps one free tile from it: a later line can bridge the first, step one tile and bridge the second (bridges cannot land on a bridge). A short side-by-side stretch, or a crossing's bridge ends, may still use them.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `MAX_ROUTES_PER_PASS` | 1 | fluid routes queued per pass |
| `LABEL_CHUNK` | 200 | occupancy tiles per atomic `label_slice()` (~3,400 operations worst) |
| `FLUID_ORDER` (`fluid_outlook`) | water, oil, steam | tie order of the fluid priority; other fluids follow by name |
| `FORECAST_WEIGHT` (`fluid_outlook`) | 0.5 | need counted per consumer whose role is designated but not built |
| `PHASE_FLUID_WEIGHTS` (`fluid_outlook`) | `{"early": {}, "late": {}}` | fluid weight per phase (unlisted: 1.0) |
| `OBSERVED_FLUID_ROLES` (`fluid_outlook`) | `biomass_mixer` | roles whose fluids follow the building, designated or not |

**Plan-ahead routes** (§11g). Field producers outside `supply_tiers.urgent_producers()` and every planned producer are *deferred*: `route_request(..., deferred)` leaves them out (listed as `deferred`). Only when no fluid has a normal route open or waiting, the power pass is `joined` and no plan-ahead pipe/bridge job of ours is open, one plan-ahead route is planned: same search without the deferred filter, cut by `grid_geom.truncate_steps()` to `PLAN_AHEAD_MAX_PIECES` tiles (a bridge counts 2; one that does not fit is left for the next chunk), queued at `PLAN_AHEAD_PRIO`, needing the pieces plus `PLAN_AHEAD_RESERVE` segments and, with bridges, `PLAN_AHEAD_BRIDGE_RESERVE` bridges spare. The stub is in `autoplay.networks`, so the next chunk continues from it. A normal route that costs more than the stock (the construction stock target can be lower than one route) is built in urgent chunks the same way as an urgent power link: once the segments and bridges in stock reach the route's cost or their construction stock target (`site_supply.construction_stock_levels()`), whichever is lower, and no normal-priority pipe/bridge job of that medium is open (`stock()` does not net queued jobs), `stock_steps()` cuts the route to the stock and queues it at normal priority. While it waits, the missing items are a rush (`site_supply.set_construction_rush()`); the pass clears the rush of every `PIPE_ITEMS` entry no route rushed. Pass outcomes: `queued`, `ahead`, `waiting` (stock, or a plan-ahead or urgent chunk still open), `done`, `error`.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `PLAN_AHEAD_BRIDGE_RESERVE` | 2 | bridges left in stock after a plan-ahead route with bridges |

`queue_pipe_route()` (§11c): one `plan_pipe` per straight run, one `plan_bridge` per bridge, all or nothing. A run that creates fewer jobs than its pieces minus `reusable_pieces()` (consecutive tile pairs both already carrying the fluid) is treated as `short` and the whole route is cancelled. On success, the runs are appended to `autoplay.networks[fluid]`; for a bridge, only its two end tiles are stored (as one-tile runs), because the middle tile belongs to the line it crosses.

## §11k Building executor (`scripts/4_controlpanel/lib/building_ops.py`)
Shared executor of the building planner ([building_planner.md](../plans/building_planner.md)). Jobs in `build.jobs` `{job_id: {kind, state, status, requester, why, tick, ...}}`, stepped by `BuildingOps.step_jobs()`; each state is written before its game call, so a restart resumes.
- `request_deploy(type_id, outpost_id, requester, why, status_key=None, ref=None, kit_id=None)`: `kit` (waits for the kit, `kit_id` or the type id, in Inventory) → `deploying` (stores the type's ids at the outpost; a new id found there on the next step is adopted, no second deploy) → `attach` (`start_script()` on the new machine; with `status_key`, done once it has an entry there) → `done`; a `SCRIPTLESS_TYPES` building (storage, tanks, batteries) is `done` once deployed. `ref` makes the request idempotent.
- `request_upgrade(machine_id, item_id, ...)`: `kit` → `upgrading` (`computer.upgrade()`) → `done`.
- `request_retire(machine_id, ..., handshake=True)`: `emptying` (entry `requested` in `build.retire`; the machine's own script checks `retire_requested(id)`, empties itself, calls `mark_retire_ready(id)`; the job restarts a stopped script) → `undeploying` → `done`. `handshake=False` starts at `undeploying`.
- Status table `classify()`: `ok`; `gone` (`not_found`); `transient` (`TRANSIENT_STATUSES`: retried next step); `kit` (`no_kit`, `item_not_in_inventory`: back to `kit`); anything else `fatal` → `blocked`, status kept.
- `undeploy(machine_id, logger, warned, computer, tag)`: the one `computer.undeploy()` wrapper; transient refusals log at debug, others warn once per machine and status. Used by `plants_retire`, `biomass_retire`, `bio_retire`, `wildlife_planner` and the jobs.

| Constant | Value | Meaning |
|---|---|---|
| `DONE_KEEP_TICKS` | 36,000 (1 sim h) | done/blocked jobs kept for the panel, then pruned |

## §11l Building pass (`autoplay/lib/building_plan.py`, BUILD card `autoplay/build_panel.py`)
Propose-only decider ([building_planner.md](../plans/building_planner.md) phase 3). Per outpost of the `outpost_needs` snapshot (the founding pass's when younger than `PASS_TICKS`):
- **roles**: one building per group a designated role lacks (`role_gaps()`), the first alternative whose kit can be had; the Warehouse group goes to storage.
- **storage** (once the Warehouse kit can be had): `ceil((stock_slots() - standing slots) / per_warehouse)` of `large_warehouse` once its kit is available, else `warehouse`; one where a designated role needs a Warehouse and none stands.
- **retire**: a Refiner whose `refiner.status` entry has `retire` `ready`.
- **focus** (`autoplay/lib/focus_plan.py`): the atmosphere focus. Every full pass reads `game_phase.snapshot()` (and records the history sample), scores each open atmosphere pillar by the research wants on it (`CHAIN_WANTS`: the early unlock chain of unlock_paths.md, plus needs carrying `blocked_by`): `URGENCY_WEIGHT / max(eta_h, ETA_FLOOR_H)` per want (`NO_RATE_ETA_H` when the pillar has no rate yet); with no scoring want the lowest pillar by share of its target gets `EVEN_SCORE` ("even growth"). Writes `autoplay.focus` `{pillar, current, swap, why, scores, mode: research | even | done, tick}` (`pillar`/`current` are `pillar_swap` keys `o2`/`heat`/`pressure`; `current` = the pillar with the most generators standing). A **swap** proposal `focus:<from>:<to>` (kind `swap`) appears when the best pillar differs from the current one, the base is past the early phases (`game_phase.phase_name()` not `cold_boot`/`early`: `early_buyer` owns that order), no swap runs, the best scores at least `SWAP_MARGIN[current]` times the current pillar, in even mode the best lags the current by more than `EVEN_LAG` share points, and the target pack of the current generators' tier (capped at `pillar_swap.MAX_SWAP_TIER`) is in the Shop catalogue or Inventory (Mk IV packs are craft-only). Approve on the BUILD card calls `pillar_swap.request_swap()`; the row is `queued` until the swap stops running. The card's first line shows the focus.
- **providers** (`autoplay/lib/build_providers.py`, `PROVIDERS` order, over `building_plan.build_context()`: grids from `power_control.grids()` with `power.grid_phase()` / `reserve_fraction()`, generators and Smelters / Fabricators with tiers, Shop prices, pack stock, fleet counts from `fleet.status` (name prefix + published role), open survey requests, the oldest pickup age, Smelter ores without a drill, Seismic work, Pioneer miners by `HOME_BASE` (`miners`: count with queued jobs, the newest one's first-seen tick, the oldest idle tick; `autoplay.miner_latch` `seen` / `idle`), their reach (`mining_reach`, `outpost_mining.mineable_ores_by_outpost()`) and raw ores at `NEED` per outpost (`ore_need`, live=False `outpost_tier_deficits()`, open since `autoplay.miner_latch` `need`; a pass off `NEED` restarts it)):
  - **atmosphere**: for the focus pillar (`autoplay.focus`, no swap pending): a Mk II / Mk III pack in place on up to `UPGRADES_PER_PASS` generators of the lowest tier whose pack is in the Shop or Inventory; else `n` generators at the host with the most free slots (home first, then a `terraform` host or one holding generators), `n` = free slots − `KEEP_FREE_SLOTS`, cut to the grid headroom (`(generated − consumed − POWER_MARGIN_W) / GENERATOR_DRAW_W[1]`); zero room → one blocked `power:` proposal.
  - **power**: a grid with `generated < consumed` and reserve under `RESERVE_LOW` gets one generator by `generator_for()` (`reactor` on a reactor grid, `oil_generator` on a steam / oil grid whose outposts hold a Liquid Tank, else `steam_turbine`, `solar_generator` first) at the grid outpost with room; a grid with Smelters / Fabricators and a bank under `BATTERY_FLOOR_WH` gets batteries (`battery_large` when its kit is available, `BATTERY_WH` sizes); a `power` / `condenser` host without a tank of its produced fluid gets one (`FLUID_TANK`).
  - **factory**: a Smelter / Fabricator group busy ≥ `BUSY_SHARE` (`BUSY_SHARE_EXTRA` past `MAX_FACTORY_HOSTS`, §11h `activity`): packs (`MACHINE_PACKS` Mk II / III) on up to `UPGRADES_PER_PASS` lowest-tier machines first, else one more machine at the host off home with the most room.
  - **kits** (by research in the phase snapshot): `SEED_MAKERS` Seed Makers at home from `research_seed_maker`; a Drone Depot at every outpost with an item role or a Smelter / Fabricator / Warehouse once a Depot kit is unlocked, the first Drone Service Station at home; the Biomass Mixer at Biosphere; Weather Station per settled biome, `LEAD_CASKS` Lead Casks and the Fuel Assembler once the Nuclear Program is within `LEAD_TICKS["found"]` × 2 (or unlocked); a Steam Condenser at a `power` host from `research_steam_condenser`.
  - **retire**: Storage Bins beside a Warehouse (the bio chain of a finished biome is `lib/bio_retire.py`'s own job); Weather Stations beyond the first while the Nuclear Program is `later` and no `weather_<biome>` is designated; batteries above `BATTERY_FLOOR_WH` + `BATTERY_SURPLUS_WH` on steam / oil grids whose bank also holds that much charge. Retire rows go straight to undeploy (no machine script answers the `build.retire` handshake).
  - **fleet** (`fleet:<kind>:<role>:+|-`, `:<outpost>` appended for a per-outpost row; approve = `fleet_commission.queue_drone()` / `queue_pioneer()` at `BUILD` prio with the row's outpost as `HOME_BASE`, or `fleet_decommission.request_decommission()` of an idle unit of the role (at the row's outpost when set); queued commission jobs count as units, a role with a decommission in flight gets no second `-1`): a scout drone before any extractor drone (a miner want is `blocked: scout first` without one); `MINERS_PER_BIOME` extractor drones per biome with a `bio_` / `liquifier_` role; one hauler drone when the oldest pickup waits `HAUL_BACKLOG_TICKS`; no scout or builder Pioneer retires (an idle one refits, hauler being the fallback, fleet_lifecycle.md §2f-1); a miner Pioneer per outpost (`miner_wants()`) for a raw ore at `NEED` there no drilled site feeds: the first when the outpost has none, more while an ore its miners reach stays open `MINER_BACKLOG_TICKS` (counted from the later of the need and the newest miner) with none idle and none queued, up to `MAX_MINERS_PER_OUTPOST` (`blocked: fleet cap …` at `MAX_PIONEER_MINERS`, `blocked: no surveyed … site` without a site); a miner idle `MINER_IDLE_TICKS` retires while its outpost has more than `MIN_MINERS_PER_OUTPOST`; a miner Pioneer retires once every Smelter ore has a drilled site (else `blocked: no drill on …`), and none is proposed then; Pioneer haulers above `max(MAX_PIONEER_HAULERS, hauler wanted)` (fleet-wide, `wanted` from a fresh `fleet.role_demand`, `hauler_wanted` in the context), or above `SALT_PIONEER_HAULERS` for pump salt once the drone yield switch is on and a hauler drone flies (drones can't load at a pump; haulers float, any idle one retires); a plated (`aftermath`) drone ahead of the Nuclear Program once a Weather Station stands.
- Reserved slots: every full pass counts the open deploys (`approved`, or `queued` with jobs not `done`) into their outpost's `used` and `reserved` `{type_id: n}` (`reserve_open()`), so free slots, hosts and the cap gate see them; the power provider adds reserved batteries to the bank and asks no generator from a grid with a power generator reserved; a queued row keeps its own `blocked`.
- Gates: a deploy over the outpost's capacity while it holds a `PENALIZED_TYPES` machine is `blocked` and can't be approved (`cap_block()`); a deploy with a known draw that leaves less than `POWER_MARGIN_W` on its grid is `blocked: power` (`power_block()`). Ids: `deploy:<outpost>:<type>`, `upgrade:<machine>:<pack>`, `retire:<machine>`, `focus:<from>:<to>`, `fleet:<kind>:<role>:<+|->[:<outpost>]`; an approved retire goes straight to undeploy.
Proposals in `autoplay.build_proposals` (`deploy:<outpost>:<type>` / `retire:<machine>`; status `proposed` → `approved` (BUILD card) → `queued` (building_ops jobs, refs `<id>#<n>`) → removed when done; a blocked job sends it back to `proposed` with the status in `blocked`; `rejected` holds the id). `kit_source`: `inventory` / `available` (Shop or Fabricator) / None. Kits are not bought yet: a queued deploy waits in the job's `kit` state.

| Constant | Value | Meaning |
|---|---|---|
| `PASS_TICKS` | 6,000 (10 sim min) | full provider pass at most this often; jobs step every loop pass |
| `GENERATOR_DRAW_W` / `TIER_DRAW_FACTOR` | O2 8, pressure 7, heat 0 W; ×1 / ×5 / ×20 / ×100 | Mk I draw per generator type (spec `powerDraw`) and the pack multipliers by tier |
| `UPGRADES_PER_PASS` / `KEEP_FREE_SLOTS` | 3 / 1 | pack proposals per type and pass; slots a host keeps when generators fill it |
| `POWER_MARGIN_W` / `RESERVE_LOW` | 20 W / 0.5 | headroom a deploy must leave; reserve under which a deficit asks for a generator |
| `BATTERY_FLOOR_WH` / `BATTERY_SURPLUS_WH` | 1,500 / 2,000 Wh | bank a grid with Smelters / Fabricators keeps; bank above the floor that retires a battery on steam / oil |
| `SEED_MAKERS` / `LEAD_CASKS` / `MINERS_PER_BIOME` / `MAX_PIONEER_HAULERS` / `SALT_PIONEER_HAULERS` | 2 / 2 / 2 / 4 / 2 | phase build-out and fleet counts |
| `HAUL_BACKLOG_TICKS` | 36,000 (1 sim h) | pickup age that asks for a hauler drone |
| `MAX_MINERS_PER_OUTPOST` / `MIN_MINERS_PER_OUTPOST` / `MAX_PIONEER_MINERS` | 4 / 2 / 12 | Pioneer miners per outpost, the idle-retire floor per outpost, all miners |
| `MINER_BACKLOG_TICKS` / `MINER_IDLE_TICKS` | 36,000 (1 sim h) / 72,000 (2 sim h) | open `NEED` ore with busy miners that asks for one more; idle time before a miner above the floor retires |
| `REJECT_HOLD_TICKS` | 864,000 (24 sim h) | a rejected proposal stays out |
| `URGENCY_WEIGHT` | now 3, soon 1, later 0.3 | weight of a research want by its need's urgency |
| `ETA_FLOOR_H` / `NO_RATE_ETA_H` | 1 / 48 | floor of a want's ETA; ETA of a want on a pillar without a rate |
| `EVEN_SCORE` / `EVEN_LAG` | 1 / 10 | even-growth score of the lowest pillar; share points it must lag the current pillar by |
| `SWAP_MARGIN` | pressure 2.0, heat 1.5, o2 1.5 | how far the best pillar must be ahead of the current one (pressure generators ramp up) |
| `MIN_SWAP_SCORE` | 0.25 | score the best pillar needs when the current pillar scores 0 (a `now` want within 12 h) |

## §11m Game phase (`scripts/4_controlpanel/lib/game_phase.py`, `research_thresholds.py`)
One derived phase view for the planners and machine scripts (`docs/plans/building_planner.md` "Phase: one shared, derived module"). Pure predicates over one snapshot: `snapshot(now)` reads `terraforming.pillars()` (`value`, `target`, `next_target`, `progress`, `complete`, `phase` per pillar), `nocturna.total_tp()`, `research.unlocked()` (fallback: `is_unlocked()` over the catalog), `drone_upgrade.upgrade_phase_reached()` (`drills`), the retire modules' done flags (`biomass_complete()`, `plants_complete()`, `wildlife_complete()`) and the `phase.history` rings.
- `nuclear_ahead(snap)`: the Nuclear Program may be planned for (`research_wildlife` or the program itself unlocked); gates the reactor need, the nuclear kits and the plated drone.
- `fronts(snap)`: `atmosphere` until the three atmosphere pillars are complete; `biomass` / `plants` / `wildlife` while their research (`research_biosphere`, `research_plant_terraformer`, `research_wildlife`) is unlocked and the pillar is not complete.
- `phase_name(snap)`: the furthest of `PHASES` = `cold_boot` (before `research_data_archive`), `early` (before `research_custom_panels`), `expansion` (before `research_biosphere`), `biomass`, `plants`, `wildlife` (by the research above), `finish` (all three biosphere pillars done).
- `locked_thresholds(snap, pillar=None)`: `(research_id, pillar, threshold, distance)` rows of research not unlocked whose threshold lies ahead, nearest first. `distance(snap, id)`, `threshold(id)`, `research_eta_ticks(snap, id)`, `eta_ticks(snap, pillar, limit)` from `rate(snap, pillar)`: the slope over the pillar's history ring (`None` under two samples or when the pillar is not rising; `0` when reached).
- `record(snap, now)` (planner loop, once per pass) appends one sample per pillar and `tp` to `phase.history` `{pillar: [[tick, value], ...]}` when the last one is older than `HISTORY_MIN_TICKS`, rings cut to `HISTORY_LEN`.
- `research_thresholds.py` is generated by `devtools/game_update/extract_research.py` from `docs/database/research_catalog.md`: `THRESHOLDS = {research_id: (pillar, threshold, save tech id)}`, `ORDER`, `TECH_TO_RESEARCH`. The research component exposes no thresholds, so the fixed limits come from the catalog; `research.is_unlocked()` stays the truth once reached. Regenerate after a game update (`tests/test_research_thresholds.py` compares module and catalog).

| Constant | Value | Meaning |
|---|---|---|
| `HISTORY_LEN` | 12 | samples kept per pillar in `phase.history` |
| `HISTORY_MIN_TICKS` | 3,000 (5 sim min) | spacing of history samples (12 samples span about 1 sim h) |
