# Drone ability: bio-survey scouting. Candidate POIs from
# nocturna.points_of_interest(), minus already-scanned/confirmed-empty ones,
# and the fly-and-scan of one POI (bio_scanner.scan()). All persistence is
# the journal's own (biomass_coords()/has_scanned()/is_empty()), plus a small
# local cache (drone_claims.py's SCOUTED_EMPTY_POI_KEY) so a restarted scout
# doesn't re-walk the whole map's already-known POIs every cycle. No mission
# to resume beyond that cache -- repeat scans are free (docs/types/biosphere.md:
# "Repeat scans are free"). The role loop is ScoutJob (lib/job_scout.py).

from typing import TYPE_CHECKING

from archive import archive
from contact_inference import SURVEY_RESEARCH, entry_reason, inferred_kind
from survey_requests import read_requests, read_unsupported, request_at, requested_first
from swallow import swallowed
from unsupported_markers import clear_wrong_scanner_marker, resolve_coordinates

if TYPE_CHECKING:
    from drone import DroneController
    from tree_console import TreeConsole


def _exotic_research_done():
    """True once every exotic classification research is unlocked (live research state)."""
    research = get_component("research")
    if not research:
        return False
    try:
        return all(research.is_unlocked(rid) for rid in SURVEY_RESEARCH["exotic"])
    except Exception as error:
        swallowed("drone_scout._exotic_research_done: research.is_unlocked", error)
        return False


def locked_exotic_coords(nocturna):
    """
    Whole-number (x, y) of every survey.unsupported_targets contact that
    contact_inference.inferred_kind() settles as an exotic deposit, while an
    exotic research is still locked. Scouts skip them: before that research
    there is nothing a bio scan there can use, so only bio sites are worth the trip.
    """
    if _exotic_research_done() or not archive or not archive.available:
        return set()
    unsupported = read_unsupported()
    coords_out = set()
    for key, entry in unsupported.items():
        if entry_reason(entry) != "research_required":
            continue
        coords = resolve_coordinates(key, entry)
        if not coords:
            continue
        biome = None
        try:
            biome = nocturna.biome_at(coords[0], coords[1])
        except Exception as error:
            swallowed("drone_scout.locked_exotic_coords: nocturna.biome_at", error)
        if inferred_kind(entry, biome) == "exotic":
            coords_out.add((int(coords[0]), int(coords[1])))
    return coords_out


class DroneScoutMixin:
    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    def scan_candidates(self):
        """
        Every undiscovered POI not already confirmed empty, nearest-first
        from the drone's current position, those inside an
        autoplay.survey_requests area (lib/survey_requests.py) first.
        journal.has_scanned()/is_empty() are checked (authoritative, shared
        across every scout) on top of
        this drone's own empty-POI cache, so a POI another scout already
        resolved is skipped too, not just ones this drone personally
        scanned.
        """
        self._host.log.start(f"[{self._host.name}] scan_candidates()", level="debug")
        self._host.log.trace("scan_candidates() entry.")
        nocturna = get_component("nocturna")
        journal = get_component("journal")
        if not nocturna or not journal:
            self._host.log.debug("missing nocturna or journal component; returning no candidates.")
            self._host.log.end()
            return []

        try:
            pois = nocturna.points_of_interest()
        except Exception as error:
            swallowed("drone_scout.DroneScoutMixin.scan_candidates: nocturna.points_of_interest", error)
            pois = []

        pos = self._host.position()
        cached_empty = self._host.confirmed_empty_pois()
        locked_exotic = locked_exotic_coords(nocturna)
        candidates = []
        skipped_scanned = 0
        skipped_known_empty = 0
        skipped_cached_empty = 0
        skipped_exotic = 0
        for poi in pois:
            if getattr(poi, "scanned", False):
                skipped_scanned += 1
                continue
            x, y = int(poi.x), int(poi.y)
            if journal.has_scanned(x, y) and journal.is_empty(x, y):
                skipped_known_empty += 1
                continue
            if f"{x}_{y}" in cached_empty:
                skipped_cached_empty += 1
                continue
            if (x, y) in locked_exotic:
                skipped_exotic += 1
                continue
            candidates.append((x, y))

        candidates.sort(key=lambda c: self._host.distance_between(pos, c))
        requests = read_requests()
        candidates = requested_first(candidates, lambda c: c, requests)
        requested = len([c for c in candidates if request_at(c[0], c[1], requests) is not None])
        self._host.log.debug(
            f"[{self._host.name}] scan_candidates(): {len(pois)} POI(s) total, {len(candidates)} unscanned candidate(s), {requested} in {len(requests)} survey request area(s) first (skipped {skipped_scanned} already-scanned, {skipped_known_empty} journal-empty, {skipped_cached_empty} cache-empty, {skipped_exotic} exotic before research)."
        )
        self._host.log.trace(f"scan_candidates() exit: {len(candidates)} candidate(s).")
        self._host.log.end()
        return candidates

    def scout_poi(self, log: "TreeConsole", target):
        """Flies to `target` (x, y) and scans it; returns the outcome text for the enclosing log block."""
        log.start(f"[{self._host.name}] scout_poi", level="debug")
        self._host.set_intent(f"scouting poi_{target[0]}_{target[1]}")
        self._host.publish_telemetry("OUTBOUND", f"poi_{target[0]}_{target[1]}")
        log.trace(f"fly_to({target[0]}, {target[1]}, precision=1.0) entry.")
        if not self._host.fly_to(target[0], target[1], precision=1.0):
            log.level("warn").print(f"[{self._host.name}] Could not safely reach POI {target}; will retry.")
            log.end()
            return "unreachable, will retry"
        log.trace(f"fly_to({target[0]}, {target[1]}) exit: reached.")

        log.trace(f"bio_scanner.scan() entry at {target}.")
        res = self._host.drone.bio_scanner.scan()
        log.trace(f"bio_scanner.scan() exit: status={res.status}.")
        if res.status != "ok":
            log.level("warn").print(f"[{self._host.name}] Scan at {target} notice: {res.status} - {res.message}")
            log.end()
            return f"scan {res.status}"
        outcome = "biosite found"
        # A rover/pioneer's sonar may have already flagged this
        # coordinate "wrong_scanner" and planted a "Bio Contact"
        # marker for it -- now that a bio_scanner has actually
        # resolved it, that marker is stale. The blacklist entry
        # itself stays (ground vehicles can never carry a
        # bio_scanner, so it must keep blocking their sonar sweeps
        # from re-attempting this contact); see
        # unsupported_markers.clear_wrong_scanner_marker().
        if clear_wrong_scanner_marker(target[0], target[1]):
            log.debug(f"Cleared stale 'Bio Contact' marker at {target}; bio_scanner resolved it.")
        scan = res.scan
        if scan is not None and getattr(scan, "is_empty", False):
            self._host.mark_poi_empty(target[0], target[1])
            log.debug(f"{target} confirmed empty; cached to skip on future cycles.")
            outcome = "empty"
        else:
            life_forms = getattr(scan, "life_forms", []) if scan else []
            types_found = ", ".join(sorted({getattr(lf, "type", "?") for lf in life_forms})) or "unknown"
            log.print(f"[{self._host.name}] Biosite found at {target}: {types_found}.")
        self._host.publish_telemetry("SCANNED", f"poi_{target[0]}_{target[1]}")
        log.end()
        return outcome
