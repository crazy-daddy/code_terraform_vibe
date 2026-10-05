# Water Pump salt as a pickup source for the reverse hauler
# (lib/vehicle_cargo.py run_pull_loop()), and home's salt request.
#
# Pumps make salt as a byproduct into their `output` (a PickupOutputSlot);
# only a physically present Rover or Pioneer can take() it -- drones get
# "not_at_source" (confirmed live). Pumps are field structures on water wells,
# not outpost buildings, so they are found through the journal: every
# surveyed WaterWell with has_pump() gives the pump id and the well's
# coordinates. The well list is cached (PUMP_CACHE_TICKS); salt counts are
# read live.
#
# Home salt request (publish_home_salt_request(), requester SALT_REQUESTER_ID,
# run by the Control Room Automation so it outlives the Harvester and
# Terraformer scripts): salt's only consumers are home's Plants -- the field
# (Harvester hand care, Dispensers) and the Plant Terraformers from 1.25m km^2
# on. All pumps together make at most 50 salt/h, so salt stored early
# shortens the late game. logistics.requests holds one requester per item per
# outpost, so this one request covers both:
#   min    = SALT_FIELD_UNITS (one Warehouse slot): the field's stock, need tier
#   target = min + salt_to_finish(Plants km^2): what the Terraformers still
#            burn up to 5m km^2, buffer tier; capped so home Warehouses keep
#            SALT_KEEP_FREE units of room
# Being a real request, outpost_free_tiers() keeps it back from other
# outposts' buffers, and salt anywhere on the network is pulled home.

from storage import discover_storage_buildings, total_stock
import logistics_requests
from tree_console import TreeConsole
from components import water_pump
from swallow import swallowed
from game_clock import now_tick

log = TreeConsole(module="pump_salt")

SALT_ITEM_ID = "salt"
SALT_REQUESTER_ID = "salt_reserve"
PUMP_CACHE_TICKS = 3000        # re-walk the journal's wells at most every ~5 min
PUMP_ARRIVAL_PRECISION_M = 2.0
# Need tier of the home salt request: one Warehouse slot for the field.
SALT_FIELD_UNITS = 2000
# Warehouse room (units) the salt target always leaves free at home: two slots.
SALT_KEEP_FREE = 4000
# Plant Terraformer bands that use salt (docs/guide/plant_terraformer_guide.md):
# (from km^2, to km^2, km^2 per Forage). Salt: 1 per SALT_FORAGE_PER_ITEM
# Forage, rounded up per batch -- at most one extra item per full Mk II batch
# (TERRAFORMER_MK2_BATCH Forage).
SALT_BANDS = ((1250000, 2250000, 5.0 / 3.0), (2250000, 3500000, 1.0), (3500000, 5000000, 1.0 / 3.0))
SALT_FORAGE_PER_ITEM = 500
TERRAFORMER_MK2_BATCH = 6600

_cache = {"tick": None, "pumps": {}}


def pump_positions(curr_tick=None):
    """{pump_id: [x, y]} for every Water Pump standing on a surveyed well."""
    log.start("pump_positions", level="debug")
    tick = curr_tick if curr_tick is not None else now_tick()
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
    pump = water_pump(pump_id)
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


def _free_warehouse_units(outpost: "OutpostRef"):
    free = 0
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        try:
            free += int(component.capacity()) - int(component.total())
        except Exception as error:
            swallowed("pump_salt._free_warehouse_units: component.capacity", error)
    return max(0, free)


def salt_to_finish(plants_km2):
    """Salt the Plant Terraformers still burn from `plants_km2` up to 5m km^2 (None = 0 km^2)."""
    done = float(plants_km2 or 0.0)
    forage = 0.0
    for low, high, km2_per_forage in SALT_BANDS:
        if done < high:
            forage += (high - max(done, low)) / km2_per_forage
    if forage <= 0:
        return 0
    return int(-(-(forage / SALT_FORAGE_PER_ITEM + forage / TERRAFORMER_MK2_BATCH) // 1))


def plants_km2():
    """Permanent Plants km^2 from the Plants Sensor, or None when there is none."""
    try:
        sensor = get_component("plants_sensor")
        return float(sensor.get_value()) if sensor else None
    except Exception as error:
        swallowed("pump_salt.plants_km2: get_component", error)
        return None


def publish_home_salt_request(home, curr_tick=None):
    """
    Publishes home's salt request (see module header) through
    logistics_requests.publish_requests(); returns its target, or None when
    there is no home. It overrides any other requester's salt entry at home:
    this target already covers the Terraformers' salt.
    """
    home_id = getattr(home, "id", None)
    if not home_id:
        return None
    tick = curr_tick if curr_tick is not None else now_tick()
    km2 = plants_km2()
    finish = salt_to_finish(km2)
    have = total_stock(SALT_ITEM_ID, home)
    room = max(0, _free_warehouse_units(home) - SALT_KEEP_FREE)
    target = max(SALT_FIELD_UNITS, min(SALT_FIELD_UNITS + finish, have + room))
    if logistics_requests.publish_requests(home_id, SALT_REQUESTER_ID, {SALT_ITEM_ID: (target, have, SALT_FIELD_UNITS)}, tick, skip_foreign=False):
        log.debug(f"home salt request: plants {km2} km^2, Terraformers still need {finish}, have {have}, room {room} -> target {target} (min {SALT_FIELD_UNITS}).")
    return target
