# Deep oil under inert formations (Seismic Sonar, Advanced Oil Extraction).
#
# World generation hides exactly RESERVOIRS_PER_MAP reservoirs under the
# inert formations (GeologicalAnomaly, kind "inert"). Only a Seismic Sonar
# scan, with Petroleum Survey and Advanced Oil Extraction both unlocked,
# sets a formation's seismic_status; every other sonar leaves "unscanned".
# The scan marks each formation in range "potential" (a reservoir, certain)
# or "dry" (none). A Seismic survey of a non-dry formation (0.5 h, 3 Wh)
# turns a reservoir into a rich Oil Well with the same site id; surveying a
# known dry formation is free and instant. So a confirmed reservoir shows up
# as an "oil" site whose id keeps the formation prefix.
# Source: decompiled simworker (seismic scan gate, deep-oil survey).
#
# prospect() reads the state from journal sites; pure, no game calls.

RESERVOIRS_PER_MAP = 3
FORMATION_ID_PREFIX = "geological_anomaly_"
SEISMIC_RESEARCH_IDS = ("research_petroleum_survey", "research_advanced_oil_extraction")


def _kind(site):
    kind = getattr(site, "kind", None)
    return kind() if callable(kind) else kind


def prospect(sites):
    """
    Deep-oil state from journal sites (discovered_sites()):
    {"unscanned": [site], "potential": [site], "dry": int, "found": int,
     "remaining": int, "odds": float}. "found" counts confirmed reservoirs
    (oil sites with a formation id), "remaining" the reservoirs not yet
    seen as potential or found, "odds" the chance each unscanned formation
    holds one of them (0.0 when none is unscanned).
    """
    unscanned = []
    potential = []
    dry = 0
    found = 0
    for site in sites or ():
        kind = _kind(site)
        if kind == "oil" and str(getattr(site, "id", "")).startswith(FORMATION_ID_PREFIX):
            found += 1
            continue
        if kind != "inert":
            continue
        status = getattr(site, "seismic_status", "unscanned")
        if status == "potential":
            potential.append(site)
        elif status == "dry":
            dry += 1
        else:
            unscanned.append(site)
    remaining = max(0, RESERVOIRS_PER_MAP - found - len(potential))
    odds = min(1.0, remaining / len(unscanned)) if unscanned else 0.0
    return {"unscanned": unscanned, "potential": potential, "dry": dry, "found": found,
            "remaining": remaining, "odds": odds}


def targets(state):
    """Formations worth a Seismic visit: every potential one, plus the unscanned ones while a reservoir is still unaccounted for."""
    return state["potential"] + (state["unscanned"] if state["remaining"] > 0 else [])


def open_work(state):
    """True while a Seismic scout has something left to scan or survey."""
    return len(targets(state)) > 0
