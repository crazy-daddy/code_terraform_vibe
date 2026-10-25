"""Stub tests for logistics_requests.publish_requests(), the shared request publisher."""

import unittest
from unittest import mock

import harness
import logistics_requests
from harness import StubTestCase

R = harness.request

OUTPOST = "outpost_1"


class PublishRequestsTests(StubTestCase):
    def publish(self, requester, wants, tick=0, **kwargs):
        return logistics_requests.publish_requests(OUTPOST, requester, wants, tick, **kwargs)

    def entries(self, tick=0):
        return logistics_requests.active_requests(tick).get(OUTPOST, {})

    def test_first_publish_writes(self):
        self.assertTrue(self.publish("a", {"iron": (R(10), 2)}))
        self.assertEqual(self.entries()["iron"]["by"], "a")

    def test_unchanged_wants_not_rewritten(self):
        self.publish("a", {"iron": (R(10, 4), 2)})
        self.assertFalse(self.publish("a", {"iron": (R(10, 4), 7)}, tick=100))
        self.assertEqual(self.entries(100)["iron"]["have"], 2)

    def test_changed_target_min_or_buy_rewrites(self):
        self.publish("a", {"iron": (R(10), 2)})
        self.assertTrue(self.publish("a", {"iron": (R(12), 2)}, tick=1))
        self.assertTrue(self.publish("a", {"iron": (R(12, 5), 2)}, tick=2))
        self.assertTrue(self.publish("a", {"iron": (R(12, 5), 2)}, tick=3, buyable=True))
        self.assertTrue(self.entries(3)["iron"]["buy"])

    def test_old_entries_republished(self):
        self.publish("a", {"iron": (R(10), 2)})
        self.assertTrue(self.publish("a", {"iron": (R(10), 2)}, tick=logistics_requests.REPUBLISH_TICKS))

    def test_empty_wants_clear_once(self):
        self.publish("a", {"iron": (R(10), 2)})
        self.assertTrue(self.publish("a", {}, tick=1))
        self.assertNotIn("iron", self.entries(1))
        self.assertFalse(self.publish("a", {}, tick=2))

    def test_foreign_owner_skipped(self):
        self.publish("a", {"iron": (R(10), 2)})
        self.publish("b", {"iron": (R(50), 2), "glass": (R(5), 0)}, tick=1)
        entries = self.entries(1)
        self.assertEqual(entries["iron"]["by"], "a")
        self.assertEqual(entries["iron"]["levels"], R(10))
        self.assertEqual(entries["glass"]["by"], "b")

    def test_skip_foreign_off_takes_item(self):
        self.publish("a", {"iron": (R(10), 2)})
        self.publish("b", {"iron": (R(50), 2)}, tick=1, skip_foreign=False)
        self.assertEqual(self.entries(1)["iron"]["by"], "b")

    def test_have_of_read_on_write_only(self):
        reads = []

        def have_of(item_id):
            reads.append(item_id)
            return 3

        self.publish("a", {"iron": (R(10), 0)}, have_of=have_of)
        self.assertEqual(self.entries()["iron"]["have"], 3)
        self.publish("a", {"iron": (R(10), 0)}, tick=1, have_of=have_of)
        self.assertEqual(reads, ["iron"])


class ClearRequestsTests(StubTestCase):
    def test_clear_drops_own_entries_only_where_asked(self):
        logistics_requests.set_requests(OUTPOST, "a", {"iron": (R(10), 0)}, 0)
        logistics_requests.set_requests(OUTPOST, "b", {"glass": (R(10), 0)}, 0)
        logistics_requests.set_requests("outpost_2", "a", {"iron": (R(10), 0)}, 0)
        logistics_requests.clear_requests("a", OUTPOST)
        requests = logistics_requests.active_requests(0)
        self.assertEqual(list(requests[OUTPOST]), ["glass"])
        self.assertEqual(list(requests["outpost_2"]), ["iron"])
        logistics_requests.clear_requests("a")
        self.assertNotIn("outpost_2", logistics_requests.active_requests(0))

    def test_set_prunes_stale_entries_of_any_requester(self):
        logistics_requests.set_requests("outpost_2", "b", {"glass": (R(10), 0)}, 0)
        logistics_requests.set_requests(OUTPOST, "a", {"iron": (R(10), 0)}, logistics_requests.REQUEST_STALE_TICKS + 1)
        self.assertNotIn("outpost_2", logistics_requests.archive.get(logistics_requests.REQUESTS_KEY))


STALE = logistics_requests.REQUEST_STALE_TICKS


def entry(by, tick):
    return {"levels": R(10), "have": 0, "by": by, "tick": tick}


class SetRequestsPruneTests(StubTestCase):
    """set_requests() prunes its own bucket fully and one other outpost's stale entries per call."""

    def setUp(self):
        super().setUp()
        logistics_requests._SWEEP["after"] = None

    def stored(self):
        return logistics_requests.archive.get(logistics_requests.REQUESTS_KEY)

    def test_own_bucket_replaced_and_pruned(self):
        logistics_requests.archive.set(
            logistics_requests.REQUESTS_KEY,
            {OUTPOST: {"iron": entry("a", STALE), "glass": entry("b", 0), "sand": entry("c", STALE)}},
        )
        logistics_requests.set_requests(OUTPOST, "a", {"copper": (R(10), 0)}, STALE + 1)
        bucket = self.stored()[OUTPOST]
        self.assertEqual(sorted(bucket), ["copper", "sand"])
        self.assertEqual(bucket["sand"]["by"], "c")

    def test_other_outposts_swept_one_per_call(self):
        others = ["outpost_2", "outpost_3", "outpost_4"]
        logistics_requests.archive.set(
            logistics_requests.REQUESTS_KEY,
            {o: {"stale": entry("b", 0), "fresh": entry("b", STALE)} for o in others},
        )
        for done in range(1, len(others) + 1):
            logistics_requests.set_requests(OUTPOST, "a", {"iron": (R(10), 0)}, STALE + done)
            stored = self.stored()
            for i, o in enumerate(others):
                self.assertEqual("stale" in stored[o], i >= done, (done, o))
                self.assertIn("fresh", stored[o])
        logistics_requests.set_requests(OUTPOST, "a", {"iron": (R(10), 0)}, STALE + len(others) + 1)
        self.assertEqual({o: sorted(self.stored()[o]) for o in others}, {o: ["fresh"] for o in others})

    def test_stale_only_bucket_dropped(self):
        logistics_requests.archive.set(logistics_requests.REQUESTS_KEY, {"outpost_2": {"stale": entry("b", 0)}})
        logistics_requests.set_requests(OUTPOST, "a", {"iron": (R(10), 0)}, STALE + 1)
        self.assertNotIn("outpost_2", self.stored())

    def test_sweep_wraps_to_first_outpost(self):
        others = ["outpost_2", "outpost_3"]
        logistics_requests.archive.set(
            logistics_requests.REQUESTS_KEY, {o: {"fresh": entry("b", STALE)} for o in others}
        )
        for tick in (STALE + 1, STALE + 2):
            logistics_requests.set_requests(OUTPOST, "a", {"iron": (R(10), 0)}, tick)
        self.assertEqual(logistics_requests._SWEEP["after"], "outpost_3")
        stored = self.stored()
        stored["outpost_2"]["stale"] = entry("b", 0)
        logistics_requests.archive.set(logistics_requests.REQUESTS_KEY, stored)
        self.assertIn("stale", self.stored()["outpost_2"])
        logistics_requests.set_requests(OUTPOST, "a", {"iron": (R(10), 0)}, STALE + 3)
        self.assertEqual(sorted(self.stored()["outpost_2"]), ["fresh"])

    def test_sweep_cursor_on_gone_id_picks_next_greater(self):
        others = ["outpost_2", "outpost_4"]
        logistics_requests.archive.set(
            logistics_requests.REQUESTS_KEY, {o: {"stale": entry("b", 0), "fresh": entry("b", STALE)} for o in others}
        )
        logistics_requests._SWEEP["after"] = "outpost_3"
        logistics_requests.set_requests(OUTPOST, "a", {"iron": (R(10), 0)}, STALE + 1)
        stored = self.stored()
        self.assertIn("stale", stored["outpost_2"])
        self.assertNotIn("stale", stored["outpost_4"])

    def test_empty_wants_withdraw_own_keep_foreign(self):
        logistics_requests.archive.set(
            logistics_requests.REQUESTS_KEY, {OUTPOST: {"iron": entry("a", STALE), "glass": entry("b", STALE)}}
        )
        logistics_requests.set_requests(OUTPOST, "a", {}, STALE + 1)
        self.assertEqual(sorted(self.stored()[OUTPOST]), ["glass"])

    def test_wake_only_for_items_not_held(self):
        logistics_requests.archive.set(logistics_requests.REQUESTS_KEY, {OUTPOST: {"iron": entry("a", STALE)}})
        wants = {"iron": (R(10), 0), "sand": ([], 0), "glass": (R(5), 0)}
        with mock.patch.object(logistics_requests, "wake_role") as wake:
            logistics_requests.set_requests(OUTPOST, "a", wants, STALE + 1)
        wake.assert_called_once_with("hauler", f"new haul request: {OUTPOST} glass")
        self.assertEqual(sorted(self.stored()[OUTPOST]), ["glass", "iron"])
        with mock.patch.object(logistics_requests, "wake_role") as wake:
            logistics_requests.set_requests(OUTPOST, "a", wants, STALE + 2)
        wake.assert_not_called()


if __name__ == "__main__":
    unittest.main()
