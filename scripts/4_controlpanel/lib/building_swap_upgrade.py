# Shared "N small buildings -> one large building" swap state machine, used by
# lib/warehouse_upgrade.py (Warehouse -> Large Warehouse) and lib/tank_upgrade.py
# (Liquid Tank -> Large Liquid Tank). Both run from the same Automation
# (automation/warehouse_upgrade_automation.py).
#
# States (fleet.upgrade[SWAP_KEY], one dict, restart-safe; every pass re-reads it
# and writes back):
#   buying    -> buy LARGE_TYPE_ID from the Shop (skipped if one is already in
#                Inventory); snapshot of the outpost's large buildings so a restart
#                adopts an already-deployed one instead of deploying twice
#   deploying -> computer.deploy(LARGE_TYPE_ID, outpost). Going over the outpost's
#                building count is fine: it only lasts for the drain.
#   draining  -> subclass _drain(swap, computer): empty each old building into the
#                new one, undeploy it (_mark_removed) and sell its kit (_sell_kits)
#   blocked   -> deploy/undeploy/connect refused for good; the operator deletes
#                fleet.upgrade[SWAP_KEY] in the Data Archive Notebook to retry (a
#                bought kit stays in Inventory and is reused). A swap blocked by a
#                TRANSIENT_UNDEPLOY_STATUSES answer resumes by itself.
#
# Subclasses set the class constants below and implement _start_next() (pick the
# group, write the "buying" swap dict) and _drain(swap, computer).

from drone_upgrade import fleet_upgrade_state, update_fleet_upgrade, is_upgrade_enabled, upgrade_phase_reached
from tree_console import TreeConsole
from swallow import swallowed
import cash
from storage import inventory_count

MAX_ATTEMPTS = 5                    # refused undeploy/connect answers in a row before "blocked"
# undeploy() answers that only mean "not right now": never count toward
# MAX_ATTEMPTS. inventory_full = no Inventory room for the returned kit.
TRANSIENT_UNDEPLOY_STATUSES = ("inventory_full",)
# deploy() answers that will not change by retrying.
FATAL_DEPLOY_STATUSES = ("deploy_limit", "duplicate_outpost_machine", "wrong_biome_for_machine", "location_not_found", "not_deployable", "locked")


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


def component(component_id, where):
    try:
        return get_component(component_id)
    except Exception as error:
        swallowed(f"{where}: get_component", error)
        return None


class BuildingSwapUpgrader:
    """Small-building group -> one large building swap state machine. One instance, reused across cycles."""

    MODULE = ""                 # log tag and swallowed() prefix
    SMALL_TYPE_ID = ""
    LARGE_TYPE_ID = ""          # also the Shop/Inventory kit id
    LARGE_RESEARCH_ID = ""
    LARGE_PRICE_FALLBACK = 0
    CASH_CONSUMER = ""          # lib/cash.py consumer id
    SWAP_KEY = ""               # section of fleet.upgrade
    STATUS_KEY = ""             # one-line summary, same dict
    SMALL_NAME = ""             # "Warehouse"
    LARGE_NAME = ""             # "Large Warehouse"
    UP_TO_DATE = ""             # status line when nothing is left to swap
    WAIT_FOR_DRILLS = True      # also gate on the mining-drill phase (upgrade_phase_reached())

    def __init__(self):
        self.log = TreeConsole(module=self.MODULE)

    def _component(self, component_id):
        return component(component_id, f"{self.MODULE}._component")

    # ------------------------------------------------------------ lookups

    def _outposts(self):
        network = self._component("outpost_network")
        try:
            return network.outposts() if network else []
        except Exception as error:
            swallowed(f"{self.MODULE}._outposts: network.outposts", error)
            return []

    def _outpost(self, outpost_id):
        return next((o for o in self._outposts() if getattr(o, "id", "") == outpost_id), None)

    def _ids_of(self, outpost: "OutpostRef", type_id):
        try:
            return sorted(getattr(ref, "id", "") for ref in outpost.buildings(type_id) if getattr(ref, "id", ""))
        except Exception as error:
            swallowed(f"{self.MODULE}._ids_of: outpost.buildings", error)
            return []

    def _credits(self):
        commander = self._component("commander")
        try:
            return int(commander.get_credits()) if commander else 0
        except Exception as error:
            swallowed(f"{self.MODULE}._credits: commander.get_credits", error)
            return 0

    def _price(self):
        shop = self._component("shop")
        try:
            for entry in shop.get_catalogue() if shop else []:
                if entry.id == self.LARGE_TYPE_ID:
                    return int(entry.cost)
        except Exception as error:
            swallowed(f"{self.MODULE}._price: shop.get_catalogue", error)
        return self.LARGE_PRICE_FALLBACK

    def _large_unlocked(self):
        research = self._component("research")
        try:
            if research and research.is_unlocked(self.LARGE_RESEARCH_ID):
                return True
        except Exception as error:
            swallowed(f"{self.MODULE}._large_unlocked: research.is_unlocked", error)
        return inventory_count(self.LARGE_TYPE_ID) > 0

    # ------------------------------------------------------------ state

    def _swap(self):
        swap = fleet_upgrade_state().get(self.SWAP_KEY)
        return swap if isinstance(swap, dict) else None

    def _patch(self, **fields):
        update_fleet_upgrade(lambda s: s.setdefault(self.SWAP_KEY, {}).update(fields))

    def _clear(self):
        update_fleet_upgrade(lambda s: s.pop(self.SWAP_KEY, None))

    def _begin(self, outpost_id, old_ids, **extra):
        """Writes a fresh "buying" swap for old_ids at outpost_id."""
        fresh = {"state": "buying", "outpost": outpost_id, "old_ids": old_ids, "removed": [], "to_sell": 0, "new_id": None, "attempts": 0}
        fresh.update(extra)
        update_fleet_upgrade(lambda s: s.update({self.SWAP_KEY: fresh}))

    def _can_buy(self, outpost_id, swaps, what=""):
        """True when a kit is in Inventory or the cash manager allows the purchase; else logs the hold-back."""
        price = self._price()
        if inventory_count(self.LARGE_TYPE_ID) > 0:
            return True
        if cash.can_spend(self.CASH_CONSUMER, price, planned=swaps * price, label=f"{swaps} {self.LARGE_NAME}(s)"):
            return True
        self.log.debug(f"cash manager holds back {price} cr for '{outpost_id}'{what}; waiting.")
        return False

    def _set_status(self, text):
        """Stores the status line; prints it when it changes beyond its numbers (no spam from counters)."""
        previous = fleet_upgrade_state().get(self.STATUS_KEY)
        if previous != text:
            update_fleet_upgrade(lambda s: s.update({self.STATUS_KEY: text}))
            if _shape(previous or "") != _shape(text):
                self.log.print(f"[{self.MODULE}] Status: {text}")
        return text

    # ------------------------------------------------------------ main step

    def step(self):
        """One pass. Returns a one-line status."""
        swap = self._swap()
        enabled = is_upgrade_enabled()

        if swap and swap.get("state") == "blocked" and swap.get("reason") in TRANSIENT_UNDEPLOY_STATUSES and swap.get("new_id"):
            reason = swap.get("reason")
            self._patch(state="draining", attempts=0, reason=None)
            self.log.print(f"[{self.MODULE}] Swap was blocked by '{reason}' (transient); resuming the drain.")
            swap = self._swap()

        if swap and swap.get("state") == "blocked":
            return self._set_status(f"blocked ({swap.get('reason')}); delete fleet.upgrade['{self.SWAP_KEY}'] to retry")

        if swap and not enabled and swap.get("state") == "buying" and inventory_count(self.LARGE_TYPE_ID) <= 0:
            self._clear()
            self.log.print(f"[{self.MODULE}] Switched off before buying: swap cancelled.")
            swap = None

        if swap:
            return self._set_status(self._advance(swap))

        if not enabled:
            return self._set_status("disabled")
        if self.WAIT_FOR_DRILLS and not upgrade_phase_reached():
            return self._set_status("waiting for mining drills")
        if not self._large_unlocked():
            return self._set_status(f"{self.LARGE_NAME} not researched")
        return self._set_status(self._start_next() or self.UP_TO_DATE)

    def _start_next(self):
        """Picks the next group and calls _begin(); returns a status line, or None when nothing is left."""
        raise NotImplementedError

    def _drain(self, swap, computer: "Computer"):
        """One "draining" pass; returns a status line."""
        raise NotImplementedError

    # ------------------------------------------------------------ swap

    def _advance(self, swap):
        """
        Runs states back to back until one has to wait. Buy -> deploy -> drain
        must not pause in between: a freshly deployed, empty large building is
        the least-full store at the outpost, so other unloaders/routers pick it
        the moment it exists; the drain step claims it first.
        """
        text = ""
        for _ in range(4):
            before = swap.get("state")
            text = self._advance_once(swap)
            swap = self._swap()
            if not swap or swap.get("state") in (before, "blocked"):
                return text
            self.log.debug(f"[{self.MODULE}] '{before}' -> '{swap.get('state')}', continuing without a pause.")
        return text

    def _advance_once(self, swap):
        self.log.start(f"[{self.MODULE}] _advance_once", level="debug")
        text = self._advance_state(swap)
        self.log.end()
        return text

    def _advance_state(self, swap):
        state = swap.get("state")
        outpost_id = swap.get("outpost")
        computer = self._component("computer")
        if not computer or not hasattr(computer, "deploy"):
            return "no Ship Computer"
        self.log.debug(f"Swap at '{outpost_id}': state '{state}'.")
        if state == "buying":
            return self._buy(outpost_id)
        if state == "deploying":
            return self._deploy(swap, outpost_id, computer)
        if state == "draining":
            return self._drain(swap, computer)
        return f"{outpost_id}: unknown state {state!r}"

    def _buy(self, outpost_id):
        if inventory_count(self.LARGE_TYPE_ID) <= 0:
            shop = self._component("shop")
            price = self._price()
            if self._credits() < price:
                return f"{outpost_id}: waiting for {price} cr"
            res = shop.buy(self.LARGE_TYPE_ID, 1) if shop else None
            status = getattr(res, "status", "no_shop")
            if status != "ok":
                self.log.debug(f"buy('{self.LARGE_TYPE_ID}'): {status} - {getattr(res, 'message', '')}")
                return f"{outpost_id}: buy {status}, retrying"
            cash.spent(self.CASH_CONSUMER, price)
            self.log.print(f"[{self.MODULE}] Bought a {self.LARGE_NAME} ({price} cr).")
        outpost = self._outpost(outpost_id)
        known = self._ids_of(outpost, self.LARGE_TYPE_ID) if outpost else []
        self._patch(state="deploying", known=known)
        return f"{outpost_id}: deploying"

    def _deploy(self, swap, outpost_id, computer: "Computer"):
        outpost = self._outpost(outpost_id)
        known = set(swap.get("known") or [])
        adopted = next((i for i in (self._ids_of(outpost, self.LARGE_TYPE_ID) if outpost else []) if i not in known), None)
        if adopted is None:
            res = computer.deploy(self.LARGE_TYPE_ID, outpost_id)
            if res.status != "ok":
                if res.status in FATAL_DEPLOY_STATUSES:
                    self._patch(state="blocked", reason=res.status)
                    self.log.level("warn").print(f"[{self.MODULE}] deploy('{self.LARGE_TYPE_ID}', '{outpost_id}') refused ({res.status}: {res.message}); swap blocked.")
                    return f"{outpost_id}: blocked ({res.status})"
                if res.status == "no_kit":
                    self._patch(state="buying")
                return f"{outpost_id}: deploy {res.status}"
            adopted = res.machine_id
        self._patch(state="draining", new_id=adopted)
        self.log.print(f"[{self.MODULE}] Deployed '{adopted}' at '{outpost_id}'; draining {swap.get('old_ids')}.")
        return f"{outpost_id}: deployed {adopted}"

    # ------------------------------------------------------------ drain helpers

    def _mark_removed(self, old_id, undeploy_status):
        """Records old_id as removed; an "ok" undeploy returned a kit to sell."""
        def mark(s):
            swap = s.setdefault(self.SWAP_KEY, {})
            removed = swap.setdefault("removed", [])
            if old_id not in removed:
                removed.append(old_id)
                if undeploy_status == "ok":
                    swap["to_sell"] = int(swap.get("to_sell") or 0) + 1
            swap["attempts"] = 0
        update_fleet_upgrade(mark)

    def _refused(self, what, res, outpost_id, reason=None):
        """Counts a refusal; MAX_ATTEMPTS in a row blocks the swap."""
        reason = reason or getattr(res, "status", "refused")
        attempts = int((self._swap() or {}).get("attempts") or 0) + 1
        if attempts >= MAX_ATTEMPTS:
            self._patch(state="blocked", reason=reason, attempts=attempts)
            self.log.level("warn").print(f"[{self.MODULE}] {what} refused {attempts}x ({reason}: {getattr(res, 'message', '')}); swap blocked.")
            return f"{outpost_id}: blocked ({reason})"
        self._patch(attempts=attempts)
        return f"{what}: {reason}, retrying"

    def _sell_kits(self):
        """Sells the small-building kits this swap got back from undeploy() (never the operator's spares)."""
        to_sell = int((self._swap() or {}).get("to_sell") or 0)
        if to_sell <= 0:
            return
        shop = self._component("shop")
        res = shop.sell(self.SMALL_TYPE_ID, to_sell) if shop else None
        if res is not None and res.status == "ok":
            self._patch(to_sell=0)
            self.log.print(f"[{self.MODULE}] Sold {to_sell} {self.SMALL_NAME} kit(s) for {res.credits} cr.")
        else:
            self.log.debug(f"[{self.MODULE}] sell('{self.SMALL_TYPE_ID}', {to_sell}): {getattr(res, 'status', 'no_shop')}; retrying next pass.")
