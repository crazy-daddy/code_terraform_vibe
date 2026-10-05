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
# Advisor output: printed when the phase or the actions change (at most every
# ADVISOR_MIN_S), and every ADVISOR_PERIOD_S regardless, for the readings.
ADVISOR_MIN_S = 30.0
ADVISOR_PERIOD_S = 300.0
# Reprint the status block once other output has been quiet this long after scrolling it away.
ADVISOR_QUIET_S = 8.0
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
            self._start_once(stem, info, retry_s=None, tiered_only=True)

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
            wait = STEP_RETRY_S if not previous[2] else retry_s
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
    machines = dict(state.get("machines") or {})
    machines.update(context.get("machines") or {})

    def rate(key, fallback):
        entry = rates.get(key) or {}
        return float(fallback if fallback is not None else entry.get("lastValue", 0.0)), float(entry.get("ratePerGh", 0.0))

    o2, o2_rate = rate("oxygen", atmos.get("oxygen"))
    pressure, pressure_rate = rate("pressure", atmos.get("pressure"))
    heat, heat_rate = rate("temperature", temp.get("heatUnits"))
    tp, tp_rate = rate("terraform", None)

    counts = {k: 0 for k in ("solar", "battery", "o2gen", "pressure", "heater", "smelter", "charger", "bio", "rover", "pioneer")}
    for m in machines.values():
        t = (m.get("typeId") or m.get("type") or "") if isinstance(m, dict) else ""
        if t == "solar_generator":
            counts["solar"] += 1
        elif "battery" in t:
            counts["battery"] += 1
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
        "counts": counts,
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
    if o2 < 9.0:
        milestones.append(f"9.0 ppt O2 ({o2:.3f}): Charging Station, Smelter")
    if p < 0.200:
        milestones.append(f"0.200 kPa ({p:.3f}): Rover Chassis, Drill")
    if heat < 12.0:
        milestones.append(f"12.0 HU ({heat:.1f}): Battery Holder")
    if tp < 100000:
        milestones.append(f"100,000 TP ({tp:,}): Pioneer Chassis")
    elif tp < 150000:
        milestones.append(f"150,000 TP ({tp:,}): Custom Panels, lib/ tier")

    if o2 >= 3.0:
        for cid, label, reward in CLEARANCE_CONTRACTS:
            if m["contracts"].get(cid) != "completed" and cid not in m["slot_stems"]:
                recs.append(f"Click contract '{label}' on the Contracts tab (+{reward}); its solver runs once the slot exists.")

    manual = not m["computer"]
    if o2 < 9.0:
        phase = "Oxygen rush to 9.0 ppt"
        if manual and c["o2gen"] < O2_RUSH_TARGET:
            order = oxygen_rush_order(c)
            if order:
                recs.append("Buy next: %s (%s)." % (", ".join(order), PRICE_NOTE))
    elif p < 0.200:
        phase = "Pressure rush to 0.200 kPa"
    elif heat < 12.0:
        phase = "Heat rush to 12.0 HU"
    elif tp < 100000:
        phase = "Run up to the 100k TP Pioneer breakout"
    else:
        phase = "Pioneer scouting until Custom Panels (lib/ tier)"
    if not manual:
        recs.append("Purchases: automated by solar.py's buyer (Ship Computer researched).")
    return phase, milestones, recs


# Oxygen rush purchase order. Power is bought just in time for the next O2 Generator
# instead of the full 6 Solar + 3 Battery anchor up front, so credits go to O2 first.
O2_RUSH_TARGET = 13          # 6 Solar + 3 Battery + 3 Bio + 13 O2 = 25/25 base slots
O2GEN_W = 8.0                # docs/components/oxygen_generator.md
PRESSURE_W = 7.0             # spec powerDraw
BIO_W = 6.0                  # bio_collector 5 / bio_lab 5 / bio_exchange 8 W, averaged
SOLAR_AVG_W = 122.0 / 6      # tracked 50 W panel averaged over the day (early runner: 6 panels ~ 122 W continuous)
NIGHT_H = 10.08              # lib/power_solar.py NIGHT_DURATION_HOURS
BATTERY_WH = 500.0           # spec defaultData capacity
NIGHT_MARGIN = 1.15          # lib/power_solar.py NIGHT_NEED_MARGIN
ORDER_PREVIEW = 4            # purchases shown ahead
PRICE_NOTE = "O2 1,000 / Solar 500 / Battery 300 cr"


def _ceil(x):
    n = int(x)
    return n if n >= x else n + 1


def oxygen_rush_order(counts, steps=ORDER_PREVIEW):
    """The next `steps` purchases toward O2_RUSH_TARGET Oxygen Generators: before each
    O2 Generator, the Solar (day-average output covers the load) and Battery (stored
    Wh covers the night with NIGHT_MARGIN) it needs. Other loads (Pressure, Bio) are
    estimated from their counts."""
    solar, battery, o2 = counts["solar"], counts["battery"], counts["o2gen"]
    other_w = counts["pressure"] * PRESSURE_W + counts["bio"] * BIO_W
    order = []
    while len(order) < steps and o2 < O2_RUSH_TARGET:
        load = other_w + (o2 + 1) * O2GEN_W
        if solar < _ceil(load / SOLAR_AVG_W):
            solar += 1
            order.append("Solar")
        elif battery < _ceil(load * NIGHT_H * NIGHT_MARGIN / BATTERY_WH):
            battery += 1
            order.append("Battery")
        else:
            o2 += 1
            order.append("O2 Generator")
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
