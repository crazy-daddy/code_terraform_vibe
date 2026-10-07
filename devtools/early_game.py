"""Early-game driver for `scripts_sync.py watch --early` (fresh saves, tier 0).

scripts_sync already fills every matched script slot and starts a newly filled
one. This module adds what a fresh save needs on top, ported from
`early_game.py` in https://github.com/crazy-daddy/code-terraform-earlygame-automation:

  1. First Contact onboarding. Each step's slot (boot, planet_power, ...) only
     exists once the operator clicks its button in game; sync fills it from
     `scripts/onboarding/`. Here: say which button to click next, and run the
     next undone step's slot (a filled slot that holds starter code is pushed
     but not started by sync). Until onboarding is done, sync touches only
     the slots slot_allowed() lets through (onboarding, plus the machines that
     work from the start); the rest fill in one sweep afterwards.
  2. Idle starter. A slot whose code already matched its source when it
     appeared is never "filled", so sync never starts it, and a machine that
     is still unpowered ("offline") refuses a start. Start each idle, matched
     tier-0 machine slot once per slot text; a refused start is retried every
     STEP_RETRY_S, quietly.
  3. Status block: the next onboarding click, then the speedrun advisor
     (phase, next milestones, human-only actions such as contract clicks and
     purchases before the Solar buyer takes over at Ship Computer). Printed
     when it changes, every ADVISOR_PERIOD_S, and again once sync output
     that scrolled it away has gone quiet for ADVISOR_QUIET_S.

The driver ends itself once the save reaches the lib tier: scripts_sync then
switches the watch to --apply-libs and carries on as a normal watch.

Reads only; every write into the save goes through scripts_sync's callbacks.
"""

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

# (slot stem, all.log pattern that marks it done, in-game button that creates its slot)
ONBOARDING_STEPS = (
    ("boot", r"power system can be activated|use:\s*activate_power|Turn On Power:\s*online", "Boot (Computer screen)"),
    ("planet_power", r"Turn On Power:\s*online", "Turn on Power"),
    ("planet_sensors", r"Read Sensor Data:\s*online", "Read Sensor Data"),
    ("uplink", r"Establish Uplink:\s*online", "Establish Uplink"),
    ("pressure_sensor", None, "Pressure Sensor"),
    ("oxygen_sensor", None, "Oxygen Sensor"),
)
ONBOARDING_STEMS = frozenset(stem for stem, _pattern, _label in ONBOARDING_STEPS)
# Machines that work before onboarding is done: their slots sync from the start.
EARLY_ALWAYS = frozenset(("harvester", "scanner"))
# Sensor steps are done once the machine reports repaired (workspace machines.<id>.data.repaired).
REPAIRED_SENSORS = ("pressure_sensor", "oxygen_sensor")
# A started step that is still not done after this long is started again.
STEP_RETRY_S = 60.0
# An idle machine slot is started again after this long (its machine may have been unpowered).
IDLE_RETRY_S = 20.0
# Advisor output: printed when the phase or the actions change (at most every
# ADVISOR_MIN_S), and every ADVISOR_PERIOD_S regardless, for the readings.
ADVISOR_MIN_S = 15.0
ADVISOR_PERIOD_S = 60.0
# Reprint the status block once other output has been quiet this long after scrolling it away.
ADVISOR_QUIET_S = 5.0
# Earth Clearance contracts: slot only exists after a click on the Contracts tab.
CLEARANCE_CONTRACTS = (
    ("sealed_vault", "Sealed Vault", "10,000 cr"),
    ("terminal_breach", "Alien Terminal Breach", "7,500 cr"),
    ("data_tablet", "Underground Data Tablet", "5,000 cr"),
)


@dataclass
class Hooks:
    """scripts_sync callbacks, so this module never writes into the save itself."""
    slots: Callable[[], dict]                             # {stem: workspace info (status, ...)}
    matched_text: Callable[[str, bool], Optional[str]]    # (stem, tier dirs only) -> slot file text when
                                                          # scripts/ has a source for it, else None
    restart: Callable[[str, str], bool]                   # (stem, body) -> started; quiet on refusal
    echo: Callable[[str], None]
    warn: Callable[[str], None]
    last_output: Callable[[], float]                      # monotonic time of the last terminal line


def slot_allowed(stem: str, base_name: str, onboarded: bool) -> bool:
    """Whether sync may fill/push slot `stem` (base name `base_name`) yet."""
    return onboarded or stem in ONBOARDING_STEMS or base_name in EARLY_ALWAYS


class EarlyGame:
    def __init__(self, save_dir: Path, hooks: Hooks):
        self.save_dir = save_dir
        self.hooks = hooks
        self.started: dict = {}       # {stem: (source text, monotonic start time)}
        self.next_step = None         # (stem, label, slot exists) of the next onboarding step
        self.onboarded = False
        self.last_advice = None
        self.last_advice_t = 0.0

    # ------------------------------------------------------------------ inputs
    def _log_text(self) -> str:
        path = self.save_dir / "logs" / "all.log"
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def _context(self) -> dict:
        try:
            with (self.save_dir / "codeterraform-workspace.json").open(encoding="utf-8") as fh:
                return json.load(fh).get("context") or {}
        except (OSError, ValueError):
            return {}

    def _state(self) -> dict:
        name = self.save_dir.name
        if not name.endswith("_scripts"):
            return {}
        path = self.save_dir.parent / (name[: -len("_scripts")] + ".json")
        for _attempt in range(3):  # the game locks the file for a few ms while it autosaves
            try:
                with path.open(encoding="utf-8") as fh:
                    return json.load(fh).get("state") or {}
            except (OSError, ValueError):
                time.sleep(0.1)
        return {}

    # -------------------------------------------------------------- onboarding
    def _step_done(self, stem, pattern, log_text, machines) -> bool:
        if stem in REPAIRED_SENSORS:
            return ((machines.get(stem) or {}).get("data") or {}).get("repaired") == 1
        return bool(pattern and re.search(pattern, log_text, re.IGNORECASE))

    def onboarding_pass(self) -> None:
        if self.onboarded:
            return
        log_text = self._log_text()
        machines = self._context().get("machines") or {}
        done = [self._step_done(stem, pattern, log_text, machines) for stem, pattern, _label in ONBOARDING_STEPS]
        # A later step done implies the earlier ones are (e.g. boot's own marker scrolled out).
        for i in range(len(done) - 2, -1, -1):
            done[i] = done[i] or done[i + 1]
        if all(done):
            self.onboarded = True
            self.next_step = None
            self.hooks.echo("  early onboarding complete (First Contact, sensors repaired): filling the other slots")
            return
        stem, _pattern, label = ONBOARDING_STEPS[done.index(False)]
        slots = self.hooks.slots()
        self.next_step = (stem, label, stem in slots)
        if stem in slots:
            self._start_once(stem, slots[stem], retry_s=STEP_RETRY_S, tiered_only=False)

    # ------------------------------------------------------------ idle starter
    def idle_pass(self) -> None:
        """Machine slots only (tier dirs): global categories such as contracts finish and sit idle."""
        for stem, info in self.hooks.slots().items():
            if stem in ONBOARDING_STEMS or not isinstance(info, dict) or info.get("status") != "idle":
                continue
            # Retried: a machine script stops when its machine is unpowered (bio loop) and stays idle.
            self._start_once(stem, info, retry_s=IDLE_RETRY_S, tiered_only=True)

    def _start_once(self, stem, info, retry_s, tiered_only) -> None:
        """Starts slot `stem` when scripts/ has a source for it and it is not running; once
        per slot text (a push starts it again), or again after retry_s seconds when given."""
        if info.get("status") == "running":
            return
        text = self.hooks.matched_text(stem, tiered_only)
        if text is None or not text.strip():
            return
        previous = self.started.get(stem)
        now = time.monotonic()
        if previous and previous[0] == text:
            wait = retry_s if previous[2] or retry_s is not None else STEP_RETRY_S
            if wait is None or now - previous[1] < wait:
                return
        started = self.hooks.restart(stem, text)
        self.started[stem] = (text, now, started)
        if started:
            self.hooks.echo("  early started %s.py" % stem)

    # ----------------------------------------------------------------- advisor
    def _status(self):
        """(change key, text) of the status block: the next onboarding click, or the advice."""
        if not self.onboarded:
            if self.next_step is None:
                return None, None
            stem, label, exists = self.next_step
            action = ("running %s.py" % stem) if exists else ("click '%s' in game to create the %s.py slot" % (label, stem))
            text = "  early onboarding | next: %s\n    other slots sync once onboarding is done (harvester and scanner already do)" % action
            return ("onboarding", stem, exists), text
        metrics = live_metrics(self._state(), self._context(), set(self.hooks.slots()))
        phase, milestones, recs = recommendations(metrics)
        return (phase, tuple(recs)), format_advice(metrics, phase, milestones, recs)

    def advisor_pass(self) -> None:
        key, text = self._status()
        if text is None:
            return
        now = time.monotonic()
        elapsed = now - self.last_advice_t
        quiet = now - self.hooks.last_output()
        scrolled = self.hooks.last_output() > self.last_advice_t and quiet >= ADVISOR_QUIET_S
        changed = key != self.last_advice
        if not (scrolled or (changed and elapsed >= ADVISOR_MIN_S) or elapsed >= ADVISOR_PERIOD_S
                or (changed and key and key[0] == "onboarding")):
            return
        self.hooks.echo(text)
        self.last_advice, self.last_advice_t = key, time.monotonic()

    def step(self) -> None:
        """One pass (the watch loop's 5 s cadence)."""
        self.onboarding_pass()
        self.idle_pass()
        self.advisor_pass()


# ---------------------------------------------------------------------- metrics
def live_metrics(state: dict, context: dict, slot_stems: set) -> dict:
    """Planet, credit and machine-count readings for the advisor, from the save
    state with the workspace's live machines layered on top."""
    planet = state.get("planet") or {}
    atmos = planet.get("atmosphere") or {}
    temp = planet.get("temperature") or {}
    rates = state.get("researchRates") or {}
    player = state.get("player") or {}
    state_machines = state.get("machines") or {}
    machines = dict(state_machines)
    machines.update(context.get("machines") or {})

    def rate(key, fallback):
        entry = rates.get(key) or {}
        return float(fallback if fallback is not None else entry.get("lastValue", 0.0)), float(entry.get("ratePerGh", 0.0))

    o2, o2_rate = rate("oxygen", atmos.get("oxygen"))
    pressure, pressure_rate = rate("pressure", atmos.get("pressure"))
    heat, heat_rate = rate("temperature", temp.get("heatUnits"))
    tp, tp_rate = rate("terraform", None)

    counts = {k: 0 for k in ("solar", "battery", "o2gen", "pressure", "heater", "smelter", "charger", "bio", "rover", "pioneer")}
    stored_wh = capacity_wh = 0.0
    for mid, m in machines.items():
        t = (m.get("typeId") or m.get("type") or "") if isinstance(m, dict) else ""
        if t == "solar_generator":
            counts["solar"] += 1
        elif "battery" in t:
            counts["battery"] += 1
            data = m.get("data") if "charge" in (m.get("data") or {}) else (state_machines.get(mid) or {}).get("data")
            data = data or {}
            capacity = float(data.get("capacity", BATTERY_WH) or 0.0)
            capacity_wh += capacity
            stored_wh += min(capacity, float(data.get("charge", 0.0) or 0.0))
        elif t == "oxygen_generator":
            counts["o2gen"] += 1
        elif t == "pressure_generator":
            counts["pressure"] += 1
        elif t in ("temp_heater", "heat_generator"):
            counts["heater"] += 1
        elif t == "smelter":
            counts["smelter"] += 1
        elif t in ("charging_station", "vehicle_charging_station"):
            counts["charger"] += 1
        elif t.startswith("bio_"):
            counts["bio"] += 1
        elif t in ("rover", "pioneer"):
            counts[t] += 1
    return {
        "tp": int(tp), "tp_rate": tp_rate,
        "o2": o2, "o2_rate": o2_rate,
        "pressure": pressure, "pressure_rate": pressure_rate,
        "heat": heat, "heat_rate": heat_rate,
        "credits": int(player.get("credits", 0) or 0),
        "computer": "ship_computer" in set(state.get("unlockedTech") or context.get("unlockedTech") or []),
        "automations": "automations_unlock" in set(state.get("unlockedTech") or context.get("unlockedTech") or []),
        "counts": counts,
        "power": {"day_fraction": float((planet.get("clock") or {}).get("normalized", 0.5) or 0.0),
                  "stored_wh": stored_wh, "capacity_wh": capacity_wh},
        "contracts": state.get("contractStatus") or context.get("contractStatus") or {},
        "slot_stems": slot_stems,
    }


def recommendations(m: dict):
    """(phase title, milestones, human actions). Once Ship Computer is researched the
    tier-0 Solar buyer (power/solar.py) makes every purchase below itself, so only
    human-only actions remain."""
    tp, p, o2, heat, c = m["tp"], m["pressure"], m["o2"], m["heat"], m["counts"]
    milestones, recs = [], []
    if o2 < 1.0:
        milestones.append(f"1.0 ppt O2 ({o2:.3f}): Auto Feeders, Bio-Loop")
    if o2 < 2.2 and not m["computer"]:
        milestones.append(f"2.2 ppt O2 ({o2:.3f}): ~10k TP, Ship Computer")
    if o2 < 9.0:
        milestones.append(f"9.0 ppt O2 ({o2:.3f}): Charging Station")
    if p < 0.200:
        milestones.append(f"0.200 kPa ({p:.3f}): Rover Chassis, Drill")
    if heat < 12.0:
        milestones.append(f"12.0 HU ({heat:.1f}): Battery Holder")
    if tp < 50000:
        milestones.append(f"50,000 TP ({tp:,}): Automations")
    if tp < 70000:
        milestones.append(f"70,000 TP ({tp:,}): Data Archive, lib/ tier")

    if o2 >= 3.0:
        for cid, label, reward in CLEARANCE_CONTRACTS:
            if m["contracts"].get(cid) != "completed" and cid not in m["slot_stems"]:
                recs.append(f"Click contract '{label}' on the Contracts tab (+{reward}); its solver runs once the slot exists.")

    # Stages of solar.py's STAGES build order (docs/autoplay/early_optimization.md).
    manual = not m["computer"]
    if manual:
        phase = "Oxygen to 2.2 ppt (Ship Computer)"
        order = oxygen_rush_order(c, m["power"])
        if order:
            recs.append("Buy next: %s (%s)." % (", ".join(order), PRICE_NOTE))
    elif o2 < 2.2:
        phase = "Oxygen to 2.2 ppt"
    elif heat < 12.0:
        phase = "Heaters to 12.0 HU"
    elif o2 < 10.0:
        phase = "Oxygen to 10 ppt"
    else:
        phase = "Pressure to 70k TP (lib/ tier)"
    if not manual:
        recs.append("Purchases: automated by solar.py's buyer (Ship Computer researched).")
    if m["automations"] and not any(stem.startswith("automation_") for stem in m["slot_stems"]):
        recs.append("Create one Automation (Computer > Automations > + New Automation) and type "
                    "'# ct-automation: control_room_automation' into it: sync fills it at 70k TP, "
                    "where it takes over the buyer.")
    return phase, milestones, recs


# Manual purchase order until Ship Computer (solar.py's first STAGES stage: O2 fills the
# base). Just in time: an O2 Generator comes next whenever the batteries carry the grid
# with it through the next night; power is bought only when they would not.
O2_RUSH_TARGET = 13          # 6 Solar + 3 Battery + 3 Bio + 13 O2 = 25/25 base slots
BASE_SLOTS = 25
RUSH_SOLAR_MAX = 6
RUSH_BATTERY_MAX = 3
O2GEN_W = 8.0                # docs/components/oxygen_generator.md
PRESSURE_W = 7.0             # spec powerDraw
HEATER_W = 5.0               # spec powerDraw
BIO_W = 6.0                  # bio_collector 5 / bio_lab 5 / bio_exchange 8 W, averaged
SOLAR_PEAK_W = 50.0          # spec generatorPeakOutput; solar.py tracks the sun (full tilt factor)
# Solar efficiency over the day (simworker clock, planet.daylight): (day fraction, efficiency)
# corners of a piecewise-linear curve. Averages ~0.39, i.e. ~19.5 W per tracked panel.
DAYLIGHT_CURVE = ((0.0, 0.0), (0.25, 0.0), (0.30, 0.5), (0.38, 1.0), (0.54, 1.0), (0.71, 0.5), (0.83, 0.0), (1.0, 0.0))
DAWN_FRACTION = 0.25
MORNING_PEAK_FRACTION = 0.38  # panels reach full output; the night's drain ends about here
DUSK_FRACTION = 0.83
BATTERY_WH = 500.0           # spec defaultData capacity; a Shop battery arrives fully charged
LOAD_MARGIN = 1.15           # lib/power_solar.py NIGHT_NEED_MARGIN
SIM_STEP_H = 0.05
# Hours of load the grid may run short before dawn: a brief brownout costs little
# (docs/autoplay/early_optimization.md "The amount of power does matter"), a battery costs 300 cr and a slot.
BROWNOUT_OK_H = 0.5
ORDER_PREVIEW = 4            # purchases shown ahead
PRICE_NOTE = "O2 1,000 / Solar 500 / Battery 300 cr"


def solar_efficiency(day_fraction):
    f = day_fraction % 1.0
    for (f0, e0), (f1, e1) in zip(DAYLIGHT_CURVE, DAYLIGHT_CURVE[1:]):
        if f < f1:
            return e0 + (f - f0) / (f1 - f0) * (e1 - e0)
    return 0.0


def lowest_charge_through_night(day_fraction, stored_wh, capacity_wh, solar, load_w):
    """Lowest stored Wh from now until the morning peak after the next night (through
    tonight when it is day; the weak dawn sun still drains the batteries), with
    load_w * LOAD_MARGIN drawn and the panels charging up to capacity_wh.
    Negative: the grid browns out before then."""
    to_peak = (MORNING_PEAK_FRACTION - day_fraction) % 1.0
    if day_fraction >= DAWN_FRACTION and day_fraction < MORNING_PEAK_FRACTION:
        to_peak += 1.0
    hours = to_peak * 24.0
    stored, lowest, f = stored_wh, stored_wh, day_fraction
    for _ in range(_ceil(hours / SIM_STEP_H)):
        stored += (solar * SOLAR_PEAK_W * solar_efficiency(f) - load_w * LOAD_MARGIN) * SIM_STEP_H
        stored = min(stored, capacity_wh)
        lowest = min(lowest, stored)
        f += SIM_STEP_H / 24.0
    return lowest


def solar_wh_until_dusk(day_fraction):
    """Wh one tracked panel still collects today (0 at night, also before dawn)."""
    wh, f = 0.0, day_fraction
    if f < DAWN_FRACTION:
        return 0.0
    while f < DUSK_FRACTION:
        wh += SOLAR_PEAK_W * solar_efficiency(f) * SIM_STEP_H
        f += SIM_STEP_H / 24.0
    return wh


def _ceil(x):
    n = int(x)
    return n if n >= x else n + 1


def oxygen_rush_order(counts, power, steps=ORDER_PREVIEW):
    """The next `steps` purchases toward O2_RUSH_TARGET Oxygen Generators, from the live
    battery charge and time of day: an O2 Generator whenever the grid still lasts
    through the next night with it, else power. A Solar Panel when the panels can't
    cover a day's load and a new one still collects half a Battery's charge today (a
    Battery only bridges one night and costs a slot); else a Battery, which arrives charged. Other loads (Pressure, Heaters, Bio) come from their counts."""
    solar, battery, o2 = counts["solar"], counts["battery"], counts["o2gen"]
    stored, capacity = power["stored_wh"], power["capacity_wh"]
    f = power["day_fraction"]
    other_w = counts["pressure"] * PRESSURE_W + counts.get("heater", 0) * HEATER_W + counts["bio"] * BIO_W
    daily_solar_wh = SOLAR_PEAK_W * 24.0 * sum((f1 - f0) * (e0 + e1) / 2 for (f0, e0), (f1, e1) in zip(DAYLIGHT_CURVE, DAYLIGHT_CURVE[1:]))
    base_other = counts["pressure"] + counts.get("heater", 0) + counts["bio"]
    order = []
    while len(order) < steps and o2 < O2_RUSH_TARGET:
        load = other_w + (o2 + 1) * O2GEN_W

        def lowest(s=solar, extra_wh=0.0):
            return lowest_charge_through_night(f, stored + extra_wh, capacity + extra_wh, s, load)

        if lowest() >= -BROWNOUT_OK_H * load * LOAD_MARGIN:
            o2 += 1
            order.append("O2 Generator")
            continue
        # Panels short of a day's load: Solar while a new panel still collects half a
        # Battery's charge today. Night, late afternoon, or a storage gap: Battery.
        short_daily = solar * daily_solar_wh < load * LOAD_MARGIN * 24.0
        want_solar = short_daily and solar_wh_until_dusk(f) >= BATTERY_WH / 2
        # The 25-slot base layout caps power at O2_RUSH_TARGET's mix; a capped need is
        # met by the O2 Generator anyway (the brownout it risks is the cheaper loss).
        slots_left = BASE_SLOTS - (solar + battery + o2 + base_other) - (O2_RUSH_TARGET - o2)
        solar_ok = solar < RUSH_SOLAR_MAX and slots_left > 0
        battery_ok = battery < RUSH_BATTERY_MAX and slots_left > 0
        if want_solar and not solar_ok:
            want_solar = False
        if not want_solar and not battery_ok:
            o2 += 1
            order.append("O2 Generator")
            continue
        if not want_solar:
            battery += 1
            stored += BATTERY_WH
            capacity += BATTERY_WH
            order.append("Battery")
        else:
            solar += 1
            order.append("Solar")
    # All O2 Generators bought: the base slots still free complete the 6 Solar + 3 Battery layout.
    while len(order) < steps and BASE_SLOTS - (solar + battery + o2 + base_other) > 0:
        if solar < RUSH_SOLAR_MAX:
            if solar_wh_until_dusk(f) < BATTERY_WH / 2:
                break  # too late in the day for a new panel to pay off: wait for morning
            solar += 1
            order.append("Solar")
        elif battery < RUSH_BATTERY_MAX:
            battery += 1
            order.append("Battery")
        else:
            break
    return order


def format_advice(m: dict, phase: str, milestones: list, recs: list) -> str:
    c = m["counts"]
    lines = [
        "  early advisor | %s" % phase,
        "    TP %s (+%.0f/h) | O2 %.3f ppt | P %.3f kPa | Heat %.1f HU | %s cr"
        % (format(m["tp"], ","), m["tp_rate"], m["o2"], m["pressure"], m["heat"], format(m["credits"], ",")),
        "    solar %d, battery %d, o2 %d, pressure %d, heater %d, bio %d, smelter %d, charger %d, rover %d, pioneer %d"
        % (c["solar"], c["battery"], c["o2gen"], c["pressure"], c["heater"], c["bio"], c["smelter"], c["charger"], c["rover"], c["pioneer"]),
    ]
    lines += ["    next: " + text for text in milestones[:3]]
    lines += ["    do:   " + text for text in recs]
    return "\n".join(lines)
