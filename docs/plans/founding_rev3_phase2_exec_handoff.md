# Founding planner rev3 phase 2: handoff to execution

Written 2026-10-21 at the end of the planning session.

## What landed

- Worktree `.claude/worktrees/founding-rev3-p2`, branch `agent/founding-rev3-p2` (from `main` at `989d0d1`). Not merged.
- Implementation plan: [founding_rev3_phase2_impl.md](founding_rev3_phase2_impl.md), approved by the operator. No code changed yet.
- Operator decisions since the [phase 2 handoff](founding_rev3_phase2_handoff.md):
  - The second outpost is ranked long before the first mining drill and before the hardness-3 drill unlock: tune `WEIGHTS_EARLY`, hardness penalty active.
  - `reach_gain` is 0 once drones haul (no station at new outposts then).
  - Drone takeover (Task 4): with autoplay active, the planner turns the drone yield switch on once every `drone_depot`-role outpost has a depot and ≥ 3 hauler drones fly; the FLEET switch is for play without autoplay. Then Charging Stations are retired except at the constructor base and a frozen salt keeper within 300 m of home.
  - Task 3.5: builders may have drifted off a single base since the Pioneer refit rework (refit `base=None` falls back to the unit's own launch `HOME_BASE`); this would break construction STOCK and station keepers. Investigate first, report, then fix.

## Next

- New session: execute the plan with `superpowers:subagent-driven-development`, inside the worktree, task order 1, 2, 3, 3.5, 4, 5.
- Task 3.5 Step 2 stops for the operator before any edit.
- After Task 5: `cavecrew-reviewer` on the branch, then ask the operator before `python devtools/agent_worktree.py merge founding-rev3-p2 -m ...`.

## Open questions

- Task 2 uses the phase 1 scout areas (≤ 2 points) as the geothermal fallback instead of all probe cells; revisit if the replay shows the fallback too coarse.
- The Charging Station pressure metric (upgrade packs) stays deferred.
