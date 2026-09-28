# ct-panel: warehouse_upgrade_panel
# Warehouse + Liquid Tank upgrade WORKER -- headless, draws nothing. Runs
# lib/warehouse_upgrade.py (pairs of Warehouses -> one Large Warehouse: buy,
# deploy, greedy drain, undeploy, sell) and lib/tank_upgrade.py (up to 5 Liquid
# Tanks of one liquid -> one Large Liquid Tank, non-blocking drain). See those
# modules' docstrings and docs/AI_CHEATSHEET.md §2k-1/§2k-3. Both run in this
# one loop, one after the other, so they never spend past the shared credit
# reserve at the same time; a Warehouse drain delays the tank step meanwhile.
#
# Its own Custom Panel because the drain blocks for tens of game minutes
# (a Warehouse feeder moves ~2.5 ticks/unit) and automation_panel.py's grid
# supervision can't wait that long. Idles cheaply between swaps.
#
# Shares drones_panel.py's fleet auto-upgrade switch (fleet.upgrade["enabled"]);
# status lines are fleet.upgrade["warehouse_status"] / ["tank_status"].
#
# New save: create an empty Custom Panel in-game -- see docs/cheatsheet/panels.md §7.

from version_guard import version_mismatch
from warehouse_upgrade import WarehouseUpgrader
from tank_upgrade import TankUpgrader

# Seconds between passes while nothing is being drained.
IDLE_SLEEP_S = 3.0

upgrader = WarehouseUpgrader()
tank_upgrader = TankUpgrader()

while True:
    if not version_mismatch():
        try:
            upgrader.step()
        except Exception as e:
            print(f"[WAREHOUSE] Upgrade error: {e}")
        try:
            tank_upgrader.step()
        except Exception as e:
            print(f"[TANK] Upgrade error: {e}")
    sleep(IDLE_SLEEP_S)
