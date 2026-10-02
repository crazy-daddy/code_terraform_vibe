# Outpost roles for the infrastructure planner (autoplay/infra_planner_automation.py):
# which fluids each outpost needs piped in.
#
# Archive shapes (one shared dict per concern):
#   autoplay.role_presets = {role: [fluid_id, ...]}  seeded with DEFAULT_ROLE_PRESETS
#                           when missing, then operator-editable.
#   autoplay.outpost_roles = {outpost_id: role | [role, ...]}  operator-set; entries
#                           of outposts that no longer exist are pruned.
# The home outpost always has HOME_ROLES on top of its entry: the Harvester's
# field sits there. Any other outpost without an entry needs no fluid. Fluid
# order within a preset is the outpost's service order when its footprint runs
# out of ports for a medium.

from archive import archive
from swallow import swallowed

PRESETS_KEY = "autoplay.role_presets"
ROLES_KEY = "autoplay.outpost_roles"

# Fluid consumers per role (docs/database/fluids.md "Consumed by" / "Tier input").
DEFAULT_ROLE_PRESETS = {
    "factory": ["water", "oil", "steam"],   # Fabricator recipes
    "terraform": ["water", "steam"],        # Oxygen/Pressure Mk III water, Heat Mk III steam
    "power": ["steam", "oil"],              # Steam Turbine, Oil Generator
    "farm": ["water"],                      # Sprinkler, Plant Terraformer (home field only)
    "steam_hub": ["steam"],
    "refinery": ["raw_sulfur_gas", "raw_chlorine", "raw_cryofluid", "raw_quicksilver"],   # Refiner recipes
    "wildlife": ["ammonia", "swamp_gas", "sulfur_gas", "chlorine", "brine", "cryofluid", "quicksilver"],   # Habitat gas_in / liquid_in
}
HOME_ROLES = ["farm"]

# One-fluid sub-roles, so exotics can be spread over several outposts:
# refinery_<refined fluid> takes its raw feed, wildlife_<fluid> one Habitat fluid.
for _raw in DEFAULT_ROLE_PRESETS["refinery"]:
    DEFAULT_ROLE_PRESETS["refinery_" + _raw[len("raw_"):]] = [_raw]
for _fluid in DEFAULT_ROLE_PRESETS["wildlife"]:
    DEFAULT_ROLE_PRESETS["wildlife_" + _fluid] = [_fluid]


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


def fluids_for(roles, role_presets):
    """Ordered, de-duplicated fluids of one outpost's roles (a role name or a list of them); unknown roles add nothing."""
    names = [roles] if isinstance(roles, str) else (roles if isinstance(roles, (list, tuple)) else [])
    out = []
    for name in names:
        fluids = role_presets.get(name)
        for fluid in fluids if isinstance(fluids, (list, tuple)) else []:
            if isinstance(fluid, str) and fluid not in out:
                out.append(fluid)
    return out


def demand(outpost_ids, roles_map, role_presets, home_id=None):
    """{outpost_id: [fluid, ...]} for the live outposts with at least one fluid; home_id gets HOME_ROLES after its own roles."""
    out = {}
    for outpost_id in outpost_ids:
        roles = roles_map.get(outpost_id)
        if outpost_id == home_id:
            roles = ([roles] if isinstance(roles, str) else list(roles or [])) + HOME_ROLES
        fluids = fluids_for(roles, role_presets)
        if fluids:
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
