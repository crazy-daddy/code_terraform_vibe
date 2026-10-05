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
const SHIM_VERSION = 5;

// The shim reaches the simulation through minified names (core class, SimHost,
// state load/serialize, command registry, ...) that change with every game
// build. findBootstrapNames() reads them from the worker bootstrap (the
// function that builds `new <Core>(<newState>(seed))` and the SimHost), anchored
// on strings that survive a rebuild: `en`, initialState:, `SimHost readTick`,
// serializeState:, produceSnapshot:, validateReplacementSnapshot:, script:,
// .game.tickRate. A required name that is not found stops the load.
const BOOTSTRAP_PATTERNS = {
  i18n: [/\.i18nReady\) \{\s*(\w+)\((\w+), `en`\);/, ["setLang", "langTable"]],
  core: [/let (\w+) = new (\w+)\((\w+)\(\w+\.seed\)\);\s*let (\w+) = new (\w+)\(\{\s*initialState: \1\.state/, [null, "Core", "newState", null, "SimHost"]],
  load: [/let (\w+) = (\w+)\(e\);\s*\w+\(\1\.tickCount, `SimHost readTick`\)/, [null, "loadState"]],
  serialize: [/serializeState: (\w+),/, ["serializeState"]],
  snapshot: [/produceSnapshot: (\w+),/, ["produceSnapshot"]],
  validate: [/validateReplacementSnapshot: \(e, t\) => (\w+)\(e, t\)/, ["validateSnapshot"]],
  registry: [/(\w+)\(\w+, \{\s*script: (\w+)\(\w+\),\s*getTimers:/, ["registerCommands", "scriptCommands"]],
  dt: [/const (\w+) = 1 \/ (\w+)\.game\.tickRate;/, ["tickDt", "config"]],
};

export function findBootstrapNames(src) {
  const names = {};
  const missing = [];
  for (const [key, [re, slots]] of Object.entries(BOOTSTRAP_PATTERNS)) {
    const m = re.exec(src);
    if (!m) { missing.push(key); continue; }
    slots.forEach((slot, i) => { if (slot) names[slot] = m[i + 1]; });
  }
  return { names, missing };
}

function shimSource(N) {
  return String.raw`
const __ctSystemMs = new Map();
const __ctSkipSystems = new Set();
let __ctStickyFluids = false;
const __ctLastFluids = new Map();
// An emptied tank also loses its per-fluid port keys, so the "*_capacity"
// key list is kept together with the fluid types.
function __ctStickyFluid(id, caps, fluids) {
  if (fluids !== "[null,null,null]") __ctLastFluids.set(id, [caps, fluids]);
  return __ctLastFluids.get(id) ?? [caps, fluids];
}
function __ctTimedSystem(name, fn) {
  if (__ctSkipSystems.has(name)) return;
  const t0 = performance.now();
  try { fn(); } finally {
    __ctSystemMs.set(name, (__ctSystemMs.get(name) ?? 0) + performance.now() - t0);
  }
}
function __ctCreateHeadless(opts = {}) {
  ${N.setLang}(${N.langTable}, ${"`en`"});
  const core = new ${N.Core}(${N.newState}(opts.seed ?? 1));
  let nextId = 0;
  const host = new ${N.SimHost}({
    initialState: core.state, initialStateInstalled: false, devModeEnabled: false,
    createNewState: e => ${N.newState}(e),
    loadState: e => ${N.loadState}(e),
    serializeState: ${N.serializeState}, produceSnapshot: ${N.produceSnapshot},
    validateReplacementSnapshot: (e, t) => ${N.validateSnapshot}(e, t),
    readTick: e => e.tickCount,
    prepareStateReplacement: (e, t, k) => core.prepareStateReplacement(e, {
      isolateSource: e === t,
      restoreScripts: k.kind === "sim.load" || k.kind === "sim.rewind" || k.kind === "sim.import" || k.kind === "sim.init" && k.saveId !== undefined
    }),
    runTick: e => ({ tick: e.tickCount, flushRequested: core.tick(${N.tickDt}) }),
    deltaSnapshots: false
  });
  ${N.registerCommands}(host, {
    script: ${N.scriptCommands}(core), getTimers: () => core.timers,
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
    serialize: () => ${N.serializeState}(core.state),
    systemMs: __ctSystemMs,
    skipSystems: __ctSkipSystems,
    setStickyFluids: v => { __ctStickyFluids = !!v; },
    config: ${N.config},
  };
}
export { __ctCreateHeadless };
`;
}

// Optional patches: a mismatch only loses the feature, with a warning.
//
// Per-system timing (and --skip-systems): the wrapper tCe.tick() runs every
// system through, function <name>(e, t) { <trace>([`system`, e]); try { t(); } ...
const SYSTEM_WRAPPER = /(function \w+\(e, t\) \{\n\s*\w+\(\[`system`, e\]\);\n\s*try \{\n\s*)t\(\);/g;
//
// Sticky fluids: the fluid-network cache signature (gx()) pushes one line per
// machine, `m:${id}:...:${caps}:${io}:${fluids}:${levels}:${content}`. A tank
// that runs empty every tick flips caps/fluids/levels/content and forces a
// full network rebuild twice per tick. With sticky fluids on, an empty machine
// keeps its last caps + fluid types and the content flags are left out, so the
// cached analysis stays.
const SIGNATURE_PUSH = /^( *)\w+\.push\(`m:\$\{(\w+)\.id\}.*`\);$/gm;

function patchSignature(src) {
  // Other systems push similar `m:` lines; keep the one whose last fields are
  // the caps / io / fluids / levels / content variables declared just above.
  const found = [];
  for (const m of src.matchAll(SIGNATURE_PUSH)) {
    const [line, indent, machine] = m;
    const vars = [...line.matchAll(/\$\{(\w+)\}/g)].map(v => v[1]);
    if (vars.length < 5) continue;
    const [caps, , fluids, levels, content] = vars.slice(-5);
    const before = src.slice(Math.max(0, m.index - 1500), m.index);
    const declares = (v, needle) => new RegExp(`let ${v} = [^\\n]*${needle}`).test(before);
    if (declares(caps, "_capacity") && declares(fluids, "stringData\\?\\.fluid") && declares(levels, "_in_level") && declares(content, "1e-9")) {
      found.push({ at: m.index, indent, machine, caps, fluids, levels, content });
    }
  }
  if (found.length !== 1) return { src, why: `fluid signature line found ${found.length}x (want 1)` };
  const { at, indent, machine, caps, fluids, levels, content } = found[0];
  const guard = `${indent}if (__ctStickyFluids) {\n${indent}  [${caps}, ${fluids}] = __ctStickyFluid(${machine}.id, ${caps}, ${fluids});\n` +
    `${indent}  ${levels} = \`\`;\n${indent}  ${content} = \`\`;\n${indent}}\n`;
  return { src: src.slice(0, at) + guard + src.slice(at) };
}

export function patchSimworker(src) {
  const warnings = [];
  const features = { systemTiming: false, stickyFluids: false };
  const { names, missing } = findBootstrapNames(src);
  if (missing.length) {
    throw new Error(`simworker changed: bootstrap pattern(s) not found: ${missing.join(", ")}. ` +
      "Update BOOTSTRAP_PATTERNS in devtools/headless/simhost.mjs against the worker bootstrap (search `SimHost readTick`).");
  }
  const wrappers = src.match(SYSTEM_WRAPPER) ?? [];
  if (wrappers.length === 1) {
    src = src.replace(SYSTEM_WRAPPER, "$1__ctTimedSystem(e, t);");
    features.systemTiming = true;
  } else {
    warnings.push(`system wrapper found ${wrappers.length}x (want 1): per-system timing and --skip-systems are off`);
  }
  const sticky = patchSignature(src);
  if (sticky.why) {
    warnings.push(`${sticky.why}: --sticky-fluids is off`);
  } else {
    src = sticky.src;
    features.stickyFluids = true;
  }
  return { src: src + "\n" + shimSource(names) + `export const __ctFeatures = ${JSON.stringify(features)};\n`, names, warnings, features };
}

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
  const raw = readFileSync(simworkerPath, "utf8");
  const patched = patchSimworker(raw);
  for (const w of patched.warnings) console.warn(`[headless] simworker changed: ${w}. Update simhost.mjs.`);
  const hash = createHash("sha1").update(patched.src).update(String(SHIM_VERSION)).digest("hex").slice(0, 12);
  const cacheDir = join(HERE, ".cache");
  const out = join(cacheDir, `sim-${hash}.mjs`);
  if (!existsSync(out)) {
    mkdirSync(cacheDir, { recursive: true });
    writeFileSync(out, patched.src);
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
  // DEFAULT_SKIP_SYSTEMS); opts.keepDebug keeps per-script debug flags;
  // opts.stickyFluids: see patchSignature().
  static async create(opts = {}) {
    const mod = await loadSimModule(opts.simworker);
    const sim = new Sim(mod.__ctCreateHeadless(opts));
    sim.features = mod.__ctFeatures;
    if (opts.stickyFluids && !sim.features.stickyFluids) console.warn("[headless] --sticky-fluids requested but unavailable on this simworker build; running without it.");
    const skip = opts.skipSystems ?? DEFAULT_SKIP_SYSTEMS;
    if (skip.length && !sim.features.systemTiming) console.warn(`[headless] cannot skip systems (${skip.join(", ")}) on this simworker build; they run.`);
    for (const name of skip) sim.h.skipSystems.add(name);
    sim.keepDebug = !!opts.keepDebug;
    sim.h.setStickyFluids(opts.stickyFluids);
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
      if (!orig) {
        console.warn(`[headless] simworker changed: scheduler.${method} not found; ${level} console lines are not captured. Update simhost.mjs.`);
        continue;
      }
      if (orig.__ctTapped) continue;
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
