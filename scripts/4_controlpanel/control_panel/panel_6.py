# Warehouse upgrade WORKER -- headless, draws nothing. Runs
# lib/warehouse_upgrade.py: replaces pairs of Warehouses with one Large
# Warehouse (buy, deploy, greedy drain, undeploy, sell). See that module's
# docstring and docs/AI_CHEATSHEET.md §2k-1.
#
# Its own Custom Panel because the drain blocks for tens of game minutes
# (a Warehouse feeder moves ~2.5 ticks/unit) and panel_4.py's grid
# supervision can't wait that long. Idles cheaply between swaps.
#
# Shares panel_5.py's fleet auto-upgrade switch (fleet.upgrade["enabled"]);
# its status line is fleet.upgrade["warehouse_status"].
#
# NOTE: a NEW Custom Panel, not yet placed in the live Control Room. The
# operator creates it in-game and points the empty slot at this file with
# devtools/scripts_sync.py's unmatched-file synctool-fill marker, same as
# panel_5.py (see docs/AI_CHEATSHEET.md #-7 for the numbering caveat).

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
