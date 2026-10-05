"""Fuel Assembler (lib/fuel_assembler.py), Lead Cask roles (lib/lead_cask.py),
the Mk IV rod feed (lib/terraforming.py) and the hot-cargo hooks in production/supply_dock."""
import unittest

import harness
from game_stubs import Building, Machine, Recipe, Slot
import fuel_assembler as fa
import lead_cask
import production
import supply_dock
import terraforming


def _recipe(recipe_id):
    spec = fa.FALLBACK_RECIPES[recipe_id]
    return Recipe(recipe_id, spec["inputs"], spec["output"])


class _Consumer(Building):
    """Reactor or a terraformer with a Fuel Rod magazine."""

    def __init__(self, world, machine_id, type_id, outpost, tier=4, staged=0):
        super().__init__(world, machine_id, outpost)
        self.type_id = type_id
        self._tier = tier
        if staged:
            self.input_buffer["fuel_rod"] = staged
        self.input = Slot(self, self.input_buffer, 4)
        world.components[machine_id] = self

    def tier(self):
        return self._tier


class _Assembler(Machine):
    """Fuel Assembler that records its recipe calls; the test sets `running`
    and the finished products in `output_buffer`."""
    type_id = "fuel_assembler"

    def __init__(self, world, outpost, recipe="", running=False):
        super().__init__(world, "fuel_assembler_1", outpost, [_recipe(fa.ROD_RECIPE), _recipe(fa.BATTERY_RECIPE)])
        self.input = Slot(self, self.input_buffer, 200)
        self.output = Slot(self, self.output_buffer, 50)
        self.recipe = recipe
        self.running = running
        self.calls = []
        world.components[self.id] = self

    def get_progress(self):
        return 0.5 if self.running else 0.0

    def get_stockpile(self):
        return {k: v for k, v in self.input_buffer.items() if v > 0}

    def set_recipe(self, recipe_or_id):
        self.calls.append(("set_recipe", recipe_or_id))
        return super().set_recipe(recipe_or_id)

    def clear_recipe(self):
        self.calls.append(("clear_recipe",))
        return super().clear_recipe()


class _Power:
    """lib/power.py stand-in: measure_grid() returns the reserve the test set."""

    def __init__(self):
        self.fraction = 1.0

    def measure_grid(self, grid, tank_ids):
        return {"bat_wh": self.fraction * 1000.0, "bat_cap": 1000.0, "steam_t": 0.0, "steam_cap": 0.0, "tanks": 0}

    def grid_steam_tank_ids(self, grid):
        return []

    def reserve_fraction(self, now):
        return now["bat_wh"] / now["bat_cap"]


class _Base(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.add_grid("grid_a", ["fuel_assembler_1"])
        self.plates = {"lead_plate": 50}
        self.fake_power = _Power()
        self._orig = (fa.take_item, fa.takeable_stock, fa.drain_port_storage_first, fa.power)

        def fake_take(port, item_id, amount, outpost=None, cache=None, report=None):
            moved = min(amount, self.plates.get(item_id, 0))
            self.plates[item_id] = self.plates.get(item_id, 0) - moved
            port.buffer[item_id] = port.buffer.get(item_id, 0) + moved
            return moved

        fa.take_item = fake_take
        fa.takeable_stock = lambda item_id, outpost=None: self.plates.get(item_id, 0)
        fa.drain_port_storage_first = lambda port, outpost=None, include=None: 0
        fa.power = self.fake_power

    def tearDown(self):
        fa.take_item, fa.takeable_stock, fa.drain_port_storage_first, fa.power = self._orig
        super().tearDown()

    def casks(self, uranium=40, rods=None):
        """lead_cask_1 with uranium; lead_cask_2 empty, or holding `rods` rods."""
        u = self.world.add_lead_cask("lead_cask_1", self.world.home, "raw_uranium", uranium)
        r = self.world.add_lead_cask("lead_cask_2", self.world.home, "fuel_rod" if rods else "", rods or 0)
        return u, r

    def plate_order(self):
        return (self.world.notebook.data.get("fabricator.upgrade_orders") or {}).get(fa.PLATE_ORDER_REQUESTER)

    def roles(self):
        return self.world.notebook.data.get(lead_cask.ROLES_KEY) or {}


class FuelAssemblerTests(_Base):
    def test_crafts_rods_for_local_reactor(self):
        _Consumer(self.world, "reactor_1", "reactor", self.world.home)
        self.casks()
        maker = _Assembler(self.world, self.world.home)
        delay = fa.FuelAssemblerController(maker).step()
        self.assertEqual(delay, fa.ACTIVE_POLL_S)
        self.assertEqual(maker.recipe, fa.ROD_RECIPE)
        # target 1 reserve + 2 per reactor = 3 rods short; stages STAGED_CRAFTS crafts
        self.assertEqual(maker.input_buffer, {"raw_uranium": 8, "lead_plate": 4})
        self.assertEqual(self.plate_order(), {"lead_plate": 4})
        self.assertEqual(self.roles(), {"lead_cask_2": "fuel_rod"})

    def test_mk4_generators_count_in_rod_target(self):
        _Consumer(self.world, "heater_1", "temp_heater", self.world.home, tier=4, staged=1)
        _Consumer(self.world, "heater_2", "temp_heater", self.world.home, tier=3)
        self.casks(rods=1)
        maker = _Assembler(self.world, self.world.home)
        ctrl = fa.FuelAssemblerController(maker)
        # 1 reserve + 1 for the Mk IV heater; 1 in the cask + 1 in its magazine
        self.assertEqual(ctrl.shortfalls(lead_cask.casks_at(self.world.home), ctrl.recipes(0)), [])

    def test_rod_stock_met_clears_recipe_and_order(self):
        self.casks(rods=1)
        self.world.notebook.data["fabricator.upgrade_orders"] = {fa.PLATE_ORDER_REQUESTER: {"lead_plate": 4}}
        maker = _Assembler(self.world, self.world.home, recipe=fa.ROD_RECIPE)
        delay = fa.FuelAssemblerController(maker).step()
        self.assertEqual(delay, fa.IDLE_POLL_S)
        self.assertIn(("clear_recipe",), maker.calls)
        self.assertIsNone(self.plate_order())

    def test_rods_before_batteries(self):
        self.world.notebook.data["fabricator.manual_orders"] = {"nuclear_battery": 5}
        self.casks()
        maker = _Assembler(self.world, self.world.home)
        fa.FuelAssemblerController(maker).step()
        self.assertEqual(maker.recipe, fa.ROD_RECIPE)

    def test_batteries_once_rods_met(self):
        self.world.notebook.data["fabricator.manual_orders"] = {"nuclear_battery": 2}
        self.casks(rods=1)
        maker = _Assembler(self.world, self.world.home)
        fa.FuelAssemblerController(maker).step()
        self.assertEqual(maker.recipe, fa.BATTERY_RECIPE)
        self.assertEqual(maker.input_buffer, {"raw_uranium": 8, "lead_plate": 6})

    def test_single_cask_blocks_rods_not_batteries(self):
        self.world.notebook.data["fabricator.manual_orders"] = {"nuclear_battery": 1}
        self.world.add_lead_cask("lead_cask_1", self.world.home, "raw_uranium", 40)
        maker = _Assembler(self.world, self.world.home)
        fa.FuelAssemblerController(maker).step()
        self.assertEqual(maker.recipe, fa.BATTERY_RECIPE)
        self.assertIn("rods need their own cask", self.debug_log())

    def test_no_uranium_blocks(self):
        self.world.add_lead_cask("lead_cask_2", self.world.home)
        self.world.add_lead_cask("lead_cask_3", self.world.home)
        maker = _Assembler(self.world, self.world.home)
        delay = fa.FuelAssemblerController(maker).step()
        self.assertEqual(delay, fa.IDLE_POLL_S)
        self.assertEqual(maker.recipe, "")
        # Plates are still requested so they are ready when uranium arrives.
        self.assertEqual(self.plate_order(), {"lead_plate": 2})

    def test_low_reserve_stages_nothing(self):
        self.casks()
        self.fake_power.fraction = fa.START_RESERVE_FRACTION - 0.1
        maker = _Assembler(self.world, self.world.home)
        delay = fa.FuelAssemblerController(maker).step()
        self.assertEqual(delay, fa.ACTIVE_POLL_S)
        self.assertEqual(maker.input_buffer, {})

    def test_shed_starts_nothing(self):
        self.world.notebook.data["power.shedded"] = ["fuel_assembler_1"]
        self.casks()
        maker = _Assembler(self.world, self.world.home)
        fa.FuelAssemblerController(maker).step()
        self.assertEqual(maker.recipe, "")
        self.assertEqual(maker.input_buffer, {})

    def test_running_craft_not_switched(self):
        self.world.notebook.data["fabricator.manual_orders"] = {"nuclear_battery": 2}
        self.casks(rods=5)
        maker = _Assembler(self.world, self.world.home, recipe=fa.ROD_RECIPE, running=True)
        delay = fa.FuelAssemblerController(maker).step()
        self.assertEqual(delay, fa.ACTIVE_POLL_S)
        self.assertEqual(maker.recipe, fa.ROD_RECIPE)

    def test_rods_go_to_rod_cask_only(self):
        uranium, rod_cask = self.casks()
        maker = _Assembler(self.world, self.world.home)
        maker.output_buffer.update({"fuel_rod": 2})
        fa.FuelAssemblerController(maker).step()
        self.assertEqual(rod_cask.count("fuel_rod"), 2)
        self.assertEqual(uranium.count("fuel_rod"), 0)

    def test_rods_past_reactor_reserve_go_to_local_dock(self):
        _uranium, rod_cask = self.casks()
        _Consumer(self.world, "reactor_1", "reactor", self.world.home)  # reserve 1 + 2 = 3
        dock = self.world.add_supply_dock("supply_dock_1", self.world.home)
        dock.order = self.world.add_order("order_1", {"fuel_rod": 10})
        maker = _Assembler(self.world, self.world.home)
        maker.output_buffer.update({"fuel_rod": 5})
        fa.FuelAssemblerController(maker).drain_output("lead_cask_2")
        self.assertEqual(dock.count("fuel_rod"), 2)
        self.assertEqual(rod_cask.count("fuel_rod"), 3)

    def test_misfiled_uranium_moved_out_of_rod_cask(self):
        uranium, rod_cask = self.casks(uranium=30)
        self.world.notebook.data[lead_cask.ROLES_KEY] = {"lead_cask_2": "fuel_rod"}
        rod_cask.add("raw_uranium", 20)  # a Depot unload landed in the rod cask
        maker = _Assembler(self.world, self.world.home)
        maker.output_buffer.update({"fuel_rod": 1})
        fa.FuelAssemblerController(maker).step()
        self.assertEqual(uranium.count("raw_uranium"), 50)
        self.assertEqual(rod_cask.count("fuel_rod"), 1)
        self.assertEqual(maker.recipe, "")  # the delivered rod meets the reserve

    def test_latched_rod_cask_unlatched_into_stockpile_when_casks_full(self):
        _Consumer(self.world, "reactor_1", "reactor", self.world.home)
        _, rod_cask = self.casks(uranium=100)  # the uranium cask is full
        self.world.notebook.data[lead_cask.ROLES_KEY] = {"lead_cask_2": "fuel_rod"}
        rod_cask.add("raw_uranium", 5)  # a Depot unload landed in the emptied rod cask
        maker = _Assembler(self.world, self.world.home, recipe=fa.ROD_RECIPE)
        maker.output_buffer.update({"fuel_rod": 3})
        ctrl = fa.FuelAssemblerController(maker)
        ctrl.step()
        self.assertEqual(rod_cask.count("raw_uranium"), 0)
        self.assertEqual(maker.input_buffer.get("raw_uranium", 0), 5)
        ctrl.step()
        self.assertEqual(rod_cask.count("fuel_rod"), 3)


class RemotePlateOrderTests(_Base):
    def test_no_plate_order_off_home(self):
        remote = self.world.add_outpost("outpost_2")
        self.world.add_lead_cask("lead_cask_1", remote, "raw_uranium", 40)
        self.world.add_lead_cask("lead_cask_2", remote)
        maker = _Assembler(self.world, remote)
        fa.FuelAssemblerController(maker).step()
        self.assertEqual(maker.recipe, fa.ROD_RECIPE)
        self.assertIsNone(self.plate_order())


class LeadCaskTests(_Base):
    def test_rod_cask_needs_two_casks(self):
        self.world.add_lead_cask("lead_cask_1", self.world.home, "raw_uranium", 10)
        cask_id, note = lead_cask.ensure_rod_cask(self.world.home)
        self.assertIsNone(cask_id)
        assert note is not None
        self.assertIn("own cask", note)

    def test_rod_cask_prefers_rods_then_empty_then_least_uranium(self):
        self.world.add_lead_cask("lead_cask_1", self.world.home, "raw_uranium", 60)
        self.world.add_lead_cask("lead_cask_2", self.world.home, "raw_uranium", 10)
        self.assertEqual(lead_cask.ensure_rod_cask(self.world.home)[0], "lead_cask_2")
        self.world.notebook.data[lead_cask.ROLES_KEY] = {}
        self.world.add_lead_cask("lead_cask_3", self.world.home)
        self.assertEqual(lead_cask.ensure_rod_cask(self.world.home)[0], "lead_cask_3")

    def test_room_skips_rod_cask(self):
        self.casks(uranium=40)
        self.world.notebook.data[lead_cask.ROLES_KEY] = {"lead_cask_2": "fuel_rod"}
        self.assertEqual(lead_cask.room_for("raw_uranium", self.world.home), 60)
        self.assertEqual(lead_cask.room_for("fuel_rod", self.world.home), 100)

    def test_take_drains_misfiled_cask_first(self):
        uranium, rod_cask = self.casks(uranium=40)
        self.world.notebook.data[lead_cask.ROLES_KEY] = {"lead_cask_2": "fuel_rod"}
        rod_cask.add("raw_uranium", 3)
        port = _Assembler(self.world, self.world.home).input
        self.assertEqual(lead_cask.take_from_casks(port, "raw_uranium", 4, self.world.home), 4)
        self.assertEqual(rod_cask.count("raw_uranium"), 0)
        self.assertEqual(uranium.count("raw_uranium"), 39)

    def test_dock_leaves_local_consumer_reserve(self):
        _Consumer(self.world, "reactor_1", "reactor", self.world.home, staged=1)
        self.casks(rods=4)
        # reserve 1 + 2 per reactor = 3, one already staged: 2 held in the casks
        self.assertEqual(lead_cask.rods_for_orders(self.world.home), (2, 2))
        _Consumer(self.world, "reactor_2", "reactor", self.world.home)
        self.assertEqual(lead_cask.rods_for_orders(self.world.home), (0, 4))

    def test_reactor_fuel_alerts_errors_first_and_skip_stale(self):
        entries = {
            "reactor_1": {"alert": "no spare Fuel Rod, ~40 h left", "level": "warn", "tick": 1000},
            "reactor_2": {"alert": "OUT OF FUEL RODS", "level": "error", "tick": 1000},
            "reactor_3": {"alert": "", "level": "", "tick": 1000},
            "reactor_4": {"alert": "OUT OF FUEL RODS", "level": "error", "tick": 1000 - lead_cask.REACTOR_FUEL_FRESH_TICKS},
        }
        self.assertEqual(lead_cask.reactor_fuel_alerts(1000, entries), [
            ("reactor_2: OUT OF FUEL RODS", "error"),
            ("reactor_1: no spare Fuel Rod, ~40 h left", "warn"),
        ])

    def test_roles_pruned_for_gone_casks(self):
        self.casks()
        self.world.notebook.data[lead_cask.ROLES_KEY] = {"lead_cask_9": "fuel_rod"}
        lead_cask.ensure_rod_cask(self.world.home)
        self.assertEqual(self.roles(), {"lead_cask_2": "fuel_rod"})


class Mk4RodFeedTests(_Base):
    def test_loads_one_rod_into_mk4_magazine(self):
        self.casks(rods=3)
        heater = _Consumer(self.world, "heater_1", "temp_heater", self.world.home, tier=4)
        feed = terraforming.Mk4RodFeed(heater, "heater_1", terraforming.TreeConsole(module="terraforming"))
        feed.step()
        self.assertEqual(heater.input.count(), terraforming.MK4_MAGAZINE_TARGET)

    def test_below_mk4_takes_nothing(self):
        _u, rod_cask = self.casks(rods=3)
        heater = _Consumer(self.world, "heater_1", "temp_heater", self.world.home, tier=3)
        terraforming.Mk4RodFeed(heater, "heater_1", terraforming.TreeConsole(module="terraforming")).step()
        self.assertEqual(rod_cask.count("fuel_rod"), 3)


class HotCargoSourcingTests(_Base):
    def test_fuel_rod_sourceable_via_assembler(self):
        self.assertFalse(production.can_source_item("fuel_rod"))
        _Assembler(self.world, self.world.home)
        self.world.add_lead_cask("lead_cask_1", self.world.home, "raw_uranium", 4)
        self.world.inventory.add("lead_plate", 10)
        self.assertTrue(production.can_source_item("fuel_rod"))

    def test_uranium_sourceable_from_live_aftermath(self):
        self.assertFalse(production.can_source_item("raw_uranium"))
        self.world.notebook.data[production.AFTERMATHS_KEY] = {"storm_1": {"kind": "uranium"}}
        self.assertTrue(production.can_source_item("raw_uranium"))

    def test_hot_order_needs_cask_at_dock_outpost(self):
        order = type("O", (), {"requires": {"raw_uranium": 12}})()
        plain = type("O", (), {"requires": {"iron_ingot": 5}})()
        self.assertFalse(supply_dock._servable_at(order, self.world.home, {}))
        self.assertTrue(supply_dock._servable_at(plain, self.world.home, {}))
        self.world.add_lead_cask("lead_cask_1", self.world.home)
        self.assertTrue(supply_dock._servable_at(order, self.world.home, {}))


if __name__ == "__main__":
    unittest.main()
