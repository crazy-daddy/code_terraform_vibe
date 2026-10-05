# Liquid Tank -> Large Liquid Tank upgrade (Phase 7, next to lib/warehouse_upgrade.py),
# run from the same Automation (automation/warehouse_upgrade_automation.py).
#
# Same gate as the warehouse upgrade (drone_upgrade.upgrades_active()), plus the
# Large Liquid Tank research and the cash manager's go-ahead (lib/cash.py
# can_spend("tank_upgrade")).
#
# One swap at a time, network-wide. A swap replaces up to SWAP_RATIO Liquid Tanks
# holding the same liquid at one outpost with ONE Large Liquid Tank (100 t each ->
# 1,000 t): leftovers are swapped too, so 7 tanks end up as 2 Large Liquid Tanks.
# A tank's liquid is its latch, else its fluid_routing.tank_assignments entry; a
# tank with neither is left alone, and so is an exotic one once Wildlife is complete
# (the Wildlife planner undeploys those). Biggest group first.
#
# Swap states and buy/deploy/sell steps: lib/building_swap_upgrade.py
# (fleet.upgrade["tank_swap"]).
#   draining  -> tank_assignments: new tank -> the liquid, old tanks -> "retiring"
#                (re-asserted every pass, which also replaces the blank "" entry
#                warn_about_unassigned_tanks() may add for the new tank). Routers
#                never pick a retiring tank, so producers move to the new one. The
#                new tank's liquid_in pulls each old tank dry in turn; an empty one
#                is disconnected, undeployed, its kit sold and its entry dropped.
#                Non-blocking: one check per pass.
#
# An old tank is undeployed only once is_empty(): undeploy() drops the liquid it
# holds (fluid never blocks undeploy). A drain that stops (new tank full, or a producer that
# can't reach the new tank still feeding the old one) just waits and says so in
# the status line.

from archive import archive
from fluid_routing import TANK_ASSIGNMENTS_KEY, RETIRING_ASSIGNMENT, get_tank_assignments, declared_connection_state, BROKEN_CONNECTION_STATES
from building_swap_upgrade import BuildingSwapUpgrader, TRANSIENT_UNDEPLOY_STATUSES
from swallow import call_or
from wildlife_common import wildlife_complete
from wildlife_data import EXOTIC_FLUIDS
import cash
from tree_console import method_block

SMALL_TYPE_ID = "liquid_tank"
SWAP_RATIO = 5                            # at most this many Liquid Tanks per Large Liquid Tank


class TankUpgrader(BuildingSwapUpgrader):
    """Liquid Tank group -> Large Liquid Tank swap. One instance, reused across cycles."""

    MODULE = "tank_upgrade"
    SMALL_TYPE_ID = SMALL_TYPE_ID
    LARGE_TYPE_ID = "bulk_liquid_reservoir"
    LARGE_RESEARCH_ID = "research_reservoir_engineering"
    LARGE_PRICE_FALLBACK = 15000              # docs/database/equipment_fluids.md
    CASH_CONSUMER = "tank_upgrade"
    SWAP_KEY = "tank_swap"
    STATUS_KEY = "tank_status"
    SMALL_NAME = "Liquid Tank"
    LARGE_NAME = "Large Liquid Tank"
    UP_TO_DATE = "liquid tanks up to date"

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

    # ------------------------------------------------------------ selection

    def _groups(self):
        """[(count, outpost_id, liquid, [(level, tank_id), ...])] of replaceable Liquid Tanks, one per outpost and liquid."""
        assignments = get_tank_assignments()
        skip = EXOTIC_FLUIDS if wildlife_complete() else ()
        groups = []
        for outpost in self._outposts():
            outpost_id = getattr(outpost, "id", "")
            by_liquid = {}
            for tank_id in self._ids_of(outpost, SMALL_TYPE_ID):
                assigned = assignments.get(tank_id, "")
                if assigned == RETIRING_ASSIGNMENT:
                    continue
                tank = self._component(tank_id)
                liquid = call_or("tank_upgrade._groups", tank, "fluid", "") or assigned
                if not liquid:
                    self.log.debug(f"[tank_upgrade] '{tank_id}' at '{outpost_id}': no latch, no assignment; skipped.")
                    continue
                if liquid in skip:
                    continue
                by_liquid.setdefault(liquid, []).append((call_or("tank_upgrade._groups", tank, "level", 0.0), tank_id))
            for liquid, tanks in by_liquid.items():
                groups.append((len(tanks), outpost_id, liquid, sorted(tanks)))
        return groups

    def _start_next(self):
        self.log.start("[tank_upgrade] _start_next", level="debug")
        groups = self._groups()
        if not groups:
            cash.release(self.CASH_CONSUMER)
            self.log.end()
            return None
        groups.sort(key=lambda g: (-g[0], g[1], g[2]))
        _, outpost_id, liquid, tanks = groups[0]
        self.log.debug(f"Liquid Tank groups: {[(g[1], g[2], g[0]) for g in groups]}; picked '{outpost_id}' {liquid}.")

        swaps = sum(-(-g[0] // SWAP_RATIO) for g in groups)
        if not self._can_buy(outpost_id, swaps, f" {liquid}"):
            _ret = f"saving up ({self._credits()}/{self._price()} cr)"
            self.log.end()
            return _ret

        old_ids = [tank_id for _, tank_id in tanks[:SWAP_RATIO]]
        self.log.debug(f"Levels at '{outpost_id}': {tanks}; retiring the emptiest {old_ids}.")
        self._begin(outpost_id, old_ids, liquid=liquid)
        self.log.print(f"[tank_upgrade] '{outpost_id}': replacing {liquid} tanks {old_ids} with one Large Liquid Tank.")
        self.log.end()
        return f"{outpost_id}: buying Large Liquid Tank"

    # ------------------------------------------------------------ swap

    def _drain(self, swap, computer: "Computer"):
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

    @method_block("[tank_upgrade] _drain_one")
    def _drain_one(self, old_id, new_id, outpost_id, computer: "Computer"):
        """One check on one old tank: keep new.liquid_in pulling from it, or remove it once empty."""
        old = self._component(old_id)
        new = self._component(new_id)
        port = getattr(new, "liquid_in", None) if new is not None else None
        if port is None:
            return f"{outpost_id}: '{new_id}' not found"
        connected = call_or("tank_upgrade._drain_one", port, "connected_id", "")

        if old is not None and not call_or("tank_upgrade._drain_one", old, "is_empty", False):
            level = call_or("tank_upgrade._drain_one", old, "level", 0.0)
            inflow = call_or("tank_upgrade._drain_one", old, "inflow_rate", 0.0)
            if connected != old_id:
                res = port.connect(old_id)
                if res.status != "ok":
                    return self._refused(f"'{new_id}'.liquid_in.connect('{old_id}')", res, outpost_id)
                self.log.debug(f"'{new_id}'.liquid_in -> '{old_id}' ({level:.0f} t left).")
            link = declared_connection_state(port)
            if link in BROKEN_CONNECTION_STATES:
                self.log.debug(f"'{new_id}' <- '{old_id}' link state '{link}'.")
                return self._refused(f"link '{new_id}' <- '{old_id}'", None, outpost_id, reason=f"link_{link}")
            if int((self._swap() or {}).get("attempts") or 0):
                self._patch(attempts=0)
            new_full = call_or("tank_upgrade._drain_one", new, "is_full", False)
            self.log.debug(f"'{old_id}': {level:.1f} t, inflow {inflow:.0f} t/h, link '{link}', '{new_id}' full={new_full}.")
            note = " (new tank full)" if new_full else (f" (still fed {inflow:.0f} t/h)" if inflow > 0 else "")
            return f"{old_id}: draining, {level:.0f} t left{note}"

        if connected == old_id:
            call_or("tank_upgrade._drain_one", port, "disconnect", None)
        res = computer.undeploy(old_id)
        if res.status in ("ok", "not_found"):
            self._mark_removed(old_id, res.status)
            self._write_assignments({old_id: None})
            self._sell_kits()
            self.log.print(f"[tank_upgrade] '{old_id}' empty and undeployed.")
            return f"{old_id}: removed"
        self.log.debug(f"undeploy('{old_id}'): {res.status} - {res.message}")
        if res.status in TRANSIENT_UNDEPLOY_STATUSES:
            return f"{old_id}: empty, waiting for Inventory room to take its kit back ({res.status})"
        if res.status == "cargo_present":
            return f"{old_id}: liquid slipped in before undeploy, draining again"
        return self._refused(f"undeploy('{old_id}')", res, outpost_id)
