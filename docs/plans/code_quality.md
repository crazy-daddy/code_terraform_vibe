# Plan: code quality

Status: **in progress** (helper stream). Helper unification started 2026-10-09. Size scan triage done
2026-10-22; its function follow-ups landed the same day, the `storage.py` split is planned.

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
| `notify()` called directly (2026-10-23) | 6 guarded `_notify` copies (`power`, `power_solar`, `reactor`, `oil_generator`, `script_parking`, `wildlife_planner`) | this branch |
| `building_ops.upgrade()`, `deploy_new()`, `undeploy()` (2026-10-23) | raw `computer.deploy()` / `undeploy()` / `upgrade()` in `early_buyer`, `fleet_decommission`, `fleet_upgrade`, `storage_expand`, `machine_pack_upgrade`, `pillar_swap`; `CALL_FAILED_STATUSES` for calls that could not ask | this branch |

## Open candidates
Both earlier candidates (`_notify` wrappers, `building_ops` raw calls) are in the Done table. The second sweep (2026-10-23) judged every family: sites, verdicts and the full ranking are in [helpers_sweep_candidates.md](helpers_sweep_candidates.md) and [helpers_sweep_candidates_2.md](helpers_sweep_candidates_2.md) (small families, keep pairs, new families). `keep` pairs are in `clone_scan_ignore.txt`. Ranked `drift-bug` and `merge` families, best first (details and sites in the files; the plan is the TODO box "Helpers: implementation plan for the judged sweep families"):
1. drift-bug: survey spiral readers raise on a non-dict, `SURVEY_SPIRAL_KEY` defined twice (S).
2. drift-bug: `vehicle_claims.get_unsupported_targets` and `archive_cleaner._merge_unsupported` disagree on legacy pioneer keys (S).
3. merge `archive.get_dict` (~25 sites; opens the spiral fix and the survey bypassers).
4. merge a research unlock helper (12 sites; five sites let a raised lookup escape today, the helper swallows it).
5. merge `components.outposts()` (~20 sites).
6. merge `archive.mutate` / `pop_entries` (~30 updaters, risk medium; after 3, in small batches).
7. merge `swallow.safe_call` (6 defs, ~30 call sites).
8. merge `cash.shop_prices` / `shop_price` (8 sites).
9. merge `components.building_ids_at` (6 sites).
10. merge keyed-state wrappers and sub-entry lookups on `archive.mutate` / `dict_entry` (9 sites).
11. merge `components.outpost_by_id` (3), `components_at` (2), `sensor_value` (3).
12. merge `geometry.dist` (3 defs, 21 calls) and `game_clock.now_tick` (4 defs).
13. merge depot walks on `discover_drone_depots` (2 sites, risk medium: memo lag in the swap flow).
14. merge the small S families (`item_tiers.best_tier`, pickup ledger totals, `parking_client.is_shedded`, `priority.ladder_totals`, `field_layout.rc_to_sector`, lazy fail dicts, `_raise_target`, building type counts and more) and the remaining singles (ranks 14 and 15 of the candidates file).
- Guarded raw `notify()` calls (`try: notify(...) except: swallowed`): `bio.py` (2), `charging.py`, `drone_service.py`, `harvesting.py`, `seed_maker.py`, `thermal_cap.py`, `vehicle_cargo.py`, `vehicle_charging.py`, `vehicle_claims.py` (all `scripts/4_controlpanel/lib`). `notify()` only raises on bad arguments, so the guards hide our own bugs; same rationale as the dropped wrappers.

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

Smaller: none left. Heater vs condenser steam latches are deliberate (condenser 250 t/h takes only a near-full
pool's surplus, heater 12 t/h bonus feed runs to 0.50); the ladder is now written down in power_fluids.md.

**To think about after PR #36 (not a must): stock refill hysteresis.** The minimum load is
`logistics_requests.min_load_units()` (`min(HAUL_MIN_LOAD_UNITS, reachable)`, drones and ground alike), so a
2-unit tar shortfall on the STOCK band is a 2-unit trip when a hauler has nothing better. That may be fine for an otherwise idle hauler, and a
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
  unless changed" is a different pattern from a value cache. They could share a helper later, but it isn't a
  `TickCache`.

## Next sweep
Ran 2026-10-23: four harvest angles (scan pairs now including `autoplay/` and short functions, game API anchors, bypassed discovery, known families refresh), merged and judged in [helpers_sweep_candidates.md](helpers_sweep_candidates.md) and [helpers_sweep_candidates_2.md](helpers_sweep_candidates_2.md). Plan: [helpers_sweep.md](helpers_sweep.md). The families that earlier notes listed here (archive read/validate wrappers, per-outpost building filters, `research.is_unlocked`, `_dist`, the recipe BFS) are all judged there. Before another harvest, land the ranked families above and list them as done in the harvester briefs.

Still unswept (the "Harvest gaps" of the candidates file):
- `clone_scan` clusters c32 (~90 one-line accessors) and c72 were checked only for the listed families; stub bodies (`NotImplementedError`, default hooks) were skipped.
- `archive.get` shape counts are regex estimates (31 multi-line calls unparsed); re-count with an AST pass when the `get_dict` swap lands.
- Generic `get_component` sites (hundreds) stay unenumerated; the target is one typed accessor per kind in `components.py`, outside the judged families.
- Whether `fluid_routing.discover_network_buildings` is pure under wildlife `run_atomic` is unverified (blocks nothing; left on its current callers).
- `free_elsewhere` as `sum_tiers(free_elsewhere_tiers(...))` needs `outpost_free_tiers`' need-only split to equal the band sum (unverified, kept apart).

## Size scan triage (2026-10-22)
Status: **done** (Order 1-6); open follow-ups below.

`size_scan.py` at default limits (file 1000 lines; Ruff C901 10, PLR0912 12, PLR0915 50). Seven agents judged
every hit by domain as REFACTOR, MINOR or KEEP. Size mostly flagged **copies between siblings**, not single long
functions, and about half the hits were defensible. No cut was blocked by CODE_GUIDES script cost: the flagged
loops are sleep-bound game I/O or run once per cycle (the atomic and hot-path keeps are the exception).

| Point | File hits | Function hits | Ignored |
|---|---|---|---|
| First run, `6815306` (270 files) | 9 | 139 | 0 |
| After `@method_block` (step 2) | 9 | 140 | 0 |
| After steps 3-5, `6c0aa67` (276 files) | 5 | 85 | 0 |
| Step 6 second cuts | 5 | 81 | 0 |
| Step 6 ignore file | 2 | 6 | 78 |

### What landed
- Step 1, bugs and rule breaks: one `get_recipe_inputs()` read in `production_demand.get_raw_material_reason`; one
  owner for `"survey.unsupported_targets"` (`unsupported_markers.SURVEY_UNSUPPORTED_KEY`, pinned by
  `tests/test_constant_owners.py`); `pillar_swap` owns `TRANSIENT_UNDEPLOY_STATUSES` and `building_ops.classify()`
  is the one deploy-status rule; `fabricator_root_targets` reuses `fabricator_unlocked_outputs()`;
  `archive_cleaner.clean_logistics_and_bio` lost its wrong docstring item and O(n²) dedupe.
- Step 2: 19 whole-function debug blocks with 2+ `end()` exits use `@method_block` / `@log.block`. Only statement
  counts fell (3 to 18 per function): `start`/`end` add no branch. Left manual: `drone_depots.resolve_home` (its
  `log` is the last parameter) and single-exit blocks.
- Step 3, shared helpers: `module_hardness_limit()`, `key_coords()`, the `StationController.manage_fleet_rescues`
  template, `_fly_to_named()`, `fleet_card.draw_detail_body()`, `building_ops.deploy_new()` / `classify()` /
  `undeploy()` / `_kit_missing()`, `BuildingSwapUpgrader._undeploy_empty()`, the storage eject loop and transfer
  tail, `unload_one` on `storage.send_stack`, one dock order candidate build, `_try_connect()` for both fluid
  routers, `drive_to_nearest_station()` and `energy_for_distance()`, `archive_cleaner._prune_dict_key()` /
  `_reset_if_not_dict()` and one legacy-retire helper, `logistics_requests._prune_requests()`,
  `parking_client._unpark()`. Skipped as false friends: smelter and fabricator recipe choice (hysteresis and join
  rule differ in every step).
- Step 4, file splits: `parking_client` from `script_parking` (a `ParkRequester` import ran ~2,490 opcodes over
  12 modules, now ~980 over 8), `storage_sweeps` from `storage`, `site_evict` from `site_supply`, `bio_orders` from
  `bio`, `wildlife_retire` from `wildlife_planner`.
- Step 5: 22 long functions cut into phases, worst first (`bio.BioLabController.step` at 37/41/135 down to
  `script_parking._park_and_tend`), plus one extraction each for the MINOR hits.
- Step 6: second cuts for `drone_hauler.load_at_depot`, `storage_sweeps.consolidate_warehouse_strays`,
  `drone_haul_plan.plan_haul_job` and `bio.BioCollectorController.step`. Every other reviewed keep is in
  `devtools/code_scan/size_scan_ignore.txt` with its reason.
- Revisit rule: every ignore entry pins its metrics at review (`size_scan.py --pin`); the scan re-flags an entry
  that grows past pin + max(3, 10 %) (file lines: + max(50, 10 %)) and lists unpinned and stale entries.

Keep rule: flat state machines and status-dispatch loops, documented priority ladders, per-type game-API probing,
data-validation guards, atomic or hot-path algorithms where calls cost opcodes, phases that share many mutable
locals ("needs two cuts"), one-off contract solvers, and pioneer-only code while pioneers are semi-retired.
Splits change import sites: use function-level imports where a split would make a cycle, and keep new modules'
bodies cheap (10k import cap).

### Open follow-ups
The scan reports no hit (`archive_cleaner.py` itself is an ignore entry: a migration clutch for changing archive
keys, accepted as-is).
- [x] `storage.py` (1434 lines) split by topic (2026-10-22): data layer `storage.py` (762 lines), take path
  `storage_take.py` (269), unload path `storage_unload.py` (432); plan in
  [storage_split.md](done/storage_split.md).
- [x] Six function hits extracted (2026-10-22): `vehicle_claims.clear_unsupported_target`,
  `drones_card.draw_detail`, `site_evict.sell_stranded_reagents`, `archive_cleaner.clean_logistics_and_bio`,
  `job_haul.HaulJob._claim_route`, `pioneer_commission._fit_pass`. The scan has no function hits left.

Not scan hits:
- [x] `script_parking` helpers (2026-10-22): `start_script()` and `set_powered()` moved to `components`,
  `stray_alerts()` and `STRAY_KEY` to `parking_client`. Their callers skip the engine import (about 1,600
  opcodes less for `building_ops`, `pillar_swap`, `turbine_commit`, `fleet_decommission`).
- Optional splits, ignored for now: `supply_dock` (orders to `supply_dock_orders`), `fluid_routing` (tanks to
  `fluid_tanks`), `logistics_requests` (pickups, fair share).

### Order
One session per step, each its own commit with tests, ruff and pyright green:
1. [x] Bugs and rule breaks.
2. [x] `@method_block` pass on the inflated functions, rescan.
3. [x] Shared helpers, one family per commit.
4. [x] File splits.
5. [x] Long functions still over the limits after 2-4.
6. [x] Second cuts, ignore file, counts recorded above.
