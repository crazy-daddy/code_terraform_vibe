"""
Callback steps: the peak interpreter steps of every script slot's pure
callbacks (each run_atomic() slice, map()/sorted(key=) callbacks, archive
transaction updaters) in a headless run of a real save, and fails when one
nears the cap.

    .venv/Scripts/python.exe devtools/perf/callback_steps.py --save SAVE
    .venv/Scripts/python.exe devtools/perf/callback_steps.py --save SAVE --hours 0.1 --slot drone_7
    .venv/Scripts/python.exe devtools/perf/callback_steps.py --records DIR/callback_steps.json

A callback runs with no tick boundary inside it, under one cap of
stepsLimit*10 (10,000) steps (dev_workflow §1d-1). Each statement checks the
step counter of the whole slice, so the steps the script already spent that
tick before the callback count against the cap too. Over it, the script
crashes with an uncatchable StepLimitError, in game too.

The run goes through run.mjs --save --include-autoplay --callback-steps (the
repo's current scripts and libs, the autoplay planner Automation started),
which writes OUT/run/callback_steps.json: one aggregate per slot, callback
function and its first callee, from the simworker's own step counter
(simhost.mjs patchCallbackSteps()). `peak` is the largest counter at the end
of an outermost callback (what the cap is checked on), `before` the slice
steps at its start, `own` the callback's own steps. A run_atomic() lambda is
listed by the fn it runs (`inner`). `at` is the location at the peak
callback's end: the throwing line when it hit the cap, else the last line
run (the lambda's line in lib/atomic.py for run_atomic()). Its lib can lag:
an archive transaction updater's lines keep the caller's lib (`archive`), so
read the line in the updater's lib or the libs it calls. Some of the
worker's checks throw over 10,000, some at 10,000, so a peak of exactly
10,000 may be a crash or a normal return: it counts as a step-limit end
(conservative); the run's console.log shows a real crash as "exceeded step
limit". A callback that suspends (a flush) and is retried is counted once
per attempt, each with its own `before`, so its count and own steps can
overstate it, and a crash on the game's own-steps total across attempts can
show without a step-limit end. Only callbacks the window reaches are
measured; --hours sets it (0.4 h on save 0839 takes ~10 min).

The report also says what each --watch callback peaks at, or that the window
never reached it (default: fair_rival_bands, the drone plan's no-snapshot
fallback).

Exit 1 when a slot's peak is over --threshold of the cap (default 0.9) or a
callback hit the step limit. Only reads the save; writes under --out
(default: a temp directory). Outside the main checkout (an agent worktree)
set CT_SIMWORKER to the main checkout's
internals/terraform_decompiled/simworker/deobfuscated.js.
"""

import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import import_steps

RECORDS = "callback_steps.json"
DEFAULT_THRESHOLD = 0.9
DEFAULT_HOURS = "0.4"
DEFAULT_WATCH = "fair_rival_bands"
# run_atomic()'s lambda lives in lib/atomic.py; its records are named by the fn it runs.
ATOMIC_SOURCE = "atomic"


def label(rec):
    """`fn (lib)` of a record; a run_atomic() lambda as the fn it runs."""
    if rec.get("source") == ATOMIC_SOURCE and rec.get("inner"):
        return f"{rec['inner']} ({rec.get('innerSource') or '?'}, atomic)"
    return f"{rec.get('fn') or '?'} ({rec.get('source') or '?'})"


def names(rec):
    """The function names a --watch entry matches: fn and inner, bare and qualified."""
    out = set()
    for name in (rec.get("fn"), rec.get("inner")):
        if name:
            out.update((name, name.rsplit(".", 1)[-1]))
    return out


def by_slot(records):
    """{script: [records, highest peak first]}."""
    slots = {}
    for rec in records:
        slots.setdefault(rec["script"], []).append(rec)
    for recs in slots.values():
        recs.sort(key=lambda r: -r["peak"])
    return slots


def over(slots, threshold):
    """Slots whose peak is over threshold * cap, or with a callback that hit the step limit, highest first."""
    bad = []
    for name, recs in slots.items():
        top = recs[0]
        if top["peak"] > threshold * top["cap"] or any(r.get("limit") for r in recs):
            bad.append((name, top))
    return sorted(bad, key=lambda item: -item[1]["peak"])


def watched(records, name):
    """Records whose fn or inner is `name`, highest peak first."""
    return sorted((r for r in records if name in names(r)), key=lambda r: -r["peak"])


def watch_line(records, name):
    hits = watched(records, name)
    if not hits:
        return f"{name}: not reached in this window"
    top = hits[0]
    count = sum(r["count"] for r in hits)
    slots = len({r["script"] for r in hits})
    return (
        f"{name}: peak {top['peak']} ({100 * top['peak'] / top['cap']:.1f} % of the cap) in {top['script']}, "
        f"own max {max(r['ownMax'] for r in hits)}, {count} call(s) in {slots} slot(s)"
    )


def report(slots, threshold, top, per_slot):
    lines = [f"{'slot':<24} {'peak':>6} {'cap %':>6} {'before':>6} {'own':>6} {'n':>5}  callback  at"]
    ranked = sorted(slots.items(), key=lambda item: -item[1][0]["peak"])
    for name, recs in ranked[:top] if top else ranked:
        for i, rec in enumerate(recs[:per_slot] if per_slot else recs):
            flag = "  OVER" if rec["peak"] > threshold * rec["cap"] else ""
            limit = f"  step limit (may be a crash) x{rec['limit']}" if rec.get("limit") else ""
            at = f"{rec.get('peakSource') or '?'}:{rec.get('peakLine') or '?'}"
            lines.append(
                f"{name if i == 0 else '':<24} {rec['peak']:>6} {100 * rec['peak'] / rec['cap']:>5.1f}% "
                f"{rec['peakBefore']:>6} {rec['ownMax']:>6} {rec['count']:>5}  {label(rec)}  {at}{flag}{limit}"
            )
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Report the peak interpreter steps of every slot's pure callbacks in a headless run."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--save", help="save_<id>.json(.gz) to run headless")
    source.add_argument("--records", help="an existing run's callback_steps.json (no run)")
    parser.add_argument("--out", help="run directory (default: a temp directory)")
    parser.add_argument("--hours", default=DEFAULT_HOURS, help=f"game hours to run (default {DEFAULT_HOURS})")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"share of the cap that fails the check (default {DEFAULT_THRESHOLD})",
    )
    parser.add_argument("--top", type=int, default=15, help="slots to list, highest peak first (0: all)")
    parser.add_argument("--per-slot", type=int, default=3, help="callbacks to list per slot (0: all)")
    parser.add_argument("--slot", help="list only this slot, all its callbacks")
    parser.add_argument(
        "--watch",
        default=DEFAULT_WATCH,
        help=f"comma-separated callback names to report on, reached or not (default {DEFAULT_WATCH})",
    )
    args = parser.parse_args(argv)

    path = args.records
    if args.save:
        out = args.out or tempfile.mkdtemp(prefix="callback_steps-")
        os.makedirs(out, exist_ok=True)
        path = import_steps.run(
            args.save,
            out,
            args.hours,
            RECORDS,
            ["--callback-steps"],
            'the pure callback pattern ("callback step records are off"',
        )
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    slots = by_slot(records)
    shown = {args.slot: slots.get(args.slot, [])} if args.slot else slots
    shown = {k: v for k, v in shown.items() if v}
    print("\n".join(report(shown, args.threshold, 0 if args.slot else args.top, 0 if args.slot else args.per_slot)))
    for name in filter(None, (n.strip() for n in args.watch.split(","))):
        print(watch_line(records, name))
    bad = over(slots, args.threshold)
    print(f"callback_steps: {len(slots)} slot(s), threshold {args.threshold:.0%} of the cap, {len(bad)} over ({path})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
