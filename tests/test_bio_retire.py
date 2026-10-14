"""Stub tests for the per-biome bio chain retirement (lib/bio_retire.py)."""

import bio_retire
import biomass_retire
from game_stubs import BioMachine, BioOrder
from harness import StubTestCase


class BioRetirementTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self._discover = bio_retire.fluid_routing.discover_network_buildings
        bio_retire.fluid_routing.discover_network_buildings = lambda type_id, resolve=True: [
            (m, m.outpost.id)
            for m in list(self.world.components.values())
            if isinstance(m, BioMachine) and m.type_id == type_id
        ]
        self.world.services["shop"].prices.update({"bio_lab": 1000, "bio_exchange": 4000, "bio_caster": 9000})
        self.volcanic = self.world.add_outpost("outpost_v", biome="volcanic")
        self.coastal = self.world.add_outpost("outpost_c", biome="coastal")

    def tearDown(self):
        bio_retire.fluid_routing.discover_network_buildings = self._discover
        super().tearDown()

    def chain(self, orders):
        self.world.add_bio_machine("bio_exchange_v", self.volcanic, "bio_exchange").bio_orders = orders
        self.world.add_bio_machine("bio_lab_v", self.volcanic, "bio_lab")
        self.world.add_bio_machine("bio_caster_v", self.volcanic, "bio_caster")
        self.world.add_bio_machine("bio_exchange_c", self.coastal, "bio_exchange").bio_orders = orders
        self.world.add_bio_machine("bio_lab_c", self.coastal, "bio_lab")

    def test_incomplete_biome_keeps_its_chain(self):
        self.chain([BioOrder("o1", "volcanic", "complete"), BioOrder("o2", "volcanic", "active")])
        self.assertEqual(bio_retire.BioRetirement().step(0), "no biome complete")
        self.assertEqual(self.world.computer.calls, [])
        self.assertFalse(bio_retire.biome_retired("volcanic"))

    def test_complete_biome_sold_other_biome_kept(self):
        self.chain(
            [BioOrder("o1", "volcanic", "complete"), BioOrder("o2", "volcanic", "complete"), BioOrder("o3", "coastal")]
        )
        bio_retire.BioRetirement().step(0)
        self.assertEqual(
            sorted(m for _, m in self.world.computer.calls), ["bio_caster_v", "bio_exchange_v", "bio_lab_v"]
        )
        self.assertEqual(self.world.services["shop"].sold, {"bio_exchange": 1, "bio_lab": 1, "bio_caster": 1})
        self.assertTrue(bio_retire.biome_retired("volcanic"))
        self.assertFalse(bio_retire.biome_retired("coastal"))

    def test_done_biome_stays_latched_and_refusal_retried(self):
        self.chain([BioOrder("o1", "volcanic", "complete")])
        self.world.computer.forced_status = "cargo_present"
        retirement = bio_retire.BioRetirement()
        self.assertIn("draining", retirement.step(0))
        self.assertEqual(self.world.services["shop"].sold, {})
        # The volcanic Exchange is gone and the coastal one lists no volcanic order.
        del self.world.components["bio_exchange_v"]
        self.world.components["bio_exchange_c"].bio_orders = []
        self.world.computer.forced_status = None
        self.assertEqual(retirement.step(0), "done volcanic; chains retired")
        self.assertEqual(self.world.services["shop"].sold, {"bio_lab": 1, "bio_caster": 1})

    def test_not_found_counts_as_gone_not_sold(self):
        self.chain([BioOrder("o1", "volcanic", "complete")])
        self.world.computer.forced_status = "not_found"
        self.assertEqual(bio_retire.BioRetirement().step(0), "done volcanic; chains retired")
        self.assertEqual(self.world.services["shop"].sold, {})
        self.assertEqual(bio_retire.archive.get(bio_retire.RETIRE_KEY, {}).get("last_sale"), "")

    def test_refused_sale_kept_and_retried(self):
        self.chain([BioOrder("o1", "volcanic", "complete")])
        shop = self.world.services["shop"]
        shop.not_sellable = {"bio_lab"}
        retirement = bio_retire.BioRetirement()
        self.assertEqual(retirement.step(0), "done volcanic; unsold bio_lab")
        self.assertEqual(shop.sold, {"bio_exchange": 1, "bio_caster": 1})
        shop.not_sellable = set()
        self.assertEqual(retirement.step(0), "done volcanic; chains retired")
        self.assertEqual(shop.sold, {"bio_exchange": 1, "bio_caster": 1, "bio_lab": 1})
        self.assertEqual(bio_retire.archive.get(bio_retire.RETIRE_KEY, {})["unsold"], [])

    def test_sold_lab_and_caster_withdraw_requests(self):
        self.chain([BioOrder("o1", "volcanic", "complete")])
        cleared = []
        original = bio_retire.logistics_requests.clear_requests
        bio_retire.logistics_requests.clear_requests = lambda requester, outpost_id=None: cleared.append(
            (requester, outpost_id)
        )
        try:
            bio_retire.BioRetirement().step(0)
        finally:
            bio_retire.logistics_requests.clear_requests = original
        self.assertEqual(sorted(cleared), [("bio_caster", "outpost_v"), ("bio_reagents", "outpost_v")])

    def test_outpost_without_biome_never_retires(self):
        self.world.notebook.set(bio_retire.RETIRE_KEY, {"done": ["volcanic"]})
        blank = self.world.add_outpost("outpost_x")
        lab = self.world.add_bio_machine("bio_lab_x", blank, "bio_lab")
        lab.specimen = object()
        self.assertFalse(bio_retire.retire_pass(lab, "bio_lab"))
        self.assertEqual(lab.calls, [])

    def test_retire_pass_drains_once_biome_done(self):
        lab = self.world.add_bio_machine("bio_lab_v", self.volcanic, "bio_lab")
        lab.specimen = object()
        self.assertFalse(bio_retire.retire_pass(lab, "bio_lab"))
        self.world.notebook.set(bio_retire.RETIRE_KEY, {"done": ["volcanic"]})
        # The script's copy of the done list is reused for RETIRE_CHECK_TICKS.
        self.assertFalse(bio_retire.retire_pass(lab, "bio_lab"))
        self.world.clock.now += bio_retire.RETIRE_CHECK_TICKS
        self.assertTrue(bio_retire.retire_pass(lab, "bio_lab"))
        self.assertEqual(lab.calls, ["discard"])

    def test_drain_per_machine_type(self):
        collector = self.world.add_bio_machine("bio_collector_v", self.volcanic, "bio_collector")
        collector.cargo = object()
        exchange = self.world.add_bio_machine("bio_exchange_v", self.volcanic, "bio_exchange")
        exchange.active = BioOrder("o1", "volcanic", "active")
        caster = self.world.add_bio_machine("bio_caster_v", self.volcanic, "bio_caster")
        caster.crucible_materials = {"basalt_glass": 2}
        conditioner = self.world.add_bio_machine("bio_conditioner_v", self.volcanic, "bio_conditioner")
        luminizer = self.world.add_bio_machine("bio_luminizer_v", self.volcanic, "bio_luminizer")
        luminizer.chamber = object()
        lab = self.world.add_bio_machine("bio_lab_v", self.volcanic, "bio_lab")
        lab.loaded_reagents = {"cryo_solvent": 3}
        for machine in (collector, exchange, caster, conditioner, luminizer, lab):
            bio_retire.drain(machine, machine.type_id)
        self.assertEqual(collector.calls, ["discard"])
        self.assertEqual(exchange.calls, ["clear_order"])
        self.assertEqual(caster.calls, ["eject"])
        self.assertEqual(conditioner.calls, [])
        self.assertEqual(luminizer.calls, ["discard"])
        self.assertEqual(lab.calls, ["unload_reagents"])

    def test_drain_discards_lab_specimen(self):
        lab = self.world.add_bio_machine("bio_lab_v", self.volcanic, "bio_lab")
        lab.specimen = object()
        bio_retire.drain(lab, "bio_lab")
        self.assertEqual(lab.calls, ["discard"])
        self.assertIsNone(lab.specimen)


class BiomassSaleTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.world.add_outpost("outpost_home", is_home=True)
        self.world.services["shop"].prices.update({"biomass_mixer": 60000, "biomass_mixer_upgrade_pack_mk2": 90000})

    def test_refused_undeploy_stays_with_reason(self):
        self.world.add_building("biomass_mixer_1", self.home, "biomass_mixer")
        self.world.computer.forced_status = "inventory_full"
        machines = {"biomass_mixer_1": {"type": "biomass_mixer", "tier": 1, "ready": True, "why": "ready"}}
        self.assertEqual(biomass_retire.sell_ready_machines(machines), ("", []))
        self.assertEqual(machines["biomass_mixer_1"]["why"], "undeploy inventory_full")

    def test_refused_sale_kept_as_unsold(self):
        self.world.add_building("biomass_mixer_1", self.home, "biomass_mixer")
        shop = self.world.services["shop"]
        shop.not_sellable = {"biomass_mixer"}
        machines = {"biomass_mixer_1": {"type": "biomass_mixer", "tier": 1, "ready": True, "why": "ready"}}
        self.assertEqual(biomass_retire.sell_ready_machines(machines), ("", ["biomass_mixer"]))
        self.assertEqual(machines, {})
        shop.not_sellable = set()
        summary, unsold = biomass_retire.sell_ready_machines({}, ["biomass_mixer"])
        self.assertEqual((summary, unsold), ("sold 1 item(s) for 60000 cr", []))
