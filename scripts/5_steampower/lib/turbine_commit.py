# Turbine commitment: how many Steam Turbines a grid runs, and which.
#
# Called once per pass per grid from PowerGridManager.supervise_grid() (lib/power.py),
# before the emergency guard. Instead of every turbine easing its own throttle, the grid
# runs just enough turbines at full output to cover consumption, plus a spare margin,
# and switches the rest off at the breaker (lib/script_parking.py's PARKED_KEY, mode
# "turbine"). A parked turbine burns no steam and its script stops counting against the
# per-tick step budget.
#
# Steam is per turbine, not per grid: a split steam network can leave one turbine with a
# full source and another dry. So capacity counts only turbines that can deliver
# (healthy own buffer, not stalled), and the running set is the best-supplied turbines:
# own buffer first, then the fill of the source their steam_in is connected to. A running
# turbine that runs dry is swapped for the best parked one.
#
# Needed turbines = ceil((consumption - other generation + battery top-up) / 108 W), plus
# TURBINE_SPARE_FRACTION of the managed turbines (at least one). Turbines switched off by
# anything else than this module are left alone.
#
# Two latches (lib/hysteresis.py), like the Oil Generator's:
#   - All on: below TURBINE_EMERGENCY_BATTERY_FRACTION battery every managed turbine runs
#     (ahead of the Oil Generators' last-resort line), until the battery is back at
#     TURBINE_EMERGENCY_RELEASE_FRACTION.
#   - Steam surplus base load: from TURBINE_SURPLUS_START_FRACTION of the grid's steam pool
#     (power.measure_grid()) until it drops below TURBINE_SURPLUS_STOP_FRACTION, the
#     turbines cover the whole consumption (other generation is not subtracted), so Caps
#     don't vent steam through their relief valves while solar or oil carry the grid. It
#     starts above the Steam Condenser's steam gate (condenses from 0.95), so the Condenser
#     takes the surplus first.
# The latch state lives in the grid manager's memory; a control room restart starts both off.

from archive import archive
from script_parking import PARKED_KEY, set_powered
from hysteresis import HysteresisLatch
from tree_console import TreeConsole
from swallow import swallowed

TURBINE_TYPE_ID = "steam_turbine"
PARK_MODE = "turbine"
# {grid anchor id: tick of the last step()}: turbines on a grid with a fresh entry leave
# surplus to this module and run at full throttle whenever their buffer is healthy
# (lib/steam_turbine.py reads it under the same key; that module is tier 4, so the name
# is repeated there instead of imported).
COMMIT_HEARTBEAT_KEY = "power.turbine_commit"
TURBINE_FULL_W = 108.0  # docs/components/steam_turbine.md: 108 W from 90 t/h at throttle 1.0

# Spare turbines kept running beyond the computed need, as a fraction of the managed
# turbines (scales with base size), at least TURBINE_MIN_SPARE.
TURBINE_SPARE_FRACTION = 0.10
TURBINE_MIN_SPARE = 1
# Battery fraction below which every managed turbine runs, and the one that releases it.
TURBINE_EMERGENCY_BATTERY_FRACTION = 0.50
TURBINE_EMERGENCY_RELEASE_FRACTION = 0.70
# Steam pool fraction that starts the surplus base load, and the one that stops it.
TURBINE_SURPLUS_START_FRACTION = 0.98
TURBINE_SURPLUS_STOP_FRACTION = 0.90
# Battery below this adds a top-up to the need: the missing Wh over TOPUP_HOURS game hours.
TURBINE_TOPUP_BELOW_FRACTION = 0.98
TOPUP_HOURS = 2.0
# A turbine counts as able to deliver with at least this much of its own steam buffer and
# not stalled (steam_turbine.STEAM_BUFFER_LOW_FRACTION).
TURBINE_CAPABLE_BUFFER_FRACTION = 0.15
# A woken turbine is not parked again for this many ticks, so a need hovering at a
# boundary doesn't toggle breakers every pass.
TURBINE_MIN_ON_TICKS = 600

log = TreeConsole(module="turbine_commit")


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed("turbine_commit._now_tick: clock.tick", error)
        return 0


def _ceil(x):
    """Smallest int >= x (the game interpreter has no math module)."""
    return int(-(-x // 1))


def turbine_needed(consumed_w, other_w, bat_wh, bat_cap, managed, all_on=None, surplus=False):
    """
    (needed, spare, reason) turbines for one grid. `other_w` = generation not from turbines.
    all_on: the all-on latch (None: battery below TURBINE_EMERGENCY_BATTERY_FRACTION, no
    hysteresis). surplus: the steam surplus latch; other generation is then not subtracted.
    Pure; see the module comment for the rule.
    """
    spare = max(TURBINE_MIN_SPARE, _ceil(managed * TURBINE_SPARE_FRACTION)) if managed else 0
    bat_frac = bat_wh / bat_cap if bat_cap > 0 else 1.0
    if all_on is None:
        all_on = bat_cap > 0 and bat_frac < TURBINE_EMERGENCY_BATTERY_FRACTION
    if all_on:
        return managed, spare, (f"battery {bat_frac * 100:.0f}% (all on below {TURBINE_EMERGENCY_BATTERY_FRACTION * 100:.0f}% "
                                f"until {TURBINE_EMERGENCY_RELEASE_FRACTION * 100:.0f}%): all turbines")
    if surplus:
        other_w = 0.0
    need_w = max(0.0, consumed_w - other_w)
    topup_w = 0.0
    if bat_cap > 0 and bat_frac < TURBINE_TOPUP_BELOW_FRACTION:
        topup_w = (bat_cap - bat_wh) / TOPUP_HOURS
    needed = _ceil((need_w + topup_w) / TURBINE_FULL_W)
    return min(managed, needed + spare), spare, (
        f"con {consumed_w:.0f} W - other {other_w:.0f} W + top-up {topup_w:.0f} W -> {needed} + {spare} spare"
        + (" (steam surplus: other generation not subtracted)" if surplus else ""))


def rank_turbines(infos, running_bonus=True):
    """
    Turbine ids best-supplied first: able to deliver, own buffer fill, source fill, then
    (to avoid swapping equals) already running. `infos`: {id: {"capable", "buffer",
    "source_fill", "powered"}}.
    """
    return sorted(infos, key=lambda t: (not infos[t]["capable"], -round(infos[t]["buffer"], 2),
                                        -round(infos[t]["source_fill"], 2),
                                        not (running_bonus and infos[t]["powered"]), t))


class TurbineCommitment:
    """One per grid (owned by PowerGridManager)."""

    def __init__(self, power=None):
        self.power = power or get_component("power_control")
        self.woken_at = {}  # {turbine_id: tick} woken here, for TURBINE_MIN_ON_TICKS
        self.turbine_ids = []  # this grid's turbines at the last step(), for release_all()
        self.all_on = HysteresisLatch(TURBINE_EMERGENCY_BATTERY_FRACTION, TURBINE_EMERGENCY_RELEASE_FRACTION, on_above=False)
        self.surplus = HysteresisLatch(TURBINE_SURPLUS_START_FRACTION, TURBINE_SURPLUS_STOP_FRACTION)

    # ------------------------------------------------------------------ reads

    @staticmethod
    def _source_fill(port):
        """Fill (0-1) of the steam source a turbine's steam_in is connected to: a Gas Tank's
        fill_pct, a Thermal Cap's pressure; 0.5 when unknown."""
        try:
            source_id = port.connected_id() if port and hasattr(port, "connected_id") else None
        except Exception as error:
            swallowed("turbine_commit._source_fill: port.connected_id", error)
            return 0.5
        source = get_component(source_id) if source_id else None
        if source is None:
            return 0.5
        try:
            if hasattr(source, "fill_pct"):
                pct = source.fill_pct()
                return pct / 100.0 if pct > 1.0 else pct
            if hasattr(source, "pressure"):
                return max(0.0, min(1.0, source.pressure()))
        except Exception as error:
            swallowed("turbine_commit._source_fill: source.fill_pct", error)
        return 0.5

    def _info(self, turbine_id):
        """{"capable", "buffer", "source_fill", "powered", "output"} for one turbine, or None."""
        turbine = get_component(turbine_id)
        if turbine is None or self.power is None:
            return None
        try:
            powered = bool(self.power.is_powered(turbine_id))
        except Exception as error:
            swallowed("turbine_commit._info: power.is_powered", error)
            return None
        port = getattr(turbine, "steam_in", None)
        buffer = 0.0
        try:
            capacity = port.capacity() if port else 0
            buffer = port.level() / capacity if capacity else 0.0
        except Exception as error:
            swallowed("turbine_commit._info: port.level", error)
        stalled = False
        output = 0.0
        if powered:
            try:
                stalled = bool(turbine.is_stalled())
                # power_output() reports the previous power tick (0 right after a restart or
                # a new throttle); the throttle is current, so take the larger of the two.
                throttle = float(turbine.throttle() or 0.0) if hasattr(turbine, "throttle") else 0.0
                output = max(float(turbine.power_output() or 0.0), 0.0 if stalled else throttle * TURBINE_FULL_W)
            except Exception as error:
                swallowed("turbine_commit._info: turbine.is_stalled", error)
        return {"capable": buffer >= TURBINE_CAPABLE_BUFFER_FRACTION and not stalled, "buffer": buffer,
                "source_fill": self._source_fill(port), "powered": powered, "output": output}

    # ------------------------------------------------------------------ step

    def _update_latches(self, bat_wh, bat_cap, steam_fraction, grid_id_str):
        """Feeds the all-on (battery) and steam surplus latches; logs each flip."""
        bat_frac = bat_wh / bat_cap if bat_cap > 0 else None
        flip = self.all_on.update(bat_frac)
        if flip == "on" and bat_frac is not None:  # all_on forces off, never on, for None
            log.print(f"[TURBINES] '{grid_id_str}': battery {bat_frac * 100:.0f}% < {TURBINE_EMERGENCY_BATTERY_FRACTION * 100:.0f}% -- all turbines on until {TURBINE_EMERGENCY_RELEASE_FRACTION * 100:.0f}%.")
        elif flip == "off":
            shown = f"{bat_frac * 100:.0f}%" if bat_frac is not None else "n/a"
            log.print(f"[TURBINES] '{grid_id_str}': battery {shown} -- all-on released, back to commitment.")
        flip = self.surplus.update(steam_fraction)
        if flip == "on":
            log.print(f"[TURBINES] '{grid_id_str}': steam pool {steam_fraction * 100:.0f}% >= {TURBINE_SURPLUS_START_FRACTION * 100:.0f}% -- steam surplus base load ON.")
        elif flip == "off":
            shown = f"{steam_fraction * 100:.0f}%" if steam_fraction is not None else "n/a"
            log.print(f"[TURBINES] '{grid_id_str}': steam pool {shown} (stop below {TURBINE_SURPLUS_STOP_FRACTION * 100:.0f}%) -- steam surplus base load OFF.")

    def step(self, grid, grid_id_str, steam_fraction=None):
        """One pass for `grid` (a power_control grid snapshot). steam_fraction: the grid's steam
        pool fill (power.measure_grid()), None without a steam tank. Returns a short status string."""
        turbine_ids = sorted(m.id for m in (getattr(grid, "members", None) or []) if getattr(m, "type_id", "") == TURBINE_TYPE_ID)
        self.turbine_ids = turbine_ids
        if not turbine_ids:
            return "no turbines"
        now = _now_tick()
        parked = archive.get(PARKED_KEY, {}) or {}
        parked = parked if isinstance(parked, dict) else {}
        ours = {t for t in turbine_ids if (parked.get(t) or {}).get("mode") == PARK_MODE}
        infos = {}
        for t in turbine_ids:
            info = self._info(t)
            if info is None:
                continue
            if info["powered"] or t in ours:  # off for another reason: not ours to run
                infos[t] = info
        if not infos:
            return "no managed turbines"

        self._heartbeat(grid_id_str, now)
        turbine_w = sum(i["output"] for i in infos.values() if i["powered"])
        other_w = max(0.0, (getattr(grid, "generated", 0.0) or 0.0) - turbine_w)
        bat_wh = (getattr(grid, "stored", 0.0) or 0.0) + (getattr(grid, "reserve_stored", 0.0) or 0.0)
        bat_cap = (getattr(grid, "capacity", 0.0) or 0.0) + (getattr(grid, "reserve_capacity", 0.0) or 0.0)
        self._update_latches(bat_wh, bat_cap, steam_fraction, grid_id_str)
        target, spare, reason = turbine_needed(getattr(grid, "consumed", 0.0) or 0.0, other_w, bat_wh, bat_cap, len(infos),
                                               all_on=self.all_on.active, surplus=self.surplus.active)

        ranked = rank_turbines(infos)
        capable = [t for t in ranked if infos[t]["capable"]]
        if len(capable) < target:
            run = set(ranked)  # not enough turbines can deliver: keep every one up
            reason += f"; only {len(capable)} can deliver, all up"
        else:
            run = set(ranked[:target])

        log.start(f"[TURBINES] '{grid_id_str}'", level="debug")
        log.debug(f"{len(infos)} managed, target {target} ({reason}); ranked {ranked}.")
        woke, parked_now = [], []
        for t in ranked:
            info = infos[t]
            if t in run and not info["powered"]:
                if self._set_powered(t, True):
                    woke.append(t)
                    self.woken_at[t] = now
            elif t not in run and info["powered"]:
                if now - self.woken_at.get(t, -TURBINE_MIN_ON_TICKS) < TURBINE_MIN_ON_TICKS and info["capable"]:
                    log.debug(f"{t} woken {now - self.woken_at[t]} tick(s) ago; stays on until {TURBINE_MIN_ON_TICKS}.")
                    continue
                if self._set_powered(t, False):
                    parked_now.append(t)
        # Parked here but switched on by the player (or anything else): no longer parked.
        cleared = [t for t in ours if infos.get(t, {}).get("powered") and t not in parked_now]
        if woke or parked_now or cleared:
            self._record(woke + cleared, parked_now, now, grid_id_str)
        if woke or parked_now:
            log.print(f"[TURBINES] '{grid_id_str}': {target} of {len(infos)} to run ({reason})"
                      + (f"; on: {', '.join(woke)}" if woke else "") + (f"; off: {', '.join(parked_now)}" if parked_now else "") + ".")
        log.end()
        running = sum(1 for t in infos if (infos[t]["powered"] and t not in parked_now) or t in woke)
        return f"{running}/{len(infos)} turbine(s) running"

    def release_all(self):
        """Switches this grid's turbines parked here back on (the grid vanished or merged)."""
        parked = archive.get(PARKED_KEY, {}) or {}
        ids = [t for t, e in (parked.items() if isinstance(parked, dict) else []) if isinstance(e, dict) and e.get("mode") == PARK_MODE
               and t in self.turbine_ids]
        woke = [t for t in ids if self._set_powered(t, True)]
        if woke:
            self._record(woke, [], _now_tick(), "released")

    # ------------------------------------------------------------------ writes

    def _set_powered(self, turbine_id, on):
        return set_powered(self.power, turbine_id, on, log)

    @staticmethod
    def _heartbeat(grid_id_str, now):
        """Marks this grid as committed (COMMIT_HEARTBEAT_KEY) so its turbines stop easing on their own."""
        def updater(beats):
            beats = beats if isinstance(beats, dict) else {}
            beats[grid_id_str] = now
            return beats

        try:
            archive.transaction(COMMIT_HEARTBEAT_KEY, {}, updater)
        except Exception as error:
            swallowed("turbine_commit._heartbeat: archive.transaction", error)

    @staticmethod
    def _record(woke, parked_now, now, grid_id_str):
        def updater(parked):
            parked = parked if isinstance(parked, dict) else {}
            for t in woke:
                parked.pop(t, None)
            for t in parked_now:
                parked[t] = {"kind": TURBINE_TYPE_ID, "mode": PARK_MODE, "since": now, "grid": grid_id_str}
            return parked

        try:
            archive.transaction(PARKED_KEY, {}, updater)
        except Exception as error:
            swallowed("turbine_commit._record: archive.transaction", error)
