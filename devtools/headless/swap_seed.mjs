// Replaces a very young save's world seed and regenerates what the seed decides:
// state.seed, planet.plants.recipeMap (Seed Maker recipes) and harvesting.grid (Harvester field).
// Checked against the game generators: only these three differ between two fresh worlds.
//
//   node devtools/headless/swap_seed.mjs --save PATH/save_x.json --seed 2021208502          (dry run)
//   node devtools/headless/swap_seed.mjs --save PATH/save_x.json --seed 2021208502 --apply
//
// --save is required and never auto-detected. Close the game (menu is fine) before --apply.
// Patches the save and its history snapshots (save_x.h0.json, ...); the originals go to
// devtools/.sync-backups/seed-swap/<stamp>/. Refuses a save that already has progress
// (ticks, scanned sectors, collected items) unless --force: scripts and machines would no
// longer fit the new world. Seed choice: docs/plans/scoring_map_seeds.md.
import { copyFileSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { parseArgs } from "node:util";
import { fileURLToPath } from "node:url";
import { Sim } from "./simhost.mjs";

const { values: a } = parseArgs({ options: {
  save: { type: "string" }, seed: { type: "string" }, apply: { type: "boolean" }, force: { type: "boolean" },
} });
if (!a.save || a.seed === undefined) throw new Error("usage: swap_seed.mjs --save FILE --seed N [--apply] [--force]");
const seed = Number(a.seed);
if (!Number.isInteger(seed) || seed < 0 || seed > 2147483646) throw new Error(`bad seed ${a.seed}`);

const dir = dirname(a.save), base = basename(a.save, ".json");
if (!/^save_[a-z0-9]+_[a-z0-9]+$/.test(base)) throw new Error(`not a save state file: ${a.save}`);
const files = [a.save, ...readdirSync(dir).filter(f => f.startsWith(base + ".h") && f.endsWith(".json")).map(f => join(dir, f))];

const sim = await Sim.create({});
sim.newGame(seed);
const fresh = JSON.parse(JSON.stringify(sim.state));

const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const backupDir = join(dirname(fileURLToPath(import.meta.url)), "..", ".sync-backups", "seed-swap", stamp);
if (a.apply) mkdirSync(backupDir, { recursive: true });

for (const file of files) {
  const raw = JSON.parse(readFileSync(file, "utf8"));
  const st = raw.state;
  const h = st.harvesting;
  const progress = st.tickCount > 1000 || h.scannedSectors.length > 0 || h.collectedCount > 0 || h.heldItem;
  if (progress && !a.force) throw new Error(`${basename(file)} has progress (tick ${st.tickCount}); --force to override`);
  const old = st.seed;
  st.seed = seed;
  st.planet.plants.recipeMap = fresh.planet.plants.recipeMap;
  h.grid = fresh.harvesting.grid;
  console.log(`${basename(file)}: seed ${old} -> ${seed}${a.apply ? "" : " (dry run)"}`);
  if (a.apply) {
    copyFileSync(file, join(backupDir, basename(file)));
    writeFileSync(file, JSON.stringify(raw));
  }
}
const rm = fresh.planet.plants.recipeMap;
console.log(`crowncap ${rm.crowncap.join(", ")} | grandbloom ${rm.grandbloom.join(", ")}`);
if (a.apply) console.log(`backups: ${backupDir}`);
