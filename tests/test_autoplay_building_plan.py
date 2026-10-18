"""autoplay/lib/building_plan.py: providers, cap gate, merge, and the propose -> approve -> job flow."""

import unittest

import building_ops
import building_plan as bp
from archive import archive
from harness import StubTestCase


def _outpost(oid="outpost_1", roles=(), types=None, used=0, capacity=20, home=False):
    return {
        "id": oid,
        "roles": list(roles),
        "types": dict(types or {}),
        "used": used,
        "capacity": capacity,
        "home": home,
    }


def _snap(outposts, kits=("smelter", "fabricator", "warehouse", "drone_station_kit"), per=5, stock=None):
    return {"outposts": outposts, "kits": set(kits), "per_warehouse": per, "stock": stock or {}}


class ProviderTests(unittest.TestCase):
    def test_role_gap_picks_unlocked_alternative_and_skips_warehouses(self):
        wants = bp.role_wants(_outpost(roles=["smelter", "mining"]), {"smelter"})
        self.assertEqual([w[0] for w in wants], ["smelter"])

    def test_storage_sized_by_stock_slots_and_kind(self):
        entry = _outpost(roles=["smelter"], types={"warehouse": 1})
        snap = _snap([entry], stock={"smelter": [f"item{i}" for i in range(12)]})
        self.assertEqual(bp.storage_wants(entry, snap), [("warehouse", 2, "stock needs 12 slots, 5 standing")])
        snap["per_warehouse"] = 15
        snap["kits"].add("large_warehouse")
        self.assertEqual(bp.storage_wants(entry, snap)[0][:2], ("large_warehouse", 1))

    def test_no_storage_before_warehouse_kit(self):
        entry = _outpost(roles=["storage"])
        self.assertEqual(bp.storage_wants(entry, _snap([entry], kits=("smelter",))), [])

    def test_storage_role_gets_one_warehouse(self):
        entry = _outpost(roles=["storage"])
        self.assertEqual(bp.storage_wants(entry, _snap([entry]))[0][:2], ("warehouse", 1))

    def test_cap_gate_only_with_penalized_machine(self):
        full = _outpost(types={"smelter": 1}, used=20)
        self.assertIsNotNone(bp.cap_block(full, "warehouse", 1))
        self.assertIsNone(bp.cap_block(_outpost(types={"warehouse": 4}, used=20), "warehouse", 1))
        self.assertIsNone(bp.cap_block(full, "warehouse", 0))

    def test_refiner_ready_becomes_retire(self):
        out = bp.fresh_proposals(
            _snap([]), {}, {"refiner_1": {"retire": "ready", "outpost": "outpost_2"}, "refiner_2": {"retire": ""}}
        )
        self.assertEqual(list(out), ["retire:refiner_1"])

    def test_reserve_open_holds_slots_of_pending_deploys(self):
        snap = {
            "outposts": [
                {"id": "o1", "used": 19, "capacity": 20, "types": {}},
                {"id": "o2", "used": 3, "capacity": 20, "types": {}},
            ]
        }
        proposals = {
            "deploy:o1:battery": {
                "kind": "deploy",
                "outpost": "o1",
                "type_id": "battery",
                "count": 2,
                "status": "queued",
                "jobs": ["deploy_1", "deploy_2"],
            },
            "deploy:o1:smelter": {
                "kind": "deploy",
                "outpost": "o1",
                "type_id": "smelter",
                "count": 1,
                "status": "proposed",
            },
            "deploy:o2:warehouse": {
                "kind": "deploy",
                "outpost": "o2",
                "type_id": "warehouse",
                "count": 1,
                "status": "approved",
            },
        }
        jobs = {"deploy_1": {"state": "done"}, "deploy_2": {"state": "kit"}}
        out = {e["id"]: e for e in bp.reserve_open(snap, proposals, jobs)["outposts"]}
        self.assertEqual((out["o1"]["used"], out["o1"]["reserved"]), (20, {"battery": 1}))
        self.assertEqual((out["o2"]["used"], out["o2"]["reserved"]), (4, {"warehouse": 1}))
        self.assertEqual(snap["outposts"][0]["used"], 19)
        self.assertIs(bp.reserve_open(snap, {}, {}), snap)

    def test_merge_keeps_blocked_of_queued(self):
        old = {"deploy:o:battery": {"kind": "deploy", "status": "queued", "blocked": None, "jobs": ["deploy_1"]}}
        out = bp.merge(old, {"deploy:o:battery": {"kind": "deploy", "count": 1, "blocked": "over cap"}}, 10)
        self.assertIsNone(out["deploy:o:battery"]["blocked"])

    def test_merge_keeps_status_and_holds_rejected(self):
        fresh = {
            "deploy:o:smelter": {"kind": "deploy", "count": 1},
            "deploy:o:fabricator": {"kind": "deploy", "count": 1},
        }
        old = {
            "deploy:o:smelter": {"status": "rejected", "tick": 100},
            "deploy:o:gone": {"status": "proposed", "tick": 1},
        }
        out = bp.merge(old, fresh, 200)
        self.assertEqual(out["deploy:o:smelter"]["status"], "rejected")
        self.assertEqual(out["deploy:o:fabricator"]["status"], "proposed")
        self.assertNotIn("deploy:o:gone", out)
        later = bp.merge(old, fresh, 100 + bp.REJECT_HOLD_TICKS)
        self.assertEqual(later["deploy:o:smelter"]["status"], "proposed")


class FlowTests(StubTestCase):
    def test_propose_approve_deploy(self):
        self.world.add_outpost("outpost_1")
        planner = bp.BuildingPlanner(bp.building_ops.log)
        snap = _snap([_outpost(roles=["smelter"])])
        self.assertEqual(planner.run_pass(snap), "waiting")
        pid = "deploy:outpost_1:smelter"
        self.assertEqual(bp.load()[pid]["status"], "proposed")
        self.assertEqual(bp.load()[pid]["kit_source"], "available")
        self.assertTrue(bp.answer(pid, True))
        self.world.inventory.add("smelter", 1)
        self.assertEqual(planner.run_pass(snap), "working")
        job_id = bp.load()[pid]["jobs"][0]
        self.assertEqual(building_ops.jobs()[job_id]["state"], "attach")
        planner.run_pass(snap)
        self.assertNotIn(pid, bp.load())
        self.assertEqual(building_ops.jobs()[job_id]["state"], "done")

    def test_blocked_proposal_cannot_be_approved(self):
        planner = bp.BuildingPlanner(bp.building_ops.log)
        planner.run_pass(_snap([_outpost(roles=["factory"], types={"smelter": 1}, used=20)]))
        pid = "deploy:outpost_1:fabricator"
        self.assertTrue(bp.load()[pid]["blocked"])
        self.assertFalse(bp.answer(pid, True))
        self.assertTrue(bp.answer(pid, False))
        self.assertEqual(archive.get(bp.PROPOSALS_KEY)[pid]["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
