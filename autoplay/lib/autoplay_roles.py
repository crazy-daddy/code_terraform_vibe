# Outpost roles for the infrastructure planner (autoplay/infra_planner_automation.py):
# which fluids each outpost needs piped in and which it makes.
#
# Archive shapes (one shared dict per concern):
#   autoplay.role_presets = {role: {"in": [fluid_id, ...], "out": [fluid_id, ...]}}
#                           seeded with DEFAULT_ROLE_PRESETS when missing, then
#                           operator-editable; a plain list is "in" only.
#   autoplay.outpost_roles = {outpost_id: role | [role, ...]}  operator-set; entries
#                           of outposts that no longer exist are pruned.
# The home outpost always has HOME_ROLES on top of its entry: the Harvester's
# field sits there. Any other outpost without an entry has no fluid. An
# outpost's fluids in role order ("in" before "out" per role, duplicates
# dropped) are its service order when its footprint runs out of ports.

from archive import archive
from swallow import swallowed

PRESETS_KEY = "autoplay.role_presets"
ROLES_KEY = "autoplay.outpost_roles"

# Fluids per role (docs/database/fluids.md "Consumed by" / "Produced by" / "Tier input").
DEFAULT_ROLE_PRESETS = {
    "factory": {"in": ["water", "oil", "steam"]},     # Fabricator recipes
    "terraform": {"in": ["water", "steam"]},          # Oxygen/Pressure Mk III water, Heat Mk III steam
    "power": {"in": ["steam", "oil"]},                # Steam Turbine, Oil Generator
    "farm": {"in": ["water"]},                        # Sprinkler, Plant Terraformer (home field only)
    "condenser": {"in": ["steam"], "out": ["water"]},   # Steam Condenser
    "reactor": {"in": ["water"]},                     # Reactor coolant
    "drone_service": {"in": ["oil"]},                 # Drone Service Station
    "bio_caster": {"in": ["steam", "water"]},         # Bio Caster heat and cooling
    "biomass_mixer": {"in": ["frozen_essence", "coastal_essence", "geothermal_essence", "volcanic_essence", "deep_essence"]},
    "refinery": {"in": ["raw_sulfur_gas", "raw_chlorine", "raw_cryofluid", "raw_quicksilver"],
                 "out": ["sulfur_gas", "chlorine", "cryofluid", "quicksilver"]},   # Refiner recipes
    "wildlife": {"in": ["ammonia", "swamp_gas", "sulfur_gas", "chlorine", "brine", "cryofluid", "quicksilver"]},   # Habitat gas_in / liquid_in
}
HOME_ROLES = ["farm"]
BIOMES = ("frozen", "coastal", "geothermal", "volcanic", "deep")
# Every fluid id (docs/database/fluids.md), for the storage_<fluid> sub-roles.
FLUIDS = ("steam", "water", "oil", "frozen_essence", "coastal_essence", "geothermal_essence", "volcanic_essence",
          "deep_essence", "ammonia", "swamp_gas", "raw_sulfur_gas", "sulfur_gas", "raw_chlorine", "chlorine", "brine",
          "raw_cryofluid", "cryofluid", "raw_quicksilver", "quicksilver")

# One-fluid sub-roles, so exotics can be spread over several outposts:
# refinery_<refined fluid> refines its raw feed, wildlife_<fluid> takes one
# Habitat fluid. liquifier_<biome>: an Essence Liquifier makes its outpost
# biome's essence. storage_<fluid>: tanks that take and give back one fluid.
for _raw in DEFAULT_ROLE_PRESETS["refinery"]["in"]:
    DEFAULT_ROLE_PRESETS["refinery_" + _raw[len("raw_"):]] = {"in": [_raw], "out": [_raw[len("raw_"):]]}
for _fluid in DEFAULT_ROLE_PRESETS["wildlife"]["in"]:
    DEFAULT_ROLE_PRESETS["wildlife_" + _fluid] = {"in": [_fluid]}
for _biome in BIOMES:
    DEFAULT_ROLE_PRESETS["liquifier_" + _biome] = {"out": [_biome + "_essence"]}
for _fluid in FLUIDS:
    DEFAULT_ROLE_PRESETS["storage_" + _fluid] = {"in": [_fluid], "out": [_fluid]}


def presets():
    """autoplay.role_presets; seeds DEFAULT_ROLE_PRESETS when the key is missing or malformed."""
    raw = archive.get(PRESETS_KEY, None)
    if isinstance(raw, dict):
        return raw
    try:
        archive.set(PRESETS_KEY, DEFAULT_ROLE_PRESETS)
    except Exception as error:
        swallowed("autoplay_roles.presets: archive.set", error)
    return DEFAULT_ROLE_PRESETS


def outpost_roles():
    """autoplay.outpost_roles as a dict ({} when missing or malformed)."""
    raw = archive.get(ROLES_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _fluid_list(value):
    return [fluid for fluid in value if isinstance(fluid, str)] if isinstance(value, (list, tuple)) else []


def fluids_for(roles, role_presets):
    """
    {"in": [...], "out": [...], "order": [...]} of one outpost's roles (a role
    name or a list of them), each ordered and de-duplicated; order = every
    fluid in role order, a role's "in" before its "out". Unknown roles add nothing.
    """
    names = [roles] if isinstance(roles, str) else (roles if isinstance(roles, (list, tuple)) else [])
    out = {"in": [], "out": [], "order": []}
    for name in names:
        preset = role_presets.get(name)
        if isinstance(preset, (list, tuple)):
            preset = {"in": preset}
        if not isinstance(preset, dict):
            continue
        for side in ("in", "out"):
            for fluid in _fluid_list(preset.get(side)):
                if fluid not in out[side]:
                    out[side].append(fluid)
                if fluid not in out["order"]:
                    out["order"].append(fluid)
    return out


def demand(outpost_ids, roles_map, role_presets, home_id=None):
    """{outpost_id: fluids_for()} for the live outposts with at least one fluid; home_id gets HOME_ROLES after its own roles."""
    out = {}
    for outpost_id in outpost_ids:
        roles = roles_map.get(outpost_id)
        if outpost_id == home_id:
            roles = ([roles] if isinstance(roles, str) else list(roles or [])) + HOME_ROLES
        fluids = fluids_for(roles, role_presets)
        if fluids["order"]:
            out[outpost_id] = fluids
    return out


def prune_roles(live_ids):
    """Drops autoplay.outpost_roles entries of outposts not in live_ids; returns how many dropped."""
    stale = [outpost_id for outpost_id in outpost_roles() if outpost_id not in live_ids]
    if not stale:
        return 0

    def updater(entries):
        if not isinstance(entries, dict):
            return {}
        for outpost_id in stale:
            entries.pop(outpost_id, None)
        return entries

    archive.transaction(ROLES_KEY, {}, updater)
    return len(stale)
