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
| Mining drill | `drill.positions` archive (`lib/drill_sites.py`; drills expose no position) |

A grid with no placeable member is skipped (debug log). Links = Kruskal MST over the nearest-tile distance between footprints of different components (`edge_slice()` in atomic batches of `PAIR_CHUNK` box pairs, `pair_segments()`). **No grid hangs on a field structure**: a field structure in a grid with other placed members is a *shared* end. A link ending there also wires that footprint's perimeter (`ring_legs()`, `RING_PIECES` = 12 pieces). Every line feeding the structure crosses a perimeter tile, so deconstructing the structure keeps the grid whole. The ring pieces count into the link's MST cost, so an outpost wins unless the shared structure is more than 12 tiles nearer. A lone field structure (its own grid) is a leaf: no ring. Existing lines end on a footprint edge or corner tile (confirmed in the save: `exotic_gas_cap_8`, centre tile (-69,-64), line on (-68,-63)), so edge tiles connect.

Each pass queues the cheapest missing links as `plan_power_line()` between the two nearest footprint tiles (tile centres), plus the ring legs, as one all-or-nothing route; on `blocked`/`invalid_route` the two explicit L elbows are tried (two legs, all-or-nothing: a rejected second leg cancels the first). A link the game rejects, or that creates no job while the grids stay apart, is not retried until the script restarts. A link needs `power_line_segment` ≥ its cost (tile distance + ring pieces) in the Inventory. Completed power lines are not visible to scripts (no list API; `list_pipes()` covers gas/liquid only); the ledger (§11d) supplies them. Ledger tiles are assigned to a grid by flooding over 4-neighbouring power tiles from the power tiles inside each grid's footprints (`flood_init()`/`flood_step()`, atomic in `FLOOD_STEP_TILES` slices); a tile two grids reach is contested and dropped, an unreached one ignored. Each grid's tiles become horizontal 1×n run boxes (`line_runs()`, member `line`, never ringed), so a link prefers ending on an existing line. `pair_segments()` pairs only boxes of different grids.

The pass waits while any power-line job is open: completed lines have no list API, so grids only show the link once it is built. Plan-ahead lines of ours (`autoplay.planned` prio `PLAN_AHEAD_PRIO`) are the exception: they do not hold up urgent links.

**Urgent vs plan-ahead links** (§11g). A grid whose every member is a built fluid extractor that `supply_tiers.urgent_producers()` leaves out is *deferred*. `split_links()`: the MST over the other grids gives the urgent links (minus links rejected this run); only when none is left, the MST over all grids gives the plan-ahead links. One plan-ahead link at a time, at `PLAN_AHEAD_PRIO`, needing its pieces plus `PLAN_AHEAD_RESERVE` in stock: whole when its cost fits `PLAN_AHEAD_MAX_PIECES`, else the first `PLAN_AHEAD_MAX_PIECES` pieces of an L from the non-deferred end (`grid_geom.capped_l_routes()`, x-first then y-first). Once built and recorded in the ledger, that stub belongs to the grid and the next chunk starts from it. Pass outcomes: `queued` (urgent link), `ahead` (plan-ahead chunk), `waiting`, `joined` (nothing urgent to join; plan-ahead blocked by stock counts as joined), `error`.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `MAX_LINKS_PER_PASS` | 1 | power links queued per pass |
| `RING_PIECES` | 12 | pieces around a 4×4 footprint perimeter; extra MST cost of a shared field-structure end |
| `PAIR_CHUNK` | 50 | footprint pairs per atomic edge batch (~3,500 operations worst) |
| `FLOOD_STEP_TILES` | 30 | ledger tiles per atomic `flood_step()` (~3,100 operations worst) |
| `PASS_SLEEP_S` (`planner_loop.py`) | 60 | seconds between passes while work is open |

Run loop (`autoplay/lib/planner_loop.py`, entrypoint `autoplay/infra_planner_automation.py`): founding pass (§11j), read `Topology`, prune `autoplay.planned`, ledger upkeep (§11d), power pass, fluid pass (§11e, plan-ahead only when power is `joined`), extractor pass (§11g, plan-ahead only when power is `joined` and fluid `done`); each phase ends with a debug `Pass: <phase> (<sim s>)` line; the script ends once power reports `joined`, fluid `done` and extractors `done` and no outpost proposal waits. While proposals wait, the loop only runs the founding pass every `WATCH_SLEEP_S` = 300 s (marker reads; a full pass every `REPLAN_TICKS`), and runs the other passes again after a designation was written (`changed`). `run_founding()` (entrypoint `autoplay/outpost_planner_automation.py`) runs the founding pass alone: a full pass first, then marker watching every `WATCH_SLEEP_S` (full pass when due), ending on `idle` or `locked`; a written designation waits for the next infrastructure planner run. Run only one of the two automations: both own the same proposals and markers.

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

**Terminals.** Producers = extractors on surveyed sites (water/oil pumps `pump_id()`, thermal caps for steam, exotic caps/taps by deposit `fluid()`) and outposts whose roles list the fluid under `"out"` (condenser water, Refiner outputs). Consumers = outposts whose roles list it under `"in"`; an outpost on both sides is one producer terminal. Only fluids some outpost takes are routed; one without any producer is skipped (`no producer` debug line). A terminal is connected when one of its footprint tiles carries the fluid.

**Route.** Per pass at most `MAX_ROUTES_PER_PASS` routes, fluids in `FLUID_ORDER` then by name. A* from every tile carrying the fluid (reused for free) to the free footprint tiles of all unconnected terminals; the route stops on the first footprint tile it reaches, so it takes one port. With no network yet, the first producer (by id) with a free tile is the source and only consumer outposts are goals. `path_plan()` steps go out via `blueprint_queue.queue_pipe_route()` (§11c). A route the game rejects, or a search that finds no path, marks its terminals failed until the script restarts. Stock gate: `<medium>_pipe_segment` ≥ route pieces and `<medium>_pipe_bridge` ≥ bridges, else the pass reports `waiting`.

**Ports.** A footprint with no free tile on a medium is *full* for it (logged, skipped). An outpost keeps its last free tiles for earlier fluids of its role order that still need a port and have a producer (*reserved*). `autoplay.port_status` = `{outpost_id: {"gas": [labels], "liquid": [labels], "full": [media]}}` for consumer outposts, rewritten only on change.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `MAX_ROUTES_PER_PASS` | 1 | fluid routes queued per pass |
| `LABEL_CHUNK` | 200 | occupancy tiles per atomic `label_slice()` (~3,400 operations worst) |
| `FLUID_ORDER` | water, oil, steam | routing order; other fluids follow by name |

**Plan-ahead routes** (§11g). Field producers outside `supply_tiers.urgent_producers()` are *deferred*: `route_request(..., deferred)` leaves them out (listed as `deferred`). Only when no fluid has a normal route open or waiting, the power pass is `joined` and no plan-ahead pipe/bridge job of ours is open, one plan-ahead route is planned: same search without the deferred filter, cut by `grid_geom.truncate_steps()` to `PLAN_AHEAD_MAX_PIECES` tiles (a bridge counts 2; one that does not fit is left for the next chunk), queued at `PLAN_AHEAD_PRIO`, needing the pieces plus `PLAN_AHEAD_RESERVE` segments and, with bridges, `PLAN_AHEAD_BRIDGE_RESERVE` bridges spare. The stub is in `autoplay.networks`, so the next chunk continues from it. Pass outcomes: `queued`, `ahead`, `waiting` (stock, or a plan-ahead chunk still open), `done`, `error`.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `PLAN_AHEAD_BRIDGE_RESERVE` | 2 | bridges left in stock after a plan-ahead route with bridges |

`queue_pipe_route()` (§11c): one `plan_pipe` per straight run, one `plan_bridge` per bridge, all or nothing. A run that creates fewer jobs than its pieces minus `reusable_pieces()` (consecutive tile pairs both already carrying the fluid) is treated as `short` and the whole route is cancelled. On success, the runs are appended to `autoplay.networks[fluid]`; for a bridge, only its two end tiles are stored (as one-tile runs), because the middle tile belongs to the line it crosses.

## §11f Outpost roles (`autoplay/lib/autoplay_roles.py`)

| Key | Shape | Writer |
| :--- | :--- | :--- |
| `autoplay.role_presets` | `{role: {"in": [fluid, ...], "out": [fluid, ...]}}` (a plain list = `"in"` only) | seeded with `DEFAULT_ROLE_PRESETS` when missing; default roles the stored dict lacks are added, operator edits of existing roles kept |
| `autoplay.outpost_roles` | `{outpost_id: role \| [role, ...]}` | operator, and an approved designate proposal (§11j); entries of gone outposts pruned each pass |

Default presets (in → out): `factory` water, oil, steam · `terraform` water, steam · `power` steam, oil · `farm` water · `condenser` steam → water · `reactor` water · `drone_service` oil · `bio_caster` steam, water · `biomass_mixer` the five essences · `refinery` the four raw exotics → sulfur_gas, chlorine, cryofluid, quicksilver · `wildlife` ammonia, swamp_gas, sulfur_gas, chlorine, brine, cryofluid, quicksilver. One-fluid sub-roles: `refinery_<fluid>` (`refinery_quicksilver` = raw_quicksilver → quicksilver) and `wildlife_<fluid>` spread exotics over outposts; `liquifier_<biome>` → `<biome>_essence` (an Essence Liquifier makes its outpost biome's essence); `storage_<fluid>` = that fluid in and out (tanks; the outpost becomes a producer terminal on that network). `fluids_for()` also returns `"supply"`: the `"out"` fluids of source roles; `condenser` (`BACKUP_ROLES`) and `storage_<fluid>` are no source (§11g). Waste Processors have no role (generic sink, wire locally). The home outpost always has `HOME_ROLES` (`farm`: the Harvester field is there) after its own roles. An outpost's fluid order (roles in order, each role's in before its out, duplicates dropped) is its port service order. Example: `{"home": ["wildlife_ammonia"], "outpost_3": ["factory", "refinery_chlorine"]}`.

**Designation vs buildings.** `autoplay.outpost_roles` is the designation (intent) every autoplay pass goes by, also for roles whose buildings are not deployed or not unlocked yet. Machine scripts go by the buildings actually there. `bio_<biome>` presets: none, except `bio_volcanic` = the `bio_caster` fluids.

**Role catalog** (`ROLE_CATALOG`, code-side; fluids stay in the presets). Per role: `buildings` (groups; a group is a type_id or a list of alternatives), `biome` lock, `unique` (max-one-per-outpost machine), `items` (item logistics, needs a Drone Depot), `ore`, `biosites`.

| Role | Buildings | Flags |
| :--- | :--- | :--- |
| `factory` / `smelter` | fabricator / smelter | items |
| `mining` | warehouse or large_warehouse | items, ore |
| `storage` | warehouse or large_warehouse | items (exempt only: may go over the cap) |
| `drone_depot` | drone_station (any size) | |
| `drone_service`, `power`, `condenser`, `reactor`, `terraform`, `biomass_mixer`, `refinery[_<fluid>]` | their machine (power: turbine or oil generator; terraform: O2, pressure or heat) | |
| `wildlife[_<fluid>]` | habitat | items |
| `bio_<biome>` | bio_collector, bio_lab, bio_exchange + the biome's processor (`BIO_PROCESSORS`; frozen has none) | biome, unique, items, biosites |
| `weather_<biome>` | weather_station | biome, unique |
| `liquifier_<biome>` | essence_liquifier | biome, items, biosites |
| `storage_<fluid>` | liquid_tank, gas_tank or bulk_liquid_reservoir | |

Not in the catalog (`farm`, operator roles): fluids only, never observed or missing.

| Function | Answer |
| :--- | :--- |
| `observed(name, type_counts)` / `observed_roles()` | every group has a deployed alternative; `observed_roles()` leaves out `FAMILY_PREFIXES` sub-roles (a tank does not tell which fluid) |
| `role_gaps(designated, type_counts)` | `missing` = designated catalog roles not observed (building planner backlog); `extra` = observed, not designated, and not covered by a designated role's buildings |
| `unlocked(name, available_kits)` | every group has an alternative whose kit (`kit_id()`, `KIT_IDS` where it differs from the type_id) is available; non-catalog roles always |
| `biome_ok()` / `biome_locks()` | biome lock check; more than one lock in a designation = no outpost can host it |
| `bundle_slots(roles, warehouses=True)` | `(counted, penalized)`: one slot per distinct group; penalized = groups with a `PENALIZED_TYPES` machine; `warehouses=False` leaves the Warehouse group out |
| `stock_slots(roles, stock)` | Warehouse slots the roles stock: distinct items of their lists in `stock` (`{role: [item, ...]}`; shared items once), fallback slots for item roles without a list, `FACTORY_BUFFER_SLOTS` for `factory`; `storage` 0 (sized by what it holds) |
| `site_slots(roles, stock, have_slots, per_warehouse)` | `(counted, penalized, warehouses)`: machine groups + Warehouses for the stock beyond `have_slots`; home too (Inventory: 60 slots × 20 at most, no bulk store) |
| `warehouse_slots(type_counts)` | `(slots, buildings)` of the Warehouses standing at an outpost |

**Warehouse stock** (every outpost, home included; one 2000-unit slot per item). Lists come from in-game data (`outpost_needs.read_stock_items()`): `smelter` = ores, outputs and byproducts of the Smelter recipes and `factory` = those outputs (`smelter_stock()`), in two stages. Before the Large Warehouse kit is available: the recipes unlocked now, small Warehouses (a later ore adds one; the Large swap frees slots again). From then on: the end state, so the list counts only once the recipes cover every `RAW_ORE_ITEM_IDS` ore, else `SMELTER_FALLBACK_SLOTS`. Warehouse size `per_warehouse` = 5, 15 once the Large Warehouse kit is available; wildlife roles unlock after it (Plants 2,250,000 vs Biomass 30,000), so they are always sized with 15. `feed` = inputs of the Feed Maker recipes in `wildlife.feed`, once they hold every species' recipe (`feed_stock()`, `wildlife_common.recipe_of()` over `wildlife_data.SPECIES`); `mining` = the need's ores. Otherwise, and for every other role, the fallbacks below.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `WAREHOUSE_SLOTS` | warehouse 5, large_warehouse 15 | slots per building; Large once its kit is available |
| `FACTORY_BUFFER_SLOTS` | 10 | factory slots on top of its ingots (intermediates, finished goods) |
| `STOCK_FALLBACK_SLOTS` | smelter 14 (`SMELTER_FALLBACK_SLOTS`), factory 7, mining 1, feed 30 (`FEED_FALLBACK_SLOTS`), wildlife 16 (`WILDLIFE_FALLBACK_SLOTS`) | a role without a complete list |
| `BIO_STOCK_SLOTS` | 9 | `bio.MAX_LOCAL_BIO_ARTIFACTS` 4 + 5 `outpost_reagents` reagents (a test checks both) |
| `STOCK_PREFIX_SLOTS` | `bio_` `BIO_STOCK_SLOTS`, `liquifier_` 6 (`LIQUIFIER_STOCK_SLOTS`), `wildlife_` 1 | liquifier: one slot per life form of its biome |
| `HOME_RESERVED_ROLES` | farm, plants, feed, wildlife | home keeps its slots for these once wildlife is unlocked (§11h) |

Catalog roles for the home end state: `feed` (feed_maker, items), `plants` (plant_terraformer).

**Overcrowding** (simworker machine table): counted buildings over the outpost cap (`buildings_capacity`) cost 10% each (floor 20%), but only `PENALIZED_TYPES` (production machines, bio chain, generators, Supply Dock, charging station, drone service station, lightning rod) slow down. Warehouses, tanks, batteries, Drone Depots, Lead Cask and Weather Station count but are exempt. Field structures, sensors and vehicles do not count.

## §11g Extractor pass and urgency tiers (`autoplay/lib/extractor_plan.py`, `autoplay/lib/supply_tiers.py`)

**Urgency tiers** (`supply_tiers`, shared by the extractor, fluid and power passes). Consumers of fluid F = outposts whose roles take F (`"in"`) and do not make it. Outposts *supplying* F = those whose role is a source of F (`autoplay_roles.fluids_for()` `"supply"`): a `condenser` (`BACKUP_ROLES`, a backup for water pumps) and `storage_<fluid>` tanks are not, so neither stops a water well from being tapped.

| Tier | Untapped site of fluid F | Prio |
| :--- | :--- | :--- |
| `TIER_NOW` (0) | F has consumers and no supply (no built or planned extractor on an F site, no outpost supplying F): the nearest F site only | 0 |
| `TIER_SOON` (1) | F has consumers and the site is at most `NEAR_TILES` from one of them; also a drill for a Smelter ore without one | 0 |
| `TIER_AHEAD` (2) | F has consumers, site farther away | `PLAN_AHEAD_PRIO` |
| `TIER_SPARE` (3) | no outpost takes F (distance = to the nearest outpost) | `PLAN_AHEAD_PRIO` |

Order: tier, distance (footprint gap in tiles), output (`flow_rate()`, `base_steam_rate()`, `base_rate()`; 0 when the survey level hides it), site id. **Built producers** (`urgent_producers()`): those at most `NEAR_TILES` from a consumer of their fluid are urgent; with none near and no outpost supplying F, the nearest one is. Every other built producer is plan-ahead: the fluid and power passes connect it only in plan-ahead chunks.

**Plan-ahead pacing.** Plan-ahead jobs get `PLAN_AHEAD_PRIO` (Pioneers build them only when no normal job is open), one chunk at a time per pass, at most `PLAN_AHEAD_MAX_PIECES` pieces per pipe route or power link, and only with the items in stock plus `PLAN_AHEAD_RESERVE`. So a plan-ahead blueprint never makes the Fabricator craft for it (the blueprint demand cascade finds its items in stock) and never takes the stock urgent work needs. Stock = `storage.takeable_stock()` at the Constructor's home (`production.construction_site_id()`), what a Pioneer can load there (`blueprint_queue.stock()`). The stock itself comes from the construction stock in `site_supply` ([production_logistics.md](production_logistics.md) §2i-1): segments, gas/liquid bridges and one kit per untapped site, built in Fabricator idle time.

**Extractor pass** (`ExtractorPlanner.run_pass(topo, idle)`). Candidates = untapped fluid sites without an extractor ghost (`supply_tiers.fluid_candidates()`; structure kinds `water_pump`, `oil_pump`, `thermal_cap`, `exotic_gas_cap` on a gas deposit, `exotic_spring_tap` on a liquid one) plus drills. **Drills** need no pipes, and one drill per ore is enough: ores = every raw ore some outpost's Smelter has an unlocked recipe for (`production.smelter_ores()`). For each such ore with no drill on any of its sites (`drill.positions` site or position, or a drill ghost), the site nearest a Smelter outpost (then purest) is a `TIER_SOON` candidate. Drill kind = the lightest that cuts the hardness with its kit in stock, else the lightest that cuts it (`DRILL_KINDS`: `mining_drill` hardness ≤ 1, `mining_drill_industrial` ≤ 3, `mining_drill_heavy` ≤ 4; kit = `<kind>_kit`).

Per pass at most one extractor. Urgent ones go while fewer than `MAX_OPEN_URGENT` urgent extractor jobs of ours are open; an urgent job whose kit is not in stock is still queued (the blueprint demand makes the Fabricator build the kit). A plan-ahead one only when `idle` (power `joined`, fluid `done`), no extractor job of ours is open and its kit is in stock. Kit per kind: `construction_plan.EXTRACTOR_KITS` (pumps deploy from the `water_pump` / `oil_pump` item itself, caps, tap and drills from a `*_kit`); a plan-ahead job whose `required_item` turns out short is cancelled again. `plan_structure()` rejections: `locked` drops the kind for the run; site rejections (`target_claimed`, `occupied`, `clearance`, `too_hard`, ...) drop the site for the run; up to `MAX_TRIES_PER_PASS` sites per pass. Outcomes: `queued`, `waiting` (extractor jobs of ours open, or urgent ones at the cap), `done`, `error`. Pipes and power lines for a new extractor follow in the fluid and power passes once it is built.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `NEAR_TILES` (`supply_tiers`) | 25 | max footprint gap (tiles) from a consumer outpost for an urgent site or producer |
| `PLAN_AHEAD_PRIO` (`supply_tiers`) | 1 | `construction.priority` of plan-ahead jobs |
| `PLAN_AHEAD_MAX_PIECES` (`supply_tiers`) | 40 | pieces per plan-ahead pipe route or power link chunk |
| `PLAN_AHEAD_RESERVE` (`supply_tiers`) | 20 | segments left in stock after a plan-ahead chunk |
| `MAX_OPEN_URGENT` | 2 | urgent extractor jobs of ours open at once |
| `MAX_TRIES_PER_PASS` | 5 | sites tried per pass when the game rejects one |
| `MATCH_TILES` | 1 | a drill or ghost this many tiles or fewer from a site stands on it |

## §11h Outpost needs (`autoplay/lib/outpost_needs.py`)

Need model of the outpost founding planner (`docs/plans/outpost_founding_planner.md`). Pure core over one snapshot (`snapshot()` reads it in game: outposts with designated roles, building type counts, used/capacity and biome; available kits; open Bio Orders per biome from the first Bio Exchange; `required_essences()` of the first Biomass Mixer; Smelter ores; surveyed mineral and fluid sites; fluids the designated roles take; `outpost_mining.resource_assignment_range_m()`).

A role is **covered** by an outpost that designates it or whose buildings make it up (`observed()`) in a biome the role allows. Family sub-roles without a biome lock (`refinery_`, `storage_`, `wildlife_`) are covered only by designation.

| Urgency | Need |
| :--- | :--- |
| `now` | `bio_<biome>`: open Bio Orders of a biome no outpost has the chain for · `liquifier_<biome>`: Biomass phase minimum above the biomes making essence (deficit only; missing biomes with an outpost first, then `BIOMES` order) |
| `soon` | `liquifier_<biome>`: the next missing biome (next phase) · `mining` (+ `ores`): wanted ores whose surveyed sites are all out of range of every outpost (an ore with no surveyed site is survey work, no need) · `smelter`/`factory`: every outpost hosting it is at or over its cap · `refinery_<fluid>`: a designated role takes the refined fluid, a raw deposit is surveyed, nothing refines it |
| `later` | end state: `weather_<biome>` and `liquifier_<biome>` in every biome, `bio_<biome>` where the biome has a processor (not frozen) · any locked role (`unlocked()` False, `locked: True`) |

Earth orders for life forms are no need (drones catch them anywhere). Only `now`/`soon` needs (`PROPOSE_URGENCIES`) reach `plan_hosts()`.

**Merge before founding** (`plan_hosts()`, `host_check()`): each need tries existing outposts by free slots (most first), then id. A host must allow the role's biome, not cover it yet, and keep its counted buildings within `buildings_capacity` when the combined bundle has a penalized machine (`site_slots()`, new Warehouses for the added stock included; exempt-only bundles may go over). Item roles add `drone_depot` when the host has none. Home counts Warehouses like any outpost. It hosts other roles only until wildlife is unlocked (`home_reserved()`: Habitat kit available, a Habitat at home, or a wildlife/feed role designated there); from then on only `HOME_RESERVED_ROLES` and `wildlife_<fluid>` (wildlife lives at home: Forage comes from the home field). `mining` needs a site of each of its ores within range; `refinery_<fluid>` needs a raw deposit of its fluid within `supply_tiers.NEAR_TILES` and never founds (`found: False`). A host that takes a need counts its new roles for the next need. Leftover needs form **founding bundles** (`found_bundles()`): one per biome lock, one for `mining` (ores joined), one for the other roles, each with `drone_depot` when an item role is in it, `slots` (`site_slots()` on an empty outpost) and `over_cap` (a penalized bundle above `FOUNDED_CAPACITY` = 20 buildings).

## §11i Outpost site scoring (`autoplay/lib/outpost_sites.py`)

Where a founding bundle (§11h `found_bundles()`) should go. Decides from in-game data only: `nocturna.points_of_interest()`, `journal.discovered_sites()`, `nocturna.biome_at()`, `get_bounds()`, outposts and outpost ghosts (`read_world()`).

**Placement checks** (`check()`, mirrors `plan_structure("outpost")`): the anchor is the placement square's NW corner, world y grows north; square `PLACE_M` = 20 m (x .. x+20, y-20 .. y), centre (x+10, y-10). Clearance is measured from a point to the `CLEAR_SIDE_M` = 26 m square around the centre: other outposts' centres and outpost ghosts `OUTPOST_CLEARANCE_M` = 40 m, every POI (unknown, scanned, biomass) `POI_CLEARANCE_M` = 20 m. The outpost's biome is the biome at the anchor. Rejections: `out_of_bounds`, `outpost_clearance`, `poi_clearance`, `biome <id>`.

**Knowledge levels**: 1 = POI of kind `unknown`; 2 = kind known (discovered site, a scanned POI kind such as `biomass`, or an unknown POI whose `poi_X_Y` entry in `survey.unsupported_targets` has reason `wrong_scanner`: vehicle sonar cannot classify biomass, `survey_requests.known_biomass()`), details `None`; 3 = surveyed site (ore, purity, hardness, exotic fluid). A water/oil/thermal contact's fluid is known from its kind. Level 1–2 contacts count by expected value; the prior (`priors()`) comes from this save's own scans: kind shares over every contact of known kind, ore and exotic shares over surveyed sites, mean purity factor; flat when nothing is known.

**Score terms** (higher better; `WEIGHTS`):

| Term | Weight | Value |
| :--- | :--- | :--- |
| `ore` | 10 | per bundle ore (the need's ores): surveyed sites within `range_m` (outpost mining range) by purity factor, `HARD_FACTOR` when no available drill kit cuts the hardness, capped at `ORE_CAP` per ore; less-known contacts add P(mineral) × P(ore) × mean purity on top, up to `ORE_CAP` × ores |
| `fluid` | 6 | per wanted field fluid (the bundle roles' `"in"` fluids with a field site: water, oil, steam, raw exotics, not made by the bundle itself): best contact within `NEAR_TILES` × 10 m, closeness 1 .. 0; unknown contacts by chance, up to 1 per fluid |
| `exotic` | 1 | `EXOTIC_VALUE` per raw exotic deposit in fluid reach the bundle does not want (a later `refinery_` role), capped at 1 |
| `biosite` | 2 | biomass contacts within `BIOSITE_RANGE_M` in the bundle's biome (bio-scanned = known, unknown POIs by P(biomass)), share of `BIOSITE_CAP`; only bundles with a `biosites` role |
| `margin` | 4 | biome-locked bundles: share of the `MARGIN_PROBES_M` rings (8 directions) around the anchor holding only its biome |
| `room` | 2 | share of 8 probe points at `ROOM_M` on the map and clear of other outposts |
| `home` | −2 | per km from the home centre |
| `grid` | −3 | per km to the nearest outpost (power line and pipe length) |

`confidence` = share of the resource terms (ore, fluid, exotic, biosite) from known contacts; below `MIN_CONFIDENCE` a row carries `survey: True` (survey trip first). A **stuck** contact adds no guess to score or confidence: an unsurveyed contact whose `poi_X_Y` or `site_<id>` entry in `survey.unsupported_targets` still blocks (`survey_requests.blocked_targets()`: every reason but `wrong_scanner`; a `research_required` entry only while no scan research from `vehicle_claims.SCAN_RESEARCH_IDS` was unlocked after it was recorded). So an area with only contacts the scouts cannot resolve stops asking for a survey; a new scan research makes its `research_required` contacts count as guesses again and the area asks again. `too_hard`/`tier_too_low` entries stay stuck until a scout with a better sonar retries them (`can_attempt_target()`) and clears or rewrites the entry. A bundle with ores keeps only anchors with ore in reach.

**Search** (`rank_sites()`): `CANDIDATE_STEP_M` grid over the map, `check()`ed and scored without margin and room; the best `REFINE_TOP` are re-searched on a `REFINE_STEP_M` grid within `REFINE_RADIUS_M`, the best of those get margin and room (`add_detail()`). Contact values per bundle are computed once (`prepare_want()`, `value_rows()`: one value per term per contact) and bucketed in `CELL_M` cells. Scoring runs in `score_step()` chunks (`run_chunked`) of `STEP_UNITS` work units, resumable mid-anchor and mid-cell, so contact density never overruns a slice. Biome reads are cached per tile for the run.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `CANDIDATE_STEP_M` | 80 | coarse candidate grid |
| `REFINE_STEP_M` / `REFINE_RADIUS_M` / `REFINE_TOP` | 20 / 40 / 5 | refine grid, window half-width, coarse candidates refined |
| `CELL_M` | 150 | contact bucket size |
| `BIOSITE_RANGE_M` | 300 | biomass contacts a bio / liquifier outpost counts |
| `ORE_CAP` / `BIOSITE_CAP` | 2 / 6 | saturation per ore / of biosites |
| `PURITY_FACTOR` | standard 1, rich 1.5, pure 2 | surveyed ore value |
| `HARD_FACTOR` | 0.2 | ore site no available drill cuts (`hardness_limit()` over `extractor_plan.DRILL_KINDS` kits) |
| `EXOTIC_VALUE` | 0.25 | per unwanted raw exotic deposit |
| `MARGIN_PROBES_M` | 20, 40, 80, 160 | biome margin rings |
| `ROOM_M` | 100 | room probe distance |
| `MIN_CONFIDENCE` | 0.5 | below: survey first |
| `FILTER_CHUNK` | 4 | anchors per atomic `check()` slice |
| `VALUE_CHUNK` | 20 | contacts per atomic `value_rows()` slice |
| `DETAIL_CHUNK` | 1 | rows per atomic `add_detail()` slice |
| `STEP_UNITS` | 50 | work units (~45 operations) per `score_step()`: row 3, cell 1, anchor start 4, finish 14 |

Slice costs are measured in `tests/test_autoplay_outpost_sites.py` against `ATOMIC_STEP_BUDGET` on a map several times denser in contacts than a real one.

## §11j Outpost proposals (`autoplay/lib/outpost_plan.py`)

The founding pass, first in the run loop: `outpost_needs` needs and hosts (§11h) and `outpost_sites` sites (§11i) become at most `MAX_PROPOSALS` = 5 proposals, each a map marker the operator answers. Nothing is bought or queued: an approved `found` proposal stays `approved`.

| Key | Shape | Writer |
| :--- | :--- | :--- |
| `autoplay.outpost_proposals` | `{proposal_id: {"id", "kind": "found" \| "designate", "outpost", "x", "y", "biome", "lock", "roles", "needs", "ores", "urgency", "why": [...], "score", "confidence", "survey", "over_cap", "price", "status": "proposed" \| "approved" \| "built" \| "rejected", "ok", "moved", "blocked", "placed", "tick"}}` | founding pass, rewritten only on change |
| `autoplay.survey_requests` | `{proposal_id: {"x", "y", "radius", "why"}}` | founding pass (`survey_areas()`), rewritten only on change; read by the ground scout (`vehicle_survey.survey_known_pois()`) and the drone scout (`drone_scout._scan_candidates()`) |

**Survey requests** (`lib/survey_requests.py`): every open found proposal with `survey` (confidence under `MIN_CONFIDENCE`) asks for its area: centre of its placement square, radius = its bundle's widest scoring range (`prepare_want()` `radius`; `BIOSITE_RANGE_M` before the want is prepared). Both scouts put candidates inside any request area first (`requested_first()`), keeping their own nearest-first order within each part, and log the count in their candidate debug line. A request goes when its proposal stops wanting a survey (re-rank after the scans raise confidence), is built, rejected or dropped. Contacts the scouts cannot resolve stay skipped by them and count as stuck in scoring (§11i), so such an area raises confidence and its request goes.

Proposal ids: `d-<outpost>` (designate, on the outpost's anchor, price 0) and `f-<biome lock | mining | general>` (one per founding bundle, at its best ranked site; price = the Shop catalogue `cost` of `outpost_kit`, which already counts every kit owned). Order: operator OK first, then urgency, designate before found, score. A rejected entry stays under `<id>~<tick>` for `REJECT_HOLD_TICKS` (newest `MAX_REJECTED` = 10): a rejected designation's (role, outpost) pairs go to the need snapshot as `"refused"` (`host_check()` skips them, so the need tries the next host or a founding); a rejected site holds anchors within `REJECT_RADIUS_M` for the same bundle.

**Markers** (id `autoplay.outpost.<proposal_id>`, label `Outpost Suggestion`, icon `flag` found / `star` designate, color `accent` / `violet`, `warning` when blocked, `success` when approved; note = roles, urgency and reasons, price, score and confidence, then what blocks it or how to approve, at most 240 characters):
- **Approve:** add the word `OK` to the label (any case). Approval needs no blocker: placement failure (`check()`), pending re-check, `survey` (confidence under `MIN_CONFIDENCE`), `over_cap`. The OK label is re-read each pass, so a blocker cleared later approves then. An approved designate writes its roles into `autoplay.outpost_roles` at once (status `built`, marker removed).
- **Move:** a found marker dragged more than `MOVE_EPS_M` gives the new anchor, kept from then on; it is re-checked and re-scored (`recheck()`), a failure goes into the note. A dragged designate marker is put back.
- **Reject:** delete the marker (only markers the planner placed count; a failed `markers.list()` skips the pass).
- The planner places a marker only when its fields differ from what it reads back, keeps an operator label holding OK, and removes markers of proposals no longer open.

Full pass (needs, hosts, merge) every pass while the other passes work, else every `REPLAN_TICKS`; sites are re-ranked only when the founding bundles change or after `RERANK_TICKS`. Every open found proposal gets `check()` on a full pass, a dragged one also in watch mode. Outcomes: `locked` (no Map Markers), `idle`, `waiting`, `changed`.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `MAX_PROPOSALS` / `MAX_REJECTED` | 5 / 10 | open proposals / rejected entries on hold |
| `REJECT_HOLD_TICKS` | 864,000 (24 sim h) | hold of a rejected proposal |
| `REJECT_RADIUS_M` | 100 | anchors a rejected site holds |
| `REPLAN_TICKS` / `RERANK_TICKS` | 6,000 / 36,000 | full pass in watch mode / site re-rank with unchanged bundles |
| `MOVE_EPS_M` | 0.5 | marker offset that counts as a drag |
