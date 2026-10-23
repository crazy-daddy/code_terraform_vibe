"""lib/machine_pack_upgrade.py: Fabricator-then-Smelter pack ladder, refusal sit-out, Oil Pump install planning."""

from unittest import mock

import machine_pack_upgrade as mpu
from archive import archive
from drone_upgrade import update_fleet_upgrade
from game_stubs import FABRICATOR_RECIPES, OilPump, Recipe
from harness import StubTestCase
from parking_client import PARKED_KEY
from production import ORDERS_KEY

PACK_RECIPES = [
    Recipe("craft_fabricator_pack_mk2", {"machine_frame": 2}, "fabricator_upgrade_pack_mk2"),
    Recipe("craft_smelter_pack_mk2", {"machine_frame": 2}, "smelter_upgrade_pack_mk2"),
]
PUMP_RECIPE = Recipe("craft_oil_pump_pack_mk2", {"machine_frame": 2}, "oil_pump_upgrade_pack_mk2")


class MachinePackUpgradeTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.world.add_outpost("base", is_home=True)
        self.fab = self.world.add_fabricator("fabricator_1", self.home, FABRICATOR_RECIPES + PACK_RECIPES)
        self.smelter = self.world.add_smelter("smelter_1", self.home)
        self.upgrader = mpu.MachinePackUpgrader()

    def order(self):
        return (archive.get(ORDERS_KEY, {}) or {}).get(mpu.REQUESTER)

    def test_fabricators_before_smelters(self):
        self.upgrader.step(0)
        self.assertEqual(set(self.order() or {}) - {"@tick", "@site", "@stale"}, {"fabricator_upgrade_pack_mk2"})
        self.world.inventory.add("fabricator_upgrade_pack_mk2", 1)
        self.upgrader.step(10)
        self.assertEqual(self.fab.tier(), 2)
        self.assertIn("smelter_upgrade_pack_mk2", self.order() or {})
        self.world.inventory.add("smelter_upgrade_pack_mk2", 1)
        text = self.upgrader.step(20)
        self.assertEqual(self.smelter.tier(), 2)
        self.assertIsNone(self.order())
        self.assertIn("up to date", text)

    def test_refused_machine_sits_out(self):
        self.world.inventory.add("fabricator_upgrade_pack_mk2", 1)
        self.world.computer.forced_status = "not_enough_power"
        self.upgrader.step(0)
        self.world.computer.forced_status = None
        self.assertEqual(self.fab.tier(), 1)
        # The ladder moves on to the Smelter while the Fabricator sits out.
        self.assertIn("smelter", self.upgrader.step(10))
        self.upgrader.step(mpu.REFUSED_RETRY_TICKS + 10)
        self.assertEqual(self.fab.tier(), 2)

    def test_apply_that_raises_waits_without_a_refusal(self):
        with mock.patch.object(self.world.computer, "upgrade", side_effect=RuntimeError("boom")):
            self.assertFalse(
                self.upgrader._apply(self.world.computer, "fabricator_upgrade_pack_mk2", "fabricator_1", 0)
            )
        self.assertEqual(self.upgrader._refused(0), {})

    def test_switch_off_clears_order(self):
        self.upgrader.step(0)
        self.assertIsNotNone(self.order())
        update_fleet_upgrade(lambda s: s.update({"enabled": False}))
        self.assertEqual(self.upgrader.step(10), "disabled")
        self.assertIsNone(self.order())

    def test_plans_one_oil_pump_install_at_a_time(self):
        self.fab._recipes.append(PUMP_RECIPE)
        self.world.add_extractor("oil_pump_1", "oil_pump", cls=OilPump)
        self.world.add_extractor("oil_pump_2", "oil_pump", cls=OilPump)
        bp = self.world.services["construction_blueprint"]
        self.world.add_pioneer("pioneer_1")
        self.world.run_control.states["pioneer_1"] = "paused"
        archive.set(PARKED_KEY, {"pioneer_1": {"kind": "pioneer", "mode": "paused", "since": 0, "role": "builder"}})
        self.upgrader.step(0)
        self.assertNotIn("pioneer_1", archive.get(PARKED_KEY, {}))
        self.upgrader.step(10)
        upgrades = [j for j in bp.pending if j.kind == "upgrade"]
        self.assertEqual([j.required_item for j in upgrades], ["oil_pump_upgrade_pack_mk2"])
