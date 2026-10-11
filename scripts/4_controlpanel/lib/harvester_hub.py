# Harvester mixin, layer 0: the controller hub every other harvester mixin calls back into.
# Composed by FieldKeeperController (lib/field_keeper.py).
#
#   act()          -- a Harvester action with heat-aware rest and busy/overheated retries
#   stage()        -- pull an item from a home Warehouse into Inventory
#   stock_count()  -- home stock, memoised per step
#   read_cells()   -- cells() keyed by sector
#
# Owns the per-step memo `stock_memo` and the staging state `stage_busy` / `busy_since`;
# init_hub() is their only initialiser, reset_step_memo() clears the memo at the start of a step
# (FieldKeeperController.prepare_pass() hands the new memo to the FieldPass as `stock`).
# Calls only the heat model (harvester_heat) and HarvesterController, never another ability mixin.

from typing import TYPE_CHECKING

from game_clock import now_tick
from storage import discover_storage_buildings, inventory_count, mark_busy, recently_busy, total_stock
from swallow import swallowed
from tree_console import flush_all

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

ACTION_RETRIES = 3  # busy/moving retries per Harvester action
STAGE_STUCK_WARN_TICKS = 6000  # a Warehouse answering "busy" to staging this long (~10 min) gets one warning


class HarvesterHubMixin:
    """Staging, stock reads and acting for the harvester ability mixins."""

    @property
    def _host(self) -> "FieldKeeperController":
        return self  # type: ignore[return-value]

    def init_hub(self):
        """Sets the hub's state; called once from the controller's __init__."""
        self.stock_memo = {}  # {item id: home stock}, per step
        self.stage_busy = False  # last failed stage(): every holder answered "busy"
        self.busy_since = {}  # {warehouse id: [first "busy" tick, warned]}, cleared on a non-busy answer

    def reset_step_memo(self):
        """Drops the per-step stock memo; called at the start of each step. Returns the new memo (FieldPass.stock)."""
        self._host.stock_memo = {}
        return self._host.stock_memo

    def inventory_count(self, item_id):
        return inventory_count(item_id)

    def stock_count(self, item_id):
        """
        Home stock of item_id (Inventory + home Warehouses), memoised per
        step: each total_stock() walks every Warehouse, and one step asks for
        up to 24 seeds, which burned the script's per-tick step budget.
        """
        found = self._host.stock_memo.get(item_id)
        if found is None:
            found = total_stock(item_id)
            self._host.stock_memo[item_id] = found
        return found

    def stage(self, item_id, n=1):
        """
        Pulls item_id from a home Warehouse into Inventory until n are there.
        Seeds and salt are kept in Warehouses so they don't clutter Inventory,
        but load_seed()/dispense_salt()/amplify() read Inventory only, so each
        is staged right before use. The rebalance sweep may move a leftover
        back later. Warehouses that just answered "busy" (an Auto Feeder
        cycle) are tried last. On failure, self._host.stage_busy is True when every
        holder answered "busy" (a short wait fixes it); a Warehouse busy for
        STAGE_STUCK_WARN_TICKS gets one warning.
        """
        self._host.log.start(f"[{self._host.name}] stage", level="debug")
        self._host.stage_busy = False
        missing = n - self._host.inventory_count(item_id)
        if missing <= 0:
            self._host.log.end()
            return True
        self._host.stock_memo.pop(item_id, None)
        now = now_tick()
        holders = []
        for building in discover_storage_buildings():
            try:
                if building["component"].count(item_id) > 0:
                    holders.append(building)
            except Exception as error:
                swallowed("harvester_hub.HarvesterHubMixin.stage: component.count", error)
        holders.sort(key=lambda b: 1 if recently_busy(b["id"], now) else 0)
        answers = []
        for building in holders:
            try:
                res = building["component"].transfer_to("inventory", item_id, missing)
            except Exception as error:
                swallowed("harvester_hub.HarvesterHubMixin.stage: component.transfer_to", error)
                answers.append("error")
                continue
            status = getattr(res, "status", "")
            answers.append(status)
            self._host.note_busy(building["id"], status == "busy", now)
            self._host.log.debug(f"stage '{item_id}' from '{building['id']}': {status}, moved {getattr(res, 'moved', 0) or 0}.")
            missing -= getattr(res, "moved", 0) or 0
            if missing <= 0:
                self._host.log.debug(f"Staged {n}x '{item_id}' into Inventory.")
                self._host.log.end()
                return True
        self._host.stage_busy = bool(answers) and all(a == "busy" for a in answers)
        self._host.log.debug(f"Could not stage '{item_id}': {missing} short ({'all holders busy' if self._host.stage_busy else 'answers ' + str(answers or 'none: no Warehouse holds it')}).")
        self._host.log.end()
        return False

    def note_busy(self, building_id, busy, now):
        """Tracks how long building_id has answered "busy"; warns once past STAGE_STUCK_WARN_TICKS."""
        if not busy:
            self._host.busy_since.pop(building_id, None)
            return
        mark_busy(building_id, now)
        entry = self._host.busy_since.setdefault(building_id, [now, False])
        if not entry[1] and now - entry[0] >= STAGE_STUCK_WARN_TICKS:
            entry[1] = True
            self._host.log.level("warn").print(f"[{self._host.name}] Warehouse '{building_id}' busy for {self._host.game_time(now - entry[0])}: Auto Feeder stuck? Staging skips it while it stays busy.")

    def act(self, method, *args):
        """
        Calls a Harvester action: rests first if its (learned) heat cost would
        cross the cap, measures that cost on success, cools on "overheated"
        and retries "busy"/"moving".
        """
        fn = getattr(self._host.harvester, method, None)
        if fn is None:
            return None
        self._host.log.start(f"[{self._host.name}] {method}", level="debug")
        where = self._host.get_position()
        res = None
        for _ in range(ACTION_RETRIES):
            self._host.ensure_headroom(self._host.action_cost(method))
            before = self._host.get_heat()
            start_tick = now_tick()
            res = fn(*args)
            status = getattr(res, "status", "")
            took = self._host.game_time(now_tick() - start_tick)
            if status in ("ok", "partial", "dropped"):
                after = self._host.get_heat()
                self._host.learn_action(method, before, after)
                self._host.log.debug(f"at {where} -> {status} after {took}, heat {before:.1f} -> {after:.1f}.")
                self._host.log.end()
                return res
            self._host.log.debug(f"at {where} -> {status} after {took}: {getattr(res, 'message', '')}")
            if status == "overheated":
                self._host.cool_down()
            elif status in ("busy", "moving"):
                flush_all()
                sleep(1.0)
            else:
                self._host.log.end()
                return res
        self._host.log.end()
        return res

    def read_cells(self):
        try:
            return {c.id: c for c in self._host.harvester.cells()}
        except Exception as e:
            self._host.log.debug(f"[{self._host.name}] cells() failed: {e}")
            return {}
