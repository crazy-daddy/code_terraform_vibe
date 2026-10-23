# Drone Depot / Drone Service Station discovery and home resolution as module
# functions (layer 0 of the drone mixins, see docs/plans/mixin_refactor/
# followups.md): every deployed building of those types across the outpost
# network, heli-capable service filtering, the pinned drone homes
# (HOME_DEPOTS_KEY) and the free-depot choice. No flying and no drone mixin
# imports; the DroneEnergyMixin wrappers (lib/drone_energy.py) pass in what
# they used to read from self. lib/drone_depot.py is the Depot's own
# controller, a different thing.

import geometry
from archive import archive
from components import drone_service_station, research_unlocked
from game_clock import TickCache
from item_tiers import DEPOT_TYPE_TIERS
from swallow import swallowed

DRONE_SERVICE_TYPE_ID = "drone_service_station"

# A drone_service_station counts as able to refuel a heli when its oil_in
# buffer (100 t max) holds at least this much, or oil is flowing in right
# now. Dry stations are skipped as refuel/return targets (still used as a
# last resort when no station has oil, see services_for()).
SERVICE_MIN_OIL_T = 10.0

# Pinned drone homes (see resolve_home()): ONE shared dict
# {drone_name: outpost_id (pool) or depot_id (hardwired)}, like
# drone_claims.py's drone.recall, not a key per
# drone. Bounded by fleet size; entries of drones that no longer exist are
# pruned on every write.
HOME_DEPOTS_KEY = "drone.home_depots"

# discover_drone_buildings() runs per drone on every flight poll and per field drone in each Drone Service
# pass; results are reused for this many ticks (~2 s), so a newly placed building is seen at most that late.
DISCOVERY_TTL_TICKS = 20

# {type_ids tuple: [building dicts]}
_DISCOVERY = TickCache(DISCOVERY_TTL_TICKS)


def pin_home_depot(drone_name, depot_id):
    def updater(pins):
        if not isinstance(pins, dict):
            pins = {}
        pins[drone_name] = depot_id
        fleet = get_component("fleet")
        if fleet and hasattr(fleet, "drones"):
            try:
                live = {getattr(d, "id", "") for d in fleet.drones()}
            except Exception:
                # Silent on purpose: this runs inside an archive.transaction()
                # updater, where any log call rejects the transaction. Keeping
                # every pin (no pruning) is the safe fallback.
                live = set()
            if live:
                pins = {name: pin for name, pin in pins.items() if name in live or name == drone_name}
        return pins

    archive.transaction(HOME_DEPOTS_KEY, {}, updater)


def service_oil_state(service_id):
    """
    (wired, buffer_t, flow_t_per_h) of a drone_service_station's oil_in.
    "wired" uses connections() (every effective peer, including a link the
    Oil Pump/tank declared from its side -- connected_to() only shows this
    port's own declaration). Unreadable reads as (False, 0.0, 0.0).
    """
    try:
        station = drone_service_station(service_id)
        port = getattr(station, "oil_in", None) if station else None
        if port is None:
            return (False, 0.0, 0.0)
        wired = bool(port.connections()) or bool(port.connected_to())
        return (wired, float(port.level() or 0.0), float(port.flow_rate() or 0.0))
    except Exception as error:
        swallowed("drone_depots.service_oil_state: get_component", error)
        return (False, 0.0, 0.0)


HELI_RESEARCH_ID = "research_heli_drones"


def heli_unlocked():
    """True once Heli-Drones is researched: heli modules can be coupled (False when unreadable)."""
    return research_unlocked(HELI_RESEARCH_ID, "drone_depots.heli_unlocked")


def heli_oil_ready():
    """True when some Drone Service Station can refuel a heli now (service_can_refuel())."""
    return any(service_can_refuel(s["id"]) for s in discover_drone_services())


def service_has_oil_feed(service_id):
    """True when a drone_service_station's oil_in has any oil source wired (docs/components/drone_service_station.md)."""
    return service_oil_state(service_id)[0]


def service_can_refuel(service_id):
    """True when the station holds >= SERVICE_MIN_OIL_T in its oil_in buffer or oil is flowing in now."""
    _wired, buffer_t, flow = service_oil_state(service_id)
    return buffer_t >= SERVICE_MIN_OIL_T or flow > 0.0


def heli_capable_services(services):
    """
    (subset, tier) of `services` (discover_drone_services() dicts) usable
    by a heli drone: tier "oil" = service_can_refuel() stations; else
    "wired" = wired but dry (may refill); else "all" (a rescue still works,
    and the station itself warns about the missing oil). Shared by
    services_for() (the drone's own choice) and lib/drone_service.py
    (rescue/nudge arbitration), so both skip dry stations the same way.
    """
    if not services:
        return services, "all"
    states = {s["id"]: service_oil_state(s["id"]) for s in services}
    usable = [s for s in services if states[s["id"]][1] >= SERVICE_MIN_OIL_T or states[s["id"]][2] > 0.0]
    if usable:
        return usable, "oil"
    wired = [s for s in services if states[s["id"]][0]]
    if wired:
        return wired, "wired"
    return services, "all"


def _extract_coords(pos):
    if pos is None:
        return None
    if isinstance(pos, (tuple, list)) and len(pos) >= 2:
        return (float(pos[0]), float(pos[1]))
    x = getattr(pos, "x", None)
    y = getattr(pos, "y", None)
    if x is not None and y is not None:
        return (float(x), float(y))
    return None


def discover_drone_buildings(type_id):
    """Memoized for DISCOVERY_TTL_TICKS; entries are shared, treat them as read-only. See _scan_drone_buildings()."""
    key = tuple(type_id) if isinstance(type_id, (tuple, list)) else (type_id,)
    return list(_DISCOVERY.get(lambda: _scan_drone_buildings(type_id), key))


def _scan_drone_buildings(type_id):
    """
    Standalone: every deployed building of type_id (drone_service_station or
    a Drone Depot typeId from DEPOT_TYPE_TIERS, "drone_station*"; a tuple of type ids matches any of them) across every owned outpost, as
    [{"id": str, "name": str, "coords": (x, y), "outpost": OutpostRef|None,
    "outpost_id": str}, ...]. Mirrors
    lib/charging_stations.py's discovery shape, shared by DroneEnergyMixin and
    lib/drone_service.py's own station-side nearest-station arbitration
    (lib/station_controller.py assess_stations()).
    """
    refs = []
    found_ids = set()
    type_ids = type_id if isinstance(type_id, (tuple, list)) else (type_id,)
    network = get_component("outpost_network")
    if network and hasattr(network, "outposts"):
        try:
            outposts = network.outposts()
        except Exception as error:
            swallowed("drone_depots.discover_drone_buildings: network.outposts", error)
            outposts = []
        for outpost in outposts:
            if not hasattr(outpost, "buildings"):
                continue
            buildings = []
            for t_id in type_ids:
                try:
                    buildings.extend(outpost.buildings(t_id))
                except Exception as error:
                    swallowed("drone_depots.discover_drone_buildings: buildings.extend", error)
                    continue
            for b in buildings:
                b_id = getattr(b, "id", "")
                if not b_id or b_id in found_ids:
                    continue
                pos = _extract_coords(getattr(b, "position", None))
                if not pos:
                    continue
                found_ids.add(b_id)
                refs.append(
                    {
                        "id": b_id,
                        "name": getattr(b, "name", "") or "",
                        "coords": pos,
                        "outpost": getattr(b, "outpost", None),
                        "outpost_id": getattr(b, "outpost_id", "") or "",
                    }
                )
    return refs


def discover_drone_services():
    return discover_drone_buildings(DRONE_SERVICE_TYPE_ID)


def discover_drone_depots():
    """Every Drone Depot drones may use: all sizes."""
    return discover_drone_buildings(DEPOT_TYPE_TIERS)


def services_for(engine, name, log):
    """
    Every drone_service_station -- for a heli drone only the ones that
    can refuel it right now (service_can_refuel(): oil in the buffer or
    flowing in), so dry stations are skipped for refuel, parking and
    return budgeting. Falls back to wired-but-dry stations (they may
    refill), then to all of them (a rescue still works, and the station
    itself warns about the missing oil).
    """
    services = discover_drone_services()
    if engine != "heli" or not services:
        return services
    chosen, tier = heli_capable_services(services)
    if tier == "oil":
        skipped = [s["id"] for s in services if s not in chosen]
        if skipped:
            log.trace(f"[{name}] Skipping dry drone_service_station(s) for heli: {skipped}.")
    else:
        log.debug(f"[{name}] No drone_service_station has oil (>= {SERVICE_MIN_OIL_T:.0f} t or inflow); " + (f"falling back to {len(chosen)} wired but dry." if tier == "wired" else f"none wired; considering all {len(chosen)}."))
    return chosen


def nearest(label, candidates, ref_coords, fallback_coords, name, log):
    """(coords, info) of the candidate nearest to ref_coords; fallback_coords with an empty id when there is none."""
    log.start(f"[{name}] nearest {label}", level="debug")
    if not candidates:
        log.trace(f"no {label} deployed yet; falling back to home_coords {fallback_coords}.")
        log.end()
        return fallback_coords, {"id": "", "coords": fallback_coords}
    best = min(candidates, key=lambda c: geometry.distance(ref_coords, c["coords"]))
    log.trace(f"{len(candidates)} candidate(s) from {ref_coords}, nearest '{best.get('id')}' at {best['coords']} ({geometry.distance(ref_coords, best['coords']):.1f}m).")
    log.end()
    return best["coords"], best


def resolve_home(name, depots, home_depot, nearest_depot_fn, log):
    """
    Picks and pins drone `name`'s home. The home is either one specific
    Drone Depot ("hardwired") or a whole outpost ("pool": any depot in
    that outpost; DroneEnergyMixin.get_home_depot() picks a free one per trip,
    since all depots of an outpost share its coords). Returns
    (representative depot info dict (coords/outpost for home_biome etc.),
    pool outpost id or None when hardwired); ({}, None) when no Depot is
    deployed. nearest_depot_fn() returns the (coords, info) of the depot
    nearest the drone. Priority:
      1. home_depot override (the HOME_DEPOT script variable): a depot
         id or display name (hardwired), or an outpost id (pool).
      2. The pin persisted in archive by a previous run (depot id or
         outpost id, same matching), so a script restart while the drone
         is out in the field does not re-home it to whichever depot
         happens to be nearest there.
      3. Nearest depot to the drone's current position (first run),
         pinned as a pool of that depot's outpost.
    The pin is written back to archive (HOME_DEPOTS_KEY dict).
    """
    log.start(f"[{name}] resolve_home_depot()", level="debug")
    if not depots:
        log.debug("no Drone Depot deployed; no home depot.")
        log.end()
        return {}, None

    def match(wanted):
        """(representative_depot, pool_outpost_id or None) for a depot id/name or outpost id."""
        depot = next((d for d in depots if wanted in (d["id"], d.get("name"))), None)
        if depot:
            return depot, None
        pool = [d for d in depots if d.get("outpost_id") == wanted]
        if pool:
            return pool[0], wanted
        return None, None

    chosen, pool_id, source = None, None, None
    if home_depot:
        wanted = str(home_depot)
        chosen, pool_id = match(wanted)
        if chosen:
            source = "HOME_DEPOT override"
        else:
            log.level("warn").print(f"[{name}] HOME_DEPOT '{wanted}' matches no Drone Depot id, name or outpost id; falling back to auto-detection.")
    if chosen is None:
        pinned = archive.get_dict(HOME_DEPOTS_KEY).get(name)
        if pinned:
            chosen, pool_id = match(str(pinned))
            if chosen:
                source = "archived pin"
            else:
                log.debug(f"archived pin '{pinned}' no longer exists; re-resolving.")
    if chosen is None:
        _, chosen = nearest_depot_fn()
        pool_id = chosen.get("outpost_id") or None
        source = "nearest to current position"

    pin_home_depot(name, pool_id or chosen["id"])
    home_desc = f"any Drone Depot in '{pool_id}'" if pool_id else f"Drone Depot '{chosen['id']}' (hardwired)"
    log.debug(f"Home pinned to {home_desc} via {source}.")
    log.end()
    return chosen, pool_id


def home_candidates(depots, pool_id, home_depot):
    """Live depot dicts making up a drone's home (the pool outpost's depots, or the one hardwired home_depot)."""
    if pool_id:
        return [d for d in depots if d.get("outpost_id") == pool_id]
    depot_id = (home_depot or {}).get("id")
    return [d for d in depots if d["id"] == depot_id] if depot_id else []


def pick_free_depot(candidates, prefer_id, current_station, pos, name, log):
    """
    Best depot of candidates for this trip: the one the drone is
    already docked at (current_station), else free bay first, then prefer_id (the depot
    already queued for, so an all-full pool doesn't churn between
    queues), then free cargo slots, then nearest to pos. Bay/slot counts are read live via get_component(depot_id);
    an unreadable depot sorts as full but stays eligible.
    """
    log.start(f"[{name}] _pick_free_depot()", level="debug")
    for d in candidates:
        if d["id"] == current_station:
            log.end()
            return d
    if len(candidates) == 1:
        log.end()
        return candidates[0]

    scored = []
    for d in candidates:
        free_bays, free_slots = 0, 0
        try:
            depot = get_component(d["id"])
            if depot is not None:
                free_bays = depot.bay_count() - depot.bays_occupied()
                free_slots = depot.slot_capacity() - depot.slots_used()
        except Exception as e:
            log.debug(f"could not read '{d['id']}': {e}")
        scored.append(((free_bays <= 0, d["id"] != prefer_id, free_slots <= 0, geometry.distance(pos, d["coords"]), d["id"]), d, free_bays, free_slots))
    scored.sort(key=lambda s: s[0])
    log.debug(f"[{name}] _pick_free_depot(): " + ", ".join(f"{d['id']}(bays free={fb}, slots free={fs})" for _, d, fb, fs in scored) + f" -> '{scored[0][1]['id']}'.")
    log.end()
    return scored[0][1]


def home_service(depot, services):
    """The service in the home depot's outpost (nearest to the depot if several), else the one nearest the depot; None when `depot` or `services` is empty."""
    if not depot or not services:
        return None
    depot_coords = depot["coords"]
    same_outpost = [s for s in services if depot.get("outpost_id") and s.get("outpost_id") == depot.get("outpost_id")]
    return min(same_outpost or services, key=lambda s: geometry.distance(depot_coords, s["coords"]))
