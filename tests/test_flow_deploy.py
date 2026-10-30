"""Deploy flow: devtools/scripts_sync.py pushes a scripts/ tree into a save.

Two full passes of `sync_all()` (the path `watch` runs on every repo edit)
over a temp save and a small fixture tree at the lib tier: the first updates
every lib and slot, the second renames one lib and drops another. The fake
game picks up files written into the save the way the game does (Library and
slot sources follow the files on disk), registers new Libraries, applies
them and restarts their running importers. Asserted from the outside: the
save's slot files and lib/ match the source, every Library runs the source
code, libs apply imported-first, and every importer's last start ran
against the fully applied lib set.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from test_scripts_sync import _FakeGame, _SyncTest, ss

LIB_TIER = "4_lib"

PASS_1 = {
    "0_base/power/solar.py": "SOLAR = 1\n",
    f"{LIB_TIER}/factory/smelter.py": "from top import TOP\n# smelter v1\n",
    f"{LIB_TIER}/lib/base.py": "BASE = 1\n",
    f"{LIB_TIER}/lib/mid.py": "from base import BASE\nMID = BASE\n",
    f"{LIB_TIER}/lib/top.py": "from mid import MID\nTOP = MID\n",
    f"{LIB_TIER}/lib/old_helper.py": "HELPER = 1\n",
}
# mid renamed to middle, old_helper removed, top and solar changed.
PASS_2 = {
    "0_base/power/solar.py": "SOLAR = 2\n",
    f"{LIB_TIER}/factory/smelter.py": "from top import TOP\n# smelter v1\n",
    f"{LIB_TIER}/lib/base.py": "BASE = 1\n",
    f"{LIB_TIER}/lib/middle.py": "from base import BASE\nMIDDLE = BASE\n",
    f"{LIB_TIER}/lib/top.py": "from middle import MIDDLE\nTOP = MIDDLE\n",
}


class _FileWatchingGame(_FakeGame):
    """_FakeGame whose Library and slot sources follow the save's files (the
    game picks up a written file), with create-library, and a record of each
    script start: did every lib it reaches run its on-disk source then?"""

    def __init__(self, root: Path):
        super().__init__(root)
        shutil.rmtree(self.src)
        self.src = self.save / "lib"  # libs resolve against the save's own lib/
        self.starts: dict = {}

    def pickup(self):
        changed = False
        for key, info in self.libraries.items():
            path = self.src / f"{key}.py"
            if path.is_file() and info["source"] != (text := path.read_text(encoding="utf-8")):
                info["source"] = text
                changed = True
        for stem, info in self.scripts.items():
            path = self.save / f"{stem}.py"
            if path.is_file() and info["source"] != (text := path.read_text(encoding="utf-8")):
                info["source"] = text
                changed = True
        if changed:
            self.write()

    def _bump(self, stem):
        self.pickup()
        super()._bump(stem)
        reached = ss.libs_reached(self.scripts[stem]["source"], self.opts())
        current = all(
            self.libraries[k]["deployedSource"] == (self.src / f"{k}.py").read_text(encoding="utf-8") for k in reached
        )
        self.starts.setdefault(stem, []).append(current)

    def command(self, save_dir, action, **fields):
        if action == "create-library":
            self.commands.append((action, fields["name"]))
            key = fields["name"]
            self.libraries[key] = {
                "id": key,
                "name": key + ".py",
                "source": fields["source"],
                "deployedSource": fields["source"],
            }
            self.write()
            return {"ok": True}
        return super().command(save_dir, action, **fields)


class DeployFlowTest(_SyncTest):
    def setUp(self):
        super().setUp()
        self.game = _FileWatchingGame(Path(tempfile.mkdtemp(dir=self.tmp)))
        ss.send_game_command = self.game.command
        self._patched = {
            name: getattr(ss, name)
            for name in (
                "BACKUP_DIR",
                "ORPHAN_DIR",
                "TIMELINE_HANDLED_FILE",
                "RECOVER_SETTLE_S",
                "STRAGGLER_SETTLE_S",
                "read_save_state",
                "read_workspace_context",
                "echo",
                "ok",
                "warn",
                "err",
            )
        }
        for name in ("echo", "ok", "warn", "err"):
            setattr(ss, name, lambda msg: None)
        ss.BACKUP_DIR = self.tmp / "backups"
        ss.ORPHAN_DIR = self.tmp / "orphans"
        ss.TIMELINE_HANDLED_FILE = self.tmp / "timeline.json"
        ss.RECOVER_SETTLE_S = 0.0
        ss.STRAGGLER_SETTLE_S = 0.0
        ss.read_save_state = lambda save_dir: None
        real_read = self._patched["read_workspace_context"]

        def read_after_pickup(save_dir):
            self.game.pickup()
            return real_read(save_dir)

        ss.read_workspace_context = read_after_pickup
        for state in (ss._REGISTERED_LIBS, ss.HELD_SLOTS, ss._FILL_BASE_WAIT, ss.ROLELESS_WARNED):
            state.clear()
        self.scripts = self.tmp / "scripts"
        # The save before the push: old code everywhere, every lib registered and applied.
        for key in ("base", "mid", "top", "old_helper"):
            self.game.add_lib(key, "# old\n")
        self.game.add_script("solar_1", "SOLAR = 0\n")
        self.game.add_script("smelter_1", "from top import TOP\n# old smelter\n")
        self.game.write()

    def tearDown(self):
        for name, value in self._patched.items():
            setattr(ss, name, value)
        super().tearDown()

    def _write_tree(self, files):
        if self.scripts.exists():
            shutil.rmtree(self.scripts)
        for rel, body in files.items():
            path = self.scripts / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

    def _push(self, files):
        self._write_tree(files)
        opts = ss.Options(self.game.save, self.scripts, apply_libs=True)
        opts.active_tier = LIB_TIER
        script_index, lib_index, conflicts = ss.build_index(self.scripts, LIB_TIER)
        self.assertEqual(conflicts, {})
        self.game.commands.clear()
        self.game.starts.clear()
        ss.sync_all(script_index, lib_index, opts)
        return lib_index

    def _applied(self):
        return [key for action, key in self.game.commands if action == "apply-library"]

    def _assert_save_matches(self, files, lib_index):
        save = self.game.save
        self.assertEqual((save / "solar_1.py").read_text(encoding="utf-8"), files["0_base/power/solar.py"])
        self.assertEqual((save / "smelter_1.py").read_text(encoding="utf-8"), files[f"{LIB_TIER}/factory/smelter.py"])
        for key, source in lib_index.items():
            body = source.read_text(encoding="utf-8")
            self.assertEqual((save / "lib" / f"{key}.py").read_text(encoding="utf-8"), body, key)
            self.assertEqual(self.game.libraries[key]["deployedSource"], body, f"{key} not applied")
        self.assertEqual(self.game.crashed_on_apply, [])
        # Every start of the lib importer ran against the applied lib set.
        self.assertTrue(self.game.starts.get("smelter_1"), "importer never restarted")
        self.assertTrue(self.game.starts["smelter_1"][-1], "importer last started on a stale lib")
        self.assertIn(("run", "solar_1"), self.game.commands)

    def test_push_then_rename_and_drop_a_lib(self):
        lib_index = self._push(PASS_1)
        self._assert_save_matches(PASS_1, lib_index)
        applied = self._applied()
        self.assertLess(applied.index("base"), applied.index("mid"))
        self.assertLess(applied.index("mid"), applied.index("top"))

        lib_index = self._push(PASS_2)
        self._assert_save_matches(PASS_2, lib_index)
        self.assertIn(("create-library", "middle"), self.game.commands)
        applied = self._applied()
        self.assertNotIn("base", applied)  # unchanged: not applied again
        self.assertIn("top", applied)
        # At the lib tier a dropped module stays in lib/ (the game may still list
        # it as a Library), but no slot in the save reaches it any more.
        opts = ss.Options(self.game.save, self.scripts)
        opts.lib_index = {p.stem: p for p in (self.game.save / "lib").glob("*.py")}
        opts.lib_closure = ss.lib_dependency_closure(opts.lib_index)
        for slot in ("solar_1", "smelter_1"):
            reached = ss.libs_reached((self.game.save / f"{slot}.py").read_text(encoding="utf-8"), opts)
            self.assertFalse(reached & {"mid", "old_helper"}, slot)


if __name__ == "__main__":
    unittest.main()
