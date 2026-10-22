# Vehicle mixin: fleet-wide target claims and hardware-capability blacklist.
# Shared by Rover and Pioneer via VehicleController (lib/vehicle.py) so peers
# never collide on the same site and never retry targets their current
# hardware can't handle. Recall handling and decommission prep moved to
# lib/vehicle_recall.py; the recall flag helpers (RECALL_KEY, is_vehicle_recalled)
# stay here. VehicleClaimsMixin is the sole writer of VehicleController.mission
# (lib/mission.py): begin_mission() claims, reserves yield and saves the resume
# record; end_mission() undoes all three.

from typing import TYPE_CHECKING

import fleet_claims_common as common
import mining_reservations
from archive import archive
from contact_inference import RESEARCH_NAMES
from fleet_claims_common import LEGACY_ROVER_CLAIMS_KEY, SURVEY_CLAIMS_KEY
from item_tiers import DRILL_TIERS, MIN_SONAR_RANGE_M, SONAR_TIERS, best_mounted, short_name, tier_rank
from swallow import swallowed
from unsupported_markers import LEGACY_PIONEER_SONAR_KEY, LEGACY_ROVER_UNSUPPORTED_KEY, MARKER_PREFIX, SURVEY_UNSUPPORTED_KEY, place_unsupported_marker

if TYPE_CHECKING:
    from vehicle import VehicleController

SCAN_RESEARCH_IDS = list(RESEARCH_NAMES.keys())


def sonar_range(vehicle, where):
    """Range (m) of `vehicle`'s mounted sonar; MIN_SONAR_RANGE_M when there is none or it can't be read."""
    sonar = getattr(vehicle, "sonar", None)
    if sonar is None:
        return MIN_SONAR_RANGE_M
    try:
        return float(sonar.range())
    except Exception as error:
        swallowed(where, error)
        return MIN_SONAR_RANGE_M


def module_hardness_limit(vehicle, kind, where, default=1.0):
    """hardness_limit() of `vehicle`'s mounted `kind` module ("sonar" or "drill");
    `default` when there is none or it can't be read."""
    module = getattr(vehicle, kind, None)
    if module is None or not hasattr(module, "hardness_limit"):
        return default
    try:
        return module.hardness_limit()
    except Exception as error:
        swallowed(where, error)
        return default


# Entry fields that decide what a blocked contact is and when to retry it.
# Every sonar sweep re-reports each blocked contact in range; an entry that
# matches on these is left alone (no archive write, no marker redraw).
BLOCK_SIGNATURE_FIELDS = ("reason", "scanner_type", "scanner_tier", "hardness_limit", "unlocked_scan_researches")


def same_block(old, new):
    """True when blacklist entry `old` already records `new`'s block (BLOCK_SIGNATURE_FIELDS)."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        return False
    return all(old.get(field) == new.get(field) for field in BLOCK_SIGNATURE_FIELDS)


def scan_research_snapshot():
    """(unlocked research count, unlocked SCAN_RESEARCH_IDS) for a
    blacklist entry; (0, []) without the research component."""
    unlocked_research_count = 0
    unlocked_scan_researches = []
    research = get_component("research")
    if research and hasattr(research, "unlocked"):
        try:
            unlocked_research_count = len(research.unlocked())
        except Exception as error:
            swallowed("vehicle_claims.scan_research_snapshot: research.unlocked", error)
    if research:
        for r_id in SCAN_RESEARCH_IDS:
            try:
                if hasattr(research, "is_unlocked") and research.is_unlocked(r_id):
                    unlocked_scan_researches.append(r_id)
            except Exception as error:
                swallowed("vehicle_claims.scan_research_snapshot: research.is_unlocked", error)
    return unlocked_research_count, unlocked_scan_researches


# SURVEY_CLAIMS_KEY / LEGACY_ROVER_CLAIMS_KEY live in fleet_claims_common (re-exported above).
# One shared dict {vehicle_name: {target_key, target, kind, tick}} of
# resumable in-progress missions (not one key per vehicle, CODE_GUIDES.md#archive).
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


def mine_claim_key(target_key, vehicle_name):
    """
    Claim key of vehicle_name's mine trip to target_key. Several vehicles can
    mine one site, so a mine claim is per vehicle and never locks the site;
    lib/mining_reservations.py decides whether one more trip is worth it.
    """
    return f"{target_key}@{vehicle_name}"


def _legacy_sonar_key(target_key):
    """
    LEGACY_PIONEER_SONAR_KEY key "X:Y" of a "poi_X_Y" target, None for any
    other key. Kept as the key's own text (no float round trip: "3" must stay "3").
    """
    if target_key.startswith("poi_"):
        parts = target_key.split("_")
        if len(parts) >= 3:
            return f"{parts[1]}:{parts[2]}"
    return None


def _remove_unsupported_marker(target_key):
    """
    Keep the Planet Map marker (placed by unsupported_markers.py under the
    same target_key) in step, instead of leaving a stale marker until someone
    clicks the Control Panel's "Sync Unsupported" button.
    """
    try:
        markers = get_component("markers")
    except Exception as error:
        swallowed("vehicle_claims._remove_unsupported_marker: get_component", error)
        markers = None
    if markers:
        try:
            markers.remove(f"{MARKER_PREFIX}{target_key}"[:64])
        except Exception as error:
            swallowed("vehicle_claims._remove_unsupported_marker: markers.remove", error)


class VehicleClaimsMixin:
    """
    Atomic target reservation and blacklist tracking, mixed into
    VehicleController. Requires get_current_tick() and self.name. Sole writer
    of self.mission (begin_mission / adopt_mission / end_mission); the
    current_target* names on VehicleController read it.
    """

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    CLAIM_STALE_TICKS = common.CLAIM_STALE_TICKS
    MISSION_KEY = MISSION_KEY
    LEGACY_MISSION_KEY_PREFIX = LEGACY_MISSION_KEY_PREFIX
    RECALL_KEY = RECALL_KEY

    def _mission_claims(self):
        """get_claims(), with this vehicle's mine claims also under their plain target key, so load_mission() finds them."""
        claims = self.get_claims()
        suffix = f"@{self._host.name}"
        for key, claim in list(claims.items()):
            if key.endswith(suffix):
                claims.setdefault(key[: -len(suffix)], claim)
        return claims

    def claim_key(self, target_key, target_type=None):
        """Archive key of this vehicle's claim on target_key: per vehicle for a mine target (mine_claim_key()), else target_key."""
        mission = self._host.mission
        if target_type is None and mission is not None and target_key == mission.target_key:
            target_type = mission.target.get("type")
        return mine_claim_key(target_key, self._host.name) if target_type == "mine" else target_key

    def claim_target(self, target_key, target_info):
        """
        Atomically claims a destination/site in Data Archive so peer vehicles skip it.
        Returns True if claim successfully acquired, False otherwise. A mine
        target's claim is per vehicle (claim_key()), so it never loses to a peer.
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
        key = self.claim_key(target_key, target_info.get("type"))
        won = common.try_claim(SURVEY_CLAIMS_KEY, key, name, _claim_owner, record, curr_tick, self.CLAIM_STALE_TICKS, notes)
        for note in notes:
            self._host.log.debug(note)
        self._host.log.debug(f"{'won' if won else 'lost'} the race.")
        self._host.log.end()
        return won

    def _owns(self, claim):
        return claim.get("rover") == self._host.name or claim.get("vehicle") == self._host.name

    def refresh_claim(self, target_key):
        """Renews heartbeat timestamp on an active target claim."""
        common.refresh_claim(SURVEY_CLAIMS_KEY, self.claim_key(target_key), self._owns, self._host.get_current_tick())

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
        """
        Releases claim on target_key or releases all claims owned by this
        vehicle. Releasing the current target (or all) also ends the mission
        (end_mission(): yield reservation, saved record).
        """
        self._release_claims(target_key)
        mission = self._host.mission
        if target_key is None or (mission is not None and target_key == mission.target_key):
            self.end_mission(release_claim=False)

    def _release_claims(self, target_key):
        keys = None if target_key is None else (target_key, mine_claim_key(target_key, self._host.name))
        released = [k for key in (SURVEY_CLAIMS_KEY, LEGACY_ROVER_CLAIMS_KEY) for k in common.release_claims(key, keys, self._owns)]
        if released:
            self._host.log.debug(f"[{self._host.name}] release_target_claim({target_key!r}): released {released}.")
        else:
            self._host.log.debug(f"[{self._host.name}] release_target_claim({target_key!r}): nothing to release (not owned or not found).")

    def begin_mission(self, mission, claimed=False):
        """
        Starts mission: claims its target (claimed=True when the caller
        already won the claim), reserves its yield when mission.reserved_yield,
        saves the resumable record and sets self.mission. Returns False, with
        nothing changed, when the claim is lost to a peer.
        """
        if not claimed and not self.claim_target(mission.target_key, mission.target):
            return False
        if mission.reserved_yield:
            target = mission.target
            mining_reservations.reserve_yield(self._host.name, mission.target_key, target["harvest_item"], target["estimated_units"], self._host.get_current_tick(), outpost_id=target.get("outpost_id"))
        mission.tick = self._host.get_current_tick()
        common.save_mission(self.MISSION_KEY, self._host.name, mission.target_key, mission.kind, mission.target, mission.tick)
        self._host.mission = mission
        return True

    def adopt_mission(self, mission):
        """Sets a mission restored from its saved record (FleetUnitMixin.load_mission); claim and record already exist."""
        self._host.mission = mission

    def end_mission(self, release_claim=True):
        """
        Ends the current mission: releases its claim (release_claim=False when
        the caller already did), its yield reservation and saved record, and
        clears self.mission.
        """
        mission = self._host.mission
        if release_claim and mission is not None:
            self._release_claims(mission.target_key)
        if mission is not None and mission.reserved_yield:
            mining_reservations.release_yield(self._host.name)
        self._host.mission = None
        self._host.clear_mission()

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
            scanner_type = self._failing_module(reason)
        scanner_tier, scanner_range, hardness_limit = self._module_limits(scanner_type, scanner_tier, hardness_limit)
        unlocked_research_count, unlocked_scan_researches = scan_research_snapshot()

        entry = {
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
            "tick": self._host.get_current_tick(),
        }

        existing = archive.get(SURVEY_UNSUPPORTED_KEY, {})
        if isinstance(existing, dict) and same_block(existing.get(target_key), entry):
            self.release_target_claim(target_key)
            return

        def updater(targets):
            if not isinstance(targets, dict):
                targets = {}
            targets[target_key] = entry
            return targets

        archive.transaction(SURVEY_UNSUPPORTED_KEY, {}, updater)
        try:
            place_unsupported_marker(target_key, entry)
        except Exception as error:
            swallowed("vehicle_claims.VehicleClaimsMixin.blacklist_target: place_unsupported_marker", error)
        self.release_target_claim(target_key)
        self._host.log.print(f"[{self._host.name}] Blacklisted unsupported target '{target_key}' ({reason}: {message} | scanner: {scanner_type}/{scanner_tier}, hardness_limit: {hardness_limit}). Fleet will skip until upgraded.")
        try:
            notify(f"[{self._host.name}] Skipped {target_key}: {reason} (req > {short_name(scanner_tier)} T{hardness_limit})", level="info", duration_seconds=8.0)
        except Exception as error:
            swallowed("vehicle_claims.VehicleClaimsMixin.blacklist_target: notify", error)

    def _failing_module(self, reason):
        """The module ("sonar" or "drill") that reports a failure reason."""
        if reason in ["wrong_scanner", "not_allowed", "out_of_range", "tier_too_low"]:
            return "sonar"
        if reason in ["too_hard", "research_required"]:
            # Ambiguous without an explicit caller hint (both sonar.survey() and
            # drill.mine() can report these) -- prefer whichever module the vehicle
            # actually has, since a scout without a drill can only mean sonar.
            if hasattr(self._host.vehicle, "drill") and not hasattr(self._host.vehicle, "sonar"):
                return "drill"
            return "sonar"
        if reason in ["depleted", "empty"]:
            return "drill"
        return "sonar"

    def _module_limits(self, scanner_type, scanner_tier, hardness_limit):
        """Mounted tier, sonar range and hardness limit of scanner_type;
        a given tier or hardness limit is kept.
        Returns (scanner_tier, scanner_range, hardness_limit)."""
        scanner_range = MIN_SONAR_RANGE_M
        if scanner_tier is None:
            # Item id of the mounted module (lib/item_tiers.py ladder), None when unreadable.
            scanner_tier = self._mounted_tier(SONAR_TIERS if scanner_type == "sonar" else DRILL_TIERS)

        if scanner_type == "sonar":
            scanner_range = sonar_range(self._host.vehicle, "vehicle_claims.VehicleClaimsMixin._module_limits: sonar.range")

        if hardness_limit is None:
            if scanner_type in ("sonar", "drill"):
                hardness_limit = module_hardness_limit(self._host.vehicle, scanner_type, f"vehicle_claims.VehicleClaimsMixin._module_limits: {scanner_type}.hardness_limit")
            else:
                hardness_limit = 1.0
        return scanner_tier, scanner_range, hardness_limit

    def _mounted_tier(self, ladder):
        """Best item id from `ladder` mounted on this vehicle, None when none is mounted or modules() fails."""
        try:
            return best_mounted(self._host.vehicle.modules(), ladder)
        except Exception as error:
            swallowed("vehicle_claims.VehicleClaimsMixin._mounted_tier: vehicle.modules", error)
            return None

    def clear_unsupported_target(self, target_key):
        """Removes a target from unsupported_targets once technology or survey successfully resolves it."""
        # Called after every successful drill/scan, so bail out cheaply when
        # the target was never blacklisted -- otherwise each mined unit costs
        # three archive transactions plus a markers.remove() that logs
        # 'not_found' to the console.
        leg_key = _legacy_sonar_key(target_key)
        listed = False
        for store_key in (SURVEY_UNSUPPORTED_KEY, LEGACY_ROVER_UNSUPPORTED_KEY, LEGACY_PIONEER_SONAR_KEY):
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
                if leg_key and leg_key in records:
                    del records[leg_key]
            return records

        archive.transaction(LEGACY_PIONEER_SONAR_KEY, {}, p_updater)
        _remove_unsupported_marker(target_key)

    def get_unsupported_targets(self):
        """Returns the unified map of unsupported/blacklisted targets across the fleet."""
        shared = archive.get(SURVEY_UNSUPPORTED_KEY, {})
        legacy_rover = archive.get(LEGACY_ROVER_UNSUPPORTED_KEY, {})
        legacy_pioneer = archive.get(LEGACY_PIONEER_SONAR_KEY, {})
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
        recorded_range = unsupported_entry.get("range", MIN_SONAR_RANGE_M)

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
                    curr_h = module_hardness_limit(self._host.vehicle, "sonar", "vehicle_claims.VehicleClaimsMixin.can_attempt_target: sonar.hardness_limit")
                    curr_tier = self._mounted_tier(SONAR_TIERS)
                    curr_range = sonar_range(self._host.vehicle, "vehicle_claims.VehicleClaimsMixin.can_attempt_target: sonar.range")

                    # An entry with no item id on record (unreadable modules(),
                    # or a tier name from before item ids) ranks -1, so any
                    # readable sonar retries it once and re-records it.
                    if curr_h > recorded_h_limit or tier_rank(SONAR_TIERS, curr_tier) > tier_rank(SONAR_TIERS, recorded_tier) or curr_range > recorded_range:
                        return True, f"upgraded_sonar_{short_name(curr_tier)}"
                return False, f"sonar_tier_too_low (has {recorded_tier} limit {recorded_h_limit})"

            elif recorded_type == "drill":
                if hasattr(self._host.vehicle, "drill"):
                    curr_h = module_hardness_limit(self._host.vehicle, "drill", "vehicle_claims.VehicleClaimsMixin.can_attempt_target: drill.hardness_limit")
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
