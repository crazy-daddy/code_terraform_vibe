# Drone role: bio-survey scout. Iterates nocturna.points_of_interest(),
# skips already-scanned/confirmed-empty ones, flies to each remaining
# candidate and bio_scanner.scan()s it. All persistence is the journal's own
# (biomass_coords()/has_scanned()/is_empty()), plus a small local cache
# (drone_claims.py's SCOUTED_EMPTY_POI_KEY) so a restarted scout doesn't
# re-walk the whole map's already-known POIs every cycle. No mission to
# resume beyond that cache -- repeat scans are free (docs/types/biosphere.md:
# "Repeat scans are free").

from tree_console import TreeConsole
from typing import TYPE_CHECKING
from unsupported_markers import clear_wrong_scanner_marker

if TYPE_CHECKING:
    from drone import DroneController


class DroneScoutMixin:

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    def _scan_candidates(self):
        """
        Every undiscovered POI not already confirmed empty, nearest-first
        from the drone's current position. journal.has_scanned()/is_empty()
        are checked (authoritative, shared across every scout) on top of
        this drone's own empty-POI cache, so a POI another scout already
        resolved is skipped too, not just ones this drone personally
        scanned.
        """
        self._host.log.trace(f"[{self._host.name}] _scan_candidates() entry.")
        nocturna = get_component("nocturna")
        journal = get_component("journal")
        if not nocturna or not journal:
            self._host.log.debug(f"[{self._host.name}] _scan_candidates(): missing nocturna or journal component; returning no candidates.")
            return []

        try:
            pois = nocturna.points_of_interest()
        except Exception:
            pois = []

        pos = self._host.position()
        candidates = []
        skipped_scanned = 0
        skipped_known_empty = 0
        skipped_cached_empty = 0
        for poi in pois:
            if getattr(poi, "scanned", False):
                skipped_scanned += 1
                continue
            x, y = int(poi.x), int(poi.y)
            if journal.has_scanned(x, y) and journal.is_empty(x, y):
                skipped_known_empty += 1
                continue
            if self._host.is_poi_confirmed_empty(x, y):
                skipped_cached_empty += 1
                continue
            candidates.append((x, y))

        candidates.sort(key=lambda c: self._host.distance_between(pos, c))
        self._host.log.debug(
            f"[{self._host.name}] _scan_candidates(): {len(pois)} POI(s) total, {len(candidates)} unscanned candidate(s) "
            f"(skipped {skipped_scanned} already-scanned, {skipped_known_empty} journal-empty, {skipped_cached_empty} cache-empty)."
        )
        self._host.log.trace(f"[{self._host.name}] _scan_candidates() exit: {len(candidates)} candidate(s).")
        return candidates

    def run_scout_loop(self, poll_interval=5.0):
        log = TreeConsole(module="drone_scout")
        log.print(f"Drone Scout Controller ({self._host.name}) online. Home outpost biome: {self._host.home_biome or 'unknown'}.")
        while True:
            try:
                if self._host.is_stranded():
                    log.level("warn").print(f"[{self._host.name}] {self._host.status()}; awaiting drone_service rescue.")
                    self._host.publish_telemetry("STRANDED")
                    sleep(poll_interval)
                    continue

                if self._host.handle_recall_if_active():
                    sleep(poll_interval)
                    continue

                curr_wh, _, _ = self._host.get_battery()
                if curr_wh <= self._host.energy_needed_to_return_comfortably():
                    self._host.return_to_service_for_charge(log, f"Battery low ({curr_wh:.1f} Wh)")
                    sleep(poll_interval)
                    continue

                candidates = self._scan_candidates()
                if not candidates:
                    log.debug(f"[{self._host.name}] No unscanned POI candidates this cycle.")
                    self._host.publish_telemetry("IDLE_NO_TARGETS")
                    # Every known POI is resolved (scanned or cache/journal-
                    # confirmed empty) -- nothing will ever change that
                    # without a fresh POI appearing, so nothing else in this
                    # loop will ever send the drone anywhere again. Without
                    # this, a scout that finishes its survey mid-field just
                    # idles wherever its last scan left it, forever.
                    if self._host.return_to_service_for_charge(log, "No scan targets remain"):
                        log.print(f"[{self._host.name}] Survey complete; standing by at drone_service.")
                    sleep(30.0)
                    continue

                target = None
                for candidate in candidates:
                    budget = self._host.calculate_trip_energy(candidate)
                    log.trace(f"POI {candidate}: {budget['total_required_wh']:.1f} Wh required, achievable={budget['is_achievable']}.")
                    if budget["is_achievable"]:
                        target = candidate
                        break
                if not target:
                    log.debug(f"[{self._host.name}] {len(candidates)} candidate(s) found but none reachable on current battery.")
                    self._host.publish_telemetry("IDLE_OUT_OF_RANGE")
                    _, _, lvl = self._host.get_battery()
                    if lvl < 0.98:
                        # Not low enough to trip the proactive-return check above
                        # (not in danger where it's parked), but too low for any
                        # scout trip -- top up now instead of idling here forever,
                        # since nothing else in this loop will ever send it home.
                        self._host.return_to_service_for_charge(log, f"No candidate reachable at {lvl*100:.0f}% charge")
                    sleep(30.0)
                    continue

                log.print(f"[{self._host.name}] Flying to POI {target} to scan.")
                self._host.publish_telemetry("OUTBOUND", f"poi_{target[0]}_{target[1]}")
                log.trace(f"[{self._host.name}] fly_to({target[0]}, {target[1]}, precision=1.0) entry.")
                if not self._host.fly_to(target[0], target[1], precision=1.0):
                    log.level("warn").print(f"[{self._host.name}] Could not safely reach POI {target}; will retry.")
                    sleep(poll_interval)
                    continue
                log.trace(f"[{self._host.name}] fly_to({target[0]}, {target[1]}) exit: reached.")

                log.trace(f"[{self._host.name}] bio_scanner.scan() entry at {target}.")
                res = self._host.drone.bio_scanner.scan()
                log.trace(f"[{self._host.name}] bio_scanner.scan() exit: status={res.status}.")
                if res.status == "ok":
                    # A rover/pioneer's sonar may have already flagged this
                    # coordinate "wrong_scanner" and planted a "Bio Contact"
                    # marker for it -- now that a bio_scanner has actually
                    # resolved it, that marker is stale. The blacklist entry
                    # itself stays (ground vehicles can never carry a
                    # bio_scanner, so it must keep blocking their sonar sweeps
                    # from re-attempting this contact); see
                    # unsupported_markers.clear_wrong_scanner_marker().
                    if clear_wrong_scanner_marker(target[0], target[1]):
                        log.debug(f"[{self._host.name}] Cleared stale 'Bio Contact' marker at {target}; bio_scanner resolved it.")
                    scan = res.scan
                    if scan is not None and getattr(scan, "is_empty", False):
                        self._host.mark_poi_empty(target[0], target[1])
                        log.debug(f"[{self._host.name}] {target} confirmed empty; cached to skip on future cycles.")
                    else:
                        life_forms = getattr(scan, "life_forms", []) if scan else []
                        types_found = ", ".join(sorted(set(getattr(lf, "type", "?") for lf in life_forms))) or "unknown"
                        log.print(f"[{self._host.name}] Biosite found at {target}: {types_found}.")
                    self._host.publish_telemetry("SCANNED", f"poi_{target[0]}_{target[1]}")
                else:
                    log.level("warn").print(f"[{self._host.name}] Scan at {target} notice: {res.status} - {res.message}")

                sleep(poll_interval)
            except Exception as e:
                log.level("error").print(f"[{self._host.name}] Scout loop exception: {e}")
                sleep(5.0)
