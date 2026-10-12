"""lib/demand_publisher.py: the signature-gated, sliced publisher of the shared demand record."""

import unittest
from unittest import mock

import demand_publisher
import production_demand_record as record
from game_stubs import SMELTER_RECIPES
from harness import SEGMENT_ORDER, StubTestCase, home_order, production


class PublisherCase(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.remote = w.add_outpost("outpost_2")
        w.add_smelter("smelter_1", w.home)
        w.add_smelter("smelter_2", self.remote, SMELTER_RECIPES)
        w.add_fabricator("fabricator_1", w.home)
        w.add_fabricator("fabricator_2", self.remote)
        home_order(SEGMENT_ORDER)
        w.notebook.set(production.SITE_PLAN_KEY, {"gas_pipe_segment": ["outpost_2"]})
        self.publisher = demand_publisher.DemandPublisher()

    def refresh(self, now=None):
        """step() until a publish; returns how many calls it took."""
        now = self.world.clock.now if now is None else now
        for calls in range(1, 50):
            if self.publisher.step(now, {}):
                return calls
        self.fail("no publish within 50 steps")


class AtomicTaskTests(PublisherCase):
    def test_every_task_runs_atomically_without_a_skip(self):
        """A refresh's tasks only read: an archive write or console print inside one raises in the
        stub as in game, and the task would be skipped."""
        w = self.world
        w.notebook.data.pop("production.ingot_stock_targets", None)  # the seed write happens in the prefetch
        w.notebook.data.pop("fabricator.manual_orders", None)
        with mock.patch.object(demand_publisher, "ATOMIC_TASKS", True):
            self.refresh()
        self.assertNotIn("demand_publisher.Refresh", self.debug_log())
        stored, _state = record.read_record(w.clock.now)
        assert stored is not None
        self.assertEqual(sorted(stored["smelter"]["sites"]), ["home", "outpost_2"])

    def test_a_failing_task_is_skipped_and_the_rest_publishes(self):
        def boom(*_args):
            raise RuntimeError("callback function cannot change game state")

        with mock.patch.object(demand_publisher, "site_smelter_demands", boom):
            self.refresh()
        stored, _state = record.read_record(self.world.clock.now)
        assert stored is not None
        self.assertEqual(sorted(stored["sites"]), ["home", "outpost_2"])
        self.assertIn("2 task(s) skipped", self.debug_log())


class SignatureGateTests(PublisherCase):
    def test_nothing_happens_without_a_change_inside_the_backstop(self):
        w = self.world
        self.refresh()
        stamped = record.record_tick()
        for offset in (1, 100, demand_publisher.DEMAND_BACKSTOP_TICKS - 1):
            self.assertFalse(self.publisher.step(w.clock.now + offset, {}))
        self.assertEqual(record.record_tick(), stamped)
        self.assertIsNone(self.publisher.cache)

    def test_a_changed_signature_publishes_once_after_the_slices(self):
        w = self.world
        self.refresh()
        first = record.record_tick()
        w.clock.now += 10
        w.notebook.set("fabricator.manual_orders", {"gas_pipe_segment": 3})
        # The stub clock stands still, so one call runs every slice and publishes.
        self.assertEqual(self.refresh(), 1)
        self.assertEqual(record.record_tick(), first + 10)
        # With no tick budget per call, one task per call: network, then per site the Fabricator part,
        # Smelter need and ingot buffer (home, outpost_2), then finish.
        w.clock.now += 10
        w.notebook.set("fabricator.manual_orders", {"gas_pipe_segment": 4})
        with mock.patch.object(demand_publisher, "DEMAND_SLICE_TICKS", 0):
            calls = self.refresh()
        self.assertEqual(calls, 1 + 2 * 3 + 1)
        self.assertEqual(record.record_tick(), first + 20)
        stored, state = record.read_record(w.clock.now)
        self.assertEqual(state, record.FRESH)
        assert stored is not None
        self.assertEqual(sorted(stored["sites"]), ["home", "outpost_2"])
        self.assertEqual(sorted(stored["smelter"]["sites"]), ["home", "outpost_2"])
        self.assertEqual(record.network_entry(stored), production.fabricator_target_ladders())
        self.assertFalse(self.publisher.step(w.clock.now, {}))  # signature remembered: idle again

    def test_the_backstop_republishes_an_unchanged_signature(self):
        w = self.world
        self.refresh()
        later = w.clock.now + demand_publisher.DEMAND_BACKSTOP_TICKS
        self.refresh(later)
        self.assertEqual(record.record_tick(), later)

    def test_publish_from_cache_is_one_call_and_quiets_step(self):
        w = self.world
        self.assertTrue(self.publisher.publish_from_cache(production.SourceCache(), w.clock.now))
        self.assertEqual(record.read_record(w.clock.now)[1], record.FRESH)
        self.assertFalse(self.publisher.step(w.clock.now + 1, {}))
        self.assertIsNone(self.publisher.cache)


if __name__ == "__main__":
    unittest.main()
