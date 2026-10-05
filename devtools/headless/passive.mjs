// Passive-machine parking for headless runs (docs/plans/headless_sim.md,
// "Passive machines"). A parked script stays in the scheduler as `waiting`, so
// it still counts toward the step allowance split and its setpoints hold; it
// only runs a loop pass when a trigger below fires. The pass is the real
// Python code, so routing, feeds and edge cases stay the script's own.

const REFRESH_TICKS = 600; // one game minute: every parked script runs at least this often
// Heaters pick a setpoint per thermal state, which changes only on a new day
// (game GK(): seeded by planet.clock.dayNumber), so they wake on the day
// change. A 1-minute refresh alone lost ~4 % heat in the A/B run; with the
// day wake it matches the full run.
const FEED_LOW_FRACTION = 0.5;

function feedLow(data) {
  for (const [key, level] of Object.entries(data)) {
    if (!key.endsWith("_in_level")) continue;
    const cap = data[key.replace(/_level$/, "_capacity")];
    if (cap > 0 && level < cap * FEED_LOW_FRACTION) return true;
  }
  return false;
}

// Per type: extra trigger(machine, memo, tick, state) -> bool. memo is per machine, kept
// across ticks. Every type also wakes on power/tier change, a low input
// port and REFRESH_TICKS.
export const PASSIVE_TYPES = {
  // Waste dump at 50 (OxygenController); intake follows CO2, which moves slowly.
  oxygen_generator: m => (m.data.waste ?? 0) >= 50,
  // One sync per sweep inside the window. The script resets its synced flag
  // when it sees the gauge wrap, so it must also see a poll after each wrap.
  pressure_generator: (m, memo) => {
    const g = m.data.gauge ?? 0;
    const wrapped = memo.gauge !== undefined && g < memo.gauge - 20;
    memo.gauge = g;
    if (wrapped) return true;
    const lo = m.data.windowLow ?? 0, hi = m.data.windowHigh ?? 0;
    const inWindow = lo <= hi ? g >= lo && g <= hi : g >= lo || g <= hi;
    return inWindow && !m.data.syncCalled;
  },
  temp_heater: heaterTrigger,
  heat_generator: heaterTrigger,
};

function heaterTrigger(m, memo, tick, st) {
  const day = st.planet.clock.dayNumber;
  const newDay = memo.day !== undefined && memo.day !== day;
  memo.day = day;
  return newDay;
}

export class Parker {
  constructor(sim, types = PASSIVE_TYPES) {
    this.sim = sim;
    this.types = types;
    this.memo = new Map();
    this.wakes = 0;
  }

  // Call before every tick.
  pass() {
    const st = this.sim.state;
    const entries = this.sim.h.core.scriptScheduler.scripts;
    for (const m of Object.values(st.machines)) {
      const trigger = this.types[m.typeId];
      if (!trigger) continue;
      const entry = entries.get(m.id);
      if (!entry) continue;
      let memo = this.memo.get(m.id);
      if (!memo) this.memo.set(m.id, (memo = { lastWake: st.tickCount }));
      const changed = memo.powered !== undefined && (memo.powered !== m.powered || memo.tier !== m.data.tier);
      memo.powered = m.powered;
      memo.tier = m.data.tier;
      const fire = trigger(m, memo, st.tickCount, st) || changed || feedLow(m.data) || st.tickCount - memo.lastWake >= REFRESH_TICKS;
      if (entry.status !== "waiting" || entry.commsWait) continue;
      if (fire) {
        if (entry.waitTicks > 1) entry.waitTicks = 1;
        memo.lastWake = st.tickCount;
        this.wakes++;
      } else if (entry.waitTicks < 2) {
        entry.waitTicks = 2;
      }
    }
  }
}
