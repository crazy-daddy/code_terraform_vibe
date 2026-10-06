// Harvester surface field of a world seed: port of the game's field generator
// (simworker wE(seed): 8x24 grid, PRNG mp(seed)). The field is a pure function
// of the seed and never respawns, so its total value is the Harvester's whole
// income. Verify the port after a game update: node field.mjs --check SAVE.
//
//   node devtools/headless/field.mjs --seeds 1-20000 [--top 10]   value stats over seeds
//   node devtools/headless/field.mjs --check save_x.json          port vs a save's grid
//   node devtools/headless/field.mjs --show 12412                 print one field
import { readFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";

// Game $p: an item spawns only at Manhattan distance >= minDistance from the
// start cell (the game calls it maxDistance).
export const ITEMS = [
  { id: "soil_sample", value: 50, rarity: 200, minDistance: 0 },
  { id: "basic_plant", value: 125, rarity: 150, minDistance: 0 },
  { id: "organic_matter", value: 250, rarity: 100, minDistance: 2 },
  { id: "mineral_fragment", value: 425, rarity: 80, minDistance: 3 },
  { id: "rare_fungi", value: 850, rarity: 50, minDistance: 5 },
  { id: "crystal_shard", value: 1700, rarity: 35, minDistance: 7 },
  { id: "alien_fossil", value: 2500, rarity: 20, minDistance: 9 },
  { id: "exotic_compound", value: 5000, rarity: 5, minDistance: 12 },
];
export const VALUE = Object.fromEntries(ITEMS.map(i => [i.id, i.value]));
const ROWS = 8, COLS = 24, START = [4, 12]; // E13
const EMPTY_CHANCE = 0.65;

function prng(seed) { // game mp()
  let t = seed | 0;
  return () => {
    t = (t + 1831565813) | 0;
    let e = Math.imul(t ^ (t >>> 15), t | 1);
    e = (e + Math.imul(e ^ (e >>> 7), e | 61)) ^ e;
    return ((e ^ (e >>> 14)) >>> 0) / 4294967296;
  };
}

export const sector = (row, col) => String.fromCharCode(65 + row) + String(col + 1);
export const distance = (row, col) => Math.abs(row - START[0]) + Math.abs(col - START[1]);

// {sector: itemId | null}, as state.harvesting.grid of a fresh world.
export function field(seed) {
  const rand = prng(seed);
  const grid = {};
  for (let row = 0; row < ROWS; row++) {
    for (let col = 0; col < COLS; col++) {
      const id = sector(row, col);
      const d = distance(row, col);
      if (d === 0) { grid[id] = null; continue; }
      const pool = ITEMS.filter(i => d >= i.minDistance);
      if (rand() < EMPTY_CHANCE) { grid[id] = null; continue; }
      let roll = rand() * pool.reduce((sum, i) => sum + i.rarity, 0);
      let pick = pool[0];
      for (const item of pool) {
        roll -= item.rarity;
        if (roll <= 0) { pick = item; break; }
      }
      grid[id] = pick.id;
    }
  }
  return grid;
}

// Allocation-free field() for scans over many seeds (~3 us/seed vs ~120): fills
// `out` (Int8Array(ROWS * COLS), row-major, index row * COLS + col) with ITEMS
// indexes, -1 for empty and the start cell. Same draws as field().
export const GRID_ROWS = ROWS, GRID_COLS = COLS, GRID_START = START;
const CELL_POOLS = [];
for (let row = 0; row < ROWS; row++) {
  for (let col = 0; col < COLS; col++) {
    const d = distance(row, col);
    if (!d) continue;
    const w = ITEMS.filter(i => d >= i.minDistance).map(i => i.rarity);
    CELL_POOLS.push({ index: row * COLS + col, w, total: w.reduce((a, b) => a + b, 0) });
  }
}
export function fieldGrid(seed, out = new Int8Array(ROWS * COLS)) {
  out.fill(-1);
  let t = seed | 0;
  for (let k = 0; k < CELL_POOLS.length; k++) {
    t = (t + 1831565813) | 0;
    let e = Math.imul(t ^ (t >>> 15), t | 1);
    e = (e + Math.imul(e ^ (e >>> 7), e | 61)) ^ e;
    if (((e ^ (e >>> 14)) >>> 0) / 4294967296 < EMPTY_CHANCE) continue;
    t = (t + 1831565813) | 0;
    e = Math.imul(t ^ (t >>> 15), t | 1);
    e = (e + Math.imul(e ^ (e >>> 7), e | 61)) ^ e;
    const c = CELL_POOLS[k];
    let roll = (((e ^ (e >>> 14)) >>> 0) / 4294967296) * c.total, i = 0;
    for (; i < c.w.length - 1; i++) {
      roll -= c.w[i];
      if (roll <= 0) break;
    }
    out[c.index] = i;
  }
  return out;
}

// Total value, items, and value within NEAR cells of the start.
const NEAR = 6;
export function fieldStats(seed) {
  let value = 0, items = 0, near = 0;
  for (const [id, item] of Object.entries(field(seed))) {
    if (!item) continue;
    items++;
    value += VALUE[item];
    if (distance(id.charCodeAt(0) - 65, Number(id.slice(1)) - 1) <= NEAR) near += VALUE[item];
  }
  return { seed, value, items, near };
}

function seedRange(spec) {
  return spec.split(",").flatMap(part => {
    const [lo, hi] = part.split("-").map(Number);
    return Array.from({ length: (hi ?? lo) - lo + 1 }, (_, i) => lo + i);
  });
}

function main() {
  const { values: a } = parseArgs({
    options: { seeds: { type: "string" }, top: { type: "string" }, check: { type: "string" }, show: { type: "string" } },
  });
  if (a.check) {
    const raw = JSON.parse(readFileSync(a.check, "utf8"));
    const st = raw.state ?? raw;
    const fresh = field(st.seed);
    // Collected cells are null in the save; every item left must match.
    const wrong = Object.entries(st.harvesting.grid).filter(([id, item]) => item !== null && fresh[id] !== item);
    console.log(`seed ${st.seed}: ${wrong.length ? `${wrong.length} cells differ: ${JSON.stringify(wrong.slice(0, 5))}` : "port matches"}`);
    process.exitCode = wrong.length ? 1 : 0;
  } else if (a.show) {
    const grid = field(Number(a.show));
    const abbr = id => (id ? id.split("_").map(w => w[0]).join("").toUpperCase() : "..");
    for (let row = 0; row < ROWS; row++) {
      const cells = Array.from({ length: COLS }, (_, col) => (distance(row, col) ? abbr(grid[sector(row, col)]).padEnd(2) : "@@"));
      console.log(String.fromCharCode(65 + row), cells.join(" "));
    }
    console.log(JSON.stringify(fieldStats(Number(a.show))));
  } else if (a.seeds) {
    const rows = seedRange(a.seeds).map(fieldStats);
    for (const key of ["value", "near"]) {
      const sorted = rows.map(r => r[key]).sort((x, y) => x - y);
      const q = p => sorted[Math.floor(p * (sorted.length - 1))];
      console.log(`${key}: min ${q(0)} p10 ${q(0.1)} median ${q(0.5)} p90 ${q(0.9)} max ${q(1)}`);
    }
    for (const r of rows.sort((x, y) => y.value - x.value).slice(0, Number(a.top ?? 10))) console.log(JSON.stringify(r));
  } else {
    console.error("one of --seeds, --check, --show");
    process.exitCode = 2;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
