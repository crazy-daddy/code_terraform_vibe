import unittest

from harness import StubTestCase
from game_stubs import ThermalCap
import thermal_cap


# Ticks a poll lands after its requested sleep: the step itself and the scheduler
# cost game time (a 1 s poll is 13-15 ticks in a live log).
POLL_LAG_TICKS = 4


class ThermalCapReliefTests(StubTestCase):
    def run_cap(self, cap, ticks, on_tick=None):
        """Runs the controller against the cap's chamber, one game flow tick per sim tick."""
        self.world.components[cap.id] = cap
        ctl = thermal_cap.ThermalCapController(cap)
        ctl.ensure_output_connection = lambda: None
        hours_per_tick = 1.0 / (10.0 * self.world.clock.seconds_per_hour)
        tick = 0
        while tick < ticks:
            sleep = ctl.step()
            for _ in range(int(round(sleep * 10)) + POLL_LAG_TICKS):
                if on_tick:
                    on_tick(tick)
                cap.advance(hours_per_tick)
                self.world.clock.now += 1
                tick += 1
        return ctl

    def test_full_downstream_holds_chamber_below_ceiling(self):
        cap = ThermalCap(self.world, "thermal_cap_1", capture=1200.0, accept=0.0, level=900.0)
        self.run_cap(cap, 3000)
        self.assertEqual(cap.overpressures, 0, self.debug_log())
        self.assertGreater(cap.relief(), 0.0)
        self.assertLess(cap.pressure(), thermal_cap.PRESSURE_RELIEF_THRESHOLD + 0.05)

    def test_downstream_filling_mid_sleep_does_not_outrun_poll(self):
        cap = ThermalCap(self.world, "thermal_cap_1", capture=1200.0, accept=1100.0, level=500.0)

        def tank_fills(tick):
            if tick == 400:
                cap.accept = 0.0

        self.run_cap(cap, 3000, tank_fills)
        self.assertEqual(cap.overpressures, 0, self.debug_log())

    def test_consumers_catching_up_close_relief(self):
        cap = ThermalCap(self.world, "thermal_cap_1", capture=1000.0, accept=0.0, level=950.0)

        def consumers_return(tick):
            if tick == 500:
                cap.accept = 2000.0

        ctl = self.run_cap(cap, 1500, consumers_return)
        self.assertEqual(cap.overpressures, 0, self.debug_log())
        self.assertFalse(ctl.relief_engaged)
        self.assertEqual(cap.relief(), 0.0)


if __name__ == "__main__":
    unittest.main()
