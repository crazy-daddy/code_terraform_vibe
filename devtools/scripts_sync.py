#!/usr/bin/env python
"""Sync the tiered scripts/ tree into a Code: Terraform save's script directory.

Adapted from inspirations/vakermit/bin/ct_sync.py, with two project-specific
differences documented in the plan this came from:

  1. Instead of vakermit's per-category "variant" subdirectories chosen by a
     `.current` file or a marker, this project's scripts/ tree is split by
     *global progression tier* first (`0_cold_boot`, `1_early`, `2_libunlock`,
     `3_archiveunlock`, `4_controlpanel`, `5_steampower`, ...), with machine
     categories (bio/, power/, rover/, ...) nested underneath. Tiers are
     discovered by scanning scripts/ for `<N>_<anything>` dirs and sorting by
     `N` ascending (`discover_tiers()`/`tier_number()`) - only the leading
     number is load-bearing, so dropping in `scripts/6_derp/` with its own
     `.criteria` picks it up automatically as the new top tier, no code
     change needed, and numbers may skip (`1_early`, `5_mid` today,
     `3_inbetween` added later slots in between with no other change). A dir
     whose name starts with a digit but isn't `<int>_...` (`1N3_DERP`) or two
     dirs claiming the same number (`10_hi`, `10_ho`) raise `TierNamingError`
     rather than being guessed past. The active tier is derived automatically,
     per save, from the save's own state file - see `read_save_state()`. No
     hint file, no manual bookkeeping. This assumes unlocks are monotonic
     (`resolve_active_tier()` stops walking at the first tier whose `.criteria`
     isn't met yet) - an out-of-order save where a higher tier's `.criteria`
     is satisfied before a lower one's isn't handled specially.

  2. `lib/` is not a flat, single-version directory - it is itself a per-tier
     category (`scripts/<tier>/lib/<module>.py`), resolved with the exact same
     tier-fallback rule as machine scripts, and mirrored into the save's
     `lib/` unconditionally on every sync (not gated behind a flag), since
     deployed scripts do `from lib.x import ...` and the game only loads
     modules physically present under the save root.

    python devtools/scripts_sync.py status          # show what maps to what
    python devtools/scripts_sync.py once             # one pass over what is there now
    python devtools/scripts_sync.py watch            # keep running and fill files as they appear

Matching ignores a trailing `_<number>` (`bio_lab_1.py` matches `bio_lab.py`),
except for machine types listed in DISTINCT_INSTANCES (currently just `panel`)
where each numbered instance is a genuinely distinct, hand-authored script
(panel_1 does Power Grid supervision, panel_2 does FLEET Sport Nav, ...) and is
matched by its exact name instead.

No duplicate files across tiers: for a given category/base_name, the resolver
walks tiers from the active one down to `0_cold_boot` and uses the first file
found, so a higher tier only needs a file when its content actually diverges
from what a lower tier already defines.

A category directory sitting directly under `scripts/` (a sibling of the tier
dirs, e.g. `scripts/contract/`) is a *global* category: it isn't gated by any
tier and is always included, unchained, alongside whatever the active tier
resolves. Use it for scripts that are genuinely tech-independent and
self-contained (no `lib/` imports) - contracts are the motivating case.

An empty game file with no match is staged into `scripts/_unmatched/` (never
used as a source) exactly as in vakermit's tool - see its docstring for the
fill/pull marker mechanics (`synctool-fill` / `synctool-pull` here, renamed
from `xyz`/`zyx` to avoid confusion with two unrelated tools sharing tokens),
renumbering, and the "already has code" guard, all ported unchanged.

A newly built (or newly re-equipped) machine's script slot exists in the
game's own `codeterraform-workspace.json` (`context.scripts`, sibling of the
save's `.py` files) well before the game ever writes a `.py` file for it on
disk - confirmed live, that file only appears once a human opens the slot in
the in-game script editor at least once. Watching the save directory for new
files (as `watch` otherwise does) can never see such a slot - there is
nothing to watch yet. `materialize_missing_slots()` polls that JSON instead
(every 5s in `watch`, once up front in `once`) and writes a real `.py` file
for any slot missing one, using the JSON's own live `source` text - never a
blank stub, so an actually-running script that just hadn't had a file
written for it yet is never clobbered. Once materialized, the slot flows
through the normal fill pipeline like any other file.

A source script may itself contain `${VAR}` / `${VAR:default}` placeholders
(same syntax as `early_game_runner/auto_deploy.py`'s substitution, kept
identical on purpose) for values only the operator knows at deploy time -
e.g. `pioneer.py`'s destination outpost. `sync_file()` prompts for these
interactively the first time a given save slot needs them and remembers the
answer in `devtools/.sync-backups/script_params.json` (gitignored) so
re-filling the same slot later doesn't re-ask.
"""
import ast
import json
import os
import re
import shutil
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SCRIPTS = REPO / "scripts"
BACKUP_DIR = REPO / "devtools" / ".sync-backups"
PARAMS_CACHE = REPO / "devtools" / ".sync-backups" / "script_params.json"
RESOLVED_PREVIEW_DIR = REPO / ".pyright-resolved"
UNMATCHED = "_unmatched"            # under scripts/; staged, never a source
SAVE_GLOB = "save_*_scripts"
GAME_DIR = "io.codeterraform.game"

LIB_CATEGORY = "lib"

# launch_in_game()'s retry cushion for the game's own disk-poll lag: a script
# slot we just wrote to isn't necessarily registered in the game's workspace
# snapshot yet by the time we try to launch it (confirmed live -- an
# immediate launch right after a fresh fill failed with "not registered",
# succeeded on retry after a short wait). Total extra wait if every attempt
# needs it: 0.5 + 1.0 + 2.0 = 3.5s, on top of the immediate first try.
LAUNCH_RETRY_DELAYS_S = (0.5, 1.0, 2.0)

# Machine types where each numbered instance is a genuinely distinct,
# hand-authored script (see module docstring) - matched by exact stem,
# never collapsed to a shared base name or renumbered.
#
# KNOWN GAP (see TODO.md "Panel dev-side numbering vs. save-side slot
# numbers"): scripts/4_controlpanel/control_panel/ was renumbered panel_1..4
# on the dev side (panel_7 -> panel_4, since _7 was just an artifact of
# which slot the game happened to assign), but the game can't rename/reorder
# an existing script slot, so the save's actual file is still panel_7.py.
# Exact-stem matching below does NOT bridge that - panel_4.py won't resolve
# against a save file named panel_7.py. Harmless while that slot already has
# code; would need a machine_id-based alias table (from
# codeterraform-workspace.json) to fix properly - not implemented.
DISTINCT_INSTANCES = {"panel"}

# The game owns these; never write to them.
RESERVED = {"user_stubs.py"}
SKIP_DIRS = {"lib"}
SKIP_SUFFIXES = (".codeterraform-write.bak",)
SKIP_PATTERNS = (re.compile(r"\.codeterraform-retired-"),)
TRAILING_INDEX = re.compile(r"_\d+$")
DEFAULT_MAGIC = "synctool-fill"     # game file -> filled from scripts/
DEFAULT_PULL = "synctool-pull"      # game file -> copied back into scripts/

SHORT_HELP = (
    "Sync the tiered scripts/ tree into a Code: Terraform save's script directory.\n\n"
    "Commands: status | once | watch | resolve-preview. Run `<command> --help` for its "
    "options, or see the module docstring in devtools/scripts_sync.py for the full "
    "tiering/matching rules.\n\n"
    "--auto (once/watch) launches filled/updated slots in-game via DAP - off by default, "
    "opt in per run."
)

app = typer.Typer(add_completion=False, help=SHORT_HELP)


@dataclass
class Options:
    save_dir: Path
    scripts_dir: Path
    strict: bool = False
    dry_run: bool = False
    verbose: bool = False
    renumber: bool = True
    magic: str = DEFAULT_MAGIC
    pull: str = DEFAULT_PULL
    force_tier: Optional[str] = None
    auto: bool = False
    auto_debounce: float = 30.0
    active_tier: str = field(default="", init=False)

    @property
    def unmatched_dir(self) -> Path:
        return self.scripts_dir / UNMATCHED


def show(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def err(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.RED, err=True)


def warn(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.YELLOW)


def ok(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.GREEN)


# ------------------------------------------------------------------ discovery
def appdata() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")


def discover_save() -> Optional[Path]:
    """Newest `save_*_scripts` directory, since the active save changes per playthrough."""
    root = appdata() / GAME_DIR
    if not root.is_dir():
        return None
    saves = [p for p in root.glob(SAVE_GLOB) if p.is_dir()]
    return max(saves, key=lambda p: p.stat().st_mtime) if saves else None


def resolve_save(save_dir: Optional[Path]) -> Path:
    if save_dir is None:
        save_dir = discover_save()
        if save_dir is None:
            err("No save directory found under %s." % (appdata() / GAME_DIR))
            err("Pass --save-dir, or set CT_SAVE_DIR.")
            raise typer.Exit(2)
        typer.echo("Save (auto-detected): %s" % save_dir)
    if not save_dir.is_dir():
        err("Not a directory: %s" % save_dir)
        raise typer.Exit(2)
    return save_dir


# --------------------------------------------------------------- save state
# Cache keyed by the state file's path: (mtime, summary). The state file is
# multi-MB and rewritten roughly every 30s during play, so re-parsing it on
# every 0.2s poll tick would be wasteful - only re-parse when mtime changes.
_state_cache: dict = {}


def state_file_for(save_dir: Path) -> Optional[Path]:
    """`save_X_scripts/` -> sibling `save_X.json`, one level up."""
    name = save_dir.name
    if not name.endswith("_scripts"):
        return None
    candidate = save_dir.parent / (name[: -len("_scripts")] + ".json")
    return candidate if candidate.is_file() else None


def read_save_state(save_dir: Path) -> Optional[dict]:
    """Read-only: state.unlockedTech and outpost count, straight from the save.

    Verified fields (see the plan this tool came from): `state.unlockedTech`
    is a list of tech ids (e.g. "shared_library", "data_archive_unlock"),
    `state.planet.outposts` is a list whose length is the outpost count, and
    `state.machines` is a dict of built machines keyed by id, each carrying a
    `typeId` (e.g. "steam_turbine", "thermal_cap") - counted per type into
    `building_counts`. Pending construction blueprints live elsewhere
    (`state.planet.constructionBlueprints`) and are deliberately not counted,
    nor are placed machines still `isUnderConstruction` - only finished,
    actually deployed buildings count.
    Returns None if the save's state file can't be found or parsed - callers
    treat that as "nothing unlocked", i.e. tier 0.
    """
    path = state_file_for(save_dir)
    if path is None:
        return None
    mtime = path.stat().st_mtime
    cached = _state_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        state = data["state"]
        summary = {
            "unlockedTech": set(state.get("unlockedTech", [])),
            "outpost_count": len(state.get("planet", {}).get("outposts", [])),
            "building_counts": Counter(
                m.get("typeId") for m in state.get("machines", {}).values()
                if isinstance(m, dict) and not m.get("isUnderConstruction", False)
            ),
        }
    except (OSError, ValueError, KeyError):
        return None
    _state_cache[path] = (mtime, summary)
    return summary


# ------------------------------------------------------- workspace state (slots)
WORKSPACE_JSON = "codeterraform-workspace.json"

# Cache keyed by the workspace file's path: (mtime, context dict) - same
# reasoning as _state_cache above, this file can be multi-MB (it embeds every
# script's full source text) and is rewritten frequently during play.
_workspace_cache: dict = {}


def read_workspace_context(save_dir: Path) -> Optional[dict]:
    """Read-only: the game's own live workspace state
    (`codeterraform-workspace.json`, sibling of the save's `.py` script
    slots). Specifically `context.scripts` - a dict of every script slot id
    the game currently knows about, each with its live `source` text and
    `status`, populated as soon as a machine granting that slot exists.

    Confirmed live (2026-09-22, this save): a slot appears here well before
    the game ever writes a `.py` file for it on disk - the file is only
    created once the operator opens that slot in the in-game script editor.
    A file watcher on the save directory (as used elsewhere in this module)
    can never see a slot that has no file yet, no matter how long it waits -
    it has nothing to watch. See materialize_missing_slots(), which is why
    this function exists: polling this JSON is the only way to notice a
    newly-built (or newly-mounted-module) machine's script slot before a
    human has opened its editor at least once.

    Returns None if the file is missing or unreadable - callers treat that
    as "nothing to discover yet".
    """
    path = save_dir / WORKSPACE_JSON
    if not path.is_file():
        return None
    mtime = path.stat().st_mtime
    cached = _workspace_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        context = data["context"]
    except (OSError, ValueError, KeyError):
        return None
    _workspace_cache[path] = (mtime, context)
    return context


def missing_slot_sources(save_dir: Path) -> dict:
    """script id -> its live `source` text, for every slot workspace state
    knows about that has no `.py` file on disk yet. Read-only; used by both
    `status` (to report) and materialize_missing_slots() (to act)."""
    context = read_workspace_context(save_dir)
    if context is None:
        return {}
    missing = {}
    for sid, info in context.get("scripts", {}).items():
        path = save_dir / ("%s.py" % sid)
        if path.exists() or not is_candidate(path, save_dir):
            continue
        missing[sid] = info.get("source") or ""
    return missing


def materialize_missing_slots(opts: Options) -> int:
    """Writes a real `.py` file for every script slot workspace state knows
    about but that has no file on disk yet (see read_workspace_context()),
    using that slot's own live `source` text from the JSON - never a blank
    stub, unless the JSON itself says the slot is empty. This matters: if the
    slot is actually running non-empty code (just hadn't had a file written
    for it yet), materializing a blank file instead would make sync_file()'s
    own fill logic treat it as an empty slot and overwrite real operator code
    with whatever scripts/ resolves to. Once materialized as a real file
    (blank or not), the normal sync_file() pipeline treats it exactly like
    any other slot from here on - this only bridges the gap of the file not
    existing at all yet. Returns how many files were created."""
    created = 0
    for sid, source in missing_slot_sources(opts.save_dir).items():
        path = opts.save_dir / ("%s.py" % sid)
        tag = "has code" if source.strip() else "empty"
        if opts.dry_run:
            ok("  would sense %-23s new slot from workspace state (%s)" % (path.name, tag))
            created += 1
            continue
        if write_atomic(path, source):
            ok("  sense %-28s <- workspace state (%s)" % (path.name, tag))
            created += 1
    return created


class TierNamingError(RuntimeError):
    """A dir directly under scripts/ has an ambiguous or conflicting tier
    name - not something to silently guess past (see tier_number/
    discover_tiers)."""


def tier_number(dirname: str) -> Optional[int]:
    """Split on the first `_` and cast the part before it to int - `10_endofworld`
    -> 10, `010_iamsmart` -> 10 (int() strips the leading zero itself, no
    octal surprise). None if there's no `_` at all, or the part before it
    doesn't start with a digit - such a dir isn't attempting to be a tier,
    it's a global category (see list_global_categories), e.g. `contract` or
    `my_stuff`.

    Raises TierNamingError if the part before the first `_` *starts* with a
    digit but isn't a plain int (e.g. `1N3_DERP`, `5b_weird`) - that's not a
    global category with a coincidental underscore, it's a typo'd tier
    number, and guessing past it silently would misfile whatever's inside."""
    prefix, sep, _ = dirname.partition("_")
    if not sep or not prefix or not prefix[0].isdigit():
        return None
    if not prefix.isdigit():
        raise TierNamingError(
            "%r looks like it's trying to name a tier (starts with a digit "
            "before the first `_`) but %r isn't a plain integer. Rename it "
            "to `<N>_<name>`, or to something not starting with a digit if "
            "it's meant to be a global (untiered) category." % (dirname, prefix)
        )
    return int(prefix)


def discover_tiers(scripts_dir: Path) -> list:
    """Tier dirs directly under scripts_dir, ordered ascending by their
    leading number - e.g. `0_cold_boot`, `1_early`, ... `10_endofworld` sorts
    after `9_...`, never between `1_` and `2_` (numeric key, not string
    compare). Only the number is load-bearing; the rest of the name is free
    text. Drop a new tier in as `scripts/<N>_<anything>/` with its own
    `.criteria` and it's picked up automatically, no code change needed.
    Numbers may skip (`1_early`, `5_mid` today, `3_inbetween` added later
    slots in between and is picked up next run with no other change).

    Raises TierNamingError if two tier dirs claim the same number (e.g.
    `10_hi` and `10_ho`) - that's a genuine conflict, not something to
    resolve by string order."""
    tiers = []
    if scripts_dir.is_dir():
        for p in scripts_dir.iterdir():
            if not p.is_dir():
                continue
            n = tier_number(p.name)
            if n is not None:
                tiers.append((n, p.name))
    by_number: dict = {}
    for n, name in tiers:
        by_number.setdefault(n, []).append(name)
    dupes = {n: names for n, names in by_number.items() if len(names) > 1}
    if dupes:
        detail = "; ".join("%d: %s" % (n, ", ".join(sorted(names)))
                            for n, names in sorted(dupes.items()))
        raise TierNamingError("duplicate tier number(s) under %s - %s" % (show(scripts_dir), detail))
    tiers.sort(key=lambda t: t[0])
    return [name for _, name in tiers]


def load_criteria(scripts_dir: Path, tier: str) -> dict:
    path = scripts_dir / tier / ".criteria"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        warn("  bad JSON in %s, treating as no criteria" % show(path))
        return {}


def criteria_met(criteria: dict, state: Optional[dict]) -> bool:
    if not criteria:
        return True
    if state is None:
        return False
    tech = set(criteria.get("tech", []))
    if not tech.issubset(state["unlockedTech"]):
        return False
    if "outpost_count" in criteria and state["outpost_count"] < criteria["outpost_count"]:
        return False
    counts = state["building_counts"]
    for type_id, minimum in criteria.get("buildings", {}).items():
        if counts.get(type_id, 0) < minimum:
            return False
    # OR-group: at least one listed type meets its minimum (e.g. any of the
    # three Mining Drill variants). Empty/absent group imposes nothing.
    any_of = criteria.get("buildings_any", {})
    if any_of and not any(counts.get(t, 0) >= n for t, n in any_of.items()):
        return False
    return True


def resolve_active_tier(scripts_dir: Path, save_dir: Path, force_tier: Optional[str]) -> str:
    """Highest tier whose `.criteria` - and every ancestor's - are satisfied.

    Tiers are evaluated in order and the walk stops at the first one that
    fails, so an ancestor's criteria are implicitly required too (this only
    holds because unlocks are monotonic - a tech never becomes "unlearned").
    """
    try:
        tiers = discover_tiers(scripts_dir)
    except TierNamingError as exc:
        err(str(exc))
        raise typer.Exit(2)
    if force_tier:
        if force_tier not in tiers:
            err("Unknown tier %r. Known tiers: %s" % (force_tier, ", ".join(tiers)))
            raise typer.Exit(2)
        return force_tier
    if not tiers:
        err("No tier dirs found under %s (expected e.g. `0_cold_boot/`)" % show(scripts_dir))
        raise typer.Exit(2)
    state = read_save_state(save_dir)
    active = tiers[0]
    for tier in tiers:
        if criteria_met(load_criteria(scripts_dir, tier), state):
            active = tier
        else:
            break
    return active


def tier_chain(scripts_dir: Path, active_tier: str) -> list:
    """Active tier first, down through its ancestors - the fallback search order."""
    tiers = discover_tiers(scripts_dir)
    idx = tiers.index(active_tier)
    return list(reversed(tiers[: idx + 1]))


# -------------------------------------------------------------------- mapping
def base_name(stem: str) -> str:
    """`bio_lab_1` -> `bio_lab`. Slot numbers differ between source and save."""
    return TRAILING_INDEX.sub("", stem)


def match_key(stem: str) -> str:
    """The key a source file is looked up by. Distinct-instance machine types
    (see DISTINCT_INSTANCES) are matched by their exact stem; everything else
    by its slot-number-stripped base name."""
    base = base_name(stem)
    return stem if base in DISTINCT_INSTANCES else base


def split_index(stem: str):
    m = re.search(r"_(\d+)$", stem)
    return (stem[:m.start()], m.group(1)) if m else (stem, None)


def renumber(text: str, src_stem: str, dst_stem: str):
    """Point the script's *own* instance id at the slot it is being filled into.

    Only the source's exact self id is rewritten; every other numbered id is
    left alone (see vakermit's ct_sync.py docstring for why). A source with no
    number, or a distinct-instance match where src_stem == dst_stem already,
    is never rewritten.
    """
    src_base, src_num = split_index(src_stem)
    if src_num is None or src_base != base_name(dst_stem) or src_stem == dst_stem:
        return text, 0, None
    old = "%s_%s" % (src_base, src_num)
    pattern = re.compile(r"(?<![0-9A-Za-z_])" + re.escape(old) + r"(?![0-9A-Za-z_])")
    new_text, count = pattern.subn(dst_stem, text)
    return new_text, count, ("%s -> %s" % (old, dst_stem) if count else None)


NUMBERED_ID = re.compile(r"(?<![0-9A-Za-z_])([a-z][a-z0-9]*(?:_[a-z0-9]+)*_\d+)(?![0-9A-Za-z_])")


def other_numbered_ids(text: str, own_base: str):
    return sorted({t for t in NUMBERED_ID.findall(text) if base_name(t) != own_base})


def resolve_category(scripts_dir: Path, chain: list, category: str):
    """Tier-fallback resolution for one category: match_key -> chosen path.

    Walks the chain from the active tier down to 0_cold_boot; the first tier
    that defines a given key wins (no duplication needed at lower tiers).
    A same-tier collision (two files reducing to the same key) is a conflict;
    a cross-tier hit for the same key is the fallback working as intended.
    """
    resolved: dict = {}
    conflicts: dict = {}
    for tier in chain:
        cat_dir = scripts_dir / tier / category
        if not cat_dir.is_dir():
            continue
        seen: dict = {}
        for path in sorted(cat_dir.rglob("*.py")):
            key = match_key(path.stem)
            if key in seen:
                conflicts.setdefault((tier, category, key), []).extend([seen[key], path])
            else:
                seen[key] = path
        for key, path in seen.items():
            resolved.setdefault(key, path)
    return resolved, conflicts


def list_categories(scripts_dir: Path, chain: list):
    cats = set()
    for tier in chain:
        tier_dir = scripts_dir / tier
        if not tier_dir.is_dir():
            continue
        for p in tier_dir.iterdir():
            if p.is_dir() and p.name != UNMATCHED:
                cats.add(p.name)
    return sorted(cats)


def list_global_categories(scripts_dir: Path):
    """Category dirs sitting directly under scripts/, sibling to the tiers -
    not gated by any tier, always included (see module docstring)."""
    cats = set()
    if scripts_dir.is_dir():
        for p in scripts_dir.iterdir():
            if p.is_dir() and p.name != UNMATCHED and tier_number(p.name) is None:
                cats.add(p.name)
    return sorted(cats)


def resolve_global_category(scripts_dir: Path, category: str):
    """Same match_key resolution as resolve_category, but for a single
    untiered dir directly under scripts/ (no tier fallback needed/possible)."""
    return resolve_category(scripts_dir, [""], category)


def build_index(scripts_dir: Path, active_tier: str):
    """(script_index, lib_index, conflicts) for the given active tier.

    script_index/lib_index map match_key -> resolved Path. Cross-category
    collisions (two categories both defining, say, "solar") are reported as
    conflicts under a synthetic ("CROSS-CATEGORY", key) entry. Global
    categories (scripts/<category>/, untiered) are merged in unconditionally,
    on top of whatever the active tier resolves.
    """
    chain = tier_chain(scripts_dir, active_tier)
    conflicts: dict = {}
    script_index: dict = {}
    for category in list_categories(scripts_dir, chain):
        if category == LIB_CATEGORY:
            continue
        resolved, cat_conflicts = resolve_category(scripts_dir, chain, category)
        conflicts.update(cat_conflicts)
        for key, path in resolved.items():
            if key in script_index and script_index[key] != path:
                conflicts.setdefault(("CROSS-CATEGORY", key), []).extend([script_index[key], path])
            else:
                script_index[key] = path
    for category in list_global_categories(scripts_dir):
        resolved, cat_conflicts = resolve_global_category(scripts_dir, category)
        conflicts.update(cat_conflicts)
        for key, path in resolved.items():
            if key in script_index and script_index[key] != path:
                conflicts.setdefault(("CROSS-CATEGORY", key), []).extend([script_index[key], path])
            else:
                script_index[key] = path
    lib_index, lib_conflicts = resolve_category(scripts_dir, chain, LIB_CATEGORY)
    conflicts.update(lib_conflicts)
    return script_index, lib_index, conflicts


def report_conflicts(conflicts: dict) -> None:
    for (tier, category, key), paths in sorted(conflicts.items(), key=lambda kv: str(kv[0])):
        warn("ambiguous %r in %s/%s, skipped: %s" % (key, tier, category, ", ".join(show(p) for p in paths)))


# --------------------------------------------------------------- game-side IO
def is_candidate(path: Path, save_dir: Path) -> bool:
    """Top-level `.py` files the game made for us - nothing else."""
    if path.suffix != ".py" or path.name in RESERVED:
        return False
    if path.name.endswith(SKIP_SUFFIXES) or any(p.search(path.name) for p in SKIP_PATTERNS):
        return False
    try:
        rel = path.resolve().relative_to(save_dir.resolve())
    except ValueError:
        return False
    return len(rel.parts) == 1 and not (set(rel.parts[:-1]) & SKIP_DIRS)


def is_empty(text: str, strict: bool) -> bool:
    if not text.strip():
        return True
    if strict:
        return False
    try:
        body = ast.parse(text).body
    except SyntaxError:
        return False
    if not body:
        return True
    return (len(body) == 1
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str))


def _first_real_line(text: str):
    for i, line in enumerate(text.splitlines()):
        if line.strip():
            return i, line
    return None, None


def _unquote_marker(line: str) -> str:
    line = line.strip().lstrip("#").strip()
    for quote in ('"""', "'''", '"', "'"):
        if line.startswith(quote) and line.endswith(quote) and len(line) > 2 * len(quote):
            return line[len(quote):-len(quote)].strip()
    return line


def parse_magic(text: str, magic: str):
    if not magic:
        return False, None
    _, line = _first_real_line(text)
    if line is None:
        return False, None
    token = _unquote_marker(line)
    if token.lower() == magic.lower():
        return True, None
    m = re.match(re.escape(magic) + r"[\s\-:/]+([A-Za-z0-9_][\w-]*)$", token, re.IGNORECASE)
    return (True, m.group(1)) if m else (False, None)


def has_magic(text: str, magic: str) -> bool:
    return parse_magic(text, magic)[0]


def strip_magic(text: str, magic: str) -> str:
    i, _ = _first_real_line(text)
    if i is None or not has_magic(text, magic):
        return text
    lines = text.splitlines(keepends=True)
    return "".join(lines[:i] + lines[i + 1:])


def read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def backup(path: Path) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, BACKUP_DIR / ("%s.%s.py" % (path.stem, stamp)))


def write_atomic(path: Path, body: str) -> bool:
    tmp = path.with_name(path.name + ".sync-tmp")
    try:
        tmp.write_text(body, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
        return True
    except OSError as exc:
        err("  fail  %-28s %s" % (path.name, exc))
        tmp.unlink(missing_ok=True)
        return False


# ---------------------------------------------------------- parameterized templates
# A source script may contain `${VAR}` / `${VAR:default}` placeholders (same
# syntax as early_game_runner/auto_deploy.py's substitute_placeholders(), kept
# identical on purpose) for values that only the operator knows at deploy time
# -- e.g. pioneer.py's destination outpost. sync_file() prompts for these
# interactively the first time a given save slot needs them, then remembers
# the answer in PARAMS_CACHE (keyed by save dir + slot filename) so re-filling
# the same slot later (e.g. after it's blanked out again) doesn't re-ask.
PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}")


def find_placeholders(text: str) -> list:
    """Ordered, de-duplicated (name, default) pairs for every placeholder in
    text - first occurrence's default wins if the same name appears twice."""
    seen: dict = {}
    for m in PLACEHOLDER.finditer(text):
        name, default = m.group(1), m.group(2)
        if name not in seen:
            seen[name] = default if default is not None else ""
    return list(seen.items())


def render_placeholders(text: str, answers: dict) -> str:
    return PLACEHOLDER.sub(lambda m: str(answers.get(m.group(1), m.group(0))), text)


def load_params_cache() -> dict:
    if not PARAMS_CACHE.is_file():
        return {}
    try:
        return json.loads(PARAMS_CACHE.read_text(encoding="utf-8"))
    except ValueError:
        warn("  bad JSON in %s, ignoring cached script parameters" % show(PARAMS_CACHE))
        return {}


def save_params_cache(cache: dict) -> None:
    PARAMS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PARAMS_CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8", newline="\n")


def resolve_placeholders(save_dir: Path, stem: str, placeholders: list, dry_run: bool) -> dict:
    """Answers for every (name, default) in placeholders. Anything already
    cached for this exact save slot is reused silently; anything new is
    prompted for interactively (blocking - see scripts_sync.py's plan notes on
    why that's fine even under `watch`: the filesystem observer runs on its
    own thread and just queues further events while we wait on input()).
    Under --dry-run nothing is prompted or cached - falls back to cached/
    default values only, as a preview of what a real run would fill in."""
    cache = load_params_cache()
    key = "%s/%s" % (save_dir.name, stem)
    slot_cache = dict(cache.get(key, {}))
    answers: dict = {}
    dirty = False
    for name, default in placeholders:
        if name in slot_cache:
            answers[name] = slot_cache[name]
            continue
        if dry_run:
            answers[name] = default
            continue
        answers[name] = typer.prompt("%s: %s" % (stem, name), default=default)
        slot_cache[name] = answers[name]
        dirty = True
    if dirty:
        cache[key] = slot_cache
        save_params_cache(cache)
    return answers


def launch_in_game(save_dir: Path, script_stem: str) -> None:
    """Best-effort DAP launch, only ever called when --auto is passed.

    This is user-invoked automation (the operator passes --auto themselves on
    each run) rather than Claude or any other assistant starting a live-debug
    session on its own initiative, so it does not need the "always ask first"
    confirmation that governs the assistant's own actions - see CLAUDE.md's
    live-debugging rule and the plan this tool came from.
    """
    sys.path.insert(0, str(REPO / "devtools"))
    try:
        from dap_client import launch_script  # type: ignore
    except ImportError:
        warn("  --auto requested but devtools/dap_client.py is unavailable")
        return
    # launch_script()'s "script" argument is matched against the workspace's
    # registered document paths (debug-adapter.cjs's Workspace.document()) --
    # a bare stem is not a registered path and is always rejected ("This file
    # is not registered to a game script"). Confirmed live: every --auto call
    # site here was passing script_stem straight through and silently failing
    # every single launch until this fix.
    script_path = str(save_dir / f"{script_stem}.py")
    try:
        for attempt, delay in enumerate((0.0,) + LAUNCH_RETRY_DELAYS_S):
            if delay:
                time.sleep(delay)
            if launch_script(str(save_dir), script_path):
                ok("  auto  %-28s launched in game%s" % (script_stem, " (retry %d)" % attempt if attempt else ""))
                break
        else:
            # Most common cause: we just wrote this file ourselves a moment
            # ago, but the game polls disk on its own cadence rather than
            # reacting instantly, so "This file is not registered to a game
            # script" is expected for the first attempt or two right after a
            # fresh fill -- confirmed live (a freshly-cleared, re-filled
            # drone_2.py failed to launch immediately, succeeded once retried
            # after a short wait). The retries above are a best-effort cushion
            # for that race, not a fix for a genuinely broken launch.
            warn("  auto  %-28s launch failed after %d attempt(s) (see DAP output above -- "
                 "the game may not have polled this file yet)" % (script_stem, len(LAUNCH_RETRY_DELAYS_S) + 1))
    except Exception as exc:  # pragma: no cover - best-effort, never fatal
        warn("  auto  %-28s launch error: %s" % (script_stem, exc))


# ---------------------------------------------------------------------- sync
def stage_unmatched(path: Path, text: str, opts: Options) -> bool:
    dest = opts.unmatched_dir / path.name
    if dest.exists():
        return False
    if opts.dry_run:
        ok("  would stage %-23s -> %s" % (path.name, show(dest)))
        return True
    try:
        opts.unmatched_dir.mkdir(parents=True, exist_ok=True)
        dest.write_text(strip_magic(text, opts.magic), encoding="utf-8", newline="\n")
    except OSError as exc:
        err("  fail  %-28s %s" % (path.name, exc))
        return False
    ok("  stage %-28s -> %s   (write it, then move it into place)" % (path.name, show(dest)))
    return True


def tidy_unmatched(index: dict, opts: Options) -> None:
    if not opts.unmatched_dir.is_dir():
        return
    for path in sorted(opts.unmatched_dir.glob("*.py")):
        matched = index.get(match_key(path.stem))
        if matched is None:
            continue
        text = read(path)
        if text is None or text.strip():
            continue
        if opts.dry_run:
            typer.echo("  would drop %-24s (blank, now matched by %s)" % (show(path), show(matched)))
            continue
        try:
            path.unlink()
            typer.echo("  drop  %-28s blank, now matched by %s" % (show(path), show(matched)))
        except OSError:
            pass


def pull_file(path: Path, text: str, index: dict, opts: Options) -> bool:
    """Copy a game file marked `synctool-pull` back into scripts/, at the
    active tier's category for its match_key if known, else scripts/_unmatched/."""
    body = strip_magic(text, opts.pull)
    if is_empty(body, strict=False):
        warn("  skip  %-28s marked %r but holds no code; nothing to pull" % (path.name, opts.pull))
        return False

    key = match_key(path.stem)
    existing_source = index.get(key)
    if existing_source is not None:
        target = existing_source
        how = "existing source"
    else:
        target = opts.unmatched_dir / path.name
        how = "new, staged"

    note = None
    if opts.renumber:
        body, _, note = renumber(body, path.stem, target.stem)
    parts = [opts.pull, how] + ([note] if note else [])
    suffix = "  [%s]" % ", ".join(parts)

    if opts.dry_run:
        ok("  would pull %-24s -> %s%s" % (path.name, show(target), suffix))
        return True

    prior = read(target) if target.exists() else None
    if prior != body:
        if prior is not None and prior.strip():
            backup(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not write_atomic(target, body):
            return False
        ok("  pull  %-28s -> %s%s" % (path.name, show(target), suffix))
        if note:
            others = other_numbered_ids(body, base_name(target.stem))
            if others:
                warn("        left as-is (check these): %s" % ", ".join(others))
    else:
        typer.echo("  pull  %-28s -> %s   already identical" % (path.name, show(target)))

    write_atomic(path, strip_magic(text, opts.pull))
    return True


def sync_file(path: Path, index: dict, opts: Options, quiet_skips: bool = True) -> bool:
    """Fill one save script from scripts/. True if it was written."""
    if not is_candidate(path, opts.save_dir):
        return False
    text = read(path)
    if text is None:
        return False
    pulled, _ = parse_magic(text, opts.pull)
    if pulled:
        return pull_file(path, text, index, opts)
    marked, _ = parse_magic(text, opts.magic)
    if not marked and not is_empty(text, opts.strict):
        if not quiet_skips:
            typer.echo("  skip  %-28s already has code" % path.name)
        return False

    source = index.get(match_key(path.stem))
    if source is None:
        first_time = not (opts.unmatched_dir / path.name).exists()
        if marked and (first_time or not quiet_skips):
            warn("  skip  %-28s marked %r but no match in scripts/" % (path.name, opts.magic))
        elif not marked and not quiet_skips:
            typer.echo("  skip  %-28s no match in scripts/" % path.name)
        stage_unmatched(path, text, opts)
        return False

    body = read(source)
    if body is None:
        err("  fail  %-28s cannot read %s" % (path.name, source))
        return False

    param_note = None
    placeholders = find_placeholders(body)
    if placeholders:
        answers = resolve_placeholders(opts.save_dir, path.stem, placeholders, opts.dry_run)
        body = render_placeholders(body, answers)
        param_note = "params: %s" % ", ".join("%s=%s" % kv for kv in answers.items())

    note = None
    if opts.renumber:
        body, _, note = renumber(body, source.stem, path.stem)
    parts = ([opts.magic] if marked else []) + ([param_note] if param_note else []) + ([note] if note else [])
    suffix = "  [%s]" % ", ".join(parts) if parts else ""

    if text == body:
        return False

    if opts.dry_run:
        ok("  would fill %-24s <- %s%s" % (path.name, show(source), suffix))
        return True

    if text.strip():
        backup(path)
    if not write_atomic(path, body):
        return False
    ok("  fill  %-28s <- %s%s" % (path.name, show(source), suffix))
    if note:
        others = other_numbered_ids(body, base_name(path.stem))
        if others:
            warn("        left as-is (check these): %s" % ", ".join(others))
    if opts.auto:
        launch_in_game(opts.save_dir, path.stem)
    return True


def sync_lib(lib_index: dict, opts: Options) -> set:
    """Unconditional mirror of the resolved lib/ into the save's lib/.

    Unlike machine scripts, lib modules aren't slots the game creates - we own
    the whole directory. Every resolved module is copied in if its content
    differs from what's already deployed (backing up the old copy first).

    Returns the set of lib_index keys actually (re)written -- including under
    --dry-run, as a preview of what would change -- so the caller can decide
    which currently-deployed scripts need relaunching (see
    relaunch_lib_dependents()): unlike a machine script slot, a lib module has
    no slot of its own whose text changing would trigger sync_file()'s own
    --auto launch, so without this a lib-only fix silently never reaches any
    already-running script - it sits on disk correct but unread until
    something restarts the scripts that import it.
    """
    dest_dir = opts.save_dir / "lib"
    changed: set = set()
    for key, source in sorted(lib_index.items()):
        dest = dest_dir / f"{key}.py"
        body = read(source)
        if body is None:
            err("  fail  %-28s cannot read %s" % (dest.name, source))
            continue
        prior = read(dest) if dest.exists() else None
        if prior == body:
            continue
        if opts.dry_run:
            ok("  would sync-lib %-19s <- %s" % (dest.name, show(source)))
            changed.add(key)
            continue
        if prior is not None and prior.strip():
            backup(dest)
        dest_dir.mkdir(parents=True, exist_ok=True)
        if write_atomic(dest, body):
            ok("  lib   %-28s <- %s" % (dest.name, show(source)))
            changed.add(key)
    return changed


def parse_module_imports(text: str) -> set:
    """Top-level module names this text `import`s or `from`-imports, e.g.
    `from vehicle_mining import VehicleMiningMixin` -> {"vehicle_mining"}.
    Matches this project's own flat, no-package import style (game scripts
    can't use relative imports or dotted packages) -- good enough to build a
    lib dependency graph, not a general-purpose import resolver. Returns an
    empty set on unparseable text rather than raising."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                names.add(node.module.split(".")[0])
    return names


def lib_dependency_closure(lib_index: dict) -> dict:
    """key -> every OTHER lib_index key it transitively imports, e.g. "rover"
    (which imports "vehicle") includes "vehicle_mining" too, since "vehicle"
    itself imports that. Used to tell whether a changed lib module reaches a
    given deployed script indirectly (rover_1.py -> "rover" -> "vehicle" ->
    "vehicle_mining"), not just through its own direct imports."""
    direct = {
        key: {n for n in parse_module_imports(read(path) or "") if n in lib_index and n != key}
        for key, path in lib_index.items()
    }
    closure: dict = {}

    def expand(key: str, seen: frozenset) -> set:
        if key in closure:
            return closure[key]
        if key in seen:
            return set()  # import cycle guard -- not memoized, this key's own answer is still being computed higher up
        result: set = set()
        for dep in direct.get(key, ()):
            result.add(dep)
            result |= expand(dep, seen | {key})
        closure[key] = result
        return result

    for key in lib_index:
        expand(key, frozenset())
    return closure


def relaunch_lib_dependents(changed_keys: set, lib_index: dict, opts: Options, skip_stems: set) -> None:
    """Reports every currently-deployed script whose import closure reaches a
    lib module sync_lib() just changed -- it deliberately does NOT attempt to
    relaunch them (despite the name -- kept for now to avoid touching every
    call site again; see TODO.md to rename). skip_stems are slots sync_file()
    already relaunched this same pass for their OWN changed body text, so
    they're excluded from the report (though see the caveat below -- that
    relaunch has the same unsolved problem for anything they import).

    CONFIRMED LIVE (2026-09-22, this save) that no automatable path actually
    applies a lib/ change to an already-running script:
    - DAP `launch` (what launch_in_game() calls) never restarts a script
      that's already running -- runIfIdle=True in debug-adapter.cjs means an
      already-running target just gets attached to, old code untouched.
    - The general external-command channel's "action":"run" (same one "Run
      Script in Game" uses) DOES force a genuine restart with fresh top-level
      code -- confirmed on rover_1.py -- but the restarted script still ran
      the STALE cached copy of the changed library, not the freshly-synced
      file on disk. The game caches an imported library module independently
      of restarting the script that imports it.
    - Every relevant VS Code command was tried directly against this exact
      changed file (Run Script/Create Library/Import File as Library/Rename
      Library) and each failed for an unrelated, semantically-correct reason
      (wrong file kind, already exists, no-op rename, ...), not "not found" --
      there is no hidden "apply library" command sitting in the palette.
    - `debug-adapter.cjs` was read in full: no restart/reload-library
      capability is advertised or implemented there either.

    Only the native in-game Script Editor's "Apply & restart all" button
    actually invalidates that cache, and it has no external hook in the
    currently shipped tooling. So rather than call launch_in_game() and print
    a misleading "launched in game" while the script silently keeps running
    stale library code, this only tells the operator which scripts need a
    manual Apply in-game.
    """
    if not changed_keys or not opts.auto or opts.dry_run:
        return
    closure = lib_dependency_closure(lib_index)
    hit_stems = []
    for path in sorted(opts.save_dir.glob("*.py")):
        if path.stem in skip_stems or not is_candidate(path, opts.save_dir):
            continue
        text = read(path)
        if text is None:
            continue
        direct = {n for n in parse_module_imports(text) if n in lib_index}
        reaches = set(direct)
        for dep in direct:
            reaches |= closure.get(dep, set())
        if reaches & changed_keys:
            hit_stems.append(path.stem)
    if hit_stems:
        warn("  auto  lib changed (%s) -- %d running script(s) need a manual Apply & restart all in-game: %s" %
             (", ".join(sorted(changed_keys)), len(hit_stems), ", ".join(hit_stems)))


def sync_all(script_index: dict, lib_index: dict, opts: Options, on_lib_changed=None) -> int:
    """Full pass: mirror lib/, fill matched script slots, stage the rest.

    on_lib_changed, when given, replaces the immediate relaunch_lib_dependents()
    call with on_lib_changed(changed_lib_keys, launched_stems) -- used by
    Watcher to debounce a burst of lib/ edits into one relaunch instead of one
    per file (see Watcher._note_lib_changed()). `once` (no callback) keeps the
    immediate relaunch: a single one-shot run has no "still mid-edit" risk to
    wait out.
    """
    materialized = materialize_missing_slots(opts)
    changed_lib_keys = sync_lib(lib_index, opts)
    written = materialized + len(changed_lib_keys)
    launched_stems: set = set()
    for path in sorted(opts.save_dir.glob("*.py")):
        if sync_file(path, script_index, opts, quiet_skips=not opts.verbose):
            written += 1
            if opts.auto:
                launched_stems.add(path.stem)
    tidy_unmatched(script_index, opts)
    if changed_lib_keys and on_lib_changed is not None:
        on_lib_changed(changed_lib_keys, launched_stems)
    else:
        relaunch_lib_dependents(changed_lib_keys, lib_index, opts, launched_stems)
    return written


def write_resolved_stubs(save_dir: Path) -> None:
    """Copy the active save's game-API stubs (the restricted-stdlib shims and
    `user_stubs.py` sitting flat at the save root) into .pyright-resolved/stubs/,
    so pyrightconfig.json can point Pyright at a repo-relative, git-ignored
    path instead of a raw AppData path - portable across machines/drives and
    scoped to just the current user's active save, not every account/save on
    the box."""
    dest_dir = RESOLVED_PREVIEW_DIR / "stubs"
    if dest_dir.is_dir():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(save_dir.glob("*.pyi")) + [save_dir / "user_stubs.py"]
    copied = 0
    for source in sources:
        if source.is_file():
            shutil.copyfile(source, dest_dir / source.name)
            copied += 1
    ok("Resolved stubs: %d file(s) -> %s" % (copied, show(dest_dir)))


def write_resolved_preview(scripts_dir: Path, active_tier: str, save_dir: Path) -> None:
    """Materialize the tier-resolved lib/ into .pyright-resolved/lib/ so
    Pyright can resolve `from lib.x import ...` for source under scripts/,
    where there is no single lib/ directory to point at directly. Also
    refreshes the game-API stubs (see write_resolved_stubs)."""
    chain = tier_chain(scripts_dir, active_tier)
    lib_index, conflicts = resolve_category(scripts_dir, chain, LIB_CATEGORY)
    report_conflicts(conflicts)
    dest_dir = RESOLVED_PREVIEW_DIR / "lib"
    if dest_dir.is_dir():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for key, source in lib_index.items():
        shutil.copyfile(source, dest_dir / f"{key}.py")
    ok("Resolved preview for tier %s: %d lib module(s) -> %s" % (active_tier, len(lib_index), show(dest_dir)))
    write_resolved_stubs(save_dir)


# ------------------------------------------------------------------- options
SaveOpt = typer.Option(None, "--save-dir", "-s", envvar="CT_SAVE_DIR",
                        help="Save scripts directory. Auto-detects the newest save.")
ScriptsOpt = typer.Option(DEFAULT_SCRIPTS, "--scripts-dir", envvar="CT_SCRIPTS_DIR",
                           help="Tiered scripts/ tree to sync from.")
StrictOpt = typer.Option(False, "--strict",
                          help="Only fill truly blank files (not comment/docstring stubs).")
DryOpt = typer.Option(False, "--dry-run", "-n", help="Report what would change.")
VerboseOpt = typer.Option(False, "--verbose", "-v", help="Also report files that were skipped.")
NoRenumberOpt = typer.Option(False, "--no-renumber",
                              help="Copy verbatim; do not point the script's own id at the slot.")
MagicOpt = typer.Option(DEFAULT_MAGIC, "--magic", envvar="CT_MAGIC")
PullOpt = typer.Option(DEFAULT_PULL, "--pull-magic", envvar="CT_PULL_MAGIC")
def _known_tiers_blurb() -> str:
    # Best-effort help text only - a bad tier name under the *default*
    # scripts/ dir shouldn't crash --help; the real validation (and a hard
    # error) happens per-command in resolve_active_tier, against whatever
    # --scripts-dir actually got passed.
    try:
        return ", ".join(discover_tiers(DEFAULT_SCRIPTS)) or "(none found)"
    except TierNamingError:
        return "(run `status` to see - one of them has a naming issue)"


ForceTierOpt = typer.Option(None, "--force-tier",
                             help="Skip save-state detection and use this tier for one run. "
                                  "Known tiers (under %s): %s" % (DEFAULT_SCRIPTS, _known_tiers_blurb()))
AutoOpt = typer.Option(False, "--auto",
                        help="Also launch filled/updated slots in-game via DAP. "
                             "User-invoked automation, not on by default.")
AutoDebounceOpt = typer.Option(30.0, "--auto-debounce",
                                help="watch --auto only: seconds of lib/ quiet time to wait before "
                                     "relaunching dependent scripts, re-extended by every further lib/ "
                                     "edit seen in that window - avoids pushing a still-mid-edit, "
                                     "inconsistent set of lib/ files into a live restart.")


def make_opts(save_dir, scripts_dir, strict, dry_run, verbose, no_renumber, magic,
              pull=DEFAULT_PULL, force_tier=None, auto=False, auto_debounce=30.0) -> Options:
    save = resolve_save(save_dir)
    if not scripts_dir.is_dir():
        err("Not a directory: %s" % scripts_dir)
        raise typer.Exit(2)
    opts = Options(save, scripts_dir, strict, dry_run, verbose, not no_renumber, magic, pull, force_tier, auto, auto_debounce)
    opts.active_tier = resolve_active_tier(scripts_dir, save, force_tier)
    return opts


@app.command()
def status(save_dir: Optional[Path] = SaveOpt, scripts_dir: Path = ScriptsOpt,
           strict: bool = StrictOpt, no_renumber: bool = NoRenumberOpt,
           magic: str = MagicOpt, pull: str = PullOpt, force_tier: Optional[str] = ForceTierOpt):
    """Show the resolved tier, the scripts/lib mapping, and what each save script would do."""
    opts = make_opts(save_dir, scripts_dir, strict, False, False, no_renumber, magic, pull, force_tier)
    typer.echo("Active tier: %s%s" % (opts.active_tier, "  (forced)" if force_tier else ""))
    script_index, lib_index, conflicts = build_index(opts.scripts_dir, opts.active_tier)
    report_conflicts(conflicts)

    typer.echo("\nResolved scripts (%d):" % len(script_index))
    for key, path in sorted(script_index.items()):
        typer.echo("  %-24s %s" % (key, show(path)))
    typer.echo("\nResolved lib/ (%d):" % len(lib_index))
    for key, path in sorted(lib_index.items()):
        typer.echo("  %-24s %s" % (key, show(path)))

    missing = missing_slot_sources(opts.save_dir)
    if missing:
        typer.echo("\nKnown to the game, no file on disk yet (%d) - `once`/`watch` will materialize these from workspace state:" % len(missing))
        for sid in sorted(missing):
            typer.echo("  %-24s %s" % (sid + ".py", "has code" if missing[sid].strip() else "empty"))

    staged = sorted(opts.unmatched_dir.glob("*.py")) if opts.unmatched_dir.is_dir() else []
    if staged:
        typer.echo("\nStaged in %s (%d), waiting to be written and moved:" % (show(opts.unmatched_dir), len(staged)))
        for path in staged:
            text = read(path) or ""
            typer.echo("  %-24s %s" % (path.name, "blank" if not text.strip() else "in progress"))

    files = sorted(p for p in opts.save_dir.glob("*.py") if is_candidate(p, opts.save_dir))
    typer.echo("\nSave scripts (%d):" % len(files))
    for path in files:
        text = read(path) or ""
        source = script_index.get(match_key(path.stem))
        pulled, _ = parse_magic(text, opts.pull)
        marked, _ = parse_magic(text, opts.magic)
        fillable = marked or is_empty(text, opts.strict)
        if pulled:
            state = "marked %r -> would pull to %s" % (opts.pull, show(source) if source else show(opts.unmatched_dir / path.name))
        elif not fillable:
            state = "has code, left alone"
        elif source is None:
            state = ("marked %r, " % opts.magic if marked else "empty, ") + "no match -> would stage"
        else:
            state = ("marked %r -> " % opts.magic if marked else "empty -> ") + "would fill from %s" % show(source)
            names = find_placeholders(read(source) or "")
            if names:
                state += "  (asks for: %s)" % ", ".join(n for n, _ in names)
        typer.echo("  %-28s %s" % (path.name, state))
    typer.echo("")


@app.command()
def once(save_dir: Optional[Path] = SaveOpt, scripts_dir: Path = ScriptsOpt,
         strict: bool = StrictOpt, dry_run: bool = DryOpt, verbose: bool = VerboseOpt,
         no_renumber: bool = NoRenumberOpt, magic: str = MagicOpt, pull: str = PullOpt,
         force_tier: Optional[str] = ForceTierOpt, auto: bool = AutoOpt):
    """Fill every empty script that is already in the save directory, and sync lib/."""
    opts = make_opts(save_dir, scripts_dir, strict, dry_run, verbose, no_renumber, magic, pull, force_tier, auto)
    typer.echo("Active tier: %s%s" % (opts.active_tier, "  (forced)" if force_tier else ""))
    script_index, lib_index, conflicts = build_index(opts.scripts_dir, opts.active_tier)
    report_conflicts(conflicts)
    typer.echo("Syncing %s" % opts.save_dir)
    n = sync_all(script_index, lib_index, opts)
    typer.echo("%s %d file(s)." % ("Would sync" if dry_run else "Synced", n))
    if not dry_run:
        write_resolved_preview(opts.scripts_dir, opts.active_tier, opts.save_dir)


@app.command(name="resolve-preview")
def resolve_preview(scripts_dir: Path = ScriptsOpt, save_dir: Optional[Path] = SaveOpt,
                     force_tier: Optional[str] = ForceTierOpt):
    """Materialize the tier-resolved lib/ into .pyright-resolved/lib/ for Pyright."""
    save = resolve_save(save_dir)
    active_tier = resolve_active_tier(scripts_dir, save, force_tier)
    write_resolved_preview(scripts_dir, active_tier, save)


class Watcher:
    def __init__(self, opts: Options, delay: float = 0.4):
        self.opts, self.delay = opts, delay
        self.script_index, self.lib_index, self.conflicts = build_index(opts.scripts_dir, opts.active_tier)
        report_conflicts(self.conflicts)
        self.pending: dict = {}
        self.repo_due = None
        self.last_tier_check = time.monotonic()
        # Debounced --auto relaunch state (see _note_lib_changed()/drain()):
        # a lib/ edit doesn't fire relaunch_lib_dependents() immediately --
        # it accumulates here and pushes auto_launch_due out by
        # opts.auto_debounce seconds, so a burst of related lib/ edits (e.g.
        # touching both vehicle_mining.py and production.py for one fix)
        # settles into a single relaunch of a CONSISTENT set of files instead
        # of restarting dependent scripts once per file mid-edit.
        self.pending_lib_changes: set = set()
        self.pending_lib_skip_stems: set = set()
        self.auto_launch_due = None

    def note_save(self, raw_path):
        path = Path(str(raw_path))
        if is_candidate(path, self.opts.save_dir):
            self.pending[path] = time.monotonic() + self.delay

    def note_repo(self, raw_path):
        path = Path(str(raw_path))
        if path.suffix != ".py" and path.name != ".criteria":
            return
        try:
            if UNMATCHED in path.relative_to(self.opts.scripts_dir).parts:
                return
        except ValueError:
            pass
        self.repo_due = time.monotonic() + self.delay

    def rebuild(self):
        # A source edit doesn't change the active tier, but the tier can
        # change on its own as the save progresses, so re-check it too.
        self.opts.active_tier = resolve_active_tier(self.opts.scripts_dir, self.opts.save_dir, self.opts.force_tier)
        self.script_index, self.lib_index, self.conflicts = build_index(self.opts.scripts_dir, self.opts.active_tier)
        report_conflicts(self.conflicts)
        self.sweep()

    def sweep(self):
        on_lib_changed = self._note_lib_changed if (self.opts.auto and not self.opts.dry_run) else None
        sync_all(self.script_index, self.lib_index, self.opts, on_lib_changed=on_lib_changed)
        if not self.opts.dry_run:
            write_resolved_preview(self.opts.scripts_dir, self.opts.active_tier, self.opts.save_dir)

    def _note_lib_changed(self, changed_keys: set, launched_stems: set) -> None:
        """sync_all()'s on_lib_changed callback: defer the relaunch instead of
        firing it inline (see Watcher.__init__'s docstring comment)."""
        self.pending_lib_changes |= changed_keys
        self.pending_lib_skip_stems |= launched_stems
        self.auto_launch_due = time.monotonic() + self.opts.auto_debounce
        ok("  auto  lib changed (%s); relaunching dependents in %.0fs unless more lib/ edits arrive" %
           (", ".join(sorted(changed_keys)), self.opts.auto_debounce))

    def drain(self):
        now = time.monotonic()
        if self.auto_launch_due is not None and self.auto_launch_due <= now:
            changed_keys, skip_stems = self.pending_lib_changes, self.pending_lib_skip_stems
            self.pending_lib_changes, self.pending_lib_skip_stems, self.auto_launch_due = set(), set(), None
            relaunch_lib_dependents(changed_keys, self.lib_index, self.opts, skip_stems)
        # Cheap periodic re-check so a tier advance (new tech unlocked
        # mid-session) is picked up even with no repo-side file change.
        if now - self.last_tier_check > 5.0:
            self.last_tier_check = now
            new_tier = resolve_active_tier(self.opts.scripts_dir, self.opts.save_dir, self.opts.force_tier)
            if new_tier != self.opts.active_tier:
                ok("  tier  %s -> %s" % (self.opts.active_tier, new_tier))
                self.opts.active_tier = new_tier
                self.script_index, self.lib_index, self.conflicts = build_index(self.opts.scripts_dir, new_tier)
                report_conflicts(self.conflicts)
                self.sweep()
            # Same cadence covers materialize_missing_slots() too: a newly
            # built (or newly re-equipped) machine's script slot shows up in
            # codeterraform-workspace.json well before the game ever writes
            # it a `.py` file - watching save_dir/*.py (as note_save() does)
            # has nothing to see until that file exists, so this has to be
            # polled rather than event-driven. Any file this actually writes
            # is then picked up by the filesystem observer itself (it's a
            # real write into the watched save_dir) and flows into the
            # normal self.pending fill path - no extra handling needed here.
            materialize_missing_slots(self.opts)
        if self.repo_due is not None and self.repo_due <= now:
            self.repo_due = None
            self.rebuild()
        for path, due in [(p, d) for p, d in self.pending.items() if d <= now]:
            del self.pending[path]
            if path.exists():
                sync_file(path, self.script_index, self.opts)


class Events(FileSystemEventHandler):
    def __init__(self, note):
        self.note = note

    def on_created(self, event):
        if not event.is_directory:
            self.note(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.note(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self.note(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.note(event.src_path)
            self.note(event.dest_path)


@app.command()
def watch(save_dir: Optional[Path] = SaveOpt, scripts_dir: Path = ScriptsOpt,
          strict: bool = StrictOpt, dry_run: bool = DryOpt, verbose: bool = VerboseOpt,
          no_renumber: bool = NoRenumberOpt, magic: str = MagicOpt, pull: str = PullOpt,
          force_tier: Optional[str] = ForceTierOpt, auto: bool = AutoOpt,
          auto_debounce: float = AutoDebounceOpt,
          poll: bool = typer.Option(False, "--poll", help="Poll instead of using filesystem events.")):
    """Watch the save directory and scripts/, filling and re-tiering as things change."""
    opts = make_opts(save_dir, scripts_dir, strict, dry_run, verbose, no_renumber, magic, pull, force_tier, auto, auto_debounce)
    watcher = Watcher(opts)

    typer.echo("Save     %s" % opts.save_dir)
    typer.echo("Scripts  %s (tier %s)" % (opts.scripts_dir, opts.active_tier))
    typer.echo("Staging  %s for game files with no match" % show(opts.unmatched_dir))
    if magic:
        typer.echo("Marker   %r at the top of a game file fills it from scripts/" % magic)
    if pull:
        typer.echo("Marker   %r at the top of a game file copies it back into scripts/" % pull)
    if auto:
        typer.echo("Auto     lib/ relaunch debounced %.0fs (resets on every further lib/ edit)" % auto_debounce)
        warn("Auto-launch enabled: filled/updated slots will be started in-game via DAP.")
    if dry_run:
        warn("Dry run: nothing will be written.")
    watcher.sweep()

    observer = (PollingObserver if poll else Observer)()
    observer.schedule(Events(watcher.note_save), str(opts.save_dir), recursive=False)
    observer.schedule(Events(watcher.note_repo), str(opts.scripts_dir), recursive=True)
    observer.start()
    typer.echo("Ready. Ctrl-C to stop.")
    try:
        while True:
            time.sleep(0.2)
            # A transient error here (a file briefly locked mid-write by the
            # game, a momentarily-unreadable workspace snapshot, ...) used to
            # propagate straight out of this loop and kill the whole watcher
            # permanently -- it would then sit in a scrolled-away terminal
            # looking normal while silently doing nothing, forever, until
            # manually noticed and restarted (this is suspected to be exactly
            # what happened to a live session this session: newly-deployed
            # machines' blank slots went unfilled with no visible error).
            # Log and keep looping instead -- only Ctrl-C should ever stop
            # a long-running watch session.
            try:
                watcher.drain()
            except Exception as exc:
                err("  drain error (watcher still running): %s" % exc)
    except KeyboardInterrupt:
        typer.echo("\nStopped.")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    app()
