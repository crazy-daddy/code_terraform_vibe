# Vehicle mixin: mineral-site candidate discovery and drill execution.
# Shared by Rover and Pioneer via VehicleController (lib/vehicle.py) so
# mining logic lives in exactly one place regardless of which vehicle type
# is doing the digging.
#
# Capability (which hardness a vehicle can mine) is always read live from
# self.vehicle.drill.hardness_limit() -- never assumed from vehicle type.
# Rovers only ever carry a basic Drill Module (hardness_limit 1, iron/silicon)
# in their fixed Drill slot; Industrial/Heavy Drills are Pioneer-universal-slot
# items for the higher-hardness sites a Rover can never reach. Job routing
# between the two is a soft priority-sort preference (see
# ROVER_PREFERRED_MAX_HARDNESS below), not a hard exclusivity rule, so a
# capable vehicle still picks up whatever's available rather than idling.

from production import get_raw_material_demands, get_raw_material_reason

# Hardness a Rover's basic drill can handle. Pioneers pass this as
# deprioritize_hardness_at_or_below so they prefer sites only they can reach,
# while still falling back to easy ore if nothing harder is pending.
ROVER_PREFERRED_MAX_HARDNESS = 1.0


class MiningMixin:
    """Mineral-site discovery, priority-sorted claiming, and drill execution."""

    def build_mineral_site_candidates(self, deprioritize_hardness_at_or_below=None):
        """
        Candidate mineral-extraction sites matching active raw-material demand
        and this vehicle's actual mounted drill capability. When
        deprioritize_hardness_at_or_below is set, sites at/below that hardness
        get priority=3 instead of priority=2, so select_best_mining_target()
        tries them last -- a soft preference, not exclusion.
        """
        journal = get_component("journal")
        if not journal or not hasattr(journal, "surveyed_sites"):
            return []

        raw_demands = get_raw_material_demands(get_component("smelter_1"))
        if not raw_demands:
            return []

        max_drill_hardness = 1.0
        if hasattr(self.vehicle, "drill") and hasattr(self.vehicle.drill, "hardness_limit"):
            try:
                max_drill_hardness = self.vehicle.drill.hardness_limit()
            except Exception:
                max_drill_hardness = 1.0

        existing_claims = self.get_claims()
        unsupported_targets = self.get_unsupported_targets()
        curr_tick = self.get_current_tick()

        candidates = []
        try:
            for site in journal.surveyed_sites("nocturna"):
                site_item = getattr(site, "item_id", None)
                if site.kind() != "mineral" or raw_demands.get(site_item, 0) <= 0:
                    continue
                hardness = getattr(site, "hardness", 99)
                if hardness > max_drill_hardness:
                    continue

                key = f"site_{site.id}"
                if key in unsupported_targets:
                    can_attempt, _ = self.can_attempt_target(key, unsupported_targets[key])
                    if not can_attempt:
                        continue

                claim = existing_claims.get(key)
                if claim and claim.get("vehicle") != self.name and claim.get("rover") != self.name:
                    claim_age = curr_tick - claim.get("tick", 0)
                    if curr_tick == 0 or claim_age < self.CLAIM_STALE_TICKS:
                        continue  # Claimed by a peer; skip!

                priority = 2
                if deprioritize_hardness_at_or_below is not None and hardness <= deprioritize_hardness_at_or_below:
                    priority = 3

                candidates.append({
                    "key": key,
                    "type": "mine",
                    "coords": (site.x, site.y),
                    "name": f"Site_{site.id}_{getattr(site, 'item_id', 'ore')}",
                    "harvest_item": site_item,
                    "reason": get_raw_material_reason(site_item, get_component("smelter_1")),
                    "priority": priority,
                })
        except Exception:
            pass

        return candidates

    def select_best_mining_target(self, candidates):
        """
        Sorts candidates by (priority, distance) -- lower priority number
        wins, ties broken by distance -- then claims the first one that fits
        the round-trip energy budget. Returns (target, budget, diagnostics);
        target is None when nothing is currently achievable.
        """
        pos = self.get_position()
        candidates = sorted(candidates, key=lambda c: (c.get("priority", 2), self.distance_between(pos, c["coords"])))

        budget_candidates = 0
        for cand in candidates:
            planned_mine = 10 if cand["type"] == "mine" else 0
            planned_scan = 1 if cand["type"] == "poi" else 0
            budget = self.calculate_trip_energy(cand["coords"], planned_drill_units=planned_mine, planned_scans=planned_scan)

            if budget["is_achievable"]:
                budget_candidates += 1
                claimed = self.claim_target(cand["key"], cand)
                if claimed:
                    self.current_target = cand
                    self.current_target_key = cand["key"]
                    self.save_mission(cand["type"], cand)
                    return cand, budget, {"candidate_count": len(candidates), "budget_candidates": budget_candidates}

        return None, None, {"candidate_count": len(candidates), "budget_candidates": budget_candidates}

    def mine_current_site(self, max_units=None):
        """Extracts minerals using the mounted Drill Module while enforcing battery & cargo limits."""
        if not hasattr(self.vehicle, "drill"):
            print(f"[{self.name}] Error: No DrillModule mounted!")
            return 0

        cargo_capacity = self.vehicle.cargo.capacity() if hasattr(self.vehicle, "cargo") else 10
        if max_units is None:
            max_units = cargo_capacity

        self.publish_telemetry("MINING")
        mined_count = 0
        self.mining_interrupted_battery = False

        while mined_count < max_units:
            if self.vehicle.cargo.full():
                print(f"[{self.name}] Cargo hold full ({cargo_capacity}/{cargo_capacity}). Finishing mining operation.")
                break

            if self.is_recalled():
                print(f"[{self.name}] Recall requested; ceasing extraction to return to base.")
                break

            curr_wh, _, _ = self.get_battery()
            needed_to_return = self.energy_needed_to_return_now()
            if curr_wh <= (needed_to_return + self.MINE_WH_PER_UNIT * 1.5):
                print(f"[{self.name}] Reached return energy threshold ({curr_wh:.1f} Wh left). Ceasing extraction for recharge.")
                self.mining_interrupted_battery = True
                break

            m_res = self.vehicle.drill.mine()
            if m_res.status == "ok":
                mined_count += 1
                if self.current_target_key:
                    self.clear_unsupported_target(self.current_target_key)
                print(f"[{self.name}] Mined unit {mined_count}/{max_units}. Cargo: {self.vehicle.cargo.count()}/{cargo_capacity}.")
            elif m_res.status == "busy":
                sleep(0.5)
            else:
                print(f"[{self.name}] Drill finished or stopped: {m_res.status} - {m_res.message}")
                if m_res.status in ["tier_too_low", "too_hard", "research_required", "depleted", "not_found", "empty"]:
                    if self.current_target_key:
                        self.blacklist_target(self.current_target_key, m_res.status, m_res.message)
                break

            if self.current_target_key:
                self.refresh_claim(self.current_target_key)

        return mined_count

    def mine_until_full_or_exhausted(self, target_coords):
        """
        Mines the current site to cargo capacity, recharging at the nearest
        station and driving back to resume as many times as needed when
        interrupted by low battery (mirrors the recharge-and-resume pattern
        used for construction jobs in pioneer.py's execute_construction()).
        """
        self.mine_current_site()

        while getattr(self, "mining_interrupted_battery", False) and not self.vehicle.cargo.full():
            if self.is_recalled():
                print(f"[{self.name}] Recall requested; not resuming mining after recharge.")
                return
            print(f"[{self.name}] Mining job at {target_coords} interrupted by low battery. Diverting to recharge and resume.")
            if self.current_target_key:
                self.refresh_claim(self.current_target_key)

            nearest_cs, _ = self.get_nearest_charging_station()
            reached_cs = self.drive_to(nearest_cs[0], nearest_cs[1], precision=1.0)
            if not reached_cs:
                print(f"[{self.name}] Failed to reach charging station during mining interruption.")
                return

            self.recharge_at_station(target_level=1.0, station_coords=nearest_cs)

            print(f"[{self.name}] Recharged to 100%. Returning to resume mining at {target_coords}...")
            if self.current_target:
                self.publish_telemetry("OUTBOUND", self.current_target.get("name", "mining site"))
            reached_site = self.drive_with_recharge(target_coords[0], target_coords[1], precision=1.5)
            if not reached_site:
                print(f"[{self.name}] Could not reach mining site after recharge.")
                return

            remaining_space = self.vehicle.cargo.capacity() - self.vehicle.cargo.count()
            if remaining_space > 0:
                self.mine_current_site(max_units=remaining_space)
            else:
                return
