// Scan every world seed (the game rolls floor(random * 2147483647), so 0..2147483646),
// keep the best K by a pluggable score. Pipeline per seed: recipes up to crowncap
// (early exit) -> crowncap load filter -> field -> grandbloom load -> score.
// Loads use the SUPPLY/DEMAND model exported by devtools/seed_quality.py (16-habitat feed
// peak), cached in .cache/seed_model.json; --regen rebuilds it (needs python).
//
//   node devtools/headless/seedscan.mjs [--from 0] [--to 2147483646] [--threads N] [--top 10000]
//        [--max-cc-load 0.8] [--score static] [--out FILE.jsonl] [--regen] [--verify]
//   --verify  compares recipes and loads with seed_quality.py for seeds 1-5000; first run
//             python devtools/seed_quality.py export --out devtools/headless/.cache/seed_model_check.json --recipes 1-5000
//
// Scores: static (default), route (from checkpoint h2), fresh (from a new game), reach /
// reach-script (run hours to the 25/25 build-out credits, current / value-density Harvester script). Add one: SCORES.name = ({ seed, grid, ccLoad, gbLoad, total, near }) => number
// (grid = Int8Array from fieldGrid, ITEMS indexes, -1 empty). A route model:
//   import { routeScore } from "./harvest_model.mjs"; SCORES.route = c => routeScore(c.grid);
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { availableParallelism } from "node:os";
import { parseArgs } from "node:util";
import { Worker, isMainThread, parentPort, workerData } from "node:worker_threads";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { ITEMS, fieldGrid, GRID_ROWS, GRID_COLS, GRID_START } from "./field.mjs";
import { routeScore, freshScore, freshReach } from "./harvest_model.mjs";
import { makePolicy, reachPossible } from "./harvest_policies.mjs";
import { recipeForms, makeRecipeState, N_FORMS, SPECIES_CROWNCAP, SPECIES_GRANDBLOOM } from "./recipes.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MODEL_FILE = path.join(HERE, ".cache", "seed_model.json");
const MAX_SEED = 2147483646, NEAR = 6, CHUNK = 1 << 20;

// Static score: value within NEAR sectors of the start, total value as tiebreak (< 1e6 total).
export const SCORES = {
  static: c => c.near + c.total * 1e-7,
  // Harvester credits by 0.2 h from checkpoint h2 (harvest_model.mjs, current script's route).
  route: c => routeScore(c.grid),
  // Harvester credits by 0.2 h from a new game (scripts from tick ~50, Scanner still mapping).
  fresh: c => freshScore(c.grid),
  // Minus run hours from a new game until the Harvester earned REACH_CREDITS (default: the
  // 25/25 build-out, 6 Solar + 3 Batteries + 13 O2 Generators = 16,900 cr, minus 2,500 uplink cr
  // and 4,150 cr of intro contracts: relay_hack 1,250, xenogenetics 1,400, corrupted_archive 1,500).
  // c.floor (worst score kept so far) caps the run, so hopeless fields stop early.
  // Route of scripts/0_cold_boot/harvesting/harvester.py (harvest_policies.mjs "hybrid").
  // Fields that can't make it by the cap even on an ideal route (reachPossible()) are skipped.
  reach: c => (reachPossible(c.grid, REACH_CREDITS, Math.min(1, -c.floor)) ? -freshReach(c.grid, REACH_CREDITS, -c.floor, HYBRID) : -1),
  // The same with vakermit's value-density script (harvest_model.mjs "script").
  "reach-script": c => -freshReach(c.grid, REACH_CREDITS, -c.floor),
};
const HYBRID = makePolicy("hybrid");
const REACH_CREDITS = 10250;

const VALUES = ITEMS.map(i => i.value);
const DIST = new Uint8Array(GRID_ROWS * GRID_COLS);
for (let r = 0; r < GRID_ROWS; r++) for (let c = 0; c < GRID_COLS; c++) DIST[r * GRID_COLS + c] = Math.abs(r - GRID_START[0]) + Math.abs(c - GRID_START[1]);

function loadModel(regen) {
  if (regen || !existsSync(MODEL_FILE)) {
    execFileSync("python", [path.join(HERE, "..", "seed_quality.py"), "export", "--out", MODEL_FILE], { stdio: "inherit" });
  }
  return JSON.parse(readFileSync(MODEL_FILE, "utf8"));
}

// Load of a fill = max over forms of (seeds/h the fill needs of the form) / supply.
function makeLoads(model) {
  const inv = Float64Array.from(model.supply, s => 1 / s);
  const dCC = model.demand.crowncap[SPECIES_CROWNCAP];
  const dGB = Float64Array.from(model.demand.grandbloom);
  const need = new Float64Array(N_FORMS);
  return {
    cc(r) {
      let m = 0;
      for (let k = 0; k < 3; k++) m = Math.max(m, dCC * inv[r[3 * SPECIES_CROWNCAP + k]]);
      return m;
    },
    gb(r) { // sums per form (a form can serve two GB species)
      need.fill(0);
      for (let s = 0; s <= SPECIES_GRANDBLOOM; s++) {
        if (!dGB[s]) continue;
        for (let k = 0; k < 3; k++) need[r[3 * s + k]] += dGB[s];
      }
      let m = 0;
      for (let f = 0; f < N_FORMS; f++) m = Math.max(m, need[f] * inv[f]);
      return m;
    },
  };
}

// Bounded min-heap on score (worst kept on top).
class TopK {
  constructor(k) { this.k = k; this.a = []; }
  get min() { return this.a.length < this.k ? -Infinity : this.a[0].score; }
  push(e) {
    const a = this.a;
    if (a.length < this.k) { a.push(e); this.up(a.length - 1); }
    else if (e.score > a[0].score) { a[0] = e; this.down(0); }
  }
  up(i) {
    const a = this.a;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (a[p].score <= a[i].score) break;
      [a[p], a[i]] = [a[i], a[p]]; i = p;
    }
  }
  down(i) {
    const a = this.a, n = a.length;
    for (;;) {
      let m = i;
      for (const c of [2 * i + 1, 2 * i + 2]) if (c < n && a[c].score < a[m].score) m = c;
      if (m === i) return;
      [a[m], a[i]] = [a[i], a[m]]; i = m;
    }
  }
}

function scanChunk(lo, hi, ctx) {
  const { loads, score, maxCc, top, rec, st, grid } = ctx;
  let passed = 0;
  for (let seed = lo; seed < hi; seed++) {
    recipeForms(seed, SPECIES_CROWNCAP + 1, rec, st);
    const ccLoad = loads.cc(rec);
    if (ccLoad > maxCc) continue;
    passed++;
    recipeForms(seed, SPECIES_GRANDBLOOM + 1, rec, st);
    const gbLoad = loads.gb(rec);
    fieldGrid(seed, grid);
    let total = 0, near = 0;
    for (let i = 0; i < grid.length; i++) {
      const g = grid[i];
      if (g < 0) continue;
      total += VALUES[g];
      if (DIST[i] <= NEAR) near += VALUES[g];
    }
    const s = score({ seed, grid, ccLoad, gbLoad, total, near, floor: top.min });
    if (s > top.min) top.push({ seed, cc_load: ccLoad, gb_load: gbLoad, total, near, score: s });
  }
  return passed;
}

function newCtx(o, model) {
  return {
    loads: makeLoads(model), score: SCORES[o.score], maxCc: o.maxCc, top: new TopK(o.top),
    rec: new Uint8Array(45), st: makeRecipeState(), grid: new Int8Array(GRID_ROWS * GRID_COLS),
  };
}

if (!isMainThread) {
  const { opts, model, counters } = workerData;
  const c = new Int32Array(counters); // [next chunk, seeds done, seeds passed]
  const ctx = newCtx(opts, model);
  for (;;) {
    const i = Atomics.add(c, 0, 1), lo = opts.from + i * CHUNK;
    if (lo > opts.to) break;
    const hi = Math.min(lo + CHUNK, opts.to + 1);
    const passed = scanChunk(lo, hi, ctx);
    Atomics.add(c, 1, hi - lo); Atomics.add(c, 2, passed);
  }
  parentPort.postMessage(ctx.top.a);
} else {
  main();
}

function verify() {
  const check = JSON.parse(readFileSync(path.join(HERE, ".cache", "seed_model_check.json"), "utf8"));
  const loads = makeLoads(check), rec = new Uint8Array(45), early = new Uint8Array(45), st = makeRecipeState();
  let bad = 0, n = 0, maxDiff = 0;
  for (const [seed, want] of Object.entries(check.recipes)) {
    recipeForms(Number(seed), 15, rec, st);
    n++;
    if (want.flat().some((f, i) => f !== rec[i])) { if (bad++ < 5) console.log("recipe mismatch", seed); }
    recipeForms(Number(seed), 10, early, st);
    if (early.subarray(0, 30).some((f, i) => f !== rec[i])) bad++;
    const wl = check.loads[seed];
    if (wl) maxDiff = Math.max(maxDiff, Math.abs(loads.cc(rec) - wl[0]), Math.abs(loads.gb(rec) - wl[1]));
  }
  recipeForms(1893323207, 15, rec, st);
  console.log(`seed 1893323207 crowncap: ${[...rec.subarray(27, 30)].map(i => check.forms[i]).join(", ")}`);
  console.log(`${n} seeds, ${bad} mismatches, max load diff ${maxDiff.toExponential(2)}`);
  process.exitCode = bad || maxDiff > 1e-9 ? 1 : 0;
}

async function main() {
  const { values: a } = parseArgs({ options: {
    from: { type: "string", default: "0" }, to: { type: "string", default: String(MAX_SEED) },
    threads: { type: "string" }, top: { type: "string", default: "10000" },
    "max-cc-load": { type: "string", default: "0.8" }, score: { type: "string", default: "static" },
    out: { type: "string" }, regen: { type: "boolean" }, verify: { type: "boolean" },
  } });
  if (a.verify) return verify();
  const model = loadModel(a.regen);
  if (!SCORES[a.score]) { console.error(`unknown --score ${a.score}; have ${Object.keys(SCORES)}`); process.exit(2); }
  const opts = { from: Number(a.from), to: Number(a.to), top: Number(a.top), maxCc: Number(a["max-cc-load"]), score: a.score };
  const threads = Number(a.threads ?? availableParallelism());
  const total = opts.to - opts.from + 1;
  const counters = new SharedArrayBuffer(12), c = new Int32Array(counters);
  const t0 = Date.now();
  const timer = setInterval(() => {
    const done = Atomics.load(c, 1), el = (Date.now() - t0) / 1000;
    console.error(`${(100 * done / total).toFixed(1)}%  ${(done / el / 1e6).toFixed(2)}M seeds/s  elapsed ${el.toFixed(0)}s  ETA ${((total - done) / (done / el)).toFixed(0)}s`);
  }, 10000);
  const parts = await Promise.all(Array.from({ length: threads }, () => new Promise((res, rej) => {
    const w = new Worker(fileURLToPath(import.meta.url), { workerData: { opts, model, counters } });
    w.on("message", res); w.on("error", rej);
  })));
  clearInterval(timer);
  const heap = new TopK(opts.top);
  for (const p of parts) for (const e of p) heap.push(e);
  const rows = heap.a.sort((x, y) => y.score - x.score);
  const el = (Date.now() - t0) / 1000;
  console.error(`done ${total} seeds in ${el.toFixed(1)}s (${(el * threads / total * 1e6).toFixed(2)} thread-us/seed); ${Atomics.load(c, 2)} passed cc-load <= ${opts.maxCc}`);
  if (a.out) {
    mkdirSync(path.dirname(path.resolve(a.out)), { recursive: true });
    writeFileSync(a.out, rows.map(r => JSON.stringify({ seed: r.seed, cc_load: r.cc_load, gb_load: r.gb_load, total: r.total, near: r.near, score: r.score })).join("\n") + "\n");
  } else {
    for (const r of rows.slice(0, 20)) console.log(JSON.stringify(r));
  }
}
