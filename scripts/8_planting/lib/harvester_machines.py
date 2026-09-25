# Harvester mixin: field machines for the full (automated) layout. Composed
# by FieldKeeperController (lib/field_keeper.py).
#
# The full layout (field_layout.FULL_LAYOUT, taken once Field Automation is
# researched) reserves one cell per machine, stored as
# plant.layout["reserved"] = {sector: kind}. The starter layout has none:
# machines unlocked before automation only save hand-care time, which isn't
# worth a rebuild.
#
#   1. kit order (Fabricator kits: Grow Lamp, Sprinkler, Dispenser): a
#      standing order under requester "field_keeper" in
#      fabricator.upgrade_orders (production.set_upgrade_order()). It is a
#      stock target, capped at KIT_STOCK_CAP per kit so Warehouses don't fill
#      up with kits. Pre-ordered from PREORDER_MIN_KM2 Plants km² on, for the
#      full layout the switch will build, so kits are waiting when it comes.
#   2. Crop Automator kits come from the Shop (30,000 cr each): bought one at
#      a time while one is missing and none is at home, keeping
#      AUTOMATOR_CREDIT_RESERVE credits back. The count still missing is
#      published in plant.status ("automators_wanted").
#   3. deploy (full layout only): with a kit at home, drive to the cell,
#      collect a loose item there if any, stage the kit into Inventory and
#      deploy() it. The Harvester can drive over machines.
#
# Deployed machines are read from outpost.harvesting_machines() (type and
# position), falling back to Cell.status == "provider". A new machine has no
# script until devtools/scripts_sync.py (or the operator) fills its slot:
# harvesting/grow_lamp.py, sprinkler.py, dispenser.py (lib/field_provider.py)
# or crop_automator.py (lib/crop_automator.py).

import field_layout
from production import set_upgrade_order
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

ORDER_REQUESTER = "field_keeper"   # listed in production.STANDING_ORDER_REQUESTERS

MACHINE_KITS = {
    "grow_lamp": "grow_lamp_kit",
    "sprinkler": "sprinkler_kit",
    "dispenser": "dispenser_kit",
    "crop_automator": "crop_automator_kit",
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
# plant there is uprooted by the clear step, harvester_planting.clear_targets()).
DEPLOY_STATUSES = ("empty", "unknown", "item")
# A cell whose deploy just failed is skipped this long (~5 min).
DEPLOY_FAIL_COOLDOWN_TICKS = 3000
# Crop Automator kits are bought only while credits stay above price + this.
AUTOMATOR_CREDIT_RESERVE = 100000
AUTOMATOR_PRICE_FALLBACK = 30000
# deployables() is research state: re-read this often.
DEPLOYABLES_REFRESH_TICKS = 3000


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception:
        return 0


def plants_km2():
    """Permanent Plants km² from the Plants Sensor, or None when there is none."""
    try:
        sensor = get_component("plants_sensor")
        return float(sensor.get_value()) if sensor else None
    except Exception:
        return None


def credits():
    try:
        commander = get_component("commander")
        return int(commander.get_credits()) if commander else 0
    except Exception:
        return 0


def shop_price(item_id, fallback):
    try:
        shop = get_component("shop")
        for entry in shop.get_catalogue() if shop else []:
            if entry.id == item_id:
                return int(entry.cost)
    except Exception:
        pass
    return fallback


def deployed_machines():
    """{sector: kind} of the field machines on the home field, or None if unreadable."""
    try:
        network = get_component("outpost_network")
        home = network.home() if network and hasattr(network, "home") else None
        if home is None and network:
            home = next((o for o in network.outposts() if getattr(o, "is_home", False)), None)
        if home is None:
            return None
        return {m.position: m.type_id for m in home.harvesting_machines()}
    except Exception:
        return None


class HarvesterMachinesMixin:
    """Orders field-machine kits and deploys them on the full layout's reserved cells."""

    @property
    def _host(self) -> "FieldKeeperController":
        return self  # type: ignore[return-value]

    def deployable_kits(self):
        """Kit ids the Harvester can deploy (research), cached."""
        now = _now_tick()
        cache = getattr(self, "_deployables_cache", None)
        if cache is None or now - cache[0] >= DEPLOYABLES_REFRESH_TICKS:
            try:
                kits = list(self._host.harvester.deployables() or [])
            except Exception:
                kits = []
            cache = (now, kits)
            self._deployables_cache = cache
            self._host.log.debug(f"[{self._host.name}] deployables(): {kits}.")
        return cache[1]

    def automation_unlocked(self):
        """True once Field Automation is researched (Crop Automator kit deployable)."""
        return MACHINE_KITS["crop_automator"] in self.deployable_kits()

    def step_machines(self):
        """deployed_machines(), read once per step (field_keeper clears step_machine_map)."""
        if getattr(self, "step_machine_map", None) is None:
            self.step_machine_map = deployed_machines()
        return self.step_machine_map

    def missing_machines(self, cells, reserved=None):
        """{sector: kind} of reserved cells of a deployable kind with no machine yet."""
        kits = self.deployable_kits()
        reserved = self._host.reserved if reserved is None else reserved
        deployed = self.step_machines()
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
        return out

    def deployed_automators(self):
        """Sectors of the Crop Automators on the field."""
        deployed = self.step_machines() or {}
        return [s for s, k in deployed.items() if k == "crop_automator"]

    def automated_cells(self):
        """Sectors a deployed Crop Automator serves (its jobs, not the Harvester's)."""
        out = set()
        for ca in self.deployed_automators():
            out |= set(field_layout.automator_area(ca))
        return out

    def kit_order_reserved(self):
        """Reserved machine cells the kit order is for: the full layout, or its pre-order."""
        if self._host.layout_mode == "full":
            return self._host.reserved or {}
        km2 = plants_km2()
        if km2 is None or km2 < PREORDER_MIN_KM2:
            return {}
        fill = self._host.field_fill()
        _, reserved, _ = field_layout.full_layout(self._host.desired_chunks(fill), fill)
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
        set_upgrade_order(ORDER_REQUESTER, order)
        wanted = sum(1 for k in missing.values() if k == "crop_automator")
        have = self._host.stock_count(MACHINE_KITS["crop_automator"]) if wanted else 0
        if wanted > have and have == 0 and self._host.layout_mode == "full":
            self.buy_automator_kit(wanted)
        return order, wanted

    def buy_automator_kit(self, wanted):
        """Buys one Crop Automator kit from the Shop if credits stay above the reserve."""
        h = self._host
        kit = MACHINE_KITS["crop_automator"]
        price = shop_price(kit, AUTOMATOR_PRICE_FALLBACK)
        have_cr = credits()
        if have_cr < price + AUTOMATOR_CREDIT_RESERVE:
            h.log.debug(f"[{h.name}] {wanted} Crop Automator(s) missing; {have_cr} cr < {price} + reserve {AUTOMATOR_CREDIT_RESERVE}, saving up.")
            return False
        try:
            shop = get_component("shop")
            res = shop.buy(kit, 1) if shop else None
        except Exception as error:
            res = None
            h.log.debug(f"[{h.name}] buy('{kit}') raised {error}.")
        status = getattr(res, "status", "no_shop")
        if status != "ok":
            h.log.debug(f"[{h.name}] buy('{kit}') -> {status}: {getattr(res, 'message', '')}")
            return False
        h.stock_memo.pop(kit, None)
        h.log.print(f"[{h.name}] Bought a Crop Automator kit ({price} cr, {wanted - 1} more to go).")
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
        now = _now_tick()
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

    def deploy_here(self, kind):
        """Deploys kind's kit in the current cell (collects a loose item there first)."""
        h = self._host
        here = h.get_position()
        kit = MACHINE_KITS[kind]
        if getattr(h.harvester.cell(here), "status", "") == "item":
            h.collect_at_current()
        h.store_held_if_any()
        if not h.stage(kit):
            self._deploy_failures()[here] = _now_tick()
            return False
        res = h.act("deploy", kit)
        status = getattr(res, "status", "?")
        if status == "ok":
            h.log.print(f"[{h.name}] Deployed {kind} at {here}. Its script slot still needs harvesting/{kind}.py (scripts_sync).")
            h.last_action = f"deploy {kind}@{here}"
            h.stock_memo.pop(kit, None)
            self.step_machine_map = None
            return True
        h.log.level("warn").print(f"[{h.name}] deploy('{kit}') at {here} -> {status}: {getattr(res, 'message', '')}")
        self._deploy_failures()[here] = _now_tick()
        return False

