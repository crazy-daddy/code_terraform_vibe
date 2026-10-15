// Simworker anchors for the stand-in patches (docs/headless/anchors.md).
//
// INSTANT_PATTERN shortens the builder's construction wait while the harness
// sets `globalThis.__ctInstantBuild` (standins.mjs `instant`).
// SCALE_PATTERNS multiplies the per-machine work of a terraformer by its
// `data.scale ?? 1` at the three sites that do that work (the atmosphere
// loops, the fluid port drain, the power draw), so one record with
// `data.scale = N` stands in for N identical machines (standins.mjs `scale`).
// The two building counters count such a record as N buildings: the
// undeployed members' slots stay taken, so `buildings_used()`, `is_full()`,
// the OutpostRef fields and the overcrowding factor (every `throughput`
// machine at that outpost) read as with N real machines.
// Every pattern is anchored on stable strings only (property names, type ids)
// and captures the minified locals it needs from the matched line; each must
// match exactly once or the whole feature stays off (a half-scaled worker is
// worse than none). The script gate (`scriptSlots.some(running)`) needs no
// patch: the survivor keeps one running script.
//
// CLI: `node devtools/simulation/headless/anchors.mjs` runs every patch on the
// current internals/ worker, prints the feature table and exits 1 on any miss
// (dev_workflow.md §10c after a game update).

import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
// Static import: simhost.mjs imports this file too, and a cycle of static
// imports is fine (patchSimworker is only called from main()); a dynamic
// import awaited at top level would deadlock the cycle.
import { DEFAULT_SIMWORKER, patchSimworker } from "./simhost.mjs";

// A `let <data> = <machine>.data;` within the enclosing loop, found by looking
// back from the anchor (the loops declare it 16-24 lines above the output
// line). A `for (` between the two means a different loop, and a brace depth
// below 0 means the declaration sits in a closed sibling block: no capture.
const DATA_LOCAL = /let (\w+) = (\w+)\.data;\n/g;
const LOOKBACK_CHARS = 4000;
export function dataLocalBefore(src, index) {
  const window = src.slice(Math.max(0, index - LOOKBACK_CHARS), index);
  const hits = [...window.matchAll(DATA_LOCAL)];
  if (!hits.length) return null;
  const last = hits[hits.length - 1];
  const between = window.slice(last.index + last[0].length);
  if (/\bfor \(/.test(between)) return null;
  let depth = 0;
  for (const ch of between) {
    if (ch === "{") depth++;
    else if (ch === "}" && --depth < 0) return null;
  }
  return last[1];
}

// {key: {what, re, data?, replace(m, data)}}. `data: true` means the data
// local of the enclosing loop is captured with dataLocalBefore(); the other
// sites name the machine in the matched line itself.
export const SCALE_PATTERNS = {
  o2: {
    what: "atmosphere O2 loop (Math.min(<output>, <atmosphere>.co2))",
    re: /(?<![\w$])let (\w+) = Math\.min\((\w+), (\w+)\.co2\);/g,
    data: true,
    replace: (m, d) => `let ${m[1]} = Math.min(${m[2]} * (${d}.scale ?? 1), ${m[3]}.co2);`,
  },
  heat: {
    what: "atmosphere heat loop (.heatUnits = <add>(<state>.planet.temperature.heatUnits, <output>))",
    re: /\.heatUnits = (\w+)\((\w+)\.planet\.temperature\.heatUnits, (\w+)\);/g,
    data: true,
    replace: (m, d) => `.heatUnits = ${m[1]}(${m[2]}.planet.temperature.heatUnits, ${m[3]} * (${d}.scale ?? 1));`,
  },
  pressure: {
    what: "atmosphere pressure loop (<atmosphere>.pressure = <add>(<atmosphere>.pressure, <output> * <dt>))",
    re: /(?<![\w$.])(\w+)\.pressure = (\w+)\(\1\.pressure, (\w+) \* (\w+)\);/g,
    data: true,
    replace: (m, d) => `${m[1]}.pressure = ${m[2]}(${m[1]}.pressure, ${m[3]} * ${m[4]} * (${d}.scale ?? 1));`,
  },
  drain: {
    what: "fluid port drain (`${<port>.portType}_level` then <port>.ratePerGameHour * <hours>)",
    re: /let (\w+) = `\$\{(\w+)\.portType\}_level`;\n(\s*)let (\w+) = Math\.max\(0, (\w+)\.data\[\1\] \?\? 0\);\n\s*let (\w+) = \2\.ratePerGameHour \* (\w+);/g,
    replace: m => `${m[0].slice(0, -1)} * (${m[5]}.data.scale ?? 1);`,
  },
  draw: {
    what: "power draw (return <base> * <tierFactor>(<machine>.data.tier ?? 1, <machine>.data.tierUpgrade ?? 0))",
    re: /return (\w+) \* (\w+)\((\w+)\.data\.tier \?\? 1, \3\.data\.tierUpgrade \?\? 0\);/g,
    replace: m => `return ${m[1]} * ${m[2]}(${m[3]}.data.tier ?? 1, ${m[3]}.data.tierUpgrade ?? 0) * (${m[3]}.data.scale ?? 1);`,
  },
  // The per-outpost building count (the outpost API's buildings_used and
  // is_full, the OutpostRef fields, the overcrowding factor's fallback).
  count: {
    what: "outpost building count (machines filtered by (<m>.locationId ?? `outpost_home`) === <outpost> && <isBuilding>(<m>.typeId), .length)",
    re: /return Object\.values\((\w+)\.machines\)\.filter\((\w+) => \(\2\.locationId \?\? `outpost_home`\) === (\w+) && (\w+)\(\2\.typeId\)\)\.length;/g,
    replace: m => `return Object.values(${m[1]}.machines).filter(${m[2]} => (${m[2]}.locationId ?? \`outpost_home\`) === ${m[3]} && ${m[4]}(${m[2]}.typeId)).reduce((__ctSum, __ctM) => __ctSum + (__ctM.data?.scale ?? 1), 0);`,
  },
  // The per-tick map of building counts by outpost (the overcrowding factor
  // of every system loop).
  counts: {
    what: "building count map (if (!<isBuilding>(<m>.typeId)) continue; <map>.set(<loc>, (<map>.get(<loc>) ?? 0) + 1))",
    re: /if \(!(\w+)\((\w+)\.typeId\)\) \{\n\s*continue;\n\s*\}\n\s*let (\w+) = \2\.locationId \?\? `outpost_home`;\n\s*(\w+)\.set\(\3, \(\4\.get\(\3\) \?\? 0\) \+ 1\);/g,
    replace: m => `${m[0].slice(0, -"+ 1);".length)}+ (${m[2]}.data?.scale ?? 1));`,
  },
};

// Construction `instant` (standins.mjs): the builder's construction command
// yields a scheduler `wait` for the whole remaining build time
// (`ticks: <toTicks>(<hours>)`), so finishing the job in the state alone
// leaves the vehicle asleep. The patch makes that wait INSTANT_WAIT_TICKS
// while `globalThis.__ctInstantBuild` is set: tick +1 the harness moves the
// job's end to now (before the tick) and the ConstructionSystem completes it;
// onResume runs the same completion check itself, so any resume from tick +1
// on reports ok. 2 ticks keeps the system's completion and the command's apart
// (exactly one of them removes the job). Anchored on the stable strings around
// the wait.
export const INSTANT_WAIT_TICKS = 2;
export const INSTANT_PATTERN = {
  what: "construction wait (type: `wait`, ticks: <toTicks>(<hours>), onResume reading .planet.clock.elapsedTime + 1 / .game.tickRate)",
  re: /type: `wait`,\n(\s*)ticks: (\w+)\((\w+)\),\n(\s*)onResume: \(\) => \{\n(\s*)let (\w+) = (\w+)\.planet\.clock\.elapsedTime \+ 1 \/ (\w+)\.game\.tickRate;/g,
  replace: m => `type: \`wait\`,\n${m[1]}ticks: globalThis.__ctInstantBuild ? ${INSTANT_WAIT_TICKS} : ${m[2]}(${m[3]}),\n${m[4]}onResume: () => {\n${m[5]}let ${m[6]} = ${m[7]}.planet.clock.elapsedTime + 1 / ${m[8]}.game.tickRate;`,
};

// Applies INSTANT_PATTERN when it matches exactly once. Returns {src, hits, why}.
export function patchInstantBuild(src) {
  const found = [...src.matchAll(INSTANT_PATTERN.re)];
  if (found.length !== 1) return { src, hits: found.length, why: `${INSTANT_PATTERN.what} found ${found.length}x (want 1)` };
  const m = found[0];
  return { src: src.slice(0, m.index) + INSTANT_PATTERN.replace(m) + src.slice(m.index + m[0].length), hits: 1, why: null };
}

// Applies SCALE_PATTERNS when every pattern matches exactly once (and its
// data local is found). Returns {src, hits: {key: n}, why}: `why` names the
// failing pattern(s) and the source is then unchanged.
export function patchScale(src) {
  const hits = {};
  const edits = [];
  const why = [];
  for (const [key, p] of Object.entries(SCALE_PATTERNS)) {
    const found = [...src.matchAll(p.re)];
    hits[key] = found.length;
    if (found.length !== 1) { why.push(`${p.what} found ${found.length}x (want 1)`); continue; }
    const m = found[0];
    let data = null;
    if (p.data) {
      data = dataLocalBefore(src, m.index);
      if (!data) { why.push(`${p.what}: no \`let <data> = <machine>.data;\` in its loop`); continue; }
    }
    edits.push({ index: m.index, length: m[0].length, text: p.replace(m, data) });
  }
  if (why.length) return { src, hits, why: why.join("; ") };
  edits.sort((a, b) => b.index - a.index);
  for (const e of edits) src = src.slice(0, e.index) + e.text + src.slice(e.index + e.length);
  return { src, hits, why: null };
}

function main() {
  const path = process.env.CT_SIMWORKER || DEFAULT_SIMWORKER;
  const raw = readFileSync(path, "utf8");
  const t0 = performance.now();
  const { features, warnings } = patchSimworker(raw);
  const scale = patchScale(raw);
  console.log(`simworker: ${path} (${(performance.now() - t0).toFixed(0)} ms)`);
  console.log("feature            on");
  for (const [k, v] of Object.entries(features)) console.log(`${k.padEnd(18)} ${v ? "yes" : "NO"}`);
  console.log("scale anchor       matches (want 1)");
  for (const [k, n] of Object.entries(scale.hits)) console.log(`${k.padEnd(18)} ${n}`);
  console.log(`${"instant wait".padEnd(18)} ${patchInstantBuild(raw).hits}`);
  for (const w of warnings) console.log(`[headless] simworker changed: ${w}`);
  const bad = warnings.length > 0 || Object.values(features).some(v => !v);
  if (bad) console.log("FAIL: update the pattern(s) above (docs/headless/anchors.md, After a game update)");
  process.exit(bad ? 1 : 0);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
