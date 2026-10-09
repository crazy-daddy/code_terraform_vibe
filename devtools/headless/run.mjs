// Runs the decompiled game simulation headlessly at full CPU speed.
// See docs/cheatsheet/dev_workflow.md §10b.
//
//   node devtools/headless/run.mjs --save save_x.json --hours 4 --out out/run1
//   node devtools/headless/run.mjs --save save_x.json --deploy-templates <dir> --until-tp 150000
//
// --save FILE            game save_<id>.json (or .json.gz) to start from (running scripts resume)
// --seed N               start a new game instead (default 1)
// --field-seed N         with --save: replace the Harvester field with seed N's fresh
//                        field (field.mjs), the rest of the world stays the save's
// --scripts DIR          put every <scriptId>.py in DIR into its slot; runs new slots and
//                        restarts running ones (a stopped slot stays stopped). With
//                        --save, build DIR with save_scripts.py: the repo's current
//                        scripts mapped onto the save's slots, plus DIR/lib for --libs
// --deploy-templates DIR auto-deploy: give each idle/errored/unscripted machine
//                        <template>.py from DIR (searched recursively, e.g.
//                        scripts/0_cold_boot), template picked by --deploy-map
// --deploy-map FILE      JSON {typeId prefix: template}; default EARLY_DEPLOY_MAP
// --hours H              game hours to run (default 1; 1 h = 36,000 ticks)
// --until-tp N           stop once the Terraform Index reaches N
// --report-every MIN     metrics line every MIN game minutes (default 10)
// --out DIR              writes console.log, metrics.jsonl, final_save.json
// --profile              per-system wall time at the end
// --skip-systems A,B     systems to leave out (default AchievementSystem; "" runs all)
// --keep-debug           keep the save's per-script debug flags (slow)
// --keep-version-guard   keep the save's confirmed game build; by default the load
//                        confirms the running build, so an older save's scripts
//                        don't halt at lib/version_guard.py
// --log-levels JSON|FILE console.log_levels entries over the default {"*": "debug"},
//                        e.g. '{"power": "trace"}'; "save" keeps the save's dict
// --paid-debug           debug console lines pause the script as in game (default:
//                        free, so only info/warn/error lines cost game time)
// --libs DIR             replace the save's lib/ modules with DIR/*.py and add the ones
//                        it lacks (e.g. scripts/4_controlpanel/lib), so old saves run current libs
// --sticky-fluids        empty tanks keep their last fluid type for the network cache
//                        (stops rebuilds when a tank runs dry every tick; optional
//                        since build e1986ce, saves ~1 ms/tick)
// --park                 park passive machines' scripts (passive.mjs); wake on triggers
// --set ID.KEY=VALUE     set machines[ID].data[KEY] after load (repeatable), e.g. to
//                        buffer a reservoir that forces fluid-network rebuilds
// --policy FILE          build-order plan (policy.mjs) buys, deploys and recycles;
//                        solar.py's buyer is switched off (sun tracking stays)
// --until-pioneer        with --until-tp: also wait until the Pioneer is scouting
// --lib-tier DIR         with --deploy-templates: once DIR/.criteria's techs are unlocked
//                        (e.g. scripts/4_controlpanel at Data Archive), add DIR/lib as the
//                        save's lib/ modules, give every machine DIR's template (falling back
//                        to --deploy-templates), and run DIR's orchestrator_automation.py in
//                        a new Automation, as scripts_sync does on a tier switch
// --fail-on-error        exit 1 when any script crashed

import { mkdirSync, readFileSync, readdirSync, writeFileSync, appendFileSync, statSync } from "node:fs";
import { basename, join } from "node:path";
import { parseArgs } from "node:util";
import { Sim } from "./simhost.mjs";
import { readSaveText } from "./savefile.mjs";
import { Parker } from "./passive.mjs";
import { Policy, netWorth, pillars, slotsUsed } from "./policy.mjs";
import { field, sector } from "./field.mjs";

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
    save: { type: "string" }, seed: { type: "string" }, "field-seed": { type: "string" }, scripts: { type: "string" },
    "deploy-templates": { type: "string" }, "deploy-map": { type: "string" },
    hours: { type: "string" }, "until-tp": { type: "string" }, "report-every": { type: "string" },
    out: { type: "string" }, profile: { type: "boolean" },
    "skip-systems": { type: "string" }, "keep-debug": { type: "boolean" }, "keep-version-guard": { type: "boolean" }, "log-levels": { type: "string" }, "paid-debug": { type: "boolean" }, libs: { type: "string" },
    park: { type: "boolean" }, "sticky-fluids": { type: "boolean" }, set: { type: "string", multiple: true }, "fail-on-error": { type: "boolean" },
    policy: { type: "string" }, "until-pioneer": { type: "boolean" }, "lib-tier": { type: "string" },
  },
});

function parseLogLevels(arg) {
  if (arg === undefined) return undefined;
  if (arg === "save") return null;
  return JSON.parse(arg.trimStart().startsWith("{") ? arg : readFileSync(arg, "utf8"));
}

const sim = await Sim.create({
  skipSystems: a["skip-systems"] === undefined ? undefined : a["skip-systems"].split(",").filter(Boolean),
  keepDebug: a["keep-debug"],
  keepVersionGuard: a["keep-version-guard"],
  logLevels: parseLogLevels(a["log-levels"]),
  paidDebug: a["paid-debug"],
  stickyFluids: a["sticky-fluids"],
});
const libs = a.libs ? Object.fromEntries(readdirSync(a.libs).filter(f => f.endsWith(".py"))
  .map(f => [basename(f, ".py"), readFileSync(join(a.libs, f), "utf8")])) : undefined;
if (a.save) {
  sim.load(readSaveText(a.save), { libs });
  if (sim.libraries) console.log(`libs: ${sim.libraries.replaced.length} replaced` +
    (sim.libraries.added.length ? `, added: ${sim.libraries.added.join(", ")}` : ""));
} else {
  if (libs) console.warn("--libs needs --save: a new game has no lib/ modules");
  sim.newGame(Number(a.seed ?? 1));
}
if (a["field-seed"] !== undefined) {
  if (!a.save) throw new Error("--field-seed needs --save");
  const grid = field(Number(a["field-seed"]));
  const harvester = Object.values(sim.state.machines).find(m => m.typeId === "harvester");
  if (harvester) grid[sector(harvester.data.posRow, harvester.data.posCol)] = null; // never an item under it
  sim.state.harvesting.grid = grid;
}
for (const spec of a.set ?? []) {
  const [, id, key, value] = /^([^.]+)\.([^=]+)=(.*)$/.exec(spec) ?? [];
  if (!sim.state.machines[id]) throw new Error(`--set: no machine ${id}`);
  sim.state.machines[id].data[key] = Number(value);
}
const parker = a.park ? new Parker(sim) : null;
if (parker) sim.park(parker);

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
    const slot = sim.state.scripts[id];
    const run = !slot || slot.status === "running";
    const r = sim.setScript(id, readFileSync(join(a.scripts, f), "utf8"), { run });
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
// {template name: path}, first match wins (DIR may hold tier subfolders; lib/ is
// not a template).
let templates = new Map();
function indexTemplates(map, dir) {
  if (!dir) return map;
  for (const f of readdirSync(dir).sort()) {
    const path = join(dir, f);
    if (statSync(path).isDirectory()) { if (!f.startsWith("_") && f !== "lib") indexTemplates(map, path); }
    else if (f.endsWith(".py") && !map.has(basename(f, ".py"))) map.set(basename(f, ".py"), path);
  }
  return map;
}
indexTemplates(templates, deployDir);
// With a policy, the tier-0 solar.py keeps tracking the sun but never becomes the buyer.
const BUYER_OFF = [/is_master = \(self\.id == get_master_solar_id\(\)\)/, "is_master = False"];
// scripts_sync template placeholders ${NAME} / ${NAME:default}: the default, as for a new slot.
const PLACEHOLDER = /\$\{(\w+)(?::([^}]*))?\}/g;
function readTemplate(name) {
  const file = templates.get(name);
  if (!file) return null;
  const src = readFileSync(file, "utf8").replace(PLACEHOLDER, (_, _name, def) => def ?? "");
  if (name !== "solar" || !a.policy || libSwitched) return src;
  if (!BUYER_OFF[0].test(src)) throw new Error("--policy: solar.py master election line not found; update BUYER_OFF in run.mjs");
  return src.replace(BUYER_OFF[0], BUYER_OFF[1]);
}

// --lib-tier: the tier switch scripts_sync makes once the save meets DIR/.criteria.
const libTier = a["lib-tier"];
if (libTier && !deployDir) throw new Error("--lib-tier needs --deploy-templates");
const libCriteria = libTier ? JSON.parse(readFileSync(join(libTier, ".criteria"), "utf8")).tech ?? [] : [];
let libSwitched = false;
function libTierReached() {
  const tech = sim.state.unlockedTech ?? [];
  return libCriteria.every(t => tech.includes(t));
}
function switchToLibTier() {
  libSwitched = true;
  const libDir = join(libTier, "lib");
  const failed = [];
  for (const f of readdirSync(libDir).filter(f => f.endsWith(".py")).sort()) {
    const r = sim.createLibrary(basename(f, ".py"), readFileSync(join(libDir, f), "utf8"));
    if (!r.ok) failed.push(`${f}: ${r.status}`);
  }
  templates = indexTemplates(indexTemplates(new Map(), libTier), deployDir);
  writeLine(`[tick ${sim.state.tickCount}] [lib-tier] ${libTier}: lib/ added${failed.length ? `, failed: ${failed.join(", ")}` : ""}`);
  if (policy) {
    policy.libTier();
    sim.setArchive("early_buyer", { generators: false, rovers: policy.plan.rovers ?? 0, pioneer: !!policy.plan.pioneer });
  }
  const automation = readTemplate("orchestrator_automation");
  if (automation) {
    const r = sim.createAutomation(automation);
    writeLine(`[tick ${sim.state.tickCount}] [lib-tier] orchestrator_automation -> ${r.scriptId ?? "-"}: ${r.status}`);
  }
  // Every machine whose template changed restarts on the new one (scripts_sync push).
  for (const m of Object.values(sim.state.machines)) {
    const tpl = templateFor(m.typeId);
    if (!tpl || !m.scriptSlots?.includes(m.id)) continue;
    const src = readTemplate(tpl);
    if (src && sim.state.scripts[m.id]?.source !== src) deploy(m, tpl, src);
  }
}
function deploy(m, name, source) {
  lastDeploy.set(m.id, sim.state.tickCount);
  const r = sim.setScript(m.id, source);
  writeLine(`[tick ${sim.state.tickCount}] [deploy] ${name} -> ${m.id}: ${r.status}`);
}
function deployPass() {
  const st = sim.state;
  for (const m of Object.values(st.machines)) {
    const tpl = templateFor(m.typeId);
    if (!tpl || !m.scriptSlots?.includes(m.id) || m.powered === false) continue;
    const s = st.scripts[m.id];
    const idle = !s || !s.source?.trim() || s.status === "idle" || s.status === "error";
    if (st.tickCount - (lastDeploy.get(m.id) ?? -Infinity) < DEPLOY_COOLDOWN_TICKS) continue;
    if (!idle) continue;
    const src = readTemplate(tpl);
    if (src) deploy(m, tpl, src);
  }
}

const policy = a.policy ? new Policy(sim, JSON.parse(readFileSync(a.policy, "utf8")), line => writeLine(`[tick ${sim.state.tickCount}] ${line}`)) : null;
if (policy && deployDir) {
  // Checkpoint scripts keep running their saved solar.py, buyer included.
  for (const m of Object.values(sim.state.machines)) {
    if (m.typeId === "solar_generator" && m.scriptSlots?.includes(m.id)) deploy(m, "solar", readTemplate("solar"));
  }
}

// Brownout: batteries empty while the load exceeds generation.
let brownoutTicks = 0;
function powerCheck() {
  const pw = sim.state.planet.power;
  if (pw && pw.stored < 1 && pw.consumed > pw.generated + 1e-6) brownoutTicks++;
}

// Pioneer ready: deployed, Nav + Sonar + a Battery Holder (any tier) mounted, script running.
function pioneerReady() {
  const st = sim.state;
  return Object.values(st.machines).some(m => m.typeId === "pioneer" &&
    ["nav_module", "sonar_module", "battery_holder"].every(id => (m.mountedModules ?? []).some(mod => mod?.startsWith(id))) &&
    st.scripts[m.id]?.status === "running");
}

function poiCounts() {
  const mining = sim.state.journal?.planets?.nocturna?.mining ?? {};
  return { discovered: mining.discoveredSites?.length ?? 0, surveyed: mining.surveyedSites?.length ?? 0 };
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
    pillars: Object.fromEntries(Object.entries(pillars(st)).filter(([k]) => k !== "tp").map(([k, v]) => [k, +v.toFixed(4)])),
    atmo: Object.fromEntries(Object.entries(st.researchRates ?? {}).map(([k, v]) => [k, +Number(v?.lastValue ?? 0).toFixed(3)])),
    credits: Math.round(st.player?.credits ?? 0),
    netWorth: Math.round(netWorth(st)),
    slots: slotsUsed(st),
    pois: poiCounts(),
    pioneerReady: pioneerReady(),
    brownoutS: +(brownoutTicks / TICKS_PER_SECOND).toFixed(1),
    ...(policy ? { stage: policy.stage } : {}),
    machines: Object.keys(st.machines).length,
    running: scripts.filter(s => s.status === "running").length,
    errored: scripts.filter(s => s.status === "error").length,
    wallS: +wall.toFixed(1),
    speedup: +(ticks / TICKS_PER_SECOND / Math.max(wall, 1e-9)).toFixed(2),
    ...(parker ? { wakes: parker.wakes } : {}),
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
let reachedTick = null;
let tpTick = null; // first tick at --until-tp, Pioneer or not
for (let t = 1; t <= total; t++) {
  policy?.pass();
  sim.tick();
  powerCheck();
  if (tpTick === null && sim.terraformIndex() >= untilTp) tpTick = sim.state.tickCount;
  if (libTier && !libSwitched && t % DEPLOY_EVERY_TICKS === 0 && libTierReached()) switchToLibTier();
  if (deployDir && t % DEPLOY_EVERY_TICKS === 0) deployPass();
  if (t % reportEvery === 0) report();
  if (sim.terraformIndex() >= untilTp && (!a["until-pioneer"] || (t % DEPLOY_EVERY_TICKS === 0 && pioneerReady()))) {
    reachedTick = sim.state.tickCount;
    console.log(`reached ${untilTp} TP${a["until-pioneer"] ? " with the Pioneer scouting" : ""} after ${((reachedTick - startTick) / TICKS_PER_SECOND / 3600).toFixed(3)} h`);
    break;
  }
}
report();

if (out) {
  writeFileSync(join(out, "final_save.json"), sim.serialize());
  const hours = tick => tick === null ? null : +((tick - startTick) / TICKS_PER_SECOND / 3600).toFixed(4);
  writeFileSync(join(out, "summary.json"), JSON.stringify({ reachedH: hours(reachedTick), tpH: hours(tpTick), crashed: [...crashed.keys()], ...metrics(wallStart, startTick) }, null, 1));
}
if (a.profile) {
  const ms = sim.systemMs();
  const sum = Object.values(ms).reduce((x, y) => x + y, 0);
  for (const [k, v] of Object.entries(ms)) console.log(`${k.padEnd(32)} ${(v / 1000).toFixed(2).padStart(8)} s ${(100 * v / sum).toFixed(1).padStart(5)} %`);
}
if (crashed.size) console.log(`${crashed.size} script(s) crashed: ${[...crashed.keys()].join(", ")}`);
process.exit(a["fail-on-error"] && crashed.size ? 1 : 0);
