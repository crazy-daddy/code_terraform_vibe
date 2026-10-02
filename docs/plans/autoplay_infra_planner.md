# Plan: `autoplay/` infrastructure planner (extractors, one power grid, per-fluid pipe networks)

## Context
Today every map structure, pipe and power line is placed by hand in Plan Mode; Pioneers
(`lib/pioneer.py` `run_construction_loop()`) only *execute* whatever sits in the
`construction_blueprint` queue. The autoplayer should own the map's infrastructure:

1. place extractors (Mining Drills, Water Pumps on water wells, Oil Pumps on oil wells),
2. keep every outpost and field extractor on **one power subnet**,
3. lay **one pipe network per fluid**, connecting the producers of a fluid to the outposts whose
   role needs it, never letting two fluids' networks touch (touching same-medium pipe merges
   them into one component → conflict, flow halts — `docs/guide/infrastructure_and_pipes.md`).

Decisions taken with the user:
- Outpost roles: **named presets set by the operator** now (archive), autoplayer-chosen later.
- Autonomy: **queue blueprints directly** (no dry-run gate), stock-gated.
- Extractors: **demand-driven first**; when idle, **plan ahead** (e.g. pipe every water well)
  as **low-priority** blueprints → needs a blueprint priority system the Pioneer loop honors.
- Outposts can be undeployed, so CLAUDE.md rule 5 (no auto-founding) is dropped in this change.
  Planning outposts is still **out of scope** here: this helper uses only the drill/pump kinds.
- Crossing another network of the same medium always goes over a **bridge**.
- Code lives in a new top-level `autoplay/` folder, not `scripts/`.

## Game facts this relies on (docs)
- `construction_blueprint.plan_structure(kind,x,y)` kinds incl. `water_pump`, `oil_pump`,
  `mining_drill[_industrial|_heavy]`; snaps to the surveyed feature; `target_claimed`,
  `too_hard`, `occupied`, `clearance` rejections. `plan_pipe(medium|fluid_id, x1,y1,x2,y2)`,
  `plan_power_line(...)` (L-elbow, reuses existing pieces), `plan_bridge(medium,x,y,axis)`
  (3-tile overpass, perpendicular line under middle stays separate). `cancel(id)`.
- **Footprints (10 m tiles).** Outposts and field extractors are both 40×40 m (4×4 tiles),
  but anchored differently: outpost `x/y` = **top-left** (outpost at 0,0 spans 0..40);
  extractor = **centre** on its POI (extractor at 50,50 spans 30..70). Internal outpost
  machines are not on the map; their utilities reach them through the outpost footprint.
- **Inside a footprint, pipes still merge on contact**, like anywhere on the map. Only pipes
  that do not touch inside the footprint stay separate. So each fluid network needs its own
  non-touching set of footprint tiles per medium → an outpost can receive only a limited
  number of distinct gas and of distinct liquid networks (gas and liquid share tiles freely).
  Same holds for extractor footprints (one network per extractor in practice).
- Sites: `journal.surveyed_sites("nocturna")` (`MiningSite.item_id/.hardness/.purity`,
  `WaterWell/OilWell.yield_tier/.flow_rate`, pumps expose `pump_id()`).
- Topology reads: `list_pipes()` → `Pipe.start()/end()/type()/contents()/is_complete()`;
  `power_control.grids()` → `PowerGrid.outpost_ids/machine_ids` (subnet membership is free).
- Gas vs liquid vs power are separate layers; only **same-medium** contact merges.
- **Pipes have no fluid of their own** (user, confirmed in simworker `tre()`): `plan_pipe(fluid_id, ...)`
  keeps only the medium; contents come from the `connect()` relationships routed through a component.
  There is no "oil pipe": keeping fluids apart is entirely the planner's job.
- **Fluids split over components** (user): between two endpoints the game assigns one fluid per
  component reaching both; 2 components carry 2 fluids, a 3rd fluid there conflicts on `connect()`.
  So a network may only touch its own fluid's terminals: foreign footprints are walls (not soft).
- Outpost clearance 40 m, POI clearance 20 m (`simworker` `plan.outpostClearanceM`) — applies
  to placing structures only; pipes and wires may cross it (confirmed by hand).

## Layout
```
autoplay/
  infra_planner_automation.py  thin entrypoint, Automation role (calls planner_loop.run_planner())
  lib/
    planner_loop.py       run loop: one pass per PASS_SLEEP_S, ends when nothing to do
    autoplay_roles.py     role presets + outpost→fluids resolution
    grid_geom.py          pure: tile snapping, segment↔tile sets, Manhattan/L routes, A* on tiles
    infra_topology.py     reads list_pipes()/pending constructions/power grids → occupancy per layer+fluid
    extractor_plan.py     which sites get which extractor (demand pass, plan-ahead pass)
    power_plan.py         join power subnets (MST over subnet anchors) + wire new extractors
    fluid_plan.py         per-fluid network: producers + role outposts → tree, avoid other fluids, bridges
    blueprint_queue.py    plan_* wrappers, budget/stock gate, records ownership + priority + fluid
```
**Save-agnostic first**: built for future saves, not tuned to this one. Everything comes
from runtime discovery (outposts, sites, grids, pipes, unlocked tech, kits in Inventory);
no save-specific ids, coordinates or counts in code or defaults. It must work from an
empty map (first well, first line) as well as on a crowded one like this save.
Same conventions as `scripts/` code (game imports only, one-line imports, `swallowed()`,
`TreeConsole` start/end blocks, `reset_all()` in run loop, one dict per concern in archive).
Pure modules (`grid_geom`, route/tree math) take plain data so CPython tests cover them.

## Archive keys (one dict per concern)
- `autoplay.role_presets` `{role: [fluid_id, ...]}` — seeded with defaults
  (e.g. `factory: [water, steam]`, `steam_hub: [steam]`, `wildlife: [...]`), operator-editable.
- `autoplay.outpost_roles` `{outpost_id: role | [role, ...]}` — operator-set; pruned for gone outposts.
- `autoplay.planned` `{blueprint_id: {"k": kind, "f": fluid|"power"|None, "p": prio, "seg": [x1,y1,x2,y2]|None, "site": id|None}}`
  — what the planner queued; pruned when the job leaves pending/active/paused.
- `autoplay.networks` `{fluid_id: [[x1,y1,x2,y2], ...]}` — completed routes we own, so a
  ghost/empty pipe's fluid is known before `contents()` latches. Bounded: segments only, merged collinear.
- `autoplay.port_status` `{outpost_id: {"gas": [fluid, ...], "liquid": [...], "full": [medium, ...]}}`
  — which networks enter each outpost and which media have no port left.
- `construction.priority` `{blueprint_id: int}` — shared, read by Pioneers (0 = normal, 1 = plan-ahead). Separate from `autoplay.*` because operators/other planners may set it too.

## Algorithms
**Roles → demand.** `fluids_needed(outpost)` = union of its roles' preset fluids. Fluid
producers = pumps (water/oil), thermal caps (steam), and later refiners/taps; read from
`outpost_network` + `surveyed_sites()` (`pump_id()` to see which wells are already tapped).

**Occupancy.** Snap every `list_pipes()` piece and every pending pipe/power job to tiles →
`occ[layer][tile] = fluid` (layer = gas/liquid/power; fluid from `contents()`, else
`autoplay.networks`, else `"?"` foreign). Foreign tiles are treated as walls for every fluid.
Footprints come from `grid_geom.outpost_tiles(x, y)` (top-left anchor) and
`grid_geom.extractor_tiles(x, y)` (centre anchor) — both 4×4. Routes may pass through
POIs and clearance rings, but a fluid route never enters the footprint of an outpost or field
structure that is not a terminal of its fluid (it would give that site a component a second
relationship could pick up); inside a terminal footprint the same "never touch another
same-medium network" rule applies as outside.

**Footprint ports.** `infra_topology.footprint_ports(footprint, occ, medium)` = which
footprint tiles each existing network already holds, and which free tiles a new network
could enter on without touching any other same-medium network's tiles there. A route ends on
the first such tile it reaches. `fluid_plan` reserves the tile before planning; when no free
non-touching tile is left, the outpost is **full for that medium**: log it, skip that
fluid there, and write it to `autoplay.port_status` so the panel/operator sees it. Order of
service when an outpost's role wants more fluids than it has ports: role preset order.

**Fluid network (per fluid, deterministic order).** Terminals = producer sites + role outposts
needing that fluid. Grow a tree Prim-style from the existing network's tiles: repeatedly A*
from the current tree to the nearest unconnected terminal on the fluid's medium layer, cost =
length, same-fluid tiles free (reuse). Other-fluid same-medium tiles are never touched;
parallel neighbour lanes stay distinct, so running alongside another network is fine. To cross another same-medium
line, A* takes a 3-tile straight step over it (penalised cost) → emit `plan_bridge` there;
a crossing over a foreign (`"?"`) line is a bridge as well. Gas and liquid ignore each other. Path → collapse into straight runs →
one `plan_pipe` per run (`already_exists` = fine). Medium-separated fluids (gas steam vs
liquid water) ignore each other entirely.

**Power.** Components = `power_control.grids()`; anchors = outpost footprints + field
extractors. MST (Kruskal, Manhattan distance) between components, route each edge with
A* on the power layer, which ignores pipes entirely.
New extractors get a spur from their (centre-anchored) footprint to the nearest grid tile.
Power has no fluid identity, so any contact is fine; power bridges are needed only to cross
a power line that must stay a separate subnet (none in the one-grid goal).

**Extractors.**
- Demand pass (prio 0): ores with deficit from `lib/production.py` (reuse its deficit API,
  imported from the deployed lib) → best surveyed `MiningSite` of that item by
  purity/(distance to grid), hardness ≤ best drill kit in Inventory; wells when a role's
  fluid has no producer or supply (`flow_rate()` sum) < consumers' rated draw.
- Plan-ahead pass (prio 1), only when the demand pass queued nothing: remaining untapped
  water wells within `PLAN_AHEAD_RADIUS_M` of the network, plus their pipe and power spurs.
- Budget per pass: at most `MAX_NEW_JOBS_PER_PASS` blueprints and only if Inventory holds the
  kit (structures) / enough segments for the route (`Construction.required_item/count`
  of the result, cancelled again if stock is short — or pre-checked when item ids are confirmed).

## Changes outside `autoplay/` (generic blueprint priority)
Constraints: these changes stand alone — nothing under `scripts/` imports or knows about
`autoplay/` — and hand-placed Plan Mode blueprints keep working unchanged: a blueprint with
no `construction.priority` entry is prio 0 (normal), so with the key absent or empty the
Pioneer behaves exactly as today. An operator can lower or raise any blueprint, manual or
planned, by editing `construction.priority` in the Data Archive Notebook. The key and its
reader live in the `scripts/` lib (`construction_plan.py`); `autoplay/` only writes it.
- [construction_plan.py](scripts/4_controlpanel/lib/construction_plan.py) `scan_slice()`:
  take a `priorities` dict, sort key becomes `(prio, dist, id, row)`; prio-1 jobs only chosen
  when no prio-0 job is open (not just aboard), and never pre-stocked by `fair_share`/batch
  loading ahead of prio-0 needs. Keep the atomic step budget test green.
- [pioneer.py](scripts/4_controlpanel/lib/pioneer.py) `run_construction_loop()`: read
  `construction.priority` once per scan, prune dead ids.
- [CLAUDE.md](CLAUDE.md) rule 5: drop the outpost-founding ban (outposts can be undeployed);
  keep only a note that outpost planning is not part of the infrastructure planner yet. **Done** (AGENTS.md rule 5 "Outpost Founding").
- Cheatsheet: new section for `autoplay/` constants + archive keys (hub index + topic file,
  e.g. `docs/cheatsheet/production_logistics.md`), and `construction.priority` in `archive_ipc.md`.

## Deployment
`devtools/scripts_sync.py` only knows `scripts/<tier>/`. v1: add `autoplay/` as an extra
source root that deploys only on explicit flag (`--include-autoplay`), so it never ships by
accident; its libs register via the existing `create-library` path. Script slot = one
headless Automation (`infra_planner_automation.py`, role marker `# ct-automation: infra_planner_automation`), no per-machine copies (script-count cost).

## Phases
0. **Probe.** Already confirmed by hand (user, on the map): parallel neighbour lanes stay
   distinct; pipes and wires may run through outposts/POIs and their clearance rings;
   power is its own layer and crosses gas and liquid pipes freely. Item ids from docs:
   `gas_pipe_segment`, `liquid_pipe_segment`, `power_line_segment`, `gas_pipe_bridge`,
   `liquid_pipe_bridge`, `power_line_bridge`, `mining_drill[_industrial|_heavy]_kit`
   (all Fabricator-made → shortages go to the existing Fabricator demand path).
   Probe run done (`automation_3.log`, 2026-10-01) — see **Probe results**. Still open:
   pump kit ids (no untapped surveyed well existed) and why a straight 60 m pipe yielded
   only 2 pieces. Both answered by the first live pass (read `required_item`, compare
   piece count). Record all answers in the cheatsheet.
1. `grid_geom` + `infra_topology` + tests (pure geometry, occupancy from fake pipes). **Done** (`cd09031`, `f1b87ca`).
2. Blueprint priority in `construction_plan`/`pioneer` + tests. **Done** (`3cc91bd`).
3. `power_plan` (join subnets) — lowest risk, first live use. **Done** (`48f8b0d`): `power_plan`, `blueprint_queue` (power only), `planner_loop` + `autoplay/infra_planner_automation.py`, cheatsheet §11b/§11c.
   Not live-tested yet (phase 6 flag now in place). Open on the first live run: does a line ending on an
   extractor footprint's edge tile connect (docs say "use the site coordinates")? If not, the pass warns
   "every piece already exists but the grids stay apart" → switch extractor endpoints to the site centre tile.
   Field power structures without a surveyed site (if any) cannot be placed; their grids are skipped and logged.
3a. **Power-line ledger** (done): scripts cannot list power lines, so
   `construction.power_tiles` holds their tiles. One-off full-map survey by `mark_deconstruct(x, y, "power")`
   probes (`autoplay/lib/power_survey.py`, under a `construction.hold` on deconstruct jobs), then Pioneers
   record every finished power job (`note_power_job()`), the planner re-probes dirty tiles and checks
   vanished jobs. Ledger lines are link ends for the power pass (no ring needed). Ring rule for shared
   field structures: `5bd36e5`. Live check pending (expected: 745 power tiles, 29 probe jobs cancelled;
   `thermal_cap_4` links 2 tiles to the bare line). Details: cheatsheet autoplay.md §11d.
4. `autoplay_roles` + `fluid_plan` (water first, then oil, steam) + conflict tests. **Done**: `autoplay_roles`
   (presets incl. `refinery_<fluid>`/`wildlife_<fluid>` sub-roles, home always `farm`), `fluid_plan` (one route
   per pass, foreign footprints are walls, bridges over other lines, port reservation, `autoplay.port_status`),
   `blueprint_queue.queue_pipe_route()`, cheatsheet §11e/§11f, `tests/test_autoplay_fluid.py`. Not live-tested.
   Open: producers inside outposts (Refiner outputs, condenser water) are not terminals yet, so refined
   exotics only route from common-exotic caps; `autoplay.networks` is never pruned (phase 5b).
5. `extractor_plan` demand pass, then plan-ahead pass at prio 1.
5b. `relic_cleanup` (per-layer deconstruction of dead pipe components).
6. sync flag + docs; TODO.md entry under "Building planner". **Done** (pulled ahead of 4/5): `scripts_sync.py --include-autoplay`
   (`merge_autoplay()`), entrypoint renamed to the Automation role `infra_planner_automation`, docs in
   `docs/cheatsheet/dev_workflow.md`, TODO.md entry links this plan.
   **First live test:** `python devtools/scripts_sync.py once --include-autoplay --apply-libs` (registers and applies
   the 5 autoplay libs), then create an Automation in game; the empty slot takes the planner role (or type
   `# ct-automation: infra_planner_automation` into it). Watch for the Power link line, the ghost on the map,
   and the grid count dropping once the Pioneer built it.

## Probe results (`automation_3.log`, 2026-10-01)
- **Tiles are 10 m, lanes on tile centres (`…5`).** Every job and every `Pipe` is one
  10 m straight piece; a job's `position` is the piece midpoint (e.g. `(10,-5)` = `5..15` at y=-5).
  `list_pipes()` returned **2,075 pieces**, all straight.
- **`plan_pipe` does not L-route.** `(0,0)→(60,40)` gave only 4 vertical pieces at x=5.
  `fluid_plan` therefore always issues **axis-aligned runs** and checks the returned job
  count against `run_length / 10`; a short result is cancelled and its tiles marked blocked.
- `plan_pipe` straight `(0,0)→(60,0)` gave only 2 pieces — cause unknown (blocked tile or
  reuse); the count check above catches it, the first live pass logs the reason.
- **`plan_power_line` L-routes as documented**: 6 horizontal + 4 vertical pieces for the
  same off-axis request. Power runs can be one call per edge.
- **Bridge job**: `kind=liquid_bridge`, item `liquid_pipe_bridge` ×1, one job.
- **Per piece cost**: every piece is 1 segment (`required_count=1`).
- **Power**: field extractors draw power (water pump 4 W, oil pump 0–5 W, thermal cap 3 W,
  exotic cap 30 W, heavy drill 0 W idle), so every one needs a line. This save is already
  one subnet, but the planner targets **future saves**: on a fresh save joining subnets is
  the normal case, so the MST pass is core, not an edge case.
- **Relic pipes**: 400 of 2,075 pieces have `contents() == None` (146 gas, 254 liquid).
  On this save they are leftovers from the essence/Biomass Mixer phase; Plan Mode can only
  deconstruct *every* layer on a tile, so they were left. Any save will collect such relics.

**Relic cleanup pass** (`autoplay/lib/relic_cleanup.py`). Scripts can do what the UI
cannot: `mark_deconstruct(x, y, layer="gas"|"liquid", target_id=pipe.id)` removes one
layer only. A piece is a relic when `contents()` is `None`, `conflicting_contents()` is
empty, `connections()` is empty, it is complete, and it is not in `autoplay.planned`/
`autoplay.networks`. Relics are grouped into connected components; a component is queued for
deconstruction (prio 1, segments come back into Pioneer cargo) when it blocks a planned route
(prio 0 in that case) or when idle. A `None` piece with non-empty `conflicting_contents()`
is a conflict, not a relic: reported, never removed. Switch `autoplay.relic_cleanup`
(`"off" | "blocking" | "all"`, default `"blocking"`).

**Consequences for the design**
- Topology read is the hot path: ~2,000 pieces × 4 method calls. `infra_topology` reads
  `list_pipes()` once per pass in `run_batched` slices (`lib/atomic.py`), builds
  `occ` with comprehensions, caches it keyed on piece count + pending-job count, and logs
  only one summary line (counts per medium/fluid); per-piece detail only via `trace()`.
- Occupancy keys are integer tile indices `(x // 10, y // 10)`, computed from piece
  midpoints; a piece occupies the two tiles it joins.

## Verification
- `pytest tests/` incl. new `tests/test_autoplay_*.py` (harness path extended with
  `autoplay/lib`): route avoids other-fluid tiles, bridge emitted on forced crossing,
  both footprint anchors map to the right 4×4 tiles, a second water network into an outpost
  gets a non-touching port, a full outpost is reported instead of merged,
  same-fluid reuse, MST joins N subnets with N-1 edges, prio ordering in `scan_slice`,
  atomic step budget.
- `tests/test_game_imports.py`, `test_log_blocks_balanced.py`, `test_reset_in_run_loops.py`
  extended to scan `autoplay/`.
- Pyright on `autoplay/`.
- Live (with user consent each time): run once with `MAX_NEW_JOBS_PER_PASS=1`; check the ghost
  on the Planet Map, Pioneer builds it, `list_pipes()` shows `contents()` == intended fluid and
  `conflicting_contents()` empty; `power_control.grids()` count drops after the power pass.
