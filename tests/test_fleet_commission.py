"""Stub tests for the COMMISSION card coordinator (lib/fleet_commission.py):
Pioneers deploy at home with a chosen HOME_BASE, drones are crafted into
Inventory and deployed at the picked outpost."""
import unittest

from harness import StubTestCase
from game_stubs import Recipe, Result
import fleet_commission
import fleet_status
import pioneer_commission
import drone_upgrade
import production
import warehouse_upgrade

DRONE_RECIPES = [
    Recipe(f"craft_{item}", {"iron_ingot": 1}, item)
    for item in ("drone_small", "drone_medium", "electric_thruster", "battery_pack", "cargo_pod_small", "cargo_pod_medium", "portable_bio_extractor")
]


class Ref:
    def __init__(self, ref_id, kind):
        self.id = ref_id
        self.kind = kind


class Fleet:
    def __init__(self):
        self.pioneers = []
        self.drone_refs = []

    def vehicles(self):
        return [Ref(p, "pioneer") for p in self.pioneers]

    def drones(self):
        return list(self.drone_refs)


class DeployResult(Result):
    def __init__(self, status="ok", machine_id=None):
        super().__init__(status)
        self.machine_id = machine_id


class Computer:
    def __init__(self, world, fleet):
        self.world = world
        self.fleet = fleet
        self.calls = []
        self.next_status = "ok"

    def deploy(self, item_id, outpost=None):
        self.calls.append((item_id, outpost))
        if self.next_status != "ok":
            return DeployResult(self.next_status)
        if self.world.inventory.count(item_id) <= 0:
            return DeployResult("no_kit")
        self.world.inventory.remove(item_id, 1)
        if item_id == "pioneer":
            new_id = f"pioneer_{len(self.fleet.pioneers) + 1}"
            self.fleet.pioneers.append(new_id)
        else:
            new_id = f"drone_{len(self.fleet.drone_refs) + 1}"
            self.fleet.drone_refs.append(Ref(new_id, item_id))
        return DeployResult("ok", new_id)


class RunControl:
    def start(self, machine_id):
        return Result("ok")


class CatalogueEntry:
    def __init__(self, item_id, cost):
        self.id = item_id
        self.cost = cost


class Shop:
    def __init__(self, world, items):
        self.world = world
        self.items = items

    def get_catalogue(self):
        return [CatalogueEntry(i, 10) for i in self.items]

    def buy(self, item_id, n):
        self.world.inventory.add(item_id, n)
        return Result("ok")


class Commander:
    def get_credits(self):
        return warehouse_upgrade.WAREHOUSE_UPGRADE_CREDIT_RESERVE * 10


PIONEER_SHOP = ["pioneer", "nav_module", "drill_module", "battery_holder_small", "cargo_rack_small", "portable_battery", "portable_bin"]


class CommissionTestCase(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.fleet = Fleet()
        self.computer = Computer(w, self.fleet)
        w.services.update({
            "fleet": self.fleet, "computer": self.computer, "run_control": RunControl(),
            "shop": Shop(w, PIONEER_SHOP), "commander": Commander(),
        })
        self.coordinator = fleet_commission.FleetCommissionCoordinator()

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
        self.assertEqual(self.computer.calls, [("pioneer", None)], self.debug_log())
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
        self.assertEqual(self.computer.calls, [("drone_medium", "outpost_2")])
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
        self.computer.next_status = "drone_station_full"
        self.steps(3)
        self.assertEqual(self.job(job_id)["state"], "deploying")
        self.computer.next_status = "missing_drone_station"
        self.steps(1)
        self.assertEqual(self.job(job_id)["state"], "blocked")

    def test_cancel_withdraws_order(self):
        job_id = fleet_commission.queue_drone("miner")
        self.steps(1)
        self.assertIn("fleet_commission", self.orders())
        self.assertTrue(fleet_commission.cancel_job(job_id))
        self.steps(1)
        self.assertNotIn("fleet_commission", self.orders())

    def test_drone_job_does_not_wait_behind_pioneer(self):
        fleet_commission.queue_pioneer("hauler")
        drone_job = fleet_commission.queue_drone("hauler")
        self.steps(1)
        self.assertEqual(self.job(drone_job)["state"], "crafting")


if __name__ == "__main__":
    unittest.main()
