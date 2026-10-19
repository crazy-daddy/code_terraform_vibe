"""
Save file -> planner snapshots, for devtools/simulation/planner_replay.py.

Builds, from one game save (a kept save of a recorded run), the inputs the
autoplay planners read in game: the outpost_needs snapshot, the game_phase
snapshot, the build_providers context and the outpost_sites world. The
archive entries of the save (state.notebook.entries) are loaded into the
stub world's archive, so in-game readers that only read the archive
(machine_activity, fleet_status, pickups, survey requests, outpost roles)
work unchanged.

Offline sources the game would answer live:
- mineral sites: the fixed site table (`ore_outpost.mjs --sites`, cached),
  filtered to the save's surveyed site ids; hardness by ore (unlock_paths.md)
- fluid sites: state.planet.sources filtered to the surveyed ids
- biome: docs/gameknowledge/biomes.json (the game's lattice)
- kits: deployed types, Inventory stacks, unlocked recipes and the unlock
  tech ids (`<type>_unlock` plus KIT_TECH)
- pillar targets: the highest catalog threshold per pillar (TerraformPillar
  targets are not in the save), completion by the pillar end values

Reads saves only; writes nothing into them.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

DEVTOOLS = Path(__file__).resolve().parent.parent
REPO = DEVTOOLS.parent
sys.path.insert(0, str(DEVTOOLS))  # savefile
sys.path.insert(0, str(DEVTOOLS / "play"))  # save_diff, decision_recorder
sys.path.insert(0, str(REPO / "tests"))  # harness: game builtins and lib paths

import harness  # noqa: E402 (installs the stub world before the lib imports)

# isort: split
import autoplay_roles  # noqa: E402
import building_plan  # noqa: E402
import game_phase  # noqa: E402
import outpost_sites  # noqa: E402
import save_diff  # noqa: E402
from archive import archive  # noqa: E402
from game_rules import SMELT_PRODUCTS  # noqa: E402
from grid_geom import extractor_box  # noqa: E402
from outpost_needs import EARLY_ORES  # noqa: E402
from research_thresholds import TECH_TO_RESEARCH, THRESHOLDS  # noqa: E402

HOME = save_diff.HOME
BIOMES_JSON = REPO / "docs" / "gameknowledge" / "biomes.json"
SITES_CACHE = REPO / "devtools" / "simulation" / "headless" / ".cache" / "mineral_sites.json"
ORE_OUTPOST = REPO / "devtools" / "simulation" / "headless" / "ore_outpost.mjs"
SITE_LINE = re.compile(r"^(\w+)\s+(\w+)\s+(\w+)\s+\(\s*(-?\d+),\s*(-?\d+)\)")
HARDNESS = {"iron_ore": 1, "silicon": 1, "titanium": 2, "cobalt": 2, "lead_ore": 2, "rare_earth": 3, "neutronium": 4}
KIT_TECH = {
    "luminizer": "bio_luminizer",
    "high_bay_warehousing": "large_warehouse",
    "large_battery": "battery_large",
    "weather_program": "weather_station",
    "nuclear_program": "reactor",
    "outpost": "outpost_kit",
    "thermal_cap": "thermal_cap_kit",
    "drones": "drone_small",
    "mining": "mining_drill",
}
BASE_KITS = ("solar_generator", "battery", "oxygen_generator", "temp_heater", "pressure_generator")
PACK_TECH = {
    "oxygen_mk2_pack_unlock": "oxygen_upgrade_pack_mk2",
    "heat_mk2_pack_unlock": "heat_upgrade_pack_mk2",
    "pressure_mk2_pack_unlock": "pressure_upgrade_pack_mk2",
    "industrial_machinery_mk2_unlock": ("smelter_upgrade_pack_mk2", "fabricator_upgrade_pack_mk2"),
    "industrial_machinery_mk3_unlock": ("smelter_upgrade_pack_mk3", "fabricator_upgrade_pack_mk3"),
}
PILLAR_FIELDS = {
    "temperature": ("temperature", "heatUnits"),
    "oxygen": ("atmosphere", "oxygen"),
    "pressure": ("atmosphere", "pressure"),
    "biomass": ("biomass", "totalTons"),
    "plants": ("plants", "km2"),
    "wildlife": ("wildlife", "population"),
}
PILLAR_END = {"biomass": 250000.0, "plants": 5000000.0, "wildlife": 5000000.0}
SOURCE_FLUID = {"water": "water", "oil": "oil", "thermal": "steam"}
RANGE_M = 200.0
ORE_OF_PRODUCT = {product: ore for ore, product in SMELT_PRODUCTS.items()}


# ---------- fixed game data ----------


def biome_lattice():
    data = json.loads(BIOMES_JSON.read_text("utf-8"))
    letters = data["encoding"]["letters"]
    rows = []
    size = int(data["encoding"]["size"])
    for index, row in enumerate(data["rows"]):
        cells = []
        for count, letter in re.findall(r"(\d*)([A-Z])", row):
            cells.extend(
                [letters.get(letter, "frozen")] * (int(count) if count else 1)
            )  # unknown falls back to frozen (biomes.md)
        if len(cells) != size:
            raise ValueError(f"biomes.json row {index} decodes to {len(cells)} cells, not {size}")
        rows.append(cells)
    return rows


_LATTICE = None


def biome_at(x, y):
    """The game's nocturna.biome_at(): lattice lookup (docs/gameknowledge/biomes.md)."""
    global _LATTICE
    if _LATTICE is None:
        _LATTICE = biome_lattice()
    n = min(max(float(x) + 900.0, 0.0), 1800.0)
    m = min(max(900.0 - float(y), 0.0), 1800.0)
    i = int(n / 4.0 + 0.5)
    r = int(m / 4.0 + 0.5)
    row = _LATTICE[min(r, len(_LATTICE) - 1)]
    return row[min(i, len(row) - 1)]


def mineral_sites(cache=SITES_CACHE):
    """[{"id", "item", "purity", "hardness", "x", "y"}] the fixed mineral site table (cached JSON, else ore_outpost.mjs --sites)."""
    if cache.is_file():
        return json.loads(cache.read_text("utf-8"))
    text = subprocess.run(["node", str(ORE_OUTPOST), "--sites"], capture_output=True, text=True, check=True).stdout
    rows = []
    lines = [line for line in text.splitlines() if line.strip()]
    for line in lines:
        found = SITE_LINE.match(line.strip())
        if found:
            item, purity, name, x, y = found.groups()
            rows.append(
                {
                    "id": name,
                    "item": item,
                    "purity": purity,
                    "hardness": HARDNESS.get(item, 1),
                    "x": float(x),
                    "y": float(y),
                }
            )
    if len(rows) != len(lines):
        raise ValueError(f"ore_outpost.mjs --sites: {len(lines)} lines, {len(rows)} parsed; the table format changed")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rows, indent=1), "utf-8")
    return rows


def machine_table():
    return save_diff.machine_table()


# ---------- save readers ----------


def state_of(save):
    return save.get("state", save)


def notebook(state):
    out = {}
    for key, entry in ((state.get("notebook") or {}).get("entries") or {}).items():
        if isinstance(entry, dict) and "value" in entry:
            out[key] = entry["value"]
    return out


def load_archive(state):
    """Fresh stub world, then every archive entry of the save in its archive."""
    world = harness.World()
    harness._install_builtins(world)
    harness._reset_module_state(world)
    for key, value in notebook(state).items():
        archive.set(key, value)
    return world


def finished_machines(state):
    return [m for m in state["machines"].values() if isinstance(m, dict) and not m.get("isUnderConstruction")]


def tier_of(machine):
    tier = (machine.get("data") or {}).get("tier")
    return int(tier) if isinstance(tier, (int, float)) and tier else 1


def tech_set(state):
    return set(state.get("unlockedTech") or [])


def research_set(state):
    return {TECH_TO_RESEARCH[t] for t in tech_set(state) if t in TECH_TO_RESEARCH}


def kits_of(state, table):
    kits: set[str] = set(BASE_KITS)
    for machine in finished_machines(state):
        kits.add(machine["typeId"])
    for slot in (state.get("inventory") or {}).get("slots") or []:
        if isinstance(slot, dict) and slot.get("id"):
            kits.add(slot["id"])
    for recipe in state["player"].get("unlockedRecipes") or []:
        if recipe.startswith("craft_"):
            kits.add(recipe[len("craft_") :])
    for tech in tech_set(state):
        base = tech.removesuffix("_unlock")
        if base in table:
            kits.add(base)
        if base in KIT_TECH:
            kits.add(KIT_TECH[base])
    return kits


def pack_prices(state):
    prices = {}
    for tech, packs in PACK_TECH.items():
        if tech in tech_set(state):
            for pack in packs if isinstance(packs, tuple) else (packs,):
                prices[pack] = 1
    return prices


def inventory_of(state):
    out = {}
    for slot in (state.get("inventory") or {}).get("slots") or []:
        if isinstance(slot, dict) and slot.get("id"):
            out[slot["id"]] = out.get(slot["id"], 0) + int(slot.get("count") or 0)
    return out


def outposts_of(state, table, roles_map, virtual=()):
    """outpost_needs snapshot entries from the save (plus virtual outposts of an accept-mode replay)."""
    tech = tech_set(state)
    counts = {}
    for machine in finished_machines(state):
        loc = machine.get("locationId")
        if loc:
            counts.setdefault(loc, {})
            counts[loc][machine["typeId"]] = counts[loc].get(machine["typeId"], 0) + 1
    out = []
    for entry in state["planet"].get("outposts") or []:
        if entry.get("isUnderConstruction"):
            continue
        oid = entry["id"]
        types = counts.get(oid, {})
        used = sum(n for t, n in types.items() if table.get(t, (False, False))[0])
        out.append(
            {
                "id": oid,
                "x": float(entry["x"]),
                "y": float(entry["y"]),
                "biome": biome_at(entry["x"], entry["y"]),
                "home": oid == HOME,
                "roles": autoplay_roles.role_list(roles_map.get(oid)),
                "types": dict(types),
                "used": used,
                "capacity": save_diff.building_cap(oid, tech),
            }
        )
    for entry in virtual:
        out.append(dict(entry, roles=autoplay_roles.role_list(roles_map.get(entry["id"], entry.get("roles")))))
    return out


def surveyed_ids(state):
    mining = ((state.get("journal") or {}).get("planets") or {}).get("nocturna", {}).get("mining") or {}
    return set(mining.get("surveyedSites") or [])


def ore_sites_of(state, sites):
    surveyed = surveyed_ids(state)
    drilled = set()
    for entry in (notebook(state).get("drill.status") or {}).values():
        if isinstance(entry, dict):
            drilled.update((entry.get("items") or {}).keys())
    return [dict(row, drill=("drill" if row["item"] in drilled else "")) for row in sites if row["id"] in surveyed]


def fluid_sites_of(state):
    surveyed = surveyed_ids(state)
    rows = []
    for source in state["planet"].get("sources") or []:
        if source.get("id") not in surveyed:
            continue
        kind = source.get("kind")
        fluid = SOURCE_FLUID.get(kind) or (
            "raw_" + source["fluid"] if kind == "exotic" and source.get("fluid") else None
        )
        if fluid is None:
            continue
        x, y = float(source["x"]), float(source["y"])
        rows.append(
            {
                "id": source["id"],
                "structure": kind,
                "fluid": fluid,
                "x": x,
                "y": y,
                "box": extractor_box(x, y),
                "machine": None,
                "rate": float(
                    source.get("baseFlowRate") or source.get("basePeakSteamRate") or source.get("basePeakRate") or 0.0
                ),
            }
        )
    return rows


def ore_wanted_of(state):
    ores = sorted(
        {
            ORE_OF_PRODUCT[r[len("smelt_") :]]
            for r in state["player"].get("unlockedRecipes") or []
            if r.startswith("smelt_") and r[len("smelt_") :] in ORE_OF_PRODUCT
        }
    )
    return ores or list(EARLY_ORES)


def pillar_targets():
    targets = {}
    for pillar, limit, _tech in THRESHOLDS.values():
        if pillar in PILLAR_FIELDS:
            targets[pillar] = max(targets.get(pillar, 0.0), float(limit))
    for pillar, end in PILLAR_END.items():
        targets[pillar] = max(targets.get(pillar, 0.0), end)
    return targets


def phase_of(state, history):
    """game_phase snapshot from the save; history = {pillar: [[tick, value], ...]} from the earlier kept saves."""
    planet = state["planet"]
    targets = pillar_targets()
    pillars = {}
    for pillar, (section, field) in PILLAR_FIELDS.items():
        value = float((planet.get(section) or {}).get(field) or 0.0)
        target = targets.get(pillar, 0.0)
        pillars[pillar] = {
            "value": value,
            "target": target,
            "next_target": None,
            "progress": 100.0 * value / target if target else 0.0,
            "complete": pillar in PILLAR_END and value >= PILLAR_END[pillar],
            "phase": 1,
        }
    done = {pillar: pillars[pillar]["complete"] for pillar in PILLAR_END}
    tp = float(((state.get("researchRates") or {}).get("terraform") or {}).get("lastValue") or 0.0)
    drills = any(str(m.get("typeId", "")).startswith("mining_drill") for m in finished_machines(state))
    return {
        "tick": int(state.get("tickCount") or 0),
        "tp": tp,
        "pillars": pillars,
        "research": research_set(state),
        "drills": drills,
        "done": done,
        "history": history,
    }


def pillar_readings(state):
    """{pillar: value} plus tp, for the history rings across kept saves."""
    planet = state["planet"]
    out = {
        pillar: float((planet.get(section) or {}).get(field) or 0.0)
        for pillar, (section, field) in PILLAR_FIELDS.items()
    }
    out["tp"] = float(((state.get("researchRates") or {}).get("terraform") or {}).get("lastValue") or 0.0)
    return out


def needs_snapshot(state, table, sites, roles_map, history, virtual=()):
    kits = kits_of(state, table)
    outposts = outposts_of(state, table, roles_map, virtual)
    presets = autoplay_roles.presets()
    taken = []
    for entry in outposts:
        for fluid in autoplay_roles.fluids_for(entry["roles"], presets)["in"]:
            if fluid not in taken:
                taken.append(fluid)
    large = "large_warehouse" in kits
    nb = notebook(state)
    return {
        "outposts": outposts,
        "kits": kits,
        "activity": building_plan.outpost_needs.read_activity(),
        "phase": phase_of(state, history),
        "bio_orders": {},
        "bio_done": {},
        "stock": {},
        "per_warehouse": autoplay_roles.WAREHOUSE_SLOTS["large_warehouse" if large else "warehouse"],
        "essences_required": None,
        "ore_wanted": ore_wanted_of(state),
        "ore_sites": ore_sites_of(state, sites),
        "fluid_sites": fluid_sites_of(state),
        "fluids_in": taken,
        "range_m": RANGE_M,
        "refused": [],
        "refused_roles": [],
        "_notebook_keys": sorted(nb),
    }


def context_of(state, snap, focus, table):
    """build_providers context from the save (one grid per power subnet, every outpost on it)."""
    tick = int(state.get("tickCount") or 0)
    machines = {}
    ids = {}
    all_types = {}
    for machine in finished_machines(state):
        type_id = machine["typeId"]
        all_types[type_id] = all_types.get(type_id, 0) + 1
        loc = machine.get("locationId")
        if loc:
            machines.setdefault(type_id, []).append((machine["id"], loc, tier_of(machine)))
            ids.setdefault((loc, type_id), []).append(machine["id"])
    grids = []
    outpost_ids = [entry["id"] for entry in snap["outposts"]]
    for anchor, sub in ((state["planet"].get("power") or {}).get("subnets") or {}).items():
        capacity = float(sub.get("capacity") or 0.0)
        stored = float(sub.get("stored") or 0.0)
        grids.append(
            {
                "anchor": anchor,
                "outposts": outpost_ids,
                "generated": float(sub.get("generated") or 0.0),
                "consumed": float(sub.get("consumed") or 0.0),
                "stored": stored,
                "capacity": capacity,
                "reserve": stored / capacity if capacity > 0 else None,
                "phase": grid_phase_of(all_types),
                "types": dict(all_types),
            }
        )
    nb = notebook(state)
    status = nb.get("fleet.status") or {}
    requests = nb.get("autoplay.survey_requests") or {}
    pickups = nb.get("logistics.pickups") or {}
    return {
        "snap": snap,
        "phase": snap["phase"],
        "focus": focus or {},
        "generators": {t: machines.get(t, []) for t in ("oxygen_generator", "temp_heater", "pressure_generator")},
        "machines": {t: machines.get(t, []) for t in ("smelter", "fabricator")},
        "machine_ids": ids,
        "grids": grids,
        "prices": pack_prices(state),
        "inventory": inventory_of(state),
        "fleet": building_plan.fleet_counts(
            status, nb.get("fleet.commission") or {}, nb.get("fleet.decommission") or {}
        ),
        "survey_open": bool(requests),
        "survey_idle_since": None
        if requests or "autoplay.survey_requests" not in nb
        else 0,  # the planner never ran in a save without the key
        "pickup_backlog": building_plan.pickup_backlog(pickups, tick),
        "drills_missing": building_plan.drills_missing(snap),
        "seismic_open": False,
        "miners": {},  # needs the planner's latches; a replay proposes no miner moves
        "mining_reach": {},
        "ore_need": {},
        "tick": tick,
    }


def grid_phase_of(types):
    if types.get("reactor", 0) > 0:
        return "reactor"
    if types.get("oil_generator", 0) > 0:
        return "oil"
    if types.get("steam_turbine", 0) > 0:
        return "steam"
    return "solar"


def world_of(snap, sites, state):
    """outpost_sites.prepare() world: surveyed sites as level-3 rows, every known site as a POI for clearance."""
    surveyed = surveyed_ids(state)
    rows = []
    pois = []
    for row in sites:
        pois.append({"x": row["x"], "y": row["y"], "kind": "mineral" if row["id"] in surveyed else "unknown"})
        if row["id"] in surveyed:
            rows.append(
                {
                    "id": row["id"],
                    "x": row["x"],
                    "y": row["y"],
                    "kind": "mineral",
                    "surveyed": True,
                    "item": row["item"],
                    "purity": row["purity"],
                    "hardness": row["hardness"],
                    "fluid": None,
                }
            )
    for source in state["planet"].get("sources") or []:
        kind = source.get("kind")
        known = source.get("id") in surveyed
        pois.append({"x": float(source["x"]), "y": float(source["y"]), "kind": kind if known else "unknown"})
        if known:
            rows.append(
                {
                    "id": source["id"],
                    "x": float(source["x"]),
                    "y": float(source["y"]),
                    "kind": kind,
                    "surveyed": True,
                    "item": None,
                    "purity": None,
                    "hardness": None,
                    "fluid": source.get("fluid") if kind == "exotic" else None,
                }
            )
    early = not game_phase.drills(snap["phase"])
    weights, reach = outpost_sites.phase_inputs(snap["outposts"], early)
    return {
        "bounds": (-900.0, 900.0, -900.0, 900.0),
        "outposts": snap["outposts"],
        "ghosts": [],
        "pois": pois,
        "sites": rows,
        "range_m": RANGE_M,
        "hardness_limit": outpost_sites.hardness_limit(snap["kits"]),
        "blocked": None,
        "unsupported": {},
        "pipes": [],
        "weights": weights,
        "demand": dict(outpost_sites.DEMAND_FALLBACK),
        "reach": reach,
    }
