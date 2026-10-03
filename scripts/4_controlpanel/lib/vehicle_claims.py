# Vehicle mixin: fleet-wide target claims and hardware-capability blacklist.
# Shared by Rover and Pioneer via VehicleController (lib/vehicle.py) so peers
# never collide on the same site and never retry targets their current
# hardware can't handle.

from archive import archive
from typing import TYPE_CHECKING
from unsupported_markers import MARKER_PREFIX
from swallow import swallowed
import fleet_claims_common as common

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
    Module-level so non-vehicle scripts (e.g. vehicles_panel.py's Fleet card) can
    read a vehicle's recall flag without instantiating a VehicleController.
    """
    return common.is_flagged(RECALL_KEY, vehicle_name)


def set_vehicle_recalled(vehicle_name, recalled):
    """Sets or clears vehicle_name's recall flag in the shared RECALL_KEY dict."""
    common.set_flagged(RECALL_KEY, vehicle_name, recalled)


def _claim_owner(claim):
    return claim.get("rover", claim.get("vehicle"))


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
        common.save_mission(MISSION_KEY, self._host.name, self.current_target_key, kind, target, self._host.get_current_tick())

    def clear_mission(self):
        common.clear_mission(MISSION_KEY, self._host.name)

    def _read_mission(self) -> "dict | None":
        """This vehicle's stored mission record (legacy vehicle.mission:<name> keys move in on first read)."""
        return common.read_mission(MISSION_KEY, LEGACY_MISSION_KEY_PREFIX, self._host.name, self._host.log)

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
        if not claim or not self._owns(claim):
            self.clear_mission()
            return None

        self.current_target_key = target_key
        self.current_target = record.get("target")
        return record

    def is_recalled(self):
        """
        True when the operator has set this vehicle's recall flag (the Fleet
        card's toggle in vehicles_panel.py, or a direct set_vehicle_recalled() call).
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
            self._prepare_decommission()
        else:
            self._host.log.start(f"[{self._host.name}] Recall active; returning to base.")
            self._host.log.debug(f"[{self._host.name}] Recall active while away from base (current position {self._host.get_position()}, base slot {self._host.assigned_slot_coords}); abandoning current_target_key={self.current_target_key!r} and heading home.")
            self._host.publish_telemetry("RECALLED")
            self.release_target_claim()
            reached = self._host.return_to_base()
            self._host.log.end(f"[{self._host.name}] Recall return {'complete' if reached else 'incomplete'}.")
        return True

    def _prepare_decommission(self):
        """
        At base while recalled for retirement (lib/fleet_decommission.py):
        unloads cargo at HOME_BASE, charges to DECOMMISSION_MIN_SOC (Portable
        Batteries sell for their charge), strips and sells every part
        (_strip_and_sell_parts()), then marks the entry ready for the
        coordinator to undeploy the bare chassis. No-op unless a request is
        pending.
        """
        from fleet_decommission import is_decommission_requested, mark_decommission_ready, DECOMMISSION_MIN_SOC
        name = self._host.name
        if not is_decommission_requested(name):
            return
        self._host.log.start(f"[{name}] Preparing for decommission")
        cargo = getattr(self._host.vehicle, "cargo", None)
        if cargo is not None and cargo.count() > 0:
            self._host.unload_cargo()
            if cargo.count() > 0:
                self._host.log.level("warn").print(f"[{name}] {cargo.count()} unit(s) still aboard (storage full?); retrying.")
                self._host.log.end("cargo aboard")
                return
        _, _, level = self._host.get_battery()
        if level < DECOMMISSION_MIN_SOC:
            self._host.log.debug(f"[{name}] Charging to {DECOMMISSION_MIN_SOC*100:.0f}% before decommission ({level*100:.0f}%).")
            self._host.recharge_at_station(target_level=1.0)
            self._host.log.end("charging")
            return
        stripped, credits, failure = self._strip_and_sell_parts()
        if failure:
            self._host.log.level("warn").print(f"[{name}] Stripping parts stopped: {failure}; retrying.")
            self._host.log.end(f"sold {stripped} part(s) for {credits} cr so far")
            return
        mark_decommission_ready(name)
        self._host.publish_telemetry("DECOMMISSION_READY")
        self._host.log.end(f"[{name}] Empty; sold {stripped} part(s) for {credits} cr; ready for undeploy.")

    def _strip_and_sell_parts(self):
        """
        Uninstalls every portable and unmounts every module, selling each one
        right after it lands in Inventory, so the retirement needs one free
        Inventory slot instead of one per part (undeploy() refuses with
        inventory_full otherwise). Portables come out before their holder
        (unmount() refuses a non-empty one). shop.sell() takes the
        lowest-indexed matching Inventory slot, so a spare of the same item
        may be the unit sold. The Nav Module stays mounted (get_position()
        and is_at_base() need it); the coordinator sells it with the chassis
        kit after the undeploy. Returns (parts sold, credits, failure or None).
        """
        vehicle = self._host.vehicle
        shop = get_component("shop")
        if not hasattr(vehicle, "unmount") or not shop:
            return 0, 0, None
        sold = [0, 0]

        def sell(item_id):
            res = shop.sell(item_id, 1)
            if res.status == "ok":
                sold[0] += 1
                sold[1] += int(getattr(res, "credits", 0) or 0)
            self._host.log.trace(f"[{self._host.name}] sell('{item_id}') -> {res.status}")

        for slot in vehicle.modules():
            module_id = getattr(slot, "module_id", None)
            if not module_id or module_id.startswith("nav_module"):
                continue
            for internal_index, item_id in enumerate(getattr(slot, "internal_items", None) or []):
                if item_id is None:
                    continue
                res = vehicle.uninstall(slot.index, internal_index)
                if res.status != "ok":
                    return sold[0], sold[1], f"uninstall(slot {slot.index}, bay {internal_index}) {res.status}: {res.message}"
                sell(item_id)
            res = vehicle.unmount(slot.index)
            if res.status != "ok":
                return sold[0], sold[1], f"unmount({slot.index}) {res.status}: {res.message}"
            sell(module_id)
        return sold[0], sold[1], None

    def claim_target(self, target_key, target_info):
        """
        Atomically claims a destination/site in Data Archive so peer vehicles skip it.
        Returns True if claim successfully acquired, False otherwise.
        """
        name = self._host.name
        self._host.log.start(f"[{name}] claim_target('{target_key}')", level="debug")
        curr_tick = self._host.get_current_tick()
        record = {
            "rover": name,
            "vehicle": name,
            "type": target_info.get("type", "unknown"),
            "coords": target_info.get("coords", (0, 0)),
            "name": target_info.get("name", target_key),
            "tick": curr_tick,
        }
        notes = []
        won = common.try_claim(SURVEY_CLAIMS_KEY, target_key, name, _claim_owner, record, curr_tick, self.CLAIM_STALE_TICKS, notes)
        for note in notes:
            self._host.log.debug(note)
        self._host.log.debug(f"{'won' if won else 'lost'} the race.")
        self._host.log.end()
        return won

    def _owns(self, claim):
        return claim.get("rover") == self._host.name or claim.get("vehicle") == self._host.name

    def refresh_claim(self, target_key):
        """Renews heartbeat timestamp on an active target claim."""
        common.refresh_claim(SURVEY_CLAIMS_KEY, target_key, self._owns, self._host.get_current_tick())

    def cleanup_stale_claims(self):
        """Removes expired fleet claims before selecting a new mission."""
        self._host.log.start(f"[{self._host.name}] cleanup_stale_claims()", level="debug")
        curr_tick = self._host.get_current_tick()
        if curr_tick <= 0:
            self._host.log.debug(f"skipped, curr_tick={curr_tick} (clock not ready yet).")
            self._host.log.end()
            return
        expired = sum(common.drop_stale_claims(key, curr_tick, self.CLAIM_STALE_TICKS) for key in (SURVEY_CLAIMS_KEY, LEGACY_ROVER_CLAIMS_KEY))
        if expired:
            self._host.log.debug(f"removed {expired} claim(s) older than CLAIM_STALE_TICKS={self.CLAIM_STALE_TICKS} at curr_tick={curr_tick}.")
        self._host.log.end()

    def release_target_claim(self, target_key=None):
        """Releases claim on target_key or releases all claims owned by this vehicle."""
        released = [k for key in (SURVEY_CLAIMS_KEY, LEGACY_ROVER_CLAIMS_KEY) for k in common.release_claims(key, target_key, self._owns)]
        if released:
            self._host.log.debug(f"[{self._host.name}] release_target_claim({target_key!r}): released {released}.")
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
                except Exception as error:
                    swallowed("vehicle_claims.VehicleClaimsMixin.blacklist_target: self._host.vehicle.sonar.tier", error)
                    scanner_tier = "basic"
            elif scanner_type == "drill" and hasattr(self._host.vehicle, "drill"):
                try:
                    h = self._host.vehicle.drill.hardness_limit()
                    scanner_tier = "heavy" if h >= 4 else ("industrial" if h >= 3 else "basic")
                except Exception as error:
                    swallowed("vehicle_claims.VehicleClaimsMixin.blacklist_target: self._host.vehicle.drill.hardness_limit", error)
                    scanner_tier = "basic"
            else:
                scanner_tier = "basic"

        if scanner_type == "sonar" and hasattr(self._host.vehicle, "sonar"):
            try:
                scanner_range = self._host.vehicle.sonar.range()
            except Exception as error:
                swallowed("vehicle_claims.VehicleClaimsMixin.blacklist_target: self._host.vehicle.sonar.range", error)
                scanner_range = 50.0

        if hardness_limit is None:
            if scanner_type == "sonar" and hasattr(self._host.vehicle, "sonar"):
                try:
                    hardness_limit = self._host.vehicle.sonar.hardness_limit()
                except Exception as error:
                    swallowed("vehicle_claims.VehicleClaimsMixin.blacklist_target: self._host.vehicle.sonar.hardness_limit", error)
                    hardness_limit = 1.0
            elif scanner_type == "drill" and hasattr(self._host.vehicle, "drill"):
                try:
                    hardness_limit = self._host.vehicle.drill.hardness_limit()
                except Exception as error:
                    swallowed("vehicle_claims.VehicleClaimsMixin.blacklist_target: self._host.vehicle.drill.hardness_limit #2", error)
                    hardness_limit = 1.0
            else:
                hardness_limit = 1.0

        unlocked_research_count = 0
        unlocked_scan_researches = []
        research = get_component("research")
        if research and hasattr(research, "unlocked"):
            try:
                unlocked_research_count = len(research.unlocked())
            except Exception as error:
                swallowed("vehicle_claims.VehicleClaimsMixin.blacklist_target: research.unlocked", error)
        if research:
            for r_id in SCAN_RESEARCH_IDS:
                try:
                    if hasattr(research, "is_unlocked") and research.is_unlocked(r_id):
                        unlocked_scan_researches.append(r_id)
                except Exception as error:
                    swallowed("vehicle_claims.VehicleClaimsMixin.blacklist_target: research.is_unlocked", error)

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
        except Exception as error:
            swallowed("vehicle_claims.VehicleClaimsMixin.blacklist_target: notify", error)

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
        except Exception as error:
            swallowed("vehicle_claims.VehicleClaimsMixin.clear_unsupported_target: get_component", error)
            markers = None
        if markers:
            try:
                markers.remove(f"{MARKER_PREFIX}{target_key}"[:64])
            except Exception as error:
                swallowed("vehicle_claims.VehicleClaimsMixin.clear_unsupported_target: markers.remove", error)

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
                        except Exception as error:
                            swallowed("vehicle_claims.VehicleClaimsMixin.can_attempt_target: self._host.vehicle.sonar.hardness_limit", error)
                            curr_h = 1.0
                    curr_tier = "basic"
                    if hasattr(self._host.vehicle.sonar, "tier"):
                        try:
                            curr_tier = self._host.vehicle.sonar.tier()
                        except Exception as error:
                            swallowed("vehicle_claims.VehicleClaimsMixin.can_attempt_target: self._host.vehicle.sonar.tier", error)
                            curr_tier = "basic"
                    curr_range = 50.0
                    if hasattr(self._host.vehicle.sonar, "range"):
                        try:
                            curr_range = self._host.vehicle.sonar.range()
                        except Exception as error:
                            swallowed("vehicle_claims.VehicleClaimsMixin.can_attempt_target: self._host.vehicle.sonar.range", error)
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
                        except Exception as error:
                            swallowed("vehicle_claims.VehicleClaimsMixin.can_attempt_target: self._host.vehicle.drill.hardness_limit", error)
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
                        except Exception as error:
                            swallowed("vehicle_claims.VehicleClaimsMixin.can_attempt_target: research.is_unlocked", error)
            return False, "scan_research_still_locked"

        return False, f"unsupported_{reason}"
