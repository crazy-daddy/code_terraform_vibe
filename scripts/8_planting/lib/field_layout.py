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
#   starter (STARTER_LAYOUT): the 2 x 4 block of the 8 species that are
#     neither spacers nor clusters (x8 diversity). Every cell touches the
#     next, so the Harvester walks plant cells only (+1 heat) and never needs
#     a paved path. Hand care for all 15 species needs ~38 Harvester hours a
#     day, so 8 is what one Harvester sustains. Machines unlocked before
#     automation (lamp, sprinkler, dispenser) only save hand-care time, which
#     isn't worth a rebuild, so the starter has no machine cells.
#   full: the whole 8 x 24 field, worked by Crop Automators and grown in
#     automator chunks (full_layout()), sized to what the Plant Terraformers
#     can use. A diversity garden with all 15 species (x15) in columns 1-5
#     plus a fill (FIELD_FILL):
#       "crowncap" (default, most of the game): CROWNCAP_GARDEN + solid
#         Crowncap, 10 Crop Automators (CROWNCAP_AUTOMATORS). 60 Forage /
#         48 h on every cell = 1.25 Forage per cell-hour, no machines, power
#         or water (Crowncap only needs shade and its cluster).
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

# 2 rows x 4 columns: the 8 species that are neither spacers nor clusters.
# TV beside DW (companion), SM beside SB (companion), SP away from packfern.
STARTER_LAYOUT = """
DW TV SB SM
SU GV SP SH
"""

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
# Crowncap-phase garden (columns 1-5), found by an offline search that
# maximised the whole field's Forage/h: it costs 14.6 Forage/h (x1, before
# diversity) against pure Crowncap, one Crowncap cell more than the best
# garden allowed to spread over 8 columns, but it fits under the first two
# Crop Automators (C3, F3), so chunk 1 needs 2 of them. 1 Grow Lamp lights
# SS, SU, GV, GB and no shade plant; 5 Sprinklers water GV, GB, DW and each
# pondmoss cell; 2 Dispensers salt SB, SM, BT. CC cells are Crowncap fill
# inside the garden; "." cells must stay empty (next to a spacer).
CROWNCAP_GARDEN = """
SP SH PF PF CC
CC CC PF PF CC
CC CC CA SU CC
SB DS SS GL GV
SM .  .  GB SK
DS BT CA SK DW
.  SK PM PM TV
LT SK PM PM SK
"""
# Crop Automators outside the Crowncap garden: rows C and F, every 5th
# column, so 10 automators (2 in the garden) cover all 192 cells.
CROWNCAP_AUTOMATORS = ("C8", "F8", "C13", "F13", "C18", "F18", "C23", "F23")
GARDEN_COLS = 5            # columns 1..GARDEN_COLS are the diversity garden (both fills)
AUTOMATOR_RADIUS = 2       # centred 5 x 5 service area

# Forage per hour a Plant Terraformer consumes: one batch per 3 h cycle.
TERRAFORMER_BATCH = {1: 1200, 2: 6600}
TERRAFORMER_CYCLE_H = 3.0


# ------------------------------------------------------------------ sectors

def sector_to_rc(sector):
    """'E14' -> (4, 14); (None, None) for anything off the grid."""
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
    r, c = sector_to_rc(sector)
    if r is None or c is None:
        return []
    out = []
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        s = rc_to_sector(r + dr, c + dc)
        if s:
            out.append(s)
    return out


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
    """Sectors a Crop Automator at `sector` serves (its centred 5 x 5, itself excluded)."""
    r, c = sector_to_rc(sector)
    if r is None or c is None:
        return []
    out = []
    for dr in range(-AUTOMATOR_RADIUS, AUTOMATOR_RADIUS + 1):
        for dc in range(-AUTOMATOR_RADIUS, AUTOMATOR_RADIUS + 1):
            s = rc_to_sector(r + dr, c + dc)
            if s and s != sector:
                out.append(s)
    return out


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


def _full_parts(fill=None):
    """
    (plants {sector: species}, machines {sector: kind}, garden set) of the
    whole field for `fill` (FIELD_FILL by default). "grandbloom" is
    FULL_LAYOUT as drawn. "crowncap" is CROWNCAP_GARDEN in columns 1-5, the
    CROWNCAP_AUTOMATORS, and Crowncap on every other cell except the base
    pad, cells a Grow Lamp lights (shade) and cells beside a spacer;
    Crowncaps left with fewer than two Crowncap neighbours are dropped.
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
        if (sector_to_rc(s)[1] or 0) <= GARDEN_COLS or s == FULL_LAYOUT_BASE:
            continue
        if s in machines or s in lit or s in beside_spacer:
            continue
        fill_cells[s] = species
    # Crowncap drawn inside the garden counts as a partner for the fill next to it.
    both = _prune_clusters(dict({k: v for k, v in garden_plants.items() if v == species}, **fill_cells), species)
    out = dict(garden_plants)
    out.update({k: v for k, v in both.items() if k not in garden_plants})
    garden = set(s for s in out if (sector_to_rc(s)[1] or 0) <= GARDEN_COLS)
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


def work_order(cells, reserved):
    """
    The full layout's build order as groups of sectors (plants and machine
    cells together): group 0 is the garden (columns 1..GARDEN_COLS) in a
    snake, row by row; then one group per Crop Automator outside the garden,
    left to right, its own cell first and then the cells of its area not in
    an earlier group, in a snake.
    """
    everything = set(cells) | set(reserved)
    garden = [s for s in everything if (sector_to_rc(s)[1] or 0) <= GARDEN_COLS]
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
    """How many automators (in order) it takes to cover every garden plant."""
    covered = set()
    for n, ca in enumerate(order):
        covered |= set(automator_area(ca))
        if garden <= covered:
            return n + 1
    return len(order)


def full_chunk_count(fill=None):
    """Largest useful `chunks` for full_layout() (chunk 1 = garden automators)."""
    plants, machines, garden = _full_parts(fill)
    order = _automators_in_order(machines)
    return len(order) - _garden_automators(order, garden) + 1


def full_layout(chunks, fill=None):
    """
    The first `chunks` chunks of FULL_LAYOUT: (cells {sector: species},
    reserved {sector: machine kind}, garden [sectors]). Chunk 1 = the
    automators it takes to cover the garden, with every checkerboard plant
    they reach; each further chunk adds the next automator, left to right,
    with the checkerboard plants in its area. Reserved = the included
    automators plus only the providers an included plant touches. A subset
    of a valid layout stays valid: dropping plants can't break a spacer or
    antagonist rule, and each included cluster/companion keeps its partners
    (the whole garden is always in).
    """
    plants, machines, garden = _full_parts(fill)
    order = _automators_in_order(machines)
    n_ca = max(1, min(len(order), _garden_automators(order, garden) + max(0, chunks - 1)))
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


def forage_per_hour(cells, rules=None):
    """
    Forage/h the planted `cells` supply at Mk I providers: base yield per
    growth hour x species diversity. Higher provider tiers only raise it, so
    sizing the field with this errs towards more plants than needed.
    """
    rules = rules or rules_from_published({})
    diversity = len(set(cells.values()))
    per_h = 0.0
    for species in cells.values():
        r = rules.get(species, {})
        per_h += r.get("base_yield", 0) / (r.get("growth_time") or 1.0)
    return per_h * diversity


def chunks_for_demand(forage_per_h, rules=None, fill=None):
    """Fewest full_layout() chunks whose plants supply forage_per_h (at least 1)."""
    total = full_chunk_count(fill)
    for n in range(1, total + 1):
        cells, _, _ = full_layout(n, fill)
        if forage_per_hour(cells, rules) >= forage_per_h:
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
