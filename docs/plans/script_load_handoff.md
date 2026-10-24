# Script Load handoff (2026-10-24)

Written after the Code Quality stream closed (plan: [done/code_quality.md](done/code_quality.md)). The next
stream is the "Script Load" section of `TODO.md`. This file says what is already measured, what is open, and
the order to take it in. Numbers are from [performance_planning_2026-10.md](performance_planning_2026-10.md)
("Results" table) unless a commit is named.

## State of the section

- **Planning-phase performance**: Vectors 1-6 of the plan have outcomes. Vector 1 (tier snapshot) landed
  (`aa72616`, `d35a168`); Vector 2 landed partly (`065c2a8`, 124 to 105 ticks per step); Vector 3 fixed trigger
  (a) (`49079d2`), dropped (b); Vector 4 closed, not needed; Vector 5 closed by measurement (1 tick per call);
  Vector 6 landed (`f50ef15`, `9af116d`). [vector1_tier_snapshot_2026-10.md](done/vector1_tier_snapshot_2026-10.md)
  still carries 31 unchecked task boxes although its outcome rows exist: tick them from the commits, then move
  it to `done/`.
- **Import-cap margin**: nothing landed. The 9,637-step count for the `outpost_plan` chain has no committed
  method that measures it (plan, "Vector 6" outcome, last bullet). `devtools/perf/tick_profile.py:418` only
  explains the crash after the fact.
- **More atomic work** (Harvester `publish`, demand cascade on a prefetched snapshot): not started.
- **Centralize Smelter/Fabricator demand**: record, publisher and Smelter split landed (2026-10-11); open are
  the Fabricator split, readers, intermediate netting, headless A/B.
- **Event-driven Automation**: Phases 1, 1.3, 1.6, 2 done; open are the live confirm of Phase 2, the Phase 3.2
  solar timer, and the deferred review minors listed under the TODO item.
- **Splitting `orchestrator_automation.py`**: partly done (2026-10-11); only if storage passes measurably delay
  grid supervision.

## Open measurements the plan names

- `OutpostPlanner._replan` costs 276 ticks on save 0839 outside `_rank` (likely `snapshot`, `needs` or
  `plan_hosts`); the coarse filter ~155 ticks, and `FILTER_CHUNK` cannot grow (dense-pipe worst case 3355 ops).
- `drone_haul_plan.outpost_sources` stays ~95 ticks after Vector 1; debug lines are ~19 of those, the rest is
  uninvestigated (likely `view.free` / `most_free`). Debug logging as a whole costs the drone plan ~93 ticks
  per call.
- The snapshot publisher step costs ~105 ticks on 0839 and cancels the role-publish saving inside the
  orchestrator. The record is ~16 KB, 88 % `free`; trim to `FAIR_BANDS` plus the top band only if the
  `archive.get` cost shows.
- Real-save peak steps per callback are unmeasured (plan, "Tool gaps"); `step_profile.py haul` peaks at ~2,224
  steps (22 % of the cap) on synthetic input.

## Recommended order

1. **Import-cap check** (one session, small). A correctness risk, not a speed item: a chain over the cap crashes
   the script at load. Build the measurement first: count the steps of a slot's top-level import chain in the
   headless runner (`devtools/simulation/headless/save_scripts.py` already knows `stepsLimit`), report every
   slot over a threshold (suggest 90 % of 10,000), and fail `tests/` or a devtools check when one exceeds it.
   Then trim the `outpost_plan` chain (work out of module bodies, lazy imports) until `infra_planner_automation`
   has real headroom, and record the before/after counts in the plan's Results table.
2. **Vector 1 plan bookkeeping** (same session or a short one): tick the boxes, move the file to `done/`.
3. **`_replan` outside `_rank`** (one session): profile with the Vector 6 command, find which of `snapshot`,
   `needs`, `plan_hosts` carries the 276 ticks, then the usual hoist or slice. Rankings are pinned by a test.
4. **`outpost_sources`** (one session): profile `view.free` / `most_free`; pairs with trimming the record's
   `free` section if `archive.get` shows.
5. **More atomic work** only after 1-4, and only with a measured target: the plan's "Do not pursue" list shows
   how often an unmeasured item turned out to cost nothing.

Each session: own worktree (`python devtools/agent_worktree.py new <topic>`), one Results row with the same
save, gate and window as its baseline, `cavecrew-reviewer` before the merge.
