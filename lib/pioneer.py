# Shared Library for Pioneer Multipurpose Heavy Vehicle Automation
# Inherits from VehicleController (lib/vehicle.py).
# Adds specialized support for Pioneer's 8 modular mount slots,
# Constructor Module field operations (pipes, power lines, outposts, caps),
# and heavy expedition & infrastructure logistics.

from archive import archive
from vehicle import VehicleController
from mining import ROVER_PREFERRED_MAX_HARDNESS
from storage import take_item

class PioneerController(VehicleController):
    """
    Automated Heavy Field Vehicle & Constructor Controller for Pioneer chassis.
    Extends VehicleController with field construction, module slot management,
    infrastructure deployment (pipes, power lines, outposts), and deep expeditions.
    """
    # Minimum construction progress a trip should budget for so a job finishes
    # in roughly 4 round trips rather than dozens of drive-there-do-almost-
    # nothing-drive-back cycles. Capped at whatever progress remains.
    TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25

    def __init__(self, vehicle, home_base=None, cruise_throttle=None):
        super().__init__(vehicle, home_base=home_base, cruise_throttle=cruise_throttle)

    def get_construction_progress(self, blueprint_id):
        """Current 0-1 progress for a blueprint id, checking pending/active/paused lists."""
        bp = get_component("construction_blueprint")
        if not bp:
            return 0.0
        for getter_name in ("pending_constructions", "active_constructions", "paused_constructions"):
            getter = getattr(bp, getter_name, None)
            if not getter:
                continue
            try:
                for c in getter():
                    if getattr(c, "id", None) == blueprint_id:
                        return getattr(c, "progress", 0.0) or 0.0
            except Exception:
                pass
        return 0.0

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
                print(f"[{self.name}] Error reading modules: {e}")
        return []

    def mount_hardware(self, slot_index, module_item_id):
        """Mounts a module into the specified slot index while at a base/outpost service area."""
        if hasattr(self.vehicle, "mount"):
            res = self.vehicle.mount(slot_index, module_item_id)
            print(f"[{self.name}] Mount slot {slot_index} -> '{module_item_id}': {res.status} ({res.message})")
            return res.status == "ok"
        return False

    def unmount_hardware(self, slot_index):
        """Unmounts a module from the specified slot index back to inventory."""
        if hasattr(self.vehicle, "unmount"):
            res = self.vehicle.unmount(slot_index)
            print(f"[{self.name}] Unmount slot {slot_index}: {res.status} ({res.message})")
            return res.status == "ok"
        return False

    def execute_construction(self, blueprint_id, coords=None):
        """
        Drives within interaction range of a construction blueprint and executes it,
        recharging on-site and resuming for as long as real progress keeps being made.
        The energy budget check before departing only commits to
        TARGET_CONSTRUCTION_PROGRESS_PER_TRIP of the job, so running low on battery
        mid-build here is normal and expected, not a failure -- returning early
        would waste the trip and abandon a perfectly workable job. Blueprints can
        build outposts, pumps, well caps, power lines, and pipe networks.
        Caller must ensure required cargo is loaded first; see load_construction_materials().

        Returns False only for a genuine rejection (blocked, insufficient materials,
        etc.) or an inability to physically reach the site/station -- never merely
        because the job is still incomplete and needs another recharge round later.
        """
        if not hasattr(self.vehicle, "constructor"):
            print(f"[{self.name}] Error: No ConstructorModule mounted on this Pioneer!")
            return False

        if coords:
            print(f"[{self.name}] Driving to construction site at {coords}...")
            if not self.drive_with_recharge(coords[0], coords[1], precision=2.0):
                print(f"[{self.name}] Could not reach construction site at {coords} safely.")
                return False

        if hasattr(self.vehicle, "nav"):
            try:
                self.vehicle.nav.brake()
            except Exception:
                pass

        while True:
            print(f"[{self.name}] Executing blueprint '{blueprint_id}'...")
            self.publish_telemetry("CONSTRUCTING", blueprint_id)
            progress_before = self.get_construction_progress(blueprint_id)
            wh_before, _, _ = self.get_battery()
            res = self.vehicle.constructor.execute(blueprint_id)
            progress_after = self.get_construction_progress(blueprint_id)
            self.calibrate_wh_per_progress(progress_after - progress_before, wh_before - self.get_battery()[0])
            print(f"[{self.name}] Constructor result: {res.status} - {res.message}")

            if res.status == "ok":
                return True
            if res.status not in ("paused_no_power", "paused"):
                return False  # genuine rejection, not a power issue -- don't keep retrying

            if progress_after <= progress_before:
                print(f"[{self.name}] No progress made this cycle ({res.status}); leaving paused for a later attempt.")
                return True

            print(f"[{self.name}] Construction paused ({res.status}) at {progress_after*100:.0f}% progress. Recharging nearby and resuming.")
            nearest_cs, _ = self.get_nearest_charging_station()
            if not self.drive_to(nearest_cs[0], nearest_cs[1], precision=1.0):
                print(f"[{self.name}] Could not reach charging station to resume construction; leaving paused for a later attempt.")
                return True
            self.recharge_at_station(target_level=1.0, station_coords=nearest_cs)
            if coords and not self.drive_with_recharge(coords[0], coords[1], precision=2.0):
                print(f"[{self.name}] Could not return to construction site after recharge; leaving paused for a later attempt.")
                return True
            if hasattr(self.vehicle, "nav"):
                try:
                    self.vehicle.nav.brake()
                except Exception:
                    pass

    def cargo_count(self, item_id):
        """Units of item_id currently sitting in the Pioneer's cargo, across all stacks."""
        try:
            return sum(getattr(s, "count", 0) for s in self.vehicle.cargo.stacks() if getattr(s, "id", None) == item_id)
        except Exception:
            return 0

    def batch_required_count(self, pending, item_id, max_limit=None):
        """Sums required_count across pending jobs that need item_id,
        up to optional max_limit, so a route split into many segment jobs
        can be stocked in one Inventory trip instead of one per job."""
        total = 0
        for job in pending:
            job_item = getattr(job, "required_item", None)
            if job_item == item_id:
                total += max(0, getattr(job, "required_count", 0))
                if max_limit is not None and total >= max_limit:
                    return max_limit
        return total

    def load_construction_materials(self, job, target_count=None):
        """Loads required_item from home Inventory or a Warehouse into cargo,
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
            except Exception:
                pass

        if have >= goal and have >= required_count:
            return True

        if not hasattr(self.vehicle, "input"):
            print(f"[{self.name}] Cannot load {required_item}: no input port / Auto Feeders.")
            return False

        missing = max(0, goal - have)
        if missing <= 0:
            return have >= required_count

        moved = take_item(self.vehicle.input, required_item, missing)
        if moved > 0:
            print(f"[{self.name}] Loaded {moved}x {required_item} for construction (stocking toward {goal} for chained jobs).")
        elif self.cargo_count(required_item) < required_count:
            print(f"[{self.name}] Could not load {required_item}: not found in Inventory or any Warehouse.")
        return self.cargo_count(required_item) >= required_count

    def run_construction_loop(self):
        """Continuously polls pending and paused construction blueprints and executes available builds."""
        print(f"Pioneer Controller ({self.name}) online. Monitoring construction blueprints.")
        bp_component = get_component("construction_blueprint")
        failed_jobs = set()

        while True:
            try:
                if self.handle_recall_if_active():
                    sleep(5.0)
                    continue

                # 1. Base Battery & Staging: If parked at home, ensure charged before departing
                if self.is_at_base():
                    _, _, lvl = self.get_battery()
                    if lvl < 0.90:
                        self.recharge_at_station(target_level=1.0)

                # 2. Field Battery Floor: proactively head back with enough reserve for a
                # normal-speed return, not just the bare survival floor (which would leave
                # conserve mode nothing to spend but the slowest possible crawl home).
                curr_wh, _, _ = self.get_battery()
                if curr_wh <= self.energy_needed_to_return_comfortably():
                    print(f"[{self.name}] Return reserve reached in field; returning to nearest station to recharge.")
                    nearest_st, _ = self.get_nearest_charging_station()
                    self.drive_to(nearest_st[0], nearest_st[1], precision=1.0)
                    self.recharge_at_station(target_level=1.0, station_coords=nearest_st)
                    continue

                # Query paused and pending constructions
                paused = []
                pending = []
                if bp_component:
                    if hasattr(bp_component, "paused_constructions"):
                        try:
                            paused = bp_component.paused_constructions() or []
                        except Exception:
                            paused = []
                    if hasattr(bp_component, "pending_constructions"):
                        try:
                            pending = bp_component.pending_constructions() or []
                        except Exception:
                            pending = []

                if not paused and not pending:
                    if failed_jobs:
                        failed_jobs.clear()
                    if self.distance_to_home() > 3.0:
                        self.return_to_base()
                    self.publish_telemetry("IDLE_AT_BASE")
                    sleep(10.0)
                    continue

                # 3. Check Paused Constructions first (resuming already-paid work)
                active_job = None
                for job in paused:
                    job_id = getattr(job, "id", None)
                    if not job_id or job_id in failed_jobs:
                        continue
                    coords = self.extract_coords(getattr(job, "position", None))
                    if not coords:
                        continue
                    budget = self.calculate_trip_energy(
                        coords, planned_drill_units=0, planned_scans=0,
                        planned_construction_progress=self.planned_progress_for_job(job),
                    )
                    if budget["is_achievable"]:
                        active_job = job
                        break
                    elif self.distance_to_home() > 3.0:
                        # Cannot reach safely from current field position; recharge at nearest station
                        print(f"[{self.name}] Insufficient energy to reach paused job safely; recharging at nearest station.")
                        nearest_st, _ = self.get_nearest_charging_station()
                        self.drive_to(nearest_st[0], nearest_st[1], precision=1.0)
                        self.recharge_at_station(target_level=1.0, station_coords=nearest_st)
                        break

                if active_job:
                    job_id = getattr(active_job, "id", None)
                    coords = self.extract_coords(getattr(active_job, "position", None))
                    print(f"[{self.name}] Resuming paused construction job: {job_id} at {coords}.")
                    if not self.execute_construction(job_id, coords):
                        failed_jobs.add(job_id)
                        sleep(2.0)
                    continue

                # 4. Check Pending Constructions matching current cargo
                current_pos = self.get_position()
                matching_jobs = []
                for job in pending:
                    job_id = getattr(job, "id", getattr(job, "blueprint_id", None))
                    if not job_id or job_id in failed_jobs:
                        continue
                    req_item = getattr(job, "required_item", None)
                    req_count = getattr(job, "required_count", 0)
                    # Deconstruction (req_count <= 0 or req_item None) or items already in cargo
                    if not req_item or req_count <= 0 or self.cargo_count(req_item) >= req_count:
                        matching_jobs.append(job)

                if matching_jobs:
                    # Sort matching jobs by proximity to current vehicle coordinates
                    matching_jobs.sort(key=lambda j: self.distance_between(current_pos, self.extract_coords(getattr(j, "position", None)) or (9999, 9999)))
                    # Gate on the speedmode throttle floor, not the typical calibrated rate:
                    # drive_with_recharge()/select_cruise_throttle() will pick whatever throttle
                    # the leg actually needs, so a job only reachable by conserving hard should
                    # still be attempted rather than rejected against a faster-than-necessary estimate.
                    candidate = None
                    for job in matching_jobs:
                        coords = self.extract_coords(getattr(job, "position", None))
                        if not coords:
                            continue
                        budget = self.calculate_trip_energy(
                            coords, planned_drill_units=0, planned_scans=0,
                            planned_construction_progress=self.planned_progress_for_job(job),
                            wh_per_meter=self.minimum_wh_per_meter(),
                        )
                        if budget["is_achievable"]:
                            candidate = job
                            break

                    if candidate:
                        job_id = getattr(candidate, "id", getattr(candidate, "blueprint_id", None))
                        coords = self.extract_coords(getattr(candidate, "position", None))
                        print(f"[{self.name}] Executing chained construction job: {job_id} at {coords}.")
                        if not self.execute_construction(job_id, coords):
                            failed_jobs.add(job_id)
                            sleep(2.0)
                        continue
                    else:
                        # We have cargo matching pending jobs, but cannot reach any right now
                        nearest_st, _ = self.get_nearest_charging_station()
                        if self.distance_between(current_pos, nearest_st) > 3.0:
                            print(f"[{self.name}] Insufficient energy to reach next construction site; recharging at nearest station.")
                            self.drive_to(nearest_st[0], nearest_st[1], precision=1.0)
                            self.recharge_at_station(target_level=1.0, station_coords=nearest_st)
                            continue
                        else:
                            curr_wh, cap_wh, lvl = self.get_battery()
                            if lvl < 0.98:
                                print(f"[{self.name}] At station with materials but need charge ({lvl*100:.0f}%); recharging to full.")
                                self.recharge_at_station(target_level=1.0, station_coords=nearest_st)
                                continue
                            else:
                                # candidate selection above already gated on minimum_wh_per_meter()
                                # (the speedmode throttle floor), so reaching here means none of
                                # these jobs are reachable even at the slowest possible throttle.
                                req_details = []
                                for job in matching_jobs:
                                    j_id = getattr(job, "id", getattr(job, "blueprint_id", "unknown"))
                                    j_coords = self.extract_coords(getattr(job, "position", None))
                                    if j_coords:
                                        j_budget = self.calculate_trip_energy(
                                            j_coords, planned_drill_units=0, planned_scans=0,
                                            planned_construction_progress=self.planned_progress_for_job(job),
                                            wh_per_meter=self.minimum_wh_per_meter(),
                                        )
                                        req_details.append(f"{j_id} ({j_budget['total_required_wh']:.1f} Wh)")
                                    else:
                                        req_details.append(f"{j_id}")
                                    failed_jobs.add(j_id)
                                print(f"[{self.name}] Advisory: Matching construction job(s) exceed maximum battery range even at minimum throttle ({cap_wh:.1f} Wh): {', '.join(req_details)}.")
                                sleep(5.0)
                                continue

                # 5. No matching jobs with current cargo: return to base, offload, and restock
                # Filter out jobs that permanently exceed maximum vehicle battery capacity from nearest station
                _, cap_wh, _ = self.get_battery()
                achievable_targets = []
                for j in pending:
                    j_id = getattr(j, "id", getattr(j, "blueprint_id", None))
                    if not j_id or j_id in failed_jobs:
                        continue
                    j_coords = self.extract_coords(getattr(j, "position", None))
                    if j_coords:
                        # Check whether job can be serviced from the closest charging station in the
                        # network, at the speedmode throttle floor (cheapest possible Wh/m) -- that's
                        # the true bound for a "permanently" unreachable verdict, since conserve mode
                        # can always throttle down that far to stretch a tight round trip. Also budget
                        # for the minimum useful on-site progress (TARGET_CONSTRUCTION_PROGRESS_PER_TRIP),
                        # since a trip that can't build anything meaningful isn't worth taking either.
                        st_near, _ = self.get_nearest_charging_station(from_coords=j_coords)
                        dist_station_leg = self.distance_between(st_near, j_coords) * 2.0
                        construction_wh = self.planned_progress_for_job(j) * self.wh_per_progress
                        required_wh = ((dist_station_leg * self.minimum_wh_per_meter()) + construction_wh) * self.SAFETY_MARGIN_MULTIPLIER + self.MIN_EMERGENCY_RESERVE_WH
                        if required_wh > cap_wh:
                            if j_id not in failed_jobs:
                                print(f"[{self.name}] Construction job '{j_id}' at {j_coords} permanently exceeds battery capacity from nearest station even at minimum throttle ({required_wh:.1f} Wh required, {cap_wh:.1f} Wh max capacity). Marking failed.")
                                failed_jobs.add(j_id)
                            continue
                    achievable_targets.append(j)

                target_jobs = achievable_targets
                if not target_jobs:
                    # All pending jobs currently marked failed; clear failure set and wait
                    failed_jobs.clear()
                    if self.distance_to_home() > 3.0:
                        self.return_to_base()
                    self.publish_telemetry("IDLE_AT_BASE")
                    sleep(10.0)
                    continue

                target_job = target_jobs[0]
                job_id = getattr(target_job, "id", getattr(target_job, "blueprint_id", None))
                required_item = getattr(target_job, "required_item", None)
                required_count = getattr(target_job, "required_count", 0)

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
                        except Exception:
                            free_space = 50

                    batch_needed = self.batch_required_count(target_jobs, required_item, max_limit=free_space)
                    batch_needed = max(required_count, batch_needed)

                    # Check if we already have the materials loaded
                    if self.cargo_count(required_item) < required_count:
                        print(f"[{self.name}] Stocking up to {batch_needed}x {required_item} for chained construction.")
                        if not self.load_construction_materials(target_job, target_count=batch_needed):
                            # required_item genuinely isn't obtainable right now (e.g. Inventory
                            # empty and nothing produces it yet) -- defer this job rather than
                            # retrying it forever and starving every other pending job behind it
                            # in the list (failed_jobs clears once no other option remains).
                            print(f"[{self.name}] Could not load materials for job {job_id}; deferring to try other pending jobs.")
                            failed_jobs.add(job_id)
                            sleep(2.0)
                            continue
                    else:
                        # Already have materials loaded; avoid rapid cycling
                        sleep(2.0)
                else:
                    # Deconstruction job - ensure cargo has space for reclaimed materials
                    if hasattr(self.vehicle, "cargo") and self.vehicle.cargo.full():
                        self.unload_cargo()

            except Exception as e:
                print(f"[{self.name}] Pioneer loop exception: {e}")
                try:
                    self.vehicle.nav.brake()
                except Exception:
                    pass
                sleep(5.0)

    def run_mining_loop(self):
        """
        Continuous autonomous mining loop for a Pioneer equipped with an
        Industrial/Heavy Drill Module. Mounting the drill is an explicit
        operator action (mount_hardware() or the Control Panel) -- this loop
        only checks for one, it never mounts one itself. Handles the hardness
        tiers a Rover's basic drill can't reach, deprioritizing hardness <=
        ROVER_PREFERRED_MAX_HARDNESS sites (mining.py) so Rovers get first
        pick of easy ore while this Pioneer still falls back to it if nothing
        harder is currently pending.
        """
        print(f"Pioneer Mining Controller ({self.name}) online. Assigned base slot: {self.assigned_slot_coords}.")
        while True:
            try:
                if self.handle_recall_if_active():
                    sleep(5.0)
                    continue

                if not hasattr(self.vehicle, "drill"):
                    print(f"[{self.name}] No Drill Module mounted; mining role idle. Mount an Industrial/Heavy Drill to begin.")
                    self.publish_telemetry("IDLE_NO_DRILL")
                    sleep(30.0)
                    continue

                # Step 1: Ensure fully charged before leaving base. Only
                # applies when actually at base -- a reload mid-trip must not
                # detour all the way home just to satisfy this check before
                # resuming its claimed target.
                if self.is_at_base():
                    _, _, lvl = self.get_battery()
                    if lvl < 0.95:
                        print(f"[{self.name}] Battery at {lvl*100:.0f}%. Recharging to 100% before launch...")
                        self.recharge_at_station(target_level=1.0)

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
                # mining.py), so nothing would reject it, it would just waste
                # capacity and leave a confusing mixed load. Fall through to
                # the normal Step 2 unload-first path instead; the resumed
                # target itself is untouched (current_target_key stays set),
                # so Step 3 still resumes it right after, just with clean cargo.
                if has_resumable_target and not self.cargo_matches_target(self.current_target):
                    print(f"[{self.name}] Cargo holds a different material than the resumed target's {self.current_target.get('harvest_item')}; unloading before resuming.")
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
                        print(f"[{self.name}] Cargo aboard but not at base (resuming after an interruption). Returning to base first.")
                        if not self.return_to_base():
                            print(f"[{self.name}] Return trip incomplete this cycle; will retry.")
                            sleep(5.0)
                            continue
                    if self.unload_cargo() < 0:
                        self.publish_telemetry("WAITING_INVENTORY_SPACE")
                        sleep(10.0)
                        continue

                # Step 3: Select safe target with exclusive claim, preferring
                # sites only this Pioneer's drill can reach.
                if has_resumable_target:
                    print(f"[{self.name}] Resuming previously claimed target '{self.current_target_key}' after reload.")
                    target = self.current_target
                    budget = self.calculate_trip_energy(
                        target["coords"],
                        planned_drill_units=10,
                        mine_item_id=target.get("harvest_item"),
                        mine_purity=target.get("purity"),
                    )
                else:
                    candidates = self.build_mineral_site_candidates(deprioritize_hardness_at_or_below=ROVER_PREFERRED_MAX_HARDNESS)
                    target, budget, _ = self.select_best_mining_target(candidates)

                if not target or not budget:
                    print(f"[{self.name}] No mining target: no reachable mineral site currently matches demand. Standing by at base slot.")
                    self.publish_telemetry("IDLE_AT_BASE")
                    sleep(15.0)
                    continue

                coords = target["coords"]
                print(
                    f"[{self.name}] Reserved {target['name']} to harvest "
                    f"{target['harvest_item']} for {target['reason']} at {coords} "
                    f"(Est. trip cost: {budget['total_required_wh']:.1f} Wh)."
                )
                self.publish_telemetry("OUTBOUND", target["name"])

                # Step 4: Drive to target (using intermediate recharge stops if needed)
                if not self.drive_with_recharge(coords[0], coords[1]):
                    print(f"[{self.name}] Could not safely complete outbound trip. Returning home.")
                    self.return_to_base()
                    continue

                # Step 5: Mine (recharges and resumes in place as needed)
                self.mine_until_full_or_exhausted(coords)

                # Step 6: Return to base (releases target claim upon return).
                # A failed return (e.g. a rescue interrupts drive_to() mid-trip)
                # must not fall through to Step 7 -- unload_cargo() requires
                # actually being at the home outpost's service area, and will
                # just fail with "not_at_target" otherwise.
                if not self.return_to_base():
                    print(f"[{self.name}] Return trip incomplete this cycle; will retry.")
                    sleep(5.0)
                    continue

                # Back at base -- release the claim regardless of how this trip
                # ended so the next cycle always re-evaluates fresh demand
                # instead of blindly resuming the same site forever (previously
                # only an explicit recall ever cleared it).
                self.release_target_claim()

                # Step 7: Offload and recharge
                if self.unload_cargo() < 0:
                    self.publish_telemetry("WAITING_INVENTORY_SPACE")
                    sleep(10.0)
                    continue
                self.recharge_at_station(target_level=1.0)
                self.publish_telemetry("READY_AT_BASE")
                print(f"[{self.name}] Mining expedition complete and Pioneer secured at base.")
            except Exception as e:
                print(f"[{self.name}] Mining loop exception: {e}. Executing emergency failsafe brake.")
                try:
                    self.vehicle.nav.brake()
                except Exception:
                    pass
                try:
                    self.release_target_claim()
                except Exception:
                    pass
                sleep(5.0)
