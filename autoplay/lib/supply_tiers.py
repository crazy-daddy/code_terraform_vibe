# Which extractor work is urgent, for the infrastructure planner
# (autoplay/infra_planner_automation.py). One rule shared by the extractor,
# fluid and power passes, so a site capped as urgent is also piped and wired
# as urgent, and plan-ahead work stays low priority all the way.
#
# Per fluid F, with consumers = outposts whose roles take F ("in"):
#   - F has consumers and no supply at all (no extractor built or planned on
#     an F site, no outpost whose role is a source of F: condensers and tanks
#     do not count, autoplay_roles.is_source_role()): the nearest F site is
#     urgent ("now").
#   - F has consumers: every F site within NEAR_TILES of a consumer outpost
#     is urgent ("soon").
#   - Anything else is plan-ahead: consumed fluids first, then the rest, by
#     distance to the nearest outpost.
# Built producers follow the same rule: one within NEAR_TILES of a consumer
# is urgent; with none near and no outpost supplying F, the nearest one is.
#
# Plan-ahead work is queued at PLAN_AHEAD_PRIO (Pioneers build it only when
# no normal job is open), one chunk at a time: a pipe route or power link of
# at most `pieces` pieces, only while every item it needs is in stock with
# `reserve` to spare (plan_ahead_limits()). So it never makes the Fabricator
# craft for it and never eats the stock urgent work needs. Both are small
# before the mining-drill phase, when site_supply's construction stock is too.

from swallow import swallowed
from grid_geom import extractor_box, outpost_box, box_closest
from drone_upgrade import upgrade_phase_reached

NEAR_TILES = 25               # a site this many tiles or fewer from a consumer outpost of its fluid is urgent
PLAN_AHEAD_PRIO = 1           # construction.priority of plan-ahead jobs
# (pieces per plan-ahead pipe route or power link chunk, segments left in stock after it)
PLAN_AHEAD_EARLY = (15, 5)    # before the mining-drill phase
PLAN_AHEAD_LATE = (30, 20)    # from the mining-drill phase on

FAR = 1 << 30   # gap() when there is nothing to measure to

TIER_NOW = 0     # consumed fluid with no supply: its nearest site
TIER_SOON = 1    # near a consumer outpost of its fluid (also: drill for a smelter ore without one)
TIER_AHEAD = 2   # consumed fluid, far from its consumers
TIER_SPARE = 3   # fluid no outpost takes

# Site kind -> (structure kind, fluid); exotic sites read their deposit.
_SITE_STRUCTURES = {"water": ("water_pump", "water"), "oil": ("oil_pump", "oil"), "thermal": ("thermal_cap", "steam")}
_EXOTIC_STRUCTURES = {"gas": "exotic_gas_cap", "liquid": "exotic_spring_tap"}
_SITE_MACHINE_GETTERS = {"water": "pump_id", "oil": "pump_id", "thermal": "cap_id", "exotic": "cap_id"}
_YIELD_RATE = {"standard": 1, "rich": 2, "pure": 3}


def plan_ahead_limits():
    """(max pieces, reserve) of a plan-ahead chunk for the current phase."""
    return PLAN_AHEAD_LATE if upgrade_phase_reached() else PLAN_AHEAD_EARLY


def tier_prio(tier):
    """construction.priority for a tier: 0 for urgent tiers, PLAN_AHEAD_PRIO otherwise."""
    return 0 if tier <= TIER_SOON else PLAN_AHEAD_PRIO


def _rate(site, kind):
    """Site output rank in t/h (0 when the survey level does not show it)."""
    if kind in ("water", "oil"):
        value = site.flow_rate()
        if value is None:
            value = _YIELD_RATE.get(site.yield_tier(), 0)
    elif kind == "thermal":
        value = site.base_steam_rate()
    else:
        value = site.base_rate()
    return float(value or 0)


def fluid_sites(sites):
    """
    [{"id", "structure", "fluid", "x", "y", "box", "machine", "rate"}] of every
    surveyed fluid site (water/oil wells, thermal vents, exotic deposits).
    machine = id of the extractor standing on it, "" when untapped.
    """
    rows = []
    for site in sites:
        try:
            kind = site.kind()
            getter = _SITE_MACHINE_GETTERS.get(kind)
            if getter is None:
                continue
            if kind == "exotic":
                structure = _EXOTIC_STRUCTURES.get(site.medium())
                fluid = site.fluid()
            else:
                structure, fluid = _SITE_STRUCTURES[kind]
            if structure is None or fluid is None:
                continue
            x = float(site.x)
            y = float(site.y)
            rows.append({"id": site.id, "structure": structure, "fluid": fluid, "x": x, "y": y,
                         "box": extractor_box(x, y), "machine": getattr(site, getter)() or "", "rate": _rate(site, kind)})
        except Exception as error:
            swallowed("supply_tiers.fluid_sites: site read", error)
    return rows


def consumer_boxes(fluid, demand, outpost_xy):
    """Footprint boxes of the outposts that take `fluid` and do not make it."""
    return [outpost_box(*outpost_xy[oid]) for oid in sorted(demand)
            if oid in outpost_xy and fluid in demand[oid]["in"] and fluid not in demand[oid]["out"]]


def makers(fluid, demand):
    """Outpost ids whose roles are a source of `fluid` (their "supply"; condensers and tanks are not)."""
    return sorted([oid for oid, entry in demand.items() if fluid in entry.get("supply", [])])


def gap(box, boxes):
    """Tiles between `box` and the nearest of `boxes`; FAR when boxes is empty."""
    best = FAR
    for other in boxes:
        dist = box_closest(box, other)[0]
        if dist < best:
            best = dist
    return best


def urgent_producers(rows, demand, outpost_xy):
    """
    Machine ids of built field producers (fluid_sites() rows with a machine)
    whose pipe and power link are urgent; every other built producer is plan-ahead.
    """
    urgent = set()
    by_fluid = {}
    for row in rows:
        if row["machine"]:
            by_fluid.setdefault(row["fluid"], []).append(row)
    for fluid, built in by_fluid.items():
        boxes = consumer_boxes(fluid, demand, outpost_xy)
        if not boxes:
            continue
        ranked = sorted([(gap(row["box"], boxes), row["machine"]) for row in built])
        near = [machine for dist, machine in ranked if dist <= NEAR_TILES]
        if near:
            urgent.update(near)
        elif not makers(fluid, demand):
            urgent.add(ranked[0][1])
    return urgent


def fluid_candidates(rows, demand, outpost_xy, planned_sites, skip=()):
    """
    [(tier, tiles, -rate, site id, row)] of the untapped fluid sites without a
    planned extractor (planned_sites = site ids with a ghost; they count as
    supply) and not in `skip`, best first.
    tiles = distance to the nearest consumer outpost of the fluid, or to the
    nearest outpost for a fluid nobody takes (FAR without outposts).
    """
    all_boxes = [outpost_box(*xy) for _oid, xy in sorted(outpost_xy.items())]
    supplied = {row["fluid"] for row in rows if row["machine"] or row["id"] in planned_sites}
    supplied.update([f for entry in demand.values() for f in entry.get("supply", [])])
    out = []
    now_taken = set()
    open_rows = [row for row in rows if not row["machine"] and row["id"] not in planned_sites and row["id"] not in skip]
    by_fluid = {}
    for row in open_rows:
        by_fluid.setdefault(row["fluid"], []).append(row)
    for fluid in sorted(by_fluid):
        boxes = consumer_boxes(fluid, demand, outpost_xy)
        ranked = sorted([(gap(row["box"], boxes or all_boxes), -row["rate"], row["id"], row) for row in by_fluid[fluid]],
                        key=lambda item: item[:3])
        for dist, neg_rate, site_id, row in ranked:
            if not boxes:
                tier = TIER_SPARE
            elif fluid not in supplied and fluid not in now_taken:
                tier = TIER_NOW
                now_taken.add(fluid)
            elif dist <= NEAR_TILES:
                tier = TIER_SOON
            else:
                tier = TIER_AHEAD
            out.append((tier, dist, neg_rate, site_id, row))
    return sorted(out, key=lambda item: item[:4])
