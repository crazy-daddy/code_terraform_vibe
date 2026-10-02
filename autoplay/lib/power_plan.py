# Power pass of the infrastructure planner (autoplay/infra_planner_automation.py): joins
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
# footprint tiles) gives the missing links. No grid may hang on a field
# structure: a link ending on a field structure whose grid has other members
# also wires that structure's footprint perimeter (ring_legs()). Every line
# feeding the structure crosses a perimeter tile, so the ring joins them and
# deconstructing the structure keeps the grid whole; the ring's RING_PIECES
# count into the link's MST cost, so outposts are preferred as link ends.
# Each pass queues the cheapest missing links, up to MAX_LINKS_PER_PASS, as
# plan_power_line() between the
# two nearest footprint tiles (the game picks the L elbow; the other elbow is
# tried when it is rejected). Completed power lines have no list API, so a
# pass waits while any power-line job is still open: the grids only merge
# once the line is built.

from atomic import run_atomic, run_chunked
from swallow import swallowed
from grid_geom import FOOTPRINT_TILES, outpost_box, extractor_box, box_closest, tile_centre, tile_xy, tile_key
from blueprint_queue import stock, queue_power_route
from infra_topology import outpost_positions, surveyed_sites
from construction_plan import DEFAULT_PRIORITY
from drill_sites import known_positions

POWER_ITEM = "power_line_segment"
MAX_LINKS_PER_PASS = 1   # power links (plan_power_line routes) queued per pass
RING_PIECES = 4 * (FOOTPRINT_TILES - 1)   # pieces around a footprint's perimeter (ring_legs())
PAIR_CHUNK = 50          # footprint pairs per atomic edge slice (worst ~3,500 operations, tests/test_autoplay_power.py)
FLOOD_STEP_TILES = 30    # ledger tiles per atomic flood_step() call (worst ~3,100 operations, tests/test_autoplay_power.py)
LINE_NAME = "line"       # member name of a bare power-line run in logs
_NEIGHBOURS = (1, -1, 1 << 16, -(1 << 16))   # tile_key() offsets of the 4 neighbours

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
    boxes = [(box, ring, member id)]; ring is True for a field structure in a
    grid with other placed members: a link ending there must ring its
    footprint (ring_legs()), so the grid does not hang on that structure.
    outpost_xy: {outpost_id: (x, y)} top-left anchors; field_xy: {machine_id: (x, y)} site centres.
    """
    placed = []
    unplaced = []
    for row in rows:
        boxes = [(outpost_box(*outpost_xy[o]), False, o) for o in row["outposts"] if o in outpost_xy]
        fields = [m for m in row["machines"] if m in field_xy]
        shared = len(boxes) + len(fields) > 1
        boxes.extend([(extractor_box(*field_xy[m]), shared, m) for m in fields])
        if boxes:
            placed.append({"anchor": row["anchor"], "boxes": boxes})
        else:
            unplaced.append(row["anchor"])
    return (placed, unplaced)


def box_tiles(box):
    """Every tile_key() of an inclusive tile box."""
    return [tile_key(tx, ty) for tx in range(box[0], box[2] + 1) for ty in range(box[1], box[3] + 1)]


def flood_init(comps, power_tiles):
    """
    State for flood_step(): which component each ledger power tile belongs
    to, flooding over 4-neighbouring power tiles from the power tiles inside
    each component's footprints.
    """
    owner = {}
    queue = []
    for index, comp in enumerate(comps):
        for box, _ring, _name in comp["boxes"]:
            for tile in box_tiles(box):
                if tile not in power_tiles:
                    continue
                held = owner.get(tile)
                if held is None:
                    owner[tile] = index
                    queue.append(tile)
                elif held != index:
                    owner[tile] = -1
    return {"tiles": power_tiles, "owner": owner, "queue": queue, "next": 0}


def flood_step(state):
    """Spreads ownership from up to FLOOD_STEP_TILES queued tiles; True when done. A tile two components reach is contested (-1)."""
    owner = state["owner"]
    tiles = state["tiles"]
    queue = state["queue"]
    end = min(len(queue), state["next"] + FLOOD_STEP_TILES)
    for position in range(state["next"], end):
        tile = queue[position]
        index = owner[tile]
        if index < 0:
            continue
        for offset in _NEIGHBOURS:
            other = tile + offset
            if other not in tiles:
                continue
            held = owner.get(other)
            if held is None:
                owner[other] = index
                queue.append(other)
            elif held != index and held >= 0:
                owner[other] = -1
    state["next"] = end
    return end >= len(queue)


def line_runs(owner):
    """[(component index, box)] horizontal runs of owned (not contested) power tiles."""
    by_row = {}
    for tile, index in owner.items():
        if index >= 0:
            tx, ty = tile_xy(tile)
            by_row.setdefault((index, ty), []).append(tx)
    runs = []
    for (index, ty), xs in by_row.items():
        xs.sort()
        start = xs[0]
        last = xs[0]
        for tx in xs[1:]:
            if tx != last + 1:
                runs.append((index, (start, ty, last, ty)))
                start = tx
            last = tx
        runs.append((index, (start, ty, last, ty)))
    return runs


def attach_lines(comps, power_tiles):
    """Adds each component's ledger power-line runs to its boxes (ring False, member LINE_NAME); returns (runs added, contested tiles)."""
    if not power_tiles:
        return (0, 0)
    state = flood_init(comps, power_tiles)
    run_chunked(flood_step, state)
    runs = line_runs(state["owner"])
    for index, box in runs:
        comps[index]["boxes"].append((box, False, LINE_NAME))
    contested = len([1 for index in state["owner"].values() if index < 0])
    return (len(runs), contested)


def flat_boxes(comps):
    """[(component index, box, ring cost)] over every component's footprints."""
    return [(index, box, RING_PIECES if ring else 0) for index, comp in enumerate(comps) for box, ring, _name in comp["boxes"]]


def pair_segments(comp_of, size=None):
    """
    Work for edge_slice() in batches of at most `size` box pairs: a list of
    batches, each a list of (i, j0, j1) = box i against boxes j0 <= j < j1.
    comp_of = component index per box, grouped (flat_boxes() order): box i is
    only paired with the boxes of later components.
    """
    size = size or PAIR_CHUNK
    count = len(comp_of)
    next_start = [count] * count
    boundary = count
    for i in range(count - 1, -1, -1):
        if i + 1 < count and comp_of[i + 1] != comp_of[i]:
            boundary = i + 1
        next_start[i] = boundary
    batches = []
    batch = []
    room = size
    for i in range(count):
        j0 = next_start[i]
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
    Cheapest footprint pair for each (i, j0, j1) segment: box i against boxes
    j0..j1-1 of another component. [(cost, ci, cj, i, j)] with ci < cj, only
    the cheapest per component pair within this call. cost = tiles apart plus
    the ring cost of both ends.
    """
    best = {}
    for i, j0, j1 in segments:
        ci, (ax0, ay0, ax1, ay1), ring_i = boxes[i]
        for j in range(j0, j1):
            cj, (bx0, by0, bx1, by1), ring_j = boxes[j]
            if ci == cj:
                continue
            dx = bx0 - ax1 if bx0 > ax1 else (ax0 - bx1 if ax0 > bx1 else 0)
            dy = by0 - ay1 if by0 > ay1 else (ay0 - by1 if ay0 > by1 else 0)
            dist = dx + dy + ring_i + ring_j
            pair = (ci, cj) if ci < cj else (cj, ci)
            held = best.get(pair)
            if held is None or dist < held[0]:
                best[pair] = (dist, pair[0], pair[1], i, j) if ci < cj else (dist, pair[0], pair[1], j, i)
    return list(best.values())


def component_edges(boxes):
    """
    Cheapest link per component pair over flat_boxes(): [(cost, ci, cj, i, j)],
    i/j = the boxes it joins (edge_slice() in atomic batches of PAIR_CHUNK pairs).
    """
    best = {}
    edges = []
    for batch in pair_segments([box[0] for box in boxes]):
        edges.extend(run_atomic(edge_slice, batch, boxes))
    for edge in edges:
        pair = (edge[1], edge[2])
        held = best.get(pair)
        if held is None or edge[0] < held[0]:
            best[pair] = edge
    return list(best.values())


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


def ring_legs(box):
    """Four legs [x1, y1, x2, y2] wiring the perimeter tiles of a footprint box (RING_PIECES pieces)."""
    x0, y0 = tile_centre(tile_key(box[0], box[1]))
    x1, y1 = tile_centre(tile_key(box[2], box[3]))
    return [[x0, y0, x1, y0], [x1, y0, x1, y1], [x1, y1, x0, y1], [x0, y1, x0, y0]]


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
    outpost_xy = outpost_positions() or {}
    sites = surveyed_sites()
    return (rows, outpost_xy, site_machines(sites, known_positions()))


def _end_name(member, tile):
    """Log name of a link end: the member id, or the line tile's world centre."""
    if member != LINE_NAME:
        return member
    x, y = tile_centre(tile)
    return f"line ({x:.0f}, {y:.0f})"


class PowerPlanner:
    """One power pass per planner tick; see the module header."""

    def __init__(self, log):
        self.log = log
        self.failed = set()   # (anchor, anchor) links the game rejected this run; not retried until restart

    def run_pass(self, topo, power_tiles=None):
        """
        "waiting" (power jobs still open, or links blocked by stock), "queued"
        (a link was planned), "joined" (one placed grid, nothing to do) or
        "error" (power_control unreadable). power_tiles: tile_key() set of the
        power-line ledger (power_survey.ledger_tiles()); lines there are link ends too.
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
        runs, contested = attach_lines(comps, power_tiles or set())
        self.log.debug(f"Power: {len(power_tiles or ())} ledger tile(s) -> {runs} line run(s) as link ends, {contested} contested tile(s) dropped.")
        flat = flat_boxes(comps)
        links = spanning_links(len(comps), component_edges(flat))
        self.log.start(f"Power: joining {len(comps)} grids ({len(links)} link(s) missing)")
        outcome = self._queue_links(comps, flat, links)
        self.log.end(outcome)
        return "queued" if outcome.startswith("queued") else "waiting"

    def _queue_links(self, comps, flat, links):
        """Queues up to MAX_LINKS_PER_PASS links; returns the block's outcome line."""
        members = [name for comp in comps for _box, _ring, name in comp["boxes"]]
        have = stock(POWER_ITEM)
        queued = 0
        short = 0
        for cost, ci, cj, i, j in links:
            if queued >= MAX_LINKS_PER_PASS:
                break
            pair = (comps[ci]["anchor"], comps[cj]["anchor"])
            names = f"{members[i]} -> {members[j]}"
            if pair in self.failed:
                self.log.debug(f"{names}: rejected earlier this run; skipped.")
                continue
            if cost > have:
                self.log.debug(f"{names}: needs {cost} {POWER_ITEM}, {have} in stock; skipped.")
                short += 1
                continue
            dist, tile_a, tile_b = box_closest(flat[i][1], flat[j][1])
            names = f"{_end_name(members[i], tile_a)} -> {_end_name(members[j], tile_b)}"
            rings = [(members[k], flat[k][1]) for k in (i, j) if flat[k][2]]
            if self._queue_link(names, dist, tile_a, tile_b, rings):
                queued += 1
                have -= cost
            else:
                self.failed.add(pair)
        if queued:
            return f"queued {queued} link(s)"
        if short:
            return f"waiting for {POWER_ITEM} ({have} in stock)"
        return "no link could be planned"

    def _queue_link(self, names, dist, tile_a, tile_b, rings):
        """
        True when the link was queued. rings = [(member id, box)] of field
        structures the link ends on that also feed other members: their
        footprint perimeter is wired too, all in one all-or-nothing route.
        A link whose pieces all exist already (no job created) while the grids
        stay apart does not connect: logged and False.
        """
        if dist < 1 and not rings:
            self.log.level("warn").print(f"Power link {names}: footprints touch but grids stay apart; not plannable.")
            return False
        ring_part = [leg for _name, box in rings for leg in ring_legs(box)]
        ring_note = f" + ring around {', '.join([name for name, _box in rings])}" if rings else ""
        for legs in link_routes(tile_a, tile_b):
            status, ids, message = queue_power_route((legs if dist else []) + ring_part, DEFAULT_PRIORITY)
            if status == "ok" and ids:
                self.log.print(f"Power link {names}: {dist} tiles{ring_note}, {len(ids)} job(s) queued.")
                return True
            if status == "ok":
                self.log.level("warn").print(f"Power link {names}: every piece already exists but the grids stay apart.")
                return False
            self.log.debug(f"{names} via {legs}: {status} {message}")
            if status not in _RETRY_STATUSES:
                return False
        return False
