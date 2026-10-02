# Pure tile geometry and the utility router for the infrastructure planner
# (autoplay/infra_planner.py). No game calls, no logging: every function takes
# plain data, so tests run it in CPython and the planner may run it through
# lib/atomic.py (run_atomic/run_chunked).
#
# Map model (docs/cheatsheet/autoplay.md §11):
#   - The map is a grid of TILE_M tiles; utility lanes run through tile centres
#     (world coordinates ending in 5 for 10 m tiles).
#   - Every pipe / power-line piece is one straight TILE_M segment joining the
#     centres of two neighbouring tiles. A construction job's position is that
#     segment's midpoint, which lies on a tile edge.
#   - Two same-medium pieces connect only when they share a tile; pieces on
#     neighbouring parallel lanes stay separate.
#   - Outposts and field extractors cover FOOTPRINT_TILES x FOOTPRINT_TILES
#     tiles. An outpost is anchored at its top-left corner, an extractor at
#     its centre (the surveyed site).
#
# Tiles are packed into one int (tile_key) so sets and dict keys stay cheap in
# the game interpreter.

from heapq import heappush, heappop

TILE_M = 10
FOOTPRINT_TILES = 4
_KEY_SPAN = 1 << 16
_KEY_OFFSET = 1 << 15

# Router costs, in tiles walked.
STEP_COST = 1
BRIDGE_COST = 6          # a bridge hop (3 tiles) costs this instead of 2 steps: bridges are a scarcer item than segments
SOFT_TILE_COST = 4       # extra cost to walk a tile in `soft` (another site's footprint)
ROUTE_MAX_NODES = 20000  # expanded tiles before the router gives up
ROUTE_STEP_NODES = 10    # expanded nodes per route_step() call (worst ~375 operations each, tests/test_autoplay_geom.py)
SEED_CHUNK = 40          # source tiles per route_seed() call (~80 operations each)

_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def tile_key(tx, ty):
    """One int for tile (tx, ty)."""
    return (tx + _KEY_OFFSET) * _KEY_SPAN + (ty + _KEY_OFFSET)


def tile_xy(key):
    """(tx, ty) of a tile_key()."""
    return (key // _KEY_SPAN - _KEY_OFFSET, key % _KEY_SPAN - _KEY_OFFSET)


def tile_index(coord):
    """Tile index along one axis for a world coordinate."""
    return int(coord // TILE_M)


def tile_at(x, y):
    """tile_key() of the tile containing world point (x, y)."""
    return tile_key(tile_index(x), tile_index(y))


def tile_centre(key):
    """World (x, y) of a tile's centre: where utility lanes run."""
    tx, ty = tile_xy(key)
    half = TILE_M / 2
    return (tx * TILE_M + half, ty * TILE_M + half)


def _on_edge(coord):
    return coord % TILE_M == 0


def piece_tiles(x1, y1, x2, y2):
    """The tiles a completed piece joins, from its start/end points (tile centres). One tile if both ends share it."""
    a = tile_at(x1, y1)
    b = tile_at(x2, y2)
    return [a] if a == b else [a, b]


def job_tiles(x, y):
    """
    Tiles of a construction job from its position: a utility piece's midpoint
    sits on a tile edge (x on an edge = horizontal piece, y on an edge =
    vertical); anything else (bridge centre, structure) is the tile it is in.
    """
    if _on_edge(x) and not _on_edge(y):
        ty = tile_index(y)
        tx = int(x // TILE_M)
        return [tile_key(tx - 1, ty), tile_key(tx, ty)]
    if _on_edge(y) and not _on_edge(x):
        tx = tile_index(x)
        ty = int(y // TILE_M)
        return [tile_key(tx, ty - 1), tile_key(tx, ty)]
    return [tile_at(x, y)]


def _square(tx0, ty0):
    return [tile_key(tx0 + dx, ty0 + dy) for dx in range(FOOTPRINT_TILES) for dy in range(FOOTPRINT_TILES)]


def outpost_tiles(x, y):
    """Footprint tiles of an outpost anchored at its top-left corner (x, y)."""
    return _square(tile_index(x), tile_index(y))


def extractor_tiles(x, y):
    """Footprint tiles of a field extractor centred on its site (x, y)."""
    half = FOOTPRINT_TILES * TILE_M / 2
    return _square(tile_index(x - half), tile_index(y - half))


def outpost_box(x, y):
    """(tx0, ty0, tx1, ty1) inclusive tile box of an outpost footprint (top-left anchor)."""
    tx0 = tile_index(x)
    ty0 = tile_index(y)
    return (tx0, ty0, tx0 + FOOTPRINT_TILES - 1, ty0 + FOOTPRINT_TILES - 1)


def extractor_box(x, y):
    """(tx0, ty0, tx1, ty1) inclusive tile box of a field extractor footprint (centre anchor)."""
    half = FOOTPRINT_TILES * TILE_M / 2
    return outpost_box(x - half, y - half)


def _span_closest(a0, a1, b0, b1):
    """Closest pair of coordinates of two inclusive ranges; equal values when they overlap."""
    if a1 < b0:
        return (a1, b0)
    if b1 < a0:
        return (a0, b1)
    value = a0 if a0 > b0 else b0
    return (value, value)


def box_closest(a, b):
    """(tiles apart, tile in a, tile in b) for the nearest tiles of two tile boxes."""
    ax, bx = _span_closest(a[0], a[2], b[0], b[2])
    ay, by = _span_closest(a[1], a[3], b[1], b[3])
    return (abs(ax - bx) + abs(ay - by), tile_key(ax, ay), tile_key(bx, by))


def manhattan(a, b):
    """Tile distance between two tile_key()s."""
    ax, ay = tile_xy(a)
    bx, by = tile_xy(b)
    return abs(ax - bx) + abs(ay - by)


def goal_box(goals):
    """(min_tx, max_tx, min_ty, max_ty) of a tile set: the router's heuristic target."""
    xs = [tile_xy(t)[0] for t in goals]
    ys = [tile_xy(t)[1] for t in goals]
    return (min(xs), max(xs), min(ys), max(ys))


def _box_distance(tile, box):
    """Manhattan distance from tile to the goal box: never more than to the nearest goal (admissible)."""
    tx = tile // _KEY_SPAN - _KEY_OFFSET
    ty = tile % _KEY_SPAN - _KEY_OFFSET
    dx = box[0] - tx if tx < box[0] else (tx - box[1] if tx > box[1] else 0)
    dy = box[2] - ty if ty < box[2] else (ty - box[3] if ty > box[3] else 0)
    return dx + dy


def route_init(sources, goals, blocked, bridgeable=None, soft=None, max_nodes=ROUTE_MAX_NODES):
    """
    Router state for route_step(): cheapest tile path from any tile in
    `sources` to any tile in `goals`.
      blocked:    tiles the route may not enter (other networks of the medium, foreign pieces).
      bridgeable: blocked tiles a bridge may pass over (the middle of a 3-tile hop
                  whose two end tiles are free). Default: none. Bridges may not overlap:
                  a bridge never starts or lands on the previous bridge's landing tile.
      soft:       free tiles that cost SOFT_TILE_COST extra (other sites' footprints).
    Sources cost nothing to start from, so an existing network is reused for free.
    Search nodes are tile * 2 + landed: a tile reached by a bridge landing (may
    not start the next bridge) is kept apart from the same tile reached on foot.
    Pass sources=() and feed them through route_seed() in SEED_CHUNK slices when
    there are many (a whole network) and the call runs atomically.
    """
    goals = set(goals)
    state = {
        "goals": goals,
        "box": goal_box(goals) if goals else (0, 0, 0, 0),
        "blocked": blocked,
        "bridgeable": bridgeable or set(),
        "soft": soft or set(),
        "max_nodes": max_nodes,
        "open": [],
        "g": {},
        "came": {},
        "closed": set(),
        "expanded": 0,
        "done": not goals,
        "found": None,
    }
    route_seed(sources, state)
    return state


def route_seed(tiles, state):
    """Adds start tiles to a route_init() state; returns [] (shaped for lib/atomic.py run_batched())."""
    blocked = state["blocked"]
    g_cost = state["g"]
    box = state["box"]
    for tile in tiles:
        node = tile * 2
        if tile in blocked or node in g_cost:
            continue
        g_cost[node] = 0
        state["came"][node] = None
        heappush(state["open"], (_box_distance(tile, box), 0, node))
    return []


# Neighbour offsets in tile_key() space: (step, landing two tiles out).
_STEPS = ((_KEY_SPAN, 2 * _KEY_SPAN), (-_KEY_SPAN, -2 * _KEY_SPAN), (1, 2), (-1, -2))


def route_step(state, nodes=ROUTE_STEP_NODES):
    """Expands up to `nodes` tiles; True once the route is found or the search is exhausted."""
    if state["done"]:
        return True
    open_heap = state["open"]
    closed = state["closed"]
    blocked = state["blocked"]
    bridgeable = state["bridgeable"]
    soft = state["soft"]
    goals = state["goals"]
    g_cost = state["g"]
    came = state["came"]
    box = state["box"]
    for _ in range(nodes):
        if not open_heap or state["expanded"] >= state["max_nodes"]:
            state["done"] = True
            return True
        _f, cost, node = heappop(open_heap)
        if node in closed:
            continue
        closed.add(node)
        state["expanded"] += 1
        tile = node // 2
        if tile in goals:
            state["found"] = node
            state["done"] = True
            return True
        link = came[node]
        last_land = link[2] if link else None  # landing tile of the latest bridge on this path
        may_bridge = node % 2 == 0 and tile != last_land
        for offset, jump in _STEPS:
            nxt = tile + offset
            bridge_over = None
            if nxt in blocked:
                if not may_bridge or nxt not in bridgeable:
                    continue
                bridge_over = nxt
                nxt = tile + jump
                if nxt in blocked or nxt == last_land:
                    continue
                new_cost = cost + BRIDGE_COST
                nxt_node = nxt * 2 + 1
            else:
                new_cost = cost + STEP_COST
                nxt_node = nxt * 2
            if nxt_node in closed:
                continue
            if nxt in soft:
                new_cost += SOFT_TILE_COST
            if new_cost >= g_cost.get(nxt_node, new_cost + 1):
                continue
            g_cost[nxt_node] = new_cost
            came[nxt_node] = (node, bridge_over, nxt if bridge_over is not None else last_land)
            heappush(open_heap, (new_cost + _box_distance(nxt, box), new_cost, nxt_node))
    return False


def route_path(state):
    """
    Found route as a list of (tile, bridge_over) from the source tile to the
    goal tile; bridge_over is the tile a bridge hop crossed to reach `tile`,
    else None. Empty list when no route was found.
    """
    node = state["found"]
    if node is None:
        return []
    path = []
    while node is not None:
        link = state["came"][node]
        path.append((node // 2, link[1] if link else None))
        node = link[0] if link else None
    path.reverse()
    return path


def route(sources, goals, blocked, bridgeable=None, soft=None, max_nodes=ROUTE_MAX_NODES):
    """route_init() + route_step() to the end + route_path(), in one call (tests, small searches)."""
    state = route_init(sources, goals, blocked, bridgeable, soft, max_nodes)
    while not route_step(state):
        pass
    return route_path(state)


def path_plan(path):
    """
    Build steps for a route_path(): ("run", tile_a, tile_b) for each straight
    stretch of ordinary pieces and ("bridge", middle_tile, axis) for each bridge
    hop, in path order. axis is "horizontal" or "vertical". The first path tile
    is the existing network (or a terminal), so a path of one tile needs nothing.
    """
    steps = []
    run_start = None
    run_dir = None
    previous = None
    for tile, bridge_over in path:
        if previous is None:
            previous = tile
            continue
        if bridge_over is not None:
            if run_start is not None:
                steps.append(("run", run_start, previous))
            px = tile_xy(previous)[0]
            tx = tile_xy(tile)[0]
            steps.append(("bridge", bridge_over, "horizontal" if tx != px else "vertical"))
            run_start = None
            run_dir = None
            previous = tile
            continue
        px, py = tile_xy(previous)
        tx, ty = tile_xy(tile)
        direction = (tx - px, ty - py)
        if run_start is None:
            run_start = previous
            run_dir = direction
        elif direction != run_dir:
            steps.append(("run", run_start, previous))
            run_start = previous
            run_dir = direction
        previous = tile
    if run_start is not None:
        steps.append(("run", run_start, previous))
    return steps


def run_pieces(tile_a, tile_b):
    """Number of pieces a straight run between two tiles needs."""
    return manhattan(tile_a, tile_b)


def run_tiles(tile_a, tile_b):
    """Every tile of a straight run, both ends included."""
    ax, ay = tile_xy(tile_a)
    bx, by = tile_xy(tile_b)
    if ax == bx:
        step = 1 if by >= ay else -1
        return [tile_key(ax, y) for y in range(ay, by + step, step)]
    step = 1 if bx >= ax else -1
    return [tile_key(x, ay) for x in range(ax, bx + step, step)]


def bridge_tiles(middle, axis):
    """The three tiles a bridge covers."""
    tx, ty = tile_xy(middle)
    if axis == "horizontal":
        return [tile_key(tx - 1, ty), middle, tile_key(tx + 1, ty)]
    return [tile_key(tx, ty - 1), middle, tile_key(tx, ty + 1)]
