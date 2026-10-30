"""Hauling flow: a hauler Pioneer runs one pull trip through the real run_job_loop().

outpost_2 asks for iron ore, outpost_3 holds it, the Pioneer starts at home.
PullJob plans and claims the pickup, the real VehicleController drives out,
loads at outpost_3, drives to outpost_2, unloads into its Warehouse and stays
there as its new base. The NavModule here moves the Pioneer toward its target
on every drive poll and draws the battery by the controller's own Wh per metre.

Bugs caught: a pickup claim leaked after the delivery (or missing during the
trip), a trip that never returns to base, cargo that never arrives, a launch
past the energy budget (battery under the emergency reserve).
"""

import unittest
from unittest import mock

from harness import StubTestCase, request  # first: puts the script libs on sys.path

# isort: split
import fleet_unit
import logistics_requests
from game_stubs import Pioneer, Position, Result, Slot, VehicleBattery
from job_pull import PullJob
from vehicle import VehicleController

DEST = ("outpost_2", 300.0)
SOURCE = ("outpost_3", -300.0)
STEP_M = 50.0  # metres the Pioneer covers per drive poll
ORE = "iron_ore"


class _StopLoop(BaseException):
    """Ends run_job_loop() (a BaseException: its `except Exception` must not catch it)."""


class _Stuck(BaseException):
    """A wait that never ends: the stub clock stands still while sleep() returns at once."""


MAX_SLEEPS = 5000
CHARGE_WH_PER_S = 50.0


def _set_wh(pioneer, wh):
    """Sets the charge the way the game shows a new level: a fresh Battery reading."""
    pioneer.battery = VehicleBattery(pioneer.battery.capacity(), wh)


class _CargoPioneer(Pioneer):
    """Pioneer with cargo ports: input takes from storage, output sends to it,
    both local to the outpost the Pioneer stands at (`outpost`, moved by the nav)."""

    def __init__(self, world, pioneer_id, **state):
        super().__init__(world, pioneer_id, world.home, **state)
        self.input = Slot(self, self.cargo.items, self.cargo.capacity())
        self.output = Slot(self, self.cargo.items, self.cargo.capacity())

    def _input_used(self):
        return self.cargo.count()


class _DrivingNav:
    """Moves the Pioneer STEP_M toward its target per drive poll (get_distance_to()),
    draws the battery at the controller's Wh/m for the cargo aboard, and parks the
    Pioneer at an outpost it reaches. Calls on_poll() after every move."""

    def __init__(self, pioneer, outposts):
        self.pioneer = pioneer
        self.outposts = outposts
        self.ctl: VehicleController | None = None
        self.target = None
        self.throttle = 0.0
        self.on_poll = lambda: None

    def get_position(self):
        return Position(self.pioneer.x, self.pioneer.y)

    def set_target(self, x, y):
        self.target = (x, y)
        return Result("ok")

    def set_throttle(self, throttle):
        self.throttle = throttle
        return Result("ok")

    def brake(self):
        self.throttle = 0.0
        return Result("ok")

    def get_distance_to(self, x, y):
        if self.target is not None and self.throttle > 0 and self.ctl is not None:
            p = self.pioneer
            tx, ty = self.target
            gap = ((tx - p.x) ** 2 + (ty - p.y) ** 2) ** 0.5
            step = min(STEP_M, gap)
            if step > 0:
                p.x += (tx - p.x) * step / gap
                p.y += (ty - p.y) * step / gap
                rate = self.ctl.wh_per_meter_at_throttle(self.throttle, cargo_units=p.cargo.count())
                _set_wh(p, max(0.0, p.battery.wh() - step * rate))
            near = [o for o in self.outposts if ((o.x - p.x) ** 2 + (o.y - p.y) ** 2) ** 0.5 <= 3.0]
            p.outpost = near[0] if near else None
            self.on_poll()
        return ((x - self.pioneer.x) ** 2 + (y - self.pioneer.y) ** 2) ** 0.5


class HaulingFlowTest(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.dest = w.add_outpost(DEST[0])
        self.dest.x = DEST[1]
        self.source = w.add_outpost(SOURCE[0])
        self.source.x = SOURCE[1]
        self.dest_store = w.add_warehouse("wh_dest", self.dest, capacity=1000)
        self.source_store = w.add_warehouse("wh_source", self.source, {ORE: 200}, capacity=1000)
        logistics_requests.set_requests(DEST[0], "fab", {ORE: (request(40, 40), 0)}, w.clock.now)
        self.pioneer = _CargoPioneer(w, "pioneer_1", battery_wh=5000.0, battery_capacity=5000.0, cargo_capacity=40)
        w.components[self.pioneer.id] = self.pioneer
        nav = _DrivingNav(self.pioneer, [w.home, self.dest, self.source])
        self.pioneer.nav = nav  # type: ignore[attr-defined]
        self.ctl = VehicleController(self.pioneer)  # type: ignore[arg-type]  # stub Pioneer stands in for the game's
        self.ctl.role = "hauler"  # type: ignore[assignment]  # set by the Pioneer script's run()
        nav.ctl = self.ctl
        self.polls = []  # (x, battery Wh, pickup destination claimed) per drive poll
        nav.on_poll = lambda: self.polls.append(
            (self.pioneer.x, self.pioneer.battery.wh(), logistics_requests.pickup_dest(self.ctl.name))
        )

    def run_cycles(self, n):
        cycles = []

        def next_job(job):
            cycles.append(job)
            if len(cycles) >= n:
                raise _StopLoop
            return job

        self.ctl.next_job = next_job  # type: ignore[method-assign]
        # The stubs have no game version builtin; test_job_loop skips the guard the same way.
        sleeps = []

        def sleep(seconds):
            """Stands in for the station script: a Pioneer parked at an outpost charges CHARGE_WH_PER_S."""
            sleeps.append(seconds)
            if len(sleeps) > MAX_SLEEPS:
                raise _Stuck
            p = self.pioneer
            if p.outpost is not None and self.pioneer.nav.throttle == 0:  # type: ignore[attr-defined]
                _set_wh(p, min(p.battery.capacity(), p.battery.wh() + CHARGE_WH_PER_S * seconds))

        with (
            mock.patch.object(fleet_unit, "validate_game_version", lambda: None),
            mock.patch("builtins.sleep", sleep, create=True),
            self.assertRaises(_StopLoop),
        ):
            self.ctl.run_job_loop(PullJob(self.ctl))

    def test_pull_trip_claims_hauls_unloads_and_stays_at_base(self):
        # One cycle plans, claims, drives and delivers. (The next one, with no
        # demand left, disperses the base to the busiest source outpost.)
        self.run_cycles(1)

        # The trip went out to the source and on to the destination.
        xs = [x for x, _wh, _claim in self.polls]
        self.assertTrue(xs, "the Pioneer never drove")
        self.assertAlmostEqual(min(xs), SOURCE[1], delta=3.0)
        # The pickup stayed claimed for the destination on every poll of the trip.
        self.assertEqual({claim for _x, _wh, claim in self.polls}, {DEST[0]})
        # Cargo moved from source to destination storage, nothing left aboard.
        self.assertEqual(self.dest_store.items.get(ORE, 0), 40)
        self.assertEqual(self.source_store.items.get(ORE, 0), 160)
        self.assertEqual(self.pioneer.cargo.count(), 0)
        # Claim released, vehicle at its new base.
        self.assertIsNone(logistics_requests.pickup_dest(self.ctl.name))
        self.assertEqual(self.ctl.base_id, DEST[0])
        self.assertTrue(self.ctl.is_at_base())
        # Never below the emergency reserve.
        self.assertGreaterEqual(min(wh for _x, wh, _claim in self.polls), self.ctl.MIN_EMERGENCY_RESERVE_WH)

    def test_short_battery_never_drives_below_the_emergency_reserve(self):
        # 20 Wh above the reserve: the 1,200 m trip needs about 30.
        start_wh = self.ctl.MIN_EMERGENCY_RESERVE_WH + 20.0
        _set_wh(self.pioneer, start_wh)
        self.run_cycles(1)
        self.assertGreaterEqual(min(wh for _x, wh, _claim in self.polls), self.ctl.MIN_EMERGENCY_RESERVE_WH)
        # It charged before the pull leg: by the time it reached the source it
        # held more than it started with (it parks at a charger first).
        at_source = next(wh for x, wh, _claim in self.polls if x <= SOURCE[1] + 3.0)
        self.assertGreater(at_source, start_wh)
        # Then it made the same delivery.
        self.assertEqual(self.dest_store.items.get(ORE, 0), 40)
        self.assertIsNone(logistics_requests.pickup_dest(self.ctl.name))
        self.assertTrue(self.ctl.is_at_base())


if __name__ == "__main__":
    unittest.main()
