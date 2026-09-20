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
from version_guard import validate_game_version
from storage import total_stock
from archive import archive
import outpost_mining
import mining_reservations
from typing import TYPE_CHECKING

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


class VehicleMiningMixin:
    """Mineral-site discovery, priority-sorted claiming, and drill execution."""

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

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
        cargo -- see run_expedition_cycle() (rover.py) / run_mining_loop()
        (pioneer.py).
        """
        if not hasattr(self._host.vehicle, "cargo") or self._host.vehicle.cargo.count() == 0:
            return True
        harvest_item = target.get("harvest_item") if target else None
        if not harvest_item:
            return True  # non-mining target (e.g. a POI survey) has no ore to mismatch against
        try:
            stacks = self._host.vehicle.cargo.stacks()
        except Exception:
            return True  # can't verify; don't block resumption over an unreadable stacks() call
        for stack in stacks:
            item_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if item_id and count > 0 and item_id != harvest_item:
                return False
        return True

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

        raw_demands = get_raw_material_demands()
        if not raw_demands:
            self._host.log.debug(f"[{self._host.name}] build_mineral_site_candidates(): no active raw-material demand; skipping candidate search.")
            return []

        max_drill_hardness = 1.0
        if hasattr(self._host.vehicle, "drill") and hasattr(self._host.vehicle.drill, "hardness_limit"):
            try:
                max_drill_hardness = self._host.vehicle.drill.hardness_limit()
            except Exception:
                max_drill_hardness = 1.0
        self._host.log.debug(
            f"[{self._host.name}] build_mineral_site_candidates(): demand={raw_demands}, max_drill_hardness={max_drill_hardness}, "
            f"deprioritize_hardness_at_or_below={deprioritize_hardness_at_or_below}"
        )

        unsupported_targets = self._host.get_unsupported_targets()

        # No peer-claim filter here: multiple Pioneers can now mine the same
        # POI, so a peer already working a site is no longer disqualifying --
        # see select_best_mining_target()'s yield reservation instead, which
        # debits home-demand for ore already promised by an in-flight trip.
        candidates = []
        try:
            for site in journal.surveyed_sites("nocturna"):
                site_item = getattr(site, "item_id", None)
                if site.kind() != "mineral" or raw_demands.get(site_item, 0) <= 0:
                    continue
                hardness = getattr(site, "hardness", 99)
                if hardness > max_drill_hardness:
                    self._host.log.debug(f"[{self._host.name}] site_{site.id}: hardness {hardness} exceeds drill limit {max_drill_hardness}; skipped.")
                    continue

                key = f"site_{site.id}"
                if key in unsupported_targets:
                    can_attempt, reason = self._host.can_attempt_target(key, unsupported_targets[key])
                    if not can_attempt:
                        self._host.log.debug(f"[{self._host.name}] {key}: blocked by unsupported-target record ({reason}); skipped.")
                        continue

                priority = 2
                if deprioritize_hardness_at_or_below is not None and hardness <= deprioritize_hardness_at_or_below:
                    priority = 3
                    self._host.log.debug(f"[{self._host.name}] {key}: hardness {hardness} deprioritized (<= {deprioritize_hardness_at_or_below}); priority=3.")

                candidates.append({
                    "key": key,
                    "type": "mine",
                    "coords": (site.x, site.y),
                    "name": f"Site_{site.id}_{getattr(site, 'item_id', 'ore')}",
                    "harvest_item": site_item,
                    "reason": get_raw_material_reason(site_item),
                    "priority": priority,
                    "purity": getattr(site, "purity", None),
                })
        except Exception:
            pass

        self._host.log.debug(f"[{self._host.name}] build_mineral_site_candidates(): {len(candidates)} candidate(s) built.")
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
        """
        journal = get_component("journal")
        if not journal or not hasattr(journal, "surveyed_sites"):
            return []

        assigned = outpost_mining.assigned_ores_for(outpost_id)
        if not assigned:
            return []

        outpost = outpost_mining.outpost_by_id(outpost_id)
        under_target = {
            item_id for item_id in assigned
            if total_stock(item_id, outpost=outpost) < outpost_mining.stock_target_for(outpost_id, item_id)
        }
        if not under_target:
            return []

        max_drill_hardness = 1.0
        if hasattr(self._host.vehicle, "drill") and hasattr(self._host.vehicle.drill, "hardness_limit"):
            try:
                max_drill_hardness = self._host.vehicle.drill.hardness_limit()
            except Exception:
                max_drill_hardness = 1.0

        unsupported_targets = self._host.get_unsupported_targets()

        # No peer-claim filter here either (see build_mineral_site_candidates()) --
        # several stationed Pioneers can converge on the same under-target ore;
        # it self-corrects next cycle once stock arrives (total_stock() is read
        # live above), so no reservation bookkeeping is needed for this path.
        candidates = []
        try:
            for site in journal.surveyed_sites("nocturna"):
                site_item = getattr(site, "item_id", None)
                if site.kind() != "mineral" or site_item not in under_target:
                    continue
                hardness = getattr(site, "hardness", 99)
                if hardness > max_drill_hardness:
                    continue
                if outpost_mining.site_assigned_outpost(site.x, site.y) != outpost_id:
                    continue

                key = f"site_{site.id}"
                if key in unsupported_targets:
                    can_attempt, _ = self._host.can_attempt_target(key, unsupported_targets[key])
                    if not can_attempt:
                        continue

                candidates.append({
                    "key": key,
                    "type": "mine",
                    "coords": (site.x, site.y),
                    "name": f"Site_{site.id}_{site_item}",
                    "harvest_item": site_item,
                    "reason": f"stockpiling for outpost '{outpost_id}'",
                    "priority": 2,
                    "purity": getattr(site, "purity", None),
                })
        except Exception:
            pass

        self._host.log.debug(f"[{self._host.name}] build_local_stockpile_candidates('{outpost_id}'): {len(candidates)} candidate(s) built (under_target={under_target}).")
        return candidates

    def select_best_mining_target(self, candidates, reserve_demand=False):
        """
        Sorts candidates by (priority, -purity_rank, distance) -- lower
        priority number wins first, then richer veins (see PURITY_RANK) win
        over merely-closer ones within the same priority tier, distance only
        breaking ties between equally-rich candidates -- then claims the
        first one that fits the round-trip energy budget. Returns (target,
        budget, diagnostics); target is None when nothing is currently
        achievable.

        reserve_demand=True (home-demand candidates only -- pass True from
        build_mineral_site_candidates() callers, False for
        build_local_stockpile_candidates() callers) additionally estimates
        this trip's mineable yield from energy on board
        (max_mineable_units()) and registers it via
        mining_reservations.reserve_yield() so a peer's home-demand search
        this cycle or later sees the deficit already promised and doesn't
        also chase it (see lib/production.py's get_raw_material_demands()).
        The stockpile path skips this -- it's already self-bounded by each
        outpost's own stock target, re-read live every cycle. Either way, the
        estimate is stashed on the candidate as "estimated_units" so callers
        can size the actual mining call instead of defaulting to cargo
        capacity.
        """
        pos = self._host.get_position()
        candidates = sorted(
            candidates,
            key=lambda c: (
                c.get("priority", 2),
                -PURITY_RANK.get(c.get("purity"), 0),
                self._host.distance_between(pos, c["coords"]),
            ),
        )

        self._host.log.trace(f"[{self._host.name}] select_best_mining_target() enter: {len(candidates)} candidate(s), reserve_demand={reserve_demand}")
        budget_candidates = 0
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

            if budget["is_achievable"]:
                budget_candidates += 1
                claimed = self._host.claim_target(cand["key"], cand)
                if not claimed:
                    self._host.log.debug(f"[{self._host.name}] {cand['key']}: within budget ({budget['total_required_wh']:.1f} Wh) but claim lost to a peer; trying next candidate.")
                    continue
                self._host.log.debug(
                    f"[{self._host.name}] select_best_mining_target(): won {cand['key']} (priority={cand.get('priority')}, "
                    f"purity={cand.get('purity')}) at {cand['coords']}, budget={budget['total_required_wh']:.1f} Wh."
                )
                self.current_target_reserved = False
                if cand["type"] == "mine":
                    estimated_units = self._host.max_mineable_units(cand["coords"], cand["harvest_item"], cand.get("purity"))
                    cand["estimated_units"] = estimated_units
                    if reserve_demand and estimated_units > 0:
                        mining_reservations.reserve_yield(self._host.name, cand["key"], cand["harvest_item"], estimated_units, self._host.get_current_tick())
                        self.current_target_reserved = True
                self.current_target = cand
                self.current_target_key = cand["key"]
                self._host.save_mission(cand["type"], cand)
                self._host.log.trace(f"[{self._host.name}] select_best_mining_target() exit: chose {cand['key']}, estimated_units={cand.get('estimated_units')}")
                return cand, budget, {"candidate_count": len(candidates), "budget_candidates": budget_candidates}
            else:
                self._host.log.debug(f"[{self._host.name}] {cand['key']}: unreachable within budget ({budget['total_required_wh']:.1f} Wh required); rejected.")

        self._host.log.trace(f"[{self._host.name}] select_best_mining_target() exit: no achievable candidate ({budget_candidates}/{len(candidates)} within budget).")
        return None, None, {"candidate_count": len(candidates), "budget_candidates": budget_candidates}

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
        reservations = archive.get(mining_reservations.RESERVED_YIELD_KEY, {})
        if not isinstance(reservations, dict):
            return
        entry = reservations.get(self.current_target_key)
        if not isinstance(entry, dict):
            entry = None
        if entry is not None and entry.get("vehicle") == self._host.name:
            self.current_target_reserved = True

    def mine_current_site(self, max_units=None):
        """Extracts minerals using the mounted Drill Module while enforcing battery & cargo limits."""
        if not hasattr(self._host.vehicle, "drill"):
            self._host.log.level("error").print(f"[{self._host.name}] Error: No DrillModule mounted!")
            return 0

        cargo_capacity = self._host.vehicle.cargo.capacity() if hasattr(self._host.vehicle, "cargo") else 10
        if max_units is None:
            max_units = cargo_capacity

        self._host.publish_telemetry("MINING")
        mined_count = 0
        self.mining_interrupted_battery = False

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
                self._host.log.print(f"[{self._host.name}] Mined unit {mined_count}/{max_units}. Cargo: {self._host.vehicle.cargo.count()}/{cargo_capacity}.")
            elif m_res.status == "busy":
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
                    mining_reservations.refresh_yield(self._host.name, self.current_target_key, self._host.get_current_tick())

        return mined_count

    def mine_until_full_or_exhausted(self, target_coords, max_units=None):
        """
        Mines the current site to cargo capacity (or max_units, if given --
        e.g. a stockpile target's remaining headroom, so a stationed miner
        doesn't overshoot a Warehouse stock target and waste a material slot
        on the overflow), recharging at the nearest station and driving back
        to resume as many times as needed when interrupted by low battery
        (mirrors the recharge-and-resume pattern used for construction jobs
        in pioneer.py's execute_construction()).
        """
        self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() enter: target_coords={target_coords}, max_units={max_units}")
        total_mined = self.mine_current_site(max_units=max_units)

        while getattr(self, "mining_interrupted_battery", False) and not self._host.vehicle.cargo.full():
            if self._host.is_recalled():
                self._host.log.print(f"[{self._host.name}] Recall requested; not resuming mining after recharge.")
                self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() exit: recalled, total_mined={total_mined}")
                return
            self._host.log.print(f"[{self._host.name}] Mining job at {target_coords} interrupted by low battery. Diverting to recharge and resume.")
            if self.current_target_key:
                self._host.refresh_claim(self.current_target_key)
                if self.current_target_reserved:
                    mining_reservations.refresh_yield(self._host.name, self.current_target_key, self._host.get_current_tick())

            nearest_cs, _ = self._host.get_nearest_charging_station()
            reached_cs = self._host.drive_to(nearest_cs[0], nearest_cs[1], precision=1.0)
            if not reached_cs:
                self._host.log.level("warn").print(f"[{self._host.name}] Failed to reach charging station during mining interruption.")
                self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() exit: could not reach charging station, total_mined={total_mined}")
                return

            # A battery-interruption recharge stop can land at the home base
            # station itself (not just some remote field station) -- if so,
            # and cargo is already carrying ore, unload it *before* recharging,
            # not after: recharge_at_station() can take several real minutes
            # (0% -> 100%), and ore sitting in cargo the whole time is ore the
            # Smelter can't touch -- unloading first gets it into circulation
            # immediately instead of leaving it stranded for the entire
            # charge. Free capacity also means the resumed mine_current_site()
            # call below can fill more before the next interruption, not just
            # recover exactly what was lost.
            if self._host.is_at_base() and self._host.vehicle.cargo.count() > 0:
                self._host.log.print(f"[{self._host.name}] At base with cargo aboard; unloading before recharging.")
                self._host.unload_cargo()

            self._host.recharge_at_station(target_level=1.0, station_coords=nearest_cs)

            self._host.log.print(f"[{self._host.name}] Recharged to 100%. Returning to resume mining at {target_coords}...")
            if self.current_target:
                self._host.publish_telemetry("OUTBOUND", self.current_target.get("name", "mining site"))
            reached_site = self._host.drive_with_recharge(target_coords[0], target_coords[1], precision=1.5)
            if not reached_site:
                self._host.log.level("warn").print(f"[{self._host.name}] Could not reach mining site after recharge.")
                self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() exit: could not reach site after recharge, total_mined={total_mined}")
                return

            remaining_space = self._host.vehicle.cargo.capacity() - self._host.vehicle.cargo.count()
            if max_units is not None:
                remaining_space = min(remaining_space, max(0, max_units - self._host.vehicle.cargo.count()))
            if remaining_space > 0:
                total_mined += self.mine_current_site(max_units=remaining_space)
            else:
                self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() exit: no remaining space, total_mined={total_mined}")
                return
        self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() exit: complete, total_mined={total_mined}")

    def run_stationed_mining_loop(self, outpost_id):
        """
        Continuous loop wrapper around _stationed_mining_cycle() -- one full
        cycle per iteration, recall-checked and exception-guarded, same shape
        as run_mining_loop()/run_haul_loop(). This is what a thin entrypoint
        script should call directly (a single line: no while/recall logic
        belongs there -- see CLAUDE.md's thin-entrypoint rule).
        """
        self._host.log.print(f"Pioneer Mining Controller ({self._host.name}) online. Assigned base slot: {self._host.assigned_slot_coords}. Stationed at '{outpost_id}'.")
        validate_game_version()
        while True:
            try:
                if self._host.handle_recall_if_active():
                    sleep(5.0)
                    continue
                self._stationed_mining_cycle(outpost_id)
            except Exception as e:
                self._host.log.level("error").print(f"[{self._host.name}] Stationed mining exception: {e}. Executing emergency failsafe brake.")
                try:
                    self._host.vehicle.nav.brake()
                except Exception:
                    pass
                try:
                    self._host.release_target_claim()
                except Exception:
                    pass
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
            if lvl < 0.95:
                self._host.log.print(f"[{self._host.name}] Battery at {lvl*100:.0f}%. Recharging to 100% before launch...")
                self._host.recharge_at_station(target_level=1.0)

        # Same reload-resume safety net as run_expedition_cycle()/run_mining_loop():
        # a target restored via load_mission() after a script reload is
        # expected mid-mission WIP, not stale leftover cargo.
        has_resumable_target = bool(self.current_target_key and self.current_target and self.current_target.get("coords"))

        if has_resumable_target and not self.cargo_matches_target(self.current_target):
            self._host.log.print(f"[{self._host.name}] Cargo holds a different material than the resumed target's {self.current_target.get('harvest_item')}; unloading before resuming.")
            has_resumable_target = False

        if not has_resumable_target and self._host.vehicle.cargo.count() > 0:
            if not self._host.is_at_base():
                self._host.log.print(f"[{self._host.name}] Cargo aboard but not at base (resuming after an interruption). Returning to base first.")
                if not self._host.return_to_base():
                    self._host.log.level("warn").print(f"[{self._host.name}] Return trip incomplete this cycle; will retry.")
                    sleep(5.0)
                    return
            if self._host.unload_cargo() < 0:
                self._host.publish_telemetry("WAITING_INVENTORY_SPACE")
                sleep(10.0)
                return

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
            target, budget, _ = self.select_best_mining_target(candidates)

        if not target or not budget:
            self._host.log.print(f"[{self._host.name}] No stockpile target at outpost '{outpost_id}': every assigned ore is at its stock target, unreachable, or claimed by a peer. Standing by.")
            self._host.publish_telemetry("IDLE_AT_OUTPOST")
            sleep(30.0)
            return

        coords = target["coords"]
        self._host.log.print(
            f"[{self._host.name}] Reserved {target['name']} to stockpile {target['harvest_item']} "
            f"for outpost '{outpost_id}' at {coords} (Est. trip cost: {budget['total_required_wh']:.1f} Wh)."
        )
        self._host.publish_telemetry("OUTBOUND", target["name"])

        reached = self._host.drive_with_recharge(coords[0], coords[1])
        if not reached:
            self._host.log.level("warn").print(f"[{self._host.name}] Could not safely complete outbound trip. Returning to outpost.")
            self._host.return_to_base()
            return

        # Cap this trip to the stockpile target's remaining headroom, not just
        # cargo capacity -- otherwise a full cargo load routinely overshoots
        # stock_target_for() (default one Warehouse slot, 2000 units) by
        # however much cargo capacity exceeds the remainder, forcing the
        # overflow into a second material slot for no benefit (found from a
        # real Warehouse: iron_ore split 2000+279 across two slots, wasting
        # one of only 5 available for other assigned ores).
        outpost_ref = outpost_mining.outpost_by_id(outpost_id)
        remaining_target = outpost_mining.stock_target_for(outpost_id, target["harvest_item"]) - total_stock(target["harvest_item"], outpost=outpost_ref)
        self.mine_until_full_or_exhausted(coords, max_units=max(1, remaining_target))

        if not self._host.return_to_base():
            self._host.log.level("warn").print(f"[{self._host.name}] Return trip incomplete this cycle; will retry.")
            sleep(5.0)
            return

        # Back at the stationed outpost -- release the claim regardless of how
        # this trip ended (cargo full, site depleted, etc.) so the next cycle
        # always re-evaluates fresh (current markers/demand) instead of blindly
        # resuming the same site forever. Previously the claim only ever
        # cleared via an explicit recall, so a vehicle could keep grinding a
        # site whose marker assignment or stock target had since changed --
        # or, once truly depleted, keep re-attempting it fruitlessly, since
        # resumption skips the unsupported-target check candidate selection
        # would otherwise apply.
        self._host.release_target_claim()

        if self._host.unload_cargo() < 0:
            self._host.publish_telemetry("WAITING_INVENTORY_SPACE")
            sleep(10.0)
            return
        self._host.recharge_at_station(target_level=1.0)
        self._host.publish_telemetry("READY_AT_OUTPOST")
        self._host.log.print(f"[{self._host.name}] Stockpile run complete; secured at outpost '{outpost_id}'.")
