# Survey requests: map areas a planner wants scouted first, and the contacts
# vehicle sonar already showed to be biomass.
#
# Archive autoplay.survey_requests {request_id: {"x", "y", "radius", "why"}}:
# written whole by the outpost founding planner (autoplay/lib/outpost_plan.py,
# one per open found proposal whose site still wants a survey), read by the
# ground scout (vehicle_survey.survey_known_pois()) and the drone scout
# (drone_scout.scan_candidates()). Contacts inside a request area go first,
# in the order the scout already gives them; the rest follow in that order.
# A request with no scannable contact left in its area changes nothing.
#
# known_biomass(): positions of survey.unsupported_targets entries with reason
# "wrong_scanner". Vehicle sonar cannot classify a biomass contact, so such a
# contact is biomass without a bio-scan. The entries stay in the blacklist for
# good (vehicle_claims.blacklist_target(), docs/cheatsheet/archive_ipc.md).
#
# blocked_targets(): the other blacklist entries, contacts no scout can resolve
# with what is unlocked now. The founding planner counts them as surveyed as
# far as it goes, so an area holding only those stops asking for a survey. A
# "research_required" entry turns stale once a scan research it did not have
# is unlocked (the scouts retry it then, vehicle_claims.can_attempt_target()),
# and the area asks again. A "too_hard"/"tier_too_low" entry stays blocked
# until a scout with a better sonar retries it and clears or rewrites it.

from archive import archive
from swallow import swallowed
from unsupported_markers import SURVEY_UNSUPPORTED_KEY
from vehicle_claims import SCAN_RESEARCH_IDS

REQUESTS_KEY = "autoplay.survey_requests"


def clean_requests(raw):
    """{request_id: {"x", "y", "radius", "why"}} of the well-formed entries of `raw`."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for rid, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            out[str(rid)] = {"x": float(entry["x"]), "y": float(entry["y"]), "radius": float(entry["radius"]), "why": str(entry.get("why", ""))}
        except (KeyError, TypeError, ValueError):
            continue
    return out


def read_requests():
    """autoplay.survey_requests, well-formed entries only ({} when missing)."""
    if not archive or not archive.available:
        return {}
    return clean_requests(archive.get(REQUESTS_KEY, {}))


def write_requests(requests):
    """Replaces autoplay.survey_requests with `requests`; returns True when it changed."""
    if clean_requests(archive.get(REQUESTS_KEY, {})) == requests:
        return False

    def updater(_old):
        return requests

    archive.transaction(REQUESTS_KEY, {}, updater)
    return True


def request_at(x, y, requests):
    """Id of the first request (sorted ids) whose area holds (x, y); None outside every area."""
    for rid in sorted(requests):
        entry = requests[rid]
        if (x - entry["x"]) ** 2 + (y - entry["y"]) ** 2 <= entry["radius"] ** 2:
            return rid
    return None


def requested_first(items, coords, requests):
    """`items` with those whose coords(item) lie in a request area first; order kept within both parts."""
    if not requests:
        return list(items)
    inside = []
    rest = []
    for item in items:
        x, y = coords(item)
        if request_at(x, y, requests) is None:
            rest.append(item)
        else:
            inside.append(item)
    return inside + rest


def target_coords(key):
    """(x, y) of a "poi_X_Y" target key; None for other keys."""
    parts = str(key).split("_")
    if len(parts) != 3 or parts[0] != "poi":
        return None
    try:
        return float(parts[1]), float(parts[2])
    except ValueError:
        return None


def known_biomass(targets):
    """[(x, y)] of the "wrong_scanner" entries of an unsupported-targets dict."""
    out = []
    if not isinstance(targets, dict):
        return out
    for key, entry in targets.items():
        if isinstance(entry, dict) and entry.get("reason") == "wrong_scanner":
            coords = target_coords(key)
            if coords is not None:
                out.append(coords)
    return out


def target_site_id(key):
    """Site id of a "site_<id>" target key; None for other keys."""
    key = str(key)
    return key[5:] if key.startswith("site_") and len(key) > 5 else None


def blocked_targets(targets, scan_research):
    """
    ({(x, y) whole meters}, {site id}) of the blacklist entries that still
    block: every reason but "wrong_scanner"; a "research_required" entry only
    while every unlocked scan research in `scan_research` was on record.
    """
    pois = set()
    site_ids = set()
    if not isinstance(targets, dict):
        return pois, site_ids
    unlocked = set(scan_research)
    for key, entry in targets.items():
        if not isinstance(entry, dict):
            continue
        reason = entry.get("reason", entry.get("status"))
        if reason == "wrong_scanner":
            continue
        if reason == "research_required" and not unlocked.issubset(set(entry.get("unlocked_scan_researches") or [])):
            continue
        coords = target_coords(key)
        if coords is not None:
            pois.add((int(round(coords[0])), int(round(coords[1]))))
        site_id = target_site_id(key)
        if site_id is not None:
            site_ids.add(site_id)
    return pois, site_ids


def unlocked_scan_research():
    """SCAN_RESEARCH_IDS unlocked now ([] when research is unreadable)."""
    research = get_component("research")
    out = []
    if research is None:
        return out
    for rid in SCAN_RESEARCH_IDS:
        try:
            if research.is_unlocked(rid):
                out.append(rid)
        except Exception as error:
            swallowed("survey_requests.unlocked_scan_research: research.is_unlocked", error)
    return out


def read_blocked():
    """blocked_targets() of survey.unsupported_targets (empty sets when unreadable)."""
    if not archive or not archive.available:
        return set(), set()
    return blocked_targets(archive.get(SURVEY_UNSUPPORTED_KEY, {}), unlocked_scan_research())


def read_unsupported():
    """survey.unsupported_targets as a dict ({} when unreadable)."""
    return archive.get_dict(SURVEY_UNSUPPORTED_KEY)


def read_known_biomass():
    """known_biomass() of survey.unsupported_targets ([] when unreadable)."""
    if not archive or not archive.available:
        return []
    return known_biomass(archive.get(SURVEY_UNSUPPORTED_KEY, {}))


def scout_work(points, sites, targets, scan_research):
    """
    Host-free count of known scout work, for the role demand
    (lib/role_demand.py): (unscanned POIs, unsurveyed known sites, scannable
    POIs). The third counts every unscanned POI but known biomass, blocked
    ones too: the scout keep floor holds until they are all scanned. `points`
    are planet points_of_interest(), `sites` journal discovered_sites();
    `targets` is survey.unsupported_targets. A contact still blocked
    (blocked_targets()) or known biomass (no vehicle sonar classifies it)
    counts as no work. Claims are ignored: a claimed target is work, just
    taken. Deep-oil formations are left out: only a Seismic Sonar works them,
    and a refit stops at the Deep tier (pioneer_commission.PART_TIERS).
    """
    blocked_pois, blocked_sites = blocked_targets(targets, scan_research)
    biomass = {(int(round(x)), int(round(y))) for x, y in known_biomass(targets)}
    skip = blocked_pois | biomass
    pois = scannable = 0
    for point in points or []:
        if getattr(point, "scanned", False):
            continue
        try:
            at = (int(round(float(point.x))), int(round(float(point.y))))
        except (AttributeError, TypeError, ValueError):
            continue
        if at not in skip:
            pois += 1
        if at not in biomass:
            scannable += 1
    unsurveyed = 0
    for site in sites or []:
        if getattr(site, "surveyed", False):
            continue
        if str(getattr(site, "id", "")) not in blocked_sites:
            unsurveyed += 1
    return pois, unsurveyed, scannable


def read_scout_work():
    """scout_work() of the live planet and journal ((0, 0, 0) when unreadable)."""
    planet = get_component("nocturna")
    journal = get_component("journal")
    try:
        points = list(planet.points_of_interest()) if planet and hasattr(planet, "points_of_interest") else []
        sites = list(journal.discovered_sites("nocturna")) if journal and hasattr(journal, "discovered_sites") else []
    except Exception as error:
        swallowed("survey_requests.read_scout_work: points_of_interest/discovered_sites", error)
        return 0, 0, 0
    return scout_work(points, sites, read_unsupported(), unlocked_scan_research())
