import unittest

from harness import StubTestCase
from game_stubs import Building, FluidPort, Slot
import script_restart
import terraforming
from script_restart import RESTART_REQUESTS_KEY, MAX_RESTARTS, request_restart, clear_restart, gave_up_ids, process_restart_requests
from steam_condenser import SteamCondenserController, WATER_TANK_STOP_FRACTION
from tree_console import TreeConsole

REASON = terraforming.MK3_PORT_RESTART_REASON


class _Generator(Building):
    """Terraforming generator whose upgrade ports exist only when a test sets them,
    like the game's `self`, which binds them at script start."""

    def __init__(self, world, building_id, outpost, tier=3):
        super().__init__(world, building_id, outpost)
        self._tier = tier
        self.water_in: FluidPort | None = None
        self.input: Slot | None = None

    def tier(self):
        return self._tier

    def is_degraded(self):
        return False


class RestartRequestTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.add_building("o2gen_1", self.world.home, "oxygen_generator")
        self.run_control = self.world.run_control
        self.run_control.running.add("o2gen_1")

    def entry(self, machine_id="o2gen_1"):
        return self.world.notebook.data.get(RESTART_REQUESTS_KEY, {}).get(machine_id) or {}

    def test_request_is_restarted_and_counted(self):
        self.assertEqual(request_restart("o2gen_1", REASON, 10), script_restart.STATE_REQUESTED)
        restarted, refused = process_restart_requests(self.run_control, 20)
        self.assertEqual((restarted, refused), (["o2gen_1"], {}))
        self.assertIn("o2gen_1", self.run_control.running)
        self.assertEqual((self.entry()["state"], self.entry()["restarts"]), (script_restart.STATE_RESTARTED, 1))
        # A restarted entry is not restarted again until the script asks again.
        self.assertEqual(process_restart_requests(self.run_control, 30), ([], {}))

    def test_gives_up_after_max_restarts(self):
        for attempt in range(MAX_RESTARTS):
            request_restart("o2gen_1", REASON, attempt)
            process_restart_requests(self.run_control, attempt)
        self.assertEqual(request_restart("o2gen_1", REASON, 99), script_restart.STATE_GAVE_UP)
        self.assertEqual(process_restart_requests(self.run_control, 100), ([], {}))
        self.assertEqual(self.entry()["restarts"], MAX_RESTARTS)
        self.assertEqual(gave_up_ids(), ["o2gen_1"])

    def test_new_reason_starts_from_zero(self):
        for attempt in range(MAX_RESTARTS):
            request_restart("o2gen_1", REASON, attempt)
            process_restart_requests(self.run_control, attempt)
        other = terraforming.MK4_INPUT_RESTART_REASON
        self.assertEqual(request_restart("o2gen_1", other, 50), script_restart.STATE_REQUESTED)
        self.assertEqual(self.entry()["restarts"], 0)

    def test_clear_only_drops_own_reason(self):
        request_restart("o2gen_1", REASON, 10)
        self.assertIsNone(clear_restart("o2gen_1", terraforming.MK4_INPUT_RESTART_REASON))
        self.assertTrue(self.entry())
        self.assertEqual((clear_restart("o2gen_1", REASON) or {}).get("reason"), REASON)
        self.assertFalse(self.entry())

    def test_refused_start_keeps_request(self):
        request_restart("gone_1", REASON, 10)
        restarted, refused = process_restart_requests(self.run_control, 20)
        self.assertEqual((restarted, refused), ([], {"gone_1": "not_found"}))
        self.assertEqual(self.entry("gone_1")["state"], script_restart.STATE_REQUESTED)


class UnboundPortTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.log = TreeConsole(module="terraforming")
        self.machine = self.world.add_building("o2gen_1", self.world.home, "oxygen_generator", cls=_Generator)

    def entry(self):
        return self.world.notebook.data.get(RESTART_REQUESTS_KEY, {}).get("o2gen_1") or {}

    def step(self, feed):
        self.world.clock.now += terraforming.FLUID_CHECK_INTERVAL_TICKS
        feed.step()

    def test_missing_mk3_port_requests_once_per_run(self):
        feed = terraforming.Mk3FluidFeed(self.machine, "water_in", "o2gen_1", self.log)
        self.step(feed)
        self.assertEqual(self.entry()["state"], script_restart.STATE_REQUESTED)
        process_restart_requests(self.world.run_control, self.world.clock.now)
        self.step(feed)
        # Same run: no second request on top of the restart already done.
        self.assertEqual(self.entry()["state"], script_restart.STATE_RESTARTED)

    def test_bound_port_clears_request(self):
        request_restart("o2gen_1", REASON, 0)
        process_restart_requests(self.world.run_control, 0)
        self.machine.water_in = FluidPort(self.world, 0.0, 5.0)
        feed = terraforming.Mk3FluidFeed(self.machine, "water_in", "o2gen_1", self.log)
        self.step(feed)
        self.assertFalse(self.entry())

    def test_missing_mk4_input_requests_restart(self):
        self.machine._tier = 4
        terraforming.Mk4RodFeed(self.machine, "o2gen_1", self.log).step()
        self.assertEqual(self.entry()["reason"], terraforming.MK4_INPUT_RESTART_REASON)

    def test_bound_mk4_input_clears_only_mk4_request(self):
        self.machine._tier = 4
        self.machine.input = Slot(self.machine, self.machine.input_buffer, 4)
        request_restart("o2gen_1", REASON, 0)
        terraforming.Mk4RodFeed(self.machine, "o2gen_1", self.log).step()
        self.assertEqual(self.entry()["reason"], REASON)


class _Condenser(Building):
    def __init__(self, world, building_id, outpost):
        super().__init__(world, building_id, outpost)
        self.steam_in = FluidPort(world, 250.0, 250.0)
        self.water_out = FluidPort(world, 0.0, 250.0)


class CondenserWaterGateTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.tanks = [w.add_tank(f"liquid_tank_{i}", w.home, "water", 0.0, capacity=1000.0) for i in (1, 2, 3)]
        w.notebook.data["fluid_routing.tank_assignments"] = {t.id: "water" for t in self.tanks}
        condenser = w.add_building("steam_condenser_1", w.home, "steam_condenser", cls=_Condenser)
        self.controller = SteamCondenserController(condenser)

    def fill(self, *levels):
        for tank, level in zip(self.tanks, levels):
            tank._level = level
        self.world.clock.now += 1000  # past the discovery cache
        self.controller.update_water_gate()

    def test_closes_only_when_every_tank_is_full(self):
        stop = WATER_TANK_STOP_FRACTION * 1000
        self.fill(stop, stop, stop - 10)
        self.assertTrue(self.controller.water_gate_open)
        self.fill(stop, stop, stop)
        self.assertFalse(self.controller.water_gate_open)

    def test_reopens_when_one_tank_runs_dry_though_the_pool_is_half_full(self):
        self.fill(1000, 1000, 1000)
        self.assertFalse(self.controller.water_gate_open)
        # Pooled 50.3 % kept the gate closed; the drained tank opens it.
        self.fill(640, 0, 870)
        self.assertTrue(self.controller.water_gate_open)

    def test_stays_closed_above_start_line(self):
        self.fill(1000, 1000, 1000)
        self.fill(1000, 600, 1000)
        self.assertFalse(self.controller.water_gate_open)


if __name__ == "__main__":
    unittest.main()
