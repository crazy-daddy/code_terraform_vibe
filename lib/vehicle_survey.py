# Vehicle mixin: sonar scanning/surveying, POI discovery, and the autonomous
# survey loop (known POIs first, optional outward spiral fallback). Shared by
# Rover and Pioneer via VehicleController (lib/vehicle.py). Drilling lives in
# lib/mining.py's MiningMixin.

from archive import archive

SURVEY_SPIRAL_KEY = "survey.spiral"
LEGACY_PIONEER_SPIRAL_KEY = "pioneer.survey_spiral"


class VehicleSurveyMixin:
    """
    Sonar field operations and the autonomous survey loop, mixed into
    VehicleController. Depends on VehicleClaimsMixin for target reservation
    and VehicleEnergyMixin/VehicleNavigationMixin for trip budgeting & driving.
    """

    def scan_and_survey(self):
        """Scans the local area and surveys discovered sites."""
        self.last_scan_status = "unavailable"
        if not hasattr(self.vehicle, "sonar"):
            print(f"[{self.name}] Error: No SonarModule mounted!")
            return []

        print(f"[{self.name}] Activating Sonar sweep...")
        self.publish_telemetry("SCANNING")
        res = self.vehicle.sonar.scan()
        self.last_scan_status = res.status
        if res.status not in ["ok", "too_hard", "tier_too_low", "research_required"]:
            print(f"[{self.name}] Sonar scan status: {res.status} - {res.message}")
            if res.status in ["wrong_scanner", "not_allowed", "out_of_range"]:
                if self.current_target_key:
                    self.blacklist_target(self.current_target_key, res.status, res.message)
            return []

        if res.status in ["too_hard", "tier_too_low", "research_required"]:
            print(f"[{self.name}] Sonar scan limitation: {res.status} - {res.message}")
            if self.current_target_key:
                self.blacklist_target(self.current_target_key, res.status, res.message)

        sites = getattr(res, "sites", [])
        if res.status == "ok" and self.current_target_key:
            self.clear_unsupported_target(self.current_target_key)

        surveyed_sites = []
        for s in sites:
            if not getattr(s, "surveyed", False):
                print(f"[{self.name}] Surveying site {s.id} ({s.kind()})...")
                s_res = self.vehicle.sonar.survey(s.id)
                if s_res.status == "ok":
                    self.clear_unsupported_target(f"site_{s.id}")
                    surveyed_sites.append(s_res.site)
                elif s_res.status in ["too_hard", "tier_too_low", "research_required", "wrong_scanner"]:
                    print(f"[{self.name}] Site {s.id} survey limitation: {s_res.status} - {s_res.message}")
                    self.blacklist_target(f"site_{s.id}", s_res.status, s_res.message)
                    surveyed_sites.append(s)
                else:
                    surveyed_sites.append(s)
            else:
                surveyed_sites.append(s)
            sleep(0.5)

        return surveyed_sites

    def sonar_signature(self):
        """Returns the mounted sonar capability used for retry decisions."""
        sonar = getattr(self.vehicle, "sonar", None)
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
        self.blacklist_target(target_key, status, f"Scan limited: {status}")

    def unscanned_pois(self):
        """Returns known map contacts that still need a vehicle sonar scan."""
        planet = get_component("nocturna")
        if not planet or not hasattr(planet, "points_of_interest"):
            return []
        try:
            unsupported_targets = self.get_unsupported_targets()
            existing_claims = self.get_claims()
            curr_tick = self.get_current_tick()
            points = []
            for point in planet.points_of_interest():
                if getattr(point, "scanned", False):
                    continue
                key = f"poi_{point.x}_{point.y}"
                legacy_key = f"{point.x}:{point.y}"

                # Check unsupported / blacklisted targets across fleet
                target_entry = unsupported_targets.get(key) or unsupported_targets.get(legacy_key)
                if target_entry:
                    can_attempt, _ = self.can_attempt_target(key, target_entry)
                    if not can_attempt:
                        continue

                # Check if claimed by another active vehicle (Rover, Pioneer, or peer)
                claim = existing_claims.get(key)
                if claim and (claim.get("vehicle") != self.name and claim.get("rover") != self.name):
                    claim_age = curr_tick - claim.get("tick", 0)
                    if curr_tick == 0 or claim_age < self.CLAIM_STALE_TICKS:
                        continue

                points.append(point)
            home = self.assigned_slot_coords
            points.sort(key=lambda p: self.distance_between(home, (p.x, p.y)))
            return points
        except Exception:
            return []

    def survey_spiral_points(self, step=None, start_index=0, max_points=160):
        """Yields indexed outward square-spiral waypoints spaced for the mounted sonar."""
        sonar = getattr(self.vehicle, "sonar", None)
        if not sonar:
            return

        if step is None:
            try:
                step = max(20.0, sonar.range() * 0.75)
            except Exception:
                step = 35.0

        x, y = self.assigned_slot_coords
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
            progress["updated_by"] = self.name
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
            print(f"[{self.name}] Resuming previously claimed POI '{resumed[0]}' at {resumed[1]} after reload.")

        while completed < max_points:
            current_pos = self.get_position()

            if resumed:
                target_key, target = resumed
                resumed = None
            else:
                points = self.unscanned_pois()
                candidates = [
                    p for p in points
                    if (getattr(p, "x", None), getattr(p, "y", None)) not in visited
                ]
                candidates.sort(key=lambda p: self.distance_between(current_pos, (p.x, p.y)))

                poi = None
                for candidate in candidates:
                    key = (candidate.x, candidate.y)
                    budget = self.calculate_trip_energy((candidate.x, candidate.y), planned_scans=4)
                    if budget["is_achievable"]:
                        poi = candidate
                        visited.add(key)
                        break
                if poi is None:
                    if candidates:
                        print(f"[{self.name}] Remaining known POIs exceed the current route budget; returning home.")
                    break

                target = (poi.x, poi.y)
                target_key = f"poi_{poi.x}_{poi.y}"

            self.claim_target(target_key, {"coords": target, "name": target_key, "type": "poi"})
            self.current_target_key = target_key
            self.current_target = {"coords": target, "name": target_key, "type": "poi"}
            self.save_mission("poi_survey", self.current_target)
            self.publish_telemetry("SURVEY_POI", f"POI_{target[0]}_{target[1]}")
            print(f"[{self.name}] Surveying known unscanned POI at {target} ({self.distance_between(current_pos, target):.1f} m leg).")
            if not self.drive_to(target[0], target[1]):
                print(f"[{self.name}] Could not safely reach POI at {target}; ending survey pass.")
                self.release_target_claim(target_key)
                break
            self.vehicle.nav.brake()
            scan_reserve = self.SONAR_WH_BUDGET * 4 * self.SAFETY_MARGIN_MULTIPLIER
            if self.get_battery()[0] <= self.energy_needed_to_return_now() + scan_reserve:
                print(f"[{self.name}] Insufficient energy to scan POI at {target}; returning home.")
                self.release_target_claim(target_key)
                break
            sites = self.scan_and_survey()
            self.release_target_claim(target_key)
            self.save_survey_waypoint(completed, target, sites)
            completed += 1
            if self.get_battery()[0] < self.energy_needed_to_return_now():
                break
        if completed:
            print(f"[{self.name}] Completed {completed} POI scans on one outward route; returning home.")
        return completed

    def run_survey_loop(self, max_points=160, spiral_fallback=False):
        """Autonomous survey loop: scans known POIs first, optionally falls back to spiral."""
        if not hasattr(self.vehicle, "sonar"):
            print(f"[{self.name}] Survey loop requires a mounted Sonar Module.")
            return
        if not hasattr(self.vehicle, "nav"):
            print(f"[{self.name}] Survey loop requires a mounted Nav Module.")
            return

        print(f"Survey Controller ({self.name}) online. Starting battery-safe survey.")
        while True:
            try:
                if self.handle_recall_if_active():
                    sleep(5.0)
                    continue

                # Only top off before departing on a fresh expedition (i.e. when
                # actually at base). A reload mid-trip must not detour all the
                # way home just to satisfy this check before resuming.
                if self.is_at_base():
                    _, _, level = self.get_battery()
                    if level < 0.95:
                        self.recharge_at_station(target_level=1.0)

                poi_completed = self.survey_known_pois(max_points=max_points)
                if poi_completed > 0 or self.unscanned_pois():
                    self.return_to_base()
                    self.publish_telemetry("SURVEY_COMPLETE", f"{poi_completed} known POIs")
                    self.recharge_at_station(target_level=1.0)
                    sleep(5.0)
                    continue

                if not spiral_fallback:
                    print(f"[{self.name}] All known POIs are scanned; no random spiral fallback requested.")
                    self.publish_telemetry("SURVEY_COMPLETE", "all known POIs scanned")
                    sleep(30.0)
                    continue

                progress = archive.get(SURVEY_SPIRAL_KEY, {}) or {}
                start_index = progress.get("next_index", 0)
                completed = 0
                for point_index, target_x, target_y in self.survey_spiral_points(
                    start_index=start_index,
                    max_points=max_points,
                ):
                    if hasattr(self.vehicle, "is_being_rescued") and self.vehicle.is_being_rescued():
                        print(f"[{self.name}] Rescue in progress; pausing survey loop.")
                        break
                    if self.is_recalled():
                        print(f"[{self.name}] Recall requested; pausing spiral survey.")
                        break

                    budget = self.calculate_trip_energy(
                        (target_x, target_y),
                        planned_scans=4,
                    )
                    if not budget["is_achievable"]:
                        print(f"[{self.name}] Spiral boundary reached at ({target_x:.1f}, {target_y:.1f}); returning home.")
                        break

                    self.publish_telemetry("SURVEY_OUTBOUND", f"{target_x:.1f},{target_y:.1f}")
                    if not self.drive_to(target_x, target_y):
                        print(f"[{self.name}] Could not safely reach spiral waypoint; returning home.")
                        break

                    scan_reserve = self.SONAR_WH_BUDGET * 4 * self.SAFETY_MARGIN_MULTIPLIER
                    if self.get_battery()[0] <= self.energy_needed_to_return_now() + scan_reserve:
                        print(f"[{self.name}] Insufficient energy for safe scan at ({target_x:.1f}, {target_y:.1f}); returning home.")
                        break

                    sites = self.scan_and_survey()
                    if hasattr(self.vehicle, "is_being_rescued") and self.vehicle.is_being_rescued():
                        print(f"[{self.name}] Rescue started during scan; abandoning survey pass.")
                        break
                    self.save_survey_waypoint(point_index, (target_x, target_y), sites)
                    completed += 1

                    if self.get_battery()[0] < self.energy_needed_to_return_now():
                        print(f"[{self.name}] Return reserve reached after survey; returning home.")
                        break

                self.return_to_base()
                spiral_data = archive.get(SURVEY_SPIRAL_KEY, {}) or {}
                next_index = spiral_data.get("next_index", start_index)
                self.publish_telemetry("SURVEY_COMPLETE", f"{completed} waypoints; next {next_index}")
                print(f"[{self.name}] Survey pass complete ({completed} waypoints). Next spiral index: {next_index}. Recharging before continuing.")
                self.recharge_at_station(target_level=1.0)
                sleep(5.0)
            except Exception as e:
                print(f"[{self.name}] Survey loop exception: {e}. Returning home.")
                try:
                    self.vehicle.nav.brake()
                except Exception:
                    pass
                self.return_to_base()
                sleep(5.0)
