import unittest

import harness
from game_stubs import Building, FluidPort, Result, Slot, spec_recipe
import refiner
from archive import archive


class _Refiner(Building):
    """Refiner: no shared fake yet. Recipes are the spec's; 40 tar loaded."""
    type_id = "refiner"
    RECIPES = [spec_recipe(r) for r in ("refine_sulfur_gas", "refine_chlorine", "refine_cryofluid")]

    def __init__(self, world, outpost, recipe=""):
        super().__init__(world, "refiner_1", outpost)
        self.recipe = recipe
        self.running = False
        self.stalled = False
        self.gas_in = FluidPort(world, capacity=10.0)
        self.liquid_in = FluidPort(world, capacity=10.0)
        self.gas_out = FluidPort(world, capacity=10.0)
        self.liquid_out = FluidPort(world, capacity=10.0)
        self.input_buffer["tar"] = 40
        self.input = Slot(self, self.input_buffer, 50)
        self.commands_queue = []
        self.calls = []
        self.set_status = "ok"

    def list_recipes(self):
        return list(self.RECIPES)

    def get_recipe(self):
        return self.recipe

    def set_recipe(self, rid):
        self.calls.append(("set_recipe", rid))
        if self.set_status == "ok":
            self.recipe = rid
        return Result(self.set_status)

    def clear_recipe(self):
        self.calls.append(("clear_recipe",))
        self.recipe = ""
        return Result("ok")

    def purge_input(self):
        self.calls.append(("purge_input",))
        self.gas_in._level = 0.0
        self.liquid_in._level = 0.0
        return Result("ok")

    def is_running(self):
        return self.running

    def is_stalled(self):
        return self.stalled

    def command_count(self):
        return len(self.commands_queue)

    def next_command(self):
        return self.commands_queue.pop(0) if self.commands_queue else None


class _Router:
    def ensure(self, *args, **kwargs):
        return None

    def ensure_connection(self, *args, **kwargs):
        return None


class RefinerTestCase(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.comp = _Refiner(self.world, self.world.add_outpost("outpost_1"))
        self.world.components["refiner_1"] = self.comp
        self.ctrl = refiner.RefinerController(self.comp)
        self.ctrl.routers = lambda rid, spec: (_Router(), _Router())
        self.ctrl.top_up_tar = lambda: None
        self.totals = {}
        self._orig_totals = refiner.fluid_totals
        refiner.fluid_totals = lambda: self.totals

    def tearDown(self):
        refiner.fluid_totals = self._orig_totals
        super().tearDown()

    def test_unlocked_recipes_reads_ports_from_recipe(self):
        spec = self.ctrl.unlocked_recipes(0)["refine_cryofluid"]
        self.assertEqual((spec["raw_fluid"], spec["refined_fluid"]), ("raw_cryofluid", "cryofluid"))
        self.assertEqual((spec["input_port"], spec["output_port"]), ("liquid_in", "liquid_out"))
        self.assertEqual(spec["tar"], 2)
        self.assertEqual(spec["raw_tons"], 4.0)

    def test_candidates_need_raw_stock_and_refined_room(self):
        unlocked = self.ctrl.unlocked_recipes(0)
        totals = {
            "raw_sulfur_gas": [50.0, 100.0], "sulfur_gas": [10.0, 100.0],
            "raw_chlorine": [2.0, 100.0], "chlorine": [0.0, 100.0],
            "raw_cryofluid": [50.0, 100.0], "cryofluid": [99.0, 100.0],
        }
        self.assertEqual(refiner.recipe_candidates(unlocked, totals), {"refine_sulfur_gas": 0.1})
        # A craft staged in the input port counts as raw supply.
        self.assertIn("refine_chlorine", refiner.recipe_candidates(unlocked, totals, {"refine_chlorine": True}))
        # No tank for the refined fluid: nowhere to put it.
        self.assertEqual(refiner.recipe_candidates(unlocked, {"raw_sulfur_gas": [50.0, 100.0]}), {})

    def test_choose_recipe_dwell_margin_and_rotation(self):
        cands = {"a": 0.5, "b": 0.4}
        self.assertEqual(refiner.choose_recipe(cands, "a", 0), "a")                           # dwell
        self.assertEqual(refiner.choose_recipe(cands, "a", refiner.MIN_RECIPE_TICKS), "a")    # inside margin
        self.assertEqual(refiner.choose_recipe(cands, "a", refiner.MAX_RECIPE_TICKS), "b")    # rotation
        self.assertEqual(refiner.choose_recipe({"a": 0.5, "b": 0.2}, "a", refiner.MIN_RECIPE_TICKS), "b")
        self.assertEqual(refiner.choose_recipe(cands, "c", 0), "b")                           # current not a candidate
        self.assertEqual(refiner.choose_recipe({}, "a", 0), "a")
        self.assertIsNone(refiner.choose_recipe({}, None, 0))

    def test_step_sets_emptiest_refined_fluid(self):
        self.totals = {
            "raw_sulfur_gas": [50.0, 100.0], "sulfur_gas": [60.0, 100.0],
            "raw_cryofluid": [50.0, 100.0], "cryofluid": [5.0, 100.0],
        }
        self.ctrl.step()
        self.assertEqual(self.comp.recipe, "refine_cryofluid")
        self.assertNotIn(("purge_input",), self.comp.calls)

    def test_no_raw_stock_keeps_recipe_and_idles(self):
        self.comp.recipe = "refine_sulfur_gas"
        self.totals = {"sulfur_gas": [0.0, 100.0], "cryofluid": [0.0, 100.0]}
        delay = self.ctrl.step()
        self.assertEqual(self.comp.recipe, "refine_sulfur_gas")
        self.assertEqual(delay, refiner.IDLE_POLL_S)
        self.assertEqual(archive.get(refiner.STATUS_KEY)["refiner_1"]["blocker"], "no_raw_supply")

    def test_no_raw_stock_leaves_input_unrouted(self):
        self.comp.recipe = "refine_sulfur_gas"
        self.totals = {"raw_sulfur_gas": [0.0, 5000.0], "sulfur_gas": [0.0, 5000.0]}
        routed = []
        self.ctrl.route_input = lambda rid, spec, curr_tick: routed.append(rid)
        self.ctrl.step()
        self.assertEqual(routed, [])
        self.totals = {"raw_sulfur_gas": [50.0, 5000.0], "sulfur_gas": [0.0, 5000.0]}
        self.ctrl._totals_tick = -refiner.TOTALS_REFRESH_TICKS
        self.ctrl.step()
        self.assertEqual(routed, ["refine_sulfur_gas"])

    def test_shared_port_switch_drains_output_then_purges(self):
        self.comp.recipe = "refine_sulfur_gas"
        self.comp.gas_in._level = 2.0      # less than one craft left
        self.comp.gas_out._level = 3.0     # old refined gas still in the shared output
        self.totals = {
            "raw_sulfur_gas": [0.0, 100.0], "sulfur_gas": [90.0, 100.0],
            "raw_chlorine": [50.0, 100.0], "chlorine": [0.0, 100.0],
        }
        self.ctrl.step()
        self.assertEqual(self.comp.recipe, "refine_sulfur_gas")
        self.assertEqual(self.comp.gas_in.disconnects, 1)
        self.assertNotIn(("purge_input",), self.comp.calls)
        self.comp.gas_out._level = 0.0
        self.ctrl.step()
        self.assertEqual(self.comp.recipe, "refine_chlorine")
        self.assertIn(("purge_input",), self.comp.calls)
        self.assertEqual(self.comp.gas_in.disconnects, 1)

    def test_switch_waits_for_running_craft(self):
        self.comp.recipe = "refine_sulfur_gas"
        self.comp.running = True
        self.totals = {"raw_cryofluid": [50.0, 100.0], "cryofluid": [0.0, 100.0]}
        self.ctrl.step()
        self.assertEqual(self.comp.recipe, "refine_sulfur_gas")
        self.comp.running = False
        self.ctrl.step()
        self.assertEqual(self.comp.recipe, "refine_cryofluid")
        self.assertNotIn(("purge_input",), self.comp.calls)  # different ports

    def test_shed_clears_recipe_after_craft(self):
        self.comp.recipe = "refine_sulfur_gas"
        self.comp.running = True
        archive.set("power.shedded", ["refiner_1"])
        self.ctrl.step()
        self.assertEqual(self.comp.recipe, "refine_sulfur_gas")
        self.comp.running = False
        self.ctrl.step()
        self.assertEqual(self.comp.recipe, "")

    def test_commands(self):
        self.comp.commands_queue = ["recipe refine_cryofluid"]
        self.ctrl.process_commands()
        self.assertEqual(self.ctrl.pinned, "refine_cryofluid")
        self.comp.commands_queue = ["auto", "purge"]
        self.ctrl.process_commands()
        self.assertIsNone(self.ctrl.pinned)
        self.assertIn(("purge_input",), self.comp.calls)

    def test_tar_top_up_only_below_refill_point(self):
        ctrl = refiner.RefinerController(self.comp)
        taken = []
        orig = refiner.take_item
        refiner.take_item = lambda port, item_id, count, outpost=None: taken.append((item_id, count)) or count
        try:
            self.comp.input_buffer["tar"] = refiner.TAR_REFILL_AT + 1
            ctrl.top_up_tar()
            self.assertEqual(taken, [])
            self.comp.input_buffer["tar"] = 10
            ctrl.top_up_tar()
            self.assertEqual(taken, [("tar", 40)])
        finally:
            refiner.take_item = orig


if __name__ == "__main__":
    unittest.main()
