# Extractor pass of the infrastructure planner (autoplay/infra_planner_automation.py):
# places extractors on surveyed sites, most needed first.
#
# Fluid sites (water/oil wells, thermal vents, exotic deposits) are ranked by
# supply_tiers: a fluid an outpost takes with no supply yet gets its nearest
# site first ("now"), then sites near a consumer outpost of their fluid
# ("soon"), then plan-ahead sites (consumed fluids far away, then fluids no
# outpost takes), each by distance and then by output.
#
# Mining drills need no pipes. One drill per ore the Smelters use is enough:
# for each ore some outpost's Smelter has a recipe for and no drill stands on
# (or is planned for), the site of that ore nearest a Smelter outpost gets
# the lightest drill that cuts its hardness (a kind with a kit in stock
# first). Drills rank with "soon".
#
# Pacing (supply_tiers header): at most MAX_OPEN_URGENT urgent extractor jobs
# of ours open at once; a plan-ahead extractor only when the power and fluid
# passes are idle, none of our extractor jobs is open and its kit
# (construction_plan.EXTRACTOR_KITS) is in stock at the Constructor's home.
# The kits get there through site_supply's construction stock (one per
# untapped site, Fabricator idle time). One extractor per pass. Pipes and power lines follow in the fluid and power
# passes once the extractor is built.

from swallow import swallowed
from grid_geom import tile_at, manhattan, outpost_box, extractor_box
from infra_topology import EXTRACTOR_KINDS, outpost_positions, home_outpost_id, surveyed_sites
from blueprint_queue import stock, queue_structure, job_need, open_planned, cancel
from construction_plan import EXTRACTOR_KITS
from production import smelter_ores
import autoplay_roles
import supply_tiers
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_console import TreeConsole

MAX_OPEN_URGENT = 2       # urgent extractor jobs of ours open at once
MAX_TRIES_PER_PASS = 5    # sites tried per pass when the game rejects one
MATCH_TILES = 1           # a drill or ghost this many tiles or fewer from a site stands on it

# Drill kinds, lightest first: (kind, hardest deposit it cuts, kit item) (docs/database/equipment_mining.md).
DRILL_KINDS = tuple((kind, cuts, EXTRACTOR_KITS[kind]) for kind, cuts in
                    (("mining_drill", 1), ("mining_drill_industrial", 3), ("mining_drill_heavy", 4)))
DRILL_KIND_NAMES = tuple(kind for kind, _hard, _kit in DRILL_KINDS)

# plan_structure() rejections that rule out the site (not the kind) for this run.
_SITE_REJECTIONS = ("target_claimed", "occupied", "clearance", "too_hard", "wrong_target", "unsurveyed_target", "out_of_bounds", "blocked")


def mining_sites(sites):
    """[{"id", "item", "hardness", "purity", "x", "y", "drill"}] of every surveyed mineral site ("drill": drill_id(), "" when none)."""
    rows = []
    for site in sites:
        try:
            if site.kind() != "mineral" or not site.item_id:
                continue
            rows.append({"id": site.id, "item": site.item_id, "hardness": site.hardness, "purity": site.purity,
                         "x": float(site.x), "y": float(site.y), "drill": site.drill_id()})
        except Exception as error:
            swallowed("extractor_plan.mining_sites: site read", error)
    return rows


def site_at(rows, x, y):
    """Id of the site in rows within MATCH_TILES of (x, y), None when none is."""
    tile = tile_at(x, y)
    best = None
    for row in rows:
        dist = manhattan(tile, tile_at(row["x"], row["y"]))
        if dist <= MATCH_TILES and (best is None or dist < best[0]):
            best = (dist, row["id"])
    return best[1] if best else None


def drilled_sites(mine_rows, ghosts):
    """Site ids with a drill (drill_id()) or a drill ghost (structure rows) on them."""
    taken = {row["id"] for row in mine_rows if row["drill"]}
    for row in ghosts:
        if row["kind"] in DRILL_KIND_NAMES:
            site_id = site_at(mine_rows, row["x"], row["y"])
            if site_id is not None:
                taken.add(site_id)
    return taken


def drill_kind(hardness, in_stock, locked):
    """(kind, kit) for a deposit: the lightest kind cutting it with a kit in stock, else the lightest cutting it; None when none can."""
    hard = 4 if hardness is None else hardness
    fitting = [(kind, kit) for kind, cuts, kit in DRILL_KINDS if cuts >= hard and kind not in locked]
    for kind, kit in fitting:
        if in_stock(kit) > 0:
            return (kind, kit)
    return fitting[0] if fitting else None


_PURITY_RANK = {"pure": 0, "rich": 1, "standard": 2}


def drill_candidates(mine_rows, wanted, smelter_boxes, taken):
    """
    [(tier, tiles, purity rank, site id, row)]: per wanted ore with no drilled
    site, its site nearest a Smelter outpost (then purest). Ores already drilled
    and sites in `taken` are skipped.
    """
    drilled = {row["item"] for row in mine_rows if row["id"] in taken}
    best = {}
    for row in mine_rows:
        if row["item"] not in wanted or row["item"] in drilled or row["id"] in taken:
            continue
        dist = supply_tiers.gap(extractor_box(row["x"], row["y"]), smelter_boxes)
        key = (dist, _PURITY_RANK.get(row["purity"], 3), row["id"])
        held = best.get(row["item"])
        if held is None or key < held[0]:
            best[row["item"]] = (key, row)
    return [(supply_tiers.TIER_SOON, key[0], key[1], key[2], row) for _item, (key, row) in sorted(best.items())]


def smelter_outposts():
    """({outpost_id: ores its Smelters take}, every ore wanted) over outpost_network."""
    network = get_component("outpost_network")
    if network is None:
        return ({}, set())
    try:
        refs = list(network.outposts() or [])
    except Exception as error:
        swallowed("extractor_plan.smelter_outposts: outpost_network.outposts", error)
        return ({}, set())
    out = {}
    for ref in refs:
        ores = smelter_ores(ref)
        if ores:
            out[ref.id] = set(ores)
    return (out, {ore for ores in out.values() for ore in ores})


class ExtractorPlanner:
    """One extractor pass per planner tick; see the module header."""

    def __init__(self, log: "TreeConsole"):
        self.log = log
        self.skip = set()     # site ids the game rejected this run
        self.locked = set()   # structure kinds plan_structure() reported locked this run

    def run_pass(self, topo, idle):
        """
        "queued" (an extractor was planned), "waiting" (extractor jobs of ours
        still open, or urgent ones at their cap), "done" or "error". idle: the
        power and fluid passes have nothing urgent left (plan-ahead allowed).
        """
        outpost_xy = outpost_positions()
        if outpost_xy is None:
            self.log.debug("Extractors: outpost_network unreadable; pass skipped.")
            return "error"
        demand = autoplay_roles.demand(sorted(outpost_xy), autoplay_roles.outpost_roles(), autoplay_roles.presets(), home_outpost_id())
        sites = surveyed_sites()
        rows = supply_tiers.fluid_sites(sites)
        mine_rows = mining_sites(sites)
        ghosts = topo.structure_rows
        ghost_sites = {site_at(rows, g["x"], g["y"]) for g in ghosts if g["kind"] not in DRILL_KIND_NAMES} - {None}
        smelters, wanted = smelter_outposts()
        smelter_boxes = [outpost_box(*outpost_xy[oid]) for oid in sorted(smelters) if oid in outpost_xy]
        candidates = supply_tiers.fluid_candidates(rows, demand, outpost_xy, ghost_sites, self.skip)
        candidates += drill_candidates(mine_rows, wanted, smelter_boxes, drilled_sites(mine_rows, ghosts) | self.skip)
        candidates = sorted(candidates, key=lambda c: c[:4])
        own = open_planned(EXTRACTOR_KINDS)
        urgent_open = len([1 for e in own.values() if e.get("p") == 0])
        tiers = [len([1 for c in candidates if c[0] == tier]) for tier in range(4)]
        self.log.debug(f"Extractors: {len(rows)} fluid site(s), {len(mine_rows)} mineral site(s), smelter ores {sorted(wanted)}; "
                       f"candidates now/soon/ahead/spare {tiers}; {len(own)} job(s) of ours open ({urgent_open} urgent).")
        outcome = self._queue(candidates, own, urgent_open, idle)
        if outcome == "done" and own:
            return "waiting"
        return outcome

    def _queue(self, candidates, own, urgent_open, idle):
        """Tries the candidates in order; returns "queued", "waiting" or "done"."""
        tries = 0
        for tier, dist, _rank, site_id, row in candidates:
            if tries >= MAX_TRIES_PER_PASS:
                return "waiting"
            prio = supply_tiers.tier_prio(tier)
            if prio == 0 and urgent_open >= MAX_OPEN_URGENT:
                self.log.debug(f"Extractors: {urgent_open} urgent job(s) open; {site_id} waits.")
                return "waiting"
            if prio != 0 and (not idle or own):
                self.log.debug(f"Extractors: plan-ahead {site_id} waits ({'own extractor jobs open' if own else 'other passes busy'}).")
                return "done"
            pick = self._pick_kind(row)
            if pick is None:
                continue
            kind, kit = pick
            if prio != 0 and stock(kit) < 1:
                self.log.debug(f"Extractors: plan-ahead {kind} on {site_id} waits for {kit} in stock.")
                return "done"
            tries += 1
            status = self._place(tier, dist, site_id, row, kind, prio)
            if status == "queued":
                return "queued"
            if status == "short":
                return "done"
        return "done"

    def _pick_kind(self, row):
        """(structure kind, kit item) for a candidate row; None when its kind is locked."""
        if "item" in row:
            return drill_kind(row["hardness"], stock, self.locked)
        kind = row["structure"]
        if kind in self.locked:
            return None
        return (kind, EXTRACTOR_KITS.get(kind, kind))

    def _place(self, tier, dist, site_id, row, kind, prio):
        """Queues one extractor; returns "queued", "rejected" or "short" (plan-ahead kit not in stock, job cancelled)."""
        what = row.get("item") or row.get("fluid")
        label = f"{kind} on {site_id} ({what}, tier {tier}, {dist if dist < supply_tiers.FAR else '?'} tiles)"
        self.log.start(f"Extractor {label}")
        status, ids, message = queue_structure(kind, row["x"], row["y"], prio, site_id, row.get("fluid"))
        if status == "locked":
            self.locked.add(kind)
            self.log.end(f"locked: {message}")
            return "rejected"
        if status != "ok" or not ids:
            if status in _SITE_REJECTIONS or status == "ok":
                self.skip.add(site_id)
            self.log.end(f"rejected ({status} {message})")
            return "rejected"
        item, count = job_need(ids[0])
        if prio != 0 and item and stock(item) < count:
            cancel(ids)
            self.log.end(f"cancelled: plan-ahead needs {count} {item}, {stock(item)} in stock")
            return "short"
        self.log.print(f"Extractor queued: {label}, prio {prio}, needs {count} {item or '?'}.")
        self.log.end("queued")
        return "queued"
