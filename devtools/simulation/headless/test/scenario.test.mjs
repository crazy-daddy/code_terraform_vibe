import { test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_PROFILE_PATH, emptyProfile, emptyScenario, loadProfile, mergeFlags, parseStandinFlag, validateScenario, modeOf } from "../scenario.mjs";
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
  assert.deepEqual(ok.subsystems.power, { mode: "trim", warmupTicks: 600, margin: 1.25, stopMargin: null, keepMin: 1, reevalTicks: null, quietWindows: 0, floor: "warmup", sweep: true });
  assert.equal(modeOf(ok, "factory"), "real");
  assert.throws(() => validateScenario({ ...emptyScenario(), subsystems: { kitchen: { mode: "off" } } }, registry), /unknown subsystem kitchen/);
  assert.throws(() => validateScenario({ ...emptyScenario(), subsystems: { factory: { mode: "trim" } } }, registry), /no mode "trim"/);
  assert.throws(() => validateScenario({ ...emptyScenario(), subsystems: { power: { mode: "trim", speed: 3 } } }, registry), /unknown parameter speed/);
  assert.deepEqual(validateScenario({ ...emptyScenario(), subsystems: { plants: { mode: "produce" } } }, registry).subsystems.plants, { mode: "produce", forage_h: null, rates: {}, sweep: true });
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

test("profile: the repo file by default, none for a foreign script set (no stubs, mover refused), --script-set wins over the file", () => {
  const sc = validateScenario({ ...emptyScenario() }, registry);
  assert.equal(sc.profile.name, "code_terraform");
  assert.deepEqual(Object.keys(sc.profile.stubs), ["orchestrator", "wildlife", "biomass"]);
  assert.equal(sc.profile.budget.key, "cash.budget");
  assert.equal(sc.profile.requests.key, "logistics.requests");
  assert.deepEqual(sc.sweep, { fields: ["by", "vehicle", "owner", "machine_id", "requester", "writer"], skipKeys: ["console.log_levels", "script.parked"], extraKeys: [] });
  assert.deepEqual(loadProfile("none"), emptyProfile());
  assert.deepEqual(loadProfile(DEFAULT_PROFILE_PATH).sweep.fields, sc.profile.sweep.fields);
  const none = validateScenario({ ...emptyScenario(), profile: "none", subsystems: { orchestrator: { mode: "off" } } }, registry);
  assert.equal(none.profile.name, "none");
  assert.deepEqual(none.profile.stubs, {});
  assert.equal(none.profile.budget, null);
  assert.throws(() => validateScenario({ ...emptyScenario(), profile: "none", subsystems: { logistics: { mode: "mover" } } }, registry), /no "requests" section/);
  assert.equal(mergeFlags({ ...emptyScenario(), profile: "a.json" }, { scriptSet: "none" }).profile, "none");
  assert.equal(mergeFlags({ ...emptyScenario(), profile: "a.json" }, {}).profile, "a.json");
  assert.throws(() => validateScenario({ ...emptyScenario(), sweep: { fields: [1] } }, registry), /sweep.fields must be a list of strings/);
  assert.throws(() => validateScenario({ ...emptyScenario(), profile: { ...emptyProfile(), budget: { key: "b" } } }, registry), /budget.floor must be/);
  assert.throws(() => validateScenario({ ...emptyScenario(), profile: { stub: {} } }, registry), /unknown field stub/);
  assert.throws(() => validateScenario({ ...emptyScenario(), profile: { stubs: { orchestrater: {} } } }, registry), /stubs.orchestrater is not a subsystem/);
  assert.equal(validateScenario({ ...emptyScenario(), profile: { name: "bare" } }, registry).profile.budget, null, "an object profile fills the omitted sections");
});
