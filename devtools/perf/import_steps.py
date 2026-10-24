"""
Import steps: counts the interpreter steps of every script slot's import
chains in a headless run of a real save, and fails when one nears the cap.

    .venv/Scripts/python.exe devtools/perf/import_steps.py --save SAVE
    .venv/Scripts/python.exe devtools/perf/import_steps.py --save SAVE --tree automation_4 --module outpost_plan
    .venv/Scripts/python.exe devtools/perf/import_steps.py --records DIR/import_steps.json

A lib's module body runs synchronously when it is first imported, and the
whole chain below one import statement shares one cap of stepsLimit*10
(10,000) steps with the rest of that slice (dev_workflow §1d-1 "Import-time
code"). Over it, the script crashes with an uncatchable StepLimitError, in
game too.

The run goes through run.mjs --save --include-autoplay (the repo's current
scripts and libs, the autoplay planner Automation started), which writes
OUT/run/import_steps.json: one record per module body run, from the
simworker's own step counter (simhost.mjs patchImportSteps()). The counter
counts the whole slice, so a record's `after` is what the cap is checked on,
including the steps the slice spent before the import (`before`). A slot's
peak is the largest `after` of an outermost load (depth 1). Imports inside
functions (lazy ones) count as the slice that reaches them, which is why
`before` is listed: a lazy load inside a heavy run_atomic() slice starts
high. Only loads the window reaches are measured; --hours sets it.

Exit 1 when a slot's peak is over --threshold of the cap (default 0.9) or a
module body hit the step limit. Bodies that raised something else are listed
but do not fail the check (an importer may catch them; a crash shows in the
run's console.log). Only reads the save; writes under --out (default: a
temp directory). Outside the main checkout (an agent worktree) set
CT_SIMWORKER to the main checkout's internals/terraform_decompiled/simworker/deobfuscated.js.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUN_MJS = os.path.join(REPO_ROOT, "devtools", "simulation", "headless", "run.mjs")
RECORDS = "import_steps.json"
DEFAULT_THRESHOLD = 0.9
# The planner Automation imports its groups in the first seconds; on save 0839
# its first founding pass (outpost_needs.snapshot()) ran 0.009 h in.
DEFAULT_HOURS = "0.02"
STEP_LIMIT = "step_limit"


def slot_peaks(records):
    """{script: {"steps", "before", "module", "cap", "crashed", "raised"}}: the
    largest step counter at the end of an outermost (depth 1) load, the slice
    steps before it, the module, the cap; modules whose body hit the step
    limit (crashed) or raised another error (raised)."""
    peaks = {}
    for rec in records:
        slot = peaks.setdefault(
            rec["script"], {"steps": 0, "before": 0, "module": None, "cap": rec["cap"], "crashed": [], "raised": []}
        )
        error = rec.get("error") or (None if rec["ok"] else "error")
        if error:
            names = slot["crashed"] if error == STEP_LIMIT else slot["raised"]
            if rec["module"] not in names:
                names.append(rec["module"])
        if rec["depth"] == 1 and rec["after"] > slot["steps"]:
            slot.update(steps=rec["after"], before=rec["before"], module=rec["module"], cap=rec["cap"])
    return peaks


def over(peaks, threshold):
    """Slots over threshold * cap, or with a body that hit the step limit, highest first."""
    bad = [(name, p) for name, p in peaks.items() if p["steps"] > threshold * p["cap"] or p["crashed"]]
    return sorted(bad, key=lambda item: -item[1]["steps"])


def import_trees(records, script):
    """The outermost loads of one script as trees {module, inclusive, exclusive, children}.
    Records come in completion order (a module after its imports), so each
    record's children are the finished records one level deeper since its last sibling."""
    pending = {}
    roots = []
    for rec in records:
        if rec["script"] != script:
            continue
        children = pending.pop(rec["depth"] + 1, [])
        inclusive = rec["after"] - rec["before"]
        node = {
            "module": rec["module"],
            "inclusive": inclusive,
            "exclusive": inclusive - sum(c["inclusive"] for c in children),
            "children": children,
        }
        pending.setdefault(rec["depth"], []).append(node)
        if rec["depth"] == 1:
            roots.append(node)
    return roots


def tree_lines(node, indent=0):
    lines = [f"{'  ' * indent}{node['module']}  {node['inclusive']} (own {node['exclusive']})"]
    for child in node["children"]:
        lines.extend(tree_lines(child, indent + 1))
    return lines


def report(peaks, threshold, top):
    lines = [f"{'slot':<32} {'peak':>6} {'cap %':>6} {'before':>6}  import"]
    ranked = sorted(peaks.items(), key=lambda item: -item[1]["steps"])
    for name, p in ranked[:top] if top else ranked:
        flag = "  OVER" if p["steps"] > threshold * p["cap"] else ""
        crashed = f"  step limit: {', '.join(p['crashed'])}" if p["crashed"] else ""
        raised = f"  raised: {', '.join(p['raised'])}" if p["raised"] else ""
        lines.append(
            f"{name:<32} {p['steps']:>6} {100 * p['steps'] / p['cap']:>5.1f}% {p['before']:>6}  "
            f"{p['module'] or '-'}{flag}{crashed}{raised}"
        )
    return lines


def run(save, out, hours):
    run_dir = os.path.join(out, "run")
    command = ["node", RUN_MJS, "--save", save, "--include-autoplay", "--hours", hours, "--out", run_dir]
    with open(os.path.join(out, "run.stdout"), "w", encoding="utf-8") as stdout:
        subprocess.run(command, check=True, stdout=stdout, stderr=subprocess.STDOUT, cwd=REPO_ROOT)
    path = os.path.join(run_dir, RECORDS)
    if not os.path.exists(path):
        sys.exit(
            f"import_steps: {path} missing: the simworker build lacks the module body pattern "
            f"(simhost.mjs MODULE_BODY warning in {out}/run.stdout)"
        )
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Count the interpreter steps of every slot's import chains in a headless run."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--save", help="save_<id>.json(.gz) to run headless")
    source.add_argument("--records", help="an existing run's import_steps.json (no run)")
    parser.add_argument("--out", help="run directory (default: a temp directory)")
    parser.add_argument("--hours", default=DEFAULT_HOURS, help=f"game hours to run (default {DEFAULT_HOURS})")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"share of the cap that fails the check (default {DEFAULT_THRESHOLD})",
    )
    parser.add_argument("--top", type=int, default=15, help="slots to list, highest first (0: all)")
    parser.add_argument(
        "--tree", metavar="SLOT", help="also print SLOT's import trees (inclusive and own steps per module)"
    )
    parser.add_argument("--module", help="with --tree: only the outermost load of this module")
    args = parser.parse_args(argv)

    path = args.records
    if args.save:
        out = args.out or tempfile.mkdtemp(prefix="import_steps-")
        os.makedirs(out, exist_ok=True)
        path = run(args.save, out, args.hours)
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    peaks = slot_peaks(records)
    print("\n".join(report(peaks, args.threshold, args.top)))
    if args.tree:
        for root in import_trees(records, args.tree):
            if args.module is None or root["module"] == args.module:
                print("\n".join(tree_lines(root)))
    bad = over(peaks, args.threshold)
    print(f"import_steps: {len(peaks)} slot(s), threshold {args.threshold:.0%} of the cap, {len(bad)} over ({path})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
