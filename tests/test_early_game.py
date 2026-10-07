"""devtools/early_game.py: onboarding steps, idle starts and the speedrun advisor of
`scripts_sync.py watch --early`, against a temporary save folder and fake hooks."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

DEVTOOLS = Path(__file__).resolve().parent.parent / "devtools"
if str(DEVTOOLS) not in sys.path:
    sys.path.insert(0, str(DEVTOOLS))

import early_game  # noqa: E402


class _Save:
    """A save_X_scripts folder: workspace context, state file and all.log."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp())
        self.dir = self.root / "save_test_scripts"
        (self.dir / "logs").mkdir(parents=True)
        self.slots = {}      # {stem: workspace info}
        self.texts = {}      # {stem: slot file text} for matched slots
        self.tiered = set()  # stems whose source sits in a tier dir
        self.machines = {}
        self.state = {}
        self.log("")
        self.write()

    def log(self, text):
        (self.dir / "logs" / "all.log").write_text(text, encoding="utf-8")

    def write(self):
        (self.dir / "codeterraform-workspace.json").write_text(json.dumps({"context": {"machines": self.machines}}), encoding="utf-8")
        (self.root / "save_test.json").write_text(json.dumps({"state": self.state}), encoding="utf-8")

    def matched_text(self, stem, tiered_only):
        if stem not in self.texts or (tiered_only and stem not in self.tiered):
            return None
        return self.texts[stem]


class EarlyGameTests(unittest.TestCase):
    def setUp(self):
        self.save = _Save()
        self.started, self.lines, self.attempts = [], [], []
        self.refuse = False
        self.output_t = 0.0
        self.addCleanup(shutil.rmtree, self.save.root, True)
        hooks = early_game.Hooks(
            slots=lambda: self.save.slots,
            matched_text=self.save.matched_text,
            restart=self.restart,
            echo=self.lines.append,
            warn=self.lines.append,
            last_output=lambda: self.output_t,
        )
        self.early = early_game.EarlyGame(self.save.dir, hooks)

    def restart(self, stem, _body):
        self.attempts.append(stem)
        if self.refuse:
            return False
        self.started.append(stem)
        return True

    def test_status_block_names_the_next_click_and_reprints_after_scrolling(self):
        self.save.log("power system can be activated\n")
        self.early.onboarding_pass()
        self.early.advisor_pass()
        self.early.advisor_pass()
        hints = [line for line in self.lines if "Turn on Power" in line]
        self.assertEqual(len(hints), 1, self.lines)
        self.assertEqual(self.started, [])
        # Sync output after the block, quiet for ADVISOR_QUIET_S since: print it again.
        self.early.last_advice_t -= early_game.ADVISOR_QUIET_S + 2.0
        self.output_t = self.early.last_advice_t + 1.0
        self.early.advisor_pass()
        self.assertEqual(len([line for line in self.lines if "Turn on Power" in line]), 2, self.lines)

    def test_slot_gate_until_onboarded(self):
        self.assertTrue(early_game.slot_allowed("planet_power", "planet_power", False))
        self.assertTrue(early_game.slot_allowed("harvester_1", "harvester", False))
        self.assertTrue(early_game.slot_allowed("scanner_1", "scanner", False))
        self.assertFalse(early_game.slot_allowed("bio_lab_1", "bio_lab", False))
        self.assertTrue(early_game.slot_allowed("bio_lab_1", "bio_lab", True))

    def test_refused_start_retries_after_a_while(self):
        self.save.slots = {"bio_lab_1": {"status": "idle"}}
        self.save.texts = {"bio_lab_1": "a"}
        self.save.tiered = {"bio_lab_1"}
        self.refuse = True
        self.early.idle_pass()
        self.early.idle_pass()
        self.assertEqual(self.attempts, ["bio_lab_1"])
        text, t0, started = self.early.started["bio_lab_1"]
        self.early.started["bio_lab_1"] = (text, t0 - early_game.STEP_RETRY_S, started)
        self.refuse = False
        self.early.idle_pass()
        self.assertEqual(self.started, ["bio_lab_1"])

    def test_starts_the_next_undone_step_and_retries_later(self):
        self.save.log("power system can be activated\n")
        self.save.slots["planet_power"] = {"status": "idle"}
        self.save.texts["planet_power"] = "activate_power()\n"
        self.early.onboarding_pass()
        self.early.onboarding_pass()
        self.assertEqual(self.started, ["planet_power"])
        stem, (text, t0, started) = next(iter(self.early.started.items()))
        self.early.started[stem] = (text, t0 - early_game.STEP_RETRY_S, started)
        self.early.onboarding_pass()
        self.assertEqual(self.started, ["planet_power", "planet_power"])

    def test_sensor_steps_follow_the_repaired_flag(self):
        self.save.log("Establish Uplink: online\n")
        self.save.machines = {"pressure_sensor": {"data": {"repaired": 1}}, "oxygen_sensor": {"data": {"repaired": 1}}}
        self.save.write()
        self.early.onboarding_pass()
        self.assertTrue(self.early.onboarded)

    def test_idle_pass_starts_tier_slots_once_per_text(self):
        self.save.slots = {"solar_generator_1": {"status": "idle"}, "lattice": {"status": "idle"},
                           "boot": {"status": "idle"}, "rover_1": {"status": "running"}}
        self.save.texts = {"solar_generator_1": "a", "lattice": "b", "boot": "c", "rover_1": "d"}
        self.save.tiered = {"solar_generator_1", "rover_1", "boot"}
        self.early.idle_pass()
        self.early.idle_pass()
        self.assertEqual(self.started, ["solar_generator_1"])
        self.save.texts["solar_generator_1"] = "a2"  # pushed again: a new text starts again
        self.early.idle_pass()
        self.assertEqual(self.started, ["solar_generator_1", "solar_generator_1"])


class RecommendationTests(unittest.TestCase):
    def metrics(self, **overrides):
        state = {"researchRates": {"terraform": {"lastValue": 5000}}, "planet": {"atmosphere": {"oxygen": 0.5, "pressure": 0.01}},
                 "machines": {"s1": {"typeId": "solar_generator"}}}
        m = early_game.live_metrics(state, {}, set())
        m.update(overrides)
        return m

    def test_manual_purchases_before_ship_computer(self):
        phase, _milestones, recs = early_game.recommendations(self.metrics())
        self.assertIn("Oxygen", phase)
        self.assertTrue(any(r.startswith("Buy next: Battery, O2 Generator") for r in recs), recs)  # no battery yet: one first

    COUNTS = {"solar": 4, "battery": 3, "o2gen": 11, "pressure": 0, "heater": 0, "bio": 3}

    def order(self, day_fraction, stored_wh, counts=None, capacity_wh=1500.0):
        power = {"day_fraction": day_fraction, "stored_wh": stored_wh, "capacity_wh": capacity_wh}
        return early_game.oxygen_rush_order(counts or self.COUNTS, power, steps=6)

    def test_oxygen_first_while_batteries_last_the_night(self):
        self.assertEqual(self.order(0.9, 1500.0)[0], "O2 Generator")
        fresh = {"solar": 1, "battery": 1, "o2gen": 0, "pressure": 0, "bio": 3}
        self.assertEqual(self.order(0.45, 500.0, fresh, 500.0)[0], "O2 Generator")  # no power anchor up front

    def test_no_solar_at_night_or_late_afternoon(self):
        for day_fraction in (0.0, 0.2, 0.75, 0.9):
            order = self.order(day_fraction, 100.0, dict(self.COUNTS, battery=2), 1000.0)
            self.assertNotIn("Solar", order, (day_fraction, order))
            self.assertIn("Battery", order)  # arrives charged: bridges the night

    def test_power_stays_inside_the_base_slots_and_layout(self):
        counts = {"solar": 5, "battery": 2, "o2gen": 12, "pressure": 0, "heater": 0, "bio": 3}
        for day_fraction in (0.3, 0.5, 0.9):
            order = self.order(day_fraction, 1000.0, counts, 1000.0)
            total = sum(counts[k] for k in ("solar", "battery", "o2gen", "pressure", "heater", "bio"))
            total += len(order)
            self.assertLessEqual(total, early_game.BASE_SLOTS, (day_fraction, order))
            self.assertLessEqual(5 + order.count("Solar"), early_game.RUSH_SOLAR_MAX)
            self.assertLessEqual(2 + order.count("Battery"), early_game.RUSH_BATTERY_MAX)

    def test_last_solar_after_all_o2_generators(self):
        counts = {"solar": 5, "battery": 3, "o2gen": 13, "pressure": 0, "heater": 0, "bio": 3}
        self.assertEqual(self.order(0.4, 1500.0, counts), ["Solar"])  # 24/25 slots: the sixth panel
        self.assertEqual(self.order(0.9, 1500.0, counts), [])  # too late in the day to pay off

    def test_solar_by_day_when_panels_cannot_cover_the_load(self):
        self.assertEqual(self.order(0.3, 300.0)[0], "Solar")

    def test_night_drain_runs_until_the_morning_peak(self):
        # Before dawn the batteries also carry the weak dawn sun, not only the dark hours.
        until_dawn = early_game.lowest_charge_through_night(0.2, 1000.0, 1500.0, 4, 100.0)
        self.assertLess(until_dawn, 1000.0 - 100.0 * early_game.LOAD_MARGIN * 0.05 * 24.0)

    def test_buyer_takes_over_after_ship_computer(self):
        _phase, _milestones, recs = early_game.recommendations(self.metrics(computer=True))
        self.assertFalse(any(r.startswith("Buy") for r in recs), recs)

    def test_contract_click_until_its_slot_exists(self):
        _p, _m, recs = early_game.recommendations(self.metrics(o2=3.5))
        self.assertTrue(any("Sealed Vault" in r for r in recs))
        _p, _m, recs = early_game.recommendations(self.metrics(o2=3.5, slot_stems={"sealed_vault"}))
        self.assertFalse(any("Sealed Vault" in r for r in recs))


if __name__ == "__main__":
    unittest.main()
