"""Refresh the split docs under docs/ from a new monolithic DOCS Manual export.

Usage:
    python devtools/split_docs_manual.py [docs/Code-Terraform-DOCS-Manual-<build>.md]

The in-game DOCS export is one big Markdown file (gitignored). Its "## Contents"
block lists every section as "<Group>" + "Category / Title", and each section
body starts with a "## Title" heading in the same order. The split files under
docs/{components,database,types,contracts,guide}/ are just those sections with a
small header, so existing files act as the mapping template:

- components/, database/: one section each, identified by the header's
  "Component Name:"/"Section:" value; the "## Title" line is dropped.
- types/, contracts/, guide/: one or more "## Title" sections verbatim;
  types/ files also get a regenerated "## Index".

Sections the template doesn't claim are routed by NEW_SECTION_RULES (or, for
Types, to the types/ file already holding most of the same category) and every
routing decision is printed, so a new build's additions are visible.

docs/models/ is not in the manual: it holds one "## `Class`" + python block per
public class of the game's __builtins__.pyi stub (STUBS, refreshed by the
editor integration on each game update). Existing files keep their classes;
a new class goes to the file whose classes mention it most (else misc_models).
"""
from __future__ import annotations

import difflib
import glob
import os
import re
import sys
from collections import Counter

DOCS = "docs"
STUBS = os.path.join(".pyright-resolved", "stubs", "__builtins__.pyi")
MODULE_SUFFIX = re.compile(r" \*\(.*\)\*$")  # "Nav Module *(MODULE)*"

# Which manual TOC groups each folder may draw sections from.
GROUPS = {
    "components": {"Components"},
    "database": {"Database"},
    "types": {"Types"},
    "contracts": {"Types", "Guide"},
    "guide": {"Guide", "Commands", "Built-in Functions", "Built-in Modules", "Language"},
}

# Files whose "## Title" sections must come from these manual paths only
# (titles like "Contracts" or "Variables" appear under several TOC paths).
PINNED_PATHS = {
    "guide/programming_language_reference.md": ("Guide", "Programming / "),
    "guide/contracts_tutorial.md": ("Guide", "Tutorials / "),
    "guide/language_reference.md": ("Language", ""),
}

# Unclaimed sections: (group, path-prefix) -> (file, header title for new files).
NEW_SECTION_RULES = [
    ("Guide", "Start Here / Frequently Asked Questions", "guide/faq.md"),
    ("Guide", "Programming / ", "guide/programming_language_reference.md"),
    ("Guide", "Automation Systems / Map Markers", "guide/map_markers_guide.md"),
    ("Guide", "World & Infrastructure / Weather System", "guide/weather_system.md"),
    ("Guide", "Reference / Components", "guide/components_overview.md"),
    ("Language", "", "guide/language_reference.md"),
    ("Built-in Functions", "", "guide/builtins_and_commands.md"),
    ("Built-in Modules", "", "guide/builtins_and_commands.md"),
    ("Commands", "", "guide/builtins_and_commands.md"),
    ("Types", "Built-in Modules / ", "types/built_in_types.md"),
]


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r", "")


def load_manual(path: str) -> tuple[str, list[dict]]:
    lines = read(path).split("\n")
    build = next((l.split()[-1] for l in lines[:10] if l.startswith("Build ")), "?")
    toc: list[tuple[str, str]] = []
    group = ""
    start = 0
    for i, line in enumerate(lines[7:], 7):
        if line.startswith("## "):
            start = i
            break
        if line.startswith("**") and line.endswith("**"):
            group = line.strip("*")
        elif line.startswith("- "):
            toc.append((group, line[2:]))
    sections: list[dict] = []
    ti = 0
    for line in lines[start:]:
        if line.startswith("## "):
            title = line[3:]
            if ti < len(toc):
                leaf = toc[ti][1]
                bare = MODULE_SUFFIX.sub("", title)
                if leaf == title or leaf.endswith(" / " + title) or leaf.endswith(" / " + bare):
                    sections.append({"title": title, "group": toc[ti][0], "path": leaf,
                                     "idx": ti, "lines": [line]})
                    ti += 1
                    continue
            sections[-1]["lines"].append(line)  # a "##" nested inside a section body
        elif sections:
            sections[-1]["lines"].append(line)
    if ti != len(toc):
        sys.exit(f"TOC/section alignment failed at TOC entry {ti}: {toc[ti]}")
    for s in sections:
        while s["lines"] and not s["lines"][-1].strip():
            s["lines"].pop()
    return build, sections


def split_file(path: str) -> tuple[list[str], list[dict]]:
    pre: list[str] = []
    parts: list[dict] = []
    for line in read(path).split("\n"):
        if line.startswith("## "):
            parts.append({"title": line[3:], "lines": [line]})
        elif parts:
            parts[-1]["lines"].append(line)
        else:
            pre.append(line)
    return pre, parts


def write(rel: str, text: str) -> None:
    with open(os.path.join(DOCS, rel), "w", encoding="utf-8", newline="\r\n") as fh:  # match the CRLF working copy
        fh.write(text.rstrip("\n") + "\n")


def stub_classes(path: str) -> dict[str, str]:
    """Top-level public class name -> its full source block from a .pyi stub."""
    classes: dict[str, str] = {}
    name = None
    block: list[str] = []
    for line in read(path).split("\n") + ["<eof>"]:
        if line and not line[0].isspace() and not line.startswith(")"):
            if name:
                classes[name] = "\n".join(block).rstrip()
            m = re.match(r"class (\w+)", line)
            name = m.group(1) if m and not m.group(1).startswith("_") else None
            block = [line]
        elif name:
            block.append(line)
    return classes


def refresh_models(stubs: str) -> None:
    source = stub_classes(stubs)
    files: dict[str, dict] = {}  # rel -> {"pre": header lines, "names": [class]}
    owner: dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(DOCS, "models", "*.md"))):
        rel = os.path.relpath(path, DOCS).replace("\\", "/")
        pre, parts = split_file(path)
        while pre and not pre[-1].strip():
            pre.pop()
        files[rel] = {"pre": pre, "names": []}
        for part in parts:
            n = part["title"].strip("`")
            if n in source:
                files[rel]["names"].append(n)
                owner[n] = rel
            else:
                print(f"  DROPPED  {rel}: class {n} no longer in stubs")
    for n in sorted(set(source) - set(owner)):
        pattern = re.compile(rf"\b{n}\b")
        votes = Counter({rel: sum(len(pattern.findall(source[c])) for c in f["names"])
                         for rel, f in files.items()})
        rel, hits = votes.most_common(1)[0]
        rel = rel if hits else "models/misc_models.md"
        files[rel]["names"].append(n)
        print(f"  ADDED    class {n} -> {rel}")
    for rel, f in files.items():
        chunks = ["\n".join(f["pre"])]
        chunks += [f"## `{n}`\n\n```python\n{source[n]}\n```" for n in sorted(f["names"])]
        write(rel, "\n\n".join(chunks))
    print(f"Wrote {len(files)} model files from {stubs} ({len(source)} classes).")


def best_match(old: str, cands: list[dict]) -> dict | None:
    if not cands:
        return None
    return max(cands, key=lambda s: difflib.SequenceMatcher(None, old, "\n".join(s["lines"])).ratio())


def main() -> None:
    manual = sys.argv[1] if len(sys.argv) > 1 else sorted(
        glob.glob(os.path.join(DOCS, "Code-Terraform-DOCS-Manual*.md")), key=os.path.getmtime)[-1]
    build, sections = load_manual(manual)
    print(f"Manual {manual}: build {build}, {len(sections)} sections")

    files: dict[str, dict] = {}  # rel path -> {"kind", "pre", "secs"}
    claimed: set[int] = set()
    for folder, groups in GROUPS.items():
        pool = [s for s in sections if s["group"] in groups]
        for path in sorted(glob.glob(os.path.join(DOCS, folder, "*.md"))):
            rel = os.path.relpath(path, DOCS).replace("\\", "/")
            pre, parts = split_file(path)
            secs: list[dict] = []
            if folder in ("components", "database"):
                name = next(l for l in pre if l.startswith("> ")).split(":** ")[-1].strip()
                cands = [s for s in pool if MODULE_SUFFIX.sub("", s["title"]) == name]
                m = best_match("\n".join(pre[3:]), cands)
                if m:
                    secs.append(m)
                pre = pre[:3]
            else:
                if rel in PINNED_PATHS:
                    group, prefix = PINNED_PATHS[rel]
                    cands_pool = [s for s in pool if s["group"] == group and s["path"].startswith(prefix)]
                elif folder == "guide":
                    cands_pool = [s for s in pool if s["group"] == "Guide"
                                  or rel == "guide/builtins_and_commands.md"]
                else:
                    cands_pool = pool
                for part in parts:
                    if part["title"] == "Index":
                        continue
                    cands = [s for s in cands_pool if s["title"] == part["title"]]
                    m = best_match("\n".join(part["lines"]), cands)
                    if m is None and any(part["lines"][0] in s["lines"] for s in secs):
                        continue  # a "##" nested inside the previous section's body
                    if m is None:
                        print(f"  DROPPED  {rel}: '{part['title']}' no longer in manual")
                    elif m["idx"] not in {s["idx"] for s in secs}:
                        secs.append(m)
                while pre and not pre[-1].strip():
                    pre.pop()
                if folder == "types":
                    pre = pre[:3]  # title + description; Index is regenerated
            if not secs:
                print(f"  EMPTY    {rel}: nothing matched, left untouched")
                continue
            claimed.update(s["idx"] for s in secs)
            files[rel] = {"kind": folder, "pre": pre, "secs": secs}

    for s in sections:
        if s["idx"] in claimed:
            continue
        target = next((f for g, prefix, f in NEW_SECTION_RULES
                       if s["group"] == g and s["path"].startswith(prefix)), None)
        if target is None and s["group"] == "Types":
            cat = s["path"].split(" / ")[0]
            votes = Counter(rel for rel, f in files.items() if f["kind"] == "types"
                            for x in f["secs"] if x["path"].split(" / ")[0] == cat)
            target = votes.most_common(1)[0][0] if votes else None
        if target is None:
            print(f"  UNROUTED {s['group']} | {s['path']}")
            continue
        if target not in files:
            stem = os.path.splitext(os.path.basename(target))[0]
            files[target] = {"kind": target.split("/")[0], "pre": [f"# Guide: {stem}"], "secs": []}
            print(f"  NEW FILE {target}")
        files[target]["secs"].append(s)
        claimed.add(s["idx"])
        print(f"  ADDED    {s['group']} | {s['path']} -> {target}")

    for rel, f in sorted(files.items()):
        secs = sorted(f["secs"], key=lambda s: s["idx"])
        if f["kind"] in ("components", "database"):
            body = "\n".join(secs[0]["lines"][1:]).strip("\n")
            out = "\n".join(f["pre"]) + "\n\n" + body
        else:
            chunks = ["\n".join(f["pre"])]
            if f["kind"] == "types":
                idx = [f"- [`{s['title']}`](#{re.sub(r'[^a-z0-9 -]', '', s['title'].lower()).replace(' ', '-')})"
                       f" ({s['path'].split(' / ')[0].upper()})" for s in secs]
                chunks.append("## Index\n\n" + "\n".join(idx) + "\n\n---")
            chunks += ["\n".join(s["lines"]) for s in secs]
            out = "\n\n".join(chunks)
        write(rel, out)
    print(f"Wrote {len(files)} files.")

    if os.path.exists(STUBS):
        refresh_models(STUBS)
    else:
        print(f"  SKIPPED  models/: {STUBS} not found")


if __name__ == "__main__":
    main()
