# Item tier ladders: every hardware family the fleet buys, upgrades or ranks,
# worst -> best. The game API has no item -> tier lookup (a mounted module's
# tier() only names its own tier), so the ladders live here, once.
# tests/test_item_tiers.py checks each ladder against docs/database/, so a
# game build that adds a tier fails the suite until the ladder lists it.
# Pure data and pure functions, no game calls.

# Pioneer function modules. The Rover's fixed slots take only the first entry.
SONAR_TIERS = ["sonar_module", "sonar_module_wide", "sonar_module_deep", "sonar_module_seismic"]
DRILL_TIERS = ["drill_module", "drill_module_industrial", "drill_module_heavy"]

# Pioneer containers and the portable items that fill their bays.
BATTERY_HOLDER_TIERS = ["battery_holder_small", "battery_holder_medium", "battery_holder_large"]
CARGO_RACK_TIERS = ["cargo_rack_small", "cargo_rack_medium", "cargo_rack_large"]
PORTABLE_BATTERY_TIERS = ["portable_battery", "heavy_portable_battery"]
PORTABLE_BIN_TIERS = ["portable_bin", "heavy_portable_bin"]

# Drone chassis and modules.
DRONE_CHASSIS_TIERS = ["drone_small", "drone_medium", "drone_large"]
CARGO_POD_TIERS = ["cargo_pod_small", "cargo_pod_medium", "cargo_pod_large"]
OIL_TANK_TIERS = ["oil_tank_small", "oil_tank_medium", "oil_tank_large"]
BATTERY_TIERS = ["battery_pack"]

# Drone Depot: the kit item and the building typeId it deploys, same order.
# The typeId is "drone_station", not "drone_depot" ("Drone Depot" is only the
# display name). outpost.buildings(type_id) matches one exact typeId, so
# callers that look for "any Depot" iterate DEPOT_TYPE_TIERS. Instance and
# script ids differ from the typeIds: drone_station_med_N / drone_station_lrg_N.
DEPOT_KIT_TIERS = ["drone_station_kit", "drone_station_kit_medium", "drone_station_kit_large"]
DEPOT_TYPE_TIERS = ["drone_station", "drone_station_medium", "drone_station_large"]
DEPOT_KIT_FOR_TYPE = dict(zip(DEPOT_TYPE_TIERS, DEPOT_KIT_TIERS))


def tier_rank(ladder, item_id):
    """Index of item_id in ladder, -1 when absent (unknown or legacy value)."""
    return ladder.index(item_id) if item_id in ladder else -1


def best_mounted(slots, ladder):
    """Best item id from ladder among MountSlot-like `slots` (.module_id), None when none is mounted."""
    best = None
    for slot in slots or ():
        module_id = getattr(slot, "module_id", None)
        if module_id in ladder and tier_rank(ladder, module_id) > tier_rank(ladder, best):
            best = module_id
    return best


def short_name(item_id):
    """Ladder id without its family prefix, for compact labels ("sonar_module_wide" -> "wide")."""
    for prefix, base in (("sonar_module_", "sonar_module"), ("drill_module_", "drill_module")):
        if item_id == base:
            return "basic"
        if isinstance(item_id, str) and item_id.startswith(prefix):
            return item_id[len(prefix):]
    return str(item_id)
