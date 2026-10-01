import unittest

import harness
import feed_maker
import wildlife_common as wc


class _Result:
    def __init__(self, status="ok"):
        self.status = status
        self.message = ""


class _Recipe:
    def __init__(self, species, forms):
        self.id = wc.recipe_of(species)
        self.output_item = wc.feed_item_of(species)
        self.inputs = dict({"forage": 100}, **{f: 1 for f in forms})


class _Input:
    def __init__(self, maker):
        self.maker = maker

    def eject(self, destination, item_id, count):
        self.maker.calls.append(("eject", item_id, count))
        self.maker.stock_pile[item_id] = self.maker.stock_pile.get(item_id, 0) - count


class _Output:
    def stacks(self):
        return []


class _FeedMaker:
    def __init__(self, recipe="", running=False, stock_pile=None):
        self.id = "feed_maker_1"
        self.outpost = type("O", (), {"id": "outpost_home", "is_home": True})()
        self.input = _Input(self)
        self.output = _Output()
        self.recipe = recipe
        self.running = running
        self.stock_pile = dict(stock_pile or {})
        self.calls = []

    def list_recipes(self):
        return [_Recipe("salt_tortoise", ["sea_algae", "snow_moss"]), _Recipe("spire_drake", ["sulfur_moss", "cinder_lichen"])]

    def get_recipe(self): return self.recipe
    def is_running(self): return self.running
    def get_progress(self): return 0.0
    def get_output_count(self): return 0
    def get_stockpile(self): return {k: v for k, v in self.stock_pile.items() if v > 0}
    def get_stockpile_capacity(self): return 200
    def get_stockpile_used(self): return sum(self.get_stockpile().values())
    def tier(self): return 1

    def clear_recipe(self):
        self.calls.append(("clear_recipe",))
        return _Result()

    def set_recipe(self, rid):
        self.calls.append(("set_recipe", rid))
        self.recipe = rid
        return _Result()


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
            self.taken.append((item_id, amount))
            port.maker.stock_pile[item_id] = port.maker.stock_pile.get(item_id, 0) + amount
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
        maker = _FeedMaker()
        ctrl = feed_maker.FeedMakerController(maker)
        self.assertEqual(ctrl.step(), feed_maker.IDLE_POLL_S)
        self.assertNotIn(("set_recipe", wc.recipe_of("salt_tortoise")), maker.calls)
        published = self.world.notebook.data[wc.FEED_KEY]["feed_maker_1"]
        self.assertIn(wc.recipe_of("salt_tortoise"), published["recipes"])

    def test_crafts_up_to_target_only(self):
        item = wc.feed_item_of("salt_tortoise")
        self.demand({item: [40, 200, 40]})
        self.feed_stock[item] = 40
        maker = _FeedMaker()
        ctrl = feed_maker.FeedMakerController(maker)
        self.assertEqual(ctrl.step(), feed_maker.IDLE_POLL_S)
        self.feed_stock[item] = 10
        self.assertEqual(ctrl.step(), feed_maker.ACTIVE_POLL_S)
        self.assertIn(("set_recipe", wc.recipe_of("salt_tortoise")), maker.calls)
        self.assertIn(("forage", 100), self.taken)

    def test_priority_class_beats_bigger_deficit(self):
        self.demand({wc.feed_item_of("salt_tortoise"): [500, 200, 500], wc.feed_item_of("spire_drake"): [5, 0, 5]})
        maker = _FeedMaker()
        feed_maker.FeedMakerController(maker).step()
        self.assertEqual(maker.recipe, wc.recipe_of("spire_drake"))

    def test_switch_ejects_leftovers_first(self):
        self.demand({wc.feed_item_of("spire_drake"): [20, 0, 20]})
        maker = _FeedMaker(recipe=wc.recipe_of("salt_tortoise"), stock_pile={"forage": 60, "sea_algae": 1})
        feed_maker.FeedMakerController(maker).step()
        names = [c[0] for c in maker.calls]
        self.assertLess(names.index("eject"), names.index("set_recipe"))
        self.assertIn(("eject", "forage", 60), maker.calls)

    def test_running_craft_finishes_before_switch(self):
        self.demand({wc.feed_item_of("spire_drake"): [20, 0, 20]})
        maker = _FeedMaker(recipe=wc.recipe_of("salt_tortoise"), running=True)
        self.assertEqual(feed_maker.FeedMakerController(maker).step(), feed_maker.ACTIVE_POLL_S)
        self.assertEqual(maker.recipe, wc.recipe_of("salt_tortoise"))

    def test_missing_inputs_blocks(self):
        self.home["sulfur_moss"] = 0
        self.demand({wc.feed_item_of("spire_drake"): [20, 0, 20]})
        maker = _FeedMaker()
        ctrl = feed_maker.FeedMakerController(maker)
        self.assertEqual(ctrl.step(), feed_maker.IDLE_POLL_S)
        self.assertEqual(self.world.notebook.data[wc.FEED_KEY]["feed_maker_1"]["blocker"], "no_inputs")

    def test_recipe_claimed_by_other_maker_skipped_for_small_deficit(self):
        rid = wc.recipe_of("spire_drake")
        self.world.notebook.data[wc.FEED_KEY] = {"feed_maker_2": {"recipe": rid, "tick": self.world.clock.tick()}}
        self.demand({wc.feed_item_of("spire_drake"): [20, 0, 20]})
        maker = _FeedMaker()
        feed_maker.FeedMakerController(maker).step()
        self.assertEqual(maker.recipe, "")
        self.demand({wc.feed_item_of("spire_drake"): [60, 0, 60]})
        feed_maker.FeedMakerController(maker).step()
        self.assertEqual(maker.recipe, rid)

    def test_shed_starts_nothing(self):
        self.world.notebook.data["power.shedded"] = ["feed_maker_1"]
        self.demand({wc.feed_item_of("spire_drake"): [20, 0, 20]})
        maker = _FeedMaker()
        feed_maker.FeedMakerController(maker).step()
        self.assertEqual(maker.recipe, "")
        self.assertEqual(self.taken, [])


if __name__ == "__main__":
    unittest.main()
