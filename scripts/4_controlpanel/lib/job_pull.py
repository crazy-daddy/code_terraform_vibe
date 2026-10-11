# PullJob: the hauler Pioneer's role (lib/job_base.py contract). Parked at
# its HOME_BASE, it fetches what that outpost is missing (its pull requests)
# from any other outpost's free stock, any field Mining Drill's stockpile or
# a Water Pump's salt, and brings it home. Buyable requests at a non-home
# HOME_BASE (remote Bio Lab reagents) can also be bought at the Shop on a
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
# run_job_loop(PullJob(pioneer)) runs it (lib/pioneer.py). Loading and
# unloading: lib/vehicle_cargo.py.

import fleet_intent
import logistics_requests
import pull_plan
from job_base import Job
from mission import Mission

# pick() found no work: why, for idle().
NO_DEMAND = "no demand"
SHORT = "short"  # demand, but the plan stays below the minimum load
TRIMMED = "trimmed"  # another hauler's claim cut the trip below the minimum


class PullJob(Job):
    """
    Hauler role. prepare(): the Pioneer's upgrade pass, then cargo already
    aboard is delivered home first. pick(): plans a trip
    (pull_plan.plan_pull_route()) and claims its pickups, as a Mission of
    kind "pull" (target "route"). execute(): drives the stops, then delivers
    home. idle(): parks or waits, depending on why pick() found nothing.
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

    @property
    def home_id(self):
        return getattr(self.host.home_outpost, "id", None)

    def announce(self):
        self.host.log.print(f"[{self.host.name}] Pull Controller online. Fetching what '{self.home_id}' needs from outposts and drills.")

    def prepare(self):
        """
        The Pioneer's upgrade pass (lib/pioneer_upgrade.py; self-guarded,
        acts only idle at base), then cargo aboard is delivered home before
        any planning. Returns the delivery's delay, None to go on.
        """
        host = self.host
        upgrade_cycle = getattr(host, "handle_upgrade_cycle_if_idle", None)
        if upgrade_cycle is not None:
            upgrade_cycle()
        if host.vehicle.cargo.count() > 0:
            host.log.debug(f"[{host.name}] pull: cargo aboard; delivering home first.")
            return self._finish_pull_delivery()
        return None

    def pick(self):
        """
        Plans the best trip for home's deficits and claims its pickups.
        None (self.wait says why) when nothing is wanted, the plan is below
        the minimum load, or the claim left less than that.
        """
        host = self.host
        home_id = self.home_id
        curr_tick = host.get_current_tick()
        # Before any demand/stock read (see claim_pickups()); drops this
        # vehicle's leftovers from an abandoned plan, nothing is aboard.
        seen = logistics_requests.planning_snapshot(host.name)
        deficits = pull_plan.pull_deficits_tiered(host.home_outpost, curr_tick)
        if not any(deficits.values()):
            self.wait = NO_DEMAND
            return None
        capacity = host.vehicle.cargo.capacity()
        host.log.debug(f"[{host.name}] pull: deficits at '{home_id}': {deficits}")
        route, reachable = pull_plan.plan_pull_route(host, deficits, capacity, curr_tick, self.unviable, self.warned_drills)
        planned = sum(a for _src, loads in route for _i, a in loads)
        # Minimum trip only over what some source can actually give:
        # deficits nobody holds (or that were left to drones) must not
        # keep a small but real delivery waiting. A route
        # carrying BLOCKER units goes alone; nothing more arrives by waiting.
        blockers = logistics_requests.blocker_units(logistics_requests.route_tier_units(deficits, route))
        wanted = logistics_requests.min_load_units(blockers, reachable)
        if not route or planned <= 0 or planned < wanted:
            host.log.debug(f"[{host.name}] pull: planned {planned} unit(s) < minimum {wanted}; waiting.")
            self.wait = SHORT
            return None

        # Atomic claim: trimmed by whatever another hauler reserved
        # since `seen` (e.g. two haulers planning on the same tick).
        granted = logistics_requests.claim_pickups(host.name, home_id, [(src["id"], i, a) for src, loads in route for i, a in loads], seen, curr_tick)
        grant_by_leg = {(s, i): g for s, i, g in granted}
        route = [(src, [(i, grant_by_leg.get((src["id"], i), 0)) for i, _a in loads if grant_by_leg.get((src["id"], i), 0) > 0]) for src, loads in route]
        route = [(src, loads) for src, loads in route if loads]
        claimed = sum(a for _src, loads in route for _i, a in loads)
        if claimed < planned:
            host.log.debug(f"[{host.name}] pull: another hauler reserved part of this trip since planning; {planned} -> {claimed} unit(s).")
        if not route or claimed < wanted:
            host.log.debug(f"[{host.name}] pull: {claimed} unit(s) left after claim < minimum {wanted}; replanning next cycle.")
            logistics_requests.release_pickups(host.name)
            self.wait = TRIMMED
            return None
        first = route[0][0]
        return Mission(kind="pull", target_key=first["id"], target={"route": route, "coords": first["coords"]}, source="request", tick=curr_tick)

    def execute(self, mission):
        """Drives the claimed stops (a stop out of reach drops it and every later one), then delivers home or releases the pickups."""
        host = self.host
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
        """No trip: parks at base as "no demand", waits for stock (SHORT) or replans after a trimmed claim (TRIMMED)."""
        host = self.host
        if self.wait == NO_DEMAND:
            if not host.is_at_base():
                host.return_to_base()
            host.publish_telemetry("IDLE_AT_OUTPOST", "no demand")
        elif self.wait == SHORT:
            host.publish_telemetry("IDLE_AT_OUTPOST", "wanted items not available anywhere yet")
        return self.idle_delay

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
        """Drives home, unloads, releases this vehicle's pickup debits and recharges; returns the delay (0 delivered, poll_interval to retry)."""
        host = self.host
        host.log.start(f"[{host.name}] Delivering pickups to '{host.home_base}'")
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
        host.publish_telemetry("RETURNING", f"returning to '{host.home_base}' with pickups")
        if not host.return_to_base():
            host.log.level("warn").print(f"[{host.name}] Could not reach home to unload; will retry.")
            return "Delivery incomplete: home not reached", self.poll_interval
        if host.unload_cargo() < 0:
            host.publish_telemetry("WAITING_INVENTORY_SPACE")
            return "Delivery blocked: no inventory space", self.poll_interval
        logistics_requests.release_pickups(host.name)
        host.recharge_at_station(target_level=1.0)
        host.publish_telemetry("READY_AT_OUTPOST")
        return "Delivered and recharged", 0
