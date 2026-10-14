import { test } from "node:test";
import assert from "node:assert/strict";
import { Standins, GROUPS, MODES, STANDIN_KEY, STANDIN_SCRIPTS, standinSource } from "../standins.mjs";
import { emptyScenario, validateScenario } from "../scenario.mjs";

// Terraforming `standin` (phase 1): the Python stand-ins replace the running
// slots, the steam guard reads the steam tanks and writes STANDIN_KEY.
function fakeSim({ tanks = {} } = {}) {
  const state = {
    tickCount: 0,
    inventory: { slots: [] },
    machines: {
      heater_1: { id: "heater_1", typeId: "temp_heater", scriptSlots: ["heater_1"], data: { tier: 3 }, powered: true },
      heater_2: { id: "heater_2", typeId: "temp_heater", scriptSlots: ["heater_2"], data: { tier: 2 }, powered: true },
      o2gen_1: { id: "o2gen_1", typeId: "oxygen_generator", scriptSlots: ["o2gen_1"], data: {}, powered: true },
      pressure_1: { id: "pressure_1", typeId: "pressure_generator", scriptSlots: ["pressure_1"], data: {}, powered: true },
      pressure_2: { id: "pressure_2", typeId: "pressure_generator", scriptSlots: ["pressure_2"], data: {}, powered: true },
      ...tanks,
    },
    scripts: {},
    planet: { power: { subnets: {}, machineSubnets: { heater_1: "subnet_0", heater_2: "subnet_0" } } },
    notebook: { entries: {} },
  };
  for (const id of ["heater_1", "heater_2", "o2gen_1", "pressure_1", "pressure_2", "boot"]) state.scripts[id] = { id, status: id === "pressure_2" || id === "boot" ? "idle" : "running", source: "real" };
  const sched = new Map(Object.values(state.scripts).map(s => [s.id, { status: s.status === "running" ? "waiting" : s.status }]));
  const set = [];
  const sim = {
    state,
    config: { interpreter: { stepsPerTick: 1000, totalStepsPerTick: 50000 } },
    h: { core: { scriptScheduler: { scripts: sched } }, skipSystems: new Set(), command() { throw new Error("no command expected"); } },
    archive: {},
    setArchive(key, value) { this.archive[key] = structuredClone(value); },
    setScript(id, source, { run }) { set.push(id); state.scripts[id].source = source; state.scripts[id].status = run ? "running" : "idle"; return { ok: true, status: "ok" }; },
    park(p) { this.parker = p; },
  };
  return { sim, set };
}
const quiet = { log: () => {}, warn: () => {} };
const registry = { GROUPS, MODES };
const tank = (id, level, cap) => ({ id, typeId: "gas_tank", stringData: { fluid: "steam" }, data: { level, capacity: cap, gas_in_level: 0, gas_in_capacity: 10 } });

test("standin replaces the running terraformer slots with the type's script, no ghosts", () => {
  const { sim, set } = fakeSim();
  const sc = validateScenario({ ...emptyScenario(), subsystems: { terraforming: { mode: "standin" } }, keep: ["o2gen_1"] }, registry);
  const st = new Standins(sim, sc, quiet);
  assert.deepEqual(set.sort(), ["heater_1", "heater_2", "pressure_1"], "kept and idle slots untouched");
  assert.equal(sim.state.scripts.heater_1.source, standinSource(STANDIN_SCRIPTS.temp_heater));
  assert.equal(sim.state.scripts.pressure_1.source, standinSource(STANDIN_SCRIPTS.pressure_generator));
  assert.equal(sim.state.scripts.o2gen_1.source, "real");
  assert.equal(st.ghosts.terraforming, undefined);
  const r = st.report();
  assert.deepEqual(r.standin.scripts, { heater_1: "heater.py", heater_2: "heater.py", pressure_1: "pressure.py" });
  assert.deepEqual(r.standin.failed, []);
  // No steam tank: the guard stays open and the key is written at setup.
  assert.deepEqual(sim.archive[STANDIN_KEY], { heater_power: {}, guard_off: [], tick: 0 });
  assert.equal(r.standin.pool, null);
});

test("every stand-in script has no lib import, binds self and carries the feed keeper", () => {
  for (const file of new Set(Object.values(STANDIN_SCRIPTS))) {
    const src = standinSource(file);
    assert.match(src, /from user_stubs import \w+ as self/, file);
    assert.doesNotMatch(src, /^(from|import) (?!typing|user_stubs)/m, `${file}: imports only typing / user_stubs`);
    assert.doesNotMatch(src, /^from _feed import/m, `${file}: the _feed import sits under TYPE_CHECKING only`);
    assert.match(src, /^def ensure_feed\(/m, `${file}: _feed.py prepended`);
    assert.match(src, /while True:/, file);
  }
});

test("steam guard closes below stop, reopens at start, every guardTicks, Mk III heaters only", () => {
  const { sim } = fakeSim({ tanks: { gas_tank_1: tank("gas_tank_1", 80, 100), gas_tank_2: { ...tank("gas_tank_2", 0, 100), stringData: { fluid: "water" } } } });
  const sc = validateScenario({ ...emptyScenario(), subsystems: { terraforming: { mode: "standin", guardTicks: 10, heaterPower: 4 } } }, registry);
  const st = new Standins(sim, sc, quiet);
  assert.deepEqual(sim.archive[STANDIN_KEY], { heater_power: { heater_1: 4, heater_2: 4 }, guard_off: [], tick: 0 }, "a number applies to every heater");
  assert.equal(st.report().standin.pool, 0.8, "the water tank does not count");
  sim.state.machines.gas_tank_1.data.level = 40;
  st.pass(5);
  assert.deepEqual(sim.archive[STANDIN_KEY].guard_off, [], "not yet due");
  st.pass(10);
  assert.deepEqual(sim.archive[STANDIN_KEY].guard_off, ["heater_1"], "40 % < 50 %, the Mk II heater is never guarded");
  sim.state.machines.gas_tank_1.data.level = 60;
  st.pass(20);
  assert.deepEqual(sim.archive[STANDIN_KEY].guard_off, ["heater_1"], "60 % is inside the hysteresis band");
  sim.state.machines.gas_tank_1.data.level = 70;
  st.pass(30);
  assert.deepEqual(sim.archive[STANDIN_KEY], { heater_power: { heater_1: 4, heater_2: 4 }, guard_off: [], tick: 30 });
  // Every steam tank on the network counts, whatever its outpost or subnet.
  sim.state.machines.gas_tank_3 = tank("gas_tank_3", 0, 100);
  st.pass(40);
  assert.equal(st.report().standin.pool, 0.35);
  assert.deepEqual(sim.archive[STANDIN_KEY].guard_off, ["heater_1"]);
});
