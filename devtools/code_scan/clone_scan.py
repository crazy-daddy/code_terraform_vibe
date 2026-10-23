"""
Near-duplicate function scan: finds functions whose bodies have nearly the
same normalized AST, as candidates to merge into one shared helper.

    python devtools/code_scan/clone_scan.py                     # clusters of new pairs, best first
    python devtools/code_scan/clean_code_scan.py clones         # the same, via the combined entry point
    python devtools/code_scan/clone_scan.py --pairs --top 0     # every pair
    python devtools/code_scan/clone_scan.py --min-ratio 0.9 --top 60
    python devtools/code_scan/clone_scan.py --all               # also pairs in the ignore file
    python devtools/code_scan/clone_scan.py --grep fluid        # only pairs touching a path/name match

Scans the highest-tier copy of every file under scripts/<N>_*/ (the copy the
game runs) plus scripts/contract/ and scripts/onboarding/ and every .py under autoplay/
(untiered, shown as autoplay/<path>). Each function body
(methods and nested functions too) is normalized: every name and argument
becomes "_", every constant becomes its type name, annotations are dropped.
Two functions pair when their line counts are within LENGTH_RATIO of each
other and the token sequences of their normalized dumps match at least
--min-ratio (difflib). Pairs rank by ratio x the shorter function's length,
so long near-clones come first. Output groups the top pairs into clusters
(connected components, so a loose chain can join unrelated functions),
ordered by their best pair; --pairs lists the pairs themselves.

"nolib" marks a pair with a side in a tier below LIB_TIER: that file cannot
import lib/, so it can only share code with files of its own tier.

No "cross" mark for autoplay/ <-> scripts/ pairs, but the sharing runs one way:
scripts_sync.py merge_autoplay() puts autoplay/lib/*.py into the same lib
index as the script libs, so autoplay modules can import script libs. It only
runs for a save at tier LIB_UNLOCK_TIER_NUMBER or above and
with --include-autoplay, so scripts/<tier> files must never import
autoplay/lib (it breaks deploys without --include-autoplay). A helper shared by an autoplay/ and a scripts/ copy must
therefore live in a scripts lib, never in autoplay/lib. Files under autoplay/
(outside the tier tree) show no tier.

Reviewed pairs that should stay apart (same shape, different intent) go in
devtools/code_scan/clone_scan_ignore.txt, one per line:
    <file>::<qualname> ~ <file>::<qualname>   # reason
<file> is the path below the tier folder (e.g. lib/fabricator.py), or the
repo-relative path for autoplay/ files (e.g. autoplay/lib/focus_plan.py); order of
the two sides does not matter. Line numbers are not used, so entries survive
edits. Merged pairs drop out on their own.

Heuristic: a high ratio means the same shape, not the same meaning. Read
both functions (and diff them) before merging.
"""

import argparse
import ast
import copy
import difflib
import itertools
import os
import re
import sys

from scan_common import ignore_lines, scanned_files

IGNORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clone_scan_ignore.txt")
LIB_TIER = 2  # first tier whose scripts can import lib/
MIN_LINES = 6
LENGTH_RATIO = 0.6


class Normalize(ast.NodeTransformer):
    def visit_Name(self, node):
        return ast.copy_location(ast.Name(id="_", ctx=node.ctx), node)

    def visit_arg(self, node):
        node.arg = "_"
        node.annotation = None
        return node

    def visit_Constant(self, node):
        return ast.copy_location(ast.Constant(value=type(node.value).__name__), node)


class Function:
    def __init__(self, rel, tier, qualname, node):
        self.rel = rel
        self.tier = tier
        self.qualname = qualname
        self.line = node.lineno
        self.length = (node.end_lineno or node.lineno) - node.lineno + 1
        body = ast.Module(body=copy.deepcopy(node.body), type_ignores=[])
        dump = ast.dump(Normalize().visit(body))
        self.tokens = dump.replace("(", " ").replace(")", " ").replace(",", " ").split()

    @property
    def key(self):
        return f"{self.rel}::{self.qualname}"


def collect(files, min_lines):
    out = []

    def visit(rel, tier, node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + child.name
                if (child.end_lineno or child.lineno) - child.lineno + 1 >= min_lines:
                    out.append(Function(rel, tier, name, child))
                visit(rel, tier, child, name + ".")
            elif isinstance(child, ast.ClassDef):
                visit(rel, tier, child, prefix + child.name + ".")
            else:
                visit(rel, tier, child, prefix)

    for rel, (path, tier) in sorted(files.items()):
        with open(path, encoding="utf-8") as f:
            visit(rel, tier, ast.parse(f.read(), path), "")
    return out


def load_ignore(path):
    pairs = set()
    for line in ignore_lines(path):
        if "~" in line:
            a, b = (s.strip() for s in line.split("~", 1))
            pairs.add(frozenset((a, b)))
    return pairs


def find_pairs(functions, min_ratio):
    pairs = []
    for a, b in itertools.combinations(functions, 2):
        if min(a.length, b.length) / max(a.length, b.length) < LENGTH_RATIO:
            continue
        if a.rel == b.rel and (b.qualname.startswith(a.qualname + ".") or a.qualname.startswith(b.qualname + ".")):
            continue  # a nested function matches the body that holds it
        sm = difflib.SequenceMatcher(None, a.tokens, b.tokens, autojunk=False)
        if sm.real_quick_ratio() >= min_ratio and sm.quick_ratio() >= min_ratio:
            ratio = sm.ratio()
            if ratio >= min_ratio:
                pairs.append((ratio, a, b))
    return pairs


def clusters(pairs):
    """{function key: cluster number}, numbered by each cluster's best pair."""
    parent = {}

    def find(k):
        while parent.setdefault(k, k) != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for _, a, b in pairs:
        parent[find(a.key)] = find(b.key)
    numbers, out = {}, {}
    for _, a, b in pairs:
        root = find(a.key)
        numbers.setdefault(root, len(numbers) + 1)
        out[a.key] = out[b.key] = numbers[root]
    return out


def add_arguments(parser):
    parser.add_argument("--min-ratio", type=float, default=0.85, help="minimum token similarity (default 0.85)")
    parser.add_argument(
        "--min-lines", type=int, default=MIN_LINES, help=f"skip shorter functions (default {MIN_LINES})"
    )
    parser.add_argument("--top", type=int, default=150, help="pairs to print (default 150, 0 = all)")
    parser.add_argument("--grep", help="regex; keep pairs whose path or qualname matches on either side")
    parser.add_argument("--pairs", action="store_true", help="print every pair instead of clusters")
    parser.add_argument("--all", action="store_true", help="include pairs listed in the ignore file")
    parser.add_argument("--no-nolib", action="store_true", help="drop pairs with a side below LIB_TIER")


def run(args):
    functions = collect(scanned_files(include_autoplay=True), args.min_lines)
    pairs = find_pairs(functions, args.min_ratio)
    ignored = set() if args.all else load_ignore(IGNORE_FILE)
    nolib = lambda a, b: any(f.tier is not None and f.tier < LIB_TIER for f in (a, b))
    pairs = [p for p in pairs if frozenset((p[1].key, p[2].key)) not in ignored]
    if args.no_nolib:
        pairs = [p for p in pairs if not nolib(p[1], p[2])]
    if args.grep:
        rx = re.compile(args.grep)
        pairs = [p for p in pairs if any(rx.search(f.key) for f in p[1:])]
    pairs.sort(key=lambda p: -p[0] * min(p[1].length, p[2].length))
    shown = pairs[: args.top] if args.top else pairs
    cluster = clusters(shown)

    print(
        f"{len(functions)} functions >= {args.min_lines} lines, {len(pairs)} pairs >= {args.min_ratio}"
        f" ({len(ignored)} ignore entries), showing {len(shown)}",
        file=sys.stderr,
    )
    if args.pairs:
        for ratio, a, b in shown:
            flag = " nolib" if nolib(a, b) else ""
            print(
                f"c{cluster[a.key]:<3} {ratio:.2f}{flag}  {a.rel}:{a.line} {a.qualname} ({a.length}L)"
                f"  ~  {b.rel}:{b.line} {b.qualname} ({b.length}L)"
            )
        return
    members, best = {}, {}
    for ratio, a, b in shown:
        c = cluster[a.key]
        members.setdefault(c, {}).update({a.key: a, b.key: b})
        best[c] = max(best.get(c, 0), ratio)
    for c, fs in members.items():
        fs = sorted(fs.values(), key=lambda f: f.key)
        flag = " nolib" if any(f.tier is not None and f.tier < LIB_TIER for f in fs) else ""
        print(f"c{c}  {len(fs)} functions, best {best[c]:.2f}{flag}")
        for f in fs:
            print(f"    {f.rel}:{f.line} {f.qualname} ({f.length}L)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(parser)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
