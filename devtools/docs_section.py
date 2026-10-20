#!/usr/bin/env python
"""Prints one Markdown section of the docs, so a reader never loads a large doc whole.

A section runs from its heading to the next heading of the same or a higher level,
so it includes its subsections. Headings inside fenced code blocks don't count.

KEY is a cheatsheet section id (`§2c` or `2c`) or else a case-insensitive heading
substring. An id matches only a heading that starts with it, so `2a-0` never picks
`§2a-0-1`. Without --file, the search covers every *.md under docs/ plus the repo
root; an id search covers docs/cheatsheet/ first.

Examples:
  python devtools/docs_section.py 2c
  python devtools/docs_section.py "§2a-0-5" --no-sub
  python devtools/docs_section.py "Supply Dock" --file docs/cheatsheet/production_logistics.md
  python devtools/docs_section.py --outline docs/cheatsheet/vehicles_drones.md
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
CHEATSHEET = DOCS / "cheatsheet"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
ID_KEY_RE = re.compile(r"^§?(\d+[a-z]?(?:-[0-9a-z]+)*)$")


@dataclass(frozen=True)
class Heading:
    line: int  # 0-based index into the file's lines
    level: int
    text: str


def headings(lines: list[str]) -> list[Heading]:
    found: list[Heading] = []
    fence: str | None = None
    for i, line in enumerate(lines):
        if m := FENCE_RE.match(line):
            if fence is None:
                fence = m.group(1)
            elif m.group(1) == fence:
                fence = None
            continue
        if fence is None and (m := HEADING_RE.match(line)):
            found.append(Heading(i, len(m.group(1)), m.group(2)))
    return found


def section_end(heads: list[Heading], start: Heading, total: int, *, no_sub: bool = False) -> int:
    """Line index after the section's last line."""
    for h in heads:
        if h.line > start.line and (h.level <= start.level or no_sub):
            return h.line
    return total


def id_pattern(section_id: str) -> re.Pattern[str]:
    return re.compile(rf"^§{re.escape(section_id)}(?![\w-])")


def find(lines: list[str], key: str) -> list[Heading]:
    heads = headings(lines)
    if m := ID_KEY_RE.match(key):
        pattern = id_pattern(m.group(1))
        return [h for h in heads if pattern.match(h.text)]
    needle = key.casefold()
    return [h for h in heads if needle in h.text.casefold()]


def candidate_files(key: str) -> list[Path]:
    everything = sorted(DOCS.rglob("*.md")) + sorted(REPO.glob("*.md"))
    if ID_KEY_RE.match(key):
        cheats = sorted(CHEATSHEET.glob("*.md"))
        return cheats + [p for p in everything if p not in cheats]
    return everything


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def cmd_outline(path: Path) -> int:
    lines = read_lines(path)
    heads = headings(lines)
    for h in heads:
        size = sum(len(s) + 1 for s in lines[h.line : section_end(heads, h, len(lines))])
        print(f"{h.line + 1:>6} {size / 1024:>6.1f}K {'  ' * (h.level - 1)}{h.text}")
    return 0


def cmd_section(key: str, files: list[Path], *, no_sub: bool, show_all: bool) -> int:
    hits: list[tuple[Path, list[str], Heading]] = []
    for path in files:
        lines = read_lines(path)
        hits.extend((path, lines, h) for h in find(lines, key))
        # An id lives in exactly one place; stop at the first file that has it.
        if hits and ID_KEY_RE.match(key) and not show_all:
            break
    if not hits:
        print(f"no section matches {key!r}", file=sys.stderr)
        return 1
    shown = hits if show_all else hits[:1]
    for path, lines, h in shown:
        end = section_end(headings(lines), h, len(lines), no_sub=no_sub)
        print(f"<!-- {rel(path)}:{h.line + 1}-{end} -->")
        print("\n".join(lines[h.line : end]).rstrip())
    if len(hits) > len(shown):
        print(f"\n<!-- {len(hits) - 1} more match(es), --all shows them: -->")
        for path, _, h in hits[1:]:
            print(f"<!--   {rel(path)}:{h.line + 1} {h.text} -->")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("key", nargs="?", help="section id (§2c / 2c) or heading substring")
    parser.add_argument("--file", type=Path, help="search only this file")
    parser.add_argument("--no-sub", action="store_true", help="stop at the first subheading")
    parser.add_argument("--all", action="store_true", help="print every match, not just the first")
    parser.add_argument("--outline", type=Path, metavar="FILE", help="list FILE's headings with line and section size")
    args = parser.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if args.outline:
        return cmd_outline(args.outline)
    if not args.key:
        parser.error("KEY or --outline is required")
    files = [args.file] if args.file else candidate_files(args.key)
    return cmd_section(args.key, files, no_sub=args.no_sub, show_all=args.all)


if __name__ == "__main__":
    sys.exit(main())
