"""devtools/buildorder_model.py: the Terraform Index curve against values read from saves."""
import sys
import unittest
from pathlib import Path

DEVTOOLS = Path(__file__).resolve().parent.parent / "devtools"
if str(DEVTOOLS) not in sys.path:
    sys.path.insert(0, str(DEVTOOLS))

import buildorder_model as bm  # noqa: E402


class TerraformIndexTests(unittest.TestCase):
    def test_matches_save_snapshot(self):
        # Early save: O2 6.94 ppt only, game reported 31,440 TP.
        self.assertAlmostEqual(bm.terraform_index(o2=6.9364), 31_440, delta=31_440 * 0.001)

    def test_phase_one_caps(self):
        full = bm.ATMO_PHASE_TP[0]
        self.assertAlmostEqual(bm.terraform_index(o2=10, pressure=0.3, heat=11), 3 * full)
        self.assertAlmostEqual(bm.pillar_tp("pressure", 0.15), full / 2)

    def test_phase_two_is_linear_from_its_start(self):
        self.assertAlmostEqual(bm.pillar_tp("heat", 11 + 129 / 2), bm.ATMO_PHASE_TP[0] + bm.ATMO_PHASE_TP[1] / 2)

    def test_marginal_drops_at_cap(self):
        self.assertGreater(bm.marginal_tp("pressure", 0.29), 10 * bm.marginal_tp("pressure", 0.31))

    def test_capped(self):
        self.assertEqual(bm.terraform_index(other=2_000_000), bm.TP_CAP)


if __name__ == "__main__":
    unittest.main()
