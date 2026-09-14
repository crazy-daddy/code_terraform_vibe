# Shared Library for Expedition Rover Automation
# Inherits from VehicleController (lib/vehicle.py) and specializes in
# autonomous planetary exploration, sonar site discovery, precision mining,
# and continuous expedition cycles.

from production import get_raw_material_demands
from vehicle import VehicleController

class RoverController(VehicleController):
    """
    Automated Expedition & Mining Controller for the Rover chassis.
    Specializes VehicleController with autonomous exploration cycles,
    unscanned POI targeting, and mineral site extraction.
    """
    def __init__(self, vehicle, home_coords=(0, 0), cruise_throttle=0.5):
        super().__init__(vehicle, home_coords=home_coords, cruise_throttle=cruise_throttle)
        self.last_target_diagnostics = {}

    def find_best_mission_target(self):
        """
        Finds the closest reachable unscanned POI or high-value surveyed mining site.
        Evaluates round-trip energy requirements and atomically reserves the target
        in Data Archive so other rovers do not compete for it. Mineral-site discovery
        and priority-sorted claiming come from MiningMixin (lib/mining.py), shared
        with Pioneer's mining role rather than duplicated here.
        Re-evaluates previously unsupported targets if upgraded technology or research is detected.
        """
        # A target restored from a saved mission (see vehicle_claims.py) after a
        # script reload takes priority over discovery, so the rover continues
        # toward the same destination instead of restarting the search.
        if self.current_target_key and self.current_target and self.current_target.get("coords"):
            print(f"[{self.name}] Resuming previously claimed target '{self.current_target_key}' after reload.")
            budget = self.calculate_trip_energy(
                self.current_target["coords"],
                planned_drill_units=10 if self.current_target.get("type") == "mine" else 0,
                planned_scans=1 if self.current_target.get("type") == "poi" else 0,
            )
            return self.current_target, budget

        self.cleanup_stale_claims()

        # Candidate pool 1: Unscanned POIs
        candidates = []
        for poi in self.unscanned_pois():
            key = f"poi_{poi.x}_{poi.y}"
            candidates.append({
                "key": key,
                "type": "poi",
                "coords": (poi.x, poi.y),
                "name": f"POI_{poi.x}_{poi.y}",
                "priority": 1
            })

        # Candidate pool 2: Surveyed mineral deposits matching demand and this
        # Rover's actual mounted drill capability. No deprioritization -- a
        # Rover always treats a reachable mineral site as priority 2.
        candidates.extend(self.build_mineral_site_candidates())

        target, budget, diagnostics = self.select_best_mining_target(candidates)
        if target:
            return target, budget

        self.last_target_diagnostics = {
            "raw_demands": get_raw_material_demands(get_component("smelter_1")),
            "claim_count": len(self.get_claims()),
            **diagnostics,
        }
        return None, None

    def run_expedition_cycle(self):
        """Executes one complete autonomous expedition cycle."""
        # Step 1: Ensure fully charged before leaving base. Only applies when
        # actually at base -- a reload mid-trip must not detour all the way
        # home just to satisfy this check before resuming its claimed target.
        if self.is_at_base():
            curr_wh, cap_wh, lvl = self.get_battery()
            if lvl < 0.95:
                print(f"[{self.name}] Battery at {lvl*100:.0f}%. Recharging to 100% before launch...")
                self.recharge_at_station(target_level=1.0)

        # Step 2: Ensure cargo is empty before launch
        if self.vehicle.cargo.count() > 0:
            if self.unload_cargo() < 0:
                self.publish_telemetry("WAITING_INVENTORY_SPACE")
                sleep(10.0)
                return

        # Step 3: Select safe target with exclusive claim
        target, budget = self.find_best_mission_target()
        if not target or not budget:
            diagnostics = self.last_target_diagnostics
            if not diagnostics.get("raw_demands"):
                reason = "no downstream raw-material demand (Inventory may be full or production is waiting)"
            elif diagnostics.get("candidate_count", 0) == 0:
                reason = "no surveyed mineral or unscanned POI matches current demand"
            elif diagnostics.get("budget_candidates", 0) == 0:
                reason = "matching targets exist but none fit the round-trip battery budget"
            else:
                reason = f"targets blocked by active claims ({diagnostics.get('claim_count', 0)} claims)"
            print(f"[{self.name}] No mission target: {reason}. Standing by at base slot.")
            self.publish_telemetry("IDLE_AT_BASE")
            sleep(10.0)
            return

        coords = target["coords"]
        if target["type"] == "mine":
            print(
                f"[{self.name}] Reserved {target['name']} to harvest "
                f"{target['harvest_item']} for {target['reason']} at {coords} "
                f"(Est. trip cost: {budget['total_required_wh']:.1f} Wh)."
            )
        else:
            print(f"[{self.name}] Reserved target '{target['name']}' at {coords} (Est. trip cost: {budget['total_required_wh']:.1f} Wh).")
        self.publish_telemetry("OUTBOUND", target["name"])

        # Step 4: Drive to target (using intermediate recharge stops if needed)
        reached = self.drive_with_recharge(coords[0], coords[1])
        if not reached:
            print(f"[{self.name}] Could not safely complete outbound trip. Returning home.")
            self.return_to_base()
            return

        # Step 5: Perform field work (Sonar / Mining)
        if target["type"] == "poi":
            self.scan_and_survey()
        elif target["type"] == "mine":
            self.mine_until_full_or_exhausted(coords)

        # Step 6: Return to base (releases target claim upon return)
        self.return_to_base()

        # Step 7: Offload and recharge
        if self.unload_cargo() < 0:
            self.publish_telemetry("WAITING_INVENTORY_SPACE")
            sleep(10.0)
            return
        self.recharge_at_station(target_level=1.0)
        self.publish_telemetry("READY_AT_BASE")
        print(f"[{self.name}] Expedition complete and rover secured at base.")

    def run(self):
        """Continuous autonomous rover mission loop."""
        print(f"Rover Controller ({self.name}) online. Assigned base slot: {self.assigned_slot_coords}.")
        while True:
            try:
                if self.handle_recall_if_active():
                    sleep(5.0)
                    continue
                self.run_expedition_cycle()
            except Exception as e:
                print(f"[{self.name}] Mission exception: {e}. Executing emergency failsafe brake.")
                try:
                    self.vehicle.nav.brake()
                except Exception:
                    pass
                # Release any active target claims on failure
                try:
                    self.release_target_claim()
                except Exception:
                    pass
                sleep(5.0)
