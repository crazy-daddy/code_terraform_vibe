"""
Thermal vent cycle log (Control Room Automation, every VENT_POLL_TICKS).

A vent's active/dormant durations read only after a Deep survey
(ThermalVent.cycle_active_minutes()/cycle_dormant_minutes()), but its phase
reads from a basic survey on (current_phase()). The game's cycle is a fixed
period, so timing one full active and one full dormant phase gives the same
durations a Deep survey would. This module polls every surveyed vent's phase
and records, per vent:

    steam.vent_cycles = {vent_id: {
        "phase": "active" | "dormant",   # last phase seen
        "since": game hours | None,      # estimated start of that phase (None = unknown)
        "since_err": game hours,         # +- uncertainty of "since"
        "seen": game hours,              # last poll
        "active": minutes | None,        # active phase length
        "dormant": minutes | None,       # dormant phase length
        "rate": t/h | None,              # base_steam_rate() (wide survey)
        "deep": bool,                    # durations came from a Deep survey
        "capped": bool,                  # has_cap()
    }}

A flip seen between two polls is placed at their midpoint, +- half the gap.
A phase length is stored only when the uncertainty of both ends adds up to at
most MAX_DURATION_ERROR_HOURS, so a busy Automation (long polls) or a restart
gap never records a wrong length; it waits for the next clean cycle. After a
gap longer than MAX_SAME_PHASE_GAP_HOURS the phase start is dropped even when
the phase looks unchanged: the vent may have flipped twice meanwhile.
Deep-surveyed vents take the API's durations and are not timed.

Only this module writes the key (one writer, the Automation); entries for
vents no longer in the journal are pruned. Readers use cycle_minutes().

Steam plan (STEAM_PLAN_KEY, for the STATUS card): every capped vent is taken
as feeding one shared steam network. Each vent's average output is
rate x active / (active + dormant); their sum over TURBINE_STEAM_T_PER_H is
the turbine count the vents carry nonstop. Tank steam for N turbines: each
vent covers its share of the load (N x 90 t/h x its share of the average)
through its own dormant phase, summed, minus the Caps' and turbines' own
buffers. That sum is what the worst phase alignment needs, so no phase
offsets are required. A value not known yet (no wide survey, phase not timed)
takes a default from the game's vent generator range (DEFAULT_*), and the plan
is marked estimated.
"""
from archive import archive
from tree_console import TreeConsole
from swallow import swallowed

VENT_CYCLES_KEY = "steam.vent_cycles"
PLANET_ID = "nocturna"

MAX_DURATION_ERROR_HOURS = 1.0
MAX_SAME_PHASE_GAP_HOURS = 12.0
# The journal's site list is re-read this often; held ThermalVent objects read live in between.
SITES_REFRESH_TICKS = 600
# Without a flip or a new value the entry is persisted every this many polls, so "seen" survives a restart.
PERSIST_EVERY_POLLS = 10

STEAM_PLAN_KEY = "steam.plan"
TURBINE_STEAM_T_PER_H = 90.0  # docs/components/steam_turbine.md: 90 t/h at throttle 1.0
CAP_BUFFER_T = 1000.0  # docs/components/thermal_cap.md
TURBINE_BUFFER_T = 100.0  # docs/components/steam_turbine.md
GAS_TANK_CAPACITY_T = 5000.0  # fallback without a live tank; live tanks' capacity() wins
# Unknown vent values, from the game's vent generator ranges (active 6480-7920 min, dormant 2160-3600 min,
# 800-1200 t/h): the rate is the middle, the cycle a rounded, slightly conservative middle (shorter active,
# longer dormant).
DEFAULT_ACTIVE_MINUTES = 7000.0
DEFAULT_DORMANT_MINUTES = 3000.0
DEFAULT_STEAM_RATE = 1000.0

log = TreeConsole(module="vent_cycles")

_STATE = {"vents": None, "sites_tick": None, "entries": None, "polls": 0}


def _read_entries():
    raw = archive.get(VENT_CYCLES_KEY, {})
    return raw if isinstance(raw, dict) else {}


def cycle_minutes(vent_id):
    """(active, dormant) minutes for vent_id from the archive; either is None until known."""
    entry = _read_entries().get(vent_id)
    if not isinstance(entry, dict):
        return (None, None)
    return (entry.get("active"), entry.get("dormant"))


def _surveyed_vents():
    """{vent_id: ThermalVent} from journal.surveyed_sites(); None when the journal can't be read."""
    journal = get_component("journal")
    if not journal or not hasattr(journal, "surveyed_sites"):
        return None
    try:
        sites = journal.surveyed_sites(PLANET_ID) or []
    except Exception as error:
        swallowed("vent_cycles._surveyed_vents: journal.surveyed_sites", error)
        return None
    return {site.id: site for site in sites if site.kind() == "thermal" and getattr(site, "id", None)}


def _game_hours():
    clock = get_component("clock")
    try:
        return float(clock.elapsed_game_hours()) if clock and hasattr(clock, "elapsed_game_hours") else None
    except Exception as error:
        swallowed("vent_cycles._game_hours: clock.elapsed_game_hours", error)
        return None


def observe(entry, phase, hours):
    """
    Folds one phase reading at `hours` into `entry` (mutated) and returns a note
    when a flip was seen or a phase length was recorded, else None.
    """
    seen = entry.get("seen")
    previous = entry.get("phase")
    entry["seen"] = hours
    entry["phase"] = phase
    if previous is None or seen is None:
        entry["since"] = None
        entry["since_err"] = 0.0
        return None
    gap = max(0.0, hours - float(seen))
    if previous == phase:
        if gap > MAX_SAME_PHASE_GAP_HOURS:
            entry["since"] = None
        return None
    flip = float(seen) + gap / 2.0
    flip_err = gap / 2.0
    note = f"{previous} -> {phase} at {flip:.1f} h (+-{flip_err:.2f} h)"
    since = entry.get("since")
    if since is not None and not entry.get("deep"):
        err = float(entry.get("since_err") or 0.0) + flip_err
        length = (flip - float(since)) * 60.0
        if err <= MAX_DURATION_ERROR_HOURS:
            entry[previous] = round(length, 1)
            note += f"; {previous} lasted {length:.0f} min (+-{err * 60.0:.0f})"
        else:
            note += f"; {previous} length {length:.0f} min dropped (+-{err * 60.0:.0f} min too wide)"
    entry["since"] = flip
    entry["since_err"] = flip_err
    return note


def _read_vent(vent):
    """(phase, rate, deep active, deep dormant, capped) of a held ThermalVent; phase None when unreadable."""
    try:
        phase = vent.current_phase()
        rate = vent.base_steam_rate()
        active = vent.cycle_active_minutes()
        dormant = vent.cycle_dormant_minutes()
        capped = bool(vent.has_cap())
    except Exception as error:
        swallowed("vent_cycles._read_vent: ThermalVent reads", error)
        return (None, None, None, None, False)
    return (phase, rate, active, dormant, capped)


def plan_steam(entries, turbines, tanks, tank_capacity=GAS_TANK_CAPACITY_T):
    """
    Steam plan over the capped vents in `entries` (STEAM_PLAN_KEY shape):
    turbines/tanks built, turbines_left (more the vents carry nonstop), short
    (tanks missing for the turbines built, capped at what the vents carry),
    tanks_left (more tanks the full turbine count needs), caps, estimated.
    """
    vents = []
    estimated = False
    for entry in entries.values():
        if not entry.get("capped"):
            continue
        rate, active, dormant = entry.get("rate"), entry.get("active"), entry.get("dormant")
        if rate is None or active is None or dormant is None:
            estimated = True
        rate = DEFAULT_STEAM_RATE if rate is None else float(rate)
        active = DEFAULT_ACTIVE_MINUTES if active is None else float(active)
        dormant = DEFAULT_DORMANT_MINUTES if dormant is None else float(dormant)
        vents.append((rate * active / max(1.0, active + dormant), dormant / 60.0))
    supply = sum(average for average, _ in vents)
    potential = int(supply // TURBINE_STEAM_T_PER_H)
    capacity = tank_capacity if tank_capacity > 0 else GAS_TANK_CAPACITY_T

    def tanks_for(count):
        if count <= 0 or supply <= 0:
            return 0
        load = count * TURBINE_STEAM_T_PER_H
        steam = sum(load * average / supply * dormant_h for average, dormant_h in vents)
        steam -= len(vents) * CAP_BUFFER_T + count * TURBINE_BUFFER_T
        return max(0, -int(-steam // capacity))

    return {
        "turbines": turbines,
        "turbines_left": max(0, potential - turbines),
        "tanks": tanks,
        "short": max(0, tanks_for(min(turbines, potential)) - tanks),
        "tanks_left": max(0, tanks_for(potential) - tanks),
        "caps": len(vents),
        "estimated": estimated,
    }


def _steam_counts(now):
    """(turbines, steam tanks, mean tank capacity) network-wide; None when the walk fails."""
    import fluid_routing
    from power import steam_tanks
    try:
        turbines = len(fluid_routing.network_buildings("steam_turbine", now))
        tanks = steam_tanks()
        capacities = [float(tank.capacity()) for tank in tanks]
    except Exception as error:
        swallowed("vent_cycles._steam_counts: network walk", error)
        return None
    capacity = sum(capacities) / len(capacities) if capacities else GAS_TANK_CAPACITY_T
    return (turbines, len(tanks), capacity)


def plan_lines(plan):
    """(turbine line, tank line, short) for the STATUS card; `~` marks estimated numbers."""
    if not isinstance(plan, dict):
        return ("-", "-", False)
    if not plan.get("caps"):
        return (f"{plan.get('turbines', 0)} (no caps)", f"{plan.get('tanks', 0)}", False)
    mark = "~" if plan.get("estimated") else ""
    short = plan.get("short", 0)
    tank_line = f"{plan.get('tanks', 0)}"
    if short:
        tank_line += f" [{mark}{short} short!]"
    tank_line += f" (+{mark}{plan.get('tanks_left', 0)})"
    return (f"{plan.get('turbines', 0)} (+{mark}{plan.get('turbines_left', 0)})", tank_line, bool(short))


def step(now):
    """One poll of every surveyed vent; persists the log when it changed (or every PERSIST_EVERY_POLLS),
    then the steam plan when it changed."""
    hours = _game_hours()
    if hours is None:
        return
    if _STATE["vents"] is None or _STATE["sites_tick"] is None or now - _STATE["sites_tick"] >= SITES_REFRESH_TICKS:
        vents = _surveyed_vents()
        if vents is not None:
            _STATE["vents"] = vents
            _STATE["sites_tick"] = now
    vents = _STATE["vents"] or {}
    if _STATE["entries"] is None:
        _STATE["entries"] = _read_entries()
    entries = _STATE["entries"]
    changed = False
    notes = []
    for vent_id, vent in vents.items():
        phase, rate, active, dormant, capped = _read_vent(vent)
        if phase not in ("active", "dormant"):
            continue
        entry = entries.setdefault(vent_id, {"active": None, "dormant": None, "rate": None, "deep": False})
        if entry.get("capped") != capped:
            entry["capped"] = capped
            changed = True
        if rate is not None and entry.get("rate") != rate:
            entry["rate"] = rate
            changed = True
        if active is not None and dormant is not None and (entry.get("active"), entry.get("dormant"), entry.get("deep")) != (active, dormant, True):
            entry["active"], entry["dormant"], entry["deep"] = active, dormant, True
            changed = True
        note = observe(entry, phase, hours)
        if note:
            notes.append(f"{vent_id}: {note}")
            changed = True
    if vents:
        for gone in [vent_id for vent_id in entries if vent_id not in vents]:
            del entries[gone]
            changed = True
    _STATE["polls"] += 1
    if changed or _STATE["polls"] >= PERSIST_EVERY_POLLS:
        _STATE["polls"] = 0
        archive.set(VENT_CYCLES_KEY, entries)
    for note in notes:
        log.print(f"[VENT] {note}")
    counts = _steam_counts(now)
    if counts is not None:
        plan = plan_steam(entries, counts[0], counts[1], counts[2])
        if plan != archive.get(STEAM_PLAN_KEY, None):
            archive.set(STEAM_PLAN_KEY, plan)
