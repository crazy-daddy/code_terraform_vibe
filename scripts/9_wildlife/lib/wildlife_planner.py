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
#   2. build_plan(snapshot): pure, called directly. Its cost grows with
#      Habitats and statuses past the 10,000-step cap of one atomic callback
#      (lib/atomic.py), and an hourly pass needs no single-tick speed.
#      Walks the offline revival schedule (wildlife_model.schedule_for(live
#      Habitat count)) the way the optimizer does: steps run strictly in
#      order; a step that can never run (species already revived, node
#      bought, not cataloged, recipe locked, no Habitat left) is skipped;
#      the first step that can run later (Insight short, Breakthrough
#      source below 10,000) stops the walk, holding Insight.
#      Then, as two atomic calls (each bounded by the Habitat count): each
#      colony's hours to its ceiling at the full-support model rate, and the
#      fluid ration (per fluid, slowest colonies first within the tank
#      budget). Then feed demand per feed item (priority classes in
#      wildlife_common, fluid-holding colonies first), the Forage reserve for
#      the Plant Terraformer, life-form targets, the Habitats to wake and the
#      operator alerts.
#   3. Writes `wildlife.plan` / `wildlife.readiness`, the life-form requests
#      at home (requester REQUESTER_ID), wakes, notify() on alert changes.
#      Returns a one-line summary for the AUTOMATION card.
#
# Parking of finished colonies (undeploy at the Mk I ceiling, rehouse) is not
# done: with no free Habitat a revive step can never run and is skipped.

from archive import archive
from swallow import swallowed
from tree_console import TreeConsole
import logistics_requests
from script_parking import wake_for_visit, wake_kind, parked_ids
from wildlife_data import SPECIES, WILDLIFE_BOOTSTRAP, BONUS_TREES, ADAPTATION_COST, BREAKTHROUGH_COST, BREAKTHROUGH_POPULATION, REVIVE_FEED_REQUIRED, STAGE_CAPACITY, HABITAT_MK2_CAPACITY_FACTOR, FEED_PER_CRAFT, GAS_PER_BIRTH_T, LIQUID_PER_BIRTH_T, BUFFER_BLEED_T_PER_H
from wildlife_model import schedule_for, breeding_rate, breakthrough_effects, adaptation_effects
from atomic import run_atomic, run_batched
import fluid_routing
import wildlife_common as wc

PLAN_TICK_INTERVAL = 250            # one game hour
REQUESTER_ID = "feed_maker"         # life-form requests at home (logistics.requests)
REQUEST_REFRESH_TICKS = 1200        # republish at least this often (REQUEST_STALE_TICKS = 6000)
IDLE_SUMMARY = "wildlife idle"
MODEL_CHUNK = 4                     # colonies per atomic model slice (worst case ~2,300 steps, devtools/step_profile.py wildlife_ration)

log = TreeConsole(module="wildlife_planner")

# Module state between passes (the Control Room Automation imports this once).
state = {"tick": 0, "summary": IDLE_SUMMARY, "alerts": None, "readiness": None, "requests": None, "request_tick": 0, "progress": None}


# ---------------------------------------------------------------- pure core

def _purchased(statuses):
    """{species: {"adaptation": bool, "breakthrough": bool}} and the set of bought node ids."""
    by_species = {}
    nodes = set()
    for entry in statuses.values():
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


def _walk(snap, colonies, free, assign, bought, insight):
    """
    Runs the schedule queue. Returns (assign, buy, skipped, waiting) where
    buy = {habitat_id: slot} and waiting = (step, reason) of the first held
    step, or None.

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
            if s in colonies:
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
    reaches the target.
    """
    stock = snap["feed_stock"]
    rows = []
    use = {}
    for species, hid in colonies.items():
        entry = statuses.get(hid) or {}
        item = wc.feed_item_of(species)
        bin_level = float(entry.get("feed_level") or 0.0)
        if entry.get("established"):
            # breeding_rate() reads 0 while the colony is blocked, an empty
            # feed bin included; the model rate keeps a starved colony's feed
            # in demand (a colony at its ceiling models 0).
            rate = float(entry.get("rate") or 0.0) or (model.get(hid) or (0.0, 0.0))[1]
            per_h = wc.feed_per_hour(species, rate, nodes)
            use[species] = per_h
            target = wc.FEED_BUFFER_H * per_h
            if per_h > 0:
                target = max(target, FEED_PER_CRAFT)
            bin_short = max(0.0, wc.FEED_TOPUP_TARGET - bin_level) if per_h > 0 else 0.0
            prio = wc.PRIO_FLUID_HELD if _holds_fluid(entry) else wc.PRIO_GROWING
            rows.append((item, target + bin_short, prio, (model.get(hid) or (0.0, 0.0))[0]))
        elif entry.get("rearing"):
            # Established within 12 h: have the bin's first top-up ready.
            rows.append((item, max(0.0, wc.FEED_TOPUP_TARGET - bin_level), wc.PRIO_REARING, 0.0))
        else:
            rows.append((item, max(0.0, REVIVE_FEED_REQUIRED + wc.REARING_FEED_EXTRA - bin_level), wc.PRIO_RESERVE, 0.0))
    ranked_prios = (wc.PRIO_FLUID_HELD, wc.PRIO_GROWING)
    ranked = sorted((r for r in rows if r[2] in ranked_prios), key=lambda r: -r[3])
    rank = {r[0]: i for i, r in enumerate(ranked)}
    demand = {}
    for item, units, prio, _hours in rows:
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


def _wakes_and_alerts(snap, statuses, assign, buy, ration):
    """([habitat ids to wake, with reason], {"no_feed": [...], "capped": [...], "rationed": [...]}).

    Only the source species' Habitat can buy its nodes, so a parked one with a
    queued purchase is woken whatever it is parked for.

    "rationed" lists every Habitat denied a fluid this pass, parked or not."""
    wakes = []
    alerts = {wc.PARK_NO_FEED: [], wc.PARK_CAPPED: [], wc.PARK_RATIONED: sorted(ration)}
    parked = snap["parked"]
    for hid in snap["habitat_ids"]:
        entry = statuses.get(hid) or {}
        reason = entry.get("parked") or ""
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


def build_plan(snap):
    """Pure: the whole plan from one snapshot (no game calls, no logging)."""
    statuses = snap["statuses"]
    bought, nodes = _purchased(statuses)
    colonies, assign, free = _colonies(snap["habitat_ids"], statuses, snap["prev_assign"])
    assign, buy, skipped, waiting = _walk(snap, colonies, free, assign, bought, snap["insight"])
    model = _colony_model(colonies, statuses, nodes)
    ration, supply = run_atomic(_ration_pass, colonies, statuses, model, snap["fluid_stock"],
                                snap["prev_supply"], snap["prev_ration"], snap["tick"])
    demand, use = _feed_demand(snap, colonies, statuses, nodes, model)
    forage = sum(wc.forage_for(v[2]) for v in demand.values())
    if forage:
        forage += wc.forage_for(FEED_PER_CRAFT)
    wakes, alerts = _wakes_and_alerts(snap, statuses, assign, buy, ration)
    missing_creatures = sorted(s for s in SPECIES if s not in snap["cataloged"])
    missing_recipes = sorted(s for s in SPECIES if snap["recipes"] and wc.recipe_of(s) not in snap["recipes"])
    return {
        "assign": assign,
        "buy": buy,
        "feed_demand": demand,
        "forage_reserve": forage,
        "form_targets": _form_targets(snap, colonies, use, demand),
        "fluid_ration": ration,
        "fluid_supply": supply,
        "progress": {
            "waiting": [list(waiting[0]), waiting[1]] if waiting else None,
            "skipped": [[list(step), reason] for step, reason in skipped],
            "colonies": len(colonies),
            "habitats": len(snap["habitat_ids"]),
        },
        "alerts": alerts,
        "wakes": wakes,
        "readiness": {"missing_creatures": missing_creatures, "missing_recipes": missing_recipes},
        "tick": snap["tick"],
    }


def summary_line(plan):
    """One AUTOMATION card item, or IDLE_SUMMARY when nothing needs the operator."""
    parts = []
    alerts = plan.get("alerts") or {}
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


def _network_habitats():
    """(sorted habitat ids on the network, home OutpostRef or None)."""
    ids = []
    home = None
    network = get_component("outpost_network")
    if not network or not hasattr(network, "outposts"):
        return ids, home
    try:
        for outpost in network.outposts():
            if getattr(outpost, "is_home", False):
                home = outpost
            for ref in outpost.buildings("habitat"):
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


def _inventory_count(item_id):
    inventory = get_component("inventory")
    try:
        return int(inventory.count(item_id)) if inventory else 0
    except Exception as error:
        swallowed("wildlife_planner._inventory_count: inventory.count", error)
        return 0


def _fluid_stock(statuses):
    """{fluid: tons in every tank eligible for it}, for each fluid a Habitat band (or pre-fill) needs."""
    wanted = {}
    for entry in statuses.values():
        for medium in wc.TANK_TYPE_IDS:
            row = entry.get(medium)
            if isinstance(row, list) and len(row) > wc.MEDIUM_REQUIRED and row[wc.MEDIUM_REQUIRED]:
                wanted[row[wc.MEDIUM_REQUIRED]] = medium
    out = {}
    for fluid, medium in wanted.items():
        total = 0.0
        for tank, _outpost_id in fluid_routing.discover_network_buildings(wc.TANK_TYPE_IDS[medium], fluid_id=fluid):
            try:
                total += float(tank.level() or 0.0)
            except Exception as error:
                swallowed("wildlife_planner._fluid_stock: tank.level", error)
        out[fluid] = total
    return out


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
    return {
        "tick": now,
        "habitat_ids": habitat_ids,
        "statuses": statuses,
        "parked": set(parked_ids("habitat")),
        "cataloged": _cataloged(),
        "recipes": recipes,
        "recipe_inputs": recipe_inputs,
        "insight": _insight(statuses, now),
        "schedule": schedule_for(len(habitat_ids)),
        "targets": list(targets) if isinstance(targets, list) else [],
        "prev_assign": plan.get("assign") or {},
        "prev_ration": plan.get("fluid_ration") or {},
        "prev_supply": plan.get("fluid_supply") or {},
        "fluid_stock": _fluid_stock(statuses),
        "feed_stock": {i: stock.get(i, 0) for i in feed_items},
        "form_stock": {f: stock.get(f, 0) for f in forms},
        "populations": populations,
        "mk2_packs": _inventory_count(wc.MK2_PACK_ITEM_ID),
        "home": home,
    }


def _publish_requests(snap: dict, plan: dict, now):
    """Life-form requests at home for the Feed Makers, skipping forms another requester owns there."""
    home = snap.get("home")
    home_id = getattr(home, "id", None)
    if not home_id:
        return
    requests = logistics_requests.active_requests(now) or {}
    owners = {}
    owned = requests.get(home_id) or {}
    for item, entry in owned.items():
        if isinstance(entry, dict):
            owners[item] = entry.get("by")
    form_stock = snap.get("form_stock") or {}
    wants = {}
    for form, target in plan["form_targets"].items():
        if owners.get(form) not in (None, REQUESTER_ID):
            continue
        wants[form] = (target, form_stock.get(form, 0))
    targets = {f: w[0] for f, w in wants.items()}
    if targets == state["requests"] and now - state["request_tick"] < REQUEST_REFRESH_TICKS:
        return
    state["requests"] = targets
    state["request_tick"] = now
    if wants:
        logistics_requests.set_requests(home_id, REQUESTER_ID, wants, now)
    else:
        logistics_requests.clear_requests(REQUESTER_ID, home_id)
    short = sorted(f for f, w in wants.items() if w[1] < w[0])
    log.debug(f"life-form requests: {len(wants)} form(s), {len(short)} below target: {short}")


def _write(plan):
    stored = {k: plan[k] for k in ("assign", "buy", "feed_demand", "forage_reserve", "form_targets", "fluid_ration", "fluid_supply", "progress", "alerts", "tick")}

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
    for hid, reason in result["wakes"]:
        wake_for_visit(hid, reason, hold=False)
    if result["feed_demand"]:
        wake_kind("feed_maker", "feed demand")
    state["summary"] = summary_line(result)
    log.end(f"{len(result['assign'])} assigned, {len(result['buy'])} purchase(s), {len(result['feed_demand'])} feed item(s) short")
    return state["summary"]


def plan_if_due(clock):
    """Every PLAN_TICK_INTERVAL: one pass. Returns the last summary."""
    now = _now(clock)
    if state["tick"] and now - state["tick"] < PLAN_TICK_INTERVAL:
        return state["summary"]
    state["tick"] = now
    return plan(clock)
