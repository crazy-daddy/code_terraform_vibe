"""Stub tests for the electric hauler's yield to idle helis: drone_haul_plan.free_helis(),
heli_should_fly(), yield_to_helis() and trip_overhead_m()."""

import unittest

import drone_haul_plan
from archive import archive
from harness import StubTestCase
from tree_console import TreeConsole


class _Electric:
    name = "drone_e"
    engine = "electric"

    def __init__(self):
        self.log = TreeConsole(module="drone")
        self.haul_memory = drone_haul_plan.HaulMemory()


def _candidate(dest_id, first, meters, blockers=0):
    return {
        "dest": {"outpost_id": dest_id},
        "route": [({"id": "src", "coords": first}, {})],
        "meters": meters,
        "blockers": blockers,
    }


class HeliYieldTests(StubTestCase):
    def test_free_helis_ignores_stale_entries(self):
        archive.set(
            drone_haul_plan.HELI_FREE_KEY,
            {
                "h1": {"tick": 1000, "at": [5, 6]},
                "h2": {"tick": 1000 - drone_haul_plan.HELI_FREE_STALE_TICKS - 1, "at": [0, 0]},
            },
        )
        self.assertEqual(drone_haul_plan.free_helis(1000), [(5.0, 6.0)])

    def test_long_job_yields_to_a_near_heli(self):
        job = _candidate("far", (3000.0, 0.0), 6000.0)
        self.assertTrue(drone_haul_plan.heli_should_fly(job, (0.0, 0.0), [(0.0, 0.0)]))

    def test_short_job_without_blockers_stays(self):
        job = _candidate("near", (100.0, 0.0), drone_haul_plan.HELI_YIELD_MIN_M - 1)
        self.assertFalse(drone_haul_plan.heli_should_fly(job, (0.0, 0.0), [(0.0, 0.0)]))

    def test_blocker_job_yields_even_when_short(self):
        job = _candidate("near", (100.0, 0.0), 400.0, blockers=5)
        self.assertTrue(drone_haul_plan.heli_should_fly(job, (0.0, 0.0), [(0.0, 0.0)]))

    def test_heli_far_away_does_not_take_it(self):
        job = _candidate("far", (3000.0, 0.0), 6000.0)
        self.assertFalse(drone_haul_plan.heli_should_fly(job, (0.0, 0.0), [(-20000.0, 0.0)]))

    def test_yield_expires_after_max_ticks(self):
        drone = _Electric()
        ranked = [_candidate("far", (3000.0, 0.0), 6000.0), _candidate("near", (100.0, 0.0), 300.0)]
        helis = [(0.0, 0.0)]
        kept = drone_haul_plan.yield_to_helis(drone, ranked, (0.0, 0.0), helis, 0)
        self.assertEqual([c["dest"]["outpost_id"] for c in kept], ["near"])
        kept = drone_haul_plan.yield_to_helis(drone, ranked, (0.0, 0.0), helis, drone_haul_plan.HELI_YIELD_MAX_TICKS)
        self.assertEqual([c["dest"]["outpost_id"] for c in kept], ["far", "near"])

    def test_heli_overhead_scales_with_speed(self):
        self.assertEqual(drone_haul_plan.trip_overhead_m("electric"), drone_haul_plan.HAUL_TRIP_OVERHEAD_M)
        self.assertEqual(drone_haul_plan.trip_overhead_m("heli"), 3 * drone_haul_plan.HAUL_TRIP_OVERHEAD_M)


if __name__ == "__main__":
    unittest.main()
