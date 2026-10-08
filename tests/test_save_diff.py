"""devtools/save_diff.py: richer save summary, change rows, owner reasons matched to rows."""
import sys
import unittest
from pathlib import Path

DEVTOOLS = Path(__file__).resolve().parent.parent / "devtools"
if str(DEVTOOLS) not in sys.path:
    sys.path.insert(0, str(DEVTOOLS))

import save_diff as sd  # noqa: E402

TABLE = {"smelter": (True, True), "warehouse": (True, False), "pioneer": (False, False)}


def _save(machines=(), outposts=("outpost_home",), tech=(), tick=100, stock=(), completed=(), scripts=()):
    ms = {}
    for i, (type_id, loc) in enumerate(machines):
        ms[f"{type_id}_{i}"] = {"id": f"{type_id}_{i}", "typeId": type_id, "locationId": loc, "data": {}}
    if stock:
        ms["warehouse_x"] = {"id": "warehouse_x", "typeId": "warehouse", "locationId": "outpost_home", "data": {},
                             "bins": {"slot_0": {"stacks": [{"id": i, "count": n} for i, n in stock]}}}
    return {"state": {
        "tickCount": tick, "playtime": tick / 10,
        "player": {"credits": 500, "totalCreditsEarned": 1000, "totalCreditsSpent": 500,
                   "unlockedAchievements": [], "purchasedItemCounts": {}},
        "unlockedTech": list(tech),
        "researchRates": {"terraform": {"lastValue": 1000}},
        "machines": ms,
        "inventory": {"slots": [{"id": "salt", "count": 5}]},
        "orders": {"completed": list(completed), "docks": {}},
        "scripts": {f"s{i}": {"status": st} for i, st in enumerate(scripts)},
        "planet": {
            "clock": {"dayNumber": tick // 100, "normalized": 0.0},
            "outposts": [{"id": o, "name": o} for o in outposts],
            "infrastructure": {"pipes": [], "powerLines": []},
            "constructionBlueprints": [],
            "power": {"subnets": {}},
        },
    }}


class CapTest(unittest.TestCase):
    def test_caps_follow_simworker(self):
        self.assertEqual(sd.building_cap("outpost_home", set()), 25)
        self.assertEqual(sd.building_cap("outpost_1", set()), 20)
        both = {sd.EXPANSION_TECH, sd.WEATHER_TECH}
        self.assertEqual(sd.building_cap("outpost_home", both), 31)
        self.assertEqual(sd.building_cap("outpost_1", both), 25)

    def test_vehicles_do_not_count(self):
        s = sd.summarize(_save([("smelter", "outpost_home"), ("pioneer", "outpost_home")]), TABLE)
        self.assertEqual(s["caps"]["outpost_home"], {"counted": 1, "penalized": 1, "cap": 25})


class RowsTest(unittest.TestCase):
    def test_rows_and_running_scripts(self):
        a = sd.summarize(_save([("smelter", "outpost_home")], scripts=("running", "idle")), TABLE)
        b = sd.summarize(_save([("smelter", "outpost_home"), ("smelter", "outpost_1")],
                               outposts=("outpost_home", "outpost_1"), completed=("helios_01",),
                               tech=("warehouse_unlock",), stock=(("salt", 20),),
                               scripts=("running", "waiting", "idle"), tick=300), TABLE)
        texts = {r["section"]: [] for r in sd.diff_rows(a, b)}
        for r in sd.diff_rows(a, b):
            texts[r["section"]].append(r["text"])
        self.assertIn("new outpost outpost_1 (outpost_1)", texts["outposts"])
        self.assertIn("outpost_1: smelter 0 -> 1", texts["buildings"])
        self.assertIn("order done helios_01", texts["orders"])
        self.assertIn("tech warehouse_unlock", texts["tech"])
        self.assertIn("running 1 -> 2 (of 2 -> 3 scripts)", texts["scripts"])
        self.assertIn("salt 5 -> 25", texts["stock"])  # scarce input, Inventory plus Warehouse bins


class AnnotateTest(unittest.TestCase):
    def test_reason_matches_rows_and_rest_is_unexplained(self):
        a = sd.summarize(_save([("smelter", "outpost_home")]), TABLE)
        b = sd.summarize(_save([("smelter", "outpost_home"), ("smelter", "outpost_home"), ("warehouse", "outpost_1")],
                               outposts=("outpost_home", "outpost_1"), tick=300), TABLE)
        rows = sd.diff_rows(a, b)
        events = [
            {"id": 7, "kind": "minor", "tick": 200, "day": 2, "minor": ["outpost_home: smelter 1 -> 2"]},
            {"id": None, "kind": "why", "ref": 7, "text": "scale smelting"},
            {"id": 9, "kind": "minor", "tick": 900, "day": 9, "minor": ["outpost_1: warehouse 0 -> 1"]},
            {"id": None, "kind": "why", "ref": 9, "text": "outside the pair"},
        ]
        notes, unexplained = sd.annotate(rows, events, 100, 300)
        self.assertEqual([n["text"] for n in notes], ["scale smelting"])
        self.assertEqual([rows[i]["text"] for i in notes[0]["rows"]], ["outpost_home: smelter 1 -> 2"])
        left = {rows[i]["text"] for i in unexplained}
        self.assertIn("outpost_1: warehouse 0 -> 1", left)
        self.assertIn("new outpost outpost_1 (outpost_1)", left)

    def test_line_keys_pair_outpost_and_type(self):
        self.assertIn("outpost_2/smelter", sd.line_keys("outpost_2: smelter 0 -> 1 (first at outpost)"))
        self.assertNotIn("first", sd.line_keys("first smelter"))


if __name__ == "__main__":
    unittest.main()
