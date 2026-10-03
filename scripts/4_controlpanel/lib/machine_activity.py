"""
Machine activity: how much of the time each machine, and each group of machines
that pools its work, is busy, waiting, idle or not running at all. Shows the
groups that have more members than their work needs (retire candidates).

Sampled by control_room_automation.py right after each script census
(script_census.census_if_due(), every CENSUS_TICK_INTERVAL ticks) from that
census snapshot plus archive state other scripts already publish
(fleet.status, script.parked, script.park_requests). No calls on the machines.

One class per machine per sample:
- "active": vehicle/drone in a working fleet.status state; building whose
  script runs with no open park request (only in groups with an idle signal,
  see "running").
- "waiting": vehicle/drone blocked by something outside it (FLEET_WAITING_STATES:
  Depot full, no free bay, no inventory space, stranded). It has work, but the
  far end cannot take it.
- "idle": script runs with nothing to do: vehicle/drone in an idle state
  (FLEET_IDLE_STATES or any "IDLE*"), or a building with an open park request
  (script_parking.ParkRequester: idle PARK_AFTER_IDLE_STEPS steps in a row).
- "running": script runs, no idle signal: a building group none of whose
  members has ever filed a park request or been parked (no ParkRequester), or
  a vehicle/drone with no fleet.status entry.
- "parked": script paused by script parking (any script.parked mode).
- "off": script neither running nor parked (stopped, completed, load-shed).
Machines that were never running or parked (storage, tanks, ...) are left out.

Group: building/field machine type_id; vehicle kind or "drone", plus
":<role>" from fleet.status (e.g. "drone:miner", "pioneer:hauler").

Archive ACTIVITY_KEY (single writer: the Automation), counts decay with half-life
HALF_LIFE_TICKS so they describe the recent past:
{"tick": last sample, "samples": n,
 "groups": {group: {"n": members now, "sig": idle signal seen, "w": decayed samples,
                    "c": {class: decayed machine-samples}, "spare": [decayed samples with k spare members],
                    "share": {class: % of machine time}, "spare_mean": avg spare members,
                    "retire": spare members in SPARE_QUANTILE of samples}},
 "machines": {id: {"g": group, "c": {class: decayed samples}, "l": class in the last sample}}}
"Spare" = SPARE_CLASSES (waiting, idle, parked, off). "retire" is the number of
members the group could lose and still have had every busy member it used in
SPARE_QUANTILE of the samples. See docs/cheatsheet/dev_workflow.md §1d-3.
"""

from archive import archive
from tree_console import TreeConsole
from swallow import swallowed
from atomic import run_batched
from fleet_status import FLEET_STATUS_KEY, IDLE_STATES
from script_parking import PARKED_KEY, PARK_REQUESTS_KEY

log = TreeConsole(module="machine_activity")

ACTIVITY_KEY = "machine.activity"
# Decay half-life of every count: ~6 h at 10 ticks/s.
HALF_LIFE_TICKS = 216000
# "retire" = spare members in at least this share of samples.
SPARE_QUANTILE = 0.9
# Ticks between two debug summaries (one line per group).
SUMMARY_LOG_TICKS = 36000
# Machines per atomic batch (classify, accumulate).
ACTIVITY_CHUNK = 50
# Decayed weights below this are dropped.
MIN_WEIGHT = 0.01

CLASSES = ("active", "waiting", "idle", "running", "parked", "off")
SPARE_CLASSES = ("waiting", "idle", "parked", "off")
FLEET_IDLE_STATES = IDLE_STATES + ("READY_AT_DEPOT", "WAITING_AFTERMATH", "DECOMMISSION_READY")
FLEET_WAITING_STATES = ("WAITING_DEPOT_SPACE", "WAITING_DEPOT_BAY", "WAITING_INVENTORY_SPACE", "STRANDED", "AWAITING_RESCUE")
DRONE_KINDS = ("drone_small", "drone_medium", "drone_large")

last_summary_tick = None


def fleet_class(state):
    """Activity class of a fleet.status state."""
    state = state or ""
    if state.startswith("IDLE") or state in FLEET_IDLE_STATES:
        return "idle"
    if state in FLEET_WAITING_STATES:
        return "waiting"
    return "active"


def group_of(kind, role=None):
    base = "drone" if kind in DRONE_KINDS else kind
    return f"{base}:{role}" if role else base


def _classify(rows, running, fleet, parked, requests):
    """[(id, group, class, idle signal)] for script_census.machine_refs() rows. A running
    building is "active" here; _accumulate() turns it "running" in groups without signal."""
    out = []
    for machine_id, kind, name, mobile in rows:
        entry = None
        if mobile:
            entry = fleet.get(machine_id) or fleet.get(name)
            entry = entry if isinstance(entry, dict) else None
            group = group_of(kind, entry.get("role") if entry else None)
        else:
            group = group_of(kind)
        if machine_id in running:
            if mobile:
                cls = fleet_class(entry.get("state")) if entry else "running"
            else:
                cls = "idle" if machine_id in requests else "active"
        elif machine_id in parked:
            cls = "parked"
        else:
            cls = "off"
        out.append((machine_id, group, cls, mobile or machine_id in requests or machine_id in parked))
    return out


def _accumulate(rows, machines, previous, factor, signal_groups):
    """Decays each tracked machine's counts by `factor`, adds this sample; writes into `machines`.
    Returns the [(group, class)] of the machines it tracked."""
    out = []
    for machine_id, group, cls, _ in rows:
        old = previous.get(machine_id)
        if not isinstance(old, dict) and cls == "off":
            continue
        if cls == "active" and group not in signal_groups:
            cls = "running"
        counts = {}
        if isinstance(old, dict):
            for key, value in (old.get("c") or {}).items():
                value = value * factor
                if value >= MIN_WEIGHT:
                    counts[key] = round(value, 3)
        counts[cls] = round(counts.get(cls, 0) + 1, 3)
        machines[machine_id] = {"g": group, "c": counts, "l": cls}
        out.append((group, cls))
    return out


def spare_quantile(spare, quantile=SPARE_QUANTILE):
    """Largest k with at least `quantile` of the sample weight at k or more spare members."""
    total = sum(spare)
    if total <= 0:
        return 0
    covered = 0.0
    for k in range(len(spare) - 1, -1, -1):
        covered += spare[k]
        if covered >= quantile * total:
            return k
    return 0


def _update_groups(tracked, previous, factor, signal_groups):
    """New groups dict from this sample's [(group, class)] and the decayed previous groups."""
    now = {}
    for group, cls in tracked:
        entry = now.setdefault(group, {"n": 0, "spare": 0, "c": {}})
        entry["n"] += 1
        entry["c"][cls] = entry["c"].get(cls, 0) + 1
        if cls in SPARE_CLASSES:
            entry["spare"] += 1
    groups = {}
    for group, sample in now.items():
        old = previous.get(group)
        old = old if isinstance(old, dict) else {}
        counts = {k: v * factor for k, v in (old.get("c") or {}).items()}
        for cls, n in sample["c"].items():
            counts[cls] = counts.get(cls, 0) + n
        counts = {k: round(v, 3) for k, v in counts.items() if v >= MIN_WEIGHT}
        spare = [round(v * factor, 3) for v in (old.get("spare") or [])]
        while len(spare) <= sample["spare"]:
            spare.append(0.0)
        spare[sample["spare"]] = round(spare[sample["spare"]] + 1, 3)
        weight = round((old.get("w") or 0) * factor + 1, 3)
        machine_time = sum(counts.values()) or 1
        groups[group] = {
            "n": sample["n"],
            "sig": group in signal_groups,
            "w": weight,
            "c": counts,
            "spare": spare,
            "share": {k: round(100.0 * v / machine_time, 1) for k, v in counts.items()},
            "spare_mean": round(sum(counts.get(k, 0) for k in SPARE_CLASSES) / weight, 2),
            "retire": spare_quantile(spare),
        }
    return groups


def _read_dict(key):
    try:
        value = archive.get(key, {}) or {}
    except Exception as error:
        swallowed(f"machine_activity._read_dict: archive.get({key})", error)
        return {}
    return value if isinstance(value, dict) else {}


def record(snapshot, now):
    """Adds one sample from a script_census.snapshot() (rows, running ids) taken at tick `now`;
    returns the new ACTIVITY_KEY value."""
    rows, running = snapshot
    state = _read_dict(ACTIVITY_KEY)
    last_tick = state.get("tick")
    elapsed = now - last_tick if isinstance(last_tick, (int, float)) else 0
    factor = 0.5 ** (elapsed / HALF_LIFE_TICKS) if elapsed > 0 else 1.0
    previous_groups = state.get("groups") or {}
    previous_machines = state.get("machines") or {}

    classified = run_batched(_classify, rows, ACTIVITY_CHUNK, running, _read_dict(FLEET_STATUS_KEY), _read_dict(PARKED_KEY), _read_dict(PARK_REQUESTS_KEY))
    signal_groups = {group for _, group, _, signal in classified if signal}
    signal_groups.update(g for g, e in previous_groups.items() if isinstance(e, dict) and e.get("sig"))
    machines = {}
    tracked = run_batched(_accumulate, classified, ACTIVITY_CHUNK, machines, previous_machines, factor, signal_groups)
    state = {
        "tick": now,
        "samples": (state.get("samples") or 0) + 1,
        "groups": _update_groups(tracked, previous_groups, factor, signal_groups),
        "machines": machines,
    }
    archive.set(ACTIVITY_KEY, state)
    _log_summary_if_due(state, now)
    return state


def _log_summary_if_due(state, now):
    global last_summary_tick
    if last_summary_tick is not None and now - last_summary_tick < SUMMARY_LOG_TICKS:
        return
    last_summary_tick = now
    groups = state.get("groups") or {}
    log.start(f"machine activity: {len(state.get('machines') or {})} machines in {len(groups)} groups, {state.get('samples')} samples", level="debug")
    for group in sorted(groups, key=lambda g: (-groups[g]["retire"], -groups[g]["spare_mean"], g)):
        entry = groups[group]
        shares = " ".join(f"{cls} {entry['share'][cls]:.0f}%" for cls in CLASSES if cls in entry["share"])
        log.debug(f"{group}: {entry['n']} machines, {shares}; spare mean {entry['spare_mean']:.1f}, retire {entry['retire']}")
    log.end()


def get():
    """The ACTIVITY_KEY value ({} before the first sample)."""
    return _read_dict(ACTIVITY_KEY)


def group_rows(state):
    """[(group, entry)] of an ACTIVITY_KEY value, most retire first, then most spare_mean, then name."""
    groups = state.get("groups") or {}
    rows = [(g, e) for g, e in groups.items() if isinstance(e, dict)]
    return sorted(rows, key=lambda r: (-(r[1].get("retire") or 0), -(r[1].get("spare_mean") or 0), r[0]))


def machine_rows(state, group):
    """[(id, {class: % of its samples}, last class, spare %)] of `group`'s machines, most spare time first."""
    rows = []
    for machine_id, entry in (state.get("machines") or {}).items():
        if not isinstance(entry, dict) or entry.get("g") != group:
            continue
        counts = entry.get("c") or {}
        total = sum(counts.values()) or 1
        share = {k: round(100.0 * v / total, 1) for k, v in counts.items()}
        spare = round(sum(share.get(k, 0) for k in SPARE_CLASSES), 1)
        rows.append((machine_id, share, entry.get("l"), spare))
    return sorted(rows, key=lambda r: (-r[3], r[0]))
