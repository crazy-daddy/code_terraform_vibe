# ct-panel: warehouse_upgrade_panel
# Warehouse upgrade WORKER -- headless, draws nothing. Runs
# lib/warehouse_upgrade.py: replaces pairs of Warehouses with one Large
# Warehouse (buy, deploy, greedy drain, undeploy, sell). See that module's
# docstring and docs/AI_CHEATSHEET.md §2k-1.
#
# Its own Custom Panel because the drain blocks for tens of game minutes
# (a Warehouse feeder moves ~2.5 ticks/unit) and automation_panel.py's grid
# supervision can't wait that long. Idles cheaply between swaps.
#
# Shares drones_panel.py's fleet auto-upgrade switch (fleet.upgrade["enabled"]);
# its status line is fleet.upgrade["warehouse_status"].
#
# New save: create an empty Custom Panel in-game -- see docs/cheatsheet/panels.md §7.

from version_guard import version_mismatch
from warehouse_upgrade import WarehouseUpgrader

# Seconds between passes while nothing is being drained.
IDLE_SLEEP_S = 3.0

upgrader = WarehouseUpgrader()

while True:
    if not version_mismatch():
        try:
            upgrader.step()
        except Exception as e:
            print(f"[WAREHOUSE] Upgrade error: {e}")
    sleep(IDLE_SLEEP_S)
