"""
Script parking: takes idle machines' scripts out of the running-script count.

Above 50 running scripts the game splits 50,000 interpreter steps per tick evenly
over every running or sleeping script (docs/cheatsheet/dev_workflow.md §1d-1), so
an idle machine whose script sleeps still shrinks every other script's budget.
Two ways out of the count:

- Breaker parking (machines with a breaker, `power_control.can_power_off()`):
  `set_powered(id, False)` pauses the machine's script and keeps its setpoints;
  `set_powered(id, True)` resumes it where it stopped. The machine script decides
  it is idle and files a request (`ParkRequester`); orchestrator_automation.py
  (`ScriptParking.step()`) switches the breaker off, and on again when the
  machine's kind is due for a re-check or a wake trigger fires.
- Night stop (solar generators; they have a breaker too, but at 0 W a stop costs
  nothing and a player-stopped script stays stopped): the panel stops their
  scripts with `run_control.stop()` once the sun is down and starts them again
  at sunrise. A stopped panel drops its tilt, which does not matter at 0 W.

Charging Stations, Drone Service Stations and Drone Depots park the same way, with two
safeguards: a vehicle or drone heading to one (or waiting at it) wakes it
itself (`wake_for_visit()`, which also holds it awake for STATION_HOLD_TICKS),
and the last awake station of each type never parks (depots have no such rule:
they do no fleet watching). Awake stations leave
parked ones out of their nearest-station responsibility (`parked_ids()`) and
wake a parked station that is nearest to a stranded vehicle, so it rescues.

Parked machines are tracked in one archive dict (PARKED_KEY) so a panel restart
keeps waking them. Load shedding (lib/power.py) uses the same breakers with its
own `power.shedded` list; a shed id is never parked. Other breaker owners
record their machines in PARKED_KEY under their own mode (turbine_commit,
biomass_mixer_gate) or in the retired registry (lib/retired_machines.py).

Stray dark machines: a grid member with a breaker that is switched off while
nothing above tracks it (not in PARKED_KEY, `power.shedded`, the retired
registry, PARK_REQUESTS_KEY or the operator's MANUAL_OFF_KEY), typically a
machine built before its grid had power. Three stages, by time since first seen
(STRAY_KEY): a warn line at once, notify() plus a Status panel alert
(stray_alerts()) after STRAY_NOTIFY_TICKS, and after STRAY_SWITCH_ON_TICKS the
breaker goes on and an idle script is started (an errored or completed one is
left alone).
"""

from archive import archive
from tree_console import TreeConsole
from components import oil_pump
from swallow import swallowed
import fluid_routing
from atomic import run_atomic
from retired_machines import retired_ids
from game_clock import now_tick
# lib/power.py is imported where it is used (_power_module()): power.py imports
# turbine_commit, which imports this module, so a module-level import would be a cycle.
power = None

log = TreeConsole(module="script_parking")

# {machine_id: {"kind": str, "tick": n}}: written by the machine scripts (ParkRequester).
PARK_REQUESTS_KEY = "script.park_requests"
# {machine_id: {"kind": str, "mode": "breaker" | "stopped", "since": n}}: owned by ScriptParking.
PARKED_KEY = "script.parked"
# {machine_id: until_tick}: written by wake_for_visit(); a held machine is not parked.
HOLDS_KEY = "script.park_holds"

# Consecutive idle steps before a machine asks to be parked.
PARK_AFTER_IDLE_STEPS = 3
# A request older than this is ignored (the machine may have found work since).
REQUEST_FRESH_TICKS = 150

# Breaker-parked kinds and how long each stays parked before its script is woken for
# a re-check (ticks, 10 per second). The script parks again on its own if still idle.
WAKE_AFTER_TICKS = {
    # Fabricators and Smelters are woken when their demand rises (wake_on_rise() at
    # each demand writer, the full pass's signature diff as the backstop), Supply Docks
    # when the dock planner assigns them an order; the timed re-check is a backstop.
    "smelter": 1200,
    "fabricator": 1200,
    "supply_dock": 1800,
    # Woken by a low grid reserve (OIL_WAKE_RESERVE_FRACTION) as soon as it matters, so the
    # timed re-check is only a backstop.
    "oil_generator": 6000,
    "thermal_cap": 600,
    "oil_pump": 3000,
    # Exotic Gas Cap / Spring Tap (lib/exotic_cap.py): woken as soon as its deposit turns
    # active, so the timed re-check is only a backstop.
    "exotic_cap": 6000,
    "crop_automator": 600,
    "charging_station": 3000,
    "drone_service_station": 3000,
    "drone_depot": 3000,
    "field_provider": 6000,
    # Below logistics_requests.REQUEST_STALE_TICKS (6000): the woken script republishes
    # its life-form requests before they expire.
    "seed_maker": 3000,
    "feed_maker": 3000,
    "refiner": 3000,
    "fuel_assembler": 3000,
    # Parked while empty and unassigned, without feed, or capped at the Mk I ceiling
    # (lib/habitat.py); the Wildlife planner wakes it when that changes or a node purchase is queued.
    "habitat": 6000,
}
# Timed re-checks that found nothing back off: a machine that files its next park request within
# FRUITLESS_REPARK_TICKS of a "re-check due" wake gets its next wake_after doubled (base
# WAKE_AFTER_TICKS << streak), up to the kind's cap here. A request filed later than that
# window (the machine did work in between) resets the streak. The request's own tick counts,
# not the park: passes can run further apart than the window. Kinds without an event wake pay
# at most the cap in extra latency for new work.
WAKE_BACKOFF_MAX_TICKS = {
    "crop_automator": 1800,
}
# A park request filed this soon after a re-check wake means the machine woke, found no work and
# idled again (it re-files on its first idle streak, PARK_AFTER_IDLE_STEPS).
FRUITLESS_REPARK_TICKS = 150
# Kinds woken when the demand they work from rises (ScriptParking._demand_wakes()). A Fabricator
# woken this way wakes the Smelters it lacks ingots from itself (fabricator.wake_local_smelters()).
DEMAND_WAKE_KINDS = ("fabricator", "smelter")
# Station kinds: never park the last awake one of a type (see the module docstring).
STATION_KINDS = ("charging_station", "drone_service_station")
# How long a visit wake holds a station awake (ticks). Covers the trip there;
# once a vehicle is docked the station's own script reports busy. Callers
# waiting at a station call wake_for_visit() again, which renews it.
STATION_HOLD_TICKS = 3000
# Kinds a wake_for_visit() hold keeps from parking: stations plus Drone Depots
# (every drone_navigation.fly_to_station() and depot_stage.request_stage() wakes its depot).
HELD_KINDS = STATION_KINDS + ("drone_depot",)
# Upper bound on a wake time a machine files itself (ParkRequester.update(wake_after=...)).
MAX_WAKE_AFTER_TICKS = 6000

# Oil Generators on a grid whose lower of battery / combined reserve fraction falls
# below this are woken at once (their script starts burning at
# oil_generator.OIL_START_RESERVE_FRACTION = 0.30, so this leaves time to react).
OIL_WAKE_RESERVE_FRACTION = 0.40
# A grid's low-reserve verdict is reused for this many ticks (the reserve moves slowly; measuring
# reads every steam tank of the grid).
RESERVE_CACHE_TICKS = 150
# Oil Generators are woken (and not parked) while the network-wide oil tank fill is at or
# above this: their script runs them as base load from oil_generator.OIL_SURPLUS_START_FRACTION
# (same value; oil_generator imports this module, so it cannot be imported here). Not on a grid a
# producing Reactor carries (power.reactor_carried()): their script burns no surplus there.
OIL_SURPLUS_WAKE_FRACTION = 0.90

SOLAR_TYPE_ID = "solar_generator"

# {machine_id: {"kind": type_id, "first": tick, "stage": 1 | 2}}: stray dark machines (module docstring).
STRAY_KEY = "script.stray_dark"
# {machine_id: note}: operator list of machines switched off on purpose; never stray.
MANUAL_OFF_KEY = "script.manual_off"
# Ticks after first sight: notify() + Status alert, then breaker on + script start.
STRAY_NOTIFY_TICKS = 600
STRAY_SWITCH_ON_TICKS = 3000


def _power_module():
    """lib/power.py, imported on first use (see the note at the imports); tests may set `power`."""
    global power
    if power is None:
        import power as grid_power
        power = grid_power
    return power


def parked_ids(kind=None):
    """Ids of breaker-parked machines (of `kind`, if given), from PARKED_KEY."""
    try:
        parked = archive.get(PARKED_KEY, {}) or {}
    except Exception as error:
        swallowed("script_parking.parked_ids: archive.get", error)
        return set()
    if not isinstance(parked, dict):
        return set()
    return {m for m, e in parked.items() if isinstance(e, dict) and e.get("mode") == "breaker" and (kind is None or e.get("kind") == kind)}


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
            swallowed("script_parking.wake_for_visit: archive.transaction(HOLDS_KEY)", error)
    if machine_id not in parked_ids():
        return False
    power_control = get_component("power_control")
    try:
        result = power_control.set_powered(machine_id, True) if power_control else None
    except Exception as error:
        swallowed("script_parking.wake_for_visit: power_control.set_powered", error)
        return False
    if getattr(result, "status", "") != "ok":
        log.debug(f"wake_for_visit({machine_id}): set_powered -> {getattr(result, 'status', None)}")
        return False

    def unpark(parked):
        parked = parked if isinstance(parked, dict) else {}
        parked.pop(machine_id, None)
        return parked

    try:
        archive.transaction(PARKED_KEY, {}, unpark)
    except Exception as error:
        swallowed("script_parking.wake_for_visit: archive.transaction(PARKED_KEY)", error)
    ScriptParking._clear_requests({machine_id: now})  # its pre-park request must not park it again
    log.print(f"[PARKING] Woke {machine_id} ({reason}).")
    return True


def parked_nearest(ref, station_refs, parked, awake_distance):
    """Id of the parked station strictly nearer to `ref` (a fleet VehicleRef/DroneRef) than
    awake_distance, the nearest one if several; None when the nearest station is awake."""
    best, best_id = awake_distance, None
    for station in station_refs:
        if station["id"] not in parked:
            continue
        dist = ((ref.x - station["coords"][0]) ** 2 + (ref.y - station["coords"][1]) ** 2) ** 0.5
        if best is None or dist < best:
            best, best_id = dist, station["id"]
    return best_id


def wake_kind(kind, reason):
    """
    Switches on every machine of `kind` parked here and drops them from PARKED_KEY,
    for a change that may give all of them work (e.g. a new field layout wakes every
    parked field provider). Callable from any script. Returns the ids woken.
    """
    try:
        parked = archive.get(PARKED_KEY, {}) or {}
    except Exception as error:
        swallowed("script_parking.wake_kind: archive.get", error)
        return []
    since = {m: e.get("since", 0) for m, e in (parked.items() if isinstance(parked, dict) else ())
             if isinstance(e, dict) and e.get("mode") == "breaker" and e.get("kind") == kind}
    ids = sorted(since)
    if not ids:
        return []
    power_control = get_component("power_control")
    woken = []
    for machine_id in ids:
        try:
            result = power_control.set_powered(machine_id, True) if power_control else None
        except Exception as error:
            swallowed("script_parking.wake_kind: power_control.set_powered", error)
            continue
        if getattr(result, "status", "") == "ok":
            woken.append(machine_id)

    def unpark(parked):
        parked = parked if isinstance(parked, dict) else {}
        for machine_id in woken:
            parked.pop(machine_id, None)
        return parked

    if woken:
        try:
            archive.transaction(PARKED_KEY, {}, unpark)
        except Exception as error:
            swallowed("script_parking.wake_kind: archive.transaction", error)
        ScriptParking._clear_requests({m: since[m] for m in woken})  # their pre-park requests must not park them again
        log.print(f"[PARKING] Woke {len(woken)} {kind}(s) ({reason}).")
    return woken


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


# Grid members per atomic _member_rows() call (~25 operations each).
MEMBER_CHUNK = 150


def _member_rows(chunk, anchor, members, by_type, dark):
    """Adds one slice of a grid's members to the pass's index: members {id: (anchor, type_id, powered)},
    by_type {type_id: [ids]}, dark [ids switched off]. Pure reads, run atomically."""
    for member in chunk:
        member_id = getattr(member, "id", None)
        if member_id:
            type_id = getattr(member, "type_id", "")
            powered = bool(getattr(member, "powered", True))
            members[member_id] = (anchor, type_id, powered)
            by_type.setdefault(type_id, []).append(member_id)
            if not powered:
                dark.append(member_id)


def _held(machine_id, now):
    """True while wake_for_visit() holds machine_id awake."""
    try:
        holds = archive.get(HOLDS_KEY, {}) or {}
    except Exception as error:
        swallowed("script_parking._held: archive.get", error)
        return True
    return isinstance(holds, dict) and holds.get(machine_id, 0) > now


def start_script(machine_id):
    """run_control.start(machine_id), treating already_running as success.
    Returns "ok", the refusal status, "no_run_control" or "error: <exception>"."""
    try:
        run = get_component("run_control")
    except Exception as error:
        swallowed("script_parking.start_script: get_component", error)
        run = None
    if not run:
        return "no_run_control"
    try:
        res = run.start(machine_id)
    except Exception as error:
        swallowed("script_parking.start_script: run.start", error)
        return f"error: {error}"
    return "ok" if res.status in ("ok", "already_running") else res.status


def set_powered(power: "PowerControl | None", machine_id, on, log: "TreeConsole"):
    """power_control.set_powered(machine_id, on); True on "ok". A refusal is
    logged at debug on log, an exception goes to swallowed()."""
    if power is None:
        return False
    try:
        result = power.set_powered(machine_id, on)
    except Exception as error:
        swallowed("script_parking.set_powered: power.set_powered", error)
        return False
    status = getattr(result, "status", "")
    if status != "ok":
        log.debug(f"set_powered({machine_id}, {on}) -> {status}")
    return status == "ok"

def _demand_signature(dock_plan):
    """
    {(kind, source key, item): amount} of the archive demand Fabricators and Smelters work from (archive
    reads only): manual / upgrade / backlog orders and the site plan (kind
    "fabricator"), ingot stock targets ("smelter"), and the order ids in the dock plan (both kinds: the
    order's items are not read here, so either may be needed). The computed site targets are left out
    on purpose: they shrink as stock arrives.
    """
    from production_orders import MANUAL_ORDERS_KEY, UPGRADE_ORDERS_KEY, BACKLOG_ORDERS_KEY
    from production_demand import INGOT_STOCK_TARGETS_KEY
    from production_sites import SITE_PLAN_KEY

    def stored(key):
        value = archive.get(key, {})
        return value if isinstance(value, dict) else {}

    def positive(amount):
        return isinstance(amount, (int, float)) and amount > 0

    signature = {}
    signature.update({("fabricator", MANUAL_ORDERS_KEY, item): amount for item, amount in stored(MANUAL_ORDERS_KEY).items() if positive(amount)})
    for key in (UPGRADE_ORDERS_KEY, BACKLOG_ORDERS_KEY):
        for items in stored(key).values():
            for item, amount in (items.items() if isinstance(items, dict) else ()):
                if positive(amount):
                    signature[("fabricator", key, item)] = signature.get(("fabricator", key, item), 0) + amount
    for root, sites in stored(SITE_PLAN_KEY).items():
        signature.update({("fabricator", SITE_PLAN_KEY, f"{root} at {site}"): 1 for site in (sites if isinstance(sites, list) else ())})
    ingots = stored(INGOT_STOCK_TARGETS_KEY)
    signature.update({("smelter", INGOT_STOCK_TARGETS_KEY, item): entry["target"] for item, entry in ingots.items() if isinstance(entry, dict) and positive(entry.get("target"))})
    for order_id in set((dock_plan or {}).values()) - {None}:
        for kind in DEMAND_WAKE_KINDS:
            signature[(kind, "dock_plan", f"dock order {order_id}")] = 1
    return signature


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
            self._write(now_tick(), wake_after)

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


def stray_alerts(entries=None):
    """[(text, "warn")] for the Status panel: one line over every stray dark machine at stage 2."""
    if entries is None:
        try:
            entries = archive.get(STRAY_KEY, {}) or {}
        except Exception as error:
            swallowed("script_parking.stray_alerts: archive.get", error)
            return []
    if not isinstance(entries, dict):
        return []
    ids = sorted(m for m, e in entries.items() if isinstance(e, dict) and e.get("stage", 1) >= 2)
    if not ids:
        return []
    shown = ", ".join(ids[:3]) + (f" +{len(ids) - 3}" if len(ids) > 3 else "")
    return [(f"Switched off, no owner: {shown}", "warn")]


class ScriptParking:
    """Panel-side half, one instance in orchestrator_automation.py; call `step()` every few seconds."""

    def __init__(self, power: "PowerControl | None" = None, run_control: "RunControl | None" = None):
        self.power = power or get_component("power_control")
        self.run_control = run_control or get_component("run_control")
        # {machine_id: (tick of its last re-check wake, fruitless streak)}; lost on a restart, which only resets the backoff.
        self._rechecks = {}
        # {grid anchor id: (tick, low)}: _low_reserve_grids() verdicts, reused for RESERVE_CACHE_TICKS.
        self._reserve_cache = {}
        # {(kind, source key, item): amount} of the last pass's demand (_demand_signature()); None before the first pass.
        self._demand = None
        # This pass's member index from _members(): {type_id: [ids]} and the ids switched off.
        self._by_type = {}
        self._dark = []
        # Last full pass's members dict and oil surplus verdict, reused by fast passes; None before the first full pass.
        self._members_seen = None
        self._oil_seen = False

    def step(self, grids: "list[PowerGrid]", elevation, dock_plan=None, full=True):
        """
        One pass: wake due or triggered machines, park fresh requests, stop/start
        solar scripts by `elevation`. `grids` = power_control.grids() of this tick;
        `dock_plan` = supply_dock.order_plan ({dock_id: order_id or None}).
        full=False is a fast pass: wakes and the sunrise solar start only, on the last
        full pass's member rows and oil surplus verdict. Parking, the powered-again and
        orphan checks, the night solar stop and strays wait for the next full pass (the
        first pass is always full).
        """
        now = now_tick()
        parked = archive.get(PARKED_KEY, {}) or {}
        parked = dict(parked) if isinstance(parked, dict) else {}
        before = dict(parked)
        requests = archive.get(PARK_REQUESTS_KEY, {}) or {}
        requests = requests if isinstance(requests, dict) else {}
        shed = set(archive.get("power.shedded", []) or [])
        full = full or self._members_seen is None
        if full:
            self._members_seen = self._members(grids)
        members = self._members_seen or {}
        changed = False
        woken = {}  # {machine_id: parked-since tick}: their requests from before parking are cleared below

        log.start("script parking", level="debug")
        low_grids = self._low_reserve_grids(grids, parked, requests, members)
        if full:
            self._oil_seen = self._oil_surplus(parked, requests)
        oil_surplus = self._oil_seen
        reactor_grids = self._reactor_grids(grids) if oil_surplus else set()
        # Demand rises and dock orders wake their machines at the writer (wake_on_rise(),
        # supply_dock.plan_dock_assignments()); these checks are the full pass's backstop.
        demand_wakes = self._demand_wakes(dock_plan) if full else {}
        for machine_id, entry in list(parked.items()):
            if entry.get("mode") != "breaker":
                continue
            member = members.get(machine_id)  # read this full pass (or the last one): it exists; its powered flag is current on full passes
            if member is None and get_component(machine_id) is None:
                log.debug(f"{machine_id} no longer exists, dropped from the parked list")
                del parked[machine_id]
                self._rechecks.pop(machine_id, None)
                changed = True
                continue
            if full and (member[2] if member is not None else self._is_powered(machine_id)):
                # Switched on by the player (or anything else): no longer parked here.
                log.debug(f"{machine_id} is powered again, dropped from the parked list")
                woken[machine_id] = entry.get("since", now)
                del parked[machine_id]
                changed = True
                continue
            reason = self._wake_reason(machine_id, entry, now, members, low_grids, dock_plan if full else None, oil_surplus, demand_wakes, reactor_grids)
            if reason and self._set_powered(machine_id, True):
                log.debug(f"woke {machine_id} ({reason})")
                woken[machine_id] = entry.get("since", now)
                del parked[machine_id]
                self._note_wake(machine_id, reason, entry, now)
                changed = True

        if woken:
            self._clear_requests(woken)
        if full:
            changed = self._park_and_tend(parked, before, requests, woken, shed, members, now, elevation, dock_plan,
                                          demand_wakes, oil_surplus, low_grids, reactor_grids) or changed
        elif elevation is not None and elevation > 0:
            # Sunrise start on fast passes too: a full pass alone starts the panels up to ~36 game min late.
            changed = self._solar(elevation, members, parked, now) or changed
        if changed:
            self._commit(before, parked)
        if full:
            self._strays(members, parked, woken, shed, requests, now)
        log.end()

    def _park_and_tend(self, parked, before, requests, woken, shed, members, now, elevation, dock_plan,
                       demand_wakes, oil_surplus, low_grids, reactor_grids):
        """Full pass only: re-adopts orphans, parks fresh requests, stops/starts solar scripts. Returns True
        when `parked` changed beyond the parks, which each commit on their own."""
        awake = None  # {station kind: ids neither parked nor shed}, built on first use
        changed = self._adopt_orphans(parked, requests, woken, shed, members, now)
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
            if kind in demand_wakes:
                continue  # demand rose this pass: stay up one more pass to see it
            if kind == "oil_generator" and ((oil_surplus and members[machine_id][0] not in reactor_grids) or members[machine_id][0] in low_grids):
                continue  # reserve already low or oil in surplus: stay ready instead of parking and waking again
            if kind in STATION_KINDS:
                if awake is None:
                    awake = self._awake_stations(self._by_type, parked, shed)
                if awake[kind] <= {machine_id}:
                    continue  # last one awake of its kind
            if kind in HELD_KINDS and _held(machine_id, now):
                continue
            entry = {"kind": kind, "mode": "breaker", "since": now}
            if request.get("wake_after") is not None:
                entry["wake_after"] = min(int(request["wake_after"]), MAX_WAKE_AFTER_TICKS)
            else:
                filed = request.get("tick")
                backoff = self._backoff_wake_after(machine_id, kind, filed if isinstance(filed, (int, float)) else now)
                if backoff is not None:
                    entry["wake_after"] = backoff
                    log.debug(f"{machine_id} found no work after its last re-check, next one in {backoff} ticks")
            # Recorded before the breaker goes off: a script killed in between leaves an
            # entry for a powered machine (dropped next pass), never an untracked dark one.
            self._commit({}, {machine_id: entry})
            if self._set_powered(machine_id, False):
                parked[machine_id] = entry
                before[machine_id] = entry
                if awake is not None and kind in awake:
                    awake[kind].discard(machine_id)
                log.debug(f"parked {machine_id} ({kind})")
            else:
                self._commit({machine_id: entry}, {})

        return self._solar(elevation, members, parked, now) or changed

    @staticmethod
    def _commit(before, after):
        """Applies only the difference between before and after to PARKED_KEY, in one
        transaction, so entries other scripts wrote meanwhile (turbine_commit,
        wake_for_visit()) survive."""
        dropped = [m for m in before if m not in after]
        written = {m: e for m, e in after.items() if before.get(m) is not e}
        if not dropped and not written:
            return

        def updater(parked):
            parked = parked if isinstance(parked, dict) else {}
            for machine_id in dropped:
                parked.pop(machine_id, None)
            parked.update(written)
            return parked

        try:
            archive.transaction(PARKED_KEY, {}, updater)
        except Exception as error:
            swallowed("script_parking.ScriptParking._commit: archive.transaction", error)

    def _adopt_orphans(self, parked, requests, woken, shed, members, now):
        """
        Backup scan: a machine switched off at its breaker with a stale park request, but
        in neither PARKED_KEY nor the shed list, was parked by a pass whose record got
        lost. Nothing else would switch it on, so it goes back into `parked` with its
        request tick as `since`, which makes its re-check due. Returns True when any was adopted.
        """
        adopted = []
        for machine_id, request in requests.items():
            if machine_id in parked or machine_id in woken or machine_id in shed or not isinstance(request, dict):
                continue
            kind = request.get("kind")
            tick = request.get("tick", 0)
            if kind not in WAKE_AFTER_TICKS or now - tick <= REQUEST_FRESH_TICKS:
                continue
            member = members.get(machine_id)
            if member is None or member[2] or self._is_powered(machine_id):
                continue
            parked[machine_id] = {"kind": kind, "mode": "breaker", "since": tick}
            adopted.append(machine_id)
        if adopted:
            log.level("warn").print(f"[PARKING] Re-adopted {len(adopted)} untracked dark machine(s): {', '.join(sorted(adopted))}.")
        return bool(adopted)

    # ------------------------------------------------------------------ wake

    def _note_wake(self, machine_id, reason, entry, now):
        """Remembers a timed re-check wake (its fruitless streak so far) for _backoff_wake_after(); other wakes forget it."""
        if reason != "re-check due" or entry.get("kind") not in WAKE_BACKOFF_MAX_TICKS:
            self._rechecks.pop(machine_id, None)
            return
        streak = self._rechecks.get(machine_id, (0, 0))[1]
        self._rechecks[machine_id] = (now, streak)

    def _backoff_wake_after(self, machine_id, kind, filed):
        """wake_after for a machine being parked, longer when its last re-check found no work; None for the kind default.
        `filed` = tick of its park request: the machine's own idle verdict, so the gap between parking passes does not count."""
        cap = WAKE_BACKOFF_MAX_TICKS.get(kind)
        recheck = self._rechecks.get(machine_id)
        if cap is None or recheck is None:
            return None
        woke, streak = recheck
        if filed - woke > FRUITLESS_REPARK_TICKS:
            self._rechecks.pop(machine_id, None)
            return None
        streak += 1
        self._rechecks[machine_id] = (woke, streak)
        return min(WAKE_AFTER_TICKS[kind] << streak, cap)

    def _demand_wakes(self, dock_plan):
        """{kind: item} of the DEMAND_WAKE_KINDS whose demand rose since the previous pass (the first pass only records it)."""
        try:
            signature = _demand_signature(dock_plan)
        except Exception as error:
            swallowed("script_parking.ScriptParking._demand_wakes: _demand_signature", error)
            return {}
        previous, self._demand = self._demand, signature
        if previous is None:
            return {}
        wakes = {}
        for key, amount in signature.items():
            if key[0] not in wakes and amount > previous.get(key, 0):
                wakes[key[0]] = key[2]
        if wakes:
            log.debug(f"demand rose: {wakes}")
        return wakes

    def _wake_reason(self, machine_id, entry, now, members, low_grids, dock_plan, oil_surplus=False, demand_wakes=None, reactor_grids=None):
        kind = entry.get("kind")
        if demand_wakes and kind in demand_wakes:
            return f"demand changed: {demand_wakes[kind]}"
        if now - entry.get("since", now) >= entry.get("wake_after", WAKE_AFTER_TICKS.get(kind, 600)):
            return "re-check due"
        if kind == "supply_dock" and (dock_plan or {}).get(machine_id):
            return "order assigned"
        if kind == "oil_generator" and members.get(machine_id, (None,))[0] in low_grids:
            return "grid reserve low"
        if kind == "oil_generator" and oil_surplus and members.get(machine_id, (None,))[0] not in (reactor_grids or ()):
            return "oil surplus"
        if kind == "oil_pump" and self._well_active(machine_id):
            return "well active"
        if kind == "exotic_cap" and self._deposit_active(machine_id):
            return "deposit active"
        return None

    @staticmethod
    def _awake_stations(by_type, parked, shed):
        """{station kind: ids on the grids neither parked nor shed}, for every STATION_KINDS kind."""
        return {kind: {m for m in by_type.get(kind, ()) if m not in parked and m not in shed} for kind in STATION_KINDS}

    @staticmethod
    def _well_active(machine_id):
        """Oil Pump well_active() (readable from any script); True on a read failure so the pump wakes."""
        pump = oil_pump(machine_id)
        if pump is None or not hasattr(pump, "well_active"):
            return False
        try:
            return bool(pump.well_active())
        except Exception as error:
            swallowed("script_parking._well_active: pump.well_active", error)
            return True

    @staticmethod
    def _deposit_active(machine_id):
        """Exotic cap/tap deposit().current_phase() == "active" (readable from any script); True on a read failure so it wakes."""
        cap = get_component(machine_id)
        if cap is None or not hasattr(cap, "deposit"):
            return False
        try:
            deposit = cap.deposit()
            return deposit is not None and deposit.current_phase() == "active"
        except Exception as error:
            swallowed("script_parking._deposit_active: cap.deposit", error)
            return True

    @staticmethod
    def _reactor_grids(grids: "list[PowerGrid]"):
        """Anchor ids of grids a producing Reactor carries (power.reactor_carried()): no oil surplus wake there."""
        grid_power = _power_module()
        carried = getattr(grid_power, "reactor_carried", None)
        if carried is None:
            return set()
        return {getattr(grid, "anchor_id", None) for grid in grids or [] if carried(grid)}

    @staticmethod
    def _oil_surplus(parked, requests):
        """True while an Oil Generator is parked or asks to be, and the network-wide oil tank fill is >= OIL_SURPLUS_WAKE_FRACTION."""
        entries = list(parked.values()) + [r for r in requests.values() if isinstance(r, dict)]
        if not any(isinstance(e, dict) and e.get("kind") == "oil_generator" for e in entries):
            return False
        fill = fluid_routing.fluid_reserve_fraction("oil")
        return fill is not None and fill >= OIL_SURPLUS_WAKE_FRACTION

    def _low_reserve_grids(self, grids: "list[PowerGrid]", parked, requests, members):
        """Anchor ids of grids with a parked or park-requesting Oil Generator whose reserve is below OIL_WAKE_RESERVE_FRACTION."""
        entries = list(parked.items()) + [(m, r) for m, r in requests.items() if isinstance(r, dict)]
        wanted = {members[m][0] for m, e in entries if e.get("kind") == "oil_generator" and m in members}
        if not wanted:
            return set()
        low = set()
        grid_power = _power_module()
        if not hasattr(grid_power, "measure_grid"):
            return low
        curr_tick = now_tick()
        tanks = {}  # {anchor: gas tank ids}, from the member rows already read this pass
        for member_id in self._by_type.get("gas_tank", ()):
            anchor = members[member_id][0]
            if anchor in wanted:
                tanks.setdefault(anchor, []).append(member_id)
        for grid in grids:
            anchor = getattr(grid, "anchor_id", None)
            if anchor not in wanted:
                continue
            cached = self._reserve_cache.get(anchor)
            if cached is not None and 0 <= curr_tick - cached[0] < RESERVE_CACHE_TICKS:
                if cached[1]:
                    low.add(anchor)
                continue
            try:
                now = grid_power.measure_grid(grid, tanks.get(anchor, []))
                fractions = [f for f in (grid_power.reserve_fraction(now), now["bat_wh"] / now["bat_cap"] if now["bat_cap"] > 0 else None) if f is not None]
            except Exception as error:
                swallowed("script_parking._low_reserve_grids: power.measure_grid", error)
                low.add(anchor)  # unreadable reserve: wake, the generator's own script fails safe
                continue
            is_low = not fractions or min(fractions) < OIL_WAKE_RESERVE_FRACTION
            self._reserve_cache[anchor] = (curr_tick, is_low)
            if is_low:
                low.add(anchor)
        for anchor in [a for a in self._reserve_cache if a not in wanted]:
            del self._reserve_cache[anchor]
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

    # ------------------------------------------------------------------ strays

    def _strays(self, members, parked, woken, shed, requests, now):
        """Advances every stray dark machine one stage when due (module docstring); keeps STRAY_KEY current."""
        try:
            strays = archive.get(STRAY_KEY, {}) or {}
        except Exception as error:
            swallowed("script_parking._strays: archive.get", error)
            return
        strays = strays if isinstance(strays, dict) else {}
        dark = [m for m in self._dark if m not in parked and m not in woken and m not in shed and m not in requests]
        if not dark and not strays:
            return
        if dark:
            manual = archive.get(MANUAL_OFF_KEY, {}) or {}
            excluded = retired_ids() | (set(manual) if isinstance(manual, dict) else set())
            dark = [m for m in dark if m not in excluded]
        updated = {}
        for machine_id in sorted(dark):
            entry = strays.get(machine_id)
            type_id = members[machine_id][1]
            if not isinstance(entry, dict):
                if not self._can_power_off(machine_id):
                    continue
                entry = {"kind": type_id, "first": now, "stage": 1}
                log.level("warn").print(
                    f"[PARKING] {machine_id} ({type_id}) is switched off at its breaker and no automation owns that. "
                    f"Switching it on in {STRAY_SWITCH_ON_TICKS // 600} min unless listed in archive '{MANUAL_OFF_KEY}'.")
            age = now - entry.get("first", now)
            if age >= STRAY_SWITCH_ON_TICKS:
                if self._switch_on_stray(machine_id, type_id):
                    continue
            elif age >= STRAY_NOTIFY_TICKS and entry.get("stage", 1) < 2:
                entry = dict(entry, stage=2)
                self._notify(f"[Parking] {machine_id} ({type_id}) has been switched off for {age // 600} min with no automation owning it; "
                             f"it is switched on in {(STRAY_SWITCH_ON_TICKS - age) // 600} min. List it in archive '{MANUAL_OFF_KEY}' to keep it off.")
            updated[machine_id] = entry
        for machine_id in strays:
            if machine_id not in updated and machine_id not in dark:
                log.debug(f"{machine_id} no longer stray dark")
        if updated != strays:
            try:
                archive.set(STRAY_KEY, updated)
            except Exception as error:
                swallowed("script_parking._strays: archive.set", error)

    def _switch_on_stray(self, machine_id, type_id):
        """Breaker on, then starts the script when it is idle (never run). True when the breaker went on."""
        if not self._set_powered(machine_id, True):
            return False
        state = self._script_state(machine_id)
        started = state == "idle" and self._run(machine_id, "start")
        if state in ("error", "completed"):
            log.level("warn").print(f"[PARKING] Switched on stray dark {machine_id} ({type_id}); its script is {state}, not restarted.")
        else:
            log.print(f"[PARKING] Switched on stray dark {machine_id} ({type_id}){'; started its script' if started else ''}.")
        return True

    def _script_state(self, machine_id):
        """run_control.status().state; None when the machine has no script or the read fails."""
        if self.run_control is None:
            return None
        try:
            return getattr(self.run_control.status(machine_id), "state", None)
        except ReferenceError:
            return None
        except Exception as error:
            swallowed("script_parking._script_state: run_control.status", error)
            return None

    @staticmethod
    def _notify(text):
        try:
            notify(text, level="warn", duration_seconds=10.0)
        except Exception as error:
            swallowed("script_parking._notify: notify", error)

    # ------------------------------------------------------------------ solar

    def _solar(self, elevation, members, parked, now):
        """Stops running solar scripts while the sun is down, starts the ones stopped here once it is up."""
        if self.run_control is None or elevation is None:
            return False
        changed = False
        if elevation <= 0:
            stopped = []
            for machine_id in self._by_type.get(SOLAR_TYPE_ID, ()):
                if machine_id in parked or not self._is_running(machine_id):
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

    def _members(self, grids: "list[PowerGrid]"):
        """{machine_id: (grid anchor id, type_id, powered)} over every grid; also sets
        self._by_type and self._dark, so later steps walk only the members they need.
        The member reads run in atomic batches (_member_rows())."""
        members, by_type, dark = {}, {}, []
        for grid in grids:
            items = list(getattr(grid, "members", []) or [])
            anchor = getattr(grid, "anchor_id", None)
            for start in range(0, len(items), MEMBER_CHUNK):
                run_atomic(_member_rows, items[start:start + MEMBER_CHUNK], anchor, members, by_type, dark)
        self._by_type, self._dark = by_type, dark
        return members

    def _is_powered(self, machine_id):
        """power_control.is_powered(); False on a read failure (the entry stays until its re-check)."""
        if self.power is None:
            return False
        try:
            return bool(self.power.is_powered(machine_id))
        except Exception as error:
            swallowed("script_parking._is_powered: power.is_powered", error)
            return False

    def _can_power_off(self, machine_id):
        if self.power is None:
            return False
        try:
            return bool(self.power.can_power_off(machine_id))
        except Exception as error:
            swallowed("script_parking._can_power_off: power.can_power_off", error)
            return False

    def _set_powered(self, machine_id, on):
        return set_powered(self.power, machine_id, on, log)

    def _is_running(self, machine_id):
        if self.run_control is None:
            return False
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
