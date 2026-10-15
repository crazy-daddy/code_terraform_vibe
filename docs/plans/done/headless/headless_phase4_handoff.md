# Headless stand-ins: handoff for phase 4 (producer modes and off-stubs)

Written 2026-10-14 after phase 3 landed (logistics `mover`). Design reference: [docs/headless/standins.md](../headless/standins.md) (groups, modes, phase table, "Design notes for the open phases": plants `produce` / `cash`, off-stubs). The owner's full plan (all phases, per-subsystem design, delegation, risks) is the local plan file `C:\Users\Adrian\.claude\plans\plan-useful-speedy-features-nested-blossom.md` (not in the repo; ask for it on another machine); its "Factory", "Harvester", "Biolab / wildlife / biomass" and "Orchestrator" sections plus "Phases" phase 4 are the spec. Earlier notes: [done/headless_phase2_handoff.md](done/headless_phase2_handoff.md), [done/headless_phase3_handoff.md](done/headless_phase3_handoff.md).

## Where phase 3 left things

- `standins.mjs` mode `mover` (`MODES.logistics.mover`, params `{every: 100, speedMps: 12, loadTicks: 50}`, validated at setup before any `script.stop`): `#moverSetup` stops the group's slots like `off` (ghosts = stopped, overridable by `ghosts.logistics`), drops the stopped haulers' own `logistics.pickups` entries, reads `state.planet.outposts[].{id, x, y}`; `#moverPass(tick)` lands due trips every tick (overflow stays queued, retries every `every` ticks, the pickup re-stamped), and every `every` ticks walks each valid request's ladder from the highest band: shortfall = band level − live store count (`stacks.mjs` `outpost:<id>`) − fresh pickups into that outpost (any vehicle) − this pass's loads; sources are the other outposts nearest first, free = count − other vehicles' reservations − max(own level at that band, `keep`); `buy: true` entries fall back to `sim.buy()`, with only what landed in the Inventory travelling (a home request keeps it there). One trip per (dest, item, source) per pass, one `logistics.pickups` write per pass. The lib facts it mirrors sit in the comment block above `#moverSetup`.
- **The runner's `pass(t)` tick counts from the run's start**, not the game's `tickCount` (`run.mjs` loop). Flows and cadence use it; anything compared with archive `tick` stamps must use `state.tickCount` (the mover's `now`). The first smoke run moved nothing because of this.
- `stacks.mjs` has a `bins` store kind: warehouses, large warehouses and storage bins hold `m.bins = {slot_i: {itemId, stacks, capacity}}` in every save (phase 0 only knew `itemStacks`, which drone stations and vehicles use), so before phase 3 `outpost:<id>` never saw warehouse stock. Rules from the worker (`deobfuscated.js` `Ub`/`zb`/`Xve`): an empty bin takes any item, a holding bin only its own, room = `capacity` − held with the capacity guarded as a safe non-negative integer, an emptied bin's `itemId` resets.
- `summary.standins.mover = {moved: {item: units}, trips, pendingUnits, bought: {item: units}, buyFailed: {item: reason}}` ([scenarios.md](../headless/scenarios.md) Output table).
- Tests: `test/mover.test.mjs` (fake sim with two outposts, a warehouse, `getArchive`/`setArchive`, `buy`; its `make()` sets `state.tickCount` to the pass tick as the game does), `test/stacks.test.mjs` bins case. `node --test "devtools/simulation/headless/test/*.test.mjs"`: 39 pass.
- A/B 0262 ([ab_results.md](../headless/ab_results.md) "Phase 3"): errored 0, no fleet warnings, 45 trips in 20 game minutes, ×4.69 vs ×3.70 real time. Gaps are the group's boundary: stopped Supply Docks ship no orders (credits −10 k), stopped miner Pioneers bring no ore (fewer ingots at outpost 3). Still open in the table: `scale` and `standin` on 0262, `park` in the phase-1 table, power `trim`.
- A/B outputs are in `out/ab_0262_real` and `out/ab_0262_mover` (untracked; never commit `out/`). The stock-per-outpost comparison script (`outpost_stock.py`, reads `bins` and `itemStacks`) lived in the session scratchpad; rewrite it in a few lines if needed.

Facts learned about the game and the lib that phase 4 will use:
- `logistics.requests` entries are `{levels: [[prio, cum], ...], have, by, tick, buy?, keep?}` (`set_requests()`); `active_requests()` skips entries without a ladder, so the old `{target, have, min}` shape in a 2026-10-07 save is dead until republished (within one requester pass: `_unchanged()` sees the ladder mismatch). `have` lags up to `REPUBLISH_TICKS` (3,000).
- `drone_haulers_present()` needs a fresh (`HAULER_FRESH_TICKS` 6,000) `fleet.status` entry with `role == "hauler"` and an `engine` key; stopped drones stop publishing, so no heartbeat is needed to keep requesters on the ground-hauler branch.
- `request_target()` / `tier_level()` live in `logistics_requests.py`, not `priority.py`; `priority.py` has `ladder()`, `ladder_level()`, `ladder_total()` and the band constants.
- `sim.buy(itemId, quantity)` is the UI `shop.buy` command; the items land in the Inventory.
- Machines carry `data.posX` / `data.posY`; outposts carry `x` / `y` in `state.planet.outposts`.

## Phase 4: factory / harvester / bio / orchestrator modes

Build order (plan file "Phases" phase 4 and "Delegation"):

0. `cavecrew-investigator` re-verifies in `scripts/4_controlpanel/lib/` before any code: `cash.py` `can_spend()` and the `cash.budget` record shape (`{tick, balance, floor, income_h, burn_h, asks, holds, planned, queue}` per the plan; the legacy floor path at :68-72), `production_demand_record.py` :68 local fallback when `production.demand` is missing, `wildlife_planner.py` / `biomass_retire.py` entry conditions for `wildlife.plan` and `biomass.retire`, `plant.status` / `plant.automators` telemetry shapes (which field is the last harvest per hour), `plant.seed_demand` readers, `script_parking.py` (never `script.stop` on stand-in slots), and `commander.get_credits()` vs `state.player.credits` (run.mjs :368 reads that field).
1. Spec in the main thread: `produce` (`{forage_h, ...}` to `flows` rows at the Inventory, defaults from telemetry when the save has it, else required and printed at start), `cash` (`creditsPerHour / 360` into `state.player.credits` every 100 ticks), the off-stubs (`power.shedded: []`, `cash.budget` fresh each pass, `wildlife.plan = {}`, `biomass.retire = {complete: false}`), and the `archive` seed section's interaction with them.
2. `standins.mjs`: `MODES.plants.produce` / `cash` (remove `PLANNED`), orchestrator/wildlife/biomass `off` stubs, `buildorder_search.py` SUITES (:172) pass `--scenario` through. Tests on fake sims like `test/mover.test.mjs`.
3. Report rows in scenarios.md, standins.md Modes and Phase rows.
4. A/B: harvester target on `0142_t248069` and `0262`: credits per hour real vs `factory=off,bio=off,logistics=mover,terraforming=scale`. Reviewer on the diff before the runs; runs in the background (20 game minutes on 0262 take ~4-5 min wall, on the midlate save ~13 min).
5. Docs: DESIGN_HISTORY entry; `archive_ipc.md` for every stub key.

Pitfalls from phases 1-3 that apply here too:
- `--only-scripts A,B` pins slot ids in `keep`, and a stand-in mode skips machines whose slots are kept; a scenario file (`default: "off"` plus explicit modes) is the way to isolate a group.
- Tests use fake sims; extend `test/mover.test.mjs`'s `fakeSim` or `test/scale_groups.test.mjs`'s rather than loading a save.
- The watcher does not cover `devtools/`, so no sync hold is needed for these files; never put probe files under `scripts/`.
- Validate scenario params for value, not only name (`validateScenario` checks names only); throw before any side effect.
- Archive ages: compare with `state.tickCount`, never with the runner's relative tick.
- A group that is `off` or stood in has a boundary (`GROUPS[g].produces` / `consumes`); the A/B gaps come from there first. Name them in ab_results.md rather than tuning the stand-in.
