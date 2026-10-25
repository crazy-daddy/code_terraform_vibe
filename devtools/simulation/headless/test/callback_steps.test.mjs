import { test } from "node:test";
import assert from "node:assert/strict";
import { CALLBACK_STEP_SHIM, patchCallbackSteps } from "../simhost.mjs";

// Synthetic snippets in the worker's shape (never copied worker code: this repo is public).
const PURE = `
  *runResumablePureCallback(f, args, line = this.currentLine, opts = {}) {
    let node = this.prepare(line);
    let cap = this.stepsLimit * 10;
    let own = 0;
    while (true) {
      let start = this.steps;
      let s;
      s = this.withPureCallback(() => this.evalPreparedCall(node, f, args, opts.kwargs));
      own += this.steps - start;
      if (own > cap) {
        throw new StepLimit(cap, this.currentLine);
      }
      return s;
    }
  }
`;
const PUSH = `
  pushDebugCallFrame(e) {
    let t = { line: e.line };
    this.callFrameStack.push(t);
    return t;
  }
`;

test("the pure callback call goes through __ctPureCall, frames through __ctCallbackFrame", () => {
  const { src, why, inner } = patchCallbackSteps(PURE + PUSH);
  assert.equal(why, undefined);
  assert.equal(inner, true);
  assert.match(src, /s = __ctPureCall\(this, f, \(\) => this\.withPureCallback\(\(\) => this\.evalPreparedCall\(node, f, args, opts\.kwargs\)\)\);/);
  assert.match(src, /pushDebugCallFrame\(e\) \{\n {4}if \(this\.__ctCbWant === this\.callFrameStack\.length\) __ctCallbackFrame\(this, e\);\n/);
});

test("no pushDebugCallFrame: patched without callee names", () => {
  const { src, why, inner } = patchCallbackSteps(PURE);
  assert.equal(why, undefined);
  assert.equal(inner, false);
  assert.match(src, /__ctPureCall\(this, f,/);
});

test("a missing, doubled or changed callback runner leaves the source alone", () => {
  assert.match(patchCallbackSteps("nothing here").why, /found 0x/);
  const twice = PURE + PURE;
  const r = patchCallbackSteps(twice);
  assert.match(r.why, /found 2x/);
  assert.equal(r.src, twice);
  const noCap = PURE.replace(/if \(own > cap\)/, "if (false)");
  assert.match(patchCallbackSteps(noCap).why, /step-limit check not found/);
  const otherFn = PURE.replace("this.evalPreparedCall(node, f,", "this.evalPreparedCall(node, g,");
  assert.match(patchCallbackSteps(otherFn).why, /pure callback call not found/);
});

// The shim's own code against a fake evaluator.
function shim() {
  return new Function(`${CALLBACK_STEP_SHIM}\nreturn { records: __ctCallbackSteps, call: __ctPureCall, frame: __ctCallbackFrame, on: v => { __ctCallbackOn = v; } };`)();
}
class StepLimit extends Error { constructor() { super("cap"); this.name = "StepLimitError"; } }

function evaluator() {
  const ev = { steps: 0, stepsLimit: 1000, ownSourceName: "drone_7", callFrameStack: [], currentSourceId: null, currentLine: 0 };
  return ev;
}
// A user function call as the evaluator runs one: push a debug frame (through the hook), run, pop.
function callFn(ev, s, name, sourceId, body) {
  const frame = { fnName: name.split(".").at(-1), fnQualname: name, sourceId };
  if (ev.__ctCbWant === ev.callFrameStack.length) s.frame(ev, frame);
  ev.callFrameStack.push(frame);
  try { return body(); } finally { ev.callFrameStack.pop(); }
}
const lambda = { type: "function", name: "<lambda>", qualname: "run_atomic.<locals>.<lambda>", sourceId: "atomic" };

test("off: the callback runs, nothing is recorded", () => {
  const s = shim();
  const ev = evaluator();
  assert.equal(s.call(ev, lambda, () => 7), 7);
  assert.equal(s.records.size, 0);
});

test("a run_atomic() slice: named by lambda and fn, peak with its before, nested callbacks inside", () => {
  const s = shim();
  s.on(true);
  const ev = evaluator();
  const slice = steps => s.call(ev, lambda, () => callFn(ev, s, "run_atomic.<locals>.<lambda>", "atomic", () =>
    callFn(ev, s, "fair_rival_bands", "logistics_requests", () => {
      ev.steps += steps;
      // A sorted(key=) inside the slice is no record of its own.
      s.call(ev, { name: "key" }, () => { ev.steps += 10; });
      ev.currentSourceId = "atomic";
      ev.currentLine = 84;
      return steps;
    })));
  ev.steps = 300;
  slice(2000);
  ev.steps = 50;
  slice(3000);
  const recs = [...s.records.values()];
  assert.equal(recs.length, 1);
  const r = recs[0];
  assert.deepEqual([r.script, r.fn, r.source, r.inner, r.innerSource, r.cap], ["drone_7", "run_atomic.<locals>.<lambda>", "atomic", "fair_rival_bands", "logistics_requests", 10000]);
  assert.deepEqual([r.count, r.ownSum, r.ownMax, r.peak, r.peakBefore, r.peakSource, r.peakLine, r.limit], [2, 5020, 3010, 3060, 50, "atomic", 84, 0]);
  assert.equal(ev.__ctCb, null);
});

test("a step-limit throw is recorded at the throwing line and rethrown", () => {
  const s = shim();
  s.on(true);
  const ev = evaluator();
  ev.steps = 9000;
  assert.throws(() => s.call(ev, { type: "function", name: "heavy", qualname: "heavy", sourceId: "roles" }, () => {
    ev.steps = 10001;
    ev.currentSourceId = "roles";
    ev.currentLine = 12;
    throw new StepLimit();
  }), StepLimit);
  const [r] = s.records.values();
  assert.deepEqual([r.fn, r.source, r.inner, r.peak, r.peakBefore, r.peakSource, r.peakLine, r.limit], ["heavy", "roles", null, 10001, 9000, "roles", 12, 1]);
  assert.equal(ev.__ctCb, null);
  // The next callback records again.
  s.call(ev, { type: "function", name: "light", sourceId: "roles" }, () => { ev.steps += 1; });
  assert.equal(s.records.size, 2);
});

test("a slice counter at exactly the cap counts as a step-limit end (the >= checks)", () => {
  const s = shim();
  s.on(true);
  const ev = evaluator();
  ev.steps = 400;
  s.call(ev, { name: "updater", sourceId: "logistics_requests" }, () => { ev.steps = 10000; });
  const [r] = s.records.values();
  assert.deepEqual([r.peak, r.limit], [10000, 1]);
});

test("own steps never go negative (a counter reset inside an attempt)", () => {
  const s = shim();
  s.on(true);
  const ev = evaluator();
  ev.steps = 500;
  s.call(ev, { name: "f", sourceId: "x" }, () => { ev.steps = 20; });
  const [r] = s.records.values();
  assert.deepEqual([r.ownSum, r.ownMax, r.peak], [0, 0, 20]);
});

test("own steps over the cap count as a step-limit end", () => {
  const s = shim();
  s.on(true);
  const ev = evaluator();
  s.call(ev, { type: "bound_method", func: { name: "m", qualname: "C.m", sourceId: "x" } }, () => { ev.steps += 10001; });
  const [r] = s.records.values();
  assert.deepEqual([r.fn, r.source, r.limit], ["C.m", "x", 1]);
});
