"""Stub tests for logistics_requests.claim_pickups(): legs trimmed by reservations made since `seen`."""

import unittest

from harness import StubTestCase
from harness import logistics_requests as lr

DEST = "outpost_x"
NOW = 100_000


class ClaimPickupsTests(StubTestCase):
    def reserve(self, vehicle, dest, item_id, units, source, tick=NOW):
        lr.reserve_pickup(vehicle, dest, item_id, units, tick, source_id=source)

    def test_trims_by_source_and_dest_growth_since_seen(self):
        # Held before `seen`: never cut.
        self.reserve("drone_1", DEST, "iron", 2, "a")
        self.reserve("drone_1", "outpost_y", "iron", 5, "b")
        seen = lr.pickups_snapshot()
        # Since `seen`: same dest (from c), same source to another dest, and noise the claim ignores.
        self.reserve("drone_2", DEST, "iron", 3, "c")
        self.reserve("drone_3", "outpost_y", "iron", 4, "b")
        self.reserve("drone_3", "outpost_y", "copper", 9, "q")
        self.reserve("drone_4", DEST, "copper", 6, "z", tick=NOW - lr.PICKUP_STALE_TICKS)  # stale
        self.reserve("drone_9", DEST, "copper", 7, "a")  # the claimer's own entry
        legs = [("a", "iron", 4), ("b", "iron", 6), ("a", "copper", 5)]
        granted = lr.claim_pickups("drone_9", DEST, legs, seen, NOW)
        # iron: dest cut 3 (drone_2), source b cut 4 (drone_3). Leg a gives up 3, which
        # clears the dest cut; leg b then loses only its source cut 4. copper: no cut.
        self.assertEqual(granted, [("a", "iron", 1), ("b", "iron", 2), ("a", "copper", 5)])
        pickups = lr.pickups_snapshot()
        self.assertEqual(pickups[lr.pickup_key("drone_9", DEST, "iron", "a")]["units"], 1)
        self.assertEqual(pickups[lr.pickup_key("drone_9", DEST, "iron", "b")]["units"], 2)
        self.assertEqual(pickups[lr.pickup_key("drone_9", DEST, "copper", "a")]["units"], 5)

    def test_zero_grant_drops_the_leg_entry(self):
        seen = lr.pickups_snapshot()
        self.reserve("drone_9", DEST, "iron", 3, "a")  # own leftover for this leg
        self.reserve("drone_2", DEST, "iron", 8, "c")
        granted = lr.claim_pickups("drone_9", DEST, [("a", "iron", 5)], seen, NOW)
        self.assertEqual(granted, [("a", "iron", 0)])
        self.assertNotIn(lr.pickup_key("drone_9", DEST, "iron", "a"), lr.pickups_snapshot())

    def test_duplicate_legs_share_one_cut(self):
        seen = lr.pickups_snapshot()
        self.reserve("drone_2", "outpost_y", "iron", 3, "a")
        legs = [("a", "iron", 2), ("a", "iron", 4)]
        # Source a cut 3: the first leg gives up 2, the second only the remaining 1.
        self.assertEqual(lr.claim_pickups("drone_9", DEST, legs, seen, NOW), [("a", "iron", 0), ("a", "iron", 3)])

    def test_reservation_released_since_seen_does_not_cut(self):
        self.reserve("drone_2", DEST, "iron", 4, "a")
        seen = lr.pickups_snapshot()
        lr.release_pickups("drone_2")
        self.reserve("drone_3", DEST, "iron", 2, "b")
        self.assertEqual(lr.claim_pickups("drone_9", DEST, [("a", "iron", 5)], seen, NOW), [("a", "iron", 5)])


if __name__ == "__main__":
    unittest.main()
