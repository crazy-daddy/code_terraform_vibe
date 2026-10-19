# Outlook of the fluid pass (fluid_plan): which fluid goes first, which
# producers are coming, and which outposts host a machine that takes fluids
# without a designation for it.
#
# Fluid priority (fluid_priority()): each pass routes the fluids most needed
# first. Per fluid F:
#   need   = consumer outposts of F whose role taking F is built
#            + FORECAST_WEIGHT x those designated only (the building pass
#            has not deployed the machine yet)
#   supply = built field producers of F + outposts whose role supplies F
#   score  = phase weight of F x need / (1 + supply)
# Highest score first; ties keep FLUID_ORDER, then the name. The phase is
# "early" before the mining-drill phase (drone_upgrade.upgrade_phase_reached()),
# "late" from then on; PHASE_FLUID_WEIGHTS holds a weight per phase and fluid
# (default 1.0).
#
# Planned producers (planned_producers()): fluid sites with no extractor yet,
# so the plan-ahead routes reach them before they are built:
#   - discovered fluid sites (journal.discovered_sites(), surveyed or not)
#     whose fluid is known and no extractor stands on; one with an extractor
#     ghost on it is named after the ghost ("ghost:<id>"), else "site:<id>",
#   - unresolved sonar contacts (survey.unsupported_targets) that
#     contact_inference types as one fluid kind (the biome at the contact is
#     a hard rule), not on a discovered site: "contact:<x>_<y>".
# Each gets a rank (1 + footprint gap to the nearest consumer outpost of its
# fluid), so with no network yet the nearest one is the route's source.
# Exotic deposits are planned only when their fluid is known.
#
# Contact hazards (contact_hazards(), site_hazards()): map contacts that may
# hold a fluid but are no planned producer yet (an unscanned "?" contact, an
# exotic deposit whose fluid is not known). fluid_plan keeps pipes of every
# medium the contact's fluid may take off its future extractor footprint (an
# exotic may be gas or liquid), so a new line never risks a fluid collision.
#
# Observed fluid roles (OBSERVED_FLUID_ROLES): roles whose fluids an outpost
# needs as soon as their building stands there, designated or not. The
# Biomass Mixer is placed by hand, so the outpost hosting it takes every
# essence and the liquifier_<biome> outposts get piped to it. The archive
# designation is not changed (only the founding pass writes it).

import autoplay_roles
import supply_tiers
from atomic import run_batched
from contact_inference import BIOME_KINDS, kind_weights, possible_kinds
from drone_upgrade import upgrade_phase_reached
from extractor_plan import DRILL_KIND_NAMES, MATCH_TILES, site_at
from grid_geom import extractor_box, extractor_tiles, outpost_box, tile_at, tile_key
from outpost_needs import read_outposts
from survey_requests import read_unsupported, target_coords
from swallow import swallowed

FLUID_ORDER = ("water", "oil", "steam")  # tie order of fluid_priority(); other fluids follow by name
FORECAST_WEIGHT = 0.5  # a consumer whose role is designated but not built counts this much
# {phase: {fluid: weight}}; a fluid not listed weighs 1.0
PHASE_FLUID_WEIGHTS = {"early": {}, "late": {}}
OBSERVED_FLUID_ROLES = ("biomass_mixer",)  # roles whose fluids follow the building, designated or not

# Contact kind -> fluid its extractor makes (exotic deposits need a survey to tell).
_KIND_FLUID = {"water": "water", "oil": "oil", "thermal": "steam"}
# Contact kind -> pipe media its fluid may take (an exotic is either until surveyed).
KIND_MEDIA = {"thermal": ("gas",), "water": ("liquid",), "oil": ("liquid",), "exotic": ("gas", "liquid")}
# Atomic slice sizes (worst operations per item measured in tests/test_autoplay_fluid.py).
TAKEN_CHUNK = 40  # site rows per taken_tiles() slice
POINT_CHUNK = 200  # map contacts per unscanned_points() slice
HAZARD_CHUNK = 5  # contacts per contact_hazards() slice (~650 operations each with a research_required entry)
SITE_HAZARD_CHUNK = 12  # discovered sites per site_hazards() slice


def game_phase():
    """Game phase for PHASE_FLUID_WEIGHTS: "early" before the mining-drill phase, "late" from then on."""
    return "late" if upgrade_phase_reached() else "early"


def outpost_types():
    """{outpost_id: {type_id: n}} of the deployed buildings; None when outpost_network is unreadable."""
    rows = read_outposts({})
    return {row["id"]: row["types"] for row in rows} if rows else None


def with_observed_roles(roles_map, types):
    """
    roles_map (autoplay.outpost_roles) with OBSERVED_FLUID_ROLES added where
    their building stands and the outpost does not designate them; a copy,
    the archive entry is not changed. types: outpost_types() (None: unchanged).
    """
    out = dict(roles_map)
    for outpost_id, counts in sorted((types or {}).items()):
        roles = autoplay_roles.role_list(out.get(outpost_id))
        extra = [name for name in OBSERVED_FLUID_ROLES if name not in roles and autoplay_roles.observed(name, counts)]
        if extra:
            out[outpost_id] = roles + extra
    return out


def consumer_counts(demand, roles_map, role_presets, types, home_id=None):
    """
    {fluid: (built, planned)} consumer outposts per fluid (takes it, does not
    make it; demand = autoplay_roles.demand()). built: a role of the outpost
    that takes the fluid stands (autoplay_roles.observed(); a role outside
    ROLE_CATALOG has no building and always stands). planned: designated only.
    types None (unreadable) counts every consumer as built.
    """
    out = {}
    for outpost_id in sorted(demand):
        entry = demand[outpost_id]
        counts = (types or {}).get(outpost_id, {})
        roles = autoplay_roles.fluid_roles(outpost_id, roles_map, home_id)
        for fluid in entry["in"]:
            if fluid in entry["out"]:
                continue
            takers = [name for name in roles if fluid in autoplay_roles.fluids_for(name, role_presets)["in"]]
            built = types is None or any(name not in autoplay_roles.ROLE_CATALOG or autoplay_roles.observed(name, counts) for name in takers)
            have = out.get(fluid, (0, 0))
            out[fluid] = (have[0] + 1, have[1]) if built else (have[0], have[1] + 1)
    return out


def supply_counts(producers, demand):
    """{fluid: built field producers (fluid_plan.site_rows()) + outposts supplying it}."""
    out = {}
    for row in producers:
        if row["fluid"]:
            out[row["fluid"]] = out.get(row["fluid"], 0) + 1
    for entry in demand.values():
        for fluid in entry.get("supply", []):
            out[fluid] = out.get(fluid, 0) + 1
    return out


def fluid_priority(fluids, consumers, supply, phase="early", weights=None):
    """
    The fluids most needed first (module header). consumers: consumer_counts(),
    supply: supply_counts(), weights: {phase: {fluid: weight}}
    (PHASE_FLUID_WEIGHTS when None).
    """
    table = (PHASE_FLUID_WEIGHTS if weights is None else weights).get(phase, {})

    def score(fluid):
        built, planned = consumers.get(fluid, (0, 0))
        return table.get(fluid, 1.0) * (built + FORECAST_WEIGHT * planned) / (1 + supply.get(fluid, 0))

    ranked = [(-score(fluid), FLUID_ORDER.index(fluid) if fluid in FLUID_ORDER else len(FLUID_ORDER), fluid) for fluid in set(fluids)]
    return [fluid for _score, _order, fluid in sorted(ranked)]


def inferred_contacts(targets, biome_of, rows):
    """
    [{"x", "y", "fluid"}] of the "poi_X_Y" entries of survey.unsupported_targets
    that contact_inference types as exactly one fluid kind (biome_of(x, y): the
    biome there), more than extractor_plan.MATCH_TILES from every site row (fluid_sites()).
    """
    out = []
    if not isinstance(targets, dict):
        return out
    for key in sorted(targets):
        coords = target_coords(key)
        if coords is None:
            continue
        weights = kind_weights(targets[key], biome_of(coords[0], coords[1]))
        fluid = _KIND_FLUID.get(list(weights)[0]) if len(weights) == 1 else None
        if fluid is None or site_at(rows, coords[0], coords[1]) is not None:
            continue
        out.append({"x": float(coords[0]), "y": float(coords[1]), "fluid": fluid})
    return out


def planned_producers(rows, ghosts, contacts, demand, outpost_xy):
    """
    [{"name", "fluid", "tiles", "rank"}] of the planned producers (module
    header): rows = fluid_sites() of the discovered sites, ghosts = structure
    rows ({"id", "kind", "x", "y"}), contacts = inferred_contacts().
    """
    ghost_on = {}
    for ghost in ghosts:
        if ghost["kind"] not in DRILL_KIND_NAMES:
            site_id = site_at(rows, ghost["x"], ghost["y"])
            if site_id is not None:
                ghost_on.setdefault(site_id, ghost["id"])
    spots = [(("ghost:" + ghost_on[row["id"]]) if row["id"] in ghost_on else ("site:" + row["id"]), row["fluid"], row["x"], row["y"]) for row in rows if not row["machine"] and row["fluid"]]
    spots += [(f"contact:{round(c['x'])}_{round(c['y'])}", c["fluid"], c["x"], c["y"]) for c in contacts]
    out = []
    for name, fluid, x, y in spots:
        boxes = supply_tiers.consumer_boxes(fluid, demand, outpost_xy) or [outpost_box(*xy) for _oid, xy in sorted(outpost_xy.items())]
        dist = supply_tiers.gap(extractor_box(x, y), boxes)
        out.append({"name": name, "fluid": fluid, "tiles": extractor_tiles(x, y), "rank": 1 + min(dist, supply_tiers.FAR)})
    return out


def taken_tiles(rows):
    """Tiles within extractor_plan.MATCH_TILES (Manhattan) of a slice of site rows, as one list (atomic-safe; contact_hazards())."""
    offsets = [tile_key(dx, dy) - tile_key(0, 0) for dx in range(-MATCH_TILES, MATCH_TILES + 1) for dy in range(-MATCH_TILES, MATCH_TILES + 1) if abs(dx) + abs(dy) <= MATCH_TILES]
    out = []
    for row in rows:
        base = tile_at(row["x"], row["y"])
        out.extend([base + offset for offset in offsets])
    return out


def contact_hazards(points, targets, biome_of, taken):
    """
    [{"name", "media", "tiles"}] of the unscanned map contacts ((x, y) whole
    metres) not on a `taken` tile (taken_tiles() of the site rows) that may
    hold a fluid: kinds from the contact's survey.unsupported_targets entry
    (possible_kinds()), else the one fluid kind of the biome there (BIOME_KINDS);
    media = the pipe media those kinds' fluids take (KIND_MEDIA).
    """
    targets = targets if isinstance(targets, dict) else {}
    out = []
    for x, y in points:
        if tile_at(x, y) in taken:
            continue
        biome = biome_of(x, y)
        entry = targets.get(f"poi_{int(x)}_{int(y)}")
        kinds = possible_kinds(entry, biome) if entry else ()
        if not kinds:
            kinds = BIOME_KINDS.get(biome or "", ())
        media = sorted({medium for kind in kinds for medium in KIND_MEDIA.get(kind, ())})
        if media:
            out.append({"name": f"poi:{int(x)}_{int(y)}", "media": media, "tiles": extractor_tiles(x, y)})
    return out


def site_hazards(sites):
    """[{"name", "media", "tiles"}] of the discovered exotic deposits without a cap whose fluid is not known: media = the site's medium, else both."""
    out = []
    for site in sites:
        try:
            if site.kind() != "exotic" or site.fluid() or site.cap_id():
                continue
            medium = site.medium()
            out.append({"name": "site:" + site.id, "media": [medium] if medium else list(KIND_MEDIA["exotic"]), "tiles": extractor_tiles(float(site.x), float(site.y))})
        except Exception as error:
            swallowed("fluid_outlook.site_hazards: site read", error)
    return out


def unscanned_points(points):
    """[(x, y)] of the unscanned contacts of a slice of nocturna.points_of_interest() (atomic-safe)."""
    return [(float(point.x), float(point.y)) for point in points if not point.scanned]


def read_hazards(rows):
    """contact_hazards() of the live unscanned contacts plus site_hazards() of the discovered sites; [] without nocturna."""
    planet = get_component("nocturna")
    journal = get_component("journal")
    if planet is None:
        return []

    def biome_of(x, y):
        try:
            return planet.biome_at(x, y)
        except Exception as error:
            swallowed("fluid_outlook.read_hazards: nocturna.biome_at", error)
            return None

    out = []
    try:
        points = run_batched(unscanned_points, planet.points_of_interest() or [], POINT_CHUNK)
        taken = set(run_batched(taken_tiles, rows, TAKEN_CHUNK))
        out = run_batched(contact_hazards, points, HAZARD_CHUNK, read_unsupported(), biome_of, taken)
    except Exception as error:
        swallowed("fluid_outlook.read_hazards: nocturna.points_of_interest", error)
    if journal is not None:
        try:
            out.extend(run_batched(site_hazards, journal.discovered_sites("nocturna") or [], SITE_HAZARD_CHUNK))
        except Exception as error:
            swallowed("fluid_outlook.read_hazards: journal.discovered_sites", error)
    return out


def discovered_fluid_rows(surveyed):
    """fluid_sites() of journal.discovered_sites() joined with the surveyed sites (by site id; surveyed wins)."""
    journal = get_component("journal")
    sites = []
    if journal is not None:
        try:
            sites = journal.discovered_sites("nocturna") or []
        except Exception as error:
            swallowed("fluid_outlook.discovered_fluid_rows: journal.discovered_sites", error)
    rows = {row["id"]: row for row in supply_tiers.fluid_sites(sites)}
    rows.update({row["id"]: row for row in supply_tiers.fluid_sites(surveyed)})
    return [rows[site_id] for site_id in sorted(rows)]


def read_contacts(rows):
    """inferred_contacts() of the live survey.unsupported_targets; [] without nocturna."""
    targets = read_unsupported()
    if not targets:
        return []
    planet = get_component("nocturna")
    if planet is None:
        return []

    def biome_of(x, y):
        try:
            return planet.biome_at(x, y)
        except Exception as error:
            swallowed("fluid_outlook.read_contacts: nocturna.biome_at", error)
            return None

    return inferred_contacts(targets, biome_of, rows)
