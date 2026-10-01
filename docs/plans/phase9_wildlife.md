# Phase 9 — Feed Maker + Habitat controllers (tier `9_wildlife`)

## Status (2026-10-01)
Done: `.criteria`, `lib/wildlife_data.py`, `lib/wildlife_model.py`, `devtools/wildlife_optimizer.py`, `WILDLIFE_SCHEDULES` (§1l-1); the planner (`lib/wildlife_planner.py`), `lib/habitat.py`, `lib/feed_maker.py`, `lib/wildlife_common.py`, entrypoints `bio/habitat.py` / `bio/feed_maker.py`, and the edits to existing libs (power tiers, cash, parking, archive cleaner, Control Room Automation, Plant Terraformer Forage reserve). Behaviour and tunables: `docs/cheatsheet/wildlife.md` §1l-2. Stub-tested only; not deployed live yet.

Decided (2026-09-30):
- The Adaptation is optional per revival (`revive` / `revive_raw` steps).
- The target is the 5,000,000 Wildlife pillar, so the Refiner and Deep Exotics are needed.
- Schedules are stored per Habitat count (5/10/16) in `WILDLIFE_SCHEDULES`; the planner uses `wildlife_model.schedule_for(live_habitat_count)`.

Decided (2026-10-01):
1. No overcapping the home slot cap: the Habitat count is whatever fits; more come when Warehouses move out. Nothing assumes 16.
2. Feed before Plants: the Plant Terraformer leaves `wildlife.plan.forage_reserve`.
3. Feed is reserved before revival: it is staged in the Habitat's own bin (nobody else can take it). Rearing eats no feed (no births), so this costs at most one craft.
4. Parking at the Mk I ceiling for a later revival (undeploy/rehouse) is deferred: 1–2 % gain at 5–10 Habitats, none at 16.
5. Fluid supply (taps, pipes, Refiner) is out of scope until unlocked; the Habitat only routes from tanks that already hold the fluid.
6. Habitat kits are bought and deployed by hand until the autobuilder.
7. Habitats are shed last (power tier 3); an unpowered Habitat only pauses.
8. Established Habitats park on `no_feed` and at the Mk I ceiling, with an operator alert (notify + AUTOMATION card).
9. Buffers, not just-in-time: feed to a 24 game-hour stock target, life forms to 48 game hours.
10. Fluid supply is not assumed ample (see "Exotic fluid supply vs demand"). The planner rations each fluid to the slowest colonies first within the tank budget. A denied Habitat stops intake and keeps its buffer, and parks once that buffer leaves the band. Feed goes to fluid-holding colonies before rearing and feed-only ones, because a starved buffer bleeds until it parks. Simworker check: an unpowered or capped Habitat neither meters nor bleeds. Details in §1l-2.

Next: deploy and observe live (see Verification), then the Refiner / fluid supply once Exotic Husbandry unlocks.

## Original session scope
1. Save this plan in the repo as `docs/plans/phase9_wildlife.md`, and link it from the TODO.md Phase 9 header, so a later session can resume.
2. Build only the offline optimizer and what it depends on:
   - `scripts/9_wildlife/lib/wildlife_data.py`
   - `scripts/9_wildlife/lib/wildlife_model.py`
   - `devtools/wildlife_optimizer.py`
   - tests
3. Run the optimizer and report its schedule.

The planner, the Habitat and Feed Maker controllers, `.criteria`, and the edits to existing libs stay staged. The tier `.criteria` is not created yet, so `scripts_sync` deploys nothing live.

## Context
10 Habitats (`habitat_1..10`) and 2 Feed Makers (`feed_maker_1/2`) sit empty and powered at home (save read 2026-09-30; typeIds `habitat` / `feed_maker`, empty slots in `scripts/_unmatched/`). All 80 fragments are cataloged, so all 16 feed recipes are unlocked. Nothing wildlife-related exists in code yet. Goal: automate feed production, revival, husbandry (feed + fluid bands) and Insight spending, per TODO.md Phase 9 and `docs/cheatsheet/wildlife.md` §1l.

Decisions from the user:
- **Revival is Insight-gated.** Every revival runs `set_revival_target` → `unlock_bonus(Adaptation)` → `revive()`, because a late Adaptation loses founding bonuses (hive_sentinel, crustal_echo, spire_drake, veil_mantle's Breakthrough) and the below-2,500 speed boosts. The only exception is the bootstrap: the 2 Commons (`magmatic_annelid`, `salt_tortoise`) revive un-adapted to seed the pool, and their Adaptations are bought as soon as Insight allows.
- **The revival and Insight order comes from an offline optimizer** run on the dev machine. The in-game planner only follows the resulting fixed schedule and skips blocked steps. The inputs are world-independent game constants, so there is no in-game simulation.
- **Reagents are auto-bought** through the cash budget.
- **Parking is part of the schedules** (superseded the earlier deferral; see Status).

## Architecture
Habitat and Feed Maker methods are self-only, so each machine runs a thin script. The central decisions (who revives what, what to buy with Insight, feed demand) are made once in the control room automation and published to the archive. The machine scripts execute them. This follows CLAUDE.md rule 5 (compute centrally) and matches `plan_sites` / `publish_all_drills`.

```
control_room_automation ──every WILDLIFE_PLAN_TICK_INTERVAL──> wildlife_planner.plan()
      reads: wildlife.status (habitats), wildlife.feed (feed makers), journal, tanks, wildlife.targets (operator)
      writes: wildlife.plan {assign:{habitat:species}, buy:{habitat:node_id}, feed_demand:{feed_item:units}, forecast}
habitat_N script   ── executes assign/buy, stages feed+reagents, revive, regulates bands ──> wildlife.status
feed_maker_N script── crafts by plan.feed_demand, stocks inputs, publishes life-form requests ──> wildlife.feed
```

## Files

### New tier `scripts/9_wildlife/`
- `.criteria` (done): `{"buildings": {"feed_maker": 1}}`. It is created early because a tier folder without `.criteria` counts as met. `resolve_active_tier` needs 1–8 met first, which is the case today.
- `bio/habitat.py`, `bio/feed_maker.py`: thin entrypoints (`HabitatController(self).run()`), same shape as `scripts/8_planting/bio/plant_terraformer.py`. `scripts_sync` fills `habitat_1..10` / `feed_maker_1/2` through `match_key()`.
- `lib/wildlife_data.py` (pure game constants, same on every world, mirrors §1l): rarity breeding multipliers, stage thresholds, the capacity table, the Insight curve points, the growth-function constants (0.0144, F(p), 150/h ceiling), per-species fluid table (`bk`/`Hq`), and the trait-effect table (`MG`: feed ×, speed %, offspring %, founding +n, below-2,500 / per-stage conditions, keeps-base-fluid flags). `CatalogedCreature.rarity` stays the live source for rarity; the table here only drives projections.
- `lib/wildlife_model.py` (pure, no game calls; unit-tested): the growth and Insight projection.
  - `breeding_rate(pop, rarity, bonuses)` implements the §1l formula.
  - `project(colony, hours, fluids_available)` steps population forward. It stops at a stage threshold whose next fluid isn't available and at capacity (Mk I 175,000). It returns population and the Insight earned.
  - `insight_at(pop)` is the piecewise-linear curve.
- `lib/wildlife_planner.py`: the central planner (details below). It is called from `scripts/4_controlpanel/automation/control_room_automation.py` on its own interval. The import stays safe on lower tiers because `lib_chain()` deploys higher-tier libs, and with no Habitats `plan()` is a no-op.
- `lib/habitat.py`: `HabitatController`.
- `lib/feed_maker.py`: `FeedMakerController`.

### Edits to existing code
- `scripts/4_controlpanel/lib/cash.py`: add the operating consumer `"wildlife_reagents"` (`OPERATING`, `CONSUMER_LABELS`).
- `scripts/4_controlpanel/lib/script_parking.py`: add `WAKE_AFTER_TICKS["feed_maker"]` (< 6000, since it publishes requests) and `["habitat"]` (empty unassigned Habitats only). A housed colony is never parked: the breaker cuts power, and without power there is no breeding.
- `scripts/4_controlpanel/lib/archive_cleaner.py`: add `MACHINE_STATUS_KEYS` entries for `wildlife.status` → `habitat` and `wildlife.feed` → `feed_maker`.
- `scripts/4_controlpanel/automation/control_room_automation.py`: add a `plan_wildlife_if_due(clock)` step.
- `tests/test_flush_before_sleep.py`, `tests/test_reset_in_run_loops.py`: add `"9_wildlife"` to `TIERS`.

## Planner (`wildlife_planner.plan()`)
1. **Readiness.** Compare `journal.cataloged_creatures(planet)` and the unlocked recipe ids (each Feed Maker publishes them in `wildlife.feed`) with the 16 species. Publish `wildlife.readiness {missing_creatures, missing_recipes}` and log once on change.
2. **Candidate ranking** (`wildlife_targets` logic folded in here; pure).
   - A species is eligible if it is cataloged, its recipe is unlocked, and it has no colony yet.
   - Score by rarity multiplier, ingredient access (the worst life-form rarity in its recipe), and fluid readiness: can a tank of its stage-1/2 fluids be reached?
   - Operator `wildlife.targets` (a list of species) overrides the ranking: listed species first, and only listed species when the list is non-empty.
3. **Follow the offline schedule** (the ranking in step 2 only orders species the schedule doesn't list, for operator-listed extras) (see "Offline optimizer" below; no simulation in-game). Walk `schedule_for(habitat_count)` in order. Each step is `revive S` (Adaptation first), `revive_raw S` (no Adaptation), `adapt S`, `breakthrough S`, or `save_for S`. A step fires when its trigger holds: Insight ≥ cost, a free Habitat, source pop ≥ 10,000 for a Breakthrough. A step blocked by something the schedule assumed away (recipe missing, no source for its next fluid, feed ingredients short) is skipped. The next unblocked step runs instead, and the skip is logged with its reason. Operator `wildlife.targets` overrides the order. Every decision is logged at `debug()`.
4. **Assignment.** Map chosen species to empty Habitats (lowest id first) in `wildlife.plan.assign`, and wake a parked Habitat with `wake_for_visit`. Queue Adaptation purchases in `wildlife.plan.buy` `{habitat_id: node_id}`. The owning Habitat (target or housed species) executes the purchase, because `unlock_bonus` is self-only and the tree appears after `set_revival_target`.
5. **Feed demand.** For each housed or assigned species: `target = revive_feed_required + rate × 0.1 × feed_mult × FEED_BUFFER_H`, minus the Habitat's `feed_level`, minus Inventory/Warehouse stock of that feed item. The result goes into `wildlife.plan.feed_demand`. When demand appears, `wake_kind("feed_maker")` runs.
6. **Progress.** Publish the current schedule step, the next trigger, and skipped steps in `wildlife.plan.progress` for a future panel card.

All planner writes go through `archive.transaction()` with a pure updater. There is one dict per concern, pruned for Habitats that no longer exist.

## Offline optimizer (`devtools/wildlife_optimizer.py`, first implementation step)
The inputs are game constants, the same on every world, so the ideal order is mostly fixed. It is solved once on the dev machine, not in-game.
- **Source of truth:** CPython imports `scripts/9_wildlife/lib/wildlife_model.py` + `wildlife_data.py`, the same code the planner would use. This keeps one source for formulas and trait effects.
- **Model:**
  - Event-stepped simulation. A decision point comes whenever Insight crosses a cost, a Habitat frees, or a colony crosses 10,000.
  - Per-colony growth follows §1l, including founding bonuses, below-2,500 / per-stage / "other established species" conditions, and the global caps.
  - Insight comes from the population curve.
  - Constraints are parameters: Habitat count (10 now, up to the slot budget), the fluid availability timeline (default: common fluids piped from day X, Refiner fluids later, chlorine/quicksilver at 500k Wildlife), Mk I cap until 600k, and optional feed throughput (2 Feed Makers × 20 feed / 0.3 h).
- **Search:** beam search over action sequences (revive-with-Adaptation S, Adapt existing, Breakthrough, save-for-X), pruned by dominance.
  - Objectives: time to 250k / 500k / 600k Wildlife, and total Wildlife at the horizon.
  - Baselines to compare: plain rarity order, the user's gut order (salt_tortoise Breakthrough early, hive_sentinel + veil_mantle early for flat founding), and greedy.
  - Growth is not exponential: F(p) = p up to 10, then p^0.85, capped at 150/h. A flat +4..+6 founding therefore matters most in the 4 → 10 window, which is the first Insight.
- **Output:**
  - The best schedule and its timeline, as a table in `docs/cheatsheet/wildlife.md`.
  - The `WILDLIFE_SCHEDULE` constant in `lib/wildlife_data.py`, which the planner walks.
  - A sensitivity note on which steps change when Habitat count or fluid timing change.

  It is re-run by hand when the assumptions change.

## Habitat controller (`lib/habitat.py`)
The state is derived live each step, so a restart is safe: `species()`, `revival_target()`, `is_established()`, `rearing_progress()`, `rearing_failed()`.
- **Empty and unassigned:** park (`ParkRequester(id, "habitat")`).
- **Assigned:** run `set_revival_target(S)` and branch on its status. If the plan lists an Adaptation to buy for this Habitat, run `unlock_bonus(node)` and branch on `insufficient_insight` / `already_purchased`. Revival waits until the Adaptation is bought, unless S is a bootstrap species.
- **Staging:**
  - Feed: take `revive_feed_required + REARING_FEED_EXTRA` of `required_feed()` into `input` via `storage.take_item(port, item, n, outpost=...)`. At home this includes Inventory.
  - Reagents: connect `reagents` to Base Inventory and `take()` each of the 5 reagents × `revive_reagents` qty. When Inventory is short, `cash.can_spend("wildlife_reagents", cost)` → `shop.buy` → `cash.spent`, following the pattern in `scripts/4_controlpanel/lib/bio.py` ~l.1110.
  - Then `revive()` and branch on every documented status.
- **Rearing (12 h):** keep feed ≥ 1. On `rearing_failed()`, log a warning with the band that failed, then re-stage and retry. The retry costs reagents again, so it is capped by `MAX_REVIVE_RETRIES` before it becomes a blocker.
- **Established:**
  - Feed: top up to `FEED_TOPUP_TARGET` (input buffer is 50) when `feed_level()` < `FEED_TOPUP_AT`.
  - Fluids (gas and liquid are handled the same way):
    - Band `[]`: intake 0, and keep the inactive reserve empty.
    - Wrong reserve fluid (`gas_fluid() != required_gas()`): intake 0 → `purge_reserve`.
    - Wrong inlet: `purge_intake("gas_in")`.
    - Source: a `FluidInputRouter` per port. Its discover step only returns tanks holding the required fluid, via `fluid_routing.discover_network_buildings(TANK_TYPE_IDS, fluid_id=...)`, own outpost first.
    - Regulator: aim for the band centre. `rate = clamp(consumption + BLEED_T_PER_H + GAIN × (centre − level), 0, MAX_INTAKE)`. Above `high + PURGE_MARGIN` with intake 0: `purge_reserve`.
  - Pre-fill for the next stage just in time: when `next_stage_population() − population() < breeding_rate() × PREFILL_LEAD_H`, regulate toward `next_*_band()` as soon as the stage flips. A buffer is never filled early, because it bleeds 0.5 t/h.
  - The fluid ports are not wired before a band is active.
- **Blockers:** `no_<fluid>_source`, `wrong_fluid`, `no_feed`, `reagent_budget`, `awaiting_insight`, `capped`. They are reported on change at info level and published.
- **Telemetry:** `wildlife.status[habitat_id] = {species, target, stage, pop, capacity, rate, efficiency, feed_item, feed_level, gas:[fluid,level,band], liquid:[…], insight_balance, bonuses, blocker, tick}`.
- **Loop:** `POLL_INTERVAL_S` (60 s; bands are ±40–200 t against 0.5 t/h bleed). `reset_all` → step → `flush_all` → `sleep`. `TreeConsole(module="habitat")`, with `start`/`end` around revive / purchase / purge blocks.

## Feed Maker controller (`lib/feed_maker.py`)
- On start and on a slow poll: publish its unlocked recipe ids (`list_recipes()`) in `wildlife.feed[id]`.
- **Recipe choice:** the largest `plan.feed_demand` deficit whose ingredients are available (forage + forms from home stock). Exclude a recipe another fresh Feed Maker has claimed, unless its deficit exceeds one craft (20).
- **Switching:** run the current craft to completion, then `input.eject()` the leftovers to `storage.best_unload_target()`. `clear_recipe` rejects `material_present`, so the eject comes first. Then `set_recipe()`.
- **Stocking:** the stockpile cap is 200, and one craft is 100 forage + 1 of each form (2–3 forms), so it holds one craft at a time. Load the next craft's inputs with `take_item` whenever the stockpile has room for them. Life forms missing at home are published with `logistics_requests.set_requests(home, "feed_maker", {form: (target, have)})`, targeting `FORM_REQUEST_CRAFTS` crafts. An item another requester already owns at home is skipped, as in `plant_terraformer.publish_requests`. `retain_amount()` and `flush_surplus()` then keep those forms automatically (they are requester-agnostic).
- **Output:** drain `output` to Base Inventory (`output.send`, with fallback `storage.drain_port_to_storage`), following `6_seeds/lib/seed_maker.py::_drain_output()`. It never crafts past demand and stops when Inventory can't take more.
- **Idle:** with no deficit or no ingredients, clear its requests and `ParkRequester(id, "feed_maker")`. The planner wakes it.
- **Forage:** it takes forage only for the craft being loaded, so the draw is bounded. The Forage split with the Plant Terraformer stays an open TODO item.
- **Telemetry:** `wildlife.feed[id] = {recipes, recipe, running, progress, output, stockpile, blocker, tick}`.

## Docs and TODO (same change)
- `docs/cheatsheet/wildlife.md`: new subsection "1l-1 Wildlife automation" listing all our tunables: `PLAN_HORIZON_H`, `INSIGHT_VALUE`, `FEED_BUFFER_H`, the feed top-up thresholds, `REARING_FEED_EXTRA`, `MAX_REVIVE_RETRIES`, the regulator gain / max intake / purge margin, `PREFILL_LEAD_H`, poll intervals, and archive keys.
- `docs/AI_CHEATSHEET.md`: add the module-map entries for the 6 new lib modules and the archive keys (`wildlife.status|feed|plan|readiness|targets`).
- `docs/DESIGN_HISTORY.md`: add a short entry on why revival is Insight-gated.
- `TODO.md`: tick the done Phase 9 items, note that parking and the panel card are deferred, and resolve the open question (typeId `feed_maker`).

## Exotic fluid supply vs demand (16 Habitats, estimate)

Deposit ranges: [docs/gameknowledge/exotics.md](../gameknowledge/exotics.md). Demand: the Mk II "all 16" totals of [docs/cheatsheet/wildlife.md](../cheatsheet/wildlife.md) §1l, spread evenly over about 3,500 h (the 16-Habitat schedule's ~147 d). Supply: every deposit at its worst roll (lowest peak rate, shortest active, longest dormant), refining 1:1. The optimizer models only a per-tier ready time, not these rates.

The "untreated" totals ignore the retain perks. Four species have one: `bone_walker` (gas and liquid), `vent_drifter` (gas), `tidal_cephalopod` (liquid), `glacial_wyrm` (liquid). A retained apex stage uses the species' base fluid. Adjusted totals below are rough (per-species doc figures moved between fluids) and assume all four perks are bought, which the 32 spare Insight allows.

| Fluid | Mk II total (t) | Adjusted (t) | Mean demand (t/h) | Worst supply (t/h) | Verdict |
|---|---|---|---|---|---|
| sulfur_gas (raw) | 30,614 | ~23,800 | 6.7 | 10 (2 deposits) | OK, tight before tar |
| cryofluid (raw) | 19,040 | ~18,260 | 5.2 | 10 (2) | OK |
| quicksilver (raw) | 4,877 | ~2,440 | 0.7 | 2.3 (1) | OK, `spire_drake` only |
| chlorine (raw) | 8,940 | 8,940 | 2.5 | 2.3 (1) | short |
| brine | 20,295 | ~23,500 | 6.7 | 31 (3) | fine |
| swamp_gas + ammonia | 18,658 | ~25,500 | 7.2 | 62 (6) | fine |

- **Chlorine is the risk.** Only `spire_drake` and `glacial_wyrm` need it (~4,470 t each), `glacial_wyrm`'s retain perk covers liquid only, and the demand sits in the late legendary stages, far shorter than the full run. A single worst-roll deposit then gates the finish. Even the best roll averages only 13.8 t/h. Bank chlorine in tanks ahead of the legendary stages.
- The averages assume peak-rate capture for the whole active phase. Live, ammonia_2 averages about 13 t/h, near the worst common roll (10.5 t/h), so real margins may be smaller.
- Open: tar draw for the refined fluids (about 6.7 t/h of sulfur_gas at the mean), tank capacity for banking, and a per-stage demand timeline to turn the chlorine concern into a number. Next step if wanted: cap each fluid's supply in `devtools/wildlife_optimizer.py` from the deposits' real rates and cycles read from the save.

## Verification
- Unit tests (`tests/`, `harness.World` + ad-hoc fakes as in `tests/test_mining_drill.py`):
  - `test_wildlife_model.py`: the growth-hours table in §1l within ~5 %, and the Insight curve.
  - `test_wildlife_planner.py`: bootstrap assigns both Commons; the Adaptation is queued before a non-bootstrap revive; a `save_for` step holds Insight; a blocked step is skipped with a reason.
  - `test_wildlife_optimizer.py` (small instance): the beam result is at least as good as the baselines, and it is deterministic.
  - `test_habitat.py`: status branches, reagent purchase gating, the regulator in band / below / above / wrong fluid, purge.
  - `test_feed_maker.py`: recipe switch ejects first, demand-driven stop, requests published.
- Full suite: `python -m pytest tests`. This includes `test_game_imports`, `test_game_builtins` (no frozenset/id), one-line imports, and `test_log_blocks_balanced`. Also run Pyright (`pyright`).
- Dry-run `devtools/scripts_sync.py` (read-only mode) to confirm tier 9 resolves active and all 12 slots match. The deploy itself and the first live observation (recipe ids, `input.take` of forage/forms, reagents connecting to Inventory, `unlock_bonus` before `revive`, the real intake flow limit) wait for the user's go. I will ask before any in-game run.
- Commits on main, split roughly: tier + data/model, planner, habitat, feed maker, docs. Messages via `caveman-commit`, no attribution.
