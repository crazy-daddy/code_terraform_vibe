# Contact inference: what an unresolved sonar contact can still be.
#
# A sonar sweep lists contacts it could not identify in SonarScanResult.blocked,
# each with a reason; vehicle_claims.blacklist_target() stores them in
# survey.unsupported_targets together with the sonar's hardness limit and the
# scan researches unlocked at that moment. The reason narrows the contact's
# kind (fixed game rules, docs/gameknowledge/survey_contacts.md):
#   wrong_scanner      -> biomass
#   too_hard           -> mineral above the tool's hardness limit
#   tier_too_low       -> oil (Petroleum Survey unlocked, sonar below Deep)
#   research_required  -> a fluid or exotic kind whose classification research
#                         was locked when the entry was written
# World generation places each fluid kind in one biome only (BIOME_KINDS), so
# the biome at the contact (nocturna.biome_at) settles a research_required
# contact by itself, even for entries written before the researches were
# recorded. possible_kinds() applies both rules; kind_weights() turns what is
# left into a uniform distribution for the planner's expected-value scoring.
# Pure functions, no game calls.

ALL_TECH_KINDS = ("thermal", "water", "oil", "exotic")

# Scan research that classifies each kind; a kind stays possible under
# "research_required" while any of its researches was locked. Exotic sites
# need Exotic Husbandry (common) or Deep Exotics (rare).
SURVEY_RESEARCH = {
    "thermal": ("research_geological_survey",),
    "water": ("research_hydrology_survey",),
    "oil": ("research_petroleum_survey",),
    "exotic": ("research_exotic_husbandry", "research_deep_exotics"),
}

# Readable names of the scan researches, for marker labels.
RESEARCH_NAMES = {
    "research_geological_survey": "Geological Survey",
    "research_hydrology_survey": "Hydrology Survey",
    "research_petroleum_survey": "Petroleum Survey",
    "research_exotic_husbandry": "Exotic Husbandry",
    "research_deep_exotics": "Deep Exotics",
}

# Biome each fluid kind spawns in (world generation places every vent, well
# and deposit only where the biome test passes, fallback included). Minerals
# and biomass spawn everywhere.
BIOME_KINDS = {
    "geothermal": ("thermal",),
    "frozen": ("water",),
    "coastal": ("water",),
    "volcanic": ("oil",),
    "deep": ("exotic",),
}

KIND_NAMES = {
    "thermal": "Thermal vent",
    "water": "Water well",
    "oil": "Oil well",
    "exotic": "Exotic deposit",
    "biomass": "Bio contact",
}


def entry_reason(entry):
    """Blacklist reason of an unsupported-targets entry ("" when unreadable)."""
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("reason", entry.get("status", "")) or "")


def _research_kinds(entry):
    """Kinds left by the blacklist reason and the scan researches on record."""
    reason = entry_reason(entry)
    if reason == "wrong_scanner":
        return ("biomass",)
    if reason == "too_hard":
        return ("mineral",)
    if reason == "tier_too_low":
        return ("oil",)
    if reason != "research_required":
        return ()
    unlocked = entry.get("unlocked_scan_researches")
    if not isinstance(unlocked, (list, tuple)):
        return ALL_TECH_KINDS
    kinds = tuple(kind for kind in ALL_TECH_KINDS
                  if not all(rid in unlocked for rid in SURVEY_RESEARCH[kind]))
    # Every classifying research was unlocked yet the sweep still said
    # research_required: the record is inconsistent, so assume nothing.
    return kinds or ALL_TECH_KINDS


def possible_kinds(entry, biome=None) -> "tuple[str, ...]":
    """
    Tuple of site kinds the contact behind `entry` (one survey.unsupported_targets
    value) can still be, from its reason, the scan researches on record and the
    biome at the contact (`biome`, else the entry's "biome" field).
    () for reasons that say nothing about the kind (depleted, out_of_range, ...).
    """
    kinds = _research_kinds(entry)
    if biome is None and isinstance(entry, dict):
        biome = entry.get("biome")
    allowed = BIOME_KINDS.get(biome or "")
    # Minerals and biomass spawn in every biome.
    if allowed is None or kinds in ((), ("mineral",), ("biomass",)):
        return kinds
    narrowed = tuple(kind for kind in kinds if kind in allowed)
    # Research and biome disagree: one record is wrong, keep the research view.
    return narrowed or kinds


def inferred_kind(entry, biome=None):
    """The contact's kind when the rules leave exactly one, else None."""
    kinds = possible_kinds(entry, biome)
    return kinds[0] if len(kinds) == 1 else None


def min_hardness(entry):
    """Lowest mineral hardness a "too_hard" contact can have (tool limit + 1); None otherwise."""
    if entry_reason(entry) != "too_hard":
        return None
    try:
        return int(float(entry.get("hardness_limit", 1))) + 1
    except (TypeError, ValueError):
        return 2


def kind_weights(entry, biome=None):
    """{kind: probability} over possible_kinds(entry, biome), uniform. {} when the reason says nothing."""
    kinds = possible_kinds(entry, biome)
    if not kinds:
        return {}
    return {kind: 1.0 / len(kinds) for kind in kinds}


def needed_research(entry, biome=None):
    """
    Names of the locked scan researches that would classify the contact
    (research_required only): the inferred kind's, else every candidate's.
    """
    if entry_reason(entry) != "research_required":
        return []
    unlocked = entry.get("unlocked_scan_researches")
    if not isinstance(unlocked, (list, tuple)):
        unlocked = []
    names = []
    for kind in possible_kinds(entry, biome):
        for rid in SURVEY_RESEARCH.get(kind, ()):
            name = RESEARCH_NAMES[rid]
            if rid not in unlocked and name not in names:
                names.append(name)
    return names


def describe(entry, biome=None):
    """Short label for a map marker: the inferred kind, or the remaining candidates."""
    kinds = possible_kinds(entry, biome)
    if not kinds:
        return ""
    if len(kinds) == 1:
        kind = kinds[0]
        if kind == "mineral":
            return f"Mineral, hardness {min_hardness(entry)}+"
        return KIND_NAMES.get(kind, f"{kind.capitalize()} site")
    return "/".join(kinds) + "?"
