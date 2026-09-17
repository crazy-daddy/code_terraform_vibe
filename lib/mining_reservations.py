# Non-exclusive in-flight mining yield reservations. Several Pioneers can now
# mine the same POI (game update), so lib/vehicle_claims.py's exclusivity lock
# is no longer used to gate mineral sites (see lib/mining.py). Without some
# bookkeeping though, several vehicles dispatched in the same demand-driven
# cycle would each see the full home-base deficit and all launch, overshooting
# it -- this module lets a vehicle debit its own projected yield from that
# deficit the moment it commits to a trip, additive rather than a lock, so it
# never blocks a peer the way vehicle_claims.py's claims do.

from archive import archive

RESERVED_YIELD_KEY = "mining.reserved_yield"

# Same expiry window as VehicleClaimsMixin.CLAIM_STALE_TICKS, so an abandoned
# reservation (crash, recall mid-trip) ages out on the same schedule a claim
# would.
RESERVATION_STALE_TICKS = 36000


def reserve_yield(vehicle_name, reservation_key, item_id, units, curr_tick):
    """
    Atomically records vehicle_name's projected yield (units of item_id) for
    reservation_key. Always succeeds -- unlike claim_target(), there's no
    ownership conflict to lose, since this is additive bookkeeping, not a lock.
    """
    def updater(reservations):
        if not isinstance(reservations, dict):
            reservations = {}
        reservations[reservation_key] = {
            "vehicle": vehicle_name,
            "item_id": item_id,
            "units": units,
            "tick": curr_tick,
        }
        return reservations

    archive.transaction(RESERVED_YIELD_KEY, {}, updater)


def refresh_yield(vehicle_name, reservation_key, curr_tick):
    """Renews heartbeat timestamp on an active yield reservation."""
    def updater(reservations):
        if isinstance(reservations, dict) and reservation_key in reservations:
            if reservations[reservation_key].get("vehicle") == vehicle_name:
                reservations[reservation_key]["tick"] = curr_tick
        return reservations

    archive.transaction(RESERVED_YIELD_KEY, {}, updater)


def release_yield(vehicle_name, reservation_key=None):
    """Releases reservation_key or every reservation owned by vehicle_name."""
    def updater(reservations):
        if not isinstance(reservations, dict):
            return {}
        if reservation_key:
            if reservation_key in reservations and reservations[reservation_key].get("vehicle") == vehicle_name:
                del reservations[reservation_key]
        else:
            keys_to_remove = [
                k for k, v in reservations.items()
                if isinstance(v, dict) and v.get("vehicle") == vehicle_name
            ]
            for k in keys_to_remove:
                del reservations[k]
        return reservations

    archive.transaction(RESERVED_YIELD_KEY, {}, updater)


def get_reserved_yield_totals(curr_tick):
    """
    Returns {item_id: total_reserved_units} summed across every non-stale
    reservation, module-level so callers without a VehicleController instance
    (e.g. lib/production.py) can read it directly.
    """
    reservations = archive.get(RESERVED_YIELD_KEY, {})
    totals = {}
    if not isinstance(reservations, dict):
        return totals
    for reservation in reservations.values():
        if not isinstance(reservation, dict):
            continue
        item_id = reservation.get("item_id")
        units = reservation.get("units", 0)
        tick = reservation.get("tick", 0)
        if not item_id or units <= 0:
            continue
        if curr_tick - tick >= RESERVATION_STALE_TICKS:
            continue
        totals[item_id] = totals.get(item_id, 0) + units
    return totals
