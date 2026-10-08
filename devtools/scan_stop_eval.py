"""
How often the pairing method for sonar scan stops misses a contact, on real world layouts.

The pairing method: contacts at most 2 x range apart pair up; pairs grow to triples and
beyond while every member pairs with every other, until no larger group exists (maximal
cliques); each group's stop is its middle. Pairwise 2 x range does not guarantee one point
within range of every member (an equilateral triple of side 2r needs 1.15r), and the middle
(centroid by default) need not be that point even when one exists. A group *fails* when its
middle leaves a member out of sonar range:
  - fixable: a point within range of every member exists (smallest enclosing circle fits),
    only the middle is wrong;
  - impossible: no single stop covers the group.
A contact is *missed* when no group holding it has a middle within range of it (a contact
paired with nobody is its own group and never missed). lib/scan_groups.py, the scouts'
planner, scores only points that cover their members, so it has no such failure.
Stop counts compare visiting every group, a greedy cover picked from the groups' middles,
and a greedy cover over contacts plus reach-circle crossings (lib/scan_groups.py's
candidates) as the reference.

Layouts: every map contact of a fresh world per seed, from the game's own generators
(node devtools/headless/sources.mjs --pois, needs node and the private internals/ submodule).
Biomass contacts count by default: every contact reads kind "unknown" until a sweep, so a
scout plans around them too; it drops one only after a sweep reports it wrong_scanner.
--no-biomass models a map where they are already known.

Usage: python devtools/scan_stop_eval.py --seeds 1-1000
       python devtools/scan_stop_eval.py --pois-file FILE.jsonl [--ranges 180,280] [--middle mec]
       options: --margin 1.0 (share of sonar range used), --no-biomass, --worst 5
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_MJS = os.path.join(REPO_ROOT, "devtools", "headless", "sources.mjs")
# Sonar range per tier, metres (docs/components/sonar_module.md).
SONAR_RANGES = {"basic": 50.0, "wide": 180.0, "deep": 280.0}
EPS = 1e-6


def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def pair_graph(points, reach):
    """Adjacency sets: i and j pair when they are less than 2 * reach apart."""
    adjacency = [set() for _ in points]
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            if dist(points[i], points[j]) < 2.0 * reach:
                adjacency[i].add(j)
                adjacency[j].add(i)
    return adjacency


def maximal_groups(adjacency):
    """Every maximal clique of the pair graph as a sorted index tuple (Bron-Kerbosch with pivot)."""
    groups = []
    stack = [(set(), set(range(len(adjacency))), set())]
    while stack:
        group, pending, done = stack.pop()
        if not pending and not done:
            groups.append(tuple(sorted(group)))
            continue
        pivot = max(pending | done, key=lambda u: len(pending & adjacency[u]))
        for v in sorted(pending - adjacency[pivot]):
            stack.append((group | {v}, pending & adjacency[v], done & adjacency[v]))
            pending = pending - {v}
            done = done | {v}
    return sorted(groups)


def _circle_two(a, b):
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, dist(a, b) / 2.0)


def _circle_three(a, b, c):
    d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < EPS:
        pairs = sorted([(a, b), (a, c), (b, c)], key=lambda pq: -dist(pq[0], pq[1]))
        return _circle_two(*pairs[0])
    a2 = a[0] ** 2 + a[1] ** 2
    b2 = b[0] ** 2 + b[1] ** 2
    c2 = c[0] ** 2 + c[1] ** 2
    x = (a2 * (b[1] - c[1]) + b2 * (c[1] - a[1]) + c2 * (a[1] - b[1])) / d
    y = (a2 * (c[0] - b[0]) + b2 * (a[0] - c[0]) + c2 * (b[0] - a[0])) / d
    return (x, y, dist((x, y), a))


def enclosing_circle(points):
    """Smallest circle (x, y, radius) holding every point (incremental Welzl)."""
    def inside(circle, p):
        return dist((circle[0], circle[1]), p) <= circle[2] + EPS

    circle = (points[0][0], points[0][1], 0.0)
    for i, p in enumerate(points):
        if inside(circle, p):
            continue
        circle = (p[0], p[1], 0.0)
        for j in range(i):
            q = points[j]
            if inside(circle, q):
                continue
            circle = _circle_two(p, q)
            for k in range(j):
                if not inside(circle, points[k]):
                    circle = _circle_three(p, q, points[k])
    return circle


def middle(points, how):
    """The group's stop: centroid (mean), bbox (bounding-box centre) or mec (smallest enclosing circle centre)."""
    if how == "centroid":
        return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
    if how == "bbox":
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
    circle = enclosing_circle(points)
    return (circle[0], circle[1])


def circle_crossings(a, b, reach):
    """The 0-2 points where circles of radius reach around a and b cross."""
    d = dist(a, b)
    if d < EPS or d > 2.0 * reach + EPS:
        return []
    h = max(0.0, reach * reach - d * d / 4.0) ** 0.5
    mx = (a[0] + b[0]) / 2.0
    my = (a[1] + b[1]) / 2.0
    ux = (b[0] - a[0]) / d
    uy = (b[1] - a[1]) / d
    return [(mx + uy * h, my - ux * h), (mx - uy * h, my + ux * h)]


def greedy_cover(sets, universe):
    """Stops greedy set cover takes: the set covering most uncovered first, until universe is covered."""
    left = set(universe)
    stops = 0
    while left:
        best = max(sets, key=lambda c: len(c & left))
        if not best & left:
            break
        left -= best
        stops += 1
    return stops


def crossing_cover(points, reach):
    """Greedy cover stops over every contact and every reach-circle crossing (the candidates lib/scan_groups.py scores)."""
    cands = list(points)
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            cands += circle_crossings(points[i], points[j], reach)
    sets = [frozenset(k for k, p in enumerate(points) if dist(c, p) <= reach + EPS) for c in cands]
    return greedy_cover(sets, range(len(points)))


def evaluate(points, reach, how="centroid"):
    """
    One layout at one sweep radius. Returns {"contacts", "groups" (size >= 2),
    "failed", "fixable", "impossible", "missed" (contacts), "by_size": {size: [groups, failed]},
    "stops_all" (every group a stop), "stops_cover" (greedy cover of the reached contacts
    from the groups' middles), "stops_crossing" (greedy cover from crossing candidates)}.
    """
    groups = maximal_groups(pair_graph(points, reach))
    reached = defaultdict(bool)
    out = {"contacts": len(points), "groups": 0, "failed": 0, "fixable": 0, "impossible": 0,
           "missed": 0, "by_size": defaultdict(lambda: [0, 0]), "stops_all": len(groups)}
    swept = []
    for group in groups:
        members = [points[i] for i in group]
        stop = middle(members, how)
        hit = [dist(stop, m) <= reach + EPS for m in members]
        swept.append(frozenset(i for i, ok in zip(group, hit) if ok))
        for i, ok in zip(group, hit):
            reached[i] = reached[i] or ok
        if len(group) < 2:
            continue
        out["groups"] += 1
        out["by_size"][len(group)][0] += 1
        if all(hit):
            continue
        out["failed"] += 1
        out["by_size"][len(group)][1] += 1
        if enclosing_circle(members)[2] <= reach + EPS:
            out["fixable"] += 1
        else:
            out["impossible"] += 1
    out["missed"] = sum(1 for i in range(len(points)) if not reached[i])
    out["stops_cover"] = greedy_cover(swept, [i for i in range(len(points)) if reached[i]])
    out["stops_crossing"] = crossing_cover(points, reach)
    return out


def load_layouts(args):
    """[(seed, [(x, y)])] from --pois-file or a sources.mjs --pois run."""
    if args.pois_file:
        with open(args.pois_file, encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]
    else:
        run = subprocess.run(["node", SOURCES_MJS, "--pois", args.seeds], capture_output=True, text=True,
                             encoding="utf-8", check=True, cwd=REPO_ROOT)
        lines = [line for line in run.stdout.splitlines() if line.strip()]
    layouts = []
    for line in lines:
        row = json.loads(line)
        pois = [(float(p["x"]), float(p["y"])) for p in row["pois"]
                if not args.no_biomass or p["kind"] != "biomass"]
        layouts.append((row["seed"], pois))
    return layouts


def pct(n, d):
    return f"{100.0 * n / d:5.1f}%" if d else "    -"


def report(layouts, reach_by_name, how, worst):
    for name, reach in reach_by_name.items():
        totals = Counter()
        by_size = defaultdict(lambda: [0, 0])
        seeds_failing = 0
        seeds_missing = 0
        per_seed = []
        for seed, points in layouts:
            r = evaluate(points, reach, how)
            for k in ("contacts", "groups", "failed", "fixable", "impossible", "missed",
                      "stops_all", "stops_cover", "stops_crossing"):
                totals[k] += r[k]
            for size, (g, f) in r["by_size"].items():
                by_size[size][0] += g
                by_size[size][1] += f
            seeds_failing += 1 if r["failed"] else 0
            seeds_missing += 1 if r["missed"] else 0
            per_seed.append((r["missed"], r["failed"], seed))
        n = len(layouts)
        print(f"\n{name} sonar, sweep radius {reach:.0f} m, middle = {how}, {n} seeds, "
              f"{totals['contacts'] / max(1, n):.0f} contacts per world")
        print(f"  groups (2+ contacts): {totals['groups'] / max(1, n):.1f} per world")
        print(f"  failed groups:  {pct(totals['failed'], totals['groups'])} of groups "
              f"(fixable by a better middle {pct(totals['fixable'], totals['groups'])}, "
              f"no single stop possible {pct(totals['impossible'], totals['groups'])})")
        print(f"  missed contacts: {totals['missed'] / max(1, n):.2f} per world "
              f"({pct(totals['missed'], totals['contacts'])} of contacts)")
        print(f"  stops per world: every group {totals['stops_all'] / max(1, n):.1f}, "
              f"greedy cover from the groups {totals['stops_cover'] / max(1, n):.1f} (missed contacts left out), "
              f"greedy cover from crossings {totals['stops_crossing'] / max(1, n):.1f} (all contacts)")
        print(f"  worlds with a failed group: {pct(seeds_failing, n)}, with a missed contact: {pct(seeds_missing, n)}")
        sizes = "  ".join(f"{s}: {pct(f, g).strip()} of {g}" for s, (g, f) in sorted(by_size.items()))
        print(f"  failed by group size: {sizes}")
        if worst:
            top = sorted(per_seed, reverse=True)[:worst]
            print("  worst seeds: " + ", ".join(f"{seed} ({m} missed, {f} failed)" for m, f, seed in top))


def main():
    ap = argparse.ArgumentParser(description="How often the pairing method for sonar scan stops misses a contact.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--seeds", help="seed range for sources.mjs --pois, e.g. 1-1000")
    src.add_argument("--pois-file", help="JSONL from sources.mjs --pois")
    ap.add_argument("--ranges", default="wide,deep",
                    help="sonar tiers (basic, wide, deep) or metres, comma separated (default wide,deep)")
    ap.add_argument("--margin", type=float, default=1.0, help="share of sonar range the stop may use (default 1.0)")
    ap.add_argument("--middle", choices=("centroid", "bbox", "mec"), default="centroid",
                    help="the group's stop (default centroid)")
    ap.add_argument("--no-biomass", action="store_true",
                    help="leave biomass contacts out (scouts know them only after a sweep blocked them)")
    ap.add_argument("--worst", type=int, default=5, help="list this many worst seeds per range (default 5)")
    args = ap.parse_args()
    reach_by_name = {}
    for item in args.ranges.split(","):
        item = item.strip()
        reach_by_name[item] = (SONAR_RANGES[item] if item in SONAR_RANGES else float(item)) * args.margin
    report(load_layouts(args), reach_by_name, args.middle, args.worst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
