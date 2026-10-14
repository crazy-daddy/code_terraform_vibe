import { test } from "node:test";
import assert from "node:assert/strict";
import { classify, TYPES, GROUPS, MODES, countsForAllowance } from "../standins.mjs";

function fakeState() {
  const machines = {
    heater_1: { id: "heater_1", typeId: "temp_heater", scriptSlots: ["heater_1"] },
    turbine_1: { id: "turbine_1", typeId: "steam_turbine", scriptSlots: ["turbine_1"] },
    fabricator_3: { id: "fabricator_3", typeId: "fabricator", scriptSlots: ["fabricator_3"] },
    seed_maker_1: { id: "seed_maker_1", typeId: "seed_maker", scriptSlots: ["seed_maker_1"] },
    gas_tank_1: { id: "gas_tank_1", typeId: "gas_tank", scriptSlots: [] },
    clock: { id: "clock", typeId: "clock", scriptSlots: [] },
    widget_1: { id: "widget_1", typeId: "widget", scriptSlots: ["widget_1"] },
    drone_2: { id: "drone_2", typeId: "drone_large", scriptSlots: ["drone_2", "ghost_slot"] },
  };
  const scripts = {};
  for (const id of ["heater_1", "turbine_1", "fabricator_3", "seed_maker_1", "widget_1", "drone_2", "boot", "uplink", "planet_power", "oxygen_sensor", "contract_relay_hack", "mystery_7"]) scripts[id] = { id, status: "running", source: "" };
  scripts.automation_1 = { id: "automation_1", status: "running", source: "# ct-automation: control_room_automation\nwhile True: pass" };
  scripts.panel_2 = { id: "panel_2", status: "running", source: "# ct-panel: cash_panel\n" };
  scripts.panel_9 = { id: "panel_9", status: "idle", source: "" };
  scripts.o2gen_51 = { id: "o2gen_51", status: "idle", source: "" }; // recycled machine's slot
  return { machines, scripts };
}

test("machines classify by type, orphans by marker, id or system name", () => {
  const { groups, unclassified, orphans } = classify(fakeState());
  assert.deepEqual(groups.terraforming.slots, ["heater_1"]);
  assert.deepEqual(groups.power.slots, ["turbine_1"]);
  assert.deepEqual(groups.factory.slots, ["fabricator_3"]);
  assert.deepEqual(groups.plants.slots, ["seed_maker_1"]);
  assert.deepEqual(groups.logistics.slots, ["drone_2"], "a slot id without a script entry is dropped");
  assert.deepEqual(groups.orchestrator.slots.sort(), ["automation_1", "panel_2", "panel_9"]);
  assert.deepEqual(groups.system.slots.sort(), ["boot", "contract_relay_hack", "oxygen_sensor", "planet_power", "uplink"]);
  assert.deepEqual(unclassified.sort(), ["mystery_7", "widget_1"]);
  assert.equal(orphans, 1, "idle slot of a recycled machine is only counted");
  assert.equal(groups.power.machines.length, 1);
});

test("assign moves a type to another group", () => {
  const { groups } = classify(fakeState(), { seed_maker: "factory" });
  assert.deepEqual(groups.factory.slots.sort(), ["fabricator_3", "seed_maker_1"]);
  assert.deepEqual(groups.plants.slots, []);
});

test("registry is consistent: every type's group exists and has a mode table", () => {
  for (const [typeId, row] of Object.entries(TYPES)) {
    assert.ok(GROUPS[row.group], `${typeId} -> ${row.group}`);
    assert.ok(MODES[row.group]?.real, `${row.group} has a real mode`);
    assert.ok(row.reason, `${typeId} has a reason`);
  }
  for (const g of Object.keys(GROUPS)) assert.ok(MODES[g], `${g} has modes`);
  assert.equal(countsForAllowance("waiting"), true);
  assert.equal(countsForAllowance("paused"), false);
});
