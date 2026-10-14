import { test } from "node:test";
import assert from "node:assert/strict";
import { Standins, GROUPS, MODES } from "../standins.mjs";
import { emptyScenario, validateScenario } from "../scenario.mjs";

// A Sim stand-in: state, the scheduler's script map, the config object and the
// command port that `script.stop` goes through.
function fakeSim({ subnets } = {}) {
  const state = {
    tickCount: 0,
    inventory: { slots: [null, null] },
    machines: {
      fabricator_3: { id: "fabricator_3", typeId: "fabricator", scriptSlots: ["fabricator_3"], itemStacks: [], itemStacksCap: 100, itemStackSlots: 4, locationId: "outpost_2" },
      smelter_8: { id: "smelter_8", typeId: "smelter", scriptSlots: ["smelter_8"] },
      harvester_1: { id: "harvester_1", typeId: "harvester", scriptSlots: ["harvester_1"] },
      heater_1: { id: "heater_1", typeId: "temp_heater", scriptSlots: ["heater_1"], data: {}, powered: true },
      turbine_1: { id: "turbine_1", typeId: "steam_turbine", scriptSlots: ["turbine_1"], powered: true },
      turbine_2: { id: "turbine_2", typeId: "steam_turbine", scriptSlots: ["turbine_2"], powered: true },
      turbine_3: { id: "turbine_3", typeId: "steam_turbine", scriptSlots: ["turbine_3"], powered: true },
    },
    scripts: {},
    planet: { power: { subnets: subnets ?? {}, machineSubnets: { turbine_1: "subnet_0", turbine_2: "subnet_0", turbine_3: "subnet_0" } } },
    notebook: { entries: {} },
  };
  for (const id of ["fabricator_3", "smelter_8", "harvester_1", "heater_1", "turbine_1", "turbine_2", "turbine_3", "boot"]) state.scripts[id] = { id, status: id === "boot" ? "idle" : "running", source: "" };
  const sched = new Map(Object.values(state.scripts).map(s => [s.id, { status: s.status === "running" ? "waiting" : s.status }]));
  const stops = [];
  const sim = {
    state,
    config: { interpreter: { stepsPerTick: 1000, totalStepsPerTick: 50000 } },
    h: {
      core: { scriptScheduler: { scripts: sched } },
      skipSystems: new Set(),
      command(name, { scriptId }) {
        assert.equal(name, "script.stop");
        stops.push(scriptId);
        state.scripts[scriptId].status = "idle";
        sched.get(scriptId).status = "idle";
        return { ok: true };
      },
    },
    archive: {},
    setArchive(key, value) { this.archive[key] = value; },
    park(p) { this.parker = p; },
  };
  return { sim, stops };
}
const quiet = { log: () => {}, warn: () => {} };
const registry = { GROUPS, MODES };

test("off stops the group's running scripts except kept ones and counts ghosts", () => {
  const { sim, stops } = fakeSim();
  const sc = validateScenario({ ...emptyScenario(), default: "off", subsystems: { plants: { mode: "real" } }, keep: ["smelter_8"], archive: { "fabricator.manual_orders": { x: 1 } } }, registry);
  const st = new Standins(sim, sc, quiet);
  assert.deepEqual(stops.sort(), ["fabricator_3", "heater_1", "turbine_1", "turbine_2", "turbine_3"]);
  assert.equal(st.ghosts.factory, 1, "the kept smelter is not a ghost");
  assert.equal(st.ghosts.terraforming, 1);
  assert.equal(st.ghosts.power, 3);
  assert.equal(st.ghosts.plants, undefined);
  assert.equal(sim.state.scripts.boot.status, "idle", "system slots untouched");
  assert.deepEqual(sim.archive, { "fabricator.manual_orders": { x: 1 } });
  const r = st.report();
  assert.equal(r.modes.plants, "real");
  assert.equal(r.modes.system, "real");
  assert.deepEqual(r.stopped.factory, ["fabricator_3"]);
});

test("virtual script count scales totalStepsPerTick by n / (n + ghosts)", () => {
  const { sim } = fakeSim();
  const sc = validateScenario({ ...emptyScenario(), subsystems: { factory: { mode: "off" } }, ghosts: { logistics: 12 } }, registry);
  const st = new Standins(sim, sc, quiet);
  st.beforeTick();
  // 7 running before, 2 stopped -> n = 5 real; ghosts = 2 (factory) + 12 (logistics)
  assert.equal(st.totalGhosts(), 14);
  assert.equal(sim.config.interpreter.totalStepsPerTick, Math.floor(50000 * 5 / 19));
  assert.deepEqual(st.allowance, { n: 5, ghosts: 14, steps: 1000 }, "capped by stepsPerTick");
  // No ghosts: the base value comes back.
  st.ghosts = {};
  st.beforeTick();
  assert.equal(sim.config.interpreter.totalStepsPerTick, 50000);
});

test("power trim keeps ceil(peak * margin / perGen) turbine scripts after the warm-up", () => {
  const { sim, stops } = fakeSim({ subnets: { subnet_0: { consumed: 100, generated: 300 } } });
  const sc = validateScenario({ ...emptyScenario(), subsystems: { power: { mode: "trim", warmupTicks: 3, margin: 1.2 } } }, registry);
  const st = new Standins(sim, sc, quiet);
  st.pass(1);
  sim.state.planet.power.subnets.subnet_0.consumed = 150; // the peak
  st.pass(2);
  sim.state.planet.power.subnets.subnet_0.consumed = 90;
  st.pass(3);
  assert.deepEqual(stops, [], "still warming up");
  st.pass(4);
  // perGen = 300 / 3 = 100 W; k = ceil(150 * 1.2 / 100) = 2 -> stop turbine_3
  assert.deepEqual(stops, ["turbine_3"]);
  assert.equal(st.ghosts.power, 1);
  assert.deepEqual(st.report().trim, { kept: { subnet_0: 2 }, stopped: 1, done: true });
  st.pass(5);
  assert.deepEqual(stops, ["turbine_3"], "trim runs once");
});

test("strict scenario fails on an unclassified slot", () => {
  const { sim } = fakeSim();
  sim.state.scripts.mystery_1 = { id: "mystery_1", status: "running", source: "" };
  assert.throws(() => new Standins(sim, validateScenario({ ...emptyScenario(), strict: true }, registry), quiet), /unclassified slot/);
});
