# Run loop of the infrastructure planner (autoplay/infra_planner_automation.py):
# one pass per PASS_SLEEP_S while infrastructure work is open, then one every
# WATCH_SLEEP_S. The loop keeps running: the building pass watches the
# outposts for the rest of the game.
#
# Pass order: the founding pass (outpost_plan.OutpostPlanner: needs, sites,
# proposals as map markers, operator answers), the building pass
# (building_plan.BuildingPlanner: proposals on the BUILD card, approved ones
# run as building_ops jobs; it reuses the founding pass's snapshot when that
# is younger than its own PASS_TICKS), then read the map (infra_topology.Topology), prune autoplay.planned,
# keep the power-line ledger current (power_survey: one-off full survey when
# the ledger has none, vanished-job check, dirty-tile re-probe), then the
# power pass (power_plan.PowerPlanner) with the ledger's line tiles, then the
# fluid pass (fluid_plan.FluidPlanner), then the extractor pass
# (extractor_plan.ExtractorPlanner). Plan-ahead work (supply_tiers) runs only
# while the passes before it have nothing urgent left. Once the power pass
# has nothing to join, the fluid pass nothing to route and the extractor pass
# nothing to place, the loop runs only the founding pass (markers; a full
# pass when OutpostPlanner.due()) and the building pass every WATCH_SLEEP_S,
# and the infrastructure passes again once a designation was written.
#
# run_founding() (autoplay/outpost_planner_automation.py) runs the founding
# pass alone: a full pass first, then marker watching every WATCH_SLEEP_S
# (a full pass when due()), ending once no proposal waits. A written
# designation is left to the next infrastructure planner run. Run only one of
# the two automations at a time: both own the same proposals and markers.

from swallow import swallowed
from tree_console import TreeConsole, reset_all, flush_all
from infra_topology import Topology
from blueprint_queue import prune_planned
from power_plan import PowerPlanner
from fluid_plan import FluidPlanner
from extractor_plan import ExtractorPlanner
from outpost_plan import OutpostPlanner
from building_plan import BuildingPlanner, PASS_TICKS as BUILD_PASS_TICKS
import power_survey

PASS_SLEEP_S = 60    # seconds between passes while work is open
WATCH_SLEEP_S = 300  # seconds between marker checks while only proposals wait


def _tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed("planner_loop._tick: clock.tick", error)
        return 0


def _phase(log: "TreeConsole", started, what):
    """Debug line naming a finished pass phase and its sim seconds since `started`; returns the current tick."""
    now = _tick()
    log.debug(f"Pass: {what} ({(now - started) / 10:.1f} s).")
    log.flush()
    return now


def _upkeep_ledger(log: "TreeConsole", survey_locked):
    """Ledger upkeep before the power pass; returns True when the full survey is unavailable (locked)."""
    if not survey_locked and power_survey.ledger()["surveyed"] is None:
        survey_locked = power_survey.run_full(log) == "locked"
    power_survey.reprobe_dirty(log)
    return survey_locked


def _founding(log: "TreeConsole", founding, infra_done):
    """The founding pass; returns its outcome ("error" on failure)."""
    try:
        mark = _tick()
        outcome = founding.run_pass(not infra_done or founding.due())
        _phase(log, mark, f"founding pass: {outcome}")
        return outcome
    except Exception as error:
        swallowed("planner_loop._founding: pass", error)
        log.level("error").print(f"Founding pass failed: {error}")
        return "error"


def _building(log: "TreeConsole", building, founding):
    """The building pass; returns its outcome ("error" on failure)."""
    try:
        mark = _tick()
        fresh = founding.snap_tick is not None and mark - founding.snap_tick < BUILD_PASS_TICKS
        outcome = building.run_pass(founding.snap if fresh else None)
        _phase(log, mark, f"building pass: {outcome}")
        return outcome
    except Exception as error:
        swallowed("planner_loop._building: pass", error)
        log.level("error").print(f"Building pass failed: {error}")
        return "error"


def run_planner():
    log = TreeConsole(module="infra_planner")
    founding = OutpostPlanner(log)
    building = BuildingPlanner(log)
    power = PowerPlanner(log)
    fluids = FluidPlanner(log)
    extractors = ExtractorPlanner(log)
    topo = Topology()
    survey_locked = False
    infra_done = False
    log.print("Infrastructure planner online.")
    while True:
        reset_all()
        founding_outcome = _founding(log, founding, infra_done)
        if founding_outcome == "changed":
            infra_done = False
        _building(log, building, founding)
        if infra_done:
            flush_all()
            sleep(WATCH_SLEEP_S)
            continue
        outcome = "error"
        fluid_outcome = "error"
        extractor_outcome = "error"
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
            fluid_outcome = fluids.run_pass(topo, outcome == "joined")
            mark = _phase(log, mark, f"fluid pass: {fluid_outcome}")
            extractor_outcome = extractors.run_pass(topo, outcome == "joined" and fluid_outcome == "done")
            _phase(log, mark, f"extractor pass: {extractor_outcome}")
        except Exception as error:
            swallowed("planner_loop.run_planner: pass", error)
            log.level("error").print(f"Planner pass failed: {error}")
        if outcome == "joined" and fluid_outcome == "done" and extractor_outcome == "done":
            log.print("Infrastructure planner: grids joined, fluid networks routed, extractors placed; "
                      "watching outposts.")
            infra_done = True
        flush_all()
        sleep(PASS_SLEEP_S)


def run_founding():
    log = TreeConsole(module="outpost_planner")
    founding = OutpostPlanner(log)
    full = True
    log.print("Outpost founding planner online.")
    while True:
        reset_all()
        outcome = _founding(log, founding, not full)
        full = founding.due()
        if outcome == "changed":
            log.print("Outpost founding planner: designation written; the infrastructure planner picks it up on its next run.")
        if outcome in ("idle", "locked"):
            log.print(f"Outpost founding planner: no outpost proposal waits ({outcome}). Ending.")
            flush_all()
            return
        flush_all()
        sleep(WATCH_SLEEP_S)
