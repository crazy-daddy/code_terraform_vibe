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

`Topology().read()` builds `occ = {layer: {tile: label}}` from `list_pipes()`, the pending/active/paused construction jobs and `autoplay.networks`. Label = the piece's `contents()`; else the planner's own fluid for that tile; else `FOREIGN` (`"?"`). Conflicted pieces and tiles claimed by two labels are `FOREIGN`. Power-line ghosts are `POWER`; completed power lines have no list API (subnets via `power_control.grids()`).

`walls(layer, fluid)` = every tile with another label; `held(layer, fluid)` = tiles of that fluid. `footprint_ports(footprint, layer, fluid)` → `held` / `free` / `others`; the footprint is full for that medium when `held` and `free` are both empty. Gas fluids: `GAS_FLUIDS` (steam, ammonia, swamp_gas, raw/refined sulfur gas and chlorine); every other fluid is a liquid.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `PIPE_CHUNK` | 16 | pipes per atomic read slice (~190 operations each) |
| `JOB_CHUNK` | 20 | jobs per atomic read slice |

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

A grid with no placeable member is skipped (debug log). Links = Kruskal MST over the nearest-tile distance between footprints of different components (`edge_slice()` in atomic batches of `PAIR_CHUNK` box pairs, `pair_segments()`). Each pass queues the shortest missing links as `plan_power_line()` between the two nearest footprint tiles (tile centres); on `blocked`/`invalid_route` the two explicit L elbows are tried (two legs, all-or-nothing: a rejected second leg cancels the first). A link the game rejects, or that creates no job while the grids stay apart, is not retried until the script restarts. A link needs `power_line_segment` ≥ its tile distance in the Inventory.

The pass waits while any power-line job is open: completed lines have no list API, so grids only show the link once it is built.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `MAX_LINKS_PER_PASS` | 1 | power links queued per pass |
| `PAIR_CHUNK` | 50 | footprint pairs per atomic edge batch (~3,500 operations worst) |
| `PASS_SLEEP_S` (`planner_loop.py`) | 60 | seconds between passes while work is open |

Run loop (`autoplay/lib/planner_loop.py`, entrypoint `autoplay/infra_planner_automation.py`): read `Topology`, prune `autoplay.planned`, power pass; the script ends once the pass reports one placed grid.

## §11c Blueprint queue (`autoplay/lib/blueprint_queue.py`)

The planner's only writer of blueprints. Archive `autoplay.planned` = `{blueprint_id: {"k": kind, "f": fluid | "power" | None, "p": prio, "seg": [x1, y1, x2, y2] | None, "site": id | None}}`; entries are dropped once their job is no longer pending/active/paused (skipped when a job list could not be read). Jobs with a prio other than `construction_plan.DEFAULT_PRIORITY` also get a `construction.priority` entry.
