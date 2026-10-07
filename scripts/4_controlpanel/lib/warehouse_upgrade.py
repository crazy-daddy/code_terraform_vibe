# Warehouse -> Large Warehouse upgrade (Phase 7, next to lib/fleet_upgrade.py),
# run from its own Automation (automation/warehouse_upgrade_automation.py).
#
# Same gate as the fleet upgrade (drone_upgrade.upgrades_active(): FLEET card
# auto-upgrade switch on AND mining-drill phase reached), plus the Large Warehouse research
# and the cash manager's go-ahead (lib/cash.py can_spend("warehouse_upgrade")).
#
# One swap at a time, network-wide. A swap replaces TWO Warehouses at the same
# outpost with ONE Large Warehouse (10 slots -> 15, 20k -> 30k units): more
# storage without doubling the buildings every Auto Feeder consumer walks.
# The outpost with the most plain Warehouses goes first; there, the two
# emptiest. A lone leftover Warehouse at an outpost is kept.
#
# Swap states and buy/deploy/sell steps: lib/building_swap_upgrade.py
# (fleet.upgrade["warehouse_swap"]).
#   draining  -> greedy drain: each old Warehouse is emptied with back-to-back
#                transfer_to() calls into the new one, then undeployed in the
#                same breath and its kit sold. While the drain runs, the old
#                Warehouse's feeder is busy nearly all the time, so every other
#                consumer's take_item()/unload already falls through to another
#                store ("busy" handling) -- no retiring-Warehouse blacklist that
#                every storage caller would have to check. Anything that still
#                slips in between two transfers is drained on the next pass;
#                undeploy() refuses ("cargo_present") while anything is left.
#
# Why not control_room_automation.py: a Warehouse feeder moves ~2.5 ticks/unit
# (docs/AI_CHEATSHEET.md §2c), so draining two full Warehouses blocks for tens
# of game minutes. control_room_automation.py's grid supervision can't wait that long, and
# Warehouses have no script slot of their own.

from building_swap_upgrade import BuildingSwapUpgrader, TRANSIENT_UNDEPLOY_STATUSES
from tree_console import flush_all, method_block
from swallow import swallowed
import cash

SMALL_TYPE_ID = "warehouse"
LARGE_TYPE_ID = "large_warehouse"      # also the Shop/Inventory kit id
SWAP_RATIO = 2                         # Warehouses retired per Large Warehouse
# Units per transfer_to() call. A whole 2000-unit slot would block ~8 game
# minutes with no status update; this keeps the old Warehouse just as busy
# (calls run back to back) while the loop can still log and notice cargo_present.
DRAIN_CHUNK_UNITS = 500
# A "busy" source/target (another consumer won the race): wait this long, retry.
BUSY_RETRY_S = 0.2
# Drain passes in one step that moved nothing before giving the step back.
DRAIN_MAX_IDLE_PASSES = 5
# "busy"/"changed" answers in a row on one chunk before that stack is skipped
# for this pass (keeps a stuck feeder from spinning the loop forever).
MAX_BUSY_RETRIES = 50


class WarehouseUpgrader(BuildingSwapUpgrader):
    """Warehouse pair -> Large Warehouse swap. One instance, reused across cycles."""

    MODULE = "warehouse_upgrade"
    SMALL_TYPE_ID = SMALL_TYPE_ID
    LARGE_TYPE_ID = LARGE_TYPE_ID
    LARGE_RESEARCH_ID = "research_high_bay_warehousing"
    LARGE_PRICE_FALLBACK = 60000           # docs/database/equipment_production.md
    CASH_CONSUMER = "warehouse_upgrade"
    SWAP_KEY = "warehouse_swap"
    STATUS_KEY = "warehouse_status"
    SMALL_NAME = "Warehouse"
    LARGE_NAME = "Large Warehouse"
    UP_TO_DATE = "warehouses up to date"

    def _total(self, building_id):
        wh = self._component(building_id)
        try:
            return int(wh.total()) if wh else 0
        except Exception as error:
            swallowed("warehouse_upgrade.WarehouseUpgrader._total: wh.total", error)
            return 0

    # ------------------------------------------------------------ selection

    def _start_next(self):
        self.log.start("[warehouse_upgrade] _start_next", level="debug")
        candidates = []
        for outpost in self._outposts():
            smalls = self._ids_of(outpost, SMALL_TYPE_ID)
            if len(smalls) >= SWAP_RATIO:
                candidates.append((-len(smalls), getattr(outpost, "id", ""), smalls))
        if not candidates:
            cash.release(self.CASH_CONSUMER)
            self.log.end()
            return None
        candidates.sort()
        _, outpost_id, smalls = candidates[0]
        self.log.debug(f"Outposts with >= {SWAP_RATIO} Warehouses: {[(c[1], -c[0]) for c in candidates]}; picked '{outpost_id}'.")

        pairs = sum(-c[0] // SWAP_RATIO for c in candidates)
        if not self._can_buy(outpost_id, pairs):
            _ret = f"saving up ({self._credits()}/{self._price()} cr)"
            self.log.end()
            return _ret

        fills = sorted((self._total(w), w) for w in smalls)
        old_ids = [w for _, w in fills[:SWAP_RATIO]]
        self.log.debug(f"Fill at '{outpost_id}': {fills}; retiring the emptiest {old_ids}.")
        self._begin(outpost_id, old_ids)
        self.log.print(f"[warehouse_upgrade] '{outpost_id}': replacing {old_ids} with one Large Warehouse.")
        self.log.end()
        return f"{outpost_id}: buying Large Warehouse"

    # ------------------------------------------------------------ drain

    def _drain(self, swap, computer: "Computer"):
        outpost_id = swap.get("outpost")
        new_id = swap.get("new_id")
        self._sell_kits()
        for old_id in swap.get("old_ids") or []:
            if old_id in (swap.get("removed") or []):
                continue
            text = self._drain_and_remove(old_id, new_id, outpost_id, computer)
            if text:
                return text
            swap = self._swap() or swap
        self._sell_kits()
        if int((self._swap() or {}).get("to_sell") or 0) > 0:
            return f"{outpost_id}: selling old Warehouse kits"
        self._clear()
        self.log.print(f"[warehouse_upgrade] Swap done at '{outpost_id}': {swap.get('old_ids')} -> '{new_id}'.")
        return f"{outpost_id}: {swap.get('old_ids')} -> {new_id} done"

    def _drain_and_remove(self, old_id, new_id, outpost_id, computer: "Computer"):
        """Greedy drain + undeploy of one old Warehouse. None once it is gone, else a status line."""
        self.log.start(f"[warehouse_upgrade] Draining '{old_id}' ({self._total(old_id)} units) into '{new_id}'")
        moved = [0]
        result = self._drain_loop(old_id, new_id, outpost_id, computer, moved)
        self.log.end(f"[warehouse_upgrade] '{old_id}': {moved[0]} unit(s) moved this pass")
        return result

    @method_block("[warehouse_upgrade] _drain_loop")
    def _drain_loop(self, old_id, new_id, outpost_id, computer: "Computer", moved):
        """Drain loop of _drain_and_remove(); moved[0] accumulates the units moved."""
        idle_passes = 0
        while True:
            old = self._component(old_id)
            stacks = []
            if old is not None:
                try:
                    stacks = old.stacks()
                except Exception as error:
                    swallowed("warehouse_upgrade.WarehouseUpgrader._drain_loop: old.stacks", error)
                    self.log.debug(f"'{old_id}'.stacks() raised {error}; trying undeploy.")

            if not stacks:
                res = computer.undeploy(old_id)
                if res.status in ("ok", "not_found"):
                    self._mark_removed(old_id, res.status)
                    self._sell_kits()
                    self.log.print(f"[warehouse_upgrade] '{old_id}' empty ({moved[0]} unit(s) moved) and undeployed.")
                    return None
                self.log.debug(f"undeploy('{old_id}'): {res.status} - {res.message}")
                if res.status in TRANSIENT_UNDEPLOY_STATUSES:
                    return f"{old_id}: empty, waiting for Inventory room to take its kit back ({res.status})"
                if res.status == "cargo_present":
                    idle_passes += 1
                    if idle_passes < DRAIN_MAX_IDLE_PASSES:
                        self.log.debug(f"'{old_id}': something slipped in before undeploy; draining again.")
                        continue
                return self._refused(f"undeploy('{old_id}')", res, outpost_id)

            moved_pass = 0
            for stack in stacks:
                moved_pass += self._move_stack(old, old_id, new_id, outpost_id, stack)
            moved[0] += moved_pass
            if moved_pass:
                idle_passes = 0
                continue
            idle_passes += 1
            if idle_passes >= DRAIN_MAX_IDLE_PASSES:
                left = self._total(old_id)
                self.log.level("warn").print(f"[warehouse_upgrade] '{old_id}': {left} unit(s) left and nowhere to move them; retrying later.")
                return f"{old_id}: stuck with {left} unit(s)"
            flush_all()
            sleep(BUSY_RETRY_S)

    def _move_stack(self, old, old_id, new_id, outpost_id, stack):
        """Moves one stack out of old in DRAIN_CHUNK_UNITS calls. Returns units moved."""
        self.log.start("[warehouse_upgrade] _move_stack", level="debug")
        moved = 0
        busy = 0
        remaining = int(getattr(stack, "count", 0) or 0)
        props = getattr(stack, "properties", None)
        while remaining > 0:
            target = self._target_for(stack.id, props, new_id, old_id, outpost_id)
            if target is None:
                self.log.debug(f"No room anywhere at '{outpost_id}' for {remaining}x {stack.id}.")
                self.log.end()
                return moved
            res = old.transfer_to(target, stack.id, min(remaining, DRAIN_CHUNK_UNITS), properties=props, property_match="exact")
            got = int(getattr(res, "moved", 0) or 0) if res.status in ("ok", "partial") else 0
            if got:
                moved += got
                remaining -= got
                busy = 0
                self.log.debug(f"{got}x {stack.id} '{old_id}' -> '{target}' ({remaining} left in this stack).")
                continue
            if res.status in ("busy", "source_changed", "target_changed", "target_under_construction"):
                busy += 1
                if busy >= MAX_BUSY_RETRIES:
                    self.log.debug(f"{stack.id}: '{res.status}' {busy}x in a row; skipping this stack for now.")
                    self.log.end()
                    return moved
                self.log.trace(f"{stack.id} '{old_id}' -> '{target}': {res.status}, retry {busy}.")
                flush_all()
                sleep(BUSY_RETRY_S)
                continue
            self.log.debug(f"transfer {stack.id} '{old_id}' -> '{target}': {res.status} - {res.message}")
            self.log.end()
            return moved
        self.log.end()
        return moved

    def _target_for(self, item_id, props, new_id, old_id, outpost_id):
        """The new Large Warehouse if it has room, else another non-retiring store at the outpost."""
        self.log.start("[warehouse_upgrade] _target_for", level="debug")
        retiring = set((self._swap() or {}).get("old_ids") or []) | {old_id}
        ordered = [new_id]
        outpost = self._outpost(outpost_id)
        if outpost:
            others = [i for t in (LARGE_TYPE_ID, SMALL_TYPE_ID) for i in self._ids_of(outpost, t)]
            ordered += [i for i in others if i != new_id and i not in retiring]
        for building_id in ordered:
            wh = self._component(building_id)
            try:
                if wh and wh.space_for(item_id, props) > 0:
                    if building_id != new_id:
                        self.log.debug(f"'{new_id}' has no room for {item_id}; falling back to '{building_id}'.")
                    self.log.end()
                    return building_id
            except Exception as error:
                swallowed("warehouse_upgrade.WarehouseUpgrader._target_for: wh.space_for", error)
                continue
        self.log.debug(f"No store at '{outpost_id}' has room for {item_id} (tried {ordered}).")
        self.log.end()
        return None

