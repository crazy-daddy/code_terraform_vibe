import unittest

from harness import StubTestCase
import script_parking
from script_parking import ParkRequester, ScriptParking, PARK_REQUESTS_KEY, PARKED_KEY, WAKE_AFTER_TICKS


class _Result:
    def __init__(self, status="ok"):
        self.status = status


class _PowerControl:
    def __init__(self):
        self.powered = {}
        self.calls = []

    def can_power_off(self, machine_id):
        return not machine_id.startswith("solar")

    def set_powered(self, machine_id, on):
        self.calls.append((machine_id, on))
        self.powered[machine_id] = on
        return _Result()


class _RunControl:
    def __init__(self, running):
        self.running = set(running)

    def is_running(self, machine_id):
        return machine_id in self.running

    def stop(self, machine_id):
        self.running.discard(machine_id)
        return _Result()

    def start(self, machine_id):
        self.running.add(machine_id)
        return _Result()


class _Member:
    def __init__(self, machine_id, type_id):
        self.id = machine_id
        self.type_id = type_id


class _Grid:
    anchor_id = "grid_a"

    def __init__(self, members):
        self.members = members


class _Machine:
    pass


class _FakePower:
    """Stands in for lib/power.py's reserve helpers."""

    def __init__(self, fraction):
        self.fraction = fraction

    def grid_steam_tank_ids(self, grid):
        return []

    def measure_grid(self, grid, tank_ids):
        return {"bat_wh": self.fraction * 100, "bat_cap": 100, "steam_t": 0, "steam_cap": 0}

    def reserve_fraction(self, now):
        return self.fraction


class ParkRequesterTests(StubTestCase):
    def test_requests_after_idle_steps_and_withdraws_when_busy(self):
        requester = ParkRequester("smelter_1", "smelter")
        for _ in range(script_parking.PARK_AFTER_IDLE_STEPS - 1):
            requester.update(True)
        self.assertNotIn("smelter_1", self.world.notebook.data.get(PARK_REQUESTS_KEY, {}))
        requester.update(True)
        self.assertEqual(self.world.notebook.data[PARK_REQUESTS_KEY]["smelter_1"]["kind"], "smelter")
        requester.update(False)
        self.assertNotIn("smelter_1", self.world.notebook.data[PARK_REQUESTS_KEY])


class ScriptParkingTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.power = _PowerControl()
        self.run = _RunControl(["solar_1"])
        for machine_id in ("smelter_1", "supply_dock_1", "oil_generator_1", "solar_1"):
            self.world.components[machine_id] = _Machine()
        self.grids = [_Grid([
            _Member("smelter_1", "smelter"),
            _Member("supply_dock_1", "supply_dock"),
            _Member("oil_generator_1", "oil_generator"),
            _Member("solar_1", "solar_generator"),
        ])]
        self.parking = ScriptParking(power=self.power, run_control=self.run)
        self._real_power = script_parking.power

    def tearDown(self):
        script_parking.power = self._real_power
        super().tearDown()

    def request(self, machine_id, kind):
        requests = self.world.notebook.data.setdefault(PARK_REQUESTS_KEY, {})
        requests[machine_id] = {"kind": kind, "tick": self.world.clock.now}

    def test_parks_fresh_request_and_wakes_when_due(self):
        self.request("smelter_1", "smelter")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls, [("smelter_1", False)])
        self.assertEqual(self.world.notebook.data[PARKED_KEY]["smelter_1"]["mode"], "breaker")
        self.world.clock.now += WAKE_AFTER_TICKS["smelter"]
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("smelter_1", True))
        self.assertNotIn("smelter_1", self.world.notebook.data[PARKED_KEY])
        self.assertNotIn("smelter_1", self.world.notebook.data[PARK_REQUESTS_KEY])

    def test_stale_request_and_shed_machine_are_not_parked(self):
        self.request("smelter_1", "smelter")
        self.world.clock.now += script_parking.REQUEST_FRESH_TICKS + 1
        self.parking.step(self.grids, 10.0)
        self.request("supply_dock_1", "supply_dock")
        self.world.notebook.data["power.shedded"] = ["supply_dock_1"]
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls, [])

    def test_dock_with_an_order_stays_and_parked_dock_wakes_on_assignment(self):
        self.request("supply_dock_1", "supply_dock")
        self.parking.step(self.grids, 10.0, {"supply_dock_1": "order_7"})
        self.assertEqual(self.power.calls, [])
        self.parking.step(self.grids, 10.0, {"supply_dock_1": None})
        self.assertEqual(self.power.calls, [("supply_dock_1", False)])
        self.parking.step(self.grids, 10.0, {"supply_dock_1": "order_7"})
        self.assertEqual(self.power.calls[-1], ("supply_dock_1", True))

    def test_oil_generator_wakes_and_stays_up_on_low_reserve(self):
        script_parking.power = _FakePower(0.5)
        self.request("oil_generator_1", "oil_generator")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls, [("oil_generator_1", False)])
        script_parking.power = _FakePower(0.1)
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("oil_generator_1", True))
        self.request("oil_generator_1", "oil_generator")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("oil_generator_1", True))

    def test_solar_stopped_at_night_and_started_at_sunrise(self):
        self.parking.step(self.grids, -3.0)
        self.assertNotIn("solar_1", self.run.running)
        self.assertEqual(self.world.notebook.data[PARKED_KEY]["solar_1"]["mode"], "stopped")
        self.parking.step(self.grids, 2.0)
        self.assertIn("solar_1", self.run.running)
        self.assertNotIn("solar_1", self.world.notebook.data[PARKED_KEY])

    def test_solar_script_stopped_by_the_player_is_not_started(self):
        self.run.running.clear()
        self.parking.step(self.grids, -3.0)
        self.parking.step(self.grids, 2.0)
        self.assertNotIn("solar_1", self.run.running)


if __name__ == "__main__":
    unittest.main()
