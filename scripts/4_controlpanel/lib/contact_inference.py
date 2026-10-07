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
# possible_kinds() applies these eliminations; kind_weights() adds the soft
# biome prior (BIOME_KIND_PRIOR) for the planner's expected-value scoring.
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

# Soft prior per biome: weight multipliers on a kind that is still possible.
# Owner rule (2026-10-07): a research-locked contact in the geothermal biome
# is most likely a thermal vent.
BIOME_KIND_PRIOR = {
    "geothermal": {"thermal": 4.0},
}


def entry_reason(entry):
    """Blacklist reason of an unsupported-targets entry ("" when unreadable)."""
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("reason", entry.get("status", "")) or "")


def possible_kinds(entry):
    """
    Tuple of site kinds the contact behind `entry` (one survey.unsupported_targets
    value) can still be, from its reason and the scan researches on record.
    () for reasons that say nothing about the kind (depleted, out_of_range, ...).
    """
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


def inferred_kind(entry):
    """The contact's kind when the rules leave exactly one, else None."""
    kinds = possible_kinds(entry)
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
    """
    {kind: probability} over possible_kinds(entry): uniform, times the
    BIOME_KIND_PRIOR factors for `biome`. {} when the reason says nothing.
    """
    kinds = possible_kinds(entry)
    if not kinds:
        return {}
    prior = BIOME_KIND_PRIOR.get(biome or "", {})
    raw = {kind: float(prior.get(kind, 1.0)) for kind in kinds}
    total = sum(raw.values())
    return {kind: weight / total for kind, weight in raw.items()}


def describe(entry):
    """Short label for a map marker: the inferred kind, or the remaining candidates."""
    kinds = possible_kinds(entry)
    if not kinds:
        return ""
    if len(kinds) == 1:
        kind = kinds[0]
        if kind == "mineral":
            return f"Mineral, hardness {min_hardness(entry)}+"
        return f"{kind.capitalize()} site"
    return "/".join(kinds) + "?"
