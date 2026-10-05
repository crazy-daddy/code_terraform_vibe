# Site scoring of the outpost founding planner (docs/plans/outpost_founding_planner.md):
# where on the map a founding bundle (outpost_needs.found_bundles()) should go.
#
# Placement rules (simworker plan_structure("outpost") checks, cheatsheet §11i):
#   - The anchor (x, y) is the footprint's NW corner; world y grows north. The
#     placement square is PLACE_M wide: x .. x + PLACE_M, y - PLACE_M .. y,
#     centre (x + PLACE_M / 2, y - PLACE_M / 2).
#   - Clearance is measured from a point to the CLEAR_SIDE_M square around the
#     centre: other outposts (their centre, ghosts too) OUTPOST_CLEARANCE_M,
#     every point of interest (unknown, scanned, biomass) POI_CLEARANCE_M.
#   - The outpost's biome is the biome at the anchor point.
#   - A bundle that keeps a pipe buffer (autoplay_roles.keeps_buffer(): the
#     storage outpost) also needs its footprint and the STORAGE_BUFFER_TILES
#     around it free of pipes and pipe jobs (ctx "pipes", pipe_blocks()).
#
# Knowledge levels per contact (in-game data only, no world knowledge):
#   1  nocturna.points_of_interest() contact, kind "unknown"
#   2  kind known (journal.discovered_sites(), a scanned POI kind, or biomass
#      from a sonar "wrong_scanner" verdict: survey_requests.known_biomass()), details None
#   3  journal surveyed site: ore item, purity, hardness, exact fluid
# Level 1-2 contacts count by expected value. The prior comes from this save's
# own scans: kind shares over every contact with a known kind, ore and exotic
# fluid shares over the surveyed ones; flat when nothing is known.
#
# Score (higher better, weights in WEIGHTS):
#   ore      per bundle ore (the need's ores, out of every outpost's range):
#            surveyed sites within range_m of the centre by purity factor
#            (HARD_FACTOR when no available drill kit cuts it), capped at
#            ORE_CAP per ore. Less-known contacts add their expected value on
#            top (discovered mineral: P(ore | mineral) x mean purity; unknown:
#            P(mineral) x that), up to ORE_CAP x ores.
#   fluid    per wanted field fluid (the bundle's "in" fluids with a site kind):
#            best contact within NEAR_TILES of the centre, closeness 1 .. 0.
#   exotic   raw exotic deposits within NEAR_TILES (a later refinery role), capped at 1.
#   biosite  biomass contacts within BIOSITE_RANGE_M in the bundle's biome,
#            unknown contacts by P(biomass), capped at BIOSITE_CAP.
#   margin   biome-locked bundles: share of the MARGIN_PROBES_M rings around
#            the anchor that hold only its biome (a site near a border scores lower).
#   room     share of the MARGIN_DIRS probe points at ROOM_M that are on the map and
#            clear of other outposts (land for later extractors).
#   home / grid  penalties per km to the home centre and to the nearest
#            outpost (power line and pipe length to the network).
# confidence = share of the resource terms (ore, fluid, exotic, biosite) from
# known contacts (surveyed; a fluid its kind tells; a bio-scanned biosite);
# under MIN_CONFIDENCE the site wants a survey trip first. A contact the scouts
# cannot resolve now (survey_requests.blocked_targets()) adds no guess, so it
# never holds a site in "survey first".
#
# Search: a CANDIDATE_STEP_M grid over the map, filtered (bounds, clearance,
# biome lock), scored without margin and room; the best REFINE_TOP are
# re-searched on a REFINE_STEP_M grid within REFINE_RADIUS_M; the best of
# those get the margin and room terms (add_detail()).
# Every heavy step runs in atomic slices (lib/atomic.py run_batched /
# run_chunked); scoring goes in score_step() chunks of STEP_UNITS work units,
# resumable mid-anchor, so contact density never overruns a slice. Sizes are
# measured by tests/test_autoplay_outpost_sites.py against ATOMIC_STEP_BUDGET.

from atomic import run_batched, run_chunked
from swallow import swallowed
from supply_tiers import NEAR_TILES
from grid_geom import TILE_M, outpost_box, buffer_box
from autoplay_roles import role_flag, fluids_for, keeps_buffer, STORAGE_BUFFER_TILES
from outpost_mining import RAW_ORE_ITEM_IDS
from extractor_plan import DRILL_KINDS
from survey_requests import read_known_biomass, read_blocked
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_console import TreeConsole

OUTPOST_CLEARANCE_M = 40   # simworker plan.outpostClearanceM
POI_CLEARANCE_M = 20       # simworker plan.outpostPoiClearanceM
PLACE_M = 20               # outpost placement square (2x2 tiles)
CLEAR_SIDE_M = 26          # square the clearance is measured to (simworker icon size, at least PLACE_M)

CANDIDATE_STEP_M = 80      # coarse candidate grid
REFINE_STEP_M = 20         # refine grid around the best coarse candidates
REFINE_RADIUS_M = 40       # refine window half-width
REFINE_TOP = 5             # coarse candidates refined
CELL_M = 150               # contact bucket size

BIOSITE_RANGE_M = 300      # biomass contacts a bio / liquifier outpost counts
FLUID_RANGE_M = NEAR_TILES * TILE_M
ORE_CAP = 2.0              # per ore: two good sites are enough
BIOSITE_CAP = 6.0
EXOTIC_VALUE = 0.25        # per raw exotic deposit in reach (exotic term capped at 1)
HARD_FACTOR = 0.2          # value of a surveyed ore site no available drill kit cuts
PURITY_FACTOR = {"standard": 1.0, "rich": 1.5, "pure": 2.0}
MARGIN_PROBES_M = (20, 40, 80, 160)
MARGIN_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (0.7, -0.7), (-0.7, 0.7), (-0.7, -0.7))
ROOM_M = 100
MIN_CONFIDENCE = 0.5

WEIGHTS = {"ore": 10.0, "fluid": 6.0, "exotic": 1.0, "biosite": 2.0, "margin": 4.0, "room": 2.0,
           "home": -2.0, "grid": -3.0}
RESOURCE_TERMS = ("ore", "fluid", "exotic", "biosite")

FILTER_CHUNK = 4           # candidates per atomic filter slice
STEP_UNITS = 50            # work units (~45 operations each) per atomic score_step() call
ROW_UNITS = 3              # per contact row accumulated (~135 operations at worst)
CELL_UNITS = 1             # per bucket cell visited (~50 operations)
START_UNITS = 4            # per anchor started (~150 operations)
FINISH_UNITS = 14          # per anchor finished (~600 operations)
DETAIL_CHUNK = 1           # candidates per atomic add_detail() slice (margin + room)
VALUE_CHUNK = 20           # contacts per atomic value_rows() slice
PIPE_BLOCK_TILES = 4       # pipe tiles bucketed in square blocks of this many tiles per side

# Site kind -> field fluid for non-exotic kinds (known from the kind alone).
KIND_FLUID = {"water": "water", "oil": "oil", "thermal": "steam"}
RAW_EXOTICS = ("raw_sulfur_gas", "raw_chlorine", "raw_cryofluid", "raw_quicksilver")
SITE_KINDS = ("mineral", "thermal", "water", "oil", "exotic", "biomass", "inert")


# --- geometry ---

def centre(x, y):
    """Centre of the placement square anchored at (x, y) (NW corner, y north)."""
    half = PLACE_M / 2
    return (x + half, y - half)


def _dist(ax, ay, bx, by):
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _rect_dist(px, py, cx, cy, half):
    """Distance from point (px, py) to the square of half-side `half` around (cx, cy); 0 inside."""
    dx = abs(px - cx) - half
    dy = abs(py - cy) - half
    dx = dx if dx > 0 else 0
    dy = dy if dy > 0 else 0
    return (dx * dx + dy * dy) ** 0.5


def in_bounds(x, y, bounds):
    """True when the placement square anchored at (x, y) lies inside bounds (min_x, max_x, min_y, max_y)."""
    return x >= bounds[0] and x + PLACE_M <= bounds[1] and y - PLACE_M >= bounds[2] and y <= bounds[3]


def grid(bounds, step, x0=None, x1=None, y0=None, y1=None):
    """Anchors on a `step` grid (multiples of TILE_M) inside bounds, optionally limited to a window."""
    lo_x = bounds[0] if x0 is None else max(bounds[0], x0)
    hi_x = bounds[1] - PLACE_M if x1 is None else min(bounds[1] - PLACE_M, x1)
    lo_y = bounds[2] + PLACE_M if y0 is None else max(bounds[2] + PLACE_M, y0)
    hi_y = bounds[3] if y1 is None else min(bounds[3], y1)
    start_x = -((-lo_x) // TILE_M) * TILE_M
    start_y = -((-lo_y) // TILE_M) * TILE_M
    out = []
    x = start_x
    while x <= hi_x:
        y = start_y
        while y <= hi_y:
            out.append((x, y))
            y += step
        x += step
    return out


# --- buckets ---

def _cell(x, y):
    return (int(x // CELL_M), int(y // CELL_M))


def bucket(rows):
    """{cell: [row, ...]} of rows with "x"/"y", CELL_M cells."""
    out = {}
    for row in rows:
        out.setdefault(_cell(row["x"], row["y"]), []).append(row)
    return out


def near(buckets, x, y, radius):
    """Rows of `buckets` within `radius` of (x, y) as (distance, row)."""
    out = []
    for i in range(int((x - radius) // CELL_M), int((x + radius) // CELL_M) + 1):
        for j in range(int((y - radius) // CELL_M), int((y + radius) // CELL_M) + 1):
            for row in buckets.get((i, j), ()):
                d = ((x - row["x"]) ** 2 + (y - row["y"]) ** 2) ** 0.5
                if d <= radius:
                    out.append((d, row))
    return out


# --- contacts and priors ---

def contacts(pois, sites, blocked=None):
    """
    Contact rows {"x", "y", "level", "kind", "item", "purity", "hardness", "fluid", "stuck"}
    from POI rows {"x", "y", "kind"} and site rows (site_rows()); a site wins
    over the POI at its position. blocked = survey_requests.blocked_targets()
    ({(x, y) whole meters}, {site id}): an unsurveyed contact in it is "stuck"
    (no scout resolves it with what is unlocked now).
    """
    pois_blocked, sites_blocked = blocked if blocked else (set(), set())
    out = []
    taken = set()
    for site in sites:
        level = 3 if site.get("surveyed") else 2
        kind = site.get("kind")
        fluid = site.get("fluid") if level == 3 else None
        if fluid is None:
            fluid = KIND_FLUID.get(kind)
        spot = (int(round(site["x"])), int(round(site["y"])))
        out.append({"x": site["x"], "y": site["y"], "level": level, "kind": kind,
                    "item": site.get("item") if level == 3 else None, "purity": site.get("purity"),
                    "hardness": site.get("hardness"), "fluid": fluid,
                    "stuck": level < 3 and (site.get("id") in sites_blocked or spot in pois_blocked)})
        taken.add(spot)
    for poi in pois:
        spot = (int(round(poi["x"])), int(round(poi["y"])))
        if spot in taken:
            continue
        kind = poi.get("kind") or "unknown"
        out.append({"x": float(poi["x"]), "y": float(poi["y"]), "level": 1 if kind == "unknown" else 2,
                    "kind": None if kind == "unknown" else kind, "item": None, "purity": None,
                    "hardness": None, "fluid": KIND_FLUID.get(kind), "stuck": spot in pois_blocked})
    return out


def _shares(values, keys):
    counts = {}
    for value in values:
        if value in keys:
            counts[value] = counts.get(value, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return {key: 1.0 / len(keys) for key in keys}
    return {key: counts.get(key, 0) / total for key in keys}


def priors(rows):
    """
    {"kind": {kind: share}, "ore": {ore: share}, "exotic": {fluid: share},
     "purity": mean purity factor} from this save's own contacts; flat when
    nothing is known.
    """
    known = [row["kind"] for row in rows if row["level"] >= 2]
    surveyed = [row for row in rows if row["level"] == 3]
    ores = [row["item"] for row in surveyed if row["kind"] == "mineral"]
    factors = [PURITY_FACTOR.get(row["purity"], 1.0) for row in surveyed if row["kind"] == "mineral"]
    return {"kind": _shares(known, SITE_KINDS), "ore": _shares(ores, RAW_ORE_ITEM_IDS),
            "exotic": _shares([row["fluid"] for row in surveyed if row["kind"] == "exotic"], RAW_EXOTICS),
            "purity": sum(factors) / len(factors) if factors else 1.0}


def ore_value(row, ore, prior, hardness_limit):
    """(expected value, surveyed?) of a contact for `ore`."""
    if row["level"] == 3:
        if row["kind"] != "mineral" or row["item"] != ore:
            return (0.0, True)
        value = PURITY_FACTOR.get(row["purity"], 1.0)
        hard = row["hardness"]
        if hardness_limit is not None and hard is not None and hard > hardness_limit:
            value *= HARD_FACTOR
        return (value, True)
    share = prior["ore"].get(ore, 0.0) * prior["purity"]
    if row["level"] == 2:
        return (share if row["kind"] == "mineral" else 0.0, False)
    return (prior["kind"].get("mineral", 0.0) * share, False)


def fluid_value(row, fluid, prior):
    """(probability the contact yields `fluid`, surveyed?)."""
    if row["fluid"] is not None:
        return (1.0 if row["fluid"] == fluid else 0.0, row["level"] == 3)
    if row["level"] == 3:
        return (0.0, True)
    if fluid.startswith("raw_"):
        p_exotic = prior["exotic"].get(fluid, 0.0)
        if row["level"] == 2:
            return (p_exotic if row["kind"] == "exotic" else 0.0, False)
        return (prior["kind"].get("exotic", 0.0) * p_exotic, False)
    if row["level"] == 2:
        return (0.0, False)
    for kind, kind_fluid in KIND_FLUID.items():
        if kind_fluid == fluid:
            return (prior["kind"].get(kind, 0.0), False)
    return (0.0, False)


# --- bundle wants ---

def field_fluids():
    """Fluids a field site can yield: KIND_FLUID values and the raw exotics."""
    return list(KIND_FLUID.values()) + list(RAW_EXOTICS)


def wants(bundle, role_presets):
    """
    {"ores", "fluids", "biosites", "biome", "clear"} a founding bundle looks for:
    its need's ores, the field fluids its roles take and do not make,
    biosites when a role collects life (bio_ / liquifier_), clear land
    without pipes when it keeps a pipe buffer (keeps_buffer()).
    """
    fluids = fluids_for(bundle.get("roles", []), role_presets)
    field = field_fluids()
    wanted = [fluid for fluid in fluids["in"] if fluid in field and fluid not in fluids["out"]]
    return {"ores": list(bundle.get("ores", [])), "fluids": wanted, "biome": bundle.get("biome"),
            "biosites": any(role_flag(name, "biosites") for name in bundle.get("roles", [])),
            "clear": keeps_buffer(bundle.get("roles", []))}


# --- context ---

def prepare(world, biome_at):
    """
    Scoring context from a world snapshot (read_world()):
      {"bounds", "outposts": [{"id", "x", "y", "home", "depot"}], "ghosts": [(x, y)],
       "pois": [{"x", "y", "kind"}], "sites": site_rows(), "range_m", "hardness_limit",
       "blocked" (survey_requests.blocked_targets(), optional),
       "pipes": [(tx, ty), ...] pipe and pipe-job tiles (optional, read for buffer bundles)}
    biome_at(x, y): the game's nocturna.biome_at (a read, atomic-safe);
    answers are cached per TILE_M tile.
    """
    rows = contacts(world.get("pois", []), world.get("sites", []), world.get("blocked"))
    centres = [centre(entry["x"], entry["y"]) for entry in world.get("outposts", [])]
    centres.extend([centre(x, y) for x, y in world.get("ghosts", [])])
    home = [centre(entry["x"], entry["y"]) for entry in world.get("outposts", []) if entry.get("home")]
    return {"bounds": world["bounds"], "range_m": world.get("range_m", 200.0),
            "hardness_limit": world.get("hardness_limit"),
            "rows": rows, "prior": priors(rows),
            "pois": bucket([{"x": float(poi["x"]), "y": float(poi["y"])} for poi in world.get("pois", [])]),
            "outposts": bucket([{"x": cx, "y": cy} for cx, cy in centres]),
            "centres": centres, "home": home[0] if home else None,
            "pipes": pipe_blocks(world.get("pipes", [])),
            "biome_at": biome_at, "biomes": {}}


def biome(ctx, x, y):
    """Biome at (x, y), cached per tile; None when unreadable."""
    key = (int(x // TILE_M), int(y // TILE_M))
    cache = ctx["biomes"]
    if key not in cache:
        try:
            cache[key] = ctx["biome_at"](x, y)
        except Exception as error:
            swallowed("outpost_sites.biome: biome_at", error)
            cache[key] = None
    return cache[key]


def pipe_blocks(tiles):
    """{(bx, by): [(tx, ty), ...]} of pipe tiles in PIPE_BLOCK_TILES square blocks."""
    out = {}
    for tx, ty in tiles:
        out.setdefault((tx // PIPE_BLOCK_TILES, ty // PIPE_BLOCK_TILES), []).append((tx, ty))
    return out


def pipe_near(blocks, x, y, width=STORAGE_BUFFER_TILES):
    """True when a pipe tile lies on the footprint anchored at (x, y) or within `width` tiles of it."""
    tx0, ty0, tx1, ty1 = buffer_box(outpost_box(x, y), width)
    for bx in range(tx0 // PIPE_BLOCK_TILES, tx1 // PIPE_BLOCK_TILES + 1):
        for by in range(ty0 // PIPE_BLOCK_TILES, ty1 // PIPE_BLOCK_TILES + 1):
            for tx, ty in blocks.get((bx, by), ()):
                if tx0 <= tx <= tx1 and ty0 <= ty <= ty1:
                    return True
    return False


def check(ctx, x, y, want_biome=None, clear=False):
    """
    None when an outpost may stand at anchor (x, y), else the reason
    (out_of_bounds, outpost_clearance, poi_clearance, biome <id>, pipe_buffer).
    clear: the bundle keeps a pipe buffer (pipe_near()).
    """
    if not in_bounds(x, y, ctx["bounds"]):
        return "out_of_bounds"
    cx, cy = centre(x, y)
    half = CLEAR_SIDE_M / 2
    reach = OUTPOST_CLEARANCE_M + half * 2
    for _d, row in near(ctx["outposts"], cx, cy, reach):
        if _rect_dist(row["x"], row["y"], cx, cy, half) < OUTPOST_CLEARANCE_M:
            return "outpost_clearance"
    for _d, row in near(ctx["pois"], cx, cy, POI_CLEARANCE_M + half * 2):
        if _rect_dist(row["x"], row["y"], cx, cy, half) < POI_CLEARANCE_M:
            return "poi_clearance"
    if want_biome is not None:
        found = biome(ctx, x, y)
        if found != want_biome:
            return "biome " + str(found)
    if clear and pipe_near(ctx.get("pipes", {}), x, y):
        return "pipe_buffer"
    return None


def filter_slice(anchors, ctx, want_biome, clear=False):
    """Anchors of a slice that pass check() (atomic-safe: reads and own caches only)."""
    return [anchor for anchor in anchors if check(ctx, anchor[0], anchor[1], want_biome, clear) is None]


# --- scoring ---

def value_rows(rows, ctx, want):
    """
    Valued contacts of a slice for `want` as tuples, rows worth nothing
    dropped (atomic-safe). Tuple fields (VALUE_FIELDS order); one value per
    term keeps the scoring cost per row flat:
      x, y             contact position
      ore, ore_sure    the surveyed site's wanted ore and its value (None, 0 otherwise)
      ore_guess        expected value of a less-known contact, summed over the wanted ores
      fluid            the wanted fluid the contact is known to yield (the kind tells
                       water / oil / steam; a surveyed exotic its fluid), else None
      fluid_guess      chance an unknown contact yields a wanted fluid, summed over them
      exotic           (sure, guess) raw exotic deposit not wanted itself
      bio              (known, guess) biosite in the bundle's biome; a contact of
                       known kind biomass (bio-scanned) counts as known
    A stuck contact (contacts()) adds no guess: it is surveyed as far as the
    scouts get, so it neither lifts the score nor asks for a survey.
    """
    out = []
    prior = ctx["prior"]
    limit = ctx["hardness_limit"]
    p_bio = prior["kind"].get("biomass", 0.0)
    for row in rows:
        ore = None
        ore_sure = 0.0
        ore_guess = 0.0
        if row["level"] == 3:
            if row["kind"] == "mineral" and row["item"] in want["ores"]:
                ore = row["item"]
                ore_sure = ore_value(row, ore, prior, limit)[0]
        else:
            ore_guess = sum([ore_value(row, item, prior, limit)[0] for item in want["ores"]])
        fluid = None
        fluid_guess = 0.0
        if row["fluid"] is not None:
            fluid = row["fluid"] if row["fluid"] in want["fluids"] else None
        elif row["level"] < 3:
            fluid_guess = sum([fluid_value(row, name, prior)[0] for name in want["fluids"]])
        exotic = (0.0, 0.0)
        if row["fluid"] and row["fluid"].startswith("raw_") and fluid is None:
            exotic = (EXOTIC_VALUE, 0.0)
        elif row["kind"] == "exotic" and row["fluid"] is None:
            exotic = (0.0, EXOTIC_VALUE)
        bio = (0.0, 0.0)
        if want["biosites"] and (row["level"] == 1 or row["kind"] == "biomass"):
            if want["biome"] is None or biome(ctx, row["x"], row["y"]) == want["biome"]:
                bio = (1.0, 0.0) if row["level"] >= 2 else (0.0, p_bio)
        if row.get("stuck"):
            ore_guess = 0.0
            fluid_guess = 0.0
            exotic = (exotic[0], 0.0)
            bio = (bio[0], 0.0)
        if ore_sure > 0 or ore_guess > 0 or fluid is not None or fluid_guess > 0 \
                or exotic[0] + exotic[1] > 0 or bio[0] + bio[1] > 0:
            out.append((row["x"], row["y"], ore, ore_sure, ore_guess, fluid, fluid_guess,
                        exotic[0], exotic[1], bio[0], bio[1]))
    return out


def prepare_want(ctx, want):
    """`want` (wants()) with its valued contacts bucketed ("valued") and the widest term range ("radius")."""
    out = dict(want)
    cells = {}
    for row in run_batched(value_rows, ctx["rows"], VALUE_CHUNK, ctx, want):
        cells.setdefault(_cell(row[0], row[1]), []).append(row)
    out["valued"] = cells
    radius = FLUID_RANGE_M
    if want["ores"]:
        radius = max(radius, ctx["range_m"])
    if want["biosites"]:
        radius = max(radius, BIOSITE_RANGE_M)
    out["radius"] = radius
    return out


def _capped(sure, maybe, cap):
    total = sure + maybe
    if total > cap:
        return (sure * cap / total, maybe * cap / total)
    return (sure, maybe)


def _topped(sure, guess, cap):
    """(sure, guess) with the guess cut so both stay within cap (sure values are capped by the caller)."""
    room = cap - sure
    return (sure, guess if guess < room else (room if room > 0 else 0.0))


def _nearest(points, x, y):
    best = None
    for px, py in points:
        d = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
        if best is None or d < best:
            best = d
    return best


def score_init(ctx, anchors, want):
    """State for score_step(): every anchor of `anchors` scored in turn into state["out"]; want = prepare_want()."""
    return {"ctx": ctx, "want": want, "anchors": list(anchors), "next": 0, "acc": None, "out": []}


def _start(state):
    """Accumulator for the next anchor: its cell window and empty term sums."""
    x, y = state["anchors"][state["next"]]
    state["next"] += 1
    cx, cy = centre(x, y)
    radius = state["want"]["radius"]
    i0 = int((cx - radius) // CELL_M)
    j0 = int((cy - radius) // CELL_M)
    nj = int((cy + radius) // CELL_M) - j0 + 1
    cells = (int((cx + radius) // CELL_M) - i0 + 1) * nj
    state["acc"] = {"x": x, "y": y, "cx": cx, "cy": cy, "i0": i0, "j0": j0, "nj": nj, "cells": cells,
                    "cell": 0, "row": 0, "ore_sure": {}, "ore_guess": 0.0, "fluid_best": {}, "fluid_guess": 0.0,
                    "exotic": [0.0, 0.0], "bio": [0.0, 0.0]}


def _accumulate(acc, rows, reach2):
    """Adds valued rows (value_rows() tuples) within their term ranges of the anchor to its sums."""
    cx = acc["cx"]
    cy = acc["cy"]
    ore_sure = acc["ore_sure"]
    fluid_best = acc["fluid_best"]
    exotic = acc["exotic"]
    bio = acc["bio"]
    fluid2 = FLUID_RANGE_M * FLUID_RANGE_M
    bio2 = BIOSITE_RANGE_M * BIOSITE_RANGE_M
    for x0, y0, ore, sure, guess, fluid, f_guess, ex_sure, ex_guess, bio_known, bio_guess in rows:
        d2 = (cx - x0) * (cx - x0) + (cy - y0) * (cy - y0)
        if d2 <= reach2:
            if ore is not None:
                ore_sure[ore] = ore_sure.get(ore, 0.0) + sure
            acc["ore_guess"] += guess
        if d2 <= fluid2:
            close = 1.0 - d2 ** 0.5 / FLUID_RANGE_M
            if fluid is not None and close > fluid_best.get(fluid, 0.0):
                fluid_best[fluid] = close
            acc["fluid_guess"] += f_guess * close
            exotic[0] += ex_sure
            exotic[1] += ex_guess
        if d2 <= bio2:
            bio[0] += bio_known
            bio[1] += bio_guess


def _finish(ctx, acc, want):
    """score() row of a finished accumulator."""
    cx = acc["cx"]
    cy = acc["cy"]
    sure = sum([value if value < ORE_CAP else ORE_CAP for value in acc["ore_sure"].values()])
    raw = {"ore": _topped(sure, acc["ore_guess"], ORE_CAP * len(want["ores"])),
           "fluid": _topped(sum(acc["fluid_best"].values()), acc["fluid_guess"], len(want["fluids"])),
           "exotic": _capped(acc["exotic"][0], acc["exotic"][1], 1.0)}
    sure, maybe = _capped(acc["bio"][0], acc["bio"][1], BIOSITE_CAP)
    raw["biosite"] = (sure / BIOSITE_CAP, maybe / BIOSITE_CAP)
    terms = {}
    known = 0.0
    guess = 0.0
    for name in RESOURCE_TERMS:
        sure, maybe = raw[name]
        terms[name] = WEIGHTS[name] * (sure + maybe)
        known += WEIGHTS[name] * sure
        guess += WEIGHTS[name] * maybe
    home = ctx["home"]
    terms["home"] = WEIGHTS["home"] * (_dist(cx, cy, home[0], home[1]) / 1000.0 if home else 0.0)
    terms["grid"] = WEIGHTS["grid"] * ((_nearest(ctx["centres"], cx, cy) or 0.0) / 1000.0)
    resource = known + guess
    return {"x": acc["x"], "y": acc["y"], "score": sum(terms.values()), "terms": terms,
            "confidence": known / resource if resource > 0 else 1.0}


def score_step(state):
    """
    One bounded chunk of scoring (lib/atomic.py run_chunked()): up to
    STEP_UNITS work units (ROW_UNITS per contact row, CELL_UNITS per bucket
    cell, START_UNITS / FINISH_UNITS per anchor); resumes mid-cell.
    Returns True once every anchor is scored.
    """
    ctx = state["ctx"]
    want = state["want"]
    valued = want["valued"]
    reach2 = ctx["range_m"] * ctx["range_m"]
    units = 0
    while units < STEP_UNITS:
        acc = state["acc"]
        if acc is None:
            if state["next"] >= len(state["anchors"]):
                return True
            _start(state)
            units += START_UNITS
            continue
        if acc["cell"] >= acc["cells"]:
            state["out"].append(_finish(ctx, acc, want))
            state["acc"] = None
            units += FINISH_UNITS
            continue
        nj = acc["nj"]
        rows = valued.get((acc["i0"] + acc["cell"] // nj, acc["j0"] + acc["cell"] % nj), ())
        units += CELL_UNITS
        start = acc["row"]
        stop = start + (STEP_UNITS - units) // ROW_UNITS + 1
        if stop >= len(rows):
            stop = len(rows)
            acc["cell"] += 1
            acc["row"] = 0
        else:
            acc["row"] = stop
        if stop > start:
            _accumulate(acc, rows[start:stop], reach2)
            units += (stop - start) * ROW_UNITS
    return False


def score_all(ctx, anchors, want):
    """score() rows of every anchor, in anchor order, in atomic score_step() chunks."""
    state = score_init(ctx, anchors, want)
    run_chunked(score_step, state)
    return state["out"]


def score(ctx, x, y, want):
    """
    {"x", "y", "score", "terms": {name: weighted value}, "confidence"} for
    anchor (x, y) without the margin and room terms (add_detail()); want = prepare_want().
    """
    return score_all(ctx, [(x, y)], want)[0]


def margin(ctx, x, y):
    """Share (0..1) of the MARGIN_PROBES_M rings the anchor's biome holds in every direction before another biome shows."""
    own = biome(ctx, x, y)
    for index, radius in enumerate(MARGIN_PROBES_M):
        for dx, dy in MARGIN_DIRS:
            if biome(ctx, x + dx * radius, y + dy * radius) != own:
                return index / len(MARGIN_PROBES_M)
    return 1.0


def room(ctx, cx, cy):
    """Share of MARGIN_DIRS probe points at ROOM_M on the map and clear of other outposts."""
    free = 0
    bounds = ctx["bounds"]
    for dx, dy in MARGIN_DIRS:
        px = cx + dx * ROOM_M
        py = cy + dy * ROOM_M
        if px < bounds[0] or px > bounds[1] or py < bounds[2] or py > bounds[3]:
            continue
        if not near(ctx["outposts"], px, py, OUTPOST_CLEARANCE_M):
            free += 1
    return free / len(MARGIN_DIRS)


def add_detail(ctx, row, want):
    """Adds the margin (biome-locked bundles) and room terms to a score() row; returns it."""
    terms = row["terms"]
    if want["biome"] is not None:
        terms["margin"] = WEIGHTS["margin"] * margin(ctx, row["x"], row["y"])
    cx, cy = centre(row["x"], row["y"])
    terms["room"] = WEIGHTS["room"] * room(ctx, cx, cy)
    row["score"] = sum(terms.values())
    return row


def detail_slice(rows, ctx, want):
    """add_detail() of every score() row of a slice (atomic-safe)."""
    return [add_detail(ctx, row, want) for row in rows]


def _best(rows, count, want):
    """The `count` best rows; a bundle with ores keeps only rows with ore in reach."""
    if want["ores"]:
        rows = [row for row in rows if row["terms"]["ore"] > 0]
    return sorted(rows, key=lambda row: (-row["score"], row["x"], row["y"]))[:count]


def rank_sites(bundle, ctx, role_presets, count=REFINE_TOP, want=None):
    """
    The `count` best anchors for a founding bundle, best first: coarse grid
    filtered and scored, the best REFINE_TOP refined and scored in full.
    Each row: score() + "biome", "survey" (confidence under MIN_CONFIDENCE).
    [] when no anchor passes check() (or, with ores wanted, none has one in reach).
    want: the bundle's prepare_want() when the caller already has it.
    """
    if want is None:
        want = prepare_want(ctx, wants(bundle, role_presets))
    clear = want.get("clear", False)
    coarse = run_batched(filter_slice, grid(ctx["bounds"], CANDIDATE_STEP_M), FILTER_CHUNK, ctx, want["biome"], clear)
    rough = _best(score_all(ctx, coarse, want), REFINE_TOP, want)
    seen = set()
    fine = []
    for row in rough:
        window = grid(ctx["bounds"], REFINE_STEP_M, row["x"] - REFINE_RADIUS_M, row["x"] + REFINE_RADIUS_M,
                      row["y"] - REFINE_RADIUS_M, row["y"] + REFINE_RADIUS_M)
        for anchor in window:
            if anchor not in seen:
                seen.add(anchor)
                fine.append(anchor)
    fine = run_batched(filter_slice, fine, FILTER_CHUNK, ctx, want["biome"], clear)
    best = _best(score_all(ctx, fine, want), count * 2, want)
    full = _best(run_batched(detail_slice, best, DETAIL_CHUNK, ctx, want), count, want)
    out = []
    for row in full:
        row["biome"] = biome(ctx, row["x"], row["y"])
        row["survey"] = row["confidence"] < MIN_CONFIDENCE
        out.append(row)
    return out


def log_sites(log: "TreeConsole", bundle, rows):
    """Debug trail of one bundle's site search (CODE_GUIDES.md#logging)."""
    if not rows:
        log.debug(f"Sites for {bundle['roles']}: no anchor passes the placement checks.")
        return
    for row in rows:
        terms = ", ".join([f"{name} {value:.1f}" for name, value in sorted(row["terms"].items()) if value])
        log.debug(f"Site ({row['x']:.0f}, {row['y']:.0f}) {row['biome']} for {bundle['roles']}: "
                  f"{row['score']:.1f} ({terms}), confidence {row['confidence']:.0%}"
                  f"{', survey first' if row['survey'] else ''}.")


# --- game readers (thin; each returns a safe default when unreadable) ---

def site_rows(sites):
    """[{"id", "x", "y", "kind", "surveyed", "item", "purity", "hardness", "fluid"}] of journal Site objects."""
    rows = []
    for site in sites:
        try:
            kind = site.kind()
            row = {"id": str(site.id), "x": float(site.x), "y": float(site.y), "kind": kind, "surveyed": bool(site.surveyed),
                   "item": None, "purity": None, "hardness": None, "fluid": None}
            if kind == "mineral":
                row["item"] = site.item_id
                row["purity"] = site.purity
                row["hardness"] = site.hardness
            elif kind == "exotic" and row["surveyed"]:
                row["fluid"] = site.fluid()
            rows.append(row)
        except Exception as error:
            swallowed("outpost_sites.site_rows: site read", error)
    return rows


def poi_rows(points, biomass=()):
    """
    [{"x", "y", "kind"}] of nocturna.points_of_interest(); an "unknown" contact
    at a `biomass` position (survey_requests.known_biomass(), whole meters
    rounded) is kind "biomass".
    """
    known = set([(int(round(x)), int(round(y))) for x, y in biomass])
    rows = []
    for point in points:
        try:
            x, y = float(point.x), float(point.y)
            kind = point.kind
            if kind == "unknown" and (int(round(x)), int(round(y))) in known:
                kind = "biomass"
            rows.append({"x": x, "y": y, "kind": kind})
        except Exception as error:
            swallowed("outpost_sites.poi_rows: point read", error)
    return rows


def hardness_limit(kits):
    """Hardest ore an available drill kit cuts (extractor_plan.DRILL_KINDS); None without one."""
    cuts = [hard for _kind, hard, kit in DRILL_KINDS if kit in kits]
    return max(cuts) if cuts else None


def read_world(outposts, kits, range_m, pipes=()):
    """
    World snapshot for prepare(): bounds, outposts (outpost_needs.read_outposts()
    entries), outpost ghosts, POIs and discovered sites; None without nocturna.
    pipes: pipe and pipe-job tiles (tx, ty) for buffer bundles (pipe_tiles()).
    """
    planet = get_component("nocturna")
    journal = get_component("journal")
    if planet is None:
        return None
    try:
        b = planet.get_bounds()
        bounds = (float(b.min_x), float(b.max_x), float(b.min_y), float(b.max_y))
        points = planet.points_of_interest() or []
    except Exception as error:
        swallowed("outpost_sites.read_world: nocturna", error)
        return None
    sites = []
    if journal is not None:
        try:
            sites = journal.discovered_sites("nocturna") or []
        except Exception as error:
            swallowed("outpost_sites.read_world: journal.discovered_sites", error)
    return {"bounds": bounds, "outposts": outposts, "ghosts": read_ghosts(),
            "pois": poi_rows(points, read_known_biomass()), "sites": site_rows(sites), "range_m": range_m,
            "blocked": read_blocked(), "pipes": list(pipes),
            "hardness_limit": hardness_limit(kits)}


def read_ghosts():
    """Anchors (x, y) of pending / active / paused outpost blueprints."""
    blueprints = get_component("construction_blueprint")
    out = []
    if blueprints is None:
        return out
    for getter in ("pending_constructions", "active_constructions", "paused_constructions"):
        try:
            for job in getattr(blueprints, getter)() or []:
                if str(getattr(job, "kind", "")) == "outpost":
                    pos = job.position
                    out.append((float(pos.x), float(pos.y)))
        except Exception as error:
            swallowed("outpost_sites.read_ghosts: " + getter, error)
    return out
