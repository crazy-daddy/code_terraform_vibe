"""devtools/decision_recorder.py: save summary, major/minor diff, reason and note handling."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

DEVTOOLS = Path(__file__).resolve().parent.parent / "devtools"
if str(DEVTOOLS) not in sys.path:
    sys.path.insert(0, str(DEVTOOLS))

import decision_recorder as dr  # noqa: E402
import savefile  # noqa: E402


def _save(machines=(), outposts=("outpost_home",), tech=(), achievements=(), seq=1, tick=100):
    ms = {}
    for i, (type_id, loc, tier) in enumerate(machines):
        m = {"id": f"{type_id}_{i}", "typeId": type_id, "data": {}}
        if loc:
            m["locationId"] = loc
        if tier is not None:
            m["data"]["tier"] = tier
        ms[m["id"]] = m
    return {
        "writeSequence": seq,
        "state": {
            "tickCount": tick, "playtime": tick / 10,
            "player": {"credits": 500, "unlockedAchievements": list(achievements)},
            "unlockedTech": list(tech),
            "researchRates": {"terraform": {"lastValue": 1234}},
            "machines": ms,
            "planet": {
                "clock": {"dayNumber": 3, "normalized": 0.5},
                "outposts": [{"id": o, "name": o} for o in outposts],
                "infrastructure": {"pipes": [], "powerLines": []},
                "constructionBlueprints": [],
            },
        },
    }


def _diff(old, new, **kw):
    return dr.diff(dr.summarize(old), dr.summarize(new), **kw)


class SummaryTest(unittest.TestCase):
    def test_counts_by_location_with_map_bucket(self):
        s = dr.summarize(_save([("smelter", "outpost_home", None), ("smelter", "outpost_home", None),
                                ("water_pump", None, None)]))
        self.assertEqual(s["counts"], {"outpost_home": {"smelter": 2}, dr.MAP: {"water_pump": 1}})
        self.assertEqual(s["tp"], 1234)
        self.assertEqual(dr.game_time(s), "day 3 12:00, run 0.00 h")


class DiffTest(unittest.TestCase):
    def test_scale_up_is_minor(self):
        old = _save([("smelter", "outpost_home", None)])
        new = _save([("smelter", "outpost_home", None), ("smelter", "outpost_home", None)])
        major, minor = _diff(old, new)
        self.assertEqual(major, [])
        self.assertEqual(minor, ["outpost_home: smelter 1 -> 2"])

    def test_new_type_outpost_tech_milestone_are_major(self):
        old = _save([], tech=["a"], achievements=["first_script"])
        new = _save([("smelter", "outpost_1", None)], outposts=("outpost_home", "outpost_1"),
                    tech=["a", "smelter_unlock"], achievements=["first_script", "phase_o2_thin_air", "pig_iron"])
        major, minor = _diff(old, new)
        self.assertIn("new outpost outpost_1 (outpost_1)", major)
        self.assertIn("tech smelter_unlock", major)
        self.assertIn("achievement phase_o2_thin_air", major)
        self.assertIn("first smelter", major)
        self.assertIn("achievement pig_iron", minor)

    def test_first_at_outpost_minor_unless_flag(self):
        old = _save([("smelter", "outpost_home", None)])
        new = _save([("smelter", "outpost_home", None), ("smelter", "outpost_2", None)])
        major, minor = _diff(old, new)
        self.assertEqual(major, [])
        self.assertIn("outpost_2: smelter 0 -> 1 (first at outpost)", minor)
        major, _ = _diff(old, new, outpost_types_major=True)
        self.assertEqual(major, ["outpost_2: smelter 0 -> 1 (first at outpost)"])

    def test_first_tier_major_then_minor(self):
        old = _save([("oxygen_generator", "outpost_home", 1)] * 2)
        mid = _save([("oxygen_generator", "outpost_home", 1), ("oxygen_generator", "outpost_home", 2)])
        new = _save([("oxygen_generator", "outpost_home", 2)] * 2)
        self.assertIn("first oxygen_generator at tier 2", _diff(old, mid)[0])
        major, minor = _diff(mid, new)
        self.assertEqual(major, [])
        self.assertIn("tier oxygen_generator@2 1 -> 2", minor)

    def test_last_of_type_gone_is_major(self):
        major, _ = _diff(_save([("refiner", "outpost_1", None)]), _save([]))
        self.assertEqual(major, ["last refiner gone"])

    @staticmethod
    def _suggest(markers, proposals):
        """A save with outpost planner markers {pid: label} and proposals {pid: status}."""
        s = _save()
        s["state"]["mapAnnotations"] = {"markers": {
            "resource.poi_1_1": {"id": "resource.poi_1_1", "label": "x"},
            **{f"autoplay.outpost.{p}": {"label": lab, "note": f"note {p}"} for p, lab in markers.items()}}}
        s["state"]["notebook"] = {"entries": {"autoplay.outpost_proposals": {
            "revision": 1, "value": {p: {"id": p, "status": st} for p, st in proposals.items()}}}}
        return s

    def test_deleted_suggestion_with_open_proposal_is_major(self):
        old = self._suggest({"f-general": "Outpost Suggestion", "d-home": "Outpost Suggestion"},
                            {"f-general": "proposed", "d-home": "proposed"})
        new = self._suggest({"d-home": "Outpost Suggestion"}, {"f-general": "proposed", "d-home": "proposed"})
        major, _ = _diff(old, new)
        self.assertEqual(major, ["outpost suggestion f-general deleted (rejected): note f-general"])

    def test_planner_removal_and_status_change_are_minor(self):
        old = self._suggest({"f-general": "Outpost Suggestion"}, {"f-general": "proposed"})
        new = self._suggest({}, {"f-general~500": "rejected"})
        major, minor = _diff(old, new)
        self.assertEqual(major, [])
        self.assertIn("outpost suggestion f-general removed by planner", minor)
        self.assertIn("proposal f-general~500 - -> rejected", minor)

    def test_ok_label_is_major_once(self):
        old = self._suggest({"f-mining": "Outpost Suggestion"}, {"f-mining": "proposed"})
        mid = self._suggest({"f-mining": "Outpost Suggestion ok"}, {"f-mining": "proposed"})
        new = self._suggest({"f-mining": "Outpost Suggestion OK"}, {"f-mining": "approved"})
        self.assertEqual(_diff(old, mid)[0], ["outpost suggestion f-mining approved (OK): note f-mining"])
        self.assertEqual(_diff(mid, new), ([], ["proposal f-mining proposed -> approved"]))


class SaveFileTest(unittest.TestCase):
    def test_reads_plain_and_gzip_by_magic_bytes(self):
        import gzip
        tmp = Path(tempfile.mkdtemp())
        (tmp / "a.json").write_text('{"x": 1}', "utf-8")
        (tmp / "b.json").write_bytes(gzip.compress(b'{"x": 2}'))  # extension does not matter
        self.assertEqual(savefile.load_save(tmp / "a.json"), {"x": 1})
        self.assertEqual(savefile.load_save(tmp / "b.json"), {"x": 2})


class RecorderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.save = self.tmp / "save_a_b.json"
        self.save.write_text(json.dumps(_save()), "utf-8")
        patcher = mock.patch.object(dr, "RUNS_ROOT", self.tmp / "runs")
        patcher.start()
        self.addCleanup(patcher.stop)
        for name, value in (("say", mock.DEFAULT), ("git_head", mock.Mock(return_value=("abc1234", False)))):
            p = mock.patch.object(dr, name, value) if value is not mock.DEFAULT else mock.patch.object(dr, name)
            p.start()
            self.addCleanup(p.stop)
        self.rec = dr.Recorder(self.save, copy_every_min=0, outpost_types_major=False, seed=42)

    def test_run_dir_named_by_date_and_commit(self):
        self.assertRegex(self.rec.dir.name, r"^\d{8}_abc1234$")
        meta = json.loads((self.rec.dir / "run.json").read_text("utf-8"))
        self.assertEqual((meta["save_id"], meta["seed"], meta["commit"]), ("save_a_b", 42, "abc1234"))

    def events(self):
        return [json.loads(x) for x in self.rec.events.read_text("utf-8").splitlines()]

    def test_major_opens_prompt_reason_closes_it(self):
        self.rec.on_save(dr.summarize(_save()))
        self.rec.on_save(dr.summarize(_save([("smelter", "outpost_home", None)], seq=2)))
        self.assertEqual(self.rec.open_id, 2)
        self.rec.on_line("iron for fabricator\n")
        self.assertIsNone(self.rec.open_id)
        self.rec.on_line("a free note\n")
        ev = self.events()
        self.assertEqual([e["kind"] for e in ev], ["start", "major", "why", "note"])
        self.assertEqual(ev[2]["ref"], 2)
        copy = self.rec.dir / ev[1]["save"]
        self.assertTrue(copy.name.endswith(".json.gz"))
        self.assertEqual(savefile.load_save(copy), json.loads(self.save.read_text("utf-8")))

    def test_next_major_times_out_open_entry_and_late_answer(self):
        self.rec.on_save(dr.summarize(_save()))
        self.rec.on_save(dr.summarize(_save([("smelter", "outpost_home", None)], seq=2)))
        self.rec.on_save(dr.summarize(_save([("smelter", "outpost_home", None)], tech=["x"], seq=3)))
        self.assertEqual(self.rec.open_id, 3)
        self.rec.on_line("#2 late reason\n")
        self.assertEqual(self.rec.open_id, 3)
        self.assertEqual(self.events()[-1]["ref"], 2)

    def test_same_write_sequence_ignored_and_restart_resumes(self):
        self.rec.on_save(dr.summarize(_save()))
        self.rec.on_save(dr.summarize(_save([("smelter", "outpost_home", None)])))  # seq unchanged
        self.assertEqual(len(self.events()), 1)
        self.rec.on_line("/n note before restart\n")
        self.rec.on_line("#1 reason before restart\n")
        self.assertEqual(self.events()[0]["commit"], "abc1234")
        again = dr.Recorder(self.save, copy_every_min=0, outpost_types_major=False)
        self.assertEqual(again.dir, self.rec.dir)
        self.assertEqual(again.next_id, 3)
        self.assertIsNotNone(again.last)


if __name__ == "__main__":
    unittest.main()
