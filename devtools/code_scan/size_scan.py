"""
Size scan: long files and complex functions. Size is a smell, not a defect:
every hit is a reason to look, and a reviewed "leave as is" goes in the ignore file.

    python devtools/code_scan/size_scan.py                  # full report, ignored ids left out
    python devtools/code_scan/size_scan.py --summary        # counts only
    python devtools/code_scan/size_scan.py --max-lines 1500 --max-complexity 15
    python devtools/code_scan/clean_code_scan.py size ...   # the same, via the combined entry point

Scans the same files as clone_scan.py and feature_scan.py. Function metrics
come from Ruff (C901 complexity, PLR0912 branches, PLR0915 statements), so the
repo's Ruff (.venv) must be installed; limits default to Ruff's. Ruff.toml
leaves these rules off on purpose: they would turn a smell into a gate.

  file      more than --max-lines lines
  function  over one or more of --max-complexity, --max-branches, --max-statements

Every hit has an id "<file>::<qualname>", "<module>" for a file hit (no line
numbers, so it survives edits). Reviewed hits that should stay as they are go
in devtools/code_scan/size_scan_ignore.txt, one id per line with the reason
after '#'. --all shows them anyway. Hits are sorted worst first: the highest
value/limit ratio of any metric.
"""

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys

from scan_common import REPO_ROOT, SCRIPTS, ignore_lines, scanned_files

IGNORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "size_scan_ignore.txt")
MODULE = "<module>"
RULES = {"C901": "complexity", "PLR0912": "branches", "PLR0915": "statements"}
FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
VALUE_LIMIT = re.compile(r"\((\d+) > (\d+)\)")


class Hit:
    def __init__(self, rel, line, subject, metrics):
        self.rel, self.line, self.subject = rel, line, subject
        self.metrics = metrics  # {metric: (value, limit)}

    @property
    def id(self):
        return f"{self.rel}::{self.subject}"

    @property
    def score(self):
        return max(value / limit for value, limit in self.metrics.values())

    @property
    def detail(self):
        return ", ".join(f"{m} {v}/{lim}" for m, (v, lim) in self.metrics.items())


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


def report(hits, summary, ignored_count):
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
    if summary:
        return "\n".join(out)
    for title, group in (("file", files), ("function", functions)):
        out.append(f"\n## {title} ({len(group)})\n")
        out += [f"- {h.rel}:{h.line} `{h.id}`: {h.detail}" for h in group]
    return "\n".join(out)


def add_arguments(parser):
    parser.add_argument("--max-lines", type=int, default=1000, help="file line limit (default 1000)")
    parser.add_argument("--max-complexity", type=int, default=10, help="C901 limit (default 10, Ruff's)")
    parser.add_argument("--max-branches", type=int, default=12, help="PLR0912 limit (default 12, Ruff's)")
    parser.add_argument("--max-statements", type=int, default=50, help="PLR0915 limit (default 50, Ruff's)")
    parser.add_argument("--summary", action="store_true", help="counts only")
    parser.add_argument("--all", action="store_true", help="include hits listed in the ignore file")
    parser.add_argument("--out", help="write the report to this file")


def run(args):
    files = scanned_files()
    hits = scan(files, args)
    ignored = set() if args.all else set(ignore_lines(IGNORE_FILE))
    kept = [h for h in hits if h.id not in ignored]
    text = report(kept, args.summary, len(hits) - len(kept))
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
