# Harvester base controller, layer 0 of FieldKeeperController (lib/field_keeper.py), its only subclass:
# the Harvester handle, grid math, position / heat / cells() reads, the held slot and collect().
# collect_at_current() rests through the heat model's cool_down() (lib/harvester_heat.py); nothing
# else here calls a mixin.

from typing import TYPE_CHECKING

from machine_controller import MachineController
from swallow import swallowed
from tree_console import TreeConsole


class HarvesterController(MachineController):
    """Base of FieldKeeperController: the Harvester's sensors, held slot and loose-item collect."""

    LABEL = "Harvester"
    LOG_MODULE = "harvesting"  # TreeConsole module; a subclass names its own
    POLL_S = 0.5
    ERROR_POLL_S = 5.0

    ROWS = "ABCDEFGH"
    NUM_ROWS = 8
    NUM_COLS = 24

    if TYPE_CHECKING:
        # Supplied by HarvesterHeatMixin (lib/harvester_heat.py); this class never runs without it.
        def cool_down(self, target_level=None) -> None: ...

    # Collect heat guard (Max heat is 100)
    HEAT_SAFE_CEILING = 75.0  # rest before a collect once heat is 10 above this
    HEAT_RESUME_LEVEL = 40.0  # cool_down() target (the heat model rests only as far as the next action needs)

    def __init__(self, harvester):
        self.harvester = harvester
        self.name = getattr(harvester, "id", "harvester_1")
        self.base_sector = self.detect_base_sector()
        self.log = TreeConsole(module=self.LOG_MODULE)

    @classmethod
    def rc_to_sector(cls, r, c):
        """Converts (row_idx, col_num) to sector string (e.g. 'E14')."""
        if 0 <= r < cls.NUM_ROWS and 1 <= c <= cls.NUM_COLS:
            return f"{cls.ROWS[r]}{c}"
        return None

    def detect_base_sector(self):
        """Determines the Harvester's depot pad / base sector (starts at depot)."""
        try:
            return self.harvester.get_position()
        except Exception as error:
            swallowed("harvesting.HarvesterController.detect_base_sector: self.harvester.get_position", error)
            return "E13"

    def get_position(self):
        """Returns current sector string."""
        try:
            return self.harvester.get_position()
        except Exception as error:
            swallowed("harvesting.HarvesterController.get_position: self.harvester.get_position", error)
            return self.base_sector

    def read_cells(self):
        """{sector: Cell} of the field (cells()); {} when unreadable."""
        try:
            return {c.id: c for c in self.harvester.cells()}
        except Exception as e:
            self.log.debug(f"[{self.name}] cells() failed: {e}")
            return {}

    def get_heat(self):
        """Returns current heat level (0-100)."""
        try:
            return self.harvester.get_heat()
        except Exception as error:
            swallowed("harvesting.HarvesterController.get_heat: self.harvester.get_heat", error)
            return 0.0

    def store_held_if_any(self):
        """Ensures the single held item slot is empty by storing into Inventory."""
        held = self.harvester.get_held()
        self.log.trace(f"[{self.name}] store_held_if_any: held slot={held!r}")
        if held and held != "":
            self.log.print(f"[{self.name}] Storing held item '{held}' into Inventory...")
            res = self.harvester.store()
            if res.status == "ok":
                self.log.print(f"[{self.name}] Successfully stored '{res.item_id}' to Inventory.")
                return True
            elif res.status == "inventory_full":
                self.log.level("warn").print(f"[{self.name}] WARNING: Base inventory full! Cannot store '{held}'.")
                try:
                    notify(f"[{self.name}] Base Inventory Full! Cannot store harvested items.", level="warn", duration_seconds=8.0)
                except Exception as error:
                    swallowed("harvesting.HarvesterController.store_held_if_any: notify", error)
                return False
            else:
                self.log.level("warn").print(f"[{self.name}] Store notice: {res.status} - {res.message}")
        return True

    def collect_at_current(self, store=True):
        """Picks up the item at current sector; stores it at once unless `store` is False (it stays held)."""
        # Free held slot if something was leftover
        self.store_held_if_any()

        # Check heat before collect: empty collect adds 9 heat
        if self.get_heat() >= (self.HEAT_SAFE_CEILING + 10.0):
            self.cool_down(self.HEAT_RESUME_LEVEL)

        res = self.harvester.collect()
        if res.status == "ok":
            item_name = getattr(res, "name", res.id)
            val = getattr(res, "value", 0)
            self.log.print(f"[{self.name}] Collected '{item_name}' (value: {val}) at {self.get_position()}.")
            if store:
                self.store_held_if_any()
            return True
        elif res.status == "empty":
            return False
        elif res.status == "overheated":
            self.cool_down(self.HEAT_RESUME_LEVEL)
            return self.collect_at_current(store)
        else:
            self.log.level("warn").print(f"[{self.name}] Collect notice: {res.status} - {res.message}")
            return False
