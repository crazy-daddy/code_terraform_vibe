"""Reactor controller (10_nuclear/lib/reactor.py) against a Reactor that steps like the simworker."""
import math
import unittest

import harness
import fluid_routing
import reactor as rx

SECONDS_PER_GH = 25.0
TICK_GH = 0.1 / SECONDS_PER_GH


class _Result:
    def __init__(self, status="ok", moved=0):
        self.status = status
        self.message = ""
        self.moved = moved


class _SimClock:
    def __init__(self):
        self.now = 1000
        self.hours = 0.0

    def tick(self):
        return self.now

    def elapsed_game_hours(self):
        return self.hours

    def real_seconds_per_hour(self):
        return SECONDS_PER_GH


class _Cask:
    type_id = "lead_cask"

    def __init__(self, world, cask_id, outpost, material="", count=0):
        self.id = cask_id
        self.outpost = outpost
        self._material = material
        self.units = count
        world.components[cask_id] = self

    def material(self):
        return self._material if self.units > 0 else ""

    def count(self, item_id):
        return self.units if item_id == self.material() else 0

    def capacity(self):
        return 100


class _RodInput:
    def __init__(self, world, staged=0):
        self.world = world
        self.staged = staged
        self.source = ""

    def connected_id(self):
        return self.source

    def connect(self, source_id):
        self.source = source_id
        return _Result()

    def take(self, item_id, count):
        cask = self.world.components.get(self.source)
        moved = min(count, cask.count(item_id)) if isinstance(cask, _Cask) else 0
        if moved:
            cask.units -= moved
            self.staged += moved
        return _Result("ok" if moved else "source_empty", moved)

    def count(self):
        return self.staged


class _Tank:
    type_id = "liquid_tank"

    def __init__(self, world, tank_id, outpost, level, capacity=100.0):
        self.id = tank_id
        self.outpost = outpost
        self.tons = level
        self.cap = capacity
        world.components[tank_id] = self

    def fluid(self):
        return "water" if self.tons > 0 else ""

    def level(self):
        return self.tons

    def capacity(self):
        return self.cap


class _WaterPort:
    def __init__(self, source="tank_a"):
        self.source = source
        self.disconnects = 0

    def connected_id(self):
        return self.source

    def connect(self, source_id):
        self.source = source_id
        return _Result()

    def disconnect(self):
        self.source = ""
        self.disconnects += 1
        return _Result()


class _SimReactor:
    """Simworker reactor step (ige) per 0.1 s tick; condition from `conditions[window]`."""
    type_id = "reactor"

    def __init__(self, world, clock, outpost, conditions, staged=1):
        self.id = "reactor_1"
        self.outpost = outpost
        self.clock = clock
        self.conditions = conditions
        self.input = _RodInput(world, staged)
        self.water_in = None
        self._heat = 0.0
        self.temp = 20.0
        self.rod = 0.0
        self.overheated = False
        self.output = 0.0
        self.max_temp = 0.0
        world.components[self.id] = self

    def set_heat(self, value):
        self._heat = min(1.0, max(0.0, value))
        return _Result()

    def heat(self):
        return self._heat

    def temperature(self):
        return self.temp

    def status(self):
        if self.overheated:
            return "overheated"
        if self.rod <= 0 and self.input.staged <= 0:
            return "no_fuel"
        return "running"

    def gain(self):
        window = int(self.clock.hours // 12)
        return 1200.0 * self.conditions[window % len(self.conditions)]

    def step(self, dt):
        if self.overheated:
            self.temp = max(0.0, self.temp - 260 * dt)
            if self.temp <= 600:
                self.overheated = False
            self.output = 0.0
            return
        if self.rod <= 0:
            if self.input.staged <= 0:
                self.temp = max(0.0, self.temp - 260 * dt)
                self.output = 0.0
                return
            self.input.staged -= 1
            self.rod = 1.0
        if self._heat <= 0:
            self.temp = max(0.0, self.temp - 260 * dt)
            self.output = 0.0
            return
        self.temp += (self._heat * self.gain() - self.temp) * min(1.0, 0.6 * dt)
        self.temp = round(self.temp, 2)
        self.max_temp = max(self.max_temp, self.temp)
        self.rod = max(0.0, self.rod - self._heat * dt / 72)
        if self.temp >= 950:
            self.overheated = True
            self.output = 0.0
            return
        if self.temp <= 300:
            frac = 0.0
        elif self.temp <= 900:
            frac = (self.temp - 300) / 600
        else:
            frac = (950 - self.temp) / 50
        self.output = 5000 * frac


class ReactorTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.clock = _SimClock()
        self.world.services["clock"] = self.clock
        fluid_routing._WATER_RESERVE_MEMO.update({"tick": None, "hold": False})
        self.notified = []
        self._orig_notify = rx._notify
        rx._notify = lambda text, **_kw: self.notified.append(text)

    def tearDown(self):
        rx._notify = self._orig_notify
        fluid_routing._WATER_RESERVE_MEMO.update({"tick": None, "hold": False})
        super().tearDown()

    def make(self, conditions, staged=3):
        machine = _SimReactor(self.world, self.clock, self.world.home, conditions, staged)
        controller = rx.ReactorController(machine)
        controller.ensure_water = lambda: None
        return machine, controller

    def run_hours(self, machine, controller, hours):
        """Runs controller polls and per-tick physics; returns the mean output (W)."""
        end = self.clock.hours + hours
        energy = 0.0
        while self.clock.hours < end:
            wait_gh = controller.step()
            ticks = max(1, int(round(wait_gh / TICK_GH)))
            for _ in range(ticks):
                machine.step(TICK_GH)
                energy += machine.output * TICK_GH
                self.clock.hours += TICK_GH
                self.clock.now += 1
        return energy / hours

    def test_steady_state_formula(self):
        decay = math.exp(-rx.LAG_PER_GH * 0.1)
        t1 = 900 + (300 - 900) * decay
        self.assertAlmostEqual(rx.steady_state(300, t1, 0.1), 900, places=6)
        self.assertIsNone(rx.steady_state(300, t1, rx.MIN_SAMPLE_GH / 2))

    def test_safe_heat_holds_below_target_at_max_gain(self):
        self.assertLessEqual(rx.SAFE_HEAT * rx.GAIN_MAX_C, rx.TARGET_C + 1e-9)

    def test_warms_up_and_holds_near_target(self):
        machine, controller = self.make([1.0])
        self.run_hours(machine, controller, 8)
        mean = self.run_hours(machine, controller, 3)
        self.assertLess(abs(machine.temp - rx.TARGET_C), 10, self.debug_log())
        self.assertGreater(mean, 4700)
        self.assertAlmostEqual(controller.gain, 1200, delta=15)

    def test_condition_changes_never_overheat(self):
        # Low to high gain is the dangerous jump: heat ~1.0 then gain 1500.
        machine, controller = self.make([0.72, 1.25, 0.8, 1.2, 0.7, 1.25])
        self.run_hours(machine, controller, 72)
        self.assertFalse(machine.overheated)
        self.assertLess(machine.max_temp, rx.TRIP_C + 10, self.debug_log())
        self.assertNotIn("overheated", self.debug_log())

    def test_trip_guard_catches_unannounced_gain_jump(self):
        machine, controller = self.make([0.72])
        self.run_hours(machine, controller, 10)
        machine.conditions = [1.25]  # mid-window, no boundary to prepare for
        self.run_hours(machine, controller, 6)
        self.assertLess(machine.max_temp, 950)
        self.assertFalse(machine.overheated)
        self.assertLess(abs(machine.temp - rx.TARGET_C), 10)

    def test_low_gain_runs_full_heat(self):
        machine, controller = self.make([0.7])
        self.run_hours(machine, controller, 10)
        self.assertAlmostEqual(machine.heat(), 1.0, places=3)
        self.assertAlmostEqual(machine.temp, 840, delta=5)

    def test_loads_rods_from_local_cask(self):
        _Cask(self.world, "lead_cask_1", self.world.home, "fuel_rod", 5)
        machine, controller = self.make([1.0], staged=0)
        controller.step()
        self.assertEqual(machine.input.staged, rx.ROD_STAGE)
        self.assertEqual(self.world.components["lead_cask_1"].units, 5 - rx.ROD_STAGE)

    def test_warns_once_without_rods(self):
        machine, controller = self.make([1.0], staged=0)
        controller.ensure_rods(force=True)
        controller.ensure_rods(force=True)
        self.assertEqual(self.debug_log().count("holds any"), 1)


    # -- water reservation --
    def publish(self, controller):
        controller.reserve_tick = None
        controller.publish_water_reserve()
        return fluid_routing.archive.get(fluid_routing.WATER_RESERVE_KEY)

    def test_reserve_holds_below_floor_with_hysteresis(self):
        tank = _Tank(self.world, "tank_a", self.world.home, 40.0, capacity=200.0)
        _, controller = self.make([1.0])
        entry = self.publish(controller)
        self.assertTrue(entry["hold"])
        self.assertEqual(len(self.notified), 1)
        self.assertEqual(entry["floor_t"], rx.WATER_RESERVE_HOURS * rx.COOLANT_MAX_T_PER_GH)
        tank.tons = 55.0  # above floor, under the release line
        self.assertTrue(self.publish(controller)["hold"])
        tank.tons = 61.0
        self.assertFalse(self.publish(controller)["hold"])

    def test_reserve_floor_capped_by_tank_capacity(self):
        _Tank(self.world, "tank_a", self.world.home, 35.0, capacity=80.0)
        _, controller = self.make([1.0])
        entry = self.publish(controller)
        self.assertEqual(entry["floor_t"], 80.0 * rx.WATER_RESERVE_MAX_FRACTION)
        self.assertTrue(entry["hold"])

    def test_no_water_tank_never_holds(self):
        _, controller = self.make([1.0])
        self.assertFalse(self.publish(controller)["hold"])

    def test_only_lowest_id_reactor_publishes(self):
        _Tank(self.world, "tank_a", self.world.home, 10.0)
        _, controller = self.make([1.0])
        controller.name = "reactor_2"
        controller.reserve_tick = None
        controller.publish_water_reserve()
        self.assertIsNone(fluid_routing.archive.get(fluid_routing.WATER_RESERVE_KEY))

    def _router(self, reserve_fluid):
        return fluid_routing.FluidInputRouter(discover=lambda: [], rescan_interval_ticks=150,
                                              discovery_cache_interval_ticks=100, neutral_grace_steps=5,
                                              stall_streak_threshold=5, label="t", reserve_fluid=reserve_fluid)

    def test_router_yields_water_port_while_held(self):
        fluid_routing.archive.set(fluid_routing.WATER_RESERVE_KEY, {"hold": True, "tick": self.clock.now})
        port = _WaterPort()
        self.assertEqual(self._router("water").ensure(port, self.clock.now).kind, "reserved")
        self.assertEqual(port.disconnects, 1)
        other = _WaterPort()
        self.assertNotEqual(self._router(None).ensure(other, self.clock.now + 1).kind, "reserved")
        self.assertEqual(other.disconnects, 0)

    def test_stale_reserve_entry_does_not_hold(self):
        fluid_routing.archive.set(fluid_routing.WATER_RESERVE_KEY, {"hold": True, "tick": self.clock.now})
        later = self.clock.now + fluid_routing.WATER_RESERVE_FRESH_TICKS
        self.assertFalse(fluid_routing.water_reserve_holds(later))
        self.assertTrue(fluid_routing.water_reserve_holds(self.clock.now + 1))


if __name__ == "__main__":
    unittest.main()
