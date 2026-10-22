"""
Size scan: long files and complex functions. Size is a smell, not a defect:
every hit is a reason to look, and a reviewed "leave as is" goes in the ignore file.

    python devtools/code_scan/size_scan.py                  # full report, ignored ids left out
    python devtools/code_scan/size_scan.py --summary        # counts only
    python devtools/code_scan/size_scan.py --pin            # pin ignore entries to current metrics
    python devtools/code_scan/size_scan.py --max-lines 1500 --max-complexity 15
    python devtools/code_scan/clean_code_scan.py size ...   # the same, via the combined entry point

Scans the same files as clone_scan.py and feature_scan.py. Function metrics
come from Ruff (C901 complexity, PLR0912 branches, PLR0915 statements), so the
repo's Ruff (.venv) must be installed; limits default to Ruff's. Ruff.toml
leaves these rules off on purpose: they would turn a smell into a gate.

  file      more than --max-lines lines
  function  over one or more of --max-complexity, --max-branches, --max-statements

Every hit has an id "<file>::<qualname>", "<module>" for a file hit (no line
numbers, so it survives edits). Hits are sorted worst first: the highest
value/limit ratio of any metric.

Reviewed hits that should stay as they are go in
devtools/code_scan/size_scan_ignore.txt, one id per line with a pin of its
metrics at review time and the reason after '#':

  lib/x.py::Cls.fn  @22/17/56  # reason    complexity/branches/statements, '-' if under the limit
  lib/x.py::<module>  @1434  # reason      line count

Revisit rule: an entry suppresses its hit only while every metric stays at
most pin + max(3, 10 % of pin) (lines: pin + max(50, 10 %)); a '-' pin counts
as the limit. Past that, the hit is reported again, marked "grew since
review". The report also lists unpinned entries (no '@', still suppress) and
stale entries (the id no longer hits: gone, renamed or under the limits;
remove them by hand). --pin rewrites the ignore file in place, setting every
still-hitting entry's pin to its current metrics and keeping comments,
reasons and order; review grown hits before you run it. Pin at the default
limits: a '-' means "under the limit". --all shows ignored hits anyway.
"""

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys

from scan_common import REPO_ROOT, SCRIPTS, scanned_files

IGNORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "size_scan_ignore.txt")
MODULE = "<module>"
RULES = {"C901": "complexity", "PLR0912": "branches", "PLR0915": "statements"}
FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
VALUE_LIMIT = re.compile(r"\((\d+) > (\d+)\)")
ENTRY = re.compile(r"^(?P<id>.+?)(?:\s+@(?P<pin>\S+))?$")
MIN_SLACK = {"lines": 50}  # absolute drift allowance per metric; other metrics: DEFAULT_SLACK
DEFAULT_SLACK = 3
SLACK_SHARE = 0.1  # relative drift allowance, of the pinned value


def metric_names(item_id):
    """Pinned metrics of a hit id, in pin order."""
    return ("lines",) if item_id.endswith("::" + MODULE) else tuple(RULES.values())


class Hit:
    def __init__(self, rel, line, subject, metrics):
        self.rel, self.line, self.subject = rel, line, subject
        self.metrics = metrics  # {metric: (value, limit)}
        self.note = ""

    @property
    def id(self):
        return f"{self.rel}::{self.subject}"

    @property
    def score(self):
        return max(value / limit for value, limit in self.metrics.values())

    @property
    def detail(self):
        text = ", ".join(f"{m} {v}/{lim}" for m, (v, lim) in self.metrics.items())
        return f"{text}; {self.note}" if self.note else text

    @property
    def pin(self):
        """Current metrics in pin format, '-' for a metric under its limit."""
        return "/".join(str(self.metrics[m][0]) if m in self.metrics else "-" for m in metric_names(self.id))


class Entry:
    """One ignore-file entry: 1-based line number, hit id, pin {metric: value or None} or None if unpinned."""

    def __init__(self, number, item_id, pin):
        self.number, self.id, self.pin = number, item_id, pin

    @property
    def pin_text(self):
        return "/".join("-" if v is None else str(v) for v in self.pin.values())


def parse_entry(code, number):
    """Entry for one ignore line with its '#' comment stripped. ValueError on a malformed pin."""
    match = ENTRY.match(code)
    if match is None:
        raise ValueError(f"line {number}: empty entry")
    item_id, raw = match.group("id"), match.group("pin")
    if raw is None:
        return Entry(number, item_id, None)
    names = metric_names(item_id)
    fields = raw.split("/")
    if len(fields) != len(names) or not all(f == "-" or f.isdigit() for f in fields):
        raise ValueError(f"line {number}: pin @{raw} of {item_id} needs {'/'.join(names)} (numbers or '-')")
    return Entry(number, item_id, {m: None if f == "-" else int(f) for m, f in zip(names, fields)})


def parse_entries(lines):
    """Entries of an ignore file's raw lines; blank and comment-only lines skipped."""
    entries = []
    for number, raw in enumerate(lines, 1):
        code = raw.split("#", 1)[0].strip()
        if code:
            entries.append(parse_entry(code, number))
    return entries


def read_lines(path):
    """Raw lines with their endings kept. Missing file: none."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return f.readlines()


def grown(hit, pin):
    """True when a metric of the hit is past its pin plus slack. A '-' pin counts as the limit."""
    for metric, (value, limit) in hit.metrics.items():
        base = pin.get(metric)
        if base is None:
            base = limit
        if value > base + max(MIN_SLACK.get(metric, DEFAULT_SLACK), base * SLACK_SHARE):
            return True
    return False


def triage(hits, entries, suppress=True):
    """(kept hits, suppressed count, grown hits, unpinned entries, stale entries). Marks grown hits' notes."""
    by_id = {e.id: e for e in entries}
    hit_ids = {h.id for h in hits}
    kept, grew = [], []
    for hit in hits:
        entry = by_id.get(hit.id)
        if entry is not None and entry.pin is not None and grown(hit, entry.pin):
            hit.note = f"grew since review ({entry.pin_text} -> {hit.pin})"
            grew.append(hit)
        elif entry is not None and suppress:
            continue
        kept.append(hit)
    unpinned = [e for e in entries if e.pin is None and e.id in hit_ids]
    stale = [e for e in entries if e.id not in hit_ids]
    return kept, len(hits) - len(kept), grew, unpinned, stale


def pin_lines(lines, hits):
    """(new lines, changed count): every still-hitting entry pinned to its current metrics, the rest unchanged."""
    current = {h.id: h.pin for h in hits}
    out, changed = [], 0
    for number, raw in enumerate(lines, 1):
        body = raw.rstrip("\r\n")
        ending = raw[len(body) :]
        code, sep, comment = body.partition("#")
        entry = parse_entry(code.strip(), number) if code.strip() else None
        if entry is None or entry.id not in current:
            out.append(raw)
            continue
        new = f"{entry.id}  @{current[entry.id]}" + (f"  #{comment}" if sep else "") + ending
        changed += new != raw
        out.append(new)
    return out, changed


def pin_file(path, hits):
    """Rewrite the ignore file with current pins. Returns the changed line count."""
    lines, changed = pin_lines(read_lines(path), hits)
    if changed:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.writelines(lines)
    return changed


def function_names(tree):
    """{def line: qualname} for every function; classes only add to the prefix."""
    names = {}

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef,) + FUNCTION_NODES):
                name = prefix + child.name
                if isinstance(child, FUNCTION_NODES):
                    names[child.lineno] = name
                visit(child, name + ".")
            else:
                visit(child, prefix)

    visit(tree, "")
    return names


def file_hits(rel, source, diagnostics, max_lines):
    """Hits for one file. diagnostics: [(row, ruff code, message)] from Ruff for this file."""
    hits = []
    lines = len(source.splitlines())
    if lines > max_lines:
        hits.append(Hit(rel, 1, MODULE, {"lines": (lines, max_lines)}))
    names = function_names(ast.parse(source)) if diagnostics else {}
    by_row = {}
    for row, code, message in sorted(diagnostics):
        match = VALUE_LIMIT.search(message)
        if code not in RULES or not match:
            continue
        hit = by_row.get(row)
        if hit is None:
            hit = by_row[row] = Hit(rel, row, names.get(row, f"<line {row}>"), {})
        hit.metrics[RULES[code]] = (int(match.group(1)), int(match.group(2)))
    return hits + list(by_row.values())


def ruff_command():
    venv = os.pathsep.join(os.path.join(REPO_ROOT, ".venv", d) for d in ("Scripts", "bin"))
    ruff = shutil.which("ruff", path=venv) or shutil.which("ruff")
    if not ruff:
        sys.exit("ruff not found: install the repo .venv (see CODE_GUIDES.md#checks)")
    return ruff


def ruff_diagnostics(args):
    """{normalized absolute path: [(row, code, message)]} for the whole scripts/ tree."""
    command = [
        ruff_command(),
        "check",
        SCRIPTS,
        "--select",
        ",".join(RULES),
        "--output-format",
        "json",
        "--exit-zero",
        "--config",
        f"lint.mccabe.max-complexity={args.max_complexity}",
        "--config",
        f"lint.pylint.max-branches={args.max_branches}",
        "--config",
        f"lint.pylint.max-statements={args.max_statements}",
    ]
    done = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", check=True)
    found = {}
    for item in json.loads(done.stdout):
        key = os.path.normcase(os.path.abspath(item["filename"]))
        found.setdefault(key, []).append((item["location"]["row"], item["code"], item["message"]))
    return found


def scan(files, args):
    diagnostics = ruff_diagnostics(args)
    hits = []
    for rel, (path, _tier) in sorted(files.items()):
        with open(path, encoding="utf-8") as f:
            source = f.read()
        try:
            hits += file_hits(rel, source, diagnostics.get(os.path.normcase(path), []), args.max_lines)
        except SyntaxError as error:
            print(f"skip {rel}: {error}", file=sys.stderr)
    return hits


def report(hits, summary, ignored_count, review=((), (), ())):
    """review: (grown hits, unpinned entries, stale entries) from triage()."""
    grew, unpinned, stale = review
    files = sorted((h for h in hits if h.subject == MODULE), key=lambda h: -h.score)
    functions = sorted((h for h in hits if h.subject != MODULE), key=lambda h: -h.score)
    out = [
        "# Size scan\n",
        "| kind | hits |",
        "|---|---|",
        f"| file | {len(files)} |",
        f"| function | {len(functions)} |",
    ]
    out.append(f"\nIgnored by {os.path.basename(IGNORE_FILE)}: {ignored_count}.")
    out.append(f"Ignore entries to revisit: {len(grew)} grown, {len(unpinned)} unpinned, {len(stale)} stale.")
    if summary:
        return "\n".join(out)
    for title, group in (("file", files), ("function", functions)):
        out.append(f"\n## {title} ({len(group)})\n")
        out += [f"- {h.rel}:{h.line} `{h.id}`: {h.detail}" for h in group]
    for title, group in (("unpinned, pin after review (--pin)", unpinned), ("stale, remove", stale)):
        if group:
            out.append(f"\n## ignore entries {title} ({len(group)})\n")
            out += [f"- line {e.number} `{e.id}`" for e in group]
    return "\n".join(out)


def add_arguments(parser):
    parser.add_argument("--max-lines", type=int, default=1000, help="file line limit (default 1000)")
    parser.add_argument("--max-complexity", type=int, default=10, help="C901 limit (default 10, Ruff's)")
    parser.add_argument("--max-branches", type=int, default=12, help="PLR0912 limit (default 12, Ruff's)")
    parser.add_argument("--max-statements", type=int, default=50, help="PLR0915 limit (default 50, Ruff's)")
    parser.add_argument("--summary", action="store_true", help="counts only")
    parser.add_argument("--all", action="store_true", help="include hits listed in the ignore file")
    parser.add_argument("--pin", action="store_true", help="set each still-hitting ignore entry's pin to its metrics")
    parser.add_argument("--out", help="write the report to this file")


def run(args):
    files = scanned_files()
    hits = scan(files, args)
    try:
        if args.pin:
            changed = pin_file(IGNORE_FILE, hits)
            print(f"pinned {changed} line(s) in {os.path.basename(IGNORE_FILE)}", file=sys.stderr)
        entries = parse_entries(read_lines(IGNORE_FILE))
    except ValueError as error:
        sys.exit(f"{IGNORE_FILE}: {error}")
    kept, ignored, *review = triage(hits, entries, suppress=not args.all)
    text = report(kept, args.summary, ignored, review)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"{len(files)} files scanned, report in {args.out}", file=sys.stderr)
    else:
        print(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(parser)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
