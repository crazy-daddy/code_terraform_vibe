"""
Script parking: takes idle machines' scripts out of the running-script count.

Above 50 running scripts the game splits 50,000 interpreter steps per tick evenly
over every running or sleeping script (docs/cheatsheet/dev_workflow.md §1d-1), so
an idle machine whose script sleeps still shrinks every other script's budget.
Two ways out of the count:

- Breaker parking (machines with a breaker, `power_control.can_power_off()`):
  `set_powered(id, False)` pauses the machine's script and keeps its setpoints;
  `set_powered(id, True)` resumes it where it stopped. The machine script decides
  it is idle and files a request (`ParkRequester`); the headless automation panel
  (`ScriptParking.step()`) switches the breaker off, and on again when the
  machine's kind is due for a re-check or a wake trigger fires.
- Night stop (solar generators, which have no breaker): the panel stops their
  scripts with `run_control.stop()` once the sun is down and starts them again
  at sunrise. A stopped panel drops its tilt, which does not matter at 0 W.

Parked machines are tracked in one archive dict (PARKED_KEY) so a panel restart
keeps waking them. Load shedding (lib/power.py) uses the same breakers with its
own `power.shedded` list; a shed id is never parked, and only ids in
PARKED_KEY are ever switched back on here.
"""

from archive import archive
from tree_console import TreeConsole
from swallow import swallowed
import power

log = TreeConsole(module="script_parking")

# {machine_id: {"kind": str, "tick": n}}: written by the machine scripts (ParkRequester).
PARK_REQUESTS_KEY = "script.park_requests"
# {machine_id: {"kind": str, "mode": "breaker" | "stopped", "since": n}}: owned by ScriptParking.
PARKED_KEY = "script.parked"

# Consecutive idle steps before a machine asks to be parked.
PARK_AFTER_IDLE_STEPS = 3
# A request older than this is ignored (the machine may have found work since).
REQUEST_FRESH_TICKS = 150

# Breaker-parked kinds and how long each stays parked before its script is woken for
# a re-check (ticks, 10 per second). The script parks again on its own if still idle.
WAKE_AFTER_TICKS = {
    "smelter": 300,
    "fabricator": 300,
    "supply_dock": 600,
    "oil_generator": 600,
    "thermal_cap": 600,
}
# Upper bound on a wake time a machine files itself (ParkRequester.update(wake_after=...)).
MAX_WAKE_AFTER_TICKS = 6000

# Oil Generators on a grid whose lower of battery / combined reserve fraction falls
# below this are woken at once (their script starts burning at
# oil_generator.OIL_START_RESERVE_FRACTION = 0.15, so this leaves time to react).
OIL_WAKE_RESERVE_FRACTION = 0.25

SOLAR_TYPE_ID = "solar_generator"


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed("script_parking._now_tick: clock.tick", error)
        return 0


class ParkRequester:
    """
    Machine-side half: call `update(idle)` once per step. After PARK_AFTER_IDLE_STEPS
    idle steps in a row it files a park request for this machine (refreshed on each
    further idle step); the first busy step withdraws it. A script resumed after
    parking keeps its counter, so it asks again on its next idle step.
    """

    def __init__(self, machine_id, kind):
        self.machine_id = machine_id
        self.kind = kind
        self.idle_steps = 0
        self.requested = False

    def update(self, idle, wake_after=None):
        """`wake_after`: ticks this machine may stay parked (default: WAKE_AFTER_TICKS for its kind)."""
        if not idle:
            self.idle_steps = 0
            if self.requested:
                self.requested = False
                self._write(None)
            return
        self.idle_steps += 1
        if self.idle_steps >= PARK_AFTER_IDLE_STEPS:
            self.requested = True
            self._write(_now_tick(), wake_after)

    def _write(self, tick, wake_after=None):
        machine_id, kind = self.machine_id, self.kind

        def updater(requests):
            requests = requests if isinstance(requests, dict) else {}
            if tick is None:
                requests.pop(machine_id, None)
            else:
                requests[machine_id] = {"kind": kind, "tick": tick}
                if wake_after is not None:
                    requests[machine_id]["wake_after"] = int(wake_after)
            return requests

        try:
            archive.transaction(PARK_REQUESTS_KEY, {}, updater)
        except Exception as error:
            swallowed("script_parking.ParkRequester._write: archive.transaction", error)


class ScriptParking:
    """Panel-side half, one instance in the headless automation panel; call `step()` every few seconds."""

    def __init__(self, power=None, run_control=None, clock=None):
        self.power = power or get_component("power_control")
        self.run_control = run_control or get_component("run_control")
        self.clock = clock or get_component("clock")

    def step(self, grids, elevation, dock_plan=None):
        """
        One pass: wake due or triggered machines, park fresh requests, stop/start
        solar scripts by `elevation`. `grids` = power_control.grids() of this tick;
        `dock_plan` = supply_dock.order_plan ({dock_id: order_id or None}). Returns a
        short summary for the automation card.
        """
        now = _now_tick()
        parked = archive.get(PARKED_KEY, {}) or {}
        parked = dict(parked) if isinstance(parked, dict) else {}
        requests = archive.get(PARK_REQUESTS_KEY, {}) or {}
        requests = requests if isinstance(requests, dict) else {}
        shed = set(archive.get("power.shedded", []) or [])
        members = self._members(grids)
        changed = False
        woken = {}  # {machine_id: parked-since tick}: their requests from before parking are cleared below

        log.start("script parking", level="debug")
        low_grids = self._low_reserve_grids(grids, parked, requests, members)
        for machine_id, entry in list(parked.items()):
            if entry.get("mode") != "breaker":
                continue
            if get_component(machine_id) is None:
                log.debug(f"{machine_id} no longer exists, dropped from the parked list")
                del parked[machine_id]
                changed = True
                continue
            reason = self._wake_reason(machine_id, entry, now, members, low_grids, dock_plan)
            if reason and self._set_powered(machine_id, True):
                log.debug(f"woke {machine_id} ({reason})")
                woken[machine_id] = entry.get("since", now)
                del parked[machine_id]
                changed = True

        if woken:
            self._clear_requests(woken)
        for machine_id, request in requests.items():
            if machine_id in parked or machine_id in woken or machine_id in shed or not isinstance(request, dict):
                continue
            kind = request.get("kind")
            if kind not in WAKE_AFTER_TICKS or now - request.get("tick", 0) > REQUEST_FRESH_TICKS:
                continue
            if machine_id not in members or not self._can_power_off(machine_id):
                continue
            if kind == "supply_dock" and (dock_plan or {}).get(machine_id):
                continue
            if kind == "oil_generator" and members[machine_id][0] in low_grids:
                continue  # reserve already low: stay ready instead of parking and waking again
            if self._set_powered(machine_id, False):
                parked[machine_id] = {"kind": kind, "mode": "breaker", "since": now}
                if request.get("wake_after") is not None:
                    parked[machine_id]["wake_after"] = min(int(request["wake_after"]), MAX_WAKE_AFTER_TICKS)
                log.debug(f"parked {machine_id} ({kind})")
                changed = True

        changed = self._solar(elevation, members, parked, now) or changed
        if changed:
            archive.set(PARKED_KEY, parked)
        log.end()
        return self._summary(parked)

    # ------------------------------------------------------------------ wake

    def _wake_reason(self, machine_id, entry, now, members, low_grids, dock_plan):
        kind = entry.get("kind")
        if now - entry.get("since", now) >= entry.get("wake_after", WAKE_AFTER_TICKS.get(kind, 600)):
            return "re-check due"
        if kind == "supply_dock" and (dock_plan or {}).get(machine_id):
            return "order assigned"
        if kind == "oil_generator" and members.get(machine_id, (None,))[0] in low_grids:
            return "grid reserve low"
        return None

    def _low_reserve_grids(self, grids, parked, requests, members):
        """Anchor ids of grids with a parked or park-requesting Oil Generator whose reserve is below OIL_WAKE_RESERVE_FRACTION."""
        entries = list(parked.items()) + [(m, r) for m, r in requests.items() if isinstance(r, dict)]
        wanted = {members[m][0] for m, e in entries if e.get("kind") == "oil_generator" and m in members}
        if not wanted:
            return set()
        low = set()
        if not hasattr(power, "measure_grid"):
            return low
        for grid in grids:
            anchor = getattr(grid, "anchor_id", None)
            if anchor not in wanted:
                continue
            try:
                now = power.measure_grid(grid, power.grid_steam_tank_ids(grid))
                fractions = [f for f in (power.reserve_fraction(now), now["bat_wh"] / now["bat_cap"] if now["bat_cap"] > 0 else None) if f is not None]
            except Exception as error:
                swallowed("script_parking._low_reserve_grids: power.measure_grid", error)
                low.add(anchor)  # unreadable reserve: wake, the generator's own script fails safe
                continue
            if not fractions or min(fractions) < OIL_WAKE_RESERVE_FRACTION:
                low.add(anchor)
        return low

    @staticmethod
    def _clear_requests(woken):
        """Drops park requests filed before each woken machine was parked; a newer one (the
        script found itself idle again already) is kept for the next pass."""
        def updater(requests):
            requests = requests if isinstance(requests, dict) else {}
            for machine_id, since in woken.items():
                request = requests.get(machine_id)
                if not isinstance(request, dict) or request.get("tick", 0) <= since:
                    requests.pop(machine_id, None)
            return requests

        try:
            archive.transaction(PARK_REQUESTS_KEY, {}, updater)
        except Exception as error:
            swallowed("script_parking._clear_requests: archive.transaction", error)

    # ------------------------------------------------------------------ solar

    def _solar(self, elevation, members, parked, now):
        """Stops running solar scripts while the sun is down, starts the ones stopped here once it is up."""
        if self.run_control is None or elevation is None:
            return False
        changed = False
        if elevation <= 0:
            stopped = []
            for machine_id, (_anchor, type_id) in members.items():
                if type_id != SOLAR_TYPE_ID or machine_id in parked or not self._is_running(machine_id):
                    continue
                if self._run(machine_id, "stop"):
                    parked[machine_id] = {"kind": "solar", "mode": "stopped", "since": now}
                    stopped.append(machine_id)
            if stopped:
                log.print(f"[PARKING] Night: stopped {len(stopped)} solar script(s) until sunrise.")
                changed = True
            return changed
        started = []
        for machine_id, entry in list(parked.items()):
            if entry.get("mode") != "stopped":
                continue
            if machine_id not in members or self._run(machine_id, "start"):
                del parked[machine_id]
                started.append(machine_id)
                changed = True
        if started:
            log.print(f"[PARKING] Sunrise: started {len(started)} solar script(s).")
        return changed

    # ------------------------------------------------------------------ game calls

    @staticmethod
    def _members(grids):
        """{machine_id: (grid anchor id, type_id)} over every grid."""
        out = {}
        for grid in grids:
            anchor = getattr(grid, "anchor_id", None)
            for member in getattr(grid, "members", []) or []:
                member_id = getattr(member, "id", None)
                if member_id:
                    out[member_id] = (anchor, getattr(member, "type_id", ""))
        return out

    def _can_power_off(self, machine_id):
        try:
            return bool(self.power.can_power_off(machine_id))
        except Exception as error:
            swallowed("script_parking._can_power_off: power.can_power_off", error)
            return False

    def _set_powered(self, machine_id, on):
        try:
            result = self.power.set_powered(machine_id, on)
        except Exception as error:
            swallowed("script_parking._set_powered: power.set_powered", error)
            return False
        status = getattr(result, "status", "")
        if status != "ok":
            log.debug(f"set_powered({machine_id}, {on}) -> {status}")
        return status == "ok"

    def _is_running(self, machine_id):
        try:
            return bool(self.run_control.is_running(machine_id))
        except Exception as error:
            swallowed("script_parking._is_running: run_control.is_running", error)
            return False

    def _run(self, machine_id, action):
        try:
            result = getattr(self.run_control, action)(machine_id)
        except Exception as error:
            swallowed(f"script_parking._run: run_control.{action}", error)
            return False
        status = getattr(result, "status", "")
        if status not in ("ok", "already_running"):
            log.debug(f"run_control.{action}({machine_id}) -> {status}")
        return status in ("ok", "already_running")

    @staticmethod
    def _summary(parked):
        if not parked:
            return "nothing parked"
        counts = {}
        for entry in parked.values():
            kind = entry.get("kind", "?")
            counts[kind] = counts.get(kind, 0) + 1
        return "parked " + " / ".join(f"{n} {kind}" for kind, n in sorted(counts.items()))
