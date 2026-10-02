# Survey requests: map areas a planner wants scouted first, and the contacts
# vehicle sonar already showed to be biomass.
#
# Archive autoplay.survey_requests {request_id: {"x", "y", "radius", "why"}}:
# written whole by the outpost founding planner (autoplay/lib/outpost_plan.py,
# one per open found proposal whose site still wants a survey), read by the
# ground scout (vehicle_survey.survey_known_pois()) and the drone scout
# (drone_scout._scan_candidates()). Contacts inside a request area go first,
# in the order the scout already gives them; the rest follow in that order.
# A request with no scannable contact left in its area changes nothing.
#
# known_biomass(): positions of survey.unsupported_targets entries with reason
# "wrong_scanner". Vehicle sonar cannot classify a biomass contact, so such a
# contact is biomass without a bio-scan. The entries stay in the blacklist for
# good (vehicle_claims.blacklist_target(), docs/cheatsheet/archive_ipc.md).

from archive import archive

REQUESTS_KEY = "autoplay.survey_requests"
UNSUPPORTED_KEY = "survey.unsupported_targets"


def clean_requests(raw):
    """{request_id: {"x", "y", "radius", "why"}} of the well-formed entries of `raw`."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for rid, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            out[str(rid)] = {"x": float(entry["x"]), "y": float(entry["y"]),
                             "radius": float(entry["radius"]), "why": str(entry.get("why", ""))}
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


def read_known_biomass():
    """known_biomass() of survey.unsupported_targets ([] when unreadable)."""
    if not archive or not archive.available:
        return []
    return known_biomass(archive.get(UNSUPPORTED_KEY, {}))
