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
  is closed (all boxes ticked, moved to `done/`, 2026-10-24).
- **Import-cap margin**: done 2026-10-24 (item 1 below). `devtools/perf/import_steps.py --save SAVE` measures
  every slot's import chains and fails over 90 % of the cap; the `outpost_plan` chain went 9,622 to 7,628 steps
  on 0839 (plan, Results, 2026-10-24 "Import-cap margin" row).
- **More atomic work**: Harvester `publish` done 2026-10-24 (plan, Results, "Harvester `publish`" row): the
  cost sat in Cell attribute reads outside atomic, not in the pure scans, which were already atomic. Left in
  `publish`: `seed_demand` ~9 and `row_scan` ~8 wrapped ticks (chunk counts); `machines` ~7 ticks per step is
  unprofiled. Demand cascade on a prefetched snapshot: not started.
- **Centralize Smelter/Fabricator demand**: record, publisher and Smelter split landed (2026-10-11); open are
  the Fabricator split, readers, intermediate netting, headless A/B.
- **Event-driven Automation**: Phases 1, 1.3, 1.6, 2 done; open are the live confirm of Phase 2, the Phase 3.2
  solar timer, and the deferred review minors listed under the TODO item.
- **Splitting `orchestrator_automation.py`**: partly done (2026-10-11); only if storage passes measurably delay
  grid supervision.

## Open measurements the plan names

- `OutpostPlanner._replan` outside `_rank` on 0839: done 2026-10-24 (item 3 below), 269 to 190 ticks; the cost
  sat in `covers()` / `observed_roles()` walks under `plan_hosts` and `needs` (plan, Results, last row). Left:
  `hosts()` scans per need in `needs()`, `_ores_in_reach` (~30 wrapped ticks). The coarse filter ~155 ticks, and
  `FILTER_CHUNK` cannot grow (dense-pipe worst case 3355 ops).
- ~~`drone_haul_plan.outpost_sources` stays ~95 ticks after Vector 1.~~ Closed by measurement (2026-10-24,
  plan "Results"): ~95 is the live path before the first snapshot publish (7 of 49 picks); on the snapshot it
  costs ~21 of an 84-tick plan. Debug logging as a whole costs the drone plan ~93 ticks per call.
- The snapshot publisher step (~105 ticks on 0839) is closed by measurement (plan "Results", 2026-10-25): the
  step fills its `LOGISTICS_SLICE_TICKS` budget by design; a 6-outpost round costs ~165 ticks, spread over
  `outpost_tier_deficits` (~55 %) and `outpost_tier_free` (~45 %); the archive write costs 1 tick. No record
  trim: every `free` band has a reader. A smaller slice would cut step peaks but age the record further.
- Real-save peak steps per callback are unmeasured (plan, "Tool gaps"); `step_profile.py haul` peaks at ~2,224
  steps (22 % of the cap) on synthetic input.

## Recommended order

1. **Import-cap check** (one session, small). A correctness risk, not a speed item: a chain over the cap crashes
   the script at load. Build the measurement first: count the steps of a slot's top-level import chain in the
   headless runner (`devtools/simulation/headless/save_scripts.py` already knows `stepsLimit`), report every
   slot over a threshold (suggest 90 % of 10,000), and fail `tests/` or a devtools check when one exceeds it.
   Then trim the `outpost_plan` chain (work out of module bodies, lazy imports) until `infra_planner_automation`
   has real headroom, and record the before/after counts in the plan's Results table.
2. ~~**Vector 1 plan bookkeeping**~~: done 2026-10-24.
3. **`_replan` outside `_rank`** (one session): profile with the Vector 6 command, find which of `snapshot`,
   `needs`, `plan_hosts` carries the 276 ticks, then the usual hoist or slice. Rankings are pinned by a test.
   Done 2026-10-24: `snapshot()` stores each outpost's covered roles once; 269 to 190 ticks.
4. ~~**`outpost_sources`**~~: closed by measurement 2026-10-24, no code (plan "Results" row).
5. **More atomic work** only after 1-4, and only with a measured target (Harvester `publish` done 2026-10-24): the plan's "Do not pursue" list shows
   how often an unmeasured item turned out to cost nothing.

Each session: own worktree (`python devtools/agent_worktree.py new <topic>`), one Results row with the same
save, gate and window as its baseline, `cavecrew-reviewer` before the merge.
