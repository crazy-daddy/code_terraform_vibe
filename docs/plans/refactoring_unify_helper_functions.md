# Plan: unify duplicated helper functions

Status: **in progress** (started 2026-10-09).

## Context
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
| `is_fresh` for Smelter/Fabricator wants | 2 hand-rolled checks in `production_core` | this branch |

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
   neutronium never get cleared. Use `outpost_mining.RAW_ORE_ITEM_IDS` and the smelt products.
8. **Drone chassis swap forgets less than decommission**: `fleet_upgrade._migrate_drone_keys` skips
   `release_pickups`, `release_yield`, `clear_stage`. No live effect: the hauler takes the swap only after its work in
   flight finishes, and delivery releases its pickups. Cleanup only: one `forget_machine()` for both paths.

Smaller: "near a fluid" is an edge-gap in `supply_tiers`/`outpost_needs` but a centre
distance in `outpost_sites`; `grid_geom.outpost_box()` spans +y while `outpost_sites` and the game (`ux()`) span -y from
the anchor (needs a headless check); `drones_card` paints `stalled_no_route` red but nothing rescues it; free-slot keep
4/1/1 and slot size in four places (`warehouse_upgrade._bin_plan` packs to a full 2000); minimum haul load 50 drone vs 10
ground; sonar range fallbacks 50 / 0.75x / 0; heater vs condenser steam latches; construction hold freshness hand-rolled.

**To think about after PR #36 (not a must): stock refill hysteresis.** The minimum load is
`min(PULL_MIN_LOAD_UNITS, reachable)` (`vehicle_cargo`; drones the same with 50), so a 2-unit tar shortfall on the
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
- **Stall cooldowns** (`drone_haul_plan` fail counter vs `vehicle_cargo._pull_unviable` tick stamp): different
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
