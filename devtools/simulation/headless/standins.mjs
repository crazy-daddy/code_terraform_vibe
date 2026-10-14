// Per-subsystem stand-ins for headless runs: a test that targets one subsystem
// runs the others as cheap models or off, with the target's inputs and outputs
// kept flowing (scenario `flows`), and with the step allowance the target would
// have in the full base (virtual script count). Design, boundaries and the
// state shapes used here: docs/headless/standins.md. Scenario format:
// docs/headless/scenarios.md.
//
// Phase 0 (this file): registry, classification, `off`, `park`, power `trim`,
// flows, archive seeds, virtual script count. Later phases add the Level-1
// Python stand-ins, the `scale` simworker patch, the item mover and the
// producer modes; their mode names are listed in MODES as planned so a
// scenario naming them fails with the phase instead of running silently.

import { Parker, PASSIVE_TYPES } from "./passive.mjs";
import { Flows } from "./stacks.mjs";
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
  standin: "phase 1: Python stand-in scripts",
  scale: "phase 2: simworker scale patch",
  mover: "phase 3: direct item mover",
  produce: "phase 4: producer flows from telemetry",
  cash: "phase 4: credits per hour",
};

// Mode table: {params: {name: default}} for an implemented mode, {planned} otherwise.
const REAL_OFF = { real: { params: {} }, off: { params: {} } };
export const MODES = {
  terraforming: { ...REAL_OFF, park: { params: {} }, standin: { planned: PLANNED.standin }, scale: { planned: PLANNED.scale } },
  power: { ...REAL_OFF, trim: { params: { warmupTicks: 600, margin: 1.25, keepMin: 1 } } },
  orchestrator: { ...REAL_OFF },
  logistics: { ...REAL_OFF, mover: { planned: PLANNED.mover } },
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
      }
      this.log(`standins: ${g} = ${mode}${this.ghosts[g] ? ` (${this.ghosts[g]} scripts stopped)` : ""}`);
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

  report() {
    return {
      scenario: this.sc.name,
      modes: this.modes,
      ghosts: this.ghosts,
      allowance: this.allowance,
      stopped: this.stopped,
      flows: this.flows.report(),
      ...(this.parker ? { wakes: this.parker.wakes } : {}),
      ...(this.trim ? { trim: { kept: this.trim.kept, stopped: this.trim.stopped.length, done: this.trim.done } } : {}),
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
