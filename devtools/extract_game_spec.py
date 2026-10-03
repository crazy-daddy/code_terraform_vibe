#!/usr/bin/env python
"""Extract the game's API contracts and data tables into tests/game_spec.json.

    python devtools/extract_game_spec.py               # regenerate, check against the newest save
    python devtools/extract_game_spec.py --source X.js  # another decompiled simworker
    python devtools/extract_game_spec.py --no-save      # skip the save check

Reads internals/terraform_decompiled/simworker/deobfuscated.js (gitignored)
and writes tests/game_spec.json (committed), so the tests and cloud agents
never need the decompiled file. Node evaluates only the requested literals in
a vm sandbox (devtools/extract_game_spec.js); see that file for how
identifiers are resolved. Rerun after a game update and review the diff.

Output keys:
  game_version   build hash from get_game_version(), else the source mtime
  api            {component: {method: {params, returns, readonly, signature,
                 outcomes, result_type, payload_fields}}} from the method
                 registry; `outcomes` is the status list of `outcomeContract`
                 (absent when the method has none, null when unresolved);
                 `contract_kind: "optional"` marks a method that returns None
                 instead of a status; `property: true` marks an attribute
  types          same shape for the object types component calls return
                 ({InputSlot: {connect: ...}, ItemStack: {count: ...}, ...})
  machines       {type_id: row} from the machine table (`kg`)
  recipes        rows of the recipe table (`Ix`), sorted by id
  storage        {type_id: {slotCount, slotCapacity}} (`Eg`)
  unresolved     getter fields and identifiers that became null
  duplicate_methods  component.method registered twice with different shapes

The save check reads the newest save_*.json under %APPDATA%\\io.codeterraform.game
(read-only, never written or copied) and reports machine typeIds missing from
`machines`. Exit code 1 when any are missing.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "internals" / "terraform_decompiled" / "simworker" / "deobfuscated.js"
EVALUATOR = Path(__file__).resolve().parent / "extract_game_spec.js"
OUTPUT = REPO_ROOT / "tests" / "game_spec.json"
GAME_DIR = "io.codeterraform.game"


def extract(source: Path) -> dict:
    proc = subprocess.run(
        ["node", str(EVALUATOR), str(source)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if proc.returncode != 0:
        sys.exit("node failed:\n" + proc.stderr)
    spec = json.loads(proc.stdout)
    if not spec["game_version"]:
        mtime = datetime.datetime.fromtimestamp(source.stat().st_mtime, datetime.timezone.utc)
        spec["game_version"] = "mtime " + mtime.strftime("%Y-%m-%dT%H:%M:%SZ")
    spec["recipes"].sort(key=lambda r: r.get("id") or "")
    return spec


def newest_save_state() -> Path | None:
    root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / GAME_DIR
    saves = [p for p in root.glob("save_*.json") if p.is_file()] if root.is_dir() else []
    return max(saves, key=lambda p: p.stat().st_mtime) if saves else None


def save_type_counts(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        state = json.load(f).get("state", {})
    counts: dict = {}
    for machine in (state.get("machines") or {}).values():
        type_id = machine.get("typeId")
        counts[type_id] = counts.get(type_id, 0) + 1
    return counts


def summary(spec: dict) -> None:
    methods = sum(len(m) for m in spec["api"].values())
    with_outcomes = sum(1 for m in spec["api"].values() for e in m.values() if e.get("outcomes"))
    print("game_version  %s" % spec["game_version"])
    print("api           %d components, %d methods, %d with outcomes" % (len(spec["api"]), methods, with_outcomes))
    type_methods = sum(len(m) for m in spec["types"].values())
    print("types         %d types, %d methods" % (len(spec["types"]), type_methods))
    print("machines      %d" % len(spec["machines"]))
    print("recipes       %d" % len(spec["recipes"]))
    print("storage       %s" % ", ".join("%s %sx%s" % (k, v.get("slotCount"), v.get("slotCapacity"))
                                         for k, v in sorted(spec["storage"].items())))
    print("unresolved    %d" % len(spec["unresolved"]))
    if spec["duplicate_methods"]:
        print("duplicates    %s" % ", ".join(spec["duplicate_methods"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--no-save", action="store_true", help="skip the live-save typeId check")
    args = parser.parse_args()
    if not args.source.is_file():
        sys.exit("decompiled source not found: %s" % args.source)

    spec = extract(args.source)
    OUTPUT.write_text(json.dumps(spec, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote %s" % OUTPUT.relative_to(REPO_ROOT))
    summary(spec)

    if args.no_save:
        return 0
    save = newest_save_state()
    if save is None:
        print("save check    skipped (no save_*.json found)")
        return 0
    counts = save_type_counts(save)
    missing = sorted(t for t in counts if t not in spec["machines"])
    print("save check    %s: %d typeIds, %d missing%s" % (
        save.name, len(counts), len(missing), (": " + ", ".join(map(str, missing))) if missing else ""))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
