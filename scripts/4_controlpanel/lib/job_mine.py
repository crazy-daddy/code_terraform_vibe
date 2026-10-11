# MineJob: the mining role of a Rover (expeditions for home) and of a
# stationed Pioneer miner (stockpiling for its outpost), lib/job_base.py
# contract. A `targets` strategy picks the work and words the role's log
# lines: RoverTargets (unscanned POIs and mineral sites for home demand) or
# OutpostStockpile(outpost_id) (the outpost's assigned ores up to their stock
# targets). Each step: top-off and upgrade pass at base, cargo aboard (resume
# the saved mission or unload first), then one trip: drive, scan (poi) or
# mine (mine), return, release the claim, unload, recharge.
# run_job_loop(MineJob(...)) runs it (lib/rover.py, lib/pioneer.py). Mining,
# candidates, yield reservation: lib/vehicle_mining.py; scans:
# lib/vehicle_survey.py; unload: lib/vehicle_cargo.py; claims and mission:
# lib/vehicle_claims.py.

from dataclasses import replace

import fleet_intent
from job_base import Job
from outpost_mining import HOME_OUTPOST_ID


class MineJob(Job):
    """
    Mining role. prepare(): top-off and upgrade pass at base, then the cargo
    aboard (keep it for a resumable mission, else return and unload first),
    then the strategy's transfer to the base slot. pick(): the resumable
    mission, else the strategy's selection (claims and reserves yield).
    execute(): one trip. idle(): the strategy's stand-by.
    """

    name = "mine"
    recall_delay = 5.0
    retry_delay = 5.0  # sleep after an incomplete return or transfer leg
    blocked_delay = 10.0  # sleep while unloading finds no inventory space

    def __init__(self, host, targets):
        super().__init__(host)
        # RoverTargets or OutpostStockpile: select(), idle(), transfer(), wording.
        self.targets = targets
        # select_best_mining_target() diagnostics of the last pick() that found nothing (for idle()).
        self.diagnostics = {}

    def announce(self):
        self.targets.announce(self)

    def prepare(self):
        """
        At base: tops the battery off below 95% (OutpostStockpile only with
        a Charging Station at its outpost: without one the station trip and
        the transfer back cost the charge it gains), then the Pioneer's idle
        upgrade cycle when the host has one. A reload mid-trip must not
        detour home just to top off. Then prepare_cargo().
        """
        host = self.host
        if host.is_at_base():
            _, _, level = host.get_battery()
            if level < 0.95 and self._may_recharge_at_base():
                host.log.print(f"[{host.name}] Battery at {level*100:.0f}%. Recharging to 100% before launch...")
                host.recharge_at_station(target_level=1.0)
            elif level >= 0.95:
                host.log.debug(f"[{host.name}] At base with battery at {level*100:.0f}%; already charged, skipping pre-launch recharge.")
            upgrade_cycle = getattr(host, "handle_upgrade_cycle_if_idle", None)
            if upgrade_cycle is not None:
                upgrade_cycle()
        return self.prepare_cargo()

    def prepare_cargo(self):
        """
        Cargo aboard with a resumable mission is mid-mission work, kept unless
        it holds another ore than the target's (cargo isn't material-locked,
        see cargo_matches_target()) or the hold is full. Otherwise cargo goes
        home first: return, unload, and end the step so the next one tops off
        and runs the upgrade pass with an empty hold (blocked_delay instead
        when unloading left cargo aboard). With an empty hold and
        nothing to resume, the strategy may first transfer to the base slot.
        """
        host = self.host
        resume = self._resumable_mission()
        if resume is not None and not host.cargo_matches_target(resume.target):
            host.log.print(f"[{host.name}] Cargo holds a different material than the resumed target's {resume.target.get('harvest_item')}; unloading before resuming.")
            resume = None
        elif resume is not None and host.cargo_full_for_resume():
            host.log.print(f"[{host.name}] Cargo full; unloading before resuming target '{resume.target_key}'.")
            resume = None
        if resume is not None:
            return None

        # "inventory" is a freight endpoint only at the home outpost's service
        # area; cargo can still be aboard after a mid-trip interruption (a
        # rescue drone charges a stranded vehicle in place), so drive home first.
        if host.vehicle.cargo.count() > 0:
            if not host.is_at_base():
                host.log.print(f"[{host.name}] Cargo aboard but not at base (resuming after an interruption). Returning to base first.")
                if not host.return_to_base():
                    host.log.level("warn").print(f"[{host.name}] Return trip incomplete this cycle; will retry.")
                    return self.retry_delay
            if host.unload_cargo() < 0:
                host.publish_telemetry("WAITING_INVENTORY_SPACE")
                return self.blocked_delay
            if host.vehicle.cargo.count() > 0:
                return self.blocked_delay  # partial unload (no port or store room): retry later, not at once
            return 0
        return self.targets.transfer(self)

    def pick(self):
        """The resumable mission (fresh trip budget), else the strategy's claimed target; None when nothing fits."""
        host = self.host
        self.diagnostics = {}
        resume = self._resumable_mission()
        if resume is not None:
            host.log.print(f"[{host.name}] Resuming previously claimed target '{resume.target_key}' after reload.")
            target = resume.target
            is_mine = target.get("type") == "mine"
            budget = host.calculate_trip_energy(
                target["coords"],
                planned_drill_units=10 if is_mine else 0,
                planned_scans=1 if target.get("type") == "poi" else 0,
                mine_item_id=target.get("harvest_item") if is_mine else None,
                mine_purity=target.get("purity") if is_mine else None,
            )
            # A copy: host.mission changes only through begin_mission/end_mission.
            return replace(resume, budget=budget)

        target, budget, diagnostics = self.targets.select(self)
        if not target or not budget:
            self.diagnostics = diagnostics
            return None
        # select_best_mining_target() returns a target only after
        # begin_mission() won its claim, so host.mission is that target's mission.
        return host.mission

    def execute(self, mission):
        host = self.host
        host.log.start(self.targets.trip_title(self, mission.target))
        outcome, delay = self._trip(mission)
        host.log.end(f"[{host.name}] {outcome}")
        return delay

    def idle(self):
        return self.targets.idle(self)

    def on_error(self):
        """Releases every claim this vehicle holds, its yield reservation and saved mission (the loop already braked)."""
        self.host.release_target_claim()

    def _may_recharge_at_base(self):
        return self.host.home_charging_station is not None or not self.targets.local_charger_only

    def _resumable_mission(self):
        """host.mission when it names a target with coords (a reload or an incomplete trip), else None."""
        mission = self.host.mission
        if mission is not None and mission.target_key and mission.target.get("coords"):
            return mission
        return None

    def _trip(self, mission):
        """Drive, field work, return, release, unload, recharge; returns (outcome text, delay)."""
        host = self.host
        targets = self.targets
        target = mission.target
        coords = target["coords"]
        trip_wh = mission.budget["total_required_wh"] if mission.budget else 0.0
        host.log.print(targets.reserved_line(self, target, trip_wh))
        host.set_intent(targets.intent(target))
        host.publish_telemetry("OUTBOUND", target["name"])

        if not host.drive_with_recharge(coords[0], coords[1]):
            host.log.level("warn").print(f"[{host.name}] Could not safely complete outbound trip. Returning {targets.home_phrase}.")
            host.return_to_base()
            return targets.outcomes["outbound"], 0

        if target.get("type") == "poi":
            host.scan_and_survey(mission)
        elif target.get("type") == "mine":
            host.mine_until_full_or_exhausted(coords, max_units=targets.mine_units(self, target))

        # A failed return (a rescue interrupts drive_to()) keeps the mission:
        # unload_cargo() needs the home outpost's service area.
        if not host.return_to_base():
            host.log.level("warn").print(f"[{host.name}] Return trip incomplete this cycle; will retry.")
            return targets.outcomes["return"], self.retry_delay

        # Released however the trip ended (cargo full, site depleted, ...), so
        # the next pick() re-evaluates demand: resuming skips the
        # unsupported-target check selection applies.
        host.release_target_claim()

        if host.unload_cargo() < 0:
            host.publish_telemetry("WAITING_INVENTORY_SPACE")
            return targets.outcomes["unload"], self.blocked_delay
        if self._may_recharge_at_base():
            host.recharge_at_station(target_level=1.0)
        return targets.trip_done(self), 0


class RoverTargets:
    """
    Rover expedition targets: unscanned POIs (priority 1) and surveyed
    mineral sites matching home ore demand and the mounted drill
    (build_mineral_site_candidates()), delivered home. Tops off at any
    Charging Station; stands by at the base slot 10 s when nothing fits.
    """

    local_charger_only = False
    home_phrase = "home"
    idle_delay = 10.0
    outcomes = {"outbound": "outbound trip failed", "return": "return trip incomplete", "unload": "waiting for inventory space"}

    def announce(self, job):
        host = job.host
        host.log.print(f"Rover Controller ({host.name}) online. Assigned base slot: {host.assigned_slot_coords}.")

    def transfer(self, job):
        """A Rover plans its trip from wherever it stands."""
        return None

    def select(self, job):
        """Claims the best reachable candidate (select_best_mining_target()); (target, budget, diagnostics)."""
        host = job.host
        host.log.start(f"[{host.name}] RoverTargets.select()", level="debug")
        host.cleanup_stale_claims()
        candidates = []
        for poi in host.unscanned_pois():
            candidates.append({
                "key": f"poi_{poi.x}_{poi.y}",
                "type": "poi",
                "coords": (poi.x, poi.y),
                "name": f"POI_{poi.x}_{poi.y}",
                "priority": 1,
            })
        poi_count = len(candidates)
        # A Rover treats every reachable mineral site as priority 2 (no hardness deprioritization).
        mineral_candidates = host.build_mineral_site_candidates()
        candidates.extend(mineral_candidates)
        host.log.debug(f"{poi_count} unscanned POI(s), {len(mineral_candidates)} mineral site candidate(s).")

        target, budget, diagnostics = host.select_best_mining_target(candidates)
        if not target:
            diagnostics = {"raw_demands": host.home_ore_demand(), "claim_count": len(host.get_claims()), **diagnostics}
        host.log.end()
        return target, budget, diagnostics

    def idle(self, job):
        host = job.host
        diagnostics = job.diagnostics
        if not diagnostics.get("raw_demands"):
            reason = "no downstream raw-material demand (Inventory may be full or production is waiting)"
        elif diagnostics.get("candidate_count", 0) == 0:
            reason = "no surveyed mineral or unscanned POI matches current demand"
        elif diagnostics.get("budget_candidates", 0) == 0:
            reason = "matching targets exist but none fit the round-trip battery budget"
        else:
            reason = f"targets blocked by active claims ({diagnostics.get('claim_count', 0)} claims)"
        host.log.level("warn").print(f"[{host.name}] No mission target: {reason}. Standing by at base slot.")
        host.publish_telemetry("IDLE_AT_BASE")
        return self.idle_delay

    def trip_title(self, job, target):
        return f"[{job.host.name}] Expedition to {target['name']}"

    def reserved_line(self, job, target, trip_wh):
        name = job.host.name
        if target["type"] == "mine":
            return (
                f"[{name}] Reserved {target['name']} to harvest "
                f"{target['harvest_item']} for {target['reason']} at {target['coords']} "
                f"(Est. trip cost: {trip_wh:.1f} Wh)."
            )
        return f"[{name}] Reserved target '{target['name']}' at {target['coords']} (Est. trip cost: {trip_wh:.1f} Wh)."

    def intent(self, target):
        if target["type"] == "mine":
            item = target["harvest_item"]
            return fleet_intent.describe("mining", [item], at=target["name"], root=fleet_intent.haul_root([item], HOME_OUTPOST_ID))
        return fleet_intent.describe("scanning", at=target["name"])

    def mine_units(self, job, target):
        """The yield select_best_mining_target() reserved (None on a resumed mission: up to cargo capacity)."""
        return target.get("estimated_units")

    def trip_done(self, job):
        host = job.host
        host.publish_telemetry("READY_AT_BASE")
        host.log.print(f"[{host.name}] Expedition complete and rover secured at base.")
        return "expedition complete"


class OutpostStockpile:
    """
    Stationed miner targets: outpost_id's assigned ores below their stock
    target (or requested at NEED band and above), at sites nearest to it
    (build_local_stockpile_candidates()), independent of home's demand, and
    delivered there (host.home_base is outpost_id). Moves to the outpost's
    base slot before picking; tops off only at an outpost with its own
    Charging Station; stands by 30 s when nothing fits.
    """

    local_charger_only = True
    home_phrase = "to outpost"
    idle_delay = 30.0
    outcomes = {"outbound": "Outbound trip incomplete", "return": "Return trip incomplete", "unload": "Unload blocked, no inventory space"}

    def __init__(self, outpost_id):
        self.outpost_id = outpost_id

    def announce(self, job):
        host = job.host
        host.log.print(f"Pioneer Mining Controller ({host.name}) online. Assigned base slot: {host.assigned_slot_coords}. Stationed at '{self.outpost_id}'.")

    def transfer(self, job):
        """
        A Pioneer freshly deployed or re-stationed starts away from its base
        slot; trip budgets from there count the transfer leg on every attempt,
        so a small battery rejects every site. Moves to the base slot first
        (0, or retry_delay when the leg is incomplete); None when already there.
        """
        host = job.host
        if host.is_at_base():
            return None
        host.log.print(f"[{host.name}] Away from outpost '{self.outpost_id}' base slot {host.get_home_slot_coords()}; transferring there before mining.")
        if not host.return_to_base():
            host.log.level("warn").print(f"[{host.name}] Transfer to outpost '{self.outpost_id}' incomplete this cycle; will retry.")
            return job.retry_delay
        return 0

    def select(self, job):
        """Claims the best reachable stockpile site (select_best_mining_target()); (target, budget, diagnostics)."""
        host = job.host
        return host.select_best_mining_target(host.build_local_stockpile_candidates(self.outpost_id))

    def idle(self, job):
        """
        Recharges when a full battery brings the cheapest out-of-range site
        into reach (charge_would_reach(); 0 s), else stands by with the reason.
        """
        host = job.host
        diagnostics = job.diagnostics
        cheapest = diagnostics.get("cheapest_rejected")
        if cheapest is not None and self.charge_would_reach(job, cheapest):
            host.log.print(f"[{host.name}] No stockpile site in range on {cheapest['current_wh']:.0f} Wh; charging at the nearest Charging Station.")
            host.recharge_at_station(target_level=1.0)
            return 0
        if diagnostics.get("candidate_count", 0) == 0:
            reason = host.stockpile_empty_reason
        else:
            reason = self.reject_reason(diagnostics)
        host.log.print(f"[{host.name}] No stockpile target at outpost '{self.outpost_id}': {reason}. Standing by.")
        host.publish_telemetry("IDLE_AT_OUTPOST")
        return self.idle_delay

    def charge_would_reach(self, job, cheapest):
        """
        True when an outpost without its own Charging Station should recharge
        for the cheapest out-of-range site: a full battery, less the transfer
        from the nearest station back to the base slot, covers its trip.
        Battery at 95%+ gains too little to change the verdict.
        """
        host = job.host
        if host.home_charging_station is not None:
            return False
        _, cap_wh, level = host.get_battery()
        if level >= 0.95:
            return False
        slot = host.assigned_slot_coords
        cs_coords, _ = host.get_nearest_charging_station(from_coords=slot)
        transfer_wh = host.energy_wh_for_leg(host.distance_between(cs_coords, slot), host.cruise_throttle)
        return cheapest["total_required_wh"] <= cap_wh - transfer_wh

    @staticmethod
    def reject_reason(diagnostics):
        """Why select_best_mining_target() chose none of the stockpile candidates, from its diagnostics."""
        count = diagnostics.get("candidate_count", 0)
        cheapest = diagnostics.get("cheapest_rejected")
        lost = diagnostics.get("claims_lost", 0)
        parts = []
        if cheapest is not None:
            parts.append(
                f"{count - diagnostics.get('budget_candidates', 0)} of {count} site(s) out of energy range "
                f"(cheapest needs {cheapest['total_required_wh']:.0f} Wh, {cheapest['current_wh']:.0f} Wh on board, "
                f"return leg {cheapest['dist_inbound']:.0f} m to Charging Station at {cheapest['nearest_cs_coords']})"
            )
        if lost:
            parts.append(f"{lost} in-range site(s) claimed by a peer")
        return "; ".join(parts) or f"none of {count} site(s) chosen"

    def trip_title(self, job, target):
        return f"[{job.host.name}] Stockpile run: {target['harvest_item']} for outpost '{self.outpost_id}'"

    def reserved_line(self, job, target, trip_wh):
        return (
            f"[{job.host.name}] Reserved {target['name']} to stockpile {target['harvest_item']} "
            f"for outpost '{self.outpost_id}' at {target['coords']} (Est. trip cost: {trip_wh:.1f} Wh)."
        )

    def intent(self, target):
        item = target["harvest_item"]
        root = fleet_intent.haul_root([item], self.outpost_id) or f"{self.outpost_id} stock"
        return fleet_intent.describe("mining", [item], at=target["name"], root=root)

    def mine_units(self, job, target):
        """
        The stock target's live headroom (net of peers' reserved trips), or a
        larger NEED-band request (stockpile_need()), not just cargo capacity:
        a load past ore_stock_target() spills into a second Warehouse material
        slot, one of only 5 shared by every assigned ore.
        """
        host = job.host
        item_id = target["harvest_item"]
        remaining = max(host.stockpile_headroom(self.outpost_id, item_id), host.stockpile_need(self.outpost_id).get(item_id, 0))
        return max(1, remaining)

    def trip_done(self, job):
        job.host.publish_telemetry("READY_AT_OUTPOST")
        return f"Stockpile run complete; secured at outpost '{self.outpost_id}'"
