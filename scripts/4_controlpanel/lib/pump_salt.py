# Water Pump salt as a pickup source for the reverse hauler
# (lib/vehicle_cargo.py run_pull_loop()).
#
# Pumps make salt as a byproduct into their `output` (a PickupOutputSlot);
# only a physically present Rover or Pioneer can take() it -- drones get
# "not_at_source" (confirmed live). Pumps are field structures on water wells,
# not outpost buildings, so they are found through the journal: every
# surveyed WaterWell with has_pump() gives the pump id and the well's
# coordinates. The well list is cached (PUMP_CACHE_TICKS); salt counts are
# read live.
#
# Salt reserve: all pumps together make at most 50 salt/h, and from the third
# Plants band on every Terraformer Forage needs salt, so salt produced early
# and stored shortens the late game. A home reverse hauler with nothing else
# to do tops a home salt reserve up to SALT_RESERVE_TARGET
# (salt_reserve_deficit()), never filling home Warehouses past
# SALT_RESERVE_KEEP_FREE units of room.

from storage import discover_storage_buildings, total_stock
import logistics_requests
from tree_console import TreeConsole
from swallow import swallowed

log = TreeConsole(module="pump_salt")

SALT_ITEM_ID = "salt"
PUMP_CACHE_TICKS = 3000        # re-walk the journal's wells at most every ~5 min
PUMP_ARRIVAL_PRECISION_M = 2.0
# Home salt the idle reverse hauler stocks up to: the Terraformers' whole
# salt use from 1.25m to 5m km^2 (0.002 salt/Forage, docs/cheatsheet/bio_seeds_planting.md).
SALT_RESERVE_TARGET = 13000
# Warehouse room (units) the reserve always leaves free at home: two slots.
SALT_RESERVE_KEEP_FREE = 4000
# A reserve trip only runs with at least this much salt planned.
SALT_RESERVE_MIN_LOAD = 20

_cache = {"tick": None, "pumps": {}}


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed("pump_salt._now_tick: get_component", error)
        return 0


def pump_positions(curr_tick=None):
    """{pump_id: [x, y]} for every Water Pump standing on a surveyed well."""
    log.start("pump_positions", level="debug")
    tick = curr_tick if curr_tick is not None else _now_tick()
    if _cache["tick"] is not None and tick - _cache["tick"] < PUMP_CACHE_TICKS:
        log.end()
        return _cache["pumps"]
    pumps = {}
    journal = get_component("journal")
    try:
        sites = journal.surveyed_sites("nocturna") if journal else []
    except Exception as e:
        log.debug(f"surveyed_sites() raised {e}")
        sites = []
    for site in sites or []:
        # Only WaterWell carries has_pump()/pump_id(); other Site kinds lack them.
        has_pump = getattr(site, "has_pump", None)
        get_pump_id = getattr(site, "pump_id", None)
        if has_pump is None or get_pump_id is None:
            continue
        try:
            if site.kind() != "water" or not has_pump():
                continue
            pump_id = get_pump_id()
        except Exception as error:
            swallowed("pump_salt.pump_positions: site.kind", error)
            continue
        if pump_id:
            pumps[pump_id] = [site.x, site.y]
    _cache["tick"] = tick
    _cache["pumps"] = pumps
    log.debug(f"{len(pumps)} Water Pump(s) on surveyed wells.")
    log.end()
    return pumps


def salt_at(pump_id):
    """Units of salt waiting in the pump's pickup output."""
    pump = get_component(pump_id)
    port = getattr(pump, "output", None) if pump else None
    if port is None:
        return 0
    try:
        return int(port.count())
    except Exception as error:
        swallowed("pump_salt.salt_at: port.count", error)
        return 0


def salt_sources(curr_tick=None):
    """{pump_id: {"coords": [x, y], "available": units}} for pumps holding salt."""
    out = {}
    for pump_id, coords in pump_positions(curr_tick).items():
        units = salt_at(pump_id)
        if units > 0:
            out[pump_id] = {"coords": coords, "available": units}
    return out


def _free_warehouse_units(outpost):
    free = 0
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        try:
            free += int(component.capacity()) - int(component.total())
        except Exception as error:
            swallowed("pump_salt._free_warehouse_units: component.capacity", error)
    return max(0, free)


def salt_reserve_deficit(outpost, curr_tick=None):
    """
    Salt units the home reserve still wants (0 away from home): up to
    SALT_RESERVE_TARGET minus salt at home and salt already on its way, and
    never more than the Warehouse room above SALT_RESERVE_KEEP_FREE.
    """
    if outpost is None or not getattr(outpost, "is_home", False):
        return 0
    have = total_stock(SALT_ITEM_ID, outpost)
    flying = logistics_requests.in_flight(getattr(outpost, "id", None), curr_tick).get(SALT_ITEM_ID, 0)
    room = _free_warehouse_units(outpost) - SALT_RESERVE_KEEP_FREE
    deficit = max(0, min(SALT_RESERVE_TARGET - have - flying, room))
    log.debug(f"salt_reserve_deficit: have {have}, in flight {flying}, room {room} -> {deficit}.")
    return int(deficit)
