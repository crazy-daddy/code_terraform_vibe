# Archive Cleaner & Validator Library
# Validates Data Archive ("notebook") entries, repairs corrupted data,
# cleans stale claims, removes obsolete blacklist/unsupported entries,
# deduplicates survey waypoints, and prunes stale telemetry.

from archive import STATUS_STALE_TICKS, archive
from components import component
from fleet_claims_common import CLAIM_STALE_TICKS, LEGACY_ROVER_CLAIMS_KEY, SURVEY_CLAIMS_KEY
from fleet_status import FLEET_STATUS_KEY, LEGACY_FLEET_STATUS_PREFIXES
from fluid_routing import discover_network_buildings
from game_clock import is_fresh, now_tick
from item_tiers import DEPOT_TYPE_TIERS
from outpost_mining import MINING_REACH_KEY
from swallow import swallowed
from tree_console import TreeConsole
from unsupported_markers import LEGACY_PIONEER_SONAR_KEY, LEGACY_ROVER_UNSUPPORTED_KEY, RESOURCE_MARKER_PREFIX, SURVEY_UNSUPPORTED_KEY, clear_resource_markers, key_tile, merge_unsupported
from vehicle_survey import LEGACY_PIONEER_SPIRAL_KEY, SURVEY_SPIRAL_KEY

# lib/profiling.py is opt-in, ad hoc instrumentation (added/removed per
# debugging session -- see docs/AI_CHEATSHEET.md §1c), not permanent
# telemetry, so an entry whose "last_tick" hasn't advanced in this long
# means whatever script wrote it no longer calls profiling.begin()/end() --
# safe clutter to purge rather than something actively tracking state.
# 10 simulation minutes at 10 ticks/sec: comfortably longer than any
# poll_interval in the codebase, short enough not to leave dead entries
# sitting in the archive's shared 2,048-entry cap for long after a script
# stops profiling itself.
PROFILING_STALE_TICKS = 6000

# Canonical & Legacy Archive Keys (claim, blacklist and spiral keys: imported
# from their owners above)

# Old one-key-per-vehicle recall flag (lib/vehicle_claims.py's now-retired
# vehicle_recall_key()), superseded by the single consolidated RECALL_KEY dict.
LEGACY_RECALL_KEY_PREFIX = "vehicle.recall:"
RECALL_KEY = "vehicle.recall"

# Key prefixes of families no script writes or reads any more. Leftovers are
# only deleted here, never by their former writers, so all migration cleanup
# lives in one place. Add a prefix when a key family is retired.
RETIRED_KEY_PREFIXES = (
    "production.site_targets",  # per-site shared targets, replaced by the demand record production.demand (lib/production_demand_record.py)
    "smelter.diag.",  # lib/smelter.py diagnostics (retired)
    "outposts.ore_stock_targets",  # per-outpost ore targets, replaced by one mining.ore_stock_targets dict
    "fabricator.stock_targets",  # home segment floor, replaced by the construction stock need levels (site_supply.construction_stock)
    "drone.loadouts",  # per-drone module slot record, replaced by drone.modules()
    "outposts.known_ids",  # outpost id diff for the retired resource-marker assignment sweep
    "drill.positions",  # recorded drill positions, replaced by MiningSite.drill_id() (lib/drill_sites.py)
    "fabricator.upgrade_orders",  # replaced by the prioritized orders book fabricator.orders (lib/production_orders.py)
    "fabricator.backlog_orders",  # same
    "smelter.key_ahead",  # key-unlock look-ahead ingots, now an orders-book entry at the ORDER_AHEAD band
    "mining.dock_ore_need",  # dock-owed ore, now a site-supply ore request at the order's prio
    # Per-machine status keys consolidated into the shared MACHINE_STATUS_KEYS
    # dicts below. Payloads are rewritten every step(), so nothing needs migrating.
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
# Drone Depots span three typeIds, one per size (lib/item_tiers.py).
MACHINE_STATUS_KEYS = {
    "drone_depot.status": tuple(DEPOT_TYPE_TIERS),
    "essence_liquifier.status": "essence_liquifier",
    "biomass_mixer.status": "biomass_mixer",
    "waste_sink.status": "garbage_disposal",  # Waste Processor typeId (decompiled)
    "wildlife.status": "habitat",
    "wildlife.feed": "feed_maker",
}

# Per-machine status dicts written through archive.publish_status(). Each publish
# drops other entries older than STATUS_STALE_TICKS, but nothing runs that once
# the last machine of a kind is gone, so the cleaner applies the same rule.
# Covers field machines and drills too, which the network listing above can't see.
# tests/test_archive_cleaner_status.py checks every publish_status() key is listed.
STATUS_TICK_KEYS = (
    "biomass_mixer.status",
    "drill.status",
    "essence_liquifier.status",
    "plant.automators",
    "plant.providers",
    "plant.status",
    "plant.terraformer",
    "refiner.status",
    "seed_maker.status",
    "waste_sink.status",
    "wildlife.feed",
    "wildlife.status",
)

# Shared dicts {building_id: ...} spanning many building types, pruned of ids that are no
# longer a building. Literal strings: script_parking / fluid_routing live in this tier, but
# the dicts are plain data and the cleaner must not depend on their owners.
BUILDING_ID_KEYS = (
    "script.parked",  # lib/parking_client.py PARKED_KEY
    "script.park_requests",  # PARK_REQUESTS_KEY
    "script.park_holds",  # HOLDS_KEY
    "script.stray_dark",  # STRAY_KEY
    "script.manual_off",  # MANUAL_OFF_KEY
    "script.restart_requests",  # lib/script_restart.py RESTART_REQUESTS_KEY
    "machine.retired",  # lib/retired_machines.py RETIRED_KEY
    "fluid_routing.tank_assignments",
    "storage.retiring",  # lib/storage.py RETIRING_STORES_KEY
)


def _canonical_poi_key(key, tile):
    """Ensure canonical key format: a legacy 'X:Y' key with a tile becomes
    'poi_X_Y'; any other key stays as it is."""
    if ":" in key and not key.startswith("poi_") and tile:
        return f"poi_{tile[0]}_{tile[1]}"
    return key


def _is_resolved(key, tile, done_keys, done_tiles):
    """True when a target's key, or its integer tile (None: no coords), is
    already among the scanned POIs or surveyed sites given."""
    return key in done_keys or (tile is not None and tile in done_tiles)


def _claim_tile(coords):
    """Integer tile of a claim's "coords"; None when missing or non-numeric."""
    if not (coords and isinstance(coords, (list, tuple)) and len(coords) >= 2):
        return None
    try:
        return int(round(float(coords[0]))), int(round(float(coords[1])))
    except (ValueError, TypeError):
        return None


def _claim_age_reason(claim_tick, current_tick):
    """Why a claim's tick rules it out (missing, stale, from the future), or None."""
    if claim_tick is None or not isinstance(claim_tick, (int, float)):
        return f"Missing or invalid tick timestamp ({claim_tick})"
    if current_tick > 0:
        tick_age = current_tick - claim_tick
        if tick_age > CLAIM_STALE_TICKS:
            return f"Stale claim (age: {tick_age} ticks > {CLAIM_STALE_TICKS})"
        elif tick_age < -1000:
            return f"Future tick timestamp anomaly ({claim_tick} vs curr {current_tick})"
    return None


def _claim_reject_reason(key, claim, current_tick, done):
    """Why ArchiveCleaner.clean_claims() drops a claim, or None to keep it.
    done: (scanned_poi_keys, scanned_poi_coords, surveyed_site_ids,
    surveyed_site_coords)."""
    if not isinstance(claim, dict):
        return "Corrupted payload (not a dict)"

    # 1. Check staleness
    reason = _claim_age_reason(claim.get("tick"), current_tick)
    if reason:
        return reason

    # A mine claim sits on a surveyed site (often at its POI's
    # coords) by definition, so rules 2 and 3 below, meant for
    # scan/survey claims, would purge every live mining trip.
    if claim.get("type") == "mine":
        return None

    # 2. Check if already scanned POI
    scanned_poi_keys, scanned_poi_coords, surveyed_site_ids, surveyed_site_coords = done
    if key in scanned_poi_keys:
        return "Target POI is already scanned"
    tile = _claim_tile(claim.get("coords"))
    if tile is not None and (tile in scanned_poi_coords or f"poi_{tile[0]}_{tile[1]}" in scanned_poi_keys):
        return "Target POI is already scanned"

    # 3. Check if already surveyed site
    if _is_resolved(key, tile, surveyed_site_ids, surveyed_site_coords):
        return "Target site is already surveyed"
    return None


def _unique_orders(orders):
    """String entries of `orders` without duplicates, first occurrence kept in order."""
    unique_orders = []
    seen = set()
    for o in orders:
        if isinstance(o, str) and o not in seen:
            seen.add(o)
            unique_orders.append(o)
    return unique_orders


class _SilentConsole:
    """Console stand-in that drops every line, for a non-verbose cleaner's info blocks."""

    def print(self, *args, **kwargs):
        pass


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
        self._log = self.console if verbose else TreeConsole(console=_SilentConsole(), module="archive_cleaner")
        self.stats = {
            "keys_scanned": 0,
            "claims_checked": 0,
            "claims_removed": 0,
            "unsupported_checked": 0,
            "unsupported_removed": 0,
            "unsupported_migrated": 0,
            "waypoints_cleaned": 0,
            "telemetry_removed": 0,
            "mining_reach_removed": 0,
            "resource_markers_removed": 0,
            "calibration_purged": 0,
            "profiling_checked": 0,
            "profiling_removed": 0,
            "recall_flags_migrated": 0,
            "grid_state_purged": 0,
            "retired_keys_purged": 0,
            "missions_migrated": 0,
            "missions_removed": 0,
            "machine_status_removed": 0,
            "building_entries_removed": 0,
            "corrupted_keys_deleted": 0,
            "errors": 0,
        }

    def log(self, msg):
        self.log_messages.append(msg)
        if self.verbose:
            self.console.print(msg)

    def _stage(self, title, stage, *args):
        """Runs one cleanup stage inside a log block; the stage returns its outcome line."""
        self.log_messages.append(title)
        self._log.start(title)
        outcome = stage(*args)
        self.log_messages.append(outcome)
        self._log.end(outcome)

    def _reset_if_not_dict(self, key, value, tag):
        """True when `value` (read from `key`) is not a dict; logs it under
        `tag` and deletes the key unless this is a dry run."""
        if isinstance(value, dict):
            return False
        self.log(f"  [{tag}] Key '{key}': not a dict, resetting")
        if not self.dry_run:
            self.archive.delete(key)
        return True

    def _prune_dict_key(self, key, stale, still_stale=None):
        """Pops the `stale` entries from dict `key` in one transaction (not in
        a dry run). With `still_stale(entry)`, pops only those it still
        matches inside the transaction. Returns len(stale)."""
        if stale and not self.dry_run:
            if still_stale is None:
                self.archive.pop_entries(key, stale)
            else:

                def pop_still_stale(current):
                    for name in stale:
                        if still_stale(current.get(name)):
                            current.pop(name, None)

                self.archive.mutate(key, pop_still_stale)
        return len(stale)

    def _prune_fleet_dict(self, key, active_vehicles, tag):
        """
        Drops entries of the fleet-keyed dict `key` whose vehicle is not in
        `active_vehicles` (skipped when that set is empty, so a failed fleet
        query never wipes the dict) or whose payload is empty/malformed. `tag`
        is the log tag ("DELETE <WHAT>"). A non-dict key is reset. Returns the
        count removed.
        """
        what = tag.split(" ", 1)[1].lower()
        removed = 0
        entries = self.archive.get(key, {})
        if self._reset_if_not_dict(key, entries, tag):
            removed += 1
            entries = {}
        stale = []
        for name, val in entries.items():
            if active_vehicles and name not in active_vehicles:
                self.log(f"  [{tag}] {key}['{name}']: not in active fleet")
                stale.append(name)
            elif not isinstance(val, dict) or not val:
                self.log(f"  [{tag}] {key}['{name}']: malformed or empty {what.split()[-1]} data")
                stale.append(name)
            else:
                self.console.debug(f"  {what.capitalize()} '{name}' retained: active, payload well-formed")
        return removed + self._prune_dict_key(key, stale)

    def _retire_legacy_key(self, key):
        """Deletes a legacy key whose content the caller has folded into its canonical key."""
        if self.archive.has(key):
            self.archive.delete(key)

    def is_available(self):
        return self.archive is not None and getattr(self.archive, "available", False)

    def get_current_tick(self):
        return now_tick()

    def get_scanned_pois(self):
        """Returns set of coordinates (x, y) and poi_x_y keys for already-scanned POIs."""
        scanned_keys = set()
        scanned_coords = set()
        nocturna = component("nocturna")
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
        journal = component("journal")
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
        fleet = component("fleet")
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
        power = component("power_control")
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
        shared_claims = self.archive.get(SURVEY_CLAIMS_KEY, {})
        legacy_claims = self.archive.get(LEGACY_ROVER_CLAIMS_KEY, {})

        combined_claims = {}
        if isinstance(legacy_claims, dict):
            combined_claims.update(legacy_claims)
        if isinstance(shared_claims, dict):
            combined_claims.update(shared_claims)

        done = (scanned_poi_keys, scanned_poi_coords, surveyed_site_ids, surveyed_site_coords)
        clean_claims_map = {}
        claims_removed = 0

        for key, claim in combined_claims.items():
            self.stats["claims_checked"] += 1
            reason = _claim_reject_reason(key, claim, current_tick, done)
            if reason:
                self.log(f"  [DELETE CLAIM] Key '{key}': {reason}")
                claims_removed += 1
                continue

            claim_tick = claim.get("tick")
            if claim.get("type") == "mine":
                self.console.debug(f"  Claim '{key}' retained: mine claim, tick_age={current_tick - claim_tick if current_tick > 0 else 'n/a'}")
            else:
                self.console.debug(f"  Claim '{key}' retained: tick_age={current_tick - claim_tick if current_tick > 0 else 'n/a'}, not a scanned POI or surveyed site")
            clean_claims_map[key] = claim

        self.stats["claims_removed"] += claims_removed
        outcome = f"{len(clean_claims_map)} active claims retained, {claims_removed} obsolete claims purged"

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
                self._retire_legacy_key(LEGACY_ROVER_CLAIMS_KEY)
        return outcome

    def clean_unsupported_targets(self, scanned_poi_keys, scanned_poi_coords, surveyed_site_ids, surveyed_site_coords):
        """
        Cleans unsupported/blacklisted targets from survey.unsupported_targets,
        rover.unsupported_targets, and legacy pioneer.sonar_retries.
        - Deletes targets that have now been scanned or surveyed.
        - Normalizes keys into canonical 'poi_x_y' format.
        - Purges transient invalid errors (e.g. out_of_range).
        """
        shared_unsupported = self.archive.get_dict(SURVEY_UNSUPPORTED_KEY)
        legacy_rover = self.archive.get_dict(LEGACY_ROVER_UNSUPPORTED_KEY)
        legacy_pioneer = self.archive.get_dict(LEGACY_PIONEER_SONAR_KEY)

        all_entries, migrated = merge_unsupported(shared_unsupported, legacy_rover, legacy_pioneer)
        self.stats["unsupported_migrated"] += migrated
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
            coords = key_tile(key)

            # Check if already scanned POI
            if _is_resolved(key, coords, scanned_poi_keys, scanned_poi_coords):
                self.log(f"  [DELETE UNSUPPORTED] Key '{key}': Target POI has been successfully scanned")
                removed_count += 1
                continue

            # Check if already surveyed site
            if _is_resolved(key, coords, surveyed_site_ids, surveyed_site_coords):
                self.log(f"  [DELETE UNSUPPORTED] Key '{key}': Target site has been fully surveyed")
                removed_count += 1
                continue

            canonical_key = _canonical_poi_key(key, coords)
            if canonical_key != key:
                self.console.debug(f"  Unsupported key '{key}' normalized to canonical form '{canonical_key}'")
            self.console.debug(f"  Unsupported entry '{canonical_key}' retained (reason='{reason}')")
            clean_unsupported[canonical_key] = entry

        self.stats["unsupported_removed"] += removed_count
        outcome = f"{len(clean_unsupported)} unsupported targets retained, {removed_count} obsolete entries purged"

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
                self._retire_legacy_key(LEGACY_ROVER_UNSUPPORTED_KEY)
            if legacy_pioneer and isinstance(legacy_pioneer, dict):
                self._retire_legacy_key(LEGACY_PIONEER_SONAR_KEY)
        return outcome

    def clean_survey_spiral(self):
        """
        Validates survey.spiral and pioneer.survey_spiral.
        Deduplicates waypoints by index and coordinate, ensuring proper ordering and structure.
        """
        spiral_shared = self.archive.get(SURVEY_SPIRAL_KEY, None)
        spiral_legacy = self.archive.get(LEGACY_PIONEER_SPIRAL_KEY, None)

        spiral_data = spiral_shared or spiral_legacy
        if not spiral_data:
            return "no survey spiral data stored"

        if not isinstance(spiral_data, dict):
            self.log("  [REPAIR] Spiral data is malformed (not a dict). Resetting.")
            if not self.dry_run:
                self.archive.set(SURVEY_SPIRAL_KEY, {"waypoints": [], "next_index": 0})
                self._retire_legacy_key(LEGACY_PIONEER_SPIRAL_KEY)
            return "malformed spiral data reset"

        waypoints = spiral_data.get("waypoints", [])
        if not isinstance(waypoints, list):
            waypoints = []

        clean_waypoints, cleaned_count = self._dedup_waypoints(waypoints)

        # Sort waypoints by index if present
        clean_waypoints.sort(key=lambda w: w.get("index", 0))

        # Check next_index
        next_idx = spiral_data.get("next_index")
        if next_idx is None or not isinstance(next_idx, int) or next_idx < len(clean_waypoints):
            self.console.debug(f"  next_index invalid/stale (was {next_idx!r}), resetting to waypoint count {len(clean_waypoints)}")
            next_idx = len(clean_waypoints)

        self.stats["waypoints_cleaned"] += cleaned_count
        outcome = f"{len(clean_waypoints)} valid waypoints ({cleaned_count} duplicates/corrupted removed), next_index={next_idx}"

        if not self.dry_run and (cleaned_count > 0 or spiral_shared != spiral_legacy or self.archive.has(LEGACY_PIONEER_SPIRAL_KEY)):
            cleaned_payload = {"waypoints": clean_waypoints, "next_index": next_idx, "last_completed": clean_waypoints[-1] if clean_waypoints else None, "updated_by": spiral_data.get("updated_by", "archive_cleaner")}
            self.archive.set(SURVEY_SPIRAL_KEY, cleaned_payload)
            # LEGACY_PIONEER_SPIRAL_KEY ("pioneer.survey_spiral") is fully dead
            # -- lib/vehicle_survey.py only reads/writes SURVEY_SPIRAL_KEY any
            # more, nothing else in the codebase references the legacy name --
            # so just delete it outright.
            self._retire_legacy_key(LEGACY_PIONEER_SPIRAL_KEY)
        return outcome

    def _dedup_waypoints(self, waypoints):
        """Spiral waypoints minus malformed ones and repeats of an index or
        a (x, y) rounded to 0.1. Returns (clean_waypoints, cleaned_count)."""
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
        return clean_waypoints, cleaned_count

    def clean_telemetry(self, active_vehicles):
        """
        Deletes the pre-consolidation per-entity telemetry keys (fleet.status.<id>,
        rover.status.<id>, drone.status.<id> -- see lib/fleet_status.py), then prunes
        entries of the shared fleet.status dict whose vehicle/drone no longer exists
        or whose payload is empty/malformed. Pruning by existence is skipped when
        the fleet query came back empty, so a failed query never wipes the dict.
        """
        telemetry_removed = 0

        for prefix in LEGACY_FLEET_STATUS_PREFIXES:
            for k in self.archive.keys(prefix):
                self.log(f"  [DELETE TELEMETRY] Legacy per-entity key '{k}' (superseded by '{FLEET_STATUS_KEY}' dict)")
                telemetry_removed += 1
                if not self.dry_run:
                    self.archive.delete(k)

        telemetry_removed += self._prune_fleet_dict(FLEET_STATUS_KEY, active_vehicles, "DELETE TELEMETRY")

        self.stats["telemetry_removed"] += telemetry_removed
        return f"{telemetry_removed} obsolete telemetry entries purged"

    def clean_mining_reach(self, active_vehicles):
        """
        Prunes outpost_mining.MINING_REACH_KEY entries (stationed miners' published
        reach) of vehicles no longer in the fleet, or whose payload is empty/malformed.
        Pruning by existence is skipped when the fleet query came back empty.
        """
        removed = self._prune_fleet_dict(MINING_REACH_KEY, active_vehicles, "DELETE MINING REACH")

        self.stats["mining_reach_removed"] += removed
        return f"{removed} stale mining reach entries purged"

    def clean_resource_markers(self):
        """Removes the retired "resource." map markers (unsupported_markers.clear_resource_markers()); dry run only counts them."""
        removed = clear_resource_markers(dry_run=self.dry_run)
        if removed:
            self.log(f"  [DELETE MARKERS] {removed} retired '{RESOURCE_MARKER_PREFIX}' marker(s)")
        self.stats["resource_markers_removed"] += removed
        return f"{removed} retired resource marker(s) removed"

    def clean_calibration(self):
        """
        Purges obsolete wh_per_meter calibration entries. Travel energy comes
        from lib/vehicle_energy.py's power/speed model; no vehicle script reads
        or writes these keys.
        Two key formats exist: dot-suffix (e.g. "<vehicle>.wh_per_meter") and
        colon-prefix ("vehicle.wh_per_meter:<vehicle_id>") -- both purged here.
        """
        all_keys = self.archive.keys()
        calib_keys = [k for k in all_keys if k.endswith(".wh_per_meter") or k == "wh_per_meter" or k.startswith("vehicle.wh_per_meter:")]
        calib_purged = 0
        self.console.debug(f"Found {len(calib_keys)} legacy Wh/m calibration key(s) to purge")

        for k in calib_keys:
            self.log(f"  [DELETE CALIBRATION] Key '{k}': Obsolete Wh/m calibration entry (no longer used).")
            calib_purged += 1
            if not self.dry_run:
                self.archive.delete(k)

        self.stats["calibration_purged"] += calib_purged
        return f"{calib_purged} obsolete calibration entries purged"

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
        all_keys = self.archive.keys()
        legacy_keys = [k for k in all_keys if k.startswith(LEGACY_RECALL_KEY_PREFIX)]
        if not legacy_keys:
            return "no legacy per-vehicle recall keys found"

        consolidated = dict(self.archive.get_dict(RECALL_KEY))
        migrated = 0

        for k in legacy_keys:
            vehicle_name = k[len(LEGACY_RECALL_KEY_PREFIX) :]
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
        return f"{len(legacy_keys)} legacy recall key(s) migrated/removed ({migrated} were actively recalled)"

    def clean_retired_keys(self):
        """Deletes every key under RETIRED_KEY_PREFIXES (families no script uses any more)."""
        purged = 0
        for prefix in RETIRED_KEY_PREFIXES:
            for k in self.archive.keys(prefix):
                self.log(f"  [DELETE RETIRED] Key '{k}' (retired family '{prefix}*')")
                purged += 1
                if not self.dry_run:
                    self.archive.delete(k)
        self.stats["retired_keys_purged"] += purged
        return f"{purged} retired key(s) purged"

    def clean_missions(self, active_vehicles):
        """
        Moves leftover per-entity mission keys (vehicle.mission:<name>,
        drone.mission:<name>) into their shared MISSION_KEYS dict -- never
        overwriting an entry the owner already re-saved -- then deletes the
        legacy key. Also drops dict entries that are malformed, or whose
        vehicle/drone no longer exists (existence check skipped when the
        fleet query came back empty).
        """
        for key, legacy_prefix in MISSION_KEYS.items():
            missions = self.archive.get(key, {})
            missions = dict(missions) if isinstance(missions, dict) else {}
            changed = False

            for k in self.archive.keys(legacy_prefix):
                name = k[len(legacy_prefix) :]
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

        return f"{self.stats['missions_migrated']} mission(s) migrated, {self.stats['missions_removed']} removed"

    def clean_machine_status(self):
        """
        Drops MACHINE_STATUS_KEYS dict entries whose building is no longer on
        the outpost network. Skipped per key when discovery finds no building
        of that type at all (not unlocked yet, or discovery failed), so a
        failed walk never wipes the dict.
        """
        removed = 0
        for key, type_id in MACHINE_STATUS_KEYS.items():
            status = self.archive.get(key, None)
            if status is None:
                continue
            if self._reset_if_not_dict(key, status, "DELETE STATUS"):
                removed += 1
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
            removed += self._prune_dict_key(key, stale)
        self.stats["machine_status_removed"] += removed
        return f"{removed} stale machine status entr{'y' if removed == 1 else 'ies'} purged"

    def clean_status_ticks(self, current_tick):
        """Drops STATUS_TICK_KEYS entries that are not a dict or whose "tick" is
        STATUS_STALE_TICKS or more behind current_tick (no tick counts as 0)."""
        if not current_tick:
            return "no clock; skipped"
        removed = 0
        for key in STATUS_TICK_KEYS:
            status = self.archive.get(key, None)
            if not isinstance(status, dict):
                continue
            stale = [mid for mid, entry in status.items() if not is_fresh(entry, current_tick, STATUS_STALE_TICKS)]
            for mid in stale:
                self.log(f"  [DELETE STATUS] {key}['{mid}']: not refreshed for {STATUS_STALE_TICKS} ticks")
            removed += self._prune_dict_key(key, stale, lambda entry: not is_fresh(entry, current_tick, STATUS_STALE_TICKS))
        self.stats["machine_status_removed"] += removed
        return f"{removed} unrefreshed status entr{'y' if removed == 1 else 'ies'} purged"

    def get_live_building_ids(self):
        """Ids of every building on the outpost network (outpost.buildings() with no type
        filter). Empty when discovery fails or finds nothing."""
        ids = set()
        network = component("outpost_network")
        if network and hasattr(network, "outposts"):
            try:
                for outpost in network.outposts() or []:
                    ids.update(str(b.id) for b in outpost.buildings() or [] if getattr(b, "id", None))
            except Exception as e:
                swallowed("archive_cleaner.ArchiveCleaner.get_live_building_ids: outposts", e)
                self.log(f"[WARN] Failed listing network buildings: {e}")
                return set()
        self.console.debug(f"get_live_building_ids: resolved {len(ids)} building ids")
        return ids

    def _building_gone(self, building_id, live_ids):
        """True when the id is off the network AND get_component() no longer resolves it.
        The second check keeps machines the network listing omits (field drills, thermal
        caps built on a vent) from being pruned."""
        if building_id in live_ids:
            return False
        try:
            return get_component(building_id) is None
        except Exception as e:
            swallowed("archive_cleaner.ArchiveCleaner._building_gone: get_component", e)
            return False

    def clean_building_entries(self, live_building_ids):
        """
        Drops BUILDING_ID_KEYS dict entries whose building no longer exists (e.g. a
        decommissioned machine that was breaker-parked). Skipped entirely when the
        network listing came back empty, so a failed walk never wipes the dicts.
        """
        if not live_building_ids:
            return "skipped: could not list network buildings this run"
        removed = 0
        for key in BUILDING_ID_KEYS:
            entries = self.archive.get(key, None)
            if entries is None:
                continue
            if self._reset_if_not_dict(key, entries, "DELETE BUILDING ENTRY"):
                removed += 1
                continue
            stale = [bid for bid in entries if self._building_gone(str(bid), live_building_ids)]
            for bid in stale:
                self.log(f"  [DELETE BUILDING ENTRY] {key}['{bid}']: building no longer exists")
            removed += self._prune_dict_key(key, stale)
        self.stats["building_entries_removed"] += removed
        return f"{removed} entr{'y' if removed == 1 else 'ies'} of removed buildings purged"

    def clean_power_grid_state(self, active_grid_anchors):
        """
        Purges per-grid power.shedded:<anchor>/power.night_wh:<anchor> entries
        whose grid anchor no longer exists -- e.g. two independent grids joined
        via a new power line. Skips entirely if grid
        discovery failed (empty active_grid_anchors), same caution as
        clean_telemetry()'s active_vehicles check -- never purge everything
        just because detection came back empty. Also purges three obsolete keys:
        power.night_duration (use lib/power_solar.py's NIGHT_DURATION_HOURS instead),
        power.last_night_wh, and power.shedded_machines. None of these are
        written by current code.
        """
        purged = 0

        if active_grid_anchors:
            all_keys = self.archive.keys()
            for prefix in ("power.shedded:", "power.night_wh:", "power.daily:", "power.daily_hist:"):
                for k in all_keys:
                    if not k.startswith(prefix):
                        continue
                    anchor = k[len(prefix) :]
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
        return f"{purged} obsolete per-grid/retired power entries purged"

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
        return f"{len(profiling_keys) - removed} active profiling entries retained, {removed} stale/legacy entries purged"

    def clean_power_and_heat(self):
        """
        Validates terraforming parameters:
        - heat.optimal_setpoints
        - power.sunset_hour, power.night_wh
        (power.night_duration and power.last_night_wh are retired outright by
        clean_power_grid_state() instead of range-checked here.)
        """
        repaired_before = self.stats["corrupted_keys_deleted"]
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
        return f"{self.stats['corrupted_keys_deleted'] - repaired_before} invalid key(s) removed"

    def clean_logistics_and_bio(self):
        """
        Validates:
        - pioneer.transport.route
        - bio.completed_orders (non-string entries and duplicates dropped, order kept)
        """
        repaired_before = self.stats["corrupted_keys_deleted"]
        self._check_transport_route()

        bio_orders_key = "bio.completed_orders"
        if self.archive.has(bio_orders_key):
            orders = self.archive.get(bio_orders_key)
            if isinstance(orders, list):
                unique_orders = _unique_orders(orders)
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
        return f"{self.stats['corrupted_keys_deleted'] - repaired_before} corrupted key(s) removed"

    def _check_transport_route(self):
        """Deletes pioneer.transport.route when it holds a non-dict value."""
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

    def clean_corrupted_or_empty_keys(self):
        """
        Scans all keys in the archive for None or corrupted empty payloads.
        """
        all_keys = self.archive.keys()
        self.stats["keys_scanned"] = len(all_keys)
        deleted_before = self.stats["corrupted_keys_deleted"]

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
        return f"{len(all_keys)} keys scanned, {self.stats['corrupted_keys_deleted'] - deleted_before} empty key(s) removed"

    def run(self):
        """Executes full archive validation and cleaning workflow."""
        mode_str = "[DRY-RUN INSPECTION]" if self.dry_run else "[LIVE COMMIT]"
        self.log_messages.append(f"DATA ARCHIVE VALIDATOR & CLEANER {mode_str}")
        self._log.start(f"Data archive validator & cleaner {mode_str}")
        outcome = self._run_stages()
        self._log.end(outcome)
        return self.stats

    def _run_stages(self):
        if not self.is_available():
            self.log("[CRITICAL] Data Archive (notebook) component is unavailable or locked!")
            return "aborted: Data Archive (notebook) unavailable or locked"

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

        self._stage("Checking survey & rover claims", self.clean_claims, current_tick, scanned_poi_keys, scanned_poi_coords, surveyed_site_ids, surveyed_site_coords)
        self._stage("Checking unsupported / blacklisted targets", self.clean_unsupported_targets, scanned_poi_keys, scanned_poi_coords, surveyed_site_ids, surveyed_site_coords)
        self._stage("Checking survey spiral data", self.clean_survey_spiral)
        self._stage("Checking vehicle fleet telemetry", self.clean_telemetry, active_vehicles)
        self._stage("Checking stationed miners' mining reach", self.clean_mining_reach, active_vehicles)
        self._stage("Removing retired resource map markers", self.clean_resource_markers)
        self._stage("Purging obsolete Wh/m calibration entries", self.clean_calibration)
        self._stage("Migrating legacy per-vehicle recall flags", self.clean_recall_flags)
        self._stage("Purging retired key families", self.clean_retired_keys)
        self._stage("Checking resumable mission records", self.clean_missions, active_vehicles)
        self._stage("Checking machine status dicts", self.clean_machine_status)
        self._stage("Checking unrefreshed status entries", self.clean_status_ticks, current_tick)
        self._stage("Checking per-building entries (parking, tank assignments)", self.clean_building_entries, self.get_live_building_ids())
        self._stage("Checking profiling entries", self.clean_profiling, current_tick)
        self._stage("Checking power & heating terraforming state", self.clean_power_and_heat)
        self._stage("Checking per-grid power state", self.clean_power_grid_state, active_grid_anchors)
        self._stage("Checking logistics & bio state", self.clean_logistics_and_bio)
        self._stage("Checking for corrupted or orphaned keys", self.clean_corrupted_or_empty_keys)

        self.log("Summary:")
        for k, v in self.stats.items():
            self.log(f"  {k.replace('_', ' ').capitalize():<30}: {v}")
        return f"{self.stats['keys_scanned']} keys scanned, {self.stats['errors']} error(s)"
