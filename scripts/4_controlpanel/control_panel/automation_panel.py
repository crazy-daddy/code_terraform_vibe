# ct-panel: automation_panel
# Control Room automation CALCULATOR -- headless, draws nothing. See
# status_panel.py for the actual STATUS/AUTOMATION card UI, which reads this
# script's results back out of `archive`.
#
# Split out because this game has no true background/daemon script type -- a
# Custom Panel is the only slot that can host an "always-on, not tied to one
# building" process, which is why Supply Dock planning (below) ended up here
# instead of on any one dock. But mixing that with UI rendering turned out to
# be fragile: a single iteration running long (e.g.
# supply_dock.plan_dock_assignments() churning through several orders, ~2-10s
# even after lib/production.py's SourceCache fix cut its cost down) wedges
# that Custom Panel's rendering permanently -- confirmed via temporary debug
# prints that the script kept looping and completing fine underneath
# (~100ms/iteration) the entire time the card stayed visually blank. There's
# no known threshold under which an occasional multi-second stall is safe for
# a script that also renders every tick, so the fix is structural: keep this
# process entirely headless (no panel.* calls at all) and publish its results
# to `archive` for status_panel.py to display instead of drawing them directly --
# same Archive-as-decoupling-channel pattern CLAUDE.md calls for when a
# result can't be produced by the component that has to display it.
#
# SLOT NUMBER: the game picks Custom Panel ids itself (ids only increment,
# cards can't be drag-reordered), so this file's live panel_N slot differs
# per save. devtools/scripts_sync.py pairs the slot with this file by the
# ct-panel marker on line 1 -- see docs/cheatsheet/panels.md §7.
#
# Responsibilities (see docs/AI_CHEATSHEET.md):
#   - Power Grid supervision (brownout load-shedding, day/night calibration)
#     for every grid, one PowerGridManager instance per grid, reused across
#     cycles so its day/night state persists.
#   - The Smelter Inventory->Warehouse rebalance sweep, once per cycle.
#   - Cross-warehouse stock consolidation, every outpost, once per cycle.
#   - Outpost-founding -> resource marker auto-reassignment
#     (lib/outpost_mining.py's reevaluate_unassigned_near_outpost()).
#   - Biomass Mixer duty-cycle gate (lib/biomass_mixer_gate.py), every
#     MIXER_GATE_TICK_INTERVAL (a paused Mixer can't wake itself, so an
#     always-on script must). Idles until a Mixer exists. The module lives in
#     the 5_steampower lib, but scripts_sync deploys new-only lib modules at
#     every tier from 2_libunlock on, so this one panel serves every tier.
#     Once biomass is complete (lib/biomass_retire.py) the gate stops and
#     BiomassRetirement switches the Liquifier/Mixer chain off instead.
#   - Supply Dock order-assignment planning across every discovered dock
#     (lib/supply_dock.py's plan_dock_assignments() -- the central "decider"
#     so multiple docks share/split Earth Orders instead of each redundantly
#     scanning the order board and independently guessing; see
#     docs/AI_CHEATSHEET.md #2a-0-5).
#   - Fleet hardware upgrades (lib/fleet_upgrade.py): Drone Depot and drone
#     chassis swaps to the best unlocked tier, one at a time, once per cycle.
#   - Fleet commissioning (lib/fleet_commission.py): buys or crafts, deploys
#     and fits the Pioneers and drones queued on the COMMISSION card, one job
#     of each kind at a time.
#   - Cash manager pass (lib/cash.py CashManager): balance history, income and
#     reagent burn, dynamic floor, ask queue with ETAs for the CASH card. Runs
#     first each storage pass so the consumers below see a fresh floor.
#   - Factory outposts (5_steampower libs, deployed at every tier like the
#     Mixer gate): lib/site_plan.py places each root Fabricator target at the
#     fab sites that build its tree, then lib/site_supply.py publishes the
#     ingots/ore/finished goods each outpost needs hauled in and evicts ore
#     stranded at an outpost that lost its Smelters.
# lib/solar.py's SolarController and lib/smelter.py's SmelterController no
# longer do any of this themselves -- it's a hard dependency on this script
# running (see legacy/README.md for pre-Control-Room saves). The manual
# "Clean Archive"/"Sync Unsupported"/"Confirm New Version" buttons live on
# status_panel.py instead -- they're rare, user-triggered one-offs, not the
# chronic per-cycle cost that forced this script headless.

from archive import archive
from power import PowerGridManager
from biomass_mixer_gate import MixerGate
from biomass_retire import BiomassRetirement, biomass_complete
from storage import rebalance_inventory_to_warehouses, consolidate_cross_warehouse_stock, reclaim_inventory_only_items_from_warehouses
from version_guard import version_mismatch
import outpost_mining
import supply_dock
from fleet_upgrade import FleetUpgradeCoordinator
from fleet_commission import FleetCommissionCoordinator
from cash import CashManager
from site_supply import publish_site_requests
from site_plan import plan_sites
from mining_drill import publish_all_drills
from script_parking import ScriptParking
from tree_console import flush_all

OUTPOST_KNOWN_IDS_KEY = "outposts.known_ids"

# Published each time the storage-tick automation runs; status_panel.py reads this
# to display the "ALWAYS-ON" line instead of computing it itself. Left
# untouched (not overwritten) while version_mismatch() halts automation below,
# same as the old combined script did -- status_panel.py shows its own fixed
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
# Script parking pass (lib/script_parking.py): parks idle machines, wakes them, stops solar at night.
PARKING_TICK_INTERVAL = 50

grid_managers = {}          # {anchor_id: PowerGridManager}, reused so day/night state persists
last_solar_tick = 0
last_storage_tick = 0
last_mixer_gate_tick = 0
last_drill_tick = 0
last_parking_tick = 0
parking = None              # ScriptParking, created once power_control is available
parking_summary = ["nothing parked"]  # one automation card item per parked kind
drill_summary = "no drills"
# count = docks assigned by the last plan; signature = plan_signature() at that plan; plan_tick = its tick
dock_plan = {"last_tick": 0, "count": 0, "signature": None, "plan_tick": 0}


def plan_docks_if_due(clock):
    """
    Every DOCK_PLAN_TICK_INTERVAL: runs supply_dock.plan_dock_assignments() when
    supply_dock.plan_signature() differs from the last plan's, or
    DOCK_PLAN_MAX_TICK_INTERVAL has passed since it.
    """
    now = clock.tick() if clock and hasattr(clock, "tick") else 0
    if dock_plan["last_tick"] != 0 and now - dock_plan["last_tick"] < DOCK_PLAN_TICK_INTERVAL:
        return
    dock_plan["last_tick"] = now
    try:
        signature = supply_dock.plan_signature()
        if signature == dock_plan["signature"] and now - dock_plan["plan_tick"] < DOCK_PLAN_MAX_TICK_INTERVAL:
            return
        plan = supply_dock.plan_dock_assignments(clock=clock)
        dock_plan["count"] = sum(1 for v in plan.values() if v)
        dock_plan["signature"] = signature
        dock_plan["plan_tick"] = now
    except Exception as e:
        print(f"[AUTOMATION] Supply Dock planning error: {e}")

mixer_gate = None           # MixerGate, created lazily once power_control is available
mixer_gate_summary = "no Mixers"
biomass_retirement = None   # BiomassRetirement, created once biomass is complete
grid_count = 0              # last solar-sync grid census; carries over on ticks solar_due is False
fleet_upgrader = FleetUpgradeCoordinator()  # stateless between cycles (state lives in archive)
fleet_commissioner = FleetCommissionCoordinator()  # same
cash_manager = CashManager()  # same

while True:
    clock = get_component("clock")
    power = get_component("power_control")

    if not version_mismatch():
        current_tick = clock.tick() if clock and hasattr(clock, "tick") else 0
        solar_due = (last_solar_tick == 0) or (current_tick - last_solar_tick >= SOLAR_TICK_INTERVAL)
        storage_due = (last_storage_tick == 0) or (current_tick - last_storage_tick >= STORAGE_TICK_INTERVAL)
        mixer_gate_due = (last_mixer_gate_tick == 0) or (current_tick - last_mixer_gate_tick >= MIXER_GATE_TICK_INTERVAL)

        if solar_due:
            last_solar_tick = current_tick
            grid_count = 0
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
                    grid_count += 1

                # Grids that stopped being reported (merged into another via a new
                # power line) -- release anything they still had shed rather than
                # stranding it forever (see PowerGridManager.release_all()).
                for stale_anchor in list(grid_managers.keys()):
                    if stale_anchor not in current_anchors:
                        grid_managers[stale_anchor].release_all()
                        del grid_managers[stale_anchor]
            except Exception as e:
                print(f"[AUTOMATION] Grid supervision error: {e}")

        if mixer_gate_due:
            last_mixer_gate_tick = current_tick
            try:
                if biomass_retirement is None and mixer_gate is None and power:
                    mixer_gate = MixerGate(power=power, clock=clock)
                if mixer_gate is not None and biomass_retirement is None:
                    gate_states = mixer_gate.step(current_tick)
                    if gate_states:
                        paused = sum(1 for st in gate_states.values() if st.get("state") == "pause")
                        mixer_gate_summary = f"{len(gate_states)} Mixer(s) ({paused} paused)"
            except Exception as e:
                print(f"[AUTOMATION] Mixer gate error: {e}")

        plan_docks_if_due(clock)

        if last_drill_tick == 0 or current_tick - last_drill_tick >= DRILL_TELEMETRY_TICK_INTERVAL:
            last_drill_tick = current_tick
            try:
                drill_count = publish_all_drills()
                drill_summary = f"{drill_count} drill(s) reported" if drill_count else "no drills"
            except Exception as e:
                print(f"[AUTOMATION] Drill telemetry error: {e}")

        if last_parking_tick == 0 or current_tick - last_parking_tick >= PARKING_TICK_INTERVAL:
            last_parking_tick = current_tick
            try:
                if parking is None and power:
                    parking = ScriptParking(power=power, clock=clock)
                if parking is not None:
                    parking_summary = parking.step(
                        power.grids() if hasattr(power, "grids") else [],
                        clock.get_elevation() if clock and hasattr(clock, "get_elevation") else None,
                        archive.get(supply_dock.ORDER_PLAN_ARCHIVE_KEY, {}) or {},
                    )
            except Exception as e:
                print(f"[AUTOMATION] Script parking error: {e}")

        if storage_due:
            last_storage_tick = current_tick
            cash_summary = "cash idle"
            try:
                cash_summary = cash_manager.step(current_tick)
            except Exception as e:
                print(f"[AUTOMATION] Cash manager error: {e}")

            try:
                rebalance_inventory_to_warehouses()
            except Exception as e:
                print(f"[AUTOMATION] Rebalance sweep error: {e}")

            plan_docks_if_due(clock)

            try:
                reclaim_inventory_only_items_from_warehouses()
            except Exception as e:
                print(f"[AUTOMATION] Reclaim sweep error: {e}")

            plan_docks_if_due(clock)

            outpost_new_count = 0
            try:
                network = get_component("outpost_network")
                if network and hasattr(network, "outposts"):
                    outposts = network.outposts()
                    current_ids = {getattr(o, "id", None) for o in outposts}
                    current_ids.discard(None)
                    known_ids = set(archive.get(OUTPOST_KNOWN_IDS_KEY, []) or [])
                    new_ids = current_ids - known_ids
                    for new_id in new_ids:
                        assigned = outpost_mining.reevaluate_unassigned_near_outpost(new_id)
                        print(f"[AUTOMATION] New outpost '{new_id}' detected -- assigned {assigned} nearby resource marker(s).")
                        outpost_new_count += 1
                    if current_ids != known_ids:
                        archive.set(OUTPOST_KNOWN_IDS_KEY, sorted(current_ids))

                    # Cross-warehouse consolidation sweep (storage.py's
                    # consolidate_cross_warehouse_stock(), which calls
                    # .compact()) -- every outpost, not just home, since a
                    # remote outpost's Warehouses (e.g. a Bio Lab reagent drop)
                    # can end up with the same item split across multiple
                    # Warehouse buildings the same way repeat hauler deliveries
                    # can at home.
                    for o in outposts:
                        o_id = getattr(o, "id", "?")
                        try:
                            consolidate_cross_warehouse_stock(o)
                        except Exception as e:
                            print(f"[AUTOMATION] Cross-warehouse consolidation error at '{o_id}': {e}")
                        plan_docks_if_due(clock)
            except Exception as e:
                print(f"[AUTOMATION] Outpost sync error: {e}")

            try:
                if biomass_retirement is None and biomass_complete():
                    biomass_retirement = BiomassRetirement(power=power)
                if biomass_retirement is not None:
                    mixer_gate_summary = biomass_retirement.step(current_tick)
            except Exception as e:
                print(f"[AUTOMATION] Biomass retirement error: {e}")

            try:
                plan_sites()
            except Exception as e:
                print(f"[AUTOMATION] Fab site plan error: {e}")

            site_count = 0
            try:
                site_count = sum(1 for wants in publish_site_requests(current_tick).values() if wants)
            except Exception as e:
                print(f"[AUTOMATION] Site supply error: {e}")

            upgrade_summary = "fleet upgrade idle"
            try:
                upgrade_summary = fleet_upgrader.step(current_tick)
            except Exception as e:
                print(f"[AUTOMATION] Fleet upgrade error: {e}")

            commission_summary = "commission idle"
            try:
                commission_summary = fleet_commissioner.step(current_tick)
            except Exception as e:
                print(f"[AUTOMATION] Fleet commission error: {e}")

            archive.set(AUTOMATION_SUMMARY_KEY, SUMMARY_SEPARATOR.join([
                f"{grid_count} grid(s) supervised", "rebalance swept", f"{outpost_new_count} new outpost(s)",
                f"{dock_plan['count']} dock(s) assigned", f"{site_count} supply site(s)", str(upgrade_summary),
                str(commission_summary), str(cash_summary), str(mixer_gate_summary), drill_summary, *parking_summary,
            ]))

    flush_all()
    sleep(1.0)
