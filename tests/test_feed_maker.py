import unittest

import game_stubs
import harness
import feed_maker
import wildlife_common as wc


def _recipe(species, forms):
    return game_stubs.Recipe(wc.recipe_of(species), dict({"forage": 100}, **{f: 1 for f in forms}), wc.feed_item_of(species))


class _FeedMaker(game_stubs.Machine):
    """Feed Maker: a recipe machine with a stockpile; logs recipe calls."""
    type_id = "feed_maker"

    def __init__(self, world, recipe="", running=False, stock_pile=None):
        super().__init__(world, "feed_maker_1", world.home, [_recipe("salt_tortoise", ["sea_algae", "snow_moss"]), _recipe("spire_drake", ["sulfur_moss", "cinder_lichen"])])
        self.input = game_stubs.Slot(self, self.input_buffer, 200)
        self.output = game_stubs.Slot(self, self.output_buffer, 50)
        self.recipe = recipe
        self.running = running
        self.input_buffer.update(stock_pile or {})
        self.calls = []

    def get_progress(self): return 0.0
    def get_output_count(self): return 0
    def get_stockpile(self): return {k: v for k, v in self.input_buffer.items() if v > 0}
    def get_stockpile_capacity(self): return 200
    def get_stockpile_used(self): return sum(self.get_stockpile().values())
    def tier(self): return 1

    def clear_recipe(self):
        self.calls.append(("clear_recipe",))
        return super().clear_recipe()

    def set_recipe(self, recipe_or_id):
        self.calls.append(("set_recipe", getattr(recipe_or_id, "id", recipe_or_id)))
        return super().set_recipe(recipe_or_id)


class _Logistics:
    def __init__(self, stock):
        self.stock = stock

    def outpost_stock(self, items, outpost):
        return {i: self.stock.get(i, 0) for i in items}


class FeedMakerTestCase(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.home = {"forage": 1000, "sea_algae": 10, "snow_moss": 10, "sulfur_moss": 10, "cinder_lichen": 10}
        self.feed_stock = {}
        self.taken = []
        self._orig = (feed_maker.take_item, feed_maker.total_stock, feed_maker.drain_port_to_storage,
                      feed_maker.local_port_target, feed_maker.logistics_requests)

        def fake_take(port, item_id, amount, outpost=None, cache=None, report=None):
            if port._slots_full_for(item_id):
                if report is not None:
                    report["sources"] = [("inventory", "slots_full", 0)]
                return 0
            self.taken.append((item_id, amount))
            port.machine.input_buffer[item_id] = port.machine.input_buffer.get(item_id, 0) + amount
            return amount

        feed_maker.take_item = fake_take
        feed_maker.total_stock = lambda item_id, outpost=None: self.feed_stock.get(item_id, 0)
        feed_maker.drain_port_to_storage = lambda port, outpost=None, include=None, allow_partial=False: 0
        feed_maker.local_port_target = lambda outpost=None: "inventory"
        feed_maker.logistics_requests = _Logistics(self.home)

    def tearDown(self):
        (feed_maker.take_item, feed_maker.total_stock, feed_maker.drain_port_to_storage,
         feed_maker.local_port_target, feed_maker.logistics_requests) = self._orig
        super().tearDown()

    def demand(self, rows):
        self.world.notebook.data[wc.PLAN_KEY] = {"feed_demand": rows}


class FeedMakerTests(FeedMakerTestCase):
    def test_idle_without_demand(self):
        maker = _FeedMaker(self.world)
        ctrl = feed_maker.FeedMakerController(maker)
        self.assertEqual(ctrl.step(), feed_maker.IDLE_POLL_S)
        self.assertNotIn(("set_recipe", wc.recipe_of("salt_tortoise")), maker.calls)
        published = self.world.notebook.data[wc.FEED_KEY]["feed_maker_1"]
        self.assertIn(wc.recipe_of("salt_tortoise"), published["recipes"])

    def test_crafts_up_to_target_only(self):
        item = wc.feed_item_of("salt_tortoise")
        self.demand({item: [40, 200, 40]})
        self.feed_stock[item] = 40
        maker = _FeedMaker(self.world)
        ctrl = feed_maker.FeedMakerController(maker)
        self.assertEqual(ctrl.step(), feed_maker.IDLE_POLL_S)
        self.feed_stock[item] = 10
        self.assertEqual(ctrl.step(), feed_maker.FAST_POLL_S)
        self.assertIn(("set_recipe", wc.recipe_of("salt_tortoise")), maker.calls)
        self.assertIn(("forage", 100), self.taken)
        maker.running = True
        self.assertEqual(ctrl.step(), feed_maker.ACTIVE_POLL_S)

    def test_priority_class_beats_bigger_deficit(self):
        self.demand({wc.feed_item_of("salt_tortoise"): [500, 200, 500], wc.feed_item_of("spire_drake"): [5, 0, 5]})
        maker = _FeedMaker(self.world)
        feed_maker.FeedMakerController(maker).step()
        self.assertEqual(maker.recipe, wc.recipe_of("spire_drake"))

    def test_switch_keeps_loaded_forage(self):
        self.demand({wc.feed_item_of("spire_drake"): [20, 0, 20]})
        maker = _FeedMaker(self.world, recipe=wc.recipe_of("salt_tortoise"), stock_pile={"forage": 100, "sea_algae": 1})
        feed_maker.FeedMakerController(maker).step()
        self.assertEqual(maker.recipe, wc.recipe_of("spire_drake"))
        self.assertEqual(self.world.inventory.items, {})
        self.assertNotIn("clear_recipe", [c[0] for c in maker.calls])
        self.assertNotIn(("forage", 100), self.taken)
        self.assertEqual(maker.input_buffer["forage"], 100)

    def test_switch_ejects_strays_only_without_room(self):
        self.demand({wc.feed_item_of("spire_drake"): [20, 0, 20]})
        maker = _FeedMaker(self.world, recipe=wc.recipe_of("salt_tortoise"), stock_pile={"forage": 50, "sea_algae": 140})
        feed_maker.FeedMakerController(maker).step()
        self.assertEqual(self.world.inventory.count("sea_algae"), 140)
        self.assertEqual(self.world.inventory.count("forage"), 0)

    def test_slots_full_ejects_strays_despite_room(self):
        self.demand({wc.feed_item_of("spire_drake"): [20, 0, 20]})
        strays = {f"stray_{i}": 1 for i in range(game_stubs.MATERIAL_SLOTS["feed_maker"] - 1)}
        maker = _FeedMaker(self.world, recipe=wc.recipe_of("spire_drake"), stock_pile=dict(strays, forage=100))
        ctrl = feed_maker.FeedMakerController(maker)
        ctrl.step()
        self.assertEqual(self.taken, [])
        self.assertEqual({item: self.world.inventory.count(item) for item in strays}, strays)
        self.assertEqual(self.world.inventory.count("forage"), 0)
        ctrl.step()
        self.assertIn(("sulfur_moss", 1), self.taken)
        self.assertIn(("cinder_lichen", 1), self.taken)

    def test_current_recipe_kept_within_class(self):
        tortoise, drake = wc.recipe_of("salt_tortoise"), wc.recipe_of("spire_drake")
        self.demand({wc.feed_item_of("salt_tortoise"): [40, 105, 40], wc.feed_item_of("spire_drake"): [200, 101, 200]})
        maker = _FeedMaker(self.world, recipe=tortoise)
        feed_maker.FeedMakerController(maker).step()
        self.assertEqual(maker.recipe, tortoise)
        self.demand({wc.feed_item_of("salt_tortoise"): [40, 105, 40], wc.feed_item_of("spire_drake"): [200, 1, 200]})
        feed_maker.FeedMakerController(maker).step()
        self.assertEqual(maker.recipe, drake)

    def test_running_craft_finishes_before_switch(self):
        self.demand({wc.feed_item_of("spire_drake"): [20, 0, 20]})
        maker = _FeedMaker(self.world, recipe=wc.recipe_of("salt_tortoise"), running=True)
        self.assertEqual(feed_maker.FeedMakerController(maker).step(), feed_maker.ACTIVE_POLL_S)
        self.assertEqual(maker.recipe, wc.recipe_of("salt_tortoise"))

    def test_missing_inputs_blocks(self):
        self.home["sulfur_moss"] = 0
        self.demand({wc.feed_item_of("spire_drake"): [20, 0, 20]})
        maker = _FeedMaker(self.world)
        ctrl = feed_maker.FeedMakerController(maker)
        self.assertEqual(ctrl.step(), feed_maker.IDLE_POLL_S)
        self.assertEqual(self.world.notebook.data[wc.FEED_KEY]["feed_maker_1"]["blocker"], "no_inputs")

    def test_recipe_claimed_by_other_maker_skipped_for_small_deficit(self):
        rid = wc.recipe_of("spire_drake")
        self.world.notebook.data[wc.FEED_KEY] = {"feed_maker_2": {"recipe": rid, "tick": self.world.clock.tick()}}
        self.demand({wc.feed_item_of("spire_drake"): [20, 0, 20]})
        maker = _FeedMaker(self.world)
        feed_maker.FeedMakerController(maker).step()
        self.assertEqual(maker.recipe, "")
        self.demand({wc.feed_item_of("spire_drake"): [60, 0, 60]})
        feed_maker.FeedMakerController(maker).step()
        self.assertEqual(maker.recipe, rid)

    def test_shed_starts_nothing(self):
        self.world.notebook.data["power.shedded"] = ["feed_maker_1"]
        self.demand({wc.feed_item_of("spire_drake"): [20, 0, 20]})
        maker = _FeedMaker(self.world)
        feed_maker.FeedMakerController(maker).step()
        self.assertEqual(maker.recipe, "")
        self.assertEqual(self.taken, [])


if __name__ == "__main__":
    unittest.main()
