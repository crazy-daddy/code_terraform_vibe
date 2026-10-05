// Build-order policy for headless runs: plays the Shop and Inventory like a
// player, from a JSON plan, so a candidate build order runs from any
// checkpoint (also before Ship Computer, when solar.py cannot buy).
// See docs/plans/buildorder_search.md.
//
// Plan:
//   {
//     "name": "baseline",
//     "stages": [                          // first stage whose `until` is unmet is active
//       { "until": { "o2": 9 }, "keep": { "battery": 3, "solar_generator": 6, "oxygen_generator": 13 } },
//       ...
//     ],
//     "opening": ["solar_generator", "battery", ...],  // optional: placed one by one, in
//                                          // order, before the stages start (waits for credits)
//     "pioneer": true,                     // buy the Pioneer + scout gear once unlocked
//     "rovers": 0,                         // rover chassis + gear once unlocked
//     "grantCredits": 0                    // calibration only: credits added at start
//   }
// `until` keys: o2 (ppt), pressure (kPa), heat (HU), tp; all must hold (>=).
// `keep` is the wanted count per typeId. Types the active stage names are
// sold down (undeploy + sell, full refund) or bought up, in `keep` order,
// while credits and base slots allow. Types it doesn't name are left alone.

// Machines that don't use a base building slot (sensors, mobile units).
const NOT_BUILDINGS = new Set(["clock", "gps", "inventory", "thermometer", "oxygen_sensor", "pressure_sensor",
  "harvester", "scanner", "rover", "pioneer"]);
export const BASE_CAPACITY = 25;
const MOBILE = new Set(["rover", "pioneer"]);
// Gear per chassis, as solar.py's VEHICLE_GEAR.
const VEHICLE_GEAR = {
  rover: { nav_module: 1, sonar_module: 1, drill_module: 1 },
  pioneer: { nav_module: 1, sonar_module: 1, battery_holder_small: 6, portable_battery: 6 },
};
const EVERY_TICKS = 50;
// Shop prices (docs/database/equipment_*.md); a sale refunds the full price.
export const PRICES = {
  solar_generator: 500, battery: 300, oxygen_generator: 1000, pressure_generator: 900, temp_heater: 800,
  charging_station: 1200, smelter: 650, bio_collector: 3000, bio_lab: 5000, bio_exchange: 4000,
  rover: 2000, pioneer: 5000, nav_module: 500, sonar_module: 800, drill_module: 1000,
  battery_holder_small: 500, portable_battery: 150, supply_dock: 5000,
};
// The Bio-Loop only works once Auto Feeders is researched (solar.py's power-on pass).
const FEEDER_TECH = "feeder_unlock";

export function pillars(st) {
  return {
    o2: st.planet.atmosphere.oxygen,
    pressure: st.planet.atmosphere.pressure,
    heat: st.planet.temperature.heatUnits,
    tp: Number(st.researchRates?.terraform?.lastValue ?? 0),
  };
}

export function counts(st) {
  const c = {};
  for (const m of Object.values(st.machines)) c[m.typeId] = (c[m.typeId] ?? 0) + 1;
  return c;
}

export function slotsUsed(st) {
  return Object.values(st.machines).filter(m => (m.locationId ?? "outpost_home") === "outpost_home" && !NOT_BUILDINGS.has(m.typeId)).length;
}

function met(until, p) {
  return Object.entries(until ?? {}).every(([k, v]) => (p[k] ?? 0) >= v);
}

// Credits plus the resale value of deployed machines, mounted gear and Inventory.
export function netWorth(st) {
  let v = st.player.credits;
  for (const m of Object.values(st.machines)) {
    v += PRICES[m.typeId] ?? 0;
    for (const id of m.mountedModules ?? []) v += PRICES[id] ?? 0;
  }
  for (const s of st.inventory.slots) if (s) v += (PRICES[s.id] ?? 0) * s.count;
  return v;
}

export class Policy {
  constructor(sim, plan, log = () => {}) {
    this.sim = sim;
    this.plan = plan;
    this.log = log;
    this.stage = -1;
    this.opening = [...(plan.opening ?? [])];
    this.failed = new Map(); // itemId -> reason of the last refused buy (logged once)
    if (plan.grantCredits) sim.state.player.credits += plan.grantCredits;
  }

  activeStage(p) {
    const i = this.plan.stages.findIndex(s => !met(s.until, p));
    return i < 0 ? this.plan.stages.length - 1 : i;
  }

  pass() {
    const st = this.sim.state;
    if (st.tickCount % EVERY_TICKS !== 0) return;
    if (this.opening.length) {
      while (this.opening.length && this.place(this.opening[0])) this.opening.shift();
      if (!this.opening.length) this.log("[policy] opening done");
      this.powerOn();
      return;
    }
    const p = pillars(st);
    const i = this.activeStage(p);
    if (i !== this.stage) {
      this.stage = i;
      this.log(`[policy] stage ${i}: keep ${JSON.stringify(this.plan.stages[i].keep)}`);
    }
    const keep = this.plan.stages[i].keep ?? {};
    const have = counts(st);
    // Sell first: frees slots and credits for the buys.
    for (const [type, want] of Object.entries(keep)) {
      for (let n = (have[type] ?? 0) - want; n > 0; n--) this.recycle(type);
    }
    // A type before a slot-filling one (keep >= BASE_CAPACITY) may take one of
    // its slots once bought, e.g. the Supply Dock when it unlocks.
    const types = Object.keys(keep);
    for (const [k, type] of types.entries()) {
      const filler = types.slice(k + 1).find(t => keep[t] >= BASE_CAPACITY && t !== type);
      const room = filler ? () => (counts(st)[filler] ?? 0) > 0 && this.recycle(filler) : null;
      for (let n = keep[type] - (counts(st)[type] ?? 0); n > 0; n--) {
        if (!this.place(type, room)) break;
      }
    }
    for (const [type, n] of [["pioneer", this.plan.pioneer ? 1 : 0], ["rover", this.plan.rovers ?? 0]]) {
      for (let k = counts(st)[type] ?? 0; k < n; k++) if (!this.place(type)) break;
    }
    this.topUpGear();
    this.powerOn();
  }

  // Powers on what is off, as solar.py's power-on pass: the Bio-Loop only
  // once Auto Feeders is researched.
  powerOn() {
    const st = this.sim.state;
    const feeders = st.unlockedTech.includes(FEEDER_TECH);
    for (const m of Object.values(st.machines)) {
      if (m.powered !== false || MOBILE.has(m.typeId) || (m.typeId.startsWith("bio_") && !feeders)) continue;
      const r = this.sim.h.command("machine.togglePower", { machineId: m.id });
      this.log(`[policy] power on ${m.id}: ${r.ok && r.result?.ok !== false ? "ok" : r.result?.reason ?? r.error}`);
    }
  }

  // Undeploys the highest-numbered machine of `type` and sells it.
  recycle(type) {
    const ids = Object.values(this.sim.state.machines).filter(m => m.typeId === type).map(m => m.id);
    const id = ids.sort((a, b) => b.localeCompare(a, undefined, { numeric: true }))[0];
    if (!id) return false;
    const u = this.sim.undeploy(id);
    if (!u.ok) { this.refused(`undeploy ${id}`, u.reason); return false; }
    const s = this.sim.sell(type, 1);
    this.log(`[policy] recycled ${id} (${s.ok ? `+${s.soldValue} cr` : s.reason})`);
    return true;
  }

  // Buys (unless Inventory holds one) and deploys one `type`.
  // `room()`, when given, frees a base slot; it runs only after the buy went
  // through, so a locked or unaffordable item never costs a slot.
  place(type, room = null) {
    const st = this.sim.state;
    const full = () => !MOBILE.has(type) && slotsUsed(st) >= BASE_CAPACITY;
    if (full() && !room) return false;
    if (!st.inventory.slots.some(s => s?.id === type)) {
      const b = this.buy(type, 1);
      if (!b.ok) { this.refused(type, b.reason); return false; }
    }
    if (full() && !room()) return false;
    const d = this.sim.deploy(type);
    if (!d.ok) { this.refused(`deploy ${type}`, d.reason); return false; }
    this.failed.delete(type);
    this.log(`[policy] deployed ${d.machineId}`);
    return true;
  }

  // Buys the gear the vehicles still lack (not mounted, not in Inventory);
  // the vehicle scripts mount it themselves.
  topUpGear() {
    const st = this.sim.state;
    const want = {};
    for (const m of Object.values(st.machines)) {
      const gear = VEHICLE_GEAR[m.typeId];
      if (!gear) continue;
      const on = {};
      for (const id of m.mountedModules ?? []) if (id) on[id] = (on[id] ?? 0) + 1;
      for (const items of Object.values(m.mountedModuleContents ?? {})) {
        for (const it of Array.isArray(items) ? items : []) {
          const id = typeof it === "string" ? it : it?.id;
          if (id) on[id] = (on[id] ?? 0) + 1;
        }
      }
      for (const [id, n] of Object.entries(gear)) want[id] = (want[id] ?? 0) + Math.max(0, n - (on[id] ?? 0));
    }
    for (const [id, n] of Object.entries(want)) {
      const held = st.inventory.slots.reduce((a, s) => a + (s?.id === id ? s.count : 0), 0);
      if (n - held <= 0) continue;
      const b = this.buy(id, n - held);
      if (b.ok) this.log(`[policy] bought ${n - held}x ${id}`);
      else this.refused(id, b.reason);
    }
  }

  // Shop buy; on a full Inventory, frees one stack of material (rover ore and
  // ingots fill it otherwise, and the Pioneer gear never lands) and retries.
  buy(id, n) {
    let b = this.sim.buy(id, n);
    if (b.ok || b.reason !== "inventory_full") return b;
    const junk = this.sim.state.inventory.slots.filter(s => s && !(s.id in PRICES)).sort((x, y) => y.count - x.count)[0];
    if (!junk) return b;
    // Raw ore and ingots can't be sold: drop them.
    let s = this.sim.sell(junk.id, junk.count);
    if (!s.ok) s = this.sim.drop(junk.id, junk.count);
    this.log(`[policy] inventory full: ${s.soldValue ? `sold ${junk.count}x ${junk.id} (+${s.soldValue} cr)` : `dropped ${junk.count}x ${junk.id}${s.ok ? "" : ` (${s.reason})`}`}`);
    return this.sim.buy(id, n);
  }

  refused(what, reason) {
    if (this.failed.get(what) === reason) return;
    this.failed.set(what, reason);
    if (reason !== "insufficient_credits") this.log(`[policy] ${what}: ${reason}`);
  }
}
