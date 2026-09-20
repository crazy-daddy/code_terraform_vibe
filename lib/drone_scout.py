# Drone role: bio-survey scout. Iterates nocturna.points_of_interest(),
# skips already-scanned/confirmed-empty ones, flies to each remaining
# candidate and bio_scanner.scan()s it. All persistence is the journal's own
# (biomass_coords()/has_scanned()/is_empty()), plus a small local cache
# (drone_claims.py's SCOUTED_EMPTY_POI_KEY) so a restarted scout doesn't
# re-walk the whole map's already-known POIs every cycle. No mission to
# resume beyond that cache -- repeat scans are free (docs/types/biosphere.md:
# "Repeat scans are free").

from tree_console import TreeConsole


class DroneScoutMixin:
    def _scan_candidates(self):
        """
        Every undiscovered POI not already confirmed empty, nearest-first
        from the drone's current position. journal.has_scanned()/is_empty()
        are checked (authoritative, shared across every scout) on top of
        this drone's own empty-POI cache, so a POI another scout already
        resolved is skipped too, not just ones this drone personally
        scanned.
        """
        nocturna = get_component("nocturna")
        journal = get_component("journal")
        if not nocturna or not journal:
            return []

        try:
            pois = nocturna.points_of_interest()
        except Exception:
            pois = []

        pos = self.position()
        candidates = []
        for poi in pois:
            if getattr(poi, "scanned", False):
                continue
            x, y = int(poi.x), int(poi.y)
            if journal.has_scanned(x, y) and journal.is_empty(x, y):
                continue
            if self.is_poi_confirmed_empty(x, y):
                continue
            candidates.append((x, y))

        candidates.sort(key=lambda c: self.distance_between(pos, c))
        return candidates

    def run_scout_loop(self, poll_interval=5.0):
        log = TreeConsole(module="drone_scout")
        log.print(f"Drone Scout Controller ({self.name}) online. Home outpost biome: {self.home_biome or 'unknown'}.")
        while True:
            try:
                if self.is_stranded():
                    log.level("warn").print(f"[{self.name}] {self.status()}; awaiting drone_service rescue.")
                    self.publish_telemetry("STRANDED")
                    sleep(poll_interval)
                    continue

                curr_wh, _, _ = self.get_battery()
                if curr_wh <= self.energy_needed_to_return_comfortably():
                    service_coords, service_info = self.get_nearest_drone_service()
                    if not self.is_at(service_coords, precision=3.0):
                        log.debug(f"[{self.name}] Battery low ({curr_wh:.1f} Wh); returning to drone_service.")
                        self.publish_telemetry("RETURNING_TO_SERVICE")
                        service_id = service_info.get("id")
                        if not (service_id and self.fly_to_station(service_id)):
                            self.fly_to(service_coords[0], service_coords[1], precision=3.0)
                    sleep(poll_interval)
                    continue

                candidates = self._scan_candidates()
                if not candidates:
                    log.debug(f"[{self.name}] No unscanned POI candidates this cycle.")
                    self.publish_telemetry("IDLE_NO_TARGETS")
                    sleep(30.0)
                    continue

                target = None
                for candidate in candidates:
                    budget = self.calculate_trip_energy(candidate)
                    log.debug(f"POI {candidate}: {budget['total_required_wh']:.1f} Wh required, achievable={budget['is_achievable']}.")
                    if budget["is_achievable"]:
                        target = candidate
                        break
                if not target:
                    log.debug(f"[{self.name}] {len(candidates)} candidate(s) found but none reachable on current battery.")
                    self.publish_telemetry("IDLE_OUT_OF_RANGE")
                    sleep(30.0)
                    continue

                log.print(f"[{self.name}] Flying to POI {target} to scan.")
                self.publish_telemetry("OUTBOUND", f"poi_{target[0]}_{target[1]}")
                if not self.fly_to(target[0], target[1], precision=1.0):
                    log.level("warn").print(f"[{self.name}] Could not safely reach POI {target}; will retry.")
                    sleep(poll_interval)
                    continue

                res = self.drone.bio_scanner.scan()
                if res.status == "ok":
                    scan = res.scan
                    if scan is not None and getattr(scan, "is_empty", False):
                        self.mark_poi_empty(target[0], target[1])
                        log.debug(f"[{self.name}] {target} confirmed empty; cached to skip on future cycles.")
                    else:
                        life_forms = getattr(scan, "life_forms", []) if scan else []
                        types_found = ", ".join(sorted(set(getattr(lf, "type", "?") for lf in life_forms))) or "unknown"
                        log.print(f"[{self.name}] Biosite found at {target}: {types_found}.")
                    self.publish_telemetry("SCANNED", f"poi_{target[0]}_{target[1]}")
                else:
                    log.level("warn").print(f"[{self.name}] Scan at {target} notice: {res.status} - {res.message}")

                sleep(poll_interval)
            except Exception as e:
                log.level("error").print(f"[{self.name}] Scout loop exception: {e}")
                sleep(5.0)
