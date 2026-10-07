"""
Syntax that CPython accepts but the game parser rejects.

Backslash line continuation: the game raises "SyntaxError: line continuation
with '\\' is not supported" at load. A backslash at line end inside a
multi-line string or a comment is fine.
"""
import io
import os
import tokenize
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
AUTOPLAY_DIR = os.path.join(REPO_ROOT, "autoplay")
STRING_TYPES = {tokenize.STRING} | {getattr(tokenize, n) for n in ("FSTRING_START", "FSTRING_MIDDLE",
                                                                     "FSTRING_END") if hasattr(tokenize, n)}


def backslash_continuations(source):
    """Line numbers (1-based) that end in a backslash continuation."""
    in_string = set()
    comment_lines = set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in STRING_TYPES:
            in_string.update(range(tok.start[0], tok.end[0]))
        elif tok.type == tokenize.COMMENT:
            comment_lines.add(tok.start[0])
    return [n for n, line in enumerate(source.splitlines(), 1)
            if line.rstrip().endswith("\\") and n not in in_string and n not in comment_lines]


class GameSyntaxTests(unittest.TestCase):
    def test_detector(self):
        self.assertEqual(backslash_continuations("x = 1 + \\\n    2\n"), [1])
        self.assertEqual(backslash_continuations('s = """a \\\nb"""\n# c \\\ny = (1 +\n     2)\n'), [])

    def test_no_backslash_continuation(self):
        bad = []
        for root, _dirs, files in [w for top in (SCRIPTS_DIR, AUTOPLAY_DIR) for w in os.walk(top)]:
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as handle:
                    source = handle.read()
                bad += [f"{os.path.relpath(path, REPO_ROOT)}:{n}" for n in backslash_continuations(source)]
        self.assertEqual(bad, [], "\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
