"""pioneer_construction claim race: a job a peer claimed between the scan and
the claim passes to the next one, and losing every reachable matching job
rescans instead of falling through to restocking at home."""
import unittest

import harness
import pioneer_construction
from tree_console import TreeConsole


def _row(job_id, coords=(10, 0)):
    return {"id": job_id, "coords": coords, "kind": "power_line", "job": job_id}


class _Builder(pioneer_construction.PioneerConstructionMixin):
    name = "pioneer_4"

    def __init__(self, peer_claims=(), reachable=None):
        self.log = TreeConsole()
        self.failed_jobs = set()
        self.material_waits = set()
        self.peer_claims = set(peer_claims)
        self.reachable = reachable
        self.built = []
        self.charged = False

    def _job_trip_budget(self, row, at_floor=False):
        ok = self.reachable is None or row["id"] in self.reachable
        return {"is_achievable": ok, "total_required_wh": 10.0}

    def _claim_and_build(self, row, verb):
        if row["id"] in self.peer_claims:
            return None
        self.built.append(row["id"])
        return 0

    def _charge_for_matching_jobs(self, matching, position):
        self.charged = True
        return 0


def _matching(*rows):
    return [(1, 0.0, 0, row) for row in rows]


class BuildMatchingJobTests(harness.StubTestCase):
    def test_lost_claim_tries_next_job(self):
        builder = _Builder(peer_claims={"bp_116"})
        delay = builder._build_matching_job(_matching(_row("bp_116"), _row("bp_117")), (0, 0))
        self.assertEqual(delay, 0)
        self.assertEqual(builder.built, ["bp_117"])

    def test_every_reachable_job_lost_rescans(self):
        builder = _Builder(peer_claims={"bp_116", "bp_117"})
        delay = builder._build_matching_job(_matching(_row("bp_116"), _row("bp_117")), (0, 0))
        self.assertEqual(delay, 2.0)
        self.assertEqual(builder.built, [])
        self.assertFalse(builder.charged)

    def test_none_reachable_charges(self):
        builder = _Builder(reachable=set())
        builder._build_matching_job(_matching(_row("bp_116")), (0, 0))
        self.assertTrue(builder.charged)


class ResumePausedJobTests(harness.StubTestCase):
    def test_lost_claim_tries_next_job(self):
        builder = _Builder(peer_claims={"bp_1"})
        self.assertEqual(builder._resume_paused_job([_row("bp_1"), _row("bp_2")]), 0)
        self.assertEqual(builder.built, ["bp_2"])

    def test_every_job_lost_falls_through(self):
        builder = _Builder(peer_claims={"bp_1"})
        self.assertIsNone(builder._resume_paused_job([_row("bp_1")]))


if __name__ == "__main__":
    unittest.main()
