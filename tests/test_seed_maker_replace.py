import unittest

import game_stubs
import harness
import seed_maker
import stock_scan
from seed_supply import SEED_DEMAND_KEY, SEED_DEMAND_STALE_TICKS

FORMS = ["fa", "fb", "fc", "fd", "fe", "ff"]
SALT_BLEND = ["fa", "fb", "fc"]


class _SeedRecipe:
    """SeedRecipe (docs/types/biosphere.md): the fields stage A reads."""

    def __init__(self, species, blend):
        self.species = species
        self.seed_id = "seed_" + species
        self.blend = list(blend)


class _SeedMaker(game_stubs.Building):
    """Seed Maker: combine() consumes the loaded blend; a known blend yields its seed into the output bin."""

    type_id = "seed_maker"

    def __init__(self, world, maker_id="seed_maker_1", recipes=()):
        super().__init__(world, maker_id, world.home)
        self.input = game_stubs.Slot(self, self.input_buffer, 3)
        self.output = game_stubs.Slot(self, self.output_buffer, 10)
        self._recipes = list(recipes)
        self.combined = []

    def life_forms(self):
        return list(FORMS)

    def recipes(self):
        return list(self._recipes)

    def is_running(self):
        return False

    def get_output_count(self):
        return sum(self.output_buffer.values())

    def combine(self, blend):
        self.combined.append(sorted(blend))
        for form in blend:
            self.input_buffer[form] = self.input_buffer.get(form, 0) - 1
            if self.input_buffer[form] <= 0:
                del self.input_buffer[form]
        recipe = next((r for r in self._recipes if sorted(r.blend) == sorted(blend)), None)
        if recipe is None:
            return game_stubs.Result("sludge")
        self.output_buffer[recipe.seed_id] = self.output_buffer.get(recipe.seed_id, 0) + 1
        return game_stubs.Result("seed_found", species=recipe.species, seed_id=recipe.seed_id)


class SeedMakerReplaceTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.home_seeds = {}
        self.stock = {f: 5 for f in FORMS}
        self._orig_held = stock_scan.held_units
        stock_scan.held_units = lambda item_id, outpost=None: self.home_seeds.get(item_id, 0)

    def tearDown(self):
        stock_scan.held_units = self._orig_held
        super().tearDown()

    def controller(self, maker):
        ctrl = seed_maker.SeedMakerController(maker)
        ctrl._local_stock = lambda: dict(self.stock)
        ctrl._publish_requests = lambda saturated, stock, curr_tick, force=False: 100

        def load_one(item_id):
            if self.stock.get(item_id, 0) < 1:
                return False
            self.stock[item_id] -= 1
            maker.input_buffer[item_id] = maker.input_buffer.get(item_id, 0) + 1
            return True

        def drain():
            for item_id, n in list(maker.output_buffer.items()):
                self.home_seeds[item_id] = self.home_seeds.get(item_id, 0) + n
            maker.output_buffer.clear()
            return True

        ctrl._load_one = load_one
        ctrl._drain_output = drain
        return ctrl

    def demand(self, replace, age=0):
        self.world.notebook.data[SEED_DEMAND_KEY] = {
            "now": {},
            "rotation": {},
            "priority": [],
            "replace": replace,
            "tick": self.world.clock.now - age,
        }

    def maker(self, maker_id="seed_maker_1"):
        return _SeedMaker(self.world, maker_id, [_SeedRecipe("saltbloom", SALT_BLEND)])

    def test_replacement_before_trial(self):
        self.demand({"seed_saltbloom": 1})
        maker = self.maker()
        ctrl = self.controller(maker)
        ctrl.step()
        self.assertEqual(maker.combined, [SALT_BLEND], self.debug_log())
        self.assertEqual(self.home_seeds.get("seed_saltbloom"), 1)
        self.assertEqual(ctrl._trials_this_run, 0)
        self.assertIs(self.world.notebook.data[seed_maker.TRIED_KEY].get("fa,fb,fc"), True)
        self.assertEqual(self.world.notebook.data[seed_maker.REPLACE_KEY], {})
        # Demand covered by the seed at home: the next step runs a discovery trial.
        ctrl.step()
        self.assertEqual(len(maker.combined), 2)
        self.assertNotEqual(maker.combined[1], SALT_BLEND)
        self.assertEqual(ctrl._trials_this_run, 1)

    def test_skips_when_forms_missing(self):
        self.demand({"seed_saltbloom": 1})
        self.stock["fa"] = 0
        maker = self.maker()
        ctrl = self.controller(maker)
        ctrl.step()
        self.assertEqual(len(maker.combined), 1)
        self.assertNotEqual(maker.combined[0], SALT_BLEND)
        self.assertEqual(ctrl._trials_this_run, 1)

    def test_skips_unknown_recipe(self):
        self.demand({"seed_moonvine": 1})
        maker = self.maker()
        ctrl = self.controller(maker)
        ctrl.step()
        self.assertEqual(ctrl._trials_this_run, 1)
        self.assertNotIn(SALT_BLEND, maker.combined)

    def test_skips_when_home_stock_covers(self):
        self.demand({"seed_saltbloom": 2})
        self.home_seeds["seed_saltbloom"] = 2
        maker = self.maker()
        ctrl = self.controller(maker)
        ctrl.step()
        self.assertEqual(ctrl._trials_this_run, 1)
        self.assertNotIn(SALT_BLEND, maker.combined)

    def test_stale_demand_ignored(self):
        self.demand({"seed_saltbloom": 1}, age=SEED_DEMAND_STALE_TICKS)
        maker = self.maker()
        ctrl = self.controller(maker)
        ctrl.step()
        self.assertEqual(ctrl._trials_this_run, 1)
        self.assertNotIn(SALT_BLEND, maker.combined)

    def test_missing_replace_field_is_no_demand(self):
        self.world.notebook.data[SEED_DEMAND_KEY] = {"now": {}, "tick": self.world.clock.now}
        maker = self.maker()
        ctrl = self.controller(maker)
        ctrl.step()
        self.assertEqual(ctrl._trials_this_run, 1)

    def test_peer_in_flight_claim_blocks_second_maker(self):
        self.demand({"seed_saltbloom": 1})
        self.world.notebook.data[seed_maker.REPLACE_KEY] = {"seed_saltbloom": {"seed_maker_2": self.world.clock.now}}
        maker = self.maker()
        ctrl = self.controller(maker)
        ctrl.step()
        self.assertNotIn(SALT_BLEND, maker.combined)
        self.assertEqual(ctrl._trials_this_run, 1)

    def test_recover_finishes_loaded_known_blend(self):
        maker = self.maker()
        for form in SALT_BLEND:
            maker.input_buffer[form] = 1
        ctrl = self.controller(maker)
        ctrl._recover(self.world.clock.now)
        self.assertEqual(maker.combined, [SALT_BLEND])
        self.assertEqual(self.home_seeds.get("seed_saltbloom"), 1)
        self.assertEqual(ctrl._trials_this_run, 0)


if __name__ == "__main__":
    unittest.main()
