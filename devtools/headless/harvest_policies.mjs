// Harvester route policies for harvest_model.mjs, and a search that compares them on a
// random sample of fresh fields (docs/plans/scoring_map_seeds.md, "optimise the
// Harvester route"). Score: run minutes from a new game until the Harvester has earned
// the 25/25 build-out (10,250 cr), credits by 0.5 h as tiebreak.
//
//   node devtools/headless/harvest_policies.mjs --eval "rate;hybrid" [--sample 20000] [--from 1]   each vs "script"
//   node devtools/headless/harvest_policies.mjs --grid rate --set "lam0=0,20;k=0.5,1" [--sample N]
//   node devtools/headless/harvest_policies.mjs --seed N --policy rate [--route]
//   node devtools/headless/harvest_policies.mjs --check     "hybrid" vs headless runs of the script
//
// Policy names take parameters: "rate:lam0=20,k=0.8". "hybrid" is the current
// scripts/0_cold_boot/harvesting/harvester.py; the others are the search's steps.
// Results (20,000 fields): docs/plans/scoring_map_seeds.md, "Harvester route".
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import { simulate, freshGrid, POLICIES, MODEL, nextHop } from "./harvest_model.mjs";

const { CELLS, ROWS, COLS, BASE, VALUES, MOVE_TICKS, COLLECT_TICKS, HEAT_LIMIT, COST_ITEM, COST_EMPTY, ROW_OF, COL_OF } = MODEL;

const NEIGHBOURS = Array.from({ length: CELLS }, (_, i) => {
  const r = ROW_OF[i], c = COL_OF[i], out = [];
  if (r > 0) out.push(i - COLS);
  if (r < ROWS - 1) out.push(i + COLS);
  if (c > 0) out.push(i - 1);
  if (c < COLS - 1) out.push(i + 1);
  return out;
});

// Planned heat of a move onto q: item cells (also ones the policy leaves lying) and the
// base pad +1, everything else +7.
const moveHeat = (v, q) => (q === BASE || v[q] >= 0 ? COST_ITEM : COST_EMPTY);

// Single-source Dijkstra over the grid, edge cost into q = MOVE_TICKS + lam x heat(q).
// Binary heap of (dist, cell) with lazy deletion.
const HEAP_D = new Float64Array(CELLS * 4), HEAP_C = new Int16Array(CELLS * 4);
function shortest(v, pos, lam, dist, prev, done) {
  dist.fill(Infinity); prev.fill(-1); done.fill(0);
  dist[pos] = 0;
  let n = 0;
  const push = (d, c) => {
    let i = n++;
    while (i > 0) { const p = (i - 1) >> 1; if (HEAP_D[p] <= d) break; HEAP_D[i] = HEAP_D[p]; HEAP_C[i] = HEAP_C[p]; i = p; }
    HEAP_D[i] = d; HEAP_C[i] = c;
  };
  push(0, pos);
  while (n > 0) {
    const du = HEAP_D[0], u = HEAP_C[0];
    const ld = HEAP_D[--n], lc = HEAP_C[n];
    let i = 0;
    for (;;) {
      let m = 2 * i + 1;
      if (m >= n) break;
      if (m + 1 < n && HEAP_D[m + 1] < HEAP_D[m]) m++;
      if (HEAP_D[m] >= ld) break;
      HEAP_D[i] = HEAP_D[m]; HEAP_C[i] = HEAP_C[m]; i = m;
    }
    HEAP_D[i] = ld; HEAP_C[i] = lc;
    if (done[u]) continue;
    done[u] = 1;
    for (const q of NEIGHBOURS[u]) {
      const d = du + MOVE_TICKS + lam * moveHeat(v, q);
      if (d < dist[q]) { dist[q] = d; prev[q] = u; push(d, q); }
    }
  }
}

// "rate": credits per tick. Target = the item with the best value / (route ticks +
// collect), routes by heat-priced Dijkstra (lam ticks per heat unit, lam0 at heat 0 up
// to lam1 at the limit: early on time is the limit, later the rests). An item the
// Harvester stands on is collected only if worth k x (63 ticks at the best target's
// rate); else it is driven over and stays as a +1 stepping stone. overhead: planning
// ticks per hop in the game script.
function ratePolicy({ lam0 = 0, lam1 = 83, k = 1, overhead = 0, look = 0 } = {}) {
  const dist = new Float64Array(CELLS), prev = new Int16Array(CELLS), done = new Uint8Array(CELLS);
  let keyT = -1, keyPos = -1, best = -1, bestRate = 0;
  function plan(v, pos, ctx) {
    if (ctx.t === keyT && pos === keyPos) return;
    keyT = ctx.t; keyPos = pos;
    const lam = lam0 + (lam1 - lam0) * Math.min(1, ctx.heat / HEAT_LIMIT);
    shortest(v, pos, lam, dist, prev, done);
    best = -1; bestRate = 0;
    for (let q = 0; q < CELLS; q++) {
      const it = v[q];
      if (it < 0 || q === pos) continue;
      let val = VALUES[it];
      if (look) { // neighbours' value as a cluster bonus
        for (const n of NEIGHBOURS[q]) if (n !== pos && v[n] >= 0) val += look * VALUES[v[n]];
      }
      const rate = val / (dist[q] + COLLECT_TICKS);
      if (rate > bestRate) { bestRate = rate; best = q; }
    }
  }
  return {
    collect(v, pos, it, ctx) {
      plan(v, pos, ctx);
      return best < 0 || VALUES[it] >= k * COLLECT_TICKS * bestRate;
    },
    choose(v, pos, clearing, ctx) { plan(v, pos, ctx); return best; },
    hop(v, pos, tgt) {
      let q = tgt;
      while (prev[q] !== pos) q = prev[q];
      return q;
    },
    hopOverhead: overhead ? () => overhead : undefined,
    reset() { keyT = -1; keyPos = -1; },
  };
}

// Monotone routes: cheapest path from pos to every cell using only steps toward it
// (no detours), by DP outward from pos per quadrant. Ties: the row step first.
// Same dist/prev contract as shortest(); ~4x cheaper in the game interpreter.
function monotone(v, pos, lam, dist, prev) {
  const pr = ROW_OF[pos], pc = COL_OF[pos], ci = MOVE_TICKS + lam * COST_ITEM, ce = MOVE_TICKS + lam * COST_EMPTY;
  dist[pos] = 0; prev[pos] = -1;
  for (const sr of [-1, 1]) for (const sc of [-1, 1]) {
    for (let r = pr; r >= 0 && r < ROWS; r += sr) for (let c = pc; c >= 0 && c < COLS; c += sc) {
      const q = r * COLS + c;
      if (q === pos) continue;
      const cost = q === BASE || v[q] >= 0 ? ci : ce;
      const a = r !== pr ? q - sr * COLS : -1, b = c !== pc ? q - sc : -1;
      const p = a < 0 ? b : b < 0 ? a : dist[a] <= dist[b] ? a : b;
      dist[q] = dist[p] + cost; prev[q] = p;
    }
  }
}

// "pair": like "rate", but rates the first target by the best two-item trip from it,
// (v1 + v2) / (T1 + T2), over the m best single-item targets.
// hybrid = e > 0: the second leg by Manhattan distance x (MOVE_TICKS + lam x e), so only one route search per hop.
// mono: monotone routes (monotone()) instead of the route search.
function pairPolicy({ lam0 = 20, lam1 = 100, k = 0.5, m = 6, e = 0, mono = 0, overhead = 0 } = {}) {
  const dist = new Float64Array(CELLS), prev = new Int16Array(CELLS), done = new Uint8Array(CELLS);
  const d2 = new Float64Array(CELLS), p2 = new Int16Array(CELLS), dn2 = new Uint8Array(CELLS);
  const candQ = new Int16Array(m), candR = new Float64Array(m);
  let keyT = -1, keyPos = -1, best = -1, bestRate = 0;
  function plan(v, pos, ctx) {
    if (ctx.t === keyT && pos === keyPos) return;
    keyT = ctx.t; keyPos = pos;
    const lam = Math.floor(lam0 + (lam1 - lam0) * Math.min(1, ctx.heat / HEAT_LIMIT) + 0.5); // script: int(x + 0.5)
    if (mono) monotone(v, pos, lam, dist, prev); else shortest(v, pos, lam, dist, prev, done);
    let nc = 0;
    candR.fill(-1);
    for (let q = 0; q < CELLS; q++) {
      const it = v[q];
      if (it < 0 || q === pos) continue;
      const rate = VALUES[it] / (dist[q] + COLLECT_TICKS);
      if (nc < m || rate > candR[nc - 1]) { // insertion into the sorted top m
        let i = Math.min(nc, m - 1);
        while (i > 0 && candR[i - 1] < rate) { candR[i] = candR[i - 1]; candQ[i] = candQ[i - 1]; i--; }
        candR[i] = rate; candQ[i] = q;
        if (nc < m) nc++;
      }
    }
    best = nc ? candQ[0] : -1; bestRate = nc ? candR[0] : 0;
    let bestPair = -1;
    for (let c = 0; c < nc; c++) {
      const q1 = candQ[c], t1 = dist[q1] + COLLECT_TICKS, v1 = VALUES[v[q1]];
      if (e) {
        const hopT = MOVE_TICKS + lam * e, r1 = ROW_OF[q1], c1 = COL_OF[q1];
        for (let q = 0; q < CELLS; q++) d2[q] = (Math.abs(ROW_OF[q] - r1) + Math.abs(COL_OF[q] - c1)) * hopT;
      } else shortest(v, q1, lam, d2, p2, dn2);
      let r = v1 / t1;
      for (let q = 0; q < CELLS; q++) {
        if (v[q] < 0 || q === pos || q === q1) continue;
        const rr = (v1 + VALUES[v[q]]) / (t1 + d2[q] + COLLECT_TICKS);
        if (rr > r) r = rr;
      }
      if (r > bestPair) { bestPair = r; best = q1; }
    }
  }
  return {
    collect(v, pos, it, ctx) {
      plan(v, pos, ctx);
      return best < 0 || VALUES[it] >= k * COLLECT_TICKS * bestRate;
    },
    choose(v, pos, clearing, ctx) { plan(v, pos, ctx); return best; },
    hop(v, pos, tgt) {
      let q = tgt;
      while (prev[q] !== pos) q = prev[q];
      return q;
    },
    hopOverhead: overhead ? () => overhead : undefined,
    reset() { keyT = -1; keyPos = -1; },
  };
}

// "lite": "pair" on Manhattan distances, cheap enough for the game script (no route
// search, O(m x items) per hop). A trip of d hops costs d x (MOVE_TICKS + lam x e) ticks,
// e = expected heat per hop; hops by the script's axis rule (an item cell first).
// m = 0: single-item rate only.
function litePolicy({ lam0 = 20, lam1 = 100, k = 0.5, e = 4, m = 3, overhead = 0 } = {}) {
  const candQ = new Int16Array(Math.max(1, m)), candR = new Float64Array(Math.max(1, m));
  let keyT = -1, keyPos = -1, best = -1, bestRate = 0;
  const items = new Int16Array(CELLS);
  function plan(v, pos, ctx) {
    if (ctx.t === keyT && pos === keyPos) return;
    keyT = ctx.t; keyPos = pos;
    const lam = lam0 + (lam1 - lam0) * Math.min(1, ctx.heat / HEAT_LIMIT);
    const hopT = MOVE_TICKS + lam * e;
    const pr = ROW_OF[pos], pc = COL_OF[pos];
    let n = 0, nc = 0;
    const mm = Math.max(1, m);
    candR.fill(-1);
    for (let q = 0; q < CELLS; q++) {
      if (v[q] < 0 || q === pos) continue;
      items[n++] = q;
      const d = Math.abs(ROW_OF[q] - pr) + Math.abs(COL_OF[q] - pc);
      const rate = VALUES[v[q]] / (d * hopT + COLLECT_TICKS);
      if (nc < mm || rate > candR[nc - 1]) {
        let i = Math.min(nc, mm - 1);
        while (i > 0 && candR[i - 1] < rate) { candR[i] = candR[i - 1]; candQ[i] = candQ[i - 1]; i--; }
        candR[i] = rate; candQ[i] = q;
        if (nc < mm) nc++;
      }
    }
    best = nc ? candQ[0] : -1; bestRate = nc ? candR[0] : 0;
    if (!m) return;
    let bestPair = -1;
    for (let c = 0; c < nc; c++) {
      const q1 = candQ[c], v1 = VALUES[v[q1]], r1 = ROW_OF[q1], c1 = COL_OF[q1];
      const t1 = (Math.abs(r1 - pr) + Math.abs(c1 - pc)) * hopT + COLLECT_TICKS;
      let r = v1 / t1;
      for (let j = 0; j < n; j++) {
        const q = items[j];
        if (q === q1) continue;
        const rr = (v1 + VALUES[v[q]]) / (t1 + (Math.abs(ROW_OF[q] - r1) + Math.abs(COL_OF[q] - c1)) * hopT + COLLECT_TICKS);
        if (rr > r) r = rr;
      }
      if (r > bestPair) { bestPair = r; best = q1; }
    }
  }
  return {
    collect(v, pos, it, ctx) {
      plan(v, pos, ctx);
      return best < 0 || VALUES[it] >= k * COLLECT_TICKS * bestRate;
    },
    choose(v, pos, clearing, ctx) { plan(v, pos, ctx); return best; },
    hop: nextHop,
    hopOverhead: overhead ? () => overhead : undefined,
    reset() { keyT = -1; keyPos = -1; },
  };
}

// "hybrid": the policy of scripts/0_cold_boot/harvesting/harvester.py: "pair" with
// monotone routes, Manhattan second leg, and the script's planning time per decision
// (planOverhead): one tick per map() callback (route rows in ROUTE_ROWS chunks, the
// ranking, pair candidates in PAIR_WORK chunks) plus p0 + p1 x items of direct work.
const ROUTE_ROWS = 3, PAIR_WORK = 150;
function hybridPolicy({ lam0 = 20, lam1 = 100, k = 0.5, m = 6, e = 4, p0 = -1, p1 = 0, wait = 10 } = {}) {
  // Arrived on the target: collect it without planning.
  const pol = pairPolicy({ lam0, lam1, k, m, e, mono: 1 });
  const { collect, choose } = pol;
  let target = -1;
  pol.collect = (v, pos, it, ctx) => pos === target || collect(v, pos, it, ctx);
  pol.choose = (v, pos, clearing, ctx) => (target = choose(v, pos, clearing, ctx));
  const { reset } = pol;
  pol.reset = () => { reset(); target = -1; };
  pol.scanWait = wait;
  pol.planOverhead = (v, pos, ctx) => {
    if (pos === target && v[pos] >= 0) return 0;
    const n = ctx.left - (v[pos] >= 0 ? 1 : 0);
    if (n <= 0) return p0;
    const pr = ROW_OF[pos];
    const routes = Math.ceil((pr + 1) / ROUTE_ROWS) + Math.ceil((ROWS - 1 - pr) / ROUTE_ROWS);
    return routes + 1 + Math.ceil(Math.min(m, n) / Math.max(1, Math.floor(PAIR_WORK / n))) + p0 + p1 * n;
  };
  return pol;
}

// Admissible pruning for seed scans: false if no route of the hybrid policy can earn
// `credits` within capHours run hours. A set S of items needs at least max(farthest
// distance, |S|) moves and |S| collects after the first move, so the bound is the best
// value of such an S. Timings are the hybrid model's minimums: first move after tick
// BOUND_START (first scanner poll with 10 sectors known), a move >= BOUND_MOVE ticks
// (125 + loop overhead + the >= 4 planning callbacks), a collect >= BOUND_COLLECT.
const BOUND_START = 94, BOUND_MOVE = 130, BOUND_COLLECT = 64;
const START_DIST = Uint8Array.from({ length: CELLS }, (_, i) => Math.abs(ROW_OF[i] - ROW_OF[BASE]) + Math.abs(COL_OF[i] - COL_OF[BASE]));
const BY_DIST = Int16Array.from({ length: CELLS }, (_, i) => i).sort((a, b) => START_DIST[a] - START_DIST[b] || a - b);
const BOUND_VALS = new Int32Array(CELLS);
export function reachPossible(grid, credits, capHours) {
  const budget = capHours * MODEL.TICKS_PER_RUN_HOUR - BOUND_START;
  let n = 0;
  for (let j = 0; j < CELLS; j++) {
    const q = BY_DIST[j];
    if (grid[q] >= 0) {
      const v = VALUES[grid[q]]; // insert, kept sorted high to low
      let i = n++;
      while (i > 0 && BOUND_VALS[i - 1] < v) { BOUND_VALS[i] = BOUND_VALS[i - 1]; i--; }
      BOUND_VALS[i] = v;
    }
    const d = START_DIST[q];
    if (j + 1 < CELLS && START_DIST[BY_DIST[j + 1]] === d) continue; // end of a distance ring
    if (BOUND_MOVE * d + BOUND_COLLECT > budget) return false;
    let sum = 0;
    for (let c = 1; c <= n; c++) {
      if (BOUND_MOVE * Math.max(d, c) + BOUND_COLLECT * c > budget) break;
      sum += BOUND_VALS[c - 1];
      if (sum >= credits) return true;
    }
  }
  return false;
}

export const FACTORIES = {
  hybrid: hybridPolicy,
  lite: litePolicy,
  script: () => POLICIES.script,
  rate: ratePolicy,
  pair: pairPolicy,
};

// "rate:lam0=20,k=0.8" -> policy object
export function makePolicy(spec) {
  const [name, args = ""] = spec.split(":");
  const params = Object.fromEntries(args.split(",").filter(Boolean).map(kv => { const [k, x] = kv.split("="); return [k, Number(x)]; }));
  if (!FACTORIES[name]) throw new Error(`unknown policy ${name}; have ${Object.keys(FACTORIES)}`);
  return FACTORIES[name](params);
}

// Same PRNG as the game's field (mp), for a reproducible random seed sample.
function sampleSeeds(n, from) {
  let t = from | 0;
  const out = new Array(n);
  for (let i = 0; i < n; i++) {
    t = (t + 1831565813) | 0;
    let e = Math.imul(t ^ (t >>> 15), t | 1);
    e = (e + Math.imul(e ^ (e >>> 7), e | 61)) ^ e;
    out[i] = ((e ^ (e >>> 14)) >>> 0) % 2147483647;
  }
  return out;
}

const TARGET = 10250;
const quant = (xs, p) => xs[Math.floor(p * (xs.length - 1))];

// -> {reach: minutes per field (60 if never), late: credits by 0.5 h per field}
export function evaluate(policy, seeds) {
  const grid = new Int8Array(CELLS), reach = new Float64Array(seeds.length), late = new Float64Array(seeds.length);
  const opts = { mode: "fresh", policy, hours: [0.5], targets: [TARGET] };
  seeds.forEach((seed, i) => {
    const r = simulate(freshGrid(seed, grid), opts);
    reach[i] = 60 * (r.reachedAt[TARGET] ?? 1);
    late[i] = r.creditsAt[0.5];
  });
  return { reach, late };
}

function summary(name, res, base) {
  const r = [...res.reach].sort((a, b) => a - b), l = [...res.late].sort((a, b) => a - b);
  const mean = xs => xs.reduce((a, b) => a + b, 0) / xs.length;
  let line = `${name.padEnd(40)} reach min mean ${mean(r).toFixed(2)} p10 ${quant(r, 0.1).toFixed(1)} med ${quant(r, 0.5).toFixed(1)} p90 ${quant(r, 0.9).toFixed(1)}`
    + ` | cr@0.5h mean ${mean(l).toFixed(0)} med ${quant(l, 0.5)}`;
  if (base) {
    let win = 0, lose = 0;
    for (let i = 0; i < r.length; i++) { const d = res.reach[i] - base.reach[i]; if (d < -0.05) win++; else if (d > 0.05) lose++; }
    line += ` | faster ${win} slower ${lose}`;
  }
  return { line, score: mean(r) - 1e-6 * mean(l) };
}

// Fresh headless games with the current script (run.mjs --seed N --deploy-templates
// scripts/0_cold_boot --hours 0.5, 2026-10-06): [seed, tick of 10,250 cr (null: not
// by 0.5 h), credits by 0.1 / 0.2 / 0.5 h]. The model matched the route collect for
// collect on 29 of 30; seed 12412 splits at the 2nd collect (scan-phase tie).
export const HYBRID_CALIBRATION = [
  [1, 3465, 11575, 18000, 23450], [2, 6540, 4025, 11150, 14875], [3, 6097, 6875, 11050, 16800],
  [4, 3757, 9800, 15450, 32750], [5, 14702, 2600, 6925, 11050], [6, 5685, 5850, 16250, 20425],
  [7, 3896, 10000, 14600, 24200], [8, 7316, 5675, 9900, 13500], [9, 8495, 4925, 7825, 20200],
  [10, 8834, 4925, 8675, 17075], [11, 7567, 7625, 8825, 16375], [12, null, 4850, 5900, 9550],
  [13, 5031, 8400, 12125, 22575], [42, 7764, 4175, 7475, 14875], [777, 8057, 6375, 9650, 16300],
  [2024, 10809, 4750, 6850, 11100], [3498, 3442, 11825, 17900, 35875], [5000, 5678, 4675, 13125, 19575],
  [7416, 4564, 7950, 13350, 21225], [9999, 4788, 8475, 12600, 19725], [12412, 3593, 10875, 15975, 34900],
  [15000, 7236, 7625, 10175, 15925], [158871, 5924, 5675, 10900, 22550], [307438010, 2269, 17850, 21200, 32550],
  [311671524, 2670, 15575, 21500, 29675], [420526420, 7546, 4275, 10200, 16425], [1028454550, 2187, 16625, 26150, 36925],
  [1119519681, 2106, 17425, 23150, 25600], [1789002546, 6358, 5775, 10750, 24450], [2014851714, 2697, 15250, 23600, 37275],
];

function check() {
  const policy = makePolicy("hybrid"), hs = [0.1, 0.2, 0.5];
  let dReach = 0, nReach = 0;
  const err = hs.map(() => 0);
  console.log("seed".padEnd(12) + "reach min sim/model".padStart(20) + hs.map(h => `cr ${h} h sim/model`.padStart(22)).join(""));
  for (const [seed, reach, ...cr] of HYBRID_CALIBRATION) {
    const r = simulate(freshGrid(seed), { mode: "fresh", policy, hours: hs, targets: [TARGET] });
    const mr = r.reachedAt[TARGET];
    if (reach !== null && mr !== null) { dReach += 60 * mr - reach / 600; nReach++; }
    hs.forEach((h, i) => { err[i] += Math.abs(r.creditsAt[h] - cr[i]) / cr[i]; });
    console.log(String(seed).padEnd(12) + `${reach === null ? "-" : (reach / 600).toFixed(2)} / ${mr === null ? "-" : (60 * mr).toFixed(2)}`.padStart(20)
      + hs.map((h, i) => `${cr[i]} / ${r.creditsAt[h]}`.padStart(22)).join(""));
  }
  console.log(`mean reach error ${(dReach / nReach).toFixed(3)} min; mean |credit error| ${hs.map((h, i) => `${h} h ${(100 * err[i] / HYBRID_CALIBRATION.length).toFixed(1)} %`).join(", ")}`);
}

function main() {
  const { values: a } = parseArgs({ options: {
    eval: { type: "string" }, grid: { type: "string" }, set: { type: "string" }, sample: { type: "string", default: "20000" },
    from: { type: "string", default: "1" }, seed: { type: "string" }, policy: { type: "string", default: "script" }, route: { type: "boolean" },
    check: { type: "boolean" },
  } });
  if (a.check) return check();
  if (a.seed) {
    const r = simulate(freshGrid(Number(a.seed)), { mode: "fresh", policy: makePolicy(a.policy), hours: [0.5], targets: [TARGET], route: !!a.route });
    if (r.route) for (const c of r.route) console.log(`${String(c.tick).padStart(6)} ${c.sector.padEnd(4)} ${c.item.padEnd(17)}${String(c.value).padStart(5)} heat ${c.heat}`);
    const { route, rests, ...rest } = r;
    console.log(JSON.stringify(rest));
    return;
  }
  const seeds = sampleSeeds(Number(a.sample), Number(a.from));
  const base = evaluate(POLICIES.script, seeds);
  console.log(summary("script", base).line);
  let specs = [];
  if (a.eval) specs = a.eval.split(";").filter(s => s !== "script");
  if (a.grid) {
    const axes = a.set.split(";").map(part => { const [k, xs] = part.split("="); return xs.split(",").map(x => `${k}=${x}`); });
    specs = axes.reduce((acc, ax) => acc.flatMap(p => ax.map(x => [...p, x])), [[]]).map(p => `${a.grid}:${p.join(",")}`);
  }
  const rows = [];
  for (const spec of specs) {
    const t0 = performance.now();
    const s = summary(spec, evaluate(makePolicy(spec), seeds), base);
    rows.push(s);
    console.log(`${s.line} (${((performance.now() - t0) / 1000).toFixed(1)} s)`);
  }
  if (rows.length > 1) console.log("best: " + rows.sort((x, y) => x.score - y.score)[0].line);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
