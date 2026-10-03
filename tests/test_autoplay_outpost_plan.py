"""Tests for autoplay/lib/outpost_plan.py (founding planner proposals: merge, holds, marker approval, designation)."""
import unittest
from types import SimpleNamespace as NS

import harness  # noqa: F401  (puts the lib/ folders on sys.path)
import outpost_plan as plan_
import outpost_needs
import autoplay_roles as roles
from game_stubs import Shop
from tree_console import TreeConsole

TICK = 1000
HOME = {"id": "home", "x": -10.0, "y": 10.0, "biome": "frozen", "home": True, "roles": [], "types": {},
        "used": 3, "capacity": 25}


def bundle(key="mining", roles_=("mining", "drone_depot"), ores=("cobalt",), urgency="soon", biome=None):
    return {"biome": biome, "roles": list(roles_), "needs": [key] if key == "mining" else list(roles_)[:1],
            "urgency": urgency, "why": ["why " + key], "ores": list(ores), "over_cap": False,
            "slots": {"counted": 3, "penalized": False, "warehouses": 1}}


def row(x, y, score=10.0, confidence=0.9, biome="frozen"):
    return {"x": x, "y": y, "score": score, "confidence": confidence, "biome": biome,
            "survey": confidence < 0.5, "terms": {}}


def designate_item(outpost="home", roles_=("smelter",), urgency="soon"):
    return {"outpost": outpost, "roles": list(roles_), "needs": list(roles_), "urgency": urgency, "why": ["full"]}


def found_entry(**over):
    entry = plan_.found_proposal(bundle(), row(300, 300), 15000, TICK)
    entry.update(over)
    return entry


class LabelTests(unittest.TestCase):
    def test_ok_is_a_whole_word_any_case(self):
        self.assertTrue(plan_.ok_label("Outpost Suggestion OK"))
        self.assertTrue(plan_.ok_label("ok"))
        self.assertTrue(plan_.ok_label("Outpost Suggestion, Ok!"))
        self.assertFalse(plan_.ok_label("Outpost Suggestion"))
        self.assertFalse(plan_.ok_label("Bookkeeping"))
        self.assertFalse(plan_.ok_label(""))

    def test_safe_id_keeps_marker_characters(self):
        self.assertEqual(plan_.safe_id("outpost 2/a"), "outpost_2_a")
        self.assertEqual(plan_.safe_id("op.1:x-y"), "op.1:x-y")

    def test_bundle_key(self):
        self.assertEqual(plan_.bundle_key(bundle()), "mining")
        self.assertEqual(plan_.bundle_key(bundle("bio", ["bio_coastal"], (), biome="coastal")), "coastal")
        self.assertEqual(plan_.bundle_key(bundle("smelter", ["smelter", "drone_depot"], ())), "general")


class FreshTests(unittest.TestCase):
    def test_one_proposal_per_designation_and_bundle(self):
        plan = {"designate": [designate_item()], "found": [bundle()], "rejected": []}
        fresh = plan_.fresh_proposals(plan, [HOME], {"mining": [row(300, 300)]}, 15000, {}, TICK)
        self.assertEqual(sorted(fresh), ["d-home", "f-mining"])
        self.assertEqual((fresh["d-home"]["x"], fresh["d-home"]["price"]), (-10.0, 0))
        self.assertEqual((fresh["f-mining"]["x"], fresh["f-mining"]["price"]), (300.0, 15000))

    def test_bundle_without_site_makes_no_proposal(self):
        plan = {"designate": [], "found": [bundle()], "rejected": []}
        self.assertEqual(plan_.fresh_proposals(plan, [HOME], {}, 15000, {}, TICK), {})

    def test_rejected_site_is_held_for_its_bundle(self):
        rejected = found_entry(status="rejected", tick=TICK)
        old = {"f-mining~1000": rejected}
        plan = {"designate": [], "found": [bundle()], "rejected": []}
        ranked = {"mining": [row(320, 300, 12.0), row(600, 600, 8.0)]}
        fresh = plan_.fresh_proposals(plan, [HOME], ranked, 15000, old, TICK + 10)
        self.assertEqual((fresh["f-mining"]["x"], fresh["f-mining"]["y"]), (600.0, 600.0))
        later = plan_.fresh_proposals(plan, [HOME], ranked, 15000, old, TICK + plan_.REJECT_HOLD_TICKS)
        self.assertEqual(later["f-mining"]["x"], 320.0)

    def test_rejected_designation_refuses_its_pairs(self):
        entry = plan_.designate_proposal(designate_item(), HOME, TICK)
        entry["status"] = "rejected"
        self.assertEqual(plan_.refused_pairs({"d-home~1000": entry}, TICK + 1), [["smelter", "home"]])


class MergeTests(unittest.TestCase):
    def test_bounded_and_ordered(self):
        fresh = {}
        for index in range(7):
            entry = found_entry(id=f"f-b{index}", score=float(index))
            fresh[entry["id"]] = entry
        fresh["d-home"] = plan_.designate_proposal(designate_item(), HOME, TICK)
        merged = plan_.merge({}, fresh, TICK)
        self.assertEqual(len(merged), plan_.MAX_PROPOSALS)
        self.assertIn("d-home", merged)
        self.assertNotIn("f-b0", merged)

    def test_open_predecessor_keeps_marker_state_and_operator_anchor(self):
        old = {"f-mining": found_entry(placed=True, moved=True, x=350.0, y=280.0, ok=True)}
        fresh = {"f-mining": found_entry(x=400.0, y=400.0)}
        merged = plan_.merge(old, fresh, TICK + 5)
        entry = merged["f-mining"]
        self.assertTrue(entry["placed"] and entry["moved"] and entry["ok"])
        self.assertEqual((entry["x"], entry["y"]), (350.0, 280.0))

    def test_unmoved_proposal_follows_the_ranking(self):
        old = {"f-mining": found_entry(placed=True)}
        merged = plan_.merge(old, {"f-mining": found_entry(x=400.0)}, TICK + 5)
        self.assertEqual(merged["f-mining"]["x"], 400.0)
        self.assertTrue(merged["f-mining"]["placed"])

    def test_built_and_dropped_go_rejected_stay_on_hold(self):
        old = {"d-home": dict(plan_.designate_proposal(designate_item(), HOME, TICK), status="built"),
               "f-mining": found_entry(placed=True),
               "f-x~10": found_entry(id="f-x", status="rejected", tick=10),
               "f-y~5": found_entry(id="f-y", status="rejected", tick=-plan_.REJECT_HOLD_TICKS)}
        merged = plan_.merge(old, {}, TICK)
        self.assertEqual(list(merged), ["f-x~10"])


class ReconcileTests(unittest.TestCase):
    def mark(self, x=300.0, y=300.0, label=plan_.MARKER_LABEL):
        return {"x": x, "y": y, "label": label}

    def test_deleted_marker_rejects(self):
        proposals = {"f-mining": found_entry(placed=True)}
        events = plan_.reconcile(proposals, {}, TICK + 7)
        self.assertEqual(events, [("rejected", "f-mining")])
        self.assertEqual(list(proposals), ["f-mining~1007"])
        self.assertEqual(proposals["f-mining~1007"]["status"], "rejected")

    def test_unplaced_proposal_is_not_rejected(self):
        proposals = {"f-mining": found_entry()}
        self.assertEqual(plan_.reconcile(proposals, {}, TICK), [])
        self.assertIn("f-mining", proposals)

    def test_ok_label_and_drag(self):
        proposals = {"f-mining": found_entry(placed=True)}
        listing = {plan_.marker_id("f-mining"): self.mark(340.0, 290.0, "Outpost Suggestion OK")}
        events = plan_.reconcile(proposals, listing, TICK)
        self.assertEqual(sorted(events), [("moved", "f-mining"), ("ok", "f-mining")])
        entry = proposals["f-mining"]
        self.assertTrue(entry["ok"] and entry["moved"] and entry["recheck"])
        self.assertEqual((entry["x"], entry["y"]), (340.0, 290.0))
        plan_.resolve(entry)
        self.assertEqual(entry["status"], "proposed")   # re-check pending

    def test_designate_drag_is_ignored(self):
        entry = plan_.designate_proposal(designate_item(), HOME, TICK)
        entry["placed"] = True
        proposals = {"d-home": entry}
        plan_.reconcile(proposals, {plan_.marker_id("d-home"): self.mark(100.0, 100.0)}, TICK)
        self.assertEqual((entry["x"], entry["moved"]), (-10.0, False))


class ApprovalTests(unittest.TestCase):
    def test_ok_approves_only_without_blockers(self):
        entry = found_entry(ok=True)
        plan_.resolve(entry)
        self.assertEqual(entry["status"], "approved")
        for blocker in ({"blocked": "poi_clearance"}, {"survey": True}, {"over_cap": True}):
            entry = found_entry(ok=True, **blocker)
            plan_.resolve(entry)
            self.assertEqual(entry["status"], "proposed", blocker)
            self.assertIn("Blocked:", plan_.note_text(entry))

    def test_note_is_bounded(self):
        entry = found_entry(why=["x" * 300])
        self.assertLessEqual(len(plan_.note_text(entry)), plan_.NOTE_MAX)

    def test_marker_view_keeps_operator_ok_label(self):
        entry = found_entry(ok=True, status="approved")
        view = plan_.marker_view(entry, "Cobalt base OK")
        self.assertEqual((view["label"], view["color"], view["icon"]), ("Cobalt base OK", "success", "flag"))
        self.assertEqual(plan_.marker_view(found_entry(), "renamed")["label"], plan_.MARKER_LABEL)


def west_frozen(x, y):
    return "frozen" if x < 0 else "coastal"


class Markers:
    def __init__(self):
        self.items = {}
        self.calls = 0

    def place(self, id, x, y, label="", icon="pin", color="accent", note=""):
        self.calls += 1
        self.items[id] = NS(id=id, x=x, y=y, label=label, icon=icon, color=color, note=note)
        return NS(status="ok", message="")

    def list(self, prefix=""):
        return [self.items[key] for key in sorted(self.items) if key.startswith(prefix)]

    def remove(self, id):
        self.calls += 1
        return NS(status="ok" if self.items.pop(id, None) else "not_found", message="")


class PlannerTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.markers = Markers()
        self.world.components["markers"] = self.markers
        self.world.components["nocturna"] = NS(biome_at=west_frozen)
        self.world.services["shop"] = Shop(self.world, {"outpost_kit": 30000})
        self.snap = {"outposts": [dict(HOME)], "kits": set(), "range_m": 200.0}
        self.plan = {"designate": [], "found": [], "rejected": []}
        self.saved = (outpost_needs.snapshot, plan_.needs, plan_.plan_hosts, plan_.read_world)
        outpost_needs.snapshot = lambda: dict(self.snap)
        plan_.needs = lambda snap: []
        plan_.plan_hosts = lambda open_needs, snap: self.plan
        plan_.read_world = lambda outposts, kits, range_m, pipes=(): {
            "bounds": (-900.0, 900.0, -900.0, 900.0), "outposts": outposts, "ghosts": [], "pois": [],
            "sites": [], "range_m": range_m, "hardness_limit": None}

    def tearDown(self):
        outpost_needs.snapshot, plan_.needs, plan_.plan_hosts, plan_.read_world = self.saved
        super().tearDown()

    def planner(self):
        return plan_.OutpostPlanner(TreeConsole(module="infra_planner"))

    def test_designation_marker_ok_writes_roles(self):
        self.plan = {"designate": [designate_item()], "found": [], "rejected": []}
        planner = self.planner()
        self.assertEqual(planner.run_pass(True), "waiting")
        mid = plan_.marker_id("d-home")
        self.assertEqual(self.markers.items[mid].label, plan_.MARKER_LABEL)
        self.assertEqual(plan_.load()["d-home"]["status"], "proposed")
        calls = self.markers.calls
        self.assertEqual(planner.run_pass(False), "waiting")
        self.assertEqual(self.markers.calls, calls)   # unchanged content: no re-place
        self.markers.items[mid].label = "Outpost Suggestion ok"
        self.assertEqual(planner.run_pass(False), "changed", self.debug_log())
        self.assertEqual(roles.outpost_roles()["home"], ["smelter"])
        self.assertNotIn(mid, self.markers.items)
        self.assertEqual(plan_.load()["d-home"]["status"], "built")

    def test_found_proposal_drag_recheck_and_approval(self):
        self.plan = {"designate": [], "found": [bundle("general", ["smelter", "drone_depot"], ())], "rejected": []}
        planner = self.planner()
        planner.run_pass(True)
        stored = plan_.load()
        self.assertEqual(sorted(stored), ["f-general"])
        self.assertEqual(stored["f-general"]["price"], 30000)
        mid = plan_.marker_id("f-general")
        self.assertIn("30,000 cr", self.markers.items[mid].note)
        # drag next to home: fails clearance, OK is not enough
        self.markers.items[mid].x = 20.0
        self.markers.items[mid].y = 10.0
        self.markers.items[mid].label = "OK"
        planner.run_pass(False)
        entry = plan_.load()["f-general"]
        self.assertEqual((entry["x"], entry["blocked"], entry["status"]), (20.0, "outpost_clearance", "proposed"))
        self.assertIn("Blocked: outpost_clearance", self.markers.items[mid].note)
        self.assertEqual(self.markers.items[mid].label, "OK")
        # drag clear: approved, anchor kept on the next full pass
        self.markers.items[mid].x = 400.0
        self.markers.items[mid].y = 400.0
        planner.run_pass(False)
        planner.run_pass(True)
        entry = plan_.load()["f-general"]
        self.assertEqual((entry["x"], entry["blocked"], entry["status"]), (400.0, None, "approved"))
        self.assertEqual(self.markers.items[mid].color, "success")

    def test_deleted_marker_rejects_and_holds(self):
        self.plan = {"designate": [designate_item()], "found": [], "rejected": []}
        planner = self.planner()
        planner.run_pass(True)
        del self.markers.items[plan_.marker_id("d-home")]
        self.assertEqual(planner.run_pass(False), "idle")
        stored = plan_.load()
        self.assertEqual([entry["status"] for entry in stored.values()], ["rejected"])
        self.assertEqual(plan_.refused_pairs(stored, 0), [["smelter", "home"]])

    def test_locked_without_markers(self):
        del self.world.components["markers"]
        self.assertEqual(self.planner().run_pass(True), "locked")

    def test_unreadable_markers_never_reject(self):
        self.plan = {"designate": [designate_item()], "found": [], "rejected": []}
        planner = self.planner()
        planner.run_pass(True)

        def broken(prefix=""):
            raise RuntimeError("down")
        self.markers.list = broken
        planner.run_pass(False)
        self.assertEqual(plan_.load()["d-home"]["status"], "proposed")
        self.world.console.lines[:] = [line for line in self.world.console.lines if "likely a code bug" not in line[1]]


class HostRefusalTests(unittest.TestCase):
    def test_host_check_skips_refused_pairs(self):
        need = {"role": "smelter", "biome": None, "urgency": "soon", "why": "x", "found": True, "locked": False}
        snap = {"outposts": [HOME], "kits": set(), "refused": [["smelter", "home"]]}
        self.assertEqual(outpost_needs.host_check(need, dict(HOME), snap)[1], "operator rejected")


if __name__ == "__main__":
    unittest.main()
