# Shared Library for Pioneer Multipurpose Heavy Vehicle Automation
# Inherits from VehicleController (lib/vehicle.py).
# Adds specialized support for Pioneer's 8 modular mount slots,
# Constructor Module field operations (pipes, power lines, outposts, caps),
# and heavy expedition & infrastructure logistics.

from archive import archive
from vehicle import VehicleController

class PioneerController(VehicleController):
    """
    Automated Heavy Field Vehicle & Constructor Controller for Pioneer chassis.
    Extends VehicleController with field construction, module slot management,
    infrastructure deployment (pipes, power lines, outposts), and deep expeditions.
    """
    def __init__(self, vehicle, home_coords=(0, 0), cruise_throttle=0.5):
        super().__init__(vehicle, home_coords=home_coords, cruise_throttle=cruise_throttle)

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
        Drives within interaction range of a construction blueprint and executes it.
        Blueprints can build outposts, pumps, well caps, power lines, and pipe networks.
        Caller must ensure required cargo is loaded first; see load_construction_materials().
        """
        if not hasattr(self.vehicle, "constructor"):
            print(f"[{self.name}] Error: No ConstructorModule mounted on this Pioneer!")
            return False

        if coords:
            print(f"[{self.name}] Driving to construction site at {coords}...")
            reached = self.drive_with_recharge(coords[0], coords[1], precision=2.0)
            if not reached:
                print(f"[{self.name}] Could not reach construction site at {coords} safely.")
                return False

        if hasattr(self.vehicle, "nav"):
            try:
                self.vehicle.nav.brake()
            except Exception:
                pass

        print(f"[{self.name}] Executing blueprint '{blueprint_id}'...")
        self.publish_telemetry("CONSTRUCTING", blueprint_id)
        res = self.vehicle.constructor.execute(blueprint_id)
        print(f"[{self.name}] Constructor result: {res.status} - {res.message}")

        # If construction was paused or ran out of power, recharge at nearest station and retry!
        if res.status in ["paused_no_power", "paused"]:
            print(f"[{self.name}] Construction paused ({res.status}). Diverting to nearest station to recharge.")
            nearest_cs, _ = self.get_nearest_charging_station()
            if self.drive_to(nearest_cs[0], nearest_cs[1], precision=1.0):
                self.recharge_at_station(target_level=1.0, station_coords=nearest_cs)
                if coords:
                    print(f"[{self.name}] Resuming construction at {coords} after recharge...")
                    if self.drive_with_recharge(coords[0], coords[1], precision=2.0):
                        if hasattr(self.vehicle, "nav"):
                            try:
                                self.vehicle.nav.brake()
                            except Exception:
                                pass
                        res = self.vehicle.constructor.execute(blueprint_id)
                        print(f"[{self.name}] Constructor retry result: {res.status} - {res.message}")

        return res.status == "ok"

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
        """Loads required_item from home Inventory into cargo, aiming for
        target_count (e.g. a whole chain of upcoming same-material jobs) but
        succeeding once this job's own required_count is met, since Inventory
        may not have the full batch on hand. Clamps the load request to available
        cargo capacity to prevent 'target_full' transfer rejections."""
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

        connect_result = self.vehicle.input.connect("inventory")
        if connect_result.status != "ok":
            print(f"[{self.name}] Could not connect to Inventory to load {required_item}: {connect_result.status} - {connect_result.message}")
            return False
        take_result = self.vehicle.input.take(required_item, missing)
        if take_result.status not in ["ok", "partial"]:
            print(f"[{self.name}] Could not load {required_item} from Inventory: {take_result.status} - {take_result.message}")
            return False
        if take_result.moved > 0:
            print(f"[{self.name}] Loaded {take_result.moved}x {required_item} for construction (stocking toward {goal} for chained jobs).")
        return self.cargo_count(required_item) >= required_count



    def find_local_store(self, outpost_id):
        """Find Inventory at home or a local warehouse/bin at an outpost."""
        if outpost_id in [None, "home", "inventory"]:
            return "inventory"
        network = get_component("outpost_network")
        if not network or not hasattr(network, "outposts"):
            return None
        try:
            for outpost in network.outposts():
                if getattr(outpost, "id", None) != outpost_id:
                    continue
                for type_id in ["large_warehouse", "warehouse", "storage_bin"]:
                    for building in outpost.buildings(type_id):
                        return building.id
        except Exception:
            pass
        return None

    def find_outpost_coords(self, outpost_id):
        """Returns an outpost anchor coordinate for transport routing."""
        if outpost_id in [None, "home", "inventory"]:
            return self.assigned_slot_coords
        network = get_component("outpost_network")
        if network and hasattr(network, "outposts"):
            try:
                for outpost in network.outposts():
                    if getattr(outpost, "id", None) == outpost_id:
                        return (outpost.x, outpost.y)
            except Exception:
                pass
        return None

    def transport_once(self, route):
        """Move one configured material load between two local stores."""
        item_id = route.get("item_id")
        requested = route.get("count", 0)
        source_outpost = route.get("source_outpost", "home")
        destination_outpost = route.get("destination_outpost", "home")
        if not item_id or requested <= 0:
            print(f"[{self.name}] Transport route needs item_id and positive count.")
            return False

        source_store = self.find_local_store(source_outpost)
        destination_store = self.find_local_store(destination_outpost)
        source_coords = self.find_outpost_coords(source_outpost)
        destination_coords = self.find_outpost_coords(destination_outpost)
        if not source_store or not destination_store or not source_coords or not destination_coords:
            print(f"[{self.name}] Transport route unavailable: check outposts and local storage.")
            return False

        if self.vehicle.cargo.count() > 0:
            self.unload_cargo()
            if self.vehicle.cargo.count() > 0:
                print(f"[{self.name}] Transport blocked: cargo hold is not empty.")
                return False

        if not self.drive_to(source_coords[0], source_coords[1]):
            return False
        self.vehicle.nav.brake()
        if not hasattr(self.vehicle, "input"):
            print(f"[{self.name}] Transport requires a Pioneer input port and Auto Feeders.")
            return False
        connect_result = self.vehicle.input.connect(source_store)
        if connect_result.status != "ok":
            print(f"[{self.name}] Could not connect transport source: {connect_result.status} - {connect_result.message}")
            return False
        take_result = self.vehicle.input.take(item_id, requested)
        if take_result.status not in ["ok", "partial"] or take_result.moved <= 0:
            print(f"[{self.name}] Could not load {item_id}: {take_result.status} - {take_result.message}")
            return False
        print(f"[{self.name}] Loaded {take_result.moved}x {item_id} from {source_outpost}.")

        if not self.drive_to(destination_coords[0], destination_coords[1]):
            return False
        self.vehicle.nav.brake()
        if not hasattr(self.vehicle, "output"):
            print(f"[{self.name}] Transport requires a Pioneer output port and Auto Feeders.")
            return False
        connect_result = self.vehicle.output.connect(destination_store)
        if connect_result.status != "ok":
            print(f"[{self.name}] Could not connect transport destination: {connect_result.status} - {connect_result.message}")
            return False
        moved_total = 0
        for stack in self.vehicle.cargo.stacks():
            send_result = self.vehicle.output.send(stack.id, stack.count)
            if send_result.status in ["ok", "partial"]:
                moved_total += send_result.moved
        print(f"[{self.name}] Delivered {moved_total}x {item_id} to {destination_outpost}.")
        return moved_total > 0

    def run_transport_loop(self, poll_interval=10.0):
        """Run the human-configured transport route from the Data Archive."""
        print(f"Pioneer Transport Controller ({self.name}) online. Awaiting route configuration.")
        while True:
            try:
                route = archive.get("pioneer.transport.route", {}) or {}
                if route:
                    self.publish_telemetry("TRANSPORT", f"{route.get('item_id', 'unknown')} route")
                    self.transport_once(route)
                else:
                    self.publish_telemetry("IDLE_AT_BASE", "no transport route")
                sleep(poll_interval)
            except Exception as error:
                print(f"[{self.name}] Transport exception: {error}")
                try:
                    self.vehicle.nav.brake()
                except Exception:
                    pass
                sleep(poll_interval)

    def run_construction_loop(self):
        """Continuously polls pending and paused construction blueprints and executes available builds."""
        print(f"Pioneer Controller ({self.name}) online. Monitoring construction blueprints.")
        bp_component = get_component("construction_blueprint")
        failed_jobs = set()

        while True:
            try:
                # 1. Base Battery & Staging: If parked at home, ensure charged before departing
                if self.distance_to_home() <= 3.0:
                    _, _, lvl = self.get_battery()
                    if lvl < 0.90:
                        self.recharge_at_station(target_level=1.0)

                # 2. Field Battery Floor: If energy drops near return reserve, return to nearest station
                curr_wh, _, _ = self.get_battery()
                if curr_wh <= self.energy_needed_to_return_now():
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
                    budget = self.calculate_trip_energy(coords, planned_drill_units=0, planned_scans=0)
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
                    candidate = None
                    for job in matching_jobs:
                        coords = self.extract_coords(getattr(job, "position", None))
                        if not coords:
                            continue
                        budget = self.calculate_trip_energy(coords, planned_drill_units=0, planned_scans=0)
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
                                # Even at full charge, none of the matching jobs can be reached within battery capacity!
                                req_details = []
                                for job in matching_jobs:
                                    j_id = getattr(job, "id", getattr(job, "blueprint_id", "unknown"))
                                    j_coords = self.extract_coords(getattr(job, "position", None))
                                    if j_coords:
                                        j_budget = self.calculate_trip_energy(j_coords, planned_drill_units=0, planned_scans=0)
                                        req_details.append(f"{j_id} ({j_budget['total_required_wh']:.1f} Wh)")
                                    else:
                                        req_details.append(f"{j_id}")
                                    failed_jobs.add(j_id)
                                print(f"[{self.name}] Advisory: Matching construction job(s) exceed maximum battery range ({cap_wh:.1f} Wh): {', '.join(req_details)}.")
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
                        # Check whether job can be serviced from the closest charging station in the network
                        st_near, _ = self.get_nearest_charging_station(from_coords=j_coords)
                        dist_station_leg = self.distance_between(st_near, j_coords) * 2.0
                        required_wh = (dist_station_leg * self.wh_per_meter * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH
                        if required_wh > cap_wh:
                            if j_id not in failed_jobs:
                                print(f"[{self.name}] Construction job '{j_id}' at {j_coords} permanently exceeds battery capacity from nearest station ({required_wh:.1f} Wh required, {cap_wh:.1f} Wh max capacity). Marking failed.")
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
                            print(f"[{self.name}] Could not load materials for job {job_id}; retrying in 10s.")
                            sleep(10.0)
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
