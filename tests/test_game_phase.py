"""Tests for lib/game_phase.py: fronts, phase names, thresholds, rates and ETAs over a plain snapshot."""

import unittest

import harness  # noqa: F401 (side effect: installs game builtins and lib paths)

# isort: split
import game_phase as gp
from game_stubs import TerraformPillar
from harness import StubTestCase


def pillar(value, target=100.0, complete=False, next_target=None, progress=None):
    return {
        "value": value,
        "target": target,
        "next_target": next_target,
        "progress": value / target * 100 if progress is None else progress,
        "complete": complete,
        "phase": 1,
    }


def snap(tp=0, research=(), pillars=None, drills=False, done=None, history=None, tick=0):
    return {
        "tick": tick,
        "tp": tp,
        "pillars": pillars or {},
        "research": set(research),
        "drills": drills,
        "done": done or {},
        "history": history or {},
    }


class PhaseTest(unittest.TestCase):
    def test_values_and_unlocked(self):
        s = snap(tp=1234, research=["research_smelter"], pillars={"oxygen": pillar(7.0)})
        self.assertEqual(gp.value(s, "tp"), 1234.0)
        self.assertEqual(gp.value(s, "oxygen"), 7.0)
        self.assertEqual(gp.value(s, "plants"), 0.0)
        self.assertTrue(gp.unlocked(s, "research_smelter"))
        self.assertFalse(gp.unlocked(s, "research_warehouse"))

    def test_fronts_follow_research_and_completion(self):
        s = snap()
        self.assertEqual(gp.fronts(s), ["atmosphere"])
        s = snap(research=[gp.BIOSPHERE_RESEARCH])
        self.assertEqual(gp.fronts(s), ["atmosphere", "biomass"])
        s = snap(research=[gp.BIOSPHERE_RESEARCH, gp.PLANTS_RESEARCH], done={"biomass": True})
        self.assertEqual(gp.fronts(s), ["atmosphere", "plants"])
        atmo = {p: pillar(100.0, complete=True) for p in gp.ATMOSPHERE}
        s = snap(
            research=[gp.BIOSPHERE_RESEARCH, gp.PLANTS_RESEARCH, gp.WILDLIFE_RESEARCH],
            pillars=atmo,
            done={"biomass": True, "plants": True},
        )
        self.assertEqual(gp.fronts(s), ["wildlife"])

    def test_phase_names(self):
        self.assertEqual(gp.phase_name(snap()), "cold_boot")
        self.assertEqual(gp.phase_name(snap(research=["research_data_archive"])), "early")
        self.assertEqual(gp.phase_name(snap(research=["research_data_archive", gp.CONTROL_ROOM_RESEARCH])), "expansion")
        base = ["research_data_archive", gp.CONTROL_ROOM_RESEARCH, gp.BIOSPHERE_RESEARCH]
        self.assertEqual(gp.phase_name(snap(research=base)), "biomass")
        self.assertEqual(gp.phase_name(snap(research=base + [gp.PLANTS_RESEARCH])), "plants")
        self.assertEqual(gp.phase_name(snap(research=base + [gp.PLANTS_RESEARCH, gp.WILDLIFE_RESEARCH])), "wildlife")
        self.assertEqual(
            gp.phase_name(snap(research=base, done={"biomass": True, "plants": True, "wildlife": True})), "finish"
        )

    def test_distance_and_locked_thresholds(self):
        s = snap(pillars={"oxygen": pillar(20.0), "pressure": pillar(1.0)}, research=["research_smelter"])
        self.assertEqual(gp.distance(s, "research_smelter"), 0.0)
        self.assertEqual(gp.distance(s, "research_drill_industrial"), 10.0)
        self.assertIsNone(gp.distance(s, "research_nope"))
        rows = gp.locked_thresholds(s, "oxygen")
        self.assertEqual(rows[0][0], "research_battery_charger")  # 25 ppt: the nearest locked oxygen threshold above 20
        self.assertEqual(rows[1], ("research_drill_industrial", "oxygen", 30, 10.0))
        ids = [row[0] for row in rows]
        self.assertNotIn("research_smelter", ids)  # unlocked
        self.assertNotIn("research_charging_station", ids)  # 9 ppt already passed
        pressure = gp.locked_thresholds(s, "pressure")
        self.assertEqual(pressure[0][:3], ("research_pressure_mk2_pack", "pressure", 1.2))
        self.assertAlmostEqual(pressure[0][3], 0.2)
        everything = gp.locked_thresholds(s)
        self.assertEqual(everything[0][0], "research_pressure_mk2_pack")

    def test_rate_and_eta(self):
        history = {"oxygen": [[0, 10.0], [3000, 11.0], [6000, 12.0]]}
        s = snap(pillars={"oxygen": pillar(12.0)}, history=history, tick=6000)
        slope = gp.rate(s, "oxygen")
        self.assertIsNotNone(slope)
        self.assertAlmostEqual(slope or 0.0, 2.0 / 6000)
        self.assertEqual(gp.eta_ticks(s, "oxygen", 30.0), 54000)
        self.assertEqual(gp.eta_ticks(s, "oxygen", 5.0), 0)
        self.assertIsNone(gp.eta_ticks(s, "pressure", 1.0))
        self.assertEqual(gp.research_eta_ticks(s, "research_drill_industrial"), 54000)
        self.assertIsNone(gp.research_eta_ticks(s, "research_nope"))
        flat = snap(pillars={"oxygen": pillar(12.0)}, history={"oxygen": [[0, 12.0], [3000, 12.0]]})
        self.assertIsNone(gp.eta_ticks(flat, "oxygen", 30.0))

    def test_nuclear_ahead(self):
        self.assertFalse(gp.nuclear_ahead(snap(research=[gp.BIOSPHERE_RESEARCH])))
        self.assertTrue(gp.nuclear_ahead(snap(research=[gp.WILDLIFE_RESEARCH])))
        self.assertTrue(gp.nuclear_ahead(snap(research=[gp.NUCLEAR_RESEARCH])))

    def test_small_predicates(self):
        s = snap(
            research=[gp.WILDLIFE_RESEARCH, gp.BIOSPHERE_RESEARCH],
            drills=True,
            pillars={"oxygen": pillar(5.0, complete=True)},
        )
        self.assertTrue(gp.drills(s))
        self.assertTrue(gp.wildlife_unlocked(s))
        self.assertTrue(gp.biosphere_unlocked(s))
        self.assertTrue(gp.complete(s, "oxygen"))
        self.assertFalse(gp.complete(s, "pressure"))
        self.assertTrue(gp.complete(snap(done={"plants": True}), "plants"))
        self.assertIsNone(gp.threshold("research_nope"))
        self.assertEqual(gp.threshold("research_smelter"), ("oxygen", 5))
        self.assertEqual(gp.distance(snap(research=["research_smelter"]), "research_smelter"), 0.0)

    def test_rate_bad_rows(self):
        falling = snap(pillars={"oxygen": pillar(8.0)}, history={"oxygen": [[0, 10.0], [3000, 8.0]]})
        self.assertLess(gp.rate(falling, "oxygen") or 0.0, 0)
        self.assertIsNone(gp.eta_ticks(falling, "oxygen", 30.0))
        backwards = snap(history={"oxygen": [[3000, 1.0], [0, 2.0]]})
        self.assertIsNone(gp.rate(backwards, "oxygen"))
        junk = snap(history={"oxygen": [[0, "x"], ["a", 1.0], [3000, 2.0], None, [6000, 4.0]]})
        self.assertAlmostEqual(gp.rate(junk, "oxygen") or 0.0, 2.0 / 3000)

    def test_with_sample_rings(self):
        s = snap(tp=50, pillars={"oxygen": pillar(1.0)})
        reset = gp.with_sample({"oxygen": [[9000, 5.0], [12000, 6.0]]}, s, 100)
        self.assertEqual(reset["oxygen"], [[100, 1.0]])
        cleaned = gp.with_sample({"oxygen": [[0, None], "bad", [10, 0.5]]}, s, 20)
        self.assertEqual(cleaned["oxygen"], [[10, 0.5]])
        s = snap(tp=50, pillars={"oxygen": pillar(1.0)})
        history = gp.with_sample({}, s, 100)
        self.assertEqual(history, {"oxygen": [[100, 1.0]], "tp": [[100, 50.0]]})
        same = gp.with_sample(history, s, 100 + gp.HISTORY_MIN_TICKS - 1)
        self.assertEqual(same, history)
        later = gp.with_sample(history, s, 100 + gp.HISTORY_MIN_TICKS)
        self.assertEqual(len(later["oxygen"]), 2)
        long = {"oxygen": [[i * gp.HISTORY_MIN_TICKS, float(i)] for i in range(gp.HISTORY_LEN + 3)]}
        cut = gp.with_sample(long, s, 10**9)
        self.assertEqual(len(cut["oxygen"]), gp.HISTORY_LEN)
        self.assertEqual(cut["oxygen"][-1][0], 10**9)


class ReaderTest(StubTestCase):
    def test_readers_over_stub_world(self):
        world = self.world
        world.terraforming.rows = [
            TerraformPillar("oxygen", value=3.0, target=10.0, progress=30.0, phase=2, unit="ppt")
        ]
        world.terraforming.tp = 777
        world.research.unlocked.add("research_smelter")
        pillars = gp.read_pillars()
        self.assertEqual(pillars["oxygen"]["value"], 3.0)
        self.assertEqual(pillars["oxygen"]["phase"], 2)
        self.assertEqual(gp.read_research(), {"research_smelter"})
        s = gp.snapshot(now=5)
        self.assertEqual(s["tick"], 5)
        self.assertIn("oxygen", s["pillars"])
        self.assertFalse(s["drills"])
        history = gp.record(s, 5)
        self.assertEqual(history["oxygen"], [[5, 3.0]])
        self.assertEqual(gp.read_history()["oxygen"], [[5, 3.0]])
        self.assertEqual(gp.record(s, 6), history)

    def test_reader_fallbacks(self):
        world = self.world
        world.services["research"] = _OldResearch({"research_smelter"})
        self.assertEqual(gp.read_research(), {"research_smelter"})
        world.services["research"] = _OldResearch(None)
        self.assertIsNone(gp.read_research())
        s = gp.snapshot(now=1, last={"research": {"research_warehouse"}})
        self.assertEqual(s["research"], {"research_warehouse"})
        self.assertEqual(gp.read_tp(), 0.0)  # no nocturna in the stub world
        world.terraforming.rows = [_BrokenPillar()]
        self.assertEqual(gp.read_pillars(), {})


class _OldResearch:
    """A research component without unlocked(); is_unlocked() answers from `ids`, or fails when ids is None."""

    def __init__(self, ids):
        self.ids = ids

    def unlocked(self):
        raise RuntimeError("unlocked")

    def is_unlocked(self, research_id):
        if self.ids is None:
            raise RuntimeError("research offline")
        return research_id in self.ids


class _BrokenPillar:
    """A pillar row whose fields fail to read."""

    id = "oxygen"

    @property
    def value(self):
        raise RuntimeError("no reading")


if __name__ == "__main__":
    unittest.main()
