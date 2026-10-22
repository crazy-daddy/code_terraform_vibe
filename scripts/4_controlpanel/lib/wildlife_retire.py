# Wildlife retirement: once the sensor reads WILDLIFE_COMPLETE_POPULATION,
# wildlife_planner.plan_if_due() runs retire_pass() each pass instead of
# planning, until no Habitat, Feed Maker, Refiner, exotic tank or cap is
# left. Split from wildlife_planner.py; shares its module state and log.
import fluid_routing
import logistics_requests
import refiner
import wildlife_common as wc
from archive import STATUS_STALE_TICKS, archive
from construction_plan import EXTRACTOR_KITS
from game_clock import is_fresh
from script_parking import parked_ids, wake_for_visit, wake_kind
from storage import inventory_count
from swallow import swallowed
from wildlife_data import EXOTIC_FLUIDS, SPECIES
from wildlife_planner import COMPLETE_SUMMARY, REFINER_TYPE_ID, REQUESTER_ID, drop_feed, log, network_habitats, state, undeploy_machine, undeploy_ready

EXOTIC_EXTRACTOR_TYPE_IDS = ("exotic_gas_cap", "exotic_spring_tap")
# Kits sold from Inventory at Wildlife complete. Mk II packs are not sellable (only droppable) and
# stay; tank kits stay for other fluids. A Pioneer brings cap/tap kits home in its cargo.
RETIRE_SELL_ITEMS = (wc.HABITAT_KIT_ITEM_ID, wc.FEED_MAKER_TYPE_ID, REFINER_TYPE_ID) + tuple(EXTRACTOR_KITS[t] for t in EXOTIC_EXTRACTOR_TYPE_IDS)


def _own_requests_left():
    """True while a life-form request by REQUESTER_ID is still published anywhere."""
    requests = archive.get(logistics_requests.REQUESTS_KEY, {}) or {}
    if not isinstance(requests, dict):
        return False
    for items in requests.values():
        if isinstance(items, dict) and any(isinstance(e, dict) and e.get("by") == REQUESTER_ID for e in items.values()):
            return True
    return False


def _retire_label(entry):
    """`plan.release` value for a Habitat at completion: its established species, else wc.RELEASE_NO_COLONY."""
    entry = entry or {}
    if entry.get("established") and entry.get("species"):
        return entry["species"]
    return wc.RELEASE_NO_COLONY


def _sell_kits():
    """Sells every RETIRE_SELL_ITEMS unit in Inventory; a refused sale leaves it there and warns."""
    shop = get_component("shop")
    if shop is None:
        return
    for item in RETIRE_SELL_ITEMS:
        units = inventory_count(item)
        if units <= 0:
            continue
        try:
            res = shop.sell(item, units)
        except Exception as error:
            swallowed("wildlife_retire._sell_kits: shop.sell", error)
            continue
        if getattr(res, "status", "") == "ok":
            log.print(f"[WILDLIFE] Sold {units}x {item} for {getattr(res, 'credits', 0) or 0} cr (Wildlife complete).")
        else:
            log.level("warn").print(f"[WILDLIFE] sell {units}x {item} -> {getattr(res, 'status', '?')}: {getattr(res, 'message', '')}. Left in Inventory.")


def _exotic_tanks():
    """Ids of every network tank latched to an exotic fluid, or unlatched and assigned one. A
    tank mid-swap (fluid_routing.RETIRING_ASSIGNMENT, lib/tank_upgrade.py) is left to its swap."""
    assignments = fluid_routing.get_tank_assignments()
    out = []
    for tank, _outpost_id in fluid_routing.discover_network_buildings(fluid_routing.TANK_TYPE_IDS, resolve=True):
        tank_id = getattr(tank, "id", None)
        assigned = assignments.get(tank_id)
        if not tank_id or assigned == fluid_routing.RETIRING_ASSIGNMENT:
            continue
        try:
            fluid = tank.fluid() or assigned
        except Exception as error:
            swallowed("wildlife_retire._exotic_tanks: tank.fluid", error)
            continue
        if fluid in EXOTIC_FLUIDS:
            out.append(tank_id)
    return sorted(out)


def _undeploy_tanks(tank_ids):
    """Undeploys each exotic tank with its fluid (fluid never blocks undeploy) and drops its
    tank_assignments entry. Returns the ids gone."""
    computer = get_component("computer") if tank_ids else None
    if computer is None:
        return []
    gone = []
    for tank_id in tank_ids:
        status = undeploy_machine(computer, tank_id)
        if status not in ("ok", "not_found"):
            continue
        gone.append(tank_id)
        state["undeploy_warned"].pop(tank_id, None)
        if status == "ok":
            log.print(f"[WILDLIFE] {tank_id}: exotic tank undeployed with its fluid; kit back in Inventory.")
    if gone and not archive.transaction(fluid_routing.TANK_ASSIGNMENTS_KEY, {}, lambda stored: _without(stored, gone)):
        log.level("warn").print(f"{fluid_routing.TANK_ASSIGNMENTS_KEY} write rejected; entries of {gone} left.")
    return gone


def _without(stored, ids):
    """Copy of the `stored` dict without `ids` (a non-dict reads as empty)."""
    return {k: v for k, v in stored.items() if k not in ids} if isinstance(stored, dict) else {}


def _exotic_extractors():
    """[(cap id, x, y)] of every Exotic Gas Cap / Spring Tap on a surveyed exotic deposit."""
    journal = get_component("journal")
    out = []
    try:
        sites = list(journal.surveyed_sites(wc.PLANET_ID)) if journal else []
    except Exception as error:
        swallowed("wildlife_retire._exotic_extractors: journal.surveyed_sites", error)
        return out
    for site in sites:
        try:
            if site.kind() != "exotic":
                continue
            cap_id = getattr(site, "cap_id")()  # an ExoticDeposit; journal types the list as Site
        except Exception as error:
            swallowed("wildlife_retire._exotic_extractors: site read", error)
            continue
        if cap_id:
            out.append((cap_id, float(site.x), float(site.y)))
    return sorted(out)


def _deconstruct_extractors(extractors):
    """Marks each cap/tap for deconstruction at its site coordinates (a field structure: a
    Pioneer deconstructs it, its kit goes to the Pioneer's cargo). Already queued ones are left."""
    blueprints = get_component("construction_blueprint") if extractors else None
    if blueprints is None:
        return
    warned = state["undeploy_warned"]
    for cap_id, x, y in extractors:
        try:
            res = blueprints.mark_deconstruct(x, y, "building", cap_id)
        except Exception as error:
            swallowed("wildlife_retire._deconstruct_extractors: mark_deconstruct", error)
            continue
        status = getattr(res, "status", "") or "?"
        if status == "ok":
            log.print(f"[WILDLIFE] {cap_id}: marked for Pioneer deconstruction (Wildlife complete).")
        elif status != "already_queued" and warned.get(cap_id) != status:
            warned[cap_id] = status
            log.level("warn").print(f"[WILDLIFE] {cap_id}: mark_deconstruct -> {status}: {getattr(res, 'message', '')}")


def _retire(now):
    """
    One pass after the Wildlife pillar is complete: withdraws the life-form
    requests (again while any is left), releases every Habitat and empties
    every Feed Maker and Refiner (`plan.release` / `plan.complete`),
    undeploys each that reports ready and every exotic tank, marks every
    exotic cap/tap for deconstruction, sells their kits, wakes the parked rest
    and drops all feed from Inventory.
    Returns the number of those machines still standing.
    """
    if _own_requests_left():
        logistics_requests.clear_requests(REQUESTER_ID)
        if _own_requests_left():
            log.level("warn").print("[WILDLIFE] life-form requests not withdrawn; retried next pass.")
        else:
            log.print("[WILDLIFE] Life-form requests withdrawn.")
    habitat_ids, _home = network_habitats()
    maker_ids, _home = network_habitats(wc.FEED_MAKER_TYPE_ID)
    refiner_ids, _home = network_habitats(REFINER_TYPE_ID)
    statuses = archive.get(wc.STATUS_KEY, {}) or {}
    statuses = statuses if isinstance(statuses, dict) else {}
    feed = archive.get(wc.FEED_KEY, {}) or {}
    feed = {m: e for m, e in feed.items() if is_fresh(e, now, STATUS_STALE_TICKS)} if isinstance(feed, dict) else {}
    release = {hid: _retire_label(statuses.get(hid)) for hid in habitat_ids}
    retired = {"assign": {}, "buy": {}, "feed_demand": {}, "forage_reserve": 0, "form_targets": {}, "fluid_ration": {}, "fluid_supply": {}, "release": release, "progress": {"waiting": None, "skipped": [], "colonies": 0, "habitats": len(habitat_ids)}, "alerts": {}, "complete": True, "tick": now}
    if not archive.transaction(wc.PLAN_KEY, {}, lambda _old: retired):
        log.level("warn").print(f"{wc.PLAN_KEY} write rejected; retire plan not published this pass.")
        return len(habitat_ids) + len(maker_ids)
    labels = {hid: ("no colony" if s == wc.RELEASE_NO_COLONY else s) + ", Wildlife complete" for hid, s in release.items()}
    gone = undeploy_ready(labels, statuses, wc.STATUS_KEY, "release")
    gone += undeploy_ready({m: "Feed Maker, Wildlife complete" for m in maker_ids}, feed, wc.FEED_KEY, "retire")
    refiners = archive.get(refiner.STATUS_KEY, {}) or {}
    refiners = refiners if isinstance(refiners, dict) else {}
    gone += undeploy_ready({r: "Refiner, Wildlife complete" for r in refiner_ids}, refiners, refiner.STATUS_KEY, "retire")
    tank_ids = _exotic_tanks()
    gone += _undeploy_tanks(tank_ids)
    extractors = _exotic_extractors()
    _deconstruct_extractors(extractors)
    _sell_kits()
    parked = parked_ids("habitat")
    for hid in habitat_ids:
        if hid in parked and hid not in gone:
            wake_for_visit(hid, "Wildlife complete", hold=False)
    if set(maker_ids) - set(gone):
        wake_kind("feed_maker", "Wildlife complete")
    if set(refiner_ids) - set(gone):
        wake_kind(REFINER_TYPE_ID, "Wildlife complete")
    drop_feed(SPECIES, "Wildlife complete")
    return len(habitat_ids) + len(maker_ids) + len(refiner_ids) + len(tank_ids) + len(extractors) - len(gone)


def retire_pass(now):
    """One _retire() pass; latches state["retired"] once no Wildlife machine is left."""
    log.start("[WILDLIFE] retire pass", level="debug")
    left = _retire(now)
    if left:
        state["summary"] = f"{COMPLETE_SUMMARY}, retiring {left}"
        log.end(f"{left} left")
        return
    state["retired"] = True
    state["summary"] = COMPLETE_SUMMARY
    log.end("none left")
    log.print("[WILDLIFE] No Habitat, Feed Maker, Refiner, exotic tank or cap left; planner stops.")
