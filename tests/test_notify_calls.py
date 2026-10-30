"""Every notify() call in scripts/ and autoplay/ passes arguments the game accepts. The game's notify builtin
raises on a bad level, a non-number duration or a non-bool dismissible, and our calls carry no guard, so one
bad toast would crash the calling script (docs/guide/builtins_and_commands.md notify)."""

import ast
import glob
import os
import unittest

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LEVELS = {"info", "warn", "error"}
KEYWORDS = {"level", "duration_seconds", "dismissible"}


def _literal_levels(node):
    """The string literals an argument can take, or None when it is not built from literals."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        body, orelse = _literal_levels(node.body), _literal_levels(node.orelse)
        return None if body is None or orelse is None else body | orelse
    return None


def _problems(call):
    args = dict(zip(("text", "level", "duration_seconds", "dismissible"), call.args))
    for kw in call.keywords:
        if kw.arg not in KEYWORDS:
            yield f"unknown keyword {kw.arg}"
        args[kw.arg] = kw.value
    if len(call.args) > 4:
        yield "more than 4 positional arguments"
    if "level" in args:
        levels = _literal_levels(args["level"])
        if levels is None or not levels <= LEVELS:
            yield f"level {ast.unparse(args['level'])}"
    duration = args.get("duration_seconds")
    if isinstance(duration, ast.Constant) and (
        isinstance(duration.value, bool) or not isinstance(duration.value, (int, float))
    ):
        yield f"duration_seconds {duration.value!r}"
    dismissible = args.get("dismissible")
    if isinstance(dismissible, ast.Constant) and not isinstance(dismissible.value, bool):
        yield f"dismissible {dismissible.value!r}"


class NotifyCallTests(unittest.TestCase):
    def test_every_notify_call_passes_game_accepted_arguments(self):
        paths = glob.glob(os.path.join(REPO, "scripts", "**", "*.py"), recursive=True)
        paths += glob.glob(os.path.join(REPO, "autoplay", "**", "*.py"), recursive=True)
        bad, seen = [], 0
        for path in sorted(paths):
            with open(path, encoding="utf-8") as f:
                source = f.read()
            if "notify(" not in source:
                continue
            for node in ast.walk(ast.parse(source, path)):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "notify":
                    seen += 1
                    bad += [f"{os.path.relpath(path, REPO)}:{node.lineno}: {p}" for p in _problems(node)]
        self.assertGreater(seen, 0)
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
