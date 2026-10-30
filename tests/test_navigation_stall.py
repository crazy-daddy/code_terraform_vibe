"""Vehicle driving limits (lib/vehicle_navigation.py) on a real VehicleController.

drive_to() polls once per sleep(1.0). A poll that moved less than the stall
threshold (0.3 m, a literal in _drive_leg) counts as stalled; 8 stalled polls in
a row trigger one recovery (brake, re-issue at MIN_SPEEDMODE_THROTTLE), and the
4th trigger gives up. Bugs caught: a rover that never gives up (throttle stays
engaged and drains the battery) or gives up before its recoveries are spent;
a drive timeout below its floor; is_at_base() off by its threshold edge.
"""

import inspect
import unittest
from unittest import mock

import game_clock
import game_rules
from harness import StubTestCase
from vehicle import VehicleController
from vehicle_host import ScriptedNav, make_vehicle

STALL_POLLS = 8  # stalled polls per recovery
RECOVERIES = 3  # recoveries before giving up
GIVE_UP_POLLS = STALL_POLLS * (RECOVERIES + 1)
FAR = (1000.0, 0.0)


def _default(func, name):
    return inspect.signature(func).parameters[name].default


class _DriveCase(StubTestCase):
    def setUp(self):
        super().setUp()
        self.nav = ScriptedNav()
        self.ctl, _pioneer = make_vehicle(self.world, nav=self.nav)
        self.polls = 0
        self.schedule = lambda _poll: 0.0  # metres moved on each poll

    def _sleep(self, seconds):
        if seconds == 1.0:
            self.polls += 1
            self.nav.x += self.schedule(self.polls)

    def drive(self, target=FAR):
        with mock.patch("builtins.sleep", self._sleep):
            return self.ctl.drive_to(target[0], target[1], timeout_ticks=10_000_000)


class StallGiveUpTests(_DriveCase):
    def assert_gave_up(self):
        self.assertFalse(self.drive())
        self.assertEqual(self.polls, GIVE_UP_POLLS)
        min_t = self.ctl.MIN_SPEEDMODE_THROTTLE
        self.assertEqual(self.nav.throttles[1:], [min_t] * RECOVERIES)
        self.assertGreaterEqual(self.nav.brakes, RECOVERIES + 1)

    def test_never_moving_gives_up_after_the_last_recovery(self):
        self.assert_gave_up()

    def test_moving_just_under_the_threshold_counts_as_stalled(self):
        self.schedule = lambda _poll: 0.29
        self.assert_gave_up()

    def test_moving_just_over_the_threshold_arrives(self):
        self.schedule = lambda _poll: 0.31
        self.assertTrue(self.drive(target=(20.0, 0.0)))
        self.assertEqual(len(self.nav.throttles), 1)  # no recovery

    def test_moving_after_the_last_recovery_still_arrives(self):
        # Stuck through 3 recoveries and 7 more polls; free on the poll that would give up.
        self.schedule = lambda poll: 0.0 if poll < GIVE_UP_POLLS else 1.0
        self.assertTrue(self.drive(target=(20.0, 0.0)))
        self.assertEqual(self.nav.throttles[1:], [self.ctl.MIN_SPEEDMODE_THROTTLE] * RECOVERIES)

    def test_progress_resets_the_recovery_count(self):
        # 3 recoveries, one good poll, then stuck again: a fresh budget of 4 triggers.
        stuck_until = STALL_POLLS * RECOVERIES
        self.schedule = lambda poll: 1.0 if poll == stuck_until + 1 else 0.0
        self.assertFalse(self.drive())
        self.assertEqual(self.polls, stuck_until + 1 + GIVE_UP_POLLS)


class DriveTimeoutTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.ctl, _pioneer = make_vehicle(self.world)
        self.min_ticks = _default(VehicleController.drive_timeout_ticks, "min_ticks")
        self.safety = _default(VehicleController.drive_timeout_ticks, "safety_multiplier")

    def edge_distance(self, throttle):
        """Distance whose expected drive time is exactly min_ticks."""
        speed = self.ctl.DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE * throttle
        seconds_per_hour = game_clock.real_seconds_per_hour()
        return self.min_ticks / (game_rules.TICKS_PER_SECOND * self.safety * seconds_per_hour) * speed

    def test_zero_distance_gets_the_floor(self):
        self.assertEqual(self.ctl.drive_timeout_ticks(0.0, 0.5), self.min_ticks)

    def test_floor_holds_up_to_its_edge(self):
        edge = self.edge_distance(0.5)
        self.assertEqual(self.ctl.drive_timeout_ticks(edge * 0.99, 0.5), self.min_ticks)
        self.assertGreater(self.ctl.drive_timeout_ticks(edge * 1.01, 0.5), self.min_ticks)

    def test_throttle_below_the_speedmode_floor_is_timed_at_the_floor(self):
        floor = self.ctl.MIN_SPEEDMODE_THROTTLE
        far = self.edge_distance(floor) * 10
        self.assertEqual(self.ctl.drive_timeout_ticks(far, 0.0), self.ctl.drive_timeout_ticks(far, floor))


class AtBaseEdgeTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.nav = ScriptedNav()
        self.ctl, _pioneer = make_vehicle(self.world, nav=self.nav)
        self.threshold = _default(VehicleController.is_at_base, "threshold")

    def at(self, x):
        self.nav.x = self.ctl.assigned_slot_coords[0] + x
        self.nav.y = self.ctl.assigned_slot_coords[1]
        return self.ctl.is_at_base()

    def test_exactly_at_threshold_is_home(self):
        self.assertTrue(self.at(self.threshold))

    def test_just_inside_is_home(self):
        self.assertTrue(self.at(self.threshold - 0.01))

    def test_just_outside_is_away(self):
        self.assertFalse(self.at(self.threshold + 0.01))


if __name__ == "__main__":
    unittest.main()
