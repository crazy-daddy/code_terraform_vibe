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
"""

import argparse
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
RETIRED_ROLES = {"drones_panel", "fleet_commission_panel"}
RETIRED_BODY = "# Retired role {role}: save_scripts.py leaves this slot empty for the headless run.\n"


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
    parser.add_argument("--out", required=True, type=Path, help="directory for <slot>.py and lib/")
    parser.add_argument("--scripts-dir", type=Path, default=sync.DEFAULT_SCRIPTS)
    parser.add_argument("--tier", help="active tier (default: the one the save's progress meets)")
    args = parser.parse_args()

    save = load_save(args.save)
    state = save.get("state", save)
    tiers = sync.discover_tiers(args.scripts_dir)
    tier = args.tier or sync.tier_for_state(args.scripts_dir, tiers, sync.summarize_state(state))
    script_index, lib_index, _ = sync.build_index(args.scripts_dir, tier)

    if args.out.exists():
        shutil.rmtree(args.out)
    (args.out / "lib").mkdir(parents=True)
    for name, path in sorted(lib_index.items()):
        shutil.copyfile(path, args.out / "lib" / (name + ".py"))

    written = same = 0
    for stem, entry in sorted(state.get("scripts", {}).items()):
        current = entry.get("source") or ""
        body, note = slot_body(stem, current, script_index)
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
    print(
        f"tier {tier}: {written} slot(s) written, {same} already current, {len(lib_index)} lib module(s) -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
