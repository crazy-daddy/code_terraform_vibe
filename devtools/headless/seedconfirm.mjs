// Confirms seedscan.mjs picks in fresh headless games: runs the top N seeds of a scan file
// with run.mjs (--deploy-templates scripts/0_cold_boot), reads credits every tick, and
// compares them with harvest_model.mjs (policy "hybrid"). The model can split from the
// game at scan-phase ties, so confirm a seed here before playing it.
//
//   node devtools/headless/seedconfirm.mjs --in FILE.jsonl [--top 30] [--rank scan|cr|20k]
//        [--threads N] [--runs DIR] [--out FILE.json]
//   --rank  scan: file order; cr: model credits by 0.5 h; 20k: model minutes to 20,000 cr
//           (the model re-ranks the whole file first, ~1 ms per seed)
//   --runs  run.mjs output per seed (default .cache/confirm); seeds already there are reused
//
// Results: docs/plans/scoring_map_seeds.md, "Full scan with the hybrid route".
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { availableParallelism } from "node:os";
import { parseArgs } from "node:util";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { simulate, freshGrid } from "./harvest_model.mjs";
import { makePolicy } from "./harvest_policies.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.join(HERE, "..", "..");
const TARGETS = [10250, 20000], HOURS = [0.1, 0.2, 0.5], TICKS_PER_MIN = 600, MATCH_MIN = 0.1;
const HYBRID = makePolicy("hybrid");

const minutes = h => h === null ? null : 60 * h;

function model(seed) {
  const r = simulate(freshGrid(seed), { mode: "fresh", policy: HYBRID, hours: HOURS, targets: TARGETS });
  return { reach: TARGETS.map(t => minutes(r.reachedAt[t])), cr: HOURS.map(h => r.creditsAt[h]) };
}

function runGame(seed, dir) {
  if (existsSync(path.join(dir, "summary.json"))) return Promise.resolve();
  return new Promise((res, rej) => {
    const p = spawn(process.execPath, [path.join(HERE, "run.mjs"), "--seed", String(seed), "--deploy-templates", "scripts/0_cold_boot",
      "--hours", String(Math.max(...HOURS)), "--report-every", String(1 / TICKS_PER_MIN), "--out", dir], { cwd: REPO, stdio: "ignore" });
    p.on("exit", code => code === 0 ? res() : rej(new Error(`run.mjs --seed ${seed} exited ${code}`)));
  });
}

function readGame(dir) {
  const rows = readFileSync(path.join(dir, "metrics.jsonl"), "utf8").trim().split("\n").map(l => JSON.parse(l));
  const reach = TARGETS.map(t => { const m = rows.find(x => x.credits >= t); return m ? m.tick / TICKS_PER_MIN : null; });
  return { reach, cr: HOURS.map(h => rows.find(x => x.gameHours >= h)?.credits ?? null) };
}

const fmt = (x, d = 2) => x === null ? "-" : x.toFixed(d);

async function main() {
  const { values: a } = parseArgs({ options: {
    in: { type: "string" }, top: { type: "string", default: "30" }, rank: { type: "string", default: "scan" },
    threads: { type: "string" }, runs: { type: "string", default: path.join(HERE, ".cache", "confirm") }, out: { type: "string" },
  } });
  if (!a.in) { console.error("--in FILE.jsonl required"); process.exit(2); }
  const scan = readFileSync(a.in, "utf8").trim().split("\n").map((l, i) => ({ ...JSON.parse(l), scanRank: i + 1 }));
  let picks;
  if (a.rank === "scan") picks = scan.slice(0, Number(a.top)).map(r => ({ ...r, model: model(r.seed) }));
  else {
    const key = { cr: r => -r.model.cr[HOURS.length - 1], "20k": r => r.model.reach[1] ?? Infinity }[a.rank];
    if (!key) { console.error(`unknown --rank ${a.rank}; have scan, cr, 20k`); process.exit(2); }
    picks = scan.map(r => ({ ...r, model: model(r.seed) })).sort((x, y) => key(x) - key(y)).slice(0, Number(a.top));
  }
  const queue = [...picks], threads = Number(a.threads ?? availableParallelism() - 1);
  await Promise.all(Array.from({ length: threads }, async () => {
    for (let r; (r = queue.shift());) await runGame(r.seed, path.join(a.runs, String(r.seed)));
  }));
  const rows = picks.map(r => {
    const sim = readGame(path.join(a.runs, String(r.seed)));
    const match = TARGETS.every((_, i) => sim.reach[i] !== null && r.model.reach[i] !== null && Math.abs(sim.reach[i] - r.model.reach[i]) <= MATCH_MIN);
    return { seed: r.seed, scan_rank: r.scanRank, cc_load: r.cc_load, gb_load: r.gb_load, total: r.total, model: r.model, sim, match };
  });
  console.log("seed".padEnd(12) + "scan#".padStart(7) + "10,250 sim/model".padStart(18) + "20,000 sim/model".padStart(18)
    + "cr 0.1/0.2/0.5 h (sim)".padStart(26) + "  cc    gb    total");
  for (const r of rows) {
    console.log(String(r.seed).padEnd(12) + String(r.scan_rank).padStart(7)
      + TARGETS.map((_, i) => `${fmt(r.sim.reach[i])}/${fmt(r.model.reach[i])}`.padStart(18)).join("")
      + r.sim.cr.join("/").padStart(26) + `  ${fmt(r.cc_load)}  ${fmt(r.gb_load)}  ${r.total}` + (r.match ? "" : "  SPLIT"));
  }
  console.log(`${rows.filter(r => r.match).length} of ${rows.length} match the model within ${MATCH_MIN} min on both targets`);
  if (a.out) writeFileSync(a.out, JSON.stringify(rows, null, 1));
}

main();
