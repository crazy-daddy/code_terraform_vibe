"""Every `log.start()` block is closed on every path: a `return`, `raise`, `break`, `continue` or the end of
a function must not leave a TreeConsole indent open (lib/tree_console.py), or every later line in the
script is indented one level deeper. `start()`/`end()` calls are matched by receiver name (`log`, `self.log`,
`self._host.log`, ...); a block may be opened and closed in different branches as long as both branches
leave the same depth."""
import ast
import glob
import os
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")


def is_log_call(node, method):
    """True for `<...>.log.<method>(...)` / `log.<method>(...)`."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == method):
        return False
    owner = node.func.value
    name = owner.id if isinstance(owner, ast.Name) else owner.attr if isinstance(owner, ast.Attribute) else ""
    return name in ("log", "_log")


def own_calls(stmt):
    """Log start/end calls made by this statement itself, not by its nested blocks or defs."""
    nested = ("body", "orelse", "finalbody", "handlers")
    stack = [child for field, value in ast.iter_fields(stmt) if field not in nested
             for child in (value if isinstance(value, list) else [value]) if isinstance(child, ast.AST)]
    calls = []
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if is_log_call(node, "start"):
            calls.append((node.lineno, 1))
        elif is_log_call(node, "end"):
            calls.append((node.lineno, -1))
        stack.extend(ast.iter_child_nodes(node))
    return sorted(calls)


class Walker:
    def __init__(self):
        self.problems = []

    def block(self, stmts, depth, loop_base=None):
        """Walk a statement list; returns depth after it, or None if every path leaves the block."""
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for lineno, delta in own_calls(stmt):
                depth += delta
                if depth < 0:
                    self.problems.append((lineno, "end() without a matching start()"))
                    depth = 0
            if isinstance(stmt, (ast.Return, ast.Raise)):
                # `raise` unwinds into the caller's handler; only returns must be balanced.
                if isinstance(stmt, ast.Return) and depth > 0:
                    self.problems.append((stmt.lineno, "return inside an open log block"))
                return None
            if isinstance(stmt, (ast.Break, ast.Continue)):
                if loop_base is not None and depth != loop_base:
                    self.problems.append((stmt.lineno, "break/continue inside a log block opened in the loop"))
                return None
            if isinstance(stmt, ast.If):
                a = self.block(stmt.body, depth, loop_base)
                b = self.block(stmt.orelse, depth, loop_base) if stmt.orelse else depth
                outcomes = [d for d in (a, b) if d is not None]
                if not outcomes:
                    return None
                if len(set(outcomes)) > 1:
                    self.problems.append((stmt.lineno, "if/else branches leave different log depths"))
                depth = outcomes[0]
            elif isinstance(stmt, (ast.For, ast.While)):
                after = self.block(stmt.body, depth, depth)
                if after is not None and after != depth:
                    self.problems.append((stmt.lineno, "loop body opens or closes a log block per iteration"))
                if stmt.orelse:
                    self.block(stmt.orelse, depth, loop_base)
            elif isinstance(stmt, ast.Try):
                inner = self.block(stmt.body, depth, loop_base)
                results = [inner if inner is not None else depth]
                for handler in stmt.handlers:
                    h = self.block(handler.body, depth, loop_base)
                    if h is not None:
                        results.append(h)
                if stmt.orelse and inner is not None:
                    inner = self.block(stmt.orelse, inner, loop_base)
                    results[0] = inner if inner is not None else depth
                if stmt.finalbody:
                    self.block(stmt.finalbody, results[0], loop_base)
                if len(set(results)) > 1:
                    self.problems.append((stmt.lineno, "try body and except handlers leave different log depths"))
                depth = results[0]
            elif isinstance(stmt, ast.With):
                d = self.block(stmt.body, depth, loop_base)
                if d is None:
                    return None
                depth = d
        return depth


def check_source(source):
    problems = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            walker = Walker()
            final = walker.block(node.body, 0)
            if final:
                walker.problems.append((node.lineno, f"{node.name}() ends with {final} log block(s) still open"))
            problems.extend((lineno, f"{node.name}(): {message}") for lineno, message in walker.problems)
    return sorted(set(problems))


class CheckerSelfTests(unittest.TestCase):
    def test_flags_return_inside_block(self):
        src = "def f(self):\n    self.log.start('a')\n    if x:\n        return\n    self.log.end('b')\n"
        self.assertEqual(len(check_source(src)), 1)

    def test_accepts_end_on_each_path(self):
        src = ("def f(self):\n    self.log.start('a')\n    if x:\n        self.log.end('n')\n        return\n"
               "    self.log.end('b')\n")
        self.assertEqual(check_source(src), [])

    def test_flags_missing_end(self):
        self.assertEqual(len(check_source("def f(self):\n    log.start('a')\n")), 1)

    def test_flags_loop_that_leaks(self):
        src = "def f(self):\n    for i in x:\n        log.start('a')\n"
        self.assertTrue(check_source(src))

    def test_accepts_balanced_loop(self):
        src = "def f(self):\n    for i in x:\n        log.start('a')\n        log.end('b')\n"
        self.assertEqual(check_source(src), [])


class LogBlocksBalancedTests(unittest.TestCase):
    def test_every_start_is_closed_on_every_path(self):
        problems = []
        for path in sorted(glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True)):
            if path.endswith("tree_console.py"):
                continue
            with open(path) as handle:
                source = handle.read()
            for lineno, message in check_source(source):
                problems.append(f"{os.path.relpath(path, ROOT)}:{lineno}: {message}")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
