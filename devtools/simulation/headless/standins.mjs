// Per-subsystem stand-ins for headless runs: a test that targets one subsystem
// runs the others as cheap models or off, with the target's inputs and outputs
// kept flowing (scenario `flows`), and with the step allowance the target would
// have in the full base (virtual script count). Design, boundaries and the
// state shapes used here: docs/headless/standins.md. Scenario format:
// docs/headless/scenarios.md.
//
// Phase 0: registry, classification, `off`, `park`, power `trim`, flows,
// archive seeds, virtual script count. Phase 1: terraforming `standin`, the
// Level-1 Python scripts in standins/ and the JS steam guard. Phase 2:
// terraforming `scale` on the anchors.mjs simworker patch. Phase 3: the
// logistics `mover`. Later phases add the producer modes; their mode names
// are listed in MODES as planned so a scenario naming them fails with the
// phase instead of running silently.

import { readFileSync } from "node:fs";
import { Parker, PASSIVE_TYPES } from "./passive.mjs";
import { Flows, HOME_OUTPOST, addAt, countAt, takeAt } from "./stacks.mjs";
import { modeOf } from "./scenario.mjs";

// Machine type -> group, grouped by chain (who feeds whom), not by what a machine
// looks like. `reason` is for the next person moving a type. A scenario's
// `assign: {typeId: group}` overrides a row.
export const TYPES = {
  temp_heater: { group: "terraforming", reason: "heat pillar" },
  heat_generator: { group: "terraforming", reason: "heat pillar (older type id)" },
  oxygen_generator: { group: "terraforming", reason: "O2 pillar" },
  pressure_generator: { group: "terraforming", reason: "pressure pillar" },

  solar_generator: { group: "power", reason: "generator" },
  steam_turbine: { group: "power", reason: "generator" },
  oil_generator: { group: "power", reason: "generator" },
  reactor: { group: "power", reason: "generator" },
  oil_pump: { group: "power", reason: "feeds oil generators" },
  water_pump: { group: "power", reason: "feeds steam, Mk III terraformers and plants" },
  thermal_cap: { group: "power", reason: "steam source" },
  steam_condenser: { group: "power", reason: "steam to water" },
  charging_station: { group: "power", reason: "vehicle charge, grid consumer" },
  vehicle_charging_station: { group: "power", reason: "vehicle charge (older type id)" },
  fuel_assembler: { group: "power", reason: "reactor fuel" },
  lead_cask: { group: "power", reason: "reactor fuel transport" },

  drone_small: { group: "logistics", reason: "hauler / extractor" },
  drone_medium: { group: "logistics", reason: "hauler / extractor" },
  drone_large: { group: "logistics", reason: "hauler / extractor" },
  drone_station: { group: "logistics", reason: "drone depot" },
  drone_station_medium: { group: "logistics", reason: "drone depot" },
  drone_station_large: { group: "logistics", reason: "drone depot" },
  drone_service_station: { group: "logistics", reason: "drone service" },
  pioneer: { group: "logistics", reason: "hauler, miner, builder" },
  rover: { group: "logistics", reason: "early miner" },
  supply_dock: { group: "logistics", reason: "order shipping" },

  smelter: { group: "factory", reason: "ore to ingots" },
  fabricator: { group: "factory", reason: "crafting" },
  garbage_disposal: { group: "factory", reason: "waste sink at the factory" },
  mining_drill: { group: "factory", reason: "ore source for the smelters" },
  mining_drill_industrial: { group: "factory", reason: "ore source for the smelters" },
  mining_drill_heavy: { group: "factory", reason: "ore source for the smelters" },

  harvester: { group: "plants", reason: "field keeper" },
  crop_automator: { group: "plants", reason: "field machine" },
  scanner: { group: "plants", reason: "field scan" },
  sprinkler: { group: "plants", reason: "field provider" },
  grow_lamp: { group: "plants", reason: "field provider" },
  dispenser: { group: "plants", reason: "field provider" },
  seed_maker: { group: "plants", reason: "fabricator-like, only the harvester uses it" },
  plant_terraformer: { group: "plants", reason: "fabricator-like, fed by the harvester, output km2" },

  bio_lab: { group: "biolab", reason: "life-form chain" },
  bio_collector: { group: "biolab", reason: "life-form chain" },
  bio_exchange: { group: "biolab", reason: "life-form chain" },
  bio_caster: { group: "biolab", reason: "life-form chain" },
  bio_luminizer: { group: "biolab", reason: "life-form chain" },
  bio_processor: { group: "biolab", reason: "life-form chain" },
  bio_conditioner: { group: "biolab", reason: "life-form chain" },
  dna_sequencer: { group: "biolab", reason: "life-form chain" },

  habitat: { group: "wildlife", reason: "revival" },
  feed_maker: { group: "wildlife", reason: "feeds habitats" },
  refiner: { group: "wildlife", reason: "fluid converter, wildlife only" },
  exotic_gas_cap: { group: "wildlife", reason: "exotic fluid source" },
  exotic_spring_tap: { group: "wildlife", reason: "exotic fluid source" },

  essence_liquifier: { group: "biomass", reason: "biomass chain" },
  biomass_mixer: { group: "biomass", reason: "biomass chain" },

  weather_station: { group: "weather", reason: "forecast" },

  // Fixtures with a script slot the harness never touches.
  oxygen_sensor: { group: "system", reason: "sensor script" },
  pressure_sensor: { group: "system", reason: "sensor script" },
  thermometer: { group: "system", reason: "sensor" },
  clock: { group: "system", reason: "fixture" },
  gps: { group: "system", reason: "fixture" },
  inventory: { group: "system", reason: "fixture" },
};

// Groups, their boundary (what a scenario must feed or drain when the group is
// off: documentation and the `off` warning), and their modes.
export const GROUPS = {
  terraforming: { produces: ["atmosphere (heat, O2, pressure)"], consumes: ["power", "steam_in / water_in (Mk III)", "fuel rods (Mk IV)"], items: false },
  power: { produces: ["grid power", "steam", "water", "oil"], consumes: ["oil", "steam", "water"], items: false },
  orchestrator: { produces: ["production.demand", "power.shedded", "cash.budget", "script.parked", "fleet.commission", "build.jobs"], consumes: ["telemetry keys"], items: false },
  logistics: { produces: ["items at outposts (logistics.requests served)", "ore at smelters", "construction"], consumes: ["logistics.requests", "power"], items: true },
  factory: { produces: ["ingots", "crafted items", "kits"], consumes: ["ore", "ingots", "fabricator.orders", "production.demand"], items: true },
  plants: { produces: ["forage", "seeds", "km2 (plants pillar)"], consumes: ["seeds", "water", "salt", "fertilizer"], items: true },
  biolab: { produces: ["samples", "life-form items"], consumes: ["reagents", "power"], items: true },
  wildlife: { produces: ["revived species", "Insight"], consumes: ["feed", "refined fluids"], items: true },
  biomass: { produces: ["biomass"], consumes: ["essence"], items: true },
  weather: { produces: ["weather.signals"], consumes: [], items: false },
  system: { produces: [], consumes: [], items: false, fixed: true }, // boot, uplink, sensors, contracts: never touched
};

const PLANNED = {
  produce: "phase 4: producer flows from telemetry",
  cash: "phase 4: credits per hour",
};

// Mode table: {params: {name: default}} for an implemented mode, {planned} otherwise.
// `scale` keeps the `standin` params: its survivors run the Level-1 scripts.
const REAL_OFF = { real: { params: {} }, off: { params: {} } };
const STANDIN_PARAMS = { guardTicks: 600, stop: 0.5, start: 0.7, heaterPower: {} };
export const MODES = {
  terraforming: { ...REAL_OFF, park: { params: {} }, standin: { params: STANDIN_PARAMS }, scale: { params: { perRecord: 10, max: 50, ...STANDIN_PARAMS } } },
  power: { ...REAL_OFF, trim: { params: { warmupTicks: 600, margin: 1.25, keepMin: 1 } } },
  orchestrator: { ...REAL_OFF },
  logistics: { ...REAL_OFF, mover: { params: { every: 100, speedMps: 12, loadTicks: 50 } } },
  factory: { ...REAL_OFF },
  plants: { ...REAL_OFF, produce: { planned: PLANNED.produce }, cash: { planned: PLANNED.cash } },
  biolab: { ...REAL_OFF },
  wildlife: { ...REAL_OFF },
  biomass: { ...REAL_OFF },
  weather: { ...REAL_OFF },
  system: { real: { params: {} } },
};

export const SYSTEM_SLOT = /^(boot|uplink|planet_\w+|\w+_sensor|contract_\w+)$/;
const ROLE_MARKER = /^\s*#\s*ct-(automation|panel)\s*:\s*(\w+)/m;
const TRIM_TYPES = new Set(["steam_turbine", "oil_generator"]);

// Level-1 stand-ins (mode `standin`): the Python file in standins/ that takes
// over each terraformer type's script slot. Source and API notes in the files.
export const STANDIN_SCRIPTS = { temp_heater: "heater.py", heat_generator: "heater.py", oxygen_generator: "o2gen.py", pressure_generator: "pressure.py" };
const HEATER_TYPES = new Set(["temp_heater", "heat_generator"]);
const MK3_TIER = 3;
export const STANDIN_KEY = "standin.terraforming"; // read by standins/heater.py
// `scale`: a record with a fluid port whose level reads 0 at every check over
// STALL_TICKS warns once (one record drains N machines' worth through one port).
// Mk IV machines (fuel rods, no port) are never scaled: the rod branch of the
// worker's drain is not patched, so a scaled record would burn one magazine
// for N machines' output.
const STALL_CHECK_TICKS = 600;
export const STALL_TICKS = 6000;
const MK4_TIER = 4;
const portKeys = m => Object.keys(m.data ?? {}).filter(k => k.endsWith("_in_level"));
const portLevel = m => portKeys(m).reduce((min, k) => Math.min(min, m.data[k] ?? 0), Infinity);
// Logistics `mover`: lib constants it mirrors (lib/logistics_requests.py, priority.py).
const REQUESTS_KEY = "logistics.requests";
const PICKUPS_KEY = "logistics.pickups";
const REQUEST_STALE_TICKS = 6000;
const PICKUP_STALE_TICKS = 36000;
const MOVER_VEHICLE = "standin_mover";
const SHOP_SOURCE = "shop";
const TICKS_PER_SECOND = 10;
// priority.py ladder_level: cum of the lowest level with p >= prio (levels run
// prio-descending, so the scan breaks at the first p < prio); 0 when none.
const ladderLevel = (levels, prio) => { let cum = 0; for (const [p, c] of levels) { if (p < prio) break; cum = c; } return cum; };
const validRequest = (e, tick) => !!e && Array.isArray(e.levels) && e.levels.length > 0 && e.levels.every(l => Array.isArray(l) && l.length === 2 && l.every(Number.isFinite))
  && tick - e.tick >= 0 && tick - e.tick < REQUEST_STALE_TICKS;
const freshPickup = (e, tick) => !!e && tick - e.tick >= 0 && tick - e.tick < PICKUP_STALE_TICKS;

// A stand-in's source is standins/_feed.py (the shared Mk III feed keeper)
// followed by the type's file; each file alone passes Ruff and Pyright.
export function standinSource(file) {
  const read = f => readFileSync(new URL(`./standins/${f}`, import.meta.url), "utf8");
  return read("_feed.py") + "\n" + read(file);
}

// Running statuses as the scheduler counts them for the step allowance (game N5()).
export function countsForAllowance(status) {
  return status === "running" || status === "waiting" || status === "flushing";
}

// Groups every script slot: machine slots by the machine's type, panels and
// automations by their role marker (orchestrator), system slots, the rest
// unclassified (idle orphan slots of recycled machines are only counted).
// Returns {groups: {name: {slots: [id], machines: [m]}}, unclassified: [id], orphans: n}.
export function classify(state, assign = {}) {
  const groups = Object.fromEntries(Object.keys(GROUPS).map(g => [g, { slots: [], machines: [] }]));
  const owned = new Set();
  const unclassified = [];
  for (const m of Object.values(state.machines)) {
    const g = assign[m.typeId] ?? TYPES[m.typeId]?.group;
    const slots = (m.scriptSlots ?? []).filter(id => id && state.scripts[id]);
    for (const id of slots) owned.add(id);
    if (!g) { if (slots.length) unclassified.push(...slots); continue; }
    groups[g].machines.push(m);
    groups[g].slots.push(...slots);
  }
  let orphans = 0;
  for (const [id, s] of Object.entries(state.scripts)) {
    if (owned.has(id)) continue;
    if (SYSTEM_SLOT.test(id)) groups.system.slots.push(id);
    else if (ROLE_MARKER.test(s.source ?? "") || /^(automation|panel)_\d+$/.test(id)) groups.orchestrator.slots.push(id);
    else if (countsForAllowance(s.status)) unclassified.push(id);
    else orphans++; // a recycled machine's idle slot: nothing to stop
  }
  return { groups, unclassified, orphans };
}

export class Standins {
  constructor(sim, scenario, { log = console.log, warn = console.warn } = {}) {
    this.sim = sim;
    this.sc = scenario;
    this.log = log;
    this.warn = warn;
    const { groups, unclassified, orphans } = classify(sim.state, scenario.assign);
    this.groups = groups;
    this.unclassified = unclassified;
    this.orphans = orphans;
    this.keep = new Set(scenario.keep);
    this.modes = Object.fromEntries(Object.keys(GROUPS).map(g => [g, GROUPS[g].fixed ? "real" : modeOf(scenario, g)]));
    this.ghosts = {};          // group -> scripts removed (virtual script count)
    this.stopped = {};         // group -> slot ids stopped
    this.parker = null;
    this.trim = null;
    this.standin = null;
    this.scale = null;
    this.mover = null;
    this.baseTotalSteps = sim.config?.interpreter?.totalStepsPerTick ?? null;
    this.allowance = null;
    if (unclassified.length) {
      const msg = `standins: ${unclassified.length} unclassified slot(s) left as they are: ${unclassified.join(", ")}`;
      if (scenario.strict) throw new Error(msg);
      warn(msg);
    }
    this.flows = new Flows(sim.state, scenario.flows);
    for (const [key, value] of Object.entries(scenario.archive)) sim.setArchive(key, value);
    this.#setup();
  }

  #setup() {
    const sim = this.sim;
    for (const [g, mode] of Object.entries(this.modes)) {
      const { slots, machines } = this.groups[g];
      if (mode === "real") continue;
      if (mode === "off") {
        const stopped = this.#stop(slots);
        this.stopped[g] = stopped;
        this.ghosts[g] = stopped.length;
        if (GROUPS[g].items && !this.sc.flows.length) this.warn(`standins: ${g} is off and the scenario has no flows; it produced ${GROUPS[g].produces.join(", ")} and consumed ${GROUPS[g].consumes.join(", ")}`);
      } else if (mode === "park") {
        const types = Object.fromEntries(Object.entries(PASSIVE_TYPES).filter(([t]) => machines.some(m => m.typeId === t)));
        this.parker = new Parker(sim, types);
        sim.park(this.parker);
      } else if (mode === "trim") {
        const p = this.sc.subsystems[g];
        this.trim = { group: g, warmupTicks: p.warmupTicks, margin: p.margin, keepMin: p.keepMin, peak: new Map(), perGen: new Map(), done: false, kept: {}, stopped: [] };
      } else if (mode === "standin") {
        this.#standinSetup(g);
      } else if (mode === "scale") {
        this.#scaleSetup(g);
      } else if (mode === "mover") {
        this.#moverSetup(g);
      }
      const note = this.scale?.group === g ? ` (${Object.keys(this.scale.records).length} records for ${Object.keys(this.scale.records).length + this.scale.undeployed.length} machines, ${this.scale.undeployed.length} undeployed)`
        : this.mover?.group === g ? ` (${this.ghosts[g] ?? 0} scripts stopped, ${this.mover.outposts.length} outposts)`
        : this.ghosts[g] ? ` (${this.ghosts[g]} scripts stopped)` : this.standin?.group === g ? ` (${Object.keys(this.standin.scripts).length} scripts replaced)` : "";
      this.log(`standins: ${g} = ${this.modes[g]}${note}`);
    }
    for (const [g, n] of Object.entries(this.sc.ghosts)) this.ghosts[g] = n;
    if (this.baseTotalSteps === null) this.warn("standins: sim.config.interpreter.totalStepsPerTick not reachable; the virtual script count is off");
  }

  // Stops the running scripts of `slots` (minus `keep`); returns the ids stopped.
  #stop(slots) {
    const st = this.sim.state;
    const stopped = [];
    for (const id of slots) {
      if (this.keep.has(id)) continue;
      const s = st.scripts[id];
      if (!s || !countsForAllowance(s.status)) continue;
      const r = this.sim.h.command("script.stop", { scriptId: id });
      if (r.ok) stopped.push(id);
      else this.warn(`standins: script.stop ${id}: ${r.error ?? JSON.stringify(r.result)}`);
    }
    return stopped;
  }

  totalGhosts() {
    return Object.values(this.ghosts).reduce((a, b) => a + b, 0);
  }

  // Before every tick: the step allowance the base would have with the removed
  // scripts still in it. allowance = min(stepsPerTick, floor(totalStepsPerTick / N)).
  beforeTick() {
    const cfg = this.sim.config?.interpreter;
    if (!cfg || this.baseTotalSteps === null) return;
    const ghosts = this.totalGhosts();
    const entries = this.sim.h.core.scriptScheduler.scripts;
    let n = 0;
    for (const e of entries.values()) if (countsForAllowance(e.status)) n++;
    cfg.totalStepsPerTick = ghosts > 0 && n > 0 ? Math.max(1, Math.floor(this.baseTotalSteps * n / (n + ghosts))) : this.baseTotalSteps;
    this.allowance = { n, ghosts, steps: Math.max(1, Math.min(cfg.stepsPerTick, Math.floor(cfg.totalStepsPerTick / Math.max(1, n)))) };
  }

  // After every tick.
  pass(tick) {
    this.flows.pass(tick);
    if (this.trim && !this.trim.done) this.#trimPass(tick);
    if (this.standin) this.#guardPass(tick);
    if (this.scale) this.#stallPass(tick);
    if (this.mover) this.#moverPass(tick);
  }

  // Terraforming `scale` (Level 2, needs features.scale and machineRevision):
  // identical machines (type, tier, tierUpgrade, outpost, subnet, declared
  // port targets; Mk I-III only; a running slot not in `keep`) collapse into records of at
  // most perRecord each: the members with the highest port level survive,
  // the others are undeployed (the game's own command, never a splice of
  // state.machines) and their kits leave the Inventory again. A survivor's
  // data.scale = N makes the patched worker do N machines' atmosphere output,
  // fluid drain and power draw. Members beyond `max` stay real. Every machine
  // left then gets the Level-1 stand-in (steam guard, setpoints). The
  // undeployed members' scripts are the ghosts. A save written with
  // data.scale must never be loaded in game.
  #scaleSetup(g) {
    const sim = this.sim, st = sim.state, p = this.sc.subsystems[g];
    const why = !sim.features?.scale ? "the scale anchors did not match this simworker build"
      : !sim.features?.machineRevision ? "Sim.undeploy() is off on this simworker build" : null;
    if (why) {
      this.warn(`standins: ${g} scale unavailable (${why}); falling back to standin`);
      this.modes[g] = "standin";
      this.#standinSetup(g);
      return;
    }
    for (const k of ["perRecord", "max"]) {
      if (!Number.isInteger(p[k]) || p[k] < 1) throw new Error(`standins: ${g} scale: ${k} must be a positive integer, got ${JSON.stringify(p[k])}`);
    }
    const s = { group: g, perRecord: p.perRecord, max: p.max, records: {}, undeployed: [], refused: {}, kits: {}, stalled: [], stallSince: {}, minLevel: {}, lastTick: null };
    this.scale = s;
    const subnets = st.planet?.power?.machineSubnets ?? {};
    const identical = new Map();
    const running = new Map();
    for (const m of this.groups[g].machines) {
      if (!STANDIN_SCRIPTS[m.typeId] || (m.data?.tier ?? 1) >= MK4_TIER) continue;
      const slots = (m.scriptSlots ?? []).filter(id => st.scripts[id] && countsForAllowance(st.scripts[id].status));
      if (!slots.length || slots.some(id => this.keep.has(id))) continue;
      running.set(m.id, slots.length);
      const key = JSON.stringify([m.typeId, m.data?.tier ?? 1, m.data?.tierUpgrade ?? 0, m.locationId ?? HOME_OUTPOST, subnets[m.id] ?? null, m.ioConnections ?? {}]);
      if (!identical.has(key)) identical.set(key, []);
      identical.get(key).push(m);
    }
    let ghosts = 0;
    for (const members of identical.values()) {
      if (members.length < 2) continue;
      members.sort((a, b) => portLevel(b) - portLevel(a) || a.id.localeCompare(b.id));
      const n = Math.min(members.length, s.max);
      const nRecords = Math.ceil(n / s.perRecord);
      const survivors = members.slice(0, nRecords);
      for (const m of survivors) s.records[m.id] = 1;
      members.slice(nRecords, n).forEach((m, i) => {
        const survivor = survivors[i % nRecords];
        const r = this.#undeploy(m);
        if (!r.ok) { s.refused[m.id] = r.reason; this.warn(`standins: scale undeploy ${m.id} refused (${r.reason}); it stays real`); return; }
        s.records[survivor.id]++;
        s.undeployed.push(m.id);
        ghosts += running.get(m.id);
      });
      for (const m of survivors) m.data.scale = s.records[m.id];
    }
    this.groups[g].machines = this.groups[g].machines.filter(m => st.machines[m.id]);
    this.ghosts[g] = ghosts;
    this.#standinSetup(g);
    this.#stallPass(st.tickCount ?? 0);
  }

  // sim.undeploy() puts the machine's kit (and any upgrade pack) into the
  // Inventory; the stacks that appeared or grew are removed again, so the
  // scaled run keeps the real run's Inventory.
  #undeploy(m) {
    const slots = this.sim.state.inventory.slots;
    const before = slots.map(s => s ? { ...s } : null);
    const r = this.sim.undeploy(m.id);
    if (!r.ok) return r;
    slots.forEach((s, i) => {
      if (!s) return;
      const was = before[i];
      const added = s.count - (was && was.id === s.id ? was.count : 0);
      if (added <= 0) return;
      this.scale.kits[s.id] = (this.scale.kits[s.id] ?? 0) + added;
      if (was && was.id === s.id) s.count = was.count;
      else slots[i] = was;
    });
    return r;
  }

  #stallPass(tick) {
    const s = this.scale;
    if (s.lastTick !== null && tick - s.lastTick < STALL_CHECK_TICKS) return;
    s.lastTick = tick;
    const st = this.sim.state;
    for (const [id, n] of Object.entries(s.records)) {
      const m = st.machines[id];
      if (!m) continue;
      const dry = portKeys(m).filter(k => (m.data[k] ?? 0) <= 0);
      if (!portKeys(m).length) continue;
      s.minLevel[id] = Math.min(s.minLevel[id] ?? Infinity, portLevel(m));
      if (!dry.length) { delete s.stallSince[id]; continue; }
      s.stallSince[id] ??= tick;
      if (tick - s.stallSince[id] >= STALL_TICKS && !s.stalled.includes(id)) {
        s.stalled.push(id);
        this.warn(`standins: scale record ${id} (x${n}) starved: ${dry.join(", ")} at 0 for ${STALL_TICKS} ticks; lower perRecord`);
      }
    }
  }

  // Terraforming `standin`: every running script slot of the group's machines
  // gets the type's Python stand-in (standins/*.py) in place of the real
  // controller; the script count stays the same, so no ghosts. final_save.json
  // carries the stand-in sources: never load it in game.
  #standinSetup(g) {
    const p = this.sc.subsystems[g];
    const s = { group: g, guardTicks: p.guardTicks, stop: p.stop, start: p.start, heaterPower: p.heaterPower, scripts: {}, failed: [], guardOff: new Set(), pool: null, lastGuardTick: null, sources: {} };
    this.standin = s;
    const st = this.sim.state;
    for (const m of this.groups[g].machines) {
      const file = STANDIN_SCRIPTS[m.typeId];
      if (!file) continue;
      for (const id of m.scriptSlots ?? []) {
        const slot = st.scripts[id];
        if (!slot || this.keep.has(id) || !countsForAllowance(slot.status)) continue;
        s.sources[file] ??= standinSource(file);
        const r = this.sim.setScript(id, s.sources[file], { run: true });
        if (r.ok) s.scripts[id] = file;
        else { s.failed.push(id); this.warn(`standins: setScript ${id} (${file}): ${r.status}`); }
      }
    }
    if (typeof s.heaterPower === "number") {
      const power = s.heaterPower;
      s.heaterPower = Object.fromEntries(this.groups[g].machines.filter(m => HEATER_TYPES.has(m.typeId)).map(m => [m.id, power]));
    }
    this.#guardPass(st.tickCount ?? 0);
  }

  // The Mk III steam guard of lib/terraforming.py (Mk3FluidFeed), computed
  // here every guardTicks from the raw state: the banked steam fraction over
  // every steam Gas Tank (`stringData.fluid === "steam"`, stored tons
  // `data.level` of `data.capacity`; the `gas_in_*` keys are the port buffer),
  // network-wide as lib/power.py steam_pool() reads it. A Mk III heater goes
  // into `guard_off` below `stop` and leaves it at `start` (hysteresis); no
  // measurable pool keeps the guard open. The result is the archive key
  // STANDIN_KEY, which standins/heater.py reads.
  #guardPass(tick) {
    const s = this.standin;
    if (s.lastGuardTick !== null && tick - s.lastGuardTick < s.guardTicks) return;
    s.lastGuardTick = tick;
    const st = this.sim.state;
    let level = 0, cap = 0;
    for (const m of Object.values(st.machines)) {
      if (m.typeId !== "gas_tank" || m.stringData?.fluid !== "steam") continue;
      level += m.data?.level ?? 0;
      cap += m.data?.capacity ?? 0;
    }
    const fraction = cap > 0 ? level / cap : null;
    s.pool = fraction;
    for (const m of this.groups[s.group].machines) {
      if (!HEATER_TYPES.has(m.typeId) || (m.data?.tier ?? 1) !== MK3_TIER) continue;
      const off = s.guardOff.has(m.id);
      if (fraction === null) {
        s.guardOff.delete(m.id);
      } else if (!off && fraction < s.stop) {
        s.guardOff.add(m.id);
        this.log(`standins: steam guard ${m.id}: pool ${(fraction * 100).toFixed(0)} % < ${s.stop * 100} %, steam_in released`);
      } else if (off && fraction >= s.start) {
        s.guardOff.delete(m.id);
        this.log(`standins: steam guard ${m.id}: pool ${(fraction * 100).toFixed(0)} % >= ${s.start * 100} %, steam_in back`);
      }
    }
    this.sim.setArchive(STANDIN_KEY, { heater_power: s.heaterPower, guard_off: [...s.guardOff].sort(), tick });
  }

  // Power `trim`: watch each subnet's demand and per-generator output for
  // warmupTicks, then keep k = ceil(peak * margin / perGen) generator scripts
  // per subnet and stop the rest (a generator without a running script makes
  // no power and drains no fluid). The stopped scripts count as ghosts.
  #trimPass(tick) {
    const t = this.trim;
    const st = this.sim.state;
    const pw = st.planet?.power;
    if (!pw?.subnets) return;
    const gens = this.groups[t.group].machines.filter(m => TRIM_TYPES.has(m.typeId) && m.powered !== false && (m.scriptSlots ?? []).some(id => st.scripts[id]?.status === "running"));
    const bySubnet = new Map();
    for (const m of gens) {
      const s = pw.machineSubnets?.[m.id];
      if (!s) continue;
      if (!bySubnet.has(s)) bySubnet.set(s, []);
      bySubnet.get(s).push(m);
    }
    for (const [s, sub] of Object.entries(pw.subnets)) {
      t.peak.set(s, Math.max(t.peak.get(s) ?? 0, sub.consumed ?? 0));
      const n = bySubnet.get(s)?.length ?? 0;
      if (n > 0 && sub.generated > 0) t.perGen.set(s, Math.max(t.perGen.get(s) ?? 0, sub.generated / n));
    }
    t.warmupStart ??= tick;
    if (tick - t.warmupStart < t.warmupTicks) return;
    t.done = true;
    for (const [s, list] of bySubnet) {
      const perGen = t.perGen.get(s);
      if (!perGen) { t.kept[s] = list.length; continue; }
      const k = Math.min(list.length, Math.max(t.keepMin, Math.ceil(t.peak.get(s) * t.margin / perGen)));
      const extra = list.slice().sort((a, b) => a.id.localeCompare(b.id)).slice(k);
      const stopped = this.#stop(extra.flatMap(m => m.scriptSlots ?? []));
      t.kept[s] = list.length - extra.length;
      t.stopped.push(...stopped);
      this.log(`standins: power trim ${s}: peak ${t.peak.get(s).toFixed(0)} W, ${perGen.toFixed(0)} W per generator, keeping ${k} of ${list.length}, stopped ${stopped.length}`);
    }
    this.stopped[t.group] = t.stopped;
    if (this.sc.ghosts[t.group] === undefined) this.ghosts[t.group] = t.stopped.length;
  }

  // Logistics `mover`: the group's scripts stop (ghosts) and a direct hauler
  // serves `logistics.requests` from the raw state instead. Lib facts it
  // follows (lib/logistics_requests.py, verified 2026-10-14):
  //   requests  {dest: {item: {levels: [[prio, cum], ...], have, by, tick, buy?, keep?}}};
  //             an entry without a levels ladder (old `{target, have}` shape) or
  //             with tick older than REQUEST_STALE_TICKS is skipped, as the lib's
  //             active_requests() does. `have` is the requester's own count at
  //             write time: never read, the live count comes from the stores.
  //   pickups   {key: {vehicle, dest, source, item_id, units, tick, aboard?}}, fresh
  //             while tick - entry.tick < PICKUP_STALE_TICKS. The mover's key is
  //             pull:standin_mover:<dest>:<item>:<source>; other vehicles' entries
  //             are read (in flight into dest, reserved from a source) and never
  //             written. The mover's own takes leave the store at once, so they
  //             are not reserved again.
  //   fleet.status is not written: drone_haulers_present() needs a fresh hauler
  //             drone entry, which the stopped drones no longer publish, so the
  //             requesters stay on the ground-hauler branch.
  #moverSetup(g) {
    const p = this.sc.subsystems[g];
    for (const k of ["every", "loadTicks"]) {
      if (!Number.isInteger(p[k]) || p[k] < 1) throw new Error(`standins: ${g} mover: ${k} must be a positive integer, got ${JSON.stringify(p[k])}`);
    }
    if (!(p.speedMps > 0)) throw new Error(`standins: ${g} mover: speedMps must be > 0, got ${JSON.stringify(p.speedMps)}`);
    const stopped = this.#stop(this.groups[g].slots);
    this.stopped[g] = stopped;
    if (this.sc.ghosts[g] === undefined) this.ghosts[g] = stopped.length;
    // A stopped hauler's pickups would count as in flight for PICKUP_STALE_TICKS
    // (nothing releases them); they go now, as release_pickups() does for a
    // vehicle that plans again. Whatever was aboard stays aboard.
    const pickups = this.sim.getArchive(PICKUPS_KEY, {}) ?? {};
    const gone = Object.keys(pickups).filter(k => stopped.includes(pickups[k]?.vehicle));
    if (gone.length) { for (const k of gone) delete pickups[k]; this.sim.setArchive(PICKUPS_KEY, pickups); }
    const outposts = (this.sim.state.planet?.outposts ?? []).filter(o => o?.id).map(o => ({ id: o.id, x: Number.isFinite(o.x) ? o.x : 0, y: Number.isFinite(o.y) ? o.y : 0 }));
    if (!outposts.length) this.warn(`standins: ${g} mover: no outposts in state.planet.outposts; nothing moves`);
    this.mover = { group: g, every: p.every, speedMps: p.speedMps, loadTicks: p.loadTicks, outposts, queue: [], moved: {}, trips: 0, bought: {}, buyFailed: {}, noPos: new Set() };
  }

  // Every tick: due trips land (overflow stays queued and retries in `every`
  // ticks). Every `every` ticks: each request's ladder is walked from the
  // highest prio; the shortfall after live stock, everything in flight and
  // this pass's loads comes from the nearest outpost that has it free (its own
  // request level at that prio, its keep and others' reservations stay), then
  // from the shop when the entry asks to buy. One trip per source per pass.
  // `tick` counts from the run's start (cadence only); ages, stamps and
  // arrival ticks use the game's tickCount, which the archive entries carry.
  #moverPass(tick) {
    const mv = this.mover, sim = this.sim, st = sim.state;
    if (!mv.outposts.length) return;
    const now = st.tickCount ?? tick;
    let pickups = null, dirty = false;
    const load = () => pickups ??= sim.getArchive(PICKUPS_KEY, {}) ?? {};
    const keyOf = q => `pull:${MOVER_VEHICLE}:${q.dest}:${q.item}:${q.source}`;
    mv.queue = mv.queue.filter(q => {
      if (q.arriveTick > now) return true;
      const n = addAt(st, "outpost:" + q.dest, q.item, q.units);
      mv.moved[q.item] = (mv.moved[q.item] ?? 0) + n;
      const p = load(), e = p[keyOf(q)];
      dirty = true;
      if (e) { e.units -= n; e.tick = now; if (e.units <= 0) delete p[keyOf(q)]; } // re-stamped: a long retry must stay fresh for in_flight()
      if (n >= q.units) return false;
      q.units -= n;
      q.arriveTick = now + mv.every;
      return true;
    });
    if (tick % mv.every === 0) {
      const requests = sim.getArchive(REQUESTS_KEY, {}) ?? {};
      const p = load();
      const pos = Object.fromEntries(mv.outposts.map(o => [o.id, o]));
      const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
      const sum = f => Object.values(p).reduce((n, e) => n + (freshPickup(e, now) && f(e) ? e.units : 0), 0);
      const entryOf = (o, item) => { const e = requests[o]?.[item]; return validRequest(e, now) ? e : null; };
      for (const [dest, items] of Object.entries(requests)) {
        const at = pos[dest];
        if (!at) { if (!mv.noPos.has(dest)) { mv.noPos.add(dest); this.warn(`standins: mover: request dest ${dest} is not in state.planet.outposts; skipped`); } continue; }
        const sources = mv.outposts.filter(o => o.id !== dest).sort((a, b) => dist(a, at) - dist(b, at));
        for (const [item, e] of Object.entries(items ?? {})) {
          if (!validRequest(e, now)) continue;
          const base = countAt(st, "outpost:" + dest, item) + sum(x => x.dest === dest && x.item_id === item);
          const loads = new Map(); // source id -> units taken this pass
          const take = (src, units) => { loads.set(src, (loads.get(src) ?? 0) + units); };
          const loaded = () => [...loads.values()].reduce((a, b) => a + b, 0);
          for (const prio of new Set(e.levels.map(l => l[0]))) {
            let want = ladderLevel(e.levels, prio) - base - loaded();
            for (const o of sources) {
              if (want <= 0) break;
              const se = entryOf(o.id, item);
              const keep = Math.max(se ? ladderLevel(se.levels, prio) : 0, se && typeof se.keep === "number" && se.keep > 0 ? se.keep : 0);
              const free = countAt(st, "outpost:" + o.id, item) - sum(x => x.source === o.id && x.item_id === item && x.vehicle !== MOVER_VEHICLE) - keep;
              const k = Math.min(want, free);
              if (k <= 0) continue;
              const taken = takeAt(st, "outpost:" + o.id, item, k);
              take(o.id, taken);
              want -= taken;
            }
            if (want > 0 && e.buy === true) {
              // The Shop lands in the Inventory; only what landed travels (never
              // home's own stock). A home request keeps the units where they are.
              const before = countAt(st, "inventory", item);
              const r = sim.buy(item, want);
              if (r?.ok) {
                const landed = Math.max(0, Math.min(want, countAt(st, "inventory", item) - before));
                mv.bought[item] = (mv.bought[item] ?? 0) + landed;
                if (dest === HOME_OUTPOST) loads.set(HOME_OUTPOST, (loads.get(HOME_OUTPOST) ?? 0) + landed);
                else take(SHOP_SOURCE, takeAt(st, "inventory", item, landed));
              } else if (!(item in mv.buyFailed)) {
                mv.buyFailed[item] = r?.reason ?? r?.status ?? "failed";
                this.warn(`standins: mover: buy ${want} ${item} for ${dest} failed: ${mv.buyFailed[item]}`);
              }
            }
          }
          for (const [source, units] of loads) {
            if (units <= 0 || source === dest) continue; // bought at home for home: already there
            const from = source === SHOP_SOURCE ? pos[HOME_OUTPOST] ?? at : pos[source];
            mv.queue.push({ dest, source, item, units, arriveTick: now + mv.loadTicks + Math.round(TICKS_PER_SECOND * dist(from, at) / mv.speedMps) });
            const pe = p[keyOf({ dest, item, source })] ??= { vehicle: MOVER_VEHICLE, dest, source, item_id: item, units: 0, tick: now, aboard: true };
            pe.units += units;
            pe.tick = now;
            mv.trips++;
            dirty = true;
          }
        }
      }
    }
    if (dirty) sim.setArchive(PICKUPS_KEY, pickups);
  }

  report() {
    const mv = this.mover;
    return {
      scenario: this.sc.name,
      modes: this.modes,
      ghosts: this.ghosts,
      allowance: this.allowance,
      stopped: this.stopped,
      flows: this.flows.report(),
      ...(this.parker ? { wakes: this.parker.wakes } : {}),
      ...(this.trim ? { trim: { kept: this.trim.kept, stopped: this.trim.stopped.length, done: this.trim.done } } : {}),
      ...(this.scale ? { scale: { records: this.scale.records, undeployed: this.scale.undeployed, refused: this.scale.refused, kits: this.scale.kits, stalled: this.scale.stalled, minLevel: this.scale.minLevel } } : {}),
      ...(this.standin ? { standin: { scripts: this.standin.scripts, failed: this.standin.failed, guardOff: [...this.standin.guardOff].sort(), pool: this.standin.pool } } : {}),
      ...(mv ? { mover: { moved: mv.moved, trips: mv.trips, pendingUnits: mv.queue.reduce((n, q) => n + q.units, 0), bought: mv.bought, buyFailed: mv.buyFailed } } : {}),
      unclassified: this.unclassified,
      orphans: this.orphans,
      counts: Object.fromEntries(Object.entries(this.groups).map(([g, v]) => [g, v.slots.length])),
    };
  }

  // Legacy summary fields (run.mjs wrote stocked/drained per item).
  legacyTotals() {
    const stocked = {}, drained = {};
    for (const f of this.flows.report()) {
      if (f.keep !== undefined) stocked[f.item] = (stocked[f.item] ?? 0) + f.added;
      if (f.after !== undefined) drained[f.item] = (drained[f.item] ?? 0) + f.removed;
    }
    return { stocked, drained };
  }
}
