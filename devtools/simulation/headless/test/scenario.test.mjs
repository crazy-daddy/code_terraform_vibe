import { test } from "node:test";
import assert from "node:assert/strict";
import { emptyScenario, mergeFlags, parseStandinFlag, validateScenario, modeOf } from "../scenario.mjs";
import { GROUPS, MODES } from "../standins.mjs";

const registry = { GROUPS, MODES };

test("legacy flags map onto the scenario", () => {
  const sc = mergeFlags(emptyScenario(), { onlyScripts: "harvester_1,crop_automator_2", stock: ["seeds_basic=40"], drain: ["forage:600"], park: true });
  assert.equal(sc.default, "off");
  assert.deepEqual(sc.keep, ["harvester_1", "crop_automator_2"]);
  assert.deepEqual(sc.flows, [{ item: "seeds_basic", keep: 40, at: "inventory" }, { item: "forage", after: 600, at: "inventory" }]);
  assert.deepEqual(sc.subsystems.terraforming, { mode: "park" });
  assert.throws(() => mergeFlags(emptyScenario(), { stock: ["seeds"] }), /--stock/);
  assert.throws(() => mergeFlags(emptyScenario(), { drain: ["forage"] }), /--drain/);
});

test("--park does not override a scenario's terraforming mode; --standin does", () => {
  const base = { ...emptyScenario(), subsystems: { terraforming: { mode: "off" } } };
  assert.equal(mergeFlags(base, { park: true }).subsystems.terraforming.mode, "off");
  const sc = mergeFlags(base, { standin: ["terraforming=park", "power=trim,margin=1.5,stopMargin=1.6,keepMin=2"] });
  assert.equal(sc.subsystems.terraforming.mode, "park");
  assert.deepEqual(sc.subsystems.power, { mode: "trim", margin: 1.5, stopMargin: 1.6, keepMin: 2 });
  assert.deepEqual(parseStandinFlag("factory=off"), ["factory", { mode: "off" }]);
  assert.throws(() => parseStandinFlag("factory"), /--standin/);
});

test("validation fills defaults and rejects unknown names, params and planned modes", () => {
  const ok = validateScenario({ ...emptyScenario(), subsystems: { power: { mode: "trim" } } }, registry);
  assert.deepEqual(ok.subsystems.power, { mode: "trim", warmupTicks: 600, margin: 1.25, stopMargin: null, keepMin: 1, reevalTicks: null, quietWindows: 0, floor: "warmup" });
  assert.equal(modeOf(ok, "factory"), "real");
  assert.throws(() => validateScenario({ ...emptyScenario(), subsystems: { kitchen: { mode: "off" } } }, registry), /unknown subsystem kitchen/);
  assert.throws(() => validateScenario({ ...emptyScenario(), subsystems: { factory: { mode: "trim" } } }, registry), /no mode "trim"/);
  assert.throws(() => validateScenario({ ...emptyScenario(), subsystems: { power: { mode: "trim", speed: 3 } } }, registry), /unknown parameter speed/);
  assert.deepEqual(validateScenario({ ...emptyScenario(), subsystems: { plants: { mode: "produce" } } }, registry).subsystems.plants, { mode: "produce", forage_h: null, rates: {} });
  assert.throws(() => validateScenario({ ...emptyScenario(), default: "park" }, registry), /default must be/);
  assert.throws(() => validateScenario({ ...emptyScenario(), assign: { seed_maker: "food" } }, registry), /assign.seed_maker/);
  assert.throws(() => validateScenario({ ...emptyScenario(), ghosts: { factory: -1 } }, registry), /ghosts.factory/);
  assert.throws(() => validateScenario({ ...emptyScenario(), flows: [{ item: "x" }] }, registry), /exactly one of/);
});

test("default off applies to unlisted groups, system stays real", () => {
  const sc = validateScenario({ ...emptyScenario(), default: "off", subsystems: { plants: { mode: "real" } } }, registry);
  assert.equal(modeOf(sc, "factory"), "off");
  assert.equal(modeOf(sc, "plants"), "real");
  assert.equal(GROUPS.system.fixed, true);
});
