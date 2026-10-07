"""
Swap a very young save's world seed and regenerate what the seed decides: state.seed,
planet.plants.recipeMap (Seed Maker recipes), harvesting.grid (Harvester field),
planet.sources (vents, exotic deposits, water and oil wells) and planet.geologicalAnomalies.

Ports of the game generators: recipes from seed_quality.recipes() (simworker Bp), the field
from field() below (simworker wE, same as devtools/headless/field.mjs). After a game update,
verify both against a fresh save before swapping:
    python devtools/seed_quality.py recipes --check SAVE.json
    node devtools/headless/field.mjs --check SAVE.json
Sources and anomalies come from the game's own generators via
devtools/headless/sources.mjs --emit (needs node and the private internals/ submodule).
Without them, both lists are emptied and the game regenerates them on load, but in load
order (wells before exotic deposits), so well and deposit positions differ from a new game.

Usage: python devtools/swap_seed.py --save PATH/save_x.json --seed 2021208502          (dry run)
       python devtools/swap_seed.py --save PATH/save_x.json --seed 2021208502 --apply

--save is required and never auto-detected. Close the game (menu is fine) before --apply.
Patches the save and its history snapshots (save_x.h0.json, ...); the originals go to
devtools/.sync-backups/seed-swap/<stamp>/. Refuses a save that already has progress
(ticks, scanned sectors, collected items) unless --force: scripts and machines would no
longer fit the new world. Seed choice: docs/plans/scoring_map_seeds.md.
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEVTOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(DEVTOOLS))
import seed_quality  # noqa: E402

BACKUP_ROOT = DEVTOOLS / ".sync-backups" / "seed-swap"
SOURCES_TOOL = DEVTOOLS / "headless" / "sources.mjs"
SAVE_NAME = re.compile(r"^save_[a-z0-9]+_[a-z0-9]+$")
MAX_SEED = 2147483646
# A save past any of these has progress the new world would not match.
PROGRESS_TICKS = 1000

# Harvester field (simworker $p, wE). An item spawns only at Manhattan distance
# >= min_distance from the start cell (the game calls it maxDistance).
FIELD_ITEMS = (  # (id, rarity, min_distance)
    ("soil_sample", 200, 0),
    ("basic_plant", 150, 0),
    ("organic_matter", 100, 2),
    ("mineral_fragment", 80, 3),
    ("rare_fungi", 50, 5),
    ("crystal_shard", 35, 7),
    ("alien_fossil", 20, 9),
    ("exotic_compound", 5, 12),
)
FIELD_ROWS, FIELD_COLS, FIELD_START = 8, 24, (4, 12)  # start cell E13
EMPTY_CHANCE = 0.65


def sector(row, col):
    return chr(65 + row) + str(col + 1)


def field(seed):
    """{sector: item id | None}, as state.harvesting.grid of a fresh world."""
    rand = seed_quality.prng(seed)
    grid = {}
    for row in range(FIELD_ROWS):
        for col in range(FIELD_COLS):
            cell = sector(row, col)
            d = abs(row - FIELD_START[0]) + abs(col - FIELD_START[1])
            if d == 0 or rand() < EMPTY_CHANCE:
                grid[cell] = None
                continue
            pool = [item for item in FIELD_ITEMS if d >= item[2]]
            roll = rand() * sum(item[1] for item in pool)
            pick = pool[0]
            for item in pool:
                roll -= item[1]
                if roll <= 0:
                    pick = item
                    break
            grid[cell] = pick[0]
    return grid


def world_sources(seed):
    """{"sources", "geologicalAnomalies"} of a fresh world from the game's generators, or None."""
    try:
        run = subprocess.run(["node", str(SOURCES_TOOL), "--emit", str(seed)], capture_output=True, text=True,
                             encoding="utf-8", cwd=DEVTOOLS.parent, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if run.returncode != 0:
        return None
    return json.loads(run.stdout)


def has_progress(state):
    h = state["harvesting"]
    return state["tickCount"] > PROGRESS_TICKS or len(h["scannedSectors"]) > 0 or h["collectedCount"] > 0 or bool(h["heldItem"])


def save_files(save):
    """The save state file and its history snapshots (<base>.h*.json)."""
    base = save.stem
    return [save] + sorted(p for p in save.parent.iterdir() if p.name.startswith(base + ".h") and p.suffix == ".json")


def swap(save, seed, apply=False, force=False, out=print):
    """Patches every file of save to seed (dry run unless apply). Returns the backup dir or None."""
    if not SAVE_NAME.match(save.stem) or save.suffix != ".json":
        raise ValueError(f"not a save state file: {save}")
    if not 0 <= seed <= MAX_SEED:
        raise ValueError(f"bad seed {seed}")
    recipe_map = seed_quality.recipes(seed)
    grid = field(seed)
    world = world_sources(seed)
    if world is None:
        out("warning: sources.mjs unavailable; sources and anomalies emptied, the game regenerates them "
            "on load in load order (well and deposit positions differ from a new game)")
        world = {"sources": [], "geologicalAnomalies": []}
    files = save_files(save)
    patched = []
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        state = raw["state"]
        if has_progress(state) and not force:
            raise ValueError(f"{path.name} has progress (tick {state['tickCount']}); --force to override")
        old = state["seed"]
        state["seed"] = seed
        state["planet"]["plants"]["recipeMap"] = recipe_map
        state["harvesting"]["grid"] = grid
        state["planet"]["sources"] = world["sources"]
        state["planet"]["geologicalAnomalies"] = world["geologicalAnomalies"]
        patched.append((path, raw))
        out(f"{path.name}: seed {old} -> {seed}{'' if apply else ' (dry run)'}")
    backup = None
    if apply:
        backup = BACKUP_ROOT / datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        backup.mkdir(parents=True, exist_ok=True)
        for path, raw in patched:
            shutil.copy2(path, backup / path.name)
            path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    out(f"crowncap {', '.join(recipe_map['crowncap'])} | grandbloom {', '.join(recipe_map['grandbloom'])}")
    if backup:
        out(f"backups: {backup}")
    return backup


def main():
    ap = argparse.ArgumentParser(description="Swap a very young save's world seed (dry run unless --apply).")
    ap.add_argument("--save", required=True, type=Path, help="save_<id>.json state file (never auto-detected)")
    ap.add_argument("--seed", required=True, type=int)
    ap.add_argument("--apply", action="store_true", help="write the files (default: dry run)")
    ap.add_argument("--force", action="store_true", help="swap even a save with progress")
    args = ap.parse_args()
    try:
        swap(args.save, args.seed, args.apply, args.force)
    except ValueError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
