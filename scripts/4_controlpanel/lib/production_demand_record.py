# The demand record: the production demand picture (network Fabricator
# targets, per-site targets and ship plans, Smelter demands) computed once and
# shared through the archive, so machines read it instead of walking the
# cascade on every poll. Writers: orchestrator_automation.py's
# publish_demand_if_due() (the normal path, signature-gated and sliced) and
# site_supply.publish_site_requests() (free: it has the cache already). A
# machine never writes it: a machine that finds no usable record computes
# what it needs itself (measured: a machine publishing the whole record
# spent ~1,400 ticks on it and starved). Leaf module: only archive, clock and
# priority imports, so every production_* module can use it.
#
# Shape of DEMAND_KEY (one dict, JSON-safe; ladders per lib/priority.py):
#   {"v": DEMAND_VERSION, "tick": publish tick, "plan": SITE_PLAN_KEY then,
#    "network": {item_id: ladder},                      fabricator_target_ladders()
#    "sites": {site_id: {"targets": {item_id: ladder},  get_site_fabricator_ladders()
#                        "ship": {item_id: [units, prio]},
#                        "have": {item_id: units}}},    fab_have() there at compute time
#    "smelter": {"network": {item_id: ladder},          get_smelter_demands()
#                "sites": {site_id: {"demands": {item_id: ladder},  site_smelter_demands()
#                                    "have": {item_id: units}}}},  held_stock() there at compute time
#    "depths": {item_id: depth},                        recipe_depths(): the same for every Fabricator
#    "blueprint": {item_id: gross units}}               blueprint_demand_items(): the construction cascade
# A reader nets a ladder against what changed locally since "have"
# (production_sites._net_consumed()); it never raises one.
from archive import archive
from components import component
from game_clock import now_tick
from priority import ladder
from swallow import swallowed

DEMAND_KEY = "production.demand"
# The record's publish tick alone (one int): what a machine reads every poll to see a new record.
DEMAND_TICK_KEY = "production.demand_tick"
# Records of another version are never read (recomputed instead).
DEMAND_VERSION = 1
# A record younger than this is FRESH; up to DEMAND_MAX_STALE_TICKS it is STALE and still
# used (readers net it by their own local changes); older, a reader computes locally.
DEMAND_FRESH_TICKS = 600
DEMAND_MAX_STALE_TICKS = 3000

FRESH = "fresh"
STALE = "stale"
MISSING = "missing"


def _stored():
    record = archive.get(DEMAND_KEY, {})
    return record if isinstance(record, dict) else {}


def record_tick(record=None):
    """Publish tick of the stored record (0 when none). Without `record`, the small
    DEMAND_TICK_KEY is read, not the record: a machine's "did it change" check per poll."""
    if record is None:
        tick = archive.get(DEMAND_TICK_KEY, 0)
        return int(tick) if isinstance(tick, (int, float)) else 0
    tick = record.get("tick") if isinstance(record, dict) else None
    return int(tick) if isinstance(tick, (int, float)) else 0


def usable(record, plan=None):
    """True when `record` is a published record of this version (and of `plan`, when given)."""
    if not isinstance(record, dict) or record.get("v") != DEMAND_VERSION or "network" not in record:
        return False
    return plan is None or record.get("plan", {}) == plan


def read_record(now=None, plan=None):
    """(record, state): the stored record and FRESH (age <= DEMAND_FRESH_TICKS),
    STALE (older, up to DEMAND_MAX_STALE_TICKS) or MISSING (none, another
    version, another site plan, or too old; record is then None)."""
    now = now_tick("production_demand_record.read_record") if now is None else now
    record = _stored()
    if not usable(record, plan):
        return None, MISSING
    age = now - record_tick(record)
    if age <= DEMAND_FRESH_TICKS:
        return record, FRESH
    if age <= DEMAND_MAX_STALE_TICKS:
        return record, STALE
    return None, MISSING


def new_record(plan, network, sites=None, smelter_network=None, smelter_sites=None, depths=None, blueprint=None):
    """A record body to publish: every ladder copied, `sites` = {site_id: (targets, ship, have)},
    `smelter_sites` = {site_id: (demands, have)}, `depths` = recipe_depths(), `blueprint` =
    blueprint_demand_items()."""
    return {
        "v": DEMAND_VERSION,
        "plan": plan if isinstance(plan, dict) else {},
        "network": _copy_ladders(network),
        "depths": _parse_units(depths),
        "blueprint": _parse_units(blueprint),
        "sites": {site_id: {"targets": _copy_ladders(targets), "ship": {i: list(v) for i, v in (ship or {}).items()}, "have": dict(have or {})} for site_id, (targets, ship, have) in (sites or {}).items()},
        "smelter": {"network": _copy_ladders(smelter_network or {}), "sites": {site_id: {"demands": _copy_ladders(demands), "have": dict(have or {})} for site_id, (demands, have) in (smelter_sites or {}).items()}},
    }


def publish_record(record, now=None):
    """Stores `record` (new_record()) stamped `now`. Returns True when stored; False when a
    record stamped later than `now` already exists (kept) or without a clock."""
    now = now_tick("production_demand_record.publish_record") if now is None else now
    if not now:
        return False  # no clock: nothing can judge its age
    entry = dict(record)
    entry["tick"] = now
    kept = []

    def updater(stored):
        if isinstance(stored, dict) and usable(stored) and record_tick(stored) > now:
            kept.append(True)
            return stored
        return entry

    try:
        written = bool(archive.transaction(DEMAND_KEY, {}, updater))
    except Exception as error:
        swallowed("production_demand_record.publish_record: archive.transaction", error)
        return False
    if written and not kept:
        archive.set(DEMAND_TICK_KEY, now)
    return written and not kept


def site_entry(record, site_id):
    """(targets, ship, have) of one site from a record: {item: ladder}, {item: [units, prio]},
    {item: units}; empty when the site has no entry."""
    sites = record.get("sites") if isinstance(record, dict) else None
    entry = sites.get(site_id) if isinstance(sites, dict) else None
    if not isinstance(entry, dict):
        return {}, {}, {}
    return _parse_ladders(entry.get("targets")), _parse_ship(entry.get("ship")), _parse_units(entry.get("have"))


def depths_entry(record):
    """{item_id: depth} of a record, None when the record has no depth map (an older writer)."""
    stored = record.get("depths") if isinstance(record, dict) else None
    return _parse_units(stored) if isinstance(stored, dict) else None


def blueprint_entry(record):
    """{item_id: gross units} of the construction cascade in a record, None when absent."""
    stored = record.get("blueprint") if isinstance(record, dict) else None
    return _parse_units(stored) if isinstance(stored, dict) else None


def network_entry(record):
    """{item: ladder} of the network Fabricator targets in a record."""
    return _parse_ladders(record.get("network") if isinstance(record, dict) else None)


def smelter_entry(record, site_id=None):
    """(demands, have) of the Smelter part: the network ladders (site_id None, have {}) or one site's."""
    part = record.get("smelter") if isinstance(record, dict) else None
    part = part if isinstance(part, dict) else {}
    if site_id is None:
        return _parse_ladders(part.get("network")), {}
    sites = part.get("sites")
    entry = sites.get(site_id) if isinstance(sites, dict) else None
    if not isinstance(entry, dict):
        return {}, {}
    return _parse_ladders(entry.get("demands")), _parse_units(entry.get("have"))


def _copy_ladders(ladders):
    return {item_id: [list(level) for level in levels] for item_id, levels in (ladders or {}).items()}


def _parse_ladders(stored):
    ladders = {}
    for item_id, levels in (stored if isinstance(stored, dict) else {}).items():
        parsed = ladder(levels)
        if parsed:
            ladders[item_id] = parsed
    return ladders


def _parse_ship(stored):
    plan = {}
    for item_id, value in (stored if isinstance(stored, dict) else {}).items():
        if isinstance(value, (list, tuple)) and len(value) == 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)) and value[0] > 0:
            plan[item_id] = [int(value[0]), int(value[1])]
    return plan


def _parse_units(stored):
    return {item_id: int(units) for item_id, units in (stored if isinstance(stored, dict) else {}).items() if isinstance(units, (int, float))}


def demand_signature(dock_plan, kinds=("fabricator", "smelter")):
    """
    {(kind, source key, item): amount} of the archive demand Fabricators and Smelters work from
    (archive reads only): manual orders, the order book and the site plan (kind "fabricator"),
    ingot stock targets ("smelter"), the order ids in the dock plan and the pending construction
    job ids (both kinds: their items are not read here, so either may be needed). The computed
    targets are left out on purpose: they shrink as stock arrives. A change in this signature is
    what makes the publisher recompute and the parking pass wake machines.
    """
    from production_demand import INGOT_STOCK_TARGETS_KEY
    from production_orders import MANUAL_ORDERS_KEY, ORDERS_KEY
    from production_sites import SITE_PLAN_KEY

    def stored(key):
        value = archive.get(key, {})
        return value if isinstance(value, dict) else {}

    def positive(amount):
        return isinstance(amount, (int, float)) and amount > 0

    signature = {}
    signature.update({("fabricator", MANUAL_ORDERS_KEY, item): amount for item, amount in stored(MANUAL_ORDERS_KEY).items() if positive(amount)})
    for requester, items in stored(ORDERS_KEY).items():
        for item, levels in items.items() if isinstance(items, dict) else ():
            for pair in levels if isinstance(levels, (list, tuple)) else ():
                if isinstance(pair, (list, tuple)) and len(pair) == 2 and positive(pair[0]):
                    name = f"{requester}/{item}@{pair[1]}"
                    signature[("fabricator", ORDERS_KEY, name)] = signature.get(("fabricator", ORDERS_KEY, name), 0) + pair[0]
    for root, sites in stored(SITE_PLAN_KEY).items():
        signature.update({("fabricator", SITE_PLAN_KEY, f"{root} at {site}"): 1 for site in (sites if isinstance(sites, list) else ())})
    ingots = stored(INGOT_STOCK_TARGETS_KEY)
    signature.update({("smelter", INGOT_STOCK_TARGETS_KEY, item): entry["target"] for item, entry in ingots.items() if isinstance(entry, dict) and positive(entry.get("target"))})
    for order_id in set((dock_plan or {}).values()) - {None}:
        for kind in kinds:
            signature[(kind, "dock_plan", f"dock order {order_id}")] = 1
    for job_id in _blueprint_job_ids():
        for kind in kinds:
            signature[(kind, "blueprint", job_id)] = 1
    return signature


def _blueprint_job_ids():
    """Ids of every pending/paused Construction Blueprint job (an empty list without the component)."""
    blueprint = component("construction_blueprint")
    if not blueprint:
        return []
    ids = []
    for getter_name in ("pending_constructions", "paused_constructions"):
        getter = getattr(blueprint, getter_name, None)
        if not getter:
            continue
        try:
            ids.extend([str(getattr(job, "id", "")) for job in getter() if getattr(job, "id", None)])
        except Exception as error:
            swallowed("production_demand_record._blueprint_job_ids: getter", error)
    return ids
