# Wildlife planner: the central decisions of the Wildlife automation, run by
# the Control Room Automation (plan_wildlife_if_due()) every
# PLAN_TICK_INTERVAL. The Habitat and Feed Maker scripts execute them
# (their game methods are self-only).
#
# One pass:
#   1. Snapshot (game reads): Habitats on the network, their `wildlife.status`
#      telemetry, the Feed Makers' `wildlife.feed` (unlocked recipes and
#      their inputs), cataloged creatures, home stock of feed and life forms,
#      tank stock of each fluid a Habitat band needs.
#   2. build_plan(snapshot): pure, as a chain of atomic calls
#      (lib/atomic.py), each bounded by the Habitat count; the whole plan in
#      one call would pass the 10,000-step callback cap. First call:
#      walks the offline revival schedule (wildlife_model.schedule_for() of
#      schedule_habitats(): peak count of deployed Habitats + Habitat kits
#      in Inventory, latched in `plan.schedule_habitats`) the way the optimizer does: steps run strictly in order; a
#      step that can never run (species already revived, node bought, not
#      cataloged, recipe locked, no Habitat left) is skipped;
#      the first step that can run later (Insight short, Breakthrough
#      source below 10,000) stops the walk, holding Insight.
#      Then each colony's hours to its ceiling at the full-support model
#      rate (MODEL_CHUNK-colony slices), and the fluid ration (per fluid, slowest colonies first within the tank
#      budget). Last call: feed demand per feed item (priority classes in
#      wildlife_common, fluid-holding colonies first), the Forage reserve for
#      the Plant Terraformer, life-form targets, the Habitats to wake and the
#      operator alerts.
#   3. Writes `wildlife.plan` / `wildlife.readiness`, the life-form requests
#      at home (requester REQUESTER_ID), wakes, notify() on alert changes.
#      Returns a one-line summary for the AUTOMATION card.
#
#   With the sensor at WILDLIFE_COMPLETE_POPULATION planning stops and each
#   pass retires instead (see plan_if_due, _retire): life-form requests
#   withdrawn, every Habitat released (`plan.release`, wc.RELEASE_NO_COLONY
#   for one without an established colony) and every Feed Maker emptied
#   (`plan.complete`), each undeployed once it reports ready, their kits sold
#   (Mk II packs stay in Inventory), all feed dropped from Inventory.
#   Wildlife never decays and an unhoused colony keeps counting
#   (docs/guide/wildlife_overview.md), so nothing is lost.
#
# Release: an established colony at wc.RELEASE_POPULATION (the Mk II
# ceiling) whose Breakthrough is bought is released (`plan.release`
# {habitat_id: species}, species recorded in wc.RELEASED_KEY). It gets no
# feed demand, fluid or purchase; its Habitat ejects its feed and reagents to
# local storage and purges its buffers, then reports `release` "ready" and is
# undeployed here (kit and Mk II pack back to Inventory). Feed of a released
# species at home (Inventory and home Warehouses) is dropped. A released species is never revived again.
#
# Parking of colonies at the Mk I ceiling (undeploy, rehouse) is not done:
# with no free Habitat a revive step can never run and is skipped.

from archive import archive
import components
from swallow import swallowed
from tree_console import TreeConsole
import logistics_requests
from script_parking import wake_for_visit, wake_kind, parked_ids
from wildlife_data import SPECIES, WILDLIFE_BOOTSTRAP, BONUS_TREES, ADAPTATION_COST, BREAKTHROUGH_COST, BREAKTHROUGH_POPULATION, REVIVE_FEED_REQUIRED, STAGE_CAPACITY, HABITAT_MK2_CAPACITY_FACTOR, FEED_PER_CRAFT, GAS_PER_BIRTH_T, LIQUID_PER_BIRTH_T, BUFFER_BLEED_T_PER_H, WILDLIFE_COMPLETE_POPULATION
from wildlife_model import schedule_for, breeding_rate, breakthrough_effects, adaptation_effects
from atomic import run_atomic, run_batched
import fluid_routing
import wildlife_common as wc
from storage import inventory_count, discover_storage_buildings, warehouse_stocks

PLAN_TICK_INTERVAL = 250            # one game hour
# undeploy() answers that only mean "not right now" (retried next pass).
TRANSIENT_UNDEPLOY_STATUSES = ("inventory_full", "cargo_present")
DROP_ROUNDS = 3                     # Warehouse -> Inventory -> drop rounds per feed item and pass (Inventory room limits each pull)
REQUESTER_ID = "feed_maker"         # life-form requests at home (logistics.requests)
# Kits sold from Inventory at Wildlife complete. Mk II packs are not sellable (only droppable) and stay.
RETIRE_SELL_ITEMS = (wc.HABITAT_KIT_ITEM_ID, wc.FEED_MAKER_TYPE_ID)
IDLE_SUMMARY = "wildlife idle"
COMPLETE_SUMMARY = "Wildlife complete"
MODEL_CHUNK = 4                     # colonies per atomic model slice (worst case ~2,300 steps, devtools/step_profile.py wildlife_ration)
TANK_CHUNK = 100                    # tanks per atomic get_component()/fluid()/level() read in _fluid_stock() (~20 steps each)

log = TreeConsole(module="wildlife_planner")

# Module state between passes (the Control Room Automation imports this once).
state = {"tick": 0, "summary": IDLE_SUMMARY, "alerts": None, "readiness": None, "progress": None, "complete": False, "retired": False, "undeploy_warned": {}}


# ---------------------------------------------------------------- pure core

def _purchased(statuses, released=None):
    """
    {species: {"adaptation": bool, "breakthrough": bool}} and the set of bought
    node ids, from the Habitats' telemetry and the released species' records
    (an undeployed colony keeps its bonuses).
    """
    by_species = {}
    nodes = set()
    entries = list(statuses.values())
    for species, record in (released or {}).items():
        if isinstance(record, dict):
            entries.append({"species": species, "bought": record.get("bought") or {}})
    for entry in entries:
        species = entry.get("species") or entry.get("target")
        bought = entry.get("bought") or {}
        if not species or species not in BONUS_TREES:
            continue
        flags = by_species.setdefault(species, {"adaptation": False, "breakthrough": False})
        for slot in ("adaptation", "breakthrough"):
            if bought.get(slot):
                flags[slot] = True
                nodes.add(BONUS_TREES[species][slot][0])
    return by_species, nodes


def _colonies(habitat_ids, statuses, prev_assign):
    """
    ({species: habitat_id} for every housed, targeted or still-assigned
    species, [free habitat ids]). An assignment stays until the Habitat
    reports the species established, or the Habitat no longer exists.
    """
    colonies = {}
    assign = {}
    free = []
    for hid in habitat_ids:
        entry = statuses.get(hid) or {}
        species = entry.get("species") or entry.get("target") or ""
        prior = prev_assign.get(hid) or {}
        if species:
            colonies[species] = hid
            if prior.get("species") == species and not entry.get("established"):
                assign[hid] = prior
        elif prior.get("species") and prior["species"] not in colonies:
            colonies[prior["species"]] = hid
            assign[hid] = prior
        else:
            free.append(hid)
    return colonies, assign, free


def _queue(schedule, targets):
    """Bootstrap revivals, then the schedule; operator targets reorder and filter the revivals."""
    steps = [("revive_raw", s) for s in WILDLIFE_BOOTSTRAP] + list(schedule)
    if not targets:
        return steps
    listed = [t for t in targets if t in SPECIES]
    kinds = {}
    for kind, s in steps:
        if kind in ("revive", "revive_raw"):
            kinds.setdefault(s, kind)
    head = [(kinds.get(s, "revive"), s) for s in listed]
    rest = [(k, s) for k, s in steps if k not in ("revive", "revive_raw")]
    return head + rest


def schedule_habitats(habitat_ids, kits, peak: "int | None" = 0):
    """
    Habitat count for schedule_for(): the largest count of owned Habitats
    (deployed + kits in Inventory) seen so far, `peak` being the last pass's
    value. The optimizer's schedules count a released colony's Habitat for the
    whole run, so its undeploy and the sale of its kit do not lower the count.
    """
    owned = len(habitat_ids) + max(0, int(kits or 0))
    return max(owned, int(peak or 0))


def _walk(snap, colonies, free, assign, bought, insight, released=()):
    """
    Runs the schedule queue. Returns (assign, buy, skipped, waiting) where
    buy = {habitat_id: slot} and waiting = (step, reason) of the first held
    step, or None. A released species is never revived, and its unbought
    nodes are skipped ("released").

    A held step keeps its cost reserved. Revivals stop at the first held
    step; a later Adaptation or Breakthrough still runs from Insight above
    the reserve, so a population-gated Breakthrough or a busy Habitat holds
    only its own cost.
    """
    cataloged = snap["cataloged"]
    recipes = snap["recipes"]
    pops = snap["populations"]
    buy = {}
    skipped = []
    free = list(free)
    waiting = None
    reserved = 0.0
    # Adaptations of earlier revive steps not bought yet: still owed.
    for hid, entry in assign.items():
        species = entry.get("species")
        if entry.get("adapt_first") and not (bought.get(species) or {}).get("adaptation"):
            buy[hid] = "adaptation"
            insight -= ADAPTATION_COST
    for step in _queue(snap["schedule"], snap["targets"]):
        kind, s = step
        flags = bought.get(s) or {}
        if kind in ("revive", "revive_raw"):
            if s in colonies or s in released:
                continue
            if s not in cataloged:
                skipped.append((step, "not_cataloged"))
                continue
            if recipes and wc.recipe_of(s) not in recipes:
                skipped.append((step, "no_recipe"))
                continue
            if not free:
                skipped.append((step, "no_habitat"))
                continue
            if waiting:
                return assign, buy, skipped, waiting
            cost = ADAPTATION_COST if kind == "revive" else 0
            if insight < cost - 1e-9:
                return assign, buy, skipped, (step, "insight %.2f < %d" % (insight, cost))
            hid = free.pop(0)
            colonies[s] = hid
            assign[hid] = {"species": s, "adapt_first": kind == "revive", "tick": snap["tick"]}
            if kind == "revive":
                buy[hid] = "adaptation"
                insight -= cost
            continue
        slot = "adaptation" if kind == "adapt" else "breakthrough"
        if flags.get(slot):
            continue
        if s in released:
            skipped.append((step, "released"))
            continue
        hid = colonies.get(s)
        cost = ADAPTATION_COST if slot == "adaptation" else BREAKTHROUGH_COST
        held = None
        if hid is None:
            if not free:
                skipped.append((step, "no_habitat"))
                continue
            held = "%s not revived" % s
        elif buy.get(hid) == slot:
            continue
        elif slot == "breakthrough" and pops.get(s, 0) < BREAKTHROUGH_POPULATION:
            held = "%s at %d < %d" % (s, pops.get(s, 0), BREAKTHROUGH_POPULATION)
        elif insight - reserved < cost - 1e-9:
            held = "insight %.2f < %d" % (insight - reserved, cost)
        elif hid in buy:
            # One purchase per Habitat per pass; the next pass queues this one.
            held = "%s busy buying %s" % (hid, buy[hid])
        if held:
            waiting = waiting or (step, held)
            reserved += cost
            continue
        buy[hid] = slot
        insight -= cost
    return assign, buy, skipped, waiting


def _mk_ceiling(entry):
    tier = int(entry.get("tier") or 1)
    return STAGE_CAPACITY[4] * (HABITAT_MK2_CAPACITY_FACTOR if tier >= 2 else 1)


def _model_rows(pairs, statuses, nodes, others):
    """[[habitat_id, hours to the Mk ceiling, individuals/h]] for the (species, habitat_id) pairs given."""
    shared = breakthrough_effects(nodes)
    out = []
    for species, hid in pairs:
        entry = statuses.get(hid) or {}
        pop = int(entry.get("pop") or 0)
        left = max(0.0, _mk_ceiling(entry) - pop)
        rate = breeding_rate(species, pop, shared + adaptation_effects(nodes, species), others) if left > 0 else 0.0
        out.append([hid, left / rate if rate > 0 else 0.0, rate])
    return out


def _colony_model(colonies, statuses, nodes):
    """
    {habitat_id: (hours to the Mk ceiling, individuals/h)} for established
    colonies at the full-support model rate (efficiency 1), not the live rate:
    a starved or rationed colony's live rate drops and would reorder the ranks
    every pass. A colony at its ceiling gets (0, 0). Runs atomically in
    MODEL_CHUNK-colony slices (one breeding_rate() with every node bought is
    ~600 steps).
    """
    pairs = [(s, hid) for s, hid in colonies.items() if s in SPECIES and (statuses.get(hid) or {}).get("established")]
    others = max(0, len(pairs) - 1)
    rows = run_batched(_model_rows, pairs, MODEL_CHUNK, statuses, nodes, others)
    return {r[0]: (r[1], r[2]) for r in rows}


def _holds_fluid(entry):
    for medium in wc.TANK_TYPE_IDS:
        row = entry.get(medium)
        if isinstance(row, list) and len(row) > wc.MEDIUM_LEVEL and float(row[wc.MEDIUM_LEVEL] or 0.0) > 0:
            return True
    return False


def _feed_demand(snap, colonies, statuses, nodes, model):
    """
    ({feed_item: [home stock target, priority, units short now]}, {species: feed per game hour}).
    Target = home buffer + what the Habitat bin still lacks; an item is listed
    while home stock is below it. Feed Makers craft until live home stock
    reaches the target. An established colony whose bin + home stock is below
    its urgent cover (wc.FEED_URGENT_H) asks for that cover only, in
    PRIO_URGENT, so no colony starves while others build their buffers.
    """
    stock = snap["feed_stock"]
    rows = []
    use = {}
    multipliers = wc.feed_multipliers(colonies, nodes)
    for species, hid in colonies.items():
        entry = statuses.get(hid) or {}
        item = wc.feed_item_of(species)
        bin_level = float(entry.get("feed_level") or 0.0)
        if entry.get("established"):
            # breeding_rate() reads 0 while the colony is blocked, an empty
            # feed bin included; the model rate keeps a starved colony's feed
            # in demand (a colony at its ceiling models 0).
            rate = float(entry.get("rate") or 0.0) or (model.get(hid) or (0.0, 0.0))[1]
            per_h = wc.feed_per_hour(rate, multipliers[species])
            use[species] = per_h
            target = wc.FEED_BUFFER_H * per_h
            if per_h > 0:
                target = max(target, FEED_PER_CRAFT)
            bin_short = max(0.0, wc.FEED_TOPUP_TARGET - bin_level) if per_h > 0 else 0.0
            hours = (model.get(hid) or (0.0, 0.0))[0]
            cover = max(wc.FEED_TOPUP_TARGET, wc.FEED_URGENT_H * per_h)
            if per_h > 0 and bin_level + stock.get(item, 0) < cover:
                rows.append((item, cover - bin_level, wc.PRIO_URGENT, hours, bin_level))
            else:
                prio = wc.PRIO_FLUID_HELD if _holds_fluid(entry) else wc.PRIO_GROWING
                rows.append((item, target + bin_short, prio, hours, bin_level))
        elif entry.get("rearing"):
            # Established within 12 h: have the bin's first top-up ready.
            rows.append((item, max(0.0, wc.FEED_TOPUP_TARGET - bin_level), wc.PRIO_REARING, 0.0, bin_level))
        else:
            rows.append((item, max(0.0, REVIVE_FEED_REQUIRED + wc.REARING_FEED_EXTRA - bin_level), wc.PRIO_RESERVE, 0.0, bin_level))
    ranked_prios = (wc.PRIO_FLUID_HELD, wc.PRIO_GROWING)
    ranked = sorted((r for r in rows if r[2] in ranked_prios), key=lambda r: -r[3])
    rank = {r[0]: i for i, r in enumerate(ranked)}
    urgent = sorted((r for r in rows if r[2] == wc.PRIO_URGENT), key=lambda r: (r[4], -r[3]))
    rank.update((r[0], i) for i, r in enumerate(urgent))
    ranked_prios += (wc.PRIO_URGENT,)
    demand = {}
    for item, units, prio, _hours, _bin in rows:
        target = int(units + 0.999)
        need = target - int(stock.get(item, 0))
        if need <= 0:
            continue
        p = prio * wc.PRIO_RANK_SCALE + rank.get(item, 0) if prio in ranked_prios else prio * wc.PRIO_RANK_SCALE
        demand[item] = [target, p, need]
    return demand, use


def _consumers(colonies, statuses, model):
    """
    {fluid: [[habitat_id, need t/h, hours to ceiling, port flow t/h]]} for
    established colonies below their ceiling whose band (or pre-fill) needs a
    fluid. Need = consumption at the model rate + bleed + the fill to the band
    centre spread over RATION_RUNWAY_H. A colony at its ceiling is skipped:
    the game neither meters nor bleeds its buffers.
    """
    out = {}
    for hid in colonies.values():
        hours, rate = model.get(hid) or (0.0, 0.0)
        if rate <= 0:
            continue
        entry = statuses.get(hid) or {}
        for medium, per_birth in (("gas", GAS_PER_BIRTH_T), ("liquid", LIQUID_PER_BIRTH_T)):
            row = entry.get(medium) or []
            if len(row) <= wc.MEDIUM_FLOW:
                continue
            fluid = row[wc.MEDIUM_REQUIRED]
            band = row[wc.MEDIUM_BAND]
            if not fluid or not isinstance(band, list) or len(band) < 2:
                continue
            fill = max(0.0, (band[0] + band[1]) / 2.0 - float(row[wc.MEDIUM_LEVEL] or 0.0))
            need = rate * per_birth + BUFFER_BLEED_T_PER_H + fill / wc.RATION_RUNWAY_H
            out.setdefault(fluid, []).append([hid, need, hours, float(row[wc.MEDIUM_FLOW] or 0.0)])
    return out


def _inflow(stock, drawn, prev, now):
    """
    Smoothed gross tank inflow (t/h): stock change since the last pass plus
    what the Habitats drew. None without a previous reading.
    """
    if not isinstance(prev, list) or len(prev) < 3:
        return None
    hours = (now - int(prev[2] or 0)) / float(wc.TICKS_PER_GAME_HOUR)
    if hours <= 0:
        return prev[1]
    raw = max(0.0, (stock - float(prev[0] or 0.0)) / hours + drawn)
    if prev[1] is None:
        return raw
    return prev[1] + wc.RATION_INFLOW_ALPHA * (raw - prev[1])


def _fluid_ration(consumers, stock, prev_supply, prev_ration, now):
    """
    ({habitat_id: [denied fluids]}, {fluid: [stock t, inflow t/h, tick, need t/h]}).
    Per fluid, colonies are granted slowest first while their need fits the
    budget (inflow + stock / RATION_RUNWAY_H). The walk stops at the first
    colony that does not fit, so stock banks up for it rather than going to
    faster colonies. Without an inflow estimate (first pass) all are granted.
    """
    ration = {}
    supply = {}
    for fluid in sorted(consumers):
        rows = sorted(consumers[fluid], key=lambda r: -r[2])
        have = float(stock.get(fluid) or 0.0)
        inflow = _inflow(have, sum(r[3] for r in rows), prev_supply.get(fluid), now)
        supply[fluid] = [round(have, 1), None if inflow is None else round(inflow, 3), now, round(sum(r[1] for r in rows), 3)]
        if inflow is None:
            continue
        budget = inflow + have / wc.RATION_RUNWAY_H
        used = 0.0
        blocked = False
        for hid, need, _hours, _flow in rows:
            granted_before = fluid not in (prev_ration.get(hid) or [])
            limit = budget if granted_before else budget * (1.0 - wc.RATION_HYSTERESIS)
            if not blocked and used + need <= limit:
                used += need
            else:
                blocked = True
                ration.setdefault(hid, []).append(fluid)
    return ration, supply


def _ration_pass(colonies, statuses, model, stock, prev_supply, prev_ration, now):
    """Consumers and the fluid ration in one pure call (run atomically; bounded by the Habitat count)."""
    return _fluid_ration(_consumers(colonies, statuses, model), stock, prev_supply, prev_ration, now)


def _form_targets(snap, colonies, use, demand):
    """{form: units} the home stock should hold: FORM_BUFFER_H of each active species' crafts + open demand."""
    inputs = snap["recipe_inputs"]
    targets = {}
    for species in colonies:
        recipe = inputs.get(wc.recipe_of(species)) or {}
        if not recipe:
            continue
        crafts = wc.FORM_BUFFER_H * use.get(species, 0.0) / FEED_PER_CRAFT
        crafts += wc.crafts_for((demand.get(wc.feed_item_of(species)) or [0, 0, 0])[2])
        crafts = max(crafts, wc.FORM_REQUEST_MIN_CRAFTS)
        for form, qty in recipe.items():
            if form == "forage":
                continue
            targets[form] = targets.get(form, 0) + int(crafts * qty + 0.999)
    return {f: min(wc.FORM_REQUEST_CAP, n) for f, n in targets.items()}


def _wakes_and_alerts(snap, statuses, assign, buy, ration, release=None):
    """([habitat ids to wake, with reason], {"no_feed": [...], "capped": [...], "rationed": [...]}).

    Only the source species' Habitat can buy its nodes, so a parked one with a
    queued purchase is woken whatever it is parked for. A released Habitat is
    woken to empty itself.

    "rationed" lists every Habitat denied a fluid this pass, parked or not."""
    wakes = []
    alerts = {wc.PARK_NO_FEED: [], wc.PARK_CAPPED: [], wc.PARK_RATIONED: sorted(ration)}
    parked = snap["parked"]
    release = release or {}
    for hid in snap["habitat_ids"]:
        entry = statuses.get(hid) or {}
        reason = entry.get("parked") or ""
        if hid in release:
            if hid in parked:
                wakes.append((hid, "release " + release[hid]))
            continue
        if reason in (wc.PARK_NO_FEED, wc.PARK_CAPPED):
            alerts[reason].append(hid)
        if hid not in parked:
            continue
        if hid in buy:
            wakes.append((hid, "buy " + buy[hid]))
        elif hid in assign and reason in ("", wc.PARK_EMPTY):
            wakes.append((hid, "assigned " + assign[hid]["species"]))
        elif reason == wc.PARK_NO_FEED:
            item = entry.get("feed_item") or ""
            if snap["feed_stock"].get(item, 0) >= wc.FEED_TOPUP_TARGET:
                wakes.append((hid, "feed in stock"))
        elif reason == wc.PARK_CAPPED and snap["mk2_packs"] > 0 and int(entry.get("tier") or 1) < 2:
            wakes.append((hid, "Mk II pack in Inventory"))
        elif reason == wc.PARK_RATIONED and hid not in ration:
            wakes.append((hid, "fluid granted"))
    return wakes, alerts


def _releases(colonies, statuses, bought, released, buy):
    """
    {habitat_id: species} to release: a housed species already released, or an
    established colony at wc.RELEASE_POPULATION whose Breakthrough is bought
    (held while its Habitat still buys a node this pass).
    """
    out = {}
    for species, hid in colonies.items():
        entry = statuses.get(hid) or {}
        if species in released:
            out[hid] = species
        elif (entry.get("established") and int(entry.get("pop") or 0) >= wc.RELEASE_POPULATION
              and (bought.get(species) or {}).get("breakthrough") and hid not in buy):
            out[hid] = species
    return out


def _assign_pass(snap):
    """Purchases, colonies, the schedule walk and the releases in one pure call (run atomically; bounded by the Habitat count)."""
    statuses = snap["statuses"]
    released = snap.get("released") or {}
    bought, nodes = _purchased(statuses, released)
    colonies, assign, free = _colonies(snap["habitat_ids"], statuses, snap["prev_assign"])
    assign, buy, skipped, waiting = _walk(snap, colonies, free, assign, bought, snap["insight"], released)
    release = _releases(colonies, statuses, bought, released, buy)
    return nodes, colonies, assign, buy, skipped, waiting, release


def _demand_pass(snap, colonies, nodes, model, assign, buy, ration, release):
    """Feed demand, Forage reserve, life-form targets, wakes and alerts in one pure call (run atomically; bounded by the Habitat count)."""
    statuses = snap["statuses"]
    demand, use = _feed_demand(snap, colonies, statuses, nodes, model)
    forage = sum(wc.forage_for(v[2]) for v in demand.values())
    if forage:
        forage += wc.forage_for(FEED_PER_CRAFT)
    wakes, alerts = _wakes_and_alerts(snap, statuses, assign, buy, ration, release)
    return demand, forage, _form_targets(snap, colonies, use, demand), wakes, alerts


def build_plan(snap):
    """Pure: the whole plan from one snapshot (no game calls, no logging)."""
    statuses = snap["statuses"]
    nodes, colonies, assign, buy, skipped, waiting, release = run_atomic(_assign_pass, snap)
    # Released colonies get no feed, fluid or model rank.
    active = {s: hid for s, hid in colonies.items() if hid not in release}
    model = _colony_model(active, statuses, nodes)
    ration, supply = run_atomic(_ration_pass, active, statuses, model, snap["fluid_stock"],
                                snap["prev_supply"], snap["prev_ration"], snap["tick"])
    demand, forage, form_targets, wakes, alerts = run_atomic(_demand_pass, snap, active, nodes, model, assign, buy, ration, release)
    missing_creatures = sorted(s for s in SPECIES if s not in snap["cataloged"])
    missing_recipes = sorted(s for s in SPECIES if snap["recipes"] and wc.recipe_of(s) not in snap["recipes"])
    return {
        "assign": assign,
        "buy": buy,
        "feed_demand": demand,
        "forage_reserve": forage,
        "form_targets": form_targets,
        "fluid_ration": ration,
        "fluid_supply": supply,
        "release": release,
        "progress": {
            "waiting": [list(waiting[0]), waiting[1]] if waiting else None,
            "skipped": [[list(step), reason] for step, reason in skipped],
            "colonies": len(colonies),
            "habitats": len(snap["habitat_ids"]),
        },
        "alerts": alerts,
        "wakes": wakes,
        "readiness": {"missing_creatures": missing_creatures, "missing_recipes": missing_recipes},
        "schedule_habitats": snap.get("schedule_habitats", len(snap["habitat_ids"])),
        "tick": snap["tick"],
    }


def summary_line(plan):
    """One AUTOMATION card item, or IDLE_SUMMARY when nothing needs the operator."""
    parts = []
    alerts = plan.get("alerts") or {}
    if plan.get("release"):
        parts.append("releasing %d at %d" % (len(plan["release"]), wc.RELEASE_POPULATION))
    if alerts.get(wc.PARK_CAPPED):
        parts.append("%d capped at Mk I (Mk II needed)" % len(alerts[wc.PARK_CAPPED]))
    if alerts.get(wc.PARK_NO_FEED):
        parts.append("%d without feed" % len(alerts[wc.PARK_NO_FEED]))
    if alerts.get(wc.PARK_RATIONED):
        parts.append("%d fluid-rationed" % len(alerts[wc.PARK_RATIONED]))
    missing = (plan.get("readiness") or {}).get("missing_recipes") or []
    if missing:
        parts.append("%d feed recipe(s) locked" % len(missing))
    return "wildlife: " + ", ".join(parts) if parts else IDLE_SUMMARY


# ---------------------------------------------------------------- game side

def _now(clock):
    try:
        return clock.tick() if clock and hasattr(clock, "tick") else 0
    except Exception as error:
        swallowed("wildlife_planner._now: clock.tick", error)
        return 0


def _network_habitats(type_id="habitat"):
    """(sorted ids of `type_id` buildings on the network, home OutpostRef or None)."""
    ids = []
    home = None
    network = get_component("outpost_network")
    if not network or not hasattr(network, "outposts"):
        return ids, home
    try:
        for outpost in network.outposts():
            if getattr(outpost, "is_home", False):
                home = outpost
            for ref in outpost.buildings(type_id):
                ref_id = getattr(ref, "id", None)
                if ref_id:
                    ids.append(ref_id)
    except Exception as error:
        swallowed("wildlife_planner._network_habitats: outpost.buildings", error)
    return sorted(ids), home


def _cataloged():
    journal = get_component("journal")
    if not journal:
        return set()
    try:
        return set(getattr(c, "creature_id", "") for c in journal.cataloged_creatures(wc.PLANET_ID))
    except Exception as error:
        swallowed("wildlife_planner._cataloged: journal.cataloged_creatures", error)
        return set()


def _recipes(feed, now):
    """(set of unlocked recipe ids, {recipe_id: {item: qty}}) from fresh Feed Maker telemetry."""
    ids = set()
    inputs = {}
    for entry in (feed or {}).values():
        if not wc.fresh(entry, now):
            continue
        for recipe_id, recipe_inputs in (entry.get("recipes") or {}).items():
            ids.add(recipe_id)
            if isinstance(recipe_inputs, dict):
                inputs[recipe_id] = recipe_inputs
    return ids, inputs


def _insight(statuses, now):
    best_tick, value = -1, 0.0
    for entry in statuses.values():
        if wc.fresh(entry, now) and entry.get("tick", 0) > best_tick and entry.get("insight") is not None:
            best_tick, value = entry["tick"], float(entry["insight"])
    return value


def _fluid_stock(statuses):
    """{fluid: tons in every tank eligible for it}, for each fluid a Habitat band (or pre-fill) needs."""
    wanted = {}
    for entry in statuses.values():
        for medium in wc.TANK_TYPE_IDS:
            row = entry.get(medium)
            if isinstance(row, list) and len(row) > wc.MEDIUM_REQUIRED and row[wc.MEDIUM_REQUIRED]:
                wanted[row[wc.MEDIUM_REQUIRED]] = medium
    out = {fluid: 0.0 for fluid in wanted}
    if not out:
        return out
    # Each tank counts only toward the fluid it is latched to (an unlatched
    # tank holds nothing); a latched tank is eligible unless retiring
    # (fluid_routing.tank_is_eligible_target()). Discovery and reads run
    # atomically: the ref walk in one call, the tank reads in TANK_CHUNK slices.
    assignments = fluid_routing.get_tank_assignments()
    retiring = set(b_id for b_id, fluid in assignments.items() if fluid == fluid_routing.RETIRING_ASSIGNMENT)
    types = {type_id: medium for medium in set(wanted.values()) for type_id in wc.TANK_TYPE_IDS[medium]}
    network = get_component("outpost_network")
    try:
        outposts = list(network.outposts()) if network else []
    except Exception as error:
        swallowed("wildlife_planner._fluid_stock: network.outposts", error)
        outposts = []
    tanks = run_atomic(_tank_refs, outposts, types, retiring)
    for fluid, level in run_batched(_tank_rows, tanks, TANK_CHUNK, wanted):
        out[fluid] += level
    return out


def _tank_refs(outposts, types, retiring):
    """[(tank id, medium)] for every tank of a `types` type id on `outposts`, not retiring; pure reads, run atomically."""
    out = []
    seen = set(retiring)
    for outpost in outposts:
        for type_id, medium in types.items():
            try:
                refs = outpost.buildings(type_id)
            except Exception as error:
                swallowed("wildlife_planner._tank_refs: outpost.buildings", error)
                continue
            for ref in refs:
                tank_id = getattr(ref, "id", None)
                if tank_id and tank_id not in seen:
                    seen.add(tank_id)
                    out.append((tank_id, medium))
    return out


def _tank_rows(tanks, wanted):
    """[(fluid, tons)] for the (tank id, medium) pairs latched to a fluid `wanted` from that medium; pure reads, run atomically."""
    rows = []
    for tank_id, medium in tanks:
        try:
            tank = components.tank(tank_id)
            if tank is None:
                continue
            fluid = tank.fluid()
            if fluid and wanted.get(fluid) == medium:
                rows.append((fluid, float(tank.level() or 0.0)))
        except Exception as error:
            swallowed("wildlife_planner._tank_rows: tank.level", error)
    return rows


def snapshot(now):
    """Every game read build_plan() needs; None when there is no Habitat."""
    habitat_ids, home = _network_habitats()
    if not habitat_ids:
        return None
    statuses = archive.get(wc.STATUS_KEY, {}) or {}
    statuses = {hid: e for hid, e in statuses.items() if hid in habitat_ids and isinstance(e, dict)}
    feed = archive.get(wc.FEED_KEY, {}) or {}
    recipes, recipe_inputs = _recipes(feed if isinstance(feed, dict) else {}, now)
    plan = archive.get(wc.PLAN_KEY, {}) or {}
    targets = archive.get(wc.TARGETS_KEY, []) or []
    released = archive.get(wc.RELEASED_KEY, {}) or {}
    released = {s: r for s, r in released.items() if isinstance(r, dict)} if isinstance(released, dict) else {}
    feed_items = [wc.feed_item_of(s) for s in SPECIES]
    forms = sorted(set(f for r in recipe_inputs.values() for f in r if f != "forage"))
    stock = logistics_requests.outpost_stock(feed_items + forms, home) if home else {}
    populations = {}
    for entry in statuses.values():
        species = entry.get("species")
        if species:
            populations[species] = int(entry.get("pop") or 0)
    if not isinstance(plan, dict):
        plan = {}
    habitats = schedule_habitats(habitat_ids, inventory_count(wc.HABITAT_KIT_ITEM_ID), plan.get("schedule_habitats") or 0)
    return {
        "tick": now,
        "habitat_ids": habitat_ids,
        "statuses": statuses,
        "parked": set(parked_ids("habitat")),
        "cataloged": _cataloged(),
        "recipes": recipes,
        "recipe_inputs": recipe_inputs,
        "insight": _insight(statuses, now),
        "schedule_habitats": habitats,
        "schedule": schedule_for(habitats),
        "targets": list(targets) if isinstance(targets, list) else [],
        "released": released,
        "prev_assign": plan.get("assign") or {},
        "prev_ration": plan.get("fluid_ration") or {},
        "prev_supply": plan.get("fluid_supply") or {},
        "fluid_stock": _fluid_stock(statuses),
        "feed_stock": {i: stock.get(i, 0) for i in feed_items},
        "form_stock": {f: stock.get(f, 0) for f in forms},
        "populations": populations,
        "mk2_packs": inventory_count(wc.MK2_PACK_ITEM_ID),
        "home": home,
    }


def _publish_requests(snap: dict, plan: dict, now):
    """Life-form requests at home for the Feed Makers; forms another requester owns there are left to it."""
    home_id = getattr(snap.get("home"), "id", None)
    if not home_id:
        return
    form_stock = snap.get("form_stock") or {}
    wants = {form: (target, form_stock.get(form, 0)) for form, target in plan["form_targets"].items()}
    if logistics_requests.publish_requests(home_id, REQUESTER_ID, wants, now):
        short = sorted(f for f, w in wants.items() if w[1] < w[0])
        log.debug(f"life-form requests: {len(wants)} form(s), {len(short)} below target: {short}")


def _write(plan):
    stored = {k: plan[k] for k in ("assign", "buy", "feed_demand", "forage_reserve", "form_targets", "fluid_ration", "fluid_supply", "release", "progress", "alerts", "schedule_habitats", "tick")}

    def updater(_old):
        return stored

    if not archive.transaction(wc.PLAN_KEY, {}, updater):
        log.level("warn").print(f"{wc.PLAN_KEY} write rejected; plan not published this pass.")
        return False
    if plan["readiness"] != state["readiness"]:
        archive.set(wc.READINESS_KEY, plan["readiness"])
    return True


def _report(plan, prev_assign, prev_buy, prev_ration):
    """Info lines for new assignments, purchases and ration changes, debug for the walk and fluid budgets, notify() on alert changes."""
    for hid, entry in plan["assign"].items():
        if (prev_assign.get(hid) or {}).get("species") != entry["species"]:
            first = " (Adaptation first)" if entry.get("adapt_first") else ""
            log.print(f"[WILDLIFE] {hid}: revive {entry['species']}{first}.")
    for hid, slot in plan["buy"].items():
        if prev_buy.get(hid) != slot:
            log.print(f"[WILDLIFE] {hid}: buy {slot}.")
    ration = plan["fluid_ration"]
    for hid in sorted(set(ration) | set(prev_ration)):
        now_denied = sorted(ration.get(hid) or [])
        if now_denied != sorted(prev_ration.get(hid) or []):
            log.print(f"[WILDLIFE] {hid}: fluid " + (f"rationed ({', '.join(now_denied)} denied)." if now_denied else "granted again."))
    for fluid, row in plan["fluid_supply"].items():
        inflow = "n/a" if row[1] is None else f"{row[1]:.2f}"
        log.debug(f"{fluid}: stock {row[0]:.0f} t, inflow {inflow} t/h, need {row[3]:.2f} t/h")
    progress = plan["progress"]
    signature = (progress["waiting"], [s[0] for s in progress["skipped"]])
    if signature != state["progress"]:
        state["progress"] = signature
        if progress["waiting"]:
            log.debug(f"schedule waits on {progress['waiting'][0]}: {progress['waiting'][1]}")
        for step, reason in progress["skipped"]:
            log.debug(f"schedule skips {step}: {reason}")
    if plan["readiness"] != state["readiness"]:
        state["readiness"] = plan["readiness"]
        missing = plan["readiness"]
        if missing["missing_creatures"] or missing["missing_recipes"]:
            log.level("warn").print(f"[WILDLIFE] Not cataloged: {missing['missing_creatures']}; feed recipes locked: {missing['missing_recipes']}.")
    alerts = plan["alerts"]
    if alerts != state["alerts"]:
        if state["alerts"] is not None or alerts[wc.PARK_CAPPED] or alerts[wc.PARK_NO_FEED] or alerts[wc.PARK_RATIONED]:
            message = summary_line(plan)
            if message != IDLE_SUMMARY:
                _notify(f"[Wildlife] {message}")
        state["alerts"] = alerts


def _record_released(snap, release, now):
    """Adds newly released species to wc.RELEASED_KEY (with their bought nodes); logs each once."""
    statuses = snap["statuses"]
    new = {s: hid for hid, s in release.items() if s not in snap["released"]}
    if not new:
        return

    def updater(records):
        records = records if isinstance(records, dict) else {}
        for species, hid in new.items():
            entry = statuses.get(hid) or {}
            records.setdefault(species, {"habitat": hid, "pop": int(entry.get("pop") or 0),
                                         "bought": dict(entry.get("bought") or {}), "tick": now})
        return records

    if not archive.transaction(wc.RELEASED_KEY, {}, updater):
        log.level("warn").print(f"{wc.RELEASED_KEY} write rejected; release recorded next pass.")
        return
    for species, hid in sorted(new.items()):
        pop = int((statuses.get(hid) or {}).get("pop") or 0)
        log.print(f"[WILDLIFE] {hid}: {species} at {pop}: released; Habitat empties, then is undeployed.")
        snap["released"][species] = {"habitat": hid}


def _undeploy(computer, hid):
    """undeploy() status ("ok", "not_found", a refusal); "error" when the call raised."""
    try:
        res = computer.undeploy(hid)
    except Exception as error:
        swallowed("wildlife_planner._undeploy: computer.undeploy", error)
        return "error"
    status = getattr(res, "status", "") or "?"
    if status not in ("ok", "not_found"):
        warned = state["undeploy_warned"]
        level = "debug" if status in TRANSIENT_UNDEPLOY_STATUSES else "warn"
        if level == "debug" or warned.get(hid) != status:
            warned[hid] = status
            log.level(level).print(f"[WILDLIFE] {hid}: undeploy -> {status}: {getattr(res, 'message', '')}")
    return status


def _pull_from_warehouses(item):
    """Moves every unit of `item` from the home Warehouses into Inventory (as far as it has room). Returns units moved."""
    moved = 0
    for building in discover_storage_buildings():
        component = building["component"]
        try:
            units = int(component.count(item) or 0) if component else 0
            if units <= 0:
                continue
            res = component.transfer_to("inventory", item, units)
        except Exception as error:
            swallowed("wildlife_planner._pull_from_warehouses: transfer_to", error)
            continue
        got = int(getattr(res, "moved", 0) or 0)
        moved += got
        log.debug(f"{building['id']}: {got}/{units}x {item} to Inventory for dropping ({getattr(res, 'status', '?')}).")
    return moved


def _drop_feed(species_ids, reason):
    """
    Drops every unit of each species' feed held at home: Inventory (an emptied
    Habitat or Feed Maker ejects it there) and the home Warehouses (pulled into
    Inventory first, up to DROP_ROUNDS rounds while Inventory room limits the
    pull; the rest goes next pass). Feed in Drone Depots is not touched.
    """
    inventory = get_component("inventory")
    if inventory is None or not species_ids:
        return
    items = {wc.feed_item_of(s): s for s in species_ids}
    stored = warehouse_stocks(sorted(items))
    for item, species in sorted(items.items()):
        dropped = 0
        for _round in range(DROP_ROUNDS):
            pulled = _pull_from_warehouses(item) if stored.get(item, 0) > 0 else 0
            if inventory_count(item) <= 0:
                break
            try:
                res = inventory.drop_all(item)
            except Exception as error:
                swallowed("wildlife_planner._drop_feed: inventory.drop_all", error)
                break
            if getattr(res, "status", "") != "ok":
                break
            dropped += int(getattr(res, "count", 0) or 0)
            if not pulled:
                break
        if dropped:
            log.print(f"[WILDLIFE] Dropped {dropped}x {item} ({species} {reason}).")


def _execute_releases(snap, plan, now):
    """
    Records new releases, undeploys each released Habitat once it reports
    `release` "ready" (refusals are retried next pass) and drops released
    species' feed from Inventory.
    """
    release = plan["release"]
    _record_released(snap, release, now)
    _undeploy_ready({hid: species + " released" for hid, species in release.items()}, snap["statuses"], wc.STATUS_KEY, "release")
    _drop_feed(snap["released"], "released")


def _undeploy_ready(machines, statuses, status_key, field):
    """
    Undeploys each of `machines` ({machine_id: label}) whose `statuses` entry
    reads `field` == wc.RELEASE_READY and drops its `status_key` entry.
    Refusals are retried next pass. Returns the ids gone.
    """
    computer = get_component("computer") if machines else None
    gone = []
    for machine_id, label in sorted(machines.items()):
        entry = statuses.get(machine_id) or {}
        if entry.get(field) != wc.RELEASE_READY:
            log.debug(f"{machine_id}: {label}, waits for it to empty ({entry.get(field) or 'not started'}).")
            continue
        if computer is None:
            continue
        status = _undeploy(computer, machine_id)
        if status in ("ok", "not_found"):
            archive.pop_entry(status_key, machine_id)
            state["undeploy_warned"].pop(machine_id, None)
            gone.append(machine_id)
            if status == "ok":
                log.print(f"[WILDLIFE] {machine_id}: undeployed ({label}); kit back in Inventory.")
    return gone


def _notify(message):
    try:
        notify(message, level="warn", duration_seconds=10.0)
    except Exception as error:
        swallowed("wildlife_planner._notify: notify", error)


def plan(clock):
    """One planning pass. Returns the AUTOMATION card summary."""
    now = _now(clock)
    snap = snapshot(now)
    if snap is None:
        state["summary"] = IDLE_SUMMARY
        return IDLE_SUMMARY
    log.start(f"[WILDLIFE] plan: {len(snap['habitat_ids'])} Habitat(s), insight {snap['insight']:.2f}", level="debug")
    prev = archive.get(wc.PLAN_KEY, {}) or {}
    pure = {k: v for k, v in snap.items() if k != "home"}
    result = build_plan(pure)
    if not _write(result):
        log.end("write rejected")
        return state["summary"]
    _report(result, snap["prev_assign"], (prev.get("buy") or {}) if isinstance(prev, dict) else {}, snap["prev_ration"])
    _publish_requests(snap, result, now)
    _execute_releases(snap, result, now)
    for hid, reason in result["wakes"]:
        wake_for_visit(hid, reason, hold=False)
    if result["feed_demand"]:
        wake_kind("feed_maker", "feed demand")
    state["summary"] = summary_line(result)
    log.end(f"{len(result['assign'])} assigned, {len(result['buy'])} purchase(s), {len(result['feed_demand'])} feed item(s) short")
    return state["summary"]


def _population():
    """Wildlife sensor reading, or None when the sensor is missing or fails."""
    try:
        sensor = get_component("wildlife_sensor")
        return sensor.get_value() if sensor else None
    except Exception as error:
        swallowed("wildlife_planner._population: wildlife_sensor.get_value", error)
        return None


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
            swallowed("wildlife_planner._sell_kits: shop.sell", error)
            continue
        if getattr(res, "status", "") == "ok":
            log.print(f"[WILDLIFE] Sold {units}x {item} for {getattr(res, 'credits', 0) or 0} cr (Wildlife complete).")
        else:
            log.level("warn").print(f"[WILDLIFE] sell {units}x {item} -> {getattr(res, 'status', '?')}: {getattr(res, 'message', '')}. Left in Inventory.")


def _retire(now):
    """
    One pass after the Wildlife pillar is complete: withdraws the life-form
    requests (again while any is left), releases every Habitat and empties
    every Feed Maker (`plan.release` / `plan.complete`), undeploys each that
    reports ready, sells their kits, wakes the parked rest and drops all feed
    from Inventory.
    Returns the number of Habitats and Feed Makers still deployed.
    """
    if _own_requests_left():
        logistics_requests.clear_requests(REQUESTER_ID)
        if _own_requests_left():
            log.level("warn").print("[WILDLIFE] life-form requests not withdrawn; retried next pass.")
        else:
            log.print("[WILDLIFE] Life-form requests withdrawn.")
    habitat_ids, _home = _network_habitats()
    maker_ids, _home = _network_habitats(wc.FEED_MAKER_TYPE_ID)
    statuses = archive.get(wc.STATUS_KEY, {}) or {}
    statuses = statuses if isinstance(statuses, dict) else {}
    feed = archive.get(wc.FEED_KEY, {}) or {}
    feed = {m: e for m, e in feed.items() if isinstance(e, dict) and wc.fresh(e, now)} if isinstance(feed, dict) else {}
    release = {hid: _retire_label(statuses.get(hid)) for hid in habitat_ids}
    retired = {"assign": {}, "buy": {}, "feed_demand": {}, "forage_reserve": 0, "form_targets": {}, "fluid_ration": {}, "fluid_supply": {},
               "release": release, "progress": {"waiting": None, "skipped": [], "colonies": 0, "habitats": len(habitat_ids)},
               "alerts": {}, "complete": True, "tick": now}
    if not archive.transaction(wc.PLAN_KEY, {}, lambda _old: retired):
        log.level("warn").print(f"{wc.PLAN_KEY} write rejected; retire plan not published this pass.")
        return len(habitat_ids) + len(maker_ids)
    labels = {hid: ("no colony" if s == wc.RELEASE_NO_COLONY else s) + ", Wildlife complete" for hid, s in release.items()}
    gone = _undeploy_ready(labels, statuses, wc.STATUS_KEY, "release")
    gone += _undeploy_ready({m: "Feed Maker, Wildlife complete" for m in maker_ids}, feed, wc.FEED_KEY, "retire")
    _sell_kits()
    parked = parked_ids("habitat")
    for hid in habitat_ids:
        if hid in parked and hid not in gone:
            wake_for_visit(hid, "Wildlife complete", hold=False)
    if len(gone) < len(habitat_ids) + len(maker_ids):
        wake_kind("feed_maker", "Wildlife complete")
    _drop_feed(SPECIES, "Wildlife complete")
    return len(habitat_ids) + len(maker_ids) - len(gone)


def _retire_pass(now):
    """One _retire() pass; latches state["retired"] once no Habitat or Feed Maker is left."""
    log.start("[WILDLIFE] retire pass", level="debug")
    left = _retire(now)
    if left:
        state["summary"] = f"{COMPLETE_SUMMARY}, retiring {left}"
        log.end(f"{left} left")
        return
    state["retired"] = True
    state["summary"] = COMPLETE_SUMMARY
    log.end("none left")
    log.print("[WILDLIFE] No Habitat or Feed Maker left; planner stops.")


def plan_if_due(clock):
    """Every PLAN_TICK_INTERVAL: one pass. Returns the last summary.

    Once the sensor reads WILDLIFE_COMPLETE_POPULATION it is no longer read
    (populations never decay): each pass retires Habitats and Feed Makers
    instead (_retire), until none is left; then passes stop for the run."""
    now = _now(clock)
    if state["retired"]:
        return state["summary"]
    if state["tick"] and now - state["tick"] < PLAN_TICK_INTERVAL:
        return state["summary"]
    state["tick"] = now
    if not state["complete"]:
        population = _population()
        if not (isinstance(population, (int, float)) and population >= WILDLIFE_COMPLETE_POPULATION):
            return plan(clock)
        state["complete"] = True
        state["alerts"] = None
        log.print(f"[WILDLIFE] Population reached {WILDLIFE_COMPLETE_POPULATION}: Wildlife pillar complete; Habitats and Feed Makers retire.")
    _retire_pass(now)
    return state["summary"]
