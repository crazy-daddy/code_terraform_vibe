# Run loop of the infrastructure planner (autoplay/infra_planner.py): one pass
# per PASS_SLEEP_S, ending the script once a pass finds nothing left to plan
# and nothing of its own still open. Restart the script to plan again.
#
# Pass order: read the map (infra_topology.Topology), prune autoplay.planned,
# then the power pass (power_plan.PowerPlanner).

from swallow import swallowed
from tree_console import TreeConsole, reset_all, flush_all
from infra_topology import Topology
from blueprint_queue import prune_planned
from power_plan import PowerPlanner

PASS_SLEEP_S = 60   # seconds between passes while work is open


def run_planner():
    log = TreeConsole(module="infra_planner")
    power = PowerPlanner(log)
    log.print("Infrastructure planner online.")
    while True:
        reset_all()
        outcome = "error"
        try:
            topo = Topology().read()
            dropped = prune_planned(topo.job_ids, topo.jobs_ok)
            if dropped:
                log.debug(f"autoplay.planned: {dropped} finished or cancelled job(s) dropped.")
            outcome = power.run_pass(topo)
        except Exception as error:
            swallowed("planner_loop.run_planner: pass", error)
            log.level("error").print(f"Planner pass failed: {error}")
        if outcome == "joined":
            log.print("Infrastructure planner: one power grid, nothing to plan. Ending.")
            flush_all()
            return
        flush_all()
        sleep(PASS_SLEEP_S)
