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
# An outpost's "supply" = the "out" fluids of its roles that are a source of
# their own: not BACKUP_ROLES (a Steam Condenser is only a backup for water
# pumps) and not storage_<fluid> (a tank gives back what it was given).
# Only supply counts when the planner asks whether a fluid has a producer.
#
# autoplay.outpost_roles is the designation (intent): it drives every autoplay
# pass, also for roles whose buildings are not deployed or not unlocked yet.
# Machine scripts go by the buildings actually there; role_gaps() compares
# the two (ROLE_CATALOG).

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
BACKUP_ROLES = ("condenser",)   # roles whose "out" is no supply of its own (storage_<fluid> neither)
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
# bio_<biome>: the biome's Bio Lab chain; Volcanic's Bio Caster takes the bio_caster fluids.
for _biome in BIOMES:
    DEFAULT_ROLE_PRESETS["bio_" + _biome] = dict(DEFAULT_ROLE_PRESETS["bio_caster"]) if _biome == "volcanic" else {}

# Role structure for the outpost founding planner (code-side; the archive
# presets above own only the fluids). Per role:
#   buildings  [group, ...]: a group is a type_id or a list of alternative
#              type_ids; the role is observed at an outpost when every group
#              has one alternative deployed there, unlocked when every group
#              has one alternative whose kit can be had (kit_id()).
#   biome      biome lock (the outpost's biome at its anchor) or None.
#   unique     holds a max-one-per-outpost machine.
#   items      takes part in item logistics (needs a Drone Depot).
#   ore        wants ore sites near the footprint.
#   biosites   wants biosites of its biome near the footprint.
# Not in the catalog: no buildings, never observed; founding treats it as
# fluids only.
BIO_PROCESSORS = {"coastal": "bio_luminizer", "geothermal": "dna_sequencer", "volcanic": "bio_caster", "deep": "bio_conditioner"}
TANKS = ["liquid_tank", "gas_tank", "bulk_liquid_reservoir"]
WAREHOUSES = ["warehouse", "large_warehouse"]
DEPOTS = ["drone_station", "drone_station_medium", "drone_station_large"]
ROLE_CATALOG = {
    "factory": {"buildings": ["fabricator"], "items": True},
    "smelter": {"buildings": ["smelter"], "items": True},
    "mining": {"buildings": [WAREHOUSES], "items": True, "ore": True},
    "storage": {"buildings": [WAREHOUSES], "items": True},
    "drone_depot": {"buildings": [DEPOTS]},
    "drone_service": {"buildings": ["drone_service_station"]},
    "power": {"buildings": [["steam_turbine", "oil_generator"]]},
    "condenser": {"buildings": ["steam_condenser"]},
    "reactor": {"buildings": ["reactor"]},
    "terraform": {"buildings": [["oxygen_generator", "pressure_generator", "temp_heater"]]},
    "biomass_mixer": {"buildings": ["biomass_mixer"]},
    "refinery": {"buildings": ["refiner"]},
    "wildlife": {"buildings": ["habitat"], "items": True},
    "bio_caster": {"buildings": ["bio_caster"], "biome": "volcanic", "unique": True},
}
for _biome in BIOMES:
    _chain = ["bio_collector", "bio_lab", "bio_exchange"] + ([BIO_PROCESSORS[_biome]] if _biome in BIO_PROCESSORS else [])
    ROLE_CATALOG["bio_" + _biome] = {"buildings": _chain, "biome": _biome, "unique": True, "items": True, "biosites": True}
    ROLE_CATALOG["weather_" + _biome] = {"buildings": ["weather_station"], "biome": _biome, "unique": True}
    ROLE_CATALOG["liquifier_" + _biome] = {"buildings": ["essence_liquifier"], "biome": _biome, "items": True, "biosites": True}
for _raw in DEFAULT_ROLE_PRESETS["refinery"]["in"]:
    ROLE_CATALOG["refinery_" + _raw[len("raw_"):]] = {"buildings": ["refiner"]}
for _fluid in DEFAULT_ROLE_PRESETS["wildlife"]["in"]:
    ROLE_CATALOG["wildlife_" + _fluid] = {"buildings": ["habitat"], "items": True}
for _fluid in FLUIDS:
    ROLE_CATALOG["storage_" + _fluid] = {"buildings": [TANKS]}
# Roles one Fluid-parameterised building stands for many times over; an
# observed tank or Refiner does not tell which of them it is.
FAMILY_PREFIXES = ("storage_", "refinery_", "wildlife_", "liquifier_", "weather_")

# Overcrowding (simworker machine table): counted buildings that lose 10%
# per building over the outpost cap; every other counted building is exempt.
PENALIZED_TYPES = ("smelter", "fabricator", "refiner", "bio_collector", "bio_lab", "bio_exchange", "bio_luminizer",
                   "dna_sequencer", "bio_caster", "bio_conditioner", "essence_liquifier", "biomass_mixer", "seed_maker",
                   "feed_maker", "habitat", "plant_terraformer", "reactor", "fuel_assembler", "steam_turbine",
                   "steam_condenser", "oil_generator", "solar_generator", "oxygen_generator", "temp_heater",
                   "pressure_generator", "garbage_disposal", "lightning_rod", "charging_station",
                   "drone_service_station", "supply_dock")
# Warehouse stock per role off home (remote outposts have no Inventory): one
# 2000-unit slot per stocked item. stock_items() fills smelter / factory /
# mining item lists from in-game recipes and sites; roles here without a
# list use STOCK_FALLBACK_SLOTS. FACTORY_BUFFER_SLOTS = room on top of the
# factory's ingots for intermediates and finished goods.
WAREHOUSE_SLOTS = {"warehouse": 5, "large_warehouse": 15}
FACTORY_BUFFER_SLOTS = 10
SMELTER_FALLBACK_SLOTS = 14   # no Smelter recipe readable yet: 7 ores + 7 ingots
STOCK_FALLBACK_SLOTS = {"smelter": SMELTER_FALLBACK_SLOTS, "factory": 7, "mining": 1}
STOCK_PREFIX_SLOTS = {"bio_": 2, "liquifier_": 2, "wildlife": 2}   # samples, life forms, feed (guess, tune live)

# Kit item ids that differ from the building's type_id.
KIT_IDS = {"drone_station": "drone_station_kit", "drone_station_medium": "drone_station_kit_medium",
           "drone_station_large": "drone_station_kit_large", "drone_service_station": "drone_service_station_kit"}


def presets():
    """
    autoplay.role_presets; seeds DEFAULT_ROLE_PRESETS when the key is missing
    or malformed, and adds default roles the stored dict lacks (operator
    edits of existing roles are kept).
    """
    raw = archive.get(PRESETS_KEY, None)
    if isinstance(raw, dict):
        missing = [name for name in DEFAULT_ROLE_PRESETS if name not in raw]
        if not missing:
            return raw
        merged = dict(raw)
        for name in missing:
            merged[name] = DEFAULT_ROLE_PRESETS[name]
        value = merged
    else:
        value = DEFAULT_ROLE_PRESETS
    try:
        archive.set(PRESETS_KEY, value)
    except Exception as error:
        swallowed("autoplay_roles.presets: archive.set", error)
    return value


def kit_id(type_id):
    """Kit item id that deploys a building of type_id."""
    return KIT_IDS.get(type_id, type_id)


def _groups(name):
    """A role's building groups as lists of alternative type_ids ([] when the role is not in ROLE_CATALOG)."""
    spec = ROLE_CATALOG.get(name) or {}
    return [group if isinstance(group, list) else [group] for group in spec.get("buildings", [])]


def role_flag(name, flag):
    """ROLE_CATALOG field of a role (False / None when absent)."""
    return (ROLE_CATALOG.get(name) or {}).get(flag, None if flag == "biome" else False)


def role_list(roles):
    """A designation (role name, list of names, or None) as a list of names."""
    if isinstance(roles, str):
        return [roles]
    return [name for name in roles if isinstance(name, str)] if isinstance(roles, (list, tuple)) else []


def observed(name, type_counts):
    """True when every building group of a catalog role has a deployed alternative in type_counts ({type_id: n})."""
    groups = _groups(name)
    return bool(groups) and all(any(type_counts.get(type_id, 0) > 0 for type_id in group) for group in groups)


def observed_roles(type_counts):
    """Catalog roles the buildings in type_counts make up, family sub-roles (FAMILY_PREFIXES) left out; sorted."""
    return sorted([name for name in ROLE_CATALOG
                   if not name.startswith(FAMILY_PREFIXES) and observed(name, type_counts)])


def role_gaps(designated, type_counts):
    """
    {"missing": [...], "extra": [...]} for one outpost: designated catalog
    roles whose buildings are not all deployed yet (the building planner's
    backlog), and observed roles nobody designated (operator built by hand).
    Roles outside the catalog are fluid-only and never missing.
    """
    names = role_list(designated)
    missing = [name for name in names if name in ROLE_CATALOG and not observed(name, type_counts)]
    covered = set()
    for name in names:
        for group in _groups(name):
            covered.update(group)
    extra = [name for name in observed_roles(type_counts)
             if name not in names and not all(type_id in covered for group in _groups(name) for type_id in group)]
    return {"missing": missing, "extra": extra}


def unlocked(name, available_kits):
    """True when every building group of the role has an alternative whose kit is in available_kits; non-catalog roles are always unlocked."""
    return all(any(kit_id(type_id) in available_kits for type_id in group) for group in _groups(name))


def biome_ok(name, biome):
    """False when the role is locked to another biome than `biome`."""
    lock = role_flag(name, "biome")
    return lock is None or lock == biome


def bundle_slots(roles, warehouses=True):
    """
    (counted, penalized) building slots a designation needs: one slot per
    building group across its catalog roles, a type shared by two roles
    counted once; penalized = how many of them lose efficiency over the cap.
    warehouses=False leaves the Warehouse group out (site_slots() sizes it).
    """
    seen = []
    for name in role_list(roles):
        for group in _groups(name):
            if group not in seen and (warehouses or group != WAREHOUSES):
                seen.append(group)
    penalized = len([group for group in seen if any(type_id in PENALIZED_TYPES for type_id in group)])
    return len(seen), penalized


def _role_stock_fallback(name):
    if name in STOCK_FALLBACK_SLOTS:
        return STOCK_FALLBACK_SLOTS[name]
    for prefix in STOCK_PREFIX_SLOTS:
        if name.startswith(prefix):
            return STOCK_PREFIX_SLOTS[prefix]
    return 0


def stock_slots(roles, stock):
    """
    Warehouse slots a designation stocks: the distinct items of its roles'
    lists in stock ({role: [item_id, ...]}, an item shared by two roles
    counted once), the fallback slots of item roles without a list, and
    FACTORY_BUFFER_SLOTS for a factory. storage is sized by what it holds,
    not by its role: 0 here.
    """
    items = set()
    extra = 0
    for name in role_list(roles):
        if not role_flag(name, "items") or name == "storage":
            continue
        listed = stock.get(name)
        if isinstance(listed, (list, tuple)) and listed:
            items.update(listed)
        else:
            extra += _role_stock_fallback(name)
        if name == "factory":
            extra += FACTORY_BUFFER_SLOTS
    return len(items) + extra


def site_slots(roles, stock, have_slots=0, per_warehouse=5, home=False):
    """
    (counted, penalized, warehouses) a designation needs at one outpost:
    its machine groups (Warehouse group left out) plus the Warehouses its
    stock_slots() need beyond the have_slots already standing there. Home
    stocks in Inventory: no Warehouses.
    """
    counted, penalized = bundle_slots(roles, warehouses=False)
    if home:
        return (counted, penalized, 0)
    deficit = max(0, stock_slots(roles, stock) - have_slots)
    count = (deficit + per_warehouse - 1) // per_warehouse
    return (counted + count, penalized, count)


def warehouse_slots(type_counts):
    """(Warehouse slots, Warehouse buildings) standing at an outpost."""
    slots = int(sum([WAREHOUSE_SLOTS[type_id] * type_counts.get(type_id, 0) for type_id in WAREHOUSE_SLOTS]))
    return (slots, int(sum([type_counts.get(type_id, 0) for type_id in WAREHOUSE_SLOTS])))


def biome_locks(roles):
    """Sorted biome locks of a designation's roles; more than one means no outpost can host it."""
    return sorted(set([role_flag(name, "biome") for name in role_list(roles) if role_flag(name, "biome")]))


def outpost_roles():
    """autoplay.outpost_roles as a dict ({} when missing or malformed)."""
    raw = archive.get(ROLES_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _fluid_list(value):
    return [fluid for fluid in value if isinstance(fluid, str)] if isinstance(value, (list, tuple)) else []


def fluids_for(roles, role_presets):
    """
    {"in": [...], "out": [...], "supply": [...], "order": [...]} of one
    outpost's roles (a role name or a list of them), each ordered and
    de-duplicated; supply = the "out" fluids of source roles (is_source_role());
    order = every fluid in role order, a role's "in" before its "out".
    Unknown roles add nothing.
    """
    names = [roles] if isinstance(roles, str) else (roles if isinstance(roles, (list, tuple)) else [])
    out = {"in": [], "out": [], "supply": [], "order": []}
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
                if side == "out" and is_source_role(name) and fluid not in out["supply"]:
                    out["supply"].append(fluid)
    return out


def is_source_role(name):
    """False for BACKUP_ROLES and storage_<fluid> roles: their "out" is no supply of its own."""
    return name not in BACKUP_ROLES and not name.startswith("storage_")


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
