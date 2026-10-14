# Shared Mk III feed keeper for the headless stand-ins (docs/headless/standins.md).
# standins.mjs standinSource() prepends this file to every stand-in script, so
# the functions below are module globals there; a stand-in file imports them
# only under TYPE_CHECKING (`from _feed import ensure_feed`) for Pyright.
# Stands in for lib/fluid_routing.py FluidInputRouter: a port under
# FEED_STARVED_FRACTION of its capacity on FEED_STARVED_CHECKS checks in a row
# moves to the next candidate (tanks latched to the fluid first, then
# producers, own outpost first). No reachability check, no blacklist, no pipe
# conflicts, no POI pumps.

FEED_CHECK_TICKS = 50  # 5 s between two checks of one port
FEED_STARVED_FRACTION = 0.2
FEED_STARVED_CHECKS = 2

# Candidate buildings per fluid: (tank types, producer types).
FEED_SOURCES = {
    "steam": (("gas_tank",), ("thermal_cap",)),
    "water": (("liquid_tank", "bulk_liquid_reservoir"), ("steam_condenser",)),
}

_feed_memo = {}  # port name -> {"tick": last check, "starved": n, "tried": [ids]}


def _feed_candidates(fluid, own_outpost_id):
    tanks, producers = FEED_SOURCES.get(fluid, ((), ()))
    net = get_component("outpost_network")
    outposts = list(net.outposts()) if net else []
    outposts.sort(key=lambda op: 0 if op.id == own_outpost_id else 1)
    ids = []
    for type_ids, latched in ((tanks, True), (producers, False)):
        for op in outposts:
            for type_id in type_ids:
                for ref in op.buildings(type_id):
                    if latched:
                        fluid_of = getattr(get_component(ref.id), "fluid", None)
                        if not fluid_of or fluid_of() != fluid:
                            continue
                    ids.append(ref.id)
    return ids


def ensure_feed(port, fluid, own_outpost_id, tick, name):
    """One check of `port` (a FluidPort of self) at most every FEED_CHECK_TICKS; reconnects
    a starved port to the next candidate. Every read is wrapped: a failure skips the check."""
    memo = _feed_memo.get(fluid)
    if memo is None:
        memo = {"tick": -1, "starved": 0, "tried": []}
        _feed_memo[fluid] = memo
    if memo["tick"] >= 0 and 0 <= tick - memo["tick"] < FEED_CHECK_TICKS:
        return
    memo["tick"] = tick
    try:
        level = port.level()
        capacity = port.capacity()
        current = port.connected_id()
    except Exception:
        return
    if capacity <= 0 or level >= capacity * FEED_STARVED_FRACTION:
        memo["starved"] = 0
        return
    memo["starved"] += 1
    if memo["starved"] < FEED_STARVED_CHECKS:
        return
    memo["starved"] = 0
    try:
        candidates = [c for c in _feed_candidates(fluid, own_outpost_id) if c != current and c not in memo["tried"]]
    except Exception:
        return
    if not candidates:
        memo["tried"] = []
        return
    target = candidates[0]
    memo["tried"].append(target)
    try:
        res = port.connect(target)
        print(
            f"[{name}] {fluid} feed starved ({level:.1f}/{capacity:.1f}); {current or '(none)'} -> {target}: {res.status}"
        )
    except Exception:
        return
