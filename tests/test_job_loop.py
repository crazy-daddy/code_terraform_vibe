"""FleetUnitMixin.run_job_loop() plumbing (hold, recall, error recovery, job swap, sleep) and Job.step()'s default prepare/pick/execute order (lib/job_base.py)."""

import builtins
import unittest
from unittest import mock

import fleet_unit
import harness
from job_base import Job
from mission import Mission
from parking_client import PARK_REQUESTS_KEY
from tree_console import TreeConsole


class StopLoop(Exception):
    pass


class _Host:
    """The controller surface run_job_loop() and Job's defaults read."""

    name = "pioneer_4"

    def __init__(self, recalled=False, at_base=True, level=1.0, charger=True):
        self.log = TreeConsole()
        self.brakes = 0
        self.recalled = recalled
        self.at_base = at_base
        self.level = level
        self.home_charging_station = {"id": "cs_1"} if charger else None
        self.calls = []
        self.swap_to: Job | None = None

    @property
    def _host(self):
        return self

    def handle_recall_if_active(self):
        return self.recalled

    def stop_moving(self):
        self.brakes += 1

    def park_update(self, job):
        self.calls.append("park_update")

    def next_job(self, job):
        return self.swap_to or job

    def is_at_base(self):
        return self.at_base

    def get_battery(self):
        return self.level * 100.0, 100.0, self.level

    def recharge_at_station(self, target_level=1.0, station_coords=None):
        self.calls.append("recharge")

    def handle_upgrade_cycle_if_idle(self):
        self.calls.append("upgrade")

    def distance_to_home(self):
        return 0.0 if self.at_base else 50.0

    def return_to_base(self):
        self.calls.append("return")

    def publish_telemetry(self, state, *args):
        self.calls.append(state)

    def end_mission(self):
        self.calls.append("end_mission")


class _ScriptedJob(Job):
    """step() pops results from a script: an Exception instance is raised, anything else returned."""

    name = "scripted"

    def __init__(self, host, script, holds=()):
        super().__init__(host)
        self.script = list(script)
        self.holds = list(holds)  # hold() results, in order; None once exhausted
        self.steps = 0
        self.errors = 0
        self.left = 0
        self.announced = 0

    def announce(self):
        self.announced += 1

    def hold(self):
        return self.holds.pop(0) if self.holds else None

    def step(self):
        self.steps += 1
        result = self.script.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def on_error(self):
        self.errors += 1

    def on_leave(self):
        self.left += 1


class RunJobLoopTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.sleeps = []
        self.stop_after = 2
        patch = mock.patch.object(fleet_unit, "validate_game_version", lambda: None)
        patch.start()
        self.addCleanup(patch.stop)
        original_sleep = builtins.sleep  # type: ignore[attr-defined]
        builtins.sleep = self._sleep  # type: ignore[attr-defined]
        self.addCleanup(setattr, builtins, "sleep", original_sleep)

    def _sleep(self, seconds):
        self.sleeps.append(seconds)
        if len(self.sleeps) >= self.stop_after:
            raise StopLoop()

    def _run(self, host, job):
        with self.assertRaises(StopLoop):
            fleet_unit.FleetUnitMixin.run_job_loop(host, job)  # type: ignore[arg-type]

    def test_error_stops_releases_and_continues(self):
        host = _Host()
        job = _ScriptedJob(host, [RuntimeError("boom"), 7.0])
        self._run(host, job)
        self.assertEqual(self.sleeps, [5.0, 7.0])
        self.assertEqual((job.steps, job.errors, job.announced), (2, 1, 1))
        self.assertEqual(host.brakes, 1)

    def test_hold_skips_recall_and_step(self):
        host = _Host(recalled=True)
        job = _ScriptedJob(host, [2.0], holds=[9.0])
        job.recall_delay = 6.0
        self._run(host, job)
        self.assertEqual(self.sleeps, [9.0, 6.0])
        self.assertEqual(job.steps, 0)

    def test_zero_delay_runs_next_step_without_sleep(self):
        host = _Host()
        job = _ScriptedJob(host, [0, None, 3.0, 4.0])
        self._run(host, job)
        self.assertEqual(self.sleeps, [3.0, 4.0])
        self.assertEqual(job.steps, 4)

    def test_recall_skips_step(self):
        host = _Host(recalled=True)
        job = _ScriptedJob(host, [])
        job.recall_delay = 6.0
        self._run(host, job)
        self.assertEqual(self.sleeps, [6.0, 6.0])
        self.assertEqual(job.steps, 0)

    def test_next_job_swap_leaves_old_announces_new(self):
        host = _Host()
        first = _ScriptedJob(host, [1.0])
        second = _ScriptedJob(host, [2.0])
        host.swap_to = second
        self._run(host, first)
        self.assertEqual(self.sleeps, [1.0, 2.0])
        self.assertEqual((first.left, second.announced, second.steps), (1, 1, 1))


class _PickJob(Job):
    def __init__(self, host, mission):
        super().__init__(host)
        self.mission = mission
        self.executed = []

    def pick(self):
        return self.mission

    def execute(self, mission):
        self.executed.append(mission)
        return 3.0


class JobDefaultStepTests(harness.StubTestCase):
    def test_no_work_idles_at_base(self):
        host = _Host(at_base=False)
        self.assertEqual(_PickJob(host, None).step(), Job.idle_delay)
        self.assertEqual(host.calls, ["return", "IDLE_AT_BASE"])

    def test_prepare_tops_off_and_upgrades_then_executes(self):
        host = _Host(level=0.5)
        mission = Mission(kind="poi", target_key="poi_1", target={"coords": (1, 2)})
        job = _PickJob(host, mission)
        self.assertEqual(job.step(), 3.0)
        self.assertEqual(host.calls, ["recharge", "upgrade"])
        self.assertEqual(job.executed, [mission])

    def test_no_top_off_without_charger_or_above_threshold(self):
        host = _Host(level=0.5, charger=False)
        _PickJob(host, None).prepare()
        self.assertEqual(host.calls, ["upgrade"])
        host = _Host(level=0.96)
        _PickJob(host, None).prepare()
        self.assertEqual(host.calls, ["upgrade"])

    def test_default_on_error_ends_mission(self):
        host = _Host()
        _PickJob(host, None).on_error()
        self.assertEqual(host.calls, ["end_mission"])


if __name__ == "__main__":
    unittest.main()


class _ParkUnit(fleet_unit.FleetUnitMixin):
    PARK_KIND = "pioneer"
    name = "pioneer_4"
    role = "hauler"

    def __init__(self, state, spot_ok=True):
        self.state = state
        self.spot_ok = spot_ok

    def park_spot_ok(self):
        return self.spot_ok


class ParkRequestTests(harness.StubTestCase):
    def requests(self):
        return self.world.notebook.data.get(PARK_REQUESTS_KEY, {})

    def cycle(self, unit, job, times=3):
        for _ in range(times):
            unit.park_update(job)

    def test_idle_unit_at_a_safe_spot_files_a_request_with_its_role(self):
        unit = _ParkUnit("IDLE_AT_BASE")
        self.cycle(unit, Job(unit))
        self.assertEqual(self.requests()["pioneer_4"]["role"], "hauler")
        unit.state = "READY_AT_BASE"
        unit.park_update(Job(unit))
        self.assertNotIn("pioneer_4", self.requests())

    def test_no_request_away_from_a_safe_spot_or_when_the_job_objects(self):
        self.cycle(_ParkUnit("IDLE_AT_BASE", spot_ok=False), Job(_ParkUnit("IDLE_AT_BASE")))
        unit = _ParkUnit("IDLE_AT_OUTPOST")
        job = Job(unit)
        job.parkable = lambda: False  # e.g. PullJob waiting for stock
        self.cycle(unit, job)
        self.cycle(_ParkUnit("RECALLED"), Job(unit))
        self.assertEqual(self.requests(), {})
