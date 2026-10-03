"""lib/turbine_commit.py: how many Steam Turbines a grid runs, and which."""
import unittest
from typing import Any, cast

from harness import StubTestCase
import turbine_commit
from script_parking import PARKED_KEY


class NeedTests(unittest.TestCase):
    def test_need_plus_ten_percent_spare(self):
        target, spare, _ = turbine_commit.turbine_needed(1000.0, 0.0, 1000.0, 1000.0, 20)
        self.assertEqual(spare, 2)
        self.assertEqual(target, 10 + 2)  # ceil(1000 / 108) = 10

    def test_other_generation_and_top_up(self):
        full, _, _ = turbine_commit.turbine_needed(1000.0, 500.0, 1000.0, 1000.0, 20)
        self.assertEqual(full, 5 + 2)
        low, _, _ = turbine_commit.turbine_needed(1000.0, 500.0, 800.0, 1000.0, 20)
        self.assertEqual(low, 6 + 2)  # (500 + 200 / 2 h) / 108 -> 6

    def test_emergency_runs_everything(self):
        target, _, reason = turbine_commit.turbine_needed(100.0, 0.0, 400.0, 1000.0, 20)
        self.assertEqual(target, 20)
        self.assertIn("all turbines", reason)

    def test_all_on_latch_overrides_battery(self):
        target, _, _ = turbine_commit.turbine_needed(100.0, 0.0, 600.0, 1000.0, 20, all_on=True)
        self.assertEqual(target, 20)
        target, _, _ = turbine_commit.turbine_needed(100.0, 0.0, 400.0, 1000.0, 20, all_on=False)
        self.assertEqual(target, 4 + 2)  # (100 + 600 / 2 h) / 108 -> 4

    def test_steam_surplus_ignores_other_generation(self):
        target, _, reason = turbine_commit.turbine_needed(1000.0, 800.0, 1000.0, 1000.0, 20, surplus=True)
        self.assertEqual(target, 10 + 2)
        self.assertIn("steam surplus", reason)


class StepTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.add_tank("tank_full", self.world.home, "steam", 90.0, type_id="gas_tank", capacity=100.0)
        self.world.add_tank("tank_empty", self.world.home, "steam", 0.0, type_id="gas_tank", capacity=100.0)
        self.power = self.world.power_control

    def add(self, turbine_id, buffer, source="", output=108.0, stalled=False, throttle=0.0):
        """A turbine with `buffer` steam in its 100-unit steam_in."""
        self.world.add_turbine(turbine_id, self.world.home, buffer, source, output, stalled, throttle)

    def grid(self, ids, consumed, generated):
        return self.world.add_grid("grid_a", ids, consumed, generated, stored=1000.0, capacity=1000.0)

    def test_parks_the_worst_supplied_and_keeps_the_best(self):
        # Y: dry own buffer on an empty tank; X: full buffer on a full tank.
        for i in range(4):
            self.add(f"turbine_{i}", buffer=80, source="tank_full")
        self.add("turbine_x", buffer=90, source="tank_full")
        self.add("turbine_y", buffer=5, source="tank_empty", output=0.0)
        ids = [f"turbine_{i}" for i in range(4)] + ["turbine_x", "turbine_y"]
        commit = turbine_commit.TurbineCommitment(self.power)
        commit.step(self.grid(ids, consumed=216.0, generated=5 * 108.0), "grid_a")  # need 2 + 1 spare
        running = {t for t in ids if self.power.is_powered(t)}
        self.assertEqual(len(running), 3)
        self.assertIn("turbine_x", running)
        self.assertNotIn("turbine_y", running)
        parked = self.world.notebook.data[PARKED_KEY]
        self.assertEqual({e["mode"] for e in parked.values()}, {"turbine"})
        self.assertEqual(set(parked), set(ids) - running)

    def test_wakes_parked_turbines_when_demand_rises_and_ignores_others_switched_off(self):
        ids = [f"turbine_{i}" for i in range(4)]
        for t in ids:
            self.add(t, buffer=80, source="tank_full")
        self.add("turbine_manual", buffer=80, source="tank_full")
        self.power.powered["turbine_manual"] = False  # switched off by the player
        commit = turbine_commit.TurbineCommitment(self.power)
        grid = self.grid(ids + ["turbine_manual"], consumed=100.0, generated=400.0)
        commit.step(grid, "grid_a")
        self.assertEqual(sum(self.power.is_powered(t) for t in ids), 2)  # 1 + 1 spare
        grid.consumed, grid.generated = 400.0, 216.0
        commit.step(grid, "grid_a")
        self.assertTrue(all(self.power.is_powered(t) for t in ids))
        self.assertFalse(self.power.is_powered("turbine_manual"))
        self.assertNotIn("turbine_manual", self.world.notebook.data.get(PARKED_KEY, {}))

    def test_restarted_turbines_count_by_throttle_not_stale_output(self):
        # Just (re)started: throttle set, power_output() still from the previous power tick.
        ids = [f"turbine_{i}" for i in range(10)]
        for t in ids:
            self.add(t, buffer=80, source="tank_full", output=0.0, throttle=1.0)
        # 10 turbines at full make all 1080 W: none of it is "other" generation.
        turbine_commit.TurbineCommitment(self.power).step(self.grid(ids, consumed=1000.0, generated=1080.0), "grid_a")
        self.assertEqual(sum(self.power.is_powered(t) for t in ids), 10)  # ceil(1000 / 108) = 10, + spare, capped

    def test_step_writes_the_commitment_heartbeat(self):
        self.add("turbine_a", buffer=80, source="tank_full")
        turbine_commit.TurbineCommitment(self.power).step(self.grid(["turbine_a"], consumed=50.0, generated=108.0), "grid_a")
        self.assertIn("grid_a", self.world.notebook.data[turbine_commit.COMMIT_HEARTBEAT_KEY])

    def test_too_few_able_to_deliver_keeps_every_turbine_up(self):
        ids = ["turbine_a", "turbine_b", "turbine_c"]
        self.add("turbine_a", buffer=80, source="tank_full")
        self.add("turbine_b", buffer=2, stalled=True)
        self.add("turbine_c", buffer=2, stalled=True)
        turbine_commit.TurbineCommitment(self.power).step(self.grid(ids, consumed=300.0, generated=108.0), "grid_a")
        self.assertTrue(all(self.power.is_powered(t) for t in ids))

    def test_all_on_holds_until_release_fraction(self):
        ids = [f"turbine_{i}" for i in range(6)]
        for t in ids:
            self.add(t, buffer=80, source="tank_full")
        commit = turbine_commit.TurbineCommitment(self.power)
        grid = self.world.add_grid("grid_a", ids, consumed=100.0, generated=600.0, stored=400.0, capacity=1000.0)
        commit.step(grid, "grid_a")
        self.assertTrue(commit.all_on.active)
        grid._stored = 650.0  # above the 50% start line, below the 70% release
        commit.step(grid, "grid_a")
        self.assertTrue(commit.all_on.active)
        self.assertTrue(all(self.power.is_powered(t) for t in ids))
        grid._stored = 700.0
        commit.step(grid, "grid_a")
        self.assertFalse(commit.all_on.active)

    def test_steam_surplus_latch(self):
        self.add("turbine_a", buffer=80, source="tank_full")
        commit = turbine_commit.TurbineCommitment(self.power)
        grid = self.grid(["turbine_a"], consumed=50.0, generated=108.0)
        for fraction, expected in ((0.95, False), (0.98, True), (0.91, True), (0.89, False), (None, False)):
            commit.step(grid, "grid_a", fraction)
            self.assertEqual(commit.surplus.active, expected, fraction)


class TurbineEasingTests(StubTestCase):
    def test_committed_grid_runs_full_otherwise_eases(self):
        import steam_turbine

        grid = self.world.add_grid("grid_a", [], consumed=1400.0, generated=2000.0, stored=10900.0, capacity=11000.0)
        controller = steam_turbine.SteamTurbineController.__new__(steam_turbine.SteamTurbineController)
        controller.name, controller.clock, controller._eased = "turbine_1", cast(Any, self.world.clock), False
        controller.log = steam_turbine.TreeConsole(module="steam_turbine")
        controller.buffer_fraction = lambda: 1.0
        controller.is_night = lambda: False
        controller.get_grid = lambda: cast(Any, grid)
        self.assertEqual(controller.choose_throttle(), steam_turbine.THROTTLE_DEMAND_MET)
        self.world.notebook.data[steam_turbine.COMMIT_HEARTBEAT_KEY] = {"grid_a": self.world.clock.now}
        self.assertEqual(controller.choose_throttle(), 1.0)
        self.world.clock.now += steam_turbine.COMMIT_FRESH_TICKS
        self.assertEqual(controller.choose_throttle(), steam_turbine.THROTTLE_DEMAND_MET)


if __name__ == "__main__":
    unittest.main()
