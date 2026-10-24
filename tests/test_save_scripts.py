"""devtools/simulation/headless/save_scripts.py: slots of removed roles get an empty script;
autoplay content warns, stages (--include-autoplay) or strips (--strip-autoplay)."""

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
PANEL_SLOT = "# ct-panel: build_panel\nfrom blueprint_queue import queue\n"


def library(source):
    return {"name": "x.py", "source": source}


def save_state():
    """A save at the lib tier holding the autoplay planner, an autoplay lib and a tier lib."""
    return {
        "scripts": {
            "automation_2": {"source": PLANNER_SLOT},
            "solar_1": {"source": SOLAR_SLOT},
            "playground_1": {"source": "from blueprint_queue import queue\n"},  # no source in scripts/
        },
        "libraryScripts": {
            "blueprint_queue": {"name": "blueprint_queue.py", "source": "from storage import takeable_stock\n"},
            "storage": {"name": "storage.py", "source": "X = 1\n"},
        },
    }


class AutoplayContentTest(unittest.TestCase):
    def test_finds_autoplay_slots_and_libs(self):
        slots, libs = save_scripts.autoplay_content(save_state(), {}, {"storage": Path("storage.py")})
        self.assertEqual(slots, [("automation_2", "infra_planner_automation")])
        self.assertEqual(libs, ["blueprint_queue"])

    def test_no_autoplay_content(self):
        state = {"scripts": {"solar_1": {"source": SOLAR_SLOT}}, "libraryScripts": {"storage": library("X = 1\n")}}
        self.assertEqual(save_scripts.autoplay_content(state, {}, {}), ([], []))

    def test_warning_names_content_and_both_flags(self):
        text = "\n".join(
            save_scripts.autoplay_warning([("automation_2", "infra_planner_automation")], ["blueprint_queue"])
        )
        for part in (
            "blueprint_queue",
            "automation_2 (infra_planner_automation)",
            "--include-autoplay",
            "--strip-autoplay",
        ):
            self.assertIn(part, text)

    def test_stripped_importers(self):
        hits = save_scripts.stripped_importers({"panel_7": PANEL_SLOT, "solar_1": SOLAR_SLOT}, ["blueprint_queue"])
        self.assertEqual(hits, [("panel_7", ["blueprint_queue"])])


class MainAutoplayTest(unittest.TestCase):
    """main() on a small save: warn without a flag, none with --include-autoplay, strip with --strip-autoplay."""

    def _main(self, *flags):
        with tempfile.TemporaryDirectory() as tmp:
            save = Path(tmp) / "save.json"
            save.write_text(json.dumps({"state": save_state()}), encoding="utf-8")
            out = Path(tmp) / "out"
            argv = ["save_scripts.py", "--save", str(save), "--out", str(out), "--tier", "4_controlpanel", *flags]
            err = io.StringIO()
            with mock.patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()), redirect_stderr(err):
                save_scripts.main()
            files = {
                p.relative_to(out).as_posix(): p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file()
            }
            return err.getvalue(), files

    def test_warns_without_flag(self):
        err, files = self._main()
        self.assertIn("without --include-autoplay", err)
        self.assertIn("blueprint_queue", err)
        self.assertIn("automation_2 (infra_planner_automation)", err)
        self.assertNotIn("lib/" + save_scripts.STRIP_MANIFEST, files)

    def test_no_warning_with_include_autoplay(self):
        err, files = self._main("--include-autoplay")
        self.assertNotIn("warn", err)
        self.assertIn("lib/blueprint_queue.py", files)

    def test_strip_autoplay(self):
        err, files = self._main("--strip-autoplay")
        self.assertNotIn("without --include-autoplay", err)
        self.assertEqual(files["automation_2.py"], save_scripts.STRIPPED_BODY.format(role="infra_planner_automation"))
        self.assertEqual(json.loads(files["lib/" + save_scripts.STRIP_MANIFEST]), {"libs": ["blueprint_queue"]})
        self.assertNotIn("lib/blueprint_queue.py", files)
        self.assertIn("strip lib/: blueprint_queue", err)
        self.assertIn("playground_1 imports stripped autoplay lib(s): blueprint_queue", err)
        self.assertNotIn("solar_1 imports", err)

    def test_flags_exclude_each_other(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            self._main("--include-autoplay", "--strip-autoplay")


if __name__ == "__main__":
    unittest.main()
