"""
Block timing from the game's script logs: pairs every TreeConsole block
start ("┏━ name") with its end ("┗━ ...") per script and reports how long
each block takes, how often it runs and its share of the observed window.
Read-only on the save folder.

    python devtools/perf/log_block_timing.py                     # newest save, all scripts
    python devtools/perf/log_block_timing.py --script automation --top 20
    python devtools/perf/log_block_timing.py --save <save_*_scripts dir> --min-count 3

Log line: "[iso] [level] [script.py] [tick=N] HH:MM:SS <indent>┏━ name".
Debug lines are buffered and written on flush, so their tick is the flush
tick; their "HH:MM:SS" game clock is the time of the call. Info lines have
a real tick and no clock. A block is timed by clock when both its lines
have one, else by tick; the two are joined with a game-seconds-per-tick
ratio calibrated from the logs (last clock of each debug flush vs its tick).

Durations are wall game time and include sleeps and waits inside the block,
not only compute. A debug block's header carries the clock of the first line
logged inside it, not of the start() call, so its time is slightly short.
Every TreeConsole instance keeps its own indent, so an "END <name>" line is
matched by name; other end lines close the open block at their depth.

Evaluating results: do not redo old work. The logs reach back hours and can
predate the deploy of a recent perf commit (e.g. 0bf90ef storage tick stamp,
b90ba66 wildlife snapshot reads, ae539d0 parking). Check `git log` for
commits touching a block's code, compare against the tick/time figures in
their messages, and use --since <iso time of the deploy> to measure only the
current code. Block names are grouped with digits replaced by "#", and
scripts by kind ("drone_23" -> "drone"). Self time is the block minus its
timed children.

Running scripts: lib/script_census.py logs "scripts running: N ..." every few
hundred ticks. Each block takes the latest N at or before its start tick;
med_N is the median of those and med_st the median cost in interpreter steps,
ticks x floor(50000 / N) (the per-script allowance, docs/cheatsheet/
dev_workflow.md §1d-1). Steps compare across windows with different N, ticks
do not. Without census lines both columns show "-".

Headless runs (--headless <run dir or console.log>): reads the console.log
of devtools/simulation/headless/run.mjs instead of a save. Its lines are
"[tick N] [level] [script] HH:MM:SS text" with a debug flush's further lines
bare ("HH:MM:SS text"); they are rewritten into the save log format with a
synthetic ISO time from the tick, so --since takes a tick in this mode.
Lines without a script id ([approve], [lib-tier], [policy]) are dropped.
Calibration works the same; --sec-per-tick overrides it when a short run
has too few debug flushes.
"""

import argparse
import bisect
import collections
import datetime
import glob
import io
import itertools
import os
import re
import statistics
import sys

LINE_RE = re.compile(
    r"^\[(?P<iso>[^\]]+)\] \[(?P<level>\w+)\] \[(?P<script>[^\]]+?)\.py\] \[tick=(?P<tick>\d+)\] "
    r"(?:(?P<clock>\d\d:\d\d:\d\d) )?(?P<body>.*)$"
)
BRANCH = "┃   "
START = "┏━ "
END = "┗━ "
DAY = 86400
CENSUS_RE = re.compile(r"scripts running: (\d+) of")
TOTAL_STEPS_PER_TICK = 50000
MAX_STEPS_PER_SCRIPT = 1000
ROTATED_RE = re.compile(r"^(?P<base>.+?)(?:\.(?P<n>\d+))?\.log$")
HEADLESS_TAGGED_RE = re.compile(r"^\[tick (\d+)\] \[(\w+)\] \[([^\]]+)\] (?:(\d\d:\d\d:\d\d) )?(.*)$")
HEADLESS_BARE_RE = re.compile(r"^(\d\d:\d\d:\d\d) (.*)$")
HEADLESS_EPOCH = datetime.datetime(2026, 1, 1)


def newest_save():
    root = os.path.join(os.environ.get("APPDATA", ""), "io.codeterraform.game")
    saves = [p for p in glob.glob(os.path.join(root, "save_*_scripts")) if os.path.isdir(p)]
    if not saves:
        sys.exit(f"no save_*_scripts folder under {root}")
    return max(saves, key=os.path.getmtime)


def log_files(logs_dir):
    """Per-script logs grouped by base name, oldest rotation first. all*.log repeats them and is skipped."""
    groups = collections.defaultdict(list)
    for path in glob.glob(os.path.join(logs_dir, "*.log")):
        match = ROTATED_RE.match(os.path.basename(path))
        if not match or match["base"] == "all":
            continue
        groups[match["base"]].append((int(match["n"] or 0), path))
    return {base: [p for _, p in sorted(files, reverse=True)] for base, files in groups.items()}


def headless_console(path):
    """console.log of a headless run: the file itself, or <dir>/run/console.log, else <dir>/console.log."""
    if os.path.isfile(path):
        return path
    for candidate in (os.path.join(path, "run", "console.log"), os.path.join(path, "console.log")):
        if os.path.isfile(candidate):
            return candidate
    sys.exit(f"no console.log at {path} (tried the file, <dir>/run/console.log and <dir>/console.log)")


def headless_iso(tick):
    """Synthetic ISO time for a headless tick (fixed epoch + tick / 10 s); sorts like the tick."""
    stamp = HEADLESS_EPOCH + datetime.timedelta(seconds=tick / 10.0)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z"


def headless_lines(console_log):
    """{script: [save-format log lines]} from a run.mjs console.log. A bare "HH:MM:SS text" line continues
    the last tagged line's debug flush. A "[tick N]" line with no script id is dropped with the bare lines
    after it; any other line (multi-line text without a clock) is skipped and the flush goes on."""
    lines = collections.defaultdict(list)
    current = None  # (tick, level, script) of the last tagged line, None after an untagged one
    with open(console_log, encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            raw = raw.rstrip("\n")
            tagged = HEADLESS_TAGGED_RE.match(raw)
            if tagged:
                tick, level, script, clock, body = tagged.groups()
                current = (int(tick), level, script)
            elif raw.startswith("[tick "):
                current = None
                continue
            else:
                bare = HEADLESS_BARE_RE.match(raw)
                if not bare or current is None:
                    continue
                clock, body = bare.groups()
            tick, level, script = current
            clock_part = f"{clock} " if clock else ""
            lines[script].append(f"[{headless_iso(tick)}] [{level}] [{script}.py] [tick={tick}] {clock_part}{body}")
    return dict(lines)


def _lines(source):
    """Lines of a source: a log file path, or an in-memory list of lines."""
    if isinstance(source, str):
        with open(source, encoding="utf-8", errors="replace") as handle:
            yield from handle
    else:
        yield from source


def script_kind(script):
    return re.sub(r"_\d+$", "", script)


def block_key(name):
    return re.sub(r"\d+", "#", name.strip())


def clock_seconds(clock):
    h, m, s = clock.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def parse_line(line):
    """(script, level, tick, clock_seconds|None, depth, kind, text) for a block line, else None.
    kind is "start" or "end"; depth counts the "┃   " in front of the marker."""
    match = LINE_RE.match(line.rstrip("\n"))
    if not match:
        return None
    body = match["body"]
    depth = 0
    while body.startswith(BRANCH):
        body = body[len(BRANCH) :]
        depth += 1
    if body.startswith(START):
        kind = "start"
    elif body.startswith(END):
        kind = "end"
    else:
        return None
    clock = clock_seconds(match["clock"]) if match["clock"] else None
    return (match["script"], match["level"], int(match["tick"]), clock, depth, kind, body[len(START) :])


def calibration(paths):
    """(median game seconds per tick or None, flush pairs used): for each script, the last debug clock of
    each flush tick, compared between consecutive flushes. paths: {base: [path or list of lines]}."""
    ratios = []
    for files in paths.values():
        flushes = []  # (tick, last clock seconds)
        for source in files:
            for line in _lines(source):
                match = LINE_RE.match(line)
                if not match or not match["clock"] or match["level"] != "debug":
                    continue
                tick, clock = int(match["tick"]), clock_seconds(match["clock"])
                if flushes and flushes[-1][0] == tick:
                    flushes[-1] = (tick, clock)
                else:
                    flushes.append((tick, clock))
        for (t0, c0), (t1, c1) in itertools.pairwise(flushes):
            dt, dc = t1 - t0, (c1 - c0) % DAY
            if 0 < dt < 5000 and 0 < dc < DAY / 2:
                ratios.append(dc / dt)
    return (statistics.median(ratios) if ratios else None), len(ratios)


def calibrate(paths):
    """Median game seconds per tick (see calibration), or None."""
    return calibration(paths)[0]


def allowance(running):
    """Steps per script per tick with `running` scripts counted (lib/script_census.py)."""
    if running <= 0:
        return MAX_STEPS_PER_SCRIPT
    return max(1, min(MAX_STEPS_PER_SCRIPT, TOTAL_STEPS_PER_TICK // running))


class Census:
    """Running-script count over ticks, from the census lines."""

    def __init__(self, points):
        points = sorted(points)
        self.ticks = [tick for tick, _ in points]
        self.counts = [count for _, count in points]

    def at(self, tick):
        """Latest count at or before tick, else None."""
        index = bisect.bisect_right(self.ticks, tick) - 1
        return self.counts[index] if index >= 0 else None


class Block:
    __slots__ = ("child_seconds", "clock", "key", "tick")

    def __init__(self, key, tick, clock):
        self.key, self.tick, self.clock, self.child_seconds = key, tick, clock, 0.0


def duration(block, tick, clock, sec_per_tick):
    """Game seconds between a block's start and an end line, or None if it cannot be told."""
    if block.clock is not None and clock is not None:
        return float((clock - block.clock) % DAY)
    if sec_per_tick is not None:
        return (tick - block.tick) * sec_per_tick
    return None


def collect(paths, sec_per_tick, script_filter, since=None):
    """{(kind, block key): {"seconds": [...], "self": [...], "starts": [...], "scripts": set}}, unclosed count,
    windows, span, Census. windows: {script: [first tick, last tick]} for share-of-window."""
    stats = collections.defaultdict(lambda: {"seconds": [], "self": [], "starts": [], "scripts": set()})
    census = []  # (tick, running scripts)
    unclosed = 0
    windows = {}
    span: list[str | None] = [None, None]  # first and last iso time read
    for base, files in paths.items():
        if script_filter and script_filter not in base:
            continue
        stack = []  # (depth, Block)
        for source in files:
            for line in _lines(source):
                if since and line[1:25] < since:
                    continue
                if line.startswith("["):
                    iso = line[1:25]
                    span[0] = iso if span[0] is None or iso < span[0] else span[0]
                    span[1] = iso if span[1] is None or iso > span[1] else span[1]
                if "scripts running: " in line:
                    found_census = CENSUS_RE.search(line)
                    match = LINE_RE.match(line) if found_census else None
                    if match and found_census:
                        census.append((int(match["tick"]), int(found_census.group(1))))
                parsed = parse_line(line)
                if parsed is None:
                    match = LINE_RE.match(line)
                    if match:
                        window = windows.setdefault(match["script"], [int(match["tick"])] * 2)
                        window[1] = max(window[1], int(match["tick"]))
                    continue
                script, _level, tick, clock, depth, kind, text = parsed
                window = windows.setdefault(script, [tick, tick])
                window[0], window[1] = min(window[0], tick), max(window[1], tick)
                # A line at depth d means every block opened at depth >= d (start) or > d (end) was
                # left open by a reset_all() or a dropped end().
                keep = depth if kind == "start" else depth + 1
                while kind == "start" and stack and stack[-1][0] >= keep:
                    stack.pop()
                    unclosed += 1
                if kind == "start":
                    stack.append((depth, Block((script_kind(script), block_key(text)), tick, clock)))
                    continue
                if text.startswith("END "):
                    name = block_key(text[4:])
                    found = next((i for i in range(len(stack) - 1, -1, -1) if stack[i][1].key[1] == name), None)
                    if found is None:
                        continue
                    unclosed += len(stack) - 1 - found
                    del stack[found + 1 :]
                elif not stack or stack[-1][0] != depth:
                    continue
                _, block = stack.pop()
                seconds = duration(block, tick, clock, sec_per_tick)
                if seconds is None:
                    continue
                entry = stats[block.key]
                entry["seconds"].append(seconds)
                entry["self"].append(max(seconds - block.child_seconds, 0.0))
                entry["starts"].append(block.tick)
                entry["scripts"].add(script)
                if stack:
                    stack[-1][1].child_seconds += seconds
        unclosed += len(stack)
    return stats, unclosed, windows, span, Census(census)


def fmt(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def fmt_steps(steps):
    if steps is None:
        return "-"
    if steps < 1000:
        return f"{steps:.0f}"
    if steps < 1e6:
        return f"{steps / 1000:.1f}k"
    return f"{steps / 1e6:.1f}M"


def step_costs(entry, sec_per_tick, census):
    """(median N, [steps per run]) for one block; (None, []) without census or calibration."""
    if not sec_per_tick or not census.ticks:
        return None, []
    counts, steps = [], []
    for seconds, start in zip(entry["seconds"], entry["starts"]):
        running = census.at(start)
        if running is None:
            continue
        counts.append(running)
        steps.append(seconds / sec_per_tick * allowance(running))
    return (statistics.median(counts) if counts else None), steps


def report(stats, windows, sec_per_tick, top, min_count, sort, census=None):
    kind_window = collections.defaultdict(float)  # summed per-instance observed game seconds per kind
    if sec_per_tick:
        for script, (first, last) in windows.items():
            kind_window[script_kind(script)] += (last - first) * sec_per_tick
    rows = []
    for (kind, key), entry in stats.items():
        seconds = entry["seconds"]
        if len(seconds) < min_count:
            continue
        total = sum(seconds)
        window = kind_window.get(kind, 0.0)
        med_n, steps = step_costs(entry, sec_per_tick, census or Census([]))
        rows.append(
            {
                "kind": kind,
                "block": key,
                "n": len(seconds),
                "inst": len(entry["scripts"]),
                "med": statistics.median(seconds),
                "max": max(seconds),
                "self": statistics.median(entry["self"]),
                "total": total,
                "share": total / window if window else 0.0,
                "self_total": sum(entry["self"]),
                "med_n": med_n,
                "med_st": statistics.median(steps) if steps else None,
                "steps": sum(steps),
            }
        )
    order = {"total": "total", "self": "self_total", "median": "med", "max": "max", "share": "share", "steps": "steps"}[
        sort
    ]
    rows.sort(key=lambda row: row[order], reverse=True)
    header = (
        f"{'script':<22} {'block':<52} {'n':>5} {'inst':>4} {'median':>7} {'med_tk':>6} {'max':>7} "
        f"{'self':>7} {'total':>7} {'share':>6} {'med_N':>5} {'med_st':>7}"
    )
    print(header)
    print("-" * len(header))
    for row in rows[:top]:
        block = row["block"] if len(row["block"]) <= 52 else row["block"][:49] + "..."
        print(
            f"{row['kind'][:22]:<22} {block:<52} {row['n']:>5} {row['inst']:>4} {fmt(row['med']):>7} "
            f"{row['med'] / (sec_per_tick or 1):>6.0f} {fmt(row['max']):>7} {fmt(row['self']):>7} {fmt(row['total']):>7} {row['share']:>6.1%} "
            f"{row['med_n'] if row['med_n'] is not None else '-':>5} {fmt_steps(row['med_st']):>7}"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--save", help="save_*_scripts folder (default: newest by mtime)")
    source.add_argument("--headless", metavar="PATH", help="headless run dir or its console.log (run.mjs --out)")
    parser.add_argument("--script", help="only log files whose name contains this")
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument("--min-count", type=int, default=2, help="skip blocks seen fewer times")
    parser.add_argument(
        "--since",
        help="skip lines logged before this ISO time (e.g. 2026-10-02T20:00); with --headless a tick (e.g. 1038500)",
    )
    parser.add_argument("--sec-per-tick", type=float, help="game seconds per tick; overrides the log calibration")
    parser.add_argument("--exclude", help="regex; skip blocks whose name matches (e.g. travel/wait blocks)")
    parser.add_argument("--sort", choices=("total", "self", "median", "max", "share", "steps"), default="total")
    args = parser.parse_args()
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

    since = args.since
    if args.headless:
        if since is not None and not since.isdigit():
            parser.error("--since takes a tick with --headless")
        since = headless_iso(int(since)) if since is not None else None
        origin = headless_console(args.headless)
        paths = {script: [lines] for script, lines in headless_lines(origin).items()}
    else:
        origin = args.save or newest_save()
        paths = log_files(os.path.join(origin, "logs"))
    if args.sec_per_tick is not None:
        if not 0 < args.sec_per_tick < float("inf"):
            parser.error("--sec-per-tick must be a positive number")
        sec_per_tick, calibrated = args.sec_per_tick, "override"
    else:
        sec_per_tick, pairs = calibration(paths)
        calibrated = f"{pairs} flush pair(s)"
    stats, unclosed, windows, span, census = collect(paths, sec_per_tick, args.script, since)
    if args.exclude:
        pattern = re.compile(args.exclude)
        stats = {key: entry for key, entry in stats.items() if not pattern.search(key[1])}
    ratio = f"{sec_per_tick:.2f} game s/tick" if sec_per_tick else "uncalibrated (tick-only blocks skipped)"
    print(f"{origin}\n{len(paths)} log groups, {ratio} ({calibrated}), {unclosed} unclosed block(s) dropped")
    if args.headless:
        ticks = [tick for window in windows.values() for tick in window]
        print(f"tick window {min(ticks, default='-')} .. {max(ticks, default='-')}")
    else:
        print(f"log window {span[0]} .. {span[1]} (UTC)")
    if census.counts:
        print(f"running scripts: {min(census.counts)}..{max(census.counts)} over {len(census.counts)} census line(s)\n")
    else:
        print("running scripts: no census lines (lib/script_census.py), med_N/med_st unknown\n")
    report(stats, windows, sec_per_tick, args.top, args.min_count, args.sort, census)


if __name__ == "__main__":
    main()
