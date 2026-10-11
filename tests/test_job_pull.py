"""PullJob (lib/job_pull.py): cargo-aboard delivery, idle reasons, the unviable-first-stop record shared with VehicleCargoMixin.pull_from_source(), and pull_plan.drop_unviable_sources() pruning."""
import unittest
from unittest import mock

import harness
import pull_plan
from game_stubs import Cargo
from job_pull import NO_DEMAND, SHORT, PullJob
from mission import Mission
from tree_console import TreeConsole
from vehicle_cargo import VehicleCargoMixin


class _Vehicle:
    def __init__(self, cargo=0):
        self.cargo = Cargo(capacity=400, items={"ore": cargo} if cargo else None)


class _Host(VehicleCargoMixin):
    """The VehicleController surface PullJob and pull_from_source() read; driving always fails."""
    name = "pioneer_8"
    home_base = "outpost_1"

    def __init__(self, cargo=0, unload=5, throttle=0.1):
        self.log = TreeConsole()
        self.vehicle = _Vehicle(cargo)
        self.home_outpost = None
        self.intent = None
        self.unload_result = unload
        self.throttle = throttle
        self.calls = []

    def handle_upgrade_cycle_if_idle(self):
        self.calls.append("upgrade")

    def get_current_tick(self):
        return 42

    def is_at_base(self):
        return False

    def set_intent(self, text):
        self.intent = text

    def publish_telemetry(self, state, *args):
        self.calls.append(state)

    def return_to_base(self):
        self.calls.append("return")
        return True

    def unload_cargo(self, outpost=None):
        self.calls.append("unload")
        self.vehicle.cargo.items = {}
        return self.unload_result

    def recharge_at_station(self, target_level=1.0):
        self.calls.append("recharge")

    def drive_with_recharge(self, x, y, precision=1.5, min_throttle=None):
        return False

    def full_battery_throttle(self, coords):
        return self.throttle


class PullJobTests(harness.StubTestCase):
    def test_cargo_aboard_is_delivered_before_planning(self):
        host = _Host(cargo=12)
        job = PullJob(host)
        with mock.patch.object(pull_plan, "pull_deficits_tiered") as deficits:
            self.assertEqual(job.step(), 0)
        deficits.assert_not_called()
        self.assertEqual(host.calls, ["upgrade", "RETURNING", "return", "unload", "recharge", "READY_AT_OUTPOST"])

    def test_blocked_unload_waits_poll_interval(self):
        host = _Host(cargo=12, unload=-1)
        self.assertEqual(PullJob(host, poll_interval=7.0).step(), 7.0)
        self.assertIn("WAITING_INVENTORY_SPACE", host.calls)

    def test_no_demand_parks_idle(self):
        host = _Host()
        job = PullJob(host)
        with mock.patch.object(pull_plan, "pull_deficits_tiered", return_value={}):
            self.assertEqual(job.step(), 10.0)
        self.assertEqual(job.wait, NO_DEMAND)
        self.assertEqual(host.calls, ["upgrade", "return", "IDLE_AT_OUTPOST"])

    def test_plan_below_minimum_waits(self):
        host = _Host()
        job = PullJob(host)
        with (mock.patch.object(pull_plan, "pull_deficits_tiered", return_value={"need": {"ore": 50}}),
              mock.patch.object(pull_plan, "plan_pull_route", return_value=([], 0)) as plan):
            self.assertEqual(job.step(), 10.0)
        self.assertIs(plan.call_args.args[4], job.unviable)
        self.assertEqual(job.wait, SHORT)
        self.assertEqual(host.calls, ["upgrade", "IDLE_AT_OUTPOST"])

    def test_unreachable_first_stop_is_recorded_on_the_job(self):
        host = _Host()
        job = PullJob(host)
        first = {"kind": "outpost", "id": "outpost_2", "coords": (100.0, 0.0), "outpost": None}
        later = {"kind": "outpost", "id": "outpost_3", "coords": (200.0, 0.0), "outpost": None}
        route = [(first, [("ore", 10)]), (later, [("ore", 5)])]
        delay = job.execute(Mission(kind="pull", target_key="outpost_2", target={"route": route}, tick=42))
        self.assertEqual(delay, job.poll_interval)
        self.assertEqual(job.unviable, {"outpost_2": 42})
        self.assertIn("return", host.calls)

    def test_viable_but_failed_leg_is_not_recorded(self):
        host = _Host(throttle=0.9)
        unviable = {}
        source = {"kind": "outpost", "id": "outpost_2", "coords": (100.0, 0.0), "outpost": None}
        self.assertIsNone(host.pull_from_source(source, [("ore", 10)], "outpost_1", 42, unviable=unviable))
        self.assertEqual(unviable, {})


class DropUnviableTests(unittest.TestCase):
    def test_prunes_expired_and_drops_the_rest(self):
        unviable = {"a": 0, "b": pull_plan.PULL_UNVIABLE_COOLDOWN_TICKS}
        sources = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        kept = pull_plan.drop_unviable_sources(sources, unviable, pull_plan.PULL_UNVIABLE_COOLDOWN_TICKS + 1)
        self.assertEqual([s["id"] for s in kept], ["a", "c"])
        self.assertEqual(unviable, {"b": pull_plan.PULL_UNVIABLE_COOLDOWN_TICKS})


if __name__ == "__main__":
    unittest.main()
