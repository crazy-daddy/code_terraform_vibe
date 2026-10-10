"""lib/building_ops.py: status table, deploy with restart adoption and attach, upgrade, retire handshake."""
import unittest

from harness import StubTestCase

import building_ops as ops
from archive import archive


class ClassifyTests(unittest.TestCase):
    def test_status_table(self):
        self.assertEqual(ops.classify("ok"), "ok")
        self.assertEqual(ops.classify("not_found"), "gone")
        for status in ("inventory_full", "cargo_present", "docked_drone", "construction_dependency"):
            self.assertEqual(ops.classify(status), "transient")
        self.assertEqual(ops.classify("no_kit"), "kit")
        self.assertEqual(ops.classify("item_not_in_inventory"), "kit")
        for status in ("deploy_limit", "wrong_biome_for_machine", "locked", "not_undeployable"):
            self.assertEqual(ops.classify(status), "fatal")


class DeployTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.outpost = self.world.add_outpost("outpost_1")
        self.ops = ops.BuildingOps()

    def job(self, job_id):
        return ops.jobs()[job_id]

    def test_waits_for_kit_then_deploys_and_attaches(self):
        job_id = ops.request_deploy("smelter", "outpost_1", "test", "factory outpost")
        self.ops.step_jobs()
        self.assertEqual(self.job(job_id)["state"], "kit")
        self.assertEqual(self.job(job_id)["status"], "no_kit")
        self.world.inventory.add("smelter", 1)
        self.ops.step_jobs()
        job = self.job(job_id)
        self.assertEqual(job["state"], "attach")
        new_id = job["machine_id"]
        self.assertIs(self.world.components[new_id].outpost, self.outpost)
        self.ops.step_jobs()
        self.assertEqual(self.job(job_id)["state"], "done")
        self.assertIn(new_id, self.world.run_control.running)

    def test_restart_adopts_instead_of_deploying_twice(self):
        job_id = ops.request_deploy("smelter", "outpost_1", "test", "why")
        self.world.inventory.add("smelter", 2)
        # A restart right after deploy(): the job still says "deploying" with the old snapshot.
        archive.transaction(ops.JOBS_KEY, {}, lambda cur: {**cur, job_id: {**cur[job_id], "state": "deploying", "known": []}})
        self.world.computer.deploy("smelter", "outpost_1")
        self.ops.step_jobs()
        deploys = [c for c in self.world.computer.calls if c[0] == "deploy"]
        self.assertEqual(len(deploys), 1)
        self.assertEqual(self.world.inventory.count("smelter"), 1)
        self.assertEqual(self.job(job_id)["state"], "attach")

    def test_scriptless_building_is_done_on_deploy(self):
        self.world.inventory.add("warehouse", 1)
        job_id = ops.request_deploy("warehouse", "outpost_1", "test", "stock")
        self.ops.step_jobs()
        self.assertEqual(self.job(job_id)["state"], "done")

    def test_fatal_refusal_blocks(self):
        self.world.inventory.add("smelter", 1)
        self.world.computer.forced_status = "deploy_limit"
        job_id = ops.request_deploy("smelter", "outpost_1", "test", "why")
        self.ops.step_jobs()
        self.assertEqual((self.job(job_id)["state"], self.job(job_id)["status"]), ("blocked", "deploy_limit"))

    def test_ref_makes_request_idempotent(self):
        a = ops.request_deploy("smelter", "outpost_1", "test", "why", ref="p1")
        b = ops.request_deploy("smelter", "outpost_1", "test", "why", ref="p1")
        c = ops.request_deploy("smelter", "outpost_1", "test", "why")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_attach_waits_for_status_key(self):
        self.world.inventory.add("smelter", 1)
        job_id = ops.request_deploy("smelter", "outpost_1", "test", "why", status_key="smelter.status")
        self.ops.step_jobs()
        self.ops.step_jobs()
        self.assertEqual(self.job(job_id)["state"], "attach")
        archive.set_entry("smelter.status", self.job(job_id)["machine_id"], {"tick": 1})
        self.ops.step_jobs()
        self.assertEqual(self.job(job_id)["state"], "done")


class UpgradeTests(StubTestCase):
    def test_pack_from_inventory(self):
        from game_stubs import PressureGenerator
        gen = self.world.add_building("pressure_generator_1", self.world.home, "pressure_generator", PressureGenerator)
        job_id = ops.request_upgrade(gen.id, "pressure_upgrade_pack_mk2", "test", "why")
        o = ops.BuildingOps()
        o.step_jobs()
        self.assertEqual(ops.jobs()[job_id]["state"], "kit")
        self.world.inventory.add("pressure_upgrade_pack_mk2", 1)
        o.step_jobs()
        self.assertEqual(ops.jobs()[job_id]["state"], "done")
        self.assertEqual(gen.tier(), 2)


class RetireTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.machine = self.world.add_building("refiner_1", self.world.home, "refiner")
        self.ops = ops.BuildingOps()

    def test_handshake_waits_for_ready(self):
        job_id = ops.request_retire("refiner_1", "test", "orders done")
        self.assertTrue(ops.retire_requested("refiner_1"))
        self.ops.step_jobs()
        self.assertIn("refiner_1", self.world.components)
        self.assertIn("refiner_1", self.world.run_control.running)  # restarted so it can empty itself
        ops.mark_retire_ready("refiner_1")
        self.ops.step_jobs()
        self.assertNotIn("refiner_1", self.world.components)
        self.assertEqual(self.world.inventory.count("refiner"), 1)
        self.assertEqual(ops.jobs()[job_id]["state"], "done")
        self.assertFalse(ops.retire_requested("refiner_1"))

    def test_no_handshake_undeploys_and_retries_transient(self):
        self.world.computer.forced_status = "inventory_full"
        job_id = ops.request_retire("refiner_1", "test", "why", handshake=False)
        self.ops.step_jobs()
        self.assertEqual((ops.jobs()[job_id]["state"], ops.jobs()[job_id]["status"]), ("undeploying", "inventory_full"))
        self.world.computer.forced_status = None
        self.ops.step_jobs()
        self.assertEqual(ops.jobs()[job_id]["state"], "done")

    def test_undeploy_warns_once_per_status(self):
        warned = {}
        self.world.computer.forced_status = "not_undeployable"
        ops.undeploy("refiner_1", warned=warned)
        ops.undeploy("refiner_1", warned=warned)
        warns = [m for level, m in self.world.console.lines if level == "warn" and "undeploy" in m]
        self.assertEqual(len(warns), 1)


if __name__ == "__main__":
    unittest.main()
