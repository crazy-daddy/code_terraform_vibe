# AftermathJob: the plated drone's storm-aftermath role (lib/drone_job.py
# contract). Each step: resume a claimed site after a reload, else unload
# cargo aboard at the home Depot (drone_cargo.return_and_unload()), charge,
# then claim the next site (uranium pass first, Storm Glass second;
# lib/drone_weather.py), fly there, wait for ready_gh, collect, come home
# and unload. run_job_loop(AftermathJob(drone)) runs it (lib/drone.py). The
# hauler's between-jobs Storm Glass pickup is HaulJob's (lib/job_haul.py)
# through the same weather abilities.

from drone_job import DroneJob
from drone_weather import IDLE_POLL_S, aftermath_target


class AftermathJob(DroneJob):
    """
    Aftermath collector role. prepare(): upgrade request, stale-claim
    cleanup, cask reservation sync, then (without a mission to resume)
    cargo aboard unloaded at home and the proactive charge. pick(): the
    resumed mission, else the first claimable site over the kind passes
    (begun as a Mission of kind "aftermath"). execute(): fly, wait, collect,
    release, home and unload.
    """

    name = "aftermath"
    log_module = "drone_weather"
    idle_delay = IDLE_POLL_S
    unreachable_delay = 15.0  # sites known, none reachable and claimable

    def announce(self):
        host = self.host
        self.log.print(f"Aftermath collector ({host.name}) online; plated={host.plated}, home {getattr(host.home_outpost, 'id', None)}.")
        if not host.plated:
            self.log.level("warn").print(f"[{host.name}] No Shield Plating: collecting Storm Glass only.")

    def prepare(self):
        delay = super().prepare()
        if delay is not None:
            return delay
        host = self.host
        host.cleanup_stale_biosite_claims()
        if host.resumed_aftermath() is not None:
            # Mid-trip: pick() returns the site; cargo from it comes home after.
            return None
        host._sync_cask_reservation()
        if host.cargo_count() > 0:
            if not host.return_and_unload():
                return self.poll_interval
            host._sync_cask_reservation()
            return 0
        if self.charge_if_low():
            return self.poll_interval
        return None

    def pick(self):
        host = self.host
        if host.resumed_aftermath() is not None:
            return host.mission
        seen = 0
        target, budget = None, None
        for kinds in host.aftermath_passes():
            candidates = host._aftermath_candidates(kinds)
            if not candidates:
                continue
            if seen == 0 and host.hold_for_launch_charge(self.log):
                return self.defer(self.poll_interval)
            seen += len(candidates)
            target, budget = host._select_aftermath_target(candidates)
            if target is not None:
                if host.plated and target["kind"] == "storm_glass":
                    self.log.debug(f"[{host.name}] No claimable uranium site; taking Storm Glass {target['event_id']}.")
                break
        if seen == 0:
            return self.defer(self.idle_delay, "IDLE_NO_TARGETS")
        if target is None or budget is None:
            self.log.debug(f"[{host.name}] {seen} aftermath site(s), none reachable and claimable.")
            self.top_up_if_unreachable("IDLE_OUT_OF_RANGE", "No aftermath reachable")
            return self.defer(self.unreachable_delay)
        self.log.debug(f"[{host.name}] Claimed aftermath {target['event_id']}; trip needs {budget['total_required_wh']:.1f} {host.energy_unit()}.")
        return host.begin_aftermath_mission(target)

    def execute(self, mission):
        host = self.host
        target = aftermath_target(mission)
        self.log.start(f"[{host.name}] Aftermath {target['event_id']}: {target['kind']} at {target['coords']}")
        units, outcome = host._fly_and_collect(target)
        # Releasing also ends the mission; cargo aboard is unloaded below or next cycle.
        host.release_biosite_claim(target["target_key"])
        host._sync_cask_reservation()
        host._end_trip_intent(target, units)
        if units > 0 and not host.return_and_unload():
            self.log.end(f"{units} unit(s), {outcome}; unload deferred")
            return self.poll_interval
        host._sync_cask_reservation()
        host.set_intent(None)
        self.log.end(f"{units} unit(s), {outcome}")
        return 0
