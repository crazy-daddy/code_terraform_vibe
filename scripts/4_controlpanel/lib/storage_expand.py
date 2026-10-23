# Storage outpost expansion, run from automation/builder_automation.py.
#
# A storage outpost (site_evict.storage_outposts()) is the dump for
# leftovers: eviction fills it to capacity, empty slots included
# (site_evict.evict_room(), storage.open_room()). When its stores have fewer
# than FREE_SLOTS_MIN empty slots in all, this step warns (script status plus
# one log line, lib/status_warning.py; the AUTOMATION card through the
# builder summary) and buys one more store there: a Large Warehouse once its
# research is unlocked, else a Warehouse (KITS). The buy goes through the
# cash manager (consumer CASH_CONSUMER, lib/cash.py). One building per pass,
# network-wide, the outpost with the fewest empty slots first; an outpost
# that just got one waits SETTLE_TICKS before the next, so the new store is
# counted first; a refused deploy retries after the same wait.
#
# A kit already in Inventory is deployed without a buy, unless a Warehouse
# or bin swap (lib/warehouse_upgrade.py) is buying or deploying that type:
# the kit is theirs. A kit bought here whose deploy fails stays in Inventory
# and is deployed on a later pass.

import building_ops
import cash
from components import component, research_unlocked
from drone_upgrade import fleet_upgrade_state
from game_clock import now_tick
from site_evict import storage_outposts
from status_warning import StatusWarning
from storage import forget_storage_discovery, inventory_count, slot_layout
from swallow import swallowed
from tree_console import TreeConsole
from warehouse_upgrade import BinUpgrader, WarehouseUpgrader

MODULE = "storage_expand"
CASH_CONSUMER = "storage_expand"
# Empty storage slots a storage outpost keeps in all its stores; below this it gets another store.
FREE_SLOTS_MIN = 2
# Ticks an outpost waits after a deploy before it may get the next store (~1 min).
SETTLE_TICKS = 600
IDLE_SUMMARY = "storage outposts have room"
# Store kits, best first: (type id, research id, fallback price, name, the swap that also uses the kit).
KITS = (
    (WarehouseUpgrader.LARGE_TYPE_ID, WarehouseUpgrader.LARGE_RESEARCH_ID, WarehouseUpgrader.LARGE_PRICE_FALLBACK, WarehouseUpgrader.LARGE_NAME, WarehouseUpgrader.SWAP_KEY),
    (BinUpgrader.LARGE_TYPE_ID, BinUpgrader.LARGE_RESEARCH_ID, BinUpgrader.LARGE_PRICE_FALLBACK, BinUpgrader.LARGE_NAME, BinUpgrader.SWAP_KEY),
)
# Swap states in which the swap's kit in Inventory is spoken for.
SWAP_KIT_STATES = ("buying", "deploying")


def free_slots(outpost: "OutpostRef"):
    """Empty storage slots at `outpost` (storage.slot_layout(): each Warehouse slot, each Storage Bin)."""
    return sum(1 for item_id, _count, _capacity in slot_layout(outpost) if not item_id)


class StorageExpander:
    """Buys a store for the storage outpost lowest on empty slots. One instance, reused across passes."""

    def __init__(self):
        self.log = TreeConsole(module=MODULE)
        self.warning = StatusWarning(self.log, MODULE, "Storage outpost full")
        self.settled = {}  # {outpost_id: tick of the last deploy there}

    def _outposts(self):
        network = component("outpost_network")
        try:
            return network.outposts() if network else []
        except Exception as error:
            swallowed("storage_expand._outposts: network.outposts", error)
            return []

    def _unlocked(self, type_id, research_id):
        return research_unlocked(research_id, "storage_expand._unlocked") or inventory_count(type_id) > 0

    def _price(self, type_id, fallback):
        shop = component("shop")
        try:
            for entry in shop.get_catalogue() if shop else []:
                if entry.id == type_id:
                    return int(entry.cost)
        except Exception as error:
            swallowed("storage_expand._price: shop.get_catalogue", error)
        return fallback

    def _kit(self):
        """(type id, name, price, swap key) of the best unlocked store kit, or None."""
        for type_id, research_id, fallback, name, swap_key in KITS:
            if self._unlocked(type_id, research_id):
                return type_id, name, self._price(type_id, fallback), swap_key
        return None

    @staticmethod
    def _kit_spoken_for(swap_key):
        swap = fleet_upgrade_state().get(swap_key)
        return isinstance(swap, dict) and swap.get("state") in SWAP_KIT_STATES

    def step(self):
        """One pass. Returns a one-line summary (IDLE_SUMMARY when every storage outpost has room)."""
        short = sorted((free_slots(o), getattr(o, "id", "")) for o in storage_outposts(self._outposts()))
        short = [(free, outpost_id) for free, outpost_id in short if free < FREE_SLOTS_MIN and outpost_id]
        if not short:
            self.warning.update(False)
            cash.release(CASH_CONSUMER)
            return IDLE_SUMMARY
        listed = ", ".join(f"{outpost_id} {free}" for free, outpost_id in short)
        self.warning.update(True, f"Storage outpost(s) low on empty slots (fewer than {FREE_SLOTS_MIN}): {listed}.")
        free, outpost_id = short[0]
        now = now_tick()
        if now - self.settled.get(outpost_id, now - SETTLE_TICKS) < SETTLE_TICKS:
            return f"{outpost_id}: {free} free slot(s), new store settling"
        kit = self._kit()
        if kit is None:
            return f"{outpost_id}: {free} free slot(s), no Warehouse researched"
        type_id, name, price, swap_key = kit
        if inventory_count(type_id) <= 0 or self._kit_spoken_for(swap_key):
            bought = self._buy(type_id, name, price, len(short))
            if bought:
                return f"{outpost_id}: {free} free slot(s), {bought}"
        return f"{outpost_id}: {self._deploy(type_id, name, outpost_id, now)}"

    def _buy(self, type_id, name, price, wanted):
        """Buys one kit; returns None on success, else why not."""
        if not cash.can_spend(CASH_CONSUMER, price, planned=wanted * price, label=f"{wanted} {name}(s) for storage outposts"):
            self.log.debug(f"[{MODULE}] cash manager holds back {price} cr for a {name}; waiting.")
            return f"saving up for a {name} ({price} cr)"
        shop = component("shop")
        res = shop.buy(type_id, 1) if shop else None
        status = getattr(res, "status", "no_shop")
        if status != "ok":
            cash.release(CASH_CONSUMER)
            self.log.debug(f"[{MODULE}] buy('{type_id}'): {status} - {getattr(res, 'message', '')}")
            return f"buy {status}, retrying"
        cash.spent(CASH_CONSUMER, price)
        self.log.print(f"[{MODULE}] Bought a {name} ({price} cr) for a storage outpost.")
        return None

    def _deploy(self, type_id, name, outpost_id, now):
        new_id, status, message = building_ops.deploy_new(type_id, outpost_id)
        if status == "no_computer":
            return "no Ship Computer"
        self.settled[outpost_id] = now  # a refused deploy retries after SETTLE_TICKS too
        if new_id is None:
            if status not in building_ops.CALL_FAILED_STATUSES:  # a raise waits quietly, no warn
                self.log.level("warn").print(f"[{MODULE}] deploy('{type_id}', '{outpost_id}') refused ({status}: {message}); kit stays in Inventory, retrying in {SETTLE_TICKS} ticks.")
            return f"deploy {status}"
        forget_storage_discovery()  # the next count and every unload target must see the new store
        self.log.print(f"[{MODULE}] Deployed {name} '{new_id}' at storage outpost '{outpost_id}'.")
        return f"deployed {name} {new_id}"
