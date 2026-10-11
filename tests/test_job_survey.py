"""SurveyJob (lib/job_survey.py): pick order (known contacts, spiral waypoint, idle), the spiral pass saving its waypoint, error path."""
import unittest

import harness
from archive import archive
from job_survey import ROUTE_KIND, SurveyJob
from mission import Mission
from tree_console import TreeConsole
from vehicle_survey import SURVEY_SPIRAL_KEY, VehicleSurveyMixin


class _Sonar:
    def range(self):
        return 40.0  # spiral step 30 m


class _Nav:
    def brake(self):
        pass


class _Vehicle:
    def __init__(self, nav=True):
        self.sonar = _Sonar()
        if nav:
            self.nav = _Nav()


class _Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class _Host(VehicleSurveyMixin):
    """The VehicleController surface SurveyJob reads; the real spiral waypoints and save_survey_waypoint()."""
    name = "pioneer_2"
    SONAR_WH_BUDGET = 1.0
    SAFETY_MARGIN_MULTIPLIER = 1.5

    def __init__(self, pois=(), nav=True):
        self.log = TreeConsole()
        self.vehicle = _Vehicle(nav)
        self.assigned_slot_coords = (0.0, 0.0)
        self.mission: Mission | None = None
        self.pois = list(pois)
        self.calls = []

    def unscanned_pois(self):
        return self.pois

    def unsurveyed_known_sites(self):
        return []

    def deep_oil_targets(self):
        return []

    def is_recalled(self):
        return False

    def is_at_base(self):
        return True

    def calculate_trip_energy(self, coords, planned_scans=0):
        return {"is_achievable": True, "total_required_wh": 1.0}

    def set_intent(self, text):
        pass

    def publish_telemetry(self, state, *args):
        self.calls.append(state)

    def drive_to(self, x, y):
        self.calls.append(("drive", x, y))
        return True

    def get_battery(self):
        return 900.0, 1000.0, 0.9

    def energy_needed_to_return_comfortably(self):
        return 10.0

    def scan_and_survey(self, mission=None):
        self.calls.append(("scan", mission.target_key if mission else None))
        return []

    def return_to_base(self):
        self.calls.append("return")

    def recharge_at_station(self, target_level=1.0):
        self.calls.append("recharge")

    def end_mission(self):
        self.calls.append("end_mission")


class SurveyJobPickTests(harness.StubTestCase):
    def test_known_poi_beats_spiral(self):
        job = SurveyJob(_Host(pois=[_Point(5, 5)]), spiral_fallback=True)
        self.assertEqual(job.pick().kind, ROUTE_KIND)  # type: ignore[union-attr]

    def test_resumed_poi_mission_is_a_route(self):
        host = _Host()
        host.mission = Mission(kind="poi_survey", target_key="poi_5_5", target={"coords": (5, 5)})
        self.assertEqual(SurveyJob(host, spiral_fallback=True).pick().kind, ROUTE_KIND)  # type: ignore[union-attr]

    def test_spiral_waypoint_when_no_known_contact(self):
        archive.set(SURVEY_SPIRAL_KEY, {"next_index": 1})
        mission = SurveyJob(_Host(), spiral_fallback=True).pick()
        assert mission is not None
        self.assertEqual(mission.kind, "poi")
        self.assertEqual(mission.target["index"], 1)
        self.assertEqual(mission.target["coords"], (30.0, 30.0))

    def test_idle_without_work_or_spiral(self):
        host = _Host()
        job = SurveyJob(host)
        self.assertIsNone(job.pick())
        self.assertEqual(job.step(), 30.0)
        self.assertEqual(host.calls, ["recharge", "SURVEY_COMPLETE"])  # 90% at base: top-off first


class SurveyJobExecuteTests(harness.StubTestCase):
    def test_spiral_pass_saves_waypoint(self):
        host = _Host()
        job = SurveyJob(host, max_points=1, spiral_fallback=True)
        mission = job.pick()
        assert mission is not None
        self.assertEqual(job.execute(mission), 5.0)
        self.assertIn(("drive", 30.0, 0.0), host.calls)
        self.assertIn(("scan", "poi_30.0_0.0"), host.calls)
        progress = archive.get(SURVEY_SPIRAL_KEY, {})
        self.assertEqual(progress["next_index"], 1)
        self.assertEqual(progress["waypoints"][0]["coords"], [30.0, 0.0])
        self.assertEqual(host.calls[-3:], ["return", "SURVEY_COMPLETE", "recharge"])

    def test_error_returns_home_and_keeps_mission(self):
        host = _Host()
        host.mission = Mission(kind="poi_survey", target_key="poi_5_5", target={"coords": (5, 5)})
        SurveyJob(host).on_error()
        self.assertEqual(host.calls, ["return"])
        self.assertNotIn("end_mission", host.calls)
        self.assertIsNotNone(host.mission)

    def test_route_with_work_left_returns_home(self):
        host = _Host(pois=[_Point(5, 5)])
        host.survey_known_pois = lambda max_points=20: 2  # type: ignore[method-assign]
        job = SurveyJob(host)
        self.assertEqual(job.execute(job.pick()), 5.0)  # type: ignore[arg-type]
        self.assertEqual(host.calls, ["return", "SURVEY_COMPLETE", "recharge"])

    def test_empty_route_falls_through_to_spiral_or_idle(self):
        host = _Host(pois=[_Point(5, 5)])
        route = SurveyJob(host, spiral_fallback=True).pick()
        host.pois = []  # the route scanned nothing and left no candidates
        host.survey_known_pois = lambda max_points=20: 0  # type: ignore[method-assign]
        job = SurveyJob(host, max_points=1, spiral_fallback=True)
        self.assertEqual(job.execute(route), 5.0)  # type: ignore[arg-type]
        self.assertIn(("drive", 30.0, 0.0), host.calls)
        host.calls.clear()
        self.assertEqual(SurveyJob(host).execute(route), 30.0)  # type: ignore[arg-type]
        self.assertEqual(host.calls, ["SURVEY_COMPLETE"])

    def test_can_run_needs_nav(self):
        self.assertTrue(SurveyJob(_Host()).can_run())
        self.assertFalse(SurveyJob(_Host(nav=False)).can_run())


if __name__ == "__main__":
    unittest.main()
