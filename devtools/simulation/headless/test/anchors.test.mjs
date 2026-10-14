import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { DEFAULT_SIMWORKER, patchSimworker } from "../simhost.mjs";
import { patchInstantBuild, patchScale } from "../anchors.mjs";

// Against the real worker (private internals/ submodule): every optional
// feature on, every scale anchor matched once. Skipped where internals/ is
// absent (cloud sessions). Run after a game update (dev_workflow.md §10c).
const path = process.env.CT_SIMWORKER || DEFAULT_SIMWORKER;
const skip = existsSync(path) ? false : "no simworker in internals/";

test("every simworker anchor matches on the current build", { skip }, () => {
  const raw = readFileSync(path, "utf8");
  const { features, warnings } = patchSimworker(raw);
  assert.deepEqual(warnings, []);
  assert.deepEqual(Object.entries(features).filter(([, v]) => !v), []);
  const scale = patchScale(raw);
  assert.equal(scale.why, null);
  assert.deepEqual(Object.values(scale.hits), [1, 1, 1, 1, 1]);
  assert.equal(patchInstantBuild(raw).hits, 1);
});
