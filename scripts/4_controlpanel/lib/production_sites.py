# Per-fab-site Fabricator demand: worker split, pipeline, the site plan split,
# targets shared through the demand record, ship-before-craft and the active recipe's
# remaining crafts.
from archive import archive
from components import component
from game_clock import now_tick
from logistics_requests import active_requests, in_flight, outpost_free_tiers
from outpost_mining import HOME_OUTPOST_ID
from priority import NONE, ladder_add, ladder_deficits, ladder_lower, ladder_max, ladder_total, top_deficit
from production_cascade import _cascade_fabricator_output_demand, fabricator_root_targets, fabricator_target_ladders, recipe_for_output, totals
from production_core import _all_outposts, _ceil, _default_fabricator, claim_site_id, craft_seconds, discover_fabricator_ids, discover_smelter_ids, home_outpost_id, log, machine_speed
from production_demand_record import read_record, site_entry
from production_source import SourceCache
from swallow import swallowed

# Ship-before-craft (ship_units()): a site short of an item that sits spare at
# another outpost has it hauled in instead of making it, unless it can make
# it from local stock in under SHIP_OVER_CRAFT_SECONDS real seconds (its own
# crafts plus making its locally missing inputs). Spare of at least
# SHIP_SURPLUS_FACTOR x the shortfall always ships (surplus piles like tar).
SHIP_OVER_CRAFT_SECONDS = 300
SHIP_SURPLUS_FACTOR = 10


def get_fabricator_worker_ids(recipe_id, site_id=None):
    """
    Sorted ids of every discovered Fabricator currently holding recipe_id
    (get_recipe() == recipe_id) right now, only those at `site_id`
    (claim_site_id()) when given -- demand is per fab site
    (get_site_fabricator_targets()), so its split is too. A live roster, not
    an archive-tracked one, so it reflects joiners too (lib/fabricator.py's
    choose_recipe() lets a Fabricator "join" a recipe another one already
    holds the coordination claim on, when no other demanded recipe is
    available -- see its pile-on fallback). Sorted so every worker computes
    the same order, which get_fabricator_active_recipe() uses to hand out
    the split's remainder deterministically.
    """
    ids = []
    for fabricator_id in discover_fabricator_ids():
        candidate = component(fabricator_id)
        if not candidate or not hasattr(candidate, "get_recipe"):
            continue
        try:
            if candidate.get_recipe() != recipe_id:
                continue
            if site_id is not None and claim_site_id(candidate) != site_id:
                continue
            ids.append(fabricator_id)
        except Exception as error:
            swallowed("production_sites.get_fabricator_worker_ids: candidate.get_recipe", error)
    return sorted(ids)


def get_fabricator_worker_count(recipe_id, site_id=None):
    """
    How many discovered Fabricators (at `site_id` when given) currently have
    recipe_id selected -- see get_fabricator_worker_ids(). Used to split
    crafts_remaining fairly (get_fabricator_active_recipe()): without this, every Fabricator working the
    same recipe would each independently load_inputs() for the FULL remaining
    shortfall, overshooting the target well before total_stock() catches up
    on the next poll. Returns at least 1 (the caller itself, even if the
    network walk finds nothing -- e.g. outpost_network unavailable).
    """
    return max(1, len(get_fabricator_worker_ids(recipe_id, site_id)))


def _pipeline_by_site(cache: "SourceCache | None" = None):
    """{site_id: {item_id: units}} finished or being finished inside the
    Fabricators at each site (claim_site_id()) but not yet in storage
    (SourceCache.fabricator_holdings())."""
    pipeline, _staged = (SourceCache() if cache is None else cache).fabricator_holdings()
    return pipeline


def get_fabricator_pipeline(cache: "SourceCache | None" = None, site_id=None):
    """
    {item_id: units} already finished or being finished inside ANY Fabricator
    on the network (only those at `site_id` when given) but not yet in
    storage: every Fabricator's output-buffer stacks, plus one craft's output
    for each craft in progress (is_running()). Netted out of every "still
    needed" figure with the staged inputs, see SourceCache.fab_have().

    Used to be each Fabricator's OWN get_output_count() only. Peers' output
    buffers and every in-progress craft were invisible, so each Fabricator on
    a recipe kept building past the order (seen live: 7 surplus Oil Tank
    (Medium) after vestibule_15). Worst when Inventory is full: finished
    data-bearing items (oil tanks carry oilTons, one slot each) pile up in
    output bins where only their own Fabricator counted them.

    Memoized on `cache` (SourceCache) for the pass, like
    get_fabricator_targets() -- get_material_demands() asks once per
    Fabricator.
    """
    by_site = _pipeline_by_site(cache)
    if site_id is not None:
        return dict(by_site.get(site_id, {}))
    pipeline = {}
    for site_pipeline in by_site.values():
        for item_id, units in site_pipeline.items():
            pipeline[item_id] = pipeline.get(item_id, 0) + units
    return pipeline


# Fab sites (outposts with >= 1 Fabricator) and the per-site plan of which
# sites build each root target's tree -- written by the lib/site_plan.py
# planner, read here by every Fabricator.
# Shape {root_item_id: [site_id, ...]}; a site listed first gets the remainder.
SITE_PLAN_KEY = "fabricator.site_plan"


def fab_site_counts(cache: "SourceCache | None" = None):
    """{site_id: Fabricators there} for every outpost with a Fabricator."""
    if cache is not None and cache._fab_sites is not None:
        return dict(cache._fab_sites)
    counts = {}
    for fabricator_id in discover_fabricator_ids():
        fabricator = component(fabricator_id)
        if fabricator:
            site_id = claim_site_id(fabricator)
            counts[site_id] = counts.get(site_id, 0) + 1
    if cache is not None:
        cache._fab_sites = dict(counts)
    return counts


def split_units(units, site_ids, counts):
    """{site_id: whole units} splitting `units` across site_ids by Fabricator
    count (counts), floor plus remainder in site_ids order; sums to units."""
    weights = [(site_id, max(1, counts.get(site_id, 1))) for site_id in site_ids]
    total = sum(w for _s, w in weights)
    shares = {site_id: units * w // total for site_id, w in weights}
    left = units - sum(shares.values())
    for site_id, _w in weights:
        if left <= 0:
            break
        shares[site_id] += 1
        left -= 1
    return shares


def default_root_sites(consumer_sites, fab_sites):
    """Fallback site list for a root the planner hasn't placed yet: the fab
    site consuming it, else home when it has Fabricators, else the first fab
    site by id."""
    for site_id in sorted(consumer_sites or {}):
        if site_id in fab_sites:
            return [site_id]
    home_id = home_outpost_id()
    if home_id in fab_sites:
        return [home_id]
    return sorted(fab_sites)[:1]


def outpost_by_site_id(site_id):
    """OutpostRef with this id, None when not found."""
    for outpost in _all_outposts():
        if getattr(outpost, "id", None) == site_id:
            return outpost
    return None


def root_remaining(item_id, target, cache: "SourceCache"):
    """Units of a root target (a ladder, or its flat total) still to build
    anywhere: target minus SourceCache.network_have() (stock anywhere on the
    network, cargo aboard haulers, every Fabricator's pipeline and staged
    inputs)."""
    total = ladder_total(target) if isinstance(target, list) else target
    return max(0, total - cache.network_have(item_id))


def root_deficits(item_id, levels, cache: "SourceCache"):
    """[(prio, missing)] of a root ladder still to build anywhere (root_remaining() per level)."""
    return ladder_deficits(levels, cache.network_have(item_id))


def get_site_fabricator_targets(site_id, cache: "SourceCache | None" = None, reuse=True):
    """{item_id: units} of get_site_fabricator_ladders(): the site's flat "keep at least N" targets."""
    return totals(get_site_fabricator_ladders(site_id, cache, reuse))


def get_site_fabricator_ladders(site_id, cache: "SourceCache | None" = None, reuse=True):
    """
    {item_id: ladder} for the Fabricators at one fab site, in the same
    "keep at least N" shape as fabricator_target_ladders(). With Fabricators
    at home only, that is fabricator_target_ladders() itself. Otherwise each
    root target (fabricator_root_targets()) builds at the sites SITE_PLAN_KEY
    lists for it (default_root_sites() until planned): its remaining units
    per level (root_deficits()) split by split_units(), and this site's
    shares become a ladder of SourceCache.fab_have() there + cumulative
    share. Intermediates cascade from those against this site's local stock
    only, so a site's stock counts only for its own trees. Memoized on `cache`.

    Ship-before-craft: an intermediate short at this site that sits spare
    at another outpost is hauled in instead of built when ship_units() says
    so. Units in flight to the site and units to ship come off its target;
    the units to ship are this site's ship plan (get_site_ship_plan(), which
    lib/site_supply.py publishes as requests). Roots are never shipped here.

    Shared across scripts through the demand record (production_demand_record.py):
    with `reuse`, a usable record's (FRESH or STALE) entry for this site is used
    (netted by _net_consumed(), its ship plan taken over) instead of computing.
    No usable record (MISSING), a site the record has no entry for, no clock
    tick and reuse=False compute here. A machine never publishes the record
    (the orchestrator's DemandPublisher does).
    """
    cache = SourceCache() if cache is None else cache
    if site_id in cache._site_targets:
        return _copy(cache._site_targets[site_id])
    now = now_tick()
    if reuse and now:
        plan = archive.get(SITE_PLAN_KEY, {}) or {}
        record, state = read_record(now, plan)
        if record is not None and _site_in_record(record, site_id):
            targets, ship, have = site_entry(record, site_id)
            cache._site_targets[site_id] = _net_consumed(site_id, targets, have, cache)
            cache._site_ship_plan[site_id] = ship
            log.debug(f"site targets({site_id}) from the {state} demand record")
            return _copy(cache._site_targets[site_id])
    return _compute_site_fabricator_targets(site_id, cache)


def _site_in_record(record, site_id):
    sites = record.get("sites")
    return isinstance(sites, dict) and isinstance(sites.get(site_id), dict)


def _copy(ladders):
    return {item_id: [list(level) for level in levels] for item_id, levels in ladders.items()}


def _site_have(item_id, site_id, cache: "SourceCache"):
    """SourceCache.fab_have() at site_id: the count get_fabricator_active_recipe() takes off a target."""
    return cache.fab_have(item_id, outpost_by_site_id(site_id))


def _net_consumed(site_id, targets, have, cache: "SourceCache"):
    """A record's site targets with each item lowered by the units the site had on hand at
    publish time (`have`) and no longer has. A target is "keep at least N" with that stock and
    pipeline inside it, while readers net live stock: a unit consumed since (a finished craft
    sent into a Supply Dock) would otherwise still count as wanted and be crafted again.
    Roots and intermediates alike: an intermediate drained since the record (sent into a dock
    or a parent's stockpile) comes off its ladder until the next record. Staged inputs still
    leave stock while their demand stays, which is why the publisher's `have` is fab_have()
    (held + pipeline + staged), not plain stock. Only lowered: a rise in stock (units hauled in)
    also changes the remaining, which only a recompute sees."""
    targets = _copy(targets)
    for item_id, then in have.items():
        if item_id not in targets:
            continue
        gone = then - _site_have(item_id, site_id, cache)
        if gone > 0:
            targets[item_id] = ladder_lower(targets[item_id], gone)
            log.debug(f"demand record({site_id}): {item_id} {gone} consumed since publish -> target {targets[item_id]}")
            if not targets[item_id]:
                del targets[item_id]
    return targets


def _compute_site_fabricator_targets(site_id, cache: "SourceCache"):
    """get_site_fabricator_targets() computed here, filling cache's site memos."""
    if _single_fab_site(cache):
        targets = fabricator_target_ladders(cache)
        cache._site_targets[site_id] = _copy(targets)
        cache._site_ship_plan[site_id] = {}
        return targets

    log.start(f"get_site_fabricator_targets({site_id})", level="debug")
    seed, fabricator_outputs, outpost = _site_seed(site_id, cache)
    flying = in_flight(site_id)
    ship_plan = {}

    def local(item_id):
        return cache.fab_have(item_id, outpost)

    def supply(item_id, shortfall, prio):
        coming = min(shortfall, flying.get(item_id, 0))
        ship = ship_units(item_id, shortfall - coming, outpost, site_id, cache)
        if ship > 0:
            planned = ship_plan.get(item_id)
            ship_plan[item_id] = [max(planned[0] if planned else 0, ship), max(planned[1] if planned else 0, prio)]
        return coming + ship

    targets = _copy(seed)
    for item_id, levels in _cascade_fabricator_output_demand(seed, fabricator_outputs, cache, stock=local, supply=supply).items():
        targets[item_id] = ladder_max(targets.get(item_id, []), levels)
    cache._site_targets[site_id] = _copy(targets)
    cache._site_ship_plan[site_id] = ship_plan
    if ship_plan:
        log.debug(f"ship plan {ship_plan}")
    log.end()
    return targets


def get_site_ship_plan(site_id, cache: "SourceCache | None" = None):
    """{item_id: [units, prio]} this site should have hauled in rather than
    build (prio = the top shortfall level the units serve) -- see
    get_site_fabricator_ladders(). Computed here, not taken from the shared
    copy: hauls reserved since then must come off at once, or the same units
    are requested twice."""
    cache = SourceCache() if cache is None else cache
    if site_id not in cache._site_ship_plan:
        cache._site_targets.pop(site_id, None)
        get_site_fabricator_ladders(site_id, cache, reuse=False)
    return {i: list(v) for i, v in cache._site_ship_plan.get(site_id, {}).items()}


def _single_fab_site(cache: "SourceCache"):
    """True when every Fabricator is at home (site targets = global targets)."""
    return set(fab_site_counts(cache)) <= {home_outpost_id(), HOME_OUTPOST_ID}


def _site_seed(site_id, cache: "SourceCache"):
    """(seed, fabricator_outputs, outpost): this site's root targets -- each
    root's remaining units, level by level (root_deficits()), split across
    the sites planned for it, as a ladder of local fab_have() + cumulative
    share."""
    fab_sites = fab_site_counts(cache)
    roots, consumers, fabricator_outputs = fabricator_root_targets(cache)
    plan = archive.get(SITE_PLAN_KEY, {}) or {}
    outpost = outpost_by_site_id(site_id)
    seed = {}
    for item_id, levels in roots.items():
        if item_id not in fabricator_outputs:
            continue
        deficits = root_deficits(item_id, levels, cache)
        if not deficits:
            continue
        planned = plan.get(item_id) if isinstance(plan, dict) else None
        sites = [s for s in (planned or []) if s in fab_sites] or default_root_sites(consumers.get(item_id), fab_sites)
        have = cache.fab_have(item_id, outpost)
        shares = []
        for prio, missing in deficits:
            share = split_units(missing, sites, fab_sites).get(site_id, 0)
            if share > 0:
                shares.append((prio, share))
        if shares:
            site_levels = []
            cum = have
            for prio, share in shares:
                cum += share
                site_levels.append([prio, cum])
            seed[item_id] = site_levels
            log.debug(f"root {item_id} remaining={deficits} sites={sites} -> shares={shares}, target={site_levels}")
    return seed, fabricator_outputs, outpost


def _site_base_targets(site_id, cache: "SourceCache"):
    """A site's targets without ship-before-craft (only local stock nets):
    what that site keeps for its own trees when another site asks for its
    spare (site_spare_elsewhere()). Memoized on `cache`."""
    if site_id in cache._site_base_targets:
        return cache._site_base_targets[site_id]
    if _single_fab_site(cache):
        targets = totals(fabricator_target_ladders(cache))
    else:
        seed, fabricator_outputs, outpost = _site_seed(site_id, cache)
        targets = _copy(seed)
        for item_id, levels in _cascade_fabricator_output_demand(seed, fabricator_outputs, cache, stock=lambda i: cache.fab_have(i, outpost)).items():
            targets[item_id] = ladder_max(targets.get(item_id, []), levels)
        targets = totals(targets)
    cache._site_base_targets[site_id] = targets
    return targets


def _site_speed(kind, outpost: "OutpostRef | None", cache: "SourceCache"):
    """machine_speed() of the fastest Fabricator/Smelter (kind) at `outpost`,
    0 when it has none. Memoized on `cache`."""
    key = f"{getattr(outpost, 'id', None)}|{kind}"
    if key not in cache._site_machines:
        ids = discover_fabricator_ids(outpost) if kind == "fabricator" else discover_smelter_ids(outpost)
        cache._site_machines[key] = max([machine_speed(component(i)) for i in ids] or [0])
    return cache._site_machines[key]


def local_make_seconds(item_id, units, outpost: "OutpostRef | None", cache: "SourceCache", depth=0):
    """
    Real seconds to make `units` of item_id at `outpost` from its local
    stock: crafts x craft_seconds() of its Fabricator/Smelter recipe on the
    site's fastest machine of that kind (_site_speed()), rescaled from the
    tier of the machine SourceCache read it from, plus
    making every input the site doesn't hold enough of the same way. None
    when the site can't (no machine of that kind there, or an input that no
    recipe makes -- raw ore -- is missing). Fluid inputs count as available.
    One machine's time: parallel Fabricators are not credited.
    """
    if units <= 0:
        return 0.0
    if depth >= 6:
        return None
    key = f"{getattr(outpost, 'id', None)}|{item_id}"
    if key not in cache._make_recipes:
        # Static per (item, outpost): only `units` varies between calls of one refresh.
        kind, recipe = recipe_for_output(item_id, cache)
        speed = _site_speed(kind, outpost, cache) if recipe is not None else 0
        cache._make_recipes[key] = (
            (
                max(1, getattr(recipe, "output_count", 1) or 1),
                craft_seconds(recipe, speed, cache.recipe_source_speed(kind)),
                tuple((getattr(recipe, "inputs", {}) or {}).items()),
            )
            if speed
            else None
        )
    made = cache._make_recipes[key]
    if made is None:
        return None
    output_count, craft_time, inputs = made
    crafts = _ceil(units / output_count)
    seconds = crafts * craft_time
    for input_id, per_craft in inputs:
        missing = crafts * per_craft - cache.local_stock(input_id, outpost)
        if missing <= 0:
            continue
        sub = local_make_seconds(input_id, missing, outpost, cache, depth + 1)
        if sub is None:
            return None
        seconds += sub
    return seconds


def site_spare_elsewhere(item_id, site_id, cache: "SourceCache"):
    """
    Units of item_id free for site_id at every other outpost: the
    outpost_free_tiers() need tier (storage minus what that outpost's own
    requests keep and other haulers reserved), minus what another fab site
    keeps for its own targets (_site_base_targets()). Memoized on `cache`.
    """
    key = f"{site_id}|{item_id}"
    if key in cache._spare_elsewhere:
        return cache._spare_elsewhere[key]
    if cache._requests is None:
        cache._requests = active_requests()
    fab_sites = fab_site_counts(cache)
    total = 0
    for outpost in _all_outposts():
        other_id = getattr(outpost, "id", None)
        if other_id is None or other_id == site_id:
            continue
        contribution_key = f"{other_id}|{item_id}"
        if contribution_key not in cache._spare_contribution:
            # Nothing held, nothing free: skips outpost_free_tiers() for the outposts that hold none (most pairs).
            if cache.held_stock(item_id, outpost) <= 0:
                cache._spare_contribution[contribution_key] = 0
                continue
            for_need, _for_buffer = outpost_free_tiers(outpost, [item_id], reads=cache.plan_reads())
            free = for_need.get(item_id, 0)
            if free > 0 and other_id in fab_sites:
                keep = min(cache.local_stock(item_id, outpost), _site_base_targets(other_id, cache).get(item_id, 0))
                free -= keep
            cache._spare_contribution[contribution_key] = max(0, int(free))
        total += cache._spare_contribution[contribution_key]
    cache._spare_elsewhere[key] = total
    return total


def ship_units(item_id, shortfall, outpost: "OutpostRef | None", site_id, cache: "SourceCache"):
    """
    Units of a site's shortfall of item_id to haul in instead of making
    them: min(shortfall, spare elsewhere) when spare >= SHIP_SURPLUS_FACTOR
    x shortfall, or when the site can't make it locally
    (local_make_seconds() None) or only in >= SHIP_OVER_CRAFT_SECONDS;
    0 otherwise (make it locally). Delivery time is not estimated.
    """
    log.start(f"ship_units({site_id})", level="debug")
    shortfall = _ceil(shortfall) if shortfall > 0 else 0
    if shortfall <= 0:
        log.end()
        return 0
    spare = site_spare_elsewhere(item_id, site_id, cache)
    if spare <= 0:
        log.debug(f"{item_id} short={shortfall}, nothing spare elsewhere -> make")
        log.end()
        return 0
    ship = min(shortfall, spare)
    if spare >= SHIP_SURPLUS_FACTOR * shortfall:
        log.debug(f"{item_id} short={shortfall} spare={spare} >= {SHIP_SURPLUS_FACTOR}x -> ship {ship} (surplus)")
        log.end()
        return ship
    seconds = local_make_seconds(item_id, shortfall, outpost, cache)
    if seconds is None:
        log.debug(f"{item_id} short={shortfall} spare={spare}, can't make locally -> ship {ship}")
        log.end()
        return ship
    if seconds >= SHIP_OVER_CRAFT_SECONDS:
        log.debug(f"{item_id} short={shortfall} spare={spare}, local make {seconds:.0f}s >= {SHIP_OVER_CRAFT_SECONDS}s -> ship {ship}")
        log.end()
        return ship
    log.debug(f"{item_id} short={shortfall} spare={spare}, local make {seconds:.0f}s < {SHIP_OVER_CRAFT_SECONDS}s -> make")
    log.end()
    return 0


def get_fabricator_active_recipe(fabricator: "Fabricator | None" = None, cache: "SourceCache | None" = None):
    """Returns (recipe, crafts_remaining, prio) for the Fabricator's selected recipe,
    where crafts_remaining covers the full remaining shortfall against its
    site's output target (get_site_fabricator_ladders(), not just one craft's
    worth), net of SourceCache.fab_have() (held stock, the site's Fabricator
    pipeline and the units staged in their stockpiles), divided across every Fabricator at the same
    site currently working this same recipe (see get_fabricator_worker_ids())
    so several Fabricators piled onto one large order split its remaining
    work instead of each independently re-loading the full shortfall. The
    split is floor-plus-remainder: the first (crafts % workers) ids in
    sorted order get one extra craft, so the shares sum to exactly
    crafts_remaining. A worker can get 0 and idles until demand changes.
    `prio` is the highest level of the target still short (priority.NONE
    when nothing is): what the recipe's inputs are wanted at."""
    if fabricator is None:
        fabricator = _default_fabricator()
    if not fabricator or not hasattr(fabricator, "get_recipe") or not hasattr(fabricator, "list_recipes"):
        return None, 0, NONE
    try:
        current_recipe_id = fabricator.get_recipe()
        if not current_recipe_id:
            return None, 0, NONE
        recipe = next((r for r in fabricator.list_recipes() if getattr(r, "id", None) == current_recipe_id), None)
        if not recipe:
            return None, 0, NONE
        cache = SourceCache() if cache is None else cache
        site_id = claim_site_id(fabricator)
        output_item = getattr(recipe, "output_item", None)
        output_count = max(1, getattr(recipe, "output_count", 1))
        current = cache.held_stock(output_item, getattr(fabricator, "outpost", None))
        in_pipeline = get_fabricator_pipeline(cache, site_id).get(output_item, 0)
        staged = cache.staged_units(output_item, site_id)
        fabricator_id = getattr(fabricator, "id", None)
        log.start(f"get_fabricator_active_recipe({fabricator_id or '?'})", level="debug")
        levels = get_site_fabricator_ladders(site_id, cache).get(output_item, [])
        target = ladder_total(levels)
        prio, _missing = top_deficit(levels, current + in_pipeline + staged)
        still_needed = max(0, target - current - in_pipeline - staged)
        crafts_remaining = -(-still_needed // output_count)  # ceil division
        worker_ids = get_fabricator_worker_ids(current_recipe_id, site_id)
        if len(worker_ids) > 1:
            pre_split = crafts_remaining
            if fabricator_id in worker_ids:
                share, extra = divmod(crafts_remaining, len(worker_ids))
                crafts_remaining = share + (1 if worker_ids.index(fabricator_id) < extra else 0)
            else:
                crafts_remaining = -(-crafts_remaining // len(worker_ids))  # id unknown: old ceil split, overshoots at most workers-1
            log.debug(f"recipe={current_recipe_id} split {pre_split} crafts across {len(worker_ids)} workers {worker_ids} -> {crafts_remaining} for this one")
        log.debug(f"site={site_id} recipe={current_recipe_id} output={output_item} target={target} prio={prio} current={current} in_pipeline={in_pipeline} staged={staged} still_needed={still_needed} crafts_remaining={crafts_remaining}")
        log.end()
        return recipe, crafts_remaining, prio
    except Exception as error:
        swallowed("production_sites.get_fabricator_active_recipe: fabricator.get_recipe", error)
        return None, 0, NONE


def fab_site_gross_need(fabricator_ids, smelter_outputs, cache: "SourceCache"):
    """{item_id: ladder} the Fabricators' active recipes still need staged:
    inputs x crafts_remaining (their split share) - stockpile, at the
    recipe's prio (get_fabricator_active_recipe()), for the inputs in
    `smelter_outputs` (every input when None)."""
    need = {}
    for fabricator_id in fabricator_ids:
        fabricator = component(fabricator_id)
        if not fabricator:
            continue
        recipe, crafts_remaining, prio = get_fabricator_active_recipe(fabricator, cache)
        if not recipe or crafts_remaining <= 0:
            continue
        try:
            stockpile = fabricator.get_stockpile() or {}
        except Exception as error:
            swallowed("production_sites.fab_site_gross_need: fabricator.get_stockpile", error)
            stockpile = {}
        for item_id, per_craft in (getattr(recipe, "inputs", {}) or {}).items():
            if smelter_outputs is not None and item_id not in smelter_outputs:
                continue
            missing = per_craft * crafts_remaining - stockpile.get(item_id, 0)
            if missing > 0:
                ladder_add(need.setdefault(item_id, []), prio, missing)
    return need
