# Drone commissioning presets for the COMMISSION card (lib/fleet_commission.py).
#
# A drone job crafts its whole kit before deploying: the best chassis the
# Fabricator can build (or Inventory already holds), an electric thruster and
# one module per LOADOUTS slot of that chassis (lib/drone_upgrade.py), each at
# its best obtainable tier. The Fabricator builds them through
# fabricator.upgrade_orders (requester COMMISSION_REQUESTER); they stay in
# Inventory (storage.INVENTORY_ONLY_ITEM_IDS) for deploy() and couple().
#
# After the deploy the drone fits itself with the unchanged new-chassis path
# (DroneUpgradeMixin.fit_loadout_if_new()): the coordinator writes a
# fleet.upgrade lineage entry with "job" instead of "from", and its "params"
# carry HOME_DEPOT, which DroneController reads for a script left at defaults
# and devtools/scripts_sync.py fills into the new slot.
#
# spec = {"kind": chassis, "engine": "electric", "role", "modules": [item_id, ...]}
#        modules = thruster first, then LOADOUTS[role][kind] in slot order

from drone_upgrade import LOADOUTS, THRUSTER_BY_ENGINE, BATTERY_TIERS, CARGO_POD_TIERS, ROLE_MODULE_ITEMS

# Worst -> best; lib/fleet_upgrade.py swaps along the same ladder.
DRONE_CHASSIS_TIERS = ["drone_small", "drone_medium", "drone_large"]
# Roles the card offers: the ones with a LOADOUTS entry (scouts are one-off,
# hand-built).
DRONE_ROLES = tuple(r for r in ("hauler", "miner") if r in LOADOUTS)
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


def build_drone_spec(role, unlocked, inventory_count):
    """
    (spec, None) for role at the best obtainable tiers, or (None, reason).
    unlocked: item ids the Fabricator can craft; inventory_count(item_id) ->
    units held. An item counts as obtainable when either is true.
    """
    loadouts = LOADOUTS.get(role)
    if not loadouts:
        return None, f"unknown drone role {role!r}"

    def obtainable(item_id):
        return item_id in unlocked or inventory_count(item_id) > 0

    kind = _best([k for k in DRONE_CHASSIS_TIERS if k in loadouts], obtainable)
    if kind is None:
        return None, "no drone chassis craftable"
    thruster = THRUSTER_BY_ENGINE[COMMISSION_ENGINE]
    if not obtainable(thruster):
        return None, f"{thruster} not craftable"
    modules = [thruster]
    for category in loadouts[kind]:
        item = _best(_ladder(category, role), obtainable)
        if item is None:
            return None, f"{category} module not craftable"
        modules.append(item)
    return {"kind": kind, "engine": COMMISSION_ENGINE, "role": role, "modules": modules}, None


def drone_spec_parts(spec):
    """{item_id: count} for the chassis and every module of spec."""
    parts = {spec["kind"]: 1}
    for item in spec.get("modules") or []:
        parts[item] = parts.get(item, 0) + 1
    return parts
