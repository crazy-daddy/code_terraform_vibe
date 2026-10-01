# Autoplay: infrastructure planner (`autoplay/`)

Part of the [AI cheatsheet](../AI_CHEATSHEET.md). Code lives in `autoplay/`, outside the tiered `scripts/` tree; `autoplay/lib/` modules import `scripts/` lib modules, never the reverse.

## §11 Map geometry (`autoplay/lib/grid_geom.py`)

| Fact | Value |
| :--- | :--- |
| Tile size `TILE_M` | 10 m; utility lanes run through tile centres (`…5`) |
| Utility piece | one straight 10 m segment between two neighbouring tile centres; 1 segment item each (`gas_pipe_segment`, `liquid_pipe_segment`, `power_line_segment`) |
| Job `position` of a pipe / power-line piece | segment midpoint, on a tile edge: `(10,-5)` = tiles `(0,-1)`+`(1,-1)` |
| Bridge | 3 tiles along its axis; job `position` = centre tile; 1 `*_bridge` item; job has no axis field |
| Connection rule | same-medium pieces connect only when they share a tile; parallel neighbour lanes stay separate, also inside footprints |
| Layers | gas, liquid and power are independent; power crosses pipes freely |
| Footprint `FOOTPRINT_TILES` | 4×4 tiles (40×40 m) for outposts and field extractors |
| Outpost anchor | `outpost.x/.y` = top-left (outpost at 0,0 covers 0..40) |
| Extractor anchor | centre on its site (site at 50,50 covers 30..70) |
| Clearance | outpost 40 m, POI 20 m (structure placement only; pipes and lines may cross) |
| `plan_pipe` | no L-routing: send axis-aligned runs only, check the job count (= tiles − 1) |
| `plan_power_line` | L-routes off-axis requests itself |

Tiles are packed into one int (`tile_key()`), neighbour = key ± `1` (y) or ± `1<<16` (x).

**Router** (`route_init` / `route_seed` / `route_step` / `route_path`, A* with a goal-bounding-box heuristic): sources cost 0 (an existing network is reused), `blocked` tiles are walls, a `bridgeable` wall tile may be hopped by a 3-tile bridge when both end tiles are free, `soft` tiles cost extra. `path_plan()` turns a path into `("run", a, b)` / `("bridge", middle, axis)` build steps.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `STEP_COST` | 1 | per tile |
| `BRIDGE_COST` | 6 | per bridge hop (instead of 2 steps) |
| `SOFT_TILE_COST` | 4 | extra per soft tile (another site's footprint) |
| `ROUTE_MAX_NODES` | 20000 | expanded tiles before giving up |
| `ROUTE_STEP_NODES` | 12 | tiles per atomic `route_step()` (~280 operations each) |
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
