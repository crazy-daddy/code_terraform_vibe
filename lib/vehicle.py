# Shared Base Library for Surface Vehicle Automation (Rover & Pioneer)
# Provides navigation, dynamic energy accounting, fleet coordination,
# target reservation/claims, station recharging, and cargo offloading.

from archive import archive

SCAN_RESEARCH_IDS = [
    "research_geological_survey",
    "research_hydrology_survey",
    "research_petroleum_survey",
    "research_exotic_husbandry",
    "research_deep_exotics",
]

SURVEY_UNSUPPORTED_KEY = "survey.unsupported_targets"
LEGACY_ROVER_UNSUPPORTED_KEY = "rover.unsupported_targets"
SURVEY_CLAIMS_KEY = "survey.claims"
LEGACY_ROVER_CLAIMS_KEY = "rover.claims"
SURVEY_SPIRAL_KEY = "survey.spiral"
LEGACY_PIONEER_SPIRAL_KEY = "pioneer.survey_spiral"

class VehicleController:
    """
    Unified base controller for autonomous surface vehicles (Rover, Pioneer).
    Manages navigation, telemetry, battery thresholds, station charging,
    target claims, and modular tool operations.
    """
    DEFAULT_CRUISE_THROTTLE = 0.5
    DEFAULT_SPEED_MPH = 25.0
    WH_PER_METER_DEFAULT = 0.08
    SONAR_WH_BUDGET = 2.0
    MINE_WH_PER_UNIT = 2.5
    SAFETY_MARGIN_MULTIPLIER = 1.35
    MIN_EMERGENCY_RESERVE_WH = 8.0
    CLAIM_STALE_TICKS = 36000

    def __init__(self, vehicle, home_coords=(0, 0), cruise_throttle=0.5):
        self.vehicle = vehicle
        self.name = getattr(vehicle, "id", getattr(vehicle, "name", "vehicle"))
        self.home_coords = home_coords
        self.cruise_throttle = cruise_throttle

        # Each vehicle and module loadout gets its own calibration. Legacy
        # shared values are read only as a migration fallback.
        self.wh_per_meter = self.load_wh_per_meter()
        self.total_distance_driven = 0.0
        self.total_wh_spent_moving = 0.0

        # State tracking
        self.state = "INIT"
        self.current_target = None
        self.current_target_key = None
        self.assigned_slot_coords = self.get_home_slot_coords()

    def calibration_key(self):
        return f"vehicle.wh_per_meter:{self.name}"

    def load_wh_per_meter(self):
        value = archive.get(self.calibration_key(), None)
        if value is None:
            value = archive.get("fleet.wh_per_meter", None)
        if value is None and str(self.name).startswith("rover"):
            value = archive.get("rover.wh_per_meter", None)
        return value if value is not None else self.WH_PER_METER_DEFAULT

    def get_vehicle_index(self):
        """Extracts integer index from vehicle name (e.g. 'rover_1' -> 1, 'pioneer_2' -> 2)."""
        digits = ""
        for ch in str(self.name):
            if ch.isdigit():
                digits += ch
        if digits:
            try:
                return int(digits)
            except Exception:
                return 1
        return 1

    def get_rover_index(self):
        """Backward compatibility alias for rover index."""
        return self.get_vehicle_index()

    @staticmethod
    def extract_coords(pos):
        """Safely extracts (x, y) float tuple from tuple/list, dict, or Position object."""
        if pos is None:
            return None
        if isinstance(pos, (tuple, list)) and len(pos) >= 2:
            return (float(pos[0]), float(pos[1]))
        if isinstance(pos, dict) and "x" in pos and "y" in pos:
            return (float(pos["x"]), float(pos["y"]))
        x = getattr(pos, "x", None)
        y = getattr(pos, "y", None)
        if x is not None and y is not None:
            return (float(x), float(y))
        return None

    def get_all_charging_stations(self):
        """
        Discovers all known vehicle charging stations across the home base and all outposts.
        Returns a list of dicts: [{"id": str, "coords": (float, float), "component": obj}]
        """
        stations = []
        found_ids = set()

        outpost_net = get_component("outpost_network")
        if outpost_net:
            outposts_to_check = []
            if hasattr(outpost_net, "home"):
                try:
                    home = outpost_net.home()
                    if home:
                        outposts_to_check.append(home)
                except Exception:
                    pass
            if hasattr(outpost_net, "outposts"):
                try:
                    for op in outpost_net.outposts():
                        outposts_to_check.append(op)
                except Exception:
                    pass

            for op in outposts_to_check:
                if hasattr(op, "buildings"):
                    try:
                        for b in op.buildings():
                            b_type = getattr(b, "type_id", "")
                            b_id = getattr(b, "id", "")
                            if "charging" in b_type or "charging" in b_id:
                                pos = self.extract_coords(getattr(b, "position", None))
                                if pos:
                                    st_id = b_id or b_type
                                    if st_id not in found_ids:
                                        found_ids.add(st_id)
                                        comp = get_component(st_id) or b
                                        stations.append({
                                            "id": st_id,
                                            "coords": pos,
                                            "component": comp
                                        })
                    except Exception:
                        pass

        # Check standalone / registered charging station components
        standalone_candidates = ["vehicle_charging_station"] + [f"charging_station_{i}" for i in range(1, 8)]
        for cand_id in standalone_candidates:
            if cand_id not in found_ids:
                try:
                    comp = get_component(cand_id)
                    if comp:
                        pos = None
                        if hasattr(comp, "position"):
                            pos = self.extract_coords(comp.position)
                        elif hasattr(comp, "x") and hasattr(comp, "y"):
                            pos = (float(comp.x), float(comp.y))
                        if pos:
                            found_ids.add(cand_id)
                            stations.append({
                                "id": cand_id,
                                "coords": pos,
                                "component": comp
                            })
                except Exception:
                    pass

        return stations

    def get_nearest_charging_station(self, from_coords=None):
        """
        Returns the closest known charging station tuple: (coords, station_info_dict).
        If no station is detected, falls back to (self.home_coords, {}).
        """
        ref_coords = from_coords if from_coords is not None else self.get_position()
        stations = self.get_all_charging_stations()
        if not stations:
            fallback = self.get_charging_station_coords() or self.home_coords
            return fallback, {"id": "home_slot", "coords": fallback, "component": None}

        best_station = min(
            stations,
            key=lambda st: self.distance_between(ref_coords, st["coords"])
        )
        return best_station["coords"], best_station

    def get_charging_station_coords(self):
        """Locates the charging station's exact position if available."""
        """Locates the primary base charging station's exact position if available."""
        outpost_net = get_component("outpost_network")
        if outpost_net and hasattr(outpost_net, "home"):
            try:
                home = outpost_net.home()
                if home and hasattr(home, "buildings"):
                    for b in home.buildings():
                        b_type = getattr(b, "type_id", "")
                        b_id = getattr(b, "id", "")
                        if "charging" in b_type or "charging" in b_id:
                            return getattr(b, "position", (0.0, 0.0))
                            pos = self.extract_coords(getattr(b, "position", None))
                            if pos:
                                return pos
            except Exception:
                pass
        return None

    def get_home_slot_coords(self):
        """
        Calculates the base / charging station staging coordinates for this vehicle.
        All vehicles dock within the ~2m common service area of base & charging station.
        """
        cs_pos = self.get_charging_station_coords()
        if cs_pos:
            return cs_pos
        return self.home_coords

    def get_current_tick(self):
        """Fetches current simulation tick from clock component if available."""
        clock = get_component("clock")
        if clock and hasattr(clock, "tick"):
            try:
                return clock.tick()
            except Exception:
                pass
        return 0

    def publish_telemetry(self, state, target_desc=None):
        """Publishes live vehicle status to Data Archive under a dedicated key."""
        self.state = state
        curr_wh, cap_wh, lvl = self.get_battery()
        pos = self.get_position()
        telemetry = {
            "name": self.name,
            "state": state,
            "x": round(pos[0], 1),
            "y": round(pos[1], 1),
            "wh": round(curr_wh, 1),
            "level": round(lvl, 2),
            "target": target_desc or (self.current_target["name"] if self.current_target else "none"),
            "tick": self.get_current_tick()
        }
        archive.set(f"fleet.status.{self.name}", telemetry)
        if str(self.name).startswith("rover"):
            archive.set(f"rover.status.{self.name}", telemetry)

    def claim_target(self, target_key, target_info):
        """
        Atomically claims a destination/site in Data Archive so peer vehicles skip it.
        Returns True if claim successfully acquired, False otherwise.
        """
        claimed = [False]
        curr_tick = self.get_current_tick()

        def updater(claims):
            if not isinstance(claims, dict):
                claims = {}

            existing = claims.get(target_key)
            if existing:
                claim_owner = existing.get("rover", existing.get("vehicle"))
                claim_tick = existing.get("tick", 0)
                claim_age = curr_tick - claim_tick

                if claim_owner != self.name:
                    if curr_tick == 0 or claim_age < self.CLAIM_STALE_TICKS:
                        claimed[0] = False
                        return claims

            claims[target_key] = {
                "rover": self.name,
                "vehicle": self.name,
                "type": target_info.get("type", "unknown"),
                "coords": target_info.get("coords", (0, 0)),
                "name": target_info.get("name", target_key),
                "tick": curr_tick
            }
            claimed[0] = True
            return claims

        archive.transaction("rover.claims", {}, updater)
        archive.transaction(SURVEY_CLAIMS_KEY, {}, updater)
        archive.transaction(LEGACY_ROVER_CLAIMS_KEY, {}, updater)
        return claimed[0]

    def refresh_claim(self, target_key):
        """Renews heartbeat timestamp on an active target claim."""
        curr_tick = self.get_current_tick()

        def updater(claims):
            if isinstance(claims, dict) and target_key in claims:
                if claims[target_key].get("rover") == self.name or claims[target_key].get("vehicle") == self.name:
                    claims[target_key]["tick"] = curr_tick
            return claims

        archive.transaction("rover.claims", {}, updater)
        archive.transaction(SURVEY_CLAIMS_KEY, {}, updater)
        archive.transaction(LEGACY_ROVER_CLAIMS_KEY, {}, updater)

    def cleanup_stale_claims(self):
        """Removes expired fleet claims before selecting a new mission."""
        curr_tick = self.get_current_tick()
        if curr_tick <= 0:
            return

        def updater(claims):
            if not isinstance(claims, dict):
                return {}
            active = {}
            for key, claim in claims.items():
                if not isinstance(claim, dict):
                    continue
                claim_tick = claim.get("tick", 0)
                if curr_tick - claim_tick < self.CLAIM_STALE_TICKS:
                    active[key] = claim
            return active

        archive.transaction("rover.claims", {}, updater)
        archive.transaction(SURVEY_CLAIMS_KEY, {}, updater)
        archive.transaction(LEGACY_ROVER_CLAIMS_KEY, {}, updater)

    def release_target_claim(self, target_key=None):
        """Releases claim on target_key or releases all claims owned by this vehicle."""
        def updater(claims):
            if not isinstance(claims, dict):
                return {}
            if target_key:
                if target_key in claims and (claims[target_key].get("rover") == self.name or claims[target_key].get("vehicle") == self.name):
                    del claims[target_key]
            else:
                keys_to_remove = [k for k, v in claims.items() if isinstance(v, dict) and (v.get("rover") == self.name or v.get("vehicle") == self.name)]
                for k in keys_to_remove:
                    del claims[k]
            return claims

        archive.transaction("rover.claims", {}, updater)
        archive.transaction(SURVEY_CLAIMS_KEY, {}, updater)
        archive.transaction(LEGACY_ROVER_CLAIMS_KEY, {}, updater)
        if target_key == self.current_target_key or target_key is None:
            self.current_target = None
            self.current_target_key = None

    def get_claims(self):
        """Returns the unified map of active mission/target claims across the fleet."""
        shared = archive.get(SURVEY_CLAIMS_KEY, {})
        legacy = archive.get(LEGACY_ROVER_CLAIMS_KEY, {})
        claims = {}
        if isinstance(legacy, dict):
            claims.update(legacy)
        if isinstance(shared, dict):
            claims.update(shared)
        return claims

    def blacklist_target(self, target_key, reason, message="", scanner_type=None, scanner_tier=None, hardness_limit=None):
        """
        Marks a target as unsupported for the vehicle's current hardware/tech configuration
        (e.g. wrong_scanner, tier_too_low, too_hard, research_required, depleted).
        Stores the scanner/drill type, tier, and hardness limit so that when a vehicle is upgraded
        or equipped with appropriate technology, the target can be automatically revisited.
        Stores scanner tier, range, hardness limit, and unlocked scan researches so that
        when a vehicle is upgraded or scanning research is unlocked, it can be automatically revisited.
        """
        if scanner_type is None:
            if reason in ["wrong_scanner", "not_allowed", "out_of_range"]:
                scanner_type = "sonar"
            elif reason in ["too_hard", "tier_too_low", "research_required"]:
                scanner_type = "sonar" if target_key.startswith("poi_") else "drill"
            elif reason in ["depleted", "empty"]:
                scanner_type = "drill"
            else:
                scanner_type = "sonar"

        scanner_range = 50.0
        if scanner_tier is None:
            if scanner_type == "sonar" and hasattr(self.vehicle, "sonar"):
                try:
                    scanner_tier = self.vehicle.sonar.tier()
                except Exception:
                    scanner_tier = "basic"
            elif scanner_type == "drill" and hasattr(self.vehicle, "drill"):
                try:
                    h = self.vehicle.drill.hardness_limit()
                    scanner_tier = "heavy" if h >= 4 else ("industrial" if h >= 3 else "basic")
                except Exception:
                    scanner_tier = "basic"
            else:
                scanner_tier = "basic"

        if scanner_type == "sonar" and hasattr(self.vehicle, "sonar"):
            try:
                scanner_range = self.vehicle.sonar.range()
            except Exception:
                scanner_range = 50.0

        if hardness_limit is None:
            if scanner_type == "sonar" and hasattr(self.vehicle, "sonar"):
                try:
                    hardness_limit = self.vehicle.sonar.hardness_limit()
                except Exception:
                    hardness_limit = 1.0
            elif scanner_type == "drill" and hasattr(self.vehicle, "drill"):
                try:
                    hardness_limit = self.vehicle.drill.hardness_limit()
                except Exception:
                    hardness_limit = 1.0
            else:
                hardness_limit = 1.0

        unlocked_research_count = 0
        unlocked_scan_researches = []
        research = get_component("research")
        if research and hasattr(research, "unlocked"):
            try:
                unlocked_research_count = len(research.unlocked())
            except Exception:
                pass
        if research:
            for r_id in SCAN_RESEARCH_IDS:
                try:
                    if hasattr(research, "is_unlocked") and research.is_unlocked(r_id):
                        unlocked_scan_researches.append(r_id)
                except Exception:
                    pass

        def updater(targets):
            if not isinstance(targets, dict):
                targets = {}
            targets[target_key] = {
                "reason": reason,
                "message": message,
                "scanner_type": scanner_type,
                "scanner_tier": scanner_tier,
                "range": scanner_range,
                "hardness_limit": hardness_limit,
                "unlocked_research_count": unlocked_research_count,
                "unlocked_scan_researches": unlocked_scan_researches,
                "rover": self.name,
                "vehicle": self.name,
                "tick": self.get_current_tick()
            }
            return targets

        archive.transaction("rover.unsupported_targets", {}, updater)
        archive.transaction(SURVEY_UNSUPPORTED_KEY, {}, updater)
        archive.transaction(LEGACY_ROVER_UNSUPPORTED_KEY, {}, updater)
        self.release_target_claim(target_key)
        print(f"[{self.name}] Blacklisted unsupported target '{target_key}' ({reason}: {message} | scanner: {scanner_type}/{scanner_tier}, hardness_limit: {hardness_limit}). Fleet will skip until upgraded.")
        try:
            notify(f"[{self.name}] Skipped {target_key}: {reason} (req > {scanner_tier} T{hardness_limit})", level="info", duration_seconds=8.0)
        except Exception:
            pass

    def clear_unsupported_target(self, target_key):
        """Removes a target from unsupported_targets once technology or survey successfully resolves it."""
        def updater(targets):
            if isinstance(targets, dict) and target_key in targets:
                del targets[target_key]
            return targets
        archive.transaction("rover.unsupported_targets", {}, updater)
        archive.transaction(SURVEY_UNSUPPORTED_KEY, {}, updater)
        archive.transaction(LEGACY_ROVER_UNSUPPORTED_KEY, {}, updater)
        def p_updater(records):
            if isinstance(records, dict):
                if target_key in records:
                    del records[target_key]
                if target_key.startswith("poi_"):
                    parts = target_key.split("_")
                    if len(parts) >= 3:
                        leg_key = f"{parts[1]}:{parts[2]}"
                        if leg_key in records:
                            del records[leg_key]
            return records
        archive.transaction("pioneer.sonar_retries", {}, p_updater)

    def get_unsupported_targets(self):
        """Returns the unified map of unsupported/blacklisted targets across the fleet."""
        shared = archive.get(SURVEY_UNSUPPORTED_KEY, {})
        legacy_rover = archive.get(LEGACY_ROVER_UNSUPPORTED_KEY, {})
        legacy_pioneer = archive.get("pioneer.sonar_retries", {})
        targets = {}
        if isinstance(legacy_rover, dict):
            targets.update(legacy_rover)
        if isinstance(legacy_pioneer, dict):
            for k, v in legacy_pioneer.items():
                if ":" in k and not k.startswith("poi_"):
                    parts = k.split(":")
                    targets[f"poi_{parts[0]}_{parts[1]}"] = v
                targets[k] = v
        if isinstance(shared, dict):
            targets.update(shared)
        return targets

    def can_attempt_target(self, target_key, unsupported_entry):
        """
        Determines if this vehicle has sufficient equipment or upgraded technology
        to attempt a previously unsupported target.
        Returns (can_attempt: bool, reason_msg: str).
        """
        if not unsupported_entry or not isinstance(unsupported_entry, dict):
            return True, "not_blacklisted"

        reason = unsupported_entry.get("reason", unsupported_entry.get("status", ""))
        recorded_type = unsupported_entry.get("scanner_type", "sonar")
        recorded_tier = unsupported_entry.get("scanner_tier", "basic")
        recorded_h_limit = unsupported_entry.get("hardness_limit", 1.0)
        recorded_range = unsupported_entry.get("range", 50.0)

        # Permanent blockers
        if reason in ["depleted", "empty"]:
            return False, "depleted"

        # Biological contacts require bio scanner
        if reason == "wrong_scanner":
            if hasattr(self.vehicle, "bio_scanner"):
                return True, "has_bio_scanner"
            return False, "requires_bio_scanner"

        # Hardness limitation / tier limitation (sonar or drill)
        if reason in ["too_hard", "tier_too_low"]:
            if recorded_type == "sonar":
                if hasattr(self.vehicle, "sonar"):
                    curr_h = 1.0
                    if hasattr(self.vehicle.sonar, "hardness_limit"):
                        try:
                            curr_h = self.vehicle.sonar.hardness_limit()
                        except Exception:
                            curr_h = 1.0
                    curr_tier = "basic"
                    if hasattr(self.vehicle.sonar, "tier"):
                        try:
                            curr_tier = self.vehicle.sonar.tier()
                        except Exception:
                            curr_tier = "basic"
                    curr_range = 50.0
                    if hasattr(self.vehicle.sonar, "range"):
                        try:
                            curr_range = self.vehicle.sonar.range()
                        except Exception:
                            curr_range = 50.0

                    tier_order = {"none": 0, "basic": 1, "wide": 2, "deep": 3}
                    curr_tier_rank = tier_order.get(curr_tier, 1)
                    rec_tier_rank = tier_order.get(recorded_tier, 1)
                    if (curr_h > recorded_h_limit or 
                        curr_tier_rank > rec_tier_rank or 
                        curr_range > recorded_range or 
                        recorded_tier in ["none", None, "unknown"]):
                        return True, f"upgraded_sonar_{curr_tier}"
                return False, f"sonar_tier_too_low (has {recorded_tier} limit {recorded_h_limit})"

            elif recorded_type == "drill":
                if hasattr(self.vehicle, "drill"):
                    curr_h = 1.0
                    if hasattr(self.vehicle.drill, "hardness_limit"):
                        try:
                            curr_h = self.vehicle.drill.hardness_limit()
                        except Exception:
                            curr_h = 1.0
                    if curr_h > recorded_h_limit:
                        return True, f"upgraded_drill (limit {curr_h} > {recorded_h_limit})"
                return False, f"drill_hardness_too_low (limit {recorded_h_limit})"

        # Research requirement: ONLY rescan when scanning-relevant research is unlocked
        if reason == "research_required":
            research = get_component("research")
            if research:
                recorded_scan_researches = set(unsupported_entry.get("unlocked_scan_researches", []))
                for res_id in SCAN_RESEARCH_IDS:
                    if res_id not in recorded_scan_researches:
                        try:
                            if hasattr(research, "is_unlocked") and research.is_unlocked(res_id):
                                return True, f"new_scan_research_{res_id}"
                        except Exception:
                            pass
            return False, "scan_research_still_locked"

        return False, f"unsupported_{reason}"

    def get_battery(self):
        """Returns (current_wh, capacity_wh, fraction 0-1)."""
        try:
            wh = self.vehicle.battery.wh()
            cap = self.vehicle.battery.capacity()
            lvl = self.vehicle.battery.level()
            return wh, cap, lvl
        except Exception:
            return 0.0, 100.0, 0.0

    def get_position(self):
        """Returns (x, y) tuple of vehicle's current coordinates."""
        try:
            pos = self.vehicle.nav.get_position()
            return (pos.x, pos.y)
        except Exception:
            return self.assigned_slot_coords

    def distance_between(self, p1, p2):
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        return (dx * dx + dy * dy) ** 0.5

    def distance_to(self, x, y):
        pos = self.get_position()
        return self.distance_between(pos, (x, y))

    def distance_to_home(self):
        return self.distance_to(self.assigned_slot_coords[0], self.assigned_slot_coords[1])

    def calculate_trip_energy(self, target_coords, planned_drill_units=0, planned_scans=1):
        """
        Accurately calculates total energy required for a round-trip expedition:
        1. Energy to drive to target: dist_to_target * wh_per_meter
        2. Energy to scan & survey: planned_scans * SONAR_WH_BUDGET
        3. Energy to mine: planned_drill_units * MINE_WH_PER_UNIT
        4. Energy to drive home from target: dist_target_to_home * wh_per_meter
        4. Energy to drive to nearest charging station from target: dist_target_to_nearest_cs * wh_per_meter
        5. Safety buffer (35% margin) + hard emergency floor (8 Wh)
        """
        current_pos = self.get_position()
        dist_outbound = self.distance_between(current_pos, target_coords)
        dist_inbound = self.distance_between(target_coords, self.assigned_slot_coords)
        nearest_cs_from_target, _ = self.get_nearest_charging_station(from_coords=target_coords)
        dist_inbound = self.distance_between(target_coords, nearest_cs_from_target)

        drive_out_wh = dist_outbound * self.wh_per_meter
        drive_home_wh = dist_inbound * self.wh_per_meter
        sonar_wh = planned_scans * self.SONAR_WH_BUDGET
        mining_wh = planned_drill_units * self.MINE_WH_PER_UNIT

        net_expedition_wh = drive_out_wh + drive_home_wh + sonar_wh + mining_wh
        buffered_expedition_wh = net_expedition_wh * self.SAFETY_MARGIN_MULTIPLIER
        total_required_wh = buffered_expedition_wh + self.MIN_EMERGENCY_RESERVE_WH

        curr_wh, cap_wh, lvl = self.get_battery()

        return {
            "dist_outbound": dist_outbound,
            "dist_inbound": dist_inbound,
            "nearest_cs_coords": nearest_cs_from_target,
            "drive_out_wh": drive_out_wh,
            "drive_home_wh": drive_home_wh,
            "sonar_wh": sonar_wh,
            "mining_wh": mining_wh,
            "net_expedition_wh": net_expedition_wh,
            "total_required_wh": total_required_wh,
            "current_wh": curr_wh,
            "is_achievable": curr_wh >= total_required_wh
        }

    def energy_needed_to_reach(self, target_coords):
        """Calculates minimum energy required to reach target coordinates with safety buffer."""
        dist = self.distance_between(self.get_position(), target_coords)
        drive_wh = dist * self.wh_per_meter
        return (drive_wh * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH

    def energy_needed_to_reach_base(self):
        """Calculates energy required to drive back to home base staging slot."""
        return self.energy_needed_to_reach(self.assigned_slot_coords)

    def energy_needed_to_return_now(self):
        """Calculates minimum energy strictly required to drive straight home right now."""
        dist_home = self.distance_to_home()
        drive_wh = dist_home * self.wh_per_meter
        """Calculates minimum energy strictly required to drive to the nearest charging station right now."""
        nearest_cs, _ = self.get_nearest_charging_station()
        dist_cs = self.distance_between(self.get_position(), nearest_cs)
        drive_wh = dist_cs * self.wh_per_meter
        return (drive_wh * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH

    def calibrate_wh_per_meter(self, delta_dist, delta_wh):
        """Dynamically calibrates actual Wh/meter based on empirical driving performance."""
        if delta_dist > 5.0 and delta_wh > 0.1:
            observed_wh_per_m = delta_wh / delta_dist
            if 0.02 <= observed_wh_per_m <= 0.30:
                base_val = self.wh_per_meter if self.wh_per_meter is not None else self.WH_PER_METER_DEFAULT
                self.wh_per_meter = (base_val * 0.70) + (observed_wh_per_m * 0.30)
                archive.set(self.calibration_key(), self.wh_per_meter)

    def drive_to(self, target_x, target_y, precision=1.5, timeout_ticks=3000):
        """
        Drives vehicle toward target coordinates while enforcing:
        1. Continuous round-trip battery floor check.
        2. Heartbeat claim renewal.
        3. Dynamic wh_per_meter calibration.
        4. Stall / obstacle detection.
        """
        if not hasattr(self.vehicle, "nav"):
            print(f"[{self.name}] Error: No NavModule mounted!")
            return False

        start_wh, _, _ = self.get_battery()
        start_pos = self.get_position()
        last_pos = start_pos
        stalled_cycles = 0

        # Set target and engage throttle
        res = self.vehicle.nav.set_target(target_x, target_y)
        if res.status != "ok":
            print(f"[{self.name}] Nav set_target rejected: {res.status} - {res.message}")
            return False

        t_res = self.vehicle.nav.set_throttle(self.cruise_throttle)
        if t_res.status != "ok":
            print(f"[{self.name}] Nav set_throttle rejected: {t_res.status} - {t_res.message}")
            self.vehicle.nav.brake()
            return False

        ticks = 0
        while ticks < timeout_ticks:
            sleep(1.0)
            ticks += 10

            if hasattr(self.vehicle, "is_being_rescued") and self.vehicle.is_being_rescued():
                self.vehicle.nav.brake()
                print(f"[{self.name}] Rescue in progress; navigation suspended.")
                return False

            curr_pos = self.get_position()
            curr_wh, _, _ = self.get_battery()
            dist_remaining = self.vehicle.nav.get_distance_to(target_x, target_y) if hasattr(self.vehicle.nav, "get_distance_to") else self.distance_to(target_x, target_y)

            if self.current_target_key:
                self.refresh_claim(self.current_target_key)

            if dist_remaining <= precision:
                self.vehicle.nav.brake()
                total_dist = self.distance_between(start_pos, curr_pos)
                wh_used = start_wh - curr_wh
                self.calibrate_wh_per_meter(total_dist, wh_used)
                return True

            energy_needed = self.energy_needed_to_return_now()
            if curr_wh <= energy_needed:
                print(f"[{self.name}] Battery threshold reached ({curr_wh:.1f} Wh left, {energy_needed:.1f} Wh required to return). Aborting trip!")
                self.vehicle.nav.brake()
                return False
            nearest_cs, _ = self.get_nearest_charging_station()
            is_driving_to_station = (
                self.distance_between((target_x, target_y), nearest_cs) <= 3.0
                or self.distance_between((target_x, target_y), self.assigned_slot_coords) <= 3.0
            )
            dist_to_cs = self.distance_between(curr_pos, nearest_cs)
            if not is_driving_to_station and dist_to_cs > 3.0:
                energy_needed = self.energy_needed_to_return_now()
                if curr_wh <= energy_needed:
                    print(f"[{self.name}] Battery threshold reached ({curr_wh:.1f} Wh left, {energy_needed:.1f} Wh required to reach nearest station at {nearest_cs}). Aborting trip!")
                    self.vehicle.nav.brake()
                    return False

            # Stall detection: if vehicle hasn't moved >0.3m in 8 seconds
            step_dist = self.distance_between(last_pos, curr_pos)
            if step_dist < 0.3:
                stalled_cycles += 1
                if stalled_cycles >= 8:
                    print(f"[{self.name}] Vehicle appears stalled/stuck at {curr_pos}. Re-issuing drive command.")
                    self.vehicle.nav.brake()
                    sleep(0.5)
                    self.vehicle.nav.set_target(target_x, target_y)
                    self.vehicle.nav.set_throttle(self.cruise_throttle)
                    stalled_cycles = 0
            else:
                stalled_cycles = 0

            last_pos = curr_pos

        print(f"[{self.name}] Navigation timed out after {timeout_ticks} ticks.")
        self.vehicle.nav.brake()
        return False

    def drive_with_recharge(self, target_x, target_y, precision=1.5, max_stops=5):
        """
        Drives to (target_x, target_y), planning intermediate stops at charging stations
        along the route if the direct trip exceeds available or single-charge battery range.
        """
        stops = 0
        while stops < max_stops:
            curr_pos = self.get_position()
            target_coords = (float(target_x), float(target_y))
            dist_to_target = self.distance_between(curr_pos, target_coords)

            if dist_to_target <= precision:
                return True

            curr_wh, cap_wh, _ = self.get_battery()
            energy_to_target = self.energy_needed_to_reach(target_coords)
            nearest_cs_from_target, _ = self.get_nearest_charging_station(from_coords=target_coords)
            energy_target_to_cs = (self.distance_between(target_coords, nearest_cs_from_target) * self.wh_per_meter * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH
            total_required = energy_to_target + energy_target_to_cs

            if curr_wh >= total_required:
                reached = self.drive_to(target_x, target_y, precision=precision)
                return reached

            # Find an intermediate charging station closer to target that we can currently reach
            stations = self.get_all_charging_stations()
            best_station = None
            best_progress = 0.0

            for st in stations:
                st_coords = st["coords"]
                dist_to_st = self.distance_between(curr_pos, st_coords)
                if dist_to_st < 2.0:
                    continue

                energy_to_st = (dist_to_st * self.wh_per_meter * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH
                if curr_wh < energy_to_st:
                    continue

                dist_st_to_target = self.distance_between(st_coords, target_coords)
                progress = dist_to_target - dist_st_to_target
                if progress > 3.0 and progress > best_progress:
                    best_progress = progress
                    best_station = st

            if best_station:
                st_coords = best_station["coords"]
                st_id = best_station.get("id", "station")
                print(f"[{self.name}] Destination ({target_x:.1f}, {target_y:.1f}) exceeds direct battery ({curr_wh:.1f} Wh < {total_required:.1f} Wh). Stopping at intermediate station '{st_id}' at {st_coords} to recharge.")
                reached = self.drive_to(st_coords[0], st_coords[1], precision=1.0)
                if not reached:
                    print(f"[{self.name}] Failed to reach intermediate station '{st_id}'.")
                    return False
                self.recharge_at_station(target_level=1.0, station_coords=st_coords, station_id=best_station.get("id"))
                stops += 1
                continue
            else:
                nearest_cs, n_info = self.get_nearest_charging_station()
                dist_near_cs = self.distance_between(curr_pos, nearest_cs)
                if dist_near_cs > 2.0 and curr_wh < (cap_wh * 0.90):
                    print(f"[{self.name}] Topping off at nearest station '{n_info.get('id', 'station')}' before proceeding.")
                    reached = self.drive_to(nearest_cs[0], nearest_cs[1], precision=1.0)
                    if reached:
                        self.recharge_at_station(target_level=1.0, station_coords=nearest_cs, station_id=n_info.get("id"))
                        stops += 1
                        continue

                return self.drive_to(target_x, target_y, precision=precision)

        return self.drive_to(target_x, target_y, precision=precision)

    def return_to_base(self):
        """Safely drives back to the vehicle's assigned base staging slot."""
        """Safely drives back to the vehicle's assigned base staging slot, using intermediate charging if needed."""
        self.publish_telemetry("RETURNING_HOME")
        slot_x, slot_y = self.get_home_slot_coords()
        self.assigned_slot_coords = (slot_x, slot_y)
        print(f"[{self.name}] Returning to base slot ({slot_x:.1f}, {slot_y:.1f})...")
        reached = self.drive_to(slot_x, slot_y, precision=1.0)
        reached = self.drive_with_recharge(slot_x, slot_y, precision=1.0)

        if self.current_target_key:
            self.release_target_claim(self.current_target_key)

        return reached

    def return_to_nearest_station(self):
        """Drives to the nearest charging station in the network to recharge."""
        st_coords, st_info = self.get_nearest_charging_station()
        st_id = st_info.get("id", "charging_station")
        print(f"[{self.name}] Heading to nearest charging station '{st_id}' at {st_coords}...")
        self.publish_telemetry("RETURNING_TO_STATION")
        reached = self.drive_to(st_coords[0], st_coords[1], precision=1.0)
        return reached

    def unload_cargo(self):
        """Transfers mined/gathered minerals and items into Base Inventory."""
        if not hasattr(self.vehicle, "cargo"):
            return 0

        cargo_count = self.vehicle.cargo.count()
        if cargo_count == 0:
            return 0

        print(f"[{self.name}] Offloading {cargo_count} items into Base Inventory...")
        self.publish_telemetry("UNLOADING")

        out_port = getattr(self.vehicle, "output", None)
        if not out_port:
            for attr in ["output_1", "port_out", "out"]:
                if hasattr(self.vehicle, attr):
                    out_port = getattr(self.vehicle, attr)
                    break

        if not out_port:
            print(f"[{self.name}] Error: No output port found on vehicle!")
            return 0

        if hasattr(out_port, "connected_to"):
            if out_port.connected_to() != "inventory":
                c_res = out_port.connect("inventory")
                if c_res.status != "ok":
                    print(f"[{self.name}] Connect to inventory notice: {c_res.status} - {c_res.message}")

        unloaded = 0
        inventory_full = False
        stacks = []
        if hasattr(self.vehicle.cargo, "stacks"):
            try:
                stacks = self.vehicle.cargo.stacks()
            except Exception:
                stacks = []

        if not stacks and hasattr(out_port, "stacks"):
            try:
                stacks = out_port.stacks()
            except Exception:
                stacks = []

        # If stacks are listed, transfer each stack
        if stacks:
            for stack in stacks:
                item_id = getattr(stack, "id", None)
                count = getattr(stack, "count", 0)
                if not item_id or count <= 0:
                    continue

                retries = 0
                while retries < 10:
                    res = out_port.send(item_id, count)
                    if res.status == "ok":
                        moved = getattr(res, "moved", count)
                        unloaded += moved
                        print(f"[{self.name}] Transferred {moved}x {item_id} to Inventory.")

                        # If ore was delivered, cooperatively wake up Smelter
                        if item_id in ["iron_ore", "silicon", "titanium", "cobalt", "rare_earth", "lead_ore"]:
                            self.wake_smelter()
                        break
                    elif res.status == "busy":
                        sleep(0.5)
                        retries += 1
                    elif res.status in ["target_full", "slots_full", "inventory_full"]:
                        inventory_full = True
                        print(f"[{self.name}] WARNING: Base inventory is full. Cargo remains aboard until space is available.")
                        try:
                            notify(f"[{self.name}] Base Inventory Full! Free space before the next expedition.", level="warn", duration_seconds=8.0)
                        except Exception:
                            pass
                        break
                    else:
                        print(f"[{self.name}] Offload notice: {res.status} - {res.message}")
                        break
                    sleep(0.3)
        else:
            # Fallback for common mined minerals if stacks() returned empty but hold has cargo
            for cand in ["iron_ore", "silicon", "titanium", "cobalt", "rare_earth", "lead_ore"]:
                if self.vehicle.cargo.count() == 0:
                    break
                res = out_port.send(cand, self.vehicle.cargo.count())
                if res.status == "ok":
                    moved = getattr(res, "moved", 1)
                    unloaded += moved
                    print(f"[{self.name}] Transferred {moved}x {cand} to Inventory.")
                    self.wake_smelter()
                    break
                if res.status in ["target_full", "slots_full", "inventory_full"]:
                    inventory_full = True
                    print(f"[{self.name}] WARNING: Base inventory is full. Cargo remains aboard until space is available.")
                    try:
                        notify(f"[{self.name}] Base Inventory Full! Free space before the next expedition.", level="warn", duration_seconds=8.0)
                    except Exception:
                        pass
                    break
                sleep(0.3)

        return -1 if inventory_full else unloaded

    def wake_smelter(self):
        """Cooperatively powers on and resumes smelter when fresh ore arrives."""
        shedded = archive.get("power.shedded", [])
        if any("smelter" in m for m in shedded):
            print(f"[{self.name}] Smelter wake deferred: currently shedded by Power Guard for grid preservation.")
            return

        pwr = get_component("power_control")
        if pwr and hasattr(pwr, "set_powered"):
            try:
                pwr.set_powered("smelter_1", True)
            except Exception:
                pass

        run_ctrl = get_component("run_control")
        if run_ctrl and hasattr(run_ctrl, "is_running") and hasattr(run_ctrl, "start"):
            try:
                if not run_ctrl.is_running("smelter_1"):
                    if pwr and hasattr(pwr, "is_powered"):
                        if pwr.is_powered("smelter_1"):
                            run_ctrl.start("smelter_1")
                    else:
                        run_ctrl.start("smelter_1")
            except Exception:
                pass

    def recharge_at_station(self, target_level=1.0, station_coords=None, station_id=None):
        """
        Parks at Vehicle Charging Station / base staging slot and charges until target level.
        Cooperates with the station controller (charging_station_*.py) which handles hardware
        charge() calls locally.
        """
        curr_wh, cap_wh, lvl = self.get_battery()
        if lvl >= target_level - 0.02:
            print(f"[{self.name}] Battery already charged ({lvl*100:.0f}%).")
            return True

        cs = None
        if station_coords is None:
            station_coords, st_info = self.get_nearest_charging_station()
            if not station_id:
                station_id = st_info.get("id")
            cs = st_info.get("component")
        else:
            station_coords = (float(station_coords[0]), float(station_coords[1]))
            if station_id:
                cs = get_component(station_id)
            if not cs:
                for st in self.get_all_charging_stations():
                    if self.distance_between(st["coords"], station_coords) < 2.0:
                        cs = st.get("component")
                        if not station_id:
                            station_id = st.get("id")
                        break

        if not cs:
            if station_id:
                cs = get_component(station_id)
            if not cs:
                for cand_id in ["vehicle_charging_station"] + [f"charging_station_{i}" for i in range(1, 8)]:
                    cand = get_component(cand_id)
                    if cand:
                        cs = cand
                        station_id = cand_id
                        break

        cs_coords = station_coords or self.get_charging_station_coords() or self.home_coords

        # Verify whether vehicle is actually inside the station's docked set
        is_docked = False
        if cs and hasattr(cs, "get_docked"):
            try:
                docked_fn = getattr(cs, "get_docked")
                is_docked = self.name in docked_fn()
            except Exception:
                pass

        if not is_docked:
            dist_to_cs = self.distance_to(cs_coords[0], cs_coords[1])
            if dist_to_cs > 1.2:
                print(f"[{self.name}] Position is {dist_to_cs:.1f}m from charging station '{station_id or 'station'}'. Driving to docking pad...")
                self.drive_to(cs_coords[0], cs_coords[1], precision=1.0)
            else:
                self.return_to_base()
                self.drive_to(cs_coords[0], cs_coords[1], precision=1.0)

        if hasattr(self.vehicle, "nav"):
            try:
                self.vehicle.nav.brake()
            except Exception:
                pass

        sleep(0.5)
        self.publish_telemetry("CHARGING")
        print(f"[{self.name}] Docked at station '{station_id or 'station'}'. Waiting for charge ({lvl*100:.0f}% -> {target_level*100:.0f}%)...")

        wait_cycles = 0
        last_reported_lvl = lvl

        while True:
            curr_wh, cap_wh, lvl = self.get_battery()
            if lvl >= target_level - 0.01:
                print(f"[{self.name}] Charging complete ({curr_wh:.1f} Wh, {lvl*100:.0f}%).")
                break

            if abs(lvl - last_reported_lvl) >= 0.10:
                print(f"[{self.name}] Charging in progress... ({lvl*100:.0f}%, {curr_wh:.1f} Wh)")
                last_reported_lvl = lvl

            wait_cycles += 1
            if wait_cycles % 5 == 0 and cs:
                try:
                    get_docked_fn = getattr(cs, "get_docked", None)
                    docked = get_docked_fn() if get_docked_fn else []
                    if self.name not in docked:
                        print(f"[{self.name}] Not yet registered in station dock area. Re-aligning to charging station ({cs_coords})...")
                        self.drive_to(cs_coords[0], cs_coords[1], precision=1.0)
                        if hasattr(self.vehicle, "nav"):
                            self.vehicle.nav.brake()
                    else:
                        get_active_fn = getattr(cs, "get_active", None)
                        get_queue_fn = getattr(cs, "get_queue", None)
                        active = get_active_fn() if get_active_fn else []
                        queued = get_queue_fn() if get_queue_fn else []
                        if self.name not in active and self.name not in queued:
                            st_script = f"{station_id}.py" if station_id and "charging_station" in station_id else "charging_station_1.py"
                            print(f"[{self.name}] Advisory: Vehicle is docked, but charging station '{station_id}' has not queued it yet. Ensure '{st_script}' is running!")
                            try:
                                notify(f"[{self.name}] Docked and waiting. Ensure '{st_script}' is running!", level="info", duration_seconds=8.0)
                            except Exception:
                                pass
                except Exception:
                    pass

            sleep(2.0)

        return True

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

    def mine_current_site(self, max_units=10):
        """Extracts minerals using the mounted Drill Module while enforcing battery & cargo limits."""
        if not hasattr(self.vehicle, "drill"):
            print(f"[{self.name}] Error: No DrillModule mounted!")
            return 0

        self.publish_telemetry("MINING")
        mined_count = 0
        self.mining_interrupted_battery = False

        while mined_count < max_units:
            if self.vehicle.cargo.full():
                print(f"[{self.name}] Cargo hold full (10/10). Finishing mining operation.")
                break

            curr_wh, _, _ = self.get_battery()
            needed_to_return = self.energy_needed_to_return_now()
            if curr_wh <= (needed_to_return + self.MINE_WH_PER_UNIT * 1.5):
                print(f"[{self.name}] Reached return energy threshold ({curr_wh:.1f} Wh left). Ceasing extraction.")
                print(f"[{self.name}] Reached return energy threshold ({curr_wh:.1f} Wh left). Ceasing extraction for recharge.")
                self.mining_interrupted_battery = True
                break

            m_res = self.vehicle.drill.mine()
            if m_res.status == "ok":
                mined_count += 1
                if self.current_target_key:
                    self.clear_unsupported_target(self.current_target_key)
                print(f"[{self.name}] Mined unit {mined_count}/{max_units}. Cargo: {self.vehicle.cargo.count()}/10.")
            elif m_res.status == "busy":
                sleep(0.5)
            else:
                print(f"[{self.name}] Drill finished or stopped: {m_res.status} - {m_res.message}")
                if m_res.status in ["tier_too_low", "too_hard", "research_required", "depleted", "not_found", "empty"]:
                    if self.current_target_key:
                        self.blacklist_target(self.current_target_key, m_res.status, m_res.message)
                break

            if self.current_target_key:
                self.refresh_claim(self.current_target_key)

        return mined_count

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
        while completed < max_points:
            points = self.unscanned_pois()
            current_pos = self.get_position()
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
            self.publish_telemetry("SURVEY_POI", f"POI_{poi.x}_{poi.y}")
            print(f"[{self.name}] Surveying known unscanned POI at {target} ({self.distance_between(current_pos, target):.1f} m leg).")
            if not self.drive_to(poi.x, poi.y):
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
