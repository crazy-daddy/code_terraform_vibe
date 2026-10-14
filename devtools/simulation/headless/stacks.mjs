// Item stores in a headless run, read and written straight in the state
// (no game command: a command would notify the UI, drop overflow on the
// field or refuse a locked slot). Used by the stand-ins (standins.mjs) for
// stock top-ups, producer/consumer flows and the direct hauler.
//
// Stores:
//   base Inventory   state.inventory.slots: Array<{id, count} | null>, one stack per slot
//   store machines   m.itemStacks: Array<{id, count}>, m.itemStacksCap (units in total),
//                    m.itemStackSlots (distinct stacks), m.locationId (outpost; the
//                    home outpost's machines carry "outpost_home" or no locationId).
//                    Warehouses and Storage Bins hold m.bins instead:
//                    {slot_i: {itemId, stacks: [{id, count}], capacity}}; a bin takes
//                    any item while empty and only its own item once it holds one
//                    (the worker's bin add: itemId ?? first stack id, room = capacity
//                    - held), and its itemId resets when it runs empty.
//
// A store address (`at` in a scenario) is "inventory", a machine id, or
// "outpost:<id>" (the outpost's store machines, plus the Inventory at home).
// Docs: docs/headless/standins.md ("Stores").

export const HOME_OUTPOST = "outpost_home";

// Machines whose itemStacks count as outpost stock (scripts/4_controlpanel/lib/storage.py
// STORAGE_TYPE_IDS, plus Drone Depots, whose freight the haulers also read).
export const STORE_TYPES = new Set(["warehouse", "large_warehouse", "storage_bin",
  "drone_station", "drone_station_medium", "drone_station_large"]);

export function inventoryStore(state) {
  return { kind: "inventory", id: "inventory", slots: state.inventory.slots };
}

export function machineStore(m) {
  return { kind: Array.isArray(m.itemStacks) ? "machine" : "bins", id: m.id, m };
}

const isStore = m => Array.isArray(m.itemStacks) || (m.bins && typeof m.bins === "object");
const bins = m => Object.values(m.bins).filter(b => b && typeof b === "object");
const binStacks = b => (b.stacks ??= []);
const binCap = b => (Number.isSafeInteger(b.capacity) && b.capacity >= 0 ? b.capacity : 0); // the worker's zb()
const binHeld = b => binStacks(b).reduce((n, s) => n + s.count, 0);
const binItem = b => (binHeld(b) > 0 ? (b.itemId ?? binStacks(b)[0].id) : null);

export function machineLocation(m) {
  return m.locationId ?? HOME_OUTPOST;
}

// Stores behind an address, in fill order (Inventory first at home).
export function stores(state, at) {
  if (at === "inventory") return [inventoryStore(state)];
  const outpost = /^outpost:(.+)$/.exec(at)?.[1];
  if (outpost) {
    const list = outpost === HOME_OUTPOST ? [inventoryStore(state)] : [];
    for (const m of Object.values(state.machines)) {
      if (STORE_TYPES.has(m.typeId) && isStore(m) && machineLocation(m) === outpost) list.push(machineStore(m));
    }
    return list;
  }
  const m = state.machines[at];
  if (!m) throw new Error(`stacks: no store at ${at} (want "inventory", "outpost:<id>" or a machine id)`);
  if (!isStore(m)) throw new Error(`stacks: ${at} (${m.typeId}) holds no item stacks`);
  return [machineStore(m)];
}

export function count(store, item) {
  if (store.kind === "inventory") return store.slots.reduce((n, s) => n + (s?.id === item ? s.count : 0), 0);
  if (store.kind === "bins") return bins(store.m).reduce((n, b) => n + binStacks(b).reduce((k, s) => k + (s.id === item ? s.count : 0), 0), 0);
  return store.m.itemStacks.reduce((n, s) => n + (s.id === item ? s.count : 0), 0);
}

export function total(store) {
  if (store.kind === "inventory") return store.slots.reduce((n, s) => n + (s?.count ?? 0), 0);
  if (store.kind === "bins") return bins(store.m).reduce((n, b) => n + binHeld(b), 0);
  return store.m.itemStacks.reduce((n, s) => n + s.count, 0);
}

// Units of `item` the store can still take.
export function room(store, item) {
  if (store.kind === "inventory") {
    // One stack per slot, no per-stack cap in the state; a free slot takes any amount.
    return store.slots.some(s => s?.id === item || !s) ? Infinity : 0;
  }
  if (store.kind === "bins") {
    return bins(store.m).reduce((n, b) => { const it = binItem(b); return it === null || it === item ? n + Math.max(0, binCap(b) - binHeld(b)) : n; }, 0);
  }
  const m = store.m;
  const cap = Number.isFinite(m.itemStacksCap) ? m.itemStacksCap : Infinity;
  const slots = Number.isFinite(m.itemStackSlots) ? m.itemStackSlots : Infinity;
  const has = m.itemStacks.some(s => s.id === item);
  if (!has && m.itemStacks.length >= slots) return 0;
  return Math.max(0, cap - total(store));
}

// Adds up to n units; returns the units added.
export function add(store, item, n) {
  if (n <= 0) return 0;
  if (store.kind === "inventory") {
    const slots = store.slots;
    const i = slots.findIndex(s => s?.id === item);
    if (i >= 0) { slots[i].count += n; return n; }
    const j = slots.findIndex(s => !s);
    if (j < 0) return 0;
    slots[j] = { id: item, count: n };
    return n;
  }
  if (store.kind === "bins") {
    // Bins already holding the item first, then empty ones (the worker's fill order).
    let left = n;
    const list = bins(store.m);
    for (const b of [...list.filter(b => binItem(b) === item), ...list.filter(b => binItem(b) === null)]) {
      if (left <= 0) break;
      const k = Math.min(left, Math.max(0, binCap(b) - binHeld(b)));
      if (k <= 0) continue;
      const s = binStacks(b).find(s => s.id === item);
      if (s) s.count += k;
      else binStacks(b).push({ id: item, count: k });
      b.itemId = item;
      left -= k;
    }
    return n - left;
  }
  const k = Math.min(n, room(store, item));
  if (k <= 0) return 0;
  const stacks = store.m.itemStacks;
  const s = stacks.find(s => s.id === item);
  if (s) s.count += k;
  else stacks.push({ id: item, count: k });
  return k;
}

// Removes up to n units; returns the units removed.
export function take(store, item, n) {
  if (n <= 0) return 0;
  let left = n;
  if (store.kind === "inventory") {
    const slots = store.slots;
    for (let i = 0; i < slots.length && left > 0; i++) {
      if (slots[i]?.id !== item) continue;
      const k = Math.min(left, slots[i].count);
      slots[i].count -= k;
      left -= k;
      if (!slots[i].count) slots[i] = null;
    }
    return n - left;
  }
  if (store.kind === "bins") {
    for (const b of bins(store.m)) {
      if (left <= 0) break;
      if (binItem(b) !== item) continue;
      const stacks = binStacks(b);
      for (let i = stacks.length - 1; i >= 0 && left > 0; i--) {
        if (stacks[i].id !== item) continue;
        const k = Math.min(left, stacks[i].count);
        stacks[i].count -= k;
        left -= k;
        if (!stacks[i].count) stacks.splice(i, 1);
      }
      if (binHeld(b) <= 0) b.itemId = null; // the worker resets an emptied bin's filter
    }
    return n - left;
  }
  const stacks = store.m.itemStacks;
  for (let i = stacks.length - 1; i >= 0 && left > 0; i--) {
    if (stacks[i].id !== item) continue;
    const k = Math.min(left, stacks[i].count);
    stacks[i].count -= k;
    left -= k;
    if (!stacks[i].count) stacks.splice(i, 1);
  }
  return n - left;
}

// The same over every store behind an address.
export function countAt(state, at, item) {
  return stores(state, at).reduce((n, s) => n + count(s, item), 0);
}
export function addAt(state, at, item, n) {
  let left = n;
  for (const s of stores(state, at)) {
    if (left <= 0) break;
    left -= add(s, item, left);
  }
  return n - left;
}
export function takeAt(state, at, item, n) {
  let left = n;
  for (const s of stores(state, at)) {
    if (left <= 0) break;
    left -= take(s, item, left);
  }
  return n - left;
}

// Producer / consumer flows (scenario `flows`), one pass every `every` ticks:
//   {item, keep: N, at}        top the store up to N units (old --stock)
//   {item, rate_h: ±N, at}     add (or remove, negative) N units per game hour
//   {item, after: TICKS, at}   remove what arrived TICKS ago (old --drain)
// Items change in state directly; totals per flow come back in report().
export const FLOW_EVERY_TICKS = 100;
export const TICKS_PER_HOUR = 36000;

export class Flows {
  constructor(state, specs, { every = FLOW_EVERY_TICKS } = {}) {
    this.state = state;
    this.every = every;
    this.flows = specs.map(spec => {
      const f = { ...spec, at: spec.at ?? "inventory", added: 0, removed: 0, balance: 0, queue: [] };
      if (f.after !== undefined) f.last = countAt(state, f.at, f.item);
      const kinds = ["keep", "rate_h", "after"].filter(k => f[k] !== undefined);
      if (kinds.length !== 1) throw new Error(`flows: ${JSON.stringify(spec)} needs exactly one of keep, rate_h, after`);
      return f;
    });
  }

  // Call after every tick with the tick count.
  pass(tick) {
    const st = this.state;
    for (const f of this.flows) {
      if (f.after !== undefined) {
        // Every tick: what arrived since the last pass leaves `after` ticks later.
        const now = countAt(st, f.at, f.item);
        if (now > f.last) f.queue.push([tick, now - f.last]);
        let due = 0;
        while (f.queue.length && tick - f.queue[0][0] >= f.after) due += f.queue.shift()[1];
        due = Math.min(due, now); // a script may have moved some away meanwhile
        if (due) f.removed += takeAt(st, f.at, f.item, due);
        f.last = countAt(st, f.at, f.item);
        continue;
      }
      if (tick % this.every !== 0) continue;
      if (f.keep !== undefined) {
        const short = f.keep - countAt(st, f.at, f.item);
        if (short > 0) f.added += addAt(st, f.at, f.item, short);
      } else {
        f.balance += f.rate_h * this.every / TICKS_PER_HOUR;
        const whole = f.balance > 0 ? Math.floor(f.balance) : Math.ceil(f.balance);
        if (whole > 0) {
          const n = addAt(st, f.at, f.item, whole);
          f.added += n;
          f.balance -= n; // a full store keeps the balance for later
        } else if (whole < 0) {
          const n = takeAt(st, f.at, f.item, -whole);
          f.removed += n;
          f.balance += n;
        }
      }
    }
  }

  report() {
    return this.flows.map(f => ({ item: f.item, at: f.at, ...(f.keep !== undefined ? { keep: f.keep } : f.after !== undefined ? { after: f.after } : { rate_h: f.rate_h }), added: f.added, removed: f.removed }));
  }
}
