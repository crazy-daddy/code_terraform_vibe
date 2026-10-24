# Helpers handoff (2026-10-24, Phase 1 session)

## What landed
- Branch `agent/helpers-impl-1` (worktree `.claude/worktrees/helpers-impl-1`), 12 commits, merged into `main` (c08b654): Tasks 1.1-1.7 of [helpers_sweep_impl.md](helpers_sweep_impl.md).
  - `ArchiveClient.get_dict`, swept over the listed def-level, try-guarded, line-level and `autoplay` sites.
  - Spiral drift-bug: `vehicle_survey.spiral_next_index()`; `SURVEY_SPIRAL_KEY` and `LEGACY_PIONEER_SPIRAL_KEY` defined once.
  - Unsupported-target drift-bug: `unsupported_markers.merge_unsupported()` / `key_tile()` shared by fleet and cleaner; `vehicle_survey.unscanned_pois` dropped its raw `X:Y` lookup.
  - `components.research_unlocked()` / `all_research_unlocked()` (12 sites), `components.outposts()` (6 copies, prologues in `L/` and `ap/`).
  - Final review fix: `weather_signals.discover_stations` keeps its own network read, so `refresh_stations` keeps the last station list on a raise.
- Docs: `archive_ipc.md`, `lib_map.md`, `Landed:` lines in both spec files, Done table in [code_quality.md](code_quality.md). Clone pairs >= 0.85: 1219 before, 1032 after.

## Decisions taken in the session (beyond the plan)
- `archive_cleaner.clean_claims` keeps its raw reads: its write check compares the raw values with the cleaned map, so `get_dict` would stop it repairing a malformed claims key.
- `weather_signals.discover_stations` stays apart (against the plan's Review Focus 5): see above.
- Modules with a local or parameter named `outposts` call `components.outposts()` through `import components`.

## What is next
- Phase 2 of the plan in worktree `helpers-impl-2`: Tasks 2.1-2.6.

## Open questions and leftovers
- About 140 unlisted `archive.get(K, {})` lines remain; the spec says they switch as they are touched. A bulk batch could take them in Phase 3.
- Two `outposts()` copies not in the spec site list: `storage_sweeps._all_outposts` (returns None on a raise), `role_demand._network_outposts`.
- The one-line `get_dict` wrappers now show up as clone clusters (they keep their names, per the spec). No ignore entries were added.
- Worktree pyright reported 6 errors for unresolved `typer`/`watchdog` (the worktree's pip-less venv). Main is clean after the merge.
