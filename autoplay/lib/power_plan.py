# Power pass of the infrastructure planner (autoplay/infra_planner.py): joins
# every power subnet into one grid.
#
# Components are power_control.grids(). Each is placed on the map by the
# footprints of its members:
#   - outposts (outpost_network, top-left anchor),
#   - field structures on a surveyed site: pumps (WaterWell/OilWell.pump_id()),
#     thermal and exotic caps (cap_id()), drills (drill.positions archive,
#     lib/drill_sites.py) -- all centre-anchored on the site.
# A grid with no placeable member is skipped and logged.
#
# A minimum spanning tree (Kruskal, tile distance between the nearest
# footprint tiles) gives the missing links; each pass queues the shortest
# missing links, up to MAX_LINKS_PER_PASS, as plan_power_line() between the
# two nearest footprint tiles (the game picks the L elbow; the other elbow is
# tried when it is rejected). Completed power lines have no list API, so a
# pass waits while any power-line job is still open: the grids only merge
# once the line is built.

from atomic import run_atomic
from swallow import swallowed
from grid_geom import outpost_box, extractor_box, box_closest, tile_centre, tile_xy, tile_key
from blueprint_queue import stock, queue_power_route
from construction_plan import DEFAULT_PRIORITY
from drill_sites import known_positions

POWER_ITEM = "power_line_segment"
MAX_LINKS_PER_PASS = 1   # power links (plan_power_line routes) queued per pass
PAIR_CHUNK = 50          # footprint pairs per atomic edge slice (worst ~3,500 operations, tests/test_autoplay_power.py)

# Site kind -> name of its method that returns the machine id standing on it.
_SITE_MACHINE_GETTERS = {"water": "pump_id", "oil": "pump_id", "thermal": "cap_id", "exotic": "cap_id"}

# plan_power_line() statuses worth retrying with the other L elbow.
_RETRY_STATUSES = ("blocked", "invalid_route")


def site_machines(sites, drill_positions):
    """{machine_id: (x, y)} of field structures standing on surveyed sites, plus drills from drill.positions."""
    out = {}
    for site in sites:
        try:
            getter = _SITE_MACHINE_GETTERS.get(site.kind())
            if getter is None:
                continue
            machine_id = getattr(site, getter)()
            if machine_id:
                out[machine_id] = (float(site.x), float(site.y))
        except Exception as error:
            swallowed("power_plan.site_machines: site read", error)
    for drill_id, entry in (drill_positions or {}).items():
        pos = entry.get("pos") if isinstance(entry, dict) else None
        if pos is not None and isinstance(pos, (list, tuple)) and len(pos) == 2:
            out[drill_id] = (float(pos[0]), float(pos[1]))
    return out


def grid_rows(grids):
    """Plain rows {anchor, outposts, machines} for power_control.grids()."""
    rows = []
    for grid in grids:
        rows.append({
            "anchor": grid.anchor_id,
            "outposts": list(grid.outpost_ids or []),
            "machines": list(grid.machine_ids or []),
        })
    return rows


def components(rows, outpost_xy, field_xy):
    """
    (placed, unplaced): placed = [{"anchor", "boxes"}] for every grid with at
    least one footprint on the map, unplaced = anchor ids of the others.
    outpost_xy: {outpost_id: (x, y)} top-left anchors; field_xy: {machine_id: (x, y)} site centres.
    """
    placed = []
    unplaced = []
    for row in rows:
        boxes = [outpost_box(*outpost_xy[o]) for o in row["outposts"] if o in outpost_xy]
        boxes.extend([extractor_box(*field_xy[m]) for m in row["machines"] if m in field_xy])
        if boxes:
            placed.append({"anchor": row["anchor"], "boxes": boxes})
        else:
            unplaced.append(row["anchor"])
    return (placed, unplaced)


def flat_boxes(comps):
    """[(component index, box)] over every component's footprints."""
    return [(index, box) for index, comp in enumerate(comps) for box in comp["boxes"]]


def pair_segments(count, size=None):
    """
    Work for edge_slice() in batches of at most `size` box pairs: a list of
    batches, each a list of (i, j0, j1) = box i against boxes j0 <= j < j1, j0 > i.
    """
    size = size or PAIR_CHUNK
    batches = []
    batch = []
    room = size
    for i in range(count - 1):
        j0 = i + 1
        while j0 < count:
            j1 = min(count, j0 + room)
            batch.append((i, j0, j1))
            room -= j1 - j0
            j0 = j1
            if room == 0:
                batches.append(batch)
                batch = []
                room = size
    if batch:
        batches.append(batch)
    return batches


def edge_slice(segments, boxes):
    """
    Nearest footprint pair for each (i, j0, j1) segment: box i against boxes
    j0..j1-1 of another component. [(tiles apart, ci, cj, i, j)] with ci < cj,
    only the shortest per component pair within this call.
    """
    best = {}
    for i, j0, j1 in segments:
        ci, (ax0, ay0, ax1, ay1) = boxes[i]
        for j in range(j0, j1):
            cj, (bx0, by0, bx1, by1) = boxes[j]
            if ci == cj:
                continue
            dx = bx0 - ax1 if bx0 > ax1 else (ax0 - bx1 if ax0 > bx1 else 0)
            dy = by0 - ay1 if by0 > ay1 else (ay0 - by1 if ay0 > by1 else 0)
            dist = dx + dy
            pair = (ci, cj) if ci < cj else (cj, ci)
            held = best.get(pair)
            if held is None or dist < held[0]:
                best[pair] = (dist, pair[0], pair[1], i, j) if ci < cj else (dist, pair[0], pair[1], j, i)
    return list(best.values())


def component_edges(boxes):
    """
    Shortest link per component pair over all boxes: [(tiles apart, ci, cj,
    tile in ci, tile in cj)] (edge_slice() in atomic batches of PAIR_CHUNK pairs).
    """
    best = {}
    edges = []
    for batch in pair_segments(len(boxes)):
        edges.extend(run_atomic(edge_slice, batch, boxes))
    for edge in edges:
        pair = (edge[1], edge[2])
        held = best.get(pair)
        if held is None or edge[0] < held[0]:
            best[pair] = edge
    out = []
    for dist, ci, cj, i, j in best.values():
        _dist, tile_i, tile_j = box_closest(boxes[i][1], boxes[j][1])
        out.append((dist, ci, cj, tile_i, tile_j))
    return out


def _root(parent, node):
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return node


def spanning_links(count, edges):
    """Kruskal: the edges (shortest first, ties by component indices) joining `count` components into one tree."""
    parent = list(range(count))
    chosen = []
    for edge in sorted(edges):
        root_a = _root(parent, edge[1])
        root_b = _root(parent, edge[2])
        if root_a == root_b:
            continue
        parent[root_a] = root_b
        chosen.append(edge)
        if len(chosen) == count - 1:
            break
    return chosen


def link_routes(tile_a, tile_b):
    """
    Candidate routes for a link, each a list of legs [x1, y1, x2, y2] on tile
    centres: the direct request first (the game picks the elbow), then the two
    explicit L elbows when the tiles are off-axis.
    """
    ax, ay = tile_centre(tile_a)
    bx, by = tile_centre(tile_b)
    routes = [[[ax, ay, bx, by]]]
    a_tx, a_ty = tile_xy(tile_a)
    b_tx, b_ty = tile_xy(tile_b)
    if a_tx != b_tx and a_ty != b_ty:
        for corner in (tile_key(b_tx, a_ty), tile_key(a_tx, b_ty)):
            cx, cy = tile_centre(corner)
            routes.append([[ax, ay, cx, cy], [cx, cy, bx, by]])
    return routes


def _game_reads():
    """(rows, outpost_xy, field_xy) from power_control, outpost_network, journal and drill.positions; None when power_control is missing."""
    power = get_component("power_control")
    if power is None:
        return None
    try:
        rows = grid_rows(power.grids() or [])
    except Exception as error:
        swallowed("power_plan._game_reads: power_control.grids", error)
        return None
    outpost_xy = {}
    network = get_component("outpost_network")
    if network is not None:
        try:
            for ref in network.outposts() or []:
                outpost_xy[ref.id] = (float(ref.x), float(ref.y))
        except Exception as error:
            swallowed("power_plan._game_reads: outpost_network.outposts", error)
    sites = []
    journal = get_component("journal")
    if journal is not None:
        try:
            sites = journal.surveyed_sites("nocturna") or []
        except Exception as error:
            swallowed("power_plan._game_reads: journal.surveyed_sites", error)
    return (rows, outpost_xy, site_machines(sites, known_positions()))


class PowerPlanner:
    """One power pass per planner tick; see the module header."""

    def __init__(self, log):
        self.log = log
        self.failed = set()   # (anchor, anchor) links the game rejected this run; not retried until restart

    def run_pass(self, topo):
        """
        "waiting" (power jobs still open, or links blocked by stock), "queued"
        (a link was planned), "joined" (one placed grid, nothing to do) or
        "error" (power_control unreadable).
        """
        if any(row["medium"] == "power" for row in topo.job_rows):
            open_jobs = len([row for row in topo.job_rows if row["medium"] == "power"])
            self.log.debug(f"Power: {open_jobs} power-line job(s) still open; waiting for the grids to merge.")
            return "waiting"
        reads = _game_reads()
        if reads is None:
            self.log.debug("Power: power_control unreadable; pass skipped.")
            return "error"
        rows, outpost_xy, field_xy = reads
        comps, unplaced = components(rows, outpost_xy, field_xy)
        if unplaced:
            self.log.debug(f"Power: {len(unplaced)} grid(s) without a placeable member skipped: {', '.join(unplaced[:5])}")
        if len(comps) < 2:
            self.log.debug(f"Power: {len(rows)} grid(s), {len(comps)} placed; nothing to join.")
            return "joined"
        links = spanning_links(len(comps), component_edges(flat_boxes(comps)))
        self.log.start(f"Power: joining {len(comps)} grids ({len(links)} link(s) missing)")
        outcome = self._queue_links(comps, links)
        self.log.end(outcome)
        return "queued" if outcome.startswith("queued") else "waiting"

    def _queue_links(self, comps, links):
        """Queues up to MAX_LINKS_PER_PASS links; returns the block's outcome line."""
        have = stock(POWER_ITEM)
        queued = 0
        short = 0
        for dist, ci, cj, tile_a, tile_b in links:
            if queued >= MAX_LINKS_PER_PASS:
                break
            pair = (comps[ci]["anchor"], comps[cj]["anchor"])
            names = f"{pair[0]} -> {pair[1]}"
            if pair in self.failed:
                self.log.debug(f"{names}: rejected earlier this run; skipped.")
                continue
            if dist > have:
                self.log.debug(f"{names}: needs {dist} {POWER_ITEM}, {have} in stock; skipped.")
                short += 1
                continue
            if self._queue_link(names, dist, tile_a, tile_b):
                queued += 1
                have -= dist
            else:
                self.failed.add(pair)
        if queued:
            return f"queued {queued} link(s)"
        if short:
            return f"waiting for {POWER_ITEM} ({have} in stock)"
        return "no link could be planned"

    def _queue_link(self, names, dist, tile_a, tile_b):
        """True when the link was queued. A link whose pieces all exist already
        (no job created) while the grids stay apart does not connect: logged and False."""
        if dist < 1:
            self.log.level("warn").print(f"Power link {names}: footprints touch but grids stay apart; not plannable.")
            return False
        for legs in link_routes(tile_a, tile_b):
            status, ids, message = queue_power_route(legs, DEFAULT_PRIORITY)
            if status == "ok" and ids:
                self.log.print(f"Power link {names}: {dist} tiles, {len(ids)} job(s) queued.")
                return True
            if status == "ok":
                self.log.level("warn").print(f"Power link {names}: every piece already exists but the grids stay apart.")
                return False
            self.log.debug(f"{names} via {legs}: {status} {message}")
            if status not in _RETRY_STATUSES:
                return False
        return False
