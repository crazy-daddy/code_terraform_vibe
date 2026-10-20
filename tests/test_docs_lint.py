"""Docs lint: links in the navigated docs resolve, the AI_CHEATSHEET.md section index and code § citations
point at real headings, cheatsheet ids are unique, and docs agents read stay under the size limits."""

import importlib.util
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
CHEATSHEET = DOCS / "cheatsheet"

_spec = importlib.util.spec_from_file_location("docs_section", REPO / "devtools" / "docs_section.py")
assert _spec and _spec.loader
ds = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ds  # dataclass needs its module registered
_spec.loader.exec_module(ds)

# Docs agents navigate by link. Plans and the TODO archives are working notes and stay unchecked.
NAVIGATED = [
    REPO / "CLAUDE.md",
    REPO / "CODE_GUIDES.md",
    REPO / "TODO.md",
    *sorted(DOCS.glob("*.md")),
    *sorted(CHEATSHEET.glob("*.md")),
    *sorted((DOCS / "gameknowledge").rglob("*.md")),
    *sorted((DOCS / "headless").rglob("*.md")),
]
# Docs agents read in slices (CLAUDE.md "Keep context small"). Game reference docs are excluded.
SIZED = [
    REPO / "CLAUDE.md",
    REPO / "CODE_GUIDES.md",
    REPO / "TODO.md",
    DOCS / "AI_CHEATSHEET.md",
    DOCS / "DESIGN_HISTORY.md",
    *sorted(CHEATSHEET.glob("*.md")),
]
FILE_LIMIT_KB = 64
SECTION_LIMIT_KB = 16  # one heading's own text, subsections excluded
# Submodules that a fresh clone may not have checked out.
SUBMODULE_PREFIXES = ("inspirations/", "internals/", "devtools/mcp/code-terraform-mcp/")

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CODE_SPAN_RE = re.compile(r"`[^`]*`")
CITE_RE = re.compile(r"§(\d+[a-z]?(?:-[0-9a-z]+)*)")
INDEX_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|[^|]*\|\s*\[[^\]]*\]\(([^)]+)\)\s*\|$")
CITING_TREES = ("scripts", "autoplay", "devtools", "tests")


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n")


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def _prose_lines(lines: list[str]):
    """(1-based number, line) outside fenced code blocks, inline code spans removed."""
    fence = None
    for n, line in enumerate(lines, 1):
        if m := ds.FENCE_RE.match(line):
            if fence is None:
                fence = m.group(1)
            elif m.group(1).startswith(fence) and not m.group(2).strip():
                fence = None
            continue
        if fence is None:
            yield n, CODE_SPAN_RE.sub("", line)


def _heading_ids(path: Path) -> list[str]:
    return [sid for h in ds.headings(_lines(path)) for sid in ds.heading_ids(h.text)]


def _size_kb(lines: list[str]) -> float:
    return sum(len(s.encode("utf-8")) + 1 for s in lines) / 1024


class DocsLinkTests(unittest.TestCase):
    longMessage = False

    def test_relative_links_resolve(self):
        for path in NAVIGATED:
            with self.subTest(doc=_rel(path)):
                broken = []
                for n, line in _prose_lines(_lines(path)):
                    for target in LINK_RE.findall(line):
                        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
                            continue
                        dest = (path.parent / target.split("#")[0]).resolve()
                        if dest.is_relative_to(REPO) and _rel(dest).startswith(SUBMODULE_PREFIXES):
                            continue
                        if not dest.exists():
                            broken.append(f"{_rel(path)}:{n} {target}")
                self.assertFalse(broken, "\n" + "\n".join(broken))


class SectionIdTests(unittest.TestCase):
    longMessage = False

    def test_cheatsheet_ids_unique(self):
        seen: dict[str, str] = {}
        dupes = []
        for path in sorted(CHEATSHEET.glob("*.md")):
            for sid in _heading_ids(path):
                if sid in seen:
                    dupes.append(f"§{sid}: {seen[sid]} and {path.name}")
                seen.setdefault(sid, path.name)
        self.assertFalse(dupes, "\n" + "\n".join(dupes))

    def test_index_ids_exist_in_named_file(self):
        missing = []
        for line in _lines(DOCS / "AI_CHEATSHEET.md"):
            if not (m := INDEX_ROW_RE.match(line)):
                continue
            target = DOCS / m.group(2)
            if target.parent != CHEATSHEET:
                continue
            ids = set(_heading_ids(target))
            # Cells list ids and ranges: "2a-0 … 2a-3", "1e–1h-1"; both range ends must exist.
            for token in re.split(r"[,…–]", m.group(1)):
                token = token.strip()
                if token and token != "—" and token not in ids:
                    missing.append(f"§{token} not a heading in {target.name}")
        self.assertFalse(missing, "\n" + "\n".join(missing))

    def test_code_citations_resolve(self):
        known = {sid for p in CHEATSHEET.glob("*.md") for sid in _heading_ids(p)}
        known |= set(_heading_ids(DOCS / "DESIGN_HISTORY.md"))
        missing = []
        for tree in CITING_TREES:
            for path in sorted((REPO / tree).rglob("*.py")):
                for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    missing.extend(
                        f"{_rel(path)}:{n} §{m.group(1)}" for m in CITE_RE.finditer(line) if m.group(1) not in known
                    )
        self.assertFalse(missing, "\n" + "\n".join(missing))


class DocsSizeTests(unittest.TestCase):
    longMessage = False

    def test_file_size(self):
        for path in SIZED:
            with self.subTest(doc=_rel(path)):
                size = _size_kb(_lines(path))
                self.assertLessEqual(
                    size, FILE_LIMIT_KB, f"{_rel(path)} is {size:.0f} KB, limit {FILE_LIMIT_KB} KB; split it by section"
                )

    def test_section_size(self):
        for path in SIZED:
            lines = _lines(path)
            heads = ds.headings(lines)
            big = []
            for h in heads:
                size = _size_kb(lines[h.line : ds.section_end(heads, h, len(lines), no_sub=True)])
                if size > SECTION_LIMIT_KB:
                    big.append(f"{_rel(path)}:{h.line + 1} {size:.0f} KB {h.text[:60]}")
            with self.subTest(doc=_rel(path)):
                self.assertFalse(big, "\n" + "\n".join(big))


if __name__ == "__main__":
    unittest.main()
