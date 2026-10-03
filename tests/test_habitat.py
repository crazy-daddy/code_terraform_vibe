import unittest

import harness
import habitat
import wildlife_common as wc
from game_stubs import FluidConnection, HabitatBonusNode, Journal, Shop
from wildlife_data import REVIVE_FEED_REQUIRED


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


class _Shop(Shop):
    """Records purchases and puts them in the test's `stock`."""

    def __init__(self, world, stock):
        super().__init__(world)
        self.stock = stock
        self.bought = []

    def buy(self, item_id, quantity=1):
        self.bought.append((item_id, quantity))
        self.stock[item_id] = self.stock.get(item_id, 0) + quantity
        return super().buy(item_id, quantity)


class _Creature:
    def __init__(self, species):
        self.creature_id = species
        self.revive_reagents = {r: 1 for r in ("alkaline_buffer", "cryo_solvent", "protein_marker", "chelating_agent", "enzyme_solution")}


class HabitatTestCase(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.services["journal"] = Journal(creatures=[_Creature(s) for s in ("salt_tortoise", "spire_drake")])
        self.stock = {}
        self._orig = (habitat.take_item, habitat.cash, habitat.local_port_target)

        def fake_take(port, item_id, amount, outpost=None, cache=None, report=None):
            moved = min(amount, self.stock.get(item_id, 0))
            self.stock[item_id] = self.stock.get(item_id, 0) - moved
            port.buffer[item_id] = port.buffer.get(item_id, 0) + moved
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
        self.shop = _Shop(self.world, self.stock)
        ctrl.shop = self.shop  # type: ignore[assignment]
        return ctrl

    def status(self):
        return self.world.notebook.data[wc.STATUS_KEY]["habitat_1"]

    def habitat(self, species="", established=False, revive=""):
        """habitat_1 at home with a colony of `species`, or empty and fed for the
        revival target `revive`; an adaptation and a breakthrough node, 2.5 insight."""
        kind = species or revive
        machine = self.world.add_habitat("habitat_1", self.world.home, species, feed_item=wc.feed_item_of(kind) if kind else "", established=established)
        machine.capacity, machine.room, machine.stage, machine.insight = 175000, 100, "thriving", 2.5
        if kind:
            machine.nodes = [HabitatBonusNode(kind + "_a", "adaptation", kind), HabitatBonusNode(kind + "_b", "breakthrough", kind)]
        return machine


class RevivalTests(HabitatTestCase):
    def test_no_revive_until_feed_reserved(self):
        machine = self.habitat(revive="salt_tortoise")
        ctrl = self.controller(machine, {"species": "salt_tortoise", "adapt_first": False})
        ctrl.step()
        self.assertIn(("set_revival_target", "salt_tortoise"), machine.calls)
        self.assertNotIn(("revive",), machine.calls)
        self.assertEqual(self.status()["blocker"], "no_feed")

    def test_revive_once_feed_and_reagents_staged(self):
        machine = self.habitat(revive="salt_tortoise")
        self.stock[wc.feed_item_of("salt_tortoise")] = 20
        ctrl = self.controller(machine, {"species": "salt_tortoise", "adapt_first": False})
        ctrl.step()
        self.assertIn(("revive",), machine.calls)
        self.assertEqual(machine.input_buffer[wc.feed_item_of("salt_tortoise")], REVIVE_FEED_REQUIRED + wc.REARING_FEED_EXTRA)
        self.assertEqual(sum(machine.reagents_buffer.values()), 5)
        self.assertEqual(len(self.shop.bought), 5)

    def test_reagent_budget_blocks_revive(self):
        habitat.cash = _Cash(False)
        machine = self.habitat(revive="salt_tortoise")
        self.stock[wc.feed_item_of("salt_tortoise")] = 20
        ctrl = self.controller(machine, {"species": "salt_tortoise", "adapt_first": False})
        ctrl.step()
        self.assertNotIn(("revive",), machine.calls)
        self.assertEqual(self.shop.bought, [])
        self.assertEqual(self.status()["blocker"], "reagent_budget")

    def test_adaptation_bought_before_revive(self):
        machine = self.habitat(revive="spire_drake")
        self.stock[wc.feed_item_of("spire_drake")] = 20
        ctrl = self.controller(machine, {"species": "spire_drake", "adapt_first": True}, buy="adaptation")
        ctrl.step()
        self.assertLess(machine.calls.index(("unlock_bonus", "spire_drake_a")), machine.calls.index(("revive",)))

    def test_waits_for_adaptation(self):
        machine = self.habitat(revive="spire_drake")
        machine.insight = 0.0
        self.stock[wc.feed_item_of("spire_drake")] = 20
        ctrl = self.controller(machine, {"species": "spire_drake", "adapt_first": True}, buy="adaptation")
        ctrl.step()
        self.assertNotIn(("revive",), machine.calls)
        self.assertEqual(self.status()["blocker"], "awaiting_insight")

    def test_wrong_feed_ejected(self):
        machine = self.habitat(revive="salt_tortoise")
        machine.input_buffer["feed_vault_crab"] = 4
        self.stock[wc.feed_item_of("salt_tortoise")] = 20
        ctrl = self.controller(machine, {"species": "salt_tortoise", "adapt_first": False})
        ctrl.step()
        self.assertEqual(self.world.inventory.count("feed_vault_crab"), 4)
        self.assertNotIn("feed_vault_crab", machine.input_buffer)


class ParkingTests(HabitatTestCase):
    def test_empty_unassigned_parks(self):
        ctrl = self.controller(self.habitat())
        for _ in range(3):
            ctrl.step()
        self.assertEqual(self.status()["parked"], wc.PARK_EMPTY)
        self.assertIn("habitat_1", self.world.notebook.data.get("script.park_requests", {}))

    def test_capped_parks(self):
        machine = self.habitat("salt_tortoise", established=True)
        machine.pop = 175000
        machine.room = 0
        machine.input_buffer[wc.feed_item_of("salt_tortoise")] = 50
        ctrl = self.controller(machine)
        ctrl.step()
        self.assertEqual(self.status()["parked"], wc.PARK_CAPPED)

    def test_no_feed_parks(self):
        machine = self.habitat("salt_tortoise", established=True)
        machine.pop = 1000
        machine.rate = 10.0
        ctrl = self.controller(machine)
        ctrl.step()
        self.assertEqual(self.status()["parked"], wc.PARK_NO_FEED)

    def test_rearing_never_parks(self):
        machine = self.habitat("salt_tortoise", established=False)
        ctrl = self.controller(machine)
        for _ in range(4):
            ctrl.step()
        self.assertEqual(self.status()["parked"], "")
        self.assertNotIn("habitat_1", self.world.notebook.data.get("script.park_requests", {}))

    def test_feed_topped_up(self):
        machine = self.habitat("salt_tortoise", established=True)
        machine.pop = 1000
        machine.rate = 10.0
        machine.input_buffer[wc.feed_item_of("salt_tortoise")] = 5
        self.stock[wc.feed_item_of("salt_tortoise")] = 100
        ctrl = self.controller(machine)
        ctrl.step()
        self.assertEqual(machine.input_buffer[wc.feed_item_of("salt_tortoise")], wc.FEED_TOPUP_TARGET)
        self.assertEqual(self.status()["parked"], "")


class RegulatorTests(HabitatTestCase):
    def setUp(self):
        super().setUp()
        self.machine = self.habitat("salt_tortoise", established=True)
        self.machine.pop = 30000
        self.machine.rate = 100.0
        self.machine.input_buffer[wc.feed_item_of("salt_tortoise")] = 50
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
        self.machine.input_buffer[wc.feed_item_of("salt_tortoise")] = 0
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


class WrongSourceTests(HabitatTestCase):
    def setUp(self):
        super().setUp()
        self.machine = self.habitat("ferric_sea_lily", established=True)
        self.ctrl = self.controller(self.machine)

    def link(self, source_id, fluid):
        self.machine.gas_in.connected = source_id
        self.machine.gas_in.links = [FluidConnection(source_id, fluid)]

    def test_link_with_old_fluid_disconnected(self):
        self.link("gas_tank_26", "ammonia")
        self.ctrl._drop_wrong_source("gas", self.machine.gas_in, "sulfur_gas")
        self.assertEqual(self.machine.gas_in.disconnects, 1)
        self.assertIn(("purge_intake", "gas_in"), self.machine.calls)
        self.assertEqual(self.machine.intake["gas"], 0.0)

    def test_empty_tank_assigned_old_fluid_disconnected(self):
        self.world.notebook.data["fluid_routing.tank_assignments"] = {"gas_tank_26": "ammonia"}
        self.link("gas_tank_26", None)
        self.ctrl._drop_wrong_source("gas", self.machine.gas_in, "sulfur_gas")
        self.assertEqual(self.machine.gas_in.disconnects, 1)

    def test_matching_source_kept(self):
        self.world.notebook.data["fluid_routing.tank_assignments"] = {"gas_tank_28": "sulfur_gas"}
        self.link("gas_tank_28", "sulfur_gas")
        self.ctrl._drop_wrong_source("gas", self.machine.gas_in, "sulfur_gas")
        self.assertEqual(self.machine.gas_in.disconnects, 0)
        self.assertNotIn(("purge_intake", "gas_in"), self.machine.calls)


class PollTests(unittest.TestCase):
    def test_poll_tracks_feed_burn(self):
        self.assertEqual(habitat.next_poll(50, 0), habitat.POLL_MAX_S)
        self.assertEqual(habitat.next_poll(30, 15.0), habitat.POLL_MIN_S)
        self.assertGreater(habitat.next_poll(50, 1.0), habitat.next_poll(50, 15.0))


if __name__ == "__main__":
    unittest.main()
