# Scan stops for sonar scouts (pure, no game calls). One sweep classifies
# every contact within sonar range of the vehicle, so the scout picks where
# to stand by weighted contacts covered per metre, one stop at a time. A
# contact weighs 1 unless the caller passes weights (vehicle_survey.py gives
# contacts near an outpost OUTPOST_WEIGHT, so a lone one there can beat a
# far cluster):
#   1. candidate points: every contact, plus where two contacts' reach
#      circles cross (a point inside the most circles always sits at one);
#   2. each candidate covers the contacts within reach of it;
#   3. pull it back toward the vehicle as far as all those contacts stay in
#      reach (_pulled()); a single contact so only drives up to reach;
#   4. score = covered weight / (drive + SCAN_COST_M + HOME_WEIGHT * extra distance
#      from home), best first.
# vehicle_survey.survey_known_pois() drives to the best affordable stop,
# sweeps once and plans again from there: scans, peer claims and battery
# change after every sweep, so a whole tour planned ahead would go stale.
#
# Step cost: the game charges every interpreter step, so the plan avoids the
# naive O(n * deg^2) cover checks:
#   - "sweep" counts coverage of every crossing in O(deg log deg) per
#     contact i: a centre on i's reach circle covers neighbour j on one arc,
#     bounded by the two crossings of i's and j's circles; sorting the arc
#     ends by pseudo-angle (_angle(), no trig) and sweeping gives the covered
#     weight at every arc start;
#   - "exact" then computes member sets, pulls and scores best score bound
#     first (_bound()) and stops once the best stop found beats every bound
#     left, so the best stop is exact and the runners-up are the best seen;
#   - plan_stops_atomic() runs the phases as lib/atomic.py chunks
#     (plan_step(), each under ATOMIC_STEP_BUDGET, measured in
#     tests/test_scan_groups.py), so each chunk costs at most one tick.

from atomic import run_chunked

# Share of sonar range a stop may use: drive_to() stops within its precision,
# and the sweep counts a contact at exactly range (deobfuscated
# findSitesInRange: skip only when distance > range).
COVER_MARGIN = 0.85
# Fixed cost of one stop in metres of driving: brake, sweep, surveys, restart.
SCAN_COST_M = 50.0
# Share of a stop's added distance from home charged now: the return leg pays it.
HOME_WEIGHT = 0.3
# Weight of a contact within outposts.resource_assignment_range_m of an
# outpost (vehicle_survey.py): a mine there needs no long haul.
OUTPOST_WEIGHT = 3.0
# Input cap, nearest contacts first (distance / weight); the rest wait for a later plan.
MAX_CONTACTS = 30
# Stops returned, best first: the caller tries them against its energy budget.
TOP_STOPS = 8
ATOMIC_STEP_BUDGET = 4000   # worst-case interpreter operations allowed for one plan_step()
# Work per plan_step(), in neighbour visits: sized so the worst step stays under ATOMIC_STEP_BUDGET.
STEP_WORK = 60
# Sweep phase step size in estimated operations: per neighbour's arc events,
# per event in the sorted sweep (measured in tests/test_scan_groups.py).
SWEEP_OPS = 2400
SWEEP_OPS_NEIGHBOUR = 250
SWEEP_OPS_EVENT = 50
_EPS = 1e-6


def _dist(a, b):
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5


def _angle(dx, dy):
    """Pseudo-angle of (dx, dy) in [0, 4): increases with the true angle, no trig."""
    s = abs(dx) + abs(dy)
    if s < _EPS:
        return 0.0
    p = dy / s
    if dx < 0:
        return 2.0 - p
    if dy < 0:
        return 4.0 + p
    return p


def circle_crossings(a, b, reach):
    """
    The points where circles of radius reach around a and b cross: two, one
    when they touch, none when apart or concentric. Seen from a, the first
    lies clockwise of b, the second counter-clockwise.
    """
    d = _dist(a, b)
    if d < _EPS or d > 2.0 * reach + _EPS:
        return []
    half = d / 2.0
    h = max(0.0, reach * reach - half * half) ** 0.5
    mx = (a[0] + b[0]) / 2.0
    my = (a[1] + b[1]) / 2.0
    ux = (b[0] - a[0]) / d
    uy = (b[1] - a[1]) / d
    if h < _EPS:
        return [(mx, my)]
    return [(mx + uy * h, my - ux * h), (mx - uy * h, my + ux * h)]


def _pulled(point, members, start, reach2):
    """
    The point on point -> start closest to start that keeps every member
    within reach (reach2 = reach squared). Per member, |point + t * (start -
    point) - m|^2 <= reach2 is a quadratic in t, feasible at t = 0; its upper
    root bounds t.
    """
    dx = start[0] - point[0]
    dy = start[1] - point[1]
    a = dx * dx + dy * dy
    if a < _EPS:
        return (point[0], point[1])
    t = 1.0
    for m in members:
        fx = point[0] - m[0]
        fy = point[1] - m[1]
        b = fx * dx + fy * dy
        c = fx * fx + fy * fy - reach2
        root = (-b + max(0.0, b * b - a * c) ** 0.5) / a
        if root < t:
            t = root
    if t < 0.0:
        t = 0.0
    return (point[0] + dx * t, point[1] + dy * t)


def stop_cost(stand, start, home):
    """Metres charged for a stop: drive there, SCAN_COST_M, HOME_WEIGHT of the added distance from home."""
    cost = _dist(start, stand) + SCAN_COST_M
    if home is not None:
        cost += HOME_WEIGHT * (_dist(stand, home) - _dist(start, home))
    return max(1.0, cost)


def new_plan(points, reach, start, home=None, weights=None):
    """Plan state for plan_step(): the MAX_CONTACTS contacts nearest start, distance divided by weight (default 1 each)."""
    if weights is None:
        weights = [1] * len(points)
    order = sorted(range(len(points)), key=lambda i: _dist(start, points[i]) / weights[i])[:MAX_CONTACTS]
    return {
        "order": order,
        "pts": [(float(points[i][0]), float(points[i][1])) for i in order],
        "w": [weights[i] for i in order],
        "reach": reach,
        "reach2": reach * reach + _EPS,
        "start": (float(start[0]), float(start[1])),
        "home": home,
        "phase": "nbrs",
        "i": 0,
        "nbrs": [],
        "cands": [],
        "sw": None,
        "queue": None,
        "scored": {},
        "best": 0.0,
        "ranked": [],
        "items": None,
        "stops": None,
    }


def _bound_factor(state, i):
    """
    Highest score per unit of covered weight for a stop holding contact i:
    its stand lies within reach of i, and the home term takes back at most
    HOME_WEIGHT of the drive (triangle inequality). bound = weight * factor.
    """
    drive = max(0.0, _dist(state["start"], state["pts"][i]) - state["reach"])
    return 1.0 / max(1.0, (1.0 - HOME_WEIGHT) * drive + SCAN_COST_M)


def _sweep_begin(state, i):
    state["sw"] = {"j": 0, "events": [], "depth": state["w"][i], "own": 0, "factor": _bound_factor(state, i)}


def _sweep_events(state, i, budget):
    """
    Arc events of up to `budget` neighbours of contact i. A centre on i's
    reach circle covers neighbour j between the crossings of their circles
    (clockwise one first); depth (covered weight) starts at i's own weight
    plus every arc wrapping past angle 0 and every neighbour at i's own
    position.
    """
    pts = state["pts"]
    p = pts[i]
    reach = state["reach"]
    reach2 = state["reach2"]
    w = state["w"]
    sw = state["sw"]
    row = state["nbrs"][i]
    end = min(len(row), sw["j"] + budget)
    while sw["j"] < end:
        j = row[sw["j"]]
        sw["j"] += 1
        q = pts[j]
        dx = q[0] - p[0]
        dy = q[1] - p[1]
        if dx * dx + dy * dy <= reach2:
            sw["own"] += w[j]
        if j == i:
            continue
        crossings = circle_crossings(p, q, reach)
        if not crossings:
            sw["depth"] += w[j]
            continue
        enter = crossings[0]
        leave = crossings[-1]
        a0 = _angle(enter[0] - p[0], enter[1] - p[1])
        a1 = _angle(leave[0] - p[0], leave[1] - p[1])
        if a0 > a1:
            sw["depth"] += w[j]
        sw["events"].append((a0, 0, j, enter))
        sw["events"].append((a1, 1, j, enter))
    return sw["j"] >= len(row)


def _sweep_finish(state, i):
    """Appends (-bound, -weight, point, i) for contact i itself and the coverage at every arc start."""
    sw = state["sw"]
    factor = sw["factor"]
    cands = state["cands"]
    w = state["w"]
    own = sw["own"]
    cands.append((-own * factor, -own, state["pts"][i], i))
    events = sorted(sw["events"])
    depth = sw["depth"]
    for e in events:
        if e[1] == 0:
            depth += w[e[2]]
            cands.append((-depth * factor, -depth, e[3], i))
        else:
            depth -= w[e[2]]
    state["sw"] = None


def _covered(point, i, state):
    """Sorted local indices within reach of point; a point within reach of contact i only reaches i's neighbours."""
    pts = state["pts"]
    reach2 = state["reach2"]
    px = point[0]
    py = point[1]
    out = []
    for j in state["nbrs"][i]:
        q = pts[j]
        dx = q[0] - px
        dy = q[1] - py
        if dx * dx + dy * dy <= reach2:
            out.append(j)
    return tuple(out)


def _score(state, key, point):
    """Pull point toward start, score it, keep the best stop per member set."""
    if not key:
        return
    pts = state["pts"]
    start = state["start"]
    w = state["w"]
    stand = _pulled(point, [pts[k] for k in key], start, state["reach2"])
    score = sum([w[k] for k in key]) / stop_cost(stand, start, state["home"])
    old = state["scored"].get(key)
    if old is None or score > old[0]:
        state["scored"][key] = (score, stand)
    if score > state["best"]:
        state["best"] = score


def plan_step(state):
    """One bounded chunk of planning (about STEP_WORK neighbour visits); True when done."""
    pts = state["pts"]
    n = len(pts)
    work = 0
    if state["phase"] == "nbrs":
        # nbrs[i]: contacts within 2 * reach of i, i included, sorted.
        limit2 = 4.0 * state["reach"] * state["reach"] + _EPS
        while state["i"] < n and work < STEP_WORK:
            p = pts[state["i"]]
            row = []
            for j in range(n):
                q = pts[j]
                dx = q[0] - p[0]
                dy = q[1] - p[1]
                if dx * dx + dy * dy <= limit2:
                    row.append(j)
            state["nbrs"].append(row)
            work += n
            state["i"] += 1
        if state["i"] >= n:
            state["phase"] = "sweep"
            state["i"] = 0
        return False
    if state["phase"] == "sweep":
        # Per contact: arc events in neighbour chunks, then one sorted sweep;
        # work here counts estimated operations (SWEEP_OPS_* per item).
        while work < SWEEP_OPS:
            i = state["i"]
            if i >= n:
                state["phase"] = "exact"
                state["i"] = 0
                return False
            if state["sw"] is None:
                _sweep_begin(state, i)
            sw = state["sw"]
            if sw["j"] < len(state["nbrs"][i]):
                budget = (SWEEP_OPS - work) // SWEEP_OPS_NEIGHBOUR
                if budget < 1:
                    return False
                before = sw["j"]
                _sweep_events(state, i, budget)
                work += (sw["j"] - before) * SWEEP_OPS_NEIGHBOUR
                continue
            cost = len(sw["events"]) * SWEEP_OPS_EVENT + SWEEP_OPS_NEIGHBOUR
            if work and work + cost > SWEEP_OPS:
                return False
            _sweep_finish(state, i)
            work += cost
            state["i"] += 1
        return False
    if state["phase"] == "exact":
        if state["queue"] is None:
            # Ties break on count, then on the point itself; i never decides.
            state["queue"] = sorted(state["cands"])
            return False
        queue = state["queue"]
        while work < STEP_WORK:
            if state["i"] >= len(queue) or (state["scored"] and state["best"] >= -queue[state["i"]][0]):
                state["phase"] = "rank"
                state["i"] = 0
                return False
            c = queue[state["i"]]
            key = _covered(c[2], c[3], state)
            _score(state, key, c[2])
            work += len(state["nbrs"][c[3]]) + 3 * len(key) + 5
            state["i"] += 1
        return False
    if state["phase"] == "rank":
        if state["items"] is None:
            state["items"] = list(state["scored"].items())
        items = state["items"]
        while state["i"] < len(items) and work < STEP_WORK:
            key, entry = items[state["i"]]
            state["ranked"].append((-entry[0], -len(key), key, entry[1]))
            work += 1
            state["i"] += 1
        if state["i"] >= len(items):
            state["phase"] = "out"
        return False
    ranked = sorted(state["ranked"])[:TOP_STOPS]
    order = state["order"]
    state["stops"] = [
        {"members": [order[k] for k in r[2]], "stand": r[3], "score": -r[0]}
        for r in ranked
    ]
    return True


def plan_stops(points, reach, start, home=None, weights=None):
    """
    Scan stops for `points` ((x, y) tuples, `weights` one number each,
    default 1) and a sweep of radius `reach` (already margined), seen from
    `start`. Returns up to TOP_STOPS
    [{"members": [index into points], "stand": (x, y), "score": float}],
    best score first; one stop per distinct member set (the cheapest).
    Only the first is meant to be driven: plan again after its sweep.
    Runs inline; in game use plan_stops_atomic().
    """
    state = new_plan(points, reach, start, home, weights)
    while not plan_step(state):
        pass
    return state["stops"]


def plan_stops_atomic(points, reach, start, home=None, weights=None):
    """plan_stops() as lib/atomic.py chunks: each plan_step() costs at most one tick."""
    state = new_plan(points, reach, start, home, weights)
    run_chunked(plan_step, state)
    return state["stops"]
