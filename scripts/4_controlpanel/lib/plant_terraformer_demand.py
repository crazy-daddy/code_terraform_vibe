from archive import archive, STATUS_STALE_TICKS
from game_clock import is_fresh
import logistics_requests
from production import fabricator_unlocked_outputs, set_upgrade_order, set_backlog_order
from plant_terraformer_common import STATUS_KEY, REQUESTER_ID, STOP_STATUSES, SUPPORT_HOLDER_CAP, FERTILIZER_ITEM_IDS, SUPPORT_REQUEST_BATCHES, ceil_int, remaining_forage
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plant_terraformer import PlantTerraformerController

# Plant Terraformer mixin: demand publishing (lib/plant_terraformer.py).
#
# Demand advertisement (lib/logistics_requests.py, requester
# "plant_terraformer"): every material the phase needs is published as a
# LOCAL STOCK target -- the next batch staged in this outpost's Warehouses /
# Drone Depots, on top of what sits in the holders. That's the shape every
# hauler already reads: the Pioneer pull hauler and the floating drone
# hauler plan from outpost_deficits() (target - Warehouses - Depots -
# in-flight pickups), miner drones from network_deficits(). Drone freight
# lands in the Depot; drone_depot.py drains non-life-form items into a
# Warehouse, and the loader also takes straight from a local Depot.
#   - Forage: one full batch, only away from home -- the field's Harvester
#     delivers to home Inventory, so home is a SOURCE of Forage, not a sink.
#   - Salt / Growth Accelerant: SUPPORT_REQUEST_BATCHES batches' worth.
#   - Fertilizer: requested as the tier the Fabricator crafts
#     (craft_fertilizer_item()), counted in that tier's potency units across
#     all tiers.
#   logistics.requests holds one entry per item per outpost; an item another
#   requester (e.g. the field Harvester's salt) already owns here is left
#   alone -- its target keeps the outpost stocked, and the Terraformer draws
#   from the same stock.
#
# Fabricator orders (fabricator_orders()): Fertilizer and Growth Accelerant
# are crafted at any fab site. Every Mk II Terraformer writes the same two orders
# for the whole fleet (fleet_size() from `plant.terraformer` telemetry):
#   - need: NEED_BATCHES batches per machine, a standing upgrade order
#     (production.set_upgrade_order(), ranked above Earth orders);
#   - backlog: BACKLOG_BATCHES batches per machine, a backlog order
#     (production.set_backlog_order(), crafted only in idle Fabricator time).
# Both net against network stock (production.SourceCache.network_stock(),
# Drone Depots included), so units at a remote fab site count; the local
# request above hauls them in.
# Both are capped by what the rest of the Plants ladder still needs
# (remaining_forage()), so they shrink to 0 near completion.

# Fertilizer tier the Fabricator is asked for, cheapest first: per potency,
# Mk II needs less Fabricator time and Tar than Mk I, and Mk III's Neutron
# Capacitor chain costs about 5x Mk II (§1k). The first unlocked one wins.
FERTILIZER_CRAFT_PREFERENCE = ("fertilizer_mk2", "fertilizer")

# Fabricator need order: batches per running Mk II Terraformer (2 machines:
# 20 Growth Accelerant, 18 Fertilizer Mk II). Fabricators sit at other
# outposts, so this covers ~30 h of use while a hauler brings a load in.
NEED_BATCHES = 10

# Fabricator backlog order: the stock kept on the network, batches per
# machine (2 machines: 200 Growth Accelerant), crafted in idle Fabricator
# time. Capped by the rest of the ladder, so it ends with the Plants phase.
BACKLOG_BATCHES = 100

# First phase each Fabricator-crafted input is needed in (cumulative after).
CRAFTED_SUPPORT_FIRST_PHASE = {"fertilizer": 4, "growth_accelerant": 5}

# craft_fertilizer_item() re-reads the Fabricator's unlocks this often; 10 ticks/s -> 1 min.
REQUEST_REFRESH_TICKS = 600


def order_sizes(per_batch, full_batch, machines, forage_left):
    """
    (need, backlog) item counts for one crafted input. per_batch = items per
    full batch of full_batch Forage (fractional for Fertilizer potency).
    Both are capped by forage_left; backlog is never below need.
    """
    if per_batch <= 0 or full_batch <= 0 or machines <= 0:
        return 0, 0
    left = ceil_int(forage_left * per_batch / full_batch)
    need = min(ceil_int(NEED_BATCHES * machines * per_batch), left)
    backlog = min(ceil_int(BACKLOG_BATCHES * machines * per_batch), left)
    return need, max(need, backlog)


class PlantTerraformerDemandMixin:

    @property
    def _host(self) -> "PlantTerraformerController":
        return self  # type: ignore[return-value]

    def _init_demand(self):
        self._published_targets = None
        self._published_orders = None
        self._order_detail = []
        self._craft_fertilizer = None
        self._craft_fertilizer_tick = 0

    # ------------------------------------------------------------ requests

    def demand_targets(self, reqs, required, batches=SUPPORT_REQUEST_BATCHES):
        """{item_id: local stock target} for the next batch and `batches` batches of support items, before ownership checks."""
        host = self._host
        targets = {}
        if not host.is_home and reqs.get("forage"):
            targets["forage"] = int(reqs["forage"])
        if "salt" in required and reqs.get("salt"):
            targets["salt"] = int(reqs["salt"]) * batches
        if reqs.get("fertilizer_potency"):
            item_id = self.craft_fertilizer_item()
            per_batch = -(-int(reqs["fertilizer_potency"]) // max(host._potency(item_id), 1))
            targets[item_id] = min(per_batch, SUPPORT_HOLDER_CAP) * batches
        if "growth_accelerant" in required and reqs.get("growth_accelerant"):
            targets["growth_accelerant"] = min(int(reqs["growth_accelerant"]), SUPPORT_HOLDER_CAP) * batches
        return targets

    def _have(self, item_id):
        """Published "have": local stock; Fertilizer in item_id's potency units over all tiers."""
        host = self._host
        if item_id not in FERTILIZER_ITEM_IDS:
            return host.local_stock(item_id)
        unit = max(host._potency(item_id), 1)
        return sum(host.local_stock(i) * host._potency(i) for i in FERTILIZER_ITEM_IDS) // unit

    def publish_requests(self, reqs, required, requests, curr_tick, batches=SUPPORT_REQUEST_BATCHES):
        """Advertises this Terraformer's demand in logistics.requests (see module header); items another requester owns here are left to it."""
        host = self._host
        if not host.outpost_id:
            return
        targets = self.demand_targets(reqs, required, batches)
        wants = {item_id: (target, 0) for item_id, target in targets.items()}
        written = logistics_requests.publish_requests(host.outpost_id, REQUESTER_ID, wants, curr_tick, requests, have_of=self._have)
        if written and targets != self._published_targets:
            if targets:
                host.log.print(f"[{host.name}] Advertising demand at {host.outpost_id}: {targets}.")
            elif self._published_targets:
                host.log.print(f"[{host.name}] Demand withdrawn at {host.outpost_id}.")
        self._published_targets = targets

    def withdraw_requests(self):
        """Clears this Terraformer's logistics.requests entries (once per withdrawal)."""
        if self._published_targets is None or self._published_targets:
            logistics_requests.clear_requests(REQUESTER_ID, self._host.outpost_id)
            self._published_targets = {}

    # -------------------------------------------------- Fabricator orders

    def craft_fertilizer_item(self, curr_tick=None):
        """First FERTILIZER_CRAFT_PREFERENCE item the Fabricator has unlocked; curr_tick re-reads it every REQUEST_REFRESH_TICKS."""
        due = self._craft_fertilizer is None or (
            curr_tick is not None
            and (curr_tick < self._craft_fertilizer_tick or curr_tick - self._craft_fertilizer_tick >= REQUEST_REFRESH_TICKS)
        )
        if due:
            unlocked = fabricator_unlocked_outputs()
            item_id = next((i for i in FERTILIZER_CRAFT_PREFERENCE if i in unlocked), FERTILIZER_CRAFT_PREFERENCE[-1])
            if item_id != self._craft_fertilizer:
                self._host.log.debug(f"[{self._host.name}] Fertilizer to craft: {item_id} (unlocked: {sorted(i for i in unlocked if i in FERTILIZER_ITEM_IDS)}).")
            self._craft_fertilizer = item_id
            self._craft_fertilizer_tick = curr_tick or 0
        return self._craft_fertilizer

    def fleet_size(self, curr_tick):
        """Mk II Terraformers on the ladder: fresh, non-stopped `plant.terraformer` entries plus this one."""
        status = archive.get(STATUS_KEY, {})
        count = 1
        if not isinstance(status, dict):
            return count
        for machine_id, entry in status.items():
            if machine_id == self._host.name or not isinstance(entry, dict):
                continue
            if not is_fresh(entry, curr_tick, STATUS_STALE_TICKS) or entry.get("status") in STOP_STATUSES:
                continue
            if int(entry.get("tier", 1) or 1) >= 2:
                count += 1
        return count

    def fabricator_orders(self, reqs, required, phase, remaining, machines, to_go=None):
        """
        ({item_id: need}, {item_id: backlog}) for the Fabricator-crafted inputs
        this phase needs (see module header); to_go (forage_to_go()) caps the
        Forage left.
        """
        host = self._host
        need, backlog = {}, {}
        self._order_detail = []
        full = int(reqs.get("forage", 0) or 0)
        if full <= 0:
            return need, backlog
        crafted = []
        if reqs.get("fertilizer_potency"):
            item_id = self.craft_fertilizer_item()
            per_batch = int(reqs["fertilizer_potency"]) / float(max(host._potency(item_id), 1))
            crafted.append((item_id, per_batch, CRAFTED_SUPPORT_FIRST_PHASE["fertilizer"]))
        if "growth_accelerant" in required and reqs.get("growth_accelerant"):
            crafted.append(("growth_accelerant", float(reqs["growth_accelerant"]), CRAFTED_SUPPORT_FIRST_PHASE["growth_accelerant"]))
        for item_id, per_batch, first_phase in crafted:
            forage_left = remaining_forage(phase, remaining, first_phase)
            if to_go is not None:
                forage_left = min(forage_left, to_go)
            n, b = order_sizes(per_batch, full, machines, forage_left)
            self._order_detail.append(f"[{host.name}] {item_id}: {per_batch:.2f}/batch x {machines} machine(s), {forage_left:,.0f} Forage left -> need {n}, backlog {b}.")
            if n > 0:
                need[item_id] = n
            if b > 0:
                backlog[item_id] = b
        return need, backlog

    def publish_fabricator_orders(self, need, backlog):
        """Writes both orders (production skips unchanged writes); info line and fabricator_orders()' sizing trail when they change."""
        host = self._host
        orders = (need, backlog)
        if orders == self._published_orders:
            return
        for line in self._order_detail:
            host.log.debug(line)
        set_upgrade_order(REQUESTER_ID, need)
        set_backlog_order(REQUESTER_ID, backlog)
        if need or backlog:
            host.log.print(f"[{host.name}] Fabricator orders: need {need}, backlog {backlog}.")
        elif self._published_orders:
            host.log.print(f"[{host.name}] Fabricator orders withdrawn.")
        self._published_orders = orders
