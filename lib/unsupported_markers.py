# Map Markers from Unsupported Targets
# Reads survey.unsupported_targets from the Data Archive and creates
# colored visual map markers on the Planet Map for all blacklisted contacts.
# Promoted out of playground/mark_unsupported_targets.py (playground/ isn't
# synced into the live game, so this never actually ran there) -- now callable
# from the root mark_unsupported_targets.py entrypoint and from panel_1.py's
# AUTOMATION section "Sync Unsupported" button.

from archive import archive
from tree_console import TreeConsole

log = TreeConsole(module="unsupported_markers")

# Prefix used for all markers created by this module
MARKER_PREFIX = "unsupported."


def _component(component_id):
    try:
        return get_component(component_id)
    except Exception:
        return None


def resolve_coordinates(key, entry, journal_sites=None):
    """
    Extracts (x, y) coordinates for a target entry from key naming conventions,
    payload fields, or the exploration journal.
    """
    # 1. Payload coords field
    if isinstance(entry, dict) and "coords" in entry:
        c = entry["coords"]
        if isinstance(c, (list, tuple)) and len(c) >= 2:
            try:
                coords = float(c[0]), float(c[1])
                log.debug(f"resolve_coordinates('{key}'): resolved from payload 'coords' field -> {coords}")
                return coords
            except (ValueError, TypeError):
                log.debug(f"resolve_coordinates('{key}'): payload 'coords' field present but non-numeric ({c!r})")

    # 2. Key format: poi_X_Y
    if key.startswith("poi_"):
        parts = key.split("_")
        if len(parts) >= 3:
            try:
                coords = float(parts[1]), float(parts[2])
                log.debug(f"resolve_coordinates('{key}'): resolved from 'poi_X_Y' key format -> {coords}")
                return coords
            except (ValueError, TypeError):
                log.debug(f"resolve_coordinates('{key}'): 'poi_X_Y' key format matched but non-numeric parts {parts!r}")

    # 3. Legacy key format: X:Y
    if ":" in key and not key.startswith("site"):
        parts = key.split(":")
        if len(parts) >= 2:
            try:
                coords = float(parts[0]), float(parts[1])
                log.debug(f"resolve_coordinates('{key}'): resolved from legacy 'X:Y' key format -> {coords}")
                return coords
            except (ValueError, TypeError):
                log.debug(f"resolve_coordinates('{key}'): legacy 'X:Y' key format matched but non-numeric parts {parts!r}")

    # 4. Site lookup in Journal
    if journal_sites:
        clean_site_id = key.replace("site_", "")
        for s in journal_sites:
            if str(getattr(s, "id", "")) == clean_site_id:
                if hasattr(s, "x") and hasattr(s, "y"):
                    coords = float(s.x), float(s.y)
                    log.debug(f"resolve_coordinates('{key}'): resolved via journal site lookup (site_id='{clean_site_id}') -> {coords}")
                    return coords

    return None


def get_marker_style(reason, entry):
    """
    Returns (icon, color, label, note) tailored to the limitation reason.
    Icons: pin, x, check, circle, flag, crosshair, warning, hammer, resource, power, fluid, star
    Colors: neutral, accent, success, warning, error, violet
    """
    scanner_tier = entry.get("scanner_tier", "basic")
    h_limit = entry.get("hardness_limit", 1.0)
    vehicle = entry.get("vehicle", entry.get("rover", "fleet"))
    msg = entry.get("message", "")

    if reason in ["too_hard", "tier_too_low"]:
        icon = "hammer"
        color = "violet"
        label = f"Limit: >{scanner_tier} T{h_limit}"[:48]
        note = f"Hardness/Tier limit: Requires > {scanner_tier} (limit {h_limit}). Reported by {vehicle}. {msg}"[:240]

    elif reason == "research_required":
        icon = "fluid"
        color = "violet"
        label = "Tech Locked Contact"[:48]
        note = f"Survey research required to resolve this contact. Reported by {vehicle}."[:240]

    elif reason == "wrong_scanner":
        icon = "star"
        color = "accent"
        label = "Bio Contact (Bio Scanner)"[:48]
        note = f"Biological signature detected. Requires a Bio Scanner. Reported by {vehicle}."[:240]

    elif reason in ["depleted", "empty"]:
        icon = "x"
        color = "neutral"
        label = "Depleted Site"[:48]
        note = f"Resource site is empty or depleted. Reported by {vehicle}."[:240]

    else:
        icon = "warning"
        color = "warning"
        label = f"Unsupported: {reason}"[:48]
        note = f"{reason}: {msg} (reported by {vehicle})"[:240]

    log.debug(f"get_marker_style(reason='{reason}'): categorized as icon='{icon}' color='{color}' label='{label}'")
    return icon, color, label, note


def update_unsupported_markers(clear_previous=True):
    """
    Places map markers for all unsupported targets stored in the archive.
    """
    markers = _component("markers")
    if not markers:
        log.level("error").print("Map Markers component ('markers') is unavailable. Unlocked by Cartography research.")
        return 0

    if not archive or not archive.available:
        log.level("error").print("Data Archive ('notebook') is unavailable or locked.")
        return 0

    # Read unsupported targets
    unsupported = archive.get("survey.unsupported_targets", {}) or {}

    if not isinstance(unsupported, dict) or not unsupported:
        log.print("No unsupported targets found in archive.")
        if clear_previous:
            markers.clear(MARKER_PREFIX)
            log.print(f"Cleared existing '{MARKER_PREFIX}' markers.")
        return 0

    # Load journal sites for site coordinate lookups
    journal = _component("journal")
    journal_sites = []
    if journal and hasattr(journal, "discovered_sites"):
        try:
            journal_sites = journal.discovered_sites("nocturna") or []
        except Exception:
            pass

    # Clear previous markers if requested to stay in sync with archive
    if clear_previous:
        clear_res = markers.clear(MARKER_PREFIX)
        cleared_count = getattr(clear_res, "count", 0)
        if cleared_count > 0:
            log.print(f"Cleared {cleared_count} previous unsupported target markers.")

    placed_count = 0
    skipped_count = 0
    breakdown = {}

    log.print(f"Syncing {len(unsupported)} unsupported target entries to Planet Map markers...")

    for key, entry in unsupported.items():
        if not isinstance(entry, dict):
            log.debug(f"  Skipping '{key}': entry payload is not a dict ({entry!r})")
            skipped_count += 1
            continue

        coords = resolve_coordinates(key, entry, journal_sites)
        if not coords:
            log.level("warn").print(f"  Could not resolve coordinates for '{key}'")
            skipped_count += 1
            continue

        reason = entry.get("reason", entry.get("status", "unknown"))
        icon, color, label, note = get_marker_style(reason, entry)

        marker_id = f"{MARKER_PREFIX}{key}"[:64]
        res = markers.place(
            id=marker_id,
            x=coords[0],
            y=coords[1],
            label=label,
            icon=icon,
            color=color,
            note=note
        )

        if getattr(res, "status", "") == "ok":
            placed_count += 1
            breakdown[reason] = breakdown.get(reason, 0) + 1
            log.debug(f"  Placed marker '{marker_id}' at ({coords[0]}, {coords[1]}) icon='{icon}' color='{color}' reason='{reason}'")
        else:
            log.level("warn").print(f"  Failed placing marker for '{key}': {res.status} - {getattr(res, 'message', '')}")

    log.print(f"Successfully placed {placed_count} map markers ({skipped_count} skipped).")
    for r, count in breakdown.items():
        log.print(f"  - {r}: {count} markers")

    return placed_count
