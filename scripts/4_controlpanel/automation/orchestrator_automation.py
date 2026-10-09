# ct-automation: orchestrator_automation
# ORCHESTRATOR -- an Automation (Computer > Automations), the base's planner:
# belongs to no machine, has no power supply, so a brownout never pauses the
# grid supervision below. Draws nothing; status_panel.py's STATUS/AUTOMATION
# card reads this script's results back out of `archive`. A single pass can
# take seconds (supply_dock.plan_dock_assignments() over several orders), which
# is why none of this runs inside a card that renders every tick.
#
# SLOT NUMBER: the game numbers automation_N slots itself, so the live slot
# differs per save. devtools/scripts_sync.py pairs the slot with this file by
# the ct-automation marker on line 1 -- see docs/cheatsheet/panels.md §7.
#
# Responsibilities, by cadence (intervals are the *_TICK_INTERVAL constants
# below; docs/cheatsheet/panels.md §7):
#
# Short timers, checked every loop and again between the storage pass's slow
# sub-steps (between_steps()), since one full loop can outlast the battery:
#   - Power Grid supervision (lib/power.py PowerGridManager), one manager per
#     grid, reused across loops so its state persists: load shedding, solar
#     night guard, turbine commitment. A grid merged into another releases
#     what it had shed.
#   - Script parking (lib/script_parking.py): wakes parked machines; every
#     PARKING_FULL_TICK_INTERVAL also parks idle ones. On the same timer:
#     requested script restarts (lib/script_restart.py; the ones out of
#     restarts are named on the AUTOMATION card) and the running-script
#     census that feeds machine activity (lib/machine_activity.py).
#   - Early build order (lib/early_buyer.py), from the lib tier (Data
#     Archive, 70k TP) until the Control Room: fills the base generator
#     slots, buys power, the Charging Station and the Rovers, queues the
#     scout Pioneer. Idle for good afterwards.
#   - Supply Dock planning (supply_dock.plan_dock_assignments()): the one
#     decider that splits Earth Orders across the docks; replans only when
#     an order or dock changed, or after DOCK_PLAN_MAX_TICK_INTERVAL.
#   - Wildlife planner (lib/wildlife_planner.py), on its own interval; a
#     no-op without Habitats.
#   - Thermal vent cycle log (lib/vent_cycles.py): times each surveyed
#     vent's active/dormant phases.
#
# Own timers, once per loop:
#   - Biomass Mixer duty-cycle gate (lib/biomass_mixer_gate.py): a paused
#     Mixer can't wake itself. Once biomass is complete (lib/biomass_retire.py)
#     BiomassRetirement switches the Liquifier/Mixer chain off instead.
#   - Mining Drill telemetry (mining_drill.publish_all_drills()).
#
# Storage pass, every STORAGE_TICK_INTERVAL, in this order:
#   - Cash manager (lib/cash.py CashManager): balance history, income and
#     reagent burn, dynamic floor, ask queue for the CASH card. First, so
#     the buyers (here and in builder_automation.py) see a fresh floor.
#   - Inventory <-> Warehouse sweeps (lib/storage.py): items spread over many
#     Inventory slots, or already split with a Warehouse, move out to a
#     Warehouse; gear that must stay in Inventory moves back.
#   - Storage Bin consolidation (storage.consolidate_storage_bins()): one
#     transfer that merges a small bin into another bin of the same item.
#   - Map markers, from Cartography (140k TP) on: once per run the backfill
#     of blacklisted targets (lib/unsupported_markers.py) and surveyed mineral
#     sites; each pass, unassigned resource markers go to the closest
#     mining-designated outpost (outpost_mining.assign_unassigned_sites()).
#   - Factory outposts: lib/site_plan.py places each root Fabricator target
#     at the fab sites that build its tree, then lib/site_supply.py publishes
#     what each outpost needs hauled in and evicts ore stranded at an outpost
#     that lost its Smelters.
#   - Home salt request (lib/pump_salt.py): the field's buffer plus what the
#     Plant Terraformers still need.
#   - Plants completion (lib/plants_retire.py): undeploys each Plant
#     Terraformer once it reads "complete" and has emptied its holders.
#   - Pipe conflicts (fluid_routing.active_pipe_conflicts()) for the card.
#   - Publishes the AUTOMATION card summary (AUTOMATION_SUMMARY_KEY).
#
# Buying, deploying, upgrading and removing hardware (fleet commission,
# decommission and upgrade, pillar swap, storage swaps) is
# builder_automation.py's job. The early build order stays here: it runs from
# the tier switch on, before a builder slot exists, and the headless runner
# (devtools/headless/run.mjs) runs only this automation.
#
# lib/solar.py's SolarController and lib/smelter.py's SmelterController rely
# on this script for the grid and storage work above. The manual
# "Clean Archive"/"Sync Unsupported"/"Confirm New Version" buttons live on
# status_panel.py: rare, operator-triggered one-offs, not per-loop work.

from archive import archive
from power import PowerGridManager
from early_buyer import EarlyBuyer
from biomass_mixer_gate import MixerGate
from biomass_retire import BiomassRetirement, biomass_complete
from storage import consolidate_storage_bins, rebalance_inventory_to_warehouses, reclaim_inventory_only_items_from_warehouses
from version_guard import version_mismatch
from unsupported_markers import update_unsupported_markers
import outpost_mining
import supply_dock
from cash import CashManager
from site_supply import publish_site_requests
from pump_salt import publish_home_salt_request
import plants_retire
from site_plan import plan_sites
from production import reconcile_manual_transit
from mining_drill import publish_all_drills
import wildlife_planner
from fluid_routing import active_pipe_conflicts
from script_parking import ScriptParking
import script_restart
from script_census import census_if_due
import machine_activity
import vent_cycles
from tree_console import flush_all, reset_all
from game_clock import now_tick

# Published each time the storage-tick automation runs; status_panel.py reads this
# to display the "ALWAYS-ON" line instead of computing it itself. Left
# untouched (not overwritten) while version_mismatch() halts automation below;
# status_panel.py shows its own fixed
# "halted" message in that case rather than trusting a stale summary.
AUTOMATION_SUMMARY_KEY = "control_room.automation_summary"
# Joins the summary's parts; status_panel.py splits on it (parts may contain commas).
SUMMARY_SEPARATOR = " | "

# ~1s and 10s at 10 ticks/sec (see lib/archive_cleaner.py's documented tick rate).
SOLAR_TICK_INTERVAL = 10
STORAGE_TICK_INTERVAL = 100
MIXER_GATE_TICK_INTERVAL = 10
# Dock planning is checked on its own, shorter interval, at the top of every loop and again between
# the storage pass's sub-steps: those sweeps wait on feeder cycles, and a plan held back until they
# finish lets docks read an assignment for an order that has already completed. A check replans only
# when supply_dock.plan_signature() changed (an order appeared, completed or expired; docks added or
# removed) or DOCK_PLAN_MAX_TICK_INTERVAL
# has passed (ranking by stock and shipped progress): a plan costs ~40 ticks in game.
DOCK_PLAN_TICK_INTERVAL = 50
DOCK_PLAN_MAX_TICK_INTERVAL = 600
# Mining Drill telemetry for every drill (lib/mining_drill.py publish_all_drills()); drills need no
# script of their own, and a stockpile fills over hours.
DRILL_TELEMETRY_TICK_INTERVAL = 600
# Script parking pass (lib/script_parking.py): wakes parked machines every PARKING_TICK_INTERVAL; every
# PARKING_FULL_TICK_INTERVAL the pass is full and also parks idle machines, stops solar at night and
# tends strays. A full pass costs about three fast ones; requests stay fresh (REQUEST_FRESH_TICKS) in between.
PARKING_TICK_INTERVAL = 50
PARKING_FULL_TICK_INTERVAL = 150
# Vent phase poll (lib/vent_cycles.py); a late poll only widens a flip's error bar, it never records a wrong length.
VENT_CYCLE_TICK_INTERVAL = 50
# The Wildlife planner (lib/wildlife_planner.py) runs on its own interval
# (wildlife_planner.PLAN_TICK_INTERVAL); a no-op without Habitats.

grid_managers = {}          # {anchor_id: PowerGridManager}, reused so day/night state persists
last_solar_tick = 0
last_storage_tick = 0
last_mixer_gate_tick = 0
last_drill_tick = 0
last_parking_tick = 0
last_parking_full_tick = 0
last_vent_tick = 0
parking = None              # ScriptParking, created once power_control is available
# signature = plan_signature() at the last plan; plan_tick = its tick
dock_plan = {"last_tick": 0, "signature": None, "plan_tick": 0}
# "<step> error" for each step that failed since the last summary publish
errors = []
# Coordinator summaries that mean "nothing for the operator to see"; left off the AUTOMATION card.
IDLE_SUMMARIES = (wildlife_planner.IDLE_SUMMARY, plants_retire.IDLE_SUMMARY, "early buyer idle", "early buyer done")
QUIET_SUMMARY = "all quiet"


def report_error(what, error):
    """Prints a failed step to the console and keeps it for the next AUTOMATION card summary."""
    print(f"[AUTOMATION] {what} error: {error}")
    if f"{what} error" not in errors:
        errors.append(f"{what} error")


def card_items(summaries):
    """AUTOMATION card items: this pass's errors, then every non-idle coordinator summary."""
    items = errors + [s for s in (str(s) for s in summaries) if s not in IDLE_SUMMARIES]
    return items or [QUIET_SUMMARY]


def plan_docks_if_due(clock: "Clock | None"):
    """
    Every DOCK_PLAN_TICK_INTERVAL: runs supply_dock.plan_dock_assignments() when
    supply_dock.plan_signature() differs from the last plan's, or
    DOCK_PLAN_MAX_TICK_INTERVAL has passed since it.
    """
    now = now_tick()
    if dock_plan["last_tick"] != 0 and now - dock_plan["last_tick"] < DOCK_PLAN_TICK_INTERVAL:
        return
    dock_plan["last_tick"] = now
    try:
        signature = supply_dock.plan_signature()
        if signature == dock_plan["signature"] and now - dock_plan["plan_tick"] < DOCK_PLAN_MAX_TICK_INTERVAL:
            return
        supply_dock.plan_dock_assignments(clock=clock)
        dock_plan["signature"] = signature
        dock_plan["plan_tick"] = now
    except Exception as e:
        report_error("Supply Dock planning", e)

def plan_wildlife_if_due():
    """Wildlife planner pass when due; its summary goes on the AUTOMATION card."""
    try:
        wildlife_planner.plan_if_due()
    except Exception as e:
        report_error("Wildlife planner", e)


def supervise_grids_if_due(clock: "Clock | None", power: "PowerControl | None"):
    """Every SOLAR_TICK_INTERVAL: PowerGridManager.supervise_grid() on every grid (Power Guard, turbine commitment)."""
    global last_solar_tick
    now = now_tick()
    if last_solar_tick != 0 and now - last_solar_tick < SOLAR_TICK_INTERVAL:
        return
    last_solar_tick = now
    try:
        elevation = clock.get_elevation() if clock else 0.0
        live_grids = power.grids() if power and hasattr(power, "grids") else []
        current_anchors = set()
        for grid in live_grids:
            anchor = getattr(grid, "anchor_id", None)
            current_anchors.add(anchor)
            manager = grid_managers.get(anchor)
            if manager is None:
                manager = PowerGridManager(grid, clock=clock, power=power)
                grid_managers[anchor] = manager
            manager.supervise_grid(grid, elevation)

        # Grids that stopped being reported (merged into another via a new
        # power line) -- release anything they still had shed rather than
        # stranding it forever (see PowerGridManager.release_all()).
        for stale_anchor in list(grid_managers.keys()):
            if stale_anchor not in current_anchors:
                grid_managers[stale_anchor].release_all()
                del grid_managers[stale_anchor]
    except Exception as e:
        report_error("Grid supervision", e)


def park_if_due(clock: "Clock | None", power: "PowerControl | None"):
    """Every PARKING_TICK_INTERVAL: one ScriptParking.step() pass (wakes due or triggered machines; every
    PARKING_FULL_TICK_INTERVAL a full pass that also parks idle ones),
    the requested script restarts (lib/script_restart.py), then the running-script census when due (script_census.census_if_due()), whose snapshot feeds the
    machine activity sample (lib/machine_activity.py)."""
    global last_parking_tick, last_parking_full_tick, parking
    now = now_tick()
    if last_parking_tick != 0 and now - last_parking_tick < PARKING_TICK_INTERVAL:
        return
    last_parking_tick = now
    try:
        if parking is None and power:
            parking = ScriptParking(power=power)
        if parking is not None:
            full = last_parking_full_tick == 0 or now - last_parking_full_tick >= PARKING_FULL_TICK_INTERVAL
            if full:
                last_parking_full_tick = now
            parking.step(
                power.grids() if power and hasattr(power, "grids") else [],
                clock.get_elevation() if clock and hasattr(clock, "get_elevation") else None,
                archive.get(supply_dock.ORDER_PLAN_ARCHIVE_KEY, {}) or {},
                full=full,
            )
    except Exception as e:
        report_error("Script parking", e)
    try:
        restarted, refused = script_restart.process_restart_requests(get_component("run_control"), now)
        if restarted:
            print(f"[AUTOMATION] Restarted on request: {', '.join(restarted)}.")
        for machine_id, status in refused.items():
            print(f"[AUTOMATION] Restart of {machine_id} refused ({status}); retrying next pass.")
    except Exception as e:
        report_error("Script restarts", e)
    try:
        taken = census_if_due(now)
    except Exception as e:
        report_error("Script census", e)
        taken = None
    if taken is not None:
        try:
            machine_activity.record(taken, now)
        except Exception as e:
            report_error("Machine activity", e)


def log_vents_if_due():
    """Every VENT_CYCLE_TICK_INTERVAL: one vent_cycles.step() poll."""
    global last_vent_tick
    now = now_tick()
    if last_vent_tick != 0 and now - last_vent_tick < VENT_CYCLE_TICK_INTERVAL:
        return
    last_vent_tick = now
    try:
        vent_cycles.step(now)
    except Exception as e:
        report_error("Vent cycles", e)


def buy_early_if_due():
    """Every early_buyer.EVAL_TICKS until the Control Room: one EarlyBuyer evaluation."""
    try:
        early_buyer.step()
    except Exception as e:
        report_error("Early buyer", e)


def between_steps(clock: "Clock | None"):
    """Short-interval checks run between the storage pass's slow sub-steps. Grid supervision and
    parking wakes go first: the power reserve can drain within one full loop pass."""
    power = get_component("power_control")
    supervise_grids_if_due(clock, power)
    park_if_due(clock, power)
    buy_early_if_due()
    plan_docks_if_due(clock)
    plan_wildlife_if_due()
    log_vents_if_due()

mixer_gate = None           # MixerGate, created lazily once power_control is available
biomass_retirement = None   # BiomassRetirement, created once biomass is complete
cash_manager = CashManager()  # stateless between cycles (state lives in archive)
early_buyer = EarlyBuyer()  # done flag in archive
plants_retirement = None    # plants_retire.PlantsRetirement, created on the first storage pass
markers_backfilled = False  # map marker backfill done this run (needs Cartography)

while True:
    reset_all()
    clock = get_component("clock")
    power = get_component("power_control")

    if not version_mismatch():
        current_tick = now_tick()
        storage_due = (last_storage_tick == 0) or (current_tick - last_storage_tick >= STORAGE_TICK_INTERVAL)
        mixer_gate_due = (last_mixer_gate_tick == 0) or (current_tick - last_mixer_gate_tick >= MIXER_GATE_TICK_INTERVAL)

        supervise_grids_if_due(clock, power)

        if mixer_gate_due:
            last_mixer_gate_tick = current_tick
            try:
                if biomass_retirement is None and mixer_gate is None and power:
                    mixer_gate = MixerGate(power=power, clock=clock)
                if mixer_gate is not None and biomass_retirement is None:
                    mixer_gate.step(current_tick)
            except Exception as e:
                report_error("Mixer gate", e)

        between_steps(clock)

        if last_drill_tick == 0 or current_tick - last_drill_tick >= DRILL_TELEMETRY_TICK_INTERVAL:
            last_drill_tick = current_tick
            try:
                publish_all_drills()
            except Exception as e:
                report_error("Drill telemetry", e)

        park_if_due(clock, power)

        if storage_due:
            last_storage_tick = current_tick
            try:
                cash_manager.step(current_tick)
            except Exception as e:
                report_error("Cash manager", e)

            try:
                rebalance_inventory_to_warehouses()
            except Exception as e:
                report_error("Rebalance sweep", e)

            between_steps(clock)

            try:
                reclaim_inventory_only_items_from_warehouses()
            except Exception as e:
                report_error("Reclaim sweep", e)

            between_steps(clock)

            try:
                consolidate_storage_bins()
            except Exception as e:
                report_error("Bin consolidation", e)

            between_steps(clock)

            try:
                if not markers_backfilled and get_component("markers"):
                    markers_backfilled = True
                    update_unsupported_markers(clear_previous=True)
                    synced = outpost_mining.sync_mineral_site_markers()
                    print(f"[AUTOMATION] Map markers backfilled: {synced} mineral site(s).")
                    between_steps(clock)
                assigned = outpost_mining.assign_unassigned_sites()
                if assigned:
                    print(f"[AUTOMATION] Assigned {assigned} resource marker(s) to mining outposts.")
            except Exception as e:
                report_error("Resource markers", e)

            # The sweeps above interleave between_steps() and can span more
            # than REQUEST_STALE_TICKS, so steps that stamp archive entries
            # read the clock again instead of the pass's start tick.
            current_tick = clock.tick() if clock and hasattr(clock, "tick") else 0
            try:
                if biomass_retirement is None and biomass_complete():
                    biomass_retirement = BiomassRetirement(power=power)
                if biomass_retirement is not None:
                    biomass_retirement.step(current_tick)
            except Exception as e:
                report_error("Biomass retirement", e)

            try:
                reconcile_manual_transit()
                plan_sites()
            except Exception as e:
                report_error("Fab site plan", e)

            current_tick = clock.tick() if clock and hasattr(clock, "tick") else 0
            try:
                publish_site_requests(current_tick)
            except Exception as e:
                report_error("Site supply", e)

            try:
                network = get_component("outpost_network")
                home = next((o for o in network.outposts() if getattr(o, "is_home", False)), None) if network else None
                publish_home_salt_request(home, current_tick)
            except Exception as e:
                report_error("Home salt request", e)

            current_tick = clock.tick() if clock and hasattr(clock, "tick") else 0
            plants_summary = plants_retire.IDLE_SUMMARY
            try:
                if plants_retirement is None:
                    plants_retirement = plants_retire.PlantsRetirement()
                plants_summary = plants_retirement.step(current_tick)
            except Exception as e:
                report_error("Plants retirement", e)

            plan_wildlife_if_due()
            conflict_items = []
            try:
                conflict_items = [f"pipe conflict: {c}" for c in active_pipe_conflicts(current_tick)]
            except Exception as e:
                report_error("Pipe conflicts", e)
            try:
                gave_up = script_restart.gave_up_ids()
                if gave_up:
                    conflict_items.append(f"restart gave up: {', '.join(gave_up)}")
            except Exception as e:
                report_error("Script restarts", e)
            archive.set(AUTOMATION_SUMMARY_KEY, SUMMARY_SEPARATOR.join(card_items(conflict_items + [early_buyer.summary, plants_summary, wildlife_planner.state["summary"]])))
            errors.clear()

    flush_all()
    sleep(1.0)
