# Vehicle mixin: sonar scanning/surveying, POI discovery, and the autonomous
# survey loop (known POIs first, optional outward spiral fallback). Shared by
# Rover and Pioneer via VehicleController (lib/vehicle.py). Drilling lives in
# lib/vehicle_mining.py's VehicleMiningMixin.

from archive import archive
from version_guard import validate_game_version
import outpost_mining
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vehicle import VehicleController

SURVEY_SPIRAL_KEY = "survey.spiral"
LEGACY_PIONEER_SPIRAL_KEY = "pioneer.survey_spiral"


class VehicleSurveyMixin:
    """
    Sonar field operations and the autonomous survey loop, mixed into
    VehicleController. Depends on VehicleClaimsMixin for target reservation
    and VehicleEnergyMixin/VehicleNavigationMixin for trip budgeting & driving.
    """

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    def scan_and_survey(self):
        """Scans the local area and surveys discovered sites."""
        log = self._host.log
        log.trace(f"[{self._host.name}] scan_and_survey() enter")
        self.last_scan_status = "unavailable"
        if not hasattr(self._host.vehicle, "sonar"):
            log.level("error").print(f"[{self._host.name}] Error: No SonarModule mounted!")
            return []

        log.print(f"[{self._host.name}] Activating Sonar sweep...")
        log.debug(f"[{self._host.name}] scan_and_survey(): current_target_key={self.current_target_key!r}")
        self._host.publish_telemetry("SCANNING")
        res = self._host.vehicle.sonar.scan()
        self.last_scan_status = res.status
        blocked = getattr(res, "blocked", [])
        log.debug(
            f"[{self._host.name}] sonar.scan() -> status={res.status!r}, message={getattr(res, 'message', '')!r}, "
            f"sites={[getattr(s, 'id', s) for s in getattr(res, 'sites', [])]}, "
            f"blocked={[(c.x, c.y, c.reason) for c in blocked]}"
        )
        if res.status not in ["ok", "too_hard", "tier_too_low", "research_required", "wrong_scanner"]:
            log.level("warn").print(f"[{self._host.name}] Sonar scan status: {res.status} - {res.message}")
            return []

        # A wide/deep sonar's range routinely covers several "?" contacts at
        # once (see the "range-aware scanning" TODO), each possibly blocked
        # for a DIFFERENT reason -- so this can't collapse onto a single
        # self.current_target_key the way scan()'s own top-level .status
        # does (that's one verdict for the whole sweep: "ok" as soon as ANY
        # contact in range resolves, even if the vehicle's own target stayed
        # unclassified). SonarScanResult.blocked gives the real per-contact
        # x/y/reason/message instead (see docs/types/fleet_and_vehicles.md
        # BlockedContact), so blacklist each one by its own coordinates.
        for contact in blocked:
            key = f"poi_{contact.x}_{contact.y}"
            log.level("warn").print(f"[{self._host.name}] Blocked contact at ({contact.x}, {contact.y}): {contact.reason} - {contact.message}")
            log.debug(f"[{self._host.name}] Blacklisting {key} (reason={contact.reason!r}).")
            self._host.blacklist_target(key, contact.reason, contact.message, scanner_type="sonar")

        sites = getattr(res, "sites", [])
        if res.status == "ok" and self.current_target_key:
            still_blocked = any(f"poi_{c.x}_{c.y}" == self.current_target_key for c in blocked)
            if not still_blocked:
                log.debug(f"[{self._host.name}] Scan resolved cleanly; clearing any prior unsupported entry for {self.current_target_key!r}.")
                self._host.clear_unsupported_target(self.current_target_key)

        surveyed_sites = []
        for s in sites:
            if not getattr(s, "surveyed", False):
                log.print(f"[{self._host.name}] Surveying site {s.id} ({s.kind()})...")
                s_res = self._host.vehicle.sonar.survey(s.id)
                log.debug(f"[{self._host.name}] sonar.survey({s.id!r}) -> status={s_res.status!r}")
                if s_res.status == "ok":
                    self._host.clear_unsupported_target(f"site_{s.id}")
                    surveyed_sites.append(s_res.site)
                    # New minable resource: drop/refresh its "resource."
                    # marker and, if unassigned, hand it to the closest
                    # outpost within range (see lib/outpost_mining.py).
                    if getattr(s_res.site, "kind", lambda: None)() == "mineral":
                        try:
                            outpost_mining.auto_assign_new_site(s_res.site)
                        except Exception:
                            pass
                elif s_res.status in ["too_hard", "tier_too_low", "research_required", "wrong_scanner"]:
                    log.level("warn").print(f"[{self._host.name}] Site {s.id} survey limitation: {s_res.status} - {s_res.message}")
                    self._host.blacklist_target(f"site_{s.id}", s_res.status, s_res.message, scanner_type="sonar")
                    surveyed_sites.append(s)
                else:
                    surveyed_sites.append(s)
            else:
                surveyed_sites.append(s)
            sleep(0.5)

        log.trace(f"[{self._host.name}] scan_and_survey() exit: {len(sites)} candidate site(s) in range, {len(surveyed_sites)} returned.")
        return surveyed_sites

    def sonar_signature(self):
        """Returns the mounted sonar capability used for retry decisions."""
        sonar = getattr(self._host.vehicle, "sonar", None)
        if not sonar:
            return "none"
        try:
            return f"{sonar.tier()}:{sonar.range()}:{sonar.hardness_limit()}"
        except Exception:
            return "unknown"

    def remember_sonar_retry(self, coords):
        """Remember a limited contact until sonar capability changes."""
        target_key = f"poi_{int(round(coords[0]))}_{int(round(coords[1]))}"
        status = getattr(self, "last_scan_status", "unknown")
        self._host.blacklist_target(target_key, status, f"Scan limited: {status}", scanner_type="sonar")

    def unscanned_pois(self):
        """Returns known map contacts that still need a vehicle sonar scan."""
        log = self._host.log
        log.trace(f"[{self._host.name}] unscanned_pois() enter")
        planet = get_component("nocturna")
        if not planet or not hasattr(planet, "points_of_interest"):
            log.trace(f"[{self._host.name}] unscanned_pois() exit: no 'nocturna' points_of_interest available.")
            return []
        try:
            unsupported_targets = self._host.get_unsupported_targets()
            existing_claims = self._host.get_claims()
            curr_tick = self._host.get_current_tick()
            points = []
            for point in planet.points_of_interest():
                if getattr(point, "scanned", False):
                    continue
                key = f"poi_{point.x}_{point.y}"
                legacy_key = f"{point.x}:{point.y}"

                # Check unsupported / blacklisted targets across fleet
                target_entry = unsupported_targets.get(key) or unsupported_targets.get(legacy_key)
                if target_entry:
                    can_attempt, attempt_reason = self._host.can_attempt_target(key, target_entry)
                    log.debug(f"[{self._host.name}] {key}: unsupported entry found (reason={target_entry.get('reason', target_entry.get('status'))!r}) -> can_attempt={can_attempt} ({attempt_reason})")
                    if not can_attempt:
                        continue
                else:
                    log.debug(f"[{self._host.name}] {key}: no unsupported entry on record.")

                # Check if claimed by another active vehicle (Rover, Pioneer, or peer)
                claim = existing_claims.get(key)
                if claim and (claim.get("vehicle") != self._host.name and claim.get("rover") != self._host.name):
                    claim_age = curr_tick - claim.get("tick", 0)
                    if curr_tick == 0 or claim_age < self._host.CLAIM_STALE_TICKS:
                        log.debug(f"[{self._host.name}] {key}: skipped, actively claimed by {claim.get('vehicle', claim.get('rover'))} ({claim_age} ticks ago).")
                        continue

                points.append(point)
            home = self._host.assigned_slot_coords
            points.sort(key=lambda p: self._host.distance_between(home, (p.x, p.y)))
            log.trace(f"[{self._host.name}] unscanned_pois() exit: {len(points)} candidate(s), nearest-first from {home}.")
            return points
        except Exception:
            return []

    def unsurveyed_known_sites(self):
        """
        Known Sites already classified by sonar (kind revealed) but never fully
        surveyed -- typically because a previous sonar.survey() call failed with
        too_hard/tier_too_low. These sites are invisible to unscanned_pois()
        because PointOfInterest.scanned flips True the moment scan() classifies
        the contact, independent of whether survey() itself ever succeeds --
        without this, a capability-blocked site would never be revisited again,
        even after a sonar upgrade or a new scan research unlock. Only returns
        sites can_attempt_target() says are actually worth another try (compares
        the mounted sonar's current tier/hardness/range and unlocked scan
        researches against what was recorded at blacklist time), so the vehicle
        doesn't repeatedly drive back to a site nothing has changed for.
        """
        log = self._host.log
        journal = get_component("journal")
        if not journal or not hasattr(journal, "discovered_sites"):
            return []
        try:
            unsupported_targets = self._host.get_unsupported_targets()
            existing_claims = self._host.get_claims()
            curr_tick = self._host.get_current_tick()
            sites = []
            for site in journal.discovered_sites("nocturna"):
                if getattr(site, "surveyed", False):
                    continue
                key = f"site_{site.id}"

                target_entry = unsupported_targets.get(key)
                if target_entry:
                    can_attempt, attempt_reason = self._host.can_attempt_target(key, target_entry)
                    log.debug(f"[{self._host.name}] {key}: unsupported entry found (reason={target_entry.get('reason', target_entry.get('status'))!r}) -> can_attempt={can_attempt} ({attempt_reason})")
                    if not can_attempt:
                        continue
                else:
                    log.debug(f"[{self._host.name}] {key}: no unsupported entry on record.")

                claim = existing_claims.get(key)
                if claim and (claim.get("vehicle") != self._host.name and claim.get("rover") != self._host.name):
                    claim_age = curr_tick - claim.get("tick", 0)
                    if curr_tick == 0 or claim_age < self._host.CLAIM_STALE_TICKS:
                        log.debug(f"[{self._host.name}] {key}: skipped, actively claimed by {claim.get('vehicle', claim.get('rover'))} ({claim_age} ticks ago).")
                        continue

                sites.append(site)
            home = self._host.assigned_slot_coords
            sites.sort(key=lambda s: self._host.distance_between(home, (s.x, s.y)))
            return sites
        except Exception:
            return []

    def survey_spiral_points(self, step=None, start_index=0, max_points=160):
        """Yields indexed outward square-spiral waypoints spaced for the mounted sonar."""
        sonar = getattr(self._host.vehicle, "sonar", None)
        if not sonar:
            return

        if step is None:
            try:
                step = max(20.0, sonar.range() * 0.75)
            except Exception:
                step = 35.0

        x, y = self._host.assigned_slot_coords
        directions = [(1, 0), (0, 1), (-1, 0), (0, -1)]
        direction_index = 0
        leg_length = 1
        point_index = 0
        yielded = 0

        while yielded < max_points:
            for _ in range(2):
                dx, dy = directions[direction_index % len(directions)]
                for _ in range(leg_length):
                    x += dx * step
                    y += dy * step
                    if point_index >= start_index:
                        yield (point_index, x, y)
                        yielded += 1
                        if yielded >= max_points:
                            return
                    point_index += 1
                direction_index += 1
            leg_length += 1

    def save_survey_waypoint(self, point_index, coords, sites):
        """Publishes completed spiral progress to the shared Data Archive notebook."""
        site_summaries = []
        for site in sites or []:
            try:
                kind = site.kind() if hasattr(site, "kind") else getattr(site, "kind", "unknown")
            except Exception:
                kind = "unknown"
            site_summaries.append({
                "id": getattr(site, "id", None),
                "kind": kind,
                "x": getattr(site, "x", None),
                "y": getattr(site, "y", None),
                "surveyed": getattr(site, "surveyed", False),
                "item_id": getattr(site, "item_id", None),
            })

        def update_progress(current):
            progress = dict(current or {})
            waypoints = list(progress.get("waypoints", []))
            entry = {
                "index": point_index,
                "coords": [coords[0], coords[1]],
                "sites": site_summaries,
            }
            if not any(item.get("index") == point_index for item in waypoints):
                waypoints.append(entry)
            progress["waypoints"] = waypoints
            progress["next_index"] = max(point_index + 1, progress.get("next_index", 0))
            progress["last_completed"] = entry
            progress["updated_by"] = self._host.name
            return progress

        archive.transaction(SURVEY_SPIRAL_KEY, {}, update_progress)

    def survey_known_pois(self, max_points=20):
        """Scans multiple known contacts in one battery-safe outward route."""
        completed = 0
        visited = set()

        # A target restored from a saved mission (see vehicle_claims.py) after
        # a script reload takes priority over discovery, so we continue toward
        # the same destination instead of restarting the search from scratch.
        resumed = None
        if self.current_target_key and self.current_target and self.current_target.get("coords"):
            resumed = (self.current_target_key, tuple(self.current_target["coords"]))
            self._host.log.print(f"[{self._host.name}] Resuming previously claimed POI '{resumed[0]}' at {resumed[1]} after reload.")

        while completed < max_points:
            current_pos = self._host.get_position()

            if resumed:
                target_key, target = resumed
                resumed = None
                target_label = "resumed target"
            else:
                # Two pools: fresh "?" contacts to scan, and already-classified
                # sites whose survey() previously failed but may now succeed
                # (upgraded sonar, new scan research) -- see
                # unsurveyed_known_sites(). Merged into one distance-sorted
                # route so the vehicle doesn't need a separate pass for each.
                candidates = [
                    {"key": f"poi_{p.x}_{p.y}", "coords": (p.x, p.y), "label": "unscanned POI"}
                    for p in self.unscanned_pois()
                    if (p.x, p.y) not in visited
                ] + [
                    {"key": f"site_{s.id}", "coords": (s.x, s.y), "label": f"unsurveyed site {s.id}"}
                    for s in self.unsurveyed_known_sites()
                    if (s.x, s.y) not in visited
                ]
                candidates.sort(key=lambda c: self._host.distance_between(current_pos, c["coords"]))
                self._host.log.debug(f"[{self._host.name}] survey_known_pois(): {len(candidates)} nearest-first candidate(s) from {current_pos}.")

                chosen = None
                for candidate in candidates:
                    budget = self._host.calculate_trip_energy(candidate["coords"], planned_scans=4)
                    if budget["is_achievable"]:
                        self._host.log.debug(f"[{self._host.name}] survey_known_pois(): chose {candidate['key']} ({candidate['label']}) at {candidate['coords']}, budget={budget['total_required_wh']:.1f} Wh.")
                        chosen = candidate
                        visited.add(candidate["coords"])
                        break
                    else:
                        self._host.log.debug(f"[{self._host.name}] survey_known_pois(): rejected {candidate['key']} ({candidate['label']}), unreachable within budget ({budget['total_required_wh']:.1f} Wh required).")
                if chosen is None:
                    if candidates:
                        self._host.log.print(f"[{self._host.name}] Remaining known POIs/sites exceed the current route budget; returning home.")
                    break

                target = chosen["coords"]
                target_key = chosen["key"]
                target_label = chosen["label"]

            self._host.claim_target(target_key, {"coords": target, "name": target_key, "type": "poi"})
            self.current_target_key = target_key
            self.current_target = {"coords": target, "name": target_key, "type": "poi"}
            self._host.save_mission("poi_survey", self.current_target)
            self._host.publish_telemetry("SURVEY_POI", f"POI_{target[0]}_{target[1]}")
            self._host.log.print(f"[{self._host.name}] Surveying known {target_label} at {target} ({self._host.distance_between(current_pos, target):.1f} m leg).")
            if not self._host.drive_to(target[0], target[1]):
                self._host.log.level("warn").print(f"[{self._host.name}] Could not safely reach POI at {target}; ending survey pass.")
                self._host.release_target_claim(target_key)
                break
            self._host.vehicle.nav.brake()
            scan_reserve = self._host.SONAR_WH_BUDGET * 4 * self._host.SAFETY_MARGIN_MULTIPLIER
            # Comfortable reserve, not the bare floor -- keeps the return leg fast.
            if self._host.get_battery()[0] <= self._host.energy_needed_to_return_comfortably() + scan_reserve:
                self._host.log.level("warn").print(f"[{self._host.name}] Insufficient energy to scan POI at {target}; returning home.")
                self._host.release_target_claim(target_key)
                break
            sites = self.scan_and_survey()
            self._host.release_target_claim(target_key)
            self.save_survey_waypoint(completed, target, sites)
            completed += 1
            if self._host.get_battery()[0] < self._host.energy_needed_to_return_comfortably():
                break
        if completed:
            self._host.log.print(f"[{self._host.name}] Completed {completed} POI scans on one outward route; returning home.")
        return completed

    def run_survey_loop(self, max_points=160, spiral_fallback=False):
        """Autonomous survey loop: scans known POIs first, optionally falls back to spiral."""
        if not hasattr(self._host.vehicle, "sonar"):
            self._host.log.level("warn").print(f"[{self._host.name}] Survey loop requires a mounted Sonar Module.")
            return
        if not hasattr(self._host.vehicle, "nav"):
            self._host.log.level("warn").print(f"[{self._host.name}] Survey loop requires a mounted Nav Module.")
            return

        self._host.log.print(f"[{self._host.name}] Survey Controller online. Starting battery-safe survey.")
        validate_game_version()
        while True:
            try:
                if self._host.handle_recall_if_active():
                    sleep(5.0)
                    continue

                # Pioneer-only auto-upgrade/Sport-Nav-request pass -- see
                # lib/vehicle_upgrade.py. Self-guarded (only acts once
                # actually idle at base), and hasattr-gated since this loop is
                # shared with RoverController, which never mixes in
                # VehicleUpgradeMixin.
                upgrade_cycle = getattr(self._host, "handle_upgrade_cycle_if_idle", None)
                if upgrade_cycle is not None:
                    upgrade_cycle()

                # Only top off before departing on a fresh expedition (i.e. when
                # actually at base). A reload mid-trip must not detour all the
                # way home just to satisfy this check before resuming.
                if self._host.is_at_base():
                    _, _, level = self._host.get_battery()
                    if level < 0.95:
                        self._host.recharge_at_station(target_level=1.0)

                poi_completed = self.survey_known_pois(max_points=max_points)
                if poi_completed > 0 or self.unscanned_pois() or self.unsurveyed_known_sites():
                    self._host.return_to_base()
                    self._host.publish_telemetry("SURVEY_COMPLETE", f"{poi_completed} known POIs")
                    self._host.recharge_at_station(target_level=1.0)
                    sleep(5.0)
                    continue

                if not spiral_fallback:
                    self._host.log.print(f"[{self._host.name}] All known POIs are scanned; no random spiral fallback requested.")
                    self._host.publish_telemetry("SURVEY_COMPLETE", "all known POIs scanned")
                    sleep(30.0)
                    continue

                progress = archive.get(SURVEY_SPIRAL_KEY, {}) or {}
                start_index = progress.get("next_index", 0)
                completed = 0
                for point_index, target_x, target_y in self.survey_spiral_points(
                    start_index=start_index,
                    max_points=max_points,
                ):
                    if hasattr(self._host.vehicle, "is_being_rescued") and self._host.vehicle.is_being_rescued():
                        self._host.log.level("warn").print(f"[{self._host.name}] Rescue in progress; pausing survey loop.")
                        break
                    if self._host.is_recalled():
                        self._host.log.print(f"[{self._host.name}] Recall requested; pausing spiral survey.")
                        break

                    budget = self._host.calculate_trip_energy(
                        (target_x, target_y),
                        planned_scans=4,
                    )
                    if not budget["is_achievable"]:
                        self._host.log.print(f"[{self._host.name}] Spiral boundary reached at ({target_x:.1f}, {target_y:.1f}); returning home.")
                        break

                    self._host.publish_telemetry("SURVEY_OUTBOUND", f"{target_x:.1f},{target_y:.1f}")
                    if not self._host.drive_to(target_x, target_y):
                        self._host.log.level("warn").print(f"[{self._host.name}] Could not safely reach spiral waypoint; returning home.")
                        break

                    # Comfortable reserve, not the bare floor -- keeps the return leg fast.
                    scan_reserve = self._host.SONAR_WH_BUDGET * 4 * self._host.SAFETY_MARGIN_MULTIPLIER
                    if self._host.get_battery()[0] <= self._host.energy_needed_to_return_comfortably() + scan_reserve:
                        self._host.log.level("warn").print(f"[{self._host.name}] Insufficient energy for safe scan at ({target_x:.1f}, {target_y:.1f}); returning home.")
                        break

                    # scan_and_survey() attributes any too_hard/tier_too_low/
                    # research_required/wrong_scanner status to
                    # self.current_target_key -- spiral waypoints aren't
                    # claimed via claim_target() (not fleet-reserved), but
                    # this still has to be set to *something* or an
                    # unresolved contact found here is silently dropped
                    # instead of blacklisted, and keeps getting rediscovered
                    # every pass (known-POI scans of the same coordinates
                    # never get a chance to fix it, since a genuinely
                    # unresolved contact has no PointOfInterest entry of its
                    # own to enumerate).
                    spiral_key = f"poi_{target_x}_{target_y}"
                    self.current_target_key = spiral_key
                    self.current_target = {"coords": (target_x, target_y), "name": spiral_key, "type": "poi"}
                    sites = self.scan_and_survey()
                    self.current_target_key = None
                    self.current_target = None
                    if hasattr(self._host.vehicle, "is_being_rescued") and self._host.vehicle.is_being_rescued():
                        self._host.log.level("warn").print(f"[{self._host.name}] Rescue started during scan; abandoning survey pass.")
                        break
                    self.save_survey_waypoint(point_index, (target_x, target_y), sites)
                    completed += 1

                    if self._host.get_battery()[0] < self._host.energy_needed_to_return_comfortably():
                        self._host.log.print(f"[{self._host.name}] Return reserve reached after survey; returning home.")
                        break

                self._host.return_to_base()
                spiral_data = archive.get(SURVEY_SPIRAL_KEY, {}) or {}
                next_index = spiral_data.get("next_index", start_index)
                self._host.publish_telemetry("SURVEY_COMPLETE", f"{completed} waypoints; next {next_index}")
                self._host.log.print(f"[{self._host.name}] Survey pass complete ({completed} waypoints). Next spiral index: {next_index}. Recharging before continuing.")
                self._host.recharge_at_station(target_level=1.0)
                sleep(5.0)
            except Exception as e:
                self._host.log.level("error").print(f"[{self._host.name}] Survey loop exception: {e}. Returning home.")
                try:
                    self._host.vehicle.nav.brake()
                except Exception:
                    pass
                self._host.return_to_base()
                sleep(5.0)