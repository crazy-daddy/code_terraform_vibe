# Shared Library for Expedition Rover Automation
# Inherits from VehicleController (lib/vehicle.py) and specializes in
# autonomous planetary exploration, sonar site discovery, precision mining,
# and continuous expedition cycles.

from archive import archive
from production import get_raw_material_demands, get_raw_material_reason
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
        in Data Archive so other rovers do not compete for it.
        Re-evaluates previously unsupported targets if upgraded technology or research is detected.
        """
        nocturna = get_component("nocturna")
        journal = get_component("journal")

        self.cleanup_stale_claims()
        candidates = []
        raw_demands = get_raw_material_demands(get_component("smelter_1"))

        # Read active claims to skip sites claimed by peers
        existing_claims = self.get_claims()
        # Read blacklisted/unsupported targets to check hardware capability
        unsupported_targets = self.get_unsupported_targets()
        curr_tick = self.get_current_tick()

        # Candidate pool 1: Unscanned POIs
        for poi in self.unscanned_pois():
            key = f"poi_{poi.x}_{poi.y}"
            candidates.append({
                "key": key,
                "type": "poi",
                "coords": (poi.x, poi.y),
                "name": f"POI_{poi.x}_{poi.y}",
                "priority": 1
            })

        # Candidate pool 2: Surveyed mineral deposits from Journal
        max_drill_hardness = 1.0
        if hasattr(self.vehicle, "drill") and hasattr(self.vehicle.drill, "hardness_limit"):
            try:
                max_drill_hardness = self.vehicle.drill.hardness_limit()
            except Exception:
                max_drill_hardness = 1.0

        if journal and hasattr(journal, "surveyed_sites"):
            try:
                for site in journal.surveyed_sites("nocturna"):
                    site_item = getattr(site, "item_id", None)
                    if site.kind() == "mineral" and raw_demands.get(site_item, 0) > 0 and getattr(site, "hardness", 99) <= max_drill_hardness:
                        key = f"site_{site.id}"
                        # Check if previously unsupported, and verify if current equipment can attempt it
                        if key in unsupported_targets:
                            can_attempt, _ = self.can_attempt_target(key, unsupported_targets[key])
                            if not can_attempt:
                                continue

                        claim = existing_claims.get(key)
                        if claim and claim.get("rover") != self.name:
                            claim_age = curr_tick - claim.get("tick", 0)
                            if curr_tick == 0 or claim_age < self.CLAIM_STALE_TICKS:
                                continue # Claimed by a peer; skip!

                        candidates.append({
                            "key": key,
                            "type": "mine",
                            "coords": (site.x, site.y),
                            "name": f"Site_{site.id}_{getattr(site, 'item_id', 'ore')}",
                            "harvest_item": site_item,
                            "reason": get_raw_material_reason(site_item, get_component("smelter_1")),
                            "priority": 2
                        })
            except Exception:
                pass

        # Sort candidates by distance from current position
        pos = self.get_position()
        candidates.sort(key=lambda c: self.distance_between(pos, c["coords"]))

        # Filter for reachable candidates within battery budget and atomically claim the best
        budget_candidates = 0
        for cand in candidates:
            planned_mine = 10 if cand["type"] == "mine" else 0
            planned_scan = 1 if cand["type"] == "poi" else 0
            budget = self.calculate_trip_energy(cand["coords"], planned_drill_units=planned_mine, planned_scans=planned_scan)

            if budget["is_achievable"]:
                budget_candidates += 1
                # Try atomic claim
                claimed = self.claim_target(cand["key"], cand)
                if claimed:
                    self.current_target = cand
                    self.current_target_key = cand["key"]
                    return cand, budget

        self.last_target_diagnostics = {
            "raw_demands": raw_demands,
            "candidate_count": len(candidates),
            "budget_candidates": budget_candidates,
            "claim_count": len(existing_claims),
        }
        return None, None

    def run_expedition_cycle(self):
        """Executes one complete autonomous expedition cycle."""
        # Step 1: Ensure fully charged before leaving base
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

        # Step 4: Drive to target
        reached = self.drive_to(coords[0], coords[1])
        if not reached:
            print(f"[{self.name}] Could not safely complete outbound trip. Returning home.")
            self.return_to_base()
            return

        # Step 5: Perform field work (Sonar / Mining)
        if target["type"] == "poi":
            self.scan_and_survey()
        elif target["type"] == "mine":
            self.mine_current_site(max_units=10)

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
