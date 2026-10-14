# Heat Generator stand-in for the headless harness (docs/headless/standins.md).
# Stands in for lib/terraforming.py HeatController: learns the optimal power
# (1-10) per thermal state and shares it through `heat.optimal_setpoints`.
# Reads `standin.terraforming` (written by the JS harness): per-heater power
# overrides and the steam-guard list. While the guard is open a starved Mk III
# steam_in moves to the next source (_feed.py, prepended by the harness).
# Deployed only by the harness into a terraformer's script slot, never into a save.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _feed import ensure_feed
    from user_stubs import heater as self

POLL_S = 2.0

best = {}  # thermal_state -> optimal power
power = -1  # last set_power() value
guard_closed = False
saved_target = ""
last_day = None
last_state = None
nb = get_component("notebook")
clock = get_component("clock")
outpost_id = None


def feed_pass():
    global clock, outpost_id
    if guard_closed:
        return
    try:
        if self.tier() != 3:
            return
        port = self.steam_in
        if not port:
            return
        if clock is None:
            clock = get_component("clock")
        tick = clock.tick() if clock else -1
        if outpost_id is None:
            outpost_id = self.outpost.id
    except Exception:
        return
    ensure_feed(port, "steam", outpost_id, tick, self.id)


def read_cfg():
    try:
        return nb.get("standin.terraforming", {}) if nb else {}
    except Exception:
        return {}


def steam_guard(cfg):
    global guard_closed, saved_target
    try:
        if self.tier() != 3:
            return
    except Exception:
        return
    off = self.id in (cfg.get("guard_off") or [])
    if off == guard_closed:
        return
    try:
        if off:
            port = self.steam_in
            if port:
                connected = port.connected_id()
                if connected:
                    saved_target = connected
                port.disconnect()
            print(f"[{self.id}] Steam guard closed: steam_in released")
        else:
            if saved_target:
                self.steam_in.connect(saved_target)
            print(f"[{self.id}] Steam guard open: steam_in -> {saved_target or '(none)'}")
        guard_closed = off
    except Exception:
        return


def store_best():
    if not nb:
        return
    try:
        nb.set("heat.optimal_setpoints", best)
    except Exception:
        return


def load_best():
    if not nb:
        return
    try:
        stored = nb.get("heat.optimal_setpoints", {})
    except Exception:
        return
    if isinstance(stored, dict):
        best.update(stored)


def scan(state):
    # Sweep 1-10 like HeatController; stop at the first ~100 % reading.
    best_power = 5
    best_eff = -1.0
    for p in range(1, 11):
        self.set_power(p)
        eff = self.efficiency()
        if eff > best_eff:
            best_eff = eff
            best_power = p
        if eff >= 99.0:
            break
    best[state] = best_power
    store_best()
    print(f"[{self.id}] Learned {state}: power={best_power} eff={best_eff}%")
    return best_power


def learned_power(cfg):
    global last_day, last_state, power
    override = (cfg.get("heater_power") or {}).get(self.id)
    if override is not None:
        try:
            forced = int(override)
        except Exception:
            forced = 0
        if 1 <= forced <= 10:
            return forced
    state = self.thermal_state()
    day = None
    try:
        clock = get_component("clock")
        if clock:
            day = clock.get_day()
    except Exception:
        day = None
    if day == last_day and state == last_state and state in best:
        return power
    last_day = day
    last_state = state
    if state in best:
        return best[state]
    load_best()
    if state in best:
        return best[state]
    power = -1
    return scan(state)


def apply_power(cfg):
    global power
    try:
        target = learned_power(cfg)
        if target != power:
            self.set_power(target)
            power = target
    except Exception:
        return


while True:
    if nb is None:
        nb = get_component("notebook")
    cfg = read_cfg()
    steam_guard(cfg)
    feed_pass()
    apply_power(cfg)
    sleep(POLL_S)
