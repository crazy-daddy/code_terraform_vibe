# Archive Cleaner & Validator Library
# Validates Data Archive ("notebook") entries, repairs corrupted data,
# cleans stale claims, removes obsolete blacklist/unsupported entries,
# deduplicates survey waypoints, and prunes stale telemetry.

from archive import archive

# Stale claim duration (1 simulation hour = 36000 ticks at 10 ticks/sec)
CLAIM_STALE_TICKS = 36000

# Canonical & Legacy Archive Keys
SURVEY_CLAIMS_KEY = "survey.claims"
LEGACY_ROVER_CLAIMS_KEY = "rover.claims"

SURVEY_UNSUPPORTED_KEY = "survey.unsupported_targets"
LEGACY_ROVER_UNSUPPORTED_KEY = "rover.unsupported_targets"
LEGACY_PIONEER_SONAR_KEY = "pioneer.sonar_retries"

SURVEY_SPIRAL_KEY = "survey.spiral"
LEGACY_PIONEER_SPIRAL_KEY = "pioneer.survey_spiral"


def safe_get_component(name):
    """Safely retrieves a game component without raising exceptions."""
    try:
        return get_component(name)
    except Exception:
        return None


class ArchiveCleaner:
    """
    Validates, repairs, and purges obsolete or corrupted entries from the Data Archive.
    Supports dry-run inspection mode and live commit mode.
    """
    def __init__(self, archive_client=None, dry_run=True, verbose=True):
        self.archive = archive_client if archive_client is not None else archive
        self.dry_run = dry_run
        self.verbose = verbose
        self.log_messages = []
        self.stats = {
            "keys_scanned": 0,
            "claims_checked": 0,
            "claims_removed": 0,
            "unsupported_checked": 0,
            "unsupported_removed": 0,
            "unsupported_migrated": 0,
            "waypoints_cleaned": 0,
            "telemetry_removed": 0,
            "calibration_repaired": 0,
            "corrupted_keys_deleted": 0,
            "errors": 0
        }

    def log(self, msg):
        self.log_messages.append(msg)
        if self.verbose:
            print(msg)

    def is_available(self):
        return self.archive is not None and getattr(self.archive, "available", False)

    def get_current_tick(self):
        clock = safe_get_component("clock")
        if clock and hasattr(clock, "tick"):
            try:
                return clock.tick()
            except Exception:
                pass
        return 0

    def get_scanned_pois(self):
        """Returns set of coordinates (x, y) and poi_x_y keys for already-scanned POIs."""
        scanned_keys = set()
        scanned_coords = set()
        nocturna = safe_get_component("nocturna")
        if nocturna and hasattr(nocturna, "points_of_interest"):
            try:
                pois = nocturna.points_of_interest() or []
                for p in pois:
                    if getattr(p, "scanned", False):
                        px, py = int(round(p.x)), int(round(p.y))
                        scanned_coords.add((px, py))
                        scanned_keys.add(f"poi_{px}_{py}")
                        scanned_keys.add(f"{px}:{py}")
            except Exception as e:
                self.log(f"[WARN] Failed querying points_of_interest: {e}")
        return scanned_keys, scanned_coords

    def get_surveyed_sites(self):
        """Returns set of site IDs and coordinates (x, y) for fully surveyed mineral sites."""
        surveyed_ids = set()
        surveyed_coords = set()
        journal = safe_get_component("journal")
        if journal and hasattr(journal, "surveyed_sites"):
            try:
                sites = journal.surveyed_sites("nocturna") or []
                for s in sites:
                    if getattr(s, "surveyed", True):
                        if hasattr(s, "id"):
                            surveyed_ids.add(str(s.id))
                        if hasattr(s, "x") and hasattr(s, "y"):
                            sx, sy = int(round(s.x)), int(round(s.y))
                            surveyed_coords.add((sx, sy))
                            surveyed_ids.add(f"site_{s.id}")
            except Exception as e:
                self.log(f"[WARN] Failed querying surveyed_sites: {e}")
        return surveyed_ids, surveyed_coords

    def get_active_vehicle_names(self):
        """Returns set of known active vehicle names/IDs from fleet."""
        vehicles = set()
        fleet = safe_get_component("fleet")
        if fleet and hasattr(fleet, "vehicles"):
            try:
                for v in fleet.vehicles() or []:
                    if hasattr(v, "id"):
                        vehicles.add(str(v.id))
                    if hasattr(v, "name"):
                        vehicles.add(str(v.name))
            except Exception as e:
                self.log(f"[WARN] Failed querying fleet.vehicles: {e}")
        return vehicles

    def clean_claims(self, current_tick, scanned_poi_keys, scanned_poi_coords, surveyed_site_ids, surveyed_site_coords):
        """
        Cleans stale, completed, or malformed claims in survey.claims and rover.claims.
        Deduplicates and synchronizes valid active claims.
        """
        self.log("\n--- Checking Survey & Rover Claims ---")
        shared_claims = self.archive.get(SURVEY_CLAIMS_KEY, {})
        legacy_claims = self.archive.get(LEGACY_ROVER_CLAIMS_KEY, {})

        combined_claims = {}
        if isinstance(legacy_claims, dict):
            combined_claims.update(legacy_claims)
        if isinstance(shared_claims, dict):
            combined_claims.update(shared_claims)

        clean_claims_map = {}
        claims_removed = 0

        for key, claim in combined_claims.items():
            self.stats["claims_checked"] += 1
            if not isinstance(claim, dict):
                self.log(f"  [DELETE CLAIM] Key '{key}': Corrupted payload (not a dict)")
                claims_removed += 1
                continue

            # 1. Check staleness
            claim_tick = claim.get("tick")
            if claim_tick is None or not isinstance(claim_tick, (int, float)):
                self.log(f"  [DELETE CLAIM] Key '{key}': Missing or invalid tick timestamp ({claim_tick})")
                claims_removed += 1
                continue

            if current_tick > 0:
                tick_age = current_tick - claim_tick
                if tick_age > CLAIM_STALE_TICKS:
                    self.log(f"  [DELETE CLAIM] Key '{key}': Stale claim (age: {tick_age} ticks > {CLAIM_STALE_TICKS})")
                    claims_removed += 1
                    continue
                elif tick_age < -1000:
                    self.log(f"  [DELETE CLAIM] Key '{key}': Future tick timestamp anomaly ({claim_tick} vs curr {current_tick})")
                    claims_removed += 1
                    continue

            # 2. Check if already scanned POI
            coords = claim.get("coords")
            is_scanned_poi = False
            if key in scanned_poi_keys:
                is_scanned_poi = True
            elif coords and isinstance(coords, (list, tuple)) and len(coords) >= 2:
                try:
                    cx, cy = int(round(float(coords[0]))), int(round(float(coords[1])))
                    if (cx, cy) in scanned_poi_coords or f"poi_{cx}_{cy}" in scanned_poi_keys:
                        is_scanned_poi = True
                except (ValueError, TypeError):
                    pass

            if is_scanned_poi:
                self.log(f"  [DELETE CLAIM] Key '{key}': Target POI is already scanned")
                claims_removed += 1
                continue

            # 3. Check if already surveyed site
            is_surveyed_site = False
            if key in surveyed_site_ids:
                is_surveyed_site = True
            elif coords and isinstance(coords, (list, tuple)) and len(coords) >= 2:
                try:
                    cx, cy = int(round(float(coords[0]))), int(round(float(coords[1])))
                    if (cx, cy) in surveyed_site_coords:
                        is_surveyed_site = True
                except (ValueError, TypeError):
                    pass

            if is_surveyed_site:
                self.log(f"  [DELETE CLAIM] Key '{key}': Target site is already surveyed")
                claims_removed += 1
                continue

            clean_claims_map[key] = claim

        self.stats["claims_removed"] += claims_removed
        self.log(f"  Result: {len(clean_claims_map)} active claims retained, {claims_removed} obsolete claims purged.")

        if not self.dry_run and (claims_removed > 0 or shared_claims != clean_claims_map or legacy_claims != clean_claims_map):
            self.archive.set(SURVEY_CLAIMS_KEY, clean_claims_map)
            self.archive.set(LEGACY_ROVER_CLAIMS_KEY, clean_claims_map)
            if self.archive.has(LEGACY_ROVER_CLAIMS_KEY):
                self.archive.delete(LEGACY_ROVER_CLAIMS_KEY)

    def clean_unsupported_targets(self, scanned_poi_keys, scanned_poi_coords, surveyed_site_ids, surveyed_site_coords):
        """
        Cleans unsupported/blacklisted targets from survey.unsupported_targets,
        rover.unsupported_targets, and legacy pioneer.sonar_retries.
        - Deletes targets that have now been scanned or surveyed.
        - Normalizes keys into canonical 'poi_x_y' format.
        - Purges transient invalid errors (e.g. out_of_range).
        """
        self.log("\n--- Checking Unsupported / Blacklisted Targets ---")
        shared_unsupported = self.archive.get(SURVEY_UNSUPPORTED_KEY, {})
        legacy_rover = self.archive.get(LEGACY_ROVER_UNSUPPORTED_KEY, {})
        legacy_pioneer = self.archive.get(LEGACY_PIONEER_SONAR_KEY, {})

        all_entries = {}
        # Load legacy pioneer first
        if isinstance(legacy_pioneer, dict):
            for k, v in legacy_pioneer.items():
                canonical_k = k
                if ":" in k and not k.startswith("poi_"):
                    parts = k.split(":")
                    if len(parts) >= 2:
                        try:
                            canonical_k = f"poi_{int(round(float(parts[0])))}_{int(round(float(parts[1])))}"
                            self.stats["unsupported_migrated"] += 1
                        except (ValueError, TypeError):
                            pass
                all_entries[canonical_k] = v

        # Load legacy rover
        if isinstance(legacy_rover, dict):
            all_entries.update(legacy_rover)

        # Load shared
        if isinstance(shared_unsupported, dict):
            all_entries.update(shared_unsupported)

        clean_unsupported = {}
        removed_count = 0

        for key, entry in all_entries.items():
            self.stats["unsupported_checked"] += 1
            if not isinstance(entry, dict):
                self.log(f"  [DELETE UNSUPPORTED] Key '{key}': Corrupted payload (not a dict)")
                removed_count += 1
                continue

            # Check transient / invalid reasons
            reason = entry.get("reason", entry.get("status", ""))
            if reason in ["out_of_range", "in_progress", "busy", "ok"]:
                self.log(f"  [DELETE UNSUPPORTED] Key '{key}': Transient reason '{reason}' should not be blacklisted")
                removed_count += 1
                continue

            # Extract coordinates from key if possible
            coords = None
            if key.startswith("poi_"):
                parts = key.split("_")
                if len(parts) >= 3:
                    try:
                        coords = (int(parts[1]), int(parts[2]))
                    except (ValueError, TypeError):
                        pass
            elif ":" in key:
                parts = key.split(":")
                if len(parts) >= 2:
                    try:
                        coords = (int(round(float(parts[0]))), int(round(float(parts[1]))))
                    except (ValueError, TypeError):
                        pass

            # Check if already scanned POI
            is_scanned = False
            if key in scanned_poi_keys:
                is_scanned = True
            elif coords and coords in scanned_poi_coords:
                is_scanned = True

            if is_scanned:
                self.log(f"  [DELETE UNSUPPORTED] Key '{key}': Target POI has been successfully scanned")
                removed_count += 1
                continue

            # Check if already surveyed site
            is_surveyed = False
            if key in surveyed_site_ids:
                is_surveyed = True
            elif coords and coords in surveyed_site_coords:
                is_surveyed = True

            if is_surveyed:
                self.log(f"  [DELETE UNSUPPORTED] Key '{key}': Target site has been fully surveyed")
                removed_count += 1
                continue

            # Ensure canonical key format
            canonical_key = key
            if ":" in key and not key.startswith("poi_") and coords:
                canonical_key = f"poi_{coords[0]}_{coords[1]}"

            clean_unsupported[canonical_key] = entry

        self.stats["unsupported_removed"] += removed_count
        self.log(f"  Result: {len(clean_unsupported)} unsupported targets retained, {removed_count} obsolete entries purged.")

        if not self.dry_run:
            self.archive.set(SURVEY_UNSUPPORTED_KEY, clean_unsupported)
            self.archive.set(LEGACY_ROVER_UNSUPPORTED_KEY, clean_unsupported)
            # Clear legacy pioneer key if it had entries
            if legacy_pioneer and isinstance(legacy_pioneer, dict):
                self.archive.set(LEGACY_PIONEER_SONAR_KEY, {})
            if self.archive.has(LEGACY_ROVER_UNSUPPORTED_KEY):
                self.archive.delete(LEGACY_ROVER_UNSUPPORTED_KEY)
            if self.archive.has(LEGACY_PIONEER_SONAR_KEY):
                self.archive.delete(LEGACY_PIONEER_SONAR_KEY)

    def clean_survey_spiral(self):
        """
        Validates survey.spiral and pioneer.survey_spiral.
        Deduplicates waypoints by index and coordinate, ensuring proper ordering and structure.
        """
        self.log("\n--- Checking Survey Spiral Data ---")
        spiral_shared = self.archive.get(SURVEY_SPIRAL_KEY, None)
        spiral_legacy = self.archive.get(LEGACY_PIONEER_SPIRAL_KEY, None)

        spiral_data = spiral_shared or spiral_legacy
        if not spiral_data:
            self.log("  No survey spiral data stored.")
            return

        if not isinstance(spiral_data, dict):
            self.log("  [REPAIR] Spiral data is malformed (not a dict). Resetting.")
            if not self.dry_run:
                self.archive.set(SURVEY_SPIRAL_KEY, {"waypoints": [], "next_index": 0})
                self.archive.set(LEGACY_PIONEER_SPIRAL_KEY, {"waypoints": [], "next_index": 0})
            return

        waypoints = spiral_data.get("waypoints", [])
        if not isinstance(waypoints, list):
            waypoints = []

        seen_indices = set()
        seen_coords = set()
        clean_waypoints = []
        cleaned_count = 0

        for wp in waypoints:
            if not isinstance(wp, dict) or "x" not in wp or "y" not in wp:
                cleaned_count += 1
                continue
            idx = wp.get("index")
            try:
                x = round(float(wp["x"]), 1)
                y = round(float(wp["y"]), 1)
            except (ValueError, TypeError):
                cleaned_count += 1
                continue

            coord_pair = (x, y)
            if idx is not None and idx in seen_indices:
                cleaned_count += 1
                continue
            if coord_pair in seen_coords:
                cleaned_count += 1
                continue

            if idx is not None:
                seen_indices.add(idx)
            seen_coords.add(coord_pair)
            clean_waypoints.append(wp)

        # Sort waypoints by index if present
        clean_waypoints.sort(key=lambda w: w.get("index", 0))

        # Check next_index
        next_idx = spiral_data.get("next_index")
        if next_idx is None or not isinstance(next_idx, int) or next_idx < len(clean_waypoints):
            next_idx = len(clean_waypoints)

        self.stats["waypoints_cleaned"] += cleaned_count
        self.log(f"  Result: {len(clean_waypoints)} valid waypoints ({cleaned_count} duplicates/corrupted removed), next_index={next_idx}.")

        if not self.dry_run and (cleaned_count > 0 or spiral_shared != spiral_legacy or self.archive.has(LEGACY_PIONEER_SPIRAL_KEY)):
            cleaned_payload = {
                "waypoints": clean_waypoints,
                "next_index": next_idx,
                "last_completed": clean_waypoints[-1] if clean_waypoints else None,
                "updated_by": spiral_data.get("updated_by", "archive_cleaner")
            }
            self.archive.set(SURVEY_SPIRAL_KEY, cleaned_payload)
            self.archive.set(LEGACY_PIONEER_SPIRAL_KEY, cleaned_payload)
            if self.archive.has(LEGACY_PIONEER_SPIRAL_KEY):
                self.archive.delete(LEGACY_PIONEER_SPIRAL_KEY)

    def clean_telemetry(self, active_vehicles):
        """
        Validates telemetry keys (fleet.status.* and rover.status.*).
        Removes entries for vehicles that no longer exist or entries that are empty/corrupted.
        """
        self.log("\n--- Checking Vehicle Fleet Telemetry ---")
        status_keys = self.archive.keys("fleet.status.") + self.archive.keys("rover.status.")
        telemetry_removed = 0

        for k in set(status_keys):
            val = self.archive.get(k)
            vehicle_name = k.split(".")[-1]

            is_obsolete = False
            if active_vehicles and vehicle_name not in active_vehicles:
                self.log(f"  [DELETE TELEMETRY] Key '{k}': Vehicle '{vehicle_name}' is not in active fleet")
                is_obsolete = True
            elif not isinstance(val, dict) or not val:
                self.log(f"  [DELETE TELEMETRY] Key '{k}': Malformed or empty telemetry data")
                is_obsolete = True

            if is_obsolete:
                telemetry_removed += 1
                if not self.dry_run:
                    self.archive.delete(k)

        self.stats["telemetry_removed"] += telemetry_removed
        self.log(f"  Result: {telemetry_removed} obsolete telemetry entries purged.")

    def clean_calibration(self):
        """
        Validates energy calibration parameters (wh_per_meter).
        Ensures numeric values within reasonable vehicle bounds (0.02 - 0.35 Wh/m).
        """
        self.log("\n--- Checking Wh/m Calibration Parameters ---")
        all_keys = self.archive.keys()
        calib_keys = [k for k in all_keys if k.endswith(".wh_per_meter") or k == "wh_per_meter"]
        calib_repaired = 0

        for k in calib_keys:
            val = self.archive.get(k)
            if val is None or not isinstance(val, (int, float)) or val < 0.02 or val > 0.35:
                self.log(f"  [REPAIR CALIBRATION] Key '{k}': Invalid Wh/m value ({val}). Resetting to default 0.08.")
                calib_repaired += 1
                if not self.dry_run:
                    self.archive.set(k, 0.08)

        self.stats["calibration_repaired"] += calib_repaired
        self.log(f"  Result: {calib_repaired} calibration entries repaired.")

    def clean_power_and_heat(self):
        """
        Validates terraforming parameters:
        - heat.optimal_setpoints
        - power.night_duration, power.sunset_hour, power.night_wh, power.last_night_wh
        """
        self.log("\n--- Checking Power & Heating Terraforming State ---")
        heat_key = "heat.optimal_setpoints"
        if self.archive.has(heat_key):
            heat_val = self.archive.get(heat_key)
            if not isinstance(heat_val, dict):
                self.log(f"  [REPAIR] Key '{heat_key}' is not a dict. Deleting corrupted entry.")
                self.stats["corrupted_keys_deleted"] += 1
                if not self.dry_run:
                    self.archive.delete(heat_key)

        num_keys = {
            "power.sunset_hour": (0.0, 24.0),
            "power.night_duration": (0.1, 24.0),
            "power.night_wh": (0.0, 1000000.0),
            "power.last_night_wh": (0.0, 1000000.0),
        }
        for k, (min_v, max_v) in num_keys.items():
            if self.archive.has(k):
                v = self.archive.get(k)
                if not isinstance(v, (int, float)) or v < min_v or v > max_v:
                    self.log(f"  [REPAIR] Key '{k}' invalid value {v}. Deleting.")
                    self.stats["corrupted_keys_deleted"] += 1
                    if not self.dry_run:
                        self.archive.delete(k)

    def clean_logistics_and_bio(self):
        """
        Validates:
        - pioneer.transport.route
        - fabricator.stock_targets
        - bio.completed_orders
        - bio.fragment_recipes
        """
        self.log("\n--- Checking Logistics & Bio State ---")
        route_key = "pioneer.transport.route"
        if self.archive.has(route_key):
            route = self.archive.get(route_key)
            if route and not isinstance(route, dict):
                self.log(f"  [REPAIR] Key '{route_key}' is malformed. Deleting.")
                self.stats["corrupted_keys_deleted"] += 1
                if not self.dry_run:
                    self.archive.delete(route_key)

        stock_key = "fabricator.stock_targets"
        if self.archive.has(stock_key):
            targets = self.archive.get(stock_key)
            if not isinstance(targets, dict):
                self.log(f"  [REPAIR] Key '{stock_key}' is not a dict. Deleting.")
                self.stats["corrupted_keys_deleted"] += 1
                if not self.dry_run:
                    self.archive.delete(stock_key)

        bio_orders_key = "bio.completed_orders"
        if self.archive.has(bio_orders_key):
            orders = self.archive.get(bio_orders_key)
            if isinstance(orders, list):
                unique_orders = []
                for o in orders:
                    if isinstance(o, str) and o not in unique_orders:
                        unique_orders.append(o)
                if len(unique_orders) != len(orders):
                    self.log(f"  [REPAIR] Key '{bio_orders_key}' contained duplicate orders. Cleaned.")
                    if not self.dry_run:
                        self.archive.set(bio_orders_key, unique_orders)
            elif orders is not None:
                self.log(f"  [REPAIR] Key '{bio_orders_key}' is not a list. Deleting.")
                self.stats["corrupted_keys_deleted"] += 1
                if not self.dry_run:
                    self.archive.delete(bio_orders_key)

    def clean_corrupted_or_empty_keys(self):
        """
        Scans all keys in the archive for None or corrupted empty payloads.
        """
        self.log("\n--- Checking for Corrupted or Orphaned Keys ---")
        all_keys = self.archive.keys()
        self.stats["keys_scanned"] = len(all_keys)

        for k in all_keys:
            try:
                if self.archive.has(k):
                    val = self.archive.get(k)
                    if val is None:
                        self.log(f"  [DELETE] Key '{k}' holds None. Removing.")
                        self.stats["corrupted_keys_deleted"] += 1
                        if not self.dry_run:
                            self.archive.delete(k)
            except Exception as e:
                self.log(f"  [ERROR] Failed inspecting key '{k}': {e}")
                self.stats["errors"] += 1

    def run(self):
        """Executes full archive validation and cleaning workflow."""
        mode_str = "[DRY-RUN INSPECTION]" if self.dry_run else "[LIVE COMMIT]"
        self.log("=" * 60)
        self.log(f" DATA ARCHIVE VALIDATOR & CLEANER {mode_str}")
        self.log("=" * 60)

        if not self.is_available():
            self.log("[CRITICAL] Data Archive (notebook) component is unavailable or locked!")
            return self.stats

        current_tick = self.get_current_tick()
        scanned_poi_keys, scanned_poi_coords = self.get_scanned_pois()
        surveyed_site_ids, surveyed_site_coords = self.get_surveyed_sites()
        active_vehicles = self.get_active_vehicle_names()

        self.log("Environment Context:")
        self.log(f"  - Current Tick: {current_tick}")
        self.log(f"  - Known Scanned POIs: {len(scanned_poi_coords)}")
        self.log(f"  - Known Surveyed Sites: {len(surveyed_site_ids)}")
        self.log(f"  - Active Fleet Vehicles: {list(active_vehicles) if active_vehicles else 'None detected'}")

        # Run cleanup stages
        self.clean_claims(current_tick, scanned_poi_keys, scanned_poi_coords, surveyed_site_ids, surveyed_site_coords)
        self.clean_unsupported_targets(scanned_poi_keys, scanned_poi_coords, surveyed_site_ids, surveyed_site_coords)
        self.clean_survey_spiral()
        self.clean_telemetry(active_vehicles)
        self.clean_calibration()
        self.clean_power_and_heat()
        self.clean_logistics_and_bio()
        self.clean_corrupted_or_empty_keys()

        self.log("\n" + "=" * 60)
        self.log(f" ARCHIVE VALIDATION SUMMARY {mode_str}")
        self.log("=" * 60)
        for k, v in self.stats.items():
            self.log(f"  {k.replace('_', ' ').capitalize():<30}: {v}")
        self.log("=" * 60 + "\n")

        return self.stats
