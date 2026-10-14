import { test } from "node:test";
import assert from "node:assert/strict";
import { Standins, GROUPS, MODES } from "../standins.mjs";
import { emptyScenario, validateScenario } from "../scenario.mjs";
import { addAt, countAt, takeAt } from "../stacks.mjs";

// Logistics `mover` (phase 3): the haulers stop, a direct mover serves
// logistics.requests from the nearest outpost (or the shop) with travel time
// and overflow retry, publishing its own logistics.pickups entries.
const ITEM = "iron_ingot";
const KEY = `pull:standin_mover:outpost_2:${ITEM}:outpost_home`;
const ARRIVE = 50 + Math.round(10 * 500 / 12); // loadTicks + 500 m at 12 m/s = 467
const OUTPOSTS = [{ id: "outpost_home", x: 0, y: 0, isHome: true }, { id: "outpost_2", x: 300, y: 400 }];

function fakeSim({ inventory = 0, cap = 10000, buyOk = true, outposts = OUTPOSTS, machines = {} } = {}) {
  const state = {
    tickCount: 0,
    inventory: { slots: [inventory ? { id: ITEM, count: inventory } : null, null, null, null] },
    machines: {
      warehouse_2: { id: "warehouse_2", typeId: "warehouse", locationId: "outpost_2", itemStacks: [], itemStacksCap: cap, itemStackSlots: 8, scriptSlots: [] },
      pioneer_1: { id: "pioneer_1", typeId: "pioneer", scriptSlots: ["pioneer_1"] },
      ...machines,
    },
    scripts: { pioneer_1: { id: "pioneer_1", status: "running", source: "real" } },
    planet: { outposts },
    notebook: { entries: {} },
  };
  const commands = [], buys = [];
  const sim = {
    state,
    config: { interpreter: { stepsPerTick: 1000, totalStepsPerTick: 50000 } },
    h: {
      core: { scriptScheduler: { scripts: new Map() } },
      command(name, args) { commands.push([name, args]); state.scripts[args.scriptId].status = "stopped"; return { ok: true }; },
    },
    getArchive(key, fallback) { const e = state.notebook.entries[key]; return e ? structuredClone(e.value) : fallback; },
    setArchive(key, value) { state.notebook.entries[key] = { value: structuredClone(value) }; },
    buy(item, n) {
      buys.push([item, n]);
      if (!buyOk) return { ok: false, reason: "insufficient_credits" };
      addAt(state, "inventory", item, n);
      return { ok: true };
    },
  };
  return { sim, commands, buys };
}
const quiet = { log: () => {}, warn: () => {} };
// run.mjs passes ticks since the run's start; the mover reads ages from state.tickCount.
function make(sim, sc, io = quiet) {
  const st = new Standins(sim, sc, io);
  const pass = st.pass.bind(st);
  st.pass = t => { sim.state.tickCount = t; pass(t); };
  return st;
}
const registry = { GROUPS, MODES };
const scenario = (params = {}) => validateScenario({ ...emptyScenario(), subsystems: { logistics: { mode: "mover", ...params } } }, registry);
const request = (levels, extra = {}, tick = 0) => ({ levels, have: 0, by: "x", tick, ...extra });
const requests = (sim, byDest) => sim.setArchive("logistics.requests", byDest);
const pickups = sim => sim.getArchive("logistics.pickups", {});
const inv = sim => countAt(sim.state, "inventory", ITEM);
const at = (sim, outpost) => countAt(sim.state, "outpost:" + outpost, ITEM);

test("setup stops the haulers and counts them as ghosts", () => {
  const { sim, commands } = fakeSim();
  sim.setArchive("logistics.pickups", { "pull:pioneer_1:outpost_2:x:outpost_home": { vehicle: "pioneer_1", dest: "outpost_2", source: "outpost_home", item_id: "x", units: 3, tick: 0 }, "pull:pioneer_9:outpost_2:x:outpost_home": { vehicle: "pioneer_9", dest: "outpost_2", source: "outpost_home", item_id: "x", units: 3, tick: 0 } });
  const st = make(sim, scenario(), quiet);
  assert.deepEqual(commands, [["script.stop", { scriptId: "pioneer_1" }]]);
  assert.equal(st.ghosts.logistics, 1);
  assert.equal(st.modes.logistics, "mover");
  assert.deepEqual(Object.keys(pickups(sim)), ["pull:pioneer_9:outpost_2:x:outpost_home"], "the stopped hauler's pickup is gone, the running one stays");
  assert.deepEqual(st.report().mover, { moved: {}, trips: 0, pendingUnits: 0, bought: {}, buyFailed: {} });
});

test("a deficit is loaded at once, published as a pickup and lands after the trip", () => {
  const { sim } = fakeSim({ inventory: 500 });
  const st = make(sim, scenario(), quiet);
  requests(sim, { outpost_2: { [ITEM]: request([[400, 30], [100, 100]]) } });
  st.pass(0);
  assert.equal(inv(sim), 400);
  assert.deepEqual(pickups(sim), { [KEY]: { vehicle: "standin_mover", dest: "outpost_2", source: "outpost_home", item_id: ITEM, units: 100, tick: 0, aboard: true } });
  assert.equal(at(sim, "outpost_2"), 0);
  for (let t = 1; t < ARRIVE; t++) st.pass(t);
  assert.equal(at(sim, "outpost_2"), 0, "nothing lands before the trip ends");
  assert.equal(inv(sim), 400, "the in-flight units are not loaded twice");
  st.pass(ARRIVE);
  assert.equal(at(sim, "outpost_2"), 100);
  assert.deepEqual(pickups(sim), {});
  assert.deepEqual(st.report().mover, { moved: { [ITEM]: 100 }, trips: 1, pendingUnits: 0, bought: {}, buyFailed: {} });
});

test("fresh foreign pickups count as in flight; stale ones are ignored", () => {
  const { sim } = fakeSim({ inventory: 500 });
  const st = make(sim, scenario(), quiet);
  const foreign = { vehicle: "pioneer_9", dest: "outpost_2", item_id: ITEM, units: 80, tick: 0 };
  sim.setArchive("logistics.pickups", { "pull:pioneer_9:x": foreign });
  requests(sim, { outpost_2: { [ITEM]: request([[400, 30], [100, 100]]) } });
  st.pass(0);
  assert.equal(inv(sim), 480);
  assert.equal(pickups(sim)[KEY].units, 20);
  assert.equal(pickups(sim)["pull:pioneer_9:x"].units, 80, "foreign entries are left alone");

  const stale = fakeSim({ inventory: 500 });
  const st2 = make(stale.sim, scenario(), quiet);
  stale.sim.setArchive("logistics.pickups", { "pull:pioneer_9:x": foreign });
  requests(stale.sim, { outpost_2: { [ITEM]: request([[400, 30], [100, 100]], {}, 40000) } });
  st2.pass(40000);
  assert.equal(inv(stale.sim), 400);
});

test("a source keeps its own request level and its keep", () => {
  for (const [extra, moved] of [[{}, 50], [{ keep: 480 }, 20]]) {
    const { sim } = fakeSim({ inventory: 500 });
    const st = make(sim, scenario(), quiet);
    requests(sim, { outpost_2: { [ITEM]: request([[400, 30], [100, 100]]) }, outpost_home: { [ITEM]: request([[100, 450]], extra) } });
    st.pass(0);
    assert.equal(inv(sim), 500 - moved, JSON.stringify(extra));
    assert.equal(st.report().mover.pendingUnits, moved);
  }
});

test("stale and old-shape requests are skipped", () => {
  const { sim } = fakeSim({ inventory: 500 });
  const st = make(sim, scenario(), quiet);
  requests(sim, { outpost_2: { [ITEM]: request([[100, 100]]) } });
  st.pass(6000);
  assert.equal(inv(sim), 500, "entry tick 0 at tick 6000 is stale");
  requests(sim, { outpost_2: { [ITEM]: { target: 5, have: 0, by: "x", tick: 6100 } } });
  st.pass(6100);
  assert.equal(inv(sim), 500, "old {target} shape");
  assert.equal(st.report().mover.trips, 0);
});

test("the nearest source goes first, the rest from the next one", () => {
  const warehouse_3 = { id: "warehouse_3", typeId: "warehouse", locationId: "outpost_3", itemStacks: [{ id: ITEM, count: 100 }], itemStacksCap: 10000, itemStackSlots: 8, scriptSlots: [] };
  const { sim } = fakeSim({ inventory: 100, outposts: [...OUTPOSTS, { id: "outpost_3", x: 1000, y: 0 }], machines: { warehouse_3 } });
  const st = make(sim, scenario(), quiet);
  requests(sim, { outpost_2: { [ITEM]: request([[100, 150]]) } });
  st.pass(0);
  assert.equal(inv(sim), 0);
  assert.equal(at(sim, "outpost_3"), 50);
  assert.deepEqual(st.mover.queue.map(q => [q.source, q.units]), [["outpost_home", 100], ["outpost_3", 50]]);
  assert.equal(st.report().mover.trips, 2);
  assert.equal(pickups(sim)[`pull:standin_mover:outpost_2:${ITEM}:outpost_3`].units, 50);
});

test("overflow at the dest stays aboard and retries once there is room", () => {
  const { sim } = fakeSim({ inventory: 500, cap: 60 });
  const st = make(sim, scenario(), quiet);
  requests(sim, { outpost_2: { [ITEM]: request([[100, 100]]) } });
  st.pass(0);
  st.pass(ARRIVE);
  assert.equal(at(sim, "outpost_2"), 60);
  assert.equal(pickups(sim)[KEY].units, 40);
  assert.equal(st.report().mover.pendingUnits, 40);
  takeAt(sim.state, "outpost:outpost_2", ITEM, 60);
  st.pass(ARRIVE + 100);
  assert.equal(at(sim, "outpost_2"), 40);
  assert.deepEqual(pickups(sim), {});
  assert.equal(st.report().mover.moved[ITEM], 100);
  assert.equal(st.report().mover.pendingUnits, 0);
});

test("buy: the shortfall comes from the shop as a trip from home; a failed buy is recorded once", () => {
  const { sim, buys } = fakeSim();
  const st = make(sim, scenario(), quiet);
  requests(sim, { outpost_2: { [ITEM]: request([[100, 50]], { buy: true }) } });
  st.pass(0);
  assert.deepEqual(buys, [[ITEM, 50]]);
  assert.equal(inv(sim), 0, "the bought units left the Inventory for the trip");
  assert.deepEqual(st.mover.queue.map(q => [q.source, q.units, q.arriveTick]), [["shop", 50, ARRIVE]]);
  assert.equal(pickups(sim)[`pull:standin_mover:outpost_2:${ITEM}:shop`].units, 50);
  assert.deepEqual(st.report().mover.bought, { [ITEM]: 50 });
  st.pass(ARRIVE);
  assert.equal(at(sim, "outpost_2"), 50);

  const fail = fakeSim({ buyOk: false });
  const warned = [];
  const st2 = new Standins(fail.sim, scenario(), { log: () => {}, warn: m => warned.push(m) });
  requests(fail.sim, { outpost_2: { [ITEM]: request([[100, 50]], { buy: true }) } });
  st2.pass(0);
  st2.pass(100);
  assert.equal(fail.buys.length, 2);
  assert.deepEqual(st2.report().mover, { moved: {}, trips: 0, pendingUnits: 0, bought: {}, buyFailed: { [ITEM]: "insufficient_credits" } });
  assert.equal(warned.filter(m => /buy .* failed/.test(m)).length, 1);
});

test("params are checked before any script stops", () => {
  for (const params of [{ every: 0 }, { loadTicks: 2.5 }, { speedMps: 0 }]) {
    const { sim, commands } = fakeSim();
    assert.throws(() => new Standins(sim, scenario(params), quiet), /mover: (every|loadTicks|speedMps) must be/);
    assert.deepEqual(commands, []);
  }
});

test("buy: only what landed travels, and a home request keeps the units in the Inventory", () => {
  const short = fakeSim({ inventory: 30 });
  short.sim.buy = (item, n) => { addAt(short.sim.state, "inventory", item, 10); return { ok: true }; }; // credits for 10 only
  const st = make(short.sim, scenario());
  requests(short.sim, { outpost_2: { [ITEM]: request([[100, 50]], { buy: true }) } });
  st.pass(0);
  assert.equal(inv(short.sim), 30 - 30 + 0, "home's own 30 went as a normal trip, the 10 bought left too");
  assert.deepEqual(st.mover.queue.map(q => [q.source, q.units]), [["outpost_home", 30], ["shop", 10]]);
  assert.deepEqual(st.report().mover.bought, { [ITEM]: 10 });

  const home = fakeSim();
  const st2 = make(home.sim, scenario());
  requests(home.sim, { outpost_home: { [ITEM]: request([[100, 20]], { buy: true }) } });
  st2.pass(0);
  assert.equal(inv(home.sim), 20, "bought for home: stays in the Inventory");
  assert.equal(st2.mover.queue.length, 0);
  assert.deepEqual(pickups(home.sim), {});
  assert.deepEqual(st2.report().mover.bought, { [ITEM]: 20 });
});
