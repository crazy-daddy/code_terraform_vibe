"""devtools/swap_seed.py: patches a young save and its history snapshots, backs them up, refuses progress."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools"))
import swap_seed  # noqa: E402


def young_state(seed=1, ticks=10):
    return {"state": {"seed": seed, "tickCount": ticks, "planet": {"plants": {"recipeMap": {}}},
                      "harvesting": {"grid": {}, "scannedSectors": [], "collectedCount": 0, "heldItem": None}}}


class SwapSeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.save = self.dir / "save_abc_def.json"
        self.history = self.dir / "save_abc_def.h0.json"
        for path in (self.save, self.history):
            path.write_text(json.dumps(young_state()), encoding="utf-8")
        self.backup_root = swap_seed.BACKUP_ROOT
        swap_seed.BACKUP_ROOT = self.dir / "backups"
        # The real world_sources() runs node on the private simworker.
        self.world_sources = swap_seed.world_sources
        swap_seed.world_sources = lambda seed: {"sources": [{"id": "vent_1", "seed": seed}], "geologicalAnomalies": [{"id": "geological_anomaly_1"}]}

    def tearDown(self):
        swap_seed.BACKUP_ROOT = self.backup_root
        swap_seed.world_sources = self.world_sources
        self.tmp.cleanup()

    def state(self, path):
        return json.loads(path.read_text(encoding="utf-8"))["state"]

    def test_dry_run_writes_nothing(self):
        self.assertIsNone(swap_seed.swap(self.save, 12412, out=lambda line: None))
        self.assertEqual(self.state(self.save)["seed"], 1)

    def test_apply_patches_save_and_history_with_backups(self):
        backup = swap_seed.swap(self.save, 12412, apply=True, out=lambda line: None)
        for path in (self.save, self.history):
            state = self.state(path)
            self.assertEqual(state["seed"], 12412)
            self.assertEqual(state["planet"]["plants"]["recipeMap"], swap_seed.seed_quality.recipes(12412))
            self.assertEqual(state["harvesting"]["grid"], swap_seed.field(12412))
            self.assertEqual(state["planet"]["sources"], [{"id": "vent_1", "seed": 12412}])
            self.assertEqual(state["planet"]["geologicalAnomalies"], [{"id": "geological_anomaly_1"}])
        assert backup is not None
        self.assertEqual(sorted(p.name for p in backup.iterdir()), [self.history.name, self.save.name])
        self.assertEqual(json.loads((backup / self.save.name).read_text(encoding="utf-8"))["state"]["seed"], 1)

    def test_without_generators_sources_are_emptied_with_a_warning(self):
        swap_seed.world_sources = lambda seed: None
        lines = []
        swap_seed.swap(self.save, 12412, apply=True, out=lines.append)
        planet = self.state(self.save)["planet"]
        self.assertEqual((planet["sources"], planet["geologicalAnomalies"]), ([], []))
        self.assertTrue(any(line.startswith("warning:") for line in lines))

    def test_progress_refused_unless_forced(self):
        self.history.write_text(json.dumps(young_state(ticks=swap_seed.PROGRESS_TICKS + 1)), encoding="utf-8")
        with self.assertRaises(ValueError):
            swap_seed.swap(self.save, 12412, apply=True, out=lambda line: None)
        self.assertEqual(self.state(self.save)["seed"], 1)
        swap_seed.swap(self.save, 12412, apply=True, force=True, out=lambda line: None)
        self.assertEqual(self.state(self.history)["seed"], 12412)

    def test_field_shape(self):
        grid = swap_seed.field(1)
        self.assertEqual(len(grid), swap_seed.FIELD_ROWS * swap_seed.FIELD_COLS)
        self.assertIsNone(grid["E13"])


if __name__ == "__main__":
    unittest.main()
