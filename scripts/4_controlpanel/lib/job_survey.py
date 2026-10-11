# SurveyJob: the Scout Pioneer's role (lib/job_base.py contract). Each step
# scans known contacts first (one battery-safe route, contacts in
# autoplay.survey_requests areas ahead of the rest), else, with
# spiral_fallback, runs an outward spiral pass from the archived
# survey.spiral index, else idles. run_job_loop(SurveyJob(pioneer)) runs it
# (lib/pioneer.py). Sonar abilities (scan_and_survey, survey_known_pois,
# spiral waypoints, save_survey_waypoint): lib/vehicle_survey.py.

from archive import archive
from job_base import Job
from mission import Mission
from vehicle_survey import SURVEY_SPIRAL_KEY

# Mission kind pick() returns for "scan the known contacts": one
# survey_known_pois() route, not a single claimed target.
ROUTE_KIND = "poi_route"


class SurveyJob(Job):
    """
    Scout role. pick(): a known-contact route, else the next spiral waypoint
    (spiral_fallback only), else None (idle 30 s). execute(): the route, or
    a spiral pass from the waypoint, then home and recharge.
    """

    name = "survey"
    recall_delay = 5.0
    idle_delay = 30.0
    pass_delay = 5.0  # sleep after a route or spiral pass

    def __init__(self, host, max_points=160, spiral_fallback=False):
        super().__init__(host)
        self.max_points = max_points
        self.spiral_fallback = spiral_fallback

    def can_run(self):
        """False (warned) without a Sonar or Nav Module; check before run_job_loop()."""
        host = self.host
        if not hasattr(host.vehicle, "sonar"):
            host.log.level("warn").print(f"[{host.name}] Survey loop requires a mounted Sonar Module.")
            return False
        if not hasattr(host.vehicle, "nav"):
            host.log.level("warn").print(f"[{host.name}] Survey loop requires a mounted Nav Module.")
            return False
        return True

    def announce(self):
        self.host.log.print(f"[{self.host.name}] Survey Controller online. Starting battery-safe survey.")

    def prepare(self):
        """
        Pioneer-only upgrade pass (lib/pioneer_upgrade.py; self-guarded, acts
        only idle at base), then a top-off to 100% below 95% when at base. A
        reload mid-trip must not detour home just to top off.
        """
        host = self.host
        upgrade_cycle = getattr(host, "handle_upgrade_cycle_if_idle", None)
        if upgrade_cycle is not None:
            upgrade_cycle()
        if host.is_at_base():
            _, _, level = host.get_battery()
            if level < 0.95:
                host.recharge_at_station(target_level=1.0)

    def pick(self):
        """A known-contact route (resumed POI mission or any candidate), else the next spiral waypoint, else None."""
        mission = self.host.mission
        resumed = mission is not None and bool(mission.target_key) and bool(mission.target.get("coords"))
        if resumed or self._known_candidates():
            # A marker, never begun or saved: survey_known_pois() claims and
            # saves each leg's own Mission.
            return Mission(kind=ROUTE_KIND, target_key="", target={}, source="poi")
        return self._spiral_mission()

    def execute(self, mission):
        if mission.kind == ROUTE_KIND:
            return self._known_route()
        return self._spiral_pass(mission.target["index"])

    def idle(self):
        """Nothing to scan and no spiral fallback: reports SURVEY_COMPLETE where it stands."""
        self.host.log.print(f"[{self.host.name}] All known POIs are scanned; no random spiral fallback requested.")
        self.host.publish_telemetry("SURVEY_COMPLETE", "all known POIs scanned")
        return self.idle_delay

    def on_error(self):
        """Heads home (the loop already braked). Keeps the POI mission so the next route resumes it."""
        self.host.return_to_base()

    def _known_candidates(self):
        host = self.host
        return bool(host.unscanned_pois() or host.unsurveyed_known_sites() or host.deep_oil_targets())

    def _known_route(self):
        """One survey_known_pois() route, then home and recharge; without work left after it, the spiral or idle."""
        host = self.host
        poi_completed = host.survey_known_pois(max_points=self.max_points)
        if poi_completed > 0 or self._known_candidates():
            host.return_to_base()
            host.publish_telemetry("SURVEY_COMPLETE", f"{poi_completed} known POIs")
            host.recharge_at_station(target_level=1.0)
            return self.pass_delay
        spiral = self._spiral_mission()
        if spiral is None:
            return self.idle()
        return self._spiral_pass(spiral.target["index"])

    def _spiral_mission(self):
        """The next unscanned spiral waypoint (survey.spiral next_index) as a Mission; None without spiral_fallback or a sonar."""
        if not self.spiral_fallback:
            return None
        progress = archive.get(SURVEY_SPIRAL_KEY, {}) or {}
        start_index = progress.get("next_index", 0)
        for point_index, target_x, target_y in self.host.survey_spiral_points(start_index=start_index, max_points=1):
            key = f"poi_{target_x}_{target_y}"
            return Mission(kind="poi", target_key=key, target={"coords": (target_x, target_y), "name": key, "type": "poi", "index": point_index}, source="spiral")
        return None

    def _spiral_pass(self, start_index):
        """Outward spiral waypoints from start_index until the budget, reserve or a rescue/recall stops it; then home and recharge."""
        host = self.host
        completed = 0
        host.log.start(f"[{host.name}] Spiral survey pass from index {start_index}")
        for point_index, target_x, target_y in host.survey_spiral_points(
            start_index=start_index,
            max_points=self.max_points,
        ):
            if hasattr(host.vehicle, "is_being_rescued") and host.vehicle.is_being_rescued():
                host.log.level("warn").print(f"[{host.name}] Rescue in progress; pausing survey loop.")
                break
            if host.is_recalled():
                host.log.print(f"[{host.name}] Recall requested; pausing spiral survey.")
                break

            budget = host.calculate_trip_energy(
                (target_x, target_y),
                planned_scans=4,
            )
            if not budget["is_achievable"]:
                host.log.print(f"[{host.name}] Spiral boundary reached at ({target_x:.1f}, {target_y:.1f}); returning home.")
                break

            host.set_intent(f"surveying waypoint {target_x:.0f},{target_y:.0f}")
            host.publish_telemetry("SURVEY_OUTBOUND", f"{target_x:.1f},{target_y:.1f}")
            if not host.drive_to(target_x, target_y):
                host.log.level("warn").print(f"[{host.name}] Could not safely reach spiral waypoint; returning home.")
                break

            # Comfortable reserve, not the bare floor -- keeps the return leg fast.
            scan_reserve = host.SONAR_WH_BUDGET * 4 * host.SAFETY_MARGIN_MULTIPLIER
            if host.get_battery()[0] <= host.energy_needed_to_return_comfortably() + scan_reserve:
                host.log.level("warn").print(f"[{host.name}] Insufficient energy for safe scan at ({target_x:.1f}, {target_y:.1f}); returning home.")
                break

            # scan_and_survey() blacklists an unresolved contact under the
            # mission's target_key. Spiral waypoints aren't claimed or saved
            # (not fleet-reserved), so the Mission goes straight to it; without
            # one an unresolved contact found here is dropped instead of
            # blacklisted and rediscovered every pass (it has no
            # PointOfInterest entry of its own for known-POI scans to fix).
            spiral_key = f"poi_{target_x}_{target_y}"
            spiral_mission = Mission(kind="poi", target_key=spiral_key, target={"coords": (target_x, target_y), "name": spiral_key, "type": "poi"}, source="poi")
            sites = host.scan_and_survey(spiral_mission)
            if hasattr(host.vehicle, "is_being_rescued") and host.vehicle.is_being_rescued():
                host.log.level("warn").print(f"[{host.name}] Rescue started during scan; abandoning survey pass.")
                break
            host.save_survey_waypoint(point_index, (target_x, target_y), sites)
            completed += 1

            if host.get_battery()[0] < host.energy_needed_to_return_comfortably():
                host.log.print(f"[{host.name}] Return reserve reached after survey; returning home.")
                break

        host.return_to_base()
        spiral_data = archive.get(SURVEY_SPIRAL_KEY, {}) or {}
        next_index = spiral_data.get("next_index", start_index)
        host.publish_telemetry("SURVEY_COMPLETE", f"{completed} waypoints; next {next_index}")
        host.recharge_at_station(target_level=1.0)
        host.log.end(f"[{host.name}] Survey pass complete ({completed} waypoints). Next spiral index: {next_index}")
        return self.pass_delay
