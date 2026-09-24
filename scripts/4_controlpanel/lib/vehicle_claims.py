# Vehicle mixin: fleet-wide target claims and hardware-capability blacklist.
# Shared by Rover and Pioneer via VehicleController (lib/vehicle.py) so peers
# never collide on the same site and never retry targets their current
# hardware can't handle.

from archive import archive
from typing import TYPE_CHECKING
from unsupported_markers import MARKER_PREFIX

if TYPE_CHECKING:
    from vehicle import VehicleController

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
# One shared dict {vehicle_name: {target_key, target, kind, tick}} of
# resumable in-progress missions (not one key per vehicle, CLAUDE.md rule 7).
# LEGACY_MISSION_KEY_PREFIX is the old per-vehicle "vehicle.mission:<name>"
# shape: load_mission() moves a leftover into the dict on first read, so a
# vehicle mid-mission across the deploy still resumes; ArchiveCleaner's
# clean_missions() migrates the rest.
MISSION_KEY = "vehicle.mission"
LEGACY_MISSION_KEY_PREFIX = "vehicle.mission:"

# One shared dict {vehicle_name: True} rather than one archive key per vehicle
# (the old "vehicle.recall:<name>" scheme) -- the Data Archive has a fixed
# shared key-count cap, so a dedicated top-level key per vehicle for a single
# boolean flag doesn't scale with fleet size. A vehicle absent from the dict
# reads as not-recalled, so only actively-recalled vehicles are ever stored.
RECALL_KEY = "vehicle.recall"


def is_vehicle_recalled(vehicle_name):
    """
    Module-level so non-vehicle scripts (e.g. panel_2.py's Fleet card) can
    read a vehicle's recall flag without instantiating a VehicleController.
    """
    recalls = archive.get(RECALL_KEY, {}) or {}
    if not isinstance(recalls, dict):
        return False
    return bool(recalls.get(vehicle_name, False))


def set_vehicle_recalled(vehicle_name, recalled):
    """Sets or clears vehicle_name's recall flag in the shared RECALL_KEY dict."""
    def updater(recalls):
        if not isinstance(recalls, dict):
            recalls = {}
        if recalled:
            recalls[vehicle_name] = True
        else:
            recalls.pop(vehicle_name, None)
        return recalls

    archive.transaction(RECALL_KEY, {}, updater)


class VehicleClaimsMixin:
    """
    Atomic target reservation and blacklist tracking, mixed into
    VehicleController. Requires get_current_tick(), self.name, and
    release_target_claim() interplay with self.current_target(_key).
    """

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    CLAIM_STALE_TICKS = 36000

    def save_mission(self, kind, target):
        """
        Persists the in-progress target (and its kind, e.g. "poi_survey" or
        "mine") so a script reload mid-trip resumes toward the same
        destination instead of restarting the mission search from base.
        """
        if not self.current_target_key:
            return
        archive.set_entry(MISSION_KEY, self._host.name, {
            "target_key": self.current_target_key,
            "target": target,
            "kind": kind,
            "tick": self._host.get_current_tick(),
        })

    def clear_mission(self):
        # Plain read first: a transaction always writes back, and this runs
        # on every claim release, mostly with no mission stored.
        if archive.get_entry(MISSION_KEY, self._host.name) is not None:
            archive.pop_entry(MISSION_KEY, self._host.name)

    def _read_mission(self) -> "dict | None":
        """This vehicle's stored mission record, moving a pre-consolidation
        vehicle.mission:<name> key into the shared dict on first read."""
        name = self._host.name
        record = archive.get_entry(MISSION_KEY, name)
        if record is not None:
            return record if isinstance(record, dict) else None
        legacy_key = f"{LEGACY_MISSION_KEY_PREFIX}{name}"
        record = archive.get(legacy_key, None)
        if record is None:
            return None
        archive.delete(legacy_key)
        if not isinstance(record, dict):
            return None
        archive.set_entry(MISSION_KEY, name, record)
        self._host.log.debug(f"[{name}] load_mission: migrated legacy '{legacy_key}' into {MISSION_KEY}.")
        return record

    def load_mission(self):
        """
        Restores an in-progress target after a script reload, provided this
        vehicle still owns that target's claim (it wasn't reassigned or
        expired while the script was down). Returns the mission record, or
        None if there was nothing to resume.
        """
        record = self._read_mission()  # dict or None
        if record is None or not record.get("target_key"):
            return None

        target_key = record["target_key"]
        claim = self.get_claims().get(target_key)
        if not claim or (claim.get("vehicle") != self._host.name and claim.get("rover") != self._host.name):
            self.clear_mission()
            return None

        self.current_target_key = target_key
        self.current_target = record.get("target")
        return record

    def is_recalled(self):
        """
        True when the operator has set this vehicle's recall flag (the Fleet
        card's toggle in panel_2.py, or a direct set_vehicle_recalled() call).
        Checked every loop cycle -- see handle_recall_if_active() -- so an
        active mission is abandoned promptly rather than only at the next
        natural idle point.
        """
        return is_vehicle_recalled(self._host.name)

    def handle_recall_if_active(self):
        """
        If recalled, abandons any current target and heads to base (or just
        idles there if already home). Returns True when recall is active, so
        callers should skip their normal cycle this pass:
            if self.handle_recall_if_active():
                sleep(5.0)
                continue
        """
        if not self.is_recalled():
            return False

        if self._host.is_at_base():
            self._host.log.debug(f"[{self._host.name}] Recall active and already at base ({self._host.get_position()}); idling in RECALLED state.")
            self._host.publish_telemetry("RECALLED")
        else:
            self._host.log.print(f"[{self._host.name}] Recall active; returning to base.")
            self._host.log.debug(f"[{self._host.name}] Recall active while away from base (current position {self._host.get_position()}, base slot {self._host.assigned_slot_coords}); abandoning current_target_key={self.current_target_key!r} and heading home.")
            self._host.publish_telemetry("RECALLED")
            self.release_target_claim()
            self._host.return_to_base()
        return True

    def claim_target(self, target_key, target_info):
        """
        Atomically claims a destination/site in Data Archive so peer vehicles skip it.
        Returns True if claim successfully acquired, False otherwise.
        """
        claimed = [False]
        notes = []  # logged after the transaction: a log call inside the updater gets it rejected
        curr_tick = self._host.get_current_tick()

        def updater(claims):
            if not isinstance(claims, dict):
                claims = {}

            existing = claims.get(target_key)
            if existing:
                claim_owner = existing.get("rover", existing.get("vehicle"))
                claim_tick = existing.get("tick", 0)
                claim_age = curr_tick - claim_tick

                if claim_owner != self._host.name:
                    if curr_tick == 0 or claim_age < self.CLAIM_STALE_TICKS:
                        notes.append(f"[{self._host.name}] claim_target('{target_key}'): lost -- held by '{claim_owner}', age={claim_age} ticks (< CLAIM_STALE_TICKS={self.CLAIM_STALE_TICKS}, curr_tick={curr_tick}).")
                        claimed[0] = False
                        return claims
                    notes.append(f"[{self._host.name}] claim_target('{target_key}'): stale claim from '{claim_owner}' (age={claim_age} ticks >= CLAIM_STALE_TICKS={self.CLAIM_STALE_TICKS}) -- taking over.")

            claims[target_key] = {
                "rover": self._host.name,
                "vehicle": self._host.name,
                "type": target_info.get("type", "unknown"),
                "coords": target_info.get("coords", (0, 0)),
                "name": target_info.get("name", target_key),
                "tick": curr_tick
            }
            claimed[0] = True
            return claims

        if not archive.transaction(SURVEY_CLAIMS_KEY, {}, updater):
            claimed[0] = False
            notes.append(f"[{self._host.name}] claim_target('{target_key}'): {SURVEY_CLAIMS_KEY} write rejected.")
        for note in notes:
            self._host.log.debug(note)
        self._host.log.debug(f"[{self._host.name}] claim_target('{target_key}'): {'won' if claimed[0] else 'lost'} the race.")
        return claimed[0]

    def refresh_claim(self, target_key):
        """Renews heartbeat timestamp on an active target claim."""
        curr_tick = self._host.get_current_tick()

        def updater(claims):
            if isinstance(claims, dict) and target_key in claims:
                if claims[target_key].get("rover") == self._host.name or claims[target_key].get("vehicle") == self._host.name:
                    claims[target_key]["tick"] = curr_tick
            return claims

        archive.transaction(SURVEY_CLAIMS_KEY, {}, updater)

    def cleanup_stale_claims(self):
        """Removes expired fleet claims before selecting a new mission."""
        curr_tick = self._host.get_current_tick()
        if curr_tick <= 0:
            self._host.log.debug(f"[{self._host.name}] cleanup_stale_claims(): skipped, curr_tick={curr_tick} (clock not ready yet).")
            return

        expired = [0]

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
                else:
                    expired[0] += 1
            return active

        archive.transaction(SURVEY_CLAIMS_KEY, {}, updater)
        archive.transaction(LEGACY_ROVER_CLAIMS_KEY, {}, updater)
        if expired[0]:
            self._host.log.debug(f"[{self._host.name}] cleanup_stale_claims(): removed {expired[0]} claim(s) older than CLAIM_STALE_TICKS={self.CLAIM_STALE_TICKS} at curr_tick={curr_tick}.")

    def release_target_claim(self, target_key=None):
        """Releases claim on target_key or releases all claims owned by this vehicle."""
        released = [[]]

        def updater(claims):
            if not isinstance(claims, dict):
                return {}
            if target_key:
                if target_key in claims and (claims[target_key].get("rover") == self._host.name or claims[target_key].get("vehicle") == self._host.name):
                    del claims[target_key]
                    released[0].append(target_key)
            else:
                keys_to_remove = [k for k, v in claims.items() if isinstance(v, dict) and (v.get("rover") == self._host.name or v.get("vehicle") == self._host.name)]
                for k in keys_to_remove:
                    del claims[k]
                released[0].extend(keys_to_remove)
            return claims

        archive.transaction(SURVEY_CLAIMS_KEY, {}, updater)
        archive.transaction(LEGACY_ROVER_CLAIMS_KEY, {}, updater)
        if released[0]:
            self._host.log.debug(f"[{self._host.name}] release_target_claim({target_key!r}): released {released[0]}.")
        else:
            self._host.log.debug(f"[{self._host.name}] release_target_claim({target_key!r}): nothing to release (not owned or not found).")
        if target_key == self.current_target_key or target_key is None:
            self.current_target = None
            self.current_target_key = None
            self.clear_mission()

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

        Callers should pass scanner_type explicitly whenever they know which module produced
        the failure (sonar.scan()/survey() vs drill.mine()) -- the target_key's naming
        convention ("poi_"/"site_") is not a reliable proxy for that (e.g. a sonar survey()
        failure on a "site_" key is still a sonar limitation, not a drill one; per
        docs/components/sonar_module.md and docs/components/drill_module.md only sonar ever
        reports "tier_too_low", and only drill's .mine() reports mining-time "too_hard").
        """
        if scanner_type is None:
            if reason in ["wrong_scanner", "not_allowed", "out_of_range", "tier_too_low"]:
                scanner_type = "sonar"
            elif reason in ["too_hard", "research_required"]:
                # Ambiguous without an explicit caller hint (both sonar.survey() and
                # drill.mine() can report these) -- prefer whichever module the vehicle
                # actually has, since a scout without a drill can only mean sonar.
                if hasattr(self._host.vehicle, "drill") and not hasattr(self._host.vehicle, "sonar"):
                    scanner_type = "drill"
                else:
                    scanner_type = "sonar"
            elif reason in ["depleted", "empty"]:
                scanner_type = "drill"
            else:
                scanner_type = "sonar"

        scanner_range = 50.0
        if scanner_tier is None:
            if scanner_type == "sonar" and hasattr(self._host.vehicle, "sonar"):
                try:
                    scanner_tier = self._host.vehicle.sonar.tier()
                except Exception:
                    scanner_tier = "basic"
            elif scanner_type == "drill" and hasattr(self._host.vehicle, "drill"):
                try:
                    h = self._host.vehicle.drill.hardness_limit()
                    scanner_tier = "heavy" if h >= 4 else ("industrial" if h >= 3 else "basic")
                except Exception:
                    scanner_tier = "basic"
            else:
                scanner_tier = "basic"

        if scanner_type == "sonar" and hasattr(self._host.vehicle, "sonar"):
            try:
                scanner_range = self._host.vehicle.sonar.range()
            except Exception:
                scanner_range = 50.0

        if hardness_limit is None:
            if scanner_type == "sonar" and hasattr(self._host.vehicle, "sonar"):
                try:
                    hardness_limit = self._host.vehicle.sonar.hardness_limit()
                except Exception:
                    hardness_limit = 1.0
            elif scanner_type == "drill" and hasattr(self._host.vehicle, "drill"):
                try:
                    hardness_limit = self._host.vehicle.drill.hardness_limit()
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
                "rover": self._host.name,
                "vehicle": self._host.name,
                "tick": self._host.get_current_tick()
            }
            return targets

        archive.transaction(SURVEY_UNSUPPORTED_KEY, {}, updater)
        self.release_target_claim(target_key)
        self._host.log.print(f"[{self._host.name}] Blacklisted unsupported target '{target_key}' ({reason}: {message} | scanner: {scanner_type}/{scanner_tier}, hardness_limit: {hardness_limit}). Fleet will skip until upgraded.")
        try:
            notify(f"[{self._host.name}] Skipped {target_key}: {reason} (req > {scanner_tier} T{hardness_limit})", level="info", duration_seconds=8.0)
        except Exception:
            pass

    def clear_unsupported_target(self, target_key):
        """Removes a target from unsupported_targets once technology or survey successfully resolves it."""
        # Called after every successful drill/scan, so bail out cheaply when
        # the target was never blacklisted -- otherwise each mined unit costs
        # three archive transactions plus a markers.remove() that logs
        # 'not_found' to the console.
        leg_key = None
        if target_key.startswith("poi_"):
            parts = target_key.split("_")
            if len(parts) >= 3:
                leg_key = f"{parts[1]}:{parts[2]}"
        listed = False
        for store_key in (SURVEY_UNSUPPORTED_KEY, LEGACY_ROVER_UNSUPPORTED_KEY, "pioneer.sonar_retries"):
            store = archive.get(store_key, {})
            if isinstance(store, dict) and (target_key in store or (leg_key and leg_key in store)):
                listed = True
                break
        if not listed:
            return

        def updater(targets):
            if isinstance(targets, dict) and target_key in targets:
                del targets[target_key]
            return targets
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

        # Keep the Planet Map marker (placed by unsupported_markers.py under
        # the same target_key) in step, instead of leaving a stale marker
        # until someone clicks the Control Panel's "Sync Unsupported" button.
        try:
            markers = get_component("markers")
        except Exception:
            markers = None
        if markers:
            try:
                markers.remove(f"{MARKER_PREFIX}{target_key}"[:64])
            except Exception:
                pass

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
            if hasattr(self._host.vehicle, "bio_scanner"):
                return True, "has_bio_scanner"
            return False, "requires_bio_scanner"

        # Hardness limitation / tier limitation (sonar or drill)
        if reason in ["too_hard", "tier_too_low"]:
            if recorded_type == "sonar":
                if hasattr(self._host.vehicle, "sonar"):
                    curr_h = 1.0
                    if hasattr(self._host.vehicle.sonar, "hardness_limit"):
                        try:
                            curr_h = self._host.vehicle.sonar.hardness_limit()
                        except Exception:
                            curr_h = 1.0
                    curr_tier = "basic"
                    if hasattr(self._host.vehicle.sonar, "tier"):
                        try:
                            curr_tier = self._host.vehicle.sonar.tier()
                        except Exception:
                            curr_tier = "basic"
                    curr_range = 50.0
                    if hasattr(self._host.vehicle.sonar, "range"):
                        try:
                            curr_range = self._host.vehicle.sonar.range()
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
                if hasattr(self._host.vehicle, "drill"):
                    curr_h = 1.0
                    if hasattr(self._host.vehicle.drill, "hardness_limit"):
                        try:
                            curr_h = self._host.vehicle.drill.hardness_limit()
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
