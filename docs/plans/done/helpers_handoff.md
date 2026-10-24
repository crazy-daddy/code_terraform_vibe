# Helpers handoff (2026-10-24, Phase 2 session)

## What landed
- Branch `agent/helpers-impl-2` (worktree `.claude/worktrees/helpers-impl-2`), 25 commits on 25a52b1, not merged yet: Tasks 2.1-2.6 of [helpers_sweep_impl.md](helpers_sweep_impl.md).
  - `ArchiveClient.mutate` / `pop_entries` / `dict_entry`; keyed-state wrappers, lookups, patches and the updater batches moved onto them. `set_entry` / `pop_entry` are one-line `mutate` calls.
  - `swallow.safe_call(where, read, default)`.
  - `cash.shop_prices()`; `cash.shop_price(item_id, fallback=None)` keeps its cache, its four callers pass `fallback=0`. The autoplay price reads call `cash.shop_prices()`.
  - `components.building_ids_at`, `outpost_by_id`, `components_at`, `sensor_value`.
  - `geometry.dist`; the four autoplay tick copies call `game_clock.now_tick`.
- Docs: `archive_ipc.md`, `lib_map.md`, `Landed:` lines in the spec, Done table in [code_quality.md](../code_quality.md). Clone pairs >= 0.85: 1032 before, 1032 after (one ignore entry removed, one added).

## Decisions taken in the session (beyond the plan)
- `mutate` edits the stored dict in place, like `set_entry` / `pop_entry`; `supply_dock`'s old `dict(stored)` copy went with it.
- The four getattr-by-name sites pass `lambda: getattr(obj, m)()`, not a bound method: a bound method would raise `AttributeError` outside the guard.
- Named wrappers (`_read`, `_call`, `_safe`, the `safe_call` one-liners, the `_tick` / `_now_tick` one-liners) keep their names as one-line calls.
- Autoplay sites call `L/cash.py` directly: all three autoplay files already imported `cash` (directly or through `pillar_swap`).
- Apart: `building_ops._ids_at` (None when unreadable; `[]` would misread machines as new), `feed_maker._read_habitat_ids` (order-sensitive), `production_sites.outpost_by_site_id` (its `_all_outposts()` scan carries the home fallback), `seed_maker._mark_tried` keeps its `self._tried` assignment inside the `mutate` fn.

## Phase 3 summary (2026-10-24, branch `agent/helpers-impl-3`)
Phase 2 merged on main (22ece059). Phase 3 landed Tasks 3.1-3.5 of [helpers_sweep_impl.md](helpers_sweep_impl.md); the sweep is complete.
- Landed: decommission depot walk on `discover_drone_depots`; the 13 part 2 small families (`item_tiers.best_tier`, `_pickup_totals`, `parking_client.is_shedded`, `priority.ladder_totals`, `geometry.ceil_int`, `RecipeClaimMixin.next_sleep`, `drone_upgrade.category_ladder`, `field_layout.rc_to_sector`, `wildlife_complete`, harvester fail dicts, `_raise_target`, `_prune_fleet_dict`, `components.building_type_counts`); the singles (`components.component(id, where)`, `cash.balance`, charging `all_stations`, `network_habitats`, sport-nav flags, wants on `publish_status`, `CASCADE_MAX_DEPTH`, `dock_order_prios(key)`); the solar nit; the 3.4 minors (early_buyer and decommission call-failed handling, one `CALL_FAILED_STATUSES`, ten direct `notify()` sites). Clone pairs >= 0.85: 1032 at 22ece059, 1051 now (merged pairs gone, 55 new pairs between 3-line functions and the new helpers); three ignore entries dropped.
- Kept apart by ruling: `fleet_upgrade._depots` (fresh read after a deploy beats the 20-tick memo); `ap/outpost_needs.read_outposts` (a raised walk must skip the outpost, `{}` reads as empty); `water_sink._water_tanks` (`discover_network_buildings` is not memoized); decommission keeps its per-status split (call-failed stays stopped, refusals restart because the Pioneer reruns its sell-parts prep); notify sites go direct, no helper; `dock_order_prios` gained a `key` parameter because the two bodies read different keys.
- Not landed: the "Commission home sentinel" family (`fleet_commission._queue`) is outside the ranking and still open.

## Open questions and leftovers
- Coercing updaters outside the Phase 2 lists remain (`pioneer_upgrade` set-or-pop is Phase 3 rank 15; `cash.release`, `retired_machines.retire`, `seed_maker` `_claim` / `_release`, `fleet_claims_common.set_flagged`). `archive_ipc.md` states the rule for new or edited sites.
- Three clone-scan ignore entries fall below 0.85 in files Phase 2 did not touch: `fluid_routing` `ensure_output_logged ~ ensure_input_logged`, `drone_navigation` `fly_to_drill ~ fly_to_station`, `production_source` `fabricator_recipes ~ fuel_assembler_recipes`. Phase 3 close can drop them.
- `cash.shop_price` does not cache a miss (pre-existing); a missing catalogue now logs one swallowed line where the old autoplay reads were silent.
- No tests cover the one-line autoplay `read_prices` / `kit_price` delegations.
- `wildlife_planner._population` returns `float(...)`; a None reading now warns through `swallowed`.
- Phase 3 deferred minors (from the review ledger):
  - `_depot_ids` returns `set()` on a failed discovery, which stalls retire (fails closed, logged, as before).
  - `script_parking` reads `SHEDDED_KEY` with `or []`, outside the spec site list.
  - `archive_cleaner._prune_fleet_dict` derives its log noun by splitting `tag`; pass the noun explicitly.
  - `building_type_counts` and `_prune_fleet_dict` have two tests each, not one.
  - `commission_card` and `site_evict` now trace a raised walk as `buildings={}`; log only.
  - `site_evict` `storage_outposts` swallow tag names `site_supply.storage_outposts` (carried-over wrong module).
  - `FieldKeeperController.__new__` test helpers (`test_loose_items`, `test_starter_layout`, `test_harvester_amplify`) lack the fail dicts; suite green.
  - `components.component` two-argument call keeps pyright ignores (the typed alias keeps per-name Literal returns).
  - `pillar_swap.TRANSIENT_UNDEPLOY_STATUSES` restates the `CALL_FAILED` pair as literals.
  - `bio.py` `ord_info.name` is read outside any guard (the removed `try` covered it).
