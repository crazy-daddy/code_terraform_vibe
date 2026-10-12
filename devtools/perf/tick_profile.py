"""
Tick profiler: times lib functions in game ticks inside a headless run of a
real save, inclusive per function, only around one gated call.

    .venv/Scripts/python.exe devtools/perf/tick_profile.py --save SAVE --out DIR
    .venv/Scripts/python.exe devtools/perf/tick_profile.py --save SAVE --out DIR \\
        --modules production_cascade,priority --min-total 50
    .venv/Scripts/python.exe devtools/perf/tick_profile.py --summarize DIR/run/console.log

It copies the repo's current scripts for the save (save_scripts.py), appends
a wrapper to every top-level function of --modules and every plain method of
--classes, and gates the timers on the --gate call: they run only inside it,
so hot code reached from other run_atomic() callbacks keeps its normal cost
(timers left on everywhere pushed those over the 10,000-step cap). Each gated
call logs one debug line `PROF <label> total=<T> :: <fn> <ticks>t/<calls> | ...`;
the run goes through run.mjs --scripts/--libs and the lines are summarized
per label: median ticks and calls per function over the samples.

Read the numbers as shares, not costs: the wrappers add ~40% (each call does
two now_tick() reads and dict updates, counted in its callers). Ticks are
whole game ticks, so a short call reads 0 or 1; summed over many calls the
total is still right on average. Recursion counts the outermost call only.
Unlike step_profile.py (synthetic world, CPython opcodes), this measures a
real save in the game's own interpreter: the synthetic worlds understated the
demand refresh tasks 10-300x. Only reads the save; writes under --out.
"""

import argparse
import os
import re
import statistics
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUN_MJS = os.path.join(REPO_ROOT, "devtools", "simulation", "headless", "run.mjs")
SAVE_SCRIPTS = os.path.join(REPO_ROOT, "devtools", "simulation", "headless", "save_scripts.py")

RUNTIME_MODULE = "tick_profile_rt"
DEFAULT_MODULES = "production_cascade,production_sites,production_source,production_demand,logistics_requests,production_core,production_docks,production_orders"
DEFAULT_CLASSES = "production_source:SourceCache,logistics_requests:PlanReads"
DEFAULT_GATE = "demand_publisher:Refresh.run_next"
DEFAULT_LABEL = "self.pending[-1][0] + ' ' + str(self.pending[-1][1] or '-')"
# The runtime module imports these (directly or through them): wrapping one is an import cycle.
UNWRAPPABLE = {RUNTIME_MODULE, "tree_console", "game_clock", "swallow", "archive", "atomic", "game_rules"}
DEFAULT_SKIP = "log,_ceil"

RUNTIME_SOURCE = """# Written by devtools/perf/tick_profile.py into a headless copy of lib/. Never deploy.
T = {}
N = {}
D = {}
ON = [False]
_LOG = []
_NOW = []  # game_clock.now_tick, imported on the first start() (no import cycle at load)


def wrap(name, fn):
    def inner(*args, **kwargs):
        if not ON[0]:
            return fn(*args, **kwargs)
        now_tick = _NOW[0]
        depth = D.get(name, 0)
        D[name] = depth + 1
        start = now_tick() if depth == 0 else 0
        try:
            return fn(*args, **kwargs)
        finally:
            D[name] = depth
            N[name] = N.get(name, 0) + 1
            if depth == 0:
                T[name] = T.get(name, 0) + now_tick() - start

    return inner


def start():
    from game_clock import now_tick

    if not _NOW:
        _NOW.append(now_tick)
    T.clear()
    N.clear()
    D.clear()
    ON[0] = True
    return now_tick()


def stop(label, began):
    from game_clock import now_tick

    ON[0] = False
    if not _LOG:
        from tree_console import TreeConsole

        _LOG.append(TreeConsole(module="tick_profile"))
    rows = sorted(T.items(), key=lambda kv: -kv[1])
    body = " | ".join([f"{k} {v}t/{N.get(k, 0)}" for k, v in rows])
    _LOG[0].debug(f"PROF {label} total={now_tick() - began} :: {body}")
"""


def _strip_class(source, name):
    """Source of `class name` up to the next top-level statement."""
    start = source.index(f"\nclass {name}") + 1
    rest = re.search(r"^\S", source[start + 1 :], re.MULTILINE)
    return source[start : start + 1 + rest.start()] if rest else source[start:]


def _undecorated(body, indent):
    """Names of `def`s at `indent` without a decorator line above them."""
    names = []
    for match in re.finditer(rf"^{indent}def (\w+)", body, re.MULTILINE):
        before = body[: match.start()].rstrip("\n").rsplit("\n", 1)[-1]
        if not before.strip().startswith("@"):
            names.append(match.group(1))
    return names


def patch_libs(lib_dir, modules, classes, gate, label, skip):
    """Appends the wrappers and the gate to the copied modules; returns {module: wrapped count}."""
    with open(os.path.join(lib_dir, f"{RUNTIME_MODULE}.py"), "w", encoding="utf-8", newline="\n") as f:
        f.write(RUNTIME_SOURCE)
    tails = {}
    counts = {}
    for module in modules:
        if module in UNWRAPPABLE:
            sys.exit(f"tick_profile: can't wrap {module} (the runtime module imports it)")
        source = _read(lib_dir, module)
        names = [n for n in _undecorated(source, "") if n not in skip and not n.startswith("__")]
        short = module.removeprefix("production_")
        tails.setdefault(module, []).extend(f"{n} = _tp.wrap('{short}.{n}', {n})\n" for n in names)
        counts[module] = len(names)
    for module, cls in classes:
        if module in UNWRAPPABLE:
            sys.exit(f"tick_profile: can't wrap {module} (the runtime module imports it)")
        body = _strip_class(_read(lib_dir, module), cls)
        names = [n for n in _undecorated(body, "    ") if not n.startswith("__") and n not in skip]
        tails.setdefault(module, []).extend(f"{cls}.{n} = _tp.wrap('{cls}.{n}', {cls}.{n})\n" for n in names)
        counts[f"{module}:{cls}"] = len(names)
    gate_module, gate_target = gate.split(":", 1)
    if "." in gate_target:
        owner, method = gate_target.split(".", 1)
        tails.setdefault(gate_module, []).append(
            f"_tp_gated = {owner}.{method}\n\n\n"
            f"def _tp_gate(self, *args, **kwargs):\n"
            f"    label = str({label})\n"
            f"    began = _tp.start()\n"
            f"    try:\n"
            f"        return _tp_gated(self, *args, **kwargs)\n"
            f"    finally:\n"
            f"        _tp.stop(label, began)\n\n\n"
            f"{owner}.{method} = _tp_gate\n"
        )
    else:
        tails.setdefault(gate_module, []).append(
            f"_tp_gated = {gate_target}\n\n\n"
            f"def {gate_target}(*args, **kwargs):\n"
            f"    label = str({label})\n"
            f"    began = _tp.start()\n"
            f"    try:\n"
            f"        return _tp_gated(*args, **kwargs)\n"
            f"    finally:\n"
            f"        _tp.stop(label, began)\n"
        )
    for module, lines in tails.items():
        path = os.path.join(lib_dir, f"{module}.py")
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"\n\nimport {RUNTIME_MODULE} as _tp  # noqa: E402\n\n" + "".join(lines))
    return counts


def _read(lib_dir, module):
    path = os.path.join(lib_dir, f"{module}.py")
    if not os.path.exists(path):
        sys.exit(f"tick_profile: no lib module {module} in {lib_dir}")
    with open(path, encoding="utf-8") as f:
        return f.read()


PROF_LINE = re.compile(r"PROF (.*?) total=(\d+) :: (.*)$")
ROW = re.compile(r"^(\S+) (\d+)t/(\d+)$")


def summarize(log_path, top, min_total, label_filter):
    """Prints median ticks and calls per function, per label, from a run's console.log."""
    samples = {}
    with open(log_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            match = PROF_LINE.search(line)
            if not match:
                continue
            label, total = match.group(1), int(match.group(2))
            if total < min_total or (label_filter and not re.search(label_filter, label)):
                continue
            rows = {}
            for cell in match.group(3).split(" | "):
                row = ROW.match(cell.strip())
                if row:
                    rows[row.group(1)] = (int(row.group(2)), int(row.group(3)))
            samples.setdefault(label, []).append((total, rows))
    if not samples:
        print(f"no PROF lines in {log_path} (min total {min_total})")
        return
    for label, runs in sorted(samples.items(), key=lambda kv: -statistics.median([t for t, _ in kv[1]])):
        totals = [t for t, _ in runs]
        print(
            f"\n== {label}: n={len(runs)} total median {statistics.median(totals):.0f} ticks (min {min(totals)}, max {max(totals)})"
        )
        names = {name for _, rows in runs for name in rows}
        stats = []
        for name in names:
            ticks = [rows.get(name, (0, 0))[0] for _, rows in runs]
            calls = [rows.get(name, (0, 0))[1] for _, rows in runs]
            stats.append((statistics.median(ticks), statistics.median(calls), max(ticks), name))
        for median_ticks, median_calls, max_ticks, name in sorted(stats, reverse=True)[:top]:
            print(f"  {median_ticks:7.0f}t  max {max_ticks:5d}t  calls {median_calls:6.0f}  {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--save", help="save to run (plain or gzipped JSON); only read")
    parser.add_argument("--out", help="work dir: scripts/ (patched copy), run/ (run.mjs --out)")
    parser.add_argument("--hours", default="0.4", help="game hours to run (default 0.4)")
    parser.add_argument(
        "--modules", default=DEFAULT_MODULES, help="comma list of lib modules whose top-level functions get timed"
    )
    parser.add_argument(
        "--classes", default=DEFAULT_CLASSES, help="comma list of module:Class whose plain methods get timed"
    )
    parser.add_argument(
        "--gate", default=DEFAULT_GATE, help="module:Class.method or module:function; timers run only inside it"
    )
    parser.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help="Python expression (game code, evaluated before the gated call; `self`/`args` in scope) naming each sample",
    )
    parser.add_argument("--skip", default=DEFAULT_SKIP, help="comma list of function names never wrapped")
    parser.add_argument("--run-args", default="--paid-debug --sticky-fluids", help="extra run.mjs options")
    parser.add_argument("--summarize", metavar="CONSOLE_LOG", help="only summarize an existing run's console.log")
    parser.add_argument("--top", type=int, default=25, help="functions per label (default 25)")
    parser.add_argument(
        "--min-total",
        type=int,
        default=0,
        help="drop samples whose gated call took fewer ticks (e.g. warm-cache passes)",
    )
    parser.add_argument("--filter", default="", help="regex on the label")
    args = parser.parse_args()

    if args.summarize:
        summarize(args.summarize, args.top, args.min_total, args.filter)
        return
    if not args.save or not args.out:
        parser.error("--save and --out are required unless --summarize")

    out = os.path.abspath(args.out)
    scripts = os.path.join(out, "scripts")
    run_dir = os.path.join(out, "run")
    python = os.path.join(
        REPO_ROOT, ".venv", "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python"
    )
    subprocess.run(
        [python if os.path.exists(python) else sys.executable, SAVE_SCRIPTS, "--save", args.save, "--out", scripts],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    modules = [m for m in args.modules.split(",") if m]
    classes = [tuple(c.split(":", 1)) for c in args.classes.split(",") if c]
    counts = patch_libs(
        os.path.join(scripts, "lib"), modules, classes, args.gate, args.label, set(args.skip.split(","))
    )
    print("wrapped: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    command = [
        "node",
        RUN_MJS,
        "--save",
        args.save,
        "--scripts",
        scripts,
        "--libs",
        os.path.join(scripts, "lib"),
        "--hours",
        args.hours,
        "--out",
        run_dir,
        *args.run_args.split(),
    ]
    with open(os.path.join(out, "run.stdout"), "w", encoding="utf-8") as stdout:
        subprocess.run(command, check=True, stdout=stdout, stderr=subprocess.STDOUT, cwd=REPO_ROOT)
    log_path = os.path.join(run_dir, "console.log")
    with open(log_path, encoding="utf-8", errors="replace") as f:
        crashes = [line.strip() for line in f if "] [crash] [" in line]
    for line in crashes[:3]:
        print(f"CRASH {line[:200]}")
    summarize(log_path, args.top, args.min_total, args.filter)


if __name__ == "__main__":
    main()
