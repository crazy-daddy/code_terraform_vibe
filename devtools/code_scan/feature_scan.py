"""
Static scan for code written around interpreter features the game supports
(dataclass, property setters, total_ordering, __getattr__, __init_subclass__,
match, TypedDict). Finds candidates only: every hit needs a verdict before a change.

    python devtools/code_scan/feature_scan.py                       # full report, ignored ids left out
    python devtools/code_scan/feature_scan.py --summary             # counts per pattern
    python devtools/code_scan/feature_scan.py -p value_class -p elif_chain --out scan.md
    python devtools/code_scan/clean_code_scan.py features ...       # the same, via the combined entry point

Scans the same files as clone_scan.py: the highest-tier copy of every file
under scripts/<N>_*/ plus scripts/contract/ and scripts/onboarding/.

  value_class    base-less class whose __init__ only stores fields, with few
                 other methods or hand-written __eq__/__repr__/__hash__  -> @dataclass
  ordering       two or more rich comparisons written by hand            -> total_ordering
  property_pair  get_x()/set_x() method pairs                            -> @property + setter
  delegation     3+ methods that only forward to self.<inner>            -> __getattr__
  registry       module dict/subscript filled with 3+ local classes      -> __init_subclass__
  tuple_return   function returns tuples of 3+ items (sort keys skipped) -> @dataclass
  tuple_index    one name read by 3+ distinct int indices                -> named fields
  elif_chain     3+ branches testing one subject against values          -> match
  dict_shape     dict literals with 3+ constant str keys, grouped by key set
                 (2+ sites or 4+ keys), with reads of those keys         -> TypedDict
  ipc_key        archive and comms calls grouped by key or channel; key
                 constants resolve to their string, "(?)" when they can't -> TypedDict + StrEnum

Every hit has an id "<file>::<pattern>::<subject>" (no line numbers, so it
survives edits; "*" as file for the cross-file patterns dict_shape and
ipc_key). Reviewed hits that should stay as they are go in
devtools/code_scan/feature_scan_ignore.txt, one id per line with the reason after '#'.
--all shows them anyway. Converted hits drop out on their own.

Heuristic: names resolve by text only; tuple_index also catches lists and
dict_shape also catches static data tables. Read the code before acting.
"""
import argparse
import ast
import collections
import os
import re
import sys
from typing import TypeGuard

from scan_common import ignore_lines, scanned_files

IGNORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feature_scan_ignore.txt")
PATTERNS = ("value_class", "ordering", "property_pair", "delegation", "registry",
            "tuple_return", "tuple_index", "elif_chain", "dict_shape", "ipc_key")
RICH_COMPARE = {"__lt__", "__le__", "__gt__", "__ge__"}
VALUE_DUNDERS = {"__eq__", "__repr__", "__hash__", "__str__", "__ne__"}
ARCHIVE_OPS = {"get", "set", "transaction", "delete", "has", "publish_status",
               "pop_entry", "get_entry", "set_entry"}
COMMS_OPS = {"broadcast", "latest", "wait_broadcast", "send", "receive"}
MIN_CHAIN = 3
MIN_DICT_KEYS = 3
SORT_KEY_NAME = re.compile(r"key|rank|sort|order", re.I)  # tuple returns used as sort keys
FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def body_without_docstring(body):
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def is_self_attr(node) -> TypeGuard[ast.Attribute]:
    return isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self"


def is_super_init(stmt):
    return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Attribute) and stmt.value.func.attr == "__init__")


def tail_name(node):
    """Last name of a dotted receiver: self.archive -> archive, comms -> comms."""
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def str_const(node) -> TypeGuard[ast.Constant]:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def qualnames(tree):
    """{id(node): qualname} for every class and function, and {id(node): enclosing qualname} for the rest."""
    own, enclosing = {}, {}

    def visit(node, prefix, scope):
        for child in ast.iter_child_nodes(node):
            enclosing[id(child)] = scope
            if isinstance(child, (ast.ClassDef,) + FUNCTION_NODES):
                name = prefix + child.name
                own[id(child)] = name
                visit(child, name + ".", name)
            else:
                visit(child, prefix, scope)

    visit(tree, "", "<module>")
    return own, enclosing


class Hit:
    def __init__(self, pattern, rel, line, subject, detail, sites=()):
        self.pattern, self.rel, self.line, self.subject, self.detail = pattern, rel, line, subject, detail
        self.sites = list(sites)

    @property
    def id(self):
        return f"{self.rel}::{self.pattern}::{self.subject}"


class Scanner:
    def __init__(self):
        self.hits = []
        self.shapes = collections.defaultdict(list)  # frozenset(keys) -> [(rel, line)]
        self.key_reads = collections.Counter()  # str key -> reads via ["k"] / .get("k")
        self.ipc_sites = []  # (kind, key node, op, rel), resolved after all files are read
        self.str_consts = collections.defaultdict(dict)  # rel -> {NAME: "value"}
        self.match_count = 0

    def add(self, pattern, rel, line, subject, detail):
        self.hits.append(Hit(pattern, rel, line, subject, detail))

    def scan_source(self, rel, source):
        tree = ast.parse(source)
        own, enclosing = qualnames(tree)
        classes = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
        self.scan_registry(rel, tree, classes)
        seen_ifs = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self.scan_class(rel, node, own[id(node)])
            elif isinstance(node, FUNCTION_NODES):
                self.scan_function(rel, node, own[id(node)])
            elif isinstance(node, ast.If) and id(node) not in seen_ifs:
                self.scan_if_chain(rel, node, enclosing[id(node)], seen_ifs)
            elif isinstance(node, ast.Dict):
                keys = [k.value for k in node.keys if str_const(k)]
                if len(keys) == len(node.keys) >= MIN_DICT_KEYS:
                    self.shapes[frozenset(keys)].append((rel, node.lineno))
            elif isinstance(node, ast.Subscript) and str_const(node.slice):
                self.key_reads[node.slice.value] += 1
            elif isinstance(node, ast.Call):
                self.scan_call(rel, node)
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                    and str_const(node.value):
                self.str_consts[rel][node.targets[0].id] = node.value.value
            elif isinstance(node, ast.Match):
                self.match_count += 1

    def scan_class(self, rel, cls, qual):
        methods = {n.name: n for n in cls.body if isinstance(n, FUNCTION_NODES)}
        is_dataclass = any(tail_name(d.func if isinstance(d, ast.Call) else d) == "dataclass" for d in cls.decorator_list)
        init = methods.get("__init__")
        if init and not cls.bases and not is_dataclass:
            stmts = body_without_docstring(init.body)
            fields, plain = 0, bool(stmts)
            for stmt in stmts:
                if isinstance(stmt, ast.Assign) and all(
                        is_self_attr(t) or isinstance(t, ast.Tuple) and all(map(is_self_attr, t.elts)) for t in stmt.targets):
                    fields += sum(len(t.elts) if isinstance(t, ast.Tuple) else 1 for t in stmt.targets)
                elif isinstance(stmt, ast.AnnAssign) and is_self_attr(stmt.target):
                    fields += 1
                elif not is_super_init(stmt):
                    plain = False
                    break
            dunders = sorted(VALUE_DUNDERS & methods.keys())
            others = [m for m in methods if not (m.startswith("__") and m.endswith("__"))]
            if plain and fields >= 2 and (dunders or len(others) <= 2):
                self.add("value_class", rel, cls.lineno, qual, f"fields={fields} dunders={dunders or '-'} methods={len(others)}")
        compares = sorted(RICH_COMPARE & methods.keys())
        if len(compares) >= 2:
            self.add("ordering", rel, cls.lineno, qual, str(compares))
        for name in methods:
            if name.startswith("get_") and "set_" + name[4:] in methods:
                self.add("property_pair", rel, methods[name].lineno, f"{qual}.{name}", f"with set_{name[4:]}")
        forwards = collections.defaultdict(list)
        for name, fn in methods.items():
            stmts = body_without_docstring(fn.body)
            if len(stmts) != 1 or not isinstance(stmts[0], (ast.Return, ast.Expr)) or stmts[0].value is None:
                continue
            value = stmts[0].value
            if isinstance(value, ast.Call):
                value = value.func
            if isinstance(value, ast.Attribute) and is_self_attr(value.value):
                forwards[value.value.attr].append(name)
        for inner, names in forwards.items():
            if len(names) >= 3:
                self.add("delegation", rel, cls.lineno, f"{qual}->{inner}", f"{len(names)} ({', '.join(sorted(names)[:6])})")

    def scan_registry(self, rel, tree, classes):
        fills = collections.defaultdict(list)
        for stmt in tree.body:
            if not isinstance(stmt, ast.Assign):
                continue
            target = stmt.targets[0]
            if isinstance(stmt.value, ast.Dict):
                count = sum(isinstance(v, ast.Name) and v.id in classes for v in stmt.value.values)
                if count >= 3:
                    self.add("registry", rel, stmt.lineno, ast.unparse(target), f"dict of {count} classes")
            elif isinstance(target, ast.Subscript) and isinstance(stmt.value, ast.Name) and stmt.value.id in classes:
                fills[ast.unparse(target.value)].append(stmt.lineno)
        for name, lines in fills.items():
            if len(lines) >= 3:
                self.add("registry", rel, lines[0], name, f"[...] = <class> x{len(lines)}")

    def scan_function(self, rel, fn, qual):
        lengths = []
        indices = collections.defaultdict(set)
        stack = list(ast.iter_child_nodes(fn))
        while stack:
            node = stack.pop()
            if isinstance(node, FUNCTION_NODES + (ast.Lambda, ast.ClassDef)):
                continue  # nested scopes report on their own
            stack.extend(ast.iter_child_nodes(node))
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple) and len(node.value.elts) >= 3:
                lengths.append(len(node.value.elts))
            elif isinstance(node, ast.Subscript) and isinstance(node.value, (ast.Name, ast.Attribute)) \
                    and isinstance(node.slice, ast.Constant) and type(node.slice.value) is int:
                indices[ast.unparse(node.value)].add(node.slice.value)
        if lengths and not SORT_KEY_NAME.search(fn.name):
            self.add("tuple_return", rel, fn.lineno, qual, f"{len(lengths)}x tuple len {max(lengths)}")
        for name, used in indices.items():
            if len(used) >= 3:
                self.add("tuple_index", rel, fn.lineno, f"{qual}:{name}", f"{name}[{','.join(map(str, sorted(used)))}]")

    @staticmethod
    def chain_subject(test):
        if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], (ast.Eq, ast.In, ast.Is)):
            return ast.unparse(test.left)
        if isinstance(test, ast.Call) and isinstance(test.func, ast.Name) and test.func.id == "isinstance" and test.args:
            return "isinstance:" + ast.unparse(test.args[0])
        return None

    def scan_if_chain(self, rel, node, scope, seen_ifs):
        subjects = []
        current = node
        while True:
            seen_ifs.add(id(current))
            subjects.append(self.chain_subject(current.test))
            if len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
                current = current.orelse[0]
            else:
                break
        best, best_subject, run, prev = 0, None, 0, None
        for subject in subjects:
            run = run + 1 if subject is not None and subject == prev else (1 if subject else 0)
            prev = subject
            if run > best:
                best, best_subject = run, subject
        if best >= MIN_CHAIN:
            self.add("elif_chain", rel, node.lineno, f"{scope}:{best_subject}", f"{best} branches on {best_subject}")

    def scan_call(self, rel, node):
        func = node.func
        if not isinstance(func, ast.Attribute) or not node.args:
            return
        if func.attr == "get" and str_const(node.args[0]):
            self.key_reads[node.args[0].value] += 1
        receiver = tail_name(func.value)
        if "archive" in receiver and func.attr in ARCHIVE_OPS:
            self.ipc_sites.append(("archive", node.args[0], func.attr, rel))
        elif receiver == "comms" and func.attr in COMMS_OPS:
            self.ipc_sites.append(("comms", node.args[0], func.attr, rel))

    def finish(self):
        """Add the cross-file hits: dict shapes and ipc keys."""
        for keys, sites in self.shapes.items():
            if len(sites) >= 2 or len(keys) >= 4:
                files = {r for r, _ in sites}
                reads = sum(self.key_reads[k] for k in keys)
                subject = ",".join(sorted(keys))
                self.hits.append(Hit("dict_shape", "*", 0, subject,
                                     f"{len(sites)} sites, {len(files)} files, key reads {reads}", sites))
        by_name = collections.defaultdict(set)
        for consts in self.str_consts.values():
            for name, value in consts.items():
                by_name[name].add(value)
        ops = collections.defaultdict(lambda: collections.defaultdict(set))
        for kind, node, op, rel in self.ipc_sites:
            if str_const(node):
                key = repr(node.value)
            else:
                name = tail_name(node)
                value = self.str_consts[rel].get(name)
                if value is None and len(by_name[name]) == 1:
                    value = next(iter(by_name[name]))
                key = repr(value) if value is not None else ast.unparse(node) + " (?)"
            ops[(kind, key)][op].add(rel)
        for (kind, key), per_op in ops.items():
            files = sorted(set().union(*per_op.values()))
            op_text = ", ".join(f"{op} {len(r)}" for op, r in sorted(per_op.items()))
            self.hits.append(Hit("ipc_key", "*", 0, f"{kind}:{key}", f"{len(files)} files ({op_text})",
                                 [(r, 0) for r in files]))


def scan(files):
    scanner = Scanner()
    for rel, (path, _tier) in sorted(files.items()):
        with open(path, encoding="utf-8") as f:
            source = f.read()
        try:
            scanner.scan_source(rel, source)
        except SyntaxError as error:
            print(f"skip {rel}: {error}", file=sys.stderr)
    scanner.finish()
    return scanner


def sort_key(hit):
    if hit.sites:  # cross-file: most sites first
        return (-len({r for r, _ in hit.sites}), -len(hit.sites), hit.subject)
    return (0, 0, hit.rel, hit.line)


def report(scanner, hits, patterns, summary, ignored_count):
    by_pattern = collections.defaultdict(list)
    for hit in hits:
        by_pattern[hit.pattern].append(hit)
    out = ["# Feature scan\n", "| pattern | hits |", "|---|---|"]
    out += [f"| {p} | {len(by_pattern[p])} |" for p in PATTERNS if p in patterns]
    out.append(f"\nIgnored by {os.path.basename(IGNORE_FILE)}: {ignored_count}. Existing `match` statements: {scanner.match_count}.")
    if summary:
        return "\n".join(out)
    for pattern in PATTERNS:
        if pattern not in patterns:
            continue
        out.append(f"\n## {pattern} ({len(by_pattern[pattern])})\n")
        for hit in sorted(by_pattern[pattern], key=sort_key):
            if hit.sites:
                out.append(f"- `{hit.id}`: {hit.detail}")
                shown = [f"{r}:{line}" if line else r for r, line in hit.sites[:8]]
                more = f" +{len(hit.sites) - 8}" if len(hit.sites) > 8 else ""
                out.append(f"  - {', '.join(shown)}{more}")
            else:
                out.append(f"- {hit.rel}:{hit.line} `{hit.id}`: {hit.detail}")
    return "\n".join(out)


def add_arguments(parser):
    parser.add_argument("-p", "--pattern", action="append", choices=PATTERNS, help="limit to these patterns (repeatable)")
    parser.add_argument("--summary", action="store_true", help="counts only")
    parser.add_argument("--all", action="store_true", help="include hits listed in the ignore file")
    parser.add_argument("--out", help="write the report to this file")


def run(args):
    files = scanned_files()
    scanner = scan(files)
    ignored = set() if args.all else set(ignore_lines(IGNORE_FILE))
    patterns = set(args.pattern or PATTERNS)
    hits = [h for h in scanner.hits if h.pattern in patterns]
    kept = [h for h in hits if h.id not in ignored]
    text = report(scanner, kept, patterns, args.summary, len(hits) - len(kept))
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
