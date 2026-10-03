"""Stub tests for logistics_requests.publish_requests(), the shared request publisher."""
import unittest

from harness import StubTestCase, logistics_requests

OUTPOST = "outpost_1"


class PublishRequestsTests(StubTestCase):
    def publish(self, requester, wants, tick=0, **kwargs):
        return logistics_requests.publish_requests(OUTPOST, requester, wants, tick, **kwargs)

    def entries(self, tick=0):
        return logistics_requests.active_requests(tick).get(OUTPOST, {})

    def test_first_publish_writes(self):
        self.assertTrue(self.publish("a", {"iron": (10, 2)}))
        self.assertEqual(self.entries()["iron"]["by"], "a")

    def test_unchanged_wants_not_rewritten(self):
        self.publish("a", {"iron": (10, 2, 4)})
        self.assertFalse(self.publish("a", {"iron": (10, 7, 4)}, tick=100))
        self.assertEqual(self.entries(100)["iron"]["have"], 2)

    def test_changed_target_min_or_buy_rewrites(self):
        self.publish("a", {"iron": (10, 2)})
        self.assertTrue(self.publish("a", {"iron": (12, 2)}, tick=1))
        self.assertTrue(self.publish("a", {"iron": (12, 2, 5)}, tick=2))
        self.assertTrue(self.publish("a", {"iron": (12, 2, 5)}, tick=3, buyable=True))
        self.assertTrue(self.entries(3)["iron"]["buy"])

    def test_old_entries_republished(self):
        self.publish("a", {"iron": (10, 2)})
        self.assertTrue(self.publish("a", {"iron": (10, 2)}, tick=logistics_requests.REPUBLISH_TICKS))

    def test_empty_wants_clear_once(self):
        self.publish("a", {"iron": (10, 2)})
        self.assertTrue(self.publish("a", {}, tick=1))
        self.assertNotIn("iron", self.entries(1))
        self.assertFalse(self.publish("a", {}, tick=2))

    def test_foreign_owner_skipped(self):
        self.publish("a", {"iron": (10, 2)})
        self.publish("b", {"iron": (50, 2), "glass": (5, 0)}, tick=1)
        entries = self.entries(1)
        self.assertEqual(entries["iron"]["by"], "a")
        self.assertEqual(entries["iron"]["target"], 10)
        self.assertEqual(entries["glass"]["by"], "b")

    def test_skip_foreign_off_takes_item(self):
        self.publish("a", {"iron": (10, 2)})
        self.publish("b", {"iron": (50, 2)}, tick=1, skip_foreign=False)
        self.assertEqual(self.entries(1)["iron"]["by"], "b")

    def test_have_of_read_on_write_only(self):
        reads = []

        def have_of(item_id):
            reads.append(item_id)
            return 3

        self.publish("a", {"iron": (10, 0)}, have_of=have_of)
        self.assertEqual(self.entries()["iron"]["have"], 3)
        self.publish("a", {"iron": (10, 0)}, tick=1, have_of=have_of)
        self.assertEqual(reads, ["iron"])


if __name__ == "__main__":
    unittest.main()
