import { test } from "node:test";
import assert from "node:assert/strict";
import { IMPORT_STEP_SHIM, patchImportSteps } from "../simhost.mjs";

// Synthetic snippet in the worker's shape (never copied worker code: this repo is public).
const RESOLVE = `
    try {
      this.executeModuleBodySync(c.body);
      u.status = \`ready\`;
    } catch (n) {
      if (n instanceof Ret) {
        u.status = \`ready\`;
      } else {
`;

test("the module body run goes through __ctImportStep with the return class", () => {
  const { src, why, readySignal } = patchImportSteps(RESOLVE);
  assert.equal(why, undefined);
  assert.equal(readySignal, "Ret");
  assert.match(src, /__ctImportStep\(this, \(\) => this\.executeModuleBodySync\(c\.body\), Ret\);/);
  assert.match(src, /u\.status = `ready`;/);
});

test("no return class found: null is passed", () => {
  const { src, readySignal } = patchImportSteps("this.executeModuleBodySync(c.body);\n");
  assert.equal(readySignal, null);
  assert.match(src, /, null\);/);
});

test("a missing or doubled module body run leaves the source alone", () => {
  assert.match(patchImportSteps("nothing here").why, /found 0x/);
  const twice = RESOLVE + RESOLVE;
  const r = patchImportSteps(twice);
  assert.match(r.why, /found 2x/);
  assert.equal(r.src, twice);
});

// The shim's own code against a fake evaluator.
function shim() {
  return new Function(`${IMPORT_STEP_SHIM}\nreturn { records: __ctImportSteps, step: __ctImportStep };`)();
}
class Ret { constructor(v) { this.value = v; } }
class StepLimit extends Error { constructor() { super("cap"); this.name = "StepLimitError"; } }

function evaluator() {
  return { steps: 0, stepsLimit: 1000, ownSourceName: "automation_4", moduleResolutionStack: [] };
}
// A module body run as resolveModule() does it: push the name, run, pop.
function load(ev, step, name, body) {
  ev.moduleResolutionStack.push(name);
  try { step(ev, () => body(ev), Ret); } finally { ev.moduleResolutionStack.pop(); }
}

test("nested loads: depth, steps, module name and cap per record", () => {
  const { records, step } = shim();
  const ev = evaluator();
  ev.steps = 40;
  load(ev, step, "outer", e => {
    e.steps += 10;
    load(e, step, "inner", f => { f.steps += 100; });
    e.steps += 5;
  });
  assert.deepEqual(records.map(r => [r.module, r.depth, r.before, r.after, r.cap, r.ok, r.error]), [
    ["inner", 2, 50, 150, 10000, true, null],
    ["outer", 1, 40, 155, 10000, true, null],
  ]);
  assert.equal(ev.__ctImportDepth, 0);
});

test("a step-limit throw is recorded, rethrown, and the depth restored", () => {
  const { records, step } = shim();
  const ev = evaluator();
  assert.throws(() => load(ev, step, "outer", e => {
    load(e, step, "heavy", f => { f.steps = 10001; throw new StepLimit(); });
  }), StepLimit);
  assert.deepEqual(records.map(r => [r.module, r.depth, r.ok, r.error]), [
    ["heavy", 2, false, "step_limit"],
    ["outer", 1, false, "step_limit"],
  ]);
  assert.equal(ev.__ctImportDepth, 0);
});

test("a top-level return is a normal end; other errors keep their name", () => {
  const { records, step } = shim();
  const ev = evaluator();
  assert.throws(() => load(ev, step, "returns", () => { throw new Ret(null); }), Ret);
  assert.throws(() => load(ev, step, "raises", () => { throw new TypeError("x"); }), TypeError);
  assert.deepEqual(records.map(r => [r.module, r.ok, r.error]), [["returns", true, null], ["raises", false, "TypeError"]]);
});
