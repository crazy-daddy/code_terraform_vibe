# Self-contained early Heat Generator controller (no lib/ imports)
# Learns the optimal power (1-10) per thermal state on this machine and
# duty-cycles it against the outpost battery level.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import heater as self, BatteryComponent

ORDER = (5, 6, 4, 7, 3, 8, 2, 9, 1, 10)
POLL_S = 0.5            # thermal_state() changes only on a new day; this bounds the switch lag
DUTY_PERIOD_S = 10.0
# Battery throttle: duty 0 at or below DUTY_EMPTY, 1 at or above DUTY_FULL, linear between.
# Heat output follows efficiency only, not watts, and efficiency drops steeply off the
# optimum. So the heater runs at its optimum or at 0 (duty cycle), never at reduced watts.
DUTY_EMPTY = 0.15
DUTY_FULL = 0.35

best = {}       # thermal_state -> optimal power; no archive or bus in this tier, so per machine
power = -1      # last set_power() value
mode = ""       # "full" | "throttled" | "off", for logging transitions only

# No lib/ access in this tier: local stand-in for lib/swallow.py's swallowed().
# Logs a caught-and-recovered error at debug level (repeats at one site once).
_SWALLOW_LAST = {}


def _swallowed(where, error):
    message = f"{error!r}"
    if _SWALLOW_LAST.get(where) == message:
        return
    _SWALLOW_LAST[where] = message
    console = get_component("console")
    if console:
        console.debug(f"[swallowed] {where}: {message}")


def get_battery_pct():
    # Charge across every Battery at this outpost (Solar buys more over time);
    # 1.0 (no throttling) when there is none or it can't be read.
    level = 0.0
    capacity = 0.0
    try:
        for ref in self.outpost.buildings("battery"):
            battery: "BatteryComponent | None" = get_component(ref.id)  # type: ignore[assignment]
            if battery:
                level += battery.get_level()
                capacity += battery.get_capacity()
    except Exception as error:
        _swallowed("heater.get_battery_pct: battery read", error)
        return 1.0
    return (level / capacity) if capacity > 0 else 1.0


def scan(state):
    # Sweep powers outward from 5; stop at the first ~100 % reading.
    global power
    best_power = 5
    best_eff = -1.0
    for p in ORDER:
        self.set_power(p)
        sleep(0.2)
        eff = self.efficiency()
        if eff > best_eff:
            best_eff = eff
            best_power = p
        if eff >= 99.0:
            break
    power = -1
    print(f"[{self.id}] Learned {state}: power={best_power} eff={best_eff}%")
    return best_power


def optimal_power():
    state = self.thermal_state()
    if state not in best:
        best[state] = scan(state)
    return best[state]


while True:
    bat_pct = get_battery_pct()
    duty = min(1.0, max(0.0, (bat_pct - DUTY_EMPTY) / (DUTY_FULL - DUTY_EMPTY)))
    new_mode = "full" if duty >= 1.0 else ("off" if duty <= 0.0 else "throttled")
    if new_mode != mode:
        print(f"[{self.id}] Battery {bat_pct*100:.1f}% -> {new_mode} (duty {duty*100:.0f}%)")
        mode = new_mode

    on_s = duty * DUTY_PERIOD_S
    elapsed = 0.0
    while elapsed < DUTY_PERIOD_S:
        target = optimal_power() if elapsed < on_s else 0
        if target != power:
            self.set_power(target)
            power = target
        sleep(POLL_S)
        elapsed += POLL_S
