import unittest

import harness
import habitat
import wildlife_common as wc
from wildlife_data import REVIVE_FEED_REQUIRED


class _Result:
    def __init__(self, status="ok", message=""):
        self.status = status
        self.message = message


class _Stack:
    def __init__(self, item_id, count):
        self.id = item_id
        self.count = count


class _Port:
    def __init__(self):
        self.items = {}
        self.ejected = []

    def stacks(self):
        return [_Stack(k, v) for k, v in self.items.items() if v > 0]

    def connect(self, target):
        return _Result()

    def eject(self, destination, item_id, count):
        self.items[item_id] = self.items.get(item_id, 0) - count
        self.ejected.append((destination, item_id, count))


class _Node:
    def __init__(self, node_id, slot, species, purchased=False):
        self.id = node_id
        self.slot = slot
        self.source_species = species
        self.purchased = purchased


class _Tree:
    def __init__(self, species, nodes):
        self.species = species
        self.nodes = nodes


class _Insight:
    shared_exact = 2.5


class _Habitat:
    def __init__(self, species="", target="", established=False):
        self.id = "habitat_1"
        self.outpost = type("O", (), {"id": "outpost_home", "is_home": True})()
        self.input = _Port()
        self.reagents = _Port()
        self.gas_in = _Port()
        self.liquid_in = _Port()
        self._species = species
        self._target = target
        self._established = established
        self.calls = []
        self.pop = 0
        self._tier = 1
        self._headroom = 100
        self.rate = 0.0
        self.bands = {"gas": [], "liquid": []}
        self.levels = {"gas": 0.0, "liquid": 0.0}
        self.fluids = {"gas": "", "liquid": ""}
        self.required = {"gas": "", "liquid": ""}
        self.next_bands = {"gas": [], "liquid": []}
        self.next_required = {"gas": "", "liquid": ""}
        self.next_pop = 0
        self.intake = {"gas": None, "liquid": None}
        self.purchased = {"adaptation": False, "breakthrough": False}

    # identity / state
    def species(self): return self._species
    def revival_target(self): return self._target
    def is_established(self): return self._established
    def rearing_failed(self): return False
    def rearing_progress(self): return 0.0
    def population(self): return self.pop
    def carrying_capacity(self): return 175000
    def tier(self): return self._tier
    def headroom(self): return self._headroom
    def life_stage(self): return "thriving"
    def breeding_rate(self): return self.rate
    def breeding_efficiency(self): return 1.0
    def next_stage_population(self): return self.next_pop
    def required_feed(self): return wc.feed_item_of(self._species or self._target)
    def feed_level(self): return float(self.input.items.get(self.required_feed(), 0))
    def feed_ok(self): return self.feed_level() > 0
    def get_insight(self): return _Insight()
    def get_active_bonuses(self): return []

    def get_bonus_tree(self):
        s = self._species or self._target
        return _Tree(s, [_Node(s + "_a", "adaptation", s, self.purchased["adaptation"]),
                         _Node(s + "_b", "breakthrough", s, self.purchased["breakthrough"])])

    # fluids
    def gas_band(self): return self.bands["gas"]
    def liquid_band(self): return self.bands["liquid"]
    def gas_level(self): return self.levels["gas"]
    def liquid_level(self): return self.levels["liquid"]
    def gas_fluid(self): return self.fluids["gas"]
    def liquid_fluid(self): return self.fluids["liquid"]
    def required_gas(self): return self.required["gas"]
    def required_liquid(self): return self.required["liquid"]
    def next_gas_band(self): return self.next_bands["gas"]
    def next_liquid_band(self): return self.next_bands["liquid"]
    def next_required_gas(self): return self.next_required["gas"]
    def next_required_liquid(self): return self.next_required["liquid"]

    def set_gas_intake(self, rate):
        self.intake["gas"] = rate
        return _Result()

    def set_liquid_intake(self, rate):
        self.intake["liquid"] = rate
        return _Result()

    def purge_reserve(self, medium):
        self.calls.append(("purge_reserve", medium))
        self.levels[medium] = 0.0
        self.fluids[medium] = ""
        return _Result()

    def purge_intake(self, port=None):
        self.calls.append(("purge_intake", port))
        return _Result()

    # actions
    def set_revival_target(self, species):
        self.calls.append(("set_revival_target", species))
        self._target = species
        return _Result()

    def unlock_bonus(self, node_id):
        self.calls.append(("unlock_bonus", node_id))
        self.purchased["adaptation" if node_id.endswith("_a") else "breakthrough"] = True
        return _Result()

    def revive(self):
        self.calls.append(("revive",))
        self._species = self._target
        return _Result()


class _Cash:
    def __init__(self, allow):
        self.allow = allow
        self.spent_calls = []

    def shop_price(self, item_id, fallback=0):
        return 100

    def can_spend(self, consumer, cost, planned=None, label=""):
        return self.allow

    def spent(self, consumer, amount):
        self.spent_calls.append((consumer, amount))

    def release(self, consumer):
        pass


class _Shop:
    def __init__(self, stock):
        self.stock = stock
        self.bought = []

    def buy(self, item_id, qty):
        self.bought.append((item_id, qty))
        self.stock[item_id] = self.stock.get(item_id, 0) + qty
        return _Result()


class _Creature:
    def __init__(self, species):
        self.creature_id = species
        self.revive_reagents = {r: 1 for r in ("alkaline_buffer", "cryo_solvent", "protein_marker", "chelating_agent", "enzyme_solution")}


class _Journal:
    def cataloged_creatures(self, planet_id):
        return [_Creature(s) for s in ("salt_tortoise", "spire_drake")]


class HabitatTestCase(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.services["journal"] = _Journal()
        self.stock = {}
        self._orig = (habitat.take_item, habitat.cash, habitat.local_port_target)

        def fake_take(port, item_id, amount, outpost=None, cache=None, report=None):
            moved = min(amount, self.stock.get(item_id, 0))
            self.stock[item_id] = self.stock.get(item_id, 0) - moved
            port.items[item_id] = port.items.get(item_id, 0) + moved
            return moved

        habitat.take_item = fake_take
        habitat.local_port_target = lambda outpost=None: "inventory"
        habitat.cash = _Cash(True)

    def tearDown(self):
        habitat.take_item, habitat.cash, habitat.local_port_target = self._orig
        super().tearDown()

    def controller(self, machine, assign=None, buy=None):
        plan = {"assign": {}, "buy": {}}
        if assign:
            plan["assign"][machine.id] = assign
        if buy:
            plan["buy"][machine.id] = buy
        self.world.notebook.data[wc.PLAN_KEY] = plan
        ctrl = habitat.HabitatController(machine)
        self.shop = _Shop(self.stock)
        ctrl.shop = self.shop  # type: ignore[assignment]
        return ctrl

    def status(self):
        return self.world.notebook.data[wc.STATUS_KEY]["habitat_1"]


class RevivalTests(HabitatTestCase):
    def test_no_revive_until_feed_reserved(self):
        machine = _Habitat()
        ctrl = self.controller(machine, {"species": "salt_tortoise", "adapt_first": False})
        ctrl.step()
        self.assertIn(("set_revival_target", "salt_tortoise"), machine.calls)
        self.assertNotIn(("revive",), machine.calls)
        self.assertEqual(self.status()["blocker"], "no_feed")

    def test_revive_once_feed_and_reagents_staged(self):
        machine = _Habitat()
        self.stock[wc.feed_item_of("salt_tortoise")] = 20
        ctrl = self.controller(machine, {"species": "salt_tortoise", "adapt_first": False})
        ctrl.step()
        self.assertIn(("revive",), machine.calls)
        self.assertEqual(machine.input.items[wc.feed_item_of("salt_tortoise")], REVIVE_FEED_REQUIRED + wc.REARING_FEED_EXTRA)
        self.assertEqual(sum(machine.reagents.items.values()), 5)
        self.assertEqual(len(self.shop.bought), 5)

    def test_reagent_budget_blocks_revive(self):
        habitat.cash = _Cash(False)
        machine = _Habitat()
        self.stock[wc.feed_item_of("salt_tortoise")] = 20
        ctrl = self.controller(machine, {"species": "salt_tortoise", "adapt_first": False})
        ctrl.step()
        self.assertNotIn(("revive",), machine.calls)
        self.assertEqual(self.shop.bought, [])
        self.assertEqual(self.status()["blocker"], "reagent_budget")

    def test_adaptation_bought_before_revive(self):
        machine = _Habitat()
        self.stock[wc.feed_item_of("spire_drake")] = 20
        ctrl = self.controller(machine, {"species": "spire_drake", "adapt_first": True}, buy="adaptation")
        ctrl.step()
        self.assertLess(machine.calls.index(("unlock_bonus", "spire_drake_a")), machine.calls.index(("revive",)))

    def test_waits_for_adaptation(self):
        machine = _Habitat()
        machine.unlock_bonus = lambda node_id: _Result("insufficient_insight")
        self.stock[wc.feed_item_of("spire_drake")] = 20
        ctrl = self.controller(machine, {"species": "spire_drake", "adapt_first": True}, buy="adaptation")
        ctrl.step()
        self.assertNotIn(("revive",), machine.calls)
        self.assertEqual(self.status()["blocker"], "awaiting_insight")

    def test_wrong_feed_ejected(self):
        machine = _Habitat()
        machine.input.items["feed_vault_crab"] = 4
        self.stock[wc.feed_item_of("salt_tortoise")] = 20
        ctrl = self.controller(machine, {"species": "salt_tortoise", "adapt_first": False})
        ctrl.step()
        self.assertIn(("inventory", "feed_vault_crab", 4), machine.input.ejected)


class ParkingTests(HabitatTestCase):
    def test_empty_unassigned_parks(self):
        ctrl = self.controller(_Habitat())
        for _ in range(3):
            ctrl.step()
        self.assertEqual(self.status()["parked"], wc.PARK_EMPTY)
        self.assertIn("habitat_1", self.world.notebook.data.get("script.park_requests", {}))

    def test_capped_parks(self):
        machine = _Habitat("salt_tortoise", established=True)
        machine.pop = 175000
        machine._headroom = 0
        machine.input.items[wc.feed_item_of("salt_tortoise")] = 50
        ctrl = self.controller(machine)
        ctrl.step()
        self.assertEqual(self.status()["parked"], wc.PARK_CAPPED)

    def test_no_feed_parks(self):
        machine = _Habitat("salt_tortoise", established=True)
        machine.pop = 1000
        machine.rate = 10.0
        ctrl = self.controller(machine)
        ctrl.step()
        self.assertEqual(self.status()["parked"], wc.PARK_NO_FEED)

    def test_rearing_never_parks(self):
        machine = _Habitat("salt_tortoise", established=False)
        ctrl = self.controller(machine)
        for _ in range(4):
            ctrl.step()
        self.assertEqual(self.status()["parked"], "")
        self.assertNotIn("habitat_1", self.world.notebook.data.get("script.park_requests", {}))

    def test_feed_topped_up(self):
        machine = _Habitat("salt_tortoise", established=True)
        machine.pop = 1000
        machine.rate = 10.0
        machine.input.items[wc.feed_item_of("salt_tortoise")] = 5
        self.stock[wc.feed_item_of("salt_tortoise")] = 100
        ctrl = self.controller(machine)
        ctrl.step()
        self.assertEqual(machine.input.items[wc.feed_item_of("salt_tortoise")], wc.FEED_TOPUP_TARGET)
        self.assertEqual(self.status()["parked"], "")


class RegulatorTests(HabitatTestCase):
    def setUp(self):
        super().setUp()
        self.machine = _Habitat("salt_tortoise", established=True)
        self.machine.pop = 30000
        self.machine.rate = 100.0
        self.machine.input.items[wc.feed_item_of("salt_tortoise")] = 50
        self.machine.bands["gas"] = [250.0, 650.0]
        self.machine.required["gas"] = "swamp_gas"
        self.ctrl = self.controller(self.machine)
        self.ctrl._route = lambda medium, fluid_id, curr_tick: True

    def test_below_band_fills_fast(self):
        self.machine.levels["gas"] = 100.0
        self.ctrl.step()
        self.assertEqual(self.machine.intake["gas"], habitat.MAX_INTAKE_T_PER_H)

    def test_in_band_holds_centre(self):
        self.machine.levels["gas"] = 450.0
        self.machine.fluids["gas"] = "swamp_gas"
        self.ctrl.step()
        self.assertAlmostEqual(float(self.machine.intake["gas"] or 0.0), 100.0 * 0.0008 + 0.5)

    def test_above_band_stops_intake(self):
        self.machine.levels["gas"] = 700.0
        self.machine.fluids["gas"] = "swamp_gas"
        self.ctrl.step()
        self.assertEqual(self.machine.intake["gas"], 0.0)
        self.assertNotIn(("purge_reserve", "gas"), self.machine.calls)

    def test_far_above_band_purges(self):
        self.machine.levels["gas"] = 800.0
        self.machine.fluids["gas"] = "swamp_gas"
        self.ctrl.step()
        self.assertIn(("purge_reserve", "gas"), self.machine.calls)

    def test_wrong_fluid_purged(self):
        self.machine.levels["gas"] = 450.0
        self.machine.fluids["gas"] = "ammonia"
        self.ctrl.step()
        self.assertIn(("purge_reserve", "gas"), self.machine.calls)
        self.assertIn(("purge_intake", "gas_in"), self.machine.calls)
        self.assertEqual(self.machine.intake["gas"], 0.0)

    def test_inactive_medium_closed(self):
        self.machine.levels["gas"] = 450.0
        self.machine.fluids["gas"] = "swamp_gas"
        self.ctrl.step()
        self.assertEqual(self.machine.intake["liquid"], 0.0)

    def ration(self):
        self.world.notebook.data[wc.PLAN_KEY]["fluid_ration"] = {"habitat_1": ["swamp_gas"]}

    def test_status_medium_entry(self):
        self.machine.levels["gas"] = 450.0
        self.machine.fluids["gas"] = "swamp_gas"
        self.ctrl.step()
        self.assertEqual(self.status()["gas"], ["swamp_gas", 450.0, [250.0, 650.0], "swamp_gas", 0.0])

    def test_rationed_in_band_coasts(self):
        self.ration()
        self.machine.levels["gas"] = 450.0
        self.machine.fluids["gas"] = "swamp_gas"
        self.ctrl.step()
        self.assertEqual(self.machine.intake["gas"], 0.0)
        self.assertNotIn(("purge_reserve", "gas"), self.machine.calls)
        self.assertEqual(self.status()["blocker"], "fluid_rationed")
        self.assertEqual(self.status()["parked"], "")

    def test_rationed_out_of_band_parks_without_purge(self):
        self.ration()
        self.machine.levels["gas"] = 800.0
        self.machine.fluids["gas"] = "swamp_gas"
        self.ctrl.step()
        self.assertEqual(self.machine.intake["gas"], 0.0)
        self.assertNotIn(("purge_reserve", "gas"), self.machine.calls)
        self.assertEqual(self.status()["parked"], wc.PARK_RATIONED)

    def test_rationed_prefill_skipped_without_parking(self):
        self.ration()
        self.machine.bands["gas"] = []
        self.machine.required["gas"] = ""
        self.machine.next_bands["gas"] = [250.0, 650.0]
        self.machine.next_required["gas"] = "swamp_gas"
        self.machine.next_pop = 30500
        self.ctrl.step()
        self.assertEqual(self.machine.intake["gas"], 0.0)
        self.assertEqual(self.status()["parked"], "")

    def test_no_feed_closes_intakes(self):
        self.machine.input.items[wc.feed_item_of("salt_tortoise")] = 0
        self.machine.levels["gas"] = 450.0
        self.machine.fluids["gas"] = "swamp_gas"
        self.ctrl.step()
        self.assertEqual(self.status()["parked"], wc.PARK_NO_FEED)
        self.assertEqual(self.machine.intake["gas"], 0.0)

    def test_no_source_blocker(self):
        self.ctrl._route = habitat.HabitatController._route.__get__(self.ctrl)
        self.ctrl.step()
        self.assertEqual(self.status()["blocker"], "no_swamp_gas_source")
        self.assertEqual(self.machine.intake["gas"], 0.0)


class PollTests(unittest.TestCase):
    def test_poll_tracks_feed_burn(self):
        self.assertEqual(habitat.next_poll(50, 0), habitat.POLL_MAX_S)
        self.assertEqual(habitat.next_poll(30, 15.0), habitat.POLL_MIN_S)
        self.assertGreater(habitat.next_poll(50, 1.0), habitat.next_poll(50, 15.0))


if __name__ == "__main__":
    unittest.main()
