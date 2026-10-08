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
//   node devtools/headless/sources.mjs --pois 1-1000       one JSON line per seed,
//        {seed, pois: [{id, kind, x, y}]}: every map contact of a fresh world as
//        nocturna.points_of_interest() lists it (devtools/scan_stop_eval.py reads it)
//
// Fields: oil (mean t/h of the 5 wells), deep_oil (the 3 deep reservoirs a
// Seismic Sonar confirms, late game), oil_total, deep_m (straight-line m to the
// nearest reservoir), steam (mean t/h, all vents), vent_m (straight-line m to
// the nearest vent), vent_steam (that vent's mean t/h).
import { readFileSync, writeFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import { loadSimModule, generateWorld } from "./simhost.mjs";
import { prng } from "./field.mjs";

const mod = await loadSimModule();
if (!mod.__ctWorldGen) throw new Error("simworker world generators not found (see simhost.mjs findWorldGen())");
const { oilCycle } = mod.__ctWorldGen;

const share = (active, dormant) => active / (active + dormant);

// Deep oil (since e1986ce): on every load, after the generators, the UI thread
// rolls planet.deepOilProspecting once (kept while present, never rerolled): a
// shuffle of the sorted anomaly ids, seeded mp(seed ^ fnv1a(DEEP_OIL_SALT)),
// first 3. A Seismic Sonar survey turns each into a rich oil well at the
// anomaly's position, same id, cycle from oilCycle() like any well.
const DEEP_OIL_SALT = "deep-oil-prospecting-v1", DEEP_OIL_RATE = 16, DEEP_OIL_SITES = 3;

function fnv1a(s) { // game hash of the salt string
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h | 0;
}

export function deepOilProspecting(state) {
  const ids = state.planet.geologicalAnomalies.map(a => a.id).sort();
  if (ids.length < DEEP_OIL_SITES) return null; // the game skips the roll
  const rand = prng(state.seed ^ fnv1a(DEEP_OIL_SALT));
  for (let i = ids.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [ids[i], ids[j]] = [ids[j], ids[i]];
  }
  return { generationVersion: 1, reservoirSiteIds: ids.slice(0, DEEP_OIL_SITES), scanResults: {} };
}

// planet.sources, planet.geologicalAnomalies and planet.deepOilProspecting of a
// fresh world (no outposts yet).
export function world(seed) {
  const state = { seed, planetId: "nocturna", planet: { sources: [], geologicalAnomalies: [], outposts: [], constructionBlueprints: [] } };
  generateWorld(mod.__ctWorldGen, state);
  state.planet.deepOilProspecting = deepOilProspecting(state);
  return state;
}

export function sources(seed) {
  const state = world(seed);
  const vents = [], oil = [], deep = [];
  const well = (s, rate, tier) => {
    const c = oilCycle(state, s.id);
    return { id: s.id, x: s.x, y: s.y, m: Math.round(Math.hypot(s.x, s.y)), tier, peak: rate, mean: rate * share(c.activeMinutes, c.dormantMinutes) };
  };
  for (const s of state.planet.sources) {
    if (s.kind === "thermal") {
      vents.push({ id: s.id, x: s.x, y: s.y, m: Math.round(Math.hypot(s.x, s.y)), peak: s.basePeakSteamRate, mean: s.basePeakSteamRate * share(s.cycleActiveMinutes, s.cycleDormantMinutes) });
    } else if (s.kind === "oil") {
      oil.push(well(s, s.baseFlowRate, s.yieldTier));
    }
  }
  for (const id of state.planet.deepOilProspecting?.reservoirSiteIds ?? []) {
    deep.push(well(state.planet.geologicalAnomalies.find(a => a.id === id), DEEP_OIL_RATE, "deep"));
  }
  return { vents, oil, deep };
}

export function score(seed) {
  const { vents, oil, deep } = sources(seed);
  const nearest = xs => xs.reduce((a, v) => (v.m < a.m ? v : a));
  const near = nearest(vents);
  const sum = xs => xs.reduce((a, x) => a + x.mean, 0);
  return {
    oil: +sum(oil).toFixed(2), deep_oil: +sum(deep).toFixed(2), oil_total: +(sum(oil) + sum(deep)).toFixed(2), deep_m: nearest(deep).m,
    steam: Math.round(sum(vents)), vent_m: near.m, vent_steam: Math.round(near.mean),
  };
}

function quantiles(rows) {
  for (const k of ["oil", "deep_oil", "oil_total", "deep_m", "steam", "vent_m", "vent_steam"]) {
    const v = rows.map(r => r[k]).sort((a, b) => a - b);
    const q = p => v[Math.floor(p * (v.length - 1))];
    console.log(`${k.padEnd(10)} min ${q(0)}  p10 ${q(0.1)}  p50 ${q(0.5)}  p90 ${q(0.9)}  max ${q(1)}`);
  }
}

function main() {
  const { values: a } = parseArgs({ options: { emit: { type: "string" }, pois: { type: "string" }, seed: { type: "string" }, seeds: { type: "string" }, in: { type: "string" }, top: { type: "string" }, out: { type: "string" } } });
  if (a.emit) {
    const { planet } = world(Number(a.emit));
    process.stdout.write(JSON.stringify({ sources: planet.sources, geologicalAnomalies: planet.geologicalAnomalies }));
    return;
  }
  if (a.pois) {
    if (!mod.__ctPoiList) throw new Error("points_of_interest list function not found (see simhost.mjs POI_LIST)");
    const [lo, hi = lo] = a.pois.split("-").map(Number);
    const lines = [];
    for (let s = lo; s <= hi; s++) {
      const pois = mod.__ctPoiList(world(s)).map(p => ({ id: p.id, kind: p.kind, x: p.x, y: p.y }));
      lines.push(JSON.stringify({ seed: s, pois }));
    }
    process.stdout.write(lines.join("\n") + "\n");
    return;
  }
  if (a.seed) {
    const { vents, oil, deep } = sources(Number(a.seed));
    console.log(JSON.stringify(score(Number(a.seed))));
    for (const s of [...vents, ...oil, ...deep]) console.log(`${s.id.padEnd(22)} (${s.x}, ${s.y}) ${String(s.m).padStart(4)} m  ${s.tier ? s.tier.padEnd(9) : "".padEnd(9)} peak ${s.peak}  mean ${s.mean.toFixed(1)} t/h`);
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
  for (const r of [...rows].sort((x, y) => y.oil - x.oil).slice(0, 10)) console.log(`  ${r.seed}  oil ${r.oil} (+${r.deep_oil} deep = ${r.oil_total})  steam ${r.steam}  vent ${r.vent_m} m (${r.vent_steam} t/h)`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
