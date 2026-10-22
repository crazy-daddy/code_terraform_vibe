# Plan: code quality

Status: **in progress**. Helper unification started 2026-10-09; size scan triage added 2026-10-22.

Two streams, one plan, because they keep finding the same code:
- **Duplicated helpers** (this section through "Next sweep"): N copies of one rule become one helper.
- **Size scan** ("Size scan triage (2026-10-22)" and below): long files and complex functions from
  `devtools/code_scan/size_scan.py`, sorted into split, refactor and keep.

The scanners behind both live in `devtools/code_scan/` (`clean_code_scan.py` runs all of them): `clone_scan.py`
(similar function bodies), `feature_scan.py`, `size_scan.py`. Each has an ignore file for reviewed hits.

Related, not merged here: the finished [mixin refactor](mixin_refactor/README.md) owns the vehicle, drone and
harvester layer tables (CODE_GUIDES §Mixins links them). Fixes below that touch a mixin follow those layers.

## Context (helpers)
Lib modules grew their own copies of small helpers: stock counters, staleness checks, tick caches, home
outpost lookups. The copies drift apart. Depot stock went missing from half the netting because each stock
counter picked its own set of stores (`7e7cc85`). Every unification here replaces N copies with one helper,
and the commit lists any behavior change that comes from settling on one rule.

Scope: `scripts/4_controlpanel/` and `autoplay/` (autoplay libs merge into the lib index and may import
`scripts` libs). `scripts/0_cold_boot` is out of scope: it has no shared `lib/` by design, so its copies stay.

## Method
1. **Harvest (cheap model).** Four parallel Haiku Explore agents, one per domain slice: storage/logistics/production,
   drones/vehicles/fleet, bio/harvest/power/wildlife, autoplay plus entry scripts and core libs. Each gets
   the same brief: list candidates by pattern family, never judge whether merging is safe, over-report, and
   flag sites that bypass an existing helper. The brief shows the pre-`7e7cc85` stock counters as the example of
   "same intent, different look": different names, per-item `.count()` vs a whole-map `.stacks()` sweep, ad hoc
   store sets and home special cases, memo dicts per outpost.
2. **Judge (strong model).** Read each cluster's bodies side by side. Sort them into real duplicate, near-duplicate
   with a parameter, or false friend, each with a reason.
3. **Unify.** One helper, all call sites, a test pinning the rule, a cheatsheet row. Check that the staged
   tree passes tests on its own when other sessions have uncommitted edits in the same files.

Haiku found the candidates well. About half of what it reported already used a shared helper or was a look-alike,
so step 2 is needed.

## Done
| Helper | Replaced | Commit |
|---|---|---|
| `stock_scan` scopes (`LOCAL`, `HELD`, `DEPOTS`, `STORES`) | 12 stock counters | `7e7cc85` |
| `game_clock.is_fresh(entry, tick, stale_ticks)` | 3 helpers + ~30 inline `tick - entry.get("tick")` checks | `70f256d` |
| `components.home_outpost()` / `home_outpost_id()` | 5 helpers + 5 inline lookups (`network.home()` vs `is_home` walk) | `ff6ac2f` |
| `geometry.distance(a, b)` | 7 Euclidean copies (nav mixins, scan_groups, outpost_mining, site_supply, 3 inline) | `ff6ac2f` |
| `game_clock.TickCache` | 10 module memos + 6 controller refresh fields + `TickedDiscoveryCache` | `c678da9` |
| `machine_controller.port_counts()` | fabricator (3), smelter, pioneer cargo, crop_automator (2), storage forage, `depot_stock`, early_buyer | not committed yet |
| `game_clock.real_seconds_per_hour()` + `game_rules.SECONDS_PER_GAME_HOUR`/`TICKS_PER_GAME_HOUR` | 7 live readers with own 25.0 fallbacks + 4 fixed constants (oil_generator, wildlife_common, habitat, production_core) | this branch |
| `fleet_status.is_idle()` / `is_off_duty()` | 3 state lists (fleet_status, machine_activity, construction_plan) + unfiltered drone hauler presence | this branch |
| `item_tiers.site_hardness()` / `can_cut()` | 4 unknown-hardness rules | this branch |
| `power` bank / rod / steam readings, `rod_yield()` | pooled rod reserve in battery fraction | this branch |
| `game_rules` (game facts, no imports) | ore lists (5), smelter recipe map, biome tuples (4), liquid tank ids (3), warehouse slot size (3), crop automator cap, tile size (3), game time constants | this branch |
| Owner-module constants | Plants bands + Mk II batch + `plants_km2()` (`plant_terraformer_common`), drill kinds (`item_tiers`), scan research ids (`contact_inference`), claim expiry (`fleet_claims_common`), stranded drone states (`drone_navigation`), oil surplus wake (`script_parking`) | this branch |
| `is_fresh` for Smelter/Fabricator wants and the construction hold | 2 hand-rolled checks in `production_core`, `construction_plan.held_kinds` | this branch |
| `storage.WAREHOUSE_STOCK_TARGET` for slot-sized stock caps | tar stockpile, life-form request cap (salt already used it) | this branch |
| `drone_navigation.NO_ROUTE_STATUS` / `is_no_route()` | nav waits sat out the timeout on `stalled_no_route`; `drones_card` status list | this branch |
| `storage.slot_fill()` in `slot_room()` | eviction filled slots to 2000 against the 1800/400 stock rule | this branch |
| Founding fluid score on the footprint edge gap | `outpost_sites` centre distance vs `supply_tiers` tile gap | this branch |
| `grid_geom` footprints centred like the game | `outpost_box` was x..x+40, y..y+40 from the anchor | this branch |
| `storage.STAGING_FREE_SLOTS_KEEP`, `site_evict.lifeform_staging_sites()` | eviction took the slot Depot life-form staging needs (miner-drone homes keep one more) | this branch |
| `logistics_requests.min_load_units()` | drone 50 vs ground 10 minimum haul load (now 10 for both, owner) | this branch |
| `vehicle_claims.sonar_range()` + `item_tiers.MIN_SONAR_RANGE_M` | sonar range fallbacks 50 / 35 m spiral / 0 | this branch |
| `fleet_decommission.forget_machine()` | decommission cleanup + drone chassis swap cleanup (`upgrade_state=False`) | this branch |

## Open candidates
- **`_notify(text, level, duration)`**: 4 identical copies (`reactor`, `oil_generator`, `power`, `power_solar`),
  each `notify()` in a swallowed try. About 10 raw `notify()` calls elsewhere have no guard (`bio`, `charging`,
  `drone_service`, `harvesting`, `fluid_routing`). One guarded helper, maybe next to `swallowed`.
- **Deploy / undeploy / upgrade sequences onto `building_ops`**: `pillar_swap.py` and `building_swap_upgrade.py`
  each run their own undeploy, sell, buy, deploy and upgrade steps with restart adoption (`known` snapshot) and
  refusal retries. `building_ops.py` (autoplay.md §11k) is the shared executor for exactly that: one status
  table, snapshot-then-deploy adoption, retire handshake. Also `early_buyer`, `fleet_upgrade`, `fleet_commission`,
  `tank_upgrade` and `fleet_decommission` call `computer.deploy()`/`undeploy()` directly. They don't touch the
  same machine today, so this is cleanup, not a fix. Move one at a time; keep each module's own sell/buy policy
  and request a `building_ops` job for the machine steps.
  Partly done (2026-10-22): the swaps and fleet coordinators call `building_ops.deploy_new()` / `undeploy()` /
  `classify()`, not jobs. Jobs are stepped only by the autoplay planner; a swap waiting on it would lose its
  back-to-back buy, deploy, drain. Left on raw calls: `early_buyer`, `fleet_decommission`, `fleet_upgrade`
  undeploy and Depot upgrade, `storage_expand`.

## Drifted copies (sweep 2026-10-11)
Copies that now disagree, so each is a bug as well as a duplicate. Found by three slice agents (storage/production,
vehicles/drones, bio/power/autoplay) briefed on drift, every finding read in the code. Ranked by risk.

1. **Battery level with Lightning Rods.** `power.measure_grid` and `turbine_commit` add the rod reserve to the battery
   pool. A rod fills only from strikes and is spent only after the batteries are empty, so drained rods hold the pooled
   fraction low: `turbine_commit`'s all-on latch and top-up and the Oil Generator's last resort (stops only at 0.70)
   never let go. Fix and the owner's power source order: see "Power source order" below.
2. **Idle fleet states, three lists** (`fleet_status.IDLE_STATES`, `machine_activity.FLEET_IDLE_STATES`,
   `construction_plan.PEER_INACTIVE_STATES`). The last lacks the Constructor's own `IDLE_AT_BASE`, so an idle peer
   halves the working builder's restock (`fair_share()`). One classifier in `fleet_status` with the `IDLE*` prefix rule.
3. **Drone hauler presence ignores state** (`logistics_requests.drone_haulers_present()`): a recalled or upgrade-held
   drone still makes ground haulers skip drills and Depot outposts. Reuse the classifier from 2.
4. **Unknown drill hardness, four rules**: hardest kit (`extractor_plan`), skip or TypeError on `None`
   (`vehicle_mining`), `or 99` turning 0 into 99 (`pioneer_upgrade`), free (`outpost_sites`). One `site_hardness()` and
   `can_cut()`.
5. **Fixed game-hour length**: `oil_generator`/`wildlife_common` 250 ticks, `habitat` 25 s, `production_core` from a
   day-length constant. Extends the open `real_seconds_per_hour` candidate: one `game_clock` reader.
6. **Site stockpiles ignore the bin rule**: `site_supply.SITE_STOCK_TARGETS` (tar 1800, forage 1000),
   `wildlife_common.FORM_REQUEST_CAP`, `pump_salt.SALT_FIELD_UNITS` are hard-wired; ore and ingot buffers use
   `storage.default_stock_target()` (400 before Warehouses). Can't happen in play (owner: tar and forage don't exist
   before Warehouses, and the upgrader replaces bins at once), so low priority: one source for the rule.
7. **`early_buyer.free_material_stack`** finds ore by `_ore`/`_ingot` suffix: titanium, silicon, cobalt, rare earth,
   neutronium never get cleared. Use `game_rules.RAW_ORE_ITEM_IDS` and the smelt products.
8. **Drone chassis swap forgets less than decommission**: `fleet_upgrade._migrate_drone_keys` skips
   `release_pickups`, `release_yield`, `clear_stage`. No live effect: the hauler takes the swap only after its work in
   flight finishes, and delivery releases its pickups. Cleanup only: one `forget_machine()` for both paths.

Smaller: none left. Heater vs condenser steam latches are deliberate (condenser 250 t/h takes only a near-full pool's surplus,
heater 12 t/h bonus feed runs to 0.50); the ladder is now written down in power_fluids.md.

**To think about after PR #36 (not a must): stock refill hysteresis.** The minimum load is
`logistics_requests.min_load_units()` (`min(HAUL_MIN_LOAD_UNITS, reachable)`, drones and ground alike), so a 2-unit tar shortfall on the
STOCK band is a 2-unit trip when a hauler has nothing better. That may be fine for an otherwise idle hauler, and a
small real need (2 kits for a cap of 2) must still go out, so no cutoff is chosen yet.

### Power source order (owner, 2026-10-11)
- Solar only: the night guard sheds so the grid survives the night.
- Steam: turbine count scaled to keep the batteries full. Turbines yield to other sources and to trickle oil, not to the
  last-resort oil burn (full oil tanks matter more than full steam tanks). Trickle steam no tank can hold always burns.
  Steam tanks are the reserve; the daily advisory warns on a fast drain.
- Oil: last, but also keeps the batteries full; burns off trickle oil.
- Reactor: the workhorse, never scales, own minimum-water guard. On a reactor grid neither trickle oil nor trickle steam
  burns: the power would be wasted too, and more machines would run.
- Lightning Rods: while they hold energy, everything but the reactor (and trickle) yields so the batteries run dry and
  the game spends the rods; scale back up before anything browns out.

Readings: full/top-up latches read the battery bank only; shortfall checks (night guard, load shedding, parking wake)
count stored rod energy as runway with only that stored part in the capacity, so a planned rod discharge never sheds.
Rod yield must end above the first shedding line.

## Checked, left alone
- **Drone vs vehicle energy models, reserves, trip costs**: separate on purpose (different formulas and values).
- **`drone_weather.cask_room`**: already delegates to `lead_cask.room_for`.
- **`recipe_claims`, `mining_reservations`**: claim-like, but non-exclusive or additive. `fleet_claims_common`
  doesn't fit them.
- **Stall cooldowns** (`drone_haul_plan` fail counter vs `PullJob.unviable` tick stamp): different
  triggers and lifetimes.
- **`_set_status`** (`fleet_upgrade`, `fleet_commission`, `building_swap_upgrade`): three lines each, different
  state stores. A shared helper would need reader and writer passed in.
- **Demand netting** in `refiner`, `fuel_assembler`, `feed_maker`: machine-specific.
- **Future-stamp guards** (`lead_cask` alerts, `logistics_requests` republish: `0 <= age < ttl`): a different rule from
  `is_fresh`, kept inline.
- **Squared-distance loops** in `construction_plan`: compare squares on purpose, root once.
- **Port loops that filter as they count** (`bio_volcanic` by properties or recipe, `mining_drill` with
  count/capacity reads): not a plain count.
- **Throttles** (`_published_tick`, `_last_request_tick`, `_want_tick`): "republish at most every N ticks
  unless changed" is a different pattern from a value cache. They could share a helper later, but it isn't a `TickCache`.

## Next sweep
Rerun the harvest after the open candidates land, with the families above marked done, so agents don't report
them again. Families not swept yet: archive read/validate wrappers (`archive.get(KEY)` + `isinstance(dict)`,
~96 sites), per-outpost building filters that bypass `discover_storage_buildings` / `discover_network_buildings`.

A spot check (2026-10-09) found more candidates the first sweep missed:
- **Guarded `research.is_unlocked` reads**: 5 identical wrappers (`early_buyer.is_unlocked`,
  `storage.warehouses_unlocked`, `pioneer_upgrade.sport_nav_unlocked`, `drone_weather.hot_cargo_unlocked`,
  `building_swap_upgrade._large_unlocked`) plus ~4 inline in `vehicle_claims`, `survey_requests`, `pioneer_upgrade`.
  `clone_scan` clusters them with `biomass_mixer_gate._is_powered` and `drone_weather.now_gh`: the general
  family is a guarded component call with a default.
- **`_dist(ax, ay, bx, by)` in autoplay**: `outpost_plan`, `outpost_sites`, `outpost_needs`, plus 3 inline in
  `outpost_sites`. Missed by the `geometry.distance` pass.
- **Recipe shortfall cascades** in `production_cascade`: `_cascade_fabricator_output_demand`,
  `get_manual_order_blocking_items` and `_walk_blueprint_demand` run the same depth-6 BFS and differ only in
  what each node records. One walker with a per-node callback.

No full strong-model sweep: the cheap tools already point at these. Before the next harvest:
- `clone_scan.py` skips `autoplay/` and functions under 6 lines. Add both, then triage its unreviewed pairs
  (325 at 0.85), not just the top of the list.
- Anchor the Haiku brief on game API calls: list every caller of `research.is_unlocked`, `notify`,
  `real_seconds_per_hour`, `archive.get`, `deploy`/`undeploy`. Wrapper copies cluster around them.
- Keep the strong model for the judge step. A targeted read of `autoplay/lib` plus `production_cascade`
  is the one place a strong-model harvest may pay off (logic-shaped duplicates, fastest-growing code).

## Size scan triage (2026-10-22)
First run of `size_scan.py` at default limits (file 1000 lines; Ruff C901 10, PLR0912 12, PLR0915 50), commit
`6815306`: 270 files, 9 file hits, 139 function hits, ignore file empty. Seven agents read every hit by domain
(storage/dock, bio/farming, production/fluids, vehicle/pioneer, drones/fleet, archive/parking, misc/contract) and
judged REFACTOR, MINOR or KEEP. Line numbers below are from that commit.

Main result: size mostly flags **copies between siblings**, not single long functions. About half the hits are
defensible and go to the ignore file. No hit is blocked by CODE_GUIDES script cost: the flagged loops are
sleep-bound game I/O or run once per cycle, so a helper call costs a few steps against reads that cost hundreds.
Exceptions are noted under "Keep".

Score inflation: manual `log.start`/`log.end` pairs and `_ret = ...; log.end(); return` before every early return
raise C901 and statement counts (`fluid_routing` routers, `fabricator_root_targets`, `bio_orders.focus_local_order`,
`biomass_mixer_gate`). The existing `@method_block` removes them with no behavior change; do that first, then rerun
the scan before judging the rest.
Done (step 2): 19 whole-function debug blocks with 2+ `end()` exits now use `@method_block` / `@log.block`. Scan
before and after: 9 file hits, 140 function hits. C901 and branches did not move (`start`/`end` add no branch); the
statement count fell 3 to 18 per function, none under 50 (closest: `_step_mixer`, `plan_haul_job`,
`manage_fleet_rescues`, `fabricator_root_targets` at 55). The inflation premise holds for statements only. Left
manual: `drone_depots.resolve_home` (its `log` is the last parameter) and single-exit blocks (no gain).

### Bugs and rule breaks found on the way
- [x] `production_demand.get_raw_material_reason` (403-412) rereads `fabricator.get_recipe_inputs()` per smelter
  recipe inside the loop (CODE_GUIDES script cost rule 1). Hoist one read.
- [x] `"survey.unsupported_targets"` exists 5 times: constants in `archive_cleaner:33`, `survey_requests:30`,
  `vehicle_claims:26`, literals in `unsupported_markers:152,257` and `drone_scout:44`. One owner constant.
  Owner: `unsupported_markers.SURVEY_UNSUPPORTED_KEY` (pinned by `tests/test_constant_owners.py`).
  Left: `LEGACY_ROVER_UNSUPPORTED_KEY` is still in `archive_cleaner` and `vehicle_claims`.
- [x] `TRANSIENT_UNDEPLOY_STATUSES` is defined in `building_swap_upgrade:37` and `pillar_swap:58`.
  Owner: `pillar_swap` (pulls in no `drone_upgrade`). `FATAL_DEPLOY_STATUSES` (both) and
  `fleet_commission.DEPLOY_BLOCKING_STATUSES` are gone: `building_ops.classify()` is the one rule.
- [x] `production_cascade.fabricator_root_targets` (618-631) copies `fabricator_unlocked_outputs()` (36-48).
- [x] `archive_cleaner.clean_logistics_and_bio` docstring lists `bio.fragment_recipes`, which it never handles;
  its `o not in unique_orders` list test is O(n²).

Checked, not a bug: `charging.manage_fleet_rescues` builds `self_known` over `awake`, `drone_service` over `refs`.
Both first `parked.discard(self.name)`, so the station is in one exactly when it is in the other.

### File splits
| File (lines) | Split | Note |
|---|---|---|
| `storage.py` (1927) | housekeeping sweeps (`consolidate_*`, `reclaim_*`, `rebalance_*`, `park_surplus` + helpers, ~1386-1927) to `storage_sweeps.py` | done (1898 to 1421 lines; must_stay_in_inventory and the dock-demand set stay, take path uses them; forage stays: storage._holder_candidates reads it). Was: only orchestrator_automation, drone_upgrade, field_keeper call them; forage (754-824) may move to `crop_automator` |
| ~~`script_parking.py` (1152)~~ done | client API (keys, `ParkRequester`, `wake_*`, `parked_ids`, `parked_nearest`, `_clear_requests`) to `parking_client.py` (engine 929, client 245 lines) | 14 machine scripts import only `ParkRequester` but pay the engine's import; a `ParkRequester` import now runs ~980 opcodes over 8 lib modules, was ~2,490 over 12 |
| `site_supply.py` (1347) | stranded/eviction pipeline (847-1272, incl. `sell_stranded_reagents`) to `site_evict.py` | done (1345 to 851 lines, site_evict 521; add_evicted and mark_reserve stay; site_evict imports as_requests, want_raise, _outposts in-function: site_supply imports it). Was: takes only outposts/requests, returns wants |
| `bio.py` (1269) | shared order/stock helpers (37-545) to `bio_orders.py`, made public | done (bio.py 729, bio_orders.py 524) |
| `wildlife_planner.py` (1187) | retire/teardown block (965-1166) to `wildlife_retire.py` | done (planner 991, wildlife_retire.py 213; `plan_if_due` imports `retire_pass` in-function, cycle) |
| `supply_dock.py` (1300) | order scoring, key unlock, DockRoles (84-730) to `supply_dock_orders.py` | optional |
| `fluid_routing.py` (1462) | tank registry and reserve queries to `fluid_tanks.py` | optional; much of the length is docstrings |
| `logistics_requests.py` (1283) | pickups (310-604), fair share/route (901-1155) | optional; well sectioned, or ignore |
| `archive_cleaner.py` (1162) | none | the helpers below take it under 1000 |

Splits change import sites: use function-level imports where a split would make a cycle, and keep new modules'
bodies cheap (10k import cap).

### Shared helpers (copies across siblings)
Each replaces copies with one helper, like the helper stream above.
- [x] `module_hardness_limit(vehicle, kind)`: the `hardness_limit()` try/except in ~7 places (`vehicle_claims` ×4,
  `vehicle_mining` 150, 302, `pioneer_upgrade` ~258). Removes most branches of `blacklist_target` and
  `can_attempt_target`.
- [x] `key_coords(key)` next to `unsupported_markers.resolve_coordinates`: `poi_X_Y` / `X:Y` parsing in
  `archive_cleaner` 317, 420 and `unsupported_markers` 49-69, with different rounding; also the `leg_key` parse twice
  in `vehicle_claims.clear_unsupported_target`.
- [x] Rescue loop template on `StationController.manage_fleet_rescues` with hooks (units, candidates, fuel,
  `_dispatch_rescue`): `charging` 150 and `drone_service` 264 are the same skeleton.
- [x] `_fly_to_named(...)`: `drone_navigation.fly_to_station` 231-285 and `fly_to_drill` 338-380.
- [x] Shared detail body in `fleet_status` for `drones_card.draw_detail` 133-176 and `vehicles_card.draw_detail`
  158-196. Done as `fleet_card.draw_detail_body()`
  (`fleet_card` imports `fleet_status`, so the body lives there; `BUTTON_H`, `RETIRE_BTN_W` moved with it).
- [x] Deploy-and-check step (`computer.deploy`, `DEPLOY_BLOCKING_STATUSES`, back a state on `no_kit`): 3 copies in
  `fleet_commission._advance`, `_advance_drone`, `fleet_upgrade._swap_drone`. Same family as the open
  "Deploy / undeploy / upgrade sequences onto `building_ops`" candidate above: solve them together.
- [x] `_undeploy_empty(...)` on `BuildingSwapUpgrader`: tail of `warehouse_upgrade._drain_loop` 201-216 and
  `tank_upgrade._drain_one` 188-200; `pillar_swap:344` repeats the status ladder. Same `building_ops` family.
  Done with the step above: `building_ops.deploy_new()` and `classify()` for every deploy, `building_ops.undeploy()`
  in `_undeploy_empty()` and `pillar_swap._undeploy` (its skip ladder stays its own).
- [x] Eject-port-to-storage loop in `storage`: `bio.py` 563, 928, 1031 and `habitat.py` 465.
- [x] Storage idioms: the transfer tail (`res.moved`, busy to `mark_busy`, `snapshot.touched`) in
  `consolidate_warehouse_strays` and `consolidate_storage_bins`; the `port.stacks()` drain loop 3× around
  `drain_port_inventory_first`; is_home resolution that bypasses `outpost_is_home()` (`_holder_candidates`,
  `best_unload_target`).
- [x] Order candidate build: `supply_dock.pick_best_order` 1061-1083 copies `plan_dock_assignments` 811-836.
- [x] Recipe choice skeleton (candidates, claim, hysteresis, join): `smelter._select_needed_ore`,
  `fabricator.choose_recipe`. Skipped, false friends: hysteresis (higher-band preempt vs in-band sticky with
  starvation) and join rule (switch minimum x workers vs crafts left > workers) differ in every step.
- [x] Router connect trial `_try_connect(...)`: `FluidOutputRouter.ensure_connection` 1361 and
  `FluidInputRouter.ensure` 1088.
- [x] Vehicle base: recharge detour (`vehicle_mining._recharge_and_resume_mining`, `pioneer_construction` 159-172,
  `vehicle_charging.recharge_at_nearest`), swallowed `nav.brake()` (3 copies), `energy_for_distance(d)` in
  `vehicle_energy` (inline twice in `drive_with_recharge`). Place per the mixin layer table.
  Shared leg is `drive_to_nearest_station()`; `recharge_at_nearest` kept: it charges even after a failed drive.
- [x] `archive_cleaner`: `_prune_dict_key(key, stale, tag)` + `_reset_if_not_dict(key, tag)` (updater at 614, 656,
  827, 854, 920) and one legacy-retire helper (272, 346, 380, 476, 502, 566).
- [x] `unload_cargo.unload_one` retry loop (115-143) on `storage.send_stack`. (`vehicle_cargo.unload_cargo`; no
  `storage.py` edit needed.)
- [x] `logistics_requests._prune_requests(...)`: `set_requests` updater and `clear_requests`.
- [x] Small: ~~`fuel_assembler.drain_output` push loop ×2~~ (done), `building_ops` kit wait ×2 (`_step_deploy`, `_step_upgrade`),
  `wake_kind`/`wake_for_visit` unpark tail.
  Done: `building_ops._kit_missing()`, `parking_client._unpark()` (then in `script_parking`).

### Long functions to cut into phases
Worst first; phases and proposed helper names are from the triage. Do the shared helpers above first: several
of these shrink on their own.

| Function | Metrics (C901/branches/statements) | Phases |
|---|---|---|
| `bio.BioLabController.step` | 37/41/135 | done: empty chamber, analyze, extract gate, load reagents, buy missing; `_pause(sec)` for ~10 `flush_all(); sleep(); return` |
| `supply_dock.plan_dock_assignments` | 33/31/128 | done (`_DockPlanPass`): collect candidates, held counts, stability pass, assign idle, publish |
| `vehicle_cargo.unload_cargo` | 32/19/96 | done: out port, cargo stacks, `unload_one` as method |
| `archive_cleaner.clean_unsupported_targets` | 30/29/82 | done: merge legacy, `key_coords`, `_is_resolved` shared with `clean_claims` |
| `crop_automator.CropAutomatorController.step` | 30/30/101 | done: layout gate, classify cells, submit plants |
| `smelter._select_needed_ore` | 29/29/88 | sourceable candidates, hysteresis pick, join pick; `Candidate` namedtuple for `c[3]`/`c[4]` |
| `vehicle_charging.recharge_at_station` | 29/30/91 | done: resolve station (calls `charging_station` twice), dock, charge watchdog |
| `site_evict.evict_stranded` | 28/28/77 | gather, track first seen, allocate, publish home request |
| `supply_dock.SupplyDockController.step` | 28/30/82 | done: release current, ensure order, load materials |
| `fluid_routing.FluidOutputRouter.ensure_connection` | 26/26/90 | blacklist if stalled, fast path, try targets |
| `production_cascade.fabricator_root_targets` | 25/25/71 | fold manual, order book, dock, consumers; `_consume_at` |
| `bio_volcanic._aggregate_material_demand` | 24/23/62 | done: open casts, net of forged, urgent need, net of staged |
| `drone_upgrade.maintain_modules_at_depot` | 24/23/69 | upgrade tiers, strip surplus, fill empty |
| `vehicle_claims.blacklist_target` | 24/24/66 | done: scanner type (if-ladder, not a dict), hardness helper, research snapshot |
| `archive_cleaner.clean_claims` | 23/22/72 | done: `_claim_reject_reason` |
| `bio.BioExchangeController.sweep_and_deliver` | 23/23/80 | done: deliver units, on order complete, default order |
| `fluid_routing.FluidInputRouter.ensure` | 22/24/97 | handle conflict, judge own link, try candidates |
| `storage_sweeps.rebalance_inventory_to_warehouses` | 22/21/85 | move to warehouses, swap into warehouse |
| `scan_groups.plan_step` | 21/20/68 | done: `{phase: fn}` dispatch for nbrs/sweep/exact/rank/out |
| `drone_mining.biosite_candidates` | 20/19/81 | score site, log candidates, `_tons(lf)` |
| `power_solar.SolarNightGuard.manage_night_loads` | 15/17/52 | night need, shed, restore (shared with day recovery); name the inline factors |
| `script_parking._park_and_tend` | 18/19 | veto, park one; 14 parameters into one pass state |

MINOR (one extraction each, do when touching the file): `bio.BioCollectorController.step` (keep: needs two cuts), `bio_retire.BioRetirement.step` (done),
`biomass_mixer_gate._step_mixer` (done), `essence_liquifier.feed_from_depot` (keep: needs two cuts), `field_keeper.run_choice` (dispatch dict +
`_visit`; keep: needs two cuts), `field_layout.path_cells` (done), `fleet_commission._advance`/`_advance_drone`, `drone_hauler.load_at_depot`,
`drone_haul_plan.plan_haul_job`, `drone_weather._aftermath_candidates`, `drone_depot.flush_surplus`,
`vehicle_navigation._drive_leg` (`_abort_leg` for 7 exits; keep: needs two cuts), `vehicle_charging.drive_with_recharge` (done),
`vehicle_mining.build_mineral_site_candidates` (reuse `cuttable_sites`; under the limits already), `pioneer_commission._fit_pass` (live via rover),
`pioneer_construction._execute_construction`, `site_supply.plan_site`/`publish_site_requests`, `smelter.load_ore`,
`fabricator.choose_recipe`, `storage._holder_candidates`/`drain_port_inventory_first`/`consolidate_warehouse_strays`,
`pull_plan.pull_sources`, `unsupported_markers.update_unsupported_markers` (keep: needs two cuts), `script_parking._strays`,
`archive_cleaner.clean_survey_spiral` (done), `wildlife_planner._walk`/`_report`, `turbine_commit.step`, `vent_cycles.step`,
`building_ops._step_deploy`, `contract/lattice.enumerate_frontier`, `contract/core_sample.solve_core`.

### Keep (ignore-file candidates)
Rule of thumb from the triage: keep flat state machines and status-dispatch loops, documented priority ladders,
per-type game-API probing, data-validation guards, and atomic or hot-path algorithms where calls cost opcodes.
- Atomic/hot path: `drone_haul_plan.plan_route_for`, `drone_haul_plan.candidate_routes`, `harvester_heat._expand_chunk`,
  `production_source.can_source_item`.
- State machines and polls: `fleet_upgrade._advance_drone`, `drone_weather._collect_at_site`, `drone_navigation._fly_leg`,
  `vehicle_mining.mine_current_site`, `fuel_assembler.step`, `job_haul._run_plan`, `biomass_mixer_gate._step_paused`,
  `script_parking.step`, `script_parking._solar`.
- Priority ladders and fallbacks: `field_keeper.choose`, `bio_processor._load_next_sample_inner`, `drone_depots.resolve_home`,
  `drone_energy.detect_engine`, `unsupported_markers.resolve_coordinates`, `bio_orders.focus_local_order`.
- Per-type APIs and guards: `bio_orders.processor_is_idle`, `bio_retire.drain`, `drone_service.manage_docked`,
  `production_demand_record.demand_signature`, `production_source._machine_holdings`, `wildlife_model.stage_inputs`
  (mirrors the simworker table 1:1).
- Flat sequences: `seed_maker.step`, `habitat.release_step`, `plants_retire.step`, `early_buyer.place_buildings`,
  `weather_signals.step`, `orchestrator_automation.park_if_due`, `wildlife_planner._wakes_and_alerts`,
  `production_demand.get_smelter_demands`/`get_material_demands`, `site_plan.plan_sites`,
  `production_cascade._cascade_fabricator_output_demand`/`blueprint_required_ladders`, `storage.take_item`/
  `reclaim_inventory_only_items_from_warehouses`/`best_unload_target`/`_items_demanded_by_active_dock_orders`,
  `supply_dock.drain_dock_cargo`, `vehicle_mining.remote_ore_need`/`build_local_stockpile_candidates`/
  `select_best_mining_target`, `vehicle_cargo.pull_from_source`, `vehicle_survey.scan_and_survey`/`survey_known_pois`,
  `drone_upgrade.convert_to_heli_if_requested`, `archive_cleaner.clean_machine_status`/`clean_building_entries`,
  `script_parking._low_reserve_grids`, `bio.BioExchangeController._cleanup_orphaned_artifacts`,
  `biomass_mixer_gate._discover`, `bio_coastal._solve_lamps`, `fluid_routing.discover_network_buildings`.
- Pioneer-only, low value while pioneers are semi-retired: `pioneer.next_job`, `pioneer_upgrade._rebalance_container_split`,
  `pioneer_upgrade.handle_sport_nav_request_if_active`, `pioneer_refit.refit`.

Add these to `size_scan_ignore.txt` with a one-line reason each only after the `@method_block` pass and a rescan:
some drop under the limits and need no entry.

### Order
One session per step, each its own commit with tests, ruff and pyright green:
1. Bugs and rule breaks (small, independent).
2. [x] `@method_block` pass on the inflated functions, rescan.
3. Shared helpers, one family per commit (the deploy/undeploy family together with the `building_ops` candidate).
4. File splits: `script_parking` first (import cost on 14+ scripts), then `storage`, `site_supply`, `bio`,
   `wildlife_planner`.
5. Long functions still over the limits after 2-4.
6. Fill the ignore file; rerun `size_scan.py --summary` and record the counts here.
