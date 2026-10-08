# Map Markers from Unsupported Targets
# Reads survey.unsupported_targets from the Data Archive and creates
# colored visual map markers on the Planet Map for all blacklisted contacts.
# Markers need Cartography (140k TP). From then on every new blacklist entry
# places its own marker (place_unsupported_marker()); update_unsupported_markers()
# rebuilds them all: once per control_room_automation.py run (the backfill of
# entries blacklisted before Cartography) and from status_panel.py's
# "Sync Unsupported" button.

from archive import archive
from tree_console import TreeConsole
from components import component
from swallow import swallowed
from contact_inference import describe, inferred_kind, needed_research, possible_kinds
from item_tiers import short_name

log = TreeConsole(module="unsupported_markers")

# Prefix used for all markers created by this module
MARKER_PREFIX = "unsupported."


def resolve_coordinates(key, entry, journal_sites=None):
    """
    Extracts (x, y) coordinates for a target entry from key naming conventions,
    payload fields, or the exploration journal.
    """
    # 1. Payload coords field
    log.start(f"resolve_coordinates('{key}')", level="debug")
    if isinstance(entry, dict) and "coords" in entry:
        c = entry["coords"]
        if isinstance(c, (list, tuple)) and len(c) >= 2:
            try:
                coords = float(c[0]), float(c[1])
                log.debug(f"resolved from payload 'coords' field -> {coords}")
                log.end()
                return coords
            except (ValueError, TypeError):
                log.debug(f"payload 'coords' field present but non-numeric ({c!r})")

    # 2. Key format: poi_X_Y
    if key.startswith("poi_"):
        parts = key.split("_")
        if len(parts) >= 3:
            try:
                coords = float(parts[1]), float(parts[2])
                log.debug(f"resolved from 'poi_X_Y' key format -> {coords}")
                log.end()
                return coords
            except (ValueError, TypeError):
                log.debug(f"'poi_X_Y' key format matched but non-numeric parts {parts!r}")

    # 3. Legacy key format: X:Y
    if ":" in key and not key.startswith("site"):
        parts = key.split(":")
        if len(parts) >= 2:
            try:
                coords = float(parts[0]), float(parts[1])
                log.debug(f"resolved from legacy 'X:Y' key format -> {coords}")
                log.end()
                return coords
            except (ValueError, TypeError):
                log.debug(f"legacy 'X:Y' key format matched but non-numeric parts {parts!r}")

    # 4. Site lookup in Journal
    if journal_sites:
        clean_site_id = key.replace("site_", "")
        for s in journal_sites:
            if str(getattr(s, "id", "")) == clean_site_id:
                if hasattr(s, "x") and hasattr(s, "y"):
                    coords = float(s.x), float(s.y)
                    log.debug(f"resolved via journal site lookup (site_id='{clean_site_id}') -> {coords}")
                    log.end()
                    return coords

    log.end()
    return None


def get_marker_style(reason, entry, biome=None):
    """
    Returns (icon, color, label, note) tailored to the limitation reason.
    `biome` (nocturna.biome_at at the contact) narrows what the contact is.
    Icons: pin, x, check, circle, flag, crosshair, warning, hammer, resource, power, fluid, star
    Colors: neutral, accent, success, warning, error, violet
    """
    scanner_tier = short_name(entry.get("scanner_tier") or "unknown")
    h_limit = entry.get("hardness_limit", 1.0)
    vehicle = entry.get("vehicle", entry.get("rover", "fleet"))
    msg = entry.get("message", "")

    if reason in ["too_hard", "tier_too_low"]:
        icon = "hammer"
        color = "violet"
        label = f"{describe(entry, biome)}: >{scanner_tier} T{h_limit}"[:48]
        note = f"Hardness/Tier limit: Requires > {scanner_tier} (limit {h_limit}). Reported by {vehicle}. {msg}"[:240]

    elif reason == "research_required":
        kind = inferred_kind(entry, biome)
        icon = "power" if kind == "thermal" else "fluid"
        color = "violet"
        research = needed_research(entry, biome)
        needs = " or ".join(research) if research else "survey research"
        label = f"{describe(entry, biome)}: needs {needs}"[:48]
        tap = " Tapping it also needs Thermal Cap (research_thermal_cap)." if kind == "thermal" else ""
        note = f"Locked until {needs}; can be {', '.join(possible_kinds(entry, biome))} (biome {biome or 'unknown'}).{tap} Reported by {vehicle}."[:240]

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


def clear_wrong_scanner_marker(x, y):
    """
    Called by a drone (drone_scout.py) right after a successful bio_scanner
    scan at whole-number (x, y). Removes any "Bio Contact" marker a rover/
    pioneer's sonar previously placed for that coordinate, without touching
    the underlying survey.unsupported_targets entry -- ground vehicles never
    carry a bio_scanner (drone-only module, see docs/database/
    equipment_biosphere.md), so the "wrong_scanner" blacklist entry must stay
    forever to stop their sonar sweeps from re-attempting and re-blacklisting
    the same contact. Only the marker is stale here, not the block itself.
    Safe to call for every scan; it is a no-op when nothing matches.
    """
    markers = component("markers")
    if not markers or not archive or not archive.available:
        return False

    unsupported = archive.get("survey.unsupported_targets", {}) or {}
    if not isinstance(unsupported, dict):
        return False

    target_x, target_y = int(x), int(y)
    cleared = False
    for key, entry in unsupported.items():
        if not isinstance(entry, dict) or entry.get("reason") != "wrong_scanner":
            continue
        coords = resolve_coordinates(key, entry)
        if not coords:
            continue
        if int(coords[0]) == target_x and int(coords[1]) == target_y:
            marker_id = f"{MARKER_PREFIX}{key}"[:64]
            try:
                res = markers.remove(marker_id)
                if getattr(res, "status", "") == "ok":
                    log.debug(f"clear_wrong_scanner_marker({target_x}, {target_y}): removed marker '{marker_id}' for resolved bio contact '{key}'.")
                    cleared = True
            except Exception as error:
                swallowed("unsupported_markers.clear_wrong_scanner_marker: markers.remove", error)
    return cleared


def _biome_at(coords):
    """nocturna.biome_at(x, y), or None when the planet component can't answer."""
    nocturna = component("nocturna")
    if not nocturna:
        return None
    try:
        return nocturna.biome_at(coords[0], coords[1])
    except Exception as error:
        swallowed("unsupported_markers._biome_at: nocturna.biome_at", error)
        return None


def _place(markers, key, entry, coords, reason):
    """Places one target's marker at coords; True when the game accepted it."""
    icon, color, label, note = get_marker_style(reason, entry, _biome_at(coords))
    marker_id = f"{MARKER_PREFIX}{key}"[:64]
    res = markers.place(id=marker_id, x=coords[0], y=coords[1], label=label, icon=icon, color=color, note=note)
    if getattr(res, "status", "") == "ok":
        log.debug(f"  Placed marker '{marker_id}' at ({coords[0]}, {coords[1]}) icon='{icon}' color='{color}' reason='{reason}'")
        return True
    log.level("warn").print(f"  Failed placing marker for '{key}': {getattr(res, 'status', '')} - {getattr(res, 'message', '')}")
    return False


def place_unsupported_marker(key, entry):
    """
    Marker for one freshly blacklisted target (vehicle_claims.blacklist_target()).
    No-op before Cartography (no markers component); update_unsupported_markers()
    backfills the targets blacklisted before then.
    """
    markers = component("markers")
    if not markers or not isinstance(entry, dict):
        return False
    journal_sites = None
    if not key.startswith("poi_"):
        journal = component("journal")
        try:
            journal_sites = journal.discovered_sites("nocturna") if journal else None
        except Exception as error:
            swallowed("unsupported_markers.place_unsupported_marker: journal.discovered_sites", error)
    coords = resolve_coordinates(key, entry, journal_sites)
    if not coords:
        return False
    return _place(markers, key, entry, coords, entry.get("reason", entry.get("status", "unknown")))


def update_unsupported_markers(clear_previous=True):
    """
    Places map markers for all unsupported targets stored in the archive.
    """
    markers = component("markers")
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

    log.start(f"Syncing {len(unsupported)} unsupported target entries to Planet Map markers...")

    # Load journal sites for site coordinate lookups
    journal = component("journal")
    journal_sites = []
    if journal and hasattr(journal, "discovered_sites"):
        try:
            journal_sites = journal.discovered_sites("nocturna") or []
        except Exception as error:
            swallowed("unsupported_markers.update_unsupported_markers: journal.discovered_sites", error)

    # Clear previous markers if requested to stay in sync with archive
    if clear_previous:
        clear_res = markers.clear(MARKER_PREFIX)
        cleared_count = getattr(clear_res, "count", 0)
        if cleared_count > 0:
            log.print(f"Cleared {cleared_count} previous unsupported target markers.")

    placed_count = 0
    skipped_count = 0
    breakdown = {}

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

        # "wrong_scanner" (bio contact) is a permanent hardware mismatch for
        # ground vehicles -- only a drone's bio_scanner can ever resolve it,
        # and that happens outside this blacklist entirely (drone_scout.py's
        # bio_scanner.scan() writes straight to the Journal, see
        # docs/components/journal.md .has_scanned()). Once the Journal shows
        # the coordinate scanned, the site is already handled: keep the
        # archive entry (so a ground vehicle's own sonar sweep never
        # re-attempts it) but stop replanting its "Bio Contact" marker, which
        # drone_scout.py already removes directly on the resolving scan --
        # this is just the sync button's path staying in agreement with that.
        if reason == "wrong_scanner" and journal and hasattr(journal, "has_scanned") and coords:
            try:
                if journal.has_scanned(int(coords[0]), int(coords[1])):
                    log.debug(f"  Skipping '{key}': Journal shows ({coords[0]}, {coords[1]}) already bio-scanned; no marker needed.")
                    skipped_count += 1
                    continue
            except Exception as error:
                swallowed("unsupported_markers.update_unsupported_markers: journal.has_scanned", error)

        if _place(markers, key, entry, coords, reason):
            placed_count += 1
            breakdown[reason] = breakdown.get(reason, 0) + 1

    for r, count in breakdown.items():
        log.print(f"  - {r}: {count} markers")
    log.end(f"Successfully placed {placed_count} map markers ({skipped_count} skipped).")

    return placed_count
