# Helpers handoff (2026-10-24, Phase 2 session)

## What landed
- Branch `agent/helpers-impl-2` (worktree `.claude/worktrees/helpers-impl-2`), 25 commits on 25a52b1, not merged yet: Tasks 2.1-2.6 of [helpers_sweep_impl.md](helpers_sweep_impl.md).
  - `ArchiveClient.mutate` / `pop_entries` / `dict_entry`; keyed-state wrappers, lookups, patches and the updater batches moved onto them. `set_entry` / `pop_entry` are one-line `mutate` calls.
  - `swallow.safe_call(where, read, default)`.
  - `cash.shop_prices()`; `cash.shop_price(item_id, fallback=None)` keeps its cache, its four callers pass `fallback=0`. The autoplay price reads call `cash.shop_prices()`.
  - `components.building_ids_at`, `outpost_by_id`, `components_at`, `sensor_value`.
  - `geometry.dist`; the four autoplay tick copies call `game_clock.now_tick`.
- Docs: `archive_ipc.md`, `lib_map.md`, `Landed:` lines in the spec, Done table in [code_quality.md](code_quality.md). Clone pairs >= 0.85: 1032 before, 1032 after (one ignore entry removed, one added).

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

## Close (2026-10-24, on main)
The stream is closed; the plan moved to [code_quality.md](code_quality.md) with status done.
- Landed: `cash.release`, `retired_machines.retire` on `archive.mutate`, `fleet_claims_common.set_flagged` on `set_entry` / `pop_entry` (no hand-written non-dict coerce is left outside the four prune-then-set sites `archive_ipc.md` names); the "Commission home sentinel" family (`fleet_commission._queue` maps a `HOME_OUTPOST_ID` `home_base` / `outpost` to None, the two card wrappers stay for their log lines); `_prune_fleet_dict` takes its log noun as a parameter; the `site_evict.storage_outposts` swallow tag names its module.
- Judged and dropped, no behavior gain:
  - `_depot_ids` returns `set()` on a failed discovery and stalls retire: fails closed, logged, as before.
  - `SHEDDED_KEY ... or []` reads (`script_parking`, `power` x2, `biomass_mixer_gate`): a list key, `get_dict` does not apply.
  - `bio.py` reads `ord_info.name` unguarded: `name` is a declared field of the order model (`docs/models/earth_orders_models.md`), the removed `try` guarded the game calls, not the attribute.
  - `components.component` two-argument call keeps its pyright ignores: the typed alias keeps per-name Literal returns.
  - `building_type_counts` and `_prune_fleet_dict` have two tests each; `commission_card` / `site_evict` trace a raised walk as `buildings={}`; the `FieldKeeperController.__new__` test helpers lack the fail dicts (suite green).
  - `cash.shop_price` does not cache a miss (pre-existing); a missing catalogue logs one swallowed line.
  - `wildlife_planner._population` warns through `swallowed` on a None reading.
  - No tests for the one-line autoplay `read_prices` / `kit_price` delegations.
