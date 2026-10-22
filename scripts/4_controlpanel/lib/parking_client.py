"""
Script parking, client side: the archive keys, the park request a machine script
files (ParkRequester) and the wakes any script may call (wake_for_visit(),
wake_kind(), wake_on_rise()), plus parked_ids() / parked_nearest() for stations
and stray_alerts() for the Status panel.
The engine that parks and wakes (ScriptParking) is lib/script_parking.py; it
imports this module, never the other way, so a machine script that only files
park requests or wakes a parked machine does not load the engine.
"""

from archive import archive
from game_clock import now_tick
from geometry import distance
from swallow import swallowed
from tree_console import TreeConsole

# Same module name as the engine: one log level setting covers both halves.
log = TreeConsole(module="script_parking")

# {machine_id: {"kind": str, "tick": n}}: written by the machine scripts (ParkRequester).
PARK_REQUESTS_KEY = "script.park_requests"
# {machine_id: {"kind": str, "mode": "breaker" | "stopped", "since": n}}: owned by ScriptParking.
PARKED_KEY = "script.parked"
# {machine_id: until_tick}: written by wake_for_visit(); a held machine is not parked.
HOLDS_KEY = "script.park_holds"
# {machine_id: {"kind": type_id, "first": tick, "stage": 1 | 2, "breaker": bool}}: stray dark machines,
# owned by ScriptParking (lib/script_parking.py module docstring); read by stray_alerts().
STRAY_KEY = "script.stray_dark"

# Consecutive idle steps before a machine asks to be parked.
PARK_AFTER_IDLE_STEPS = 3
# How long a visit wake holds a station awake (ticks). Covers the trip there;
# once a vehicle is docked the station's own script reports busy. Callers
# waiting at a station call wake_for_visit() again, which renews it.
STATION_HOLD_TICKS = 3000
# Oil Generators are woken (and not parked) while the network-wide oil tank fill is at or
# above this; oil_generator.OIL_SURPLUS_START_FRACTION is this value, so their script starts
# the surplus base load right then. Not on a grid a producing Reactor carries
# (power.reactor_carried()): their script burns no surplus there.
OIL_SURPLUS_WAKE_FRACTION = 0.90
# Oil Generators on a grid whose lower of battery / combined reserve fraction falls
# below this are woken at once (their script starts burning at
# oil_generator.OIL_START_RESERVE_FRACTION = 0.30, so this leaves time to react).
OIL_WAKE_RESERVE_FRACTION = 0.40
# run_control outcomes that leave the script in the asked state (start/resume: running, pause: paused).
RUN_OK = ("ok", "already_running", "already_paused")


def parked_ids(kind=None, mode="breaker"):
    """Ids of machines parked in `mode` (of `kind`, if given), from PARKED_KEY."""
    try:
        parked = archive.get(PARKED_KEY, {}) or {}
    except Exception as error:
        swallowed("parking_client.parked_ids: archive.get", error)
        return set()
    if not isinstance(parked, dict):
        return set()
    return {m for m, e in parked.items() if isinstance(e, dict) and e.get("mode") == mode and (kind is None or e.get("kind") == kind)}


def wake_for_visit(machine_id, reason="visit", hold_ticks=STATION_HOLD_TICKS, hold=True):
    """
    Called by a vehicle or drone heading to (or waiting at) a station, or by a
    station handing a rescue to a parked one: holds the station awake for
    hold_ticks and, when it is breaker-parked, switches it on and drops it
    from PARKED_KEY. Safe to call for any id (a machine that is not parked
    only gets the hold). hold=False skips the hold, for kinds outside HELD_KINDS
    (clearing the pre-park request on wake is enough there). Returns True when it
    switched a parked machine on.
    """
    if not machine_id:
        return False
    now = now_tick()

    def add_hold(holds):
        holds = holds if isinstance(holds, dict) else {}
        holds = {m: t for m, t in holds.items() if isinstance(t, (int, float)) and t > now}
        holds[machine_id] = now + hold_ticks
        return holds

    if hold:
        try:
            archive.transaction(HOLDS_KEY, {}, add_hold)
        except Exception as error:
            swallowed("parking_client.wake_for_visit: archive.transaction(HOLDS_KEY)", error)
    if machine_id not in parked_ids():
        return False
    power_control = get_component("power_control")
    try:
        result = power_control.set_powered(machine_id, True) if power_control else None
    except Exception as error:
        swallowed("parking_client.wake_for_visit: power_control.set_powered", error)
        return False
    if getattr(result, "status", "") != "ok":
        log.debug(f"wake_for_visit({machine_id}): set_powered -> {getattr(result, 'status', None)}")
        return False

    _unpark({machine_id: now}, "wake_for_visit")
    log.print(f"[PARKING] Woke {machine_id} ({reason}).")
    return True


def _unpark(woken, where):
    """
    Drops the woken machines ({machine_id: tick}) from PARKED_KEY and their pre-park
    requests filed up to that tick, which must not park them again.
    """

    def unpark(parked):
        parked = parked if isinstance(parked, dict) else {}
        for machine_id in woken:
            parked.pop(machine_id, None)
        return parked

    try:
        archive.transaction(PARKED_KEY, {}, unpark)
    except Exception as error:
        swallowed(f"parking_client.{where}: archive.transaction(PARKED_KEY)", error)
    _clear_requests(woken)


def parked_nearest(ref, station_refs, parked, awake_distance):
    """Id of the parked station strictly nearer to `ref` (a fleet VehicleRef/DroneRef) than
    awake_distance, the nearest one if several; None when the nearest station is awake."""
    best, best_id = awake_distance, None
    for station in station_refs:
        if station["id"] not in parked:
            continue
        dist = distance((ref.x, ref.y), station["coords"])
        if best is None or dist < best:
            best, best_id = dist, station["id"]
    return best_id


def _parked_entries(where):
    """The PARKED_KEY entries that are dicts ({machine_id: entry}); {} when unreadable."""
    try:
        parked = archive.get(PARKED_KEY, {}) or {}
    except Exception as error:
        swallowed(f"parking_client.{where}: archive.get", error)
        return {}
    return {m: e for m, e in (parked.items() if isinstance(parked, dict) else ()) if isinstance(e, dict)}


def _wake_entries(entries, reason, label, where):
    """
    Resumes the "paused" entries ({machine_id: entry}) with run_control, switches the "breaker" ones
    on, drops the woken from PARKED_KEY and prints one line. Returns the ids woken.
    """
    since = {m: e.get("since", 0) for m, e in entries.items()}
    ids = sorted(since)
    if not ids:
        return []
    power_control = get_component("power_control")
    run_control = get_component("run_control")
    woken = []
    for machine_id in ids:
        paused = entries[machine_id]["mode"] == "paused"
        try:
            if paused:
                result = run_control.resume(machine_id) if run_control else None
            else:
                result = power_control.set_powered(machine_id, True) if power_control else None
        except Exception as error:
            swallowed(f"parking_client.{where}: resume / set_powered", error)
            continue
        if getattr(result, "status", "") in RUN_OK:
            woken.append(machine_id)

    if woken:
        _unpark({m: since[m] for m in woken}, where)
        log.print(f"[PARKING] Woke {len(woken)} {label}(s) ({reason}).")
    return woken


def wake_kind(kind, reason, within=None):
    """
    Switches on (or resumes, a paused vehicle) every machine of `kind` parked here and drops them from PARKED_KEY,
    for a change that may give all of them work (e.g. a new field layout wakes every
    parked field provider). `within` (any iterable of ids; None = all) restricts it to those ids.
    Callable from any script. Returns the ids woken.
    """
    allowed = None if within is None else set(within)
    entries = {m: e for m, e in _parked_entries("wake_kind").items() if e.get("mode") in ("breaker", "paused") and e.get("kind") == kind and (allowed is None or m in allowed)}
    return _wake_entries(entries, reason, kind, "wake_kind")


def wake_role(role, reason):
    """Resumes every paused vehicle of `role` (e.g. "hauler") and drops it from PARKED_KEY. Returns the ids woken."""
    entries = {m: e for m, e in _parked_entries("wake_role").items() if e.get("mode") == "paused" and e.get("role") == role}
    return _wake_entries(entries, reason, role, "wake_role")


def resume_vehicle(machine_id, reason):
    """Resumes `machine_id` if it is parked paused here and drops it from PARKED_KEY. True when resumed."""
    entry = _parked_entries("resume_vehicle").get(machine_id)
    if not entry or entry.get("mode") != "paused":
        return False
    return bool(_wake_entries({machine_id: entry}, reason, machine_id, "resume_vehicle"))


def wake_on_rise(kinds, before, after, label):
    """
    For a demand writer (Phase 1 of docs/plans/event_driven_automation.md): when any
    amount in `after` ({key: amount}) exceeds its amount in `before`, wakes every parked
    machine of each kind in `kinds` (wake_kind()). Unchanged or falling demand wakes
    nothing, so a writer that rewrites the same value every pass costs one dict walk.
    Returns the first risen key, or None.
    """
    risen = next((k for k, amount in after.items() if isinstance(amount, (int, float)) and amount > (before.get(k) or 0)), None)
    if risen is None:
        return None
    for kind in kinds:
        wake_kind(kind, f"demand changed: {label} {risen}")
    return risen


def stray_alerts(entries=None):
    """[(text, "warn")] for the Status panel: one line over every stray dark machine at stage 2."""
    if entries is None:
        try:
            entries = archive.get(STRAY_KEY, {}) or {}
        except Exception as error:
            swallowed("parking_client.stray_alerts: archive.get", error)
            return []
    if not isinstance(entries, dict):
        return []
    ids = sorted(m for m, e in entries.items() if isinstance(e, dict) and e.get("stage", 1) >= 2)
    if not ids:
        return []
    shown = ", ".join(ids[:3]) + (f" +{len(ids) - 3}" if len(ids) > 3 else "")
    return [(f"Switched off, no owner: {shown}", "warn")]


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
        swallowed("parking_client._clear_requests: archive.transaction", error)


class ParkRequester:
    """
    Machine-side half: call `update(idle)` once per step. After PARK_AFTER_IDLE_STEPS
    idle steps in a row it files a park request for this machine (refreshed on each
    further idle step); the first busy step withdraws it. A script resumed after
    parking keeps its counter, so it asks again on its next idle step.
    """

    def __init__(self, machine_id, kind, role=None):
        self.machine_id = machine_id
        self.kind = kind
        self.role = role  # a vehicle's job role, for the work wakes (ScriptParking._work_wakes())
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
            self._write(now_tick(), wake_after)

    def _write(self, tick, wake_after=None):
        machine_id, kind, role = self.machine_id, self.kind, self.role

        def updater(requests):
            requests = requests if isinstance(requests, dict) else {}
            if tick is None:
                requests.pop(machine_id, None)
            else:
                requests[machine_id] = {"kind": kind, "tick": tick}
                if role:
                    requests[machine_id]["role"] = role
                if wake_after is not None:
                    requests[machine_id]["wake_after"] = int(wake_after)
            return requests

        try:
            archive.transaction(PARK_REQUESTS_KEY, {}, updater)
        except Exception as error:
            swallowed("parking_client.ParkRequester._write: archive.transaction", error)
