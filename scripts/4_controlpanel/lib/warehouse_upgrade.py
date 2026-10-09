# Warehouse -> Large Warehouse upgrade (Phase 7, next to lib/fleet_upgrade.py),
# run from its own Automation (automation/builder_automation.py).
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
#   draining  -> each old Warehouse is emptied with back-to-back transfer_to()
#                calls into the new one, then undeployed in the same breath and
#                its kit sold. One pass drains for at most DRAIN_PASS_TICKS,
#                then gives the loop back; the next pass carries on. While deploying/draining, the
#                old Warehouses are retiring stores (storage.RETIRING_STORES_KEY,
#                RETIRES_STORES): no delivery targets them, takes still do.
#                Anything that still slips in (a script's retiring cache, a
#                manual drop) is drained on the next pass; undeploy() refuses
#                ("cargo_present") while anything is left.
#
# A Warehouse feeder moves ~2.5 ticks/unit (docs/AI_CHEATSHEET.md §2c), so
# draining two full Warehouses takes tens of game minutes; DRAIN_PASS_TICKS
# splits that into passes so the other steps of the Automation keep running.
#
# BinUpgrader (interim, until the autoplay builder upgrades bins by slot demand,
# TODO.md): Storage Bins -> one Warehouse. Bins of one material share a planned
# Warehouse slot (up to SLOT_UNITS units), up to
# WAREHOUSE_SLOTS slots, plus every empty bin. Any bin starts a swap, so every bin
# goes; Warehouses bought <= ceil(bins / 4).
# Its drain targets follow storage.best_unload_target(), so a material's bins
# land on one stack. Other deliveries can fill the new Warehouse mid-drain;
# after STUCK_PASSES_BEFORE_REBUY passes with no room anywhere, the swap buys
# one more Warehouse (BuildingSwapUpgrader._rebuy()) and drains into that.

from building_swap_upgrade import BuildingSwapUpgrader, TRANSIENT_UNDEPLOY_STATUSES
from tree_console import flush_all, method_block
from game_clock import now_tick
from swallow import swallowed
from storage import WAREHOUSE_TECH_ID, BinStore, best_unload_target, forget_storage_discovery
import cash

SMALL_TYPE_ID = "warehouse"
LARGE_TYPE_ID = "large_warehouse"      # also the Shop/Inventory kit id
SWAP_RATIO = 2                         # Warehouses retired per Large Warehouse
# Warehouse layout (docs/components/warehouse.md) the bin plan packs into.
WAREHOUSE_SLOTS = 5
SLOT_UNITS = 2000
# Units per transfer_to() call (~500 ticks of feeder time at 2.5 ticks/unit,
# §2c). Feeder time is linear in units, so smaller chunks cost only script
# steps; they bound how far a pass can run over DRAIN_PASS_TICKS.
DRAIN_CHUNK_UNITS = 200
# Game ticks one pass may drain (~1 game minute, ~240 units at ~2.5 ticks/unit);
# checked between transfer_to() calls, so a pass can run one chunk longer.
DRAIN_PASS_TICKS = 600
# A "busy" source/target (another consumer won the race): wait this long, retry.
BUSY_RETRY_S = 0.2
# Drain passes in one step that moved nothing before giving the step back.
DRAIN_MAX_IDLE_PASSES = 5
# "busy"/"changed" answers in a row on one chunk before that stack is skipped
# for this pass (keeps a stuck feeder from spinning the loop forever).
MAX_BUSY_RETRIES = 50
# BinUpgrader: drain steps in a row that end stuck with no room at the outpost
# before the swap buys one more Warehouse.
STUCK_PASSES_BEFORE_REBUY = 3


class WarehouseUpgrader(BuildingSwapUpgrader):
    """Warehouse pair -> Large Warehouse swap. One instance, reused across cycles."""

    MODULE = "warehouse_upgrade"
    RETIRES_STORES = True
    _deadline = 0               # now_tick() at which this pass's drain stops
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
    SWAP_RATIO = SWAP_RATIO
    # Store types a drain may fall back to when the new building is full.
    TARGET_TYPE_IDS = (LARGE_TYPE_ID, SMALL_TYPE_ID)
    # Stuck drain steps (no room anywhere) before _rebuy(); 0 = never re-buy.
    STUCK_PASSES_BEFORE_REBUY = 0
    _no_room = False            # this drain step met a stack with no target at the outpost

    def _total(self, building_id):
        wh = self._component(building_id)
        try:
            if wh and not hasattr(wh, "total"):
                return int(wh.get_capacity()) - int(wh.space())   # Storage Bin
            return int(wh.total()) if wh else 0
        except Exception as error:
            swallowed("warehouse_upgrade.WarehouseUpgrader._total: wh.total", error)
            return 0

    # ------------------------------------------------------------ selection

    def _start_next(self):
        self.log.start(f"[{self.MODULE}] _start_next", level="debug")
        candidates = self._candidates()
        if not candidates:
            cash.release(self.CASH_CONSUMER)
            self.log.end()
            return None
        candidates.sort()
        _, outpost_id, smalls, _ = candidates[0]
        self.log.debug(f"Outposts with {self.SMALL_NAME}s to retire: {[(c[1], -c[0]) for c in candidates]}; picked '{outpost_id}'.")

        groups = sum(c[3] for c in candidates)
        if not self._can_buy(outpost_id, groups):
            _ret = f"saving up ({self._credits()}/{self._price()} cr)"
            self.log.end()
            return _ret

        old_ids = self._pick(outpost_id, smalls)
        self._begin(outpost_id, old_ids)
        self.log.print(f"[{self.MODULE}] '{outpost_id}': replacing {old_ids} with one {self.LARGE_NAME}.")
        self.log.end()
        return f"{outpost_id}: buying {self.LARGE_NAME}"

    def _candidates(self):
        """[(-rank, outpost_id, small_ids, swaps), ...] for every outpost with a swap to do."""
        candidates = []
        for outpost in self._outposts():
            smalls = self._ids_of(outpost, self.SMALL_TYPE_ID)
            if len(smalls) >= self.SWAP_RATIO:
                candidates.append((-len(smalls), getattr(outpost, "id", ""), smalls, len(smalls) // self.SWAP_RATIO))
        return candidates

    def _pick(self, outpost_id, smalls):
        """The SWAP_RATIO emptiest of smalls."""
        fills = sorted((self._total(w), w) for w in smalls)
        old_ids = [w for _, w in fills[:self.SWAP_RATIO]]
        self.log.debug(f"Fill at '{outpost_id}': {fills}; retiring the emptiest {old_ids}.")
        return old_ids

    # ------------------------------------------------------------ drain

    def _drain(self, swap, computer: "Computer"):
        outpost_id = swap.get("outpost")
        new_id = swap.get("new_id")
        self._deadline = now_tick() + DRAIN_PASS_TICKS
        self._no_room = False
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
            return f"{outpost_id}: selling old {self.SMALL_NAME} kits"
        self._clear()
        self.log.print(f"[{self.MODULE}] Swap done at '{outpost_id}': {swap.get('old_ids')} -> '{new_id}'.")
        return f"{outpost_id}: {swap.get('old_ids')} -> {new_id} done"

    def _drain_and_remove(self, old_id, new_id, outpost_id, computer: "Computer"):
        """Greedy drain + undeploy of one old building. None once it is gone, else a status line."""
        self.log.start(f"[{self.MODULE}] Draining '{old_id}' ({self._total(old_id)} units) into '{new_id}'")
        moved = [0]
        result = self._drain_loop(old_id, new_id, outpost_id, computer, moved)
        self.log.end(f"[{self.MODULE}] '{old_id}': {moved[0]} unit(s) moved this pass")
        return result

    @method_block(lambda self, *_args: f"[{self.MODULE}] _drain_loop")
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
                    self.log.print(f"[{self.MODULE}] '{old_id}' empty ({moved[0]} unit(s) moved) and undeployed.")
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
                if self._out_of_time():
                    break
            moved[0] += moved_pass
            if self._out_of_time():
                return f"{old_id}: draining, {self._total(old_id)} unit(s) left"
            if moved_pass:
                idle_passes = 0
                if int((self._swap() or {}).get("stuck") or 0):
                    self._patch(stuck=0)
                continue
            idle_passes += 1
            if idle_passes >= DRAIN_MAX_IDLE_PASSES:
                return self._stuck(old_id, outpost_id)
            flush_all()
            sleep(BUSY_RETRY_S)

    def _stuck(self, old_id, outpost_id):
        """A drain step that moved nothing: counts it when there was no room, re-buys after
        STUCK_PASSES_BEFORE_REBUY in a row. Returns a status line."""
        left = self._total(old_id)
        stuck = int((self._swap() or {}).get("stuck") or 0) + 1 if self._no_room else 0
        self._patch(stuck=stuck)
        if self.STUCK_PASSES_BEFORE_REBUY and stuck >= self.STUCK_PASSES_BEFORE_REBUY:
            return self._rebuy(outpost_id, f"'{old_id}' stuck with {left} unit(s) and no room, {stuck}x")
        self.log.level("warn").print(f"[{self.MODULE}] '{old_id}': {left} unit(s) left and nowhere to move them; retrying later.")
        return f"{old_id}: stuck with {left} unit(s)"

    def _out_of_time(self):
        """True once this pass's DRAIN_PASS_TICKS are used up."""
        return now_tick() >= self._deadline

    def _move_stack(self, old, old_id, new_id, outpost_id, stack):
        """Moves one stack out of old in DRAIN_CHUNK_UNITS calls. Returns units moved."""
        self.log.start(f"[{self.MODULE}] _move_stack", level="debug")
        moved = 0
        busy = 0
        remaining = int(getattr(stack, "count", 0) or 0)
        props = getattr(stack, "properties", None)
        while remaining > 0 and not self._out_of_time():
            target = self._target_for(stack.id, props, new_id, old_id, outpost_id)
            if target is None:
                self._no_room = True
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
        """The new building if it has room, else another non-retiring TARGET_TYPE_IDS store at the outpost."""
        self.log.start(f"[{self.MODULE}] _target_for", level="debug")
        retiring = set((self._swap() or {}).get("old_ids") or []) | {old_id}
        ordered = [new_id]
        outpost = self._outpost(outpost_id)
        if outpost:
            others = [i for t in self.TARGET_TYPE_IDS for i in self._ids_of(outpost, t)]
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



class BinUpgrader(WarehouseUpgrader):
    """Four Storage Bins -> one Warehouse swap (interim). One instance, reused across cycles."""

    MODULE = "bin_upgrade"
    SMALL_TYPE_ID = "storage_bin"
    LARGE_TYPE_ID = "warehouse"
    LARGE_RESEARCH_ID = WAREHOUSE_TECH_ID
    LARGE_PRICE_FALLBACK = 3000            # docs/database/equipment_production.md
    CASH_CONSUMER = "bin_upgrade"
    SWAP_KEY = "bin_swap"
    STATUS_KEY = "bin_status"
    SMALL_NAME = "Storage Bin"
    LARGE_NAME = "Warehouse"
    UP_TO_DATE = "storage bins up to date"
    TARGET_TYPE_IDS = ("warehouse", "large_warehouse")
    WAIT_FOR_DRILLS = False     # starts as soon as Warehouses are researched
    STUCK_PASSES_BEFORE_REBUY = STUCK_PASSES_BEFORE_REBUY

    def _candidates(self):
        candidates = []
        for outpost in self._outposts():
            plan = self._bin_plan(outpost)
            if plan:
                candidates.append((-len(plan), getattr(outpost, "id", ""), plan, 1))
        return candidates

    def _pick(self, outpost_id, smalls):
        self.log.debug(f"Bin plan at '{outpost_id}': retiring {smalls}.")
        return smalls

    def _bin_plan(self, outpost: "OutpostRef"):
        """Bin ids one Warehouse absorbs: per material, the emptiest bins packed
        into slots of <= SLOT_UNITS units, biggest
        slots first, WAREHOUSE_SLOTS slots at most, plus every empty bin (no slot needed)."""
        by_material = {}
        empty = []
        for bin_id in self._ids_of(outpost, self.SMALL_TYPE_ID):
            bin_ = self._component(bin_id)
            try:
                material = bin_.get_material() if bin_ else ""
            except Exception as error:
                swallowed("warehouse_upgrade.BinUpgrader._bin_plan: get_material", error)
                continue
            if material:
                by_material.setdefault(material, []).append((self._total(bin_id), bin_id))
            else:
                empty.append(bin_id)
        slots = []
        for material in sorted(by_material):
            chunk, units = [], 0
            for count, bin_id in sorted(by_material[material]):
                if chunk and units + count > SLOT_UNITS:
                    slots.append(chunk)
                    chunk, units = [], 0
                chunk.append(bin_id)
                units += count
            slots.append(chunk)
        slots.sort(key=lambda chunk: -len(chunk))
        return [bin_id for chunk in slots[:WAREHOUSE_SLOTS] for bin_id in chunk] + empty

    def _drain(self, swap, computer: "Computer"):
        forget_storage_discovery()     # best_unload_target() must see the new Warehouse
        return super()._drain(swap, computer)

    def _target_for(self, item_id, props, new_id, old_id, outpost_id):
        """storage.best_unload_target() over the outpost's stores minus the retiring bins; base fallback."""
        retiring = tuple(set((self._swap() or {}).get("old_ids") or []) | {old_id})
        outpost = self._outpost(outpost_id)
        target = best_unload_target(item_id, outpost=outpost, exclude=retiring) if outpost else None
        store = self._component(target) if target else None
        if store is not None and hasattr(store, "get_material"):
            store = BinStore(store)
        try:
            if store is not None and store.space_for(item_id, props) > 0:
                return target
        except Exception as error:
            swallowed("warehouse_upgrade.BinUpgrader._target_for: space_for", error)
        return super()._target_for(item_id, props, new_id, old_id, outpost_id)
