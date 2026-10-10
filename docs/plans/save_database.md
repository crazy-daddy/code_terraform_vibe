# Plan: save game database (annotated saves across one playthrough)

Status: **draft** (owner idea, 2026-10-06).

## Context
The planners (founding, building, infra) need two things the repo lacks: real game states from every phase,
and the decision points a player meets in them. We have three private saves: early ~31k TP and two late ones
(824k, 887k; [headless_sim.md](headless_sim.md) "Uploaded saves"). Nothing covers ~150k to ~600k TP, where
drones, biomass, oil, the first Plants and most outpost founding happen.

Idea: the owner plays one game with our scripts, decides by hand where no script does yet, copies a save out at
fixed points, and notes each hand decision. An agent annotates the saves.

## The owner is a baseline, not an oracle
The owner's choices may be suboptimal (owner, 2026-10-06), so the database never turns them into rules directly.
- **States are facts.** What a phase looks like, which limits bite (cap, power, salt, uranium, scripts), what is
  unlocked when: true whatever was decided.
- **Notes mark decision points, not answers.** "Home was full, so I moved the smelter" says a decision exists
  here. The planner scores its own options at that point with its cost rules
  ([building_planner.md](building_planner.md), "Cost of a proposal"); the owner's move is one candidate.
- **The headless sim judges.** From the same save, run the owner's move and the planner's proposal side by side
  (`devtools/headless/`) and compare TP, cash and days to the next milestone. Planner wins: keep its rule. Owner
  wins: the cost model misses something, which becomes a finding.
- Mistakes are useful data: they show where the planner must do better.

## Second source: the repo's own history
The repo grew along with the owner's first playthrough (572 commits since 2026-09-13), so it already records
which problems came up in which phase, from specifics (Auto Feeders blocking Warehouses) to general ones
(logistics, supply of life forms and salt). Sources: `git log` (a full clone; cloud checkouts are shallow, so
`git fetch --unshallow` first), [DESIGN_HISTORY.md](../DESIGN_HISTORY.md), `TODO_done.md`,
`TODO_inspirations_done.md`.
- An agent builds a **problem timeline**: each problem, the phase it appeared in (from the game state the commit
  talks about, not the commit date), the fix, and whether that fix is a planner concern (where to build, how
  many, when) or a machine-script concern.
- Planner concerns become decision points like the owner's notes, with the same baseline rule: the fix taken is
  one candidate, not the answer.
- Caveat: the first run went slowly, with optimization rounds before each new phase (owner). So the timeline
  shows the **order** problems appear in and roughly which phase, not how long a phase takes or when an ideal
  player would hit them. Phase durations come from the saves and the headless sim, not from commit dates.
- This needs no new saves, so it can run first and tell the playthrough which phases to save most densely.

## When to save
At each phase start of [manual_walkthrough.md](../autoplay/manual_walkthrough.md), roughly: first Pioneer,
steam online, water online, first drones, biomass running, oil, Plants Mk II, wildlife unlock, nuclear. Plus
right after any building decision that was not obvious (a move, a new outpost, a retire).

## What goes with each save
One short note file per save, written by the owner:
- game day / TP (the save has these too, the note is for humans);
- what was done by hand since the last save and why, one line each ("built 2 turbines at outpost 4: night
  brownouts");
- what felt like a bottleneck (optional).

## Storage and privacy
Saves stay private: project files `saves/` (never the public repo), named `<phase>_<tp>k_<save suffix>.json`
like the existing ones, the note next to it as `.md`. `.notes/inputs.md` gets one entry per save (size, tick,
TP, machines, scripts). Annotations derived from a save may go into the repo only as summaries and test
expectations, never as copied save content.

## Annotation (agent)
Per pair of consecutive saves, a diff report (script, `devtools/`):
- buildings added / removed per outpost, designations, caps and slot use;
- research and kits unlocked, orders done;
- power balance and phase, fluid networks, running script count;
- scarce inputs: salt, uranium, exotic flows;
- each owner note matched to the diff rows it explains; diff rows no note explains listed as "unexplained".

Then per decision point: what the planners would propose from the earlier save, and the headless comparison
above. Output: one annotation file per save pair (project files, next to the saves) and, where a rule is
confirmed, a headless test case in the repo ("from save X, the planner proposes Y within N passes").

## Phases
0. Problem timeline from git history and DESIGN_HISTORY (no saves needed). **Done**: [problem_timeline.md](../autoplay/problem_timeline.md).
1. Save naming, note template, `.notes/inputs.md` entries; the owner plays and uploads.
2. Diff script over two saves (pure, reads the save JSON). **Done**: `devtools/save_diff.py`.
3. Annotation per pair: owner notes matched to diffs, unexplained changes listed. **Done** for the new-seed run
   (20 saves, 19 pairs; reports in project files `saves/new_seed_1831033811/annotations/`).
4. Planner comparison from each decision point once the building planner proposes (its phase 3).
5. Confirmed rules become headless tests; findings feed the cost model.

## Open
- Which phases need a save first: the ~150k to ~600k gap, or a full run from start.
- Whether the headless comparison can run long enough per decision (days of game time on mid saves) at current
  sim speed ([headless_sim.md](headless_sim.md) "Speed").
