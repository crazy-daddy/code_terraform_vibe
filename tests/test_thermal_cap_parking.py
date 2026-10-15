import unittest
from typing import Any, cast

import thermal_cap
from game_stubs import Clock
from harness import StubTestCase


class _Cap:
    id = "thermal_cap_1"

    def __init__(self, phase_in=None):
        self.phase_in = phase_in

    def next_phase_in(self):
        return self.phase_in


def _controller(cap, phase="dormant", pressure=0.0, max_rise=0.0):
    ctl = thermal_cap.ThermalCapController.__new__(thermal_cap.ThermalCapController)
    ctl.cap = cap
    ctl.name = cap.id
    ctl.clock = cast(Any, Clock(30.0))
    ctl.last_phase = phase
    ctl.last_pressure = pressure
    ctl.max_rise_per_tick = max_rise
    return ctl


class ParkWakeTicksTests(StubTestCase):
    def test_active_or_undrained_cap_keeps_running(self):
        self.assertIsNone(_controller(_Cap(60), phase="active").park_wake_ticks())
        self.assertIsNone(_controller(_Cap(60), pressure=0.1).park_wake_ticks())

    def test_deep_surveyed_vent_parks_until_just_before_it_turns_active(self):
        # 240 game-minutes at 30 real s/h = 120 s = 1,200 ticks, minus the lead
        self.assertEqual(_controller(_Cap(240)).park_wake_ticks(), 1200 - thermal_cap.CAP_WAKE_LEAD_TICKS)

    def test_deep_surveyed_vent_close_to_active_keeps_running(self):
        # 60 game-minutes = 300 ticks: less than the lead plus CAP_PARK_MIN_TICKS
        self.assertIsNone(_controller(_Cap(60)).park_wake_ticks())

    def test_without_phase_timing_uses_fastest_rise(self):
        self.assertIsNone(_controller(_Cap(None)).park_wake_ticks())
        ticks = _controller(_Cap(None), max_rise=0.001).park_wake_ticks()
        self.assertEqual(ticks, int(thermal_cap.PRESSURE_BAND_CRITICAL / 0.001 * thermal_cap.CAP_PARK_WAKE_FRACTION))


if __name__ == "__main__":
    unittest.main()
