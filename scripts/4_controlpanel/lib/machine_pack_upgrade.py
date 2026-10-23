# Machine tier packs (§2k-6): crafts Mk II/III upgrade packs and applies them
# to deployed machines, run by the builder_automation.py Automation.
#
#   - Fabricators and Smelters: one step of PACK_LADDER at a time, in order
#     (Fabricators first: they craft every later pack faster). The step's pack
#     is ordered through the order book (REQUESTER, UPGRADE band) and applied
#     from Inventory with computer.upgrade() as soon as one is there; the
#     machine keeps its id, recipe, cargo, scripts and batch progress.
#   - Oil Pumps: a field structure, upgraded by a Pioneer. One
#     construction_blueprint.plan_upgrade() at a time; the Pioneer constructor
#     runs the "upgrade" blueprint like any other, and the pack reaches the
#     Fabricators as blueprint demand (production_cascade.blueprint_required_items()).
#
# Gate: the FLEET card's auto-upgrade switch (drone_upgrade.is_upgrade_enabled())
# and the pack's Fabricator recipe being unlocked. A refused machine (e.g.
# not_enough_power: Mk II draws 1.5x, Mk III 3x) sits out REFUSED_RETRY_TICKS,
# so one weak subnet doesn't hold up the rest of the ladder.
#
# State: fleet.upgrade[STATE_KEY] = {"refused": {machine_id: [status, tick]}},
# fleet.upgrade[STATUS_KEY] = one status line.

import building_ops
from components import component, machine_tier
from drone_upgrade import fleet_upgrade_state, is_upgrade_enabled, update_fleet_upgrade
from fluid_routing import poi_extractor_ids
from parking_client import wake_role
from production import clear_order, discover_fabricator_ids, discover_smelter_ids, fabricator_unlocked_outputs, order_levels, set_order
from storage import inventory_count
from swallow import swallowed
from tree_console import TreeConsole

# Order-book requester (production.STANDING_ORDER_REQUESTERS).
REQUESTER = "machine_upgrade"
STATE_KEY = "machine_packs"
STATUS_KEY = "machine_packs_status"
# (machine kind, target tier, pack), applied in this order. Mk II on every
# machine before any Mk III: a Mk III pack needs a Mk II machine.
PACK_LADDER = (
    ("fabricator", 2, "fabricator_upgrade_pack_mk2"),
    ("smelter", 2, "smelter_upgrade_pack_mk2"),
    ("fabricator", 3, "fabricator_upgrade_pack_mk3"),
    ("smelter", 3, "smelter_upgrade_pack_mk3"),
)
OIL_PUMP_PACK = "oil_pump_upgrade_pack_mk2"
OIL_PUMP_TIER = 2
# Packs ordered ahead of the machines still to do (each Mk II pack is ~0.5 h of a Fabricator).
ORDER_BATCH = 2
# Ticks a refused machine sits out before the next try (~30 min).
REFUSED_RETRY_TICKS = 18000
# upgrade() answers that only mean "not right now": retried next pass, no sit-out.
WAIT_STATUSES = ("under_construction", "item_not_in_inventory")
# plan_upgrade() answer when the pump already has an upgrade or dismantling job.
PLAN_CLAIMED = "target_claimed"


class MachinePackUpgrader:
    """Orders and applies Fabricator/Smelter tier packs, plans Oil Pump pack installs. One instance, reused."""

    def __init__(self):
        self.log = TreeConsole(module="machine_upgrade")

    # ------------------------------------------------------------ state

    def _refused(self, now):
        """{machine_id: status} of machines still sitting out a refusal."""
        refused = (fleet_upgrade_state().get(STATE_KEY) or {}).get("refused") or {}
        return {k: v[0] for k, v in refused.items() if isinstance(v, list) and len(v) == 2 and now - v[1] < REFUSED_RETRY_TICKS}

    def _refuse(self, machine_id, status, now):
        def mark(s):
            entry = s.setdefault(STATE_KEY, {})
            refused = entry.setdefault("refused", {})
            for k in [k for k, v in refused.items() if not isinstance(v, list) or len(v) != 2 or now - v[1] >= REFUSED_RETRY_TICKS]:
                refused.pop(k, None)
            refused[machine_id] = [status, now]

        update_fleet_upgrade(mark)

    def _set_status(self, text):
        if fleet_upgrade_state().get(STATUS_KEY) != text:
            update_fleet_upgrade(lambda s: s.update({STATUS_KEY: text}))
            self.log.print(f"[machine_upgrade] Status: {text}")
        return text

    # ------------------------------------------------------------ main step

    def step(self, now):
        """One pass. Returns a one-line status."""
        if not is_upgrade_enabled():
            clear_order(REQUESTER)
            return self._set_status("disabled")
        computer = component("computer")
        if not computer or not hasattr(computer, "upgrade"):
            return self._set_status("no Ship Computer")
        unlocked = fabricator_unlocked_outputs()
        refused = self._refused(now)
        text = self._step_factories(computer, unlocked, refused, now)
        pump_text = self._step_pumps(unlocked, refused, now)
        return self._set_status(f"{text}; {pump_text}" if pump_text else text)

    def _below(self, kind, tier, refused):
        """Ids of `kind` machines one tier below `tier`, refused ones left out."""
        ids = discover_fabricator_ids() if kind == "fabricator" else discover_smelter_ids()
        return [i for i in ids if i not in refused and machine_tier(i) == tier - 1]

    def _step_factories(self, computer: "Computer", unlocked, refused, now):
        for kind, tier, pack in PACK_LADDER:
            if pack not in unlocked and inventory_count(pack) <= 0:
                continue
            todo = self._below(kind, tier, refused)
            # A machine below tier - 1 (Mk I while this is the Mk III step) is
            # the earlier step's; one at tier - 1 waits for this one.
            if not todo:
                continue
            for machine_id in list(todo):
                if inventory_count(pack) <= 0:
                    break
                if self._apply(computer, pack, machine_id, now):
                    todo.remove(machine_id)
            if not todo or pack not in unlocked:
                continue  # a leftover pack applied; can't craft more
            need = min(len(todo), ORDER_BATCH) - inventory_count(pack)
            if need > 0:
                set_order(REQUESTER, {pack: order_levels(need=need)})
            self.log.debug(f"[machine_upgrade] {kind} Mk {tier}: {len(todo)} left ({todo}); ordered {max(need, 0)} '{pack}'.")
            return f"{kind} Mk {tier}: {len(todo)} left, waiting for {pack}"
        clear_order(REQUESTER)
        return "machines up to date"

    def _apply(self, computer: "Computer", pack, machine_id, now):
        """computer.upgrade(pack, machine_id); True when the machine is done (ok or already at the tier)."""
        status, message = building_ops.upgrade(pack, machine_id, computer)
        if status == "ok":
            self.log.print(f"[machine_upgrade] '{machine_id}' upgraded with '{pack}'.")
            return True
        if status == "tier_too_high":
            return True
        if status not in WAIT_STATUSES and status not in building_ops.CALL_FAILED_STATUSES:
            self._refuse(machine_id, status, now)
            self.log.level("warn").print(f"[machine_upgrade] upgrade('{pack}', '{machine_id}') refused ({status}: {message}); retry in {REFUSED_RETRY_TICKS} ticks.")
        return False

    # ------------------------------------------------------------ oil pumps

    def _step_pumps(self, unlocked, refused, now):
        """Plans one Oil Pump pack install at a time; "" when there is nothing to do."""
        if OIL_PUMP_PACK not in unlocked:
            return ""
        pumps = [i for i in poi_extractor_ids(("oil_pump",)) if i not in refused and machine_tier(i) < OIL_PUMP_TIER]
        if not pumps:
            return ""
        bp = component("construction_blueprint")
        if bp is None:
            return ""
        try:
            jobs = list(bp.pending_constructions()) + list(bp.paused_constructions()) + list(bp.active_constructions())
        except Exception as error:
            swallowed("machine_pack_upgrade._step_pumps: construction lists", error)
            return ""
        if any(getattr(job, "kind", None) == "upgrade" for job in jobs):
            return f"oil pump Mk II: install planned, {len(pumps)} below Mk II"
        pump_id = pumps[0]
        try:
            res = bp.plan_upgrade(OIL_PUMP_PACK, pump_id)
        except Exception as error:
            swallowed("machine_pack_upgrade._step_pumps: plan_upgrade", error)
            return ""
        if res.status == "ok":
            self.log.print(f"[machine_upgrade] Planned the '{OIL_PUMP_PACK}' install on '{pump_id}' ({res.blueprint_ids}).")
            wake_role("builder", f"new construction job: {OIL_PUMP_PACK}")
        elif res.status != PLAN_CLAIMED:
            self._refuse(pump_id, res.status, now)
            self.log.level("warn").print(f"[machine_upgrade] plan_upgrade('{OIL_PUMP_PACK}', '{pump_id}') refused ({res.status}: {res.message}); retry in {REFUSED_RETRY_TICKS} ticks.")
        return f"oil pump Mk II: {len(pumps)} below Mk II"
