# Oxygen Generator stand-in for the headless harness (docs/headless/standins.md).
# Replaces lib/terraforming.py OxygenController: intake = ambient CO2 / 10, dump
# waste at >= 50; a starved Mk III water_in moves to the next source (_feed.py,
# prepended by the harness). No archive, no fuel rods.
# Deployed only by the headless harness into a terraformer's script slot, never
# into a save.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _feed import ensure_feed
    from user_stubs import o2gen as self

POLL_S = 1.0

atm = None
last_intake = -1.0
clock = get_component("clock")
outpost_id = None


def feed_pass():
    global clock, outpost_id
    try:
        if self.tier() != 3:
            return
        port = self.water_in
        if not port:
            return
        if clock is None:
            clock = get_component("clock")
        tick = clock.tick() if clock else -1
        if outpost_id is None:
            outpost_id = self.outpost.id
    except Exception:
        return
    ensure_feed(port, "water", outpost_id, tick, self.id)


while True:
    sleep(POLL_S)
    if atm is None:
        atm = get_component("atmosphere")
        if atm is None:
            continue
    waste = -1.0
    try:
        co2 = atm.get_co2()
        waste = self.waste()
    except Exception:
        co2 = None
    if co2 is None or waste < 0:
        continue
    target = co2 / 10.0
    if abs(target - last_intake) > 0.01:
        self.set_intake(target)
        last_intake = target
    if waste >= 50:
        self.dump_waste()
        print(f"[{self.id}] Dumped waste at {waste:.1f}.")
    feed_pass()
