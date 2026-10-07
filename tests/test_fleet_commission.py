"""Stub tests for the FLEET card's Commission tab coordinator (lib/fleet_commission.py):
Pioneers deploy at home with a chosen HOME_BASE, drones are crafted into
Inventory and deployed at the picked outpost."""
import unittest

from harness import StubTestCase
from game_stubs import Commander, Recipe, Shop
import fleet_commission
import fleet_status
import pioneer_commission
import drone_upgrade
import production
import cash
import logistics_requests

DRONE_RECIPES = [
    Recipe(f"craft_{item}", {"iron_ingot": 1}, item)
    for item in ("drone_small", "drone_medium", "electric_thruster", "battery_pack", "cargo_pod_small", "cargo_pod_medium", "portable_bio_extractor")
]


PIONEER_SHOP = ["pioneer", "nav_module", "drill_module", "battery_holder_small", "cargo_rack_small", "portable_battery", "portable_bin"]


class CommissionTestCase(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        w.add_outpost("outpost_2")
        self.computer = w.computer
        w.services.update({"shop": self.shop(PIONEER_SHOP), "commander": Commander(cash.LEGACY_RESERVE * 10)})
        self.coordinator = fleet_commission.FleetCommissionCoordinator()

    def shop(self, items):
        return Shop(self.world, {i: 10 for i in items})

    def steps(self, n):
        for _ in range(n):
            self.coordinator.step(self.world.clock.now)
            self.world.clock.now += 1

    def find_job(self, job_id):
        return next((j for j in pioneer_commission.commission_state().get("jobs") or [] if j.get("id") == job_id), None)

    def job(self, job_id) -> dict:
        found = self.find_job(job_id)
        assert found is not None, f"job {job_id} gone: {self.debug_log()}"
        return found

    def orders(self) -> dict:
        return self.world.notebook.get(production.UPGRADE_ORDERS_KEY) or {}

    def lineage(self, drone_id) -> dict:
        entry = drone_upgrade.lineage_entry(drone_id)
        assert entry is not None
        return entry


class PioneerCommissionTests(CommissionTestCase):
    def test_deploys_at_home_and_records_home_base(self):
        job_id = fleet_commission.queue_pioneer("hauler", "outpost_2")
        self.steps(3)  # queued -> buying -> deploying -> attach
        self.assertEqual(self.computer.calls, [("deploy", "pioneer", None)], self.debug_log())
        job = self.job(job_id)
        self.assertEqual(job["state"], "attach")
        lineage = pioneer_commission.commission_state()["lineage"][job["new_id"]]
        self.assertEqual(lineage["home_base"], "outpost_2")

    def test_waits_for_matching_home_before_done(self):
        job_id = fleet_commission.queue_pioneer("hauler", "outpost_2")
        self.steps(3)
        new_id = self.job(job_id)["new_id"]
        fleet_status.publish(new_id, {"name": new_id, "state": "FITTING", "home": "outpost_home", "tick": 1})
        self.steps(1)  # attach -> fitting
        pioneer_commission.update_commission(lambda s: s["lineage"][new_id].update({"fitted": True}))
        self.steps(1)
        self.assertIsNotNone(self.find_job(job_id))
        self.assertIn("HOME_BASE", pioneer_commission.commission_state()["status"])
        fleet_status.publish(new_id, {"name": new_id, "state": "IDLE", "home": "outpost_2", "tick": 2})
        self.steps(1)
        self.assertIsNone(self.find_job(job_id))

    def test_home_outpost_stored_as_none(self):
        job_id = fleet_commission.queue_pioneer("miner", "outpost_home")
        self.assertIsNone(self.job(job_id)["home_base"])


class DroneCommissionTests(CommissionTestCase):
    def setUp(self):
        super().setUp()
        self.world.add_fabricator("fabricator_1", self.world.home, DRONE_RECIPES)

    def test_orders_best_kit_then_deploys_at_outpost(self):
        job_id = fleet_commission.queue_drone("hauler", "outpost_2")
        self.steps(2)  # queued -> crafting, then waiting
        job = self.job(job_id)
        self.assertEqual(job["state"], "crafting", self.debug_log())
        self.assertEqual(job["spec"]["kind"], "drone_medium")
        self.assertEqual(job["spec"]["modules"], ["electric_thruster", "battery_pack", "cargo_pod_medium", "cargo_pod_medium"])
        order = self.orders()["fleet_commission"]
        self.assertEqual(order, {"drone_medium": 1, "electric_thruster": 1, "battery_pack": 1, "cargo_pod_medium": 2})

        for item_id, n in order.items():
            self.world.inventory.add(item_id, n)
        self.steps(2)  # crafting -> deploying -> attach
        self.assertEqual(self.computer.calls, [("deploy", "drone_medium", "outpost_2")])
        self.assertNotIn("fleet_commission", self.orders())
        job = self.job(job_id)
        self.assertEqual(job["state"], "attach")
        lineage = self.lineage(job["new_id"])
        self.assertEqual(lineage["job"], job_id)
        self.assertEqual(lineage["params"]["HOME_DEPOT"], "outpost_2")
        self.assertEqual(drone_upgrade.inherited_params(job["new_id"])["HOME_DEPOT"], "outpost_2")

        fleet_status.publish(job["new_id"], {"name": job["new_id"], "state": "AWAITING_MODULES", "tick": 1})
        drone_upgrade.update_fleet_upgrade(lambda s: s["lineage"][job["new_id"]].update({"fitted": True}))
        self.steps(2)
        self.assertIsNone(self.find_job(job_id))

    def test_full_depot_waits_and_missing_depot_blocks(self):
        job_id = fleet_commission.queue_drone("hauler")
        self.steps(1)
        for item_id, n in fleet_commission.drone_spec_parts(self.job(job_id)["spec"]).items():
            self.world.inventory.add(item_id, n)
        self.computer.forced_status = "drone_station_full"
        self.steps(3)
        self.assertEqual(self.job(job_id)["state"], "deploying")
        self.computer.forced_status = "missing_drone_station"
        self.steps(1)
        self.assertEqual(self.job(job_id)["state"], "blocked")

    def test_cancel_withdraws_order(self):
        job_id = fleet_commission.queue_drone("miner")
        self.steps(1)
        self.assertIn("fleet_commission", self.orders())
        self.assertTrue(fleet_commission.cancel_job(job_id))
        self.steps(1)
        self.assertNotIn("fleet_commission", self.orders())

    def test_shop_only_part_bought_through_cash_manager(self):
        w = self.world
        w.components.clear()
        w.add_fabricator("fabricator_1", w.home, [r for r in DRONE_RECIPES if r.output_item != "portable_bio_extractor"])
        w.services["shop"] = self.shop(PIONEER_SHOP + ["portable_bio_extractor"])
        job_id = fleet_commission.queue_drone("miner")
        self.steps(1)
        spec = self.job(job_id)["spec"]
        self.assertEqual(spec["buy"], ["portable_bio_extractor"])
        self.assertNotIn("portable_bio_extractor", self.orders()["fleet_commission"])
        self.steps(1)  # crafting: buys the extractor, waits on the Fabricator for the rest
        self.assertEqual(w.inventory.count("portable_bio_extractor"), 1, self.debug_log())
        spent = [e[1:] for e in (w.notebook.get(cash.BUDGET_KEY) or {}).get("spent", [])]
        self.assertIn(["drone_commission", 10], spent)
        self.assertEqual(self.job(job_id)["state"], "crafting")

    def test_shop_only_part_waits_for_cash(self):
        w = self.world
        w.components.clear()
        w.add_fabricator("fabricator_1", w.home, [r for r in DRONE_RECIPES if r.output_item != "portable_bio_extractor"])
        w.services["shop"] = self.shop(PIONEER_SHOP + ["portable_bio_extractor"])
        w.services["commander"] = Commander(5)
        job_id = fleet_commission.queue_drone("miner")
        self.steps(2)
        self.assertEqual(w.inventory.count("portable_bio_extractor"), 0)
        self.assertIn("waiting for credits", pioneer_commission.commission_state()["status"])

    def test_kit_in_inventory_deploys_in_one_pass(self):
        job_id = fleet_commission.queue_drone("hauler", "outpost_2")
        for item_id, n in {"drone_medium": 1, "electric_thruster": 1, "battery_pack": 1, "cargo_pod_medium": 2}.items():
            self.world.inventory.add(item_id, n)
        self.assertTrue(fleet_commission.commission_fast())
        self.steps(1)  # queued -> crafting -> deploying -> attach, script started
        self.assertEqual(self.job(job_id)["state"], "attach", self.debug_log())
        self.assertEqual(self.computer.calls, [("deploy", "drone_medium", "outpost_2")])
        self.assertTrue(fleet_commission.commission_fast())

    def test_part_built_remotely_awaits_haul_home(self):
        w = self.world
        job_id = fleet_commission.queue_drone("hauler")
        self.steps(1)
        order = self.orders()["fleet_commission"]
        w.add_warehouse("warehouse_2", w.add_outpost("outpost_2"), {"drone_medium": 1})
        for item_id, n in order.items():
            if item_id != "drone_medium":
                w.inventory.add(item_id, n)
        self.steps(1)
        self.assertEqual(self.job(job_id)["state"], "crafting")
        status = pioneer_commission.commission_state()["status"]
        self.assertIn("awaiting haul home (1x drone_medium)", status)
        self.assertNotIn("crafting (", status)

        logistics_requests.reserve_pickup("pioneer_1", "home", "drone_medium", 1, w.clock.now, source_id="outpost_2")
        self.steps(1)
        self.assertIn("hauling home (1x drone_medium)", pioneer_commission.commission_state()["status"])

    def test_unhauled_part_warns_once(self):
        w = self.world
        fleet_commission.queue_drone("hauler")
        self.steps(1)
        w.add_warehouse("warehouse_2", w.add_outpost("outpost_2"), {"drone_medium": 1})
        self.steps(1)
        w.clock.now += fleet_commission.HAUL_HOME_WARN_TICKS
        self.steps(2)
        self.assertEqual(self.debug_log().count("not hauled home"), 1, self.debug_log())

    def test_crafting_wait_is_not_fast(self):
        fleet_commission.queue_drone("hauler")
        self.steps(1)
        self.assertFalse(fleet_commission.commission_fast())

    def test_drone_job_does_not_wait_behind_pioneer(self):
        fleet_commission.queue_pioneer("hauler")
        drone_job = fleet_commission.queue_drone("hauler")
        self.steps(1)
        self.assertEqual(self.job(drone_job)["state"], "crafting")


if __name__ == "__main__":
    unittest.main()
