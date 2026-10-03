import unittest

from harness import StubTestCase
from game_stubs import Building, Result
import script_parking
import retired_machines
from script_parking import ParkRequester, ScriptParking, PARK_REQUESTS_KEY, PARKED_KEY, WAKE_AFTER_TICKS


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
        w = self.world
        self.power, self.run_control = w.power_control, w.run_control
        self.run_control.running.add("solar_1")
        machines = {"smelter_1": "smelter", "supply_dock_1": "supply_dock", "oil_generator_1": "oil_generator", "solar_1": "solar_generator"}
        for machine_id, type_id in machines.items():
            w.add_building(machine_id, w.home, type_id)
        self.grid = w.add_grid("grid_a", list(machines))
        self.grids = [self.grid]
        self.parking = ScriptParking(power=self.power, run_control=self.run_control)
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

    def test_machine_switched_on_by_hand_leaves_the_parked_list(self):
        self.request("smelter_1", "smelter")
        self.parking.step(self.grids, 10.0)
        self.power.powered["smelter_1"] = True  # player flips the breaker back on
        self.parking.step(self.grids, 10.0)
        self.assertNotIn("smelter_1", self.world.notebook.data[PARKED_KEY])
        self.assertEqual(self.power.calls, [("smelter_1", False)])

    def test_stale_request_and_shed_machine_are_not_parked(self):
        self.request("smelter_1", "smelter")
        self.world.clock.now += script_parking.REQUEST_FRESH_TICKS + 1
        self.parking.step(self.grids, 10.0)
        self.request("supply_dock_1", "supply_dock")
        self.world.notebook.data["power.shedded"] = ["supply_dock_1"]
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls, [])

    def test_untracked_dark_machine_with_stale_request_is_adopted_and_woken(self):
        self.request("smelter_1", "smelter")
        self.power.powered["smelter_1"] = False  # parked by a pass whose record was lost
        self.world.clock.now += WAKE_AFTER_TICKS["smelter"]
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls, [])
        self.assertEqual(self.world.notebook.data[PARKED_KEY]["smelter_1"]["mode"], "breaker")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls, [("smelter_1", True)])
        self.assertNotIn("smelter_1", self.world.notebook.data[PARKED_KEY])

    def test_dark_machine_without_request_or_shed_is_not_adopted(self):
        self.power.powered["smelter_1"] = False
        self.request("supply_dock_1", "supply_dock")
        self.power.powered["supply_dock_1"] = False
        self.world.notebook.data["power.shedded"] = ["supply_dock_1"]
        self.world.clock.now += script_parking.REQUEST_FRESH_TICKS + 1
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.world.notebook.data.get(PARKED_KEY, {}), {})

    def test_park_is_recorded_before_the_breaker_and_dropped_when_it_fails(self):
        seen = []
        set_powered = self.power.set_powered

        def recording(machine_id, on):
            seen.append(machine_id in self.world.notebook.data.get(PARKED_KEY, {}))
            return set_powered(machine_id, on) if machine_id != "supply_dock_1" else Result("failed")
        self.power.set_powered = recording
        self.request("smelter_1", "smelter")
        self.request("supply_dock_1", "supply_dock")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(seen, [True, True])
        self.assertIn("smelter_1", self.world.notebook.data[PARKED_KEY])
        self.assertNotIn("supply_dock_1", self.world.notebook.data[PARKED_KEY])

    def test_entries_written_by_others_during_a_pass_survive(self):
        self.request("smelter_1", "smelter")
        set_powered = self.power.set_powered

        def turbine_writes_meanwhile(machine_id, on):
            self.world.notebook.data.setdefault(PARKED_KEY, {})["turbine_1"] = {"kind": "steam_turbine", "mode": "turbine", "since": 0}
            return set_powered(machine_id, on)
        self.power.set_powered = turbine_writes_meanwhile
        self.world.clock.now += 1
        self.parking.step(self.grids, 10.0)
        self.assertIn("turbine_1", self.world.notebook.data[PARKED_KEY])
        self.assertIn("smelter_1", self.world.notebook.data[PARKED_KEY])

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
        self.assertEqual(self.power.calls[-1], ("oil_generator_1", False))  # the 0.5 verdict is still cached
        self.world.clock.now += script_parking.RESERVE_CACHE_TICKS
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("oil_generator_1", True))
        self.request("oil_generator_1", "oil_generator")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("oil_generator_1", True))

    def _recheck_cycle(self, idle_ticks):
        """Wakes smelter_1 on its timed re-check, lets it idle for idle_ticks, then files its next park request."""
        entry = self.world.notebook.data[PARKED_KEY]["smelter_1"]
        self.world.clock.now += entry.get("wake_after", WAKE_AFTER_TICKS["smelter"])
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("smelter_1", True))
        self.world.clock.now += idle_ticks
        self.request("smelter_1", "smelter")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("smelter_1", False))
        return self.world.notebook.data[PARKED_KEY]["smelter_1"]

    def test_fruitless_rechecks_back_off_up_to_the_cap_and_work_resets_it(self):
        self.request("smelter_1", "smelter")
        self.parking.step(self.grids, 10.0)
        base = WAKE_AFTER_TICKS["smelter"]
        cap = script_parking.WAKE_BACKOFF_MAX_TICKS["smelter"]
        self.assertNotIn("wake_after", self.world.notebook.data[PARKED_KEY]["smelter_1"])
        self.assertEqual(self._recheck_cycle(50)["wake_after"], min(base * 2, cap))
        self.assertEqual(self._recheck_cycle(50)["wake_after"], min(base * 4, cap))
        self.assertEqual(self._recheck_cycle(50)["wake_after"], cap)
        # It worked after this wake (parked again later than the window): back to the default.
        self.assertNotIn("wake_after", self._recheck_cycle(script_parking.FRUITLESS_REPARK_TICKS + 50))
        self.assertEqual(self._recheck_cycle(50)["wake_after"], min(base * 2, cap))

    def test_event_wake_does_not_start_a_backoff(self):
        self.request("supply_dock_1", "supply_dock")
        self.parking.step(self.grids, 10.0, {"supply_dock_1": None})
        self.parking.step(self.grids, 10.0, {"supply_dock_1": "order_7"})
        self.world.clock.now += 50
        self.request("supply_dock_1", "supply_dock")
        self.parking.step(self.grids, 10.0, {"supply_dock_1": None})
        self.assertNotIn("wake_after", self.world.notebook.data[PARKED_KEY]["supply_dock_1"])

    def test_machine_filed_wake_time_is_used(self):
        requests = self.world.notebook.data.setdefault(PARK_REQUESTS_KEY, {})
        requests["smelter_1"] = {"kind": "smelter", "tick": self.world.clock.now, "wake_after": 40}
        self.parking.step(self.grids, 10.0)
        self.world.clock.now += 39
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls, [("smelter_1", False)])
        self.world.clock.now += 1
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("smelter_1", True))

    def test_oil_pump_wakes_when_its_well_turns_active(self):
        class _Pump(Building):
            active = False

            def well_active(self):
                return self.active

        pump = self.world.add_building("oil_pump_1", self.world.home, "oil_pump", _Pump)
        self.grid.machine_ids.append("oil_pump_1")
        self.request("oil_pump_1", "oil_pump")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls, [("oil_pump_1", False)])
        self.parking.step(self.grids, 10.0)
        self.assertEqual(len(self.power.calls), 1)
        pump.active = True
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("oil_pump_1", True))

    def test_exotic_cap_wakes_when_its_deposit_turns_active(self):
        class _Deposit:
            phase = "dormant"

            def current_phase(self):
                return self.phase

        class _Cap(Building):
            site = _Deposit()

            def deposit(self):
                return self.site

        cap = self.world.add_building("exotic_gas_cap_1", self.world.home, "exotic_gas_cap", _Cap)
        self.grid.machine_ids.append("exotic_gas_cap_1")
        self.request("exotic_gas_cap_1", "exotic_cap")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls, [("exotic_gas_cap_1", False)])
        self.parking.step(self.grids, 10.0)
        self.assertEqual(len(self.power.calls), 1)
        cap.site.phase = "active"
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("exotic_gas_cap_1", True))

    def test_solar_stopped_at_night_and_started_at_sunrise(self):
        self.parking.step(self.grids, -3.0)
        self.assertNotIn("solar_1", self.run_control.running)
        self.assertEqual(self.world.notebook.data[PARKED_KEY]["solar_1"]["mode"], "stopped")
        self.parking.step(self.grids, 2.0)
        self.assertIn("solar_1", self.run_control.running)
        self.assertNotIn("solar_1", self.world.notebook.data[PARKED_KEY])

    def test_solar_script_stopped_by_the_player_is_not_started(self):
        self.run_control.running.clear()
        self.parking.step(self.grids, -3.0)
        self.parking.step(self.grids, 2.0)
        self.assertNotIn("solar_1", self.run_control.running)


class DemandWakeTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.power = w.power_control
        machines = {"fabricator_1": "fabricator", "smelter_1": "smelter"}
        for machine_id, type_id in machines.items():
            w.add_building(machine_id, w.home, type_id)
        self.grids = [w.add_grid("grid_a", list(machines))]
        self.parking = ScriptParking(power=self.power, run_control=w.run_control)
        self.data = w.notebook.data
        self.data[PARK_REQUESTS_KEY] = {m: {"kind": t, "tick": w.clock.now} for m, t in machines.items()}
        self.parking.step(self.grids, 10.0, {})  # records the first signature and parks both
        self.assertEqual(sorted(self.data[PARKED_KEY]), ["fabricator_1", "smelter_1"])
        self.power.calls.clear()

    def step(self, dock_plan=None):
        self.world.clock.now += 50
        self.parking.step(self.grids, 10.0, dock_plan or {})

    def test_new_manual_order_wakes_only_the_fabricator(self):
        self.data["fabricator.manual_orders"] = {"drone_small": 2}
        self.step()
        self.assertEqual(self.power.calls, [("fabricator_1", True)])

    def test_rising_amount_wakes_and_a_decrease_does_not(self):
        self.data["fabricator.stock_targets"] = {"gear": 10}
        self.step()
        self.power.calls.clear()
        self.data[PARK_REQUESTS_KEY]["fabricator_1"] = {"kind": "fabricator", "tick": self.world.clock.now}
        self.step()
        self.assertEqual(self.power.calls, [("fabricator_1", False)])
        self.data["fabricator.stock_targets"] = {"gear": 5}
        self.step()
        self.assertEqual(self.power.calls[1:], [])
        self.data["fabricator.stock_targets"] = {"gear": 6}
        self.step()
        self.assertEqual(self.power.calls[-1], ("fabricator_1", True))

    def test_unchanged_demand_wakes_nothing(self):
        self.data["fabricator.manual_orders"] = {"drone_small": 2}
        self.data["production.ingot_stock_targets"] = {"iron_ingot": {"target": 100, "need": 10}}
        self.step({"supply_dock_1": "order_7"})
        self.assertEqual(len(self.power.calls), 2)
        self.power.calls.clear()
        self.data[PARK_REQUESTS_KEY] = {m: {"kind": m.split("_")[0], "tick": self.world.clock.now} for m in ("fabricator_1", "smelter_1")}
        self.step({"supply_dock_1": "order_7"})
        self.assertEqual(sorted(self.power.calls), [("fabricator_1", False), ("smelter_1", False)])
        self.power.calls.clear()
        self.step({"supply_dock_1": "order_7"})
        self.step({"supply_dock_1": "order_7"})
        self.assertEqual(self.power.calls, [])

    def test_new_dock_order_wakes_the_smelter(self):
        self.step({"supply_dock_1": "order_7"})
        self.assertIn(("smelter_1", True), self.power.calls)

    def test_ingot_target_wakes_only_the_smelter(self):
        self.data["production.ingot_stock_targets"] = {"iron_ingot": {"target": 100, "need": 10}}
        self.step()
        self.assertEqual(self.power.calls, [("smelter_1", True)])

    def test_demand_decrease_wakes_nothing(self):
        self.data["fabricator.manual_orders"] = {"drone_small": 2}
        self.step()
        self.power.calls.clear()
        self.data["fabricator.manual_orders"] = {}
        self.step()
        self.assertEqual(self.power.calls, [])

    def test_demand_wake_resets_the_recheck_backoff(self):
        self.parking._rechecks["smelter_1"] = (self.world.clock.now, 2)
        self.data["production.ingot_stock_targets"] = {"iron_ingot": {"target": 100, "need": 10}}
        self.step()
        self.assertEqual(self.power.calls, [("smelter_1", True)])
        self.assertNotIn("smelter_1", self.parking._rechecks)
        self.world.clock.now += 50
        self.data[PARK_REQUESTS_KEY]["smelter_1"] = {"kind": "smelter", "tick": self.world.clock.now}
        self.parking.step(self.grids, 10.0, {})
        self.assertNotIn("wake_after", self.data[PARKED_KEY]["smelter_1"])


class StationParkingTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.power = w.power_control
        for machine_id in ("charging_station_1", "charging_station_2"):
            w.add_building(machine_id, w.home, "charging_station")
        self.grid = w.add_grid("grid_a", ["charging_station_1", "charging_station_2"])
        self.grids = [self.grid]
        self.parking = ScriptParking(power=self.power, run_control=w.run_control)

    def request(self, machine_id):
        requests = self.world.notebook.data.setdefault(PARK_REQUESTS_KEY, {})
        requests[machine_id] = {"kind": "charging_station", "tick": self.world.clock.now}

    def test_last_awake_station_never_parks(self):
        self.request("charging_station_1")
        self.request("charging_station_2")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(len([c for c in self.power.calls if c[1] is False]), 1)
        self.request("charging_station_1")
        self.request("charging_station_2")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(len([c for c in self.power.calls if c[1] is False]), 1)

    def test_visit_wakes_parked_station_and_holds_it(self):
        self.request("charging_station_1")
        self.parking.step(self.grids, 10.0)
        self.assertIn("charging_station_1", script_parking.parked_ids("charging_station"))
        self.assertTrue(script_parking.wake_for_visit("charging_station_1", "test"))
        self.assertEqual(self.power.calls[-1], ("charging_station_1", True))
        self.assertNotIn("charging_station_1", script_parking.parked_ids())
        self.request("charging_station_1")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("charging_station_1", True))  # held: not parked again
        self.world.clock.now += script_parking.STATION_HOLD_TICKS
        self.request("charging_station_1")
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("charging_station_1", False))

    def test_visit_wake_clears_the_pre_park_request(self):
        self.request("charging_station_1")
        self.parking.step(self.grids, 10.0)
        self.world.clock.now += 1
        self.assertTrue(script_parking.wake_for_visit("charging_station_1", "test", hold=False))
        self.assertNotIn("charging_station_1", self.world.notebook.data[PARK_REQUESTS_KEY])
        self.assertNotIn("charging_station_1", self.world.notebook.data.get(script_parking.HOLDS_KEY, {}))

    def test_visit_to_awake_station_only_holds(self):
        self.assertFalse(script_parking.wake_for_visit("charging_station_2", "test"))
        self.assertEqual(self.power.calls, [])
        self.assertGreater(self.world.notebook.data[script_parking.HOLDS_KEY]["charging_station_2"], self.world.clock.now)

    def test_only_depot_parks_and_a_visit_hold_keeps_it_up(self):
        self.world.add_building("drone_station_1", self.world.home, "drone_station")
        self.grid.machine_ids.append("drone_station_1")
        requests = self.world.notebook.data.setdefault(PARK_REQUESTS_KEY, {})
        requests["drone_station_1"] = {"kind": "drone_depot", "tick": self.world.clock.now}
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls, [("drone_station_1", False)])  # no last-awake rule for depots
        self.assertTrue(script_parking.wake_for_visit("drone_station_1", "test"))
        requests = self.world.notebook.data.setdefault(PARK_REQUESTS_KEY, {})
        requests["drone_station_1"] = {"kind": "drone_depot", "tick": self.world.clock.now}
        self.parking.step(self.grids, 10.0)
        self.assertEqual(self.power.calls[-1], ("drone_station_1", True))

    def test_parked_nearest_hands_over_only_to_a_nearer_parked_station(self):
        class Ref:
            x, y = 0.0, 0.0
        refs = [{"id": "near", "coords": (10.0, 0.0)}, {"id": "far", "coords": (100.0, 0.0)}]
        self.assertEqual(script_parking.parked_nearest(Ref(), refs, {"near"}, 100.0), "near")
        self.assertIsNone(script_parking.parked_nearest(Ref(), refs, {"far"}, 10.0))
        self.assertIsNone(script_parking.parked_nearest(Ref(), refs, set(), 10.0))


class FieldProviderParkingTests(StubTestCase):
    def test_wake_kind_switches_on_every_parked_provider(self):
        for type_id in ("grow_lamp", "sprinkler"):
            self.world.add_building(f"{type_id}_1", self.world.home, type_id)
        self.world.notebook.data[PARKED_KEY] = {
            "grow_lamp_1": {"kind": "field_provider", "mode": "breaker", "since": 0},
            "sprinkler_1": {"kind": "field_provider", "mode": "breaker", "since": 0},
            "smelter_1": {"kind": "smelter", "mode": "breaker", "since": 0},
        }
        self.assertEqual(script_parking.wake_kind("field_provider", "test"), ["grow_lamp_1", "sprinkler_1"])
        self.assertEqual(set(self.world.notebook.data[PARKED_KEY]), {"smelter_1"})
        self.assertEqual(script_parking.wake_kind("field_provider", "test"), [])

    def test_switched_off_provider_asks_to_park_and_a_needed_one_does_not(self):
        import field_provider

        class Lamp:
            id = "grow_lamp_1"
            enabled = True

            def position(self):
                return "B2"

            def is_enabled(self):
                return self.enabled

            def set_enabled(self, on):
                self.enabled = on
                return Result("ok")

            def status(self):
                return "active" if self.enabled else "disabled"

            def buffer(self):
                return 0.0

        self.world.notebook.data["plant.recipes"] = {}  # fallback rules: sunpetal needs light, dewmoss water
        lamp = Lamp()
        controller = field_provider.FieldProviderController(lamp, "grow_lamp")
        self.world.notebook.data["plant.layout"] = {"mode": "starter", "cells": {"B3": "dewmoss"}}
        for _ in range(script_parking.PARK_AFTER_IDLE_STEPS):
            controller.step()
        self.assertFalse(lamp.enabled)
        self.assertIn("grow_lamp_1", self.world.notebook.data[PARK_REQUESTS_KEY])
        self.world.notebook.data["plant.layout"] = {"mode": "starter", "cells": {"B3": "sunpetal"}}
        controller.step()
        self.assertTrue(lamp.enabled)
        self.assertNotIn("grow_lamp_1", self.world.notebook.data[PARK_REQUESTS_KEY])


class StrayDarkTests(StubTestCase):
    """Breakers switched off with no owner: warn, then notify + alert, then switched on."""

    def setUp(self):
        super().setUp()
        w = self.world
        self.power, self.run_control = w.power_control, w.run_control
        for machine_id in ("smelter_1", "smelter_2"):
            w.add_building(machine_id, w.home, "smelter")
        self.grids = [w.add_grid("grid_a", ["smelter_1", "smelter_2"])]
        self.parking = ScriptParking(power=self.power, run_control=self.run_control)
        self.power.powered["smelter_1"] = False

    def step_at(self, age):
        self.world.clock.now = self.start + age
        self.parking.step(self.grids, 10.0)

    def strays(self):
        return self.world.notebook.data.get(script_parking.STRAY_KEY, {})

    def test_three_stages(self):
        self.start = self.world.clock.now
        self.step_at(0)
        self.assertEqual(self.strays()["smelter_1"]["stage"], 1)
        self.assertEqual(self.world.notices, [])
        self.assertEqual(script_parking.stray_alerts(), [])
        self.step_at(script_parking.STRAY_NOTIFY_TICKS)
        self.assertEqual(self.strays()["smelter_1"]["stage"], 2)
        self.assertEqual(len(self.world.notices), 1)
        self.assertIn("smelter_1", script_parking.stray_alerts()[0][0])
        self.step_at(script_parking.STRAY_NOTIFY_TICKS + 50)
        self.assertEqual(len(self.world.notices), 1)  # notified once
        self.assertEqual(self.power.calls, [])
        self.step_at(script_parking.STRAY_SWITCH_ON_TICKS)
        self.assertEqual(self.power.calls, [("smelter_1", True)])
        self.assertIn("smelter_1", self.run_control.running)
        self.assertEqual(self.strays(), {})

    def test_errored_script_is_not_restarted(self):
        self.run_control.states["smelter_1"] = "error"
        self.start = self.world.clock.now
        self.step_at(0)
        self.step_at(script_parking.STRAY_SWITCH_ON_TICKS)
        self.assertEqual(self.power.calls, [("smelter_1", True)])
        self.assertNotIn("smelter_1", self.run_control.running)

    def test_switched_on_by_hand_is_forgotten(self):
        self.start = self.world.clock.now
        self.step_at(0)
        self.power.powered["smelter_1"] = True
        self.step_at(50)
        self.assertEqual(self.strays(), {})

    def test_owned_dark_machines_are_not_stray(self):
        self.world.notebook.data[script_parking.MANUAL_OFF_KEY] = {"smelter_1": "kept off for testing"}
        self.power.powered["smelter_2"] = False
        retired_machines.retire(["smelter_2"], "test")
        self.start = self.world.clock.now
        self.step_at(0)
        self.step_at(script_parking.STRAY_SWITCH_ON_TICKS)
        self.assertEqual(self.strays(), {})
        self.assertEqual(self.power.calls, [])

    def test_shed_or_otherwise_parked_machines_are_not_stray(self):
        self.world.notebook.data["power.shedded"] = ["smelter_1"]
        self.power.powered["smelter_2"] = False
        self.world.notebook.data[PARKED_KEY] = {"smelter_2": {"kind": "biomass_mixer", "mode": "mixer_gate", "since": 0}}
        self.start = self.world.clock.now
        self.step_at(0)
        self.step_at(script_parking.STRAY_SWITCH_ON_TICKS)
        self.assertEqual(self.strays(), {})
        self.assertEqual(self.power.calls, [])


if __name__ == "__main__":
    unittest.main()
