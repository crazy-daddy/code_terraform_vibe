# Harvester ability: field machines for the full (automated) layout. Composed
# by FieldKeeperController (lib/field_keeper.py); calls only the hub
# (lib/harvester_hub.py: layout state, deployed-machine reads, act/stage), the
# heat model and HarvesterController, never another ability mixin.
#
# The full layout (field_layout.FULL_LAYOUT, taken once Field Automation is
# researched) reserves one cell per machine, stored as
# plant.layout["reserved"] = {sector: kind}. The starter layout has none:
# machines unlocked before automation only save hand-care time, which isn't
# worth a rebuild.
#
#   1. kit order (Fabricator kits: Grow Lamp, Sprinkler, Dispenser): a
#      standing order under requester "field_keeper" in
#      the order book (production.set_order(), UPGRADE band). It is a
#      stock target, capped at KIT_STOCK_CAP per kit so Warehouses don't fill
#      up with kits. Pre-ordered from PREORDER_MIN_KM2 Plants km² on, for the
#      full layout the switch will build, so kits are waiting when it comes.
#   2. Crop Automator kits come from the Shop (30,000 cr each): bought one at
#      a time while one is missing and none is at home, once the cash
#      manager grants it (lib/cash.py can_spend("crop_automator")). The count still missing is
#      published in plant.status ("automators_wanted").
#   3. deploy (full layout only): with a kit at home, drive to the cell,
#      collect a loose item there if any, stage the kit into Inventory and
#      deploy() it. The Harvester can drive over machines.
#   4. remove strays (full layout only): a field machine on a cell the
#      layout doesn't reserve for its kind (left over from an older layout)
#      is left alone until it holds no items (undeploy() refuses stored
#      items, and eject() is self-only): its own script ejects its input to
#      Inventory (field_provider / crop_automator, stray branch; a stopped
#      script is restarted via run_control.start() for that), and Forage in
#      an automator's output drains through storage.take_item(). Re-checked
#      every DEPLOY_FAIL_COOLDOWN_TICKS. Once empty, the Harvester drives
#      there, stops its script (run_control.stop()) and undeploy()s it; the
#      kit goes back to Inventory. No Crop Automator kit is bought while a
#      stray one is still out.
#
# Deployed machines are read from outpost.harvesting_machines() (type and
# position), falling back to Cell.status == "provider". A new machine has no
# script until devtools/scripts_sync.py (or the operator) fills its slot:
# harvesting/grow_lamp.py, sprinkler.py, dispenser.py (lib/field_provider.py)
# or crop_automator.py (lib/crop_automator.py).

from typing import TYPE_CHECKING

import cash
import field_layout
from game_clock import now_tick
from harvester_hub import AUTOMATOR_KIT, deployed_machine_ids, desired_chunks, field_fill
from plant_terraformer_common import plants_km2
from production import order_levels, set_order
from swallow import swallowed

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

ORDER_REQUESTER = "field_keeper"  # listed in production.STANDING_ORDER_REQUESTERS

MACHINE_KITS = {
    "grow_lamp": "grow_lamp_kit",
    "sprinkler": "sprinkler_kit",
    "dispenser": "dispenser_kit",
    "crop_automator": AUTOMATOR_KIT,
}
# Kits the Fabricator makes (the Crop Automator kit is a Shop item).
FABRICATED_KITS = ("grow_lamp_kit", "sprinkler_kit", "dispenser_kit")
# At most this many of each kit are ordered into stock at a time.
KIT_STOCK_CAP = 10
# Kits are pre-ordered for the full layout from this Plants km² on (Field
# Automation unlocks at 620,000), so they don't compete with other
# production too early.
PREORDER_MIN_KM2 = 550000
# Cell statuses a machine can go on (a loose item is collected first; a
# plant there is stale and swept, harvester_planting.stale_targets()).
DEPLOY_STATUSES = ("empty", "unknown", "item")
# A cell whose deploy just failed is skipped this long (~5 min).
DEPLOY_FAIL_COOLDOWN_TICKS = 3000
CASH_CONSUMER = "crop_automator"  # lib/cash.py consumer id
AUTOMATOR_PRICE_FALLBACK = 30000


def shop_price(item_id, fallback):
    try:
        shop = get_component("shop")
        for entry in shop.get_catalogue() if shop else []:
            if entry.id == item_id:
                return int(entry.cost)
    except Exception as error:
        swallowed("harvester_machines.shop_price: get_component", error)
    return fallback


class HarvesterMachinesMixin:
    """Orders field-machine kits and deploys them on the full layout's reserved cells."""

    @property
    def _host(self) -> "FieldKeeperController":
        return self  # type: ignore[return-value]

    def missing_machines(self, cells, reserved=None):
        """
        {sector: kind} of reserved cells of a deployable kind with no machine
        yet. Memoised per step on the reserved dict, the deployed machines and
        the deployable kits (and `cells`, when the machines are unreadable);
        the returned dict is shared and read-only.
        """
        kits = self._host.deployable_kits()
        reserved = self._host.reserved if reserved is None else reserved
        deployed = self._host.step_machines()
        memo = getattr(self, "_missing_memo", None)
        if memo is not None and memo[0] is reserved and memo[1] is deployed and memo[2] is kits and (deployed is not None or memo[3] is cells):
            return memo[4]
        out = {}
        for sector, kind in (reserved or {}).items():
            kit = MACHINE_KITS.get(kind)
            if not kit or kit not in kits:
                continue
            if deployed is not None:
                if deployed.get(sector) == kind:
                    continue
            elif getattr(cells.get(sector), "status", "unknown") == "provider":
                continue
            out[sector] = kind
        self._missing_memo = (reserved, deployed, kits, cells, out)
        return out

    def kit_order_reserved(self):
        """Reserved machine cells the kit order is for: the full layout, or its pre-order."""
        if self._host.layout_mode == "full":
            return self._host.reserved or {}
        km2 = plants_km2()
        if km2 is None or km2 < PREORDER_MIN_KM2:
            return {}
        fill = field_fill()
        _, reserved, _ = field_layout.full_layout(desired_chunks(fill), fill)
        return reserved

    def publish_kit_order(self, cells):
        """Standing Fabricator order: missing kits, at most KIT_STOCK_CAP of each in stock."""
        missing = self.missing_machines(cells, self.kit_order_reserved())
        order = {}
        for kind in missing.values():
            kit = MACHINE_KITS[kind]
            if kit in FABRICATED_KITS:
                order[kit] = order.get(kit, 0) + 1
        order = {kit: min(n, KIT_STOCK_CAP) for kit, n in order.items()}
        set_order(ORDER_REQUESTER, {kit: order_levels(need=qty) for kit, qty in order.items()})
        wanted = sum(1 for k in missing.values() if k == "crop_automator")
        have = self._host.stock_count(MACHINE_KITS["crop_automator"]) if wanted else 0
        # A stray automator's kit comes back on removal: reuse it before buying.
        strays = "crop_automator" in self.stray_machines(ignore_cooldown=True).values()
        if wanted > have and have == 0 and not strays and self._host.layout_mode == "full":
            self.buy_automator_kit(wanted)
        elif not wanted:
            cash.release(CASH_CONSUMER)
        return order, wanted

    def buy_automator_kit(self, wanted):
        """Buys one Crop Automator kit from the Shop once the cash manager grants it."""
        h = self._host
        kit = MACHINE_KITS["crop_automator"]
        price = shop_price(kit, AUTOMATOR_PRICE_FALLBACK)
        if not cash.can_spend(CASH_CONSUMER, price, planned=wanted * price, label=f"{wanted} Crop Automator(s)"):
            h.log.debug(f"[{h.name}] {wanted} Crop Automator(s) missing; {cash.balance()} cr, cash manager holds {price} cr back, saving up.")
            return False
        h.log.start(f"[{h.name}] Buying a Crop Automator kit ({price} cr)")
        bought = self._buy_kit(kit, price, wanted)
        h.log.end("Bought" if bought else "Not bought")
        return bought

    def _buy_kit(self, kit, price, wanted):
        h = self._host
        h.log.start("_buy_kit", level="debug")
        try:
            shop = get_component("shop")
            res = shop.buy(kit, 1) if shop else None
        except Exception as error:
            res = None
            h.log.debug(f"[{h.name}] buy('{kit}') raised {error}.")
        status = getattr(res, "status", "no_shop")
        if status != "ok":
            h.log.debug(f"[{h.name}] buy('{kit}') -> {status}: {getattr(res, 'message', '')}")
            h.log.end()
            return False
        cash.spent(CASH_CONSUMER, price)
        h.stock_memo.pop(kit, None)
        h.log.print(f"[{h.name}] Bought a Crop Automator kit ({price} cr, {wanted - 1} more to go).")
        h.log.end()
        return True

    def _deploy_failures(self):
        """{sector: tick of last failed deploy}, in memory only."""
        if not hasattr(self, "_deploy_fail_ticks"):
            self._deploy_fail_ticks = {}
        return self._deploy_fail_ticks

    def deploy_targets(self, cells):
        """{sector: kind} of reserved cells ready for a machine whose kit is at home (full layout only)."""
        if self._host.layout_mode != "full":
            return {}
        now = now_tick()
        failed = self._deploy_failures()
        out = {}
        for sector, kind in self.missing_machines(cells).items():
            if now - failed.get(sector, -DEPLOY_FAIL_COOLDOWN_TICKS) < DEPLOY_FAIL_COOLDOWN_TICKS:
                continue
            if getattr(cells.get(sector), "status", "unknown") not in DEPLOY_STATUSES:
                continue
            if self._host.stock_count(MACHINE_KITS[kind]) < 1:
                continue
            out[sector] = kind
        return out

    def stray_machines(self, ignore_cooldown=False):
        """
        {sector: kind} of deployed field machines the full layout doesn't
        reserve for their kind, outside their removal cooldown unless
        `ignore_cooldown`. Empty outside the full layout.
        """
        h = self._host
        if h.layout_mode != "full":
            return {}
        deployed = self._host.step_machines() or {}
        reserved = h.reserved or {}
        now = now_tick()
        failed = {} if ignore_cooldown else self._deploy_failures()
        strays = {s: k for s, k in deployed.items() if reserved.get(s) != k and now - failed.get(s, -DEPLOY_FAIL_COOLDOWN_TICKS) >= DEPLOY_FAIL_COOLDOWN_TICKS}
        if strays and not ignore_cooldown:
            ids = deployed_machine_ids() or {}
            for s in list(strays):
                machine_id = ids.get(s, (None, None))[1]
                held_out, held_in = self.items_held(machine_id) if machine_id else (0, 0)
                if held_out or held_in:
                    # undeploy() refuses stored items, and eject() is self-only: the
                    # machine's own script empties its input (field_provider /
                    # crop_automator, stray branch); Forage drains through
                    # storage.take_item(). A stopped script is restarted to do it.
                    self.ensure_running(machine_id)
                    h.log.debug(f"[{h.name}] Stray {strays[s]} at {s} still holds {held_out} output / {held_in} input; removal waits.")
                    failed[s] = now
                    del strays[s]
        return strays

    def items_held(self, machine_id):
        """(output, input) item counts of a field machine (remote reads); 0 for a missing or unreadable port."""
        machine = get_component(machine_id)
        out = []
        for name in ("output", "input"):
            port = getattr(machine, name, None) if machine is not None else None
            try:
                out.append(int(port.count()) if port is not None else 0)
            except Exception as error:
                swallowed("harvester_machines.HarvesterMachinesMixin.items_held: port.count", error)
                out.append(0)
        return out[0], out[1]

    def ensure_running(self, machine_id):
        """Starts a stray machine's stopped script so it can empty itself (run_control)."""
        h = self._host
        run = get_component("run_control")
        if run is None or run.is_running(machine_id):
            return
        res = run.start(machine_id)
        h.log.debug(f"[{h.name}] run_control.start('{machine_id}') -> {getattr(res, 'status', '?')} (stray must empty itself).")

    def remove_here(self, kind):
        """Stops and undeploys the (emptied) stray field machine in the current cell."""
        h = self._host
        h.log.start("remove_here", level="debug")
        here = h.get_position()
        machine_id = (deployed_machine_ids() or {}).get(here, (None, None))[1]
        self._host.forget_machines()
        if not machine_id:
            h.log.debug(f"[{h.name}] No field machine at {here}; stray {kind} already gone.")
            h.log.end()
            return False
        held_out, held_in = self.items_held(machine_id)
        if held_out or held_in:
            h.log.debug(f"[{h.name}] Stray {kind} at {here} holds {held_out} output / {held_in} input again; removal waits.")
            self.ensure_running(machine_id)
            self._deploy_failures()[here] = now_tick()
            h.log.end()
            return False
        run = get_component("run_control")
        if run is not None and run.is_running(machine_id):
            res = run.stop(machine_id)
            h.log.debug(f"[{h.name}] run_control.stop('{machine_id}') -> {getattr(res, 'status', '?')}.")
        h.store_held_if_any()
        res = h.act("undeploy")
        status = getattr(res, "status", "?")
        if status == "ok":
            h.log.print(f"[{h.name}] Removed stray {kind} at {here} (not in the layout); kit back to Inventory.")
            h.note_action(f"undeploy {kind}@{here}")
            h.log.end()
            return True
        h.log.level("warn").print(f"[{h.name}] undeploy {kind} at {here} -> {status}: {getattr(res, 'message', '')}")
        self._deploy_failures()[here] = now_tick()
        h.log.end()
        return False

    def deploy_here(self, kind):
        """Deploys kind's kit in the current cell (clears a loose item there first: clear_here())."""
        h = self._host
        here = h.get_position()
        h.log.start(f"[{h.name}] Deploying {kind} at {here}")
        deployed = self._deploy(kind, here)
        h.log.end(f"Deployed {kind}" if deployed else f"Deploy of {kind} failed")
        return deployed

    def _deploy(self, kind, here):
        h = self._host
        kit = MACHINE_KITS[kind]
        if getattr(h.harvester.cell(here), "status", "") == "item":
            h.clear_here()
        h.store_held_if_any()
        if not h.stage(kit):
            self._deploy_failures()[here] = now_tick()
            return False
        res = h.act("deploy", kit)
        status = getattr(res, "status", "?")
        if status == "ok":
            h.log.print(f"[{h.name}] Deployed {kind} at {here}. Its script slot still needs harvesting/{kind}.py (scripts_sync).")
            h.note_action(f"deploy {kind}@{here}")
            h.stock_memo.pop(kit, None)
            self._host.forget_machines()
            return True
        h.log.level("warn").print(f"[{h.name}] deploy('{kit}') at {here} -> {status}: {getattr(res, 'message', '')}")
        self._deploy_failures()[here] = now_tick()
        return False
