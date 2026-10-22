"""devtools/perf/tick_profile.py: lib patching, the gate, --chunk-scale and the presets' argv."""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools", "perf"))

import tick_profile as tp

OUTPOST_PLAN = """\
GEO_PROBE_CHUNK = 4  # biome reads per atomic slice
STEP_UNITS = 50


def _rank(urgency):
    return urgency


def plan_sites(ctx):
    return ctx


class OutpostPlanner:
    def __init__(self):
        self.x = 1

    def step(self, tick):
        return self._replan([], tick)

    def _replan(self, proposals, tick):
        return self._rank(proposals, None, tick)

    def _rank(self, plan, snap, tick):
        return plan

    @property
    def busy(self):
        return False


def after():
    return 2
"""


def _lib_dir(root):
    lib = os.path.join(root, "lib")
    os.makedirs(lib)
    with open(os.path.join(lib, "outpost_plan.py"), "w", encoding="utf-8") as f:
        f.write(OUTPOST_PLAN)
    return lib


def _founding(lib, chunk_scale=1.0):
    preset = tp.PRESETS["founding"]
    return tp.patch_libs(
        lib,
        ["outpost_plan"],
        [("outpost_plan", "OutpostPlanner")],
        preset["gate"],
        preset["label"],
        set(preset["skip"].split(",")),
        chunk_scale,
    )


class PatchLibsTest(unittest.TestCase):
    def test_founding_gate_and_wrappers(self):
        with tempfile.TemporaryDirectory() as root:
            lib = _lib_dir(root)
            counts = _founding(lib)
            with open(os.path.join(lib, "outpost_plan.py"), encoding="utf-8") as f:
                text = f.read()
            self.assertTrue(text.startswith(OUTPOST_PLAN))
            tail = text[len(OUTPOST_PLAN) :]
            self.assertIn("import tick_profile_rt as _tp", tail)
            self.assertIn("plan_sites = _tp.wrap('outpost_plan.plan_sites', plan_sites)\n", tail)
            self.assertIn("after = _tp.wrap('outpost_plan.after', after)\n", tail)
            self.assertIn("OutpostPlanner.step = _tp.wrap('OutpostPlanner.step', OutpostPlanner.step)\n", tail)
            # Skipped by name: the module helper and the method of the same name.
            self.assertNotIn("_tp.wrap('outpost_plan._rank'", tail)
            self.assertNotIn("OutpostPlanner._rank =", tail)
            # The gated method is gated, never wrapped as well.
            self.assertNotIn("OutpostPlanner._replan = _tp.wrap", tail)
            self.assertIn("_tp_gated = OutpostPlanner._replan\n", tail)
            self.assertIn("    label = str(args[1])\n", tail)
            self.assertIn("OutpostPlanner._replan = _tp_gate\n", tail)
            self.assertEqual(counts, {"outpost_plan": 2, "outpost_plan:OutpostPlanner": 1})
            self.assertTrue(os.path.exists(os.path.join(lib, "tick_profile_rt.py")))
            compile(text, "outpost_plan.py", "exec")

    def test_chunk_scale_rewrites_patched_modules_only(self):
        with tempfile.TemporaryDirectory() as root:
            lib = _lib_dir(root)
            other = os.path.join(lib, "other.py")
            with open(other, "w", encoding="utf-8") as f:
                f.write("SITE_CHUNK = 8\n")
            _founding(lib, chunk_scale=0.5)
            with open(os.path.join(lib, "outpost_plan.py"), encoding="utf-8") as f:
                text = f.read()
            self.assertIn("GEO_PROBE_CHUNK = 2  # biome reads per atomic slice\n", text)
            self.assertIn("STEP_UNITS = 25\n", text)
            with open(other, encoding="utf-8") as f:
                self.assertEqual(f.read(), "SITE_CHUNK = 8\n")

    def test_chunk_scale_keeps_at_least_one(self):
        self.assertEqual(tp.scale_chunks("FILTER_CHUNK = 1\n", 0.25), ("FILTER_CHUNK = 1\n", 1))
        self.assertEqual(tp.scale_chunks("X_CHUNK = 3\nY = 3\n", 2), ("X_CHUNK = 6\nY = 3\n", 1))

    def test_chunk_scale_only_plain_literals(self):
        source = "A_CHUNK = 4 * 2\nB_CHUNK = 0x10\n    C_CHUNK = 8\nD_CHUNK = 8  # note\nE_CHUNK = 8"
        self.assertEqual(
            tp.scale_chunks(source, 0.5),
            ("A_CHUNK = 4 * 2\nB_CHUNK = 0x10\n    C_CHUNK = 8\nD_CHUNK = 4  # note\nE_CHUNK = 4", 2),
        )

    def test_function_gate_is_not_wrapped_too(self):
        with tempfile.TemporaryDirectory() as root:
            lib = _lib_dir(root)
            counts = tp.patch_libs(lib, ["outpost_plan"], [], "outpost_plan:plan_sites", "'x'", set())
            with open(os.path.join(lib, "outpost_plan.py"), encoding="utf-8") as f:
                tail = f.read()[len(OUTPOST_PLAN) :]
            self.assertNotIn("plan_sites = _tp.wrap", tail)
            self.assertIn("_tp_gated = plan_sites\n", tail)
            self.assertEqual(counts, {"outpost_plan": 2})


class MainArgvTest(unittest.TestCase):
    def _run(self, *argv, out_arg=True):
        """main() with subprocess.run mocked; returns the argv lists it was called with."""
        calls = []
        with tempfile.TemporaryDirectory() as out, mock.patch.object(tp.tempfile, "mkdtemp", return_value=out):

            def fake_run(command, **kwargs):
                calls.append(list(command))
                if command[0] == "node":
                    run_dir = os.path.join(out, "run")
                    os.makedirs(run_dir, exist_ok=True)
                    with open(os.path.join(run_dir, "console.log"), "w", encoding="utf-8") as f:
                        f.write("")

            with (
                mock.patch.object(tp.subprocess, "run", side_effect=fake_run),
                mock.patch.object(tp, "patch_libs", return_value={}) as patch,
                mock.patch.object(tp, "summarize"),
                mock.patch.object(
                    sys, "argv", ["tick_profile.py", "--save", "S.json", *(["--out", out] if out_arg else []), *argv]
                ),
                mock.patch("builtins.print"),
            ):
                tp.main()
        return calls, patch.call_args.args

    def test_founding_preset(self):
        calls, patch_args = self._run("--preset", "founding")
        stage, node = calls
        self.assertIn("--include-autoplay", stage)
        self.assertEqual(stage[stage.index("--save") + 1], "S.json")
        self.assertIn("--include-autoplay", node)
        self.assertIn("--libs", node)
        _lib, modules, classes, gate, label, skip, chunk_scale = patch_args
        self.assertEqual(modules, ["outpost_plan", "outpost_sites", "outpost_needs"])
        self.assertEqual(classes, [("outpost_plan", "OutpostPlanner")])
        self.assertEqual(gate, "outpost_plan:OutpostPlanner._replan")
        self.assertEqual(label, "args[1]")
        self.assertTrue({"log", "_ceil", "_rank", "_fmt_price", "score", "check"} <= skip)
        self.assertEqual(chunk_scale, 1.0)

    def test_refresh_is_the_default(self):
        calls, patch_args = self._run()
        stage, node = calls
        self.assertNotIn("--include-autoplay", stage)
        self.assertNotIn("--include-autoplay", node)
        self.assertEqual(patch_args[1], tp.DEFAULT_MODULES.split(","))
        self.assertEqual(patch_args[3], tp.DEFAULT_GATE)

    def test_explicit_options_override_the_preset(self):
        _calls, patch_args = self._run(
            "--preset", "founding", "--gate", "outpost_plan:OutpostPlanner._rank", "--chunk-scale", "0.5"
        )
        self.assertEqual(patch_args[3], "outpost_plan:OutpostPlanner._rank")
        self.assertEqual(patch_args[1], ["outpost_plan", "outpost_sites", "outpost_needs"])
        self.assertEqual(patch_args[6], 0.5)

    def test_chunk_scale_must_be_positive(self):
        for bad in ("0", "-1", "nan"):
            with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
                self._run("--chunk-scale", bad)

    def test_function_gate_label_needs_no_self(self):
        _calls, patch_args = self._run("--gate", "fleet_intent:haul_root", "--modules", "fleet_intent")
        self.assertEqual(patch_args[3], "fleet_intent:haul_root")
        self.assertEqual(patch_args[4], "'haul_root'")

    def test_function_gate_rejects_an_explicit_self_label(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            self._run("--gate", "fleet_intent:haul_root", "--label", "self.name")

    def test_out_defaults_to_a_temp_dir(self):
        calls, _ = self._run(out_arg=False)
        stage, node = calls
        self.assertTrue(stage[stage.index("--out") + 1].endswith("scripts"))
        self.assertTrue(node[node.index("--out") + 1].endswith("run"))

    def test_include_autoplay_without_preset(self):
        calls, _ = self._run("--include-autoplay")
        stage, node = calls
        self.assertIn("--include-autoplay", stage)
        self.assertIn("--include-autoplay", node)


if __name__ == "__main__":
    unittest.main()
