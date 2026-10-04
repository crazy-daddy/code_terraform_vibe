# Per-fab-site Fabricator demand: worker split, pipeline, the site plan split,
# targets shared across scripts, ship-before-craft and the active recipe's
# remaining crafts.
from archive import archive
from outpost_mining import HOME_OUTPOST_ID
from logistics_requests import active_requests, in_flight, outpost_free_tiers
from components import component
from swallow import swallowed
from production_core import claim_site_id, craft_seconds, discover_fabricator_ids, discover_smelter_ids, home_outpost_id, log, _all_outposts, _ceil, _current_tick, _default_fabricator
from production_source import SourceCache
from production_cascade import fabricator_root_targets, get_fabricator_targets, _cascade_fabricator_output_demand


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
    Fabricators at each site (claim_site_id()) but not yet in storage."""
    if cache is not None and cache._pipeline_by_site is not None:
        return cache._pipeline_by_site
    by_site = {}
    for fabricator_id in discover_fabricator_ids():
        fabricator = component(fabricator_id)
        if not fabricator:
            continue
        pipeline = by_site.setdefault(claim_site_id(fabricator), {})
        try:
            output = getattr(fabricator, "output", None)
            if output and hasattr(output, "stacks"):
                for stack in output.stacks():
                    stack_item_id = getattr(stack, "id", None)
                    if stack_item_id:
                        pipeline[stack_item_id] = pipeline.get(stack_item_id, 0) + (getattr(stack, "count", 0) or 0)
            if hasattr(fabricator, "is_running") and fabricator.is_running():
                recipe_id = fabricator.get_recipe()
                recipe = fabricator.find_recipe(recipe_id) if recipe_id and hasattr(fabricator, "find_recipe") else None
                output_item = getattr(recipe, "output_item", None) if recipe else None
                if output_item:
                    pipeline[output_item] = pipeline.get(output_item, 0) + max(1, getattr(recipe, "output_count", 1))
        except Exception as error:
            swallowed("production_sites._pipeline_by_site: output.stacks", error)
    log.trace(f"_pipeline_by_site: {by_site}")
    if cache is not None:
        cache._pipeline_by_site = by_site
    return by_site


def get_fabricator_pipeline(cache: "SourceCache | None" = None, site_id=None):
    """
    {item_id: units} already finished or being finished inside ANY Fabricator
    on the network (only those at `site_id` when given) but not yet in
    storage: every Fabricator's output-buffer stacks, plus one craft's output
    for each craft in progress (is_running()). Netted out of every "still
    needed" figure alongside total_stock().

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
# sites build each root target's tree -- written by the 5_steampower lib
# site_plan.py planner, read here by every Fabricator.
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
    """Units of a root target still to build anywhere: target minus stock
    anywhere on the network (cargo aboard haulers included) and every
    Fabricator's pipeline."""
    return max(0, target - cache.network_stock(item_id) - get_fabricator_pipeline(cache).get(item_id, 0))


def get_site_fabricator_targets(site_id, cache: "SourceCache | None" = None, reuse=True):
    """
    {item_id: target} for the Fabricators at one fab site, in the same
    "keep at least N" shape as get_fabricator_targets(). With Fabricators at
    home only, that is get_fabricator_targets() itself. Otherwise each root
    target (fabricator_root_targets()) builds at the sites SITE_PLAN_KEY
    lists for it (default_root_sites() until planned): its remaining units
    (root_remaining()) split by split_units(), and this site's share becomes
    a target of local stock + local pipeline + share. Intermediates cascade
    from those against this site's local stock only, so a site's stock
    counts only for its own trees. Memoized on `cache`.

    Ship-before-craft: an intermediate short at this site that sits spare
    at another outpost is hauled in instead of built when ship_units() says
    so. Units in flight to the site and units to ship come off its target;
    the units to ship are this site's ship plan (get_site_ship_plan(), which
    lib/site_supply.py publishes as requests). Roots are never shipped here.

    Shared across scripts (SITE_TARGETS_KEY): a result computed by any
    Fabricator, Smelter or the panel is reused by the others for
    SITE_TARGETS_FRESH_TICKS; while one script recomputes a stale site
    (lease), the others keep the stale copy up to SITE_TARGETS_MAX_STALE_TICKS.
    reuse=False skips the shared copy (computes here, then shares the result).
    A shared copy computed under a different site plan (SITE_PLAN_KEY) is not used.
    """
    cache = SourceCache() if cache is None else cache
    if site_id in cache._site_targets:
        return dict(cache._site_targets[site_id])
    now = _current_tick()
    plan = archive.get(SITE_PLAN_KEY, {}) or {}
    shared = _shared_site_targets(site_id, now, plan) if reuse else None
    if shared is None and now and reuse:
        shared = _lease_site_targets(site_id, now, plan)
    if shared is not None:
        cache._site_targets[site_id] = dict(shared.get("targets") or {})
        cache._site_ship_plan[site_id] = dict(shared.get("ship") or {})
        return dict(cache._site_targets[site_id])
    targets = _compute_site_fabricator_targets(site_id, cache)
    if now:
        _publish_site_targets(site_id, now, plan, targets, cache._site_ship_plan.get(site_id, {}))
    return targets


# Site targets shared across scripts: {site_id: {"tick": computed at, "plan": SITE_PLAN_KEY then,
# "targets": {...}, "ship": {...}, "lease": tick a script started recomputing}}.
SITE_TARGETS_KEY = "production.site_targets"
# A shared result younger than this is used as is.
SITE_TARGETS_FRESH_TICKS = 150
# A lease older than this is taken over (its script died or is slow).
SITE_TARGETS_LEASE_TICKS = 300
# While another script holds the lease, a stale result up to this age is used instead of
# computing it a second time.
SITE_TARGETS_MAX_STALE_TICKS = 600
# Entries not refreshed for this long are dropped on the next write.
SITE_TARGETS_PRUNE_TICKS = 6000


def _site_targets_entry(site_id):
    shared = archive.get(SITE_TARGETS_KEY, {}) or {}
    entry = shared.get(site_id) if isinstance(shared, dict) else None
    return entry if isinstance(entry, dict) else None


def _usable(entry, plan):
    return isinstance(entry, dict) and "targets" in entry and entry.get("plan", {}) == plan


def _shared_site_targets(site_id, now, plan):
    """The shared entry for site_id when fresh, or stale while another script recomputes it; else None.
    Only an entry computed under the same site plan counts."""
    entry = _site_targets_entry(site_id)
    if entry is None or not _usable(entry, plan):
        return None
    age = now - entry.get("tick", 0)
    if age <= SITE_TARGETS_FRESH_TICKS:
        return entry
    lease = entry.get("lease")
    if lease is not None and now - lease <= SITE_TARGETS_LEASE_TICKS and age <= SITE_TARGETS_MAX_STALE_TICKS:
        return entry
    return None


def _lease_site_targets(site_id, now, plan):
    """Takes the recompute lease for site_id. Returns the entry to use instead when another
    script took it first (a stale result inside SITE_TARGETS_MAX_STALE_TICKS), else None."""
    lost = []

    def updater(shared):
        shared = shared if isinstance(shared, dict) else {}
        current = shared.get(site_id)
        entry = dict(current) if isinstance(current, dict) else {}
        lease = entry.get("lease")
        if lease is not None and now - lease <= SITE_TARGETS_LEASE_TICKS and lease != now:
            lost.append(entry)
            return shared
        entry["lease"] = now
        shared[site_id] = entry
        return shared

    try:
        archive.transaction(SITE_TARGETS_KEY, {}, updater)
    except Exception as error:
        swallowed("production_sites._lease_site_targets: archive.transaction", error)
        return None
    if lost and _usable(lost[0], plan) and now - lost[0].get("tick", 0) <= SITE_TARGETS_MAX_STALE_TICKS:
        return lost[0]
    return None


def _publish_site_targets(site_id, started, plan, targets, ship_plan):
    """Stores a computed result for the other scripts, stamped with the tick its computation
    started, releases the lease and drops entries not refreshed in SITE_TARGETS_PRUNE_TICKS."""
    entry = {"tick": started, "plan": plan, "targets": dict(targets), "ship": dict(ship_plan or {})}

    def updater(shared):
        shared = shared if isinstance(shared, dict) else {}
        shared = {key: value for key, value in shared.items()
                  if isinstance(value, dict) and started - value.get("tick", value.get("lease", started)) <= SITE_TARGETS_PRUNE_TICKS}
        current = shared.get(site_id)
        if isinstance(current, dict) and current.get("tick", 0) > started and "targets" in current:
            return shared
        shared[site_id] = entry
        return shared

    try:
        archive.transaction(SITE_TARGETS_KEY, {}, updater)
    except Exception as error:
        swallowed("production_sites._publish_site_targets: archive.transaction", error)


def _compute_site_fabricator_targets(site_id, cache: "SourceCache"):
    """get_site_fabricator_targets() computed here, filling cache's site memos."""
    if _single_fab_site(cache):
        targets = get_fabricator_targets(cache)
        cache._site_targets[site_id] = dict(targets)
        cache._site_ship_plan[site_id] = {}
        return targets

    log.start(f"get_site_fabricator_targets({site_id})", level="debug")
    seed, fabricator_outputs, outpost = _site_seed(site_id, cache)
    flying = in_flight(site_id)
    ship_plan = {}

    def local(item_id):
        return cache.held_stock(item_id, outpost)

    def supply(item_id, shortfall):
        coming = min(shortfall, flying.get(item_id, 0))
        ship = ship_units(item_id, shortfall - coming, outpost, site_id, cache)
        if ship > 0:
            ship_plan[item_id] = max(ship_plan.get(item_id, 0), ship)
        return coming + ship

    targets = dict(seed)
    for item_id, count in _cascade_fabricator_output_demand(seed, fabricator_outputs, cache, stock=local, supply=supply).items():
        targets[item_id] = max(targets.get(item_id, 0), count)
    cache._site_targets[site_id] = dict(targets)
    cache._site_ship_plan[site_id] = ship_plan
    if ship_plan:
        log.debug(f"ship plan {ship_plan}")
    log.end()
    return targets


def get_site_ship_plan(site_id, cache: "SourceCache | None" = None):
    """{item_id: units} this site should have hauled in rather than build --
    see get_site_fabricator_targets(). Computed here, not taken from the
    shared copy: hauls reserved since then must come off at once, or the
    same units are requested twice."""
    cache = SourceCache() if cache is None else cache
    if site_id not in cache._site_ship_plan:
        cache._site_targets.pop(site_id, None)
        get_site_fabricator_targets(site_id, cache, reuse=False)
    return dict(cache._site_ship_plan.get(site_id, {}))


def _single_fab_site(cache: "SourceCache"):
    """True when every Fabricator is at home (site targets = global targets)."""
    return set(fab_site_counts(cache)) <= {home_outpost_id(), HOME_OUTPOST_ID}


def _site_seed(site_id, cache: "SourceCache"):
    """(seed, fabricator_outputs, outpost): this site's root targets -- each
    root's remaining units split across the sites planned for it, as local
    stock + local pipeline + share."""
    fab_sites = fab_site_counts(cache)
    roots, consumers, fabricator_outputs = fabricator_root_targets(cache)
    plan = archive.get(SITE_PLAN_KEY, {}) or {}
    outpost = outpost_by_site_id(site_id)
    pipeline = get_fabricator_pipeline(cache, site_id)
    seed = {}
    for item_id, target in roots.items():
        if item_id not in fabricator_outputs:
            continue
        remaining = root_remaining(item_id, target, cache)
        if remaining <= 0:
            continue
        planned = plan.get(item_id) if isinstance(plan, dict) else None
        sites = [s for s in (planned or []) if s in fab_sites] or default_root_sites(consumers.get(item_id), fab_sites)
        share = split_units(remaining, sites, fab_sites).get(site_id, 0)
        if share > 0:
            seed[item_id] = cache.held_stock(item_id, outpost) + pipeline.get(item_id, 0) + share
            log.debug(f"root {item_id} remaining={remaining} sites={sites} -> share={share}, target={seed[item_id]}")
    return seed, fabricator_outputs, outpost


def _site_base_targets(site_id, cache: "SourceCache"):
    """A site's targets without ship-before-craft (only local stock nets):
    what that site keeps for its own trees when another site asks for its
    spare (site_spare_elsewhere()). Memoized on `cache`."""
    if site_id in cache._site_base_targets:
        return cache._site_base_targets[site_id]
    if _single_fab_site(cache):
        targets = get_fabricator_targets(cache)
    else:
        seed, fabricator_outputs, outpost = _site_seed(site_id, cache)
        targets = dict(seed)
        for item_id, count in _cascade_fabricator_output_demand(seed, fabricator_outputs, cache, stock=lambda i: cache.held_stock(i, outpost)).items():
            targets[item_id] = max(targets.get(item_id, 0), count)
    cache._site_base_targets[site_id] = targets
    return targets


def _recipe_for_output(item_id, cache: "SourceCache"):
    """("fabricator"|"smelter", Recipe) building item_id, (None, None) when none does."""
    for kind, recipes in (("fabricator", cache.fabricator_recipes()), ("smelter", cache.smelter_recipes())):
        for recipe in recipes:
            if getattr(recipe, "output_item", None) == item_id:
                return kind, recipe
    return None, None


def _site_has_machine(kind, outpost: "OutpostRef | None", cache: "SourceCache"):
    """True when `outpost` has at least one Fabricator/Smelter (kind). Memoized on `cache`."""
    key = f"{getattr(outpost, 'id', None)}|{kind}"
    if key not in cache._site_machines:
        ids = discover_fabricator_ids(outpost) if kind == "fabricator" else discover_smelter_ids(outpost)
        cache._site_machines[key] = bool(ids)
    return cache._site_machines[key]


def local_make_seconds(item_id, units, outpost: "OutpostRef | None", cache: "SourceCache", depth=0):
    """
    Real seconds to make `units` of item_id at `outpost` from its local
    stock: crafts x craft_seconds() of its Fabricator/Smelter recipe, plus
    making every input the site doesn't hold enough of the same way. None
    when the site can't (no machine of that kind there, or an input that no
    recipe makes -- raw ore -- is missing). Fluid inputs count as available.
    One machine's time: parallel Fabricators are not credited.
    """
    if units <= 0:
        return 0.0
    if depth >= 6:
        return None
    kind, recipe = _recipe_for_output(item_id, cache)
    if recipe is None or not _site_has_machine(kind, outpost, cache):
        return None
    crafts = _ceil(units / max(1, getattr(recipe, "output_count", 1) or 1))
    seconds = crafts * craft_seconds(recipe)
    for input_id, per_craft in (getattr(recipe, "inputs", {}) or {}).items():
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
            for_need, _for_buffer = outpost_free_tiers(outpost, [item_id], cache._requests)
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
    """Returns (recipe, crafts_remaining) for the Fabricator's selected recipe,
    where crafts_remaining covers the full remaining shortfall against its
    site's output target (get_site_fabricator_targets(), not just one craft's
    worth), net of the site's local stock and its Fabricators' pipeline
    (get_fabricator_pipeline()), divided across every Fabricator at the same
    site currently working this same recipe (see get_fabricator_worker_ids())
    so several Fabricators piled onto one large order split its remaining
    work instead of each independently re-loading the full shortfall. The
    split is floor-plus-remainder: the first (crafts % workers) ids in
    sorted order get one extra craft, so the shares sum to exactly
    crafts_remaining. A worker can get 0 and idles until demand changes."""
    if fabricator is None:
        fabricator = _default_fabricator()
    if not fabricator or not hasattr(fabricator, "get_recipe") or not hasattr(fabricator, "list_recipes"):
        return None, 0
    try:
        current_recipe_id = fabricator.get_recipe()
        if not current_recipe_id:
            return None, 0
        recipe = next((r for r in fabricator.list_recipes() if getattr(r, "id", None) == current_recipe_id), None)
        if not recipe:
            return None, 0
        cache = SourceCache() if cache is None else cache
        site_id = claim_site_id(fabricator)
        output_item = getattr(recipe, "output_item", None)
        output_count = max(1, getattr(recipe, "output_count", 1))
        current = cache.held_stock(output_item, getattr(fabricator, "outpost", None))
        in_pipeline = get_fabricator_pipeline(cache, site_id).get(output_item, 0)
        fabricator_id = getattr(fabricator, "id", None)
        log.start(f"get_fabricator_active_recipe({fabricator_id or '?'})", level="debug")
        target = get_site_fabricator_targets(site_id, cache).get(output_item, 0)
        still_needed = max(0, target - current - in_pipeline)
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
        log.debug(f"site={site_id} recipe={current_recipe_id} output={output_item} target={target} current={current} in_pipeline={in_pipeline} still_needed={still_needed} crafts_remaining={crafts_remaining}")
        log.end()
        return recipe, crafts_remaining
    except Exception as error:
        swallowed("production_sites.get_fabricator_active_recipe: fabricator.get_recipe", error)
        return None, 0


def fab_site_gross_need(fabricator_ids, smelter_outputs, cache: "SourceCache"):
    """{item_id: units} the Fabricators' active recipes still need staged:
    inputs x crafts_remaining (their split share) - stockpile, for the
    inputs in `smelter_outputs` (every input when None)."""
    need = {}
    for fabricator_id in fabricator_ids:
        fabricator = component(fabricator_id)
        if not fabricator:
            continue
        recipe, crafts_remaining = get_fabricator_active_recipe(fabricator, cache)
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
                need[item_id] = need.get(item_id, 0) + missing
    return need
