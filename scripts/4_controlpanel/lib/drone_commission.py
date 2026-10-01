# Drone commissioning presets for the COMMISSION card (lib/fleet_commission.py).
#
# A drone job crafts its whole kit before deploying: the best chassis the
# Fabricator can build (or Inventory already holds), an electric thruster and
# one module per LOADOUTS slot of that chassis (lib/drone_upgrade.py), each at
# its best obtainable tier. A Fabricator builds them through
# fabricator.upgrade_orders (requester COMMISSION_REQUESTER); deploy() and
# couple() take them from home Inventory (storage.INVENTORY_ONLY_ITEM_IDS).
# Parts a remote fab site builds are hauled home on site supply's home pull
# request (lib/site_supply.py consumer_wants()) and unloaded straight into
# Inventory (storage.best_unload_target()).
# A part the Fabricator can't craft but the Shop sells (the miner's Portable
# Bio Extractor) is bought instead, through the cash manager (consumer
# "drone_commission", lib/cash.py); spec["buy"] lists those parts.
#
# After the deploy the drone fits itself with the unchanged new-chassis path
# (DroneUpgradeMixin.fit_loadout_if_new()): the coordinator writes a
# fleet.upgrade lineage entry with "job" instead of "from", and its "params"
# carry HOME_DEPOT, which DroneController reads for a script left at defaults
# and devtools/scripts_sync.py fills into the new slot.
#
# spec = {"kind": chassis, "engine": "electric", "role", "modules": [item_id, ...], "buy": [item_id, ...]}
#        modules = thruster first, then LOADOUTS[role][kind] in slot order
#        buy = parts of the spec bought at the Shop (not craftable, not held)

from drone_upgrade import LOADOUTS, THRUSTER_BY_ENGINE, BATTERY_TIERS, CARGO_POD_TIERS, ROLE_MODULE_ITEMS

# Worst -> best; lib/fleet_upgrade.py swaps along the same ladder.
DRONE_CHASSIS_TIERS = ["drone_small", "drone_medium", "drone_large"]
# Roles the card offers: the ones with a LOADOUTS entry (scouts are one-off,
# hand-built).
DRONE_ROLES = tuple(r for r in ("hauler", "miner", "aftermath") if r in LOADOUTS)
# Electric only: heli drones need an oil-distribution check first (TODO.md).
COMMISSION_ENGINE = "electric"
# fabricator.upgrade_orders requester id for commissioned drone kits
# (production.STANDING_ORDER_REQUESTERS keeps fleet_upgrade from pruning it).
COMMISSION_REQUESTER = "fleet_commission"


def _ladder(category, role):
    if category == "energy":
        return BATTERY_TIERS
    if category == "cargo":
        return CARGO_POD_TIERS
    if category == "role":
        item = ROLE_MODULE_ITEMS.get(role)
        return [item] if item else []
    return []


def _best(ladder, obtainable):
    for item_id in reversed(ladder):
        if obtainable(item_id):
            return item_id
    return None


def build_drone_spec(role, unlocked, inventory_count, buyable=()):
    """
    (spec, None) for role at the best obtainable tiers, or (None, reason).
    unlocked: item ids the Fabricator can craft; inventory_count(item_id) ->
    units held; buyable: item ids the Shop sells. An item counts as
    obtainable when any is true; one only the Shop has goes in spec["buy"].
    """
    loadouts = LOADOUTS.get(role)
    if not loadouts:
        return None, f"unknown drone role {role!r}"

    def obtainable(item_id):
        return item_id in unlocked or inventory_count(item_id) > 0 or item_id in buyable

    kind = _best([k for k in DRONE_CHASSIS_TIERS if k in loadouts], obtainable)
    if kind is None:
        return None, "no drone chassis craftable"
    thruster = THRUSTER_BY_ENGINE[COMMISSION_ENGINE]
    if not obtainable(thruster):
        return None, f"{thruster} not obtainable"
    modules = [thruster]
    for category in loadouts[kind]:
        item = _best(_ladder(category, role), obtainable)
        if item is None:
            return None, f"{category} module not obtainable"
        modules.append(item)
    buy = sorted({i for i in [kind] + modules if i not in unlocked and inventory_count(i) <= 0})
    return {"kind": kind, "engine": COMMISSION_ENGINE, "role": role, "modules": modules, "buy": buy}, None


def drone_craft_parts(spec):
    """{item_id: count} of spec's parts the Fabricator builds (everything not in spec["buy"])."""
    buy = set(spec.get("buy") or [])
    return {i: n for i, n in drone_spec_parts(spec).items() if i not in buy}


def drone_buy_parts(spec):
    """{item_id: count} of spec's parts bought at the Shop."""
    buy = set(spec.get("buy") or [])
    return {i: n for i, n in drone_spec_parts(spec).items() if i in buy}


def drone_spec_parts(spec):
    """{item_id: count} for the chassis and every module of spec."""
    parts = {spec["kind"]: 1}
    for item in spec.get("modules") or []:
        parts[item] = parts.get(item, 0) + 1
    return parts
