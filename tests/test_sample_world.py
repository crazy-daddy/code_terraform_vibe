"""Smoke tests for tests/sample_world.py: every size builds and the main controllers run on it cleanly."""
import unittest

from harness import StubTestCase, fabricator, smelter, supply_dock
import sample_world


class SampleWorldTests(StubTestCase):
    def use(self, size):
        sample = sample_world.build_sample_world(size)
        self.world = sample.world  # tearDown checks this world's console for swallowed bugs
        return sample

    def test_every_size_runs_controllers_and_plans_every_dock(self):
        for size in sample_world.SIZES:
            with self.subTest(size=size):
                sample = self.use(size)
                fabricator.FabricatorController(sample.fabricators[0]).step()
                smelter.SmelterController(sample.smelters[0]).step()
                plan = supply_dock.plan_dock_assignments(sample.world.get_component("clock"))
                self.assertEqual(set(plan), {dock.id for dock in sample.docks})
                self.assertTrue(any(plan.values()))

    def test_remote_outposts_hold_machines(self):
        sample = self.use("medium")
        remote_ids = {outpost.id for outpost in sample.remotes}
        self.assertTrue(any(f.outpost.id in remote_ids for f in sample.fabricators))
        self.assertTrue(any(d.outpost.id in remote_ids for d in sample.docks))

    def test_route_scenario_is_seeded(self):
        self.assertEqual(sample_world.route_scenario("small"), sample_world.route_scenario("small"))
        dests, sources = sample_world.route_scenario("large")
        self.assertEqual((len(dests), len(sources)), (4, 20))


if __name__ == "__main__":
    unittest.main()
