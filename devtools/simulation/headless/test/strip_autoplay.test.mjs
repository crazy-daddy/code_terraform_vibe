import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Sim, dropLibraries } from "../simhost.mjs";

const RUN_MJS = join(dirname(fileURLToPath(import.meta.url)), "..", "run.mjs");

test("dropLibraries removes the named lib modules by entry name, not by key", () => {
  const state = {
    libraryScripts: {
      blueprint_queue: { name: "blueprint_queue.py" },
      lib_7: { name: "outpost_plan.py" },
      storage: { name: "storage.py" },
      grid_geom: { name: "other.py" }, // key matches, name does not: kept
      power_plan: {}, // no name: the key stands in
    },
  };
  assert.deepEqual(dropLibraries(state, ["blueprint_queue", "outpost_plan", "grid_geom", "power_plan", "missing"]),
    ["blueprint_queue", "outpost_plan", "power_plan"]);
  assert.deepEqual(Object.keys(state.libraryScripts), ["storage", "grid_geom"]);
  assert.deepEqual(dropLibraries({}, ["storage"]), []);
});

// A Sim over a fake worker handle: load() hands the save to sim.load as bytes.
function fakeSim() {
  class Scheduler {}
  for (const m of ["emitScriptOutput", "emitScriptWarn", "emitScriptDebug", "emitScriptConsoleError", "emitScriptError"]) {
    Scheduler.prototype[m] = () => {};
  }
  const loaded = [];
  const h = { core: { scriptScheduler: new Scheduler(), state: {} }, control: (cmd, args) => (loaded.push(JSON.parse(args.bytes)), { ok: true }) };
  return { sim: new Sim(h), loaded };
}

test("Sim.load({dropLibs}) drops the lib from the loaded copy, not from the caller's save", () => {
  const save = { state: { scripts: {}, libraryScripts: { a: { name: "blueprint_queue.py" }, b: { name: "storage.py" } } } };
  const before = JSON.stringify(save);
  const { sim, loaded } = fakeSim();
  sim.load(save, { dropLibs: ["blueprint_queue"] });
  assert.deepEqual(Object.keys(loaded[0].state.libraryScripts), ["b"]);
  assert.deepEqual(sim.droppedLibraries, ["blueprint_queue"]);
  assert.equal(JSON.stringify(save), before);
});

test("run.mjs: --include-autoplay and --strip-autoplay exclude each other", () => {
  const r = spawnSync(process.execPath, [RUN_MJS, "--save", "none.json", "--include-autoplay", "--strip-autoplay"], { encoding: "utf8" });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /--include-autoplay and --strip-autoplay exclude each other/);
});

test("run.mjs: --strip-autoplay needs a staged strip_autoplay.json", () => {
  const r = spawnSync(process.execPath, [RUN_MJS, "--save", "none.json", "--as-saved", "--strip-autoplay"], { encoding: "utf8" });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /--strip-autoplay needs --save/);
});
