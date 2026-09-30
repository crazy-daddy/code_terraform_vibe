"""lib/turbine_commit.py: how many Steam Turbines a grid runs, and which."""
import unittest

from harness import StubTestCase
import turbine_commit
from script_parking import PARKED_KEY


class _Result:
    status = "ok"


class _Port:
    def __init__(self, level, capacity=100, source=None):
        self._level, self._capacity, self._source = level, capacity, source

    def level(self):
        return self._level

    def capacity(self):
        return self._capacity

    def connected_id(self):
        return self._source


class _Turbine:
    def __init__(self, buffer, source=None, output=108.0, stalled=False):
        self.steam_in = _Port(buffer, source=source)
        self.output, self.stalled = output, stalled

    def is_stalled(self):
        return self.stalled

    def power_output(self):
        return self.output


class _Tank:
    def __init__(self, pct):
        self.pct = pct

    def fill_pct(self):
        return self.pct


class _Power:
    def __init__(self, powered):
        self.powered = dict(powered)

    def is_powered(self, machine_id):
        return self.powered.get(machine_id, True)

    def set_powered(self, machine_id, on):
        self.powered[machine_id] = on
        return _Result()


class _Member:
    def __init__(self, machine_id):
        self.id, self.type_id = machine_id, "steam_turbine"


class _Grid:
    def __init__(self, ids, consumed, generated, stored=1000.0, capacity=1000.0):
        self.members = [_Member(i) for i in ids]
        self.consumed, self.generated, self.stored, self.capacity = consumed, generated, stored, capacity


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


class StepTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.components["tank_full"] = _Tank(90.0)
        self.world.components["tank_empty"] = _Tank(0.0)

    def add(self, turbine_id, **kwargs):
        self.world.components[turbine_id] = _Turbine(**kwargs)

    def test_parks_the_worst_supplied_and_keeps_the_best(self):
        # Y: dry own buffer on an empty tank; X: full buffer on a full tank.
        for i in range(4):
            self.add(f"turbine_{i}", buffer=80, source="tank_full")
        self.add("turbine_x", buffer=90, source="tank_full")
        self.add("turbine_y", buffer=5, source="tank_empty", output=0.0)
        ids = [f"turbine_{i}" for i in range(4)] + ["turbine_x", "turbine_y"]
        power = _Power({})
        commit = turbine_commit.TurbineCommitment(power)
        commit.step(_Grid(ids, consumed=216.0, generated=5 * 108.0), "grid_a")  # need 2 + 1 spare
        running = {t for t in ids if power.is_powered(t)}
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
        power = _Power({"turbine_manual": False})  # switched off by the player
        commit = turbine_commit.TurbineCommitment(power)
        commit.step(_Grid(ids + ["turbine_manual"], consumed=100.0, generated=400.0), "grid_a")
        self.assertEqual(sum(power.is_powered(t) for t in ids), 2)  # 1 + 1 spare
        commit.step(_Grid(ids + ["turbine_manual"], consumed=400.0, generated=216.0), "grid_a")
        self.assertTrue(all(power.is_powered(t) for t in ids))
        self.assertFalse(power.is_powered("turbine_manual"))
        self.assertNotIn("turbine_manual", self.world.notebook.data.get(PARKED_KEY, {}))

    def test_too_few_able_to_deliver_keeps_every_turbine_up(self):
        ids = ["turbine_a", "turbine_b", "turbine_c"]
        self.add("turbine_a", buffer=80, source="tank_full")
        self.add("turbine_b", buffer=2, stalled=True)
        self.add("turbine_c", buffer=2, stalled=True)
        power = _Power({})
        turbine_commit.TurbineCommitment(power).step(_Grid(ids, consumed=300.0, generated=108.0), "grid_a")
        self.assertTrue(all(power.is_powered(t) for t in ids))


if __name__ == "__main__":
    unittest.main()
