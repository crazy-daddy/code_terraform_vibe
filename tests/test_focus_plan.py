"""Tests for autoplay/lib/focus_plan.py: pillar scores from research wants, even growth, swap hysteresis, the BUILD-card swap row."""

import unittest

import harness  # noqa: F401 (side effect: installs game builtins and lib paths)

# isort: split
import building_plan as bp
import focus_plan as fp
import game_phase as gp
import pillar_swap
from archive import archive
from harness import StubTestCase

EXPANSION = ["research_data_archive", gp.CONTROL_ROOM_RESEARCH]


def pillar(value, target=100.0, complete=False):
    return {"value": value, "target": target, "next_target": None, "progress": 0.0, "complete": complete, "phase": 1}


def snap(research=EXPANSION, pillars=None, history=None, tp=200000):
    base = {"temperature": pillar(50.0, 1000.0), "oxygen": pillar(20.0, 1000.0), "pressure": pillar(1.0, 100.0)}
    base.update(pillars or {})
    return {
        "tick": 0,
        "tp": tp,
        "pillars": base,
        "research": set(research),
        "drills": False,
        "done": {},
        "history": history or {},
    }


def rising(pillar_id, per_tick):
    return {pillar_id: [[0, 0.0], [36000, per_tick * 36000]]}


def packs_ok(_type_id, _tier):
    return True


def packs_missing(_type_id, _tier):
    return False


class ScoreTests(unittest.TestCase):
    def test_want_on_nearest_research_wins(self):
        s = snap(history={"oxygen": [[0, 19.0], [36000, 20.0]], "pressure": [[0, 0.5], [36000, 1.0]]})
        wants = [{"research": "research_drill_industrial", "urgency": "now", "why": "titanium"}]
        totals, mode, why = fp.scores(s, wants)
        self.assertEqual(mode, "research")
        self.assertGreater(totals["o2"], 0)
        self.assertEqual(totals["pressure"], 0)
        self.assertIn("research_drill_industrial", why[0])

    def test_unlocked_or_foreign_wants_ignored(self):
        s = snap(research=EXPANSION + ["research_drill_industrial"])
        wants = [
            {"research": "research_drill_industrial", "urgency": "now", "why": "done"},
            {"research": "research_seed_maker", "urgency": "now", "why": "biomass pillar, not atmosphere"},
            {"research": "research_nope", "urgency": "now", "why": "unknown"},
        ]
        totals, mode, _why = fp.scores(s, wants)
        self.assertEqual(mode, "even")
        self.assertEqual(sum(totals.values()), fp.EVEN_SCORE)

    def test_even_growth_picks_lowest_share(self):
        s = snap(
            pillars={
                "pressure": pillar(1.0, 100.0),
                "oxygen": pillar(500.0, 1000.0),
                "temperature": pillar(500.0, 1000.0),
            }
        )
        totals, mode, why = fp.scores(s, [])
        self.assertEqual(mode, "even")
        self.assertEqual(totals["pressure"], fp.EVEN_SCORE)
        self.assertIn("Press", why[0])

    def test_complete_pillars_drop_out(self):
        s = snap(pillars={p: pillar(1.0, complete=True) for p in gp.ATMOSPHERE})
        self.assertEqual(fp.scores(s, []), ({}, "done", ["every atmosphere pillar is complete"]))
        s = snap(pillars={"oxygen": pillar(1000.0, 1000.0, complete=True)})
        wants = [{"research": "research_oxygen_mk4_pack", "urgency": "now", "why": "o2 done anyway"}]
        totals, _mode, _why = fp.scores(s, wants)
        self.assertNotIn("o2", totals)

    def test_no_rate_counts_far(self):
        s = snap()
        rows = fp.want_rows(s, [{"research": "research_warehouse", "urgency": "now", "why": "x"}])
        self.assertAlmostEqual(rows[0][1], fp.URGENCY_WEIGHT["now"] / fp.NO_RATE_ETA_H)


class DecideTests(unittest.TestCase):
    def test_swap_when_best_clears_margin(self):
        s = snap(history={"oxygen": [[0, 19.0], [36000, 20.0]]})
        wants = [{"research": "research_drill_industrial", "urgency": "now", "why": "titanium"}]
        focus = fp.decide(s, wants, {"temp_heater": [1, 1]}, packs_ok)
        self.assertEqual((focus["pillar"], focus["current"], focus["swap"]), ("o2", "heat", True))
        entry = fp.swap_entry(focus) or {}
        self.assertEqual(
            (entry["kind"], entry["from"], entry["to"], entry["type_id"]), ("swap", "heat", "o2", "oxygen_generator")
        )
        self.assertEqual(fp.proposal_id(focus), "focus:heat:o2")

    def test_no_swap_when_already_on_focus(self):
        s = snap(history={"oxygen": [[0, 19.0], [36000, 20.0]]})
        wants = [{"research": "research_drill_industrial", "urgency": "now", "why": "titanium"}]
        focus = fp.decide(s, wants, {"oxygen_generator": [2]}, packs_ok)
        self.assertEqual((focus["pillar"], focus["swap"]), ("o2", False))
        self.assertIsNone(fp.swap_entry(focus))

    def test_margin_keeps_pressure_sticky(self):
        s = snap(history={"oxygen": [[0, 19.0], [36000, 20.0]], "pressure": [[0, 0.5], [36000, 1.0]]})
        wants = [
            {"research": "research_drill_industrial", "urgency": "soon", "why": "titanium"},  # o2, ~10 h
            {"research": "research_hydrology_survey", "urgency": "soon", "why": "water"},  # pressure, ~34 h
        ]
        on_pressure = fp.decide(s, wants, {"pressure_generator": [1]}, packs_ok)
        self.assertEqual(on_pressure["pillar"], "o2")
        self.assertTrue(on_pressure["swap"])  # 3.4x ahead clears even the pressure margin of 2
        wants[1]["urgency"] = "now"  # pressure want 3x heavier: o2 1.13x ahead, under the margin
        on_pressure = fp.decide(s, wants, {"pressure_generator": [1]}, packs_ok)
        self.assertEqual(on_pressure["pillar"], "o2")
        self.assertFalse(on_pressure["swap"])
        self.assertTrue(any("not ahead" in w for w in on_pressure["why"]))

    def test_early_phase_and_running_swap_suppress(self):
        s = snap(research=["research_data_archive"], history={"oxygen": [[0, 19.0], [36000, 20.0]]})
        wants = [{"research": "research_drill_industrial", "urgency": "now", "why": "titanium"}]
        focus = fp.decide(s, wants, {"temp_heater": [1]}, packs_ok)
        self.assertFalse(focus["swap"])
        self.assertIn("early buyer owns the opening order", focus["why"])
        focus = fp.decide(
            snap(history={"oxygen": [[0, 19.0], [36000, 20.0]]}),
            wants,
            {"temp_heater": [1]},
            packs_ok,
            swap_running=True,
        )
        self.assertFalse(focus["swap"])

    def test_pack_gate_only_above_mk1(self):
        s = snap(history={"oxygen": [[0, 19.0], [36000, 20.0]]})
        wants = [{"research": "research_drill_industrial", "urgency": "now", "why": "titanium"}]
        self.assertTrue(fp.decide(s, wants, {"temp_heater": [1]}, packs_missing)["swap"])
        focus = fp.decide(s, wants, {"temp_heater": [1, 3]}, packs_missing)
        self.assertFalse(focus["swap"])
        self.assertIn("O2 packs up to Mk 3 not available", focus["why"])
        self.assertEqual(fp.swap_tier({"temp_heater": [4, 2]}, "heat"), pillar_swap.MAX_SWAP_TIER)
        only_mk2 = lambda _type_id, tier: tier <= 2
        focus = fp.decide(s, wants, {"temp_heater": [3]}, only_mk2)
        self.assertTrue(focus["swap"])
        self.assertIn("O2 swap lands at Mk 2", focus["why"])
        self.assertEqual(fp.target_tier("oxygen_generator", 3, only_mk2), 2)

    def test_zero_score_current_needs_a_floor_and_ids_count_once(self):
        s = snap()  # no rates: every want is NO_RATE_ETA_H away, scores well under MIN_SWAP_SCORE
        wants = [{"research": "research_drill_industrial", "urgency": "now", "why": "titanium"}]
        focus = fp.decide(s, wants, {"temp_heater": [1]}, packs_ok)
        self.assertEqual(focus["pillar"], "o2")
        self.assertFalse(focus["swap"])
        self.assertTrue(any("scores under" in w for w in focus["why"]))
        twice = wants + [dict(wants[0], why="again")]
        self.assertEqual(fp.scores(s, twice)[0]["o2"], fp.scores(s, wants)[0]["o2"])

    def test_even_growth_needs_lag(self):
        s = snap(
            pillars={
                "pressure": pillar(10.0, 100.0),
                "oxygen": pillar(150.0, 1000.0),
                "temperature": pillar(500.0, 1000.0),
            }
        )
        focus = fp.decide(s, [], {"oxygen_generator": [1]}, packs_ok)
        self.assertEqual(
            (focus["mode"], focus["pillar"], focus["swap"]), ("even", "pressure", False)
        )  # 15 vs 10: lag 5
        s = snap(
            pillars={
                "pressure": pillar(10.0, 100.0),
                "oxygen": pillar(300.0, 1000.0),
                "temperature": pillar(500.0, 1000.0),
            }
        )
        focus = fp.decide(s, [], {"oxygen_generator": [1]}, packs_ok)
        self.assertTrue(focus["swap"])  # 30 vs 10: lag 20

    def test_current_pillar_and_wants_from_needs(self):
        self.assertIsNone(fp.current_pillar({}))
        self.assertEqual(fp.current_pillar({"temp_heater": [1], "oxygen_generator": [1, 2]}), "o2")
        self.assertEqual(fp.current_pillar({"temp_heater": [1], "oxygen_generator": [1]}), "heat")
        needs = [
            {"role": "power", "urgency": "soon", "why": "steam", "blocked_by": "research_thermal_cap"},
            {"role": "mining", "urgency": "soon", "why": "x"},
        ]
        self.assertEqual(
            fp.wants_from_needs(needs), [{"research": "research_thermal_cap", "urgency": "soon", "why": "power: steam"}]
        )


class CardFlowTests(StubTestCase):
    def test_swap_row_approve_requests_swap_and_settles(self):
        focus = {"pillar": "o2", "current": "heat", "swap": True, "why": ["titanium"], "scores": {}, "mode": "research"}
        proposals = bp.fresh_proposals({"outposts": [], "kits": set()}, {}, {}, focus)
        pid = "focus:heat:o2"
        self.assertEqual(proposals[pid]["kind"], "swap")
        planner = bp.BuildingPlanner(bp.building_ops.log)
        archive.set(bp.PROPOSALS_KEY, bp.merge({}, proposals, 1))
        planner.full_tick = 0  # not due: no fresh pass, the stored swap row stays
        self.assertTrue(bp.answer(pid, True))
        self.assertEqual(planner.run_pass({"outposts": [], "kits": set()}), "working")
        self.assertTrue(pillar_swap.is_running())
        self.assertEqual(bp.load()[pid]["status"], "queued")
        archive.set(pillar_swap.SWAP_KEY, dict(pillar_swap.swap_state() or {}, state="done"))
        planner.run_pass({"outposts": [], "kits": set()})
        self.assertNotIn(pid, bp.load())

    def test_refused_and_stopped_swaps(self):
        focus = {"pillar": "o2", "current": "heat", "swap": True, "why": ["titanium"], "scores": {}, "mode": "research"}
        pid = "focus:heat:o2"
        planner = bp.BuildingPlanner(bp.building_ops.log)
        archive.set(
            bp.PROPOSALS_KEY, bp.merge({}, bp.fresh_proposals({"outposts": [], "kits": set()}, {}, {}, focus), 1)
        )
        planner.full_tick = 0
        pillar_swap.request_swap("pressure", "heat")  # another swap runs
        bp.answer(pid, True)
        planner.run_pass({"outposts": [], "kits": set()})
        self.assertEqual((bp.load()[pid]["status"], bp.load()[pid]["blocked"]), ("proposed", "swap running"))
        archive.set(pillar_swap.SWAP_KEY, None)
        archive.set(
            bp.PROPOSALS_KEY, bp.merge({}, bp.fresh_proposals({"outposts": [], "kits": set()}, {}, {}, focus), 1)
        )
        bp.answer(pid, True)
        planner.run_pass({"outposts": [], "kits": set()})
        self.assertEqual(bp.load()[pid]["status"], "queued")
        archive.set(pillar_swap.SWAP_KEY, dict(pillar_swap.swap_state() or {}, state="stopped"))
        planner.run_pass({"outposts": [], "kits": set()})
        self.assertEqual(bp.load()[pid]["status"], "rejected")  # held: not re-proposed by the next pass
        held = bp.merge(bp.load(), bp.fresh_proposals({"outposts": [], "kits": set()}, {}, {}, focus), 2)
        self.assertEqual(held[pid]["status"], "rejected")

    def test_stale_approved_swap_drops_when_focus_moves(self):
        focus = {"pillar": "o2", "current": "heat", "swap": True, "why": [], "scores": {}, "mode": "research"}
        proposals = bp.merge({}, bp.fresh_proposals({"outposts": [], "kits": set()}, {}, {}, focus), 1)
        proposals["focus:heat:o2"]["status"] = "approved"
        bp._drop_stale_swaps(proposals, {})
        merged = bp.merge(proposals, {}, 2)
        self.assertNotIn("focus:heat:o2", merged)

    def test_full_pass_writes_focus(self):
        planner = bp.BuildingPlanner(bp.building_ops.log)
        self.world.research.unlocked.update(EXPANSION)
        planner.run_pass({"outposts": [], "kits": set()})
        focus = archive.get(fp.FOCUS_KEY, {})
        self.assertEqual(
            focus.get("mode"), "research"
        )  # no pillar rows in the stub world: every atmosphere pillar counts as open
        self.assertIn(focus.get("pillar"), ("o2", "heat", "pressure"))
        self.assertIn("tp", archive.get(gp.HISTORY_KEY, {}))


if __name__ == "__main__":
    unittest.main()
