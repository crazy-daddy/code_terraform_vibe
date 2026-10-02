# Run loop of the infrastructure planner (autoplay/infra_planner_automation.py):
# one pass per PASS_SLEEP_S, ending the script once a pass finds nothing left
# to plan and nothing of its own still open. Restart the script to plan again.
#
# Pass order: read the map (infra_topology.Topology), prune autoplay.planned,
# keep the power-line ledger current (power_survey: one-off full survey when
# the ledger has none, vanished-job check, dirty-tile re-probe), then the
# power pass (power_plan.PowerPlanner) with the ledger's line tiles.

from swallow import swallowed
from tree_console import TreeConsole, reset_all, flush_all
from infra_topology import Topology
from blueprint_queue import prune_planned
from power_plan import PowerPlanner
import power_survey

PASS_SLEEP_S = 60   # seconds between passes while work is open


def _upkeep_ledger(log, survey_locked):
    """Ledger upkeep before the power pass; returns True when the full survey is unavailable (locked)."""
    if not survey_locked and power_survey.ledger()["surveyed"] is None:
        survey_locked = power_survey.run_full(log) == "locked"
    power_survey.reprobe_dirty(log)
    return survey_locked


def run_planner():
    log = TreeConsole(module="infra_planner")
    power = PowerPlanner(log)
    survey_locked = False
    log.print("Infrastructure planner online.")
    while True:
        reset_all()
        outcome = "error"
        try:
            topo = Topology().read()
            dropped = prune_planned(topo.job_ids, topo.jobs_ok)
            if dropped:
                log.debug(f"autoplay.planned: {dropped} finished or cancelled job(s) dropped.")
            vanished = power_survey.track_jobs(topo)
            if vanished:
                log.debug(f"Power ledger: {vanished} tile(s) of vanished power jobs marked for re-probe.")
            survey_locked = _upkeep_ledger(log, survey_locked)
            outcome = power.run_pass(topo, power_survey.ledger_tiles())
        except Exception as error:
            swallowed("planner_loop.run_planner: pass", error)
            log.level("error").print(f"Planner pass failed: {error}")
        if outcome == "joined":
            log.print("Infrastructure planner: one power grid, nothing to plan. Ending.")
            flush_all()
            return
        flush_all()
        sleep(PASS_SLEEP_S)
