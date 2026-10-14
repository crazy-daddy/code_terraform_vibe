import { test } from "node:test";
import assert from "node:assert/strict";
import { stores, count, add, take, room, countAt, addAt, takeAt, Flows } from "../stacks.mjs";

function fakeState() {
  return {
    inventory: { slots: [{ id: "iron_ore", count: 5 }, null, null] },
    machines: {
      warehouse_1: { id: "warehouse_1", typeId: "warehouse", itemStacks: [{ id: "iron_ingot", count: 10 }], itemStacksCap: 100, itemStackSlots: 2, locationId: "outpost_2" },
      warehouse_2: { id: "warehouse_2", typeId: "warehouse", itemStacks: [], itemStacksCap: 50, itemStackSlots: 8 },
      fabricator_3: { id: "fabricator_3", typeId: "fabricator", itemStacks: [], itemStacksCap: 200, itemStackSlots: 8, locationId: "outpost_2" },
      heater_1: { id: "heater_1", typeId: "temp_heater", data: {} },
    },
    tickCount: 0,
  };
}

test("inventory: count, add into existing and free slots, take", () => {
  const st = fakeState();
  const inv = stores(st, "inventory")[0];
  assert.equal(count(inv, "iron_ore"), 5);
  assert.equal(add(inv, "iron_ore", 3), 3);
  assert.equal(add(inv, "seeds", 4), 4);
  assert.equal(add(inv, "salt", 1), 1);
  assert.equal(add(inv, "glass", 1), 0, "no free slot left");
  assert.equal(take(inv, "iron_ore", 20), 8);
  assert.equal(st.inventory.slots[0], null, "emptied slot is freed");
});

test("machine store: unit cap and stack slots", () => {
  const st = fakeState();
  const w = stores(st, "warehouse_1")[0];
  assert.equal(room(w, "iron_ingot"), 90);
  assert.equal(add(w, "iron_ingot", 100), 90);
  assert.equal(add(w, "glass", 1), 0, "cap reached");
  assert.equal(take(w, "iron_ingot", 50), 50);
  assert.equal(add(w, "glass", 5), 5, "second stack slot");
  assert.equal(add(w, "salt", 5), 0, "slot count reached");
  assert.equal(take(w, "glass", 5), 5);
  assert.equal(w.m.itemStacks.length, 1, "empty stack removed");
});

test("addresses: outpost stores, home includes the Inventory, bad address throws", () => {
  const st = fakeState();
  assert.deepEqual(stores(st, "outpost:outpost_2").map(s => s.id), ["warehouse_1"], "fabricators are not stores");
  assert.deepEqual(stores(st, "outpost:outpost_home").map(s => s.id), ["inventory", "warehouse_2"]);
  assert.equal(countAt(st, "outpost:outpost_2", "iron_ingot"), 10);
  assert.equal(addAt(st, "outpost:outpost_home", "glass", 60), 60, "spreads over the stores");
  assert.equal(takeAt(st, "outpost:outpost_home", "glass", 100), 60);
  assert.throws(() => stores(st, "nope"), /no store at nope/);
  assert.throws(() => stores(st, "heater_1"), /holds no item stacks/);
});

test("flows: keep tops up every pass, rate_h accumulates, after drains arrivals", () => {
  const st = fakeState();
  const flows = new Flows(st, [
    { item: "seeds", keep: 10 },
    { item: "steel", rate_h: 360, at: "outpost:outpost_2" },
    { item: "iron_ore", rate_h: -360 },
    { item: "forage", after: 3 },
  ], { every: 100 });
  for (let t = 1; t <= 100; t++) flows.pass(t);
  assert.equal(countAt(st, "inventory", "seeds"), 10);
  assert.equal(countAt(st, "outpost:outpost_2", "steel"), 1, "360/h over 100 ticks is 1 unit");
  assert.equal(countAt(st, "inventory", "iron_ore"), 4);
  add(stores(st, "inventory")[0], "forage", 7);
  flows.pass(101);
  flows.pass(102);
  assert.equal(countAt(st, "inventory", "forage"), 7, "not due yet");
  flows.pass(104);
  assert.equal(countAt(st, "inventory", "forage"), 0, "drained 3 ticks after arrival");
  const r = Object.fromEntries(flows.report().map(f => [f.item, f]));
  assert.equal(r.seeds.added, 10);
  assert.equal(r.forage.removed, 7);
  assert.equal(r.iron_ore.removed, 1);
  assert.throws(() => new Flows(st, [{ item: "x", keep: 1, after: 2 }]), /exactly one of/);
});
