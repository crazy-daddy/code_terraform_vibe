// Runs the decompiled game simulation headlessly at full CPU speed.
// See docs/cheatsheet/dev_workflow.md §10b.
//
//   node devtools/headless/run.mjs --save save_x.json --hours 4 --out out/run1
//   node devtools/headless/run.mjs --save save_x.json --deploy-templates <dir> --until-tp 150000
//
// --save FILE            game save_<id>.json to start from (running scripts resume)
// --seed N               start a new game instead (default 1)
// --scripts DIR          put every <scriptId>.py in DIR into its slot and run it
// --deploy-templates DIR auto-deploy: give each idle/errored/unscripted machine
//                        DIR/<template>.py, template picked by --deploy-map
// --deploy-map FILE      JSON {typeId prefix: template}; default EARLY_DEPLOY_MAP
// --hours H              game hours to run (default 1; 1 h = 36,000 ticks)
// --until-tp N           stop once the Terraform Index reaches N
// --report-every MIN     metrics line every MIN game minutes (default 10)
// --out DIR              writes console.log, metrics.jsonl, final_save.json
// --profile              per-system wall time at the end
// --skip-systems A,B     systems to leave out (default AchievementSystem; "" runs all)
// --keep-debug           keep the save's per-script debug flags (slow)
// --fail-on-error        exit 1 when any script crashed

import { mkdirSync, readFileSync, readdirSync, writeFileSync, appendFileSync, existsSync } from "node:fs";
import { basename, join } from "node:path";
import { parseArgs } from "node:util";
import { Sim } from "./simhost.mjs";

// Mirrors resolve_machine_template_type() of the earlygame runner's early_game.py.
export const EARLY_DEPLOY_MAP = {
  solar_generator: "solar", pressure_generator: "pressure", oxygen_generator: "o2gen",
  heat_generator: "heater", temp_heater: "heater", harvester: "harvester", scanner: "scanner",
  smelter: "smelter", vehicle_charging_station: "charging_station", charging_station: "charging_station",
  rover: "rover", pioneer: "pioneer", bio_collector: "bio_collector", bio_lab: "bio_lab",
  bio_exchange: "bio_exchange", supply_dock: "supply_dock",
};
const TICKS_PER_SECOND = 10;
const DEPLOY_EVERY_TICKS = 50;
const DEPLOY_COOLDOWN_TICKS = 150;

const { values: a } = parseArgs({
  options: {
    save: { type: "string" }, seed: { type: "string" }, scripts: { type: "string" },
    "deploy-templates": { type: "string" }, "deploy-map": { type: "string" },
    hours: { type: "string" }, "until-tp": { type: "string" }, "report-every": { type: "string" },
    out: { type: "string" }, profile: { type: "boolean" },
    "skip-systems": { type: "string" }, "keep-debug": { type: "boolean" }, "fail-on-error": { type: "boolean" },
  },
});

const sim = await Sim.create({
  skipSystems: a["skip-systems"] === undefined ? undefined : a["skip-systems"].split(",").filter(Boolean),
  keepDebug: a["keep-debug"],
});
if (a.save) sim.load(readFileSync(a.save, "utf8"));
else sim.newGame(Number(a.seed ?? 1));

const out = a.out;
if (out) mkdirSync(out, { recursive: true });
const crashed = new Map();
const writeLine = line => (out ? appendFileSync(join(out, "console.log"), line + "\n") : null);
sim.onConsole(({ scriptId, level, text, tick }) => {
  if (level === "crash") {
    crashed.set(scriptId, text);
    console.log(`[tick ${tick}] CRASH ${scriptId}: ${text}`);
  }
  writeLine(`[tick ${tick}] [${level}] [${scriptId}] ${text}`);
});

if (a.scripts) {
  for (const f of readdirSync(a.scripts).filter(f => f.endsWith(".py"))) {
    const id = basename(f, ".py");
    const r = sim.setScript(id, readFileSync(join(a.scripts, f), "utf8"));
    console.log(`script ${id}: ${r.status}`);
  }
}

const deployDir = a["deploy-templates"];
const deployMap = a["deploy-map"] ? JSON.parse(readFileSync(a["deploy-map"], "utf8")) : EARLY_DEPLOY_MAP;
const lastDeploy = new Map();
function templateFor(typeId) {
  if (deployMap[typeId]) return deployMap[typeId];
  const key = Object.keys(deployMap).find(k => typeId?.startsWith(k));
  return key ? deployMap[key] : null;
}
function deployPass() {
  const st = sim.state;
  for (const m of Object.values(st.machines)) {
    const tpl = templateFor(m.typeId);
    if (!tpl || !m.scriptSlots?.includes(m.id) || m.powered === false) continue;
    const file = join(deployDir, `${tpl}.py`);
    if (!existsSync(file)) continue;
    const s = st.scripts[m.id];
    const idle = !s || !s.source?.trim() || s.status === "idle" || s.status === "error";
    if (!idle || st.tickCount - (lastDeploy.get(m.id) ?? -Infinity) < DEPLOY_COOLDOWN_TICKS) continue;
    lastDeploy.set(m.id, st.tickCount);
    const r = sim.setScript(m.id, readFileSync(file, "utf8"));
    writeLine(`[tick ${st.tickCount}] [deploy] ${tpl} -> ${m.id}: ${r.status}`);
  }
}

function metrics(wallStart, startTick) {
  const st = sim.state;
  const scripts = Object.values(st.scripts);
  const ticks = st.tickCount - startTick;
  const wall = (performance.now() - wallStart) / 1000;
  return {
    tick: st.tickCount,
    gameHours: +(ticks / TICKS_PER_SECOND / 3600).toFixed(3),
    tp: Math.round(sim.terraformIndex()),
    credits: Math.round(st.player?.credits ?? 0),
    machines: Object.keys(st.machines).length,
    running: scripts.filter(s => s.status === "running").length,
    errored: scripts.filter(s => s.status === "error").length,
    wallS: +wall.toFixed(1),
    speedup: Math.round(ticks / TICKS_PER_SECOND / Math.max(wall, 1e-9)),
  };
}

const total = Math.round(Number(a.hours ?? 1) * 3600 * TICKS_PER_SECOND);
const reportEvery = Math.round(Number(a["report-every"] ?? 10) * 60 * TICKS_PER_SECOND);
const untilTp = a["until-tp"] ? Number(a["until-tp"]) : Infinity;
const startTick = sim.state.tickCount;
const wallStart = performance.now();
const report = () => {
  const m = metrics(wallStart, startTick);
  console.log(JSON.stringify(m));
  if (out) appendFileSync(join(out, "metrics.jsonl"), JSON.stringify(m) + "\n");
};
report();
for (let t = 1; t <= total; t++) {
  sim.tick();
  if (deployDir && t % DEPLOY_EVERY_TICKS === 0) deployPass();
  if (t % reportEvery === 0) report();
  if (sim.terraformIndex() >= untilTp) { console.log(`reached ${untilTp} TP`); break; }
}
report();

if (out) writeFileSync(join(out, "final_save.json"), sim.serialize());
if (a.profile) {
  const ms = sim.systemMs();
  const sum = Object.values(ms).reduce((x, y) => x + y, 0);
  for (const [k, v] of Object.entries(ms)) console.log(`${k.padEnd(32)} ${(v / 1000).toFixed(2).padStart(8)} s ${(100 * v / sum).toFixed(1).padStart(5)} %`);
}
if (crashed.size) console.log(`${crashed.size} script(s) crashed: ${[...crashed.keys()].join(", ")}`);
process.exit(a["fail-on-error"] && crashed.size ? 1 : 0);
