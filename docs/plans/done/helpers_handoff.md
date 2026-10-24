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

## What is next
- Operator: approve the merge (`python devtools/agent_worktree.py merge helpers-impl-2 -m "<subject>"`).
- Phase 3 of the plan in worktree `helpers-impl-3`: Tasks 3.1-3.5.

## Open questions and leftovers
- Coercing updaters outside the Phase 2 lists remain (`pioneer_upgrade` set-or-pop is Phase 3 rank 15; `cash.release`, `retired_machines.retire`, `seed_maker` `_claim` / `_release`, `fleet_claims_common.set_flagged`). `archive_ipc.md` states the rule for new or edited sites.
- Three clone-scan ignore entries fall below 0.85 in files Phase 2 did not touch: `fluid_routing` `ensure_output_logged ~ ensure_input_logged`, `drone_navigation` `fly_to_drill ~ fly_to_station`, `production_source` `fabricator_recipes ~ fuel_assembler_recipes`. Phase 3 close can drop them.
- `cash.shop_price` does not cache a miss (pre-existing); a missing catalogue now logs one swallowed line where the old autoplay reads were silent.
- No tests cover the one-line autoplay `read_prices` / `kit_price` delegations.
- `wildlife_planner._population` returns `float(...)`; a None reading now warns through `swallowed`.
