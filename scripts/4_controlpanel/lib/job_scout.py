# ScoutJob: the Bio Scanner drone's role (lib/drone_job.py contract). Each
# step: proactive charge, the next unscanned POI it can afford
# (drone_scout.scan_candidates()), fly there and scan (scout_poi()). No
# claims and no saved mission: repeat scans are free and the journal is the
# shared record. run_job_loop(ScoutJob(drone)) runs it (lib/drone.py).

from drone_job import DroneJob
from mission import Mission


class ScoutJob(DroneJob):
    """
    Scout role. prepare(): upgrade request, then the proactive low-battery
    return. pick(): the nearest affordable unscanned POI as a Mission of kind
    "poi" (never begun: no claim to hold); no candidates: back to the
    service and stand by. execute(): fly and scan.
    """

    name = "scout"
    log_module = "drone_scout"
    idle_delay = 30.0

    def announce(self):
        host = self.host
        self.log.print(f"Drone Scout Controller ({host.name}) online. Home outpost biome: {host.home_biome or 'unknown'}.")

    def prepare(self):
        delay = super().prepare()
        if delay is not None:
            return delay
        if self.charge_if_low():
            return self.poll_interval
        return None

    def pick(self):
        host = self.host
        candidates = host.scan_candidates()
        if not candidates:
            self.log.debug(f"[{host.name}] No unscanned POI candidates this cycle.")
            host.publish_telemetry("IDLE_NO_TARGETS")
            # Every known POI is resolved (scanned or cache/journal-confirmed
            # empty) -- nothing will ever change that without a fresh POI
            # appearing, so nothing else would ever send the drone anywhere
            # again. Without this, a scout that finishes its survey mid-field
            # just idles wherever its last scan left it, forever.
            if host.return_to_service_for_charge(self.log, "No scan targets remain"):
                self.log.print(f"[{host.name}] Survey complete; standing by at drone_service.")
            return self.defer(self.idle_delay)
        if host.hold_for_launch_charge(self.log):
            return self.defer(self.poll_interval)
        for candidate in candidates:
            budget = host.calculate_trip_energy(candidate)
            self.log.trace(f"POI {candidate}: {budget['total_required_wh']:.1f} {host.energy_unit()} required, achievable={budget['is_achievable']}.")
            if budget["is_achievable"]:
                key = f"poi_{candidate[0]}_{candidate[1]}"
                return Mission(kind="poi", target_key=key, target={"coords": candidate, "name": key}, source="poi", budget=budget)
        self.log.debug(f"[{host.name}] {len(candidates)} candidate(s) found but none reachable on current battery.")
        self.top_up_if_unreachable("IDLE_OUT_OF_RANGE", "No candidate reachable")
        return self.defer(self.idle_delay)

    def execute(self, mission):
        target = mission.target["coords"]
        self.log.start(f"[{self.host.name}] Scouting POI {target}")
        self.log.end(self.host.scout_poi(self.log, target))
        return self.poll_interval

    def on_error(self):
        """Nothing to release: the scout holds no claim."""
        return
