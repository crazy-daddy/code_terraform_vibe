# Archive Cleaner & Validator Library
# Validates Data Archive ("notebook") entries, repairs corrupted data,
# cleans stale claims, removes obsolete blacklist/unsupported entries,
# deduplicates survey waypoints, and prunes stale telemetry.

from archive import archive
from tree_console import TreeConsole
from fleet_status import FLEET_STATUS_KEY, LEGACY_FLEET_STATUS_PREFIXES
from fluid_routing import discover_network_buildings

# Stale claim duration (1 simulation hour = 36000 ticks at 10 ticks/sec)
CLAIM_STALE_TICKS = 36000

# lib/profiling.py is opt-in, ad hoc instrumentation (added/removed per
# debugging session -- see docs/AI_CHEATSHEET.md §1c), not permanent
# telemetry, so an entry whose "last_tick" hasn't advanced in this long
# means whatever script wrote it no longer calls profiling.begin()/end() --
# safe clutter to purge rather than something actively tracking state.
# 10 simulation minutes at 10 ticks/sec: comfortably longer than any
# poll_interval in the codebase, short enough not to leave dead entries
# sitting in the archive's shared 512-entry cap for long after a script
# stops profiling itself.
PROFILING_STALE_TICKS = 6000

# Canonical & Legacy Archive Keys
SURVEY_CLAIMS_KEY = "survey.claims"
LEGACY_ROVER_CLAIMS_KEY = "rover.claims"

SURVEY_UNSUPPORTED_KEY = "survey.unsupported_targets"
LEGACY_ROVER_UNSUPPORTED_KEY = "rover.unsupported_targets"
LEGACY_PIONEER_SONAR_KEY = "pioneer.sonar_retries"

SURVEY_SPIRAL_KEY = "survey.spiral"
LEGACY_PIONEER_SPIRAL_KEY = "pioneer.survey_spiral"

# Old one-key-per-vehicle recall flag (lib/vehicle_claims.py's now-retired
# vehicle_recall_key()), superseded by the single consolidated RECALL_KEY dict.
LEGACY_RECALL_KEY_PREFIX = "vehicle.recall:"
RECALL_KEY = "vehicle.recall"

# Key prefixes of families no script writes or reads any more. Leftovers are
# only deleted here, never by their former writers, so all migration cleanup
# lives in one place. Add a prefix when a key family is retired.
RETIRED_KEY_PREFIXES = (
    "smelter.diag.",  # lib/smelter.py diagnostics, retired 2026-09-23
    # Per-machine status keys, consolidated 2026-09-23 into the shared
    # MACHINE_STATUS_KEYS dicts below. Payloads are rewritten every step(),
    # so nothing needs migrating.
    "drone_depot.status.",
    "essence_liquifier.status.",
    "biomass_mixer.status.",
)

# Shared resumable-mission dicts {name: record} and their pre-consolidation
# per-entity key prefixes (lib/vehicle_claims.py / lib/drone_claims.py).
# Unlike telemetry, a legacy record is real state (a claim is still held for
# it), so it's migrated into the dict, not just deleted.
MISSION_KEYS = {
    "vehicle.mission": "vehicle.mission:",
    "drone.mission": "drone.mission:",
}

# Shared machine-status dicts {building_id: telemetry} -> building type_id(s),
# pruned of buildings no longer found on the outpost network. Literal
# strings, not imports: the Liquifier/Mixer modules live in a later tier.
# Drone Depots span three typeIds, one per size (lib/drone_energy.py).
MACHINE_STATUS_KEYS = {
    "drone_depot.status": ("drone_station", "drone_station_medium", "drone_station_large"),
    "essence_liquifier.status": "essence_liquifier",
    "biomass_mixer.status": "biomass_mixer",
}


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
        self.console = TreeConsole(module="archive_cleaner")
        self.stats = {
            "keys_scanned": 0,
            "claims_checked": 0,
            "claims_removed": 0,
            "unsupported_checked": 0,
            "unsupported_removed": 0,
            "unsupported_migrated": 0,
            "waypoints_cleaned": 0,
            "telemetry_removed": 0,
            "calibration_purged": 0,
            "profiling_checked": 0,
            "profiling_removed": 0,
            "recall_flags_migrated": 0,
            "grid_state_purged": 0,
            "retired_keys_purged": 0,
            "missions_migrated": 0,
            "missions_removed": 0,
            "machine_status_removed": 0,
            "corrupted_keys_deleted": 0,
            "errors": 0
        }

    def log(self, msg):
        self.log_messages.append(msg)
        if self.verbose:
            self.console.print(msg)

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
        self.console.debug(f"get_scanned_pois: resolved {len(scanned_coords)} coords / {len(scanned_keys)} keys")
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
        self.console.debug(f"get_surveyed_sites: resolved {len(surveyed_ids)} ids / {len(surveyed_coords)} coords")
        return surveyed_ids, surveyed_coords

    def get_active_vehicle_names(self):
        """Returns set of known active ground vehicle AND drone names/IDs from fleet.
        Drones come from fleet.drones(), not fleet.vehicles() -- leaving them out made
        clean_telemetry() treat every drone's telemetry as orphaned."""
        vehicles = set()
        fleet = safe_get_component("fleet")
        for source in ("vehicles", "drones"):
            if not (fleet and hasattr(fleet, source)):
                continue
            try:
                for v in getattr(fleet, source)() or []:
                    if hasattr(v, "id"):
                        vehicles.add(str(v.id))
                    if hasattr(v, "name"):
                        vehicles.add(str(v.name))
            except Exception as e:
                self.log(f"[WARN] Failed querying fleet.{source}: {e}")
        self.console.debug(f"get_active_vehicle_names: resolved {len(vehicles)} active vehicle/drone identifiers")
        return vehicles

    def get_active_grid_anchors(self):
        """Returns set of currently active power grid anchor ids (power_control.grids()),
        used to tell a still-live per-grid power.shedded:<anchor>/power.night_wh:<anchor>
        entry apart from one orphaned by two grids joining into one via a new power line."""
        anchors = set()
        power = safe_get_component("power_control")
        if power and hasattr(power, "grids"):
            try:
                for g in power.grids() or []:
                    anchor = getattr(g, "anchor_id", None)
                    if anchor:
                        anchors.add(anchor)
            except Exception as e:
                self.log(f"[WARN] Failed querying power_control.grids: {e}")
        self.console.debug(f"get_active_grid_anchors: resolved {len(anchors)} active grid anchors")
        return anchors

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

            self.console.debug(f"  Claim '{key}' retained: tick_age={current_tick - claim_tick if current_tick > 0 else 'n/a'}, not a scanned POI or surveyed site")
            clean_claims_map[key] = claim

        self.stats["claims_removed"] += claims_removed
        self.log(f"  Result: {len(clean_claims_map)} active claims retained, {claims_removed} obsolete claims purged.")

        if not self.dry_run and (claims_removed > 0 or shared_claims != clean_claims_map or legacy_claims != clean_claims_map):
            self.archive.set(SURVEY_CLAIMS_KEY, clean_claims_map)
            # LEGACY_ROVER_CLAIMS_KEY ("rover.claims") no longer gains new
            # entries -- vehicle_claims.py's claim_target()/refresh_claim()
            # only write SURVEY_CLAIMS_KEY now; cleanup_stale_claims() and
            # release_target_claim() still prune this key so old-save entries
            # can shrink out, same treatment as LEGACY_PIONEER_SONAR_KEY below.
            # Fully retire it once its entries have been folded into the
            # canonical key above.
            if legacy_claims and isinstance(legacy_claims, dict):
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

            if canonical_key != key:
                self.console.debug(f"  Unsupported key '{key}' normalized to canonical form '{canonical_key}'")
            self.console.debug(f"  Unsupported entry '{canonical_key}' retained (reason='{reason}')")
            clean_unsupported[canonical_key] = entry

        self.stats["unsupported_removed"] += removed_count
        self.log(f"  Result: {len(clean_unsupported)} unsupported targets retained, {removed_count} obsolete entries purged.")

        if not self.dry_run:
            self.archive.set(SURVEY_UNSUPPORTED_KEY, clean_unsupported)
            # LEGACY_ROVER_UNSUPPORTED_KEY ("rover.unsupported_targets") and
            # LEGACY_PIONEER_SONAR_KEY ("pioneer.sonar_retries") no longer
            # gain new entries -- vehicle_claims.py's blacklist_target() only
            # writes SURVEY_UNSUPPORTED_KEY now; clear_unsupported_target()'s
            # delete-only updaters still touch both legacy keys to retire
            # entries as they resolve, so each only ever shrinks. Fully
            # retire each once its entries have been folded into the
            # canonical key above.
            if legacy_rover and isinstance(legacy_rover, dict):
                if self.archive.has(LEGACY_ROVER_UNSUPPORTED_KEY):
                    self.archive.delete(LEGACY_ROVER_UNSUPPORTED_KEY)
            if legacy_pioneer and isinstance(legacy_pioneer, dict):
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
                if self.archive.has(LEGACY_PIONEER_SPIRAL_KEY):
                    self.archive.delete(LEGACY_PIONEER_SPIRAL_KEY)
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
                self.console.debug(f"  Waypoint discarded: not a dict or missing x/y ({wp!r})")
                cleaned_count += 1
                continue
            idx = wp.get("index")
            try:
                x = round(float(wp["x"]), 1)
                y = round(float(wp["y"]), 1)
            except (ValueError, TypeError):
                self.console.debug(f"  Waypoint index={idx} discarded: non-numeric x/y ({wp.get('x')!r}, {wp.get('y')!r})")
                cleaned_count += 1
                continue

            coord_pair = (x, y)
            if idx is not None and idx in seen_indices:
                self.console.debug(f"  Waypoint index={idx} discarded: duplicate index (already seen)")
                cleaned_count += 1
                continue
            if coord_pair in seen_coords:
                self.console.debug(f"  Waypoint index={idx} discarded: duplicate coordinate {coord_pair} (already seen)")
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
            self.console.debug(f"  next_index invalid/stale (was {next_idx!r}), resetting to waypoint count {len(clean_waypoints)}")
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
            # LEGACY_PIONEER_SPIRAL_KEY ("pioneer.survey_spiral") is fully dead
            # -- lib/vehicle_survey.py only reads/writes SURVEY_SPIRAL_KEY any
            # more, nothing else in the codebase references the legacy name --
            # so there's no reason to keep writing a payload into it. Just
            # retire it outright instead of the old set-then-immediately-
            # delete (which only ever wrote a payload no one would read a
            # moment before deleting it again).
            if self.archive.has(LEGACY_PIONEER_SPIRAL_KEY):
                self.archive.delete(LEGACY_PIONEER_SPIRAL_KEY)

    def clean_telemetry(self, active_vehicles):
        """
        Deletes the pre-consolidation per-entity telemetry keys (fleet.status.<id>,
        rover.status.<id>, drone.status.<id> -- see lib/fleet_status.py), then prunes
        entries of the shared fleet.status dict whose vehicle/drone no longer exists
        or whose payload is empty/malformed. Pruning by existence is skipped when
        the fleet query came back empty, so a failed query never wipes the dict.
        """
        self.log("\n--- Checking Vehicle Fleet Telemetry ---")
        telemetry_removed = 0

        for prefix in LEGACY_FLEET_STATUS_PREFIXES:
            for k in self.archive.keys(prefix):
                self.log(f"  [DELETE TELEMETRY] Legacy per-entity key '{k}' (superseded by '{FLEET_STATUS_KEY}' dict)")
                telemetry_removed += 1
                if not self.dry_run:
                    self.archive.delete(k)

        status = self.archive.get(FLEET_STATUS_KEY, {})
        if not isinstance(status, dict):
            self.log(f"  [DELETE TELEMETRY] Key '{FLEET_STATUS_KEY}': not a dict, resetting")
            telemetry_removed += 1
            if not self.dry_run:
                self.archive.delete(FLEET_STATUS_KEY)
            status = {}

        stale = []
        for name, val in status.items():
            if active_vehicles and name not in active_vehicles:
                self.log(f"  [DELETE TELEMETRY] {FLEET_STATUS_KEY}['{name}']: not in active fleet")
                stale.append(name)
            elif not isinstance(val, dict) or not val:
                self.log(f"  [DELETE TELEMETRY] {FLEET_STATUS_KEY}['{name}']: malformed or empty telemetry data")
                stale.append(name)
            else:
                self.console.debug(f"  Telemetry '{name}' retained: active, payload well-formed")

        if stale and not self.dry_run:
            def updater(current):
                if not isinstance(current, dict):
                    return {}
                for name in stale:
                    current.pop(name, None)
                return current
            self.archive.transaction(FLEET_STATUS_KEY, {}, updater)
        telemetry_removed += len(stale)

        self.stats["telemetry_removed"] += telemetry_removed
        self.log(f"  Result: {telemetry_removed} obsolete telemetry entries purged.")

    def clean_calibration(self):
        """
        Purges obsolete wh_per_meter calibration entries. Travel energy now uses
        the developer-confirmed exact power/speed model (lib/vehicle_energy.py),
        not an empirically-calibrated Wh/meter, so these archive keys are no
        longer read or written by any vehicle script -- just leftover clutter
        from before that change. Two historical key shapes existed: a dot-suffix
        one (e.g. "<vehicle>.wh_per_meter") and an older colon-prefixed one from
        an earlier iteration ("vehicle.wh_per_meter:<vehicle_id>", one key per
        vehicle) -- both purged here.
        """
        self.log("\n--- Purging Obsolete Wh/m Calibration Entries ---")
        all_keys = self.archive.keys()
        calib_keys = [
            k for k in all_keys
            if k.endswith(".wh_per_meter") or k == "wh_per_meter" or k.startswith("vehicle.wh_per_meter:")
        ]
        calib_purged = 0
        self.console.debug(f"Found {len(calib_keys)} legacy Wh/m calibration key(s) to purge")

        for k in calib_keys:
            self.log(f"  [DELETE CALIBRATION] Key '{k}': Obsolete Wh/m calibration entry (no longer used).")
            calib_purged += 1
            if not self.dry_run:
                self.archive.delete(k)

        self.stats["calibration_purged"] += calib_purged
        self.log(f"  Result: {calib_purged} obsolete calibration entries purged.")

    def clean_recall_flags(self):
        """
        Migrates the old one-key-per-vehicle "vehicle.recall:<name>" flags
        (lib/vehicle_claims.py's now-retired vehicle_recall_key()) into the
        single consolidated RECALL_KEY dict, then deletes the legacy keys. The
        Data Archive has a fixed shared key-count cap, so a dedicated top-level
        key per vehicle for one boolean flag doesn't scale with fleet size --
        only actively-recalled vehicles are stored in the dict at all (a
        vehicle absent from it just reads as not-recalled), so consolidating
        costs nothing at rest either.
        """
        self.log("\n--- Migrating Legacy Per-Vehicle Recall Flags ---")
        all_keys = self.archive.keys()
        legacy_keys = [k for k in all_keys if k.startswith(LEGACY_RECALL_KEY_PREFIX)]
        if not legacy_keys:
            self.log("  No legacy per-vehicle recall keys found.")
            return

        consolidated = self.archive.get(RECALL_KEY, {})
        consolidated = dict(consolidated) if isinstance(consolidated, dict) else {}
        migrated = 0

        for k in legacy_keys:
            vehicle_name = k[len(LEGACY_RECALL_KEY_PREFIX):]
            value = self.archive.get(k, False)
            if value:
                consolidated[vehicle_name] = True
                migrated += 1
            self.log(f"  [MIGRATE RECALL] Key '{k}' -> {RECALL_KEY}['{vehicle_name}'] = {bool(value)}")
            if not self.dry_run:
                self.archive.delete(k)

        if not self.dry_run:
            self.archive.set(RECALL_KEY, consolidated)

        self.stats["recall_flags_migrated"] += len(legacy_keys)
        self.log(f"  Result: {len(legacy_keys)} legacy recall key(s) migrated/removed ({migrated} were actively recalled).")

    def clean_retired_keys(self):
        """Deletes every key under RETIRED_KEY_PREFIXES (families no script uses any more)."""
        self.log("\n--- Purging Retired Key Families ---")
        purged = 0
        for prefix in RETIRED_KEY_PREFIXES:
            for k in self.archive.keys(prefix):
                self.log(f"  [DELETE RETIRED] Key '{k}' (retired family '{prefix}*')")
                purged += 1
                if not self.dry_run:
                    self.archive.delete(k)
        self.stats["retired_keys_purged"] += purged
        self.log(f"  Result: {purged} retired key(s) purged.")

    def clean_missions(self, active_vehicles):
        """
        Moves leftover per-entity mission keys (vehicle.mission:<name>,
        drone.mission:<name>) into their shared MISSION_KEYS dict -- never
        overwriting an entry the owner already re-saved -- then deletes the
        legacy key. Also drops dict entries that are malformed, or whose
        vehicle/drone no longer exists (existence check skipped when the
        fleet query came back empty).
        """
        self.log("\n--- Checking Resumable Mission Records ---")
        for key, legacy_prefix in MISSION_KEYS.items():
            missions = self.archive.get(key, {})
            missions = dict(missions) if isinstance(missions, dict) else {}
            changed = False

            for k in self.archive.keys(legacy_prefix):
                name = k[len(legacy_prefix):]
                record = self.archive.get(k, None)
                if isinstance(record, dict) and name not in missions:
                    missions[name] = record
                    changed = True
                    self.stats["missions_migrated"] += 1
                    self.log(f"  [MIGRATE MISSION] Key '{k}' -> {key}['{name}']")
                else:
                    self.log(f"  [DELETE MISSION] Key '{k}': {'superseded by dict entry' if name in missions else 'malformed'}")
                if not self.dry_run:
                    self.archive.delete(k)

            for name in list(missions):
                record = missions[name]
                if not isinstance(record, dict) or not record.get("target_key"):
                    reason = "malformed record"
                elif active_vehicles and name not in active_vehicles:
                    reason = "not in active fleet"
                else:
                    self.console.debug(f"  {key}['{name}'] retained: target '{record.get('target_key')}'")
                    continue
                self.log(f"  [DELETE MISSION] {key}['{name}']: {reason}")
                del missions[name]
                changed = True
                self.stats["missions_removed"] += 1

            # Plain set, not a transaction: this rebuilds the whole dict from
            # legacy keys, and the cleaner is a rare, operator-triggered run.
            if changed and not self.dry_run:
                self.archive.set(key, missions)

        self.log(f"  Result: {self.stats['missions_migrated']} mission(s) migrated, {self.stats['missions_removed']} removed.")

    def clean_machine_status(self):
        """
        Drops MACHINE_STATUS_KEYS dict entries whose building is no longer on
        the outpost network. Skipped per key when discovery finds no building
        of that type at all (not unlocked yet, or discovery failed), so a
        failed walk never wipes the dict.
        """
        self.log("\n--- Checking Machine Status Dicts ---")
        removed = 0
        for key, type_id in MACHINE_STATUS_KEYS.items():
            status = self.archive.get(key, None)
            if status is None:
                continue
            if not isinstance(status, dict):
                self.log(f"  [DELETE STATUS] Key '{key}': not a dict, resetting")
                removed += 1
                if not self.dry_run:
                    self.archive.delete(key)
                continue
            type_ids = type_id if isinstance(type_id, tuple) else (type_id,)
            try:
                live = {str(b) for t_id in type_ids for b, _ in discover_network_buildings(t_id, resolve=False)}
            except Exception as e:
                self.log(f"  [WARN] Discovering '{type_id}' failed: {e}; skipping '{key}'.")
                continue
            if not live:
                self.console.debug(f"  No '{type_id}' found on network; not pruning '{key}'.")
                continue
            stale = [bid for bid in status if bid not in live]
            for bid in stale:
                self.log(f"  [DELETE STATUS] {key}['{bid}']: building no longer on network")
            if stale and not self.dry_run:
                def updater(current, stale=stale):
                    if not isinstance(current, dict):
                        return {}
                    for bid in stale:
                        current.pop(bid, None)
                    return current
                self.archive.transaction(key, {}, updater)
            removed += len(stale)
        self.stats["machine_status_removed"] += removed
        self.log(f"  Result: {removed} stale machine status entr{'y' if removed == 1 else 'ies'} purged.")

    def clean_power_grid_state(self, active_grid_anchors):
        """
        Purges per-grid power.shedded:<anchor>/power.night_wh:<anchor> entries
        whose grid anchor no longer exists -- e.g. two independent grids joined
        via a new power line and elected a single Master, orphaning the old
        per-grid keys forever otherwise. Skips entirely if grid discovery itself
        failed (empty active_grid_anchors), same caution as clean_telemetry()'s
        active_vehicles check -- never purge everything just because detection
        came back empty. Also retires three now-obsolete keys outright:
        power.night_duration (replaced by the fixed day-cycle schedule -- see
        lib/power.py's NIGHT_DURATION_HOURS), power.last_night_wh (a dead key
        from before the power.night_wh:<anchor> per-grid keying scheme), and
        power.shedded_machines (an exact duplicate of power.shedded that nothing
        ever actually read) -- none of these are written by current code any more.
        """
        self.log("\n--- Checking Per-Grid Power State ---")
        purged = 0

        if active_grid_anchors:
            all_keys = self.archive.keys()
            for prefix in ("power.shedded:", "power.night_wh:", "power.daily:", "power.daily_hist:"):
                for k in all_keys:
                    if not k.startswith(prefix):
                        continue
                    anchor = k[len(prefix):]
                    if anchor in active_grid_anchors:
                        self.console.debug(f"  Grid state key '{k}' retained: anchor '{anchor}' still active")
                        continue
                    self.log(f"  [DELETE GRID STATE] Key '{k}': grid anchor '{anchor}' no longer active (grids likely joined).")
                    purged += 1
                    if not self.dry_run:
                        self.archive.delete(k)
        else:
            self.log("  Skipped per-grid anchor check: could not determine active grids this run.")

        for k in ("power.night_duration", "power.last_night_wh", "power.shedded_machines"):
            if self.archive.has(k):
                self.log(f"  [DELETE RETIRED] Key '{k}': retired mechanic, no longer read or written.")
                purged += 1
                if not self.dry_run:
                    self.archive.delete(k)

        self.stats["grid_state_purged"] += purged
        self.log(f"  Result: {purged} obsolete per-grid/retired power entries purged.")

    def clean_profiling(self, current_tick):
        """
        Purges lib/profiling.py entries ("profiling.<name>") nobody is
        actively writing to any more. Unlike claims/telemetry, there's no
        live game state (fleet, outpost buildings) to cross-check a script
        name against -- profiling is opt-in instrumentation a script can
        stop calling at any time while still existing -- so staleness is the
        only signal available: each entry carries "last_tick" (see
        lib/profiling.py's _record()), and one that hasn't moved in
        PROFILING_STALE_TICKS means that script no longer calls
        profiling.begin()/end(). A legacy entry from before the {"history",
        "last_tick"} shape (a bare list) has no way to check staleness at
        all, so it's always purged -- one-time migration cleanup.
        """
        self.log("\n--- Checking Profiling Entries ---")
        profiling_keys = self.archive.keys("profiling.") if hasattr(self.archive, "keys") else []
        removed = 0

        for k in profiling_keys:
            self.stats["profiling_checked"] += 1
            entry = self.archive.get(k)

            if not isinstance(entry, dict) or "history" not in entry or "last_tick" not in entry:
                self.log(f"  [DELETE PROFILING] Key '{k}': legacy/malformed format (no last_tick to check staleness).")
                removed += 1
                if not self.dry_run:
                    self.archive.delete(k)
                continue

            last_tick = entry.get("last_tick")
            if current_tick > 0 and isinstance(last_tick, (int, float)):
                age = current_tick - last_tick
                if age > PROFILING_STALE_TICKS:
                    self.log(f"  [DELETE PROFILING] Key '{k}': no update in {age} ticks (> {PROFILING_STALE_TICKS}) -- script no longer profiling itself.")
                    removed += 1
                    if not self.dry_run:
                        self.archive.delete(k)

        self.stats["profiling_removed"] += removed
        self.log(f"  Result: {len(profiling_keys) - removed} active profiling entries retained, {removed} stale/legacy entries purged.")

    def clean_power_and_heat(self):
        """
        Validates terraforming parameters:
        - heat.optimal_setpoints
        - power.sunset_hour, power.night_wh
        (power.night_duration and power.last_night_wh are retired outright by
        clean_power_grid_state() instead of range-checked here.)
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
            else:
                self.console.debug(f"  Key '{heat_key}' valid (dict, {len(heat_val)} entries)")

        num_keys = {
            "power.sunset_hour": (0.0, 24.0),
            "power.night_wh": (0.0, 1000000.0),
        }
        for k, (min_v, max_v) in num_keys.items():
            if self.archive.has(k):
                v = self.archive.get(k)
                if not isinstance(v, (int, float)) or v < min_v or v > max_v:
                    self.log(f"  [REPAIR] Key '{k}' invalid value {v}. Deleting.")
                    self.stats["corrupted_keys_deleted"] += 1
                    if not self.dry_run:
                        self.archive.delete(k)
                else:
                    self.console.debug(f"  Key '{k}'={v} within valid range [{min_v}, {max_v}]")

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
            elif route:
                self.console.debug(f"  Key '{route_key}' valid (dict, {len(route)} entries)")

        stock_key = "fabricator.stock_targets"
        if self.archive.has(stock_key):
            targets = self.archive.get(stock_key)
            if not isinstance(targets, dict):
                self.log(f"  [REPAIR] Key '{stock_key}' is not a dict. Deleting.")
                self.stats["corrupted_keys_deleted"] += 1
                if not self.dry_run:
                    self.archive.delete(stock_key)
            else:
                self.console.debug(f"  Key '{stock_key}' valid (dict, {len(targets)} entries)")

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
                else:
                    self.console.debug(f"  Key '{bio_orders_key}' valid ({len(orders)} orders, no duplicates)")
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

        self.console.debug(f"clean_corrupted_or_empty_keys: scanned {len(all_keys)} keys, {self.stats['corrupted_keys_deleted']} corrupted-so-far, {self.stats['errors']} inspection errors")

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
        active_grid_anchors = self.get_active_grid_anchors()

        self.log("Environment Context:")
        self.log(f"  - Current Tick: {current_tick}")
        self.log(f"  - Known Scanned POIs: {len(scanned_poi_coords)}")
        self.log(f"  - Known Surveyed Sites: {len(surveyed_site_ids)}")
        self.log(f"  - Active Fleet Vehicles: {list(active_vehicles) if active_vehicles else 'None detected'}")
        self.log(f"  - Active Power Grids: {list(active_grid_anchors) if active_grid_anchors else 'None detected'}")

        # Run cleanup stages
        self.clean_claims(current_tick, scanned_poi_keys, scanned_poi_coords, surveyed_site_ids, surveyed_site_coords)
        self.clean_unsupported_targets(scanned_poi_keys, scanned_poi_coords, surveyed_site_ids, surveyed_site_coords)
        self.clean_survey_spiral()
        self.clean_telemetry(active_vehicles)
        self.clean_calibration()
        self.clean_recall_flags()
        self.clean_retired_keys()
        self.clean_missions(active_vehicles)
        self.clean_machine_status()
        self.clean_profiling(current_tick)
        self.clean_power_and_heat()
        self.clean_power_grid_state(active_grid_anchors)
        self.clean_logistics_and_bio()
        self.clean_corrupted_or_empty_keys()

        self.log("\n" + "=" * 60)
        self.log(f" ARCHIVE VALIDATION SUMMARY {mode_str}")
        self.log("=" * 60)
        for k, v in self.stats.items():
            self.log(f"  {k.replace('_', ' ').capitalize():<30}: {v}")
        self.log("=" * 60 + "\n")

        return self.stats
