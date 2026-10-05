// Headless host for the game's decompiled simworker: runs the real
// simulation (systems + Python interpreter + scheduler) in Node, without the
// browser worker, UI or wall clock. See docs/cheatsheet/dev_workflow.md §10b.
//
// The decompiled file is private (internals/ submodule) and is never copied
// into the repo: loadSimModule() appends a small export shim to it at run
// time and caches the result under devtools/headless/.cache/ (gitignored).

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");
export const DEFAULT_SIMWORKER = join(REPO, "internals", "terraform_decompiled", "simworker", "deobfuscated.js");
const SHIM_VERSION = 2;

// Names below are the minified identifiers of the simworker build the shim was
// written against. After a game update, re-find them next to the worker
// bootstrap at the end of the file (the function that builds `new tCe(LB(seed))`
// and the SimHost with loadState/serializeState/runTick).
const SHIM = String.raw`
const __ctSystemMs = new Map();
const __ctSkipSystems = new Set();
function __ctTimedSystem(name, fn) {
  if (__ctSkipSystems.has(name)) return;
  const t0 = performance.now();
  try { fn(); } finally {
    __ctSystemMs.set(name, (__ctSystemMs.get(name) ?? 0) + performance.now() - t0);
  }
}
function __ctCreateHeadless(opts = {}) {
  _e(mue, ${"`en`"});
  const core = new tCe(LB(opts.seed ?? 1));
  let nextId = 0;
  const host = new _Ce({
    initialState: core.state, initialStateInstalled: false, devModeEnabled: false,
    createNewState: e => LB(e),
    loadState: e => Kpe(e),
    serializeState: qpe, produceSnapshot: Kbe,
    validateReplacementSnapshot: (e, t) => MCe(e, t),
    readTick: e => e.tickCount,
    prepareStateReplacement: (e, t, k) => core.prepareStateReplacement(e, {
      isolateSource: e === t,
      restoreScripts: k.kind === "sim.load" || k.kind === "sim.rewind" || k.kind === "sim.import" || k.kind === "sim.init" && k.saveId !== undefined
    }),
    runTick: e => ({ tick: e.tickCount, flushRequested: core.tick(UCe) }),
    deltaSnapshots: false
  });
  sSe(host, {
    script: nme(core), getTimers: () => core.timers,
    requestPresentationFlush: () => core.requestPresentationFlush(),
    getTransmissionSystem: () => core.transmissionSystem,
    retireScript: (e, t) => core.retireScript(e, t),
    retireLibraryConsumers: (e, t, k) => core.retireLibraryConsumers(e, t, k),
    discardBufferedConsoleLines: e => core.discardBufferedConsoleLines(e)
  });
  return {
    core, host,
    command: (kind, payload = {}) => host.applyCommand({ v: 7, id: ++nextId, kind, payload }),
    control: (kind, extra = {}) => host.applyControl({ v: 7, id: ++nextId, kind, ...extra }),
    advance: () => host.advanceTick(),
    serialize: () => qpe(core.state),
    systemMs: __ctSystemMs,
    skipSystems: __ctSkipSystems,
    config: n,
  };
}
export { __ctCreateHeadless };
`;

// Per-system timing: v9(name, fn) wraps every system call in tCe.tick().
const V9_HEAD = "function v9(e, t) {\n  nH([`system`, e]);\n  try {\n    t();\n  }";
const V9_TIMED = "function v9(e, t) {\n  nH([`system`, e]);\n  try {\n    __ctTimedSystem(e, t);\n  }";


// Control Room panels draw into OffscreenCanvas, which Node lacks. A no-op
// canvas keeps panel scripts running; nothing is rendered.
function installCanvasStub() {
  if (globalThis.OffscreenCanvas) return;
  const noop = () => {};
  const gradient = { addColorStop: noop };
  const special = {
    measureText: text => ({ width: String(text).length * 6, actualBoundingBoxAscent: 8, actualBoundingBoxDescent: 2,
      fontBoundingBoxAscent: 8, fontBoundingBoxDescent: 2 }),
    getImageData: (x, y, w, h) => ({ width: w, height: h, data: new Uint8ClampedArray(Math.max(0, w * h * 4)) }),
    createImageData: (w, h) => ({ width: w, height: h, data: new Uint8ClampedArray(Math.max(0, w * h * 4)) }),
    createLinearGradient: () => gradient, createRadialGradient: () => gradient, createConicGradient: () => gradient,
    createPattern: () => ({}), getTransform: () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }),
    isPointInPath: () => false, isPointInStroke: () => false, getLineDash: () => [],
  };
  globalThis.OffscreenCanvas = class {
    constructor(width, height) { this.width = width; this.height = height; }
    getContext() {
      const props = { canvas: this };
      return new Proxy(props, {
        get: (t, k) => (k in t ? t[k] : k in special ? special[k] : noop),
        set: (t, k, v) => { t[k] = v; return true; },
      });
    }
    transferToImageBitmap() { return { width: this.width, height: this.height, close: noop }; }
    convertToBlob() { return Promise.resolve(new Blob()); }
  };
}

export async function loadSimModule(simworkerPath = process.env.CT_SIMWORKER || DEFAULT_SIMWORKER) {
  if (!existsSync(simworkerPath)) {
    throw new Error(`simworker not found: ${simworkerPath}\n` +
      "Init the private submodule: git -c submodule.internals.update=checkout submodule update --init internals");
  }
  const src = readFileSync(simworkerPath, "utf8");
  const hash = createHash("sha1").update(src).update(SHIM).update(String(SHIM_VERSION)).digest("hex").slice(0, 12);
  const cacheDir = join(HERE, ".cache");
  const out = join(cacheDir, `sim-${hash}.mjs`);
  if (!existsSync(out)) {
    if (!src.includes(V9_HEAD)) throw new Error("simworker changed: system wrapper v9() not found, update simhost.mjs");
    for (const name of ["var tCe = class", "function LB(", "function Kpe(", "function qpe(", "function sSe(", "function nme(", "var _Ce", "const UCe", "const mue"]) {
      if (!src.includes(name)) throw new Error(`simworker changed: '${name}' not found, update the shim in simhost.mjs`);
    }
    mkdirSync(cacheDir, { recursive: true });
    writeFileSync(out, src.replace(V9_HEAD, V9_TIMED) + "\n" + SHIM);
  }
  installCanvasStub();
  return import(pathToFileURL(out).href);
}

// Bookkeeping only; no script or production reads them.
export const DEFAULT_SKIP_SYSTEMS = ["AchievementSystem"];

// A script or library with the debug flag on makes the scheduler build a
// debug snapshot at every step boundary: measured 148 -> 60 ms per tick on a
// late save with 15 flagged sources. Tests don't attach a debugger.
function clearDebugFlags(state) {
  for (const group of [state.scripts, state.libraryScripts]) {
    for (const entry of Object.values(group ?? {})) entry.debug = false;
  }
}

// One simulation per process: the simworker keeps module-level state (event
// bus, i18n, panel buffers), so two Sims in one process can interfere.
export class Sim {
  // opts.skipSystems: names as tCe.tick() passes them to v9() (default
  // DEFAULT_SKIP_SYSTEMS); opts.keepDebug keeps per-script debug flags.
  static async create(opts = {}) {
    const mod = await loadSimModule(opts.simworker);
    const sim = new Sim(mod.__ctCreateHeadless(opts));
    for (const name of opts.skipSystems ?? DEFAULT_SKIP_SYSTEMS) sim.h.skipSystems.add(name);
    sim.keepDebug = !!opts.keepDebug;
    return sim;
  }

  constructor(h) {
    this.h = h;
    this.listeners = [];
    const sched = Object.getPrototypeOf(h.core.scriptScheduler);
    const sim = this;
    // Script console lines reach the UI only through the presentation path,
    // which the headless host skips; tap the scheduler's emitters instead.
    for (const [method, level] of [["emitScriptOutput", "info"], ["emitScriptWarn", "warn"],
      ["emitScriptDebug", "debug"], ["emitScriptConsoleError", "error"], ["emitScriptError", "crash"]]) {
      const orig = sched[method];
      if (!orig || orig.__ctTapped) continue;
      const tapped = function (scriptId, payload, ...rest) {
        const text = typeof payload === "string" ? payload : payload?.message ?? JSON.stringify(payload);
        for (const fn of sim.listeners) fn({ scriptId, level, text, tick: sim.state.tickCount });
        return orig.call(this, scriptId, payload, ...rest);
      };
      tapped.__ctTapped = true;
      sched[method] = tapped;
    }
  }

  get state() { return this.h.core.state; }
  get config() { return this.h.config; }
  onConsole(fn) { this.listeners.push(fn); }

  newGame(seed = 1) { return this.#ok(this.h.control("sim.new", { seed }), "sim.new"); }

  // Accepts the game's save_<id>.json text or object; running scripts resume.
  load(saveJson) {
    const save = typeof saveJson === "string" ? JSON.parse(saveJson) : structuredClone(saveJson);
    if (!this.keepDebug) clearDebugFlags(save.state ?? save);
    const bytes = JSON.stringify(save);
    return this.#ok(this.h.control("sim.load", { bytes, saveId: "headless" }), "sim.load");
  }

  serialize() { return this.h.serialize(); }

  // Puts `source` into a script slot (creating it if needed) and optionally runs it.
  setScript(scriptId, source, { run = true } = {}) {
    const exists = Object.prototype.hasOwnProperty.call(this.state.scripts, scriptId);
    const r = exists
      ? this.h.command("script.setSource", { scriptId, source })
      : this.h.command("script.create", { scriptId, name: scriptId, source });
    if (!r.ok || r.result?.ok === false) return { ok: false, status: r.error ?? r.result?.status ?? "set_failed" };
    if (!run) return { ok: true, status: "set" };
    if (this.state.scripts[scriptId]?.status === "running") this.h.command("script.stop", { scriptId });
    const run_ = this.h.command("script.run", { scriptId });
    return { ok: !!run_.result?.ok, status: run_.result?.status ?? run_.error };
  }

  tick(n = 1) {
    for (let i = 0; i < n; i++) {
      this.parker?.pass();
      this.h.advance();
    }
  }

  // Park passive machines' scripts (devtools/headless/passive.mjs).
  park(parker) { this.parker = parker; }

  terraformIndex() { return Number(this.state.researchRates?.terraform?.lastValue ?? 0); }

  systemMs() { return Object.fromEntries([...this.h.systemMs].sort((a, b) => b[1] - a[1])); }

  #ok(r, what) {
    if (!r.ok) throw new Error(`${what} failed: ${r.error ?? JSON.stringify(r)}`);
    return r;
  }
}
