// Where to put a Smelter/Fabricator outpost that Pioneers feed by hand (before
// static drills and drones). The mineral sites are a fixed game table, the same
// in every world, so this is a map question, not a seed score.
//
// Cost of a spot = sum over minerals of weight x Pioneer hours per unit, from the
// best site of that mineral for this spot:
//   drive  2 x distance / (DRIVE_M_PER_H x throttle) / units per trip
//   dig    base minutes x drill speed multiplier / purity (1 / 2 / 3) / 60
// Straight-line distances. Spots are a grid over the map; the output keeps the
// best spot per distinct set of picked sites, so each row is another layout.
//
//   node devtools/simulation/headless/ore_outpost.mjs [--weights iron_ore=4,silicon=3,titanium=2,cobalt=1,rare_earth=1]
//        [--load 50] [--throttle 0.6] [--drill-mult 1] [--step 10] [--top 10]
//   node devtools/simulation/headless/ore_outpost.mjs --at=X,Y       cost and picks of one spot (= form: X may be negative)
//   node devtools/simulation/headless/ore_outpost.mjs --sites        the site table
import { parseArgs } from "node:util";
import { loadSimModule } from "./simhost.mjs";

// scripts/4_controlpanel/lib/vehicle_energy.py DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE.
const DRIVE_M_PER_H = 100;
// Drill Module base minutes per unit (docs: drill_module.mine).
const DIG_MIN = { iron_ore: 15, silicon: 15, lead_ore: 18, titanium: 20, cobalt: 20, rare_earth: 25, neutronium: 30 };
const PURITY = { standard: 1, rich: 2, pure: 3 };
const MAP = 750;

function parseWeights(s) {
  return Object.fromEntries(s.split(",").map(kv => {
    const [k, v] = kv.split("=");
    if (!(k in DIG_MIN)) throw new Error(`unknown mineral ${k}; have ${Object.keys(DIG_MIN)}`);
    return [k, Number(v)];
  }));
}

// Best site per weighted mineral for the spot (x, y): [{mineral, site, m, h}], h = Pioneer h/unit.
function picks(sites, weights, o, x, y) {
  const mPerH = DRIVE_M_PER_H * o.throttle;
  return Object.keys(weights).map(mineral => {
    let best = null;
    for (const s of sites) {
      if (s.mineralId !== mineral) continue;
      const m = Math.hypot(s.x - x, s.y - y);
      const h = (2 * m) / mPerH / o.load + (DIG_MIN[mineral] * o.drillMult) / PURITY[s.purity] / 60;
      if (!best || h < best.h) best = { mineral, site: s, m, h };
    }
    if (!best) throw new Error(`no ${mineral} site in the game table`);
    return best;
  });
}

const cost = (weights, ps) => ps.reduce((a, p) => a + weights[p.mineral] * p.h, 0);

function show(weights, x, y, ps) {
  console.log(`(${x}, ${y})  ${Math.round(Math.hypot(x, y))} m from home  cost ${cost(weights, ps).toFixed(2)} h`);
  for (const p of ps) {
    console.log(`  ${p.mineral.padEnd(11)} x${weights[p.mineral]}  ${p.site.id.padEnd(18)} ${p.site.purity.padEnd(8)} ${String(Math.round(p.m)).padStart(4)} m  ${p.h.toFixed(3)} h/unit`);
  }
}

async function main() {
  const { values: a } = parseArgs({ options: {
    weights: { type: "string", default: "iron_ore=4,silicon=3,titanium=2,cobalt=1,rare_earth=1" },
    load: { type: "string", default: "50" }, throttle: { type: "string", default: "0.6" },
    "drill-mult": { type: "string", default: "1" }, step: { type: "string", default: "10" },
    top: { type: "string", default: "10" }, at: { type: "string" }, sites: { type: "boolean" },
  } });
  const mod = await loadSimModule();
  const sites = mod.__ctMiningSites;
  if (!sites) throw new Error("mineral site table not found (see simhost.mjs POI_LIST)");
  if (a.sites) {
    for (const s of [...sites].sort((p, q) => p.mineralId.localeCompare(q.mineralId) || PURITY[p.purity] - PURITY[q.purity])) {
      console.log(`${s.mineralId.padEnd(11)} ${s.purity.padEnd(8)} ${s.id.padEnd(18)} (${s.x}, ${s.y})  ${Math.round(Math.hypot(s.x, s.y))} m`);
    }
    return;
  }
  const weights = parseWeights(a.weights);
  const o = { load: Number(a.load), throttle: Number(a.throttle), drillMult: Number(a["drill-mult"]) };
  if (a.at) {
    const [x, y] = a.at.split(",").map(Number);
    show(weights, x, y, picks(sites, weights, o, x, y));
    return;
  }
  const step = Number(a.step), byLayout = new Map();
  for (let x = -MAP; x <= MAP; x += step) {
    for (let y = -MAP; y <= MAP; y += step) {
      const ps = picks(sites, weights, o, x, y), c = cost(weights, ps);
      const key = ps.map(p => p.site.id).join(",");
      const prev = byLayout.get(key);
      if (!prev || c < prev.c) byLayout.set(key, { x, y, ps, c });
    }
  }
  const rows = [...byLayout.values()].sort((p, q) => p.c - q.c).slice(0, Number(a.top));
  console.log(`weights ${a.weights}; ${o.load} units/trip, throttle ${o.throttle} (${DRIVE_M_PER_H * o.throttle} m/h), drill x${o.drillMult}`);
  for (const r of rows) show(weights, r.x, r.y, r.ps);
}

main();
