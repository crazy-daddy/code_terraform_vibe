import { test } from "node:test";
import assert from "node:assert/strict";
import { Standins, GROUPS, MODES, STALL_TICKS, STANDIN_SCRIPTS, standinSource } from "../standins.mjs";
import { emptyScenario, validateScenario } from "../scenario.mjs";

// Terraforming `scale` (phase 2): identical terraformers collapse into
// records of at most perRecord, the rest are undeployed through sim.undeploy()
// and their kits leave the Inventory; survivors carry data.scale and the
// Level-1 stand-in.
const KIT = "temp_heater_kit";
function fakeSim({ levels = { heater_1: 7, heater_2: 8, heater_3: 3, heater_4: 5, heater_5: 6 }, refuse = {}, features = { scale: true, machineRevision: true } } = {}) {
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
    inventory: { slots: [{ id: "iron_ingot", count: 3 }, null, { id: KIT, count: 1 }, null] },
    machines,
    scripts: {},
    planet: { power: { subnets: {}, machineSubnets: Object.fromEntries(Object.keys(machines).map(id => [id, "subnet_0"])) } },
    notebook: { entries: {} },
  };
  for (const id of Object.keys(machines)) state.scripts[id] = { id, status: id === "heater_7" ? "idle" : "running", source: "real" };
  const sched = new Map(Object.values(state.scripts).map(s => [s.id, { status: s.status === "running" ? "waiting" : s.status }]));
  const undeployed = [];
  const sim = {
    state, features,
    config: { interpreter: { stepsPerTick: 1000, totalStepsPerTick: 50000 } },
    h: { core: { scriptScheduler: { scripts: sched } }, skipSystems: new Set(), command() { throw new Error("no command expected"); } },
    archive: {},
    setArchive(key, value) { this.archive[key] = structuredClone(value); },
    getArchive(key, fallback) { return key in this.archive ? structuredClone(this.archive[key]) : fallback; },
    setScript(id, source, { run }) { state.scripts[id].source = source; state.scripts[id].status = run ? "running" : "idle"; return { ok: true, status: "ok" }; },
    undeploy(id) {
      if (refuse[id]) return { ok: false, reason: refuse[id] };
      const m = state.machines[id];
      if (!m) return { ok: false, reason: "machine_not_found" };
      // As the game does: kit into the Inventory (merged or a free slot), slot stopped, machine gone.
      const slots = state.inventory.slots;
      const stack = slots.find(s => s?.id === KIT);
      if (stack && undeployed.length % 2 === 0) stack.count++;
      else slots[slots.indexOf(null)] = { id: KIT, count: 1 };
      for (const sid of m.scriptSlots) { state.scripts[sid].status = "stopped"; sched.get(sid).status = "stopped"; }
      delete state.machines[id];
      undeployed.push(id);
      return { ok: true };
    },
    park(p) { this.parker = p; },
  };
  return { sim, undeployed };
}
const quiet = { log: () => {}, warn: () => {} };
const registry = { GROUPS, MODES };
const scenario = (params = {}, extra = {}) => validateScenario({ ...emptyScenario(), subsystems: { terraforming: { mode: "scale", ...params } }, ...extra }, registry);

test("identical terraformers collapse into perRecord-sized records; the highest port levels survive", () => {
  const { sim, undeployed } = fakeSim();
  const inventoryBefore = structuredClone(sim.state.inventory.slots);
  const st = new Standins(sim, scenario({ perRecord: 2 }), quiet);
  // Sorted by level: heater_2 (8), heater_1 (7), heater_5 (6) survive; heater_4 -> heater_2, heater_3 -> heater_1.
  assert.deepEqual(undeployed, ["heater_4", "heater_3"]);
  assert.deepEqual(st.report().scale.records, { heater_2: 2, heater_1: 2, heater_5: 1 });
  assert.equal(sim.state.machines.heater_2.data.scale, 2);
  assert.equal(sim.state.machines.heater_5.data.scale, 1);
  assert.equal(sim.state.machines.heater_6.data.scale, undefined, "a group of one is left alone");
  assert.ok(sim.state.machines.heater_7, "an idle machine is not identical to running ones");
  assert.ok(sim.state.machines.heater_8 && sim.state.machines.heater_9 && sim.state.machines.heater_8.data.scale === undefined, "Mk IV stays out");
  assert.equal(sim.state.machines.heater_3, undefined);
  assert.deepEqual(sim.state.inventory.slots, inventoryBefore, "the kits left the Inventory again");
  assert.deepEqual(st.report().scale.kits, { [KIT]: 2 });
  assert.equal(st.ghosts.terraforming, 2, "the undeployed members' scripts are ghosts");
  // Survivors and the lone members run the Level-1 stand-in; the undeployed slots are untouched.
  for (const id of ["heater_1", "heater_2", "heater_5", "heater_6"]) assert.equal(sim.state.scripts[id].source, standinSource(STANDIN_SCRIPTS.temp_heater), id);
  assert.equal(sim.state.scripts.heater_3.source, "real");
  assert.equal(sim.state.scripts.heater_7.source, "real");
  assert.equal(sim.state.scripts.o2gen_1.source, standinSource(STANDIN_SCRIPTS.oxygen_generator));
  assert.equal(st.modes.terraforming, "scale");
  const r = st.report().scale;
  assert.deepEqual(r.undeployed, ["heater_4", "heater_3"]);
  assert.deepEqual(r.refused, {});
  assert.deepEqual(r.stalled, []);
  assert.deepEqual(r.minLevel, { heater_2: 8, heater_1: 7, heater_5: 6 });
});

test("perRecord and max must be positive integers", () => {
  for (const params of [{ perRecord: 0 }, { max: -3 }, { perRecord: 2.5 }]) {
    const { sim, undeployed } = fakeSim();
    assert.throws(() => new Standins(sim, scenario(params), quiet), /scale: (perRecord|max) must be a positive integer/);
    assert.deepEqual(undeployed, [], "nothing undeployed before the check");
  }
});

test("round-robin fills the records evenly when several members go to each", () => {
  const levels = Object.fromEntries(Array.from({ length: 7 }, (_, i) => [`h_${i + 1}`, 7 - i]));
  const { sim } = fakeSim({ levels });
  const st = new Standins(sim, scenario({ perRecord: 3 }), quiet);
  // 7 members, 3 per record -> 3 records: h_1..3 survive, 4 extra members round-robin: 3, 2, 2.
  assert.deepEqual(st.report().scale.records, { h_1: 3, h_2: 2, h_3: 2 });
});

test("max caps the scaled members; a refused undeploy keeps that member real", () => {
  const { sim, undeployed } = fakeSim({ refuse: { heater_5: "cargo_present" } });
  const st = new Standins(sim, scenario({ max: 4 }), quiet);
  // n = 4 of 5 -> one record on heater_2; heater_1, heater_5, heater_4 to undeploy; heater_3 stays real.
  assert.deepEqual(undeployed, ["heater_1", "heater_4"]);
  assert.deepEqual(st.report().scale.records, { heater_2: 3 });
  assert.deepEqual(st.report().scale.refused, { heater_5: "cargo_present" });
  assert.ok(sim.state.machines.heater_5 && sim.state.machines.heater_3);
  assert.equal(sim.state.machines.heater_3.data.scale, undefined);
  assert.equal(st.ghosts.terraforming, 2);
});

test("without the scale feature the group falls back to standin and says so", () => {
  const { sim, undeployed } = fakeSim({ features: { scale: false, machineRevision: true } });
  const warned = [];
  const st = new Standins(sim, scenario(), { log: () => {}, warn: m => warned.push(m) });
  assert.deepEqual(undeployed, []);
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
