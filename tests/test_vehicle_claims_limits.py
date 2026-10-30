"""Vehicle target claims (lib/vehicle_claims.py) at the CLAIM_STALE_TICKS edge.

Two real VehicleControllers race for one survey site on the stub clock. Bugs
caught: a claim that expires one tick early (two vehicles drive to the same
site), never expires (a crashed vehicle locks the site forever), a heartbeat
that does not extend it, or a claim made before the clock is readable (tick 0)
that a peer can take at once.
"""

import unittest

from harness import StubTestCase
from vehicle_host import make_vehicle

SITE = "poi_1"
SITE_INFO = {"type": "survey", "coords": (50.0, 50.0), "name": SITE}
START = 1000


class ClaimStaleEdgeTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.owner, _ = make_vehicle(self.world, pioneer_id="pioneer_1")
        self.peer, _ = make_vehicle(self.world, pioneer_id="pioneer_2")
        self.stale = self.owner.CLAIM_STALE_TICKS

    def at(self, tick):
        self.world.clock.now = tick

    def claim(self, vehicle, tick):
        self.at(tick)
        return vehicle.claim_target(SITE, SITE_INFO)

    def holder(self):
        return (self.owner.get_claims().get(SITE) or {}).get("vehicle")

    def test_peer_locked_out_until_the_last_fresh_tick(self):
        self.assertTrue(self.claim(self.owner, START))
        self.assertFalse(self.claim(self.peer, START + self.stale - 1))
        self.assertEqual(self.holder(), "pioneer_1")

    def test_peer_takes_over_at_exactly_stale(self):
        self.assertTrue(self.claim(self.owner, START))
        self.assertTrue(self.claim(self.peer, START + self.stale))
        self.assertEqual(self.holder(), "pioneer_2")

    def test_owner_reclaims_its_own_claim_at_any_age(self):
        self.assertTrue(self.claim(self.owner, START))
        self.assertTrue(self.claim(self.owner, START + self.stale - 1))
        self.assertFalse(self.claim(self.peer, START + 2 * self.stale - 2))

    def test_heartbeat_extends_the_claim(self):
        self.claim(self.owner, START)
        self.at(START + self.stale - 1)
        self.owner.refresh_claim(SITE)
        self.assertFalse(self.claim(self.peer, START + 2 * self.stale - 2))
        self.assertTrue(self.claim(self.peer, START + 2 * self.stale - 1))

    def test_peer_heartbeat_does_not_extend_anothers_claim(self):
        self.claim(self.owner, START)
        self.at(START + self.stale - 1)
        self.peer.refresh_claim(SITE)
        self.assertTrue(self.claim(self.peer, START + self.stale))

    def test_cleanup_keeps_fresh_and_drops_stale_at_the_edge(self):
        self.claim(self.owner, START)
        self.at(START + self.stale - 1)
        self.peer.cleanup_stale_claims()
        self.assertEqual(self.holder(), "pioneer_1")
        self.at(START + self.stale)
        self.peer.cleanup_stale_claims()
        self.assertIsNone(self.holder())

    def test_claim_at_tick_zero_holds_against_a_peer(self):
        self.assertTrue(self.claim(self.owner, 0))
        self.assertFalse(self.claim(self.peer, 0))
        self.assertEqual(self.holder(), "pioneer_1")

    def test_claim_at_tick_zero_expires_once_the_clock_runs(self):
        self.claim(self.owner, 0)
        self.assertFalse(self.claim(self.peer, self.stale - 1))
        self.assertTrue(self.claim(self.peer, self.stale))


if __name__ == "__main__":
    unittest.main()
