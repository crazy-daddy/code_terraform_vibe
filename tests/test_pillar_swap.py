"""Stub tests for the pillar swap (lib/pillar_swap.py): every generator of one
pillar is undeployed, its kit and packs sold, and the other pillar's
generator deployed at the same outpost at the same tier (or the best one the
Shop sells), one machine at a time."""
import unittest

from harness import StubTestCase
from game_stubs import Commander, PressureGenerator, Shop
import pillar_swap

PRICES = {
    "temp_heater": 800, "oxygen_generator": 1000, "pressure_generator": 900,
    "heat_upgrade_pack_mk2": 12000, "oxygen_upgrade_pack_mk2": 12000, "pressure_upgrade_pack_mk2": 12000,
    "heat_upgrade_pack_mk3": 90000, "pressure_upgrade_pack_mk3": 90000,
}


class PillarSwapTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.outpost = w.add_outpost("outpost_2")
        self.shop = Shop(w, PRICES)
        w.services.update({"shop": self.shop, "commander": Commander(1000)})
        self.swapper = pillar_swap.PillarSwap()

    def heater(self, heater_id, outpost, tier=1):
        machine = self.world.add_building(heater_id, outpost, "temp_heater", PressureGenerator)
        machine.installed_tier = tier
        self.world.run_control.running.add(heater_id)
        return machine

    def of_type(self, type_id):
        return {c.id: c for c in self.world.components.values() if getattr(c, "type_id", "") == type_id}

    def state(self) -> dict:
        found = pillar_swap.swap_state()
        assert found is not None, self.debug_log()
        return found

    def test_swaps_each_heater_in_place_at_its_tier(self):
        w = self.world
        self.heater("heater_1", w.home, tier=2)
        self.heater("heater_2", self.outpost)
        self.assertTrue(pillar_swap.request_swap("heat", "o2"))
        for _ in range(3):
            self.swapper.step()
        self.assertEqual(self.state()["state"], "done", self.debug_log())
        self.assertEqual(self.of_type("temp_heater"), {})
        o2gens = self.of_type("oxygen_generator")
        by_outpost = {m.outpost.id: m.tier() for m in o2gens.values()}
        self.assertEqual(by_outpost, {w.home.id: 2, "outpost_2": 1}, self.debug_log())
        for item in ("temp_heater", "heat_upgrade_pack_mk2", "oxygen_generator", "oxygen_upgrade_pack_mk2"):
            self.assertEqual(w.inventory.count(item), 0, item)
        self.assertEqual(self.shop.sold, {"temp_heater": 2, "heat_upgrade_pack_mk2": 1})
        self.assertEqual(self.state()["done"], 2)

    def test_tier_falls_back_and_mk4_stays(self):
        w = self.world
        self.heater("heater_1", w.home, tier=3)
        self.heater("heater_2", w.home, tier=4)
        w.services["commander"].credits = 0
        pillar_swap.request_swap("heat", "o2")
        for _ in range(2):
            self.swapper.step()
        state = self.state()
        self.assertEqual(state["state"], "done", self.debug_log())
        self.assertEqual(state["kept"], ["heater_2"])
        self.assertIn("heater_2", w.components)
        (o2gen,) = self.of_type("oxygen_generator").values()
        self.assertEqual(o2gen.tier(), 2, "no Mk III oxygen pack in the Shop: Mk II")
        self.assertEqual(self.shop.sold.get("heat_upgrade_pack_mk3"), 1)

    def test_waits_for_credits_before_undeploying(self):
        w = self.world
        self.heater("heater_1", w.home)
        self.shop.prices["oxygen_generator"] = 5000
        w.services["commander"].credits = 0
        pillar_swap.request_swap("heat", "o2")
        status = self.swapper.step()
        self.assertIn("waiting for 4200 cr", status, self.debug_log())
        self.assertIn("heater_1", w.components)
        self.assertEqual(w.computer.calls, [])

    def test_one_pass_swaps_every_machine(self):
        w = self.world
        for n in range(1, 6):
            self.heater(f"heater_{n}", w.home if n % 2 else self.outpost)
        pillar_swap.request_swap("heat", "o2")
        self.swapper.step()
        self.assertEqual(self.state()["state"], "done", self.debug_log())
        self.assertEqual(len(self.of_type("oxygen_generator")), 5)
        self.assertEqual(w.inventory.count("temp_heater"), 0)

    def test_stop_ends_a_waiting_swap(self):
        w = self.world
        self.heater("heater_1", w.home)
        self.heater("heater_2", w.home, tier=2)
        self.shop.prices["pressure_upgrade_pack_mk2"] = 13000
        w.services["commander"].credits = 100
        pillar_swap.request_swap("heat", "pressure")
        status = self.swapper.step()
        self.assertIn("heater_2: waiting for 1100 cr", status, self.debug_log())
        pillar_swap.request_stop()
        self.swapper.step()
        self.assertEqual(self.state()["state"], "stopped", self.debug_log())
        self.assertEqual(len(self.of_type("pressure_generator")), 1)
        self.assertEqual(list(self.of_type("temp_heater")), ["heater_2"])

    def test_resumes_after_restart_mid_swap(self):
        w = self.world
        self.heater("heater_1", w.home, tier=2)
        pillar_swap.request_swap("heat", "o2")
        w.computer.forced_status = "under_construction"
        self.swapper._run(self.state())  # picks, then the undeploy waits
        w.computer.forced_status = None
        w.computer.undeploy("heater_1")  # undeployed, but the job never saw it
        pillar_swap.PillarSwap().step()
        self.assertEqual(self.state()["done"], 1, self.debug_log())
        self.assertEqual(self.shop.sold, {"temp_heater": 1, "heat_upgrade_pack_mk2": 1})

    def test_rejects_same_pillar_and_second_request(self):
        self.assertFalse(pillar_swap.request_swap("heat", "heat"))
        self.assertTrue(pillar_swap.request_swap("heat", "o2"))
        self.assertFalse(pillar_swap.request_swap("o2", "heat"))


if __name__ == "__main__":
    unittest.main()
