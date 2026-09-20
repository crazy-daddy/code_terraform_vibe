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

BIOSITE_CLAIMS_KEY = "biosite.claims"
MISSION_KEY_PREFIX = "drone.mission:"
SCOUTED_EMPTY_POI_KEY = "scout.empty_pois"

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
    CLAIM_STALE_TICKS = CLAIM_STALE_TICKS

    def mission_key(self):
        return f"{MISSION_KEY_PREFIX}{self.name}"

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
        archive.set(self.mission_key(), {
            "target_key": self.current_target_key,
            "target": target,
            "kind": kind,
            "tick": self.get_current_tick(),
        })

    def clear_mission(self):
        archive.delete(self.mission_key())

    def load_mission(self):
        """
        Restores an in-progress target after a script reload, provided this
        drone still owns that target's claim. Returns the mission record, or
        None if there was nothing to resume.
        """
        record = archive.get(self.mission_key(), None)
        if not isinstance(record, dict) or not record.get("target_key"):
            return None

        target_key = record["target_key"]
        claim = self.get_biosite_claims().get(target_key)
        if not claim or claim.get("drone") != self.name:
            self.log.debug(f"[{self.name}] load_mission: saved mission for '{target_key}' found but claim no longer owned by this drone; discarding.")
            self.clear_mission()
            return None

        self.current_target_key = target_key
        self.current_target = record.get("target")
        return record

    def claim_biosite(self, target_key, target_info):
        """
        Atomically claims a biosite in Data Archive so peer miner drones skip
        it -- an EXCLUSIVE lock (mirrors vehicle_claims.py's claim_target()),
        not mining_reservations.py's additive yield-debit bookkeeping, since
        only one drone may extract a given biosite at a time (see module
        docstring). Returns True if claim successfully acquired.
        """
        claimed = [False]
        curr_tick = self.get_current_tick()

        def updater(claims):
            if not isinstance(claims, dict):
                claims = {}
            existing = claims.get(target_key)
            if existing:
                claim_owner = existing.get("drone")
                claim_age = curr_tick - existing.get("tick", 0)
                if claim_owner != self.name:
                    if curr_tick == 0 or claim_age < self.CLAIM_STALE_TICKS:
                        claimed[0] = False
                        self.log.debug(f"[{self.name}] claim_biosite('{target_key}'): lost -- held by '{claim_owner}' (age={claim_age} ticks < stale threshold {self.CLAIM_STALE_TICKS}).")
                        return claims
                    self.log.debug(f"[{self.name}] claim_biosite('{target_key}'): existing claim by '{claim_owner}' is stale (age={claim_age} ticks >= {self.CLAIM_STALE_TICKS}); taking over.")
            claims[target_key] = {
                "drone": self.name,
                "coords": target_info.get("coords", (0, 0)),
                "name": target_info.get("name", target_key),
                "tick": curr_tick,
            }
            claimed[0] = True
            self.log.debug(f"[{self.name}] claim_biosite('{target_key}'): won at tick {curr_tick}.")
            return claims

        archive.transaction(BIOSITE_CLAIMS_KEY, {}, updater)
        return claimed[0]

    def refresh_biosite_claim(self, target_key):
        """Renews heartbeat timestamp on an active biosite claim."""
        curr_tick = self.get_current_tick()

        def updater(claims):
            if isinstance(claims, dict) and target_key in claims:
                if claims[target_key].get("drone") == self.name:
                    claims[target_key]["tick"] = curr_tick
            return claims

        archive.transaction(BIOSITE_CLAIMS_KEY, {}, updater)

    def release_biosite_claim(self, target_key=None):
        """Releases claim on target_key, or every claim owned by this drone."""
        def updater(claims):
            if not isinstance(claims, dict):
                return {}
            if target_key:
                if target_key in claims and claims[target_key].get("drone") == self.name:
                    del claims[target_key]
                    self.log.debug(f"[{self.name}] release_biosite_claim('{target_key}'): released.")
                else:
                    self.log.debug(f"[{self.name}] release_biosite_claim('{target_key}'): not owned by this drone; no-op.")
            else:
                keys_to_remove = [k for k, v in claims.items() if isinstance(v, dict) and v.get("drone") == self.name]
                for k in keys_to_remove:
                    del claims[k]
                self.log.debug(f"[{self.name}] release_biosite_claim(all): released {len(keys_to_remove)} claim(s): {keys_to_remove}.")
            return claims

        archive.transaction(BIOSITE_CLAIMS_KEY, {}, updater)
        if target_key == self.current_target_key or target_key is None:
            self.current_target = None
            self.current_target_key = None
            self.clear_mission()

    def cleanup_stale_biosite_claims(self):
        """Removes expired fleet biosite claims before selecting a new mission."""
        curr_tick = self.get_current_tick()
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
            self.log.debug(f"[{self.name}] cleanup_stale_biosite_claims: removed {removed_count[0]} stale claim(s) at tick {curr_tick}.")

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
        self.log.debug(f"[{self.name}] is_poi_confirmed_empty({int(x)}, {int(y)}): cache {'hit' if hit else 'miss'} ({len(cache)} entries cached).")
        return hit

    def mark_poi_empty(self, x, y):
        """
        Records (x, y) as a confirmed-empty scanned POI, bounded to
        SCOUTED_EMPTY_POI_MAX_ENTRIES (fixed-size history per CLAUDE.md rule
        7) by dropping the oldest-scanned entries once the cache overflows.
        """
        curr_tick = self.get_current_tick()
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
                self.log.debug(f"[{self.name}] mark_poi_empty: cache overflow ({SCOUTED_EMPTY_POI_MAX_ENTRIES} cap), evicted {overflow} oldest entries.")
            return cache

        archive.transaction(SCOUTED_EMPTY_POI_KEY, {}, updater)
        self.log.debug(f"[{self.name}] mark_poi_empty({int(x)}, {int(y)}): recorded confirmed-empty at tick {curr_tick}.")
