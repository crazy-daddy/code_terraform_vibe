#!/usr/bin/env python
"""Diff two builds of the decompiled simworker, ignoring minifier renames.

    python devtools/simworker_diff.py                    # previous internals commit vs working file
    python devtools/simworker_diff.py --old REV          # internals revision (or a .js path) as old
    python devtools/simworker_diff.py --old A.js --new B.js
    python devtools/simworker_diff.py --all              # also list editor/tutorial chunks

Finds game changes the changelog doesn't mention. A plain git diff of deobfuscated.js is
mostly noise: the minifier renames every local and top-level binding per build, and code
blocks move. This tool:
  1. tokenizes both files (strings, template literals, regex literals, comments) and
     replaces minified bindings (bare identifiers of <= 3 chars, not property names or
     object keys) with `_`; property names and strings stay, they are stable across builds;
  2. cuts each file into chunks: top-level statements, and members of a statement longer
     than --max-chunk lines (repeated one level down);
  3. pairs old and new chunks by exact normalized text, then by Jaccard similarity of
     their distinctive normalized lines;
  4. diffs each changed pair on normalized lines and prints the original lines.

Report sections: number-only changes (a constant moved: 80 -> 40), code changes, added and
removed code chunks, then text changes (string-dominated chunks: UI text, i18n, docs).
Editor, linter and tutorial chunks are counted but not listed unless --all.

Writes Markdown to devtools/.simworker-diff/<old>_<new>.md (gitignored: it holds
decompiled code, and this repo is public). Needs the private internals/ submodule for the
default sources.
"""
import argparse
import bisect
import difflib
import hashlib
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INTERNALS = REPO_ROOT / "internals"
SIMWORKER_REL = "terraform_decompiled/simworker/deobfuscated.js"
OUT_DIR = REPO_ROOT / "devtools" / ".simworker-diff"

# Short identifiers that are not minifier output.
KEEP_IDENTS = set(
    "if in do for let new try var case else enum null this true void with break catch "
    "class const false super throw while yield delete export import return static switch "
    "typeof default extends finally continue debugger function await async of get set "
    "NaN Map Set Math JSON Date Number String Object Array Symbol Error Promise BigInt "
    "Reflect Proxy console globalThis undefined Infinity arguments".split()
)
# Keywords after which `/` starts a regex literal.
REGEX_AFTER_WORDS = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete",
                     "void", "throw", "instanceof", "yield", "await"}
MINIFIED_MAX_LEN = 3

# Chunk categories hidden by default (matched against the chunk's original text).
NOISE_CATEGORIES = [
    ("editor", re.compile(r"editorlinter\.|monaco|codemirror|languageService|completionItem", re.I)),
    ("tutorial", re.compile(r"\bstarterSource\b|\bhints\s*:|tutorial\.", re.I)),
]
TEXT_SHARE = 0.6           # chunk is "text" when this share of its chars sits in strings
FUZZY_MIN_SCORE = 0.3      # Jaccard threshold for pairing changed chunks
INDEX_MAX_DF = 12          # lines shared by more chunks than this are too common to index

_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<lcom>//[^\n]*)
  | (?P<bcom>/\*.*?\*/)
  | (?P<ident>[A-Za-z_$][\w$]*)
  | (?P<num>0[xXoObB][\w]+|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d+)?n?)
  | (?P<str>"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')
  | (?P<tpl>`)
  | (?P<punct>\?\.|\.\.\.|=>|[=!]={0,2}|>>>?=?|<<=?|[<>]=?|&&=?|\|\|=?|\?\?=?|\*\*=?|\+\+|--|[-+*%&|^/]=?|[{}()\[\];,.:?~@#])
""", re.S | re.X)
_REGEX_RE = re.compile(r"/(?:[^/\\\[\n]|\\.|\[(?:[^\]\\\n]|\\.)*\])+/[a-z]*")
_TPL_TEXT_RE = re.compile(r"(?:[^`\\$]|\\.|\$(?!\{))*", re.S)


def tokenize(src):
    """Yield (kind, start, end) for every significant token. Kinds: ident, num, str, tpl,
    regex, punct. A template literal is one `tpl` token per text part; its ${} parts are
    tokenized normally."""
    pos, n = 0, len(src)
    prev = None                 # (kind, text) of the last significant token
    tpl_stack = []              # brace depth at each open ${ ... }
    depth = 0
    while pos < n:
        ch = src[pos]
        if ch == "/" and _regex_allowed(prev):
            m = _REGEX_RE.match(src, pos)
            if m:
                yield ("regex", pos, m.end())
                prev = ("regex", "")
                pos = m.end()
                continue
        if ch == "}" and tpl_stack and tpl_stack[-1] == depth:
            tpl_stack.pop()
            pos = yield from _template_tail(src, pos + 1, tpl_stack, depth)
            prev = ("tpl", "")
            continue
        m = _TOKEN_RE.match(src, pos)
        if not m:
            pos += 1            # stray char (non-ASCII identifier etc.)
            continue
        kind = m.lastgroup
        end = m.end()
        if kind in ("ws", "lcom", "bcom"):
            pos = end
            continue
        if kind == "tpl":
            pos = yield from _template_tail(src, pos + 1, tpl_stack, depth, start=pos)
            prev = ("tpl", "")
            continue
        text = src[pos:end]
        if kind == "punct":
            if text in "{([":
                depth += 1
            elif text in "})]":
                depth -= 1
        yield (kind, pos, end)
        prev = (kind, text)
        pos = end


def _template_tail(src, pos, tpl_stack, depth, start=None):
    """Scan template text from pos to the closing backtick or the next `${`."""
    m = _TPL_TEXT_RE.match(src, pos)
    end = m.end() if m else pos
    tok_start = pos - 1 if start is None else start
    if src.startswith("${", end):
        yield ("tpl", tok_start, end + 2)
        tpl_stack.append(depth)
        return end + 2
    yield ("tpl", tok_start, min(end + 1, len(src)))
    return end + 1


def _regex_allowed(prev):
    if prev is None:
        return True
    kind, text = prev
    if kind == "punct":
        return text not in (")", "]")
    if kind == "ident":
        return text in REGEX_AFTER_WORDS
    return False


class Build:
    """One simworker build: original lines, normalized lines, chunks."""

    def __init__(self, name, src, max_chunk):
        self.name = name
        self.src = src.replace("\r\n", "\n")
        self.lines = self.src.split("\n")
        self._scan()
        self._normalize()
        self.chunks = []
        self._chunk(0, len(self.lines), 0, max_chunk, "")

    def _normalize(self):
        """Replace minified names with `_`. Every minified binding in the builds seen so
        far has <= MINIFIED_MAX_LEN chars; longer bare names are real (class members,
        globals) and stay."""
        out, last = [], 0
        for s, e, text in self.bare:
            if len(text) <= MINIFIED_MAX_LEN:
                out.append(self.src[last:s])
                out.append("_")
                last = e
        out.append(self.src[last:])
        self.norm = [re.sub(r"\s+", " ", l).strip() for l in "".join(out).split("\n")]

    def _scan(self):
        """Record bracket depth and string state per line, and the bare identifiers
        (minifier candidates)."""
        src = self.src
        toks = list(tokenize(src))
        self.bare = []
        string_chars = [0] * len(self.lines)
        line_starts = [0]
        for i, c in enumerate(src):
            if c == "\n":
                line_starts.append(i + 1)
        line_of = lambda p: bisect.bisect_right(line_starts, p) - 1
        # Depth at the start of each line and whether a line begins inside a string.
        self.depth_at = [-1] * len(self.lines)     # -1: not reached yet
        self.in_string = [False] * len(self.lines)
        depth = 0
        tok_line_cursor = 0
        for idx, (kind, s, e) in enumerate(toks):
            ls = line_of(s)
            while tok_line_cursor <= ls:
                if self.depth_at[tok_line_cursor] == -1:
                    self.depth_at[tok_line_cursor] = depth
                tok_line_cursor += 1
            text = src[s:e]
            if kind == "punct":
                if text in "{([":
                    depth += 1
                elif text in "})]":
                    depth -= 1
            elif kind in ("str", "tpl"):
                le = line_of(e - 1)
                for ln in range(ls + 1, le + 1):
                    self.in_string[ln] = True
                string_chars[ls] += e - s
            elif kind == "ident" and self._bare(toks, idx, text):
                self.bare.append((s, e, text))
        for ln in range(tok_line_cursor, len(self.lines)):
            self.depth_at[ln] = depth
        self.string_chars = string_chars

    def _bare(self, toks, idx, text):
        """Not a property access, object key or keyword."""
        if text in KEEP_IDENTS:
            return False
        prev = self._tok_text(toks, idx - 1)
        if prev in (".", "?."):
            return False
        return not (prev in ("{", ",") and self._tok_text(toks, idx + 1) == ":")

    def _tok_text(self, toks, idx):
        if 0 <= idx < len(toks) and toks[idx][0] == "punct":
            return self.src[toks[idx][1]:toks[idx][2]]
        return None

    def _chunk(self, start, end, depth, max_chunk, parent):
        """Split [start, end) at lines that begin a statement or member at `depth`."""
        bounds = [start]
        for ln in range(start + 1, end):
            if self._starts_unit(ln, depth):
                bounds.append(ln)
        bounds.append(end)
        for a, b in zip(bounds, bounds[1:]):
            if b - a > max_chunk and depth < 4 and any(self._starts_unit(l, depth + 1) for l in range(a + 1, b)):
                path = f"{parent} > {self.label(a, b)}" if parent else self.label(a, b)
                self._chunk(a, b, depth + 1, max_chunk, " > ".join(path.split(" > ")[-3:]))
            elif any(self.norm[l] for l in range(a, b)):
                self.chunks.append(Chunk(self, a, b, parent))

    def _starts_unit(self, ln, depth):
        if self.in_string[ln] or self.depth_at[ln] != depth:
            return False
        text = self.lines[ln]
        stripped = text.lstrip()
        return bool(stripped) and stripped[0] not in "})].?:+-*/&|," and not stripped.startswith("//")

    def label(self, a, b):
        """First line of [a, b); when it holds no string or long name, also the first
        line below that does (a minified `function Uu(e) {` says nothing)."""
        first = self.lines[a].strip()[:60]
        if _LABEL_HINT_RE.search(self.norm[a]):
            return first
        for ln in range(a + 1, min(b, a + 30)):
            if _LABEL_HINT_RE.search(self.norm[ln]):
                return f"{first} ... {self.lines[ln].strip()[:60]}"
        return first


_LABEL_HINT_RE = re.compile(r"[`'\"][A-Za-z_.]{4,}|[A-Za-z$][\w$]{3,}")

# First line of an object member, method or case: its key or name, when not minified.
_MEMBER_KEY_RE = re.compile(r"""^(?:(?:static|async|get|set|case)\s+)*("[^"]+"|'[^']+'|`[^`$]+`|[A-Za-z$][\w$]{3,})\s*[:(]""")


class Chunk:
    def __init__(self, build, a, b, parent):
        self.build, self.a, self.b, self.parent = build, a, b, parent
        norm = [l for l in build.norm[a:b] if l]
        self.key = hashlib.sha1("\n".join(norm).encode()).hexdigest()
        self.features = {l for l in norm if len(l) > 3}
        m = _MEMBER_KEY_RE.match(norm[0]) if norm else None
        key = m.group(1) if m else None
        self.member_key = None if key in KEEP_IDENTS or key in REGEX_AFTER_WORDS else key
        text = "\n".join(build.lines[a:b])
        total = sum(len(l) for l in build.lines[a:b]) or 1
        self.text_share = sum(build.string_chars[a:b]) / total
        self.category = next((name for name, rx in NOISE_CATEGORIES if rx.search(text)), None)
        if self.category is None:
            self.category = "text" if self.text_share >= TEXT_SHARE else "code"

    @property
    def label(self):
        own = self.build.label(self.a, self.b)
        return f"{self.parent} > {own}" if self.parent else own


def match(old, new):
    """Pair chunks: exact normalized text first, then best Jaccard over indexed lines."""
    by_key = defaultdict(list)
    for c in old.chunks:
        by_key[c.key].append(c)
    pairs, rest_new = [], []
    used = set()
    for c in new.chunks:
        bucket = by_key.get(c.key)
        if bucket:
            used.add(id(bucket.pop()))
        else:
            rest_new.append(c)
    rest_old = [c for c in old.chunks if id(c) not in used]
    # Members with the same key, unique on both sides (text tables reword most values).
    old_keys = Counter(c.member_key for c in rest_old if c.member_key)
    new_keys = Counter(c.member_key for c in rest_new if c.member_key)
    old_by_key = {c.member_key: c for c in rest_old if c.member_key and old_keys[c.member_key] == 1}
    keyed = set()
    for c in rest_new:
        o = old_by_key.get(c.member_key) if c.member_key and new_keys[c.member_key] == 1 else None
        if o is not None:
            pairs.append((o, c))
            keyed.update((id(o), id(c)))
    rest_old = [c for c in rest_old if id(c) not in keyed]
    rest_new = [c for c in rest_new if id(c) not in keyed]
    df = Counter(f for c in rest_old for f in c.features)
    index = defaultdict(list)
    for c in rest_old:
        for f in c.features:
            if df[f] <= INDEX_MAX_DF:
                index[f].append(c)
    candidates = []
    for c in rest_new:
        seen = set()
        for f in c.features:
            for o in index.get(f, ()):
                if id(o) in seen:
                    continue
                seen.add(id(o))
                inter = len(c.features & o.features)
                score = inter / (len(c.features | o.features) or 1)
                if score >= FUZZY_MIN_SCORE:
                    candidates.append((score, o, c))
    candidates.sort(key=lambda t: -t[0])
    taken_old, taken_new = set(), set()
    for score, o, c in candidates:
        if id(o) in taken_old or id(c) in taken_new:
            continue
        taken_old.add(id(o))
        taken_new.add(id(c))
        pairs.append((o, c))
    added = [c for c in rest_new if id(c) not in taken_new]
    removed = [c for c in rest_old if id(c) not in taken_old]
    return pairs, added, removed


_NUM_RE = re.compile(r"(?<![\w$.])\d[\d_]*\.?\d*(?:[eE][+-]?\d+)?")


def diff_pair(o, c, context=2):
    """Return (hunks, number_changes) for one matched pair. Hunks hold original lines."""
    ob, nb = o.build, c.build
    ol = list(range(o.a, o.b))
    nl = list(range(c.a, c.b))
    ol = [i for i in ol if ob.norm[i]]
    nl = [i for i in nl if nb.norm[i]]
    sm = difflib.SequenceMatcher(None, [ob.norm[i] for i in ol], [nb.norm[i] for i in nl], autojunk=False)
    hunks, numbers = [], []
    for group in sm.get_grouped_opcodes(context):
        hunk, real = [], False
        for tag, i1, i2, j1, j2 in group:
            olds = [ol[i] for i in range(i1, i2)]
            news = [nl[j] for j in range(j1, j2)]
            if tag == "equal":
                hunk.extend((" ", nb.lines[j]) for j in news)
                continue
            if tag == "replace" and len(olds) == len(news) and all(
                    _NUM_RE.sub("#", ob.norm[a]) == _NUM_RE.sub("#", nb.norm[b]) for a, b in zip(olds, news)):
                numbers.extend((a, b, ob.lines[a].strip(), nb.lines[b].strip()) for a, b in zip(olds, news))
            else:
                real = True
            hunk.extend(("-", ob.lines[i]) for i in olds)
            hunk.extend(("+", nb.lines[j]) for j in news)
        if real:
            hunks.append(hunk)
    return hunks, numbers


def load_source(spec, default_rev):
    """spec: a .js path, an internals revision, or None for default_rev/working file."""
    if spec and Path(spec).is_file():
        return Path(spec).name, Path(spec).read_text(encoding="utf-8")
    rev = spec or default_rev
    if rev is None:
        path = INTERNALS / SIMWORKER_REL
        return "working", path.read_text(encoding="utf-8")
    text = subprocess.run(["git", "-C", str(INTERNALS), "show", f"{rev}:{SIMWORKER_REL}"],
                          capture_output=True, check=True).stdout.decode("utf-8")
    short = subprocess.run(["git", "-C", str(INTERNALS), "rev-parse", "--short", rev],
                           capture_output=True, text=True, check=True).stdout.strip()
    return short, text


def previous_rev():
    """Second-newest internals commit that touched the simworker."""
    out = subprocess.run(["git", "-C", str(INTERNALS), "log", "-n2", "--format=%H", "--", SIMWORKER_REL],
                         capture_output=True, text=True, check=True).stdout.split()
    if len(out) < 2:
        sys.exit("internals has only one simworker commit; pass --old")
    return out[1]


_OWNER_RE = re.compile(r"^\s*(?:id|typeId|type|name|key)\s*:")


def _owner_line(build, chunk, ln):
    """Nearest `id:`/`name:`/... line above ln inside the chunk: which table row a
    changed number belongs to."""
    for i in range(ln - 1, max(chunk.a, ln - 40) - 1, -1):
        if _OWNER_RE.match(build.lines[i]):
            return build.lines[i].strip()[:100]
    return None


def _around_change(a, b, width=60):
    """Both strings cut to a window around their first difference."""
    i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    start = max(0, i - width // 2)
    pre = "..." if start else ""
    return pre + a[start:start + width], pre + b[start:start + width]


def _adjacent_runs(chunks):
    """Group chunks (sorted by start line) whose line ranges touch."""
    runs = []
    for c in chunks:
        if runs and runs[-1][-1].b == c.a:
            runs[-1].append(c)
        else:
            runs.append([c])
    return runs


def render(old, new, pairs, added, removed, show_all, context_lines):
    out = [f"# Simworker diff {old.name} -> {new.name}", ""]
    changed = []
    numbers = []
    for o, c in pairs:
        hunks, nums = diff_pair(o, c)
        numbers.extend((c, n) for n in nums)
        if hunks:
            changed.append((o, c, hunks))
    hidden = Counter()

    def visible(c):
        if c.category in ("code", "text") or show_all:
            return True
        hidden[c.category] += 1
        return False

    def count(lst, cat):
        return sum(1 for x in lst if (x[1] if isinstance(x, tuple) else x).category == cat)

    out.append(f"Chunks: {len(old.chunks)} old, {len(new.chunks)} new; "
               f"{len(pairs)} fuzzy-paired, {len(changed)} changed, {len(added)} added, {len(removed)} removed.")
    out.append("")

    out.append("## Number changes")
    out.append("")
    for c, (a, b, ot, nt) in numbers:
        if not visible(c):
            continue
        owner = _owner_line(new, c, b)
        ot, nt = _around_change(ot, nt)
        out.append(f"- new L{b + 1} (old L{a + 1}) in `{owner or c.label}`:\n  `{ot}` -> `{nt}`")
    out.append("")

    for cat, title in (("code", "Code changes"), ("text", "Text changes")):
        out.append(f"## {title}")
        out.append("")
        for o, c, hunks in changed:
            if c.category != cat:
                continue
            out.append(f"### new L{c.a + 1} (old L{o.a + 1}): `{c.label}`")
            out.append("```diff")
            for hunk in hunks:
                out.extend(sign + line[:context_lines] for sign, line in hunk)
                out.append("@@")
            out.append("```")
            out.append("")
        for lst, sign, title2, build in ((added, "+", "Added", new), (removed, "-", "Removed", old)):
            items = sorted((c for c in lst if c.category == cat), key=lambda c: c.a)
            if not items:
                continue
            out.append(f"### {title2} ({cat})")
            out.append("")
            for run in _adjacent_runs(items):
                out.append(f"#### {build.name} L{run[0].a + 1}-{run[-1].b}: `{run[0].label}`")
                out.append("```diff")
                for c in run:
                    out.extend(sign + build.lines[i][:context_lines] for i in range(c.a, c.b))
                out.append("```")
                out.append("")
    if show_all:
        for cat, _ in NOISE_CATEGORIES:
            out.append(f"## {cat.title()} chunks")
            out.append("")
            for o, c, hunks in changed:
                if c.category == cat:
                    out.append(f"- changed: new L{c.a + 1} `{c.label}` ({sum(len(h) for h in hunks)} lines)")
            for c in added:
                if c.category == cat:
                    out.append(f"- added: new L{c.a + 1}-{c.b} `{c.label}`")
            for c in removed:
                if c.category == cat:
                    out.append(f"- removed: old L{c.a + 1}-{c.b} `{c.label}`")
            out.append("")
    else:
        for o, c, _ in changed:
            visible(c)
        for c in added + removed:
            visible(c)
        if hidden:
            out.append("Hidden (pass --all): " + ", ".join(f"{k} {v}" for k, v in sorted(hidden.items())))
    return "\n".join(out) + "\n", changed, numbers


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--old", help="internals revision or .js path (default: previous simworker commit)")
    ap.add_argument("--new", help="internals revision or .js path (default: working file)")
    ap.add_argument("--out", type=Path, help="report path (default: devtools/.simworker-diff/<old>_<new>.md)")
    ap.add_argument("--max-chunk", type=int, default=150, help="split chunks longer than this many lines")
    ap.add_argument("--width", type=int, default=240, help="truncate report lines to this width")
    ap.add_argument("--all", action="store_true", help="list editor/tutorial chunks too")
    args = ap.parse_args()

    old_name, old_src = load_source(args.old, None if args.old else previous_rev())
    new_name, new_src = load_source(args.new, None)
    old = Build(old_name, old_src, args.max_chunk)
    new = Build(new_name, new_src, args.max_chunk)
    pairs, added, removed = match(old, new)
    report, changed, numbers = render(old, new, pairs, added, removed, args.all, args.width)
    out = args.out or OUT_DIR / f"{old.name}_{new.name}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"{len(changed)} changed, {len(added)} added, {len(removed)} removed chunks, "
          f"{len(numbers)} number changes -> {out.relative_to(REPO_ROOT) if out.is_relative_to(REPO_ROOT) else out}")


if __name__ == "__main__":
    main()
