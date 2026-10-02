# Run loop of the infrastructure planner (autoplay/infra_planner_automation.py):
# one pass per PASS_SLEEP_S, ending the script once a pass finds nothing left
# to plan and nothing of its own still open. Restart the script to plan again.
#
# Pass order: read the map (infra_topology.Topology), prune autoplay.planned,
# keep the power-line ledger current (power_survey: one-off full survey when
# the ledger has none, vanished-job check, dirty-tile re-probe), then the
# power pass (power_plan.PowerPlanner) with the ledger's line tiles, then the
# fluid pass (fluid_plan.FluidPlanner). The script ends once the power pass
# reports one grid and the fluid pass has nothing left to route.

from swallow import swallowed
from tree_console import TreeConsole, reset_all, flush_all
from infra_topology import Topology
from blueprint_queue import prune_planned
from power_plan import PowerPlanner
from fluid_plan import FluidPlanner
import power_survey

PASS_SLEEP_S = 60   # seconds between passes while work is open


def _tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed("planner_loop._tick: clock.tick", error)
        return 0


def _phase(log, started, what):
    """Debug line naming a finished pass phase and its sim seconds since `started`; returns the current tick."""
    now = _tick()
    log.debug(f"Pass: {what} ({(now - started) / 10:.1f} s).")
    log.flush()
    return now


def _upkeep_ledger(log, survey_locked):
    """Ledger upkeep before the power pass; returns True when the full survey is unavailable (locked)."""
    if not survey_locked and power_survey.ledger()["surveyed"] is None:
        survey_locked = power_survey.run_full(log) == "locked"
    power_survey.reprobe_dirty(log)
    return survey_locked


def run_planner():
    log = TreeConsole(module="infra_planner")
    power = PowerPlanner(log)
    fluids = FluidPlanner(log)
    topo = Topology()
    survey_locked = False
    log.print("Infrastructure planner online.")
    while True:
        reset_all()
        outcome = "error"
        fluid_outcome = "error"
        try:
            mark = _tick()
            topo.read(log)
            mark = _phase(log, mark, f"map read: {topo.last}, {len(topo.job_rows)} utility jobs")
            dropped = prune_planned(topo.job_ids, topo.jobs_ok)
            vanished = power_survey.track_jobs(topo)
            mark = _phase(log, mark, f"bookkeeping, {dropped} planned job(s) dropped, {vanished} vanished power tile(s) to re-probe")
            survey_locked = _upkeep_ledger(log, survey_locked)
            tiles = power_survey.ledger_tiles()
            mark = _phase(log, mark, f"power ledger ready, {len(tiles)} tile(s)")
            outcome = power.run_pass(topo, tiles)
            mark = _phase(log, mark, f"power pass: {outcome}")
            fluid_outcome = fluids.run_pass(topo)
            _phase(log, mark, f"fluid pass: {fluid_outcome}")
        except Exception as error:
            swallowed("planner_loop.run_planner: pass", error)
            log.level("error").print(f"Planner pass failed: {error}")
        if outcome == "joined" and fluid_outcome == "done":
            log.print("Infrastructure planner: one power grid, every fluid network routed. Ending.")
            flush_all()
            return
        flush_all()
        sleep(PASS_SLEEP_S)
