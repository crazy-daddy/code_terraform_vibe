# Shared Library for Pioneer Multipurpose Heavy Vehicle Automation
# Inherits from VehicleController (lib/vehicle.py).
# Adds specialized support for Pioneer's 8 modular mount slots,
# Constructor Module field operations (pipes, power lines, outposts, caps),
# and heavy expedition & infrastructure logistics.

from archive import archive
from vehicle import VehicleController
from vehicle_claims import SURVEY_CLAIMS_KEY, LEGACY_ROVER_CLAIMS_KEY
from vehicle_mining import ROVER_PREFERRED_MAX_HARDNESS
from vehicle_upgrade import VehicleUpgradeMixin
from pioneer_commission import PioneerFittingMixin
from storage import take_item
from version_guard import validate_game_version
import mining_reservations
import drill_sites
import fleet_intent
from outpost_mining import HOME_OUTPOST_ID
from swallow import swallowed
import construction_plan
from atomic import run_batched
from tree_console import flush_all, reset_all

class PioneerController(VehicleController, VehicleUpgradeMixin, PioneerFittingMixin):
    """
    Automated Heavy Field Vehicle & Constructor Controller for Pioneer chassis.
    Extends VehicleController with field construction, module slot management,
    infrastructure deployment (pipes, power lines, outposts), and deep expeditions.
    """
    # Minimum construction progress a trip should budget for so a job finishes
    # in roughly 4 round trips rather than dozens of drive-there-do-almost-
    # nothing-drive-back cycles. Capped at whatever progress remains.
    TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25

    # Role name -> the vehicle attribute whose presence identifies it, used by
    # detect_role()/run() to pick a role from mounted equipment rather than
    # requiring the entrypoint script to name the loop function directly.
    # "hauler" is deliberately absent: it's the fallback when none of these
    # are mounted, not a module-detected role.
    ROLE_MODULES = {
        "constructor": "constructor",
        "scout": "sonar",
        "miner": "drill",
    }

    def __init__(self, vehicle, home_base=None):
        super().__init__(vehicle, home_base=home_base)

    def detect_role(self, role_override=None):
        """
        Inspects mounted modules (ROLE_MODULES) and returns one of
        "constructor"/"scout"/"miner"/"hauler" (hauler = fallback, no
        relevant module mounted). role_override skips equipment probing
        entirely and returns that role as-is, for the rare intentionally
        mixed loadout that would otherwise be ambiguous. Returns None only
        when more than one role-defining module is mounted and no override
        was given -- caller must treat that as "cannot start".
        """
        if role_override is not None:
            self.log.debug(f"[{self.name}] Role override supplied: '{role_override}'; skipping equipment probe.")
            return role_override

        self.log.start(f"[{self.name}] Detecting role from mounted equipment")
        present = []
        for role, attr in self.ROLE_MODULES.items():
            mounted = hasattr(self.vehicle, attr)
            self.log.debug(f"{attr} module mounted: {mounted}")
            if mounted:
                present.append(role)

        if len(present) > 1:
            self.log.level("warn").print(
                f"[{self.name}] Multiple role-defining modules mounted ({', '.join(present)}); "
                f"cannot auto-detect a role. Call run(role_override=...) with one of "
                f"{list(self.ROLE_MODULES)} + 'hauler' to force a role."
            )
            self.log.end(f"[{self.name}] Role detection failed")
            return None

        role = present[0] if present else "hauler"
        self.log.end(f"[{self.name}] Detected role: '{role}'")
        return role

    def run(self, role_override=None, dest_outpost_id=None):
        """
        Unified entrypoint: detects this Pioneer's role from its mounted
        equipment (Constructor Module -> constructor, Sonar Module -> scout,
        Drill Module -> miner, none of those -> hauler) and dispatches to the
        matching loop, so a thin entrypoint script no longer needs to name
        the loop function by hand. Every role works for its HOME_BASE: a
        hauler fetches what that outpost requests from anywhere and brings
        it there (run_pull_loop()). role_override forces a specific role,
        bypassing detection -- required when more than one role-defining
        module is mounted at once (see detect_role()). A Pioneer launched from
        the COMMISSION card fits its parts first (lib/pioneer_commission.py).
        dest_outpost_id is ignored; a real outpost id there (an entrypoint
        written for push hauling) is warned about, since haulers pull to
        HOME_BASE rather than deliver elsewhere.
        """
        if dest_outpost_id not in (None, "", "None", "*", "any", "%"):
            self.log.level("warn").print(
                f"[{self.name}] DESTINATION_OUTPOST_ID='{dest_outpost_id}' is ignored: haulers pull to HOME_BASE "
                f"('{self.home_base}'). Set HOME_BASE='{dest_outpost_id}' to supply that outpost."
            )
        self.fit_commissioned_loadout()
        role = self.detect_role(role_override)
        if role is None:
            return
        self.role = role

        if role == "constructor":
            self.run_construction_loop()
        elif role == "scout":
            self.run_survey_loop()
        elif role == "miner":
            self.run_stationed_mining_loop(self.home_base)
        elif role == "hauler":
            self.run_pull_loop()
        else:
            self.log.level("warn").print(f"[{self.name}] Unknown role '{role}'.")

    def construction_claim_key(self, job_id):
        """
        Shared claims dict key for a construction job -- distinct prefix from
        mining's "site_"/POI's "poi_" so the three never collide in the same
        archive dict. Unlike mining sites (several Pioneers can now dig the
        same POI), a construction job is NOT shareable: two Constructor
        Pioneers both loading/building the same blueprint would double-load
        materials and waste a trip, so this reuses vehicle_claims.py's
        existing EXCLUSIVE claim mechanism as-is (see construction_plan.claim_free())
        rather than mining_reservations.py's non-exclusive yield-debit pattern.
        """
        return construction_plan.claim_key(job_id)

    def get_construction_progress(self, blueprint_id):
        """
        Current 0-1 progress for a blueprint id, checking pending/active/paused lists.

        A blueprint that is in NONE of those lists (while at least one of them
        could actually be read) is finished (or was removed), so it counts as
        1.0: the game drops a completed blueprint from every list. Without this,
        run_construction_loop()'s "release the claim once progress >= 1.0"
        check never fires (stale build_* claims block other builders for up to
        CLAIM_STALE_TICKS), and the completing execute() step reads as negative
        progress, so calibrate_wh_per_progress() ignores it. Stays 0.0 when the
        component or every list is unreadable.
        """
        bp = get_component("construction_blueprint")
        if not bp:
            return 0.0
        any_list_read = False
        for getter_name in ("pending_constructions", "active_constructions", "paused_constructions"):
            getter = getattr(bp, getter_name, None)
            if not getter:
                continue
            try:
                jobs = getter() or []
            except Exception as error:
                swallowed("pioneer.PioneerController.get_construction_progress: getter", error)
                continue
            any_list_read = True
            progress = construction_plan.job_progress(jobs, blueprint_id)
            if progress is not None:
                return progress
        if any_list_read:
            self.log.debug(f"[{self.name}] get_construction_progress({blueprint_id}): not in any blueprint list -- treating as complete (1.0)")
            return 1.0
        return 0.0

    def release_finished_construction_claims(self, live_job_ids, existing_claims):
        """
        Drops every build_* claim THIS Pioneer holds whose blueprint is no
        longer live (not in pending/active/paused) -- finished or removed
        while this script wasn't the one to observe it (restart mid-build, or
        claims leaked before get_construction_progress() learned that "gone"
        means done). One transaction per claims key, and only when something
        actually needs releasing (checked first against existing_claims, which
        the caller already fetched).
        """
        mine = [
            key for key, claim in (existing_claims or {}).items()
            if key.startswith("build_") and isinstance(claim, dict)
            and (claim.get("vehicle") == self.name or claim.get("rover") == self.name)
            and key[len("build_"):] not in live_job_ids
        ]
        if not mine:
            return 0
        dead = set(mine)

        def updater(claims):
            if not isinstance(claims, dict):
                return {}
            return {k: v for k, v in claims.items() if k not in dead}

        archive.transaction(SURVEY_CLAIMS_KEY, {}, updater)
        archive.transaction(LEGACY_ROVER_CLAIMS_KEY, {}, updater)
        self.log.print(f"[{self.name}] Released {len(dead)} build claim(s) on finished/removed blueprints.")
        return len(dead)

    def planned_progress_for_job(self, job):
        """Remaining progress capped at TARGET_CONSTRUCTION_PROGRESS_PER_TRIP, for trip budgeting."""
        remaining = max(0.0, 1.0 - (getattr(job, "progress", 0.0) or 0.0))
        return min(remaining, self.TARGET_CONSTRUCTION_PROGRESS_PER_TRIP)

    def inspect_slots(self):
        """Inspects all 8 chassis mount slots and returns detailed status."""
        if hasattr(self.vehicle, "modules"):
            try:
                return self.vehicle.modules()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Error reading modules: {e}")
        return []

    def mount_hardware(self, slot_index, module_item_id):
        """Mounts a module into the specified slot index while at a base/outpost service area."""
        if hasattr(self.vehicle, "mount"):
            res = self.vehicle.mount(slot_index, module_item_id)
            self.log.print(f"[{self.name}] Mount slot {slot_index} -> '{module_item_id}': {res.status} ({res.message})")
            return res.status == "ok"
        return False

    def unmount_hardware(self, slot_index):
        """Unmounts a module from the specified slot index back to inventory."""
        if hasattr(self.vehicle, "unmount"):
            res = self.vehicle.unmount(slot_index)
            self.log.print(f"[{self.name}] Unmount slot {slot_index}: {res.status} ({res.message})")
            return res.status == "ok"
        return False

    def execute_construction(self, blueprint_id, coords=None, kind=None):
        """
        Drives within interaction range of a construction blueprint and executes it,
        recharging on-site and resuming for as long as real progress keeps being made.
        The energy budget check before departing only commits to
        TARGET_CONSTRUCTION_PROGRESS_PER_TRIP of the job, so running low on battery
        mid-build here is normal and expected, not a failure -- returning early
        would waste the trip and abandon a perfectly workable job. Blueprints can
        build outposts, pumps, well caps, power lines, and pipe networks.
        Caller must ensure required cargo is loaded first; see load_construction_materials().
        `kind` (the Construction's .kind): a finished mining_drill* blueprint
        records the new drill's position (drill_sites.record_built_drill()),
        since no game API exposes drill coordinates.

        Returns False only for a genuine rejection (blocked, insufficient materials,
        etc.) or an inability to physically reach the site/station -- never merely
        because the job is still incomplete and needs another recharge round later.
        """
        self.log.start(f"[{self.name}] Build '{blueprint_id}' ({kind or 'blueprint'}) at {coords}")
        ok = self._execute_construction(blueprint_id, coords, kind)
        self.log.end(f"[{self.name}] Build '{blueprint_id}' {'finished or paused for later' if ok else 'failed'}")
        return ok

    def _execute_construction(self, blueprint_id, coords, kind):
        """Body of execute_construction()."""
        self.log.start(f"[{self.name}] _execute_construction", level="debug")
        self.log.trace(f"execute_construction() enter: blueprint_id={blueprint_id!r}, coords={coords}")
        if not hasattr(self.vehicle, "constructor"):
            self.log.level("error").print(f"[{self.name}] Error: No ConstructorModule mounted on this Pioneer!")
            self.log.end()
            return False

        self.set_intent(fleet_intent.describe("building", [kind or "blueprint"], at=f"{coords[0]:.0f},{coords[1]:.0f}" if coords else None))
        if coords:
            self.log.print(f"[{self.name}] Driving to construction site at {coords}...")
            if not self.drive_with_recharge(coords[0], coords[1], precision=2.0):
                self.log.level("warn").print(f"[{self.name}] Could not reach construction site at {coords} safely.")
                self.log.trace("execute_construction() exit: could not reach site")
                self.log.end()
                return False

        if hasattr(self.vehicle, "nav"):
            try:
                self.vehicle.nav.brake()
            except Exception as exc:
                swallowed("pioneer.PioneerController.execute_construction: self.vehicle.nav.brake", exc)

        while True:
            # No-op if this Pioneer doesn't actually own the job's claim (the
            # caller is expected to claim_target() before calling this), so
            # safe to call unconditionally.
            self.refresh_claim(self.construction_claim_key(blueprint_id))
            self.log.print(f"[{self.name}] Executing blueprint '{blueprint_id}'...")
            self.publish_telemetry("CONSTRUCTING", blueprint_id)
            progress_before = self.get_construction_progress(blueprint_id)
            wh_before, _, _ = self.get_battery()
            res = self.vehicle.constructor.execute(blueprint_id)
            progress_after = self.get_construction_progress(blueprint_id)
            self.calibrate_wh_per_progress(progress_after - progress_before, wh_before - self.get_battery()[0])
            self.log.print(f"[{self.name}] Constructor result: {res.status} - {res.message}")

            if res.status == "ok":
                if kind and str(kind).startswith("mining_drill") and coords and hasattr(self.vehicle, "input"):
                    try:
                        drill_sites.record_built_drill(self.vehicle.input, str(kind), coords)
                    except Exception as error:
                        self.log.level("warn").print(f"[{self.name}] Could not record new drill position: {error}")
                self.log.trace(f"execute_construction() exit: blueprint '{blueprint_id}' complete")
                self.log.end()
                return True
            if res.status not in ("paused_no_power", "paused"):
                self.log.trace(f"execute_construction() exit: genuine rejection ({res.status})")
                self.log.end()
                return False  # genuine rejection, not a power issue -- don't keep retrying

            if progress_after <= progress_before:
                self.log.level("warn").print(f"[{self.name}] No progress made this cycle ({res.status}); leaving paused for a later attempt.")
                self.log.trace("execute_construction() exit: no progress made, leaving paused")
                self.log.end()
                return True

            self.log.print(f"[{self.name}] Construction paused ({res.status}) at {progress_after*100:.0f}% progress. Recharging nearby and resuming.")
            nearest_cs, _ = self.get_nearest_charging_station()
            if not self.drive_to(nearest_cs[0], nearest_cs[1], precision=1.0):
                self.log.level("warn").print(f"[{self.name}] Could not reach charging station to resume construction; leaving paused for a later attempt.")
                self.log.trace("execute_construction() exit: could not reach charging station")
                self.log.end()
                return True
            self.recharge_at_station(target_level=1.0, station_coords=nearest_cs)
            if coords and not self.drive_with_recharge(coords[0], coords[1], precision=2.0):
                self.log.level("warn").print(f"[{self.name}] Could not return to construction site after recharge; leaving paused for a later attempt.")
                self.log.trace("execute_construction() exit: could not return to site after recharge")
                self.log.end()
                return True
            if hasattr(self.vehicle, "nav"):
                try:
                    self.vehicle.nav.brake()
                except Exception as exc:
                    swallowed("pioneer.PioneerController.execute_construction: self.vehicle.nav.brake #2", exc)
        self.log.end()

    def cargo_count(self, item_id):
        """Units of item_id currently sitting in the Pioneer's cargo, across all stacks."""
        try:
            return sum(getattr(s, "count", 0) for s in self.vehicle.cargo.stacks() if getattr(s, "id", None) == item_id)
        except Exception as error:
            swallowed("pioneer.PioneerController.cargo_count: self.vehicle.cargo.stacks", error)
            return 0

    def cargo_counts(self):
        """{item_id: units} aboard, from one cargo.stacks() read ({} if unreadable)."""
        counts = {}
        try:
            for stack in self.vehicle.cargo.stacks():
                item_id = getattr(stack, "id", None)
                counts[item_id] = counts.get(item_id, 0) + getattr(stack, "count", 0)
        except Exception as error:
            swallowed("pioneer.PioneerController.cargo_counts: self.vehicle.cargo.stacks", error)
        return counts

    def load_construction_materials(self, job, target_count=None):
        """Loads required_item from storage at this Pioneer's home outpost
        (Inventory too when that is the home outpost) into cargo,
        aiming for target_count (e.g. a whole chain of upcoming same-material
        jobs) but succeeding once this job's own required_count is met, since
        storage may not have the full batch on hand. Clamps the load request
        to available cargo capacity to prevent 'target_full' transfer
        rejections."""
        required_item = getattr(job, "required_item", None)
        required_count = getattr(job, "required_count", 0)
        if not required_item or required_count <= 0:
            return True  # deconstruction jobs and already-started jobs need nothing

        have = self.cargo_count(required_item)
        goal = max(required_count, target_count or 0)

        # Clamp goal to fit within available cargo space
        if hasattr(self.vehicle, "cargo"):
            try:
                cap = self.vehicle.cargo.capacity()
                cnt = self.vehicle.cargo.count()
                free_space = max(0, cap - cnt)
                goal = min(goal, have + free_space)
            except Exception as error:
                swallowed("pioneer.PioneerController.load_construction_materials: self.vehicle.cargo.capacity", error)

        if have >= goal and have >= required_count:
            return True

        if not hasattr(self.vehicle, "input"):
            self.log.level("warn").print(f"[{self.name}] Cannot load {required_item}: no input port / Auto Feeders.")
            return False

        missing = max(0, goal - have)
        if missing <= 0:
            return have >= required_count

        # run_construction_loop() returns to self.home_outpost before stocking.
        moved = take_item(self.vehicle.input, required_item, missing, outpost=self.home_outpost)
        if moved > 0:
            self.log.print(f"[{self.name}] Loaded {moved}x {required_item} for construction (stocking toward {goal} for chained jobs).")
        elif self.cargo_count(required_item) < required_count:
            self.log.level("warn").print(f"[{self.name}] Could not load {required_item}: none in storage at '{self.home_base}'.")
        return self.cargo_count(required_item) >= required_count

    def run_construction_loop(self):
        """Continuously polls pending and paused construction blueprints and executes available builds."""
        self.log.print(f"Pioneer Controller ({self.name}) online. Monitoring construction blueprints.")
        bp_component = get_component("construction_blueprint")
        failed_jobs = set()

        validate_game_version()
        while True:
            reset_all()
            try:
                if self.handle_recall_if_active():
                    flush_all()
                    sleep(5.0)
                    continue

                # 1. Base Battery & Staging: If parked at home, ensure charged before departing
                if self.is_at_base():
                    _, _, lvl = self.get_battery()
                    if lvl < 0.90:
                        self.recharge_at_station(target_level=1.0)
                    self.handle_upgrade_cycle_if_idle()

                # 2. Field Battery Floor: proactively head back with enough reserve for a
                # normal-speed return, not just the bare survival floor (which would leave
                # conserve mode nothing to spend but the slowest possible crawl home).
                curr_wh, _, _ = self.get_battery()
                if curr_wh <= self.energy_needed_to_return_comfortably():
                    self.log.start(f"[{self.name}] Return reserve reached in field; returning to nearest station to recharge.")
                    nearest_st, _ = self.get_nearest_charging_station()
                    self.drive_to(nearest_st[0], nearest_st[1], precision=1.0)
                    self.recharge_at_station(target_level=1.0, station_coords=nearest_st)
                    self.log.end(f"[{self.name}] Field recharge done.")
                    continue

                # Query paused and pending constructions
                paused = []
                pending = []
                # Only sweep leaked claims when every list read cleanly -- a
                # failed read would make live jobs look finished.
                lists_ok = bool(bp_component)
                if bp_component:
                    if hasattr(bp_component, "paused_constructions"):
                        try:
                            paused = bp_component.paused_constructions() or []
                        except Exception as error:
                            swallowed("pioneer.PioneerController.run_construction_loop: bp_component.paused_constructions", error)
                            paused = []
                            lists_ok = False
                    if hasattr(bp_component, "pending_constructions"):
                        try:
                            pending = bp_component.pending_constructions() or []
                        except Exception as error:
                            swallowed("pioneer.PioneerController.run_construction_loop: bp_component.pending_constructions", error)
                            pending = []
                            lists_ok = False

                if not paused and not pending:
                    self.log.debug(f"[{self.name}] run_construction_loop(): no paused or pending construction jobs; idling.")
                    if lists_ok and bp_component is not None:
                        try:
                            active_now = bp_component.active_constructions() if hasattr(bp_component, "active_constructions") else []
                        except Exception as error:
                            swallowed("pioneer.PioneerController.run_construction_loop: bp_component.active_constructions", error)
                            active_now = None  # unreadable -- don't sweep this cycle
                        if active_now is not None:
                            live_ids = {getattr(j, "id", getattr(j, "blueprint_id", None)) for j in (active_now or [])}
                            self.release_finished_construction_claims(live_ids, self.get_claims())
                    if failed_jobs:
                        failed_jobs.clear()
                    if self.distance_to_home() > 3.0:
                        self.return_to_base()
                    self.publish_telemetry("IDLE_AT_BASE")
                    flush_all()
                    sleep(10.0)
                    continue

                # Unlike mining POIs (several Pioneers can now dig the same
                # site), a construction job is NOT shareable -- two
                # Constructor Pioneers both loading/building the same
                # blueprint would double-load materials and waste a trip.
                # The job scan skips anything a peer already owns (self-owned
                # claims pass through, per construction_plan.claim_free()).
                existing_claims = self.get_claims()
                curr_tick = self.get_current_tick()
                active = []
                if bp_component and hasattr(bp_component, "active_constructions"):
                    try:
                        active = bp_component.active_constructions() or []
                    except Exception as error:
                        swallowed("pioneer.PioneerController.run_construction_loop: bp_component.active_constructions #2", error)
                        active = []
                        lists_ok = False
                current_pos = self.get_position()
                cargo = self.cargo_counts()
                scan_args = (current_pos, cargo, existing_claims, self.name, curr_tick, self.CLAIM_STALE_TICKS, failed_jobs)
                paused_ids, paused_rows, _ = construction_plan.scan_jobs(paused, *scan_args)
                pending_ids, pending_rows, matching = construction_plan.scan_jobs(pending, *scan_args)
                if lists_ok:
                    active_ids, _, _ = construction_plan.scan_jobs(active, *scan_args)
                    self.release_finished_construction_claims(set(paused_ids + pending_ids + active_ids), existing_claims)
                self.log.debug(f"[{self.name}] Job scan: {len(paused_rows)}/{len(paused_ids)} paused and {len(pending_rows)}/{len(pending_ids)} pending open, {len(matching)} matching cargo {cargo}.")

                # 3. Check Paused Constructions first (resuming already-paid work)
                active_job = None
                for row in paused_rows:
                    if not row["coords"]:
                        continue
                    budget = self.calculate_trip_energy(
                        row["coords"], planned_drill_units=0, planned_scans=0,
                        planned_construction_progress=self.planned_progress_for_job(row["job"]),
                    )
                    if budget["is_achievable"]:
                        active_job = row
                        break
                    elif self.distance_to_home() > 3.0:
                        # Cannot reach safely from current field position; recharge at nearest station
                        self.log.start(f"[{self.name}] Insufficient energy to reach paused job safely; recharging at nearest station.")
                        nearest_st, _ = self.get_nearest_charging_station()
                        self.drive_to(nearest_st[0], nearest_st[1], precision=1.0)
                        self.recharge_at_station(target_level=1.0, station_coords=nearest_st)
                        self.log.end(f"[{self.name}] Recharge before paused job done.")
                        break

                if active_job:
                    job_id = active_job["id"]
                    coords = active_job["coords"]
                    if self.claim_target(self.construction_claim_key(job_id), {"type": "build", "coords": coords, "name": job_id}):
                        self.log.debug(f"[{self.name}] Resuming paused construction job: {job_id} at {coords}.")
                        success = self.execute_construction(job_id, coords, kind=active_job["kind"])
                        if not success:
                            failed_jobs.add(job_id)
                            self.release_target_claim(self.construction_claim_key(job_id))
                            flush_all()
                            sleep(2.0)
                        elif self.get_construction_progress(job_id) >= 1.0:
                            self.release_target_claim(self.construction_claim_key(job_id))
                        continue
                    # Lost the race to a peer between filtering and claiming -- fall
                    # through to step 4 this cycle instead of executing nothing.

                # 4. Check Pending Constructions matching current cargo (deconstruction
                # or materials aboard), nearest first
                if matching:
                    # Gate on the speedmode throttle floor, not the typical calibrated rate:
                    # drive_with_recharge()/select_cruise_throttle() will pick whatever throttle
                    # the leg actually needs, so a job only reachable by conserving hard should
                    # still be attempted rather than rejected against a faster-than-necessary estimate.
                    candidate = None
                    for _, _, row in matching:
                        if not row["coords"]:
                            continue
                        budget = self.calculate_trip_energy(
                            row["coords"], planned_drill_units=0, planned_scans=0,
                            planned_construction_progress=self.planned_progress_for_job(row["job"]),
                            wh_per_meter=self.minimum_wh_per_meter(),
                        )
                        if budget["is_achievable"]:
                            candidate = row
                            break

                    if candidate:
                        job_id = candidate["id"]
                        coords = candidate["coords"]
                        if self.claim_target(self.construction_claim_key(job_id), {"type": "build", "coords": coords, "name": job_id}):
                            self.log.debug(f"[{self.name}] Executing chained construction job: {job_id} at {coords}.")
                            success = self.execute_construction(job_id, coords, kind=candidate["kind"])
                            if not success:
                                failed_jobs.add(job_id)
                                self.release_target_claim(self.construction_claim_key(job_id))
                                flush_all()
                                sleep(2.0)
                            elif self.get_construction_progress(job_id) >= 1.0:
                                self.release_target_claim(self.construction_claim_key(job_id))
                            continue
                        # Lost the race to a peer between filtering and claiming --
                        # fall through to the restocking branch below this cycle.
                    else:
                        # We have cargo matching pending jobs, but cannot reach any right now
                        nearest_st, _ = self.get_nearest_charging_station()
                        if self.distance_between(current_pos, nearest_st) > 3.0:
                            self.log.start(f"[{self.name}] Insufficient energy to reach next construction site; recharging at nearest station.")
                            self.drive_to(nearest_st[0], nearest_st[1], precision=1.0)
                            self.recharge_at_station(target_level=1.0, station_coords=nearest_st)
                            self.log.end(f"[{self.name}] Recharge before next site done.")
                            continue
                        else:
                            curr_wh, cap_wh, lvl = self.get_battery()
                            if lvl < 0.98:
                                self.log.start(f"[{self.name}] At station with materials but need charge ({lvl*100:.0f}%); recharging to full.")
                                self.recharge_at_station(target_level=1.0, station_coords=nearest_st)
                                self.log.end(f"[{self.name}] Recharged with materials aboard.")
                                continue
                            else:
                                # candidate selection above already gated on minimum_wh_per_meter()
                                # (the speedmode throttle floor), so reaching here means none of
                                # these jobs are reachable even at the slowest possible throttle.
                                req_details = []
                                for _, _, row in matching:
                                    j_id = row["id"]
                                    if row["coords"]:
                                        j_budget = self.calculate_trip_energy(
                                            row["coords"], planned_drill_units=0, planned_scans=0,
                                            planned_construction_progress=self.planned_progress_for_job(row["job"]),
                                            wh_per_meter=self.minimum_wh_per_meter(),
                                        )
                                        req_details.append(f"{j_id} ({j_budget['total_required_wh']:.1f} Wh)")
                                    else:
                                        req_details.append(f"{j_id}")
                                    failed_jobs.add(j_id)
                                self.log.level("warn").print(f"[{self.name}] Advisory: Matching construction job(s) exceed maximum battery range even at minimum throttle ({cap_wh:.1f} Wh): {', '.join(req_details)}.")
                                flush_all()
                                sleep(5.0)
                                continue

                # 5. No matching jobs with current cargo: return to base, offload, and restock.
                # Filter out jobs that permanently exceed maximum vehicle battery capacity from
                # the closest charging station in the network, at the speedmode throttle floor
                # (cheapest possible Wh/m) -- that's the true bound for a "permanently" unreachable
                # verdict, since conserve mode can always throttle down that far to stretch a tight
                # round trip. Also budget for the minimum useful on-site progress
                # (TARGET_CONSTRUCTION_PROGRESS_PER_TRIP), since a trip that can't build anything
                # meaningful isn't worth taking either.
                _, cap_wh, _ = self.get_battery()
                stations = [st["coords"] for st in self.get_all_charging_stations()] or [self.home_coords]
                trips = run_batched(
                    construction_plan.station_trip_wh, pending_rows, construction_plan.TRIP_CHUNK,
                    stations, self.minimum_wh_per_meter(), self.wh_per_progress,
                    self.TARGET_CONSTRUCTION_PROGRESS_PER_TRIP, self.SAFETY_MARGIN_MULTIPLIER, self.MIN_EMERGENCY_RESERVE_WH,
                )
                achievable_targets = []
                for row, required_wh in trips:
                    if required_wh is not None and required_wh > cap_wh:
                        if row["id"] not in failed_jobs:
                            self.log.level("warn").print(f"[{self.name}] Construction job '{row['id']}' at {row['coords']} permanently exceeds battery capacity from nearest station even at minimum throttle ({required_wh:.1f} Wh required, {cap_wh:.1f} Wh max capacity). Marking failed.")
                            failed_jobs.add(row["id"])
                        continue
                    achievable_targets.append(row)

                target_jobs = achievable_targets
                if not target_jobs:
                    # All pending jobs currently marked failed; clear failure set and wait
                    self.log.debug(f"[{self.name}] run_construction_loop(): every pending job is unreachable this cycle; clearing failed_jobs and idling.")
                    failed_jobs.clear()
                    if self.distance_to_home() > 3.0:
                        self.return_to_base()
                    self.publish_telemetry("IDLE_AT_BASE")
                    flush_all()
                    sleep(10.0)
                    continue

                # Claim the first target_jobs entry this Pioneer can actually win --
                # commits to it before the round trip home for materials, so a peer
                # Constructor Pioneer doesn't also fetch and build the same job.
                target_job = None
                for candidate_row in target_jobs:
                    if self.claim_target(self.construction_claim_key(candidate_row["id"]), {"type": "build", "coords": candidate_row["coords"], "name": candidate_row["id"]}):
                        target_job = candidate_row
                        break
                if not target_job:
                    # Every achievable job just got claimed out from under us; retry next cycle.
                    flush_all()
                    sleep(2.0)
                    continue

                job_id = target_job["id"]
                required_item = target_job["item"]
                required_count = target_job["count"]

                # Return to base for restocking
                if self.distance_to_home() > 3.0:
                    self.return_to_base()

                # Ensure vehicle is fully charged before embarking on a new batch
                _, _, lvl = self.get_battery()
                if lvl < 0.98:
                    self.recharge_at_station(target_level=1.0)

                if required_item and required_count > 0:
                    # If cargo is occupied by other materials, offload first to clear storage bins
                    if hasattr(self.vehicle, "cargo") and self.vehicle.cargo.count() > 0:
                        if self.cargo_count(required_item) == 0:
                            self.unload_cargo()

                    # Calculate batch needed across upcoming same-material jobs, capped by vehicle cargo capacity
                    free_space = 50
                    if hasattr(self.vehicle, "cargo"):
                        try:
                            free_space = max(0, self.vehicle.cargo.capacity() - self.vehicle.cargo.count())
                        except Exception as error:
                            swallowed("pioneer.PioneerController.run_construction_loop: self.vehicle.cargo.capacity", error)
                            free_space = 50

                    batch_needed = construction_plan.batch_count(target_jobs, required_item, max_limit=free_space)
                    batch_needed = max(required_count, batch_needed)

                    # Check if we already have the materials loaded
                    if self.cargo_count(required_item) < required_count:
                        self.log.start(f"[{self.name}] Stocking up to {batch_needed}x {required_item} for chained construction.")
                        loaded = self.load_construction_materials(target_job["job"], target_count=batch_needed)
                        self.log.end(f"[{self.name}] Stocking {'done' if loaded else 'failed'}.")
                        if not loaded:
                            # required_item genuinely isn't obtainable right now (e.g. Inventory
                            # empty and nothing produces it yet) -- defer this job rather than
                            # retrying it forever and starving every other pending job behind it
                            # in the list (failed_jobs clears once no other option remains).
                            self.log.level("warn").print(f"[{self.name}] Could not load materials for job {job_id}; deferring to try other pending jobs.")
                            failed_jobs.add(job_id)
                            self.release_target_claim(self.construction_claim_key(job_id))
                            flush_all()
                            sleep(2.0)
                            continue
                    else:
                        # Already have materials loaded; avoid rapid cycling
                        self.log.debug(f"[{self.name}] run_construction_loop(): {required_item} already loaded for job {job_id}; waiting a beat before retry.")
                        flush_all()
                        sleep(2.0)
                else:
                    # Deconstruction job - ensure cargo has space for reclaimed materials
                    self.log.debug(f"[{self.name}] run_construction_loop(): deconstruction job {job_id}, no materials required.")
                    if hasattr(self.vehicle, "cargo") and self.vehicle.cargo.full():
                        self.unload_cargo()

            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Pioneer loop exception: {e}")
                try:
                    self.vehicle.nav.brake()
                except Exception as error:
                    swallowed("pioneer.PioneerController.run_construction_loop: self.vehicle.nav.brake", error)
                # Release any construction job claim on failure -- run_construction_loop()
                # doesn't use self.current_target_key at all (unlike mining/survey), so
                # this releases every claim this Pioneer holds; harmless since a
                # Constructor Pioneer only ever runs this one loop.
                try:
                    self.release_target_claim()
                except Exception as error:
                    swallowed("pioneer.PioneerController.run_construction_loop: self.release_target_claim", error)
                flush_all()
                sleep(5.0)

    def run_mining_loop(self):
        """
        Continuous autonomous mining loop for a Pioneer equipped with an
        Industrial/Heavy Drill Module. Mounting the drill is an explicit
        operator action (mount_hardware() or the Control Panel) -- this loop
        only checks for one, it never mounts one itself. Handles the hardness
        tiers a Rover's basic drill can't reach, deprioritizing hardness <=
        ROVER_PREFERRED_MAX_HARDNESS sites (vehicle_mining.py) so Rovers get first
        pick of easy ore while this Pioneer still falls back to it if nothing
        harder is currently pending.
        """
        self.log.print(f"Pioneer Mining Controller ({self.name}) online. Assigned base slot: {self.assigned_slot_coords}.")
        while True:
            reset_all()
            try:
                if self.handle_recall_if_active():
                    flush_all()
                    sleep(5.0)
                    continue

                if not hasattr(self.vehicle, "drill"):
                    self.log.level("warn").print(f"[{self.name}] No Drill Module mounted; mining role idle. Mount an Industrial/Heavy Drill to begin.")
                    self.publish_telemetry("IDLE_NO_DRILL")
                    flush_all()
                    sleep(30.0)
                    continue

                # Step 1: Ensure fully charged before leaving base. Only
                # applies when actually at base -- a reload mid-trip must not
                # detour all the way home just to satisfy this check before
                # resuming its claimed target.
                if self.is_at_base():
                    _, _, lvl = self.get_battery()
                    if lvl < 0.95:
                        self.log.print(f"[{self.name}] Battery at {lvl*100:.0f}%. Recharging to 100% before launch...")
                        self.recharge_at_station(target_level=1.0)
                    self.handle_upgrade_cycle_if_idle()

                # A target restored from a saved mission after a script
                # reload (see vehicle_claims.py) means cargo aboard right now
                # is expected mid-mission WIP, not stale leftovers -- Step 2
                # below must not force a return-to-base detour for it, or a
                # reload mid-trip drives all the way home just to turn right
                # back around. The mission's own Step 6/7 already returns and
                # unloads once mining actually finishes.
                has_resumable_target = bool(self.current_target_key and self.current_target and self.current_target.get("coords"))

                # A mismatch between cargo already aboard and the resumed
                # target's own ore means blindly continuing would mine a
                # *different* material straight into the same hold -- cargo
                # isn't material-locked (see cargo_matches_target() in
                # vehicle_mining.py), so nothing would reject it, it would just waste
                # capacity and leave a confusing mixed load. Fall through to
                # the normal Step 2 unload-first path instead; the resumed
                # target itself is untouched (current_target_key stays set),
                # so Step 3 still resumes it right after, just with clean cargo.
                if has_resumable_target and self.current_target and not self.cargo_matches_target(self.current_target):
                    self.log.print(f"[{self.name}] Cargo holds a different material than the resumed target's {self.current_target.get('harvest_item')}; unloading before resuming.")
                    has_resumable_target = False

                # Step 2: Ensure cargo is empty before launch. "inventory" is
                # only a valid freight endpoint while parked at the home
                # outpost's service area -- cargo can still be aboard here
                # after a mid-trip interruption (e.g. a rescue drone charges
                # a stranded vehicle in place, it does not drive it home), so
                # drive home first rather than attempting the transfer from
                # wherever the vehicle currently stands.
                if not has_resumable_target and self.vehicle.cargo.count() > 0:
                    if not self.is_at_base():
                        self.log.print(f"[{self.name}] Cargo aboard but not at base (resuming after an interruption). Returning to base first.")
                        if not self.return_to_base():
                            self.log.level("warn").print(f"[{self.name}] Return trip incomplete this cycle; will retry.")
                            flush_all()
                            sleep(5.0)
                            continue
                    if self.unload_cargo() < 0:
                        self.publish_telemetry("WAITING_INVENTORY_SPACE")
                        flush_all()
                        sleep(10.0)
                        continue

                # Step 3: Select safe target with exclusive claim, preferring
                # sites only this Pioneer's drill can reach.
                if has_resumable_target and self.current_target:
                    self.log.print(f"[{self.name}] Resuming previously claimed target '{self.current_target_key}' after reload.")
                    target = self.current_target
                    budget = self.calculate_trip_energy(
                        target["coords"],
                        planned_drill_units=10,
                        mine_item_id=target.get("harvest_item"),
                        mine_purity=target.get("purity"),
                    )
                else:
                    candidates = self.build_mineral_site_candidates(deprioritize_hardness_at_or_below=ROVER_PREFERRED_MAX_HARDNESS)
                    target, budget, _ = self.select_best_mining_target(candidates, reserve_demand=True)

                if not target or not budget:
                    self.log.print(f"[{self.name}] No mining target: no reachable mineral site currently matches demand. Standing by at base slot.")
                    self.publish_telemetry("IDLE_AT_BASE")
                    flush_all()
                    sleep(15.0)
                    continue

                self.log.start(f"[{self.name}] Mining trip to {target['name']}")
                outcome = self._run_mining_trip(target, budget)
                self.log.end(f"[{self.name}] {outcome}")
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Mining loop exception: {e}. Executing emergency failsafe brake.")
                try:
                    self.vehicle.nav.brake()
                except Exception as error:
                    swallowed("pioneer.PioneerController.run_mining_loop: self.vehicle.nav.brake", error)
                try:
                    self.release_target_claim()
                    if self.current_target_reserved:
                        mining_reservations.release_yield(self.name)
                        self.current_target_reserved = False
                except Exception as error:
                    swallowed("pioneer.PioneerController.run_mining_loop: self.release_target_claim", error)
                flush_all()
                sleep(5.0)

    def _run_mining_trip(self, target, budget):
        """Steps 4-7 of a mining expedition for a reserved target. Returns a short outcome for the enclosing log block."""
        coords = target["coords"]
        self.log.print(
            f"[{self.name}] Reserved {target['name']} to harvest "
            f"{target['harvest_item']} for {target['reason']} at {coords} "
            f"(Est. trip cost: {budget['total_required_wh']:.1f} Wh)."
        )
        self.set_intent(fleet_intent.describe("mining", [target["harvest_item"]], at=target["name"], root=fleet_intent.haul_root([target["harvest_item"]], HOME_OUTPOST_ID)))
        self.publish_telemetry("OUTBOUND", target["name"])

        # Step 4: Drive to target (using intermediate recharge stops if needed)
        if not self.drive_with_recharge(coords[0], coords[1]):
            self.log.level("warn").print(f"[{self.name}] Could not safely complete outbound trip. Returning home.")
            self.return_to_base()
            return "outbound trip failed"

        # Step 5: Mine (recharges and resumes in place as needed)
        self.mine_until_full_or_exhausted(coords, max_units=target.get("estimated_units"))

        # Step 6: Return to base (releases target claim upon return).
        # A failed return (e.g. a rescue interrupts drive_to() mid-trip)
        # must not fall through to Step 7 -- unload_cargo() requires
        # actually being at the home outpost's service area, and will
        # just fail with "not_at_target" otherwise.
        if not self.return_to_base():
            self.log.level("warn").print(f"[{self.name}] Return trip incomplete this cycle; will retry.")
            flush_all()
            sleep(5.0)
            return "return trip incomplete"

        # Back at base -- release the claim regardless of how this trip
        # ended so the next cycle always re-evaluates fresh demand
        # instead of blindly resuming the same site forever.
        self.release_target_claim()
        if self.current_target_reserved:
            mining_reservations.release_yield(self.name)
            self.current_target_reserved = False

        # Step 7: Offload and recharge
        if self.unload_cargo() < 0:
            self.publish_telemetry("WAITING_INVENTORY_SPACE")
            flush_all()
            sleep(10.0)
            return "waiting for inventory space"
        self.recharge_at_station(target_level=1.0)
        self.publish_telemetry("READY_AT_BASE")
        self.log.print(f"[{self.name}] Mining expedition complete and Pioneer secured at base.")
        return "mining expedition complete"
