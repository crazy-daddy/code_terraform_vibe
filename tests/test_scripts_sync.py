"""devtools/scripts_sync.py: library apply order and crashed-importer recovery.

The game restarts a running importer as soon as one Library is applied, and
the restarted script resolves its other imports against each Library's last
applied source. So a lib set has to be applied imported-libs-first, and a
script that crashed meanwhile has to be found from the fleet file's live
status (the workspace file keeps a stale "running" for minutes).
"""

import builtins
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
        import typer
        import watchdog

        return
    except ImportError:
        pass
    typer = types.ModuleType("typer")

    class Typer:
        def __init__(self, *a, **k):
            pass

        def command(self, *a, **k):
            return lambda fn: fn

        def callback(self, *a, **k):
            return lambda fn: fn

    class Exit(Exception):
        def __init__(self, code=0):
            super().__init__(code)

    _fill(
        typer,
        Typer=Typer,
        Exit=Exit,
        Context=object,
        Option=lambda default=None, *a, **k: default,
        Argument=lambda default=None, *a, **k: default,
        echo=lambda msg="", **k: None,
        secho=lambda msg="", **k: None,
        prompt=lambda *a, **k: k.get("default"),
        colors=types.SimpleNamespace(RED="red", YELLOW="yellow", GREEN="green"),
    )
    sys.modules["typer"] = typer
    watchdog = types.ModuleType("watchdog")
    events = _fill(
        types.ModuleType("watchdog.events"), FileSystemEventHandler=builtins.type("FileSystemEventHandler", (), {})
    )
    observers = _fill(types.ModuleType("watchdog.observers"), Observer=builtins.type("Observer", (), {}))
    polling = _fill(
        types.ModuleType("watchdog.observers.polling"), PollingObserver=builtins.type("PollingObserver", (), {})
    )
    for name, mod in (
        ("watchdog", watchdog),
        ("watchdog.events", events),
        ("watchdog.observers", observers),
        ("watchdog.observers.polling", polling),
    ):
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
        self.building = set()  # script ids whose machine is still under construction
        self.unpowered = set()  # script ids whose machine has no power yet
        self.skip_on_apply = set()  # running importers an apply passes over (no loaded source)

    def add_lib(self, key, new, old=None):
        (self.save / "lib" / (f"{key}.py")).write_text(new, encoding="utf-8")
        (self.src / (f"{key}.py")).write_text(new, encoding="utf-8")
        self.libraries[key] = {
            "id": key,
            "name": key + ".py",
            "source": new,
            "deployedSource": new if old is None else old,
        }

    def add_script(self, stem, body, status="running"):
        (self.save / (f"{stem}.py")).write_text(body, encoding="utf-8")
        self.scripts[stem] = {
            "id": stem,
            "name": stem + ".py",
            "source": body,
            "status": status,
            "runtimeRunSerial": "1",
        }
        self.fleet_status[stem] = status

    def write(self, fleet=True):
        ss._workspace_cache.clear()
        ss._fleet_cache.clear()
        context = {"scripts": self.scripts, "libraryScripts": self.libraries}
        (self.save / ss.WORKSPACE_JSON).write_text(
            json.dumps({"session": {"id": "s", "generation": 1}, "context": context}), encoding="utf-8"
        )
        if fleet:
            scripts = {
                s: {
                    "name": s + ".py",
                    "status": st,
                    "errorLine": 1 if st == "error" else None,
                    "errorMessage": "ImportError" if st == "error" else None,
                }
                for s, st in self.fleet_status.items()
            }
            (self.save / ss.FLEET_JSON).write_text(json.dumps({"scripts": scripts}), encoding="utf-8")

    def opts(self):
        opts = ss.Options(self.save, self.src)
        opts.lib_index = {k: self.src / (f"{k}.py") for k in self.libraries}
        opts.lib_closure = ss.lib_dependency_closure(opts.lib_index)
        return opts

    def _bump(self, stem):
        self.scripts[stem]["runtimeRunSerial"] = str(int(self.scripts[stem]["runtimeRunSerial"]) + 1)

    def _imports_ok(self, key):
        """True when every lib key transitively imports is applied (deployed)."""
        closure = ss.lib_dependency_closure({k: self.src / (f"{k}.py") for k in self.libraries})
        return all(self.libraries[d]["deployedSource"] == self.libraries[d]["source"] for d in closure[key])

    def command(self, save_dir, action, **fields):
        self.commands.append((action, fields.get("scriptId")))
        if action == "apply-library":
            key = fields["scriptId"]
            self.libraries[key]["deployedSource"] = self.libraries[key]["source"]
            if not self._imports_ok(key):
                self.crashed_on_apply.append(key)
            opts = self.opts()
            for stem, info in self.scripts.items():
                if (
                    self.fleet_status.get(stem) == "running"
                    and stem not in self.skip_on_apply
                    and key in ss.libs_reached(info["source"], opts)
                ):
                    self._bump(stem)
            self.write()
            return {"ok": True, "libraryApply": {"applied": [key + ".py"], "affected": 0, "restartFailed": 0}}
        if action == "run":
            if fields["scriptId"] in self.building:
                return {"ok": False, "reason": "under_construction"}
            if fields["scriptId"] in self.unpowered:
                return {"ok": False, "reason": "offline"}
            self.fleet_status[fields["scriptId"]] = "running"
            if fields["scriptId"] in self.scripts:
                self._bump(fields["scriptId"])
            return {"ok": True}
        return {"ok": False, "reason": "invalid_action"}


class _SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.game = _FakeGame(self.tmp)
        self._saved = {
            name: getattr(ss, name)
            for name in (
                "SYNC_LOG",
                "HELD_FILE",
                "send_game_command",
                "APPLY_PICKUP_TIMEOUT_S",
                "APPLY_CONFIRM_TIMEOUT_S",
                "RECOVER_POLL_S",
                "STRAGGLER_SETTLE_S",
            )
        }
        ss.SYNC_LOG = self.tmp / "sync.log"
        ss.HELD_FILE = self.tmp / "held.json"
        ss.send_game_command = self.game.command
        ss.APPLY_PICKUP_TIMEOUT_S = 0.0
        ss.APPLY_CONFIRM_TIMEOUT_S = 0.0
        ss.RECOVER_POLL_S = 0.01
        ss.STRAGGLER_SETTLE_S = 0.0
        for state in (ss._APPLIED_LIBS, ss._RESTARTS, ss._RECOVER_NOTES, ss._CONSTRUCTION_WAIT):
            state.clear()
        for state in (
            ss._TOUCHED_LIBS,
            ss._PUSHED_SCRIPTS,
            ss._HELD_RESTARTS,
            ss._HELD_LOADED,
            ss._REPORTED_ERRORS,
            ss._OFFLINE_WAIT,
        ):
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

    def test_restarts_importer_the_apply_skipped(self):
        self.game.add_lib("storage", "X = 1\n", old="# old\n")
        self.game.add_script("automation_1", "from storage import X\n")
        self.game.add_script("smelter_1", "from storage import X\n")
        self.game.add_script("panel_1", "print(1)\n")
        self.game.add_script("smelter_5", "from storage import X\n", status="paused")
        self.game.skip_on_apply = {"automation_1", "smelter_5"}
        self.game.write()
        self.assertEqual(ss.apply_pending_libraries(self.game.opts()), 1)
        self.assertEqual(self.game.commands, [("apply-library", "storage"), ("run", "automation_1")])

    def test_no_restart_when_the_apply_restarted_every_importer(self):
        self.game.add_lib("storage", "X = 1\n", old="# old\n")
        self.game.add_script("automation_1", "from storage import X\n")
        self.game.write()
        ss.apply_pending_libraries(self.game.opts())
        self.assertEqual(self.game.commands, [("apply-library", "storage")])

    def _settle_run(self, rise_on_read):
        """apply_pending_libraries() with a 30 s straggler settle on a fake clock (no real wait). The apply
        skips automation_1; its run serial rises on read `rise_on_read` (1 = the pre-apply read), or never."""
        self.game.add_lib("storage", "X = 1\n", old="# old\n")
        self.game.add_script("automation_1", "from storage import X\n")
        self.game.skip_on_apply = {"automation_1"}
        self.game.write()
        ss.STRAGGLER_SETTLE_S = 30.0
        now, reads = [0.0], [0]
        clock = types.SimpleNamespace(monotonic=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
        real_serials, real_restart = ss.run_serials, ss.restart_stragglers

        def run_serials(save_dir):
            reads[0] += 1
            serials = real_serials(save_dir)
            if rise_on_read and reads[0] >= rise_on_read:
                serials["automation_1"] = serials.get("automation_1", 0) + 1
            return serials

        def restart_stragglers(*args):
            ss.time = clock  # fake clock only around the settle poll
            try:
                return real_restart(*args)
            finally:
                ss.time = time

        ss.run_serials, ss.restart_stragglers = run_serials, restart_stragglers
        try:
            ss.apply_pending_libraries(self.game.opts())
        finally:
            ss.run_serials, ss.restart_stragglers = real_serials, real_restart
        return reads[0], now[0]

    def test_settle_waits_for_a_late_serial_rise(self):
        reads, waited = self._settle_run(rise_on_read=3)
        self.assertEqual(reads, 3)  # pre-apply read, a stale poll, the risen one
        self.assertLess(waited, 30.0)
        self.assertEqual(self.game.commands, [("apply-library", "storage")])

    def test_settle_restarts_when_the_serial_never_rises(self):
        _reads, waited = self._settle_run(rise_on_read=None)
        self.assertGreater(waited, 30.0)
        self.assertEqual(self.game.commands, [("apply-library", "storage"), ("run", "automation_1")])

    def _slow_reply(self, key, reply, applies=True):
        """The fake game answers `reply` for `key` (applying it only if `applies`), normally otherwise."""
        real = self.game.command

        def command(save_dir, action, **fields):
            if action == "apply-library" and fields["scriptId"] == key and reply is not None:
                self.game.commands.append((action, key))
                if applies:
                    self.game.libraries[key]["deployedSource"] = self.game.libraries[key]["source"]
                    self.game.write()
                return {"ok": False, "reason": reply}
            return real(save_dir, action, **fields)

        ss.send_game_command = command

    def test_unconfirmed_apply_confirmed_from_workspace(self):
        for key, body in LIBS.items():
            self.game.add_lib(key, body, old="# old\n")
        self.game.write()
        self._slow_reply("production_orders", "unconfirmed")
        self.assertEqual(ss.apply_pending_libraries(self.game.opts()), 4)
        self.assertEqual(len(self.game.commands), 4)

    def test_unconfirmed_and_not_applied_stops(self):
        for key, body in LIBS.items():
            self.game.add_lib(key, body, old="# old\n")
        self.game.write()
        self._slow_reply("production_orders", "unconfirmed", applies=False)
        self.assertEqual(ss.apply_pending_libraries(self.game.opts()), 0)
        self.assertEqual(self.game.commands, [("apply-library", "production_orders")])

    def test_stale_session_changed_resends_once(self):
        self.game.add_lib("storage", "X = 1\n", old="# old\n")
        self.game.write()
        replies = ["session_changed"]
        real = self.game.command

        def command(save_dir, action, **fields):
            if replies:
                self.game.commands.append((action, fields.get("scriptId")))
                return {"ok": False, "reason": replies.pop()}
            return real(save_dir, action, **fields)

        ss.send_game_command = command
        self.assertEqual(ss.apply_pending_libraries(self.game.opts()), 1)
        self.assertEqual(self.game.commands, [("apply-library", "storage")] * 2)

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
        self._patched = {
            name: getattr(ss, name)
            for name in ("ORPHAN_DIR", "TIER_HIGH_WATER_FILE", "TIMELINE_HANDLED_FILE", "read_save_state")
        }
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
        kept = ss._apply_tier_high_water(
            self.opts.save_dir, tiers, "0_base", scripts, {"unlockedTech": {"custom_panels_unlock"}}
        )
        self.assertEqual(kept, "4_lib")  # tech still there: a building criterion lapsed
        dropped = ss._apply_tier_high_water(self.opts.save_dir, tiers, "0_base", scripts, {"unlockedTech": set()})
        self.assertEqual(dropped, "0_base")
        self.assertEqual(
            json.loads(ss.TIER_HIGH_WATER_FILE.read_text(encoding="utf-8"))[self.opts.save_dir.name], "0_base"
        )

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
        text = (
            'Couldn\'t save "solar_5.py" to disk for external editing: it contains modified code owned '
            "by a timeline discarded by Restore Snapshot; rename or remove that file."
        )
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

    def test_restart_under_construction_held_until_built(self):
        PUMP = "print('pump')\n"
        self.game.add_script("water_pump_1", PUMP, status="idle")
        self.game.building.add("water_pump_1")
        self.game.write()
        opts = self.game.opts()
        self.assertFalse(ss.restart_in_game(opts.save_dir, "water_pump_1", PUMP))
        self.assertEqual(self.game.commands, [("run", "water_pump_1")])  # no quick retries
        self.assertIn("water_pump_1", ss._HELD_RESTARTS)
        self.assertEqual(ss.recover_scripts(opts), 0)  # tried a moment ago: waits
        self.assertEqual(len(self.game.commands), 1)
        self.game.building.clear()
        ss._CONSTRUCTION_WAIT["water_pump_1"] -= ss.CONSTRUCTION_RETRY_S
        self.assertEqual(ss.recover_scripts(opts), 1)
        self.assertEqual(self.game.commands[-1], ("run", "water_pump_1"))
        self.assertNotIn("water_pump_1", ss._HELD_RESTARTS)
        self.assertNotIn("water_pump_1", ss._CONSTRUCTION_WAIT)

    def test_restart_offline_held_until_powered(self):
        CAP = "print('cap')\n"
        self.game.add_script("exotic_gas_cap_1", CAP, status="idle")
        self.game.unpowered.add("exotic_gas_cap_1")
        self.game.write()
        opts = self.game.opts()
        self.assertFalse(ss.restart_in_game(opts.save_dir, "exotic_gas_cap_1", CAP))
        self.assertEqual(self.game.commands, [("run", "exotic_gas_cap_1")])
        self.assertIn("exotic_gas_cap_1", ss._HELD_RESTARTS)
        self.assertEqual(ss.recover_scripts(opts), 0)  # tried a moment ago: waits
        self.assertEqual(len(self.game.commands), 1)
        self.game.unpowered.clear()
        ss._CONSTRUCTION_WAIT["exotic_gas_cap_1"] -= ss.CONSTRUCTION_RETRY_S
        self.assertEqual(ss.recover_scripts(opts), 1)
        self.assertEqual(self.game.commands[-1], ("run", "exotic_gas_cap_1"))
        self.assertNotIn("exotic_gas_cap_1", ss._HELD_RESTARTS)
        self.assertNotIn("exotic_gas_cap_1", ss._OFFLINE_WAIT)

    def test_offline_hold_dropped_when_started_in_game(self):
        CAP = "print('cap')\n"
        self.game.add_script("exotic_gas_cap_1", CAP, status="idle")
        self.game.unpowered.add("exotic_gas_cap_1")
        self.game.write()
        opts = self.game.opts()
        ss.restart_in_game(opts.save_dir, "exotic_gas_cap_1", CAP)
        self.game.fleet_status["exotic_gas_cap_1"] = "running"  # the panel started it once powered
        self.game.write()
        ss._CONSTRUCTION_WAIT["exotic_gas_cap_1"] -= ss.CONSTRUCTION_RETRY_S
        self.assertEqual(ss.recover_scripts(opts), 0)
        self.assertEqual(len(self.game.commands), 1)  # no second start
        self.assertNotIn("exotic_gas_cap_1", ss._HELD_RESTARTS)
        self.assertNotIn("exotic_gas_cap_1", ss._OFFLINE_WAIT)


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
