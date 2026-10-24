# Helper sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the second duplicated-helper harvest of the code quality plan and end with a judged, ranked list of helper families, ready for an implementation plan.

**Architecture:** Cheap tools and cheap agents find, one strong agent judges. Task 1 widens `clone_scan.py` to `autoplay/` and short functions. Task 2 runs Haiku harvesters, each on one search angle, into one candidates file. Task 3 hands every candidate plus a targeted read of `autoplay/lib` and `production_cascade` to a Fable judge (`model: "fable"`, operator-approved for this judge step only). Task 4 records the verdicts. No production code changes in this plan.

**Tech Stack:** `devtools/code_scan/` (Python, host-side), `unittest`, Agent tool subagents.

**Spec:** [code_quality.md](../code_quality.md), "Next sweep".

## Global Constraints
- Read-only on `scripts/` and `autoplay/`: no edits, no scratch files there (CLAUDE.md §Boundaries).
- Harvesters: `caveman:cavecrew-investigator`, default model (Haiku). Judge: `general-purpose` with `model: "fable"`. Reviews: `caveman:cavecrew-reviewer`, default model; the final review no higher than the session's main-loop model.
- Families already done or planned are out of scope; every harvester brief lists them: everything in the "Done" table of code_quality.md, `_notify`, the `building_ops` deploy/undeploy/upgrade calls ([notify_building_ops.md](notify_building_ops.md)), every `clone_scan_ignore.txt` pair.
- Harvest output: `docs/plans/done/helpers_sweep_candidates.md` (tracked, under 64 KB, `tests/test_docs_lint.py`). One `## <family>` section each: sites as `path:line qualname`, the shared rule in one line, how the copies differ, found-by angle.
- Every claimed site is read in the code by the agent that reports it; no site from scan output alone.

## Review Focus
1. Same AST shape, different intent (`clone_scan` "same shape" pairs): the judge must say `keep` with the reason, which then goes to the ignore file, or the next harvest reports it again.
2. Pairs across tiers or across `autoplay/` and `scripts/`: code that cannot import the other side cannot share a helper. Task 1 marks them; the judge must not propose a cross-boundary helper.
3. Drifted copies (copies that now disagree): rank them as bugs above plain duplicates, as the 2026-10-11 sweep did.
4. A family the 2026-10-09 spot check already named (`research.is_unlocked` wrappers, `_dist`, `production_cascade` BFS walkers) must come back with today's site list, not the old one.
5. Candidates file over the doc caps: split by family group, never raise the caps.

---

### Task 1: `clone_scan` covers `autoplay/`

**Files:**
- Modify: `devtools/code_scan/scan_common.py:11-25` (`scanned_files`)
- Modify: `devtools/code_scan/clone_scan.py` (`main`, `nolib` marking, `-h` text)
- Test: `tests/test_scan_groups.py` (or a new `tests/test_clone_scan.py` if that file covers only grouping)

**Interfaces:**
- Produces: `scan_common.scanned_files(include_autoplay=False) -> dict[str, tuple[str, int | None]]`; with `True` it adds every `.py` under `autoplay/` (no `__pycache__`), display path `autoplay/<rel>` (forward slashes), tier `None`. `size_scan.py` and `feature_scan.py` keep the default.
- Produces: `clone_scan.py` scans with `include_autoplay=True` by default; a pair with one side under `autoplay/` and one under `scripts/` prints `cross` (like `nolib`), unless `devtools/scripts_sync.py` shows `autoplay/lib` modules can import the script libs, in which case no mark (check before coding, write the finding into the `-h` text).

- [ ] **Step 1: Write the failing test** `test_scanned_files_adds_autoplay`: `scanned_files(include_autoplay=True)` contains `"autoplay/lib/outpost_plan.py"` with tier `None`; `scanned_files()` contains no key starting `autoplay/`.
- [ ] **Step 2: Run** `python -m unittest tests.test_scan_groups`. Expected: FAIL, `unexpected keyword argument 'include_autoplay'`.
- [ ] **Step 3: Implement** the parameter and the `clone_scan` default plus the `cross` mark.
- [ ] **Step 4: Run** the test file and `python devtools/code_scan/clone_scan.py --top 5`. Expected: PASS; the summary line counts more functions than before and at least one `autoplay/` pair appears with `--grep autoplay`.
- [ ] **Step 5: Checks:** full unittest, ruff check + format on `devtools/code_scan tests`, `npx pyright`. Expected: green.
- [ ] **Step 6: Commit** `feat(clone_scan): scan autoplay/ too, mark cross-boundary pairs`.

### Task 2: Harvest

**Files:**
- Create: `docs/plans/done/helpers_sweep_candidates.md`

Dispatch the four harvesters in one message (parallel), each with the Global Constraints exclusions and output format, each returning its families as text; the controller merges them into the candidates file, joining the same family found by two angles.

- [ ] **Step 1: Angle A, scan pairs.** Brief: run `python devtools/code_scan/clone_scan.py --min-ratio 0.85 --min-lines 3 --top 0` (slow, run in background); triage every unreviewed cluster, not just the top. Report a family only when the bodies apply one game or repo rule; list rejected same-shape pairs separately as `keep?` lines for the judge.
- [ ] **Step 2: Angle B, game API anchors.** Brief: list every caller of `research.is_unlocked`, `real_seconds_per_hour`, `archive.get` and `get_component` under `scripts/4_controlpanel/lib` and `autoplay/lib`; report wrapper copies clustered around each (guard, default, validation). For `archive.get` (~96 sites) report the read-and-validate shapes (`archive.get(KEY)` then `isinstance(..., dict)`), counted per shape, not every site.
- [ ] **Step 3: Angle C, bypassed discovery.** Brief: find per-outpost building filters that walk machines themselves instead of `discover_storage_buildings` / `discover_network_buildings` (grep their definitions first, then loops over outpost machines filtering by `type_id`).
- [ ] **Step 4: Angle D, known families refresh.** Brief: today's sites for the three 2026-10-09 families (`research.is_unlocked` wrappers, `_dist(ax, ay, bx, by)` in `autoplay/lib`, the depth-6 BFS in `production_cascade`: `_cascade_fabricator_output_demand`, `get_manual_order_blocking_items`, `_walk_blueprint_demand`) and how each copy differs.
- [ ] **Step 5: Merge** into `helpers_sweep_candidates.md`; run `python -m unittest tests.test_docs_lint`. Expected: PASS.
- [ ] **Step 6: Commit** `docs(plans): helper sweep candidates`.

### Task 3: Fable judge

**Files:**
- Modify: `docs/plans/done/helpers_sweep_candidates.md` (a `Verdict:` block per family)

- [ ] **Step 1: Dispatch one `general-purpose` agent with `model: "fable"`.** Brief: read `helpers_sweep_candidates.md`, the "Done" table and "Drifted copies" of code_quality.md, and CODE_GUIDES.md; for each family read every site, then write under it: `Verdict: merge | keep | drift-bug`, owner module and helper signature (`name(params) -> return`), the rule the helper owns, sites that must stay apart and why, risk (`low | medium | high`), size (`S | M | L`). Then do a targeted read of `autoplay/lib` and `production_cascade.py` for logic-shaped duplicates the scans cannot see and add them as new families with verdicts. Return a ranking: drift-bugs first, then merges by sites saved over risk.
- [ ] **Step 2: Spot-check** two `merge` and one `keep` verdict by reading their sites yourself. A wrong verdict goes back to the judge with the evidence, once.
- [ ] **Step 3: Commit** `docs(plans): judge the helper sweep`.

### Task 4: Record

**Files:**
- Modify: `devtools/code_scan/clone_scan_ignore.txt` (one line per `keep` pair, with the judge's reason)
- Modify: `docs/plans/code_quality.md` ("Open candidates": the ranked `merge` and `drift-bug` families, linking the candidates file; "Next sweep": state it ran, date, what is still unswept)
- Modify: `TODO.md` (Code Quality: tick the sweep box, add one box "Helpers: implementation plan for the judged sweep families")

- [ ] **Step 1: Write the ignore entries.** Run `python devtools/code_scan/clone_scan.py --top 0 --pairs`. Expected: no `keep` pair listed.
- [ ] **Step 2: Update** code_quality.md and TODO.md.
- [ ] **Step 3: Checks:** `python -m unittest tests.test_docs_lint tests.test_scan_groups`. Expected: PASS.
- [ ] **Step 4: Commit** `docs(code_quality): record the second helper sweep`.
