"""
Script census: how many machine scripts count toward the game's step split.

Above 50 running scripts the game gives every running or sleeping script
floor(50000 / N) interpreter steps per tick (docs/cheatsheet/dev_workflow.md
§1d-1), so a block's cost in ticks depends on N at the time it ran.
`census_if_due()` counts `run_control.is_running()` over every machine id
(outpost buildings, Harvesting-field machines, vehicles and drones) every
CENSUS_TICK_INTERVAL ticks and logs one debug line, "scripts running: N of M
machines, allowance A steps/tick", which devtools/log_block_timing.py reads to
turn block ticks into steps. is_running() reads True while a script runs or
sleeps and False when paused (breaker), stopped, completed or errored: the
same set the game counts in N.
"""

from tree_console import TreeConsole
from swallow import swallowed
from atomic import run_batched

log = TreeConsole(module="script_census")

# Ticks between two counts.
CENSUS_TICK_INTERVAL = 300
# Machine ids per atomic is_running() batch (a few steps each).
CENSUS_CHUNK = 100
# Game scheduler constants (§1d-1): total steps per tick shared by all scripts, cap per script.
TOTAL_STEPS_PER_TICK = 50000
MAX_STEPS_PER_SCRIPT = 1000

last_census_tick = None


def allowance(running):
    """Steps per script per tick with `running` scripts counted."""
    if running <= 0:
        return MAX_STEPS_PER_SCRIPT
    return max(1, min(MAX_STEPS_PER_SCRIPT, TOTAL_STEPS_PER_TICK // running))


def machine_ids():
    """Ids of every owned machine that can carry a script."""
    ids = []
    network = get_component("outpost_network")
    try:
        outposts = list(network.outposts()) if network else []
    except Exception as error:
        swallowed("script_census.machine_ids: network.outposts", error)
        outposts = []
    for outpost in outposts:
        try:
            ids.extend(getattr(ref, "id", "") for ref in outpost.buildings())
            if hasattr(outpost, "harvesting_machines"):
                ids.extend(getattr(ref, "id", "") for ref in outpost.harvesting_machines())
        except Exception as error:
            swallowed("script_census.machine_ids: outpost.buildings", error)
    fleet = get_component("fleet")
    try:
        if fleet:
            ids.extend(getattr(ref, "id", "") for ref in fleet.mobile_units())
    except Exception as error:
        swallowed("script_census.machine_ids: fleet.mobile_units", error)
    return list(dict.fromkeys(i for i in ids if i))


def _running_rows(ids, run):
    return [machine_id for machine_id in ids if run.is_running(machine_id)]


def count_running():
    """(running scripts, machine ids checked), or None without run_control."""
    run = get_component("run_control")
    if not run:
        return None
    ids = machine_ids()
    try:
        running = run_batched(_running_rows, ids, CENSUS_CHUNK, run)
    except Exception as error:
        swallowed("script_census.count_running: atomic is_running", error)
        running = _running_rows(ids, run)
    return len(running), len(ids)


def census_if_due(now):
    """Every CENSUS_TICK_INTERVAL ticks: count running scripts and log the census line."""
    global last_census_tick
    if last_census_tick is not None and now - last_census_tick < CENSUS_TICK_INTERVAL:
        return
    last_census_tick = now
    counted = count_running()
    if counted is None:
        return
    running, total = counted
    log.start("script census", level="debug")
    log.debug(f"scripts running: {running} of {total} machines, allowance {allowance(running)} steps/tick")
    log.end()
