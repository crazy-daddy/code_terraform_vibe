# Drone mixin: exclusive biosite extraction claims (own archive key, distinct
# from vehicle_claims.py's ground-vehicle claims) and the scout's bounded
# "confirmed-empty POI" cache. Biosite extraction is exclusive-WITH-COOLDOWN
# (only one drone at a time; journal.is_ready()/next_ready_at() gate re-entry
# only after full depletion), unlike mineral mining's shared yield-debit
# pattern (lib/mining_reservations.py) -- so this reuses vehicle_claims.py's
# claim/heartbeat/staleness SHAPE verbatim, on its own key, rather than the
# non-exclusive reservation pattern. See docs/AI_CHEATSHEET.md's note
# distinguishing the two.

from archive import archive
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drone import DroneController

BIOSITE_CLAIMS_KEY = "biosite.claims"
# One shared dict {drone_name: {target_key, target, kind, tick}}, same
# shape and legacy handling as vehicle_claims.py's MISSION_KEY (old
# per-drone "drone.mission:<name>" keys are moved in on first read).
MISSION_KEY = "drone.mission"
LEGACY_MISSION_KEY_PREFIX = "drone.mission:"
SCOUTED_EMPTY_POI_KEY = "scout.empty_pois"

# Same one-shared-dict shape as vehicle_claims.py's RECALL_KEY, on its own key
# so a drone and a ground vehicle sharing a display name can never collide.
# Recall sends a drone to the nearest Drone Depot, NOT the nearest
# drone_service -- the point is docking somewhere couple()/uncouple() can
# re-equip it (drone.md: both require "docked at an operational Drone
# Depot"), unlike a ground vehicle's charging-station "base".
DRONE_RECALL_KEY = "drone.recall"


def is_drone_recalled(drone_name):
    """Module-level so non-drone scripts (e.g. panel_5.py's DRONE FLEET card) can
    read a drone's recall flag without instantiating a DroneController."""
    recalls = archive.get(DRONE_RECALL_KEY, {}) or {}
    if not isinstance(recalls, dict):
        return False
    return bool(recalls.get(drone_name, False))


def set_drone_recalled(drone_name, recalled):
    """Sets or clears drone_name's recall flag in the shared DRONE_RECALL_KEY dict."""
    def updater(recalls):
        if not isinstance(recalls, dict):
            recalls = {}
        if recalled:
            recalls[drone_name] = True
        else:
            recalls.pop(drone_name, None)
        return recalls

    archive.transaction(DRONE_RECALL_KEY, {}, updater)

# Bounded fixed-size cache per CLAUDE.md rule 7 -- 35 permanent biosites total
# (7 per biome x 5 biomes, docs/guide/biosphere_biomass_tier.md) means the
# realistic ceiling of ever-scanned-empty POIs is small; this cap is a very
# generous margin, not a tight tuning.
SCOUTED_EMPTY_POI_MAX_ENTRIES = 2000

# Same expiry window as VehicleClaimsMixin.CLAIM_STALE_TICKS, so an abandoned
# claim (crash, drone rescued away mid-mission) ages out on the same schedule.
CLAIM_STALE_TICKS = 36000


def biosite_key(x, y):
    """Shared key format for a biosite claim/target, distinct from ground-
    vehicle claim prefixes ("poi_"/"build_"/"site_") so a shared archive
    reader (e.g. a future dashboard) can tell claim kinds apart at a glance."""
    return f"bio_{int(x)}_{int(y)}"


class DroneClaimsMixin:
    """
    Exclusive biosite claims + resumable mission persistence + scout
    empty-POI cache, mixed into DroneController. Requires get_current_tick(),
    self.name, and self.current_target/_key.
    """

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    CLAIM_STALE_TICKS = CLAIM_STALE_TICKS

    def save_mission(self, kind, target):
        """
        Persists the in-progress target so a script reload mid-trip resumes
        toward the same biosite instead of restarting target selection. A
        drone's go_to() is fire-and-forget and IS cancelled by a script
        restart (drone.md: "completing the script... cancels this route"),
        unlike a rover's drive_to() loop -- so resuming here only restores
        WHICH target to head back to; the flight leg itself must always be
        re-issued (see drone_navigation.py/drone_mining.py).
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
        """This drone's stored mission record, moving a pre-consolidation
        drone.mission:<name> key into the shared dict on first read."""
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
        drone still owns that target's claim. Returns the mission record, or
        None if there was nothing to resume.
        """
        record = self._read_mission()  # dict or None
        if record is None or not record.get("target_key"):
            return None

        target_key = record["target_key"]
        claim = self.get_biosite_claims().get(target_key)
        if not claim or claim.get("drone") != self._host.name:
            self._host.log.debug(f"[{self._host.name}] load_mission: saved mission for '{target_key}' found but claim no longer owned by this drone; discarding.")
            self.clear_mission()
            return None

        self.current_target_key = target_key
        self.current_target = record.get("target")
        return record

    def is_recalled(self):
        """
        True when the operator has set this drone's recall flag (the DRONE
        FLEET card's toggle in panel_5.py, or a direct set_drone_recalled()
        call). Checked every loop cycle -- see handle_recall_if_active() --
        so an active mission is abandoned promptly rather than only at the
        next natural idle point.
        """
        return is_drone_recalled(self._host.name)

    def handle_recall_if_active(self):
        """
        If recalled, abandons any current biosite claim/mission and heads to
        its home Drone Depot (get_home_depot()) for re-equipping (couple()/uncouple() both
        require being docked at one -- NOT the nearest drone_service, unlike
        a stranded/low-battery return). Idles there once docked rather than
        undocking (mirrors leave_station()'s opposite intent: recall exists
        so the operator can swap modules, which needs the berth held).
        Returns True when recall is active, so callers should skip their
        normal cycle this pass:
            if self.handle_recall_if_active():
                sleep(5.0)
                continue
        """
        if not self.is_recalled():
            return False

        if not self._host.get_all_drone_depots():
            # get_nearest_drone_depot() would otherwise fall back to
            # home_coords (often (0.0, 0.0) this early) with an empty depot
            # id -- flying there is meaningless when no Depot exists yet.
            # Stay put and wait for one to be built rather than heading
            # toward a bogus coordinate.
            self._host.log.level("warn").print(f"[{self._host.name}] Recall active but no Drone Depot is deployed yet; staying put.")
            self._host.publish_telemetry("RECALLED")
            return True

        depot_coords, depot_info = self._host.get_home_depot()
        depot_id = depot_info.get("id")

        if depot_id and self._host.current_station() == depot_id:
            self._host.log.debug(f"[{self._host.name}] Recall active and already docked at Drone Depot '{depot_id}'; idling in RECALLED state for re-equip.")
            self._host.publish_telemetry("RECALLED")
            return True

        self._host.log.print(f"[{self._host.name}] Recall active; returning to Drone Depot '{depot_id or depot_coords}' for re-equip.")
        self._host.publish_telemetry("RECALLED")
        self.release_biosite_claim()

        reached = bool(depot_id) and self._host.fly_to_station(depot_id, target_coords=depot_coords)
        if not reached and self._host.status() == "waiting_bay":
            # At the depot, bay taken: next cycle's get_home_depot() re-picks
            # (a free sibling depot in a pool home), no direct fly_to needed.
            self._host.log.debug(f"[{self._host.name}] Recall: Drone Depot '{depot_id}' bay taken; retrying next cycle.")
            return True
        if not reached:
            self._host.log.debug(f"[{self._host.name}] fly_to_station({depot_id}) unavailable or failed; falling back to direct fly_to({depot_coords}).")
            self._host.fly_to(depot_coords[0], depot_coords[1], precision=1.5)
        return True

    def claim_biosite(self, target_key, target_info):
        """
        Atomically claims a biosite in Data Archive so peer miner drones skip
        it -- an EXCLUSIVE lock (mirrors vehicle_claims.py's claim_target()),
        not mining_reservations.py's additive yield-debit bookkeeping, since
        only one drone may extract a given biosite at a time (see module
        docstring). Returns True if claim successfully acquired.
        """
        claimed = [False]
        curr_tick = self._host.get_current_tick()

        def updater(claims):
            if not isinstance(claims, dict):
                claims = {}
            existing = claims.get(target_key)
            if existing:
                claim_owner = existing.get("drone")
                claim_age = curr_tick - existing.get("tick", 0)
                if claim_owner != self._host.name:
                    if curr_tick == 0 or claim_age < self.CLAIM_STALE_TICKS:
                        claimed[0] = False
                        self._host.log.debug(f"[{self._host.name}] claim_biosite('{target_key}'): lost -- held by '{claim_owner}' (age={claim_age} ticks < stale threshold {self.CLAIM_STALE_TICKS}).")
                        return claims
                    self._host.log.debug(f"[{self._host.name}] claim_biosite('{target_key}'): existing claim by '{claim_owner}' is stale (age={claim_age} ticks >= {self.CLAIM_STALE_TICKS}); taking over.")
            claims[target_key] = {
                "drone": self._host.name,
                "coords": target_info.get("coords", (0, 0)),
                "name": target_info.get("name", target_key),
                "tick": curr_tick,
            }
            claimed[0] = True
            self._host.log.debug(f"[{self._host.name}] claim_biosite('{target_key}'): won at tick {curr_tick}.")
            return claims

        archive.transaction(BIOSITE_CLAIMS_KEY, {}, updater)
        return claimed[0]

    def refresh_biosite_claim(self, target_key):
        """Renews heartbeat timestamp on an active biosite claim."""
        curr_tick = self._host.get_current_tick()

        def updater(claims):
            if isinstance(claims, dict) and target_key in claims:
                if claims[target_key].get("drone") == self._host.name:
                    claims[target_key]["tick"] = curr_tick
            return claims

        archive.transaction(BIOSITE_CLAIMS_KEY, {}, updater)

    def release_biosite_claim(self, target_key=None):
        """Releases claim on target_key, or every claim owned by this drone."""
        def updater(claims):
            if not isinstance(claims, dict):
                return {}
            if target_key:
                if target_key in claims and claims[target_key].get("drone") == self._host.name:
                    del claims[target_key]
                    self._host.log.debug(f"[{self._host.name}] release_biosite_claim('{target_key}'): released.")
                else:
                    self._host.log.debug(f"[{self._host.name}] release_biosite_claim('{target_key}'): not owned by this drone; no-op.")
            else:
                keys_to_remove = [k for k, v in claims.items() if isinstance(v, dict) and v.get("drone") == self._host.name]
                for k in keys_to_remove:
                    del claims[k]
                self._host.log.debug(f"[{self._host.name}] release_biosite_claim(all): released {len(keys_to_remove)} claim(s): {keys_to_remove}.")
            return claims

        archive.transaction(BIOSITE_CLAIMS_KEY, {}, updater)
        if target_key == self.current_target_key or target_key is None:
            self.current_target = None
            self.current_target_key = None
            self.clear_mission()

    def cleanup_stale_biosite_claims(self):
        """Removes expired fleet biosite claims before selecting a new mission."""
        curr_tick = self._host.get_current_tick()
        if curr_tick <= 0:
            return

        removed_count = [0]

        def updater(claims):
            if not isinstance(claims, dict):
                return {}
            active = {}
            for key, claim in claims.items():
                if not isinstance(claim, dict):
                    continue
                if curr_tick - claim.get("tick", 0) < self.CLAIM_STALE_TICKS:
                    active[key] = claim
                else:
                    removed_count[0] += 1
            return active

        archive.transaction(BIOSITE_CLAIMS_KEY, {}, updater)
        if removed_count[0]:
            self._host.log.debug(f"[{self._host.name}] cleanup_stale_biosite_claims: removed {removed_count[0]} stale claim(s) at tick {curr_tick}.")

    def get_biosite_claims(self):
        """Returns the fleet-wide biosite claims dict {target_key: {"drone", "coords", "name", "tick"}}."""
        claims = archive.get(BIOSITE_CLAIMS_KEY, {})
        return claims if isinstance(claims, dict) else {}

    # --- Scout's confirmed-empty POI cache ---------------------------------

    def is_poi_confirmed_empty(self, x, y):
        """
        True if a bio scanner already confirmed (x, y) empty -- a fixed fact
        about that coordinate (unlike vehicle_claims.py's blacklist_target(),
        which tracks a hardware-capability mismatch that can change on
        upgrade). Distinct from journal.is_empty(x, y), which the caller
        should also check -- this cache only exists to keep the scout's
        per-tick candidate scan cheap once most of the map is already known,
        it is not the source of truth (the journal is).
        """
        cache = archive.get(SCOUTED_EMPTY_POI_KEY, {}) or {}
        if not isinstance(cache, dict):
            return False
        hit = f"{int(x)}_{int(y)}" in cache
        self._host.log.trace(f"[{self._host.name}] is_poi_confirmed_empty({int(x)}, {int(y)}): cache {'hit' if hit else 'miss'} ({len(cache)} entries cached).")
        return hit

    def mark_poi_empty(self, x, y):
        """
        Records (x, y) as a confirmed-empty scanned POI, bounded to
        SCOUTED_EMPTY_POI_MAX_ENTRIES (fixed-size history per CLAUDE.md rule
        7) by dropping the oldest-scanned entries once the cache overflows.
        """
        curr_tick = self._host.get_current_tick()
        key = f"{int(x)}_{int(y)}"

        def updater(cache):
            if not isinstance(cache, dict):
                cache = {}
            cache[key] = curr_tick
            if len(cache) > SCOUTED_EMPTY_POI_MAX_ENTRIES:
                overflow = len(cache) - SCOUTED_EMPTY_POI_MAX_ENTRIES
                oldest = sorted(cache.items(), key=lambda kv: kv[1])[:overflow]
                for k, _ in oldest:
                    del cache[k]
                self._host.log.debug(f"[{self._host.name}] mark_poi_empty: cache overflow ({SCOUTED_EMPTY_POI_MAX_ENTRIES} cap), evicted {overflow} oldest entries.")
            return cache

        archive.transaction(SCOUTED_EMPTY_POI_KEY, {}, updater)
        self._host.log.debug(f"[{self._host.name}] mark_poi_empty({int(x)}, {int(y)}): recorded confirmed-empty at tick {curr_tick}.")
