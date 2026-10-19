# Outpost flow statistic and floating-hauler dispersal
# (docs/plans/dynamic_roles Stage 1b). logistics.outpost_flow =
# {outpost_id: {"sent": units, "received": units, "tick": tick}}: units
# haulers picked up at (sent) and delivered to (received) each outpost,
# decayed with a half-life of FLOW_HALF_LIFE_TICKS so old traffic fades.
# Pioneer pull haulers (lib/job_pull.py) and hauler drones (lib/job_haul.py,
# lib/drone_hauler.py) record through record(). A pickup at a drill or a
# pump counts for the nearest outpost.
#
# An idle Pioneer hauler (PullJob.idle(), no demand) moves its base to the
# outpost most goods leave from per idle hauler already there
# (dispersal_target()), so the next request finds a hauler near its source.

import fleet_status
from archive import archive
from game_clock import is_fresh
from geometry import distance
from swallow import swallowed

OUTPOST_FLOW_KEY = "logistics.outpost_flow"
# Units recorded this long ago count half.
FLOW_HALF_LIFE_TICKS = 36000
# A move must raise the hauler's dispersal weight by this factor (hysteresis).
DISPERSE_GAIN = 1.25
# An idle hauler's fleet.status entry older than this does not count.
IDLE_STALE_TICKS = 3000
# A hauler that dispersed waits this long before it may move again.
DISPERSE_COOLDOWN_TICKS = 3000


def decayed(entry, curr_tick):
    """(sent, received) of one flow entry, decayed to curr_tick; (0.0, 0.0) for a malformed one."""
    if not isinstance(entry, dict):
        return 0.0, 0.0
    age = max(0, curr_tick - (entry.get("tick") or 0))
    factor = 0.5 ** (age / FLOW_HALF_LIFE_TICKS)
    return float(entry.get("sent") or 0) * factor, float(entry.get("received") or 0) * factor


def read(curr_tick):
    """{outpost_id: (sent, received)} decayed to curr_tick."""
    flow = archive.get(OUTPOST_FLOW_KEY, {})
    if not isinstance(flow, dict):
        return {}
    return {oid: decayed(entry, curr_tick) for oid, entry in flow.items()}


def record(curr_tick, sent=None, received=None):
    """Adds {outpost_id: units} to the outposts' sent/received counters (decaying the old values to curr_tick) in one transaction."""
    sent = {o: u for o, u in (sent or {}).items() if o and u > 0}
    received = {o: u for o, u in (received or {}).items() if o and u > 0}
    if not sent and not received:
        return

    def updater(flow):
        if not isinstance(flow, dict):
            flow = {}
        for oid in set(sent) | set(received):
            old_sent, old_received = decayed(flow.get(oid), curr_tick)
            flow[oid] = {"sent": round(old_sent + sent.get(oid, 0), 1), "received": round(old_received + received.get(oid, 0), 1), "tick": curr_tick}
        return flow

    try:
        archive.transaction(OUTPOST_FLOW_KEY, {}, updater)
    except Exception as error:
        swallowed("outpost_flow.record", error)


def founded_outposts():
    """{outpost_id: (x, y)} of the network's outposts."""
    network = get_component("outpost_network")
    try:
        outposts = list(network.outposts()) if network else []
    except Exception as error:
        swallowed("outpost_flow.founded_outposts: network.outposts", error)
        return {}
    found = {}
    for outpost in outposts:
        oid = getattr(outpost, "id", None)
        if oid is None or not hasattr(outpost, "coords"):
            continue
        try:
            found[oid] = tuple(outpost.coords())[:2]
        except Exception as error:
            swallowed("outpost_flow.founded_outposts: coords", error)
    return found


def nearest_outpost(coords, outposts):
    """Id of the outpost in {id: coords} nearest to coords, None when there is none."""
    if coords is None or not outposts:
        return None
    return min(outposts, key=lambda oid: (distance(coords, outposts[oid]), oid))


def source_outpost(source, outposts):
    """Outpost a pickup at `source` (a pull_plan/drone_haul_plan source dict) counts for: its own outpost, else the nearest one."""
    outpost = source.get("outpost")
    oid = getattr(outpost, "id", None)
    if oid is not None:
        return oid
    return nearest_outpost(source.get("coords"), outposts)


def sent_by_outpost(moved_by_source, outposts):
    """{outpost_id: units} from [(source dict, units), ...]."""
    sent = {}
    for source, units in moved_by_source:
        oid = source_outpost(source, outposts)
        if oid is not None and units > 0:
            sent[oid] = sent.get(oid, 0) + units
    return sent


def idle_haulers_by_base(status, curr_tick, exclude=None):
    """{base_id: count} of on-duty idle Pioneer haulers in fleet.status (entries with a "base"), without `exclude`."""
    counts = {}
    for name, entry in status.items():
        if name == exclude or not isinstance(entry, dict) or entry.get("role") != "hauler" or not entry.get("base"):
            continue
        state = entry.get("state")
        if not fleet_status.is_idle(state) or fleet_status.is_off_duty(state) or not is_fresh(entry, curr_tick, IDLE_STALE_TICKS):
            continue
        counts[entry["base"]] = counts.get(entry["base"], 0) + 1
    return counts


def dispersal_target(current_id, outposts, flow, idle_by_base, pos, gain=DISPERSE_GAIN):
    """
    Outpost id an idle hauler based at current_id should move to, None to
    stay. Weight of an outpost = (1 + sent) / (1 + idle haulers there,
    counting this one as if it stood there); the highest weight wins, ties
    go to the nearest to pos. Moves only when the winner's weight exceeds
    the current base's by `gain`.
    """
    if not outposts:
        return None

    def weight(oid):
        return (1.0 + flow.get(oid, (0.0, 0.0))[0]) / (2.0 + idle_by_base.get(oid, 0))

    best = max(outposts, key=lambda oid: (weight(oid), -distance(pos, outposts[oid]) if pos else 0.0, oid == current_id))
    if best == current_id:
        return None
    current = weight(current_id) if current_id in outposts else 0.0
    return best if weight(best) > current * gain else None
