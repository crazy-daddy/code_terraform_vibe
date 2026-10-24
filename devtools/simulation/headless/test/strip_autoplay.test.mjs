import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { dropLibraries } from "../simhost.mjs";

const RUN_MJS = join(dirname(fileURLToPath(import.meta.url)), "..", "run.mjs");

test("dropLibraries removes the named lib modules by key or file name", () => {
  const state = {
    libraryScripts: {
      blueprint_queue: { name: "blueprint_queue.py" },
      lib_7: { name: "outpost_plan.py" },
      storage: { name: "storage.py" },
    },
  };
  assert.deepEqual(dropLibraries(state, ["blueprint_queue", "outpost_plan", "missing"]), ["blueprint_queue", "outpost_plan"]);
  assert.deepEqual(Object.keys(state.libraryScripts), ["storage"]);
  assert.deepEqual(dropLibraries({}, ["storage"]), []);
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
