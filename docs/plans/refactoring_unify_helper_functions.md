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

## Open candidates
- **`_notify(text, level, duration)`**: 4 identical copies (`reactor`, `oil_generator`, `power`, `power_solar`),
  each `notify()` in a swallowed try. About 10 raw `notify()` calls elsewhere have no guard (`bio`, `charging`,
  `drone_service`, `harvesting`, `fluid_routing`). One guarded helper, maybe next to `swallowed`.
- **Real seconds per game hour**: `clock.real_seconds_per_hour()` with a 25.0 fallback is read in 7 places
  (`drone_navigation`, `vehicle_navigation`, `exotic_cap`, `harvester_heat`, `reactor`, `thermal_cap`,
  `weather_signals`). A `game_clock` reader fits there. `flight_timeout_ticks` and `drive_timeout_ticks` are then
  one formula with a different speed function and `min_ticks`.

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
