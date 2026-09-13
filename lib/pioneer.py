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
        """
        if not hasattr(self.vehicle, "constructor"):
            print(f"[{self.name}] Error: No ConstructorModule mounted on this Pioneer!")
            return False

        if coords:
            print(f"[{self.name}] Driving to construction site at {coords}...")
            reached = self.drive_to(coords[0], coords[1], precision=2.0)
            if not reached:
                print(f"[{self.name}] Could not reach construction site at {coords} safely.")
                return False

        print(f"[{self.name}] Executing blueprint '{blueprint_id}'...")
        self.publish_telemetry("CONSTRUCTING", blueprint_id)
        res = self.vehicle.constructor.execute(blueprint_id)
        print(f"[{self.name}] Constructor result: {res.status} - {res.message}")
        return res.status == "ok"

    def survey_spiral_points(self, step=None, start_index=0, max_points=160):
        """Yields indexed outward square-spiral waypoints spaced for the mounted sonar."""
        sonar = getattr(self.vehicle, "sonar", None)
        if not sonar:
            return

        if step is None:
            try:
                step = max(20.0, sonar.range() * 0.75)
            except Exception:
                step = 35.0

        x, y = self.assigned_slot_coords
        directions = [(1, 0), (0, 1), (-1, 0), (0, -1)]
        direction_index = 0
        leg_length = 1
        point_index = 0
        yielded = 0

        while yielded < max_points:
            for _ in range(2):
                dx, dy = directions[direction_index % len(directions)]
                for _ in range(leg_length):
                    x += dx * step
                    y += dy * step
                    if point_index >= start_index:
                        yield (point_index, x, y)
                        yielded += 1
                        if yielded >= max_points:
                            return
                    point_index += 1
                direction_index += 1
            leg_length += 1

    def save_survey_waypoint(self, point_index, coords, sites):
        """Publishes completed spiral progress to the shared Data Archive notebook."""
        site_summaries = []
        for site in sites:
            try:
                kind = site.kind() if hasattr(site, "kind") else "unknown"
            except Exception:
                kind = "unknown"
            site_summaries.append({
                "id": getattr(site, "id", None),
                "kind": kind,
                "item_id": getattr(site, "item_id", None),
            })

        def update_progress(current):
            progress = dict(current or {})
            waypoints = list(progress.get("waypoints", []))
            entry = {
                "index": point_index,
                "x": round(coords[0], 2),
                "y": round(coords[1], 2),
                "sites": site_summaries,
            }
            if not any(item.get("index") == point_index for item in waypoints):
                waypoints.append(entry)
            progress["waypoints"] = waypoints
            progress["next_index"] = max(point_index + 1, progress.get("next_index", 0))
            progress["last_completed"] = entry
            progress["updated_by"] = self.name
            return progress

        archive.transaction("pioneer.survey_spiral", {}, update_progress)

    def run_survey_loop(self, max_points=160):
        """Surveys an outward spiral while preserving a guaranteed return reserve."""
        if not hasattr(self.vehicle, "sonar"):
            print(f"[{self.name}] Survey loop requires a mounted Sonar Module.")
            return
        if not hasattr(self.vehicle, "nav"):
            print(f"[{self.name}] Survey loop requires a mounted Nav Module.")
            return

        print(f"Pioneer Survey Controller ({self.name}) online. Starting battery-safe spiral.")
        while True:
            try:
                _, _, level = self.get_battery()
                if level < 0.95:
                    self.recharge_at_station(target_level=1.0)

                progress = archive.get("pioneer.survey_spiral", {}) or {}
                start_index = progress.get("next_index", 0)
                completed = 0
                for point_index, target_x, target_y in self.survey_spiral_points(
                    start_index=start_index,
                    max_points=max_points,
                ):
                    if self.vehicle.is_being_rescued() if hasattr(self.vehicle, "is_being_rescued") else False:
                        print(f"[{self.name}] Rescue in progress; pausing survey loop.")
                        break

                    budget = self.calculate_trip_energy(
                        (target_x, target_y),
                        # A scan may survey several contacts; budget conservatively
                        # for the sweep plus follow-up survey work.
                        planned_scans=4,
                    )
                    if not budget["is_achievable"]:
                        print(f"[{self.name}] Spiral boundary reached at ({target_x:.1f}, {target_y:.1f}); returning home.")
                        break

                    self.publish_telemetry("SURVEY_OUTBOUND", f"{target_x:.1f},{target_y:.1f}")
                    if not self.drive_to(target_x, target_y):
                        print(f"[{self.name}] Could not safely reach spiral waypoint; returning home.")
                        break

                    # Never start a field action with only the driving reserve.
                    # Sonar scan/survey time can consume several Wh before the
                    # call returns control to this script.
                    scan_reserve = self.SONAR_WH_BUDGET * 4 * self.SAFETY_MARGIN_MULTIPLIER
                    if self.get_battery()[0] <= self.energy_needed_to_return_now() + scan_reserve:
                        print(f"[{self.name}] Insufficient energy for safe scan at ({target_x:.1f}, {target_y:.1f}); returning home.")
                        break

                    sites = self.scan_and_survey()
                    if self.vehicle.is_being_rescued() if hasattr(self.vehicle, "is_being_rescued") else False:
                        print(f"[{self.name}] Rescue started during scan; abandoning survey pass.")
                        break
                    self.save_survey_waypoint(point_index, (target_x, target_y), sites)
                    completed += 1

                    if self.get_battery()[0] < self.energy_needed_to_return_now():
                        print(f"[{self.name}] Return reserve reached after survey; returning home.")
                        break

                self.return_to_base()
                next_index = archive.get("pioneer.survey_spiral", {}).get("next_index", start_index)
                self.publish_telemetry("SURVEY_COMPLETE", f"{completed} waypoints; next {next_index}")
                print(f"[{self.name}] Survey pass complete ({completed} waypoints). Next spiral index: {next_index}. Recharging before continuing.")
                self.recharge_at_station(target_level=1.0)
                sleep(5.0)
            except Exception as e:
                print(f"[{self.name}] Survey loop exception: {e}. Returning home.")
                try:
                    self.vehicle.nav.brake()
                except Exception:
                    pass
                self.return_to_base()
                sleep(5.0)

    def run_construction_loop(self):
        """Continuously polls pending construction blueprints and executes available builds."""
        print(f"Pioneer Controller ({self.name}) online. Monitoring construction blueprints.")
        bp_component = get_component("construction_blueprint")

        while True:
            try:
                # Ensure vehicle is charged before setting off
                _, _, lvl = self.get_battery()
                if lvl < 0.90:
                    self.recharge_at_station(target_level=1.0)

                pending = []
                if bp_component and hasattr(bp_component, "pending_constructions"):
                    try:
                        pending = bp_component.pending_constructions()
                    except Exception:
                        pass

                if pending:
                    job = pending[0]
                    job_id = getattr(job, "id", getattr(job, "blueprint_id", None))
                    job_pos = getattr(job, "position", None)
                    coords = (job_pos.x, job_pos.y) if job_pos else None

                    print(f"[{self.name}] Found pending construction job: {job_id} at {coords}.")
                    success = self.execute_construction(job_id, coords)
                    if not success:
                        sleep(5.0)
                else:
                    self.publish_telemetry("IDLE_AT_BASE")
                    sleep(10.0)

            except Exception as e:
                print(f"[{self.name}] Pioneer loop exception: {e}")
                try:
                    self.vehicle.nav.brake()
                except Exception:
                    pass
                sleep(5.0)
