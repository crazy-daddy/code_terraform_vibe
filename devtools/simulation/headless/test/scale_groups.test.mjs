import { test } from "node:test";
import assert from "node:assert/strict";
import { Standins, GROUPS, MODES, STALL_TICKS, STANDIN_SCRIPTS, standinSource } from "../standins.mjs";
import { emptyScenario, validateScenario } from "../scenario.mjs";

// Terraforming `scale` (phase 2): identical terraformers collapse into
// records of at most perRecord, the other members' scripts are stopped (the
// machines stay deployed); survivors carry data.scale and the Level-1
// stand-in.
function fakeSim({ levels = { heater_1: 7, heater_2: 8, heater_3: 3, heater_4: 5, heater_5: 6 }, refuse = {}, features = { scale: true } } = {}) {
  const heater = (id, level, extra = {}) => ({
    id, typeId: "temp_heater", scriptSlots: [id], powered: true, locationId: "outpost_5",
    ioConnections: { steam_in: "gas_tank_3" }, data: { tier: 3, tierUpgrade: 0, power: 5, steam_in_level: level, steam_in_capacity: 8 }, ...extra,
  });
  const machines = {};
  for (const [id, level] of Object.entries(levels)) machines[id] = heater(id, level);
  machines.heater_6 = heater("heater_6", 8, { ioConnections: { steam_in: "gas_tank_9" } }); // other tank: its own group of one
  machines.heater_7 = heater("heater_7", 8);                                                  // idle slot: not identical
  machines.heater_8 = heater("heater_8", 0, { data: { tier: 4, tierUpgrade: 0, rodFuel: 3 } });  // Mk IV: never scaled
  machines.heater_9 = heater("heater_9", 0, { data: { tier: 4, tierUpgrade: 0, rodFuel: 3 } });
  machines.o2gen_1 = { id: "o2gen_1", typeId: "oxygen_generator", scriptSlots: ["o2gen_1"], powered: true, data: { tier: 2 } };
  const state = {
    tickCount: 0,
    inventory: { slots: [{ id: "iron_ingot", count: 3 }, null] },
    machines,
    scripts: {},
    planet: { power: { subnets: {}, machineSubnets: Object.fromEntries(Object.keys(machines).map(id => [id, "subnet_0"])) } },
    notebook: { entries: {} },
  };
  for (const id of Object.keys(machines)) state.scripts[id] = { id, status: id === "heater_7" ? "idle" : "running", source: "real" };
  const sched = new Map(Object.values(state.scripts).map(s => [s.id, { status: s.status === "running" ? "waiting" : s.status }]));
  const stops = [], runs = [];
  const set = (id, status) => { state.scripts[id].status = status; sched.get(id).status = status === "running" ? "waiting" : status; };
  const sim = {
    state, features,
    config: { interpreter: { stepsPerTick: 1000, totalStepsPerTick: 50000 } },
    h: {
      core: { scriptScheduler: { scripts: sched } }, skipSystems: new Set(),
      // As the game does: script.stop answers nothing on success, { ok: false } on a refusal.
      command(name, { scriptId }) {
        if (name === "script.stop") {
          if (refuse[scriptId]) return { ok: true, result: { ok: false } };
          set(scriptId, "stopped"); stops.push(scriptId); return { ok: true };
        }
        if (name === "script.run") { set(scriptId, "running"); runs.push(scriptId); return { ok: true }; }
        throw new Error(`unexpected command ${name}`);
      },
    },
    archive: {},
    setArchive(key, value) { this.archive[key] = structuredClone(value); },
    getArchive(key, fallback) { return key in this.archive ? structuredClone(this.archive[key]) : fallback; },
    archiveKeys() { return Object.keys(this.archive); },
    archiveRaw(key) { return this.archive[key]; },
    deleteArchive(key) { delete this.archive[key]; },
    setScript(id, source, { run }) { state.scripts[id].source = source; set(id, run ? "running" : "idle"); return { ok: true, status: "ok" }; },
    undeploy() { throw new Error("scale must not undeploy"); },
    park(p) { this.parker = p; },
  };
  return { sim, stops, runs, set };
}
const quiet = { log: () => {}, warn: () => {} };
const registry = { GROUPS, MODES };
const scenario = (params = {}, extra = {}) => validateScenario({ ...emptyScenario(), subsystems: { terraforming: { mode: "scale", ...params } }, ...extra }, registry);

test("identical terraformers collapse into perRecord-sized records; the highest port levels survive", () => {
  const { sim, stops } = fakeSim();
  const inventoryBefore = structuredClone(sim.state.inventory.slots);
  const st = new Standins(sim, scenario({ perRecord: 2 }), quiet);
  // Sorted by level: heater_2 (8), heater_1 (7), heater_5 (6) survive; heater_4 -> heater_2, heater_3 -> heater_1.
  assert.deepEqual(stops, ["heater_4", "heater_3"]);
  assert.deepEqual(st.report().scale.records, { heater_2: 2, heater_1: 2, heater_5: 1 });
  assert.equal(sim.state.machines.heater_2.data.scale, 2);
  assert.equal(sim.state.machines.heater_5.data.scale, 1);
  assert.equal(sim.state.machines.heater_6.data.scale, undefined, "a group of one is left alone");
  assert.ok(sim.state.machines.heater_7, "an idle machine is not identical to running ones");
  assert.ok(sim.state.machines.heater_8 && sim.state.machines.heater_9 && sim.state.machines.heater_8.data.scale === undefined, "Mk IV stays out");
  // A member stays deployed with its script stopped: same building slot, same id, no output.
  assert.ok(sim.state.machines.heater_3 && sim.state.machines.heater_4);
  assert.equal(sim.state.machines.heater_3.data.scale, undefined);
  assert.equal(sim.state.scripts.heater_3.status, "stopped");
  assert.deepEqual(sim.state.inventory.slots, inventoryBefore, "nothing enters the Inventory");
  assert.equal(st.ghosts.terraforming, 2, "the members' stopped scripts are ghosts");
  assert.deepEqual(st.report().stopped.terraforming, ["heater_4", "heater_3"]);
  // Survivors and the lone members run the Level-1 stand-in; the members' slots keep their source.
  for (const id of ["heater_1", "heater_2", "heater_5", "heater_6"]) assert.equal(sim.state.scripts[id].source, standinSource(STANDIN_SCRIPTS.temp_heater), id);
  assert.equal(sim.state.scripts.heater_3.source, "real");
  assert.equal(sim.state.scripts.heater_7.source, "real");
  assert.equal(sim.state.scripts.o2gen_1.source, standinSource(STANDIN_SCRIPTS.oxygen_generator));
  assert.equal(st.modes.terraforming, "scale");
  const r = st.report().scale;
  assert.deepEqual(r.members, ["heater_4", "heater_3"]);
  assert.deepEqual(r.refused, {});
  assert.deepEqual(r.stalled, []);
  assert.deepEqual(r.minLevel, { heater_2: 8, heater_1: 7, heater_5: 6 });
});

test("perRecord and max must be positive integers", () => {
  for (const params of [{ perRecord: 0 }, { max: -3 }, { perRecord: 2.5 }]) {
    const { sim, stops } = fakeSim();
    assert.throws(() => new Standins(sim, scenario(params), quiet), /scale: (perRecord|max) must be a positive integer/);
    assert.deepEqual(stops, [], "nothing stopped before the check");
  }
});

test("round-robin fills the records evenly when several members go to each", () => {
  const levels = Object.fromEntries(Array.from({ length: 7 }, (_, i) => [`h_${i + 1}`, 7 - i]));
  const { sim } = fakeSim({ levels });
  const st = new Standins(sim, scenario({ perRecord: 3 }), quiet);
  // 7 members, 3 per record -> 3 records: h_1..3 survive, 4 extra members round-robin: 3, 2, 2.
  assert.deepEqual(st.report().scale.records, { h_1: 3, h_2: 2, h_3: 2 });
});

test("max caps the scaled members; a refused stop keeps that member real", () => {
  const { sim, stops } = fakeSim({ refuse: { heater_5: true } });
  const warned = [];
  const st = new Standins(sim, scenario({ max: 4 }), { log: () => {}, warn: m => warned.push(m) });
  // n = 4 of 5 -> one record on heater_2; heater_1, heater_5, heater_4 to stop; heater_3 stays real.
  assert.deepEqual(stops, ["heater_1", "heater_4"]);
  assert.deepEqual(st.report().scale.records, { heater_2: 3 });
  assert.deepEqual(st.report().scale.refused, { heater_5: "script.stop refused" });
  assert.match(warned.join("\n"), /scale stop heater_5 refused \(heater_5\); it stays real/);
  assert.equal(sim.state.machines.heater_3.data.scale, undefined);
  assert.equal(sim.state.scripts.heater_5.source, standinSource(STANDIN_SCRIPTS.temp_heater), "a refused member runs the stand-in like any real one");
  assert.equal(st.ghosts.terraforming, 2);
});

test("a member with one refused slot of two starts the stopped one again and stays real", () => {
  const { sim, runs } = fakeSim({ levels: { heater_1: 8, heater_2: 7 }, refuse: { heater_2b: true } });
  sim.state.machines.heater_2.scriptSlots = ["heater_2", "heater_2b"];
  sim.state.scripts.heater_2b = { id: "heater_2b", status: "running", source: "real" };
  sim.h.core.scriptScheduler.scripts.set("heater_2b", { status: "waiting" });
  const st = new Standins(sim, scenario(), quiet);
  assert.deepEqual(runs, ["heater_2"]);
  assert.equal(sim.state.scripts.heater_2.status, "running");
  assert.deepEqual(st.report().scale.records, { heater_1: 1 });
  assert.deepEqual(st.report().scale.refused, { heater_2: "script.stop refused" });
  assert.deepEqual(st.report().stopped.terraforming, []);
});

test("without the scale feature the group falls back to standin and says so", () => {
  const { sim, stops } = fakeSim({ features: { scale: false } });
  const warned = [];
  const st = new Standins(sim, scenario(), { log: () => {}, warn: m => warned.push(m) });
  assert.deepEqual(stops, []);
  assert.equal(st.modes.terraforming, "standin");
  assert.equal(st.report().scale, undefined);
  assert.ok(st.report().standin);
  assert.match(warned.join("\n"), /scale unavailable \(the scale anchors did not match this simworker build\); falling back to standin/);
  assert.equal(sim.state.machines.heater_2.data.scale, undefined);
});

test("a record whose port level stays 0 for STALL_TICKS warns once", () => {
  const { sim } = fakeSim({ levels: { heater_1: 0, heater_2: 0, heater_3: 0 } });
  const warned = [];
  const st = new Standins(sim, scenario(), { log: () => {}, warn: m => warned.push(m) });
  assert.deepEqual(st.report().scale.records, { heater_1: 3 });
  for (let t = 600; t < STALL_TICKS; t += 600) st.pass(t);
  assert.deepEqual(st.report().scale.stalled, []);
  st.pass(STALL_TICKS);
  st.pass(STALL_TICKS + 600);
  assert.deepEqual(st.report().scale.stalled, ["heater_1"]);
  assert.equal(warned.filter(m => /starved/.test(m)).length, 1);
  assert.match(warned.find(m => /starved/.test(m)), /scale record heater_1 \(x3\) starved: steam_in_level at 0 for 6000 ticks; lower perRecord/);
  // A refill resets the clock.
  sim.state.machines.heater_1.data.steam_in_level = 4;
  st.pass(STALL_TICKS + 1200);
  assert.equal(st.report().scale.minLevel.heater_1, 0);
});

test("scale sweeps the stopped members' archive records; a refused member keeps its own", () => {
  const { sim } = fakeSim({ refuse: { heater_3: true } });
  sim.setArchive("fluid_routing.tank_assignments", { heater_4: "tank_1", heater_3: "tank_1", heater_2: "tank_2" });
  sim.setArchive("script.park_holds", { heater_4: 99 });
  sim.setArchive("script.parked", { heater_4: { mode: "stopped" } });
  const st = new Standins(sim, scenario({ perRecord: 2 }), quiet);
  assert.deepEqual(st.report().scale.members, ["heater_4"]);
  assert.deepEqual(sim.archive["fluid_routing.tank_assignments"], { heater_3: "tank_1", heater_2: "tank_2" });
  assert.deepEqual(sim.archive["script.park_holds"], {});
  assert.deepEqual(sim.archive["script.parked"], { heater_4: { mode: "stopped" } }, "the repo profile keeps script.parked (its skipKeys)");
  assert.deepEqual(st.report().leftovers, { "fluid_routing.tank_assignments": 1, "script.park_holds": 1 });
  sim.setArchive("script.restart_requests", { heater_4: 1 }); // the member's slot id is dead too (slot id == machine id here)
  st.pass(100);
  assert.deepEqual(sim.archive["script.restart_requests"], {});
});

test("a member a real script starts again is stopped again, even with sweep false", () => {
  for (const sweep of [true, false]) {
    const { sim, set } = fakeSim();
    const st = new Standins(sim, scenario({ perRecord: 2 }, sweep ? {} : { sweep: false }), quiet);
    set("heater_3", "running");
    st.pass(1);
    assert.equal(sim.state.scripts.heater_3.status, "stopped", `sweep ${sweep}`);
    assert.deepEqual(st.report().revived, { heater_3: 1 });
  }
});
