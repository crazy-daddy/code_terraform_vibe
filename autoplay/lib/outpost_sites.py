# Site scoring of the outpost founding planner (docs/plans/outpost_founding_planner.md):
# where on the map a founding bundle (outpost_needs.found_bundles()) should go.
#
# Placement rules (simworker plan_structure("outpost") checks, cheatsheet §11i):
#   - The anchor (x, y) is the footprint's NW corner; world y grows north. The
#     placement square is OUTPOST_PLACE_M wide: x .. x + OUTPOST_PLACE_M, y - OUTPOST_PLACE_M .. y,
#     centre (x + OUTPOST_PLACE_M / 2, y - OUTPOST_PLACE_M / 2).
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
#            best contact whose extractor footprint is within NEAR_TILES of the
#            outpost footprint (Manhattan tile gap = pipe pieces, as in
#            supply_tiers), closeness 1 .. 0.
#   exotic   raw exotic deposits within that gap (a later refinery role), capped at 1.
#   biosite  biomass contacts within BIOSITE_RANGE_M in the bundle's biome,
#            unknown contacts by P(biomass), capped at BIOSITE_CAP.
#   margin   biome-locked bundles: share of the MARGIN_PROBES_M rings around
#            the anchor that hold only its biome (a site near a border scores lower).
#   room     share of the MARGIN_DIRS probe points at ROOM_M that are on the map and
#            clear of other outposts (land for later extractors).
#   home     penalty per km to the home centre (haul distance).
#   near     penalty under HOME_NEAR_M from the home centre (share of the
#            shortfall): the base should spread outward. With home it puts the
#            best home distance at HOME_NEAR_M.
#   grid     penalty per km of Manhattan distance to the nearest outpost or
#            ghost: links run on tiles, so a diagonal gap costs its full L of
#            power line and pipe.
#   travel   penalty per km to the nearest reach point (home or a Charging
#            Station host): constructors drive there and back on battery.
#   crowd    penalty when the tile gap between this footprint and the nearest
#            outpost's is under SPACING_TILES (share of the shortfall): every
#            fluid an outpost takes needs its own pipe in, with a free tile
#            between pipes (for bridges) and some room at the outposts. With
#            grid it puts the best gap at SPACING_TILES.
# confidence = share of the resource terms (ore, fluid, exotic, biosite) from
# known contacts (surveyed; a fluid its kind tells; a bio-scanned biosite);
# under MIN_CONFIDENCE the site wants a survey trip first. A contact the scouts
# cannot resolve now (survey_requests.blocked_targets()) adds no guess, so it
# never holds a site in "survey first".
# Unresolved contacts are typed from their sonar verdict (contact_inference,
# docs/gameknowledge/survey_contacts.md): a verdict that leaves one kind makes
# the contact level 2 of that kind; several kinds become the contact's own
# kind prior (the biome at the contact is a hard rule: geothermal = thermal,
# frozen/coastal = water, volcanic = oil, deep = exotic). A stuck
# contact's fluid value from that prior counts as known: the verdict is all a
# survey would tell now, so it lifts the score without asking for a survey.
#
# Search: a CANDIDATE_STEP_M grid over the map, filtered (bounds, clearance,
# biome lock), scored without margin and room; the best REFINE_TOP are
# re-searched on a REFINE_STEP_M grid within REFINE_RADIUS_M; the best of
# those get the margin and room terms (add_detail()).
# Every heavy step runs in atomic slices (lib/atomic.py run_batched /
# run_chunked); scoring goes in score_step() chunks of STEP_UNITS work units,
# resumable mid-anchor, so contact density never overruns a slice. Sizes are
# measured by tests/test_autoplay_outpost_sites.py against ATOMIC_STEP_BUDGET.

from typing import TYPE_CHECKING

from atomic import run_batched, run_chunked
from autoplay_roles import STORAGE_BUFFER_TILES, fluids_for, keeps_buffer, role_flag
from contact_inference import BIOME_KINDS, kind_weights
from extractor_plan import DRILL_KINDS
from game_rules import RAW_ORE_ITEM_IDS
from grid_geom import FOOTPRINT_TILES, OUTPOST_PLACE_M, TILE_M, buffer_box, extractor_box, outpost_box, outpost_centre
from item_tiers import can_cut
from supply_tiers import NEAR_TILES
from survey_requests import read_blocked, read_known_biomass, read_unsupported, target_coords, target_site_id
from swallow import swallowed

if TYPE_CHECKING:
    from tree_console import TreeConsole

OUTPOST_CLEARANCE_M = 40  # simworker plan.outpostClearanceM
POI_CLEARANCE_M = 20  # simworker plan.outpostPoiClearanceM
CLEAR_SIDE_M = 26  # square the clearance is measured to (simworker icon size, at least OUTPOST_PLACE_M)

CANDIDATE_STEP_M = 80  # coarse candidate grid
REFINE_STEP_M = 20  # refine grid around the best coarse candidates
REFINE_RADIUS_M = 40  # refine window half-width
REFINE_TOP = 5  # coarse candidates refined
CELL_M = 150  # contact bucket size

BIOSITE_RANGE_M = 300  # biomass contacts a bio / liquifier outpost counts
# Contact window around the centre for the fluid terms: footprint half-width plus
# NEAR_TILES plus an extractor footprint's half-width, on each axis.
FLUID_WINDOW_M = (NEAR_TILES + FOOTPRINT_TILES) * TILE_M
ORE_CAP = 2.0  # per ore: two good sites are enough
BIOSITE_CAP = 6.0
EXOTIC_VALUE = 0.25  # per raw exotic deposit in reach (exotic term capped at 1)
HARD_FACTOR = 0.2  # value of a surveyed ore site no available drill kit cuts
PURITY_FACTOR = {"standard": 1.0, "rich": 1.5, "pure": 2.0}
MARGIN_PROBES_M = (20, 40, 80, 160)
MARGIN_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (0.7, -0.7), (-0.7, 0.7), (-0.7, -0.7))
ROOM_M = 100
HOME_NEAR_M = 300  # home distance below which the near term costs (operator: expand outward, not too far)
SPACING_TILES = 4  # free tiles between outpost footprints below which the crowd term costs (operator: 3-5 do)
MIN_CONFIDENCE = 0.5

# Score weights per phase (prepare() "weights"; WEIGHTS = the late phase, from
# the first mining drill on: drills sit on the ore, so ore reach matters less and
# haul distance more). Early, Pioneers mine by hand: ore near the outpost and a
# short trip home weigh more, and the site must be in constructor reach. The ore
# term splits by demand share ("demand": {ore: share}, DEMAND_FALLBACK before a
# Smelter demand is readable: iron carried most of both recorded runs). biome_new
# rewards a biome no outpost stands in yet (every biome gets its bio chain,
# liquifier and Weather Station later). reach_gain rewards the share of
# out-of-reach contacts (not stuck) the site's Charging Station would bring within
# CONSTRUCTOR_REACH_M; it is off (0) while drones haul the freight (phase_inputs()).
# future pulls toward the best contact of each look-ahead fluid
# (outpost_needs.future_fluids(): steam before a power host, water before a
# reactor host), closeness 1 - d / FUTURE_RANGE_M; with no steam contact a
# geothermal scout area counts at FUTURE_CELL_VALUE.
WEIGHTS = {"ore": 10.0, "fluid": 6.0, "exotic": 1.0, "biosite": 2.0, "margin": 4.0, "room": 2.0, "home": -2.0, "near": -3.0, "grid": -6.0, "travel": -2.0, "crowd": -3.0, "biome_new": 1.0, "reach_gain": 3.0, "future": 3.0}
WEIGHTS_EARLY = dict(WEIGHTS, home=-4.0, travel=-3.0, biome_new=3.0, reach_gain=9.0)  # reach_gain 9: rev3 replay (planner_rev2_results.md "Revision 3")
DEMAND_FALLBACK = {"iron_ore": 0.6, "silicon": 0.3}  # shares of the early ore demand (run 2: 20k iron, 12k silicon mined)
CONSTRUCTOR_REACH_M = 600  # one-way distance from home or a Charging Station host a constructor Pioneer can build at (early phase gate)
RESOURCE_TERMS = ("ore", "fluid", "exotic", "biosite")

FILTER_CHUNK = 4  # candidates per atomic filter slice
STEP_UNITS = 64  # work units (~45 operations each) per atomic score_step() call
ROW_UNITS = 6  # per contact row accumulated (~260 operations at worst)
WINDOW_CELLS = 3  # window cells per work unit scanned at an anchor's start (~15 operations each)
START_UNITS = 4  # per anchor started (~150 operations)
FINISH_UNITS = 22  # per anchor finished (~1000 operations with 9 outposts)
REACH_ITEMS = 2  # remote contact clusters tested for reach_gain, and future spots, per work unit at an anchor's finish (~25 operations each)
FUTURE_RANGE_M = 500.0  # future term: closeness falls to 0 at this distance from a look-ahead fluid spot
REMOTE_TOP = 40  # remote clusters (by contact count) kept for reach_gain; remote_n stays the full count
FUTURE_TOP = 8  # best spots kept per look-ahead fluid
FUTURE_CELL_VALUE = 0.5  # value of a geothermal scout area when no steam contact is known
DETAIL_CHUNK = 1  # candidates per atomic add_detail() slice (margin + room)
VALUE_CHUNK = 15  # contacts per atomic value_rows() slice
PIPE_BLOCK_TILES = 4  # pipe tiles bucketed in square blocks of this many tiles per side

# Site kind -> field fluid for non-exotic kinds (known from the kind alone).
KIND_FLUID = {"water": "water", "oil": "oil", "thermal": "steam"}
FLUID_KIND = {fluid: kind for kind, fluid in KIND_FLUID.items()}
BIOME_BOUND = {kind for kinds in BIOME_KINDS.values() for kind in kinds}  # kinds that spawn in their biome only
RAW_EXOTICS = ("raw_sulfur_gas", "raw_chlorine", "raw_cryofluid", "raw_quicksilver")
SITE_KINDS = ("mineral", "thermal", "water", "oil", "exotic", "biomass", "inert")


# --- geometry ---


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
    return x >= bounds[0] and x + OUTPOST_PLACE_M <= bounds[1] and y - OUTPOST_PLACE_M >= bounds[2] and y <= bounds[3]


def grid(bounds, step, x0=None, x1=None, y0=None, y1=None):
    """Anchors on a `step` grid (multiples of TILE_M) inside bounds, optionally limited to a window."""
    lo_x = bounds[0] if x0 is None else max(bounds[0], x0)
    hi_x = bounds[1] - OUTPOST_PLACE_M if x1 is None else min(bounds[1] - OUTPOST_PLACE_M, x1)
    lo_y = bounds[2] + OUTPOST_PLACE_M if y0 is None else max(bounds[2] + OUTPOST_PLACE_M, y0)
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


def contacts(pois, sites, blocked=None, inferred=None):
    """
    Contact rows {"x", "y", "level", "kind", "item", "purity", "hardness", "fluid", "stuck"}
    from POI rows {"x", "y", "kind"} and site rows (site_rows()); a site wins
    over the POI at its position. blocked = survey_requests.blocked_targets()
    ({(x, y) whole meters}, {site id}): an unsurveyed contact in it is "stuck"
    (no scout resolves it with what is unlocked now). inferred = infer_kinds()
    ({(x, y) whole meters: weights}, {site id: weights}): an unknown contact
    with one inferred kind becomes level 2 of it, with several gets "kinds".
    """
    pois_blocked, sites_blocked = blocked if blocked else (set(), set())
    spots_inferred, _sites_inferred = inferred if inferred else ({}, {})
    out = []
    taken = set()
    for site in sites:
        level = 3 if site.get("surveyed") else 2
        kind = site.get("kind")
        fluid = site.get("fluid") if level == 3 else None
        if fluid is None:
            fluid = KIND_FLUID.get(kind)
        spot = (int(round(site["x"])), int(round(site["y"])))
        out.append({"x": site["x"], "y": site["y"], "level": level, "kind": kind, "item": site.get("item") if level == 3 else None, "purity": site.get("purity"), "hardness": site.get("hardness"), "fluid": fluid, "stuck": level < 3 and (site.get("id") in sites_blocked or spot in pois_blocked)})
        taken.add(spot)
    for poi in pois:
        spot = (int(round(poi["x"])), int(round(poi["y"])))
        if spot in taken:
            continue
        kind = poi.get("kind") or "unknown"
        row = {"x": float(poi["x"]), "y": float(poi["y"]), "level": 1 if kind == "unknown" else 2, "kind": None if kind == "unknown" else kind, "item": None, "purity": None, "hardness": None, "fluid": KIND_FLUID.get(kind), "stuck": spot in pois_blocked}
        if row["level"] == 1:
            _apply_inferred(row, spots_inferred.get(spot))
        out.append(row)
    return out


def _apply_inferred(row, weights):
    """Types an unknown contact row from contact_inference weights ({kind: probability})."""
    if not weights:
        return
    if len(weights) == 1:
        kind = list(weights)[0]
        row["level"] = 2
        row["kind"] = kind
        row["fluid"] = KIND_FLUID.get(kind)
    else:
        row["kinds"] = weights


def infer_kinds(targets, biome_of):
    """
    ({(x, y) whole meters: weights}, {site id: weights}) of an unsupported-targets
    dict (survey.unsupported_targets): contact_inference.kind_weights() of each
    entry with the biome at its position (biome_of(x, y)); entries that say
    nothing about the kind are left out.
    """
    spots = {}
    site_ids = {}
    if not isinstance(targets, dict):
        return spots, site_ids
    for key, entry in targets.items():
        coords = target_coords(key)
        if coords is None:
            continue
        weights = kind_weights(entry, biome_of(coords[0], coords[1]))
        if not weights:
            continue
        spots[(int(round(coords[0])), int(round(coords[1])))] = weights
        site_id = target_site_id(key)
        if site_id is not None:
            site_ids[site_id] = weights
    return spots, site_ids


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
    return {"kind": _shares(known, SITE_KINDS), "ore": _shares(ores, RAW_ORE_ITEM_IDS), "exotic": _shares([row["fluid"] for row in surveyed if row["kind"] == "exotic"], RAW_EXOTICS), "purity": sum(factors) / len(factors) if factors else 1.0}


def ore_value(row, ore, prior, hardness_limit):
    """(expected value, surveyed?) of a contact for `ore`."""
    if row["level"] == 3:
        if row["kind"] != "mineral" or row["item"] != ore:
            return (0.0, True)
        value = PURITY_FACTOR.get(row["purity"], 1.0)
        hard = row["hardness"]
        if hardness_limit is not None and not can_cut(hard, hardness_limit):
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


def wants(bundle, role_presets, future=()):
    """
    {"ores", "fluids", "biosites", "biome", "clear", "future"} a founding bundle
    looks for: its need's ores, the field fluids its roles take and do not make,
    biosites when a role collects life (bio_ / liquifier_), clear land
    without pipes when it keeps a pipe buffer (keeps_buffer()), and the
    look-ahead fluids (outpost_needs.future_fluids()) for the future term.
    """
    fluids = fluids_for(bundle.get("roles", []), role_presets)
    field = field_fluids()
    wanted = [fluid for fluid in fluids["in"] if fluid in field and fluid not in fluids["out"]]
    return {"ores": list(bundle.get("ores", [])), "fluids": wanted, "biome": bundle.get("biome"), "biosites": any(role_flag(name, "biosites") for name in bundle.get("roles", [])), "clear": keeps_buffer(bundle.get("roles", [])), "future": list(future)}


# --- context ---


def prepare(world, biome_at):
    """
    Scoring context from a world snapshot (read_world()):
      {"bounds", "outposts": [{"id", "x", "y", "home", "depot", "biome", "types"}], "ghosts": [(x, y)],
       "pois": [{"x", "y", "kind"}], "sites": site_rows(), "range_m", "hardness_limit",
       "blocked" (survey_requests.blocked_targets(), optional),
       "unsupported" (survey.unsupported_targets, optional; infer_kinds()),
       "pipes": [(tx, ty), ...] pipe and pipe-job tiles (optional, read for buffer bundles),
       "weights" (optional, WEIGHTS), "demand" {ore: share} (optional),
       "reach": {"points": [(x, y), ...], "m": metres} (optional: anchors farther from
       every point are rejected by check(), "out_of_reach"),
       "geothermal": [(x, y), ...] geothermal scout areas (optional, the future term's steam fallback)}
    biome_at(x, y): the game's nocturna.biome_at (a read, atomic-safe);
    answers are cached per TILE_M tile. rank_sites() adds "coarse": the
    coarse grid anchors that pass check() without a biome or pipe buffer.
    """
    biomes = {}
    probe = {"biome_at": biome_at, "biomes": biomes}
    inferred = infer_kinds(world.get("unsupported"), lambda x, y: biome(probe, x, y))
    rows = contacts(world.get("pois", []), world.get("sites", []), world.get("blocked"), inferred)
    centres = [outpost_centre(entry["x"], entry["y"]) for entry in world.get("outposts", [])]
    centres.extend([outpost_centre(x, y) for x, y in world.get("ghosts", [])])
    home = [outpost_centre(entry["x"], entry["y"]) for entry in world.get("outposts", []) if entry.get("home")]
    starts = reach_points(world.get("outposts", []))
    remote = remote_clusters(rows, starts)
    return {
        "bounds": world["bounds"],
        "range_m": world.get("range_m", 200.0),
        "hardness_limit": world.get("hardness_limit"),
        "rows": rows,
        "prior": priors(rows),
        "pois": bucket([{"x": float(poi["x"]), "y": float(poi["y"])} for poi in world.get("pois", [])]),
        "outposts": bucket([{"x": cx, "y": cy} for cx, cy in centres]),
        "centres": centres,
        "home": home[0] if home else None,
        "starts": starts,
        "remote": sorted(remote, key=lambda cluster: -cluster[2])[:REMOTE_TOP],
        "remote_n": sum([n for _x, _y, n in remote]),
        "pipes": pipe_blocks(world.get("pipes", [])),
        "biome_at": biome_at,
        "biomes": biomes,
        "weights": dict(world.get("weights") or WEIGHTS),
        "demand": dict(world.get("demand") or {}),
        "reach": world.get("reach"),
        "geothermal": [(float(x), float(y)) for x, y in world.get("geothermal") or []],
        "settled": sorted({str(entry.get("biome")) for entry in world.get("outposts", []) if entry.get("biome")}),
    }


def remote_clusters(rows, starts):
    """
    [(x, y, n)] clusters of the non-stuck contacts farther than CONSTRUCTOR_REACH_M
    from every start point, one per CELL_M cell (x, y = mean position, n = count).
    No start point: none (nothing to measure reach from).
    """
    if not starts:
        return []
    cells = {}
    for row in rows:
        if row.get("stuck"):
            continue
        x = row["x"]
        y = row["y"]
        if any(_dist(x, y, sx, sy) <= CONSTRUCTOR_REACH_M for sx, sy in starts):
            continue
        acc = cells.setdefault(_cell(x, y), [0.0, 0.0, 0])
        acc[0] += x
        acc[1] += y
        acc[2] += 1
    return [(sx / n, sy / n, n) for sx, sy, n in cells.values()]


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
    cx, cy = outpost_centre(x, y)
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
    reach = ctx.get("reach")
    if reach and not any(_dist(cx, cy, px, py) <= reach["m"] for px, py in reach.get("points") or []):
        return "out_of_reach"  # no reach point at all (no home read) fails closed
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
      fluid_inf        a stuck contact's fluid chance from its inferred kinds, counted as known
    A contact with inferred "kinds" (contacts()) uses them as its kind prior.
    A stuck contact (contacts()) adds no guess: it is surveyed as far as the
    scouts get, so it neither lifts the score nor asks for a survey. Only its
    inferred fluid value stays, as fluid_inf.
    """
    out = []
    prior = ctx["prior"]
    limit = ctx["hardness_limit"]
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
            kinds = row.get("kinds")
            row_prior = prior if kinds is None else {"kind": kinds, "exotic": prior["exotic"]}
            fluid_guess = sum([fluid_value(row, name, row_prior)[0] for name in want["fluids"]])
        exotic = (0.0, 0.0)
        if row["fluid"] and row["fluid"].startswith("raw_") and fluid is None:
            exotic = (EXOTIC_VALUE, 0.0)
        elif row["kind"] == "exotic" and row["fluid"] is None:
            exotic = (0.0, EXOTIC_VALUE)
        bio = (0.0, 0.0)
        if want["biosites"] and (row["level"] == 1 or row["kind"] == "biomass"):
            if want["biome"] is None or biome(ctx, row["x"], row["y"]) == want["biome"]:
                bio = (1.0, 0.0) if row["level"] >= 2 else (0.0, (row.get("kinds") or prior["kind"]).get("biomass", 0.0))
        fluid_inf = 0.0
        if row.get("stuck"):
            if row.get("kinds") is not None:
                fluid_inf = fluid_guess
            ore_guess = 0.0
            fluid_guess = 0.0
            exotic = (exotic[0], 0.0)
            bio = (bio[0], 0.0)
        if ore_sure > 0 or ore_guess > 0 or fluid is not None or fluid_guess > 0 or fluid_inf > 0 or exotic[0] + exotic[1] > 0 or bio[0] + bio[1] > 0:
            out.append((row["x"], row["y"], ore, ore_sure, ore_guess, fluid, fluid_guess, exotic[0], exotic[1], bio[0], bio[1], fluid_inf, extractor_box(row["x"], row["y"])))
    return out


def biome_share(prior, kind, found):
    """
    prior["kind"][kind] renormalised over the kinds that can spawn in biome
    `found` (contact_inference.BIOME_KINDS; a kind no biome lists spawns
    everywhere); 0 when the biome rules `kind` out. found None: the plain prior.
    """
    shares = prior["kind"]
    if found is None:
        return shares.get(kind, 0.0)
    allowed = [name for name in SITE_KINDS if name not in BIOME_BOUND or name in BIOME_KINDS.get(found, ())]
    if kind not in allowed:
        return 0.0
    total = sum([shares.get(name, 0.0) for name in allowed])
    return shares.get(kind, 0.0) / total if total > 0 else 0.0


def future_rows(rows, ctx, fluids):
    """
    Look-ahead fluid spots of a slice (atomic-safe): (fluid, x, y, value) per
    non-stuck contact worth something. A contact known to yield the fluid
    (any level) is 1; an unknown one (level 1) its inferred "kinds" weight of
    the fluid's kind, else biome_share() of the save's prior at its biome.
    """
    out = []
    prior = ctx["prior"]
    shares = {}  # (kind, biome) -> biome_share(), per slice
    for row in rows:
        if row.get("stuck"):
            continue
        for fluid in fluids:
            if row["fluid"] is not None:
                value = 1.0 if row["fluid"] == fluid else 0.0
            elif row["level"] == 1:
                kind = FLUID_KIND.get(fluid)
                kinds = row.get("kinds")
                if kind is None:
                    value = 0.0
                elif kinds is not None:
                    value = kinds.get(kind, 0.0)
                else:
                    found = biome(ctx, row["x"], row["y"])
                    key = (kind, found)
                    if key not in shares:
                        shares[key] = biome_share(prior, kind, found)
                    value = shares[key]
            else:
                value = 0.0
            if value > 0:
                out.append((fluid, row["x"], row["y"], value))
    return out


def future_spots(ctx, fluids):
    """
    {fluid: [(x, y, value), ...]}: the FUTURE_TOP best spots of each look-ahead
    fluid (future_rows(); ties nearest home first). Steam with no spot worth
    anything falls back to the geothermal scout areas at FUTURE_CELL_VALUE.
    """
    spots = {fluid: [] for fluid in fluids}
    if not fluids:
        return spots
    for fluid, x, y, value in run_batched(future_rows, ctx["rows"], VALUE_CHUNK, ctx, list(fluids)):
        spots[fluid].append((x, y, value))
    home = ctx.get("home") or (0.0, 0.0)
    for fluid in fluids:
        if fluid == "steam" and not spots[fluid]:
            spots[fluid] = [(x, y, FUTURE_CELL_VALUE) for x, y in ctx.get("geothermal") or []]
        ranked = sorted(spots[fluid], key=lambda spot: (-spot[2], _dist(spot[0], spot[1], home[0], home[1]), spot[0], spot[1]))
        spots[fluid] = ranked[:FUTURE_TOP]
    return spots


def prepare_want(ctx, want):
    """
    `want` (wants()) with its valued contacts bucketed ("valued"), the widest
    term range ("radius"), the non-empty cells in (i, j) order ("cells") and
    the most cells an anchor's start scans ("window"), the look-ahead fluid spots ("future_spots",
    future_spots(); "future_n" spots in all), and what _finish() would
    otherwise redo per anchor: ctx's term weights with every term present
    ("weights", 0 for a term ctx's weights lack) and the ores' demand_factors()
    ("factors").
    """
    out = dict(want)
    weights = ctx.get("weights") or WEIGHTS
    out["weights"] = {name: weights.get(name, 0.0) for name in WEIGHTS}
    out["factors"] = demand_factors(want["ores"], ctx.get("demand") or {})
    cells = {}
    for row in run_batched(value_rows, ctx["rows"], VALUE_CHUNK, ctx, want):
        cells.setdefault(_cell(row[0], row[1]), []).append(row)
    out["valued"] = cells
    out["future"] = list(want.get("future") or [])
    out["future_spots"] = future_spots(ctx, out["future"])
    out["future_n"] = sum([len(spots) for spots in out["future_spots"].values()])
    radius = FLUID_WINDOW_M
    if want["ores"]:
        radius = max(radius, ctx["range_m"])
    if want["biosites"]:
        radius = max(radius, BIOSITE_RANGE_M)
    out["radius"] = radius
    out["cells"] = sorted(cells)
    out["window"] = min((int(2 * radius // CELL_M) + 2) ** 2, len(out["cells"]))  # most cells _start() scans
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


def _nearest_both(points, x, y):
    """(smallest Chebyshev, smallest Manhattan = tile-routed link) distance from (x, y) to `points`; (None, None) without points."""
    best = None
    best_l = None
    for px, py in points:
        dx = x - px if x > px else px - x
        dy = y - py if y > py else py - y
        d = dx if dx > dy else dy
        if best is None or d < best:
            best = d
        if best_l is None or dx + dy < best_l:
            best_l = dx + dy
    return (best, best_l)


def score_init(ctx, anchors, want):
    """State for score_step(): every anchor of `anchors` scored in turn into state["out"]; want = prepare_want()."""
    return {"ctx": ctx, "want": want, "anchors": list(anchors), "next": 0, "acc": None, "out": []}


def _start(state):
    """
    Accumulator for the next anchor: the valued rows of its cell window
    ("lists", one list per non-empty cell, window order), the cells scanned
    for them ("window": the window's cells, or want["cells"] when that list is
    shorter, as with a wide mining range) and empty term sums.
    """
    x, y = state["anchors"][state["next"]]
    state["next"] += 1
    cx, cy = outpost_centre(x, y)
    want = state["want"]
    radius = want["radius"]
    valued = want["valued"]
    i0 = int((cx - radius) // CELL_M)
    i1 = int((cx + radius) // CELL_M)
    j0 = int((cy - radius) // CELL_M)
    j1 = int((cy + radius) // CELL_M)
    scanned = (i1 - i0 + 1) * (j1 - j0 + 1)
    if scanned <= len(want["cells"]):
        lists = []
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                rows = valued.get((i, j))
                if rows is not None:
                    lists.append(rows)
    else:  # want["cells"] is sorted (i, j), the window's own order
        lists = [valued[key] for key in want["cells"] if i0 <= key[0] <= i1 and j0 <= key[1] <= j1]
        scanned = len(want["cells"])
    state["acc"] = {"x": x, "y": y, "cx": cx, "cy": cy, "lists": lists, "cells": len(lists), "window": scanned, "box": outpost_box(x, y), "cell": 0, "row": 0, "ore_sure": {}, "ore_guess": 0.0, "fluid_best": {}, "fluid_guess": 0.0, "fluid_inf": 0.0, "exotic": [0.0, 0.0], "bio": [0.0, 0.0]}


def _accumulate(acc, rows, reach2):
    """Adds valued rows (value_rows() tuples) within their term ranges of the anchor to its sums."""
    cx = acc["cx"]
    cy = acc["cy"]
    ore_sure = acc["ore_sure"]
    fluid_best = acc["fluid_best"]
    exotic = acc["exotic"]
    bio = acc["bio"]
    box = acc["box"]
    bio2 = BIOSITE_RANGE_M * BIOSITE_RANGE_M
    for x0, y0, ore, sure, guess, fluid, f_guess, ex_sure, ex_guess, bio_known, bio_guess, f_inf, ext in rows:
        d2 = (cx - x0) * (cx - x0) + (cy - y0) * (cy - y0)
        if d2 <= reach2:
            if ore is not None:
                ore_sure[ore] = ore_sure.get(ore, 0.0) + sure
            acc["ore_guess"] += guess
        gap_x = ext[0] - box[2] if ext[0] > box[2] else (box[0] - ext[2] if box[0] > ext[2] else 0)
        gap_y = ext[1] - box[3] if ext[1] > box[3] else (box[1] - ext[3] if box[1] > ext[3] else 0)
        gap = gap_x + gap_y
        if gap <= NEAR_TILES:
            close = 1.0 - gap / NEAR_TILES
            if fluid is not None and close > fluid_best.get(fluid, 0.0):
                fluid_best[fluid] = close
            acc["fluid_guess"] += f_guess * close
            acc["fluid_inf"] += f_inf * close
            exotic[0] += ex_sure
            exotic[1] += ex_guess
        if d2 <= bio2:
            bio[0] += bio_known
            bio[1] += bio_guess


def _future(want, cx, cy):
    """Mean over the look-ahead fluids of the best spot value × closeness (1 - d / FUTURE_RANGE_M, at least 0); 0 without fluids."""
    fluids = want.get("future") or []
    if not fluids:
        return 0.0
    spots = want.get("future_spots") or {}
    total = 0.0
    for fluid in fluids:
        best = 0.0
        for x, y, value in spots.get(fluid, ()):
            close = 1.0 - ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5 / FUTURE_RANGE_M  # _dist() inlined (per anchor)
            if close > 0 and value * close > best:
                best = value * close
        total += best
    return total / len(fluids)


def _finish(ctx, acc, want):
    """score() row of a finished accumulator."""
    cx = acc["cx"]
    cy = acc["cy"]
    weights = want["weights"]
    factors = want["factors"]
    sure = sum([(value if value < ORE_CAP else ORE_CAP) * factors.get(ore, 1.0) for ore, value in acc["ore_sure"].items()])
    raw = {"ore": _topped(sure, acc["ore_guess"], ORE_CAP * len(want["ores"])), "fluid": _topped(min(sum(acc["fluid_best"].values()) + acc["fluid_inf"], len(want["fluids"])), acc["fluid_guess"], len(want["fluids"])), "exotic": _capped(acc["exotic"][0], acc["exotic"][1], 1.0)}
    sure, maybe = _capped(acc["bio"][0], acc["bio"][1], BIOSITE_CAP)
    raw["biosite"] = (sure / BIOSITE_CAP, maybe / BIOSITE_CAP)
    terms = {}
    known = 0.0
    guess = 0.0
    for name in RESOURCE_TERMS:
        sure, maybe = raw[name]
        terms[name] = weights[name] * (sure + maybe)
        known += weights[name] * sure
        guess += weights[name] * maybe
    home = ctx["home"]
    home_m = _dist(cx, cy, home[0], home[1]) if home else None
    terms["home"] = weights["home"] * (home_m / 1000.0 if home_m is not None else 0.0)
    terms["near"] = weights["near"] * (1.0 - home_m / HOME_NEAR_M if home_m is not None and home_m < HOME_NEAR_M else 0.0)
    gap, link = _nearest_both(ctx["centres"], cx, cy)
    terms["grid"] = weights["grid"] * ((link or 0.0) / 1000.0)
    terms["travel"] = weights["travel"] * ((_nearest(ctx.get("starts") or [], cx, cy) or 0.0) / 1000.0)
    gap = gap / TILE_M - FOOTPRINT_TILES if gap is not None else None  # free tiles between the two footprints
    terms["crowd"] = weights["crowd"] * (1.0 - gap / SPACING_TILES if gap is not None and gap < SPACING_TILES else 0.0)
    found = biome(ctx, acc["x"], acc["y"])
    terms["biome_new"] = weights["biome_new"] * (1.0 if found is not None and found not in (ctx.get("settled") or []) else 0.0)
    remote_n = ctx.get("remote_n") or 0
    gained = sum([n for rx, ry, n in ctx["remote"] if ((cx - rx) ** 2 + (cy - ry) ** 2) ** 0.5 <= CONSTRUCTOR_REACH_M]) if remote_n else 0  # _dist() inlined
    terms["reach_gain"] = weights["reach_gain"] * (gained / remote_n if remote_n else 0.0)
    terms["future"] = weights["future"] * _future(want, cx, cy)
    resource = known + guess
    return {"x": acc["x"], "y": acc["y"], "score": sum(terms.values()), "terms": terms, "confidence": known / resource if resource > 0 else 1.0}


def demand_factors(ores, demand):
    """
    {ore: factor} scaling each wanted ore's term by its demand share, mean 1
    over the wanted ores (equal shares or no demand data = 1 each). Ores with
    no share get the smallest listed share, so a side ore still counts a little.
    """
    ores = list(ores or [])
    shares = {ore: float(demand.get(ore, 0.0)) for ore in ores if float(demand.get(ore, 0.0)) > 0}
    if not ores or not shares:
        return {ore: 1.0 for ore in ores}
    floor = min(shares.values())
    full = {ore: shares.get(ore, floor) for ore in ores}
    mean = sum(full.values()) / len(full)
    return {ore: value / mean for ore, value in full.items()}


def score_step(state):
    """
    One bounded chunk of scoring (lib/atomic.py run_chunked()): up to
    STEP_UNITS work units (ROW_UNITS per contact row, START_UNITS plus one
    per WINDOW_CELLS window cells scanned at an anchor's start, FINISH_UNITS per
    anchor plus one per REACH_ITEMS remote clusters and future spots);
    resumes mid-cell. Returns True once every anchor is scored.
    """
    ctx = state["ctx"]
    want = state["want"]
    reach2 = ctx["range_m"] * ctx["range_m"]
    units = 0
    while units < STEP_UNITS:
        acc = state["acc"]
        if acc is None:
            if state["next"] >= len(state["anchors"]):
                return True
            if units and units + START_UNITS + (want["window"] + WINDOW_CELLS - 1) // WINDOW_CELLS > STEP_UNITS:
                return False  # a wide window scan gets a slice of its own
            _start(state)
            units += START_UNITS + (state["acc"]["window"] + WINDOW_CELLS - 1) // WINDOW_CELLS
            continue
        if acc["cell"] >= acc["cells"]:
            cost = FINISH_UNITS + (len(ctx["remote"]) + want.get("future_n", 0) + REACH_ITEMS - 1) // REACH_ITEMS
            if units and units + cost > STEP_UNITS:
                return False  # the finish alone is big: give it a slice of its own
            state["out"].append(_finish(ctx, acc, want))
            state["acc"] = None
            units += cost
            continue
        rows = acc["lists"][acc["cell"]]
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
    cx, cy = outpost_centre(row["x"], row["y"])
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
    coarse = ctx.get("coarse")
    if coarse is None:
        coarse = run_batched(filter_slice, grid(ctx["bounds"], CANDIDATE_STEP_M), FILTER_CHUNK, ctx, want["biome"], clear)
        if want["biome"] is None and not clear:
            ctx["coarse"] = coarse  # the bundle-free checks, shared by the next bundles ranked on this ctx
    elif want["biome"] is not None or clear:
        coarse = run_batched(filter_slice, coarse, FILTER_CHUNK, ctx, want["biome"], clear)
    rough = _best(score_all(ctx, coarse, want), REFINE_TOP, want)
    seen = set()
    fine = []
    for row in rough:
        window = grid(ctx["bounds"], REFINE_STEP_M, row["x"] - REFINE_RADIUS_M, row["x"] + REFINE_RADIUS_M, row["y"] - REFINE_RADIUS_M, row["y"] + REFINE_RADIUS_M)
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
        log.debug(f"Site ({row['x']:.0f}, {row['y']:.0f}) {row['biome']} for {bundle['roles']}: {row['score']:.1f} ({terms}), confidence {row['confidence']:.0%}{', survey first' if row['survey'] else ''}.")


# --- game readers (thin; each returns a safe default when unreadable) ---


def site_rows(sites):
    """[{"id", "x", "y", "kind", "surveyed", "item", "purity", "hardness", "fluid"}] of journal Site objects."""
    rows = []
    for site in sites:
        try:
            kind = site.kind()
            row = {"id": str(site.id), "x": float(site.x), "y": float(site.y), "kind": kind, "surveyed": bool(site.surveyed), "item": None, "purity": None, "hardness": None, "fluid": None}
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
    known = {(int(round(x)), int(round(y))) for x, y in biomass}
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


def read_world(outposts, kits, range_m, pipes=(), weights=None, demand=None, reach=None, geothermal=()):
    """
    World snapshot for prepare(): bounds, outposts (outpost_needs.read_outposts()
    entries), outpost ghosts, POIs and discovered sites; None without nocturna.
    pipes: pipe and pipe-job tiles (tx, ty) for buffer bundles (pipe_tiles()).
    weights / demand / reach: the phase's scoring inputs (prepare()).
    geothermal: geothermal scout areas (x, y), the future term's steam fallback.
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
    return {
        "bounds": bounds,
        "outposts": outposts,
        "ghosts": read_ghosts(),
        "pois": poi_rows(points, read_known_biomass()),
        "sites": site_rows(sites),
        "range_m": range_m,
        "blocked": read_blocked(),
        "unsupported": read_unsupported(),
        "pipes": list(pipes),
        "hardness_limit": hardness_limit(kits),
        "weights": weights,
        "demand": demand,
        "reach": reach,
        "geothermal": list(geothermal),
    }


def reach_points(outposts):
    """Centres of home and of every outpost with a Charging Station: where a constructor can set out from."""
    out = []
    for entry in outposts:
        types = entry.get("types") or {}
        if entry.get("home") or types.get("charging_station", 0) > 0:
            out.append(outpost_centre(float(entry["x"]), float(entry["y"])))
    return out


def phase_inputs(outposts, early, drones=False):
    """
    (weights, reach) for prepare(): early = before the first mining drill (game_phase.drills()).
    drones: drones haul the freight, so a Pioneer's reach is worth nothing (reach_gain 0).
    """
    weights = WEIGHTS_EARLY if early else WEIGHTS
    if drones:
        weights = dict(weights, reach_gain=0.0)
    if not early:
        return (weights, None)
    return (weights, {"points": reach_points(outposts), "m": float(CONSTRUCTOR_REACH_M)})


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
