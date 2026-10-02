import os
import sys
import unittest

import harness  # noqa: F401  (puts the tiered lib/ folders on sys.path)
import wildlife_data as wd
import wildlife_model as wm

sys.path.insert(0, os.path.join(harness.REPO_ROOT, "devtools"))
import wildlife_optimizer as wo  # noqa: E402

# Untreated full-support hours per stage (docs/cheatsheet/wildlife.md §1l table).
STAGE_HOURS = {
    "salt_tortoise": (351, 310, 464, 1123, 1169),
    "veil_mantle": (468, 413, 619, 1497, 1559),
    "hive_sentinel": (702, 619, 929, 2246, 2338),
    "spire_drake": (1170, 1032, 1548, 3743, 3897),
}
STAGE_SPANS = ((4, 250), (250, 2500), (2500, 25000), (25000, 175000), (175000, 350000))


def hours(species, start, end, effects=()):
    pop, t = float(start), 0.0
    while pop < end:
        rate = wm.breeding_rate(species, pop, list(effects))
        dt = max(0.01, min(5.0, 0.005 * pop / rate))
        pop += rate * dt
        t += dt
    return t


class WildlifeModelTest(unittest.TestCase):
    def test_stage_hours_match_cheatsheet(self):
        for species, expected in STAGE_HOURS.items():
            for (start, end), want in zip(STAGE_SPANS, expected):
                self.assertAlmostEqual(hours(species, start, end), want, delta=want * 0.05, msg=f"{species} {start}->{end}")

    def test_insight_curve(self):
        self.assertEqual(wm.insight_at(4), 0.0)
        self.assertAlmostEqual(wm.insight_at(10), 1.0)
        self.assertAlmostEqual(wm.insight_at(55), 1.25)
        self.assertAlmostEqual(wm.insight_at(350000), 7.0)
        self.assertAlmostEqual(wm.insight_at(10 ** 7), 7.0)
        self.assertAlmostEqual(wm.insight_between(4, 350000) * len(wd.SPECIES), 112.0)

    def test_stages_and_capacity(self):
        self.assertEqual(wm.stage_of(249), 0)
        self.assertEqual(wm.stage_of(250), 1)
        self.assertEqual(wm.stage_of(175000), 3)
        self.assertEqual(wm.stage_of(175001), 4)
        self.assertEqual(wm.capacity(3), 175000)
        self.assertEqual(wm.capacity(4, tier=2), 350000)

    def test_required_fluids_and_retain(self):
        self.assertEqual(wm.required_fluids("salt_tortoise", 2), (None, None))
        self.assertEqual(wm.required_fluids("salt_tortoise", 3), ("swamp_gas", None))
        self.assertEqual(wm.required_fluids("veil_mantle", 1), ("ammonia", None))
        self.assertEqual(wm.required_fluids("bone_walker", 4), ("sulfur_gas", "cryofluid"))
        self.assertEqual(wm.required_fluids("bone_walker", 4, retain_gas=True, retain_liquid=True), ("ammonia", "brine"))
        self.assertEqual(wm.required_fluids("glacial_wyrm", 2), ("sulfur_gas", "cryofluid"))
        self.assertEqual(wm.required_fluids("glacial_wyrm", 3), ("chlorine", "cryofluid"))

    def test_bonus_resolution(self):
        fx = wm.node_effects(["many_chambers", "complete_veil", "saltwise_digestion"], "hive_sentinel")
        static = wm.static_bonuses(fx)
        self.assertEqual(static["founding"], 6)         # own Adaptation 4 + complete_veil 2
        self.assertAlmostEqual(static["feed_multiplier"], 0.5)  # saltwise is salt_tortoise-only
        self.assertEqual(wm.founding_population(fx), 10)
        # below-2,500 condition and the global +150 % speed cap
        drake = wm.node_effects(["spire_nursery", "sky_dominion", "harmonic_structure"], "spire_drake")
        speed_low = wm.dynamic_bonuses(drake, 100, 0, 0)[0]
        speed_high = wm.dynamic_bonuses(drake, 3000, 2, 0)[0]
        self.assertAlmostEqual(speed_low, 1.45 * 1.12 - 1)
        self.assertAlmostEqual(speed_high, 0.12)
        # per-other speed, capped at 12 %
        mycelium = wm.node_effects(["planetary_mycelium"], "salt_tortoise")
        self.assertAlmostEqual(wm.dynamic_bonuses(mycelium, 100, 0, 5)[0], 0.05)
        self.assertAlmostEqual(wm.dynamic_bonuses(mycelium, 100, 0, 15)[0], 0.12)

    def test_feed_multipliers_match_feed_multiplier(self):
        import wildlife_common as wc
        all_nodes = sorted(tree[slot][0] for tree in wd.BONUS_TREES.values() for slot in ("adaptation", "breakthrough"))
        for purchased in (set(), set(all_nodes[::2]), set(all_nodes[1::3]), set(all_nodes)):
            species = sorted(wd.SPECIES)
            got = wc.feed_multipliers(species, purchased)
            for s in species:
                self.assertEqual(got[s], wc.feed_multiplier(s, purchased), (s, sorted(purchased)))

    def test_natural_growth_ceiling(self):
        rate = wm.breeding_rate("salt_tortoise", 10 ** 9, [])
        self.assertAlmostEqual(rate, wd.NATURAL_RATE_CEILING, delta=0.5)
        self.assertAlmostEqual(wm.breeding_rate("salt_tortoise", 5000, []), 28.0, delta=0.5)


def pillar_scenario(habitats):
    """Scenario the shipped WILDLIFE_SCHEDULES were solved for."""
    return wo.Scenario(habitats=habitats, target=wo.PILLAR_WILDLIFE, common_lead_h=120.0, refined_lead_h=240.0, deep_lead_h=240.0, allow_unadapted=True)


class WildlifeOptimizerTest(unittest.TestCase):
    def test_schedule_steps_are_valid(self):
        for habitats, schedule in wd.WILDLIFE_SCHEDULES.items():
            items = set(wo.all_items(pillar_scenario(habitats)))
            for step in schedule:
                self.assertIn(step, items)

    def test_schedule_not_worse_than_default(self):
        for habitats, schedule in wd.WILDLIFE_SCHEDULES.items():
            scenario = pillar_scenario(habitats)
            default = wo.start_sim(scenario).run(wo.default_order(scenario), wo.default_order(scenario))
            best = wo.start_sim(scenario).run(list(schedule), wo.default_order(scenario))
            self.assertLess(best, default)

    def test_schedule_for_habitat_count(self):
        self.assertIs(wm.schedule_for(10), wd.WILDLIFE_SCHEDULES[10])
        self.assertIs(wm.schedule_for(12), wd.WILDLIFE_SCHEDULES[10])
        self.assertIs(wm.schedule_for(7), wd.WILDLIFE_SCHEDULES[5])
        self.assertIs(wm.schedule_for(3), wd.WILDLIFE_SCHEDULES[5])
        self.assertIs(wm.schedule_for(20), wd.WILDLIFE_SCHEDULES[16])

    def test_parking_frees_habitats_only_when_short(self):
        order = wo.default_order(pillar_scenario(16))
        for habitats, faster in ((5, True), (16, False)):
            parked = wo.start_sim(pillar_scenario(habitats)).run(order, order)
            scenario = pillar_scenario(habitats)
            scenario.park_finished = False
            housed = wo.start_sim(scenario).run(order, order)
            if faster:
                self.assertLess(parked, housed)
            else:
                self.assertAlmostEqual(parked, housed, delta=housed * 0.01)

    def test_holding_insight_for_an_early_breakthrough_is_slower(self):
        scenario = wo.Scenario()
        default = wo.start_sim(scenario).run(wo.default_order(scenario), wo.default_order(scenario))
        gut = wo.start_sim(scenario).run(wo.gut_order(scenario), wo.default_order(scenario))
        self.assertGreater(gut, default)

    def test_deterministic(self):
        scenario = wo.Scenario()
        order = wo.default_order(scenario)
        self.assertEqual(wo.start_sim(scenario).run(order, order), wo.start_sim(scenario).run(order, order))


if __name__ == "__main__":
    unittest.main()
