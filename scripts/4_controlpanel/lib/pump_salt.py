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

from tree_console import TreeConsole

log = TreeConsole(module="pump_salt")

SALT_ITEM_ID = "salt"
PUMP_CACHE_TICKS = 3000        # re-walk the journal's wells at most every ~5 min
PUMP_ARRIVAL_PRECISION_M = 2.0

_cache = {"tick": None, "pumps": {}}


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception:
        return 0


def pump_positions(curr_tick=None):
    """{pump_id: [x, y]} for every Water Pump standing on a surveyed well."""
    tick = curr_tick if curr_tick is not None else _now_tick()
    if _cache["tick"] is not None and tick - _cache["tick"] < PUMP_CACHE_TICKS:
        return _cache["pumps"]
    pumps = {}
    journal = get_component("journal")
    try:
        sites = journal.surveyed_sites("nocturna") if journal else []
    except Exception as e:
        log.debug(f"pump_positions: surveyed_sites() raised {e}")
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
        except Exception:
            continue
        if pump_id:
            pumps[pump_id] = [site.x, site.y]
    _cache["tick"] = tick
    _cache["pumps"] = pumps
    log.debug(f"pump_positions: {len(pumps)} Water Pump(s) on surveyed wells.")
    return pumps


def salt_at(pump_id):
    """Units of salt waiting in the pump's pickup output."""
    pump = get_component(pump_id)
    port = getattr(pump, "output", None) if pump else None
    if port is None:
        return 0
    try:
        return int(port.count())
    except Exception:
        return 0


def salt_sources(curr_tick=None):
    """{pump_id: {"coords": [x, y], "available": units}} for pumps holding salt."""
    out = {}
    for pump_id, coords in pump_positions(curr_tick).items():
        units = salt_at(pump_id)
        if units > 0:
            out[pump_id] = {"coords": coords, "available": units}
    return out
