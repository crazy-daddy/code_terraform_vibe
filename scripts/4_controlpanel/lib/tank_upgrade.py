# Liquid Tank -> Large Liquid Tank upgrade (Phase 7, next to lib/warehouse_upgrade.py),
# run from the same headless Custom Panel (control_panel/warehouse_upgrade_panel.py).
#
# Same gate as the warehouse upgrade (drone_upgrade.upgrades_active()), plus the
# Large Liquid Tank research and the cash manager's go-ahead (lib/cash.py
# can_spend("tank_upgrade")).
#
# One swap at a time, network-wide. A swap replaces up to SWAP_RATIO Liquid Tanks
# holding the same liquid at one outpost with ONE Large Liquid Tank (100 t each ->
# 1,000 t): leftovers are swapped too, so 7 tanks end up as 2 Large Liquid Tanks.
# A tank's liquid is its latch, else its fluid_routing.tank_assignments entry; a
# tank with neither is left alone. Biggest group first.
#
# States (fleet.upgrade["tank_swap"], one dict, restart-safe; every pass re-reads
# it and writes back):
#   buying    -> buy bulk_liquid_reservoir from the Shop (skipped if one is already
#                in Inventory); snapshot of the outpost's Large Liquid Tanks so a
#                restart adopts an already-deployed one instead of deploying twice
#   deploying -> computer.deploy("bulk_liquid_reservoir", outpost). Going over the
#                outpost's building count is fine: it only lasts for the drain.
#   draining  -> tank_assignments: new tank -> the liquid, old tanks -> "retiring"
#                (re-asserted every pass, which also replaces the blank "" entry
#                warn_about_unassigned_tanks() may add for the new tank). Routers
#                never pick a retiring tank, so producers move to the new one. The
#                new tank's liquid_in pulls each old tank dry in turn; an empty one
#                is disconnected, undeployed, its kit sold and its entry dropped.
#                Non-blocking: one check per pass.
#   blocked   -> deploy/undeploy/connect refused for good; the operator deletes
#                fleet.upgrade["tank_swap"] in the Data Archive Notebook to retry
#                (a bought kit stays in Inventory and is reused).
#
# An old tank is undeployed only once is_empty(): undeploy() may refuse liquid as
# cargo_present, or drop it. A drain that stops (new tank full, or a producer that
# can't reach the new tank still feeding the old one) just waits and says so in
# the status line.

from archive import archive
from drone_upgrade import fleet_upgrade_state, update_fleet_upgrade, is_upgrade_enabled, upgrade_phase_reached
from fluid_routing import TANK_ASSIGNMENTS_KEY, RETIRING_ASSIGNMENT, get_tank_assignments, declared_connection_state, BROKEN_CONNECTION_STATES
from warehouse_upgrade import TRANSIENT_UNDEPLOY_STATUSES
import cash
from tree_console import TreeConsole
from swallow import swallowed

SMALL_TYPE_ID = "liquid_tank"
LARGE_TYPE_ID = "bulk_liquid_reservoir"   # also the Shop/Inventory kit id
LARGE_RESEARCH_ID = "research_reservoir_engineering"
LARGE_PRICE_FALLBACK = 15000              # docs/database/equipment_fluids.md
SWAP_RATIO = 5                            # at most this many Liquid Tanks per Large Liquid Tank
CASH_CONSUMER = "tank_upgrade"            # lib/cash.py consumer id
MAX_ATTEMPTS = 5                          # refused undeploy/connect answers before "blocked"

SWAP_KEY = "tank_swap"                    # section of fleet.upgrade
STATUS_KEY = "tank_status"                # one-line summary, same dict


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
    except Exception as error:
        swallowed("tank_upgrade._component: get_component", error)
        return None


def _call(obj, method, default, where):
    try:
        return getattr(obj, method)() if obj is not None else default
    except Exception as error:
        swallowed(f"tank_upgrade.{where}: {method}", error)
        return default


class TankUpgrader:
    """Liquid Tank group -> Large Liquid Tank swap state machine. One instance, reused across cycles."""

    def __init__(self):
        self.log = TreeConsole(module="tank_upgrade")

    # ------------------------------------------------------------ lookups

    def _outposts(self):
        network = _component("outpost_network")
        try:
            return network.outposts() if network else []
        except Exception as error:
            swallowed("tank_upgrade.TankUpgrader._outposts: network.outposts", error)
            return []

    def _outpost(self, outpost_id):
        return next((o for o in self._outposts() if getattr(o, "id", "") == outpost_id), None)

    def _ids_of(self, outpost, type_id):
        try:
            return sorted(getattr(ref, "id", "") for ref in outpost.buildings(type_id) if getattr(ref, "id", ""))
        except Exception as error:
            swallowed("tank_upgrade.TankUpgrader._ids_of: outpost.buildings", error)
            return []

    def _inventory_count(self, item_id):
        inventory = _component("inventory")
        try:
            return int(inventory.count(item_id) or 0) if inventory else 0
        except Exception as error:
            swallowed("tank_upgrade.TankUpgrader._inventory_count: inventory.count", error)
            return 0

    def _credits(self):
        commander = _component("commander")
        try:
            return int(commander.get_credits()) if commander else 0
        except Exception as error:
            swallowed("tank_upgrade.TankUpgrader._credits: commander.get_credits", error)
            return 0

    def _price(self):
        shop = _component("shop")
        try:
            for entry in shop.get_catalogue() if shop else []:
                if entry.id == LARGE_TYPE_ID:
                    return int(entry.cost)
        except Exception as error:
            swallowed("tank_upgrade.TankUpgrader._price: shop.get_catalogue", error)
        return LARGE_PRICE_FALLBACK

    def _large_unlocked(self):
        research = _component("research")
        try:
            if research and research.is_unlocked(LARGE_RESEARCH_ID):
                return True
        except Exception as error:
            swallowed("tank_upgrade.TankUpgrader._large_unlocked: research.is_unlocked", error)
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
                self.log.print(f"[tank_upgrade] Status: {text}")
        return text

    def _write_assignments(self, wanted):
        """Sets tank_assignments[id] = value for every (id, value) in wanted (None drops the entry). Skips the write when nothing differs."""
        stored = archive.get(TANK_ASSIGNMENTS_KEY, {})
        stored = stored if isinstance(stored, dict) else {}
        if all(stored.get(b_id) == value and (value is not None or b_id not in stored) for b_id, value in wanted.items()):
            return True

        def updater(current):
            current = dict(current) if isinstance(current, dict) else {}
            for b_id, value in wanted.items():
                if value is None:
                    current.pop(b_id, None)
                else:
                    current[b_id] = value
            return current
        ok = archive.transaction(TANK_ASSIGNMENTS_KEY, {}, updater)
        if ok:
            self.log.debug(f"[tank_upgrade] tank_assignments <- {wanted}")
        else:
            self.log.level("warn").print(f"[tank_upgrade] tank_assignments write failed ({wanted}); retrying next pass.")
        return ok

    # ------------------------------------------------------------ main step

    def step(self):
        """One non-blocking pass. Returns a one-line status."""
        swap = self._swap()
        enabled = is_upgrade_enabled()

        if swap and swap.get("state") == "blocked":
            return self._set_status(f"blocked ({swap.get('reason')}); delete fleet.upgrade['{SWAP_KEY}'] to retry")

        if swap and not enabled and swap.get("state") == "buying" and self._inventory_count(LARGE_TYPE_ID) <= 0:
            self._clear()
            self.log.print("[tank_upgrade] Switched off before buying: swap cancelled.")
            swap = None

        if swap:
            return self._set_status(self._advance(swap))

        if not enabled:
            return self._set_status("disabled")
        if not upgrade_phase_reached():
            return self._set_status("waiting for mining drills")
        if not self._large_unlocked():
            return self._set_status("Large Liquid Tank not researched")
        return self._set_status(self._start_next() or "liquid tanks up to date")

    # ------------------------------------------------------------ selection

    def _groups(self):
        """[(count, outpost_id, liquid, [(level, tank_id), ...])] of replaceable Liquid Tanks, one per outpost and liquid."""
        assignments = get_tank_assignments()
        groups = []
        for outpost in self._outposts():
            outpost_id = getattr(outpost, "id", "")
            by_liquid = {}
            for tank_id in self._ids_of(outpost, SMALL_TYPE_ID):
                assigned = assignments.get(tank_id, "")
                if assigned == RETIRING_ASSIGNMENT:
                    continue
                tank = _component(tank_id)
                liquid = _call(tank, "fluid", "", "_groups") or assigned
                if not liquid:
                    self.log.debug(f"[tank_upgrade] '{tank_id}' at '{outpost_id}': no latch, no assignment; skipped.")
                    continue
                by_liquid.setdefault(liquid, []).append((_call(tank, "level", 0.0, "_groups"), tank_id))
            for liquid, tanks in by_liquid.items():
                groups.append((len(tanks), outpost_id, liquid, sorted(tanks)))
        return groups

    def _start_next(self):
        groups = self._groups()
        if not groups:
            cash.release(CASH_CONSUMER)
            return None
        groups.sort(key=lambda g: (-g[0], g[1], g[2]))
        _, outpost_id, liquid, tanks = groups[0]
        self.log.debug(f"[tank_upgrade] Liquid Tank groups: {[(g[1], g[2], g[0]) for g in groups]}; picked '{outpost_id}' {liquid}.")

        price = self._price()
        swaps = sum(-(-g[0] // SWAP_RATIO) for g in groups)
        if self._inventory_count(LARGE_TYPE_ID) <= 0 and not cash.can_spend(CASH_CONSUMER, price, planned=swaps * price, label=f"{swaps} Large Liquid Tank(s)"):
            self.log.debug(f"[tank_upgrade] cash manager holds back {price} cr for '{outpost_id}' {liquid}; waiting.")
            return f"saving up ({self._credits()}/{price} cr)"

        old_ids = [tank_id for _, tank_id in tanks[:SWAP_RATIO]]
        self.log.debug(f"[tank_upgrade] Levels at '{outpost_id}': {tanks}; retiring the emptiest {old_ids}.")
        update_fleet_upgrade(lambda s: s.update({SWAP_KEY: {
            "state": "buying", "outpost": outpost_id, "liquid": liquid, "old_ids": old_ids,
            "removed": [], "to_sell": 0, "new_id": None, "attempts": 0,
        }}))
        self.log.print(f"[tank_upgrade] '{outpost_id}': replacing {liquid} tanks {old_ids} with one Large Liquid Tank.")
        return f"{outpost_id}: buying Large Liquid Tank"

    # ------------------------------------------------------------ swap

    def _advance(self, swap):
        """Runs states back to back until one has to wait, so the new tank is claimed right after deploy."""
        text = ""
        for _ in range(4):
            before = swap.get("state")
            text = self._advance_once(swap)
            swap = self._swap()
            if not swap or swap.get("state") in (before, "blocked"):
                return text
            self.log.debug(f"[tank_upgrade] '{before}' -> '{swap.get('state')}', continuing without a pause.")
        return text

    def _advance_once(self, swap):
        state = swap.get("state")
        outpost_id = swap.get("outpost")
        computer = _component("computer")
        if not computer or not hasattr(computer, "deploy"):
            return "no Ship Computer"
        self.log.debug(f"[tank_upgrade] Swap at '{outpost_id}': state '{state}'.")

        if state == "buying":
            if self._inventory_count(LARGE_TYPE_ID) <= 0:
                shop = _component("shop")
                price = self._price()
                if self._credits() < price:
                    return f"{outpost_id}: waiting for {price} cr"
                res = shop.buy(LARGE_TYPE_ID, 1) if shop else None
                status = getattr(res, "status", "no_shop")
                if status != "ok":
                    self.log.debug(f"[tank_upgrade] buy('{LARGE_TYPE_ID}'): {status} - {getattr(res, 'message', '')}")
                    return f"{outpost_id}: buy {status}, retrying"
                cash.spent(CASH_CONSUMER, price)
                self.log.print(f"[tank_upgrade] Bought a Large Liquid Tank ({price} cr).")
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
                        self.log.level("warn").print(f"[tank_upgrade] deploy('{LARGE_TYPE_ID}', '{outpost_id}') refused ({res.status}: {res.message}); swap blocked.")
                        return f"{outpost_id}: blocked ({res.status})"
                    if res.status == "no_kit":
                        self._patch(state="buying")
                    return f"{outpost_id}: deploy {res.status}"
                adopted = res.machine_id
            self._patch(state="draining", new_id=adopted)
            self.log.print(f"[tank_upgrade] Deployed '{adopted}' at '{outpost_id}'; draining {swap.get('old_ids')}.")
            return f"{outpost_id}: deployed {adopted}"

        if state == "draining":
            return self._drain(swap, computer)

        return f"{outpost_id}: unknown state {state!r}"

    def _drain(self, swap, computer):
        outpost_id = swap.get("outpost")
        new_id = swap.get("new_id")
        liquid = swap.get("liquid")
        removed = swap.get("removed") or []
        pending = [t for t in (swap.get("old_ids") or []) if t not in removed]

        wanted = {new_id: liquid}
        for tank_id in pending:
            wanted[tank_id] = RETIRING_ASSIGNMENT
        if not self._write_assignments(wanted):
            return f"{outpost_id}: tank_assignments write failed"

        self._sell_kits()
        if pending:
            return self._drain_one(pending[0], new_id, outpost_id, computer)

        self._write_assignments({tank_id: None for tank_id in swap.get("old_ids") or []})
        if int((self._swap() or {}).get("to_sell") or 0) > 0:
            return f"{outpost_id}: selling old Liquid Tank kits"
        self._clear()
        self.log.print(f"[tank_upgrade] Swap done at '{outpost_id}': {swap.get('old_ids')} -> '{new_id}' ({liquid}).")
        return f"{outpost_id}: {swap.get('old_ids')} -> {new_id} done"

    def _drain_one(self, old_id, new_id, outpost_id, computer):
        """One check on one old tank: keep new.liquid_in pulling from it, or remove it once empty."""
        old = _component(old_id)
        new = _component(new_id)
        port = getattr(new, "liquid_in", None) if new is not None else None
        if port is None:
            return f"{outpost_id}: '{new_id}' not found"
        connected = _call(port, "connected_id", "", "_drain_one")

        if old is not None and not _call(old, "is_empty", False, "_drain_one"):
            level = _call(old, "level", 0.0, "_drain_one")
            inflow = _call(old, "inflow_rate", 0.0, "_drain_one")
            if connected != old_id:
                res = port.connect(old_id)
                if res.status != "ok":
                    return self._refused(f"'{new_id}'.liquid_in.connect('{old_id}')", res, outpost_id)
                self.log.debug(f"[tank_upgrade] '{new_id}'.liquid_in -> '{old_id}' ({level:.0f} t left).")
            link = declared_connection_state(port)
            if link in BROKEN_CONNECTION_STATES:
                self.log.debug(f"[tank_upgrade] '{new_id}' <- '{old_id}' link state '{link}'.")
                return self._refused(f"link '{new_id}' <- '{old_id}'", None, outpost_id, reason=f"link_{link}")
            if int((self._swap() or {}).get("attempts") or 0):
                self._patch(attempts=0)
            new_full = _call(new, "is_full", False, "_drain_one")
            self.log.debug(f"[tank_upgrade] '{old_id}': {level:.1f} t, inflow {inflow:.0f} t/h, link '{link}', '{new_id}' full={new_full}.")
            note = " (new tank full)" if new_full else (f" (still fed {inflow:.0f} t/h)" if inflow > 0 else "")
            return f"{old_id}: draining, {level:.0f} t left{note}"

        if connected == old_id:
            _call(port, "disconnect", None, "_drain_one")
        res = computer.undeploy(old_id)
        if res.status in ("ok", "not_found"):
            def mark(s):
                swap = s.setdefault(SWAP_KEY, {})
                removed = swap.setdefault("removed", [])
                if old_id not in removed:
                    removed.append(old_id)
                    if res.status == "ok":
                        swap["to_sell"] = int(swap.get("to_sell") or 0) + 1
                swap["attempts"] = 0
            update_fleet_upgrade(mark)
            self._write_assignments({old_id: None})
            self._sell_kits()
            self.log.print(f"[tank_upgrade] '{old_id}' empty and undeployed.")
            return f"{old_id}: removed"
        self.log.debug(f"[tank_upgrade] undeploy('{old_id}'): {res.status} - {res.message}")
        if res.status in TRANSIENT_UNDEPLOY_STATUSES:
            return f"{old_id}: empty, waiting for Inventory room to take its kit back ({res.status})"
        if res.status == "cargo_present":
            return f"{old_id}: liquid slipped in before undeploy, draining again"
        return self._refused(f"undeploy('{old_id}')", res, outpost_id)

    def _refused(self, what, res, outpost_id, reason=None):
        """Counts a refusal; MAX_ATTEMPTS in a row blocks the swap."""
        reason = reason or getattr(res, "status", "refused")
        attempts = int((self._swap() or {}).get("attempts") or 0) + 1
        if attempts >= MAX_ATTEMPTS:
            self._patch(state="blocked", reason=reason, attempts=attempts)
            self.log.level("warn").print(f"[tank_upgrade] {what} refused {attempts}x ({reason}: {getattr(res, 'message', '')}); swap blocked.")
            return f"{outpost_id}: blocked ({reason})"
        self._patch(attempts=attempts)
        return f"{what}: {reason}, retrying"

    def _sell_kits(self):
        """Sells the Liquid Tank kits this swap got back from undeploy() (never the operator's spares)."""
        to_sell = int((self._swap() or {}).get("to_sell") or 0)
        if to_sell <= 0:
            return
        shop = _component("shop")
        res = shop.sell(SMALL_TYPE_ID, to_sell) if shop else None
        if res is not None and res.status == "ok":
            self._patch(to_sell=0)
            self.log.print(f"[tank_upgrade] Sold {to_sell} Liquid Tank kit(s) for {res.credits} cr.")
        else:
            self.log.debug(f"[tank_upgrade] sell('{SMALL_TYPE_ID}', {to_sell}): {getattr(res, 'status', 'no_shop')}; retrying next pass.")
