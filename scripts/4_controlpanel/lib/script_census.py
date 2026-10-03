"""
Script census: how many scripts count toward the game's step split.

Above 50 running scripts the game gives every running or sleeping script
floor(50000 / N) interpreter steps per tick (docs/cheatsheet/dev_workflow.md
§1d-1), so a block's cost in ticks depends on N at the time it ran.
`census_if_due()` counts `run_control.is_running()` every CENSUS_TICK_INTERVAL
ticks over every machine id and logs one debug line, "scripts running: N of M
machines (...), allowance A steps/tick", which devtools/log_block_timing.py
reads to turn block ticks into steps. is_running() reads True while a script
runs or sleeps and False when paused (breaker), stopped, completed or errored:
the same set the game counts in N.

Machines (machine_refs()): outpost buildings, Harvesting-field machines, the
mobile Harvester, vehicles and drones, plus the extractors at points of
interest (POI_TYPE_IDS), which outpost.buildings() omits and which are found
as power_control grid members. Panel and automation scripts (ui_script_ids())
count toward N only: no API lists them, so panel_1..panel_K and
automation_1..automation_K are probed (K = max(fixed probe limit, highest id
found + PROBE_AHEAD)). Scripts on sensors and the planet (boot, uplink, ...)
are not listed and not counted, so N is a lower bound. The machine rows and
running machine ids feed lib/machine_activity.py; panel/automation ids stay
out of them.
"""

from tree_console import TreeConsole
from swallow import swallowed
from atomic import run_batched

log = TreeConsole(module="script_census")

# Ticks between two counts.
CENSUS_TICK_INTERVAL = 300
# Ids per atomic is_running() batch (a few steps each).
CENSUS_CHUNK = 100
# Game scheduler constants (§1d-1): total steps per tick shared by all scripts, cap per script.
TOTAL_STEPS_PER_TICK = 50000
MAX_STEPS_PER_SCRIPT = 1000
# Extractors at points of interest: not in outpost.buildings(), found as power grid members.
POI_TYPE_IDS = ("thermal_cap", "water_pump", "exotic_gas_cap", "exotic_spring_tap", "oil_pump")
# Id of the single mobile Harvester.
HARVESTER_ID = "harvester_1"
# Panel/automation id probes: always up to these numbers, or PROBE_AHEAD past the highest one found.
PANEL_PROBE_LIMIT = 40
AUTOMATION_PROBE_LIMIT = 10
PROBE_AHEAD = 40

last_census_tick = None
highest_found = {"panel": 0, "automation": 0}


def allowance(running):
    """Steps per script per tick with `running` scripts counted."""
    if running <= 0:
        return MAX_STEPS_PER_SCRIPT
    return max(1, min(MAX_STEPS_PER_SCRIPT, TOTAL_STEPS_PER_TICK // running))


def _poi_rows():
    """Rows of the POI extractors, from power_control grid members."""
    power = get_component("power_control")
    try:
        grids = list(power.grids()) if power else []
    except Exception as error:
        swallowed("script_census._poi_rows: power.grids", error)
        return []
    rows = []
    for grid in grids:
        for member in getattr(grid, "members", None) or []:
            if getattr(member, "type_id", "") in POI_TYPE_IDS:
                rows.append((getattr(member, "id", ""), member.type_id, getattr(member, "name", ""), False))
    return rows


def _harvester_rows():
    """Row of the mobile Harvester (not in harvesting_machines()). Its id is fixed and not
    listed by any API; an unknown id reads not running."""
    return [(HARVESTER_ID, "harvester", "", False)]


def ui_script_ids():
    """Candidate ids of panel and automation scripts (probed; most do not exist)."""
    ids = []
    for prefix, limit in (("panel", PANEL_PROBE_LIMIT), ("automation", AUTOMATION_PROBE_LIMIT)):
        top = max(limit, highest_found[prefix] + PROBE_AHEAD)
        ids.extend(f"{prefix}_{n}" for n in range(1, top + 1))
    return ids


def _note_found(ids):
    for prefix in highest_found:
        numbers = [int(i[len(prefix) + 1:]) for i in ids if i.startswith(prefix + "_") and i[len(prefix) + 1:].isdigit()]
        if numbers:
            highest_found[prefix] = max(highest_found[prefix], max(numbers))


def machine_refs():
    """(id, kind, name, mobile) of every owned machine that can carry a script: kind is the
    building or field machine's type_id, or the mobile unit's kind ("pioneer", "drone_small", ...)."""
    rows = []
    network = get_component("outpost_network")
    try:
        outposts = list(network.outposts()) if network else []
    except Exception as error:
        swallowed("script_census.machine_refs: network.outposts", error)
        outposts = []
    for outpost in outposts:
        try:
            rows.extend((getattr(ref, "id", ""), getattr(ref, "type_id", ""), getattr(ref, "name", ""), False) for ref in outpost.buildings())
            if hasattr(outpost, "harvesting_machines"):
                rows.extend((getattr(ref, "id", ""), getattr(ref, "type_id", ""), getattr(ref, "name", ""), False) for ref in outpost.harvesting_machines())
        except Exception as error:
            swallowed("script_census.machine_refs: outpost.buildings", error)
    fleet = get_component("fleet")
    try:
        if fleet:
            rows.extend((getattr(ref, "id", ""), getattr(ref, "kind", ""), getattr(ref, "name", ""), True) for ref in fleet.mobile_units())
    except Exception as error:
        swallowed("script_census.machine_refs: fleet.mobile_units", error)
    rows.extend(_poi_rows())
    rows.extend(_harvester_rows())
    seen = set()
    unique = []
    for row in rows:
        if row[0] and row[0] not in seen:
            seen.add(row[0])
            unique.append(row)
    return unique


def machine_ids():
    """Ids of every owned machine that can carry a script."""
    return [row[0] for row in machine_refs()]


def _running_rows(ids, run):
    return [machine_id for machine_id in ids if run.is_running(machine_id)]


def snapshot():
    """(machine_refs() rows, set of machine ids whose script runs or sleeps, set of running
    panel/automation ids), or None without run_control."""
    run = get_component("run_control")
    if not run:
        return None
    rows = machine_refs()
    ids = [row[0] for row in rows]
    probes = [i for i in ui_script_ids() if i not in set(ids)]
    try:
        running = run_batched(_running_rows, ids + probes, CENSUS_CHUNK, run)
    except Exception as error:
        swallowed("script_census.snapshot: atomic is_running", error)
        running = _running_rows(ids + probes, run)
    probe_set = set(probes)
    ui = {i for i in running if i in probe_set}
    _note_found(ui)
    return rows, set(running) - ui, ui


def count_running():
    """(running scripts incl. panels/automations, machine ids checked), or None without run_control."""
    taken = snapshot()
    if taken is None:
        return None
    rows, running, ui = taken
    return len(running) + len(ui), len(rows)


def census_if_due(now):
    """Every CENSUS_TICK_INTERVAL ticks: count running scripts and log the census line.
    Returns the snapshot() it counted (lib/machine_activity.py samples it), else None."""
    global last_census_tick
    if last_census_tick is not None and now - last_census_tick < CENSUS_TICK_INTERVAL:
        return None
    last_census_tick = now
    taken = snapshot()
    if taken is None:
        return None
    rows, running, ui = taken
    total = len(running) + len(ui)
    log.start("script census", level="debug")
    log.debug(f"scripts running: {total} of {len(rows)} machines (incl. {len(ui)} panel/automation scripts; sensor and planet scripts not counted), allowance {allowance(total)} steps/tick")
    log.end()
    return taken
