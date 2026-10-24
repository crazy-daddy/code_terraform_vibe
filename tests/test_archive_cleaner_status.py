import ast
import glob
import importlib
import os
import unittest

import harness
from archive import STATUS_STALE_TICKS, archive
from archive_cleaner import STATUS_TICK_KEYS, ArchiveCleaner
from outpost_mining import MINING_REACH_KEY

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
        self.assertEqual(
            data["x.status"], {"fresh": {"tick": STATUS_STALE_TICKS}, "me": {"a": 1, "tick": STATUS_STALE_TICKS}}
        )
        self.assertEqual(
            sorted(m for lvl, m in log.lines if lvl == "debug"),
            ["[me] pruned stale x.status['junk'].", "[me] pruned stale x.status['old']."],
        )

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
        data["seed_maker.status"] = {
            "gone": {"tick": now - STATUS_STALE_TICKS},
            "live": {"tick": now - 1},
            "legacy": {"state": "x"},
        }
        ArchiveCleaner(dry_run=False, verbose=False).clean_status_ticks(now)
        self.assertEqual(list(data["seed_maker.status"]), ["live"])

    def test_entry_refreshed_before_the_write_survives(self):
        # _prune_dict_key(still_stale=...) re-checks inside the transaction.
        data = self.world.notebook.data
        now = 2 * STATUS_STALE_TICKS
        data["seed_maker.status"] = {"gone": {"tick": 0}, "back": {"tick": 0}}
        original = archive.transaction

        def refresh_then_write(key, default, updater):
            data[key]["back"] = {"tick": now}
            return original(key, default, updater)

        archive.transaction = refresh_then_write  # type: ignore[method-assign]
        self.addCleanup(setattr, archive, "transaction", original)
        ArchiveCleaner(dry_run=False, verbose=False).clean_status_ticks(now)
        self.assertEqual(list(data["seed_maker.status"]), ["back"])

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
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "publish_status"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "archive"
                ):
                    continue
                # stale_ticks=None keeps others (pruned elsewhere); any other value still needs the cleaner.
                if (
                    any(
                        k.arg == "stale_ticks" and isinstance(k.value, ast.Constant) and k.value.value is None
                        for k in node.keywords
                    )
                    or not node.args
                ):
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


class DictKeyHelperTests(harness.StubTestCase):
    """_reset_if_not_dict() and _prune_dict_key(), via clean_mining_reach()."""

    def test_non_dict_key_is_deleted(self):
        data = self.world.notebook.data
        data[MINING_REACH_KEY] = ["junk"]
        ArchiveCleaner(dry_run=False, verbose=False).clean_mining_reach({"rover_1"})
        self.assertNotIn(MINING_REACH_KEY, data)

    def test_stale_entries_pruned_live_only(self):
        data = self.world.notebook.data
        data[MINING_REACH_KEY] = {"rover_1": {"r": 1}, "rover_2": {"r": 1}, "rover_3": {}}
        ArchiveCleaner(dry_run=True, verbose=False).clean_mining_reach({"rover_1", "rover_3"})
        self.assertEqual(len(data[MINING_REACH_KEY]), 3)
        ArchiveCleaner(dry_run=False, verbose=False).clean_mining_reach({"rover_1", "rover_3"})
        self.assertEqual(list(data[MINING_REACH_KEY]), ["rover_1"])


class PruneFleetDictTests(harness.StubTestCase):
    """_prune_fleet_dict(): stale vehicles and malformed payloads of one fleet-keyed dict, with the count."""

    def test_prunes_stale_and_malformed_and_counts(self):
        data = self.world.notebook.data
        data[MINING_REACH_KEY] = {"rover_1": {"r": 1}, "rover_2": {"r": 1}, "rover_3": {}, "rover_4": "junk"}
        cleaner = ArchiveCleaner(dry_run=False, verbose=False)
        self.assertEqual(
            cleaner._prune_fleet_dict(MINING_REACH_KEY, {"rover_1", "rover_3", "rover_4"}, "DELETE MINING REACH"), 3
        )
        self.assertEqual(list(data[MINING_REACH_KEY]), ["rover_1"])

    def test_empty_fleet_keeps_well_formed_and_junk_key_counts_one(self):
        data = self.world.notebook.data
        data[MINING_REACH_KEY] = {"rover_1": {"r": 1}}
        cleaner = ArchiveCleaner(dry_run=False, verbose=False)
        self.assertEqual(cleaner._prune_fleet_dict(MINING_REACH_KEY, set(), "DELETE MINING REACH"), 0)
        data[MINING_REACH_KEY] = ["junk"]
        self.assertEqual(cleaner._prune_fleet_dict(MINING_REACH_KEY, set(), "DELETE MINING REACH"), 1)


class KeyCoordsTests(unittest.TestCase):
    """unsupported_markers.key_coords(): one parser for 'poi_X_Y' and legacy 'X:Y' keys."""

    def test_formats(self):
        from unsupported_markers import key_coords

        self.assertEqual(key_coords("poi_12_-3"), (12.0, -3.0))
        self.assertEqual(key_coords("12.5:3"), (12.5, 3.0))
        self.assertIsNone(key_coords("site_4:5"))
        self.assertIsNone(key_coords("site_7"))
        self.assertIsNone(key_coords("poi_a_b"))
        self.assertIsNone(key_coords("poi_1"))


class CleanUnsupportedTests(harness.StubTestCase):
    def test_both_key_formats_round_to_tile(self):
        # One rule for both formats: int(round(float)). A fractional
        # 'poi_X_Y' key used to parse as no coords and survive the scan check.
        data = self.world.notebook.data
        data["survey.unsupported_targets"] = {
            "poi_4.6_5": {"reason": "too_hard"},
            "7.4:8": {"reason": "too_hard"},
            "poi_1_1": {"reason": "too_hard"},
        }
        ArchiveCleaner(dry_run=False, verbose=False).clean_unsupported_targets(set(), {(5, 5), (7, 8)}, set(), set())
        self.assertEqual(list(data["survey.unsupported_targets"]), ["poi_1_1"])

    def test_legacy_pioneer_key_migrates_to_rounded_poi_key(self):
        data = self.world.notebook.data
        data["pioneer.sonar_retries"] = {"3.6:-2.2": {"reason": "too_hard"}}
        ArchiveCleaner(dry_run=False, verbose=False).clean_unsupported_targets(set(), set(), set(), set())
        self.assertEqual(list(data["survey.unsupported_targets"]), ["poi_4_-2"])


if __name__ == "__main__":
    unittest.main()
