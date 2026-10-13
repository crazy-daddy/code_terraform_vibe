# BiositeJob: the Bio Extractor drone's role (lib/drone_job.py contract).
# Each step: resume a claimed site after a reload, else charge, deliver
# cargo aboard to the home Depot (with the full-Depot backoff and the
# deliver-elsewhere stall fallback), else claim the best ready home-biome
# biosite (drone_mining.biosite_candidates()/select_biosite_target()), fly
# there, extract until the site cools or cargo fills, return and unload
# (drone_cargo.return_and_unload()). run_job_loop(BiositeJob(drone)) runs it
# (lib/drone.py).

import fleet_intent
import logistics_requests
from drone_job import DroneJob
from mission import Mission
from swallow import swallowed

# After this many full-Depot unload failures in a row, cargo another Depot
# outpost requests is delivered there instead (_deliver_elsewhere()).
DEPOT_FULL_STALL_ATTEMPTS = 3


class BiositeJob(DroneJob):
    """
    Miner role. prepare(): upgrade request, stale-claim cleanup, the one-time
    adoption of an extraction running across the restart, then (without a
    mission to resume) the proactive charge and cargo aboard. pick(): the
    resumed mission, else a claimed biosite as a Mission of kind "mine".
    execute(): fly, extract, return and unload.
    """

    name = "biosite"
    log_module = "drone_mining"
    idle_delay = 30.0
    unreachable_delay = 15.0  # candidates, but none reachable and claimable

    def __init__(self, host):
        super().__init__(host)
        self.started = False  # adopt_interrupted_extraction() ran
        self.fresh = False  # the mission pick() returned was claimed this cycle, not resumed

    def announce(self):
        host = self.host
        self.log.print(f"Drone Miner Controller ({host.name}) online. Home biome: {host.home_biome or 'unknown'}.")

    def prepare(self):
        delay = super().prepare()
        if delay is not None:
            return delay
        host = self.host
        host.cleanup_stale_biosite_claims()
        if not self.started:
            self.started = True
            host.adopt_interrupted_extraction(self.log)
        if host.mission is not None:
            # Resume comes first (pick() returns the mission): the drone is
            # mid-trip, maybe mid-extraction, so no detour to charge or unload.
            return None
        if self.charge_if_low():
            return self.poll_interval
        return self.prepare_cargo()

    def prepare_cargo(self):
        """Cargo aboard goes to the home Depot: wait out a full-Depot backoff, deliver elsewhere after DEPOT_FULL_STALL_ATTEMPTS, else return_and_unload()."""
        host = self.host
        if host.cargo_count() <= 0:
            return None
        backoff = host.depot_full
        now = host.get_current_tick()
        if now < backoff.retry_tick:
            host.wait_for_depot_space(backoff.depot_id, backoff.retry_tick - now)
            return self.poll_interval
        if backoff.count >= DEPOT_FULL_STALL_ATTEMPTS and self._deliver_elsewhere():
            return 0
        # Without the sleep a failed return (e.g. go_to "busy") retried in a
        # tight loop and flooded the console.
        if not host.return_and_unload():
            return self.poll_interval
        return 0

    def pick(self):
        host = self.host
        if host.mission is not None:
            self.fresh = False
            return host.mission
        candidates = host.biosite_candidates()
        if not candidates:
            self.log.debug(f"[{host.name}] No ready home-biome biosite candidates this cycle.")
            return self.defer(self.idle_delay, "IDLE_NO_TARGETS")
        if host.hold_for_launch_charge(self.log):
            return self.defer(self.poll_interval)
        target, budget = host.select_biosite_target(candidates)
        if not target or not budget:
            self.log.debug(f"[{host.name}] {len(candidates)} candidate(s) found but none both reachable and claimable.")
            self.top_up_if_unreachable("IDLE_OUT_OF_RANGE", "No candidate reachable")
            return self.defer(self.unreachable_delay)
        # select_biosite_target() already won the claim.
        mission = Mission(kind="mine", target_key=target["target_key"], target={"coords": target["coords"], "name": target["target_key"], "sample_type": target["sample_type"]}, budget=budget)
        host.begin_mission(mission, claimed=True)
        self.fresh = True
        return mission

    def execute(self, mission):
        """Flies to the claimed biosite (re-validating the position of a resumed one), extracts, returns and unloads."""
        host = self.host
        coords = tuple(mission.target.get("coords", (0, 0)))
        key = mission.target_key
        if self.fresh:
            sample = mission.target.get("sample_type")
            cost = (mission.budget or {}).get("total_required_wh", 0.0)
            self.log.start(f"[{host.name}] Reserved biosite {key} ({sample}) at {coords} (Est. trip cost: {cost:.1f} {host.energy_unit()}).")
            host.set_intent(fleet_intent.describe("sampling", [sample], at=key, root=fleet_intent.haul_root([sample])))
            host.publish_telemetry("OUTBOUND", key)
            if not host.fly_to(coords[0], coords[1], precision=1.0):
                self.log.level("warn").print(f"[{host.name}] Could not reach biosite {coords}; releasing claim and retrying later.")
                host.release_biosite_claim(key)
                self.log.end("unreachable, claim released")
                return self.poll_interval
        else:
            # A drone's go_to() is CANCELLED by a script restart (drone.md),
            # unlike a rover's persistent drive command, so re-validate the
            # physical position and re-issue the flight leg -- extract()
            # itself resumes transparently once physically there again (its
            # own docs: "stays occupied... including across a script stop
            # and restart").
            self.log.debug(f"[{host.name}] Resuming claimed target '{key}' after reload; re-validating position.")
            if not host.is_at(coords, precision=1.0) and not host.fly_to(coords[0], coords[1], precision=1.0):
                self.log.level("warn").print(f"[{host.name}] Could not re-reach resumed target {coords}; will retry.")
                return self.poll_interval
            self.log.start(f"[{host.name}] Resumed biosite {key} at {coords}")
        host.extract_until_done(coords)
        # The site is done: end the mission now, not at the Depot. A kept
        # mission made a deferred unload (bay taken, Depot out of range)
        # resume as a flight back to the site, skipping charge_if_low()
        # and prepare_cargo(), until the battery ran out. Cargo aboard is
        # unloaded below or by prepare_cargo() next cycle.
        host.release_biosite_claim(key)
        if not host.return_and_unload():
            self.log.end("extracted, unload deferred")
            return self.poll_interval
        self.log.end("extracted and unloaded")
        return 0

    # ------------------------------------------------------------ stall fallback

    def _deliver_elsewhere(self):
        """
        Stalled at a full home Depot: delivers cargo that another Depot
        outpost requests (logistics_requests.outpost_deficits_tiered(): NEED band and above, then
        lower bands) there, once, if the trip is affordable
        (calculate_trip_energy()). Picks the outpost taking the most
        NEED-or-higher units, then the most units. True when anything was
        unloaded (the stall counter resets); False leaves the drone waiting at home.
        """
        host = self.host
        try:
            contents = {i: int(n) for i, n in dict(host.drone.cargo.contents()).items() if n > 0}
        except Exception as error:
            swallowed("job_biosite.BiositeJob._deliver_elsewhere: host.drone.cargo.contents", error)
            return False
        home_ids = {d["id"] for d in host._home_depot_candidates()}
        by_outpost = {}
        for depot in host.get_all_drone_depots():
            if depot["id"] not in home_ids and depot.get("outpost_id"):
                by_outpost.setdefault(depot["outpost_id"], []).append(depot)
        network = get_component("outpost_network")
        try:
            outposts = {o.id: o for o in network.outposts()} if network else {}
        except Exception as error:
            swallowed("job_biosite.BiositeJob._deliver_elsewhere: network.outposts", error)
            outposts = {}
        best, best_units, best_rank = None, 0, (0, 0)
        for outpost_id, depots in by_outpost.items():
            need, buffer = logistics_requests.outpost_deficits_tiered(outposts.get(outpost_id), live=False) if outpost_id in outposts else ({}, {})
            need_units = sum(min(n, need.get(i, 0)) for i, n in contents.items())
            units = sum(min(n, need.get(i, 0) + buffer.get(i, 0)) for i, n in contents.items())
            if units <= 0:
                continue
            budget = host.calculate_trip_energy(depots[0]["coords"])
            if not budget["is_achievable"]:
                self.log.debug(f"[{host.name}] Stalled cargo: '{outpost_id}' wants {units} unit(s) but is out of range.")
                continue
            if (need_units, units) > best_rank:
                best, best_units, best_rank = (outpost_id, depots), units, (need_units, units)
        if best is None:
            self.log.debug(f"[{host.name}] Stalled cargo {contents}: no other Depot outpost requests it in range; waiting at home.")
            return False
        outpost_id, depots = best
        depot = host._pick_free_depot(depots)
        self.log.start(f"[{host.name}] Home Depot full {host.depot_full.count}x; delivering {contents} to '{depot['id']}' ({outpost_id}), which requests {best_units} unit(s).")
        delivered = self._deliver_to_depot(depot)
        self.log.end("delivered" if delivered else "not delivered")
        return delivered

    def _deliver_to_depot(self, depot):
        """Docks at the other outpost's Depot and unloads the stalled cargo; True when anything was unloaded."""
        host = self.host
        host.publish_telemetry("DELIVERING", depot["id"])
        if not host.fly_to_station(depot["id"], target_coords=depot["coords"]):
            self.log.level("warn").print(f"[{host.name}] Could not dock at '{depot['id']}' for the stalled cargo; back to waiting at home.")
            return False
        unloaded = host.unload_cargo_at_depot()
        host.leave_station()
        if unloaded <= 0:
            self.log.debug(f"[{host.name}] '{depot['id']}' took nothing ({unloaded}); back to waiting at home.")
            return False
        self.log.print(f"[{host.name}] Unloaded {unloaded} stalled unit(s) at '{depot['id']}'.")
        host.depot_full.clear()
        return True
