"""devtools/simulation/headless/save_scripts.py: slots of removed roles get an empty script;
autoplay content warns (also --check), stages (--include-autoplay) or strips (--strip-autoplay)."""

import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SIMULATION = Path(__file__).resolve().parent.parent / "devtools" / "simulation"
if str(SIMULATION) not in sys.path:
    sys.path.insert(0, str(SIMULATION))

from headless import save_scripts  # noqa: E402

FOUNDING_SLOT = (
    "# ct-automation: outpost_planner_automation\n"
    "# Outpost founding planner alone -- an Automation (Computer > Automations).\n"
    "from planner_loop import run_founding\n\n"
    "run_founding()\n"
)


class RetiredRoleTest(unittest.TestCase):
    def test_founding_planner_slot_is_emptied(self):
        # Its old code imports the whole planner chain against the current libs and
        # crashed at load on the step cap in tick_profile runs (save 0839, automation_3).
        body, note = save_scripts.slot_body("automation_3", FOUNDING_SLOT, {})
        self.assertEqual(body, save_scripts.RETIRED_BODY.format(role="outpost_planner_automation"))
        self.assertEqual(note, "retired role outpost_planner_automation")


PLANNER_SLOT = "# ct-automation: infra_planner_automation\nfrom planner_loop import run\n\nrun()\n"
SOLAR_SLOT = "from solar import main\n\nmain()\n"


def make_autoplay(root: Path) -> Path:
    """A small autoplay/ tree: the planner Automation and an autoplay lib, plus solar.py and
    lib/storage.py, which scripts/ also resolves (so they stay scripts/ content)."""
    (root / "lib").mkdir(parents=True)
    (root / "infra_planner_automation.py").write_text(PLANNER_SLOT, encoding="utf-8")
    (root / "solar.py").write_text(SOLAR_SLOT, encoding="utf-8")
    (root / "lib" / "blueprint_queue.py").write_text("from storage_take import takeable_stock\n", encoding="utf-8")
    (root / "lib" / "storage.py").write_text("X = 2\n", encoding="utf-8")
    return root


def save_state():
    """A save holding the autoplay planner, a stale autoplay lib, a tier lib and a slot importing the autoplay lib."""
    return {
        "scripts": {
            "automation_2": {"source": PLANNER_SLOT},
            "solar_1": {"source": SOLAR_SLOT},
            "playground_1": {"source": "from blueprint_queue import queue\n"},  # no source in scripts/
        },
        "libraryScripts": {
            "lib_a": {"name": "blueprint_queue.py", "source": "from storage import takeable_stock\n"},
            "storage": {"name": "storage.py", "source": "X = 1\n"},
        },
    }


class AutoplayContentTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.autoplay = make_autoplay(Path(tmp.name) / "autoplay")

    def content(self, state, script_index=None, lib_index=None):
        tier_scripts = {"solar": Path("solar.py")} if script_index is None else script_index
        tier_libs = {"storage": Path("storage.py")} if lib_index is None else lib_index
        return save_scripts.autoplay_content(state, tier_scripts, tier_libs, self.autoplay)

    def test_finds_autoplay_slots_and_libs_by_entry_name(self):
        self.assertEqual(
            self.content(save_state()), ([("automation_2", "infra_planner_automation")], ["blueprint_queue"])
        )

    def test_keys_scripts_also_resolves_stay_scripts_content(self):
        # solar.py and lib/storage.py exist in autoplay/ too, but the tier resolves them.
        slots, libs = self.content(save_state())
        self.assertNotIn("solar_1", dict(slots))
        self.assertNotIn("storage", libs)
        # Without the tier's keys they would count as autoplay.
        slots, libs = self.content(save_state(), {}, {})
        self.assertIn("solar_1", dict(slots))
        self.assertIn("storage", libs)

    def test_no_autoplay_content(self):
        state = {"scripts": {"solar_1": {"source": SOLAR_SLOT}}, "libraryScripts": {"storage": {"name": "storage.py"}}}
        self.assertEqual(self.content(state), ([], []))

    def test_lib_tier_gate(self):
        self.assertTrue(save_scripts.at_lib_tier("4_controlpanel"))
        self.assertFalse(save_scripts.at_lib_tier("0_cold_boot"))
        self.assertFalse(save_scripts.at_lib_tier("contract"))

    def test_stripped_importers(self):
        hits = save_scripts.stripped_importers(
            {"panel_7": "from blueprint_queue import queue\n", "solar_1": SOLAR_SLOT}, ["blueprint_queue"]
        )
        self.assertEqual(hits, [("panel_7", ["blueprint_queue"])])


class MainAutoplayTest(unittest.TestCase):
    """main() on a small save with a tmp autoplay/: warn, --check, --include-autoplay, --strip-autoplay."""

    def _main(self, *flags, tier="4_controlpanel", out=True, staged=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            autoplay = make_autoplay(root / "autoplay")
            save = root / "save.json"
            save.write_text(json.dumps({"state": save_state()}), encoding="utf-8")
            before = hashlib.sha256(save.read_bytes()).hexdigest()
            extra = []
            for option, files in (staged or {}).items():
                folder = root / option.strip("-")
                folder.mkdir()
                for name in files:
                    (folder / name).write_text("", encoding="utf-8")
                extra += [option, str(folder)]
            argv = ["save_scripts.py", "--save", str(save), "--tier", tier, "--autoplay-dir", str(autoplay)]
            argv += ["--out", str(root / "out")] if out else []
            err = io.StringIO()
            with (
                mock.patch.object(sys, "argv", [*argv, *extra, *flags]),
                redirect_stdout(io.StringIO()),
                redirect_stderr(err),
            ):
                save_scripts.main()
            self.assertEqual(hashlib.sha256(save.read_bytes()).hexdigest(), before, "save file changed")
            outdir = root / "out"
            # Read slot scripts, the strip manifest and the autoplay lib under test; the ~200 staged lib copies
            # only by name (reading them all cost about a second per call on Windows).
            read_libs = {"lib/" + save_scripts.STRIP_MANIFEST, "lib/blueprint_queue.py"}
            files = {}
            for p in outdir.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(outdir).as_posix()
                    files[rel] = p.read_text(encoding="utf-8") if "/" not in rel or rel in read_libs else ""
            return err.getvalue(), files

    def test_warns_without_flag(self):
        err, files = self._main()
        self.assertIn("without --include-autoplay", err)
        self.assertIn("lib/: blueprint_queue\n", err)
        self.assertIn("slots: automation_2 (infra_planner_automation)\n", err)
        self.assertNotIn("lib/" + save_scripts.STRIP_MANIFEST, files)

    def test_below_the_lib_tier_only_the_warning_is_gated(self):
        err, _ = self._main(tier="0_cold_boot")
        self.assertNotIn("warn", err)
        _, files = self._main("--include-autoplay", tier="0_cold_boot")
        self.assertIn("lib/blueprint_queue.py", files)  # staged as before: run.mjs adds the planner
        _, files = self._main("--strip-autoplay", tier="0_cold_boot")
        self.assertEqual(files["automation_2.py"], save_scripts.STRIPPED_BODY.format(role="infra_planner_automation"))
        # The fixture's autoplay/lib/storage.py counts too here: tier 0 resolves no storage lib.
        self.assertIn("blueprint_queue", json.loads(files["lib/" + save_scripts.STRIP_MANIFEST])["libs"])

    def test_no_warning_with_include_autoplay(self):
        err, files = self._main("--include-autoplay")
        self.assertNotIn("warn", err)
        # autoplay/lib's copy, not the stale one the save holds
        self.assertEqual(files["lib/blueprint_queue.py"], "from storage_take import takeable_stock\n")

    def test_check_warns_and_writes_nothing(self):
        err, files = self._main("--check", out=False)
        self.assertIn("lib/: blueprint_queue\n", err)
        self.assertEqual(files, {})

    def test_check_skips_what_the_run_stages(self):
        staged = {"--staged-scripts": ["automation_2.py"], "--staged-libs": ["blueprint_queue.py"]}
        err, _ = self._main("--check", out=False, staged=staged)
        self.assertNotIn("warn", err)

    def test_strip_autoplay(self):
        err, files = self._main("--strip-autoplay")
        self.assertNotIn("without --include-autoplay", err)
        self.assertEqual(files["automation_2.py"], save_scripts.STRIPPED_BODY.format(role="infra_planner_automation"))
        self.assertEqual(json.loads(files["lib/" + save_scripts.STRIP_MANIFEST]), {"libs": ["blueprint_queue"]})
        self.assertNotIn("lib/blueprint_queue.py", files)
        self.assertIn("strip lib/: blueprint_queue", err)
        self.assertIn("playground_1 imports stripped autoplay lib(s): blueprint_queue", err)
        self.assertNotIn("solar_1 imports", err)
        self.assertNotIn("Autoplay role", files.get("solar_1.py", ""))  # scripts/ content, not stripped


if __name__ == "__main__":
    unittest.main()
