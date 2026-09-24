# Warehouse -> Large Warehouse upgrade (Phase 7, next to lib/fleet_upgrade.py),
# run from its own headless Custom Panel (control_panel/panel_6.py).
#
# Same gate as the fleet upgrade (drone_upgrade.upgrades_active(): panel_5.py
# switch on AND mining-drill phase reached), plus the Large Warehouse research
# and enough credits: price + WAREHOUSE_UPGRADE_CREDIT_RESERVE.
#
# One swap at a time, network-wide. A swap replaces TWO Warehouses at the same
# outpost with ONE Large Warehouse (10 slots -> 15, 20k -> 30k units): more
# storage without doubling the buildings every Auto Feeder consumer walks.
# The outpost with the most plain Warehouses goes first; there, the two
# emptiest. A lone leftover Warehouse at an outpost is kept.
#
# States (fleet.upgrade["warehouse_swap"], one dict, restart-safe; every pass
# re-reads it and writes back):
#   buying    -> buy large_warehouse from the Shop (skipped if one is already
#                in Inventory); snapshot of the outpost's Large Warehouses so a
#                restart adopts an already-deployed one instead of deploying twice
#   deploying -> computer.deploy("large_warehouse", outpost). Going over the
#                outpost's building count is fine: it only lasts for the drain.
#   draining  -> greedy drain: each old Warehouse is emptied with back-to-back
#                transfer_to() calls into the new one, then undeployed in the
#                same breath and its kit sold. While the drain runs, the old
#                Warehouse's feeder is busy nearly all the time, so every other
#                consumer's take_item()/unload already falls through to another
#                store ("busy" handling) -- no retiring-Warehouse blacklist that
#                every storage caller would have to check. Anything that still
#                slips in between two transfers is drained on the next pass;
#                undeploy() refuses ("cargo_present") while anything is left.
#   blocked   -> deploy/undeploy refused for good; the operator deletes
#                fleet.upgrade["warehouse_swap"] in the Data Archive Notebook
#                to retry (a bought kit stays in Inventory and is reused).
#
# Why not panel_4.py: a Warehouse feeder moves ~2.5 ticks/unit
# (docs/AI_CHEATSHEET.md §2c), so draining two full Warehouses blocks for tens
# of game minutes. panel_4.py's grid supervision can't wait that long, and
# Warehouses have no script slot of their own.

from drone_upgrade import fleet_upgrade_state, update_fleet_upgrade, is_upgrade_enabled, upgrade_phase_reached
from tree_console import TreeConsole

SMALL_TYPE_ID = "warehouse"
LARGE_TYPE_ID = "large_warehouse"      # also the Shop/Inventory kit id
LARGE_RESEARCH_ID = "research_high_bay_warehousing"
LARGE_PRICE_FALLBACK = 60000           # docs/database/equipment_production.md
SWAP_RATIO = 2                         # Warehouses retired per Large Warehouse

# Credits that must remain AFTER buying the Large Warehouse.
WAREHOUSE_UPGRADE_CREDIT_RESERVE = 100000
# Units per transfer_to() call. A whole 2000-unit slot would block ~8 game
# minutes with no status update; this keeps the old Warehouse just as busy
# (calls run back to back) while the loop can still log and notice cargo_present.
DRAIN_CHUNK_UNITS = 500
# A "busy" source/target (another consumer won the race): wait this long, retry.
BUSY_RETRY_S = 0.2
# Drain passes in one step that moved nothing before giving the step back.
DRAIN_MAX_IDLE_PASSES = 5
MAX_UNDEPLOY_ATTEMPTS = 5
# "busy"/"changed" answers in a row on one chunk before that stack is skipped
# for this pass (keeps a stuck feeder from spinning the loop forever).
MAX_BUSY_RETRIES = 50
# undeploy() answers that only mean "not right now": never count toward
# MAX_UNDEPLOY_ATTEMPTS, and a swap blocked by one of them (older code)
# resumes by itself. inventory_full = no Inventory room for the returned kit.
TRANSIENT_UNDEPLOY_STATUSES = ("inventory_full",)

SWAP_KEY = "warehouse_swap"            # section of fleet.upgrade
STATUS_KEY = "warehouse_status"        # one-line summary, same dict


def _shape(text):
    """text with every digit run collapsed to '#', to compare status lines without their counters."""
    out = []
    for c in text:
        if c.isdigit():
            if not out or out[-1] != "#":
                out.append("#")
        else:
            out.append(c)
    return "".join(out)


def _component(component_id):
    try:
        return get_component(component_id)
    except Exception:
        return None


class WarehouseUpgrader:
    """Warehouse pair -> Large Warehouse swap state machine. One instance, reused across cycles."""

    def __init__(self):
        self.log = TreeConsole(module="warehouse_upgrade")

    # ------------------------------------------------------------ lookups

    def _outposts(self):
        network = _component("outpost_network")
        try:
            return network.outposts() if network else []
        except Exception:
            return []

    def _outpost(self, outpost_id):
        return next((o for o in self._outposts() if getattr(o, "id", "") == outpost_id), None)

    def _ids_of(self, outpost, type_id):
        try:
            return sorted(getattr(ref, "id", "") for ref in outpost.buildings(type_id) if getattr(ref, "id", ""))
        except Exception:
            return []

    def _total(self, building_id):
        wh = _component(building_id)
        try:
            return int(wh.total()) if wh else 0
        except Exception:
            return 0

    def _inventory_count(self, item_id):
        inventory = _component("inventory")
        try:
            return int(inventory.count(item_id) or 0) if inventory else 0
        except Exception:
            return 0

    def _credits(self):
        commander = _component("commander")
        try:
            return int(commander.get_credits()) if commander else 0
        except Exception:
            return 0

    def _price(self):
        shop = _component("shop")
        try:
            for entry in shop.get_catalogue() if shop else []:
                if entry.id == LARGE_TYPE_ID:
                    return int(entry.cost)
        except Exception:
            pass
        return LARGE_PRICE_FALLBACK

    def _large_unlocked(self):
        research = _component("research")
        try:
            if research and research.is_unlocked(LARGE_RESEARCH_ID):
                return True
        except Exception:
            pass
        return self._inventory_count(LARGE_TYPE_ID) > 0

    # ------------------------------------------------------------ state

    def _swap(self):
        swap = fleet_upgrade_state().get(SWAP_KEY)
        return swap if isinstance(swap, dict) else None

    def _patch(self, **fields):
        update_fleet_upgrade(lambda s: s.setdefault(SWAP_KEY, {}).update(fields))

    def _clear(self):
        update_fleet_upgrade(lambda s: s.pop(SWAP_KEY, None))

    def _set_status(self, text):
        """Stores the status line; prints it when it changes beyond its numbers (no spam from counters)."""
        previous = fleet_upgrade_state().get(STATUS_KEY)
        if previous != text:
            update_fleet_upgrade(lambda s: s.update({STATUS_KEY: text}))
            if _shape(previous or "") != _shape(text):
                self.log.print(f"[warehouse_upgrade] Status: {text}")
        return text

    # ------------------------------------------------------------ main step

    def step(self):
        """One pass. May block for a long time while draining. Returns a one-line status."""
        swap = self._swap()
        enabled = is_upgrade_enabled()

        if swap and swap.get("state") == "blocked" and swap.get("reason") in TRANSIENT_UNDEPLOY_STATUSES and swap.get("new_id"):
            reason = swap.get("reason")
            self._patch(state="draining", attempts=0, reason=None)
            self.log.print(f"[warehouse_upgrade] Swap was blocked by '{reason}' (transient); resuming the drain.")
            swap = self._swap()

        if swap and swap.get("state") == "blocked":
            return self._set_status(f"blocked ({swap.get('reason')}); delete fleet.upgrade['{SWAP_KEY}'] to retry")

        if swap and not enabled and swap.get("state") == "buying" and self._inventory_count(LARGE_TYPE_ID) <= 0:
            self._clear()
            self.log.print("[warehouse_upgrade] Switched off before buying: swap cancelled.")
            swap = None

        if swap:
            return self._set_status(self._advance(swap))

        if not enabled:
            return self._set_status("disabled")
        if not upgrade_phase_reached():
            return self._set_status("waiting for mining drills")
        if not self._large_unlocked():
            return self._set_status("Large Warehouse not researched")
        return self._set_status(self._start_next() or "warehouses up to date")

    # ------------------------------------------------------------ selection

    def _start_next(self):
        candidates = []
        for outpost in self._outposts():
            smalls = self._ids_of(outpost, SMALL_TYPE_ID)
            if len(smalls) >= SWAP_RATIO:
                candidates.append((-len(smalls), getattr(outpost, "id", ""), smalls))
        if not candidates:
            return None
        candidates.sort()
        _, outpost_id, smalls = candidates[0]
        self.log.debug(f"[warehouse_upgrade] Outposts with >= {SWAP_RATIO} Warehouses: {[(c[1], -c[0]) for c in candidates]}; picked '{outpost_id}'.")

        price = self._price()
        credits = self._credits()
        needed = price + WAREHOUSE_UPGRADE_CREDIT_RESERVE
        if credits < needed and self._inventory_count(LARGE_TYPE_ID) <= 0:
            self.log.debug(f"[warehouse_upgrade] {credits} cr < {price} + reserve {WAREHOUSE_UPGRADE_CREDIT_RESERVE}; waiting.")
            return f"saving up ({credits}/{needed} cr)"

        fills = sorted((self._total(w), w) for w in smalls)
        old_ids = [w for _, w in fills[:SWAP_RATIO]]
        self.log.debug(f"[warehouse_upgrade] Fill at '{outpost_id}': {fills}; retiring the emptiest {old_ids}.")
        update_fleet_upgrade(lambda s: s.update({SWAP_KEY: {
            "state": "buying", "outpost": outpost_id, "old_ids": old_ids,
            "removed": [], "to_sell": 0, "new_id": None, "attempts": 0,
        }}))
        self.log.print(f"[warehouse_upgrade] '{outpost_id}': replacing {old_ids} with one Large Warehouse.")
        return f"{outpost_id}: buying Large Warehouse"

    # ------------------------------------------------------------ swap

    def _advance(self, swap):
        """
        Runs states back to back until one has to wait. Buy -> deploy -> drain
        must not pause in between: a freshly deployed, empty Large Warehouse is
        the least-full store at the outpost, so every other unloader and
        panel_4.py's Inventory rebalance pick it the moment it exists. Only a
        running drain (its feeder locked by our transfers) keeps them off it.
        """
        text = ""
        for _ in range(4):
            before = swap.get("state")
            text = self._advance_once(swap)
            swap = self._swap()
            if not swap or swap.get("state") in (before, "blocked"):
                return text
            self.log.debug(f"[warehouse_upgrade] '{before}' -> '{swap.get('state')}', continuing without a pause.")
        return text

    def _advance_once(self, swap):
        state = swap.get("state")
        outpost_id = swap.get("outpost")
        computer = _component("computer")
        if not computer or not hasattr(computer, "deploy"):
            return "no Ship Computer"
        self.log.debug(f"[warehouse_upgrade] Swap at '{outpost_id}': state '{state}'.")

        if state == "buying":
            if self._inventory_count(LARGE_TYPE_ID) <= 0:
                shop = _component("shop")
                price = self._price()
                if self._credits() < price:
                    return f"{outpost_id}: waiting for {price} cr"
                res = shop.buy(LARGE_TYPE_ID, 1) if shop else None
                status = getattr(res, "status", "no_shop")
                if status != "ok":
                    self.log.debug(f"[warehouse_upgrade] buy('{LARGE_TYPE_ID}'): {status} - {getattr(res, 'message', '')}")
                    return f"{outpost_id}: buy {status}, retrying"
                self.log.print(f"[warehouse_upgrade] Bought a Large Warehouse ({price} cr).")
            outpost = self._outpost(outpost_id)
            known = self._ids_of(outpost, LARGE_TYPE_ID) if outpost else []
            self._patch(state="deploying", known=known)
            return f"{outpost_id}: deploying"

        if state == "deploying":
            outpost = self._outpost(outpost_id)
            known = set(swap.get("known") or [])
            adopted = next((i for i in (self._ids_of(outpost, LARGE_TYPE_ID) if outpost else []) if i not in known), None)
            if adopted is None:
                res = computer.deploy(LARGE_TYPE_ID, outpost_id)
                if res.status != "ok":
                    if res.status in ("deploy_limit", "duplicate_outpost_machine", "wrong_biome_for_machine", "location_not_found", "not_deployable", "locked"):
                        self._patch(state="blocked", reason=res.status)
                        self.log.level("warn").print(f"[warehouse_upgrade] deploy('{LARGE_TYPE_ID}', '{outpost_id}') refused ({res.status}: {res.message}); swap blocked.")
                        return f"{outpost_id}: blocked ({res.status})"
                    if res.status == "no_kit":
                        self._patch(state="buying")
                    return f"{outpost_id}: deploy {res.status}"
                adopted = res.machine_id
            self._patch(state="draining", new_id=adopted)
            self.log.print(f"[warehouse_upgrade] Deployed '{adopted}' at '{outpost_id}'; draining {swap.get('old_ids')}.")
            return f"{outpost_id}: deployed {adopted}"

        if state == "draining":
            return self._drain_all(swap, computer)

        return f"{outpost_id}: unknown state {state!r}"

    def _drain_all(self, swap, computer):
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

    def _drain_and_remove(self, old_id, new_id, outpost_id, computer):
        """Greedy drain + undeploy of one old Warehouse. None once it is gone, else a status line."""
        self.log.start(f"[warehouse_upgrade] Draining '{old_id}' ({self._total(old_id)} units) into '{new_id}'")
        idle_passes = 0
        moved_total = 0
        try:
            while True:
                old = _component(old_id)
                stacks = []
                if old is not None:
                    try:
                        stacks = old.stacks()
                    except Exception as e:
                        self.log.debug(f"[warehouse_upgrade] '{old_id}'.stacks() raised {e}; trying undeploy.")

                if not stacks:
                    res = computer.undeploy(old_id)
                    if res.status in ("ok", "not_found"):
                        def mark(s):
                            swap = s.setdefault(SWAP_KEY, {})
                            removed = swap.setdefault("removed", [])
                            if old_id not in removed:
                                removed.append(old_id)
                                if res.status == "ok":
                                    swap["to_sell"] = int(swap.get("to_sell") or 0) + 1
                        update_fleet_upgrade(mark)
                        self._sell_kits()
                        self.log.print(f"[warehouse_upgrade] '{old_id}' empty ({moved_total} unit(s) moved) and undeployed.")
                        return None
                    self.log.debug(f"[warehouse_upgrade] undeploy('{old_id}'): {res.status} - {res.message}")
                    if res.status in TRANSIENT_UNDEPLOY_STATUSES:
                        return f"{old_id}: empty, waiting for Inventory room to take its kit back ({res.status})"
                    if res.status == "cargo_present":
                        idle_passes += 1
                        if idle_passes < DRAIN_MAX_IDLE_PASSES:
                            self.log.debug(f"[warehouse_upgrade] '{old_id}': something slipped in before undeploy; draining again.")
                            continue
                    attempts = int((self._swap() or {}).get("attempts") or 0) + 1
                    if attempts >= MAX_UNDEPLOY_ATTEMPTS:
                        self._patch(state="blocked", reason=res.status, attempts=attempts)
                        self.log.level("warn").print(f"[warehouse_upgrade] undeploy('{old_id}') refused {attempts}x ({res.status}: {res.message}); swap blocked.")
                        return f"{outpost_id}: blocked ({res.status})"
                    self._patch(attempts=attempts)
                    return f"{old_id}: undeploy {res.status}, retrying"

                moved_pass = 0
                for stack in stacks:
                    moved_pass += self._move_stack(old, old_id, new_id, outpost_id, stack)
                moved_total += moved_pass
                if moved_pass:
                    idle_passes = 0
                    continue
                idle_passes += 1
                if idle_passes >= DRAIN_MAX_IDLE_PASSES:
                    left = self._total(old_id)
                    self.log.level("warn").print(f"[warehouse_upgrade] '{old_id}': {left} unit(s) left and nowhere to move them; retrying later.")
                    return f"{old_id}: stuck with {left} unit(s)"
                sleep(BUSY_RETRY_S)
        finally:
            self.log.end(f"[warehouse_upgrade] '{old_id}': {moved_total} unit(s) moved this pass")

    def _move_stack(self, old, old_id, new_id, outpost_id, stack):
        """Moves one stack out of old in DRAIN_CHUNK_UNITS calls. Returns units moved."""
        moved = 0
        busy = 0
        remaining = int(getattr(stack, "count", 0) or 0)
        props = getattr(stack, "properties", None)
        while remaining > 0:
            target = self._target_for(stack.id, props, new_id, old_id, outpost_id)
            if target is None:
                self.log.debug(f"[warehouse_upgrade] No room anywhere at '{outpost_id}' for {remaining}x {stack.id}.")
                return moved
            res = old.transfer_to(target, stack.id, min(remaining, DRAIN_CHUNK_UNITS), properties=props, property_match="exact")
            got = int(getattr(res, "moved", 0) or 0) if res.status in ("ok", "partial") else 0
            if got:
                moved += got
                remaining -= got
                busy = 0
                self.log.debug(f"[warehouse_upgrade] {got}x {stack.id} '{old_id}' -> '{target}' ({remaining} left in this stack).")
                continue
            if res.status in ("busy", "source_changed", "target_changed", "target_under_construction"):
                busy += 1
                if busy >= MAX_BUSY_RETRIES:
                    self.log.debug(f"[warehouse_upgrade] {stack.id}: '{res.status}' {busy}x in a row; skipping this stack for now.")
                    return moved
                self.log.trace(f"[warehouse_upgrade] {stack.id} '{old_id}' -> '{target}': {res.status}, retry {busy}.")
                sleep(BUSY_RETRY_S)
                continue
            self.log.debug(f"[warehouse_upgrade] transfer {stack.id} '{old_id}' -> '{target}': {res.status} - {res.message}")
            return moved
        return moved

    def _target_for(self, item_id, props, new_id, old_id, outpost_id):
        """The new Large Warehouse if it has room, else another non-retiring store at the outpost."""
        retiring = set((self._swap() or {}).get("old_ids") or []) | {old_id}
        ordered = [new_id]
        outpost = self._outpost(outpost_id)
        if outpost:
            others = [i for t in (LARGE_TYPE_ID, SMALL_TYPE_ID) for i in self._ids_of(outpost, t)]
            ordered += [i for i in others if i != new_id and i not in retiring]
        for building_id in ordered:
            wh = _component(building_id)
            try:
                if wh and wh.space_for(item_id, props) > 0:
                    if building_id != new_id:
                        self.log.debug(f"[warehouse_upgrade] '{new_id}' has no room for {item_id}; falling back to '{building_id}'.")
                    return building_id
            except Exception:
                continue
        self.log.debug(f"[warehouse_upgrade] No store at '{outpost_id}' has room for {item_id} (tried {ordered}).")
        return None

    def _sell_kits(self):
        """Sells the Warehouse kits this swap got back from undeploy() (never the operator's spares)."""
        to_sell = int((self._swap() or {}).get("to_sell") or 0)
        if to_sell <= 0:
            return
        shop = _component("shop")
        res = shop.sell(SMALL_TYPE_ID, to_sell) if shop else None
        if res is not None and res.status == "ok":
            self._patch(to_sell=0)
            self.log.print(f"[warehouse_upgrade] Sold {to_sell} Warehouse kit(s) for {res.credits} cr.")
        else:
            self.log.debug(f"[warehouse_upgrade] sell('{SMALL_TYPE_ID}', {to_sell}): {getattr(res, 'status', 'no_shop')}; retrying next pass.")
