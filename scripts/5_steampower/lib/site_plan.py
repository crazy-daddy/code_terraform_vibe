# Fab site plan for factory outposts: which fab sites (outposts with >= 1
# Fabricator) build each root Fabricator target's whole tree. Written to
# production.SITE_PLAN_KEY ({root_item: [site_id, ...]}), read by every
# Fabricator through production.get_site_fabricator_targets(), which splits
# the root's remaining units across the listed sites by Fabricator count
# (production.split_units(), the first site listed gets the remainder).
# Run once per storage tick by the headless automation_panel.py, before
# lib/site_supply.py publishes the site requests.
#
# Placement of a root not yet planned:
#   - Sites: min(fab sites, max(1, remaining // SPLIT_UNITS_PER_SITE)), so a
#     small root builds at one site and a large one splits by whole units.
#   - Order: the fab site consuming most of it (its Supply Dock's outpost,
#     home for the rest), then the least loaded site (planned roots per
#     Fabricator), home, then site id.
# A placed root keeps its sites while it has units left (dead sites are
# dropped, the root is replanned once none is left) and its entry is removed
# once built. With Fabricators at home only, the plan is cleared: every
# Fabricator then works the global targets.

from archive import archive
from production import SourceCache, SITE_PLAN_KEY, fab_site_counts, fabricator_root_targets, root_remaining, home_outpost_id
from outpost_mining import HOME_OUTPOST_ID
from tree_console import TreeConsole

log = TreeConsole(module="site_plan")

# Remaining units per extra fab site a root is split across.
SPLIT_UNITS_PER_SITE = 20


def _site_order(consumer_sites, fab_sites, load, home_id):
    """Fab site ids in placement preference order -- see the module comment."""
    def key(site_id):
        consumes = -(consumer_sites or {}).get(site_id, 0)
        per_fabricator = load.get(site_id, 0) / max(1, fab_sites.get(site_id, 1))
        return (consumes, per_fabricator, 0 if site_id == home_id else 1, site_id)
    return sorted(fab_sites, key=key)


def plan_sites(cache=None):
    """Updates SITE_PLAN_KEY (written only on change); returns the plan."""
    cache = SourceCache() if cache is None else cache
    home_id = home_outpost_id()
    fab_sites = fab_site_counts(cache)
    stored = archive.get(SITE_PLAN_KEY, {})
    stored = stored if isinstance(stored, dict) else {}
    if set(fab_sites) <= {home_id, HOME_OUTPOST_ID}:
        if stored:
            archive.set(SITE_PLAN_KEY, {})
            log.print("Fab site plan cleared (Fabricators at home only).")
        return {}

    roots, consumers, fabricator_outputs = fabricator_root_targets(cache)
    remaining = {}
    for item_id, target in roots.items():
        if item_id in fabricator_outputs:
            units = root_remaining(item_id, target, cache)
            if units > 0:
                remaining[item_id] = units

    plan = {}
    load = {}
    for item_id in sorted(remaining):
        sites = [s for s in (stored.get(item_id) or []) if s in fab_sites]
        if sites:
            plan[item_id] = sites
            for site_id in sites:
                load[site_id] = load.get(site_id, 0) + 1
    for item_id, units in sorted(remaining.items(), key=lambda pair: (-pair[1], pair[0])):
        if item_id in plan:
            continue
        count = min(len(fab_sites), max(1, units // SPLIT_UNITS_PER_SITE))
        sites = _site_order(consumers.get(item_id), fab_sites, load, home_id)[:count]
        plan[item_id] = sites
        for site_id in sites:
            load[site_id] = load.get(site_id, 0) + 1
        log.debug(f"plan_sites: {item_id} remaining={units} consumers={sorted(consumers.get(item_id) or {})} -> {sites}")

    if plan != stored:
        archive.set(SITE_PLAN_KEY, plan)
        placed = sorted(set(plan) - set(stored))
        if placed:
            described = ", ".join(item_id + " at " + "/".join(plan[item_id]) for item_id in placed)
            log.print(f"Fab site plan: {described}.")
    return plan
