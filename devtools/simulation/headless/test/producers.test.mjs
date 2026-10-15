import { test } from "node:test";
import assert from "node:assert/strict";
import { Standins, GROUPS, MODES } from "../standins.mjs";
import { DEFAULT_PROFILE_PATH, emptyScenario, loadProfile, validateScenario } from "../scenario.mjs";
import { countAt } from "../stacks.mjs";

// The repo profile: its stubs and budget key are what the tests check against.
const PROFILE = loadProfile(DEFAULT_PROFILE_PATH);
const STUBS = PROFILE.stubs;
const BUDGET_KEY = PROFILE.budget.key;

// Phase 4: plants `produce` (rates into the Inventory) and `cash` (credits per
// hour), and the archive stubs an `off` orchestrator / wildlife / biomass leaves
// for the readers that stay real.
function fakeSim({ credits = 500 } = {}) {
  const state = {
    tickCount: 0,
    player: { credits },
    inventory: { slots: [null, null, null, null] },
    machines: {
      harvester_1: { id: "harvester_1", typeId: "harvester", scriptSlots: ["harvester_1"] },
      crop_automator_2: { id: "crop_automator_2", typeId: "crop_automator", scriptSlots: ["crop_automator_2"] },
      habitat_1: { id: "habitat_1", typeId: "habitat", scriptSlots: ["habitat_1"] },
    },
    scripts: {
      harvester_1: { id: "harvester_1", status: "running", source: "" },
      crop_automator_2: { id: "crop_automator_2", status: "running", source: "" },
      habitat_1: { id: "habitat_1", status: "running", source: "" },
    },
    notebook: { entries: {} },
  };
  const stops = [];
  const sim = {
    state,
    config: { interpreter: { stepsPerTick: 1000, totalStepsPerTick: 50000 } },
    h: {
      core: { scriptScheduler: { scripts: new Map() } },
      command(name, { scriptId }) { assert.equal(name, "script.stop"); stops.push(scriptId); state.scripts[scriptId].status = "stopped"; return { ok: true }; },
    },
    getArchive(key, fallback) { const e = state.notebook.entries[key]; return e ? structuredClone(e.value) : fallback; },
    archiveKeys() { return Object.keys(state.notebook.entries); },
    archiveRaw(key) { return state.notebook.entries[key]?.value; },
    deleteArchive(key) { delete state.notebook.entries[key]; },
    setArchive(key, value) { state.notebook.entries[key] = { value: structuredClone(value) }; },
  };
  return { sim, stops };
}
const quiet = { log: () => {}, warn: () => {} };
const registry = { GROUPS, MODES };
const scenario = (subsystems, extra = {}) => validateScenario({ ...emptyScenario(), subsystems, ...extra }, registry);
// run.mjs passes ticks since the run's start; ages use state.tickCount.
function run(st, sim, from, to) {
  for (let t = from; t <= to; t++) { sim.state.tickCount = t; st.pass(t); }
}

test("produce stops the plants and adds the stated rates to the Inventory", () => {
  const { sim, stops } = fakeSim();
  const lines = [];
  const st = new Standins(sim, scenario({ plants: { mode: "produce", forage_h: 360, rates: { seeds_wheat: 72 } } }), { log: l => lines.push(l), warn: () => {} });
  assert.deepEqual(stops.sort(), ["crop_automator_2", "harvester_1"]);
  assert.equal(st.ghosts.plants, 2);
  assert.match(lines.find(l => l.startsWith("standins: plants = produce")), /seeds_wheat 72\/h, forage 360\/h/);
  run(st, sim, 1, 1000); // 10 flow passes: 360/h = 1 per pass, 72/h = 0.2 per pass
  assert.equal(countAt(sim.state, "inventory", "forage"), 10);
  assert.equal(countAt(sim.state, "inventory", "seeds_wheat"), 2);
  assert.deepEqual(st.report().produce, { rates: { seeds_wheat: 72, forage: 360 }, added: { seeds_wheat: 2, forage: 10 } });
  assert.equal(st.report().flows.filter(f => f.by === "produce").length, 2, "produce rows show up as flows");
});

test("produce without a rate fails at setup before any stop", () => {
  const { sim, stops } = fakeSim();
  assert.throws(() => new Standins(sim, scenario({ plants: { mode: "produce" } }), quiet), /needs forage_h or rates/);
  assert.throws(() => new Standins(sim, scenario({ plants: { mode: "produce", forage_h: -1 } }), quiet), /rate for forage must be a number >= 0/);
  assert.throws(() => new Standins(sim, scenario({ plants: { mode: "produce", rates: { forage: "x" } } }), quiet), /rate for forage/);
  assert.throws(() => new Standins(sim, scenario({ plants: { mode: "produce", forage_h: 1, rates: { forage: 2 } } }), quiet), /both given/);
  assert.deepEqual(stops, []);
});

test("cash adds creditsPerHour to state.player.credits in whole credits", () => {
  const { sim, stops } = fakeSim({ credits: 500 });
  const st = new Standins(sim, scenario({ plants: { mode: "cash", creditsPerHour: 900 } }), quiet);
  assert.deepEqual(stops.sort(), ["crop_automator_2", "harvester_1"]);
  run(st, sim, 1, 300); // 900/h = 2.5 per pass: 2, 5, 7
  assert.equal(sim.state.player.credits, 507);
  assert.deepEqual(st.report().cash, { creditsPerHour: 900, added: 7 });
  assert.throws(() => new Standins(fakeSim().sim, scenario({ plants: { mode: "cash" } }), quiet), /creditsPerHour must be a number >= 0/);
  const { sim: noPlayer } = fakeSim();
  delete noPlayer.state.player;
  assert.throws(() => new Standins(noPlayer, scenario({ plants: { mode: "cash", creditsPerHour: 1 } }), quiet), /state.player.credits/);
});

test("off groups leave their stubs unless the scenario seeds the key", () => {
  const { sim } = fakeSim();
  sim.setArchive("wildlife.plan", { assign: { habitat_1: "x" }, complete: false });
  const st = new Standins(sim, scenario({ wildlife: { mode: "off" }, biomass: { mode: "off" } }, { archive: { "biomass.retire": { complete: true } } }), quiet);
  assert.deepEqual(sim.getArchive("wildlife.plan"), STUBS.wildlife["wildlife.plan"], "the stale plan is replaced");
  assert.deepEqual(sim.getArchive("biomass.retire"), { complete: true }, "the seed wins");
  assert.deepEqual(st.report().stubs, ["wildlife.plan"]);
  assert.equal(sim.getArchive(BUDGET_KEY), undefined, "orchestrator real: no budget stub");
});

test("orchestrator off refreshes cash.budget every pass and keeps fresh asks and holds", () => {
  const { sim } = fakeSim({ credits: 1234 });
  sim.setArchive(BUDGET_KEY, { priority: ["x"], asks: { a: { cost: 10, tick: 0 }, old: { cost: 1, tick: -5000 } }, holds: { a: { amount: 10, tick: 0 }, b: "junk" }, tick: -9999, floor: 50000 });
  const st = new Standins(sim, scenario({ orchestrator: { mode: "off" } }), quiet);
  assert.deepEqual(sim.getArchive("power.shedded"), []);
  const b0 = sim.getArchive(BUDGET_KEY);
  assert.deepEqual(b0, { priority: ["x"], tick: 0, balance: 1234, floor: 1000, income_h: null, burn_h: null, asks: { a: { cost: 10, tick: 0 } }, holds: { a: { amount: 10, tick: 0 } }, planned: 0, queue: [] });
  sim.state.player.credits = 2000;
  run(st, sim, 1, 700); // holds age out after 600 ticks, asks after 3000
  const b1 = sim.getArchive(BUDGET_KEY);
  assert.equal(b1.tick, 700);
  assert.equal(b1.balance, 2000);
  assert.deepEqual(Object.keys(b1.asks), ["a"]);
  assert.deepEqual(b1.holds, {});
  assert.deepEqual(st.report().stubs.sort(), ["cash.budget", "power.shedded"]);
});

test("a seeded cash.budget is not refreshed", () => {
  const { sim } = fakeSim();
  const st = new Standins(sim, scenario({ orchestrator: { mode: "off" } }, { archive: { [BUDGET_KEY]: { tick: 5, floor: 7 } } }), quiet);
  run(st, sim, 1, 200);
  assert.deepEqual(sim.getArchive(BUDGET_KEY), { tick: 5, floor: 7 });
  assert.deepEqual(st.report().stubs, ["power.shedded"]);
});
