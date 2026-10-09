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

from production import get_raw_material_reason
from version_guard import validate_game_version
import outpost_mining
import mining_reservations
import logistics_requests
import fleet_intent
from swallow import swallowed
from typing import TYPE_CHECKING
from tree_console import flush_all, reset_all

if TYPE_CHECKING:
    from vehicle import VehicleController

# Hardness a Rover's basic drill can handle. Pioneers pass this as
# deprioritize_hardness_at_or_below so they prefer sites only they can reach,
# while still falling back to easy ore if nothing harder is pending.
ROVER_PREFERRED_MAX_HARDNESS = 1.0

# A surveyed MiningSite's .purity ("standard"/"rich"/"pure" -- see
# docs/types/world_and_sites.md) is a 1x/2x/3x extraction-rate multiplier: a
# "rich" site yields roughly twice the ore for the same drilling time/energy
# as a "standard" one. select_best_mining_target() uses this rank as a sort
# tiebreak WITHIN the same priority tier -- richer sites win over merely-
# closer ones, same lexicographic-tiering style priority itself already
# uses (a priority=2 candidate always beats priority=3 regardless of
# distance; richness now works the same way one level down). A soft
# preference, not a hard filter -- an unreachable-on-budget rich site still
# loses to a reachable standard one, since the achievability check runs
# after sorting either way.
PURITY_RANK = {"standard": 0, "rich": 1, "pure": 2}

# Demand tier a mine candidate serves ("tier"): an ore the delivery outpost
# requests at need tier (logistics_requests.outpost_deficits_tiered()) beats
# stock-only ore, as haulers already rank it (haul_rank()). Sorted after
# priority, before purity and distance.
TIER_NEED = 0
TIER_STOCK = 1


def ore_tiers(need, buffer):
    """({ore: need units}, {ore: buffer units}): the raw-ore entries of need
    and buffer (outpost_deficits_tiered() output, already net of in-flight
    mining yield). Positive entries only."""
    need_left, buffer_left = {}, {}
    for item_id in sorted(set(need) | set(buffer)):
        if item_id not in outpost_mining.RAW_ORE_ITEM_IDS:
            continue
        n, b = need.get(item_id, 0), buffer.get(item_id, 0)
        if n > 0:
            need_left[item_id] = n
        if b > 0:
            buffer_left[item_id] = b
    return need_left, buffer_left


class VehicleMiningMixin:
    """Mineral-site discovery, priority-sorted claiming, and drill execution."""

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    def cargo_full_for_resume(self):
        """
        True when the cargo hold is full (Cargo.full()). A reload mid-return
        restores the mining claim, and resuming it with a full hold only
        drives back to the site and home again without mining, so callers
        unload first instead -- see run_expedition_cycle() (rover.py) /
        _stationed_mining_cycle().
        """
        cargo = getattr(self._host.vehicle, "cargo", None)
        if cargo is None:
            return False
        try:
            return bool(cargo.full())
        except Exception as error:
            swallowed("vehicle_mining.VehicleMiningMixin.cargo_full_for_resume: cargo.full", error)
            return False

    def cargo_matches_target(self, target):
        """
        True when the vehicle's cargo is empty, or holds only the target's
        own harvest_item. Cargo isn't material-locked (docs/models/storage_and_items.md's
        Cargo.stacks() lists property-distinct stacks -- a Rover/Pioneer can
        physically carry a mix of ore types at once), so nothing stops a
        resumed mining job from mining a *different* ore straight into a hold
        that already carries something else -- wasteful (capacity meant for
        one clean load gets split across two materials) and confusing (an
        "interrupted, resume this job" trip budget assumed a roughly-empty
        hold, not one already partly full of an unrelated material). Callers
        use this to decide whether resuming a claimed target should first
        detour through an unload instead of mining straight into mismatched
        cargo -- see run_expedition_cycle() (rover.py) /
        _stationed_mining_cycle().
        """
        if not hasattr(self._host.vehicle, "cargo") or self._host.vehicle.cargo.count() == 0:
            return True
        harvest_item = target.get("harvest_item") if target else None
        if not harvest_item:
            return True  # non-mining target (e.g. a POI survey) has no ore to mismatch against
        try:
            stacks = self._host.vehicle.cargo.stacks()
        except Exception as error:
            swallowed("vehicle_mining.VehicleMiningMixin.cargo_matches_target: self._host.vehicle.cargo.stacks", error)
            return True  # can't verify; don't block resumption over an unreadable stacks() call
        for stack in stacks:
            item_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if item_id and count > 0 and item_id != harvest_item:
                return False
        return True

    def home_ore_demand_tiered(self):
        """
        ({ore: need units}, {ore: buffer units}) this vehicle's home_base
        still requests (logistics_requests.outpost_deficits_tiered(), net of
        stock, in-flight pickups and the yield in-flight mining trips to home
        already promised). Home is planned like any outpost: a smelting
        site's ore requests come from lib/site_supply.py.
        """
        tick = self._host.get_current_tick()
        return ore_tiers(*logistics_requests.outpost_deficits_tiered(self._host.home_outpost, tick, live=True))

    def home_ore_demand(self):
        """{ore: units} of home_ore_demand_tiered(), both tiers summed."""
        need, buffer = self.home_ore_demand_tiered()
        demand = dict(need)
        for item_id, units in buffer.items():
            demand[item_id] = demand.get(item_id, 0) + units
        return demand

    def build_mineral_site_candidates(self, deprioritize_hardness_at_or_below=None):
        """
        Candidate mineral-extraction sites matching home_ore_demand() and this
        vehicle's actual mounted drill capability. When
        deprioritize_hardness_at_or_below is set, sites at/below that hardness
        get priority=3 instead of priority=2, so select_best_mining_target()
        tries them last -- a soft preference, not exclusion.
        """
        self._host.log.start(f"[{self._host.name}] build_mineral_site_candidates()", level="debug")
        journal = get_component("journal")
        if not journal or not hasattr(journal, "surveyed_sites"):
            self._host.log.end()
            return []

        need_demands, buffer_demands = self.home_ore_demand_tiered()
        raw_demands = {i: need_demands.get(i, 0) + buffer_demands.get(i, 0) for i in set(need_demands) | set(buffer_demands)}
        if not raw_demands:
            self._host.log.debug("no ore requested at home; skipping candidate search.")
            self._host.log.end()
            return []

        max_drill_hardness = 1.0
        if hasattr(self._host.vehicle, "drill") and hasattr(self._host.vehicle.drill, "hardness_limit"):
            try:
                max_drill_hardness = self._host.vehicle.drill.hardness_limit()
            except Exception as error:
                swallowed("vehicle_mining.VehicleMiningMixin.build_mineral_site_candidates: self._host.vehicle.drill.hardness_limit", error)
                max_drill_hardness = 1.0
        self._host.log.debug(
            f"[{self._host.name}] build_mineral_site_candidates(): demand={raw_demands}, max_drill_hardness={max_drill_hardness}, "
            f"deprioritize_hardness_at_or_below={deprioritize_hardness_at_or_below}"
        )

        unsupported_targets = self._host.get_unsupported_targets()

        # No peer-claim filter here: several vehicles can mine the same site,
        # so a peer already working a site is not disqualifying -- see
        # select_best_mining_target()'s yield reservation instead, which
        # debits home demand for ore already promised by an in-flight trip.
        home_id = getattr(self._host.home_outpost, "id", None)
        candidates = []
        try:
            for site in journal.surveyed_sites("nocturna"):
                site_item = getattr(site, "item_id", None)
                if site.kind() != "mineral" or raw_demands.get(site_item, 0) <= 0:
                    continue
                hardness = getattr(site, "hardness", 99)
                if hardness > max_drill_hardness:
                    self._host.log.debug(f"site_{site.id}: hardness {hardness} exceeds drill limit {max_drill_hardness}; skipped.")
                    continue

                key = f"site_{site.id}"
                if key in unsupported_targets:
                    can_attempt, reason = self._host.can_attempt_target(key, unsupported_targets[key])
                    if not can_attempt:
                        self._host.log.debug(f"{key}: blocked by unsupported-target record ({reason}); skipped.")
                        continue

                priority = 2
                if deprioritize_hardness_at_or_below is not None and hardness <= deprioritize_hardness_at_or_below:
                    priority = 3
                    self._host.log.debug(f"{key}: hardness {hardness} deprioritized (<= {deprioritize_hardness_at_or_below}); priority=3.")

                candidates.append({
                    "key": key,
                    "type": "mine",
                    "coords": (site.x, site.y),
                    "name": f"Site_{site.id}_{getattr(site, 'item_id', 'ore')}",
                    "harvest_item": site_item,
                    "reason": get_raw_material_reason(site_item),
                    "priority": priority,
                    "tier": TIER_NEED if need_demands.get(site_item, 0) > 0 else TIER_STOCK,
                    "purity": getattr(site, "purity", None),
                    "outpost_id": home_id,
                })
        except Exception as error:
            swallowed("vehicle_mining.VehicleMiningMixin.build_mineral_site_candidates: journal.surveyed_sites", error)

        self._host.log.debug(f"{len(candidates)} candidate(s) built.")
        self._host.log.end()
        return candidates

    def build_local_stockpile_candidates(self, outpost_id):
        """
        Candidate mineral-extraction sites for a vehicle STATIONED at
        outpost_id (see run_stationed_mining_loop()) -- independent of home's
        live demand, since the whole point is stockpiling ahead of it (TODO.md
        Phase 3). Only considers outpost_id's assigned ores
        (lib/outpost_mining.py's assigned_ores_for()) that haven't yet reached
        their stock target in that outpost's own Warehouse, and only sites
        whose nearest outpost is this one -- a site closer to some other
        outpost is that outpost's job, not this vehicle's, even if this
        vehicle could physically reach it.

        When it returns no candidate, self.stockpile_empty_reason says why
        (for the stand-by line in _stationed_mining_cycle()).
        """
        self.stockpile_empty_reason = ""
        journal = get_component("journal")
        if not journal or not hasattr(journal, "surveyed_sites"):
            self.stockpile_empty_reason = "journal unavailable, no surveyed sites to read"
            return []

        assigned = outpost_mining.assigned_ores_for(outpost_id)
        if not assigned:
            self.stockpile_empty_reason = "no ore assigned to this outpost"
            return []

        # An assigned ore the outpost requests at need tier (a dock order, a
        # local Fabricator's ingots) goes ahead of stock-only ore, and may be
        # mined past the stock target up to that need.
        need = self.stockpile_need(outpost_id)
        under_target = {}
        for item_id in assigned:
            room = max(self.stockpile_headroom(outpost_id, item_id), need.get(item_id, 0))
            if room > 0:
                under_target[item_id] = room
        if not under_target:
            self.stockpile_empty_reason = f"every assigned ore ({', '.join(sorted(assigned))}) is at its stock target"
            return []

        max_drill_hardness = 1.0
        if hasattr(self._host.vehicle, "drill") and hasattr(self._host.vehicle.drill, "hardness_limit"):
            try:
                max_drill_hardness = self._host.vehicle.drill.hardness_limit()
            except Exception as error:
                swallowed("vehicle_mining.VehicleMiningMixin.build_local_stockpile_candidates: self._host.vehicle.drill.hardness_limit", error)
                max_drill_hardness = 1.0

        unsupported_targets = self._host.get_unsupported_targets()

        # No peer-claim filter here either (see build_mineral_site_candidates()):
        # stockpile_headroom() already nets out peers' reserved trips, so a
        # second vehicle only joins while the stock target still has room.
        candidates = []
        skipped = {"too hard": 0, "other outpost": 0, "blacklisted": 0}
        try:
            for site in journal.surveyed_sites("nocturna"):
                site_item = getattr(site, "item_id", None)
                if site.kind() != "mineral" or site_item not in under_target:
                    continue
                hardness = getattr(site, "hardness", 99)
                if hardness > max_drill_hardness:
                    skipped["too hard"] += 1
                    continue
                if outpost_mining.site_assigned_outpost(site.x, site.y) != outpost_id:
                    skipped["other outpost"] += 1
                    continue

                key = f"site_{site.id}"
                if key in unsupported_targets:
                    can_attempt, _ = self._host.can_attempt_target(key, unsupported_targets[key])
                    if not can_attempt:
                        skipped["blacklisted"] += 1
                        continue

                candidates.append({
                    "key": key,
                    "type": "mine",
                    "coords": (site.x, site.y),
                    "name": f"Site_{site.id}_{site_item}",
                    "harvest_item": site_item,
                    "reason": f"stockpiling for outpost '{outpost_id}'",
                    "priority": 2,
                    "tier": TIER_NEED if need.get(site_item, 0) > 0 else TIER_STOCK,
                    "purity": getattr(site, "purity", None),
                    "outpost_id": outpost_id,
                    "max_units": under_target[site_item],
                })
        except Exception as error:
            swallowed("vehicle_mining.VehicleMiningMixin.build_local_stockpile_candidates: journal.surveyed_sites", error)

        if not candidates:
            skip_text = ", ".join(f"{count} {why}" for why, count in skipped.items() if count)
            self.stockpile_empty_reason = (
                f"no usable surveyed site for {', '.join(sorted(under_target))}"
                + (f" (skipped: {skip_text})" if skip_text else "")
            )
        self._host.log.debug(f"[{self._host.name}] build_local_stockpile_candidates('{outpost_id}'): {len(candidates)} candidate(s) built (under_target={under_target}, need={need}).")
        return candidates

    def stockpile_headroom(self, outpost_id, item_id):
        """
        Units of item_id still missing from outpost_id's stock target, net of
        the yield peers' trips there already reserved (this vehicle's own
        reservation excluded) and of hauler pickups bound there.
        """
        return self.stockpile_room(outpost_id, item_id, outpost_mining.ore_stock_target(item_id))

    def stockpile_room(self, outpost_id, item_id, level):
        """Units of item_id missing at outpost_id up to `level`: level minus
        its held stock (logistics_requests.outpost_stock(): Warehouses, Drone
        Depots, Inventory only at home), the yield peers' trips there already
        reserved (this vehicle's own excluded) and hauler pickups bound there."""
        outpost = outpost_mining.outpost_by_id(outpost_id)
        tick = self._host.get_current_tick()
        reserved = mining_reservations.get_reserved_yield_totals(tick, outpost_id=outpost_id, exclude_vehicle=self._host.name).get(item_id, 0)
        hauled = logistics_requests.in_flight(outpost_id, tick).get(item_id, 0)
        held = logistics_requests.outpost_stock([item_id], outpost).get(item_id, 0)
        return level - held - reserved - hauled

    def stockpile_need(self, outpost_id):
        """
        {ore: units} outpost_id requests at need tier
        (logistics_requests.outpost_deficits_tiered()), net of the yield
        peers' trips there already reserved (this vehicle's own excluded),
        raised by the ore a Supply Dock order waits on there
        (outpost_mining.dock_ore_need(), netted by stockpile_room()).
        """
        tick = self._host.get_current_tick()
        need, buffer = logistics_requests.outpost_deficits_tiered(outpost_mining.outpost_by_id(outpost_id), tick, live=True, exclude_vehicle=self._host.name)
        need = ore_tiers(need, buffer)[0]
        for ore, level in outpost_mining.dock_ore_need(outpost_id, tick, logistics_requests.REQUEST_STALE_TICKS).items():
            room = self.stockpile_room(outpost_id, ore, level)
            if room > need.get(ore, 0):
                need[ore] = room
        return need

    def select_best_mining_target(self, candidates):
        """
        Sorts candidates by (priority, tier, -purity_rank, distance) -- lower
        priority number wins first, then ore the delivery outpost needs
        (TIER_NEED) beats stock-only ore, then richer veins (see PURITY_RANK)
        win over merely-closer ones, distance only breaking ties between
        equally-rich candidates -- then claims the
        first one that fits the round-trip energy budget. Returns (target,
        budget, diagnostics); target is None when nothing is currently
        achievable.

        A mine target's claim is per vehicle (VehicleClaimsMixin.claim_key()),
        so a peer mining the same site never blocks it. Instead this estimates
        the trip's yield -- energy on board (max_mineable_units()), capped by
        the candidate's "max_units" (stockpile headroom) -- and registers it
        via mining_reservations.reserve_yield(). A peer's next search sees
        that much of the deficit already promised (home_ore_demand(),
        stockpile_headroom()) and only joins the site while demand is left.
        The estimate is stashed on the candidate as "estimated_units" so
        callers size the actual mining call to it.

        Feasibility is first checked at a full 10-unit haul; if that doesn't
        fit the round-trip budget, retries at whatever max_mineable_units()
        says IS affordable instead of rejecting the site outright -- a
        vehicle whose battery can never fit a full 10-unit trip (e.g. a
        Rover with no bigger battery available, or a Pioneer eyeing
        expensive-per-unit ore like Neutronium) would otherwise stand by at
        base forever despite live demand and a perfectly reachable smaller
        load. Only 0 affordable units is a genuine rejection.
        """
        self._host.log.start(f"[{self._host.name}] select_best_mining_target", level="debug")
        pos = self._host.get_position()
        candidates = sorted(
            candidates,
            key=lambda c: (
                c.get("priority", 2),
                c.get("tier", TIER_STOCK),
                -PURITY_RANK.get(c.get("purity"), 0),
                self._host.distance_between(pos, c["coords"]),
            ),
        )

        self._host.log.trace(f"select_best_mining_target() enter: {len(candidates)} candidate(s)")
        budget_candidates = 0
        claims_lost = 0
        cheapest_rejected = None
        for cand in candidates:
            planned_mine = 10 if cand["type"] == "mine" else 0
            planned_scan = 1 if cand["type"] == "poi" else 0
            budget = self._host.calculate_trip_energy(
                cand["coords"],
                planned_drill_units=planned_mine,
                planned_scans=planned_scan,
                mine_item_id=cand.get("harvest_item"),
                mine_purity=cand.get("purity"),
            )

            # A full 10-unit haul is only ever a planning assumption for the
            # feasibility check, not a hard requirement -- a vehicle whose
            # battery can never fit 10 units' worth of round trip (e.g. a
            # Rover with no bigger battery available) would otherwise reject
            # every site and sit at base forever despite live demand and a
            # perfectly reachable partial load. If the full haul doesn't fit,
            # fall back to whatever IS affordable (max_mineable_units() --
            # same estimator already used below to size the real mining call)
            # and retry the budget check with that instead. Only 0 affordable
            # units is a genuine rejection.
            partial_load = False
            if not budget["is_achievable"] and cand["type"] == "mine":
                affordable = self._host.max_mineable_units(cand["coords"], cand["harvest_item"], cand.get("purity"))
                if affordable > 0:
                    self._host.log.debug(f"{cand['key']}: full {planned_mine}-unit load needs {budget['total_required_wh']:.1f} Wh, not affordable; retrying at {affordable} units.")
                    planned_mine = affordable
                    budget = self._host.calculate_trip_energy(
                        cand["coords"],
                        planned_drill_units=planned_mine,
                        planned_scans=planned_scan,
                        mine_item_id=cand.get("harvest_item"),
                        mine_purity=cand.get("purity"),
                    )
                    partial_load = budget["is_achievable"]

            if budget["is_achievable"]:
                budget_candidates += 1
                claimed = self._host.claim_target(cand["key"], cand)
                if not claimed:
                    claims_lost += 1
                    self._host.log.debug(f"{cand['key']}: within budget ({budget['total_required_wh']:.1f} Wh) but claim lost to a peer; trying next candidate.")
                    continue
                self._host.log.debug(
                    f"[{self._host.name}] select_best_mining_target(): won {cand['key']} (priority={cand.get('priority')}, "
                    f"tier={'need' if cand.get('tier') == TIER_NEED else 'stock'}, purity={cand.get('purity')}) at {cand['coords']}, budget={budget['total_required_wh']:.1f} Wh."
                )
                if partial_load:
                    self._host.log.print(f"[{self._host.name}] {cand['key']}: battery can't afford a full load -- heading out for a partial ~{planned_mine}-unit load instead of standing by.")
                self.current_target_reserved = False
                if cand["type"] == "mine":
                    estimated_units = self._host.max_mineable_units(cand["coords"], cand["harvest_item"], cand.get("purity"))
                    if cand.get("max_units") is not None:
                        estimated_units = max(0, min(estimated_units, cand["max_units"]))
                    cand["estimated_units"] = estimated_units
                    if estimated_units > 0:
                        mining_reservations.reserve_yield(self._host.name, cand["key"], cand["harvest_item"], estimated_units, self._host.get_current_tick(), outpost_id=cand.get("outpost_id"))
                        self.current_target_reserved = True
                self.current_target = cand
                self.current_target_key = cand["key"]
                self._host.save_mission(cand["type"], cand)
                self._host.log.trace(f"select_best_mining_target() exit: chose {cand['key']}, estimated_units={cand.get('estimated_units')}")
                _ret = cand, budget, {"candidate_count": len(candidates), "budget_candidates": budget_candidates, "claims_lost": claims_lost, "cheapest_rejected": cheapest_rejected}
                self._host.log.end()
                return _ret
            else:
                if cheapest_rejected is None or budget["total_required_wh"] < cheapest_rejected["total_required_wh"]:
                    cheapest_rejected = budget
                self._host.log.debug(f"{cand['key']}: unreachable within budget ({budget['total_required_wh']:.1f} Wh required); rejected.")

        self._host.log.trace(f"select_best_mining_target() exit: no achievable candidate ({budget_candidates}/{len(candidates)} within budget).")
        _ret = None, None, {"candidate_count": len(candidates), "budget_candidates": budget_candidates, "claims_lost": claims_lost, "cheapest_rejected": cheapest_rejected}
        self._host.log.end()
        return _ret

    def restore_yield_reservation_flag(self):
        """
        Called once after VehicleController.__init__'s load_mission() resumes
        a mission post-reload: reservations live in the archive independently
        of the in-memory current_target_reserved flag (see vehicle.py), so a
        resumed mine-type mission needs this to re-arm refresh_yield()/
        release_yield() instead of silently letting its reservation go stale.
        """
        self.current_target_reserved = False
        if not self.current_target_key:
            return
        entry = mining_reservations.reservation_of(self._host.name)
        if entry is not None and entry["target_key"] == self.current_target_key:
            self.current_target_reserved = True

    def mine_current_site(self, max_units=None):
        """Extracts minerals using the mounted Drill Module while enforcing battery & cargo limits."""
        if not hasattr(self._host.vehicle, "drill"):
            self._host.log.level("error").print(f"[{self._host.name}] Error: No DrillModule mounted!")
            return 0

        cargo_capacity = self._host.vehicle.cargo.capacity() if hasattr(self._host.vehicle, "cargo") else 10
        if max_units is None:
            max_units = cargo_capacity
        # Callers may pass a stockpile headroom far above what the hold can
        # take (e.g. 1999 left to a 2000-unit stock target); the cargo.full()
        # check stops us anyway, so cap here to keep progress logs honest.
        free_space = cargo_capacity - self._host.vehicle.cargo.count() if hasattr(self._host.vehicle, "cargo") else cargo_capacity
        max_units = max(0, min(max_units, free_space))

        self._host.publish_telemetry("MINING")
        mined_count = 0
        self.mining_interrupted_battery = False

        self._host.log.start(f"[{self._host.name}] Mining (up to {max_units} units, cargo {self._host.vehicle.cargo.count()}/{cargo_capacity})")
        while mined_count < max_units:
            if self._host.vehicle.cargo.full():
                self._host.log.print(f"[{self._host.name}] Cargo hold full ({cargo_capacity}/{cargo_capacity}). Finishing mining operation.")
                break

            if self._host.is_recalled():
                self._host.log.print(f"[{self._host.name}] Recall requested; ceasing extraction to return to base.")
                break

            curr_wh, _, _ = self._host.get_battery()
            # Comfortable (not bare-minimum) reserve: stopping here still leaves
            # enough charge for a normal-speed return, instead of grinding down
            # to the true floor and being forced to crawl home at minimum throttle.
            needed_to_return = self._host.energy_needed_to_return_comfortably()
            if curr_wh <= (needed_to_return + self._host.MINE_WH_PER_UNIT * 1.5):
                self._host.log.print(f"[{self._host.name}] Reached return energy threshold ({curr_wh:.1f} Wh left). Ceasing extraction for recharge.")
                self.mining_interrupted_battery = True
                break

            m_res = self._host.vehicle.drill.mine()
            if m_res.status == "ok":
                mined_count += 1
                if self.current_target_key:
                    self._host.clear_unsupported_target(self.current_target_key)
                self._host.log.trace(f"[{self._host.name}] Mined unit {mined_count}/{max_units}. Cargo: {self._host.vehicle.cargo.count()}/{cargo_capacity}.")
            elif m_res.status == "busy":
                flush_all()
                sleep(0.5)
            else:
                self._host.log.print(f"[{self._host.name}] Drill finished or stopped: {m_res.status} - {m_res.message}")
                if m_res.status in ["tier_too_low", "too_hard", "research_required", "depleted", "not_found", "empty"]:
                    if self.current_target_key:
                        self._host.blacklist_target(self.current_target_key, m_res.status, m_res.message, scanner_type="drill")
                break

            if self.current_target_key:
                self._host.refresh_claim(self.current_target_key)
                if self.current_target_reserved:
                    mining_reservations.refresh_yield(self._host.name, self._host.get_current_tick())

        self._host.log.end(f"[{self._host.name}] Mined {mined_count}/{max_units} units")
        return mined_count

    def mine_until_full_or_exhausted(self, target_coords, max_units=None):
        """
        Mines the current site to cargo capacity (or max_units, if given --
        e.g. a stockpile target's remaining headroom, so a stationed miner
        doesn't overshoot a Warehouse stock target and waste a material slot
        on the overflow), recharging at the nearest station and driving back
        to resume as many times as needed when interrupted by low battery
        (mirrors the recharge-and-resume pattern used for construction jobs
        in pioneer.py's execute_construction()). max_units bounds the whole
        job, units unloaded at a base stop included, and an at-base unload
        ends the job so the next cycle picks its target from current demand.
        """
        self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() enter: target_coords={target_coords}, max_units={max_units}")
        total_mined = self.mine_current_site(max_units=max_units)

        while getattr(self, "mining_interrupted_battery", False) and not self._host.vehicle.cargo.full():
            if self._host.is_recalled():
                self._host.log.print(f"[{self._host.name}] Recall requested; not resuming mining after recharge.")
                self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() exit: recalled, total_mined={total_mined}")
                return
            left = None if max_units is None else max_units - total_mined
            if left is not None and left <= 0:
                break
            self._host.log.start(f"[{self._host.name}] Mining job at {target_coords} interrupted by low battery; recharge and resume")
            mined, stop_reason = self._recharge_and_resume_mining(target_coords, left)
            self._host.log.end(f"[{self._host.name}] {'Resumed, mined ' + str(mined) + ' more' if stop_reason is None else 'Not resumed: ' + stop_reason}")
            total_mined += mined
            if stop_reason is not None:
                self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() exit: {stop_reason}, total_mined={total_mined}")
                return
        self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() exit: complete, total_mined={total_mined}")

    def _recharge_and_resume_mining(self, target_coords, max_units):
        """One recharge detour and resumed mining pass; returns (units mined, reason it stopped or None to keep going).

        max_units is what the job may still mine (None = up to cargo capacity).
        """
        if self.current_target_key:
            self._host.refresh_claim(self.current_target_key)
            if self.current_target_reserved:
                mining_reservations.refresh_yield(self._host.name, self._host.get_current_tick())

        nearest_cs, _ = self._host.get_nearest_charging_station()
        reached_cs = self._host.drive_to(nearest_cs[0], nearest_cs[1], precision=1.0)
        if not reached_cs:
            self._host.log.level("warn").print(f"[{self._host.name}] Failed to reach charging station during mining interruption.")
            return 0, "could not reach charging station"

        # A battery-interruption recharge stop can land at the home base
        # station itself (not just some remote field station) -- if so,
        # and cargo is already carrying ore, unload it *before* recharging:
        # recharge_at_station() can take several real minutes, and ore in
        # cargo the whole time is ore the Smelter can't touch. The load is
        # then delivered, so the job ends: resuming would keep mining this
        # ore with an empty hold and never re-check demand (a stationed
        # miner whose battery ran out before its hold filled stockpiled one
        # ore for hours while the others ran dry).
        delivered = self._host.is_at_base() and self._host.vehicle.cargo.count() > 0
        if delivered:
            self._host.log.print(f"[{self._host.name}] At base with cargo aboard; unloading before recharging.")
            self._host.unload_cargo()

        self._host.recharge_at_station(target_level=1.0, station_coords=nearest_cs)

        # Pioneer-only Sonar/Drill upgrade at a base stop inside the job
        # (lib/pioneer_upgrade.py). hasattr-gated: RoverController shares
        # this mixin without PioneerUpgradeMixin.
        mid_job_upgrade = getattr(self._host, "run_module_upgrades_mid_job", None)
        if mid_job_upgrade is not None:
            mid_job_upgrade()
        if delivered:
            return 0, "load delivered at base"

        self._host.log.print(f"[{self._host.name}] Recharged to 100%. Returning to resume mining at {target_coords}...")
        if self.current_target:
            self._host.publish_telemetry("OUTBOUND", self.current_target.get("name", "mining site"))
        reached_site = self._host.drive_with_recharge(target_coords[0], target_coords[1], precision=1.5)
        if not reached_site:
            self._host.log.level("warn").print(f"[{self._host.name}] Could not reach mining site after recharge.")
            return 0, "could not reach site after recharge"

        remaining_space = self._host.vehicle.cargo.capacity() - self._host.vehicle.cargo.count()
        if max_units is not None:
            remaining_space = min(remaining_space, max(0, max_units))
        if remaining_space > 0:
            return self.mine_current_site(max_units=remaining_space), None
        return 0, "no remaining space"

    def run_stationed_mining_loop(self, outpost_id):
        """
        Continuous loop wrapper around _stationed_mining_cycle() -- one full
        cycle per iteration, recall-checked and exception-guarded, same shape
        as run_pull_loop(). This is what a thin entrypoint
        script should call directly (a single line: no while/recall logic
        belongs there -- see CODE_GUIDES.md#module-layout).
        """
        self._host.log.print(f"Pioneer Mining Controller ({self._host.name}) online. Assigned base slot: {self._host.assigned_slot_coords}. Stationed at '{outpost_id}'.")
        validate_game_version()
        while True:
            reset_all()
            try:
                if self._host.handle_recall_if_active():
                    flush_all()
                    sleep(5.0)
                    continue
                self._stationed_mining_cycle(outpost_id)
            except Exception as e:
                self._host.log.level("error").print(f"[{self._host.name}] Stationed mining exception: {e}. Executing emergency failsafe brake.")
                try:
                    self._host.vehicle.nav.brake()
                except Exception as error:
                    swallowed("vehicle_mining.VehicleMiningMixin.run_stationed_mining_loop: self._host.vehicle.nav.brake", error)
                try:
                    self._host.release_target_claim()
                except Exception as error:
                    swallowed("vehicle_mining.VehicleMiningMixin.run_stationed_mining_loop: self._host.release_target_claim", error)
                flush_all()
                sleep(5.0)

    def _stationed_mining_cycle(self, outpost_id):
        """
        One mining cycle for a vehicle stationed at outpost_id (not home) --
        see TODO.md Phase 3's Multi-Outpost Production Network. Mines this
        outpost's assigned ores (lib/outpost_mining.py) up to their stock
        targets, independent of home's live demand, and returns/unloads at
        this outpost rather than home (both already follow from
        self.home_base -- see VehicleController.__init__ and
        vehicle_cargo.py's unload_cargo()). Mirrors run_expedition_cycle()'s
        (rover.py) overall shape, swapping demand-driven target selection for
        stockpile-driven selection.
        """
        if self._host.is_at_base():
            curr_wh, cap_wh, lvl = self._host.get_battery()
            # Top off only at an outpost with its own Charging Station.
            # Without one, the station trip and the transfer back cost the
            # charge it gains; select_best_mining_target() budgets from what
            # is on board and the energy-reject branch below recharges.
            if lvl < 0.95 and self._base_has_charger():
                self._host.log.print(f"[{self._host.name}] Battery at {lvl*100:.0f}%. Recharging to 100% before launch...")
                self._host.recharge_at_station(target_level=1.0)
            # Pioneer-only auto-upgrade/Sport-Nav-request pass -- see
            # lib/pioneer_upgrade.py. hasattr-gated since this mixin is
            # shared with RoverController, which never mixes in
            # PioneerUpgradeMixin.
            upgrade_cycle = getattr(self._host, "handle_upgrade_cycle_if_idle", None)
            if upgrade_cycle is not None:
                upgrade_cycle()

        # Same reload-resume safety net as run_expedition_cycle():
        # a target restored via load_mission() after a script reload is
        # expected mid-mission WIP, not stale leftover cargo.
        has_resumable_target = bool(self.current_target_key and self.current_target and self.current_target.get("coords"))

        if has_resumable_target and not self.cargo_matches_target(self.current_target):
            self._host.log.print(f"[{self._host.name}] Cargo holds a different material than the resumed target's {self.current_target.get('harvest_item')}; unloading before resuming.")
            has_resumable_target = False
        elif has_resumable_target and self.cargo_full_for_resume():
            self._host.log.print(f"[{self._host.name}] Cargo full; unloading before resuming target '{self.current_target_key}'.")
            has_resumable_target = False

        if not has_resumable_target and self._host.vehicle.cargo.count() > 0:
            if not self._host.is_at_base():
                self._host.log.print(f"[{self._host.name}] Cargo aboard but not at base (resuming after an interruption). Returning to base first.")
                if not self._host.return_to_base():
                    self._host.log.level("warn").print(f"[{self._host.name}] Return trip incomplete this cycle; will retry.")
                    flush_all()
                    sleep(5.0)
                    return
            if self._host.unload_cargo() < 0:
                self._host.publish_telemetry("WAITING_INVENTORY_SPACE")
                flush_all()
                sleep(10.0)
                return
            # Next cycle starts empty at base, so its recharge and idle
            # upgrade pass run before a target is picked.
            return

        # Transfer: a Pioneer freshly deployed at home, or re-stationed to
        # another outpost, starts away from its base slot. Trip budgets from
        # there count the long transfer leg on every attempt, so a small
        # battery rejects every site. Move to the base slot first; the next
        # cycle tops off and plans from there.
        if not has_resumable_target and not self._host.is_at_base():
            self._host.log.print(f"[{self._host.name}] Away from outpost '{outpost_id}' base slot {self._host.get_home_slot_coords()}; transferring there before mining.")
            if not self._host.return_to_base():
                self._host.log.level("warn").print(f"[{self._host.name}] Transfer to outpost '{outpost_id}' incomplete this cycle; will retry.")
                flush_all()
                sleep(5.0)
            return

        candidates = []
        diagnostics = {}
        if has_resumable_target:
            self._host.log.print(f"[{self._host.name}] Resuming previously claimed target '{self.current_target_key}' after reload.")
            target = self.current_target
            self._host.log.trace(f"[{self._host.name}] _stationed_mining_cycle(): calculate_trip_energy() for resumed target {target['coords']}")
            budget = self._host.calculate_trip_energy(
                target["coords"],
                planned_drill_units=10,
                mine_item_id=target.get("harvest_item"),
                mine_purity=target.get("purity"),
            )
            self._host.log.trace(f"[{self._host.name}] _stationed_mining_cycle(): budget total_required_wh={budget['total_required_wh']:.1f}, is_achievable={budget['is_achievable']}")
        else:
            candidates = self.build_local_stockpile_candidates(outpost_id)
            target, budget, diagnostics = self.select_best_mining_target(candidates)

        if not target or not budget:
            cheapest = diagnostics.get("cheapest_rejected")
            if cheapest is not None and self._charge_would_reach(cheapest):
                self._host.log.print(f"[{self._host.name}] No stockpile site in range on {cheapest['current_wh']:.0f} Wh; charging at the nearest Charging Station.")
                self._host.recharge_at_station(target_level=1.0)
                return
            reason = self.stockpile_empty_reason if not candidates else self._stockpile_reject_reason(diagnostics)
            self._host.log.print(f"[{self._host.name}] No stockpile target at outpost '{outpost_id}': {reason}. Standing by.")
            self._host.publish_telemetry("IDLE_AT_OUTPOST")
            flush_all()
            sleep(30.0)
            return

        self._host.log.start(f"[{self._host.name}] Stockpile run: {target['harvest_item']} for outpost '{outpost_id}'")
        outcome = self._stationed_stockpile_trip(outpost_id, target, budget)
        self._host.log.end(f"[{self._host.name}] {outcome}")

    def _base_has_charger(self):
        """True when this vehicle's stationed outpost has its own Charging Station (resolved at construction)."""
        return self._host.home_charging_station is not None

    def _charge_would_reach(self, cheapest):
        """
        True when an outpost without its own Charging Station should recharge
        for the cheapest out-of-range site: a full battery, less the transfer
        from the nearest station back to the base slot, covers its trip.
        Battery at 95%+ gains too little to change the verdict.
        """
        if self._base_has_charger():
            return False
        curr_wh, cap_wh, lvl = self._host.get_battery()
        if lvl >= 0.95:
            return False
        slot = self._host.assigned_slot_coords
        cs_coords, _ = self._host.get_nearest_charging_station(from_coords=slot)
        transfer_wh = self._host.energy_wh_for_leg(self._host.distance_between(cs_coords, slot), self._host.cruise_throttle)
        return cheapest["total_required_wh"] <= cap_wh - transfer_wh

    def _stockpile_reject_reason(self, diagnostics):
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

    def _stationed_stockpile_trip(self, outpost_id, target, budget):
        """Outbound drive, mining, return and unload for one stockpile target; returns the outcome text."""
        coords = target["coords"]
        self._host.log.print(
            f"[{self._host.name}] Reserved {target['name']} to stockpile {target['harvest_item']} "
            f"for outpost '{outpost_id}' at {coords} (Est. trip cost: {budget['total_required_wh']:.1f} Wh)."
        )
        root = fleet_intent.haul_root([target["harvest_item"]], outpost_id) or f"{outpost_id} stock"
        self._host.set_intent(fleet_intent.describe("mining", [target["harvest_item"]], at=target["name"], root=root))
        self._host.publish_telemetry("OUTBOUND", target["name"])

        reached = self._host.drive_with_recharge(coords[0], coords[1])
        if not reached:
            self._host.log.level("warn").print(f"[{self._host.name}] Could not safely complete outbound trip. Returning to outpost.")
            self._host.return_to_base()
            return "Outbound trip incomplete"

        # Cap this trip to the stockpile target's remaining headroom (net of
        # peers' reserved trips), not just cargo capacity. A full load past
        # ore_stock_target() (default storage.default_stock_target()) spills
        # into a second Warehouse material slot, one of only 5 shared by every
        # assigned ore. A larger need-tier request (stockpile_need()) raises it.
        item_id = target["harvest_item"]
        remaining_target = max(self.stockpile_headroom(outpost_id, item_id), self.stockpile_need(outpost_id).get(item_id, 0))
        self.mine_until_full_or_exhausted(coords, max_units=max(1, remaining_target))

        if not self._host.return_to_base():
            self._host.log.level("warn").print(f"[{self._host.name}] Return trip incomplete this cycle; will retry.")
            flush_all()
            sleep(5.0)
            return "Return trip incomplete"

        # Back at the stationed outpost -- release the claim and its yield
        # reservation however this trip ended (cargo full, site depleted,
        # etc.), so the next cycle re-evaluates current markers and demand.
        # Resuming skips the unsupported-target check candidate selection
        # applies, so a kept claim could grind a depleted site forever.
        self._host.release_target_claim()

        if self._host.unload_cargo() < 0:
            self._host.publish_telemetry("WAITING_INVENTORY_SPACE")
            flush_all()
            sleep(10.0)
            return "Unload blocked, no inventory space"
        if self._base_has_charger():
            self._host.recharge_at_station(target_level=1.0)
        self._host.publish_telemetry("READY_AT_OUTPOST")
        return f"Stockpile run complete; secured at outpost '{outpost_id}'"
