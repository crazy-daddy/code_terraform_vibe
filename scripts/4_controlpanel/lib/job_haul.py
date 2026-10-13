# HaulJob: the floating drone hauler's role (lib/drone_job.py contract).
# Each step: cargo aboard is delivered first (resume after a reload or a
# failed delivery), then the launch and recharge floors, then an urgent
# Storm Glass aftermath (lib/drone_weather.py), else the best haul
# (drone_haul_plan.plan_haul_job()): claim its pickups, stage the outpost
# legs, fly them (drone_hauler.load_at_drill()/load_at_depot()), deliver
# (deliver()). Nothing to do: hover (hover_idle()), or charge at a
# drone_service once idle HAUL_IDLE_CHARGE_TICKS in a row. The delivery in progress
# is the Mission of kind "haul" (target {"dest": outpost_id}, no claim key),
# so a reload resumes it. run_job_loop(HaulJob(drone)) runs it (lib/drone.py).

import depot_stage
import drone_haul_plan
import fleet_intent
import logistics_requests
from drone_hauler import HAUL_RECHARGE_SOC
from drone_job import DroneJob
from mission import Mission

HAUL_KIND = "haul"


def haul_mission(dest_id):
    """The Mission for a delivery to dest_id's Depot: kind "haul", no claim key."""
    return Mission(kind=HAUL_KIND, target_key="", target={"dest": dest_id, "name": f"haul to {dest_id}"}, source="request")


class HaulJob(DroneJob):
    """
    Floating hauler role. prepare(): upgrade request, cargo aboard delivered,
    launch and recharge floors. pick(): an urgent Storm Glass site, else a
    planned haul (not yet begun: execute() claims the route first), else a
    non-urgent glass site, else hover idle. execute(): refuel for the haul's
    budget and replan, or claim, load and deliver; or collect the glass.
    """

    name = "haul"
    idle_delay = 5.0  # poll between plans: demand changes with every delivery

    def __init__(self, host):
        super().__init__(host)
        self.plan = None  # the drone_haul_plan.plan_haul_job() dict behind the mission pick() returned
        self.plan_tick = 0
        self.leg_depots = {}  # {source outpost id: depot dict} staged for the current route
        self.idle_since: int | None = None  # tick the current no-job streak began

    def announce(self):
        host = self.host
        host.log.print(f"[{host.name}] Floating hauler online ({host.engine}, cargo capacity {host.cargo_capacity()}).")

    def prepare(self):
        delay = super().prepare()
        if delay is not None:
            return delay
        delay = self.prepare_cargo()
        if delay is not None:
            return delay
        host = self.host
        # Launch hysteresis only where it's free: already parked at a
        # service, let the station finish topping up first.
        _, _, frac = host.get_battery()
        if host.docked_at_service() and frac < host.LAUNCH_MIN_SOC:
            host.log.debug(f"[{host.name}] At service with {frac * 100:.0f}% < {host.LAUNCH_MIN_SOC * 100:.0f}% launch floor; waiting for top-up.")
            host.publish_telemetry("REFUELING", "launch floor")
            return self.poll_interval
        if frac < HAUL_RECHARGE_SOC:
            host.publish_telemetry("REFUELING", "recharge floor")
            if host.go_to_nearest_service(f"Charge {frac * 100:.0f}% < {HAUL_RECHARGE_SOC * 100:.0f}% recharge floor"):
                return self.poll_interval
        return None

    def prepare_cargo(self):
        """Cargo aboard goes to the haul mission's outpost, else the best taker (pick_delivery_outpost()); refuels for the leg first."""
        host = self.host
        contents = host.cargo_contents()
        if not contents:
            return None
        self.idle_since = None
        mission = host.mission
        saved = mission.target.get("dest") if mission is not None and mission.kind == HAUL_KIND else None
        dest_id = host.pick_delivery_outpost(contents, saved)
        if not dest_id:
            host.log.level("warn").print(f"[{host.name}] Cargo {contents} aboard but no Drone Depot to deliver to (all on stall cooldown or none deployed).")
            host.hover_wait("STUCK_WITH_CARGO")
            return self.poll_interval
        # Re-assert the debits from what's physically aboard (a restart may
        # have lost them; per-drill ones from the trip would double-count).
        curr_tick = host.get_current_tick()
        host.release_haul_reservations()
        for item_id, units in contents.items():
            logistics_requests.reserve_pickup(host.name, dest_id, item_id, units, curr_tick, aboard=True)
        if saved != dest_id:
            host.begin_mission(haul_mission(dest_id), claimed=True)
        host.set_intent(fleet_intent.describe("hauling", contents, dest=dest_id, root=fleet_intent.haul_root(contents, dest_id, curr_tick)))
        services = host.get_all_drone_services()
        dest_coords = next((d["coords"] for d in host.get_all_drone_depots() if d.get("outpost_id") == dest_id), host.position())
        needed = drone_haul_plan.route_fuel(host, [host.position(), dest_coords], services)
        level, _, _ = host.get_battery()
        if level < needed and not host.refuel(needed, f"Low fuel for delivery ({level:.1f} < {needed:.1f} {host.energy_unit()})"):
            return self.poll_interval
        if not host.deliver(dest_id):
            if drone_haul_plan.is_cooling(host, "dest", dest_id, host.get_current_tick()):
                # Requeue at the back: forget the destination so the next
                # cycle picks the next-best one for this cargo.
                host.end_mission()
            return self.poll_interval
        return 0

    def pick(self):
        host = self.host
        # Storm Glass aftermaths (lib/drone_weather.py): one about to expire
        # beats a haul job; any other only fills idle time.
        glass = host.pick_aftermath_pickup(urgent_only=True)
        if glass is not None:
            return glass
        self.plan_tick = host.get_current_tick()
        self.plan = drone_haul_plan.plan_haul_job(host, self.plan_tick)
        if self.plan is None:
            glass = host.pick_aftermath_pickup(urgent_only=False)
            if glass is not None:
                return glass
            return self.defer(self.idle_delay)
        self.idle_since = None
        return haul_mission(self.plan["dest"]["outpost_id"])

    def idle(self):
        now = self.host.get_current_tick()
        if self.idle_since is None:
            self.idle_since = now
        self.host.hover_idle("No haul job", now - self.idle_since)
        return self.idle_delay

    def execute(self, mission):
        host = self.host
        if mission.kind != HAUL_KIND:
            host.collect_aftermath(mission)
            return 0
        plan = self.plan
        if plan is None:
            return 0
        level, _, _ = host.get_battery()
        if level < plan["fuel"]:
            host.refuel(plan["fuel"], f"Job needs {plan['fuel']:.1f} {host.energy_unit()}, have {level:.1f}")
            return 0  # re-plan from the service: demand may have moved meanwhile
        self._run_plan(plan, self.plan_tick)
        return self.poll_interval

    def on_error(self):
        """Releases nothing: pickups stay reserved while cargo may be aboard, and prepare_cargo() re-asserts them from what is."""
        return

    # ------------------------------------------------------------ a planned haul

    def _claim_route(self, plan, curr_tick):
        """
        Reserves the planned route atomically (logistics_requests.claim_pickups()),
        trimmed by whatever other haulers reserved since planning. Returns the
        route with granted amounts, or None when too little is left to be
        worth the trip (then nothing stays reserved; _run_plan() tries the alternates).
        """
        host = self.host
        host.log.start(f"[{host.name}] _claim_route", level="debug")
        dest = plan["dest"]
        dest_id = dest["outpost_id"]
        legs = [(source["id"], item_id, amount) for source, loads in plan["route"] for item_id, amount in loads]
        granted = logistics_requests.claim_pickups(host.name, dest_id, legs, plan.get("seen", {}), curr_tick)
        grant_by_leg = {(s, i): g for s, i, g in granted}
        route = []
        for source, loads in plan["route"]:
            kept = [(i, grant_by_leg.get((source["id"], i), 0)) for i, _n in loads]
            kept = [(i, n) for i, n in kept if n > 0]
            if kept:
                route.append((source, kept))
        units = sum(n for _s, loads in route for _i, n in loads)
        wanted = plan.get("wanted", logistics_requests.min_load_units(0, sum(dest["deficits"].values())))
        if units < plan["units"]:
            host.log.debug(f"haul: another hauler reserved part of this job since planning; {plan['units']} -> {units} unit(s).")
        if not route or units < wanted:
            host.log.debug(f"haul: {units} unit(s) left after claim < minimum {wanted}; dropping this job.")
            logistics_requests.release_pickups(host.name)
            host.log.end()
            return None
        # Outpost pickups: have the source Depot stage the goods while the
        # drone flies there.
        self.leg_depots = {}
        tick = host.get_current_tick()
        for source, loads in route:
            if source.get("kind") != "outpost":
                continue
            depot = host.stage_depot_for(source)
            self.leg_depots[source["id"]] = depot
            for item_id, amount in loads:
                depot_stage.request_stage(depot["id"], host.name, item_id, amount, tick)
            host.log.debug(f"haul: staging {loads} at Depot '{depot['id']}' ({source['id']}).")
        host.log.end()
        return route

    def _claim_alternate(self, plan, curr_tick):
        """
        After the planned job lost its load to another hauler: claims the
        best of plan["alternates"] (drone_haul_plan.HAUL_CLAIM_ALTERNATES
        next-ranked candidates) that the fuel aboard covers, one claim each
        instead of a whole replan. Returns (alternate, route), or (None, None).
        """
        host = self.host
        level, _, _ = host.get_battery()
        for alternate in plan.get("alternates") or []:
            if alternate["fuel"] > level:
                continue
            route = self._claim_route(alternate, curr_tick)
            if route:
                host.log.debug(f"haul: claimed alternate -> '{alternate['dest']['outpost_id']}' ({alternate['units']} unit(s) planned).")
                return alternate, route
        return None, None

    def _run_plan(self, plan, curr_tick):
        """Claims the route, begins the haul mission, flies the pickups and delivers."""
        host = self.host
        route = self._claim_route(plan, curr_tick)
        if not route:
            plan, route = self._claim_alternate(plan, curr_tick)
            if plan is None or not route:
                host.log.debug("haul: no alternate left to claim; replanning next cycle.")
                return
            self.plan = plan
        dest = plan["dest"]
        dest_id = dest["outpost_id"]
        planned = {}
        legs = []
        for source, loads in route:
            legs.append(source["id"] + " (" + ", ".join(f"{n}x {i}" for i, n in loads) + ")")
            for item_id, amount in loads:
                planned[item_id] = planned.get(item_id, 0) + amount
        host.begin_mission(haul_mission(dest_id), claimed=True)
        source_ids = [source["id"] for source, _loads in route]
        source_label = source_ids[0] + (f" +{len(source_ids) - 1}" if len(source_ids) > 1 else "")
        host.set_intent(fleet_intent.describe("hauling", planned, source_label, dest_id, fleet_intent.haul_root(planned, dest_id, curr_tick)))
        host.log.start(f"[{host.name}] Haul job -> '{dest_id}': " + " -> ".join(legs))

        loaded = {i: 0 for i in planned}
        for index, (source, loads) in enumerate(route):
            if source.get("kind") == "outpost":
                moved = host.load_at_depot(source, loads, dest_id, curr_tick, depot=self.leg_depots.get(source["id"]))
            else:
                moved = host.load_at_drill(source, loads, dest_id, curr_tick)
            if moved is None:
                for later, later_loads in route[index:]:
                    for item_id, _n in later_loads:
                        logistics_requests.reserve_pickup(host.name, dest_id, item_id, 0, curr_tick, source_id=later["id"])
                break
            for item_id, n in moved.items():
                loaded[item_id] = loaded.get(item_id, 0) + n
        total = sum(loaded.values())
        host.log.end(f"[{host.name}] Pickups done: {total} unit(s) aboard.")

        if total <= 0:
            host.release_haul_reservations()
            host.end_mission()
            host.set_intent(None)
            return
        host.deliver(dest_id)
