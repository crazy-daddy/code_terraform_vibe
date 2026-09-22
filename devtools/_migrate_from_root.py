"""One-off migration: reorganize the flat root-script layout (inherited from the
save-folder-as-repo era) into the tiered scripts/ tree.

Rationale (see TODO.md "Tiered scripts/ migration" entry and the plan this came
from): the save this codebase was actually written and tested against already
has 60 techs unlocked, including data_archive_unlock and custom_panels_unlock.
So the current root scripts are NOT early-game code - they're tier-4
(4_controlpanel) code. Retroactively figuring out which individual script could
also run correctly on an earlier-tier save (no Archive, no Signal Bus, no
Control Room) needs per-file judgment this script does not attempt; that split
is left as a manual follow-up (see TODO.md). This script's only job is a
faithful, non-lossy move of "the code as it stands today" into its honest home
tier, deduplicating identical instances of the same machine type.

Run once from the Code_Terraform root: `python devtools/_migrate_from_root.py`.
Safe to re-run (idempotent): it only reads root *.py/lib/*.py and writes under
scripts/, never touches the root files themselves.
"""
from __future__ import annotations

import ast
import re
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NUMBERED_SUFFIX = re.compile(r"_(\d+)$")
SELF_ID_TOKEN = re.compile(r"\b([a-z_]+?)_(\d+)\b")

# base_name -> category, for the tier-4 (current, advanced) codebase.
CATEGORY = {
    "solar": "power", "boot": "power", "charging_station": "power",
    "thermal_cap": "power", "turbine": "power", "planet_power": "power",
    "water_pump": "power",
    "rover": "rover",
    "pioneer": "pioneer",
    "drone": "drone", "drone_service": "drone", "drone_station": "drone",
    "bio_caster": "bio", "bio_collector": "bio", "bio_conditioner": "bio",
    "bio_exchange": "bio", "bio_glow_diagnostic": "bio", "bio_lab": "bio",
    "bio_luminizer": "bio", "dna_sequencer": "bio",
    "fabricator": "factory", "smelter": "factory",
    "harvester": "harvesting", "scanner": "harvesting",
    "sync_resource_markers": "harvesting",
    "heater": "atmos", "o2gen": "atmos", "pressure": "atmos",
    "weather_station": "atmos",
    "oxygen_sensor": "sensor", "pressure_sensor": "sensor",
    "planet_sensors": "sensor", "uplink": "sensor",
    "supply_dock": "supply_dock",
    "panel": "panel",
    "cold_boot": "contract", "corrupted_archive": "contract",
    "data_tablet": "contract", "drifting_signal": "contract",
    "relay_hack": "contract", "sealed_vault": "contract",
    "terminal_breach": "contract", "three_echoes": "contract",
    "xenogenetics": "contract",
}
EXCLUDE = {"user_stubs"}  # game-generated, never a source file
HOME_TIER = "4_controlpanel"

# Machine types where each numbered instance is a genuinely distinct,
# hand-authored script (not interchangeable copies of one template) - per
# TODO.md, panel_1 does Power Grid supervision, panel_2 does FLEET Sport Nav,
# etc. These are kept as separate files by their full stem, never collapsed
# or renumbered by base_name.
DISTINCT_INSTANCES = {"panel"}


def base_name(stem: str) -> str:
    m = NUMBERED_SUFFIX.search(stem)
    return stem[: m.start()] if m else stem


def is_empty(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return True
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    body = tree.body
    if not body:
        return True
    if len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(
        getattr(body[0], "value", None), (ast.Constant,)
    ):
        return isinstance(body[0].value.value, str)
    return False


def normalized(text: str) -> str:
    """Blank out every '<name>_<n>' self-id token so instance number
    differences don't count as real content divergence."""
    return SELF_ID_TOKEN.sub(r"\1_N", text)


def main() -> None:
    groups: dict[str, list[Path]] = defaultdict(list)
    for f in sorted(ROOT.glob("*.py")):
        base = base_name(f.stem)
        if base in EXCLUDE:
            continue
        groups[base].append(f)

    conflicts: list[str] = []
    written: list[str] = []
    skipped_empty: list[str] = []

    for base, files in sorted(groups.items()):
        category = CATEGORY.get(base)
        if category is None:
            conflicts.append(f"UNMAPPED base_name '{base}' (files: {[f.name for f in files]}) - add to CATEGORY dict")
            continue

        non_empty = [f for f in files if not is_empty(f)]
        if not non_empty:
            skipped_empty.append(base)
            continue

        if base in DISTINCT_INSTANCES:
            dest_dir = ROOT / "scripts" / HOME_TIER / category
            dest_dir.mkdir(parents=True, exist_ok=True)
            for f in non_empty:
                dest = dest_dir / f.name
                shutil.copyfile(f, dest)
                written.append(str(dest.relative_to(ROOT)))
            continue

        by_norm: dict[str, list[Path]] = defaultdict(list)
        for f in non_empty:
            by_norm[normalized(f.read_text(encoding="utf-8"))].append(f)

        if len(by_norm) > 1:
            variants = ", ".join(f"{p[0].name} (x{len(p)})" for p in by_norm.values())
            conflicts.append(f"DIVERGENT content for base_name '{base}': {variants} - picking most-recently-modified, review manually")

        canonical_file = max(non_empty, key=lambda f: f.stat().st_mtime)
        dest_dir = ROOT / "scripts" / HOME_TIER / category
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{base}.py"
        shutil.copyfile(canonical_file, dest)
        written.append(str(dest.relative_to(ROOT)))

    # lib/ -> scripts/4_controlpanel/lib/ (unconditional, nothing tier-gated yet)
    lib_src = ROOT / "lib"
    lib_dest = ROOT / "scripts" / HOME_TIER / "lib"
    if lib_src.is_dir():
        lib_dest.mkdir(parents=True, exist_ok=True)
        for f in lib_src.glob("*.py"):
            shutil.copyfile(f, lib_dest / f.name)
            written.append(str((lib_dest / f.name).relative_to(ROOT)))

    print(f"Wrote {len(written)} files under scripts/{HOME_TIER}/")
    if skipped_empty:
        print(f"Skipped {len(skipped_empty)} base_names with only empty/stub instances: {sorted(skipped_empty)}")
    if conflicts:
        print(f"\n{len(conflicts)} items need manual review:")
        for c in conflicts:
            print(f"  - {c}")


if __name__ == "__main__":
    main()
