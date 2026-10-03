import unittest

from harness import StubTestCase
from game_stubs import Clock
import thermal_cap


class _Cap:
    id = "thermal_cap_1"

    def __init__(self, phase_in=None):
        self.phase_in = phase_in

    def next_phase_in(self):
        return self.phase_in


class _Clock(Clock):
    def real_seconds_per_hour(self):
        return 30.0


def _controller(cap, phase="dormant", pressure=0.0, max_rise=0.0):
    ctl = thermal_cap.ThermalCapController.__new__(thermal_cap.ThermalCapController)
    ctl.cap = cap
    ctl.name = cap.id
    ctl.clock = _Clock()
    ctl.last_phase = phase
    ctl.last_pressure = pressure
    ctl.max_rise_per_tick = max_rise
    return ctl


class ParkWakeTicksTests(StubTestCase):
    def test_active_or_undrained_cap_keeps_running(self):
        self.assertIsNone(_controller(_Cap(60), phase="active").park_wake_ticks())
        self.assertIsNone(_controller(_Cap(60), pressure=0.1).park_wake_ticks())

    def test_deep_surveyed_vent_parks_for_half_the_dormancy_left(self):
        # 60 game-minutes at 30 real s/h = 30 s = 300 ticks; half of that
        self.assertEqual(_controller(_Cap(60)).park_wake_ticks(), 150)

    def test_without_phase_timing_uses_fastest_rise(self):
        self.assertIsNone(_controller(_Cap(None)).park_wake_ticks())
        ticks = _controller(_Cap(None), max_rise=0.001).park_wake_ticks()
        self.assertEqual(ticks, int(thermal_cap.PRESSURE_BAND_CRITICAL / 0.001 * thermal_cap.CAP_PARK_WAKE_FRACTION))


if __name__ == "__main__":
    unittest.main()
