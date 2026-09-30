# Harvesting-field layout: which species grows in which cell.
#
# Pure logic, no game calls, so it can be checked offline with plain Python.
#
# The field is the fixed 8 x 24 grid around Nocturna Base (rows A-H, columns
# 1-24, docs/guide/faq.md). Plant rules only ever read the four orthogonal
# neighbours (docs/guide/biosphere_plants_tier.md):
#   spacer     -> no OTHER plant beside it (machines are fine)
#   cluster    -> at least two of its own species beside it (2x2 block minimum)
#   companion  -> the named species beside it
#   antagonist -> the named species NOT beside it
#   light / water / salt -> a treatment (Harvester for now, providers later)
#   shade      -> the cell must NOT be lit
#
# Rules come from SeedRecipe.requirements (seed_supply.py publishes them to
# `plant.recipes`); FALLBACK_RULES is the same data taken from
# docs/database/items_agriculture_and_feeds.md for when nothing is published.
#
# Two layouts, one switch (made once, when Field Automation is researched):
#   starter (STARTER_LAYOUT): 13 species (x13 diversity) cared for by hand,
#     no machine cells. A plant counts toward diversity while its conditions
#     are met, mature or not, so the STARTER_KEEP species are planted once,
#     kept cared for and never harvested (starter_kept()); the Harvester's
#     remaining time goes to a Crowncap crop (care-free, the best Forage per
#     Harvester hour) and to the salt trio, Glowvine and Grandbloom, which
#     get a daily care visit anyway. Pondmoss (a 2x2 needing 4 waterings a
#     day) and Sunspur (a lit spacer, 2 extra hops a day) aren't worth their
#     hand care. Actions cost no heat and plant cells +1 per hop against 3/h
#     cooling, so the Harvester's budget here is time, not heat; the gap
#     cells between patches are paved (path_cells()).
#   full: the whole 8 x 24 field, worked by Crop Automators and grown in
#     automator chunks (full_layout()), sized to what the Plant Terraformers
#     can use. A diversity garden with all 15 species (x15) on the left
#     (garden_cols()) plus a fill (FIELD_FILL):
#       "crowncap" (default, most of the game): CROWNCAP_GARDEN in columns
#         1-4, hand-cared and never harvested, + solid Crowncap, 8 Crop
#         Automators (CROWNCAP_AUTOMATORS). 60 Forage / 48 h on every cell =
#         1.25 Forage per cell-hour, no machines, power or water (Crowncap
#         only needs shade and its cluster).
#       "grandbloom": the checkerboard of FULL_LAYOUT, every gap a Grow
#         Lamp or Sprinkler. 150 / 72 h on half the cells = 1.04 per
#         cell-hour at Mk I, but x3 from Mk II lamps + sprinklers (x12 cap
#         at Mk IV), so it wins once machines are upgraded. Switching is a
#         rebuild, an operator decision: Data Archive key plant.field_fill
#         (harvester_planting.py).
#     Crowncap needs about twice the life forms per Forage (a seed per 60
#     Forage instead of per 150).
# expand_layout() (off) adds extra plants to the starter within a daily care
# budget, preferring species whose seed blend uses common life forms.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

ROWS = "ABCDEFGH"
NUM_ROWS = 8
NUM_COLS = 24

CARE_KINDS = ("light", "water", "salt")

# species -> reqs [(kind, related species or None)], growth hours, base Forage
FALLBACK_RULES = {
    "sunpetal":   {"reqs": [("light", None)], "growth_time": 12.0, "base_yield": 10},
    "shadeleaf":  {"reqs": [("shade", None)], "growth_time": 12.0, "base_yield": 10},
    "dewmoss":    {"reqs": [("water", None)], "growth_time": 12.0, "base_yield": 10},
    "lonethorn":  {"reqs": [("spacer", None)], "growth_time": 24.0, "base_yield": 25},
    "packfern":   {"reqs": [("cluster", None)], "growth_time": 24.0, "base_yield": 25},
    "twinvine":   {"reqs": [("companion", "dewmoss")], "growth_time": 24.0, "base_yield": 25},
    "spitebud":   {"reqs": [("antagonist", "packfern")], "growth_time": 24.0, "base_yield": 25},
    "sunspur":    {"reqs": [("light", None), ("spacer", None)], "growth_time": 24.0, "base_yield": 25},
    "glowvine":   {"reqs": [("light", None), ("water", None)], "growth_time": 48.0, "base_yield": 60},
    "crowncap":   {"reqs": [("shade", None), ("cluster", None)], "growth_time": 48.0, "base_yield": 60},
    "pondmoss":   {"reqs": [("water", None), ("cluster", None)], "growth_time": 48.0, "base_yield": 60},
    "saltbloom":  {"reqs": [("salt", None)], "growth_time": 72.0, "base_yield": 120},
    "brinethorn": {"reqs": [("salt", None), ("spacer", None)], "growth_time": 72.0, "base_yield": 120},
    "saltmate":   {"reqs": [("salt", None), ("companion", "saltbloom")], "growth_time": 72.0, "base_yield": 120},
    "grandbloom": {"reqs": [("light", None), ("water", None), ("spacer", None)], "growth_time": 72.0, "base_yield": 150},
}

# Life-form rarity (docs/database/items_life_forms.md). Stable game data; the
# only runtime source is a bio scan (LifeFormSample.rarity).
LIFE_FORM_RARITY = {
    "ice_algae": "common", "snow_moss": "common", "frost_lichen": "common",
    "cold_spores": "uncommon", "ice_crust": "uncommon", "frost_fungus": "rare",
    "sea_algae": "common", "tide_moss": "common", "shore_lichen": "common",
    "brine_plankton": "uncommon", "salt_crust": "uncommon", "coral_fungus": "rare",
    "vent_algae": "common", "steam_moss": "common", "heat_lichen": "common",
    "hot_spores": "uncommon", "heat_crust": "uncommon", "vent_fungus": "rare",
    "sulfur_moss": "common", "cinder_lichen": "common", "ash_spores": "common",
    "lava_algae": "uncommon", "magma_crust": "uncommon", "black_fungus": "rare",
    "cave_moss": "common", "stone_lichen": "common", "crystal_spores": "common",
    "deep_algae": "uncommon", "stone_mat": "uncommon", "cave_fungus": "rare",
}
# Relative cost of 1 t of a life form by rarity (rarer biosites cool down longer).
RARITY_COST = {"common": 1.0, "uncommon": 2.0, "rare": 5.0}

# v2 expansion is off until v1 has run live.
LAYOUT_EXPANSION_ENABLED = False
# Daily manual care actions (light/water/salt, 0.25 h each plus walking) the
# Harvester is allowed to take on in total, v1 block included (14 today).
MAX_DAILY_CARE = 20
# Total plants the v2 expansion may grow the field to. Every plant also costs
# a harvest (0.5 h) and a replant (0.5 h) per rotation plus a seed (3 t of
# life forms), so care-free species can't be added without limit.
MAX_FIELD_PLANTS = 40

_ABBREV = {
    "SU": "sunpetal", "SH": "shadeleaf", "DW": "dewmoss", "LT": "lonethorn",
    "PF": "packfern", "TV": "twinvine", "SP": "spitebud", "SS": "sunspur",
    "GV": "glowvine", "CC": "crowncap", "PM": "pondmoss", "SB": "saltbloom",
    "BT": "brinethorn", "SM": "saltmate", "GB": "grandbloom",
}

# Machine cells in a layout: never planted, never paved. One-letter tokens
# and the two-letter ones FULL_LAYOUT uses.
_MACHINE_ABBREV = {
    "L": "grow_lamp", "W": "sprinkler", "D": "dispenser", "A": "crop_automator",
    "GL": "grow_lamp", "SK": "sprinkler", "DS": "dispenser", "CA": "crop_automator",
}
# Service each machine kind provides (CARE_KINDS); Crop Automators provide none.
MACHINE_SERVICE = {"grow_lamp": "light", "sprinkler": "water", "dispenser": "salt"}

# 6 rows x 8 columns, anchored nearest the base (anchor_layout()). Found by
# a search that scores D x Forage/day with the real daily care tour (Manhattan
# hops over every light/water/salt cell, 0.5 h each): SU GV DW SB SM form one
# chain and the spacers BT, GB sit two hops apart, so the tour is 10 hops
# (~7.3 h/day with treatments) and ~17 Crowncap fill the rest of the day.
# Sunspur is left out: a lit spacer adds 2 hops + a treatment a day, more
# than its +1 diversity earns. TV beside DW and SM beside SB (companions), SP
# away from Packfern; "." cells stay empty (spacer gaps, the tour's walkway).
STARTER_LAYOUT = """
.  CC CC CC .  .  .  .
CC CC .  CC .  SH .  .
CC CC CC CC PF PF CC CC
CC CC CC .  PF PF CC CC
.  SP .  BT .  SM SB .
LT .  GB .  SU GV DW TV
"""
# Starter species planted once and never harvested: they only carry the
# diversity multiplier (care-free, or one care stop on the daily tour). Every
# other starter species is harvested and replanted.
STARTER_KEEP = ("sunpetal", "shadeleaf", "dewmoss", "lonethorn", "packfern",
                "twinvine", "spitebud")

# The whole field, fixed to the grid (column 1 = A1). XX is the Harvester
# base pad, which is always E13. Columns 1-5 are the diversity garden (all
# 15 species); column 6 on is the Grandbloom checkerboard: every Grandbloom
# (a spacer) touches only machines, lamp rows alternating with sprinkler
# rows so each gets both. CA = Crop Automator: every plant sits in some
# automator's centred 5 x 5 area. validate() and provider_violations() are
# clean for every full_layout() chunk count.
FULL_LAYOUT = """
CC CC SH PF PF GL GB GL GB GL GB GL GB GL GB GL GB GL GB GL GB GL GB GL
CC CC SK PF PF SK SK GB SK GB SK GB SK GB SK GB SK GB SK GB SK GB SK GB
SK CA DW TV GL CA GB GL GB CA GB GL GB CA GB GL GB CA GB GL GB CA GB GL
PM PM SK GV GL SK SK GB SK GB SK GB SK GB SK GB SK GB SK GB SK GB SK GB
PM PM SK .  SU GL GB GL GB GL GB GL XX GL GB GL GB GL GB GL GB GL GB GL
SK SK CA DS SP DS CA GB SK GB CA GB SK GB CA GB SK GB CA GB SK GB CA SS
LT .  SB SM DS GL GB GL GB GL GB GL GB GL GB GL GB GL GB GL GB GL GB GL
GL SS DS DS BT SK SK GB SK GB SK GB SK GB SK GB SK GB SK GB SK GB SK GB
"""
FULL_LAYOUT_BASE = "E13"
# What fills the field outside the garden: "crowncap" or "grandbloom" (see above).
FIELD_FILL = "crowncap"
FILL_SPECIES = {"crowncap": "crowncap", "grandbloom": "grandbloom"}
# The garden has no Grandbloom (it only grows in the checkerboard), so the
# crowncap fill keeps these checkerboard Grandblooms, with their machines,
# for x15 diversity. C7 sits between Crop Automator C6 and the lamp/sprinkler
# cells around it, inside chunk 1.
# Crowncap-phase garden (columns 1-CROWNCAP_GARDEN_COLS): the 14 non-fill
# species, no machines and no Crop Automator. The Harvester plants every
# cell once, keeps it cared for by hand and never harvests it (kept_crop()):
# a Dispenser burns 48 salt/day against 1 per salt cell by hand, and a hand
# light treatment lights only its own cell, so lit species may border the
# Crowncap fill. Found by an offline search: 3 columns can't hold all 14
# species' neighbour rules, 4 can with no spacer beside column 5; among
# those, the shortest care tour (14 hops over the 13 cells needing light,
# water or salt). "." cells stay empty (next to a spacer).
CROWNCAP_GARDEN = """
BT .  LT .
.  GB .  SH
SS .  .  .
.  PF PF .
SU PF PF .
SM SB GV .
SP TV PM PM
.  DW PM PM
"""
CROWNCAP_GARDEN_COLS = 4
# Crop Automators of the Crowncap fill: rows C and F, every 5th column, so
# their 5 x 5 areas cover columns 5-24 exactly and none reaches the garden.
CROWNCAP_AUTOMATORS = ("C7", "F7", "C12", "F12", "C17", "F17", "C22", "F22")
GARDEN_COLS = 5            # columns 1..GARDEN_COLS are FULL_LAYOUT's diversity garden (grandbloom fill)
AUTOMATOR_RADIUS = 2       # centred 5 x 5 service area

# Forage per hour a Plant Terraformer consumes: one batch per 3 h cycle.
TERRAFORMER_BATCH = {1: 1200, 2: 6600}
TERRAFORMER_CYCLE_H = 3.0



def garden_cols(fill=None):
    """Columns 1..n that hold the diversity garden for `fill` (FIELD_FILL by default)."""
    return CROWNCAP_GARDEN_COLS if (fill or FIELD_FILL) == "crowncap" else GARDEN_COLS


# ------------------------------------------------------------------ sectors

_RC_CACHE = {}          # {sector string: (row, col)}; pure function of the string
_NEIGHBOUR_CACHE = {}   # {sector: (orthogonal neighbour sectors)}
_AREA_CACHE = {}        # {sector: (automator_area sectors)}
_CACHE_LIMIT = 1024     # a cache past this many entries stops growing (junk sector strings)


def sector_to_rc(sector):
    """'E14' -> (4, 14); (None, None) for anything off the grid. Memoised per string."""
    found = _RC_CACHE.get(sector)
    if found is None:
        found = _parse_sector(sector)
        if len(_RC_CACHE) < _CACHE_LIMIT:
            _RC_CACHE[sector] = found
    return found


def _parse_sector(sector):
    if not sector or len(sector) < 2:
        return None, None
    row = sector[0].upper()
    if row not in ROWS:
        return None, None
    try:
        col = int(sector[1:])
    except ValueError:
        return None, None
    if not 1 <= col <= NUM_COLS:
        return None, None
    return ROWS.index(row), col


def rc_to_sector(r, c):
    if 0 <= r < NUM_ROWS and 1 <= c <= NUM_COLS:
        return f"{ROWS[r]}{c}"
    return None


def neighbours(sector):
    """Orthogonal neighbours of `sector` on the grid, as a tuple (memoised; do not expect a list)."""
    found = _NEIGHBOUR_CACHE.get(sector)
    if found is None:
        r, c = sector_to_rc(sector)
        out = []
        if r is not None and c is not None:
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                s = rc_to_sector(r + dr, c + dc)
                if s:
                    out.append(s)
        found = tuple(out)
        if len(_NEIGHBOUR_CACHE) < _CACHE_LIMIT:
            _NEIGHBOUR_CACHE[sector] = found
    return found


def all_sectors():
    return [f"{ROWS[r]}{c}" for r in range(NUM_ROWS) for c in range(1, NUM_COLS + 1)]


# -------------------------------------------------------------------- rules

def rules_from_published(published: "Any"):
    """Rules from the `plant.recipes` archive entry, falling back per species."""
    source: "Any" = published if isinstance(published, dict) else {}
    rules = {}
    for species, fallback in FALLBACK_RULES.items():
        e: "Any" = source.get(species)
        if not isinstance(e, dict) or e.get("reqs") is None:
            rules[species] = dict(fallback, blend=[], seed_id="seed_" + species)
            continue
        rules[species] = {
            "reqs": [(r[0], r[1] if len(r) > 1 else None) for r in e.get("reqs") or []],
            "growth_time": float(e.get("growth_time") or fallback["growth_time"]),
            "base_yield": int(e.get("base_yield") or fallback["base_yield"]),
            "blend": list(e.get("blend") or []),
            "seed_id": e.get("seed_id") or "seed_" + species,
        }
    return rules


def kinds(rules, species):
    return [k for k, _ in rules.get(species, {}).get("reqs", [])]


def care_kinds(rules, species):
    """Treatments the Harvester must renew for this species (light/water/salt)."""
    return [k for k in kinds(rules, species) if k in CARE_KINDS]


def daily_care(cells, rules):
    return sum(len(care_kinds(rules, sp)) for sp in cells.values())


# --------------------------------------------------------------- validation

def cell_violations(cells, sector, rules):
    """Rule kinds the plant at `sector` breaks given the planned `cells`."""
    species = cells.get(sector)
    if not species:
        return []
    nb = [cells.get(n) for n in neighbours(sector)]
    bad = []
    for kind, other in rules.get(species, {}).get("reqs", []):
        if kind == "spacer" and any(nb):
            bad.append(kind)
        elif kind == "cluster" and sum(1 for n in nb if n == species) < 2:
            bad.append(kind)
        elif kind == "companion" and other not in nb:
            bad.append(kind)
        elif kind == "antagonist" and other in nb:
            bad.append(kind)
    return bad


def validate(cells, rules=None):
    """[(sector, species, kind), ...] for every broken neighbour rule; [] if clean."""
    rules = rules or rules_from_published({})
    out = []
    for sector in sorted(cells):
        for kind in cell_violations(cells, sector, rules):
            out.append((sector, cells[sector], kind))
    return out


# ------------------------------------------------------------------- layout

def parse_block(text=STARTER_LAYOUT, abbrev=None):
    """[[species or None, ...], ...] rows of the block (machine cells -> None)."""
    abbrev = abbrev or _ABBREV
    block = []
    for line in text.strip().splitlines():
        block.append([abbrev.get(tok) for tok in line.split()])
    return block


def parse_machines(text=STARTER_LAYOUT):
    """Same grid as parse_block(), with the reserved machine kind per cell."""
    return parse_block(text, _MACHINE_ABBREV)


def place_block(block, col_offset, row_offset=0):
    """{sector: token} for the block with its top-left cell at (row_offset, col_offset), cols 1-based."""
    cells = {}
    for r, row in enumerate(block):
        for c, token in enumerate(row):
            if token:
                s = rc_to_sector(row_offset + r, col_offset + c)
                if s:
                    cells[s] = token
    return cells


def anchor_layout(base_sector, cell_status, block=None, machines=None):
    """
    Places the block where it costs the Harvester least: no plant on the base
    pad or on a provider, no machine cell on the base pad, as close to the
    base as possible, then fewest cells that still need clearing (loose
    items, unscanned ground, foreign crops). `cell_status` = {sector:
    Cell.status}. Returns (anchor sector of the top-left cell, {sector:
    species}, {sector: machine kind}) or (None, {}, {}) if nothing fits.
    """
    block = block or parse_block()
    machines = machines if machines is not None else parse_machines()
    height = len(block)
    width = max(len(row) for row in block)
    base_row, base_col = sector_to_rc(base_sector)
    best = None
    for row_off in range(0, NUM_ROWS - height + 1):
        for col_off in range(1, NUM_COLS - width + 2):
            cells = place_block(block, col_off, row_off)
            reserved = place_block(machines, col_off, row_off)
            if base_sector in cells or base_sector in reserved:
                continue
            if any(cell_status.get(s) in ("base", "provider") for s in cells):
                continue
            if any(cell_status.get(s) == "base" for s in reserved):
                continue
            if base_row is None or base_col is None:
                gap = 0
                centre = 0.0
            else:
                gap_r = max(0, row_off - base_row, base_row - (row_off + height - 1))
                gap_c = max(0, col_off - base_col, base_col - (col_off + width - 1))
                gap = gap_r + gap_c
                # Centre on the base when several offsets tie.
                centre = abs((col_off + (width - 1) / 2.0) - base_col) + abs((row_off + (height - 1) / 2.0) - base_row)
            dirty = sum(1 for s in list(cells) + list(reserved) if cell_status.get(s) not in (None, "empty"))
            score = (gap, dirty, centre)
            if best is None or score < best[0]:
                best = (score, rc_to_sector(row_off, col_off), cells, reserved)
    if best is None:
        return None, {}, {}
    return best[1], best[2], best[3]


def misplaced(layout, reserved, cell_plants):
    """
    Sectors holding a plant that is in the way of the layout: on a layout cell
    with the wrong species, on a reserved machine cell, or beside a layout
    cell (it could break a spacer or antagonist rule there). `cell_plants` =
    {sector: species} of every planted cell. Plants away from the block are
    left to finish their cycle.
    """
    out = []
    for sector, species in cell_plants.items():
        want = layout.get(sector)
        if want == species:
            continue
        if want or sector in reserved or any(n in layout for n in neighbours(sector)):
            out.append(sector)
    return sorted(out)


# ------------------------------------------------------------- full layout

def provider_violations(cells, reserved):
    """
    [(sector, species, problem)] where the machines in `reserved` ({sector:
    kind}) don't give a plant a care service it needs ("no light" etc.) or
    light a shade plant ("lit"). Species rules as in FALLBACK_RULES.
    """
    rules = rules_from_published({})
    out = []
    for sector in sorted(cells):
        species = cells[sector]
        served = [MACHINE_SERVICE.get(reserved.get(n) or "") for n in neighbours(sector)]
        for kind in kinds(rules, species):
            if kind in CARE_KINDS and kind not in served:
                out.append((sector, species, "no " + kind))
            elif kind == "shade" and "light" in served:
                out.append((sector, species, "lit"))
    return out


def automator_area(sector):
    """Sectors a Crop Automator at `sector` serves (its centred 5 x 5, itself excluded), as a memoised tuple."""
    found = _AREA_CACHE.get(sector)
    if found is None:
        r, c = sector_to_rc(sector)
        out = []
        if r is not None and c is not None:
            for dr in range(-AUTOMATOR_RADIUS, AUTOMATOR_RADIUS + 1):
                for dc in range(-AUTOMATOR_RADIUS, AUTOMATOR_RADIUS + 1):
                    s = rc_to_sector(r + dr, c + dc)
                    if s and s != sector:
                        out.append(s)
        found = tuple(out)
        if len(_AREA_CACHE) < _CACHE_LIMIT:
            _AREA_CACHE[sector] = found
    return found


def priority_seeds(cells, garden, fill, rules):
    """
    Seed ids to make first, sorted: every species in the diversity garden
    except the fill species (FILL_SPECIES[fill]). The garden carries the
    field's species multiplier, so its seeds (and their life forms) come
    before the fill's bulk. Published as plant.seed_demand["priority"] and
    read by lib/seed_supply.py.
    """
    fill_species = FILL_SPECIES.get(fill or FIELD_FILL)
    out = set()
    for s in garden or []:
        species = cells.get(s)
        if species and species != fill_species:
            out.add((rules.get(species) or {}).get("seed_id") or "seed_" + species)
    return sorted(out)


def starter_kept(cells):
    """Sorted sectors of a starter layout whose species is in STARTER_KEEP (never harvested)."""
    return sorted(s for s, sp in cells.items() if sp in STARTER_KEEP)


def kept_crop(sector, plant, cells, garden):
    """
    True for a kept cell (full-layout garden, starter_kept()) holding its
    own layout species: never harvested. A mature crop still counts toward
    the species multiplier while its conditions are met, and replanting
    risks a species missing its seed; the other cells carry the Forage. A
    wrong species in a kept cell (after a rebuild) is not kept.
    """
    return bool(plant) and sector in (garden or ()) and cells.get(sector) == plant


def automator_owner(sector, automators):
    """
    The Crop Automator (sector) among `automators` that owns `sector`, or
    None if none reaches it. Areas overlap, so the nearest one owns it
    (Chebyshev distance, then Manhattan, then sector id): every cell has
    exactly one owner. Used by lib/crop_automator.py (which cells to
    queue).
    """
    r, c = sector_to_rc(sector)
    if r is None or c is None:
        return None

    def rank(ca):
        ar, ac = sector_to_rc(ca)
        if ar is None or ac is None:
            return (99, 99, ca)
        return (max(abs(ar - r), abs(ac - c)), abs(ar - r) + abs(ac - c), ca)

    reach = [ca for ca in automators if sector in automator_area(ca)]
    return min(reach, key=rank) if reach else None


def _needed_machines(cells, machines):
    """{sector: kind} of the providers in `machines` that give some plant in `cells` a service it needs."""
    rules = rules_from_published({})
    out = {}
    for s, species in cells.items():
        needs = care_kinds(rules, species)
        for n in neighbours(s):
            kind = machines.get(n)
            if MACHINE_SERVICE.get(kind or "") in needs:
                out[n] = kind
    return out


def _prune_clusters(cells, species):
    """Drops `species` cells with fewer than two of their own kind beside them, until none are left."""
    changed = True
    while changed:
        changed = False
        for s in [s for s, sp in cells.items() if sp == species]:
            if sum(1 for n in neighbours(s) if cells.get(n) == species) < 2:
                del cells[s]
                changed = True
    return cells


_FULL_PARTS_CACHE = {}    # {fill: _full_parts result}; the result is shared, callers must not mutate it


def _full_parts(fill=None):
    """Memoised per fill; the returned dicts and set are shared and read-only. See _compute_full_parts()."""
    fill = fill or FIELD_FILL
    found = _FULL_PARTS_CACHE.get(fill)
    if found is None:
        found = _compute_full_parts(fill)
        _FULL_PARTS_CACHE[fill] = found
    return found


def _compute_full_parts(fill=None):
    """
    (plants {sector: species}, machines {sector: kind}, garden set) of the
    whole field for `fill` (FIELD_FILL by default). "grandbloom" is
    FULL_LAYOUT as drawn. "crowncap" is CROWNCAP_GARDEN in columns
    1-CROWNCAP_GARDEN_COLS, the CROWNCAP_AUTOMATORS, and Crowncap on every
    other cell except the base pad, cells a Grow Lamp lights (shade) and
    cells beside a spacer; Crowncaps left with fewer than two Crowncap
    neighbours are dropped.
    """
    fill = fill or FIELD_FILL
    if fill == "grandbloom":
        plants = place_block(parse_block(FULL_LAYOUT), 1)
        machines = place_block(parse_machines(FULL_LAYOUT), 1)
        garden = set(s for s in plants if (sector_to_rc(s)[1] or 0) <= GARDEN_COLS)
        return plants, machines, garden
    species = FILL_SPECIES.get(fill, "crowncap")
    garden_plants = place_block(parse_block(CROWNCAP_GARDEN), 1)
    machines = place_block(parse_machines(CROWNCAP_GARDEN), 1)
    for s in CROWNCAP_AUTOMATORS:
        machines[s] = "crop_automator"
    rules = rules_from_published({})
    lit = set(n for m, k in machines.items() if k == "grow_lamp" for n in neighbours(m))
    beside_spacer = set(n for p, sp in garden_plants.items() if "spacer" in kinds(rules, sp) for n in neighbours(p))
    fill_cells = {}
    for s in all_sectors():
        if (sector_to_rc(s)[1] or 0) <= CROWNCAP_GARDEN_COLS or s == FULL_LAYOUT_BASE:
            continue
        if s in machines or s in lit or s in beside_spacer:
            continue
        fill_cells[s] = species
    # Crowncap drawn inside the garden counts as a partner for the fill next to it.
    both = _prune_clusters(dict({k: v for k, v in garden_plants.items() if v == species}, **fill_cells), species)
    out = dict(garden_plants)
    out.update({k: v for k, v in both.items() if k not in garden_plants})
    garden = set(s for s in out if (sector_to_rc(s)[1] or 0) <= CROWNCAP_GARDEN_COLS)
    return out, machines, garden


def _automators_in_order(machines):
    """Crop Automator sectors, left to right (garden side first), then top to bottom."""
    cas = [s for s, k in machines.items() if k == "crop_automator"]
    return sorted(cas, key=lambda s: ((sector_to_rc(s)[1] or 0), (sector_to_rc(s)[0] or 0)))


def snake(sectors):
    """`sectors` row by row, A first, alternating direction (A left to right, B right to left, ...)."""
    def key(s):
        r, c = sector_to_rc(s)
        r = r or 0
        c = c or 0
        return (r, c if r % 2 == 0 else -c)
    return sorted(sectors, key=key)


_WORK_ORDER_MEMO = [None, None]   # [inputs key, groups] of the last work_order() call


def work_order(cells, reserved, fill=None):
    """Memoised on the sectors of cells / reserved and the garden width; the returned groups are shared and read-only."""
    key = (tuple(sorted(cells)), tuple(sorted(reserved.items())), garden_cols(fill))
    if _WORK_ORDER_MEMO[0] != key:
        _WORK_ORDER_MEMO[1] = _compute_work_order(cells, reserved, fill)
        _WORK_ORDER_MEMO[0] = key
    return _WORK_ORDER_MEMO[1]


def _compute_work_order(cells, reserved, fill=None):
    """
    The full layout's build order as groups of sectors (plants and machine
    cells together): group 0 is the garden (columns 1..garden_cols(fill))
    plus any cell no Crop Automator in `reserved` reaches, in a snake, row
    by row; then one group per Crop Automator outside the garden, left to
    right, its own cell first and then the cells of its area not in an
    earlier group, in a snake.
    """
    everything = set(cells) | set(reserved)
    cols = garden_cols(fill)
    reach = set()
    for ca in [s for s, k in reserved.items() if k == "crop_automator"]:
        reach |= set(automator_area(ca)) | {ca}
    garden = [s for s in everything if (sector_to_rc(s)[1] or 0) <= cols or s not in reach]
    groups = [snake(garden)]
    seen = set(garden)
    for ca in _automators_in_order(reserved):
        if ca in seen:
            continue
        area = [s for s in automator_area(ca) if s in everything and s not in seen and s != ca]
        groups.append([ca] + snake(area))
        seen |= set(area)
        seen.add(ca)
    return groups


def _garden_automators(order, garden):
    """
    How many automators (in order) it takes to cover every garden plant any
    of them reaches: 0 for a garden outside every automator area (crowncap).
    """
    reach = set()
    for ca in order:
        reach |= set(automator_area(ca))
    garden = set(garden) & reach
    if not garden:
        return 0
    covered = set()
    for n, ca in enumerate(order):
        covered |= set(automator_area(ca))
        if garden <= covered:
            return n + 1
    return len(order)


_CHUNK_COUNT_CACHE = {}   # {fill: full_chunk_count}
_FULL_LAYOUT_CACHE = {}   # {(chunks, fill): (cells, reserved, garden)}


def full_chunk_count(fill=None):
    """Largest useful `chunks` for full_layout() (chunk 1 = garden automators). Memoised per fill."""
    fill = fill or FIELD_FILL
    found = _CHUNK_COUNT_CACHE.get(fill)
    if found is None:
        plants, machines, garden = _full_parts(fill)
        order = _automators_in_order(machines)
        found = len(order) - _garden_automators(order, garden) + 1
        _CHUNK_COUNT_CACHE[fill] = found
    return found


def full_layout(chunks, fill=None):
    """Memoised per (chunks, fill); returns fresh copies of the result each call. See _compute_full_layout()."""
    fill = fill or FIELD_FILL
    key = (chunks, fill)
    found = _FULL_LAYOUT_CACHE.get(key)
    if found is None:
        found = _compute_full_layout(chunks, fill)
        _FULL_LAYOUT_CACHE[key] = found
    cells, reserved, garden = found
    return dict(cells), dict(reserved), list(garden)


def _compute_full_layout(chunks, fill=None):
    """
    The first `chunks` chunks of FULL_LAYOUT: (cells {sector: species},
    reserved {sector: machine kind}, garden [sectors]). Chunk 1 = the
    garden and the automators it takes to cover it (none for the crowncap
    garden), with every fill plant they reach; each further chunk adds the
    next automator, left to right,
    with the checkerboard plants in its area. Reserved = the included
    automators plus only the providers an included plant touches. A subset
    of a valid layout stays valid: dropping plants can't break a spacer or
    antagonist rule, and each included cluster/companion keeps its partners
    (the whole garden is always in).
    """
    plants, machines, garden = _full_parts(fill)
    order = _automators_in_order(machines)
    n_ca = min(len(order), _garden_automators(order, garden) + max(0, chunks - 1))
    cas = order[:n_ca]
    area = set()
    for ca in cas:
        area |= set(automator_area(ca))
    cells = {s: sp for s, sp in plants.items() if s in garden or s in area}
    # A chunk edge can cut a fill cluster: drop fill cells left without two partners.
    # (Crowncap drawn inside the garden is fill too: its partners may lie outside.)
    fill_species = FILL_SPECIES.get(fill or FIELD_FILL)
    if fill_species == "crowncap":
        fill_cells = _prune_clusters({k: v for k, v in cells.items() if v == fill_species}, fill_species)
        cells = dict({k: v for k, v in cells.items() if v != fill_species}, **fill_cells)
    reserved = {ca: "crop_automator" for ca in cas}
    reserved.update(_needed_machines(cells, machines))
    return cells, reserved, sorted(garden)


def forage_per_hour(cells, rules=None, garden=()):
    """
    Forage/h the planted `cells` supply at Mk I providers: base yield per
    growth hour x species diversity. `garden` cells count toward diversity
    only (never harvested, see kept_crop()). Higher provider tiers only raise
    it, so sizing the field with this errs towards more plants than needed.
    """
    rules = rules or rules_from_published({})
    diversity = len(set(cells.values()))
    garden = set(garden or ())
    per_h = 0.0
    for sector, species in cells.items():
        if sector in garden:
            continue
        r = rules.get(species, {})
        per_h += r.get("base_yield", 0) / (r.get("growth_time") or 1.0)
    return per_h * diversity


def chunks_for_demand(forage_per_h, rules=None, fill=None):
    """Fewest full_layout() chunks whose plants supply forage_per_h (at least 1)."""
    total = full_chunk_count(fill)
    for n in range(1, total + 1):
        cells, _, garden = full_layout(n, fill)
        if forage_per_hour(cells, rules, garden) >= forage_per_h:
            return n
    return total


def terraformer_demand(terraformers):
    """Forage/h the Plant Terraformers use; `terraformers` = the plant.terraformer telemetry dict."""
    total = 0.0
    for e in (terraformers or {}).values():
        if not isinstance(e, dict) or e.get("status") == "complete":
            continue
        tier = e.get("tier") or 1
        total += TERRAFORMER_BATCH.get(tier, TERRAFORMER_BATCH[1]) / TERRAFORMER_CYCLE_H
    return total


# -------------------------------------------------------------------- path

def path_cells(layout, blocked=()):
    """
    A short path of non-plant cells joining every plant patch: moving onto a
    plant or an item cell costs +1 heat, onto an empty cell +7, so paving
    these few cells (drop an item/seed on them) lets the Harvester reach any
    plant over +1 cells only. Greedy Steiner tree: start from the biggest
    4-connected patch and repeatedly join the nearest remaining patch by the
    fewest non-plant cells (BFS). `blocked` cells (base pad) are never used.
    Reserved machine cells belong in `blocked` too. 0 cells for the starter
    block (one patch).
    """
    plants = set(layout)
    patches = []
    seen = set()
    for start in sorted(plants):
        if start in seen:
            continue
        patch = {start}
        seen.add(start)
        stack = [start]
        while stack:
            x = stack.pop()
            for n in neighbours(x):
                if n in plants and n not in seen:
                    seen.add(n)
                    patch.add(n)
                    stack.append(n)
        patches.append(patch)
    if not patches:
        return []
    patches.sort(key=lambda p: (-len(p), min(p)))
    joined = set(patches[0])
    path = set()
    remaining = patches[1:]
    while remaining:
        sources = sorted(joined | path)
        prev = {x: None for x in sources}
        queue = list(sources)
        head = 0
        hit = None
        while head < len(queue) and hit is None:
            x = queue[head]
            head += 1
            for n in neighbours(x):
                if n in prev:
                    continue
                prev[n] = x
                if n in plants and n not in joined:
                    hit = n
                    break
                if n not in plants and n not in blocked:
                    queue.append(n)
        if hit is None:
            break
        x = prev[hit]
        while x is not None and x not in joined and x not in path:
            path.add(x)
            x = prev[x]
        patch = [p for p in remaining if hit in p][0]
        joined |= patch
        remaining = [p for p in remaining if p is not patch]
    return sorted(path)


# ------------------------------------------------------- v2: rarity expansion

def blend_cost(rules, species, rarity=None):
    rarity = rarity or LIFE_FORM_RARITY
    blend = rules.get(species, {}).get("blend") or []
    if not blend:
        return 3.0 * RARITY_COST["uncommon"]
    return sum(RARITY_COST.get(rarity.get(f, "uncommon"), 2.0) for f in blend)


def species_score(rules, species, rarity=None):
    """Forage per growth hour per unit of seed cost: higher = better filler."""
    r = rules.get(species, {})
    hours = r.get("growth_time") or 1.0
    return r.get("base_yield", 0) / hours / blend_cost(rules, species, rarity)


def expand_layout(cells, rules, blocked=(), max_daily_care=MAX_DAILY_CARE,
                  max_plants=MAX_FIELD_PLANTS, exclude=(), rarity=None):
    """
    Greedy v2: adds single plants of the best-scoring species to free cells
    while every touched plant stays valid and total daily care stays within
    max_daily_care. `blocked` = sectors never planted (base pad, providers).
    Only the new cell and its neighbours are re-checked, so this stays cheap.
    Returns a new dict; `cells` is not modified.
    """
    out = dict(cells)
    ranked = sorted((sp for sp in rules if sp not in exclude),
                    key=lambda sp: -species_score(rules, sp, rarity))
    care = daily_care(out, rules)
    for species in ranked:
        need = len(care_kinds(rules, species))
        for sector in all_sectors():
            if max_plants is not None and len(out) >= max_plants:
                return out
            if sector in out or sector in blocked:
                continue
            if care + need > max_daily_care:
                break
            out[sector] = species
            touched = [sector] + [n for n in neighbours(sector) if n in out]
            if any(cell_violations(out, s, rules) for s in touched):
                del out[sector]
                continue
            care += need
    return out
