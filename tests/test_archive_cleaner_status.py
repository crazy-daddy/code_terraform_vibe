import ast
import glob
import importlib
import os
import unittest

import harness
from archive import archive, STATUS_STALE_TICKS
from archive_cleaner import ArchiveCleaner, STATUS_TICK_KEYS

LIB = os.path.join(os.path.dirname(__file__), "..", "scripts", "4_controlpanel", "lib")


class _Log:
    def __init__(self):
        self.lines = []

    def level(self, level):
        log = self

        class _Level:
            def print(self, msg):
                log.lines.append((level, msg))
        return _Level()

    def debug(self, msg):
        self.lines.append(("debug", msg))


class PublishStatusTests(harness.StubTestCase):
    def test_sets_tick_and_prunes_stale_others(self):
        data = self.world.notebook.data
        data["x.status"] = {"old": {"tick": 0}, "fresh": {"tick": STATUS_STALE_TICKS}, "junk": 5}
        log = _Log()
        self.assertTrue(archive.publish_status("x.status", "me", {"a": 1}, STATUS_STALE_TICKS, log))
        self.assertEqual(data["x.status"], {"fresh": {"tick": STATUS_STALE_TICKS}, "me": {"a": 1, "tick": STATUS_STALE_TICKS}})
        self.assertEqual(sorted(m for lvl, m in log.lines if lvl == "debug"),
                         ["[me] pruned stale x.status['junk'].", "[me] pruned stale x.status['old']."])

    def test_no_prune_keeps_quiet_entries(self):
        data = self.world.notebook.data
        data["x.status"] = {"old": {"name": "old"}}
        archive.publish_status("x.status", "me", {}, 10 * STATUS_STALE_TICKS, _Log(), stale_ticks=None)
        self.assertIn("old", data["x.status"])

    def test_rejected_write_warns(self):
        log = _Log()
        original = archive.transaction
        archive.transaction = lambda *args: False  # type: ignore[method-assign]
        self.addCleanup(setattr, archive, "transaction", original)
        self.assertFalse(archive.publish_status("x.status", "me", {}, 1, log))
        self.assertEqual(log.lines, [("warn", "[me] x.status write rejected; status not published this cycle.")])


class CleanStatusTicksTests(harness.StubTestCase):
    def test_drops_unrefreshed_entries(self):
        data = self.world.notebook.data
        now = 2 * STATUS_STALE_TICKS
        data["seed_maker.status"] = {"gone": {"tick": now - STATUS_STALE_TICKS}, "live": {"tick": now - 1}, "legacy": {"state": "x"}}
        ArchiveCleaner(dry_run=False, verbose=False).clean_status_ticks(now)
        self.assertEqual(list(data["seed_maker.status"]), ["live"])

    def test_dry_run_and_no_clock_keep_entries(self):
        data = self.world.notebook.data
        data["plant.status"] = {"gone": {"tick": 0}}
        ArchiveCleaner(dry_run=True, verbose=False).clean_status_ticks(2 * STATUS_STALE_TICKS)
        ArchiveCleaner(dry_run=False, verbose=False).clean_status_ticks(0)
        self.assertIn("gone", data["plant.status"])


class PublishStatusKeysListedTests(unittest.TestCase):
    """Every key written with the tick prune is also aged out by the cleaner."""

    def test_every_pruned_key_is_in_cleaner(self):
        found = {}
        for path in glob.glob(os.path.join(LIB, "*.py")):
            module_name = os.path.splitext(os.path.basename(path))[0]
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "publish_status"
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "archive"):
                    continue
                if any(k.arg == "stale_ticks" for k in node.keywords) or not node.args:
                    continue
                arg = node.args[0]
                module = importlib.import_module(module_name)
                if isinstance(arg, ast.Name):
                    key = getattr(module, arg.id)
                elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
                    key = getattr(getattr(module, arg.value.id), arg.attr)
                else:
                    self.fail(f"{module_name}: publish_status key is not a constant: {ast.dump(arg)}")
                found[key] = module_name
        self.assertTrue(found)
        missing = {k: m for k, m in found.items() if k not in STATUS_TICK_KEYS}
        self.assertEqual(missing, {})



class CleanClaimsTests(harness.StubTestCase):
    def test_mine_claim_on_surveyed_site_kept_survey_claim_purged(self):
        data = self.world.notebook.data
        data["survey.claims"] = {
            "site_9@rover_1": {"vehicle": "rover_1", "type": "mine", "coords": (5, 5), "tick": 100},
            "site_9": {"vehicle": "rover_2", "type": "unknown", "coords": (5, 5), "tick": 100},
        }
        ArchiveCleaner(dry_run=False, verbose=False).clean_claims(200, set(), {(5, 5)}, {"site_9"}, {(5, 5)})
        self.assertEqual(list(data["survey.claims"]), ["site_9@rover_1"])

if __name__ == "__main__":
    unittest.main()
