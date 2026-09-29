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
    python devtools/scripts_sync.py watch            # keep running and push changes as they happen

scripts/ is the only source of truth. Every save slot with a confident match
(see below) is overwritten with its resolved source whenever the two differ
(old copy backed up to devtools/.sync-backups/), then restarted in game over
the external-command channel (`"action": "run"`) if it was running or was
just filled from empty. A slot whose imports reach a lib/ module the game
hasn't applied yet (deployed file != the Library's `deployedSource` in
codeterraform-workspace.json) is still pushed but not restarted: a restart
would run the new script against the stale cached lib, and only the in-game
"Apply & restart all" swaps that cache. `--no-restart` pushes only.

Matching ignores a trailing `_<number>` (`bio_lab_1.py` matches `bio_lab.py`),
except for machine types listed in ROLE_MATCHED (currently just `panel`),
where each numbered instance is a genuinely distinct, hand-authored script
(status card, vehicle fleet card, headless automation worker, ...) and the
slot number is whatever the game happened to assign in that save. Source
files for these are named by role (`vehicles_panel.py`, `drones_panel.py`)
and start with a `# ct-panel: <role>` marker line. A save slot `panel_N.py`
is paired with its source by, in order:
  1. the `# ct-panel: <role>` marker in the slot's current code - every slot
     filled from source carries it;
  2. the slot's first comment line equal to a role source's first comment
     line (after the marker) - bridges slots filled before markers existed;
  3. an empty slot takes the one role no other slot of that type holds yet.
     With several unpaired roles it is skipped with a warning; type the
     `# ct-panel: <role>` line into it in game to choose.

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
used as a source): write the script there, then move it into a category.
A slot with code and no match is left alone. Filling renumbers the source's
own instance id to the slot's (see renumber()).

A newly built (or newly re-equipped) machine's script slot exists in the
game's own `codeterraform-workspace.json` (`context.scripts`, sibling of the
save's `.py` files) well before the game ever writes a `.py` file for it on
disk - confirmed live, that file only appears once a human opens the slot in
the in-game script editor at least once. Watching the save directory for new
files (as `watch` otherwise does) can never see such a slot - there is
nothing to watch yet. `materialize_missing_slots()` polls that JSON instead
(every 5s in `watch`, once up front in `once`) and writes a real `.py` file
for any slot missing one, using the JSON's own live `source` text - never a
blank stub. Once materialized, the slot flows through the normal push
pipeline like any other file.

A source script may itself contain `${VAR}` / `${VAR:default}` placeholders
(same syntax as `early_game_runner/auto_deploy.py`'s substitution, kept
identical on purpose) for values only the operator knows at deploy time -
e.g. `pioneer.py`'s destination outpost. `sync_file()` resolves each one
per save slot from, in order: the value the slot's current code holds at
the placeholder's position (see infer_placeholders()) - so an in-game edit
sticks and replaces the cached answer - the answer cached in
`devtools/.sync-backups/script_params.json` (gitignored), the template default when the slot already has code
(code that predates a placeholder never set it), an interactive prompt for
an empty slot. Answers are cached.
"""
import ast
import json
import os
import re
import shutil
import sys
import time
import uuid
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

# restart_in_game()'s retry cushion: the game polls disk on its own cadence,
# so a slot file we just created may not be registered yet. Total extra wait
# if every attempt needs it: 0.5 + 1.0 + 2.0 = 3.5s after the first try.
RESTART_RETRY_DELAYS_S = (0.5, 1.0, 2.0)

# Machine types where each numbered instance is a genuinely distinct,
# hand-authored script with its own role (see module docstring). The game
# picks slot numbers per save and can't rename a slot, so the number carries
# no meaning: source files are named by role (`drones_panel.py`, i.e. any
# stem ending in `_<type>`) and carry a `# ct-<type>: <role>` header marker.
# A save slot is paired with its source by role, never by number - see
# role_for_slot().
ROLE_MATCHED = {"panel"}
ROLE_SCAN_LINES = 15                # how far into a file the role marker may sit

# The game owns these; never write to them.
RESERVED = {"user_stubs.py"}
SKIP_DIRS = {"lib"}
SKIP_SUFFIXES = (".codeterraform-write.bak",)
SKIP_PATTERNS = (re.compile(r"\.codeterraform-retired-"),)
TRAILING_INDEX = re.compile(r"_\d+$")

SHORT_HELP = (
    "Sync the tiered scripts/ tree into a Code: Terraform save's script directory.\n\n"
    "Commands: status | once | watch | resolve-preview | register-libs. Run `<command> --help` for its "
    "options, or see the module docstring in devtools/scripts_sync.py for the full "
    "tiering/matching rules.\n\n"
    "once/watch push every matched slot and restart it in game; --no-restart pushes only."
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
    force_tier: Optional[str] = None
    restart: bool = True
    active_tier: str = field(default="", init=False)
    lib_index: dict = field(default_factory=dict, init=False)
    lib_closure: dict = field(default_factory=dict, init=False)

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
    `plant_recipes` is the number of discovered seed recipes
    (`state.planet.plants.discoveredRecipes`, the Flora journal), used by the
    `plant_recipes` criterion (8_planting unlocks once all 15 are known).
    Also carries three fleet handoff fields read from the same parse
    (see upgrade_fill_for()): `machine_types` ({machine id: typeId}),
    `fleet_upgrade` and `fleet_commission` (the `fleet.upgrade` /
    `fleet.commission` Data Archive entries, stored in the save under
    `state.notebook.entries[key].value`, or None).
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
            "machine_types": {
                mid: m.get("typeId") for mid, m in state.get("machines", {}).items()
                if isinstance(m, dict)
            },
            "plant_recipes": len(state.get("planet", {}).get("plants", {}).get("discoveredRecipes", []) or []),
            "fleet_upgrade": (state.get("notebook", {}).get("entries", {}).get(FLEET_UPGRADE_KEY) or {}).get("value"),
            "fleet_commission": (state.get("notebook", {}).get("entries", {}).get(FLEET_COMMISSION_KEY) or {}).get("value"),
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
    stub, unless the JSON itself says the slot is empty. The live text
    matters to sync_file(): it reads placeholder values out of it, and a
    role-matched slot is paired by it. Once materialized as a real file
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
    if "plant_recipes" in criteria and state.get("plant_recipes", 0) < criteria["plant_recipes"]:
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


# Tier from which every lib module is deployed, not just the active tier's
# chain (see lib_chain()). 2_libunlock = the game's Library research.
LIB_UNLOCK_TIER_NUMBER = 2


def lib_chain(scripts_dir: Path, active_tier: str) -> list:
    """Search order for lib/ modules: the active tier's chain (active tier down
    to 0_cold_boot), then - once the save is at 2_libunlock or later - every
    HIGHER tier in ascending order.

    A module defined at or below the active tier resolves exactly as before,
    so a higher tier's override of an existing module (today only
    5_steampower/lib/power.py) stays gated behind its tier. A module that only
    exists in a higher tier is deployed anyway, from the lowest tier defining
    it: it does nothing until its machines exist, and deploying it early lets
    one entrypoint (panel_4.py's Biomass Mixer gate) serve every tier instead
    of needing a per-tier copy."""
    chain = tier_chain(scripts_dir, active_tier)
    number = tier_number(active_tier)
    if number is None or number < LIB_UNLOCK_TIER_NUMBER:
        return chain
    tiers = discover_tiers(scripts_dir)
    return chain + tiers[tiers.index(active_tier) + 1:]


# -------------------------------------------------------------------- mapping
def base_name(stem: str) -> str:
    """`bio_lab_1` -> `bio_lab`. Slot numbers differ between source and save."""
    return TRAILING_INDEX.sub("", stem)


def match_key(stem: str) -> str:
    """The key a source file is looked up by: the slot-number-stripped base
    name. A role-matched save slot (see ROLE_MATCHED) keeps its exact stem,
    which no source file uses - such slots resolve through role_for_slot()."""
    base = base_name(stem)
    return stem if base in ROLE_MATCHED else base


def _role_marker(text: str, slot_type: str) -> Optional[str]:
    """`<role>` from a `# ct-<slot_type>: <role>` line near the top of text."""
    pattern = re.compile(r"#\s*ct-%s\s*:\s*([A-Za-z0-9_]+)\s*$" % re.escape(slot_type))
    for line in text.splitlines()[:ROLE_SCAN_LINES]:
        m = pattern.match(line.strip())
        if m:
            return m.group(1)
    return None


def _header_line(text: str, slot_type: str) -> Optional[str]:
    """First non-blank line that isn't a role marker."""
    for line in text.splitlines()[:ROLE_SCAN_LINES]:
        s = line.strip()
        if s and not _role_marker(s, slot_type):
            return s
    return None


def role_sources(index: dict, slot_type: str) -> dict:
    """{role: source path} for every source named `<something>_<slot_type>`."""
    suffix = "_" + slot_type
    return {k: p for k, p in index.items() if k.endswith(suffix)}


def role_for_slot(stem: str, text: str, index: dict, save_dir: Optional[Path] = None):
    """(role, how) for a role-matched save slot, or (None, why-not).

    Resolution order is documented in the module docstring. A marker naming no
    source is reported rather than falling through to the next rule: it is a
    typo to fix, not a guess to make. The empty-slot rule needs save_dir to see
    which roles the other slots of this type already hold.
    """
    slot_type = base_name(stem)
    roles = role_sources(index, slot_type)
    known = ", ".join(sorted(roles)) or "none"

    given = _role_marker(text, slot_type)
    if given:
        role = given if given in roles else (given + "_" + slot_type if given + "_" + slot_type in roles else None)
        if role is None:
            return None, "ct-%s marker names unknown role %r (known: %s)" % (slot_type, given, known)
        return role, "ct-%s marker" % slot_type

    header = _header_line(text, slot_type)
    if header:
        hits = [r for r, p in roles.items() if _header_line(read(p) or "", slot_type) == header]
        if len(hits) == 1:
            return hits[0], "header match"
        if len(hits) > 1:
            return None, "header matches several roles: %s" % ", ".join(sorted(hits))
        return None, "code matches no role (known: %s)" % known

    if save_dir is None:
        return None, "empty"
    taken = set()
    for other in save_dir.glob("%s_*.py" % slot_type):
        if other.stem != stem and base_name(other.stem) == slot_type and is_candidate(other, save_dir):
            role, _ = role_for_slot(other.stem, read(other) or "", index)
            if role:
                taken.add(role)
    free = sorted(set(roles) - taken)
    if len(free) == 1:
        return free[0], "only unpaired role"
    if not free:
        return None, "empty, every role already has a slot"
    return None, "empty, several unpaired roles (%s) - type `# ct-%s: <role>` into it in game" % (", ".join(free), slot_type)


def source_for(stem: str, text: str, index: dict, save_dir: Optional[Path] = None):
    """(source path or None, note) for a save slot. The note names how a
    role-matched slot was paired, or why it wasn't; None for plain slots."""
    if base_name(stem) not in ROLE_MATCHED:
        return index.get(match_key(stem)), None
    role, how = role_for_slot(stem, text, index, save_dir)
    return (index[role], "role %s via %s" % (role, how)) if role else (None, how)


def split_index(stem: str):
    m = re.search(r"_(\d+)$", stem)
    return (stem[:m.start()], m.group(1)) if m else (stem, None)


def renumber(text: str, src_stem: str, dst_stem: str):
    """Point the script's *own* instance id at the slot it is being filled into.

    Only the source's exact self id is rewritten; every other numbered id is
    left alone (see vakermit's ct_sync.py docstring for why). A source with no
    number (every role-matched source, e.g. `drones_panel`), or one where
    src_stem == dst_stem already, is never rewritten.
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
    lib_index, lib_conflicts = resolve_category(scripts_dir, lib_chain(scripts_dir, active_tier), LIB_CATEGORY)
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


# Fleet upgrade handoff (scripts/4_controlpanel/lib/fleet_upgrade.py): when
# the in-game coordinator replaces a drone with a bigger chassis, the new
# drone gets a new id and an empty script slot. The coordinator writes the
# swap to the Data Archive key below BEFORE deploying (state "announced"),
# then records `lineage[new_id] = {"from": old_id, ...}` right after. Both
# reach the save file on the next autosave (~30 s), and upgrade_fill_for()
# uses them to fill the new slot with the old drone's parameters instead of
# prompting. Interim: reading the save for this is tracked for retirement in
# TODO.md.
FLEET_UPGRADE_KEY = "fleet.upgrade"
UPGRADE_SLOT_KEY = "drone"  # match_key() of the only slots a drone swap creates
# COMMISSION card handoff (scripts/4_controlpanel/lib/fleet_commission.py):
# a commissioned drone gets a `fleet.upgrade` lineage entry with "job" (no
# "from") whose params carry HOME_DEPOT; a commissioned Pioneer gets
# `fleet.commission` lineage[new_id]["home_base"] (None = home). Both are
# written in the same pass as the deploy, so they reach the save together
# with the new machine.
FLEET_COMMISSION_KEY = "fleet.commission"
COMMISSION_SLOT_KEY = "pioneer"  # match_key() of a commissioned Pioneer's slot
UPGRADE_PENDING_STATES = ("announced", "swapping")

# Slots upgrade_fill_for() said to hold (save not caught up yet). `watch`
# re-queues these every few seconds; `once` just reports them.
HELD_SLOTS: set = set()

# Role-matched slots skipped for lack of a role -> the reason last printed,
# so `watch` warns once per reason instead of on every pass.
ROLELESS_WARNED: dict = {}


def commission_fill_for(state: dict, stem: str):
    """upgrade_fill_for() for a Pioneer slot: ("inherit", source, {"HOME_BASE"})
    when the COMMISSION card deployed it, ("hold", reason, None) while a
    commissioned Pioneer is being deployed and the save predates this slot's
    machine, else ("normal", None, None)."""
    commission = state.get("fleet_commission") or {}
    if not isinstance(commission, dict):
        return ("normal", None, None)
    lineage = commission.get("lineage") or {}
    entry = lineage.get(stem) if isinstance(lineage, dict) else None
    if isinstance(entry, dict):
        home = entry.get("home_base")
        return ("inherit", "commission %s" % entry.get("job"), {"HOME_BASE": home if home else "None"})
    if (state.get("machine_types") or {}).get(stem) is None:
        deploying = [
            j for j in commission.get("jobs") or []
            if isinstance(j, dict) and j.get("kind", "pioneer") == "pioneer" and j.get("state") == "deploying"
        ]
        if deploying:
            return ("hold", "machine not in save yet, Pioneer %s deploying (waiting for the next autosave)" % deploying[0].get("id"), None)
    return ("normal", None, None)


def upgrade_fill_for(save_dir: Path, stem: str):
    """How sync_file() should treat an empty slot with respect to a fleet
    upgrade or a COMMISSION card deploy.

    Returns ("inherit", source, params) when the slot is a replacement drone
    (lineage names it, or it is a new drone slot of the kind the one pending
    announced swap deploys), a commissioned drone (lineage with "job") or a
    commissioned Pioneer (commission_fill_for()), ("hold", reason, None) when
    the save file is too old to tell yet, else ("normal", None, None)."""
    state = read_save_state(save_dir)
    if not state:
        return ("normal", None, None)
    if match_key(stem) == COMMISSION_SLOT_KEY:
        return commission_fill_for(state, stem)
    upgrade = state.get("fleet_upgrade") or {}
    if not isinstance(upgrade, dict):
        return ("normal", None, None)
    lineage = upgrade.get("lineage") or {}
    entry = lineage.get(stem) if isinstance(lineage, dict) else None
    if isinstance(entry, dict) and entry.get("from"):
        return ("inherit", entry["from"], entry.get("params") or {})
    if isinstance(entry, dict) and entry.get("job"):
        return ("inherit", "commission %s" % entry["job"], entry.get("params") or {})
    if match_key(stem) != UPGRADE_SLOT_KEY:
        return ("normal", None, None)

    machine_type = (state.get("machine_types") or {}).get(stem)
    drones = upgrade.get("drones") or {}
    pending = [
        (old_id, e) for old_id, e in (drones.items() if isinstance(drones, dict) else [])
        if isinstance(e, dict) and e.get("state") in UPGRADE_PENDING_STATES and e.get("new_id") in (None, stem)
    ]
    if machine_type is None:
        # The slot exists (workspace state) but the save predates its machine:
        # an announced swap could still be on its way. Wait for the next save.
        return ("hold", "machine not in save yet (waiting for the next autosave)", None)
    if len(pending) == 1:
        old_id, e = pending[0]
        if machine_type == e.get("target_kind"):
            return ("inherit", old_id, e.get("params") or {})
        return ("normal", None, None)  # a hand-deployed drone of another kind
    return ("normal", None, None)


def inherit_placeholders(save_dir: Path, stem: str, old_id: str, params: dict, placeholders: list, dry_run: bool) -> dict:
    """Answers for a replacement drone's placeholders, never prompting: the old
    slot's cached answers first, then the params the old drone stored in the
    archive before its swap, then the template defaults. Cached under the new
    slot too (not under --dry-run)."""
    cache = load_params_cache()
    old_cache = cache.get("%s/%s" % (save_dir.name, old_id), {})
    answers = {}
    for name, default in placeholders:
        if name in old_cache:
            answers[name] = old_cache[name]
        elif name in params and params[name] is not None:
            answers[name] = str(params[name])
        else:
            answers[name] = default
    if not dry_run:
        cache["%s/%s" % (save_dir.name, stem)] = dict(answers)
        save_params_cache(cache)
    return answers


def infer_placeholders(template: str, current: str) -> dict:
    """{name: value} read out of a slot's current code: every template line
    holding a placeholder becomes a regex (literal text around it, the
    placeholder as a capture) matched against current. First match wins;
    a line whose surrounding text changed since simply doesn't match."""
    found: dict = {}
    for line in template.splitlines():
        marks = list(PLACEHOLDER.finditer(line))
        if not marks or all(m.group(1) in found for m in marks):
            continue
        pattern, pos = "", 0
        for m in marks:
            pattern += re.escape(line[pos:m.start()]) + "(.*?)"
            pos = m.end()
        pattern += re.escape(line[pos:])
        hit = re.search(r"^" + pattern.strip() + r"\s*$", current, re.MULTILINE)
        if hit:
            for m, value in zip(marks, hit.groups()):
                found.setdefault(m.group(1), value)
    return found


# The Pioneer template has no DESTINATION_OUTPOST_ID: every hauler pulls TO
# its HOME_BASE. A slot (cache or code) still holding a real destination id
# from push-hauler days is re-homed there, so an ore hauler parked at a mine
# pulls to home instead of toward the mine.
# "*"/"any"/"%" (the old pull wildcard) and empty keep HOME_BASE.
RETIRED_DESTINATION = "DESTINATION_OUTPOST_ID"
RETIRED_DESTINATION_KEEP = ("", "None", "*", "any", "%")
RETIRED_DESTINATION_LINE = re.compile(r'^DESTINATION_OUTPOST_ID\s*=\s*"([^"]*)"\s*$', re.MULTILINE)


def rehome_retired_destination(stem: str, placeholders: list, slot_cache: dict, current: str) -> Optional[str]:
    """New HOME_BASE for a slot that still carries a retired push-hauler
    DESTINATION_OUTPOST_ID (see RETIRED_DESTINATION), else None. Drops the
    retired key from slot_cache either way. Only for templates that ask for
    HOME_BASE and no longer ask for the destination."""
    names = {name for name, _default in placeholders}
    if "HOME_BASE" not in names or RETIRED_DESTINATION in names:
        return None
    value = slot_cache.pop(RETIRED_DESTINATION, None)
    if value is None and current.strip():
        hit = RETIRED_DESTINATION_LINE.search(current)
        value = hit.group(1) if hit else None
    if value is None or value in RETIRED_DESTINATION_KEEP:
        return None
    home = "None" if value == "outpost_home" else value
    warn("  note  %-28s push hauler to %s: re-homed there (HOME_BASE=%s), now pulls to it" % (stem, value, home))
    return home


def resolve_placeholders(save_dir: Path, stem: str, placeholders: list, dry_run: bool,
                         template: str = "", current: str = "") -> dict:
    """Answers for every (name, default) in placeholders, from: a retired
    push-hauler destination (rehome_retired_destination(); beats both
    below), the value the slot's current code holds (infer_placeholders();
    an in-game edit overrides the cache), this save slot's cached answers,
    the template default when the slot already has
    code (it predates the placeholder), an interactive prompt for an empty
    slot (blocking - fine under
    `watch`: the filesystem observer runs on its own thread and just queues
    further events while we wait on input()). New answers are cached.
    Under --dry-run nothing is prompted or cached - unknown names fall back
    to their template defaults, as a preview of what a real run would fill in."""
    cache = load_params_cache()
    key = "%s/%s" % (save_dir.name, stem)
    slot_cache = dict(cache.get(key, {}))
    inferred = infer_placeholders(template, current) if current.strip() else {}
    answers: dict = {}
    had_retired = RETIRED_DESTINATION in slot_cache
    rehomed = rehome_retired_destination(stem, placeholders, slot_cache, current)
    dirty = (had_retired or rehomed is not None) and not dry_run
    if rehomed is not None:
        # The slot's code still says the old push-hauler HOME_BASE; the
        # re-homed value must beat it.
        slot_cache["HOME_BASE"] = rehomed
        inferred["HOME_BASE"] = rehomed
    for name, default in placeholders:
        if name in inferred:
            # The slot's own code wins: an operator edit made in-game is the
            # newest answer and replaces the cached one.
            answers[name] = inferred[name]
            if slot_cache.get(name) == answers[name]:
                continue
            ok("  param %-28s %s %s -> %s (in-game edit)" % (
                stem, name, slot_cache.get(name, "(uncached)"), answers[name]))
        elif name in slot_cache:
            answers[name] = slot_cache[name]
            continue
        elif dry_run:
            answers[name] = default
            continue
        elif current.strip():
            # Code that predates this placeholder never set it: the template
            # default reproduces what it did.
            answers[name] = default
        else:
            answers[name] = typer.prompt("%s: %s" % (stem, name), default=default)
        if not dry_run:
            slot_cache[name] = answers[name]
            dirty = True
    if dirty:
        cache[key] = slot_cache
        save_params_cache(cache)
    return answers


def restart_in_game(save_dir: Path, stem: str, body: str) -> bool:
    """(Re)start one script slot with body over the external-command channel
    (`"action": "run"`, same as VS Code's "Run Script in Game"): stops a
    running copy and starts body fresh. User-invoked automation (the operator
    runs this tool), not the assistant starting a live session on its own.
    Retries briefly while the game hasn't registered a just-created slot."""
    reason = None
    for attempt, delay in enumerate((0.0,) + RESTART_RETRY_DELAYS_S):
        if delay:
            time.sleep(delay)
        result = send_game_command(save_dir, "run", scriptId=stem, source=body)
        if result.get("ok"):
            ok("  run   %-28s restarted in game%s" % (stem + ".py", " (retry %d)" % attempt if attempt else ""))
            return True
        reason = result.get("reason") or result.get("status") or result.get("message")
        if reason in ("no_session", "unconfirmed", "busy"):
            break  # game unreachable: retrying won't help
    warn("  run   %-28s not restarted (%s) - is the game running with this save open?" % (stem + ".py", reason))
    return False


def libs_awaiting_apply(opts: Options) -> set:
    """lib_index keys whose resolved source differs from the code the game
    actually runs (`deployedSource` of the matching Library in
    codeterraform-workspace.json), or that the game has no Library for yet.
    Empty when the workspace file is unreadable (nothing known)."""
    context = read_workspace_context(opts.save_dir)
    if context is None:
        return set()
    running = {}
    for info in (context.get("libraryScripts") or {}).values():
        name = str(info.get("name") or "")
        if name.endswith(".py"):
            running[name[:-3]] = info.get("deployedSource")
    pending = set()
    for key, source in opts.lib_index.items():
        if key not in running or running[key] != read(source):
            pending.add(key)
    return pending


def libs_reached(text: str, opts: Options) -> set:
    """Every lib_index key text imports, directly or through other libs."""
    direct = {n for n in parse_module_imports(text) if n in opts.lib_index}
    reached = set(direct)
    for dep in direct:
        reached |= opts.lib_closure.get(dep, set())
    return reached


def slot_status(save_dir: Path, stem: str) -> Optional[str]:
    """The game's own run status for a slot ("running", "idle", ...), or None."""
    context = read_workspace_context(save_dir)
    info = (context or {}).get("scripts", {}).get(stem)
    return info.get("status") if isinstance(info, dict) else None


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
        dest.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        err("  fail  %-28s %s" % (path.name, exc))
        return False
    ok("  stage %-28s -> %s   (write it, then move it into place)" % (path.name, show(dest)))
    return True


def tidy_unmatched(index: dict, opts: Options) -> None:
    if not opts.unmatched_dir.is_dir():
        return
    for path in sorted(opts.unmatched_dir.glob("*.py")):
        # A role-matched slot never resolves by its number, so a blank one
        # staged here has nothing to wait for.
        role_slot = base_name(path.stem) in ROLE_MATCHED
        matched = index.get(match_key(path.stem))
        if matched is None and not role_slot:
            continue
        text = read(path)
        if text is None or text.strip():
            continue
        why = "now matched by %s" % show(matched) if matched else "role slot, paired by role instead"
        if opts.dry_run:
            typer.echo("  would drop %-24s (blank, %s)" % (show(path), why))
            continue
        try:
            path.unlink()
            typer.echo("  drop  %-28s blank, %s" % (show(path), why))
        except OSError:
            pass


def sync_file(path: Path, index: dict, opts: Options, quiet_skips: bool = True) -> bool:
    """Push one save slot's resolved source into it when they differ, then
    restart it in game (see module docstring). True if it was written."""
    if not is_candidate(path, opts.save_dir):
        return False
    text = read(path)
    if text is None:
        return False
    was_empty = is_empty(text, opts.strict)

    source, role_note = source_for(path.stem, text, index, opts.save_dir)
    if source is None and role_note is not None:
        # Role-matched slot with no resolvable role: staging it under its
        # slot number would be meaningless, so only say why.
        if ROLELESS_WARNED.get(path) != role_note:
            warn("  skip  %-28s %s" % (path.name, role_note))
        ROLELESS_WARNED[path] = role_note
        return False
    ROLELESS_WARNED.pop(path, None)
    if source is None:
        if not was_empty:
            if not quiet_skips:
                typer.echo("  skip  %-28s has code, no match in scripts/" % path.name)
            return False
        if not quiet_skips:
            typer.echo("  skip  %-28s no match in scripts/" % path.name)
        stage_unmatched(path, text, opts)
        return False

    template = read(source)
    if template is None:
        err("  fail  %-28s cannot read %s" % (path.name, source))
        return False
    body = template

    param_note = None
    placeholders = find_placeholders(template)
    if placeholders:
        mode, old_id, params = upgrade_fill_for(opts.save_dir, path.stem) if was_empty else ("normal", None, None)
        if mode == "hold":
            if path not in HELD_SLOTS:
                typer.echo("  hold  %-28s %s" % (path.name, old_id))
            HELD_SLOTS.add(path)
            return False
        HELD_SLOTS.discard(path)
        if mode == "inherit":
            answers = inherit_placeholders(opts.save_dir, path.stem, str(old_id), params or {}, placeholders, opts.dry_run)
            param_note = "inherited from %s: %s" % (old_id, ", ".join("%s=%s" % kv for kv in answers.items()))
        else:
            answers = resolve_placeholders(opts.save_dir, path.stem, placeholders, opts.dry_run, template, text)
            param_note = "params: %s" % ", ".join("%s=%s" % kv for kv in answers.items())
        body = render_placeholders(template, answers)

    note = None
    if opts.renumber:
        body, _, note = renumber(body, source.stem, path.stem)

    if text == body:
        return False

    parts = ([role_note] if role_note else []) + ([param_note] if param_note else []) + ([note] if note else [])
    suffix = "  [%s]" % ", ".join(parts) if parts else ""
    verb = "fill" if was_empty else "push"
    restart = opts.restart and (was_empty or slot_status(opts.save_dir, path.stem) == "running")
    blockers = sorted(libs_reached(body, opts) & libs_awaiting_apply(opts)) if restart else []

    if opts.dry_run:
        then = ("; not restarted, unapplied lib: %s" % ", ".join(blockers)) if blockers else ("; then restart" if restart else "")
        ok("  would %s %-23s <- %s%s%s" % (verb, path.name, show(source), suffix, then))
        return True

    if text.strip():
        backup(path)
    if not write_atomic(path, body):
        return False
    ok("  %-5s %-28s <- %s%s" % (verb, path.name, show(source), suffix))
    if note:
        others = other_numbered_ids(body, base_name(path.stem))
        if others:
            warn("        left as-is (check these): %s" % ", ".join(others))
    if blockers:
        warn("  run   %-28s not restarted: reaches unapplied lib %s - Apply & restart all in game"
             % (path.name, ", ".join(blockers)))
    elif restart:
        restart_in_game(opts.save_dir, path.stem, body)
    return True


def sync_lib(lib_index: dict, opts: Options) -> set:
    """Unconditional mirror of the resolved lib/ into the save's lib/.

    Unlike machine scripts, lib modules aren't slots the game creates - we own
    the whole directory. Every resolved module is copied in if its content
    differs from what's already deployed (backing up the old copy first).

    Returns the set of lib_index keys actually (re)written -- including under
    --dry-run, as a preview of what would change. A rewritten module still
    needs the in-game "Apply & restart all" before any script runs it (see
    report_unapplied_libs()).
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


# ------------------------------------------------ library registration hook
# A lib module written to the save's lib/ folder is NOT seen by the game until
# it is registered as a Library (in game: Computer -> Library -> + New, same
# name; the game then picks up the file already on disk). The VS Code
# extension's "Import File as Game Library" command does exactly that through
# the game's external-command channel, reverse-read from the bundled
# language server (server.cjs, `codeterraform/gameCommand` handler):
#   .codeterraform/command.lock   exclusive-create lock, stale after 30 s
#   .codeterraform/command.json   {version: 1, requestId, issuedAt (ms),
#                                  session (from codeterraform-workspace.json),
#                                  action: "create-library", name, source}
#                                 written as command.json.<requestId>.tmp, then renamed
#   .codeterraform/command-result.json  polled for {requestId, ok, ...} (20 s)
# The same channel carries "run"/"stop"/"rename-library" (see
# docs/AI_CHEATSHEET.md section 8). register_new_libraries() sends one
# create-library per deployed lib module the game does not list yet.
COMMAND_DIR = ".codeterraform"
COMMAND_LOCK_STALE_S = 30.0
COMMAND_LOCK_WAIT_S = 35.0
COMMAND_RESULT_TIMEOUT_S = 20.0
MAX_LIBRARY_SOURCE = 200_000  # interpreter.maxSourceLength in server.cjs

# Library names registered (or found already registered) by this process, so a
# `watch` sweep does not resend before the game refreshes the workspace file.
_REGISTERED_LIBS: set = set()


def registered_library_names(save_dir: Path) -> Optional[set]:
    """Stems of every Library the game has registered (context.libraryScripts),
    or None when the workspace file is unreadable (game never opened this save)."""
    context = read_workspace_context(save_dir)
    if context is None:
        return None
    names = set()
    for info in (context.get("libraryScripts") or {}).values():
        name = str(info.get("name") or "")
        names.add(name[:-3] if name.endswith(".py") else name)
    return names


def workspace_session(save_dir: Path) -> Optional[dict]:
    """The live game session block of codeterraform-workspace.json (top level,
    beside `context`), required on every external command. None if missing."""
    path = save_dir / WORKSPACE_JSON
    try:
        with path.open(encoding="utf-8") as fh:
            session = json.load(fh).get("session")
    except (OSError, ValueError):
        return None
    return session if isinstance(session, dict) and session.get("id") else None


def send_game_command(save_dir: Path, action: str, **fields) -> dict:
    """Sends one external command to the running game and waits for its
    result. Returns the result dict ({"ok": bool, ...}) or {"ok": False,
    "reason": ...} when the game did not answer (not running / save not open)."""
    session = workspace_session(save_dir)
    if session is None:
        return {"ok": False, "reason": "no_session"}
    cmd_dir = save_dir / COMMAND_DIR
    cmd_dir.mkdir(exist_ok=True)
    lock = cmd_dir / "command.lock"
    deadline = time.monotonic() + COMMAND_LOCK_WAIT_S
    while True:
        try:
            if time.time() - lock.stat().st_mtime > COMMAND_LOCK_STALE_S:
                lock.unlink()
        except OSError:
            pass
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                return {"ok": False, "reason": "busy"}
            time.sleep(0.2)
    request_id = str(uuid.uuid4())
    tmp = cmd_dir / ("command.json.%s.tmp" % request_id)
    try:
        payload = {"version": 1, "requestId": request_id, "issuedAt": int(time.time() * 1000),
                   "session": session, "action": action}
        payload.update(fields)
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, cmd_dir / "command.json")
        result_path = cmd_dir / "command-result.json"
        end = time.monotonic() + COMMAND_RESULT_TIMEOUT_S
        while time.monotonic() < end:
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                if result.get("requestId") == request_id and isinstance(result.get("ok"), bool):
                    return result
            except (OSError, ValueError):
                pass
            time.sleep(0.1)
        return {"ok": False, "reason": "unconfirmed"}
    finally:
        for path in (tmp, lock):
            try:
                path.unlink()
            except OSError:
                pass


def register_new_libraries(lib_index: dict, opts: Options) -> int:
    """Registers every deployed lib module the game does not list as a Library
    yet (create-library with the deployed source). Returns how many were
    registered. Needs the game running with this save open; otherwise it
    warns and the next sync retries."""
    registered = registered_library_names(opts.save_dir)
    if registered is None:
        return 0
    missing = sorted(k for k in lib_index if k not in registered and k not in _REGISTERED_LIBS)
    done = 0
    for key in missing:
        path = opts.save_dir / "lib" / ("%s.py" % key)
        body = read(path) if path.exists() else None
        if body is None:
            continue
        if opts.dry_run:
            ok("  would register %-19s as a game Library" % key)
            continue
        if len(body) > MAX_LIBRARY_SOURCE:
            warn("  skip  %-28s %d chars, over the game's %d source limit" % (key, len(body), MAX_LIBRARY_SOURCE))
            continue
        result = send_game_command(opts.save_dir, "create-library", name=key, source=body)
        reason = result.get("reason") or result.get("status") or result.get("message")
        if result.get("ok") or reason == "duplicate_name":
            _REGISTERED_LIBS.add(key)
            ok("  reg   %-28s registered as a game Library%s" % (key, "" if result.get("ok") else " (already known)"))
            done += 1
        else:
            warn("  reg   %-28s not registered (%s) - is the game running with this save open? Result: %s" % (key, reason, result))
            if reason in ("no_session", "unconfirmed", "busy"):
                break  # game unreachable: do not wait 20 s per remaining module
    return done


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


# Last unapplied-lib report printed, so `watch` repeats it only on change.
_LAST_APPLY_REPORT: list = [None]


def report_unapplied_libs(opts: Options) -> None:
    """Names every save script that reaches a lib/ module the game hasn't
    applied yet. No external command applies a changed Library: the game
    caches an imported module independently of the importing script, and
    only the in-game Script Editor's "Apply & restart all" swaps that cache
    (restarting the importer over the command channel runs the stale copy)."""
    if opts.dry_run:
        return
    pending = libs_awaiting_apply(opts)
    hits = []
    if pending:
        for path in sorted(opts.save_dir.glob("*.py")):
            if is_candidate(path, opts.save_dir) and libs_reached(read(path) or "", opts) & pending:
                hits.append(path.stem)
    report = (sorted(pending), hits)
    if report == _LAST_APPLY_REPORT[0]:
        return
    _LAST_APPLY_REPORT[0] = report
    if hits:
        warn("  apply lib(s) not applied in game yet (%s) - %d script(s) need Apply & restart all: %s" %
             (", ".join(sorted(pending)), len(hits), ", ".join(hits)))


def sync_all(script_index: dict, lib_index: dict, opts: Options) -> int:
    """Full pass: mirror lib/, push matched script slots, stage the rest."""
    opts.lib_index = lib_index
    opts.lib_closure = lib_dependency_closure(lib_index)
    materialized = materialize_missing_slots(opts)
    changed_lib_keys = sync_lib(lib_index, opts)
    register_new_libraries(lib_index, opts)
    written = materialized + len(changed_lib_keys)
    for path in sorted(opts.save_dir.glob("*.py")):
        if sync_file(path, script_index, opts, quiet_skips=not opts.verbose):
            written += 1
    tidy_unmatched(script_index, opts)
    report_unapplied_libs(opts)
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
    lib_index, conflicts = resolve_category(scripts_dir, lib_chain(scripts_dir, active_tier), LIB_CATEGORY)
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
NoRestartOpt = typer.Option(False, "--no-restart",
                            help="Push matched slots but don't restart them in game.")


def make_opts(save_dir, scripts_dir, strict, dry_run, verbose, no_renumber,
              force_tier=None, no_restart=False) -> Options:
    save = resolve_save(save_dir)
    if not scripts_dir.is_dir():
        err("Not a directory: %s" % scripts_dir)
        raise typer.Exit(2)
    opts = Options(save, scripts_dir, strict, dry_run, verbose, not no_renumber, force_tier, not no_restart)
    opts.active_tier = resolve_active_tier(scripts_dir, save, force_tier)
    return opts


@app.command()
def status(save_dir: Optional[Path] = SaveOpt, scripts_dir: Path = ScriptsOpt,
           strict: bool = StrictOpt, no_renumber: bool = NoRenumberOpt,
           force_tier: Optional[str] = ForceTierOpt):
    """Show the resolved tier, the scripts/lib mapping, and what each save script would do."""
    opts = make_opts(save_dir, scripts_dir, strict, False, False, no_renumber, force_tier)
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

    opts.lib_index = lib_index
    opts.lib_closure = lib_dependency_closure(lib_index)
    pending = libs_awaiting_apply(opts)
    if pending:
        typer.echo("\nlib/ modules the game hasn't applied yet (%d): %s" % (len(pending), ", ".join(sorted(pending))))

    files = sorted(p for p in opts.save_dir.glob("*.py") if is_candidate(p, opts.save_dir))
    typer.echo("\nSave scripts (%d):" % len(files))
    for path in files:
        text = read(path) or ""
        empty = is_empty(text, opts.strict)
        source, role_note = source_for(path.stem, text, script_index, opts.save_dir)
        if source is None:
            state = role_note or ("empty, no match -> would stage" if empty else "has code, no match -> left alone")
        else:
            template = read(source) or ""
            body = template
            names = find_placeholders(template)
            if names:
                cached = dict(load_params_cache().get("%s/%s" % (opts.save_dir.name, path.stem), {}))
                rehomed = rehome_retired_destination(path.stem, names, cached, text)
                inferred = infer_placeholders(template, text)
                if rehomed is not None:
                    inferred["HOME_BASE"] = rehomed
                body = render_placeholders(template, {n: inferred.get(n, cached.get(n, d)) for n, d in names})
            if opts.renumber:
                body, _, _ = renumber(body, source.stem, path.stem)
            if body == text:
                state = "up to date with %s" % show(source)
            else:
                state = "%s from %s" % ("would fill" if empty else "would push", show(source))
                blockers = sorted(libs_reached(body, opts) & pending)
                if blockers:
                    state += "  (no restart: unapplied lib %s)" % ", ".join(blockers)
            if role_note:
                state += "  [%s]" % role_note
        typer.echo("  %-28s %s" % (path.name, state))
    typer.echo("")


@app.command()
def once(save_dir: Optional[Path] = SaveOpt, scripts_dir: Path = ScriptsOpt,
         strict: bool = StrictOpt, dry_run: bool = DryOpt, verbose: bool = VerboseOpt,
         no_renumber: bool = NoRenumberOpt, force_tier: Optional[str] = ForceTierOpt,
         no_restart: bool = NoRestartOpt):
    """Push every matched save script, restart it in game, and sync lib/."""
    opts = make_opts(save_dir, scripts_dir, strict, dry_run, verbose, no_renumber, force_tier, no_restart)
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


@app.command(name="register-libs")
def register_libs(save_dir: Optional[Path] = SaveOpt, scripts_dir: Path = ScriptsOpt,
                  dry_run: bool = DryOpt, force_tier: Optional[str] = ForceTierOpt):
    """Register every deployed lib/ module the game does not know yet as a game Library (nothing else)."""
    opts = make_opts(save_dir, scripts_dir, False, dry_run, False, False, force_tier)
    _, lib_index, _ = build_index(opts.scripts_dir, opts.active_tier)
    registered = registered_library_names(opts.save_dir)
    if registered is None:
        err("Cannot read %s - open this save in the game first." % WORKSPACE_JSON)
        raise typer.Exit(1)
    typer.echo("Deployed lib modules not registered in game: %s" % (", ".join(sorted(k for k in lib_index if k not in registered)) or "none"))
    typer.echo("Registered %d." % register_new_libraries(lib_index, opts))


class Watcher:
    def __init__(self, opts: Options, delay: float = 0.4):
        self.opts, self.delay = opts, delay
        self.script_index, self.lib_index, self.conflicts = build_index(opts.scripts_dir, opts.active_tier)
        report_conflicts(self.conflicts)
        self.pending: dict = {}
        self.repo_due = None
        self.last_tier_check = time.monotonic()

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
        sync_all(self.script_index, self.lib_index, self.opts)
        if not self.opts.dry_run:
            write_resolved_preview(self.opts.scripts_dir, self.opts.active_tier, self.opts.save_dir)

    def drain(self):
        now = time.monotonic()
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
            # The game rewrites the workspace file on its own cadence, so an
            # in-game "Apply & restart all" only shows up here.
            report_unapplied_libs(self.opts)
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
            # Slots held for a fleet-upgrade handoff (upgrade_fill_for()):
            # the save file sits outside the watched directory, so nothing
            # fires when the next autosave lands. Retry them on this cadence.
            for held in list(HELD_SLOTS):
                self.pending.setdefault(held, now)
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
          no_renumber: bool = NoRenumberOpt, force_tier: Optional[str] = ForceTierOpt,
          no_restart: bool = NoRestartOpt,
          poll: bool = typer.Option(False, "--poll", help="Poll instead of using filesystem events.")):
    """Watch the save directory and scripts/, pushing and re-tiering as things change."""
    opts = make_opts(save_dir, scripts_dir, strict, dry_run, verbose, no_renumber, force_tier, no_restart)
    watcher = Watcher(opts)

    typer.echo("Save     %s" % opts.save_dir)
    typer.echo("Scripts  %s (tier %s)" % (opts.scripts_dir, opts.active_tier))
    typer.echo("Staging  %s for game files with no match" % show(opts.unmatched_dir))
    typer.echo("Push     every matched slot follows scripts/ (in-game edits are overwritten, backups in %s)" % show(BACKUP_DIR))
    typer.echo("Restart  %s" % ("off (--no-restart)" if no_restart else "running and newly filled slots, unless an unapplied lib/ is reached"))
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
