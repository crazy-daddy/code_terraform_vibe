"""Stub tests for Crop Automator output room: harvests are only queued while
the output holds their yield (lib/crop_automator.py), and a
Forage pull wakes a parked automator only once it leaves room for one
harvest (storage.take_item())."""
import unittest
from unittest import mock

from game_stubs import CropAutomator, CropJob
from harness import StubTestCase, storage

import crop_automator
from crop_automator import CropAutomatorController, HARVEST_YIELD_DEFAULT, OUTPUT_CAP


class HarvestBudgetTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.machine = self.world.add_building("ca_1", self.world.home, "crop_automator", cls=CropAutomator)
        self.ctrl = CropAutomatorController(self.machine)

    def fill_output(self, units):
        self.machine.output_buffer["forage"] = units

    def test_budget_counts_whole_harvests_of_free_space(self):
        self.fill_output(OUTPUT_CAP - 100)
        self.assertEqual(self.ctrl.harvest_budget(), (0, 100))
        self.fill_output(OUTPUT_CAP - 2 * HARVEST_YIELD_DEFAULT - 1)
        self.assertEqual(self.ctrl.harvest_budget()[0], 2)

    def test_yield_follows_largest_recent_harvest_and_decays(self):
        self.ctrl.learn_yield(1800)
        self.assertEqual(self.ctrl._harvest_yield, 1800)
        self.ctrl.learn_yield(900)
        self.assertEqual(self.ctrl._harvest_yield, int(1800 * crop_automator.HARVEST_YIELD_DECAY))
        for _ in range(100):
            self.ctrl.learn_yield(900)
        self.assertEqual(self.ctrl._harvest_yield, 900)

    def test_harvests_beyond_budget_are_canceled_newest_first(self):
        self.machine.jobs = [CropJob(1, "harvest", "C5", state="blocked", blocker="output_full"),
                             CropJob(2, "plant", "C6", item_id="seed_crowncap"),
                             CropJob(3, "harvest", "C8"), CropJob(4, "harvest", "C9")]
        queued, _committed, blocked, harvests = self.ctrl.queued_jobs_info()
        self.assertIs(blocked, self.machine.jobs[0])
        kept, canceled = self.ctrl.trim_harvests(harvests, 1, queued)
        self.assertEqual(kept, 1)
        self.assertEqual(self.machine.canceled, [3, 4])
        self.assertEqual(queued, {"C5", "C6"})
        self.assertEqual([j.id for j in canceled], [3, 4])

    def test_no_room_cancels_blocked_head_but_not_a_working_harvest(self):
        self.machine.jobs = [CropJob(1, "harvest", "C5", state="working"), CropJob(2, "harvest", "C6")]
        _queued, _c, _b, harvests = self.ctrl.queued_jobs_info()
        kept, _canceled = self.ctrl.trim_harvests(harvests, 0, set())
        self.assertEqual((kept, self.machine.canceled), (1, [2]))

        self.machine.jobs = [CropJob(3, "harvest", "C7", state="blocked", blocker="output_full")]
        _queued, _c, _b, harvests = self.ctrl.queued_jobs_info()
        self.ctrl.trim_harvests(harvests, 0, set())
        self.assertEqual(self.machine.canceled, [2, 3])
        self.assertEqual(self.machine.jobs, [])


class WakeOnPullTests(StubTestCase):
    def pull(self, held, amount, harvest_yield=None):
        if harvest_yield is not None:
            self.world.notebook.set(storage.CROP_AUTOMATOR_STATUS_KEY, {"ca_1": {"harvest_yield": harvest_yield}})
        with mock.patch.object(storage, "crop_automator_forage", lambda outpost=None: [("ca_1", held, True, False)]), \
                mock.patch.object(storage, "wake_for_visit") as wake, \
                mock.patch.object(storage, "discover_storage_buildings", lambda outpost=None: []):
            storage.take_item(_Port(), "forage", amount)
        return wake.called

    def test_small_pull_from_a_full_automator_does_not_wake_it(self):
        self.assertFalse(self.pull(OUTPUT_CAP, 100))

    def test_pull_leaving_room_for_one_harvest_wakes_it(self):
        self.assertTrue(self.pull(OUTPUT_CAP, storage.CROP_AUTOMATOR_WAKE_FREE_MIN))

    def test_wake_threshold_follows_published_yield(self):
        self.assertFalse(self.pull(OUTPUT_CAP, 1500, harvest_yield=2700))
        self.assertTrue(self.pull(OUTPUT_CAP, 2700, harvest_yield=2700))


class ForageDrainOrderTests(StubTestCase):
    def test_inventory_and_warehouses_drain_before_any_automator(self):
        automators = [("ca_clogged", OUTPUT_CAP, True, False), ("ca_garden", 100, False, True), ("ca_fill", 5000, False, False)]
        cache = mock.Mock(building_stock=lambda _item_id: [("inventory", 5), ("wh_small", 10), ("wh_big", 2000)])
        with mock.patch.object(storage, "crop_automator_forage", lambda outpost=None: automators):
            order = [source for source, _units in storage._holder_candidates("forage", cache=cache)]
        self.assertEqual(order, ["inventory", "wh_big", "wh_small", "ca_clogged", "ca_garden", "ca_fill"])


class _Port:
    def connect(self, _source_id):
        return mock.Mock(status="not_local")

    def connected_id(self):
        return ""

    def take(self, _item_id, _count):
        return mock.Mock(status="ok", moved=0)


if __name__ == "__main__":
    unittest.main()
