# PullJob: the hauler Pioneer's role (lib/job_base.py contract). The hauler
# floats (docs/plans/dynamic_roles): it fetches what any outpost is missing
# (its pull requests; the highest band first, pull_plan.pull_destinations())
# from any other outpost's free stock, any field Mining Drill's stockpile or
# a Water Pump's salt, and delivers it there, moving its base to that
# outpost (VehicleController.set_base()). Buyable requests at a non-home
# outpost (remote Bio Lab reagents) can also be bought at the Shop on a
# stop at the home outpost. One trip chains up to PULL_MAX_STOPS_PER_TRIP
# sources, nearest-neighbour ordered (planning: lib/pull_plan.py). Every leg
# goes through drive_with_recharge(), which refuses a leg unless the vehicle
# can still reach a charging station afterwards.
#
# Plays nice with other haulers on both ends: planned amounts are reserved
# per source (logistics.pickups "source", so nobody else plans the same
# units there), and in-flight units count against the destination's deficits
# (logistics_requests.in_flight()), so a drone already bringing 800 ore makes
# this one see 800 less demand, and vice versa.
#
# Every trip records its pickups and its delivery in logistics.outpost_flow;
# with no demand, an idle hauler moves its base to the outpost most goods
# leave from per idle hauler there (lib/outpost_flow.py).
# run_job_loop(PullJob(pioneer)) runs it (lib/pioneer.py). Loading and
# unloading: lib/vehicle_cargo.py.

import fleet_intent
import fleet_status
import logistics_requests
import logistics_snapshot
import outpost_flow
import pull_plan
from job_base import Job
from mission import Mission
from swallow import swallowed

# pick() found no work: why, for idle().
NO_DEMAND = "no demand"
SHORT = "short"  # demand, but the plan stays below the minimum load
TRIMMED = "trimmed"  # another hauler's claim cut the trip below the minimum


class PullJob(Job):
    """
    Hauler role. prepare(): the Pioneer's upgrade pass, then cargo already
    aboard is delivered to its pickups' destination first. pick(): plans a
    trip per destination (pull_plan.plan_pull_route()), claims the best
    one's pickups and moves the base there, as a Mission of kind "pull"
    (target "route", "dest"). execute(): drives the stops, then delivers to
    the base. idle(): parks or waits, depending on why pick() found nothing.
    """

    name = "pull"

    def __init__(self, host, poll_interval=10.0):
        super().__init__(host)
        self.poll_interval = poll_interval
        self.recall_delay = poll_interval
        self.idle_delay = poll_interval
        # {source_id: tick} first stops refused as too slow
        # (VehicleCargoMixin.pull_from_source(), PULL_MIN_LEG_THROTTLE),
        # left out of planning for PULL_UNVIABLE_COOLDOWN_TICKS.
        self.unviable = {}
        # Drills already warned about standing on no surveyed site (pull_plan.pull_sources()).
        self.warned_drills = set()
        # Why the last pick() returned None: NO_DEMAND, SHORT or TRIMMED.
        self.wait = NO_DEMAND
        # Tick of the last dispersal move (idle()), None before the first.
        self.dispersed_tick = None

    @property
    def home_id(self):
        """Id of the host's current base (set_base()), where cargo is delivered."""
        return getattr(self.host.home_outpost, "id", None)

    def announce(self):
        self.host.log.print(f"[{self.host.name}] Pull Controller online. Fetching what any outpost needs from outposts and drills (based at '{self.home_id}').")

    def prepare(self):
        """
        The Pioneer's upgrade pass (lib/pioneer_upgrade.py; self-guarded,
        acts only idle at base), then cargo aboard is delivered home before
        any planning. Cargo claimed for another outpost than the base (a
        script reload resets the base to HOME_BASE) moves the base back to
        that destination first. Returns the delivery's delay, None to go on.
        """
        host = self.host
        upgrade_cycle = getattr(host, "handle_upgrade_cycle_if_idle", None)
        if upgrade_cycle is not None:
            upgrade_cycle()
        if host.vehicle.cargo.count() > 0:
            # A failed set_base() (destination gone) keeps the base: the cargo
            # is unloaded there and its pickups released.
            dest_id = logistics_requests.pickup_dest(host.name)
            if dest_id:
                host.set_base(dest_id)
            host.log.debug(f"[{host.name}] pull: cargo aboard; delivering to '{self.home_id}' first.")
            return self._finish_pull_delivery()
        return None

    def pick(self):
        """
        Plans the best trip to any outpost with deficits and claims its
        pickups. Destinations come in band groups, highest first
        (pull_plan.pull_destinations()); within a group each destination's
        trip is planned from the vehicle's position and the best
        logistics_requests.haul_rank() wins; a group with no trip above the
        minimum load falls through to the next. While the tier snapshot is
        FRESH the destinations' deficits come from it and the chosen trip is
        capped at the destination's live deficit before the claim
        (logistics_snapshot.trim_to_live()); a trip trimmed below its minimum
        load is dropped and the destinations are planned once live in the same
        call. The claimed destination
        becomes the base (set_base()). None (self.wait says why) when
        nothing is wanted, every plan is below the minimum load, or the
        claim left less than that.
        """
        host = self.host
        curr_tick = host.get_current_tick()
        # Before any demand/stock read (see claim_pickups()); drops this
        # vehicle's leftovers from an abandoned plan, nothing is aboard.
        seen = logistics_requests.planning_snapshot(host.name)
        reads = logistics_requests.PlanReads(curr_tick, seen)
        # Destination tiers from the tier snapshot when it is FRESH, else read
        # live (a snapshot plan is trimmed to the live deficit before the claim).
        record, state = logistics_snapshot.read_snapshot(curr_tick)
        view = logistics_snapshot.TierView(record, reads, exclude_vehicle=host.name) if state == logistics_snapshot.FRESH else None
        if state == logistics_snapshot.STALE and record is not None:
            host.log.debug(f"[{host.name}] pull: tier snapshot STALE ({curr_tick - record['tick']} ticks old); planning live.")
        best = self._choose(curr_tick, reads, view)
        if best is None:
            return None
        dest, route, planned, wanted = best
        dest_id = dest.id

        legs = [(src["id"], i, a) for src, loads in route for i, a in loads]
        if view is not None:
            # A snapshot plan: capped at the destination's live deficit first; legs left at 0 are not claimed.
            live = logistics_snapshot.trim_to_live(dest, legs, curr_tick, seen, host.name)
            if live != legs:
                host.log.debug(f"[{host.name}] pull: '{dest_id}' filled since the tier snapshot; legs " + ", ".join(f"{s}:{i} {u}->{n}" for (s, i, u), (_s, _i, n) in zip(legs, live) if n < u) + ".")
            legs = [leg for leg in live if leg[2] > 0]
            planned = sum(n for _s, _i, n in legs)
            if planned < wanted:
                # The record is behind the destination (stock arrived since the
                # build) and every hauler reads the same record: plan live now, or
                # this destination would block the lower ones until the next build.
                host.log.debug(f"[{host.name}] pull: '{dest_id}' trimmed to {planned} unit(s) < minimum {wanted} since the tier snapshot; replanning live.")
                logistics_requests.release_pickups(host.name)
                best = self._choose(curr_tick, reads, None)
                if best is None:
                    return None
                dest, route, planned, wanted = best
                dest_id = dest.id
                legs = [(src["id"], i, a) for src, loads in route for i, a in loads]
        # Atomic claim: trimmed by whatever another hauler reserved
        # since `seen` (e.g. two haulers planning on the same tick).
        granted = logistics_requests.claim_pickups(host.name, dest_id, legs, seen, curr_tick) if legs else []
        grant_by_leg = {(s, i): g for s, i, g in granted}
        route = [(src, [(i, grant_by_leg.get((src["id"], i), 0)) for i, _a in loads if grant_by_leg.get((src["id"], i), 0) > 0]) for src, loads in route]
        route = [(src, loads) for src, loads in route if loads]
        claimed = sum(a for _src, loads in route for _i, a in loads)
        if claimed < planned:
            host.log.debug(f"[{host.name}] pull: another hauler reserved part of this trip since planning; {planned} -> {claimed} unit(s).")
        if not route or claimed < wanted:
            host.log.debug(f"[{host.name}] pull: {claimed} unit(s) left after claim < minimum {wanted}; replanning next cycle.")
            # The other destinations are not retried this cycle: the next
            # one replans against the claim that trimmed this one.
            logistics_requests.release_pickups(host.name)
            self.wait = TRIMMED
            return None
        if not host.set_base(dest_id):
            # The destination left the network since planning: nowhere to deliver.
            logistics_requests.release_pickups(host.name)
            self.wait = TRIMMED
            return None
        first = route[0][0]
        return Mission(kind="pull", target_key=first["id"], target={"route": route, "coords": first["coords"], "dest": dest_id}, source="request", tick=curr_tick)

    def _choose(self, curr_tick, reads, view):
        """(dest, route, planned, wanted) of the best trip over the destinations of pull_plan.pull_destinations() (from `view` when given, else live), None when there is none (self.wait says why: NO_DEMAND or SHORT)."""
        groups = pull_plan.pull_destinations(curr_tick, reads, view)
        if not groups:
            self.wait = NO_DEMAND
            return None
        best = self._best_trip(groups, curr_tick, reads)
        if best is None:
            self.wait = SHORT
        return best

    def _best_trip(self, groups, curr_tick, reads):
        """(dest, route, planned, wanted) of the best trip in the first band group of `groups` that has one at or above the minimum load, None when none has."""
        host = self.host
        capacity = host.vehicle.cargo.capacity()
        for group in groups:
            best, best_rank = None, None
            for dest, deficits in group:
                host.log.debug(f"[{host.name}] pull: deficits at '{dest.id}': {deficits}")
                route, reachable, rank = pull_plan.plan_pull_route(host, dest, deficits, capacity, curr_tick, self.unviable, self.warned_drills, reads)
                planned = sum(a for _src, loads in route for _i, a in loads)
                # Minimum trip only over what some source can actually give:
                # deficits nobody holds (or that were left to drones) must not
                # keep a small but real delivery waiting. A route
                # carrying BLOCKER units goes alone; nothing more arrives by waiting.
                blockers = logistics_requests.blocker_units(logistics_requests.route_tier_units(deficits, route))
                wanted = logistics_requests.min_load_units(blockers, reachable)
                if not route or planned <= 0 or planned < wanted:
                    host.log.debug(f"[{host.name}] pull: '{dest.id}': planned {planned} unit(s) < minimum {wanted}.")
                    continue
                if logistics_requests.rank_beats(rank, best_rank):
                    best, best_rank = (dest, route, planned, wanted), rank
            if best is not None:
                return best
        host.log.debug(f"[{host.name}] pull: no trip reaches the minimum load; waiting.")
        return None

    def execute(self, mission):
        """Drives the claimed stops (a stop out of reach drops it and every later one), then delivers to the base or releases the pickups."""
        host = self.host
        # A mission resumed after a reload: the base is back at HOME_BASE.
        # A failed set_base() (destination gone) delivers to the current base.
        dest_id = mission.target.get("dest")
        if dest_id:
            host.set_base(dest_id)
        home_id = self.home_id
        route = mission.target["route"]
        curr_tick = mission.tick
        legs = []
        planned_totals = {}
        for source, loads in route:
            legs.append(source["id"] + " (" + ", ".join(str(a) + "x " + i for i, a in loads) + ")")
            for item_id, amount in loads:
                planned_totals[item_id] = planned_totals.get(item_id, 0) + amount
        source_ids = [src["id"] for src, _loads in route]
        source_label = source_ids[0] + (f" +{len(source_ids) - 1}" if len(source_ids) > 1 else "")
        host.set_intent(fleet_intent.describe("hauling", planned_totals, source_label, home_id, fleet_intent.haul_root(planned_totals, home_id, curr_tick)))
        host.log.start(f"[{host.name}] Pull trip: " + " -> ".join(legs))

        moved_by_source = []
        for index, (source, loads) in enumerate(route):
            # Only a first stop is recorded as unviable: a chained stop refused
            # from an earlier stop may still be fine as a first stop next trip.
            moved_by_item = host.pull_from_source(source, loads, home_id, curr_tick, unviable=self.unviable if index == 0 else None)
            if moved_by_item is None:
                # Unreachable: drop this and every later stop's reservations.
                for later_source, later_loads in route[index:]:
                    for item_id, _amount in later_loads:
                        logistics_requests.reserve_pickup(host.name, home_id, item_id, 0, curr_tick, source_id=later_source["id"])
                break
            moved_by_source.append((source, sum(moved_by_item.values())))
        outpost_flow.record(host.get_current_tick(), sent=outpost_flow.sent_by_outpost(moved_by_source, outpost_flow.founded_outposts()))
        host.log.end(f"[{host.name}] Pickups done; {host.vehicle.cargo.count()} unit(s) aboard.")

        if host.vehicle.cargo.count() > 0:
            return self.poll_interval + self._finish_pull_delivery()
        logistics_requests.release_pickups(host.name)
        if not host.is_at_base():
            host.return_to_base()
        return self.poll_interval

    def parkable(self):
        """Only with no demand: a new request wakes a paused hauler, arriving stock does not."""
        return self.wait == NO_DEMAND

    def idle(self):
        """No trip: disperses and parks at base while waiting (NO_DEMAND pauses, SHORT polls for stock), replans after a trimmed claim (TRIMMED)."""
        host = self.host
        if self.wait in (NO_DEMAND, SHORT):
            # SHORT disperses too: the stock is short everywhere, not out
            # of this hauler's reach, so the wait is best spent at the
            # outpost it will most likely come from.
            try:
                self._disperse()
            except Exception as error:
                swallowed("PullJob._disperse", error)
            if not host.is_at_base():
                host.return_to_base()
            host.publish_telemetry("IDLE_AT_OUTPOST", "no demand" if self.wait == NO_DEMAND else "wanted items not available anywhere yet")
        return self.idle_delay

    def _disperse(self):
        """Moves the base to outpost_flow.dispersal_target() unless a move happened within DISPERSE_COOLDOWN_TICKS."""
        host = self.host
        curr_tick = host.get_current_tick()
        if self.dispersed_tick is not None and curr_tick - self.dispersed_tick < outpost_flow.DISPERSE_COOLDOWN_TICKS:
            return
        idle_by_base = outpost_flow.idle_haulers_by_base(fleet_status.get_all(), curr_tick, exclude=host.name)
        target = outpost_flow.dispersal_target(self.home_id, outpost_flow.founded_outposts(), outpost_flow.read(curr_tick), idle_by_base, host.get_position())
        if target is None or not host.set_base(target):
            return
        self.dispersed_tick = curr_tick
        host.log.print(f"[{host.name}] No trip; dispersing to '{target}' (most outbound flow per idle hauler).")
        # Published before the drive, so other idle haulers count this one there.
        host.publish_telemetry("IDLE_AT_OUTPOST", f"dispersing to '{target}'")

    def on_error(self):
        """
        Nothing to release: pickups stay reserved while cargo may be aboard
        (prepare() delivers it next cycle), and pick()'s planning_snapshot()
        drops an abandoned plan's leftovers.
        """
        return

    def on_leave(self):
        """Releases this vehicle's pickup reservations."""
        logistics_requests.release_pickups(self.host.name)

    def _finish_pull_delivery(self):
        """Drives to the base, unloads, releases this vehicle's pickup debits and recharges; returns the delay (0 delivered, poll_interval to retry)."""
        host = self.host
        host.log.start(f"[{host.name}] Delivering pickups to '{self.home_id}'")
        outcome, delay = self._deliver_pull_cargo()
        host.log.end(f"[{host.name}] {outcome}")
        return delay

    def _deliver_pull_cargo(self):
        """(outcome text, delay) of one delivery attempt."""
        host = self.host
        if not host.intent:
            home_id = self.home_id
            aboard = host.cargo_totals()
            host.set_intent(fleet_intent.describe("hauling", aboard, dest=home_id, root=fleet_intent.haul_root(aboard, home_id)))
        host.publish_telemetry("RETURNING", f"returning to '{self.home_id}' with pickups")
        if not host.return_to_base():
            host.log.level("warn").print(f"[{host.name}] Could not reach '{self.home_id}' to unload; will retry.")
            return "Delivery incomplete: base not reached", self.poll_interval
        unloaded = host.unload_cargo()
        if unloaded < 0:
            host.publish_telemetry("WAITING_INVENTORY_SPACE")
            return "Delivery blocked: no inventory space", self.poll_interval
        outpost_flow.record(host.get_current_tick(), received={self.home_id: unloaded})
        logistics_requests.release_pickups(host.name)
        host.recharge_at_station(target_level=1.0)
        host.publish_telemetry("READY_AT_OUTPOST")
        return "Delivered and recharged", 0
