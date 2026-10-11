# Charging-station discovery as module functions (layer 0 of the vehicle
# mixins, see docs/plans/mixin_refactor/README.md): every deployed Vehicle
# Charging Station across the outpost network, the nearest one, outpost and
# station lookup by id, the home staging slot and per-station queue load.
# No driving and no vehicle mixin imports; the VehicleEnergyMixin wrappers
# (lib/vehicle_energy.py) and VehicleChargingMixin (lib/vehicle_charging.py)
# pass in what they used to read from self.

import geometry
from components import home_outpost
from construction_plan import coords_of
from game_clock import TickCache
from swallow import swallowed

# all_stations() runs on every drive poll's return-energy check; results are reused for this
# many ticks (~2 s), so a newly placed station is seen at most that late.
STATION_DISCOVERY_TTL_TICKS = 20

# [station dicts]
_STATIONS = TickCache(STATION_DISCOVERY_TTL_TICKS)

# {vehicle name: station id last logged by nearest()}
_NEAREST_LOGGED = {}

# Building type id as returned by OutpostRef.buildings() / Machine.typeId
# ("charging_station"), not the component doc name
# ("vehicle_charging_station"), which never matches and silently made every
# station lookup fall back to the home slot.
CHARGING_STATION_TYPE_ID = "charging_station"


def all_stations():
    """
    Discovers every deployed Vehicle Charging Station across all owned outposts
    (outpost_network.outposts() already includes home), filtered by exact
    type_id so any number of stations is found regardless of id numbering.
    Returns a list of dicts: [{"id": str, "coords": (float, float), "outpost": str, "component": obj}]
    Memoized per script for STATION_DISCOVERY_TTL_TICKS; entries are shared, treat them as read-only.
    """
    return list(_STATIONS.get(_scan_stations))


def _scan_stations():
    stations = []
    found_ids = set()

    outpost_net = get_component("outpost_network")
    if outpost_net and hasattr(outpost_net, "outposts"):
        try:
            outposts = outpost_net.outposts()
        except Exception as error:
            swallowed("charging_stations.all_stations: outpost_net.outposts", error)
            outposts = []

        for op in outposts:
            if not hasattr(op, "buildings"):
                continue
            try:
                buildings = op.buildings(CHARGING_STATION_TYPE_ID)
            except Exception as error:
                swallowed("charging_stations.all_stations: op.buildings", error)
                continue
            for b in buildings:
                b_id = getattr(b, "id", "")
                if not b_id or b_id in found_ids:
                    continue
                pos = coords_of(getattr(b, "position", None))
                if not pos:
                    continue
                found_ids.add(b_id)
                stations.append({
                    "id": b_id,
                    "coords": pos,
                    "outpost": getattr(op, "id", ""),
                    "component": get_component(b_id) or b
                })

    return stations


def nearest(ref_coords, name, home_coords, home_station, log):
    """
    Returns the closest known charging station tuple to ref_coords:
    (coords, station_info_dict). If no station is detected, falls back to
    (home_coords, {"id": "home_slot", ...}) with home_station as its component.
    Logs the choice (to log, under vehicle name) only when it differs from the
    last one logged for that name; drive polls and budgets ask many times per trip.
    """
    stations = all_stations()
    if not stations:
        if _NEAREST_LOGGED.get(name) != "home_slot":
            _NEAREST_LOGGED[name] = "home_slot"
            log.debug(f"[{name}] get_nearest_charging_station: no stations discovered network-wide, falling back to home slot {home_coords}.")
        return home_coords, {"id": "home_slot", "coords": home_coords, "component": home_station}

    best_station = min(
        stations,
        key=lambda st: geometry.distance(ref_coords, st["coords"])
    )
    if _NEAREST_LOGGED.get(name) != best_station.get("id"):
        _NEAREST_LOGGED[name] = best_station.get("id")
        log.debug(f"[{name}] get_nearest_charging_station: chose '{best_station.get('id')}' at {best_station['coords']} ({geometry.distance(ref_coords, best_station['coords']):.1f}m), out of {len(stations)} candidate(s).")
    return best_station["coords"], best_station


def outpost_ref(outpost_id=None):
    """
    Resolves outpost_id to its live OutpostRef, or the home outpost if
    outpost_id is None. A one-off lookup-by-id utility -- VehicleController
    calls this exactly once at construction to populate self.home_outpost
    (see __init__), so prefer reading that cached field over calling this
    again for the vehicle's own home outpost. Still useful standalone for
    resolving some *other* outpost id (e.g. a future transporter's source
    outpost, distinct from this vehicle's own home_base).
    """
    if outpost_id is None:
        return home_outpost()
    network = get_component("outpost_network")
    if not network:
        return None
    if hasattr(network, "outposts"):
        try:
            for outpost in network.outposts():
                if getattr(outpost, "id", None) == outpost_id:
                    return outpost
        except Exception as error:
            swallowed("charging_stations.outpost_ref: network.outposts", error)
    return None


def station_at(outpost: "OutpostRef | None"):
    """
    First Vehicle Charging Station building object at outpost (an
    already-resolved outpost object, not an id -- see outpost_ref()).
    Called once at construction to populate self.home_charging_station;
    prefer that cached field over calling this again for the vehicle's
    own home outpost.
    """
    if not outpost or not hasattr(outpost, "buildings"):
        return None
    try:
        for b in outpost.buildings(CHARGING_STATION_TYPE_ID):
            if coords_of(getattr(b, "position", None)):
                return b
    except Exception as error:
        swallowed("charging_stations.station_at: outpost.buildings", error)
    return None


def home_slot_coords(home_station, home_outpost_ref):
    """
    Calculates the base / charging station staging coordinates for a
    vehicle, at whichever outpost its home_base names (None = the
    production/home outpost). All vehicles dock within the ~2m common
    service area of base & charging station. Reads the vehicle's cached
    home_charging_station / home_outpost (resolved once at construction,
    see VehicleController.__init__), not re-walked here. Falls back to the
    outpost's own coords() if it has no charging station yet, and only to
    a literal (0, 0) if outpost_network itself was unavailable at
    construction time.
    """
    if home_station is not None:
        pos = coords_of(getattr(home_station, "position", None))
        if pos:
            return pos
    if home_outpost_ref is not None and hasattr(home_outpost_ref, "coords"):
        try:
            coords = home_outpost_ref.coords()
            if coords:
                return (float(coords[0]), float(coords[1]))
        except Exception as error:
            swallowed("charging_stations.home_slot_coords: home_outpost.coords", error)
    return (0.0, 0.0)


def current(vehicle):
    """Id of the Vehicle Charging Station vehicle (the raw game object) is docked at ("" while moving or away)."""
    try:
        return vehicle.current_station() or ""
    except Exception as error:
        swallowed("charging_stations.current: vehicle.current_station", error)
        return ""


def station_load(component, own_name):
    """Vehicles other than own_name queued or charging at a station, per charging bay."""
    try:
        waiting = set(component.get_queue()) | set(component.get_active())
        bays = component.get_bay_count()
    except Exception as error:
        swallowed("charging_stations.station_load: station queue", error)
        return float("inf")
    waiting.discard(own_name)
    return len(waiting) / max(1, bays)
