"""Resolve the repo's current scripts for every script slot of a save, for a headless run.

    .venv/Scripts/python.exe devtools/headless/save_scripts.py --save SAVE.json --out DIR
    node devtools/headless/run.mjs --save SAVE.json --scripts DIR --libs DIR/lib ...

Writes DIR/<slot>.py for each slot whose resolved source differs from the save's, and
DIR/lib/<module>.py for every lib/ module of the tier chain. Slots are matched the way
scripts_sync.py's sync_file() matches them (role marker or header for panels and
automations, file name otherwise), placeholders are read from the slot's code in the
save (infer_placeholders()), else the template default, and the own id is renumbered.
A slot whose placeholder has neither is skipped and reported: there is nobody to ask.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scripts_sync as sync  # noqa: E402


def slot_body(stem: str, current: str, index: dict):
    """(body, note) for one save slot; body None when the slot has no source here."""
    source, role_note = sync.source_for(stem, current, index)
    if source is None:
        return None, role_note or "no match in scripts/"
    template = sync.read(source)
    if template is None:
        return None, "cannot read %s" % source
    body = template
    placeholders = sync.find_placeholders(template)
    if placeholders:
        found = sync.infer_placeholders(template, current)
        missing = [name for name, default in placeholders if name not in found and not default]
        if missing:
            return None, "placeholder(s) %s not in the slot's code" % ", ".join(missing)
        body = sync.render_placeholders(template, {name: found.get(name, default) for name, default in placeholders})
    body, _, _ = sync.renumber(body, source.stem, stem)
    return body, role_note


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve the repo's current scripts for every script slot of a save.")
    parser.add_argument("--save", required=True, type=Path, help="save_<id>.json")
    parser.add_argument("--out", required=True, type=Path, help="directory for <slot>.py and lib/")
    parser.add_argument("--scripts-dir", type=Path, default=sync.DEFAULT_SCRIPTS)
    parser.add_argument("--tier", help="active tier (default: the highest one)")
    args = parser.parse_args()

    tier = args.tier or sync.discover_tiers(args.scripts_dir)[-1]
    script_index, lib_index, _ = sync.build_index(args.scripts_dir, tier)
    save = json.loads(args.save.read_text(encoding="utf-8"))
    state = save.get("state", save)

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
                print("  skip  %-28s %s" % (stem, note))
            continue
        if body == current:
            same += 1
            continue
        (args.out / (stem + ".py")).write_text(body, encoding="utf-8", newline="\n")
        written += 1
        print("  push  %-28s%s" % (stem, "  [%s]" % note if note else ""))
    print("tier %s: %d slot(s) written, %d already current, %d lib module(s) -> %s"
          % (tier, written, same, len(lib_index), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
