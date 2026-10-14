# Headless stand-in for the Pressure Generator controller (lib/terraforming.py
# PressureController): syncs the resonance sweep once per sweep inside the
# window [next_window_low, next_window_high] and paces its polls to the measured
# sweep speed; a starved Mk III water_in moves to the next source (_feed.py,
# prepended by the harness). No archive, no fuel rods.
# Deployed only by the headless harness (docs/headless/standins.md), never into a save.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _feed import ensure_feed
    from user_stubs import pressure as self

TICKS_PER_SECOND = 10
MIN_POLL_S = 0.1
MAX_POLL_S = 5.0
WAKE_FRACTION = 0.7

synced = False
last_gauge = -1.0
last_tick = -1
gauge_per_tick = 0.0
clock = get_component("clock")
first_sync_logged = False
outpost_id = None


def feed_pass(tick):
    global outpost_id
    try:
        if self.tier() != 3:
            return
        port = self.water_in
        if not port:
            return
        if outpost_id is None:
            outpost_id = self.outpost.id
    except Exception:
        return
    ensure_feed(port, "water", outpost_id, tick, self.id)


while True:
    if clock is None:
        clock = get_component("clock")

    try:
        g = self.gauge()
        lo = self.next_window_low()
        hi = self.next_window_high()
    except Exception:
        sleep(MIN_POLL_S)
        continue

    tick = -1
    if clock is not None:
        try:
            tick = clock.tick()
        except Exception:
            tick = -1

    # Gauge wrap (~100 -> ~0) starts a new sweep; a rising gauge measures the sweep speed
    if last_gauge >= 0 and g < last_gauge and last_gauge - g > 20:
        synced = False
    elif tick > last_tick >= 0 and g > last_gauge >= 0:
        gauge_per_tick = (g - last_gauge) / (tick - last_tick)
    last_gauge = g
    last_tick = tick

    feed_pass(tick)
    in_window = (lo <= g <= hi) if lo <= hi else (g >= lo or g <= hi)

    if not synced and in_window:
        status = ""
        try:
            status = self.sync().status
        except Exception:
            status = "error"
        if status == "ok":
            synced = True
            if not first_sync_logged:
                first_sync_logged = True
                print(f"[{self.id}] First resonance sync: gauge {g:.1f} in [{lo:.1f}, {hi:.1f}]")

    # Pacing per PressureController.next_poll_seconds: wake just before the next target
    rate = gauge_per_tick
    if rate <= 0:
        wait = MIN_POLL_S
    else:
        if synced or (lo <= hi and g > hi):
            distance = 100.0 - g
        elif g < lo:
            distance = lo - g
        elif lo > hi and g > hi:
            distance = lo - g
        else:
            distance = 0.0
        if distance <= 0:
            wait = MIN_POLL_S
        else:
            seconds = distance / rate / TICKS_PER_SECOND * WAKE_FRACTION
            wait = min(MAX_POLL_S, max(MIN_POLL_S, seconds))

    sleep(wait)
