# Mission pool: a read-only index of the fleet's open work, one entry per
# demand (docs/cheatsheet/fleet_lifecycle.md §2f-1, docs/plans/dynamic_roles/mission_pool.md).
#
# role_demand.publish() calls publish() on the same cadence with the
# intermediates role_demand.compute() already built ("parts"), so nothing is
# read twice. An entry says what is open, where, how urgent, since when and
# who works it; it never decides who goes. There is no take: holders are
# derived from the reservations the jobs already make (logistics.pickups,
# survey.claims, mining.reserved_yield), so nothing is accounted twice. The
# FLEET card, the role tie-break and autoplay's text are to read it; no job does
# (the index is up to ROLE_DEMAND_TICK_INTERVAL stale by design).
#
# Archive (CODE_GUIDES.md#archive, archive_ipc.md):
#   fleet.missions = {"tick": t, "entries": [entry, ...], "dropped": {kind: n}}
#     entry = {"id", "kind", "prio", "outpost", "coords", "by", "item", "units", "since", "holders"}
#     a list, sorted band, oldest since, id; capped per kind first (cap())
#     id      = stable per demand: haul:<outpost>:<band>, build:<job id>,
#               mine:<outpost>:<ore>, scan:<request id>, scan:pois
#     prio    = the priority band (lib/priority.py)
#     since   = the tick the id first appeared, carried over by id (the only
#               state the index keeps; an entry the cap dropped starts over)
#     holders = vehicle names working it, derived each publish

import construction_plan
import fleet_claims_common as common
import mining_reservations
from archive import archive
from game_clock import is_fresh
from logistics_requests import PICKUP_STALE_TICKS
from priority import NEED, NONE, STOCK, band

MISSIONS_KEY = "fleet.missions"

# Entries kept per publish: KIND_SHARE per kind first, then band, oldest; the rest only counts in "dropped".
MAX_ENTRIES = 48
KIND_SHARE = 12
# A fleet.missions older than this is ignored (read()). = role_demand.ROLE_DEMAND_STALE_TICKS
MISSIONS_STALE_TICKS = 3000

# Entry kind per Pioneer role, for the FLEET card counts and the tie-break.
ROLE_KINDS = {"hauler": "haul", "builder": "build", "miner": "mine", "scout": "scan"}


def _entry(eid, kind, prio, outpost=None, coords=None, by=None, item=None, units=None, holders=()):
    return {
        "id": eid,
        "kind": kind,
        "prio": band(int(prio)),
        "outpost": outpost,
        "coords": [float(coords[0]), float(coords[1])] if coords else None,
        "by": by,
        "item": item,
        "units": units,
        "since": None,
        "holders": sorted(holders),
    }


def _request_by(requests, oid, item):
    entry = (requests.get(oid) or {}).get(item)
    return entry.get("by") if isinstance(entry, dict) else None


def haul_holders(pickups, curr_tick):
    """{dest outpost id: {vehicle}} of the fresh logistics.pickups entries."""
    out = {}
    for entry in (pickups or {}).values():
        if is_fresh(entry, curr_tick, PICKUP_STALE_TICKS) and entry.get("vehicle"):
            out.setdefault(entry.get("dest"), set()).add(entry["vehicle"])
    return out


def build_holders(claims, curr_tick):
    """{survey.claims key: vehicle} of the fresh claims."""
    out = {}
    for key, claim in (claims or {}).items():
        if is_fresh(claim, curr_tick, common.CLAIM_STALE_TICKS):
            name = claim.get("vehicle") or claim.get("rover")
            if name:
                out[key] = name
    return out


def haul_entries(deficits, requests, holders):
    """haul:<outpost>:<band> per band with units left; item = the largest, by = its requester."""
    out = []
    for oid in sorted(deficits, key=str):
        for tier, items in (deficits[oid] or {}).items():
            items = {i: u for i, u in (items or {}).items() if u > 0}
            if not items or tier <= NONE:
                continue
            item = max(sorted(items), key=lambda i: items[i])
            out.append(
                _entry(
                    f"haul:{oid}:{tier}",
                    "haul",
                    tier,
                    outpost=oid,
                    by=_request_by(requests, oid, item),
                    item=item,
                    units=sum(items.values()),
                    holders=holders.get(oid, ()),
                )
            )
    return out


def build_entries(jobs, holders):
    """build:<job id> per open job row (id, kind, outpost, coords, prio); a repeated id counts once."""
    out, seen = [], set()
    for job_id, kind, oid, coords, prio in jobs:
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        name = holders.get(construction_plan.claim_key(job_id))
        out.append(_entry(f"build:{job_id}", "build", prio, outpost=oid, coords=coords, by=kind, holders=(name,) if name else ()))
    return out


def mine_entries(miner_bands, requests, holders):
    """mine:<outpost>:<ore> per raw ore in reach: prio = its top band, units summed over bands."""
    out = []
    for oid in sorted(miner_bands, key=str):
        ores = {}
        for tier, items in (miner_bands[oid] or {}).items():
            for ore, units in items.items():
                top, total = ores.get(ore, (NONE, 0))
                ores[ore] = (max(top, tier), total + units)
        for ore in sorted(ores):
            tier, units = ores[ore]
            out.append(
                _entry(
                    f"mine:{oid}:{ore}",
                    "mine",
                    tier,
                    outpost=oid,
                    by=_request_by(requests, oid, ore),
                    item=ore,
                    units=units,
                    holders=holders.get((oid, ore), ()),
                )
            )
    return out


def _outpost_in(request, founded):
    """Id of the first founded outpost (sorted ids) inside the request's area, else None."""
    for oid in sorted(founded or {}, key=str):
        x, y = founded[oid]
        if (x - request["x"]) ** 2 + (y - request["y"]) ** 2 <= request["radius"] ** 2:
            return oid
    return None


def scan_entries(survey, scout, founded):
    """scan:<request id> per survey request (NEED), scan:pois for the other known scout work (STOCK)."""
    out = [_entry(f"scan:{rid}", "scan", NEED, outpost=_outpost_in(req, founded), coords=(req["x"], req["y"]), by=req.get("why")) for rid, req in sorted((survey or {}).items())]
    pois, sites = scout or (0, 0)
    if pois or sites:
        out.append(_entry("scan:pois", "scan", STOCK, units=int(pois) + int(sites)))
    return out


def build(curr_tick, parts, previous=None):
    """
    The fleet.missions value from role_demand.compute()'s "parts" plus the
    holder reads ("claims" = survey.claims, "reserved" = mining.reserved_yield).
    `previous` (read()) carries each id's "since".
    """
    parts = parts or {}
    since = {e["id"]: e.get("since") for e in (previous or {}).get("entries", []) if isinstance(e, dict) and "id" in e}
    requests = parts.get("requests") or {}
    entries = (
        haul_entries(parts.get("deficits") or {}, requests, haul_holders(parts.get("pickups"), curr_tick))
        + build_entries(parts.get("jobs") or [], build_holders(parts.get("claims"), curr_tick))
        + mine_entries(parts.get("miner_bands") or {}, requests, mining_reservations.holders_by_target(parts.get("reserved"), curr_tick))
        + scan_entries(parts.get("survey"), parts.get("scout"), parts.get("founded"))
    )
    for entry in entries:
        carried = since.get(entry["id"])
        entry["since"] = int(carried) if isinstance(carried, (int, float)) else curr_tick
    entries = sorted(entries, key=lambda e: (-e["prio"], e["since"], e["id"]))
    kept, dropped = cap(entries), {}
    for entry in entries:
        if entry["id"] not in kept:
            dropped[entry["kind"]] = dropped.get(entry["kind"], 0) + 1
    return {"tick": curr_tick, "entries": [e for e in entries if e["id"] in kept], "dropped": dropped}


def cap(entries):
    """
    Ids of the sorted `entries` the index keeps: each kind its first
    KIND_SHARE, then the rest in order up to MAX_ENTRIES. One kind's flood
    (a pipe run of blueprints at BUILD) never hides the other kinds.
    """
    kept, per_kind = set(), {}
    for entry in entries:
        if per_kind.get(entry["kind"], 0) < KIND_SHARE:
            per_kind[entry["kind"]] = per_kind.get(entry["kind"], 0) + 1
            kept.add(entry["id"])
    for entry in entries:
        if len(kept) >= MAX_ENTRIES:
            break
        kept.add(entry["id"])
    return kept


def publish(curr_tick, parts):
    """Writes build() to fleet.missions, reading the holder sources and the previous value. Returns the value written."""
    parts = dict(parts or {})
    parts["claims"] = archive.get(common.SURVEY_CLAIMS_KEY, {})
    parts["reserved"] = archive.get(mining_reservations.RESERVED_YIELD_KEY, {})
    value = build(curr_tick, parts, read())
    if not archive.set(MISSIONS_KEY, value):
        raise RuntimeError(f"{MISSIONS_KEY} write refused")  # after fleet.role_demand is stored; the AUTOMATION card shows it as "Role demand error"
    return value


def read(tick=None):
    """fleet.missions ({"entries": [], "dropped": {}} when missing, malformed or, given tick, older than MISSIONS_STALE_TICKS)."""
    value = archive.get(MISSIONS_KEY, {})
    if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
        return {"entries": [], "dropped": {}}
    if tick is not None and not is_fresh(value, tick, MISSIONS_STALE_TICKS):
        return {"entries": [], "dropped": {}}
    dropped = value.get("dropped")
    return {
        "tick": value.get("tick"),
        "entries": [e for e in value["entries"] if isinstance(e, dict) and isinstance(e.get("id"), str)],
        "dropped": dropped if isinstance(dropped, dict) else {},
    }


def oldest_open(entries, kind):
    """The entry of `kind` without holders that is open longest (lowest since, then id), None without one."""
    best = None
    for entry in entries or []:
        if entry.get("kind") != kind or entry.get("holders"):
            continue
        rank = (int(entry.get("since") or 0), str(entry.get("id")))
        if best is None or rank < best[0]:
            best = (rank, entry)
    return best[1] if best else None
