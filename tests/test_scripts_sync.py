"""devtools/scripts_sync.py: library apply order and crashed-importer recovery.

The game restarts a running importer as soon as one Library is applied, and
the restarted script resolves its other imports against each Library's last
applied source. So a lib set has to be applied imported-libs-first, and a
script that crashed meanwhile has to be found from the fleet file's live
status (the workspace file keeps a stale "running" for minutes).
"""
import json
import os
import shutil
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

DEVTOOLS = Path(__file__).resolve().parent.parent / "devtools"
if str(DEVTOOLS) not in sys.path:
    sys.path.insert(0, str(DEVTOOLS))


def _fill(module, **attrs):
    for name, value in attrs.items():
        setattr(module, name, value)
    return module


def _stub_cli_modules():
    """Minimal typer/watchdog stand-ins so the module imports where the CLI
    dependencies are not installed (the test runner's interpreter)."""
    try:
        import typer  # noqa: F401
        import watchdog  # noqa: F401
        return
    except ImportError:
        pass
    typer = types.ModuleType("typer")

    class Typer:
        def __init__(self, *a, **k):
            pass

        def command(self, *a, **k):
            return lambda fn: fn

    class Exit(Exception):
        def __init__(self, code=0):
            super().__init__(code)

    _fill(typer, Typer=Typer, Exit=Exit, Option=lambda default=None, *a, **k: default,
          Argument=lambda default=None, *a, **k: default,
          echo=lambda msg="", **k: None, secho=lambda msg="", **k: None, prompt=lambda *a, **k: k.get("default"),
          colors=types.SimpleNamespace(RED="red", YELLOW="yellow", GREEN="green"))
    sys.modules["typer"] = typer
    watchdog = types.ModuleType("watchdog")
    events = _fill(types.ModuleType("watchdog.events"), FileSystemEventHandler=type("FileSystemEventHandler", (), {}))
    observers = _fill(types.ModuleType("watchdog.observers"), Observer=type("Observer", (), {}))
    polling = _fill(types.ModuleType("watchdog.observers.polling"), PollingObserver=type("PollingObserver", (), {}))
    for name, mod in (("watchdog", watchdog), ("watchdog.events", events),
                      ("watchdog.observers", observers), ("watchdog.observers.polling", polling)):
        sys.modules[name] = mod


_stub_cli_modules()
import scripts_sync as ss  # noqa: E402

# production_orders <- production <- production_cascade, site_supply
LIBS = {
    "production_orders": "SITE_ORDER_REQUESTERS = ()\n",
    "production": "from production_orders import SITE_ORDER_REQUESTERS\n",
    "production_cascade": "from production import SITE_ORDER_REQUESTERS\n",
    "site_supply": "import production\nfrom production_orders import SITE_ORDER_REQUESTERS\n",
}
IMPORTER = "import production_cascade\n"


class _FakeGame:
    """The save folder plus the game's side of the command channel: writes
    codeterraform-workspace.json / codeterraform-fleet.json and answers
    apply-library / run the way the game does."""

    def __init__(self, root: Path):
        self.root = root
        self.save = root / "save_test_scripts"
        (self.save / "lib").mkdir(parents=True)
        self.src = root / "src"
        self.src.mkdir()
        self.libraries = {}
        self.scripts = {}
        self.fleet_status = {}
        self.commands = []
        self.crashed_on_apply = []

    def add_lib(self, key, new, old=None):
        (self.save / "lib" / ("%s.py" % key)).write_text(new, encoding="utf-8")
        (self.src / ("%s.py" % key)).write_text(new, encoding="utf-8")
        self.libraries[key] = {"id": key, "name": key + ".py", "source": new,
                               "deployedSource": new if old is None else old}

    def add_script(self, stem, body, status="running"):
        (self.save / ("%s.py" % stem)).write_text(body, encoding="utf-8")
        self.scripts[stem] = {"id": stem, "name": stem + ".py", "source": body, "status": status}
        self.fleet_status[stem] = status

    def write(self, fleet=True):
        ss._workspace_cache.clear()
        ss._fleet_cache.clear()
        context = {"scripts": self.scripts, "libraryScripts": self.libraries}
        (self.save / ss.WORKSPACE_JSON).write_text(
            json.dumps({"session": {"id": "s", "generation": 1}, "context": context}), encoding="utf-8")
        if fleet:
            scripts = {s: {"name": s + ".py", "status": st, "errorLine": 1 if st == "error" else None,
                           "errorMessage": "ImportError" if st == "error" else None}
                       for s, st in self.fleet_status.items()}
            (self.save / ss.FLEET_JSON).write_text(json.dumps({"scripts": scripts}), encoding="utf-8")

    def opts(self):
        opts = ss.Options(self.save, self.src)
        opts.lib_index = {k: self.src / ("%s.py" % k) for k in self.libraries}
        opts.lib_closure = ss.lib_dependency_closure(opts.lib_index)
        return opts

    def _imports_ok(self, key):
        """True when every lib key transitively imports is applied (deployed)."""
        closure = ss.lib_dependency_closure({k: self.src / ("%s.py" % k) for k in self.libraries})
        return all(self.libraries[d]["deployedSource"] == self.libraries[d]["source"] for d in closure[key])

    def command(self, save_dir, action, **fields):
        self.commands.append((action, fields.get("scriptId")))
        if action == "apply-library":
            key = fields["scriptId"]
            self.libraries[key]["deployedSource"] = self.libraries[key]["source"]
            if not self._imports_ok(key):
                self.crashed_on_apply.append(key)
            return {"ok": True, "libraryApply": {"applied": [key + ".py"], "affected": 0, "restartFailed": 0}}
        if action == "run":
            self.fleet_status[fields["scriptId"]] = "running"
            return {"ok": True}
        return {"ok": False, "reason": "invalid_action"}


class _SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.game = _FakeGame(self.tmp)
        self._saved = {name: getattr(ss, name) for name in
                       ("SYNC_LOG", "HELD_FILE", "send_game_command", "APPLY_PICKUP_TIMEOUT_S", "RECOVER_POLL_S")}
        ss.SYNC_LOG = self.tmp / "sync.log"
        ss.HELD_FILE = self.tmp / "held.json"
        ss.send_game_command = self.game.command
        ss.APPLY_PICKUP_TIMEOUT_S = 0.0
        ss.RECOVER_POLL_S = 0.01
        for state in (ss._APPLIED_LIBS, ss._RESTARTS, ss._RECOVER_NOTES):
            state.clear()
        for state in (ss._TOUCHED_LIBS, ss._PUSHED_SCRIPTS, ss._HELD_RESTARTS, ss._HELD_LOADED, ss._REPORTED_ERRORS):
            state.clear()
        ss._APPLY_GENERATION[0] = 0

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(ss, name, value)
        shutil.rmtree(self.tmp, ignore_errors=True)


class ApplyOrderTest(_SyncTest):
    def test_imported_libs_come_first(self):
        for key, body in LIBS.items():
            self.game.add_lib(key, body)
        opts = self.game.opts()
        order = ss.apply_order(LIBS, opts.lib_closure)
        self.assertLess(order.index("production_orders"), order.index("production"))
        self.assertLess(order.index("production"), order.index("production_cascade"))
        self.assertLess(order.index("production"), order.index("site_supply"))

    def test_cycle_keeps_every_key(self):
        closure = {"a": {"b"}, "b": {"a"}, "c": set()}
        self.assertEqual(sorted(ss.apply_order({"a", "b", "c"}, closure)), ["a", "b", "c"])

    def test_dependent_set_applies_without_stale_import(self):
        for key, body in LIBS.items():
            self.game.add_lib(key, body, old="# old\n")
        self.game.write()
        self.assertEqual(ss.apply_pending_libraries(self.game.opts()), 4)
        self.assertEqual(self.game.crashed_on_apply, [])
        self.assertEqual([c for c in self.game.commands if c[0] != "apply-library"], [])
        self.assertEqual(self.game.commands[0], ("apply-library", "production_orders"))

    def test_importer_waits_for_unpicked_import(self):
        for key, body in LIBS.items():
            self.game.add_lib(key, body, old="# old\n")
        # The game has not picked up the new production_orders file yet.
        self.game.libraries["production_orders"]["source"] = "# old\n"
        self.game.write()
        self.assertEqual(ss.apply_pending_libraries(self.game.opts()), 0)
        self.assertEqual(self.game.commands, [])


class RestoredSnapshotTest(_SyncTest):
    """A save restored to an earlier snapshot: lower tier, stale lib/, slot files of the discarded timeline."""

    def setUp(self):
        super().setUp()
        self._patched = {name: getattr(ss, name) for name in
                         ("ORPHAN_DIR", "TIER_HIGH_WATER_FILE", "TIMELINE_HANDLED_FILE", "read_save_state")}
        ss.ORPHAN_DIR = self.tmp / "orphans"
        ss.TIER_HIGH_WATER_FILE = self.tmp / "high_water.json"
        ss.TIMELINE_HANDLED_FILE = self.tmp / "timeline.json"
        self.opts = self.game.opts()

    def tearDown(self):
        for name, value in self._patched.items():
            setattr(ss, name, value)
        super().tearDown()

    def test_autoplay_libs_only_from_the_lib_tier(self):
        _, tier0, _ = ss.build_index(ss.REPO / "scripts", "0_cold_boot", ss.AUTOPLAY_DIR)
        _, tier4, _ = ss.build_index(ss.REPO / "scripts", "4_controlpanel", ss.AUTOPLAY_DIR)
        autoplay = {p.stem for p in (ss.AUTOPLAY_DIR / "lib").glob("*.py")}
        self.assertFalse(autoplay & set(tier0))
        self.assertTrue(autoplay <= set(tier4))

    def test_high_water_yields_to_lost_tech(self):
        scripts = self.tmp / "scripts"
        (scripts / "0_base").mkdir(parents=True)
        (scripts / "4_lib").mkdir()
        (scripts / "4_lib" / ".criteria").write_text('{"tech": ["custom_panels_unlock"]}', encoding="utf-8")
        tiers = ["0_base", "4_lib"]
        ss.TIER_HIGH_WATER_FILE.write_text(json.dumps({self.opts.save_dir.name: "4_lib"}), encoding="utf-8")
        kept = ss._apply_tier_high_water(self.opts.save_dir, tiers, "0_base", scripts,
                                         {"unlockedTech": {"custom_panels_unlock"}})
        self.assertEqual(kept, "4_lib")  # tech still there: a building criterion lapsed
        dropped = ss._apply_tier_high_water(self.opts.save_dir, tiers, "0_base", scripts, {"unlockedTech": set()})
        self.assertEqual(dropped, "0_base")
        self.assertEqual(json.loads(ss.TIER_HIGH_WATER_FILE.read_text(encoding="utf-8"))[self.opts.save_dir.name], "0_base")

    def test_stale_lib_modules_are_retired(self):
        lib_dir = self.opts.save_dir / "lib"
        lib_dir.mkdir(exist_ok=True)
        (lib_dir / "planner_loop.py").write_text("# stale", encoding="utf-8")
        (lib_dir / "kept.py").write_text("# kept", encoding="utf-8")
        self.opts.active_tier = "4_controlpanel"  # lib tier: leftovers may still be registered Libraries
        self.assertEqual(ss.retire_stale_libs({"kept": lib_dir / "kept.py"}, self.opts), 0)
        self.opts.active_tier = "0_cold_boot"
        self.assertEqual(ss.retire_stale_libs({"kept": lib_dir / "kept.py"}, self.opts), 1)
        self.assertFalse((lib_dir / "planner_loop.py").exists())
        self.assertTrue((ss.ORPHAN_DIR / self.opts.save_dir.name / "lib" / "planner_loop.py").exists())
        self.assertTrue((lib_dir / "kept.py").exists())

    def test_undeployed_machine_slot_is_unassigned(self):
        self.game.add_script("heater_1", "# heater\n", status="idle")
        self.game.add_script("solar_1", "# solar\n")
        self.game.scripts["heater_1"]["formerHost"] = {"machineId": "heater_1", "typeId": "temp_heater", "slot": 0}
        self.game.write()
        self.assertTrue(ss.unassigned_slot(self.opts.save_dir, "heater_1"))
        self.assertFalse(ss.unassigned_slot(self.opts.save_dir, "solar_1"))

    def test_discarded_timeline_file_retired_once(self):
        text = ("Couldn't save \"solar_5.py\" to disk for external editing: it contains modified code owned "
                "by a timeline discarded by Restore Snapshot; rename or remove that file.")
        match = ss.TIMELINE_CONFLICT.search(text)
        self.assertIsNotNone(match)
        assert match is not None
        ss.read_save_state = lambda save_dir: {"timeline_conflicts": [(108, match.group(1))]}
        slot = self.opts.save_dir / "solar_5.py"
        slot.write_text("# old timeline", encoding="utf-8")
        self.assertEqual(ss.retire_timeline_conflicts(self.opts), 1)
        self.assertFalse(slot.exists())
        slot.write_text("# pushed again", encoding="utf-8")  # refilled from scripts/
        self.assertEqual(ss.retire_timeline_conflicts(self.opts), 0)
        self.assertTrue(slot.exists())


class RecoverTest(_SyncTest):
    def setUp(self):
        super().setUp()
        for key, body in LIBS.items():
            self.game.add_lib(key, body)
        ss._TOUCHED_LIBS.update(LIBS)
        self.game.add_script("drone_8", IMPORTER)
        self.game.add_script("panel_3", "print('unrelated')\n")

    def test_crash_seen_only_in_fleet_file_is_restarted(self):
        # Workspace still says "running"; only the fleet file shows the crash.
        self.game.fleet_status["drone_8"] = "error"
        self.game.write()
        self.assertEqual(ss.recover_scripts(self.game.opts()), 1)
        self.assertEqual(self.game.commands, [("run", "drone_8")])

    def test_crash_after_settle_window_restarted_on_later_tick(self):
        self.game.write()
        self.assertEqual(ss.recover_scripts(self.game.opts(), settle_s=0.05), 0)
        self.game.fleet_status["drone_8"] = "error"
        self.game.write()
        self.assertEqual(ss.recover_scripts(self.game.opts()), 1)
        self.assertEqual(self.game.commands, [("run", "drone_8")])

    def test_script_started_meanwhile_not_restarted_twice(self):
        # Both crashed; while drone_8 restarts, the operator starts everything.
        self.game.add_script("drone_9", IMPORTER)
        self.game.fleet_status.update(drone_8="error", drone_9="error")
        self.game.write()
        command = self.game.command

        def bulk_start_after_first(save_dir, action, **fields):
            result = command(save_dir, action, **fields)
            self.game.fleet_status.update(drone_8="running", drone_9="running")
            self.game.write()
            return result

        ss.send_game_command = bulk_start_after_first
        self.assertEqual(ss.recover_scripts(self.game.opts()), 1)
        self.assertEqual(self.game.commands, [("run", "drone_8")])

    def test_untouched_error_left_alone(self):
        self.game.fleet_status["panel_3"] = "error"
        self.game.write()
        self.assertEqual(ss.recover_scripts(self.game.opts()), 0)

    def test_repeat_error_not_retried(self):
        self.game.fleet_status["drone_8"] = "error"
        self.game.write()
        opts = self.game.opts()
        self.assertEqual(ss.recover_scripts(opts), 1)
        self.game.fleet_status["drone_8"] = "error"  # crashed again, same source and libs
        self.game.write()
        ss._RESTARTS["drone_8"] = ss._RESTARTS["drone_8"][:2] + (time.monotonic() - ss.RECOVER_REERROR_S,)
        self.assertEqual(ss.recover_scripts(opts), 0)
        self.assertIn("drone_8", ss._REPORTED_ERRORS)

    def test_waits_while_reached_lib_unapplied(self):
        self.game.libraries["production_orders"]["deployedSource"] = "# old\n"
        self.game.fleet_status["drone_8"] = "error"
        self.game.write()
        self.assertEqual(ss.recover_scripts(self.game.opts()), 0)
        self.assertEqual(self.game.commands, [])


class SyncLogTest(_SyncTest):
    def test_lines_are_stamped_and_appended(self):
        ss.warn("first")
        ss.ok("second\nthird")
        lines = ss.SYNC_LOG.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        self.assertRegex(lines[0], r"^\[\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z\] \[warn\] first$")
        self.assertTrue(lines[2].endswith("[ok] third"))


class HoldTest(_SyncTest):
    def setUp(self):
        super().setUp()
        self._hold_saved = (ss.SYNC_HOLDS_DIR, ss.SYNC_HOLD_FILE)
        ss.SYNC_HOLDS_DIR = self.tmp / "holds"
        ss.SYNC_HOLD_FILE = self.tmp / "hold"
        self.watcher = types.SimpleNamespace(holders=[], stale_warned=set())

    def tearDown(self):
        ss.SYNC_HOLDS_DIR, ss.SYNC_HOLD_FILE = self._hold_saved
        super().tearDown()

    def held(self):
        return ss.Watcher.held(self.watcher)  # type: ignore[arg-type]

    def test_release_keeps_another_sessions_hold(self):
        ss.hold("session-a", note="")
        ss.hold("session-b", note="")
        self.assertTrue(self.held())
        ss.release("session-a")
        self.assertEqual(sorted(ss.active_holds()), ["session-b"])
        self.assertTrue(self.held())
        ss.release("session-b")
        self.assertFalse(self.held())

    def test_legacy_hold_file_still_holds(self):
        ss.SYNC_HOLD_FILE.write_text("", encoding="utf-8")
        self.assertEqual(sorted(ss.active_holds()), ["hold"])
        self.assertTrue(self.held())

    def test_stale_hold_is_warned_once_and_still_holds(self):
        ss.hold("old", note="")
        past = time.time() - ss.HOLD_STALE_S - 60
        os.utime(ss.SYNC_HOLDS_DIR / "old", (past, past))
        self.assertTrue(self.held())
        self.assertTrue(self.held())
        log = ss.SYNC_LOG.read_text(encoding="utf-8")
        self.assertEqual(log.count("min old"), 1)

    def test_bad_holder_name_is_refused(self):
        with self.assertRaises(ss.typer.Exit):
            ss.hold("../x", note="")


if __name__ == "__main__":
    unittest.main()
