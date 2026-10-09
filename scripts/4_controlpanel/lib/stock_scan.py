# One read of every store at an outpost, served to every stock scope.
#
# Every "how much X is at Y" question is the same sweep with a different set
# of store kinds, so the sweep runs once (one stacks() per store) and the
# scopes are tuples of kinds over the same rows:
#
#   LOCAL  what a machine port there can take(): Inventory (home only),
#          Warehouses, Storage Bins, Crop Automator outputs (Forage).
#   HELD   LOCAL plus Drone Depot stockpiles: what is on hand for netting
#          demand. A Depot pushes its freight to local consumers and stores
#          (lib/drone_depot.py), so machines never pull from it.
#   DEPOTS the Drone Depot stockpiles alone (what a docked drone loads).
#   STORES Warehouses and Storage Bins alone.
#
# Netting (Fabricator targets, demand cascades, Supply Dock readiness,
# logistics requests) counts HELD; loaders count LOCAL. SourceCache
# (lib/production_source.py) and PlanReads (lib/logistics_requests.py)
# memoize one scan per outpost per pass.
from storage import discover_storage_buildings, crop_automator_forage, outpost_is_home, BinStore, CROP_AUTOMATOR_ITEM_ID, STOCKS_CHUNK
from atomic import run_batched
from item_tiers import DEPOT_TYPE_TIERS
from outpost_mining import HOME_OUTPOST_ID
import components
from swallow import swallowed

INVENTORY = "inventory"
WAREHOUSE = "warehouse"
BIN = "bin"
DEPOT = "depot"
AUTOMATOR = "automator"

STORES = (WAREHOUSE, BIN)
LOCAL = (INVENTORY, WAREHOUSE, BIN, AUTOMATOR)
HELD = LOCAL + (DEPOT,)
DEPOTS = (DEPOT,)


def scan_key(outpost: "OutpostRef | None"):
    """Memo key for an outpost's scan: HOME_OUTPOST_ID for home (None included), else its id."""
    return HOME_OUTPOST_ID if outpost_is_home(outpost) else getattr(outpost, "id", None)


class StockScan:
    """The stores at one outpost, each read once: {store_id: (kind, {item_id: units})}."""

    def __init__(self, rows):
        self.rows = rows

    def totals(self, kinds, item_ids=None):
        """{item_id: units} over the stores of `kinds`; with item_ids, exactly those keys (0 when absent)."""
        totals = {item_id: 0 for item_id in item_ids} if item_ids is not None else {}
        for kind, held in self.rows.values():
            if kind not in kinds:
                continue
            for item_id, units in held.items():
                if item_ids is None or item_id in totals:
                    totals[item_id] = totals.get(item_id, 0) + units
        return totals

    def units(self, item_id, kinds):
        """Units of item_id over the stores of `kinds`."""
        return sum([held.get(item_id, 0) for kind, held in self.rows.values() if kind in kinds])

    def holders(self, item_id, kinds):
        """[(store_id, units)] of the stores of `kinds` holding item_id, scan order."""
        return [(store_id, held[item_id]) for store_id, (kind, held) in self.rows.items() if kind in kinds and held.get(item_id, 0) > 0]


def _port_rows(sources):
    """[[(item_id, units), ...]] per (store_id, port) from one stacks() read each; pure reads, run atomically."""
    rows = []
    for _store_id, port in sources:
        try:
            rows.append([(stack.id, stack.count) for stack in port.stacks()])
        except Exception as error:
            swallowed("stock_scan._port_rows: port.stacks", error)
            rows.append([])
    return rows


def _summed(row):
    held = {}
    for item_id, units in row:
        if item_id:
            held[item_id] = held.get(item_id, 0) + units
    return held


def scan(outpost: "OutpostRef | None" = None):
    """StockScan of `outpost` (None = home): one stacks() per Inventory (home), Warehouse,
    Storage Bin and Drone Depot stockpile, STOCKS_CHUNK stores per atomic call, plus
    the home Crop Automators' Forage (storage.crop_automator_forage())."""
    at_home = outpost_is_home(outpost)
    sources = []
    kinds = {}
    if at_home:
        inventory = components.component("inventory")
        if inventory and hasattr(inventory, "stacks"):
            sources.append(("inventory", inventory))
            kinds["inventory"] = INVENTORY
    for building in discover_storage_buildings(outpost):
        store = building["component"]
        if store and hasattr(store, "stacks"):
            sources.append((building["id"], store))
            kinds[building["id"]] = BIN if isinstance(store, BinStore) else WAREHOUSE
    for building in discover_storage_buildings(outpost, DEPOT_TYPE_TIERS):
        port = getattr(building["component"], "output", None)
        if port and hasattr(port, "stacks"):
            sources.append((building["id"], port))
            kinds[building["id"]] = DEPOT
    rows = {}
    for (store_id, _port), row in zip(sources, run_batched(_port_rows, sources, STOCKS_CHUNK)):
        rows[store_id] = (kinds[store_id], _summed(row))
    if at_home:
        for ca_id, forage, _clogged, _garden in crop_automator_forage(outpost):
            rows[ca_id] = (AUTOMATOR, {CROP_AUTOMATOR_ITEM_ID: forage})
    return StockScan(rows)


def held_units(item_id, outpost: "OutpostRef | None" = None):
    """HELD units of item_id at `outpost` (None = home) from a fresh scan; for a
    one-off netting read. A pass that asks more than once memoizes a scan instead."""
    return scan(outpost).units(item_id, HELD)
