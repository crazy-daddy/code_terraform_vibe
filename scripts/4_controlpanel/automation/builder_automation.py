# ct-automation: builder_automation
# BUILDER -- an Automation (Computer > Automations), draws nothing. Everything
# that buys, deploys, upgrades or removes hardware, one step after the other
# each pass, so purchases never race each other past the cash floor:
#   - Fleet commissioning (lib/fleet_commission.py): buys or crafts, deploys
#     and fits the Pioneers and drones queued on the FLEET card's Commission
#     tab, one job of each kind at a time. Every pass while the head job is in
#     a quick state (fleet_commission.commission_fast()), else every
#     FLEET_TICK_INTERVAL.
#   - Fleet decommissioning (lib/fleet_decommission.py): undeploys the
#     Pioneers and drones retired from the FLEET card once they are home and
#     empty; sells a Pioneer's parts. Every FLEET_TICK_INTERVAL.
#   - Fleet hardware upgrades (lib/fleet_upgrade.py): Drone Depot and drone
#     chassis swaps to the best unlocked tier, one at a time. Every
#     FLEET_TICK_INTERVAL.
#   - Pillar swap (lib/pillar_swap.py): the PRODUCTION card's generator swap.
#   - Storage swaps: Storage Bins -> Warehouse and Warehouse pairs -> Large
#     Warehouse (lib/warehouse_upgrade.py, §2k-1), Liquid Tanks -> Large Liquid
#     Tank (lib/tank_upgrade.py, §2k-3).
#
# The fleet steps run first; the storage swaps get the rest of the pass. A
# Warehouse drain runs at most warehouse_upgrade.DRAIN_PASS_TICKS per pass, and
# the bin and Warehouse swaps sit out every pass in which a commission job is
# in a quick state, so a queued Pioneer or drone never waits on a drain.
#
# Not here: the early build order (lib/early_buyer.py) stays in
# orchestrator_automation.py, which also runs the cash manager every ~10 s.
# Summary for status_panel.py's AUTOMATION card: BUILDER_SUMMARY_KEY, only
# the parts that need the operator.
#
# New save: create an empty Automation in-game -- see docs/cheatsheet/panels.md §7.

from archive import archive
from version_guard import version_mismatch
from fleet_upgrade import FleetUpgradeCoordinator
from fleet_commission import FleetCommissionCoordinator, commission_fast
from fleet_decommission import FleetDecommissionCoordinator
from pillar_swap import PillarSwap
import pillar_swap
from warehouse_upgrade import WarehouseUpgrader, BinUpgrader
from tank_upgrade import TankUpgrader
from game_clock import now_tick
from tree_console import flush_all, reset_all

# Joined summary parts for status_panel.py; "" when nothing needs the operator.
BUILDER_SUMMARY_KEY = "builder.summary"
SUMMARY_SEPARATOR = " | "  # must match status_panel.py
# Summaries that mean "nothing for the operator to see"; left off the card.
IDLE_SUMMARIES = ("commission idle", "decommission idle", "fleet upgrade off", "fleet upgrade: waiting for mining drills",
                  "upgrade: fleet up to date", "fleet upgrade idle", pillar_swap.IDLE_SUMMARY)
# Ticks between fleet coordinator passes (~10 s); commission also runs every
# pass while its head job is quick.
FLEET_TICK_INTERVAL = 100
# Seconds between passes while a commission job is quick / otherwise.
FAST_SLEEP_S = 1.0
IDLE_SLEEP_S = 3.0

fleet_upgrader = FleetUpgradeCoordinator()
fleet_commissioner = FleetCommissionCoordinator()
fleet_decommissioner = FleetDecommissionCoordinator()
pillar_swapper = PillarSwap()
bin_upgrader = BinUpgrader()
upgrader = WarehouseUpgrader()
tank_upgrader = TankUpgrader()

summaries = {"upgrade": "fleet upgrade idle", "commission": "commission idle", "decommission": "decommission idle"}
last_fleet_tick = 0
last_summary = None
errors = []


def report_error(what, error):
    """Prints a failed step and keeps it for the next summary."""
    print(f"[BUILDER] {what} error: {error}")
    if f"{what} error" not in errors:
        errors.append(f"{what} error")


def run_step(what, fn, fallback):
    """fn()'s result, or fallback after report_error()."""
    try:
        return fn()
    except Exception as e:
        report_error(what, e)
        return fallback


while True:
    reset_all()
    fast = False
    if not version_mismatch():
        now = now_tick()
        fleet_due = last_fleet_tick == 0 or now - last_fleet_tick >= FLEET_TICK_INTERVAL
        fast = run_step("Fleet commission check", commission_fast, False)
        if fleet_due or fast:
            summaries["commission"] = run_step("Fleet commission", lambda: fleet_commissioner.step(now), "commission idle")
        if fleet_due:
            last_fleet_tick = now
            summaries["decommission"] = run_step("Fleet decommission", lambda: fleet_decommissioner.step(now), "decommission idle")
            summaries["upgrade"] = run_step("Fleet upgrade", lambda: fleet_upgrader.step(now), "fleet upgrade idle")
        swap_summary = run_step("Pillar swap", pillar_swapper.step, pillar_swap.IDLE_SUMMARY)
        fast = fast or run_step("Fleet commission check", commission_fast, False)
        if not fast:
            run_step("Bin upgrade", bin_upgrader.step, "")
            run_step("Warehouse upgrade", upgrader.step, "")
        run_step("Tank upgrade", tank_upgrader.step, "")
        parts = errors + [str(s) for s in (summaries["commission"], summaries["decommission"], summaries["upgrade"], swap_summary) if s not in IDLE_SUMMARIES]
        summary = SUMMARY_SEPARATOR.join(parts)
        if summary != last_summary:
            archive.set(BUILDER_SUMMARY_KEY, summary)
            last_summary = summary
        errors.clear()
    flush_all()
    sleep(FAST_SLEEP_S if fast else IDLE_SLEEP_S)
