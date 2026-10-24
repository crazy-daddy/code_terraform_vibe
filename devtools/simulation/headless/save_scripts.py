"""Resolve the repo's current scripts for every script slot of a save, for a headless run.

    .venv/Scripts/python.exe devtools/simulation/headless/save_scripts.py --save SAVE.json --out DIR
    node devtools/simulation/headless/run.mjs --save SAVE.json --scripts DIR --libs DIR/lib ...

Writes DIR/<slot>.py for each slot whose resolved source differs from the save's, and
DIR/lib/<module>.py for every lib/ module of the tier chain. Slots are matched the way
scripts_sync.py's sync_file() matches them (role marker or header for panels and
automations, file name otherwise), placeholders are read from the slot's code in the
save (infer_placeholders()), else the template default, and the own id is renumbered.
A slot whose placeholder has neither is skipped and reported: there is nobody to ask.

The tier defaults to the one scripts_sync.py would pick for the save (`.criteria`, no
high-water mark). A role marker naming a renamed role (RENAMED_ROLES) resolves to the
new role; a slot holding a removed role (RETIRED_ROLES) gets an empty script, so its old
code doesn't run against the current libs. In game the player retypes or deletes those.
run.mjs calls this by default for --save runs.

Autoplay content of the save (lib/ modules named like an autoplay/lib/*.py, slots that
resolve to an autoplay/*.py the way scripts_sync.py resolves them) is staged only with
--include-autoplay. Without it, that content would run from the save's stale copies:
a warning on stderr names it. --strip-autoplay loads none of it instead: its slots get
an empty script and DIR/lib/strip_autoplay.json lists its lib modules, which run.mjs
--strip-autoplay drops from the loaded save (the save file is never changed). A slot or
lib module that still imports a stripped lib is reported. --check prints only the
warning and writes nothing (run.mjs runs it for --save runs that stage their own
scripts; --staged-scripts/--staged-libs name what replaces the save's). Below the lib
tier autoplay/ is neither staged nor detected, as in scripts_sync.build_index().

    save_scripts.py --save SAVE.json --out DIR [--include-autoplay | --strip-autoplay]
    save_scripts.py --save SAVE.json --check [--staged-scripts DIR] [--staged-libs DIR]
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # devtools/: scripts_sync, savefile
import scripts_sync as sync
from savefile import load_save

# Roles renamed in scripts/: old `# ct-<type>:` marker -> current role.
RENAMED_ROLES = {
    "control_room_automation": "orchestrator_automation",
    "warehouse_upgrade_automation": "builder_automation",
}
# Roles removed from scripts/ (their views moved into other panels' cards).
# outpost_planner_automation: removed from autoplay/ (infra_planner_automation runs the
# founding pass); its old code imports the whole planner chain against the current libs
# and hit the 10,000-step import cap at load in tick_profile runs.
RETIRED_ROLES = {"drones_panel", "fleet_commission_panel", "outpost_planner_automation"}
RETIRED_BODY = "# Retired role {role}: save_scripts.py leaves this slot empty for the headless run.\n"
STRIPPED_BODY = (
    "# Autoplay role {role}: save_scripts.py --strip-autoplay leaves this slot empty for the headless run.\n"
)
STRIP_MANIFEST = "strip_autoplay.json"  # in DIR/lib: the autoplay lib modules run.mjs --strip-autoplay drops


def save_libraries(state: dict) -> dict:
    """Module stem -> source of every lib/ module the save holds (state.libraryScripts),
    keyed by the entry's `<name>.py` (its dict key only when it has none), as
    scripts_sync._library_entries() keys them; simhost.mjs dropLibraries() matches the same."""
    libs = {}
    for key, info in (state.get("libraryScripts") or {}).items():
        stem = str(info.get("name") or key).removesuffix(".py")
        libs[stem] = info.get("source") or ""
    return libs


def at_lib_tier(tier: str) -> bool:
    """True when scripts_sync.build_index() would merge autoplay/ at this tier: below it the
    game refuses Libraries (research_required), so autoplay/ is neither staged nor detected."""
    number = sync.tier_number(tier)
    return number is not None and number >= sync.LIB_UNLOCK_TIER_NUMBER


def autoplay_content(state: dict, script_index: dict, lib_index: dict, autoplay_dir: Path = sync.AUTOPLAY_DIR):
    """(slots, libs) of the save that are autoplay content: slots as [(stem, role)] whose code
    resolves to an autoplay/*.py (sync.source_for() over autoplay/ alone), libs as the save's
    lib/ module stems whose match_key() names an autoplay/lib/*.py (merge_autoplay()'s keys).
    script_index/lib_index are the tier's, before merge_autoplay(): a key scripts/ resolves
    stays scripts/ content, as there. Callers apply the lib-tier gate (at_lib_tier())."""
    ap_scripts, ap_libs = {}, {}
    sync.merge_autoplay(autoplay_dir, ap_scripts, ap_libs, {})
    slots = []
    for stem, entry in sorted(state.get("scripts", {}).items()):
        current, retired = migrate_marker(stem, entry.get("source") or "")
        if retired or not current.strip():
            continue
        source, _ = sync.source_for(stem, current, ap_scripts)
        if source is not None and sync.match_key(source.stem) not in script_index:
            slots.append((stem, source.stem))
    libs = sorted(
        s for s in save_libraries(state) if sync.match_key(s) in ap_libs and sync.match_key(s) not in lib_index
    )
    return slots, libs


def autoplay_warning(slots: list, libs: list) -> list:
    """Lines naming what a run without --include-autoplay runs from the save's stale copies."""
    lines = ["  warn  save holds autoplay content; without --include-autoplay it runs from the save's stale copies:"]
    if libs:
        lines.append("  warn    lib/: " + ", ".join(libs))
    if slots:
        lines.append("  warn    slots: " + ", ".join(f"{stem} ({role})" for stem, role in slots))
    lines.append("  warn  pass --include-autoplay (stage the repo's autoplay/) or --strip-autoplay (load none of it)")
    return lines


def stripped_importers(sources: dict, stripped: list) -> list:
    """[(name, [stripped libs it imports])] for the sources {name: code} left after a strip."""
    gone = set(stripped)
    hits = []
    for name, code in sorted(sources.items()):
        used = sorted(sync.parse_module_imports(code) & gone)
        if used:
            hits.append((name, used))
    return hits


def migrate_marker(stem: str, current: str):
    """(current with a renamed role's marker rewritten, retired role or None)."""
    slot_type = sync.base_name(stem)
    role = sync._role_marker(current, slot_type)
    if role in RETIRED_ROLES:
        return current, role
    if role in RENAMED_ROLES:
        pattern = re.compile(rf"^(\s*#\s*ct-{re.escape(slot_type)}\s*:\s*){role}\b", re.MULTILINE)
        current = pattern.sub(lambda m: m.group(1) + RENAMED_ROLES[role], current, count=1)
    return current, None


def slot_body(stem: str, current: str, index: dict):
    """(body, note) for one save slot; body None when the slot has no source here."""
    current, retired = migrate_marker(stem, current)
    if retired:
        return RETIRED_BODY.format(role=retired), "retired role " + retired
    source, role_note = sync.source_for(stem, current, index)
    if source is None:
        return None, role_note or "no match in scripts/"
    template = sync.read(source)
    if template is None:
        return None, f"cannot read {source}"
    body = template
    placeholders = sync.find_placeholders(template)
    if placeholders:
        found = sync.infer_placeholders(template, current)
        missing = [name for name, default in placeholders if name not in found and not default]
        if missing:
            return None, "placeholder(s) {} not in the slot's code".format(", ".join(missing))
        body = sync.render_placeholders(template, {name: found.get(name, default) for name, default in placeholders})
    body, _, _ = sync.renumber(body, source.stem, stem)
    return body, role_note


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve the repo's current scripts for every script slot of a save.")
    parser.add_argument("--save", required=True, type=Path, help="save_<id>.json or .json.gz")
    parser.add_argument("--out", type=Path, help="directory for <slot>.py and lib/ (required unless --check)")
    parser.add_argument("--scripts-dir", type=Path, default=sync.DEFAULT_SCRIPTS)
    parser.add_argument("--tier", help="active tier (default: the one the save's progress meets)")
    autoplay = parser.add_mutually_exclusive_group()
    autoplay.add_argument(
        "--include-autoplay",
        action="store_true",
        help="also index autoplay/ (planner scripts, autoplay/lib modules), as scripts_sync --include-autoplay does",
    )
    autoplay.add_argument(
        "--strip-autoplay",
        action="store_true",
        help="load none of the save's autoplay content: its slots get an empty script, its lib modules are "
        f"listed in DIR/lib/{STRIP_MANIFEST} for run.mjs --strip-autoplay to drop",
    )
    autoplay.add_argument(
        "--check",
        action="store_true",
        help="only print the stale-autoplay warning (stderr), write nothing: run.mjs runs this for --save runs "
        "that stage their own scripts (--scripts, --libs, --deploy-templates, --policy)",
    )
    parser.add_argument("--staged-scripts", type=Path, help="with --check: <slot>.py files here replace the save's")
    parser.add_argument("--staged-libs", type=Path, help="with --check: lib modules here replace the save's")
    parser.add_argument("--autoplay-dir", type=Path, default=sync.AUTOPLAY_DIR, help="autoplay/ root (tests)")
    args = parser.parse_args()
    if not args.check and args.out is None:
        parser.error("--out is required unless --check")

    save = load_save(args.save)
    state = save.get("state", save)
    tiers = sync.discover_tiers(args.scripts_dir)
    tier = args.tier or sync.tier_for_state(args.scripts_dir, tiers, sync.summarize_state(state))
    script_index, lib_index, conflicts = sync.build_index(args.scripts_dir, tier)
    # Same lib-tier gate as scripts_sync.build_index(): below it autoplay/ is neither staged nor detected.
    gated = at_lib_tier(tier)
    ap_slots, ap_libs = autoplay_content(state, script_index, lib_index, args.autoplay_dir) if gated else ([], [])
    if args.check:
        staged = {p.stem for p in args.staged_scripts.glob("*.py")} if args.staged_scripts else set()
        staged_libs = {p.stem for p in args.staged_libs.glob("*.py")} if args.staged_libs else set()
        ap_slots = [(stem, role) for stem, role in ap_slots if stem not in staged]
        ap_libs = [stem for stem in ap_libs if stem not in staged_libs]
    if args.include_autoplay and gated:
        sync.merge_autoplay(args.autoplay_dir, script_index, lib_index, conflicts)
    elif not (args.include_autoplay or args.strip_autoplay) and (ap_slots or ap_libs):
        for line in autoplay_warning(ap_slots, ap_libs):
            print(line, file=sys.stderr)
    if args.check:
        return 0

    if args.out.exists():
        shutil.rmtree(args.out)
    (args.out / "lib").mkdir(parents=True)
    for name, path in sorted(lib_index.items()):
        shutil.copyfile(path, args.out / "lib" / (name + ".py"))

    stripped = dict(ap_slots) if args.strip_autoplay else {}
    remaining = {}  # name -> code each kept slot and lib module runs, for the stripped-import check
    written = same = 0
    for stem, entry in sorted(state.get("scripts", {}).items()):
        current = entry.get("source") or ""
        if stem in stripped:
            body, note = STRIPPED_BODY.format(role=stripped[stem]), "stripped autoplay role " + stripped[stem]
        else:
            body, note = slot_body(stem, current, script_index)
            remaining[stem] = current if body is None else body
        if body is None:
            if current.strip():
                print(f"  skip  {stem!s:<28} {note}")
            continue
        if body == current:
            same += 1
            continue
        (args.out / (stem + ".py")).write_text(body, encoding="utf-8", newline="\n")
        written += 1
        print(f"  push  {stem!s:<28}{(f'  [{note}]' if note else '')}")
    if args.strip_autoplay:
        (args.out / "lib" / STRIP_MANIFEST).write_text(json.dumps({"libs": ap_libs}) + "\n", encoding="utf-8")
        for stem, role in ap_slots:
            print(f"  strip {stem} ({role}): empty script", file=sys.stderr)
        if ap_libs:
            print("  strip lib/: " + ", ".join(ap_libs), file=sys.stderr)
        kept = {f"lib/{s}": code for s, code in save_libraries(state).items() if s not in ap_libs}
        kept.update({f"lib/{name}": sync.read(path) or "" for name, path in lib_index.items()})
        for name, used in stripped_importers({**remaining, **kept}, ap_libs):
            print(f"  warn  {name} imports stripped autoplay lib(s): {', '.join(used)}", file=sys.stderr)
    print(
        f"tier {tier}: {written} slot(s) written, {same} already current, {len(lib_index)} lib module(s) -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
