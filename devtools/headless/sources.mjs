// Scores a seed's power sources (scoring_map_seeds.md, Part 3): total oil mean
// (all 5 wells, peak rate x active share) is the score; total steam mean and the
// nearest Thermal Cap site (vent) are printed for eyeballing. Runs the game's own
// world generators (vents, exotic deposits, wells, in game order) on an empty
// planet, ~44 us per seed. Home is fixed at (0, 0).
//
//   node devtools/headless/sources.mjs --seed N            one seed, every vent and well
//   node devtools/headless/sources.mjs --seeds 1-20000     quantiles over a range
//   node devtools/headless/sources.mjs --in FILE.jsonl [--top N] [--out FILE.jsonl]
//        scores a scan file (seedscan.mjs output) in file order; --out writes each
//        row with the fields below added; prints quantiles and the best by oil
//   node devtools/headless/sources.mjs --emit N            {sources, geologicalAnomalies} JSON
//        of a fresh world (devtools/swap_seed.py writes it into a save)
//
// Fields: oil, steam (mean t/h, all sources), vent_m (straight-line m to the
// nearest vent), vent_steam (that vent's mean t/h).
import { readFileSync, writeFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import { loadSimModule, generateWorld } from "./simhost.mjs";

const mod = await loadSimModule();
if (!mod.__ctWorldGen) throw new Error("simworker world generators not found (see simhost.mjs findWorldGen())");
const { oilCycle } = mod.__ctWorldGen;

const share = (active, dormant) => active / (active + dormant);

// planet.sources and planet.geologicalAnomalies of a fresh world (no outposts yet).
export function world(seed) {
  const state = { seed, planetId: "nocturna", planet: { sources: [], geologicalAnomalies: [], outposts: [], constructionBlueprints: [] } };
  generateWorld(mod.__ctWorldGen, state);
  return state;
}

export function sources(seed) {
  const state = world(seed);
  const vents = [], oil = [];
  for (const s of state.planet.sources) {
    const m = Math.round(Math.hypot(s.x, s.y));
    if (s.kind === "thermal") {
      vents.push({ id: s.id, x: s.x, y: s.y, m, peak: s.basePeakSteamRate, mean: s.basePeakSteamRate * share(s.cycleActiveMinutes, s.cycleDormantMinutes) });
    } else if (s.kind === "oil") {
      const c = oilCycle(state, s.id);
      oil.push({ id: s.id, x: s.x, y: s.y, m, tier: s.yieldTier, peak: s.baseFlowRate, mean: s.baseFlowRate * share(c.activeMinutes, c.dormantMinutes) });
    }
  }
  return { vents, oil };
}

export function score(seed) {
  const { vents, oil } = sources(seed);
  const near = vents.reduce((a, v) => (v.m < a.m ? v : a));
  const sum = xs => xs.reduce((a, x) => a + x.mean, 0);
  return { oil: +sum(oil).toFixed(2), steam: Math.round(sum(vents)), vent_m: near.m, vent_steam: Math.round(near.mean) };
}

function quantiles(rows) {
  for (const k of ["oil", "steam", "vent_m", "vent_steam"]) {
    const v = rows.map(r => r[k]).sort((a, b) => a - b);
    const q = p => v[Math.floor(p * (v.length - 1))];
    console.log(`${k.padEnd(10)} min ${q(0)}  p10 ${q(0.1)}  p50 ${q(0.5)}  p90 ${q(0.9)}  max ${q(1)}`);
  }
}

function main() {
  const { values: a } = parseArgs({ options: { emit: { type: "string" }, seed: { type: "string" }, seeds: { type: "string" }, in: { type: "string" }, top: { type: "string" }, out: { type: "string" } } });
  if (a.emit) {
    const { planet } = world(Number(a.emit));
    process.stdout.write(JSON.stringify({ sources: planet.sources, geologicalAnomalies: planet.geologicalAnomalies }));
    return;
  }
  if (a.seed) {
    const { vents, oil } = sources(Number(a.seed));
    console.log(JSON.stringify(score(Number(a.seed))));
    for (const s of [...vents, ...oil]) console.log(`${s.id.padEnd(11)} (${s.x}, ${s.y}) ${String(s.m).padStart(4)} m  ${s.tier ? s.tier.padEnd(9) : "".padEnd(9)} peak ${s.peak}  mean ${s.mean.toFixed(1)} t/h`);
    return;
  }
  let rows;
  if (a.seeds) {
    const [lo, hi] = a.seeds.split("-").map(Number);
    rows = [];
    for (let s = lo; s <= hi; s++) rows.push({ seed: s, ...score(s) });
  } else if (a.in) {
    rows = readFileSync(a.in, "utf8").trim().split("\n").map(l => JSON.parse(l));
    if (a.top) rows = rows.slice(0, Number(a.top));
    rows = rows.map(r => ({ ...r, ...score(r.seed) }));
  } else {
    throw new Error("pass --seed, --seeds or --in");
  }
  quantiles(rows);
  if (a.out) writeFileSync(a.out, rows.map(r => JSON.stringify(r)).join("\n") + "\n");
  console.log("best by oil:");
  for (const r of [...rows].sort((x, y) => y.oil - x.oil).slice(0, 10)) console.log(`  ${r.seed}  oil ${r.oil}  steam ${r.steam}  vent ${r.vent_m} m (${r.vent_steam} t/h)`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
