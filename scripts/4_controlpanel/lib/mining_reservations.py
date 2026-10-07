# Non-exclusive in-flight mining yield reservations. Several vehicles can
# mine the same site, so lib/vehicle_claims.py keys a mine claim per vehicle
# and never locks a site (see VehicleClaimsMixin.claim_key()). Without some
# bookkeeping though, several vehicles dispatched in the same cycle would
# each see the full deficit and all launch, overshooting it -- this module
# lets a vehicle debit its planned trip yield from that deficit the moment
# it commits to a trip. A peer still launches at the same site while the
# deficit left after every reservation is positive.
#
# One entry per vehicle (a vehicle runs one trip at a time):
#   {vehicle_name: {vehicle, target_key, item_id, units, outpost_id, tick}}
# Entries written before this shape are keyed by target_key; they carry the
# same "vehicle" field, so release_yield() and the totals still read them
# until they age out.

from archive import archive
from tree_console import TreeConsole

log = TreeConsole(module="mining_reservations")

RESERVED_YIELD_KEY = "mining.reserved_yield"

# Same expiry window as VehicleClaimsMixin.CLAIM_STALE_TICKS, so an abandoned
# reservation (crash, recall mid-trip) ages out on the same schedule a claim
# would.
RESERVATION_STALE_TICKS = 36000


def reserve_yield(vehicle_name, target_key, item_id, units, curr_tick, outpost_id=None):
    """
    Atomically records vehicle_name's planned trip yield (units of item_id
    from target_key, delivered to outpost_id), replacing any earlier entry of
    that vehicle. Always succeeds -- unlike claim_target(), there's no
    ownership conflict to lose, since this is additive bookkeeping, not a lock.
    """
    def updater(reservations):
        if not isinstance(reservations, dict):
            reservations = {}
        for k in [k for k, v in reservations.items() if isinstance(v, dict) and v.get("vehicle") == vehicle_name]:
            del reservations[k]
        reservations[vehicle_name] = {
            "vehicle": vehicle_name,
            "target_key": target_key,
            "item_id": item_id,
            "units": units,
            "outpost_id": outpost_id,
            "tick": curr_tick,
        }
        return reservations

    archive.transaction(RESERVED_YIELD_KEY, {}, updater)
    log.debug(f"reserve_yield({target_key!r}): {vehicle_name} reserved {units}x {item_id} for outpost {outpost_id!r} at tick {curr_tick}.")


def reservation_of(vehicle_name):
    """vehicle_name's reservation entry, or None."""
    reservations = archive.get(RESERVED_YIELD_KEY, {})
    if not isinstance(reservations, dict):
        return None
    for key, entry in reservations.items():
        if isinstance(entry, dict) and entry.get("vehicle") == vehicle_name:
            return {"target_key": key, **entry}
    return None


def refresh_yield(vehicle_name, curr_tick):
    """Renews the heartbeat tick on vehicle_name's reservation."""
    def updater(reservations):
        if isinstance(reservations, dict):
            for entry in reservations.values():
                if isinstance(entry, dict) and entry.get("vehicle") == vehicle_name:
                    entry["tick"] = curr_tick
        return reservations

    archive.transaction(RESERVED_YIELD_KEY, {}, updater)


def release_yield(vehicle_name):
    """Releases every reservation owned by vehicle_name."""
    released = []

    def updater(reservations):
        del released[:]
        if not isinstance(reservations, dict):
            return {}
        for k in [k for k, v in reservations.items() if isinstance(v, dict) and v.get("vehicle") == vehicle_name]:
            released.append(k)
            del reservations[k]
        return reservations

    archive.transaction(RESERVED_YIELD_KEY, {}, updater)
    if released:
        log.debug(f"release_yield({vehicle_name!r}): released {released}.")
    else:
        log.debug(f"release_yield({vehicle_name!r}): nothing owned by {vehicle_name} to release.")


def get_reserved_yield_totals(curr_tick, outpost_id=None, exclude_vehicle=None):
    """
    Returns {item_id: total_reserved_units} summed across every non-stale
    reservation, module-level so callers without a VehicleController instance
    (e.g. lib/production.py) can read it directly. With outpost_id, only
    reservations delivering there count (an entry without outpost_id, written
    before that field existed, counts everywhere). exclude_vehicle leaves out
    that vehicle's own reservation.
    """
    log.start("get_reserved_yield_totals()", level="debug")
    reservations = archive.get(RESERVED_YIELD_KEY, {})
    totals = {}
    if not isinstance(reservations, dict):
        log.end()
        return totals
    stale_count = 0
    for key, reservation in reservations.items():
        if not isinstance(reservation, dict):
            continue
        item_id = reservation.get("item_id")
        units = reservation.get("units", 0)
        tick = reservation.get("tick", 0)
        if not item_id or units <= 0:
            continue
        if exclude_vehicle is not None and reservation.get("vehicle") == exclude_vehicle:
            continue
        entry_outpost = reservation.get("outpost_id")
        if outpost_id is not None and entry_outpost is not None and entry_outpost != outpost_id:
            continue
        if curr_tick - tick >= RESERVATION_STALE_TICKS:
            stale_count += 1
            log.debug(f"{key!r} ({reservation.get('vehicle')}, {units}x {item_id}) is stale ({curr_tick - tick} ticks old); excluded from totals.")
            continue
        totals[item_id] = totals.get(item_id, 0) + units
    if stale_count:
        log.debug(f"totals={totals} ({stale_count} stale reservation(s) excluded, tick={curr_tick}).")
    log.end()
    return totals
