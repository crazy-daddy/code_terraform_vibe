"""Tests for lib/mission_pool.py: the fleet.missions index of open work
(ids, since carried over, cap and dropped counts, holders) and its publish
beside fleet.role_demand."""

import unittest

import harness  # puts the lib/ folders on sys.path
import mission_pool
import role_demand
from priority import BUILD, BUILD_AHEAD, MANUAL, NEED, STOCK

PARTS = {
    "deficits": {"o1": {NEED: {"iron_ore": 5, "copper_ingot": 20}, STOCK: {"sand": 3}}, "o2": {}},
    "requests": {"o1": {"copper_ingot": {"by": "smelter_1"}, "iron_ore": {"by": "smelter_2"}}},
    "pickups": {
        "pull:p1:o1:copper_ingot": {"vehicle": "p1", "dest": "o1", "item_id": "copper_ingot", "units": 5, "tick": 90},
        "pull:p9:o1:sand": {"vehicle": "p9", "dest": "o1", "item_id": "sand", "units": 1, "tick": -40000},  # stale
    },
    "jobs": [
        ("job_1", "smelter", "o1", (3.0, 4.0), BUILD + 99),
        ("job_1", "smelter", "o1", (3.0, 4.0), BUILD + 99),
        ("job_2", None, None, None, MANUAL + 99),
    ],
    "survey": {
        "r1": {"x": 0.0, "y": 0.0, "radius": 10.0, "why": "iron"},
        "r2": {"x": 500.0, "y": 0.0, "radius": 5.0, "why": "oil"},
    },
    "scout": (2, 1),
    "miner_bands": {"o1": {NEED: {"iron_ore": 5}, STOCK: {"iron_ore": 4, "copper_ore": 2}}},
    "founded": {"o1": (3.0, 4.0)},
    "claims": {"build_job_1": {"vehicle": "p2", "tick": 80}, "poi_7": {"vehicle": "p3", "tick": 80}},
    "reserved": {"p4": {"vehicle": "p4", "item_id": "iron_ore", "units": 6, "outpost_id": "o1", "tick": 70}},
}


def by_id(value):
    return {e["id"]: e for e in value["entries"]}


class BuildTests(unittest.TestCase):
    def test_entries_per_kind(self):
        value = mission_pool.build(100, PARTS)
        self.assertEqual(len(value["entries"]), 9)  # job_1 listed twice counts once
        entries = by_id(value)
        self.assertEqual(
            set(entries),
            {
                f"haul:o1:{NEED}",
                f"haul:o1:{STOCK}",
                "build:job_1",
                "build:job_2",
                "mine:o1:iron_ore",
                "mine:o1:copper_ore",
                "scan:r1",
                "scan:r2",
                "scan:pois",
            },
        )
        haul = entries[f"haul:o1:{NEED}"]
        self.assertEqual(
            (haul["prio"], haul["item"], haul["units"], haul["by"]), (NEED, "copper_ingot", 25, "smelter_1")
        )
        self.assertEqual(haul["holders"], ["p1"])  # the stale sand pickup holds nothing
        self.assertEqual(entries["build:job_1"]["prio"], BUILD)
        self.assertEqual((entries["build:job_1"]["holders"], entries["build:job_1"]["coords"]), (["p2"], [3.0, 4.0]))
        self.assertEqual((entries["build:job_2"]["prio"], entries["build:job_2"]["holders"]), (MANUAL, []))
        mine = entries["mine:o1:iron_ore"]
        self.assertEqual((mine["prio"], mine["units"], mine["by"], mine["holders"]), (NEED, 9, "smelter_2", ["p4"]))
        self.assertEqual(entries["mine:o1:copper_ore"]["prio"], STOCK)
        self.assertEqual((entries["scan:r1"]["outpost"], entries["scan:r2"]["outpost"]), ("o1", None))
        self.assertEqual((entries["scan:pois"]["prio"], entries["scan:pois"]["units"]), (STOCK, 3))

    def test_since_carried_by_id(self):
        first = mission_pool.build(100, PARTS)
        parts = dict(PARTS, jobs=[("job_3", "pump", None, None, BUILD_AHEAD + 99)])
        second = by_id(mission_pool.build(700, parts, first))
        self.assertEqual(second[f"haul:o1:{NEED}"]["since"], 100)
        self.assertEqual(second["build:job_3"]["since"], 700)
        self.assertNotIn("build:job_1", second)

    def test_sorted_band_then_oldest(self):
        previous = {"entries": [{"id": "scan:r2", "since": 5}]}
        ids = [e["id"] for e in mission_pool.build(100, PARTS, previous)["entries"]]
        self.assertEqual(ids[:2], ["build:job_2", "build:job_1"])  # MANUAL, then BUILD
        self.assertEqual(ids[2], "scan:r2")  # NEED band, oldest first
        self.assertEqual(ids[-1], "scan:pois")

    def test_cap_counts_dropped_per_kind(self):
        survey = {f"r{i:02d}": {"x": 0.0, "y": 0.0, "radius": 1.0, "why": ""} for i in range(mission_pool.MAX_ENTRIES)}
        value = mission_pool.build(100, dict(PARTS, survey=survey, founded={}))
        self.assertEqual(len(value["entries"]), mission_pool.MAX_ENTRIES)
        kept = by_id(value)
        self.assertTrue(
            {"build:job_1", f"haul:o1:{STOCK}", "mine:o1:copper_ore"} <= set(kept)
        )  # inside their kind's share
        # 55 entries: the 7 last scans in order (scan:pois among them) drop
        self.assertEqual(value["dropped"], {"scan": 7})
        self.assertNotIn("scan:pois", kept)

    def test_one_kind_cannot_flood_the_cap(self):
        jobs = [(f"job_{i:03d}", "pipe", None, None, BUILD + 99) for i in range(100)]
        value = mission_pool.build(100, dict(PARTS, jobs=jobs))
        kinds = [e["kind"] for e in value["entries"]]
        self.assertEqual(len(kinds), mission_pool.MAX_ENTRIES)
        self.assertEqual({k: kinds.count(k) for k in set(kinds)}, {"haul": 2, "mine": 2, "scan": 3, "build": 41})
        self.assertEqual(value["dropped"], {"build": 59})

    def test_bad_since_starts_over(self):
        value = by_id(
            mission_pool.build(
                100, PARTS, {"entries": [{"id": "scan:pois", "since": "x"}, {"id": "scan:r1", "since": 7}]}
            )
        )
        self.assertEqual((value["scan:pois"]["since"], value["scan:r1"]["since"]), (100, 7))

    def test_stale_window_matches_role_demand(self):
        self.assertEqual(mission_pool.MISSIONS_STALE_TICKS, role_demand.ROLE_DEMAND_STALE_TICKS)

    def test_no_work_no_entries(self):
        self.assertEqual(mission_pool.build(100, {}), {"tick": 100, "entries": [], "dropped": {}})

    def test_oldest_open_skips_held(self):
        entries = [
            {"id": "build:a", "kind": "build", "since": 10, "holders": ["p1"]},
            {"id": "build:b", "kind": "build", "since": 30, "holders": []},
            {"id": "build:c", "kind": "build", "since": 20, "holders": []},
            {"id": "haul:o1:400", "kind": "haul", "since": 1, "holders": []},
        ]
        self.assertEqual((mission_pool.oldest_open(entries, "build") or {}).get("id"), "build:c")
        self.assertIsNone(mission_pool.oldest_open(entries, "mine"))


class PublishTests(harness.StubTestCase):
    def test_publish_writes_both_keys_and_keeps_since(self):
        self.world.add_blueprint("job_1", "iron_ingot")
        now = self.world.clock.now
        role_demand.publish(now)
        first = mission_pool.read(now)
        self.assertIn("build:job_1", by_id(first))
        self.assertIsInstance((self.world.notebook.get(mission_pool.MISSIONS_KEY) or {}).get("entries"), list)
        role_demand.publish(now + 600)
        entry = by_id(mission_pool.read(now + 600))["build:job_1"]
        self.assertEqual((entry["since"], entry["prio"]), (now, MANUAL))  # not in autoplay.planned: operator-placed

    def test_read_ignores_stale_and_malformed(self):
        self.world.notebook.set(mission_pool.MISSIONS_KEY, {"tick": 0, "entries": [{"id": "scan:pois"}, "junk"]})
        self.assertEqual([e["id"] for e in mission_pool.read()["entries"]], ["scan:pois"])
        self.assertEqual(mission_pool.read(mission_pool.MISSIONS_STALE_TICKS)["entries"], [])
        self.world.notebook.set(mission_pool.MISSIONS_KEY, "junk")
        self.assertEqual(mission_pool.read(), {"entries": [], "dropped": {}})


class ReservationHolderTests(unittest.TestCase):
    def test_fresh_reservations_with_outpost_only(self):
        from mining_reservations import RESERVATION_STALE_TICKS, holders_by_target

        reservations = {
            "a": {"vehicle": "a", "item_id": "iron_ore", "units": 3, "outpost_id": "o1", "tick": 10},
            "b": {"vehicle": "b", "item_id": "iron_ore", "units": 3, "outpost_id": None, "tick": 10},
            "c": {
                "vehicle": "c",
                "item_id": "iron_ore",
                "units": 3,
                "outpost_id": "o1",
                "tick": 10 - RESERVATION_STALE_TICKS,
            },
            "d": {"vehicle": "d", "item_id": "iron_ore", "units": 0, "outpost_id": "o1", "tick": 10},
        }
        self.assertEqual(holders_by_target(reservations, 10), {("o1", "iron_ore"): {"a"}})
        self.assertEqual(holders_by_target("junk", 10), {})


if __name__ == "__main__":
    unittest.main()
