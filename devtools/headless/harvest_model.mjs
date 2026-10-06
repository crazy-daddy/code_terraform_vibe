// Offline model of the early-game Harvester collecting the surface field, for
// scoring world seeds by early Harvester income (docs/plans/scoring_map_seeds.md
// part 1) and, later, searching a better route policy. Microseconds per field
// instead of seconds per headless sim.
//
//   node devtools/headless/harvest_model.mjs --seed 12412 [--route]   one field
//   node devtools/headless/harvest_model.mjs --check                  model vs headless sims (both modes)
//   --fresh: start from a new game (FRESH) instead of checkpoint h2 (CHECKPOINT_H2)
//   node devtools/headless/harvest_model.mjs --seeds 1-20000 [--top N] stats over seeds
//   node devtools/headless/harvest_model.mjs --compare DIR --seed N   route vs a run.mjs --out DIR
//
// Mechanics (simworker harvesting config and Harvester API, docs/components/harvester.md):
// move 0.5 world h = 125 ticks, heat +1 onto an item cell / +7 onto an empty one,
// added when the move starts, refused if it would pass 100 (the base pad
// counts as an item cell, but the script plans it as empty); collect 0.25 h = 63
// ticks, no heat on an item cell; cooling 3 heat per world hour (250 ticks), also
// while moving. store() works anywhere and the script sells at once, so credits
// land at the collect. Times are in ticks (10 per real second); the "hours" of
// creditsAt are run.mjs hours (36,000 ticks), counted from the checkpoint.
//
// Policy "script": port of scripts/0_cold_boot/harvesting/harvester.py
// (vakermit's value-density script): re-target before every hop; an item on the
// current cell is collected first; else the nearest item within 2 (ties: higher
// value, then row-major), else max value / d^1.35 (ties: scanner order); in
// clearing mode (base slots full once) the nearest item. One hop at a time,
// along the row axis first unless only the column step lands on an item or the
// column gap is larger. Rest before a hop that would pass 97 heat.
import { readFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import { ITEMS, fieldGrid, GRID_ROWS as ROWS, GRID_COLS as COLS, GRID_START } from "./field.mjs";

const CELLS = ROWS * COLS;
const BASE = GRID_START[0] * COLS + GRID_START[1];
const VALUES = ITEMS.map(i => i.value);
const TICKS_PER_RUN_HOUR = 36000;      // run.mjs hours (real time)
const TICKS_PER_WORLD_HOUR = 250;      // dayCycleDuration 600 s / 24 at 10 ticks/s
const MOVE_TICKS = 125, COLLECT_TICKS = 63;
const COOL_PER_TICK = 3 / TICKS_PER_WORLD_HOUR;
const HEAT_LIMIT = 97;                 // script: HEAT_MAX 100 - HEAT_SAFETY 3
const COST_ITEM = 1, COST_EMPTY = 7;    // the base pad E13 costs 1 too (simworker IE(): "base", not "empty")
// Script overhead per loop in ticks (interpreter step budget, info prints): the
// script loops over every known item each pass, so it grows with the items left.
// Least squares over 1,640 collect intervals of 54 headless runs (both modes,
// rms 0.65 ticks): hop loop 1.88 + 0.0537 x items left, collect loop
// (collect + store + sell) 1.88 + 0.0306 x items left.
const MOVE_OVERHEAD = [1.88, 0.0537], COLLECT_OVERHEAD = [1.88, 0.0306];
const REST_OVERHEAD = 2;

// Checkpoint h2 (devtools/headless/.cache/checkpoints/early_h2.json, tick 1193,
// 550 cr): Harvester moving A14 -> A15, heat 15.5, all 192 sectors scanned; the
// restarted script first gets "moving" and sleeps 0.25 world h, so its first
// hop starts ~63 ticks in. A13, C13, D13 already collected (main-save field only;
// run.mjs --field-seed swaps in a fresh field with just A15 cleared).
export const CHECKPOINT_H2 = {
  pos: 0 * COLS + 14, heat: 15.508, startDelay: 63,
  collected: ["A13", "C13", "D13"],
  // Clearing mode starts when the base's slots first fill: plan-dependent, with
  // feeders2.2 at 0.09-0.22 h, earlier on rich fields. Fit over 30 sims
  // (r -0.95, residual 280 ticks): tick = CLEARING_FIT[0] - CLEARING_FIT[1] x
  // Harvester credits by tick 3600 (0.1 h). clearingTick or clearingCredits
  // override it (switch at that tick / once credits reach that).
  clearingTick: null, clearingCredits: Infinity,
};

const CLEARING_FIT = [7994, 0.359], CLEARING_FIT_TICK = 3600;

// Fresh game (run.mjs --seed N --deploy-templates scripts/0_cold_boot, like the
// user's opening: scripts start ~50 ticks after the new game). Ticks count from
// the new game. Harvester at the base pad E13, heat 0, nothing scanned.
// Scanner (scanner.py): one sector every 3 ticks in SCAN_ORDER, +1 tick per
// item found (its info print), first sector known after tick 55 (the script's sort
// costs a few ticks). Harvester: polls get_scanned() at tick 52 and then every
// 21 ticks (sleep 2 s + print) until >= 60 sectors are known, then plays as
// usual on the sectors known so far: an item not yet scanned is neither a target
// nor collected, and planned as an empty cell. Fitted to fresh headless logs.
// No purchases run in that setup, so the base slots never fill and clearing
// mode never starts (the user's real run buys by hand; set clearingTick then).
export const FRESH = {
  pos: GRID_START[0] * COLS + GRID_START[1], heat: 0,
  scan: { first: 55, perSector: 3, perItem: 1, poll: 52, pollEvery: 21, wait: 60 },
  clearingTick: Infinity, clearingCredits: Infinity,
};
export const STARTS = { h2: CHECKPOINT_H2, fresh: FRESH };

const sectorIndex = id => (id.charCodeAt(0) - 65) * COLS + Number(id.slice(1)) - 1;
export const sectorName = i => String.fromCharCode(65 + ((i / COLS) | 0)) + String((i % COLS) + 1);

// Scanner order (scripts/0_cold_boot/harvesting/scanner.py: by squared distance
// from (3.5, 11.5), stable): get_scanned()'s dict order, which breaks ties.
const SCAN_ORDER = Int16Array.from(
  Array.from({ length: CELLS }, (_, i) => i)
    .map(i => [((i / COLS) | 0) - 3.5, (i % COLS) - 11.5, i])
    .map(([r, c, i]) => [r * r + c * c, i])
    .sort((a, b) => a[0] - b[0] || a[1] - b[1])
    .map(x => x[1]));
const ROW_OF = Int8Array.from({ length: CELLS }, (_, i) => (i / COLS) | 0);
const COL_OF = Int8Array.from({ length: CELLS }, (_, i) => i % COLS);
const DPOW = Float64Array.from({ length: ROWS + COLS }, (_, d) => d ** 1.35);
// Cells within distance 2, in the script's local order (d, then row-major).
const LOCAL = [];
for (let d = 1; d <= 2; d++)
  for (let dr = -2; dr <= 2; dr++)
    for (let dc = -2; dc <= 2; dc++) if (Math.abs(dr) + Math.abs(dc) === d) LOCAL.push([d, dr, dc]);

function chooseScript(g, pos, clearing) {
  const pr = ROW_OF[pos], pc = COL_OF[pos];
  // Priority 1: nearest item within 2, higher value first, then row-major.
  let best = -1, bestD = 9, bestV = -1;
  for (let k = 0; k < LOCAL.length; k++) {
    const [d, dr, dc] = LOCAL[k];
    const r = pr + dr, c = pc + dc;
    if (r < 0 || r >= ROWS || c < 0 || c >= COLS) continue;
    const q = r * COLS + c, it = g[q];
    if (it < 0) continue;
    const v = VALUES[it];
    if (d < bestD || (d === bestD && (v > bestV || (v === bestV && q < best)))) { best = q; bestD = d; bestV = v; }
  }
  if (best >= 0) return best;
  let bestS = -1;
  for (let k = 0; k < CELLS; k++) {
    const q = SCAN_ORDER[k], it = g[q];
    if (it < 0) continue;
    const d = Math.abs(ROW_OF[q] - pr) + Math.abs(COL_OF[q] - pc);
    if (clearing) {
      if (best < 0 || d < bestD) { best = q; bestD = d; }
    } else {
      const s = VALUES[it] / DPOW[d];
      if (s > bestS) { bestS = s; best = q; }
    }
  }
  return best;
}

function nextHop(g, pos, tgt) {
  const dr = ROW_OF[tgt] - ROW_OF[pos], dc = COL_OF[tgt] - COL_OF[pos];
  const a = dr > 0 ? pos + COLS : dr < 0 ? pos - COLS : -1;
  const b = dc > 0 ? pos + 1 : dc < 0 ? pos - 1 : -1;
  if (a >= 0 && g[a] >= 0) return a;
  if (b >= 0 && g[b] >= 0) return b;
  if (a >= 0 && b >= 0) return Math.abs(dc) > Math.abs(dr) ? b : a;
  return a >= 0 ? a : b;
}

export const POLICIES = { script: { choose: chooseScript, hop: nextHop } };

const WORK = new Int8Array(CELLS), VIEW = new Int8Array(CELLS), KNOWN_AT = new Int32Array(CELLS);
const HOURS_DEFAULT = [0.1, 0.2, 0.5];

// grid: Int8Array(192) of ITEMS indexes (-1 empty), not modified.
// opts: mode ("h2" checkpoint, default | "fresh" new game), policy, hours (list
// of run hours to report, from the checkpoint / the new game), start (overrides of
// the mode's start state: pos, heat, startDelay, scan),
// clearingTick / clearingCredits (see CHECKPOINT_H2; Infinity: never), route (true: list the collects),
// targets (credit totals; the run goes on until all are reached or the last hour).
// -> {creditsAt: {h: credits}, reachedAt: {credits: run hours | null}, collected, heatMax, restTicks, clearingTick, route?}
export function simulate(grid, opts = {}) {
  const policy = POLICIES[opts.policy ?? "script"];
  const hours = opts.hours ?? HOURS_DEFAULT;
  const base = STARTS[opts.mode ?? "h2"];
  const start = { ...base, ...(opts.start ?? {}) };
  const clearingCredits = opts.clearingCredits ?? start.clearingCredits;
  let clearingAt = opts.clearingTick ?? start.clearingTick ?? Infinity;
  const fitClearing = (opts.clearingTick ?? start.clearingTick) == null;
  const route = opts.route ? [] : null, rests = opts.route ? [] : null;
  const g = WORK;
  g.set(grid);
  // v: the script's view (scanned items still there); g itself once all is scanned.
  let v = g, nKnown = CELLS, firstTick = start.startDelay, left = 0;
  for (let k = 0; k < CELLS; k++) if (g[k] >= 0) left++; // items the script knows
  const sc = start.scan;
  if (sc) {
    v = VIEW;
    v.fill(-1);
    nKnown = 0;
    left = 0;
    let at = sc.first;
    for (let k = 0; k < CELLS; k++) {
      KNOWN_AT[k] = at;
      at += sc.perSector + (g[SCAN_ORDER[k]] >= 0 ? sc.perItem : 0);
    }
    firstTick = sc.poll;
    while (!(KNOWN_AT[sc.wait - 1] < firstTick)) firstTick += sc.pollEvery;
  }
  const marks = hours.map(h => Math.round(h * TICKS_PER_RUN_HOUR));
  const end = Math.max(...marks);
  const targets = opts.targets ?? [];
  const reached = new Float64Array(targets.length).fill(-1);
  let nReached = 0;
  const creditsAt = new Float64Array(hours.length);
  let pos = start.pos, heat = start.heat, t = 0, credits = 0, restTicks = 0, heatMax = heat;
  let creditsFit = 0;
  let clearing = false, clearingTick = -1, collected = 0, m = 0;
  const pass = dt => { t += dt; heat = Math.max(0, heat - dt * COOL_PER_TICK); };
  pass(firstTick);
  while (t <= end) {
    while (nKnown < CELLS && KNOWN_AT[nKnown] < t) {
      const q = SCAN_ORDER[nKnown++];
      v[q] = g[q];
      if (g[q] >= 0) left++;
    }
    if (fitClearing && clearingAt === Infinity && t >= CLEARING_FIT_TICK)
      clearingAt = CLEARING_FIT[0] - CLEARING_FIT[1] * creditsFit;
    if (!clearing && (t >= clearingAt || credits >= clearingCredits)) { clearing = true; clearingTick = t; }
    const it = v[pos];
    if (it >= 0) {
      pass(COLLECT_TICKS);
      while (m < marks.length && marks[m] < t) creditsAt[m++] = credits;
      if (m === marks.length && nReached === targets.length) break;
      if (t <= CLEARING_FIT_TICK) creditsFit = credits + VALUES[it];
      credits += VALUES[it];
      for (let k = 0; k < targets.length; k++) if (reached[k] < 0 && credits >= targets[k]) { reached[k] = t; nReached++; }
      g[pos] = -1;
      v[pos] = -1;
      collected++;
      if (route) route.push({ tick: t, sector: sectorName(pos), item: ITEMS[it].id, value: VALUES[it], heat: +heat.toFixed(1) });
      left--;
      pass(COLLECT_OVERHEAD[0] + COLLECT_OVERHEAD[1] * left);
      continue;
    }
    const tgt = policy.choose(v, pos, clearing);
    if (tgt < 0) { pass(TICKS_PER_WORLD_HOUR / 2); continue; } // field empty: idle
    const q = policy.hop(v, pos, tgt);
    const cost = v[q] >= 0 ? COST_ITEM : COST_EMPTY;
    if (heat + cost > HEAT_LIMIT) { // script cool_to(): sleep the exact need, >= 0.1 h, up to 6 rounds
      const target = HEAT_LIMIT - cost;
      for (let n = 0; n < 6 && heat > target; n++) {
        const dt = Math.round((Math.max(0.1, (heat - target) / 3) * 25 + 0.2) * 10) + REST_OVERHEAD;
        restTicks += dt;
        if (rests) rests.push({ tick: t, heat: +heat.toFixed(1), hours: +(dt / TICKS_PER_WORLD_HOUR).toFixed(2), sector: sectorName(pos) });
        pass(dt);
      }
    }
    heat += q === BASE || g[q] >= 0 ? COST_ITEM : COST_EMPTY; // the game charges the base pad like an item cell
    if (heat > heatMax) heatMax = heat;
    pos = q;
    pass(MOVE_TICKS + MOVE_OVERHEAD[0] + MOVE_OVERHEAD[1] * left);
  }
  while (m < marks.length) creditsAt[m++] = credits;
  return {
    creditsAt: Object.fromEntries(hours.map((h, i) => [h, creditsAt[i]])),
    reachedAt: Object.fromEntries(targets.map((c, i) => [c, reached[i] < 0 ? null : reached[i] / TICKS_PER_RUN_HOUR])),
    collected, heatMax: +heatMax.toFixed(1), restTicks, clearingTick, ...(route ? { route, rests } : {}),
  };
}

// Start grid of a run from checkpoint h2: the seed's fresh field, the Harvester's
// cell cleared (run.mjs --field-seed); mainSave: the checkpoint's own field.
export function startGrid(seed, { mainSave = false } = {}, out = new Int8Array(CELLS)) {
  fieldGrid(seed, out);
  out[CHECKPOINT_H2.pos] = -1;
  if (mainSave) for (const id of CHECKPOINT_H2.collected) out[sectorIndex(id)] = -1;
  return out;
}

// Seed scanner hooks: Harvester credits by 0.2 run hours, from checkpoint h2
// (mode "h2", default) or a new game (mode "fresh").
const SCORE_GRID = new Int8Array(CELLS);
const SCORE_HOURS = [0.2];
const SCORE_OPTS = { h2: { hours: SCORE_HOURS }, fresh: { hours: SCORE_HOURS, mode: "fresh" } };
export function routeScore(grid, mode = "h2") {
  return simulate(grid, SCORE_OPTS[mode]).creditsAt[0.2];
}
export const freshScore = grid => routeScore(grid, "fresh");
// Run hours from a new game until the Harvester has earned `credits` (default: the 25/25 slot
// build-out, 16,900 cr of Solar/Battery/O2 minus 2,500 uplink and 4,150 intro-contract cr); hoursCap if never.
// cap: give up after this many run hours (returns cap), e.g. a scan's current worst kept.
const REACH_TARGETS = [0], REACH_HOURS = [1.0];
const REACH_OPTS = { mode: "fresh", hours: REACH_HOURS, targets: REACH_TARGETS };
export function freshReach(grid, credits = 10250, cap = 1.0) {
  REACH_TARGETS[0] = credits;
  REACH_HOURS[0] = Math.min(1.0, cap);
  return simulate(grid, REACH_OPTS).reachedAt[credits] ?? REACH_HOURS[0];
}
export const seedScore = (seed, mode = "h2") =>
  routeScore(mode === "fresh" ? freshGrid(seed, SCORE_GRID) : startGrid(seed, {}, SCORE_GRID), mode);

// Start grid of a new game: the seed's field as generated (the base pad is empty).
export const freshGrid = (seed, out = new Int8Array(CELLS)) => fieldGrid(seed, out);

// Headless runs (run.mjs --save early_h2.json --field-seed N --policy feeders2.2,
// 2026-10-06): Harvester credits (sold) by 0.1/0.2/0.5 h. mainSave: no field swap.
export const CALIBRATION = [
  // [seed, mainSave, by 0.1 h, by 0.2 h, by 0.5 h]
  [12412, false, 11600, 16350, 34875],
  [3498, false, 3025, 10875, 24525],
  [4, false, 5675, 9500, 18400],
  [1, false, 3475, 5725, 23950],
  [7416, false, 3875, 7325, 13375],
  [420526420, false, 7675, 10750, 13100],
  [3, false, 4475, 7000, 13350],
  [2, false, 2400, 8850, 15075],
  [5, false, 2075, 4875, 11050],
  // more runs (0.55 h each), same setup
  [420526420, true, 7675, 10800, 12725],
  [6, false, 6475, 12225, 19725], [7, false, 4025, 9975, 24575], [8, false, 2575, 6325, 12850],
  [9, false, 3250, 6450, 12800], [10, false, 5625, 9800, 18525], [11, false, 1600, 6625, 8375],
  [12, false, 1550, 3975, 7025], [13, false, 4850, 10375, 15125], [14, false, 3350, 6275, 11825],
  [15, false, 5975, 10150, 19975], [17, false, 3300, 4850, 10550], [42, false, 3675, 6725, 13925],
  [100, false, 2450, 4625, 10925], [123, false, 3150, 8325, 12500], [777, false, 1825, 6700, 13900],
  [1000, false, 2300, 5400, 17275], [2024, false, 4150, 6750, 9550], [5000, false, 7725, 10275, 18025],
  [9999, false, 3350, 8975, 13125], [15000, false, 1525, 10775, 16175],
];

function spearman(xs, ys) {
  const rank = v => {
    const idx = v.map((x, i) => [x, i]).sort((a, b) => a[0] - b[0]);
    const r = new Array(v.length);
    for (let i = 0; i < idx.length;) {
      let j = i;
      while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++;
      for (let k = i; k <= j; k++) r[idx[k][1]] = (i + j) / 2;
      i = j + 1;
    }
    return r;
  };
  const a = rank(xs), b = rank(ys), n = xs.length, ma = (n - 1) / 2;
  let num = 0, da = 0, db = 0;
  for (let i = 0; i < n; i++) { num += (a[i] - ma) * (b[i] - ma); da += (a[i] - ma) ** 2; db += (b[i] - ma) ** 2; }
  return num / Math.sqrt(da * db);
}

// Fresh headless games (run.mjs --seed N --deploy-templates scripts/0_cold_boot,
// 2026-10-06): Harvester credits (sold) by 0.1/0.2/0.5 h from the new game.
export const FRESH_CALIBRATION = [
  // [seed, by 0.1 h, by 0.2 h, by 0.5 h]
  [1789002546, 6250, 12225, 23525],
  [12412, 3975, 14200, 24775], [3498, 2775, 10675, 30725], [4, 4375, 11900, 27300], [1, 4950, 17350, 24125],
  [7416, 3700, 7500, 17725], [420526420, 2800, 10350, 15625], [3, 4600, 7075, 16875], [2, 3500, 4850, 14750],
  [5, 1725, 4925, 9900], [6, 3675, 7625, 20700], [7, 3900, 9850, 24425], [8, 4175, 6325, 9650],
  [9, 4525, 7575, 17375], [10, 5775, 8625, 17325], [11, 4150, 9125, 15725], [12, 1375, 3750, 6675],
  [13, 5175, 9900, 21075], [42, 1900, 7950, 12275], [777, 2975, 6275, 15800], [2024, 2450, 6175, 9500],
  [5000, 4975, 7500, 15875], [9999, 2050, 7850, 9775], [15000, 3000, 6325, 15150],
];

function check(mode) {
  const hs = HOURS_DEFAULT;
  const table = mode === "fresh" ? FRESH_CALIBRATION.map(([seed, ...sim]) => [seed, false, ...sim]) : CALIBRATION;
  console.log(`mode ${mode}`);
  console.log("seed".padEnd(12) + hs.map(h => `sim ${h}`.padStart(9) + `model`.padStart(8) + "err%".padStart(6)).join(""));
  const sims = hs.map(() => []), models = hs.map(() => []), errs = hs.map(() => []);
  for (const [seed, mainSave, ...sim] of table) {
    const r = simulate(mode === "fresh" ? freshGrid(seed) : startGrid(seed, { mainSave }), { mode });
    let line = (String(seed) + (mainSave ? "*" : "")).padEnd(12);
    hs.forEach((h, i) => {
      const mod = r.creditsAt[h], e = (100 * (mod - sim[i])) / sim[i];
      sims[i].push(sim[i]); models[i].push(mod); errs[i].push(Math.abs(e));
      line += String(sim[i]).padStart(9) + String(mod).padStart(8) + e.toFixed(0).padStart(6);
    });
    console.log(line);
  }
  console.log("mean |err| %".padEnd(12) + errs.map(e => (e.reduce((a, b) => a + b, 0) / e.length).toFixed(1).padStart(23)).join(""));
  console.log("spearman".padEnd(12) + hs.map((_, i) => spearman(sims[i], models[i]).toFixed(2).padStart(23)).join(""));
  if (table.some(r => r[1])) console.log("* main save field (A13, C13, D13 collected)");
}

// Collect lines of a run.mjs console.log: [{tick (from startTick: the checkpoint's,
// 0 for a new game), sector, value, heat}].
export function simRoute(consoleLog, startTick = 1193) {
  const out = [];
  for (const m of consoleLog.matchAll(/\[tick (\d+)\] \[info\] \[harvester_1\] \[harvester\] \+ .*?\((\d+) cr\) at ([A-H]\d+) \| heat ([\d.]+)/g))
    out.push({ tick: Number(m[1]) - startTick, sector: m[3], value: Number(m[2]), heat: Number(m[4]) });
  return out;
}

function seedRange(spec) {
  return spec.split(",").flatMap(part => {
    const [lo, hi] = part.split("-").map(Number);
    return Array.from({ length: (hi ?? lo) - lo + 1 }, (_, i) => lo + i);
  });
}

function main() {
  const { values: a } = parseArgs({
    options: {
      seed: { type: "string" }, route: { type: "boolean" }, check: { type: "boolean" }, seeds: { type: "string" },
      top: { type: "string" }, compare: { type: "string" }, main: { type: "boolean" }, fresh: { type: "boolean" }, clearing: { type: "string" }, "clearing-tick": { type: "string" },
    },
  });
  const mode = a.fresh ? "fresh" : "h2";
  const opts = { mode };
  const grid0 = (seed, out) => (a.fresh ? freshGrid(seed, out) : startGrid(seed, { mainSave: !!a.main }, out));
  if (a.clearing !== undefined) opts.clearingCredits = Number(a.clearing);
  if (a["clearing-tick"] !== undefined) opts.clearingTick = Number(a["clearing-tick"]);
  if (a.check) {
    check("h2");
    console.log();
    check("fresh");
  } else if (a.compare) {
    const sim = simRoute(readFileSync(`${a.compare}/console.log`, "utf8"), a.fresh ? 0 : 1193);
    const mod = simulate(grid0(Number(a.seed)), { ...opts, route: true, hours: [0.5] }).route;
    for (let i = 0; i < Math.max(sim.length, mod.length); i++) {
      const s = sim[i], m = mod[i];
      const fmt = x => (x ? `${String(x.tick).padStart(6)} ${x.sector.padEnd(4)}${String(x.value).padStart(5)} h${String(x.heat).padStart(5)}` : "".padEnd(26));
      console.log(`${fmt(s)}   ${fmt(m)}${s && m && s.sector !== m.sector ? "   <> " : ""}`);
    }
  } else if (a.seed) {
    const seed = Number(a.seed);
    const r = simulate(grid0(seed), { ...opts, route: !!a.route });
    if (r.route) for (const c of r.route) console.log(`${String(c.tick).padStart(6)} ${c.sector.padEnd(4)} ${c.item.padEnd(17)}${String(c.value).padStart(5)} heat ${c.heat}`);
    if (r.rests) for (const x of r.rests) console.log(`rest ${x.tick} at ${x.sector} heat ${x.heat} for ${x.hours} h`);
    const { route, rests, ...rest } = r;
    console.log(JSON.stringify({ seed, ...rest }));
  } else if (a.seeds) {
    const seeds = seedRange(a.seeds);
    const grid = new Int8Array(CELLS);
    const t0 = performance.now();
    const rows = seeds.map(seed => ({ seed, ...simulate(grid0(seed, grid), opts).creditsAt }));
    const ms = performance.now() - t0;
    for (const h of HOURS_DEFAULT) {
      const v = rows.map(r => r[h]).sort((x, y) => x - y);
      const q = p => v[Math.floor(p * (v.length - 1))];
      console.log(`by ${h} h: min ${q(0)} p10 ${q(0.1)} median ${q(0.5)} p90 ${q(0.9)} max ${q(1)}`);
    }
    console.log(`${seeds.length} fields in ${ms.toFixed(0)} ms (${((1000 * ms) / seeds.length).toFixed(0)} us/field)`);
    for (const r of rows.sort((x, y) => y[0.2] - x[0.2]).slice(0, Number(a.top ?? 10))) console.log(JSON.stringify(r));
  } else {
    console.error("one of --seed, --check, --seeds, --compare");
    process.exitCode = 2;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
