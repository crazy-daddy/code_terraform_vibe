# Shared Library for Supply Dock Logistics
# Automatically matches and assigns Earth Contractor Campaign Orders & Weekly Orders,
# feeds required materials from Base Inventory, and enables continuous dispatch.
#
# Multi-Dock coordination (see docs/AI_CHEATSHEET.md §2a-0-5): with more than one
# Supply Dock, a single dock's independent per-instance decision-making leaves
# docks either all piling onto the same order (fine when it's genuinely the only
# one worth doing, wasteful otherwise) or scanning the full Earth Order board
# redundantly every cycle (the same N-times-redundant-per-cycle pattern bio.py's
# Collector/Luminizer hit). `plan_dock_assignments()` is the central "decider" --
# called once per cycle from orchestrator_automation.py's AUTOMATION section (this script's own
# `set_order()`/`clear_order()`/`set_enabled()` are all `*(self only)*` hardware
# calls per docs/components/supply_dock.md, so the plan itself has to be computed
# somewhere else and handed to each dock via Archive; each dock's own
# `SupplyDockController` then reads its assignment and performs the self-only
# calls on itself). `desired_order_id()` falls back to this dock's own
# `pick_best_order()` if no plan is available yet (orchestrator_automation not running this
# cycle, or not running at all) so a dock never sits idle waiting on a planner
# that may not be online.
#
# Docks at any outpost (production.discover_supply_dock_ids() is network-wide):
# a dock off home loads from and drains to its own outpost's Warehouses
# (Inventory is home-only), and plan_dock_assignments() ranks first the orders
# whose items the dock's outpost already holds unpromised (_local_supply()),
# and breaks priority ties toward the outpost that plans to build (production
# SITE_PLAN_KEY) the order's items -- the order's items are then consumed at
# that outpost, so its whole tree builds there (lib/site_plan.py).
#
# Dock site roles (DockRoles): the buildings at a dock's outpost decide which
# order items it ships. A Fabricator gives crafted items (Fabricator recipe
# outputs), a Smelter gives every raw ore and Smelter output, a resource
# marker naming the outpost (lib/outpost_mining.py) gives that ore, a Lead
# Cask gives Raw Uranium and Fuel Rods. Items with none of these kinds ship
# from any dock. A dock takes only orders it covers at least one role-bound
# item of; it ranks orders by the share it covers, and the rest of a mixed
# order reaches its outpost as a site-supply consumer request
# (lib/site_supply.py). An empty dock leaves an order it covers
# nothing of, so a dock at a nuclear site without Fabricators never waits on
# a crafted-only order.
import math

import lead_cask
from archive import archive
from components import home_outpost, supply_dock
from drone_kit_stock import publish_drone_kit_order
from game_clock import now_hours
from game_rules import RAW_ORE_ITEM_IDS
from machine_controller import MachineController
from outpost_mining import assigned_ores_by_outpost
from priority import ORDER_AHEAD, band_name, clamp, order_prio
from production import NO_CONSUMER_SITE, ORDER_PRIO_KEY, SITE_PLAN_KEY, SourceCache, can_fulfill_order, discover_fabricator_ids, discover_smelter_ids, discover_supply_dock_ids, fabricator_unlocked_outputs, get_construction_material_reservations, home_outpost_id, machine_outpost_id, remote_dock_reservations, set_order
from script_parking import ParkRequester, parked_ids, wake_for_visit
from storage import best_unload_target, inventory_room, local_port_target, outpost_is_home, take_item, total_stock
from swallow import swallowed
from tree_console import TreeConsole

log = TreeConsole(module="supply_dock")

# {dock_id: order_id or None}, recomputed and overwritten wholesale every
# planning cycle -- see plan_dock_assignments().
ORDER_PLAN_ARCHIVE_KEY = "supply_dock.order_plan"

# Several docks may now share the same active order (docs/components/supply_dock.md:
# "Several docks may serve the same order and share shipped progress"), so a
# dock's own material loading can no longer assume it has no sibling contesting
# the same Inventory/Warehouse stock -- the same fairness problem
# Fabricator/Smelter loading hit (docs/AI_CHEATSHEET.md §2a-0-2). Capped the
# same way: a chunked per-call take instead of grabbing the full remaining need
# in one shot, so a heavy shortfall spreads across several `step()` cycles and
# a sibling dock's own poll gets a chance to interleave.
SUPPLY_DOCK_LOAD_CHUNK_SIZE = 10

# A fixed chunk starves a researched dispatcher: one step() takes tens of game
# minutes, so 10 units per step ships ~25 u/h against 100-400 u/h with Bulk
# Logistics II/III. load_chunk() lifts the floor to cover the dispatch until the
# next step (measured step gap, clamped, times the lookahead), and splits the
# stock evenly among docks the central plan puts on the same order, so the
# fairness the chunk gave still holds when stock is short.
SUPPLY_DOCK_LOAD_LOOKAHEAD = 2.0
SUPPLY_DOCK_DEFAULT_GAP_HOURS = 0.5
SUPPLY_DOCK_MAX_GAP_HOURS = 2.0


def load_chunk(rate, gap_hours, in_dock, available, siblings=1):
    """Units one step() may take of an item: enough for `rate` u/h over the step gap
    (`gap_hours`, None = unmeasured) times the lookahead, less the `in_dock` cargo,
    at least SUPPLY_DOCK_LOAD_CHUNK_SIZE; at most `available` split over `siblings`
    docks on the order (but never under the chunk). The caller caps by need."""
    gap = SUPPLY_DOCK_DEFAULT_GAP_HOURS if gap_hours is None else min(max(gap_hours, 0.0), SUPPLY_DOCK_MAX_GAP_HOURS)
    want = max(SUPPLY_DOCK_LOAD_CHUNK_SIZE, math.ceil(rate * gap * SUPPLY_DOCK_LOAD_LOOKAHEAD) - in_dock)
    share = max(SUPPLY_DOCK_LOAD_CHUNK_SIZE, available // max(1, siblings))
    return max(0, min(want, share, available))


# Key unlock orders (docs/cheatsheet/production_logistics.md "Key unlock orders"):
# early campaign orders whose recipe unlocks rank in this order, first is
# best: Titanium Ingot (helios_01, the Power Line Segment recipe needs it),
# Power Line Segment (vestibule_01), Gas Pipe Segment (helios_02), Liquid Pipe
# Segment (spire_intake_2); then the electric drone path up to helios_09
# (Small Cargo Pod) and spire_10 (Drone Service Station Kit), interleaved by
# dependency (docs/gameknowledge/unlock_paths.md "Drone path"); then the
# Helios queue on to helios_25 (Mining Drill, Drone (Large), Heavy Mining
# Drill; its inputs come from orders above, "Helios after the drone path");
# then the Spire queue on to spire_18 (Yield Amplifier) and the Vestibule
# queue on to vestibule_15 (Heli Thruster, Oil Tanks up to Large; "Yield
# Amplifier and heli path"); then the Helios queue on to helios_28 (Lead Cask)
# and the Vestibule queue on to vestibule_28 (Shield Plating, Fuel Rod; no
# vestibule_27 exists; "Nuclear path").
# Order.id is stable; reward_label is translated. Each step outweighs the
# readiness term, so a cheap order that is ready sooner (spire_intake_2: 75
# units) can't jump the queue. The first dock that serves one takes it before
# any other order; more docks join only with stock at their own outpost
# (_key_rush()). The order in front of one in its contractor's queue earns
# part of its weight (key_unlock_bonus()).
EARLY_UNLOCK_ORDER_IDS = (
    "helios_01",
    "vestibule_01",
    "helios_02",
    "spire_intake_2",
    "spire_intake_3",
    "spire_01",
    "spire_02",
    "helios_03",
    "spire_03",
    "spire_04",
    "helios_04",
    "helios_05",
    "helios_06",
    "spire_05",
    "spire_06",
    "spire_07",
    "helios_07",
    "spire_08",
    "helios_08",
    "helios_09",
    "spire_09",
    "spire_10",
    "helios_10",
    "helios_11",
    "helios_12",
    "helios_13",
    "helios_14",
    "helios_15",
    "helios_16",
    "helios_17",
    "helios_18",
    "helios_19",
    "helios_20",
    "helios_21",
    "helios_22",
    "helios_23",
    "helios_24",
    "helios_25",
    "spire_11",
    "spire_12",
    "spire_13",
    "spire_14",
    "spire_15",
    "spire_16",
    "spire_17",
    "spire_18",
    "vestibule_02",
    "vestibule_03",
    "vestibule_04",
    "vestibule_05",
    "vestibule_06",
    "vestibule_07",
    "vestibule_08",
    "vestibule_09",
    "vestibule_10",
    "vestibule_11",
    "vestibule_12",
    "vestibule_13",
    "vestibule_14",
    "vestibule_15",
    "helios_26",
    "helios_27",
    "helios_28",
    "vestibule_16",
    "vestibule_17",
    "vestibule_18",
    "vestibule_19",
    "vestibule_20",
    "vestibule_21",
    "vestibule_22",
    "vestibule_23",
    "vestibule_24",
    "vestibule_25",
    "vestibule_26",
    "vestibule_28",
)
CAMPAIGN_READINESS_WEIGHT = 30
EARLY_UNLOCK_STEP = CAMPAIGN_READINESS_WEIGHT + 1
# Largest _score_campaign_order(): base 10 + 50 (recipe/tech reward) + the
# first key order's weight + half of it as key_unlock_bonus() + readiness.
# priority.order_prio() maps 0..this onto the ORDER band's fine value.
ORDER_SCORE_MAX = 60 + len(EARLY_UNLOCK_ORDER_IDS) * EARLY_UNLOCK_STEP * 3 // 2 + CAMPAIGN_READINESS_WEIGHT
# Operator overrides of an order's prio (ORDERS card): {order_id: prio 0-999},
# any band, so an order can be lifted above manual orders or dropped under
# the stock buffers. Wins over the score (order_prio()). Entries of orders no
# longer on the board are dropped by the planner.
PRIORITY_OVERRIDE_KEY = "supply_dock.priority_override"
# Orders-book requester of publish_key_ahead() (production.set_order()).
KEY_AHEAD_REQUESTER = "key_unlock_ahead"


def order_overrides():
    """{order_id: prio} from PRIORITY_OVERRIDE_KEY ({} when unset or malformed)."""
    stored = archive.get(PRIORITY_OVERRIDE_KEY, {})
    if not isinstance(stored, dict):
        return {}
    return {order_id: clamp(prio) for order_id, prio in stored.items() if isinstance(prio, (int, float))}


def set_order_override(order_id, prio):
    """Sets (prio 0-999) or clears (None) the operator override of one order."""

    def updater(stored):
        stored = dict(stored) if isinstance(stored, dict) else {}
        if prio is None:
            stored.pop(order_id, None)
        else:
            stored[order_id] = clamp(prio)
        return stored

    archive.transaction(PRIORITY_OVERRIDE_KEY, {}, updater)


def _order_prio(order: "Order", score, overrides):
    """The order's prio (lib/priority.py): its ORDER-band score, or the operator's override."""
    return order_prio(score, overrides.get(getattr(order, "id", None)), ORDER_SCORE_MAX)


def publish_order_prios(candidates, overrides):
    """Writes {order_id: prio} of this pass's candidates to ORDER_PRIO_KEY
    (read by the demand tree, production_docks.dock_order_prios()) and
    drops overrides of orders that are no candidate any more. Writes only
    on change."""
    prios = {c["order"].id: c["prio"] for c in candidates}
    stored = archive.get(ORDER_PRIO_KEY, {})
    if stored != prios:
        archive.set(ORDER_PRIO_KEY, prios)
    stale = [order_id for order_id in overrides if order_id not in prios]
    if stale:
        for order_id in stale:
            set_order_override(order_id, None)
        log.debug(f"dropped priority overrides of finished orders {stale}")


def order_rows(clock: "Clock | None" = None):
    """[{"id", "name", "prio", "band", "score", "override", "docks", "needs"}]
    for the ORDERS card, most urgent first: every active campaign and weekly
    order with its prio (ORDER_PRIO_KEY), the operator override when set and
    the docks the plan assigns to it."""
    prios = archive.get(ORDER_PRIO_KEY, {})
    prios = prios if isinstance(prios, dict) else {}
    overrides = order_overrides()
    plan = archive.get(ORDER_PLAN_ARCHIVE_KEY, {})
    plan = plan if isinstance(plan, dict) else {}
    orders_api = get_component("orders")
    rows = []
    if not orders_api:
        return rows
    board = []
    for getter in ("list_orders", "list_weekly_orders"):
        try:
            board.extend(getattr(orders_api, getter)())
        except Exception as error:
            swallowed(f"supply_dock.order_rows: orders_api.{getter}", error)
    for order in board:
        if getattr(order, "status", "") != "active":
            continue
        order_id = getattr(order, "id", None)
        prio = prios.get(order_id)
        shipped = getattr(order, "shipped", {}) or {}
        needs = {i: max(0, n - shipped.get(i, 0)) for i, n in (getattr(order, "requires", {}) or {}).items()}
        rows.append(
            {
                "id": order_id,
                "name": getattr(order, "name", order_id),
                "prio": prio,
                "band": band_name(prio) if prio is not None else "-",
                "override": overrides.get(order_id),
                "docks": sorted(d for d, o in plan.items() if o == order_id),
                "needs": {i: n for i, n in needs.items() if n > 0},
            }
        )
    rows.sort(key=lambda r: -(r["prio"] if r["prio"] is not None else -1))
    return rows


def early_unlock_weight(order_id):
    """Score bonus of a key unlock order (EARLY_UNLOCK_ORDER_IDS), 0 for any other."""
    if order_id not in EARLY_UNLOCK_ORDER_IDS:
        return 0
    return (len(EARLY_UNLOCK_ORDER_IDS) - EARLY_UNLOCK_ORDER_IDS.index(order_id)) * EARLY_UNLOCK_STEP


# Local stock rank steps (_local_supply()): an order whose still-owed units sit
# unpromised at the dock's outpost ranks above priority, in tenths of the order,
# so a few stray units don't outrank a better order.
LOCAL_STOCK_STEPS = 10

# Dock site roles (module comment).
ROLE_FAB = "fab"
ROLE_MINE = "mine"
ROLE_CASK = "cask"


class DockRoles:
    """Per-pass memo of dock site roles and item kinds (module comment).
    Never held across passes: a new building changes a site's roles."""

    def __init__(self, cache: "SourceCache | None" = None):
        self.cache = cache if cache is not None else SourceCache()
        self._fab_items = None
        self._mine_items = None
        self._marker_ores = None
        self._sites = {}

    def item_roles(self, item_id):
        """Roles that ship item_id; empty = any dock ships it."""
        if item_id in lead_cask.HOT_ITEMS:
            return {ROLE_CASK}
        if self._fab_items is None or self._mine_items is None:
            self._fab_items = {getattr(r, "output_item", None) for r in self.cache.fabricator_recipes()} - {None}
            self._mine_items = set(RAW_ORE_ITEM_IDS) | ({getattr(r, "output_item", None) for r in self.cache.smelter_recipes()} - {None})
        roles = set()
        if item_id in self._fab_items:
            roles.add(ROLE_FAB)
        if item_id in self._mine_items:
            roles.add(ROLE_MINE)
        return roles

    def site(self, outpost: "OutpostRef | None"):
        """(roles, marker ores) of the dock site `outpost` (None = home); (None, None) when the site can't be resolved."""
        if outpost is None:
            outpost = home_outpost()
        site_id = getattr(outpost, "id", None)
        if site_id is None:
            return None, None
        if site_id not in self._sites:
            roles = set()
            if discover_fabricator_ids(outpost):
                roles.add(ROLE_FAB)
            if discover_smelter_ids(outpost):
                roles.add(ROLE_MINE)
            if lead_cask.casks_at(outpost):
                roles.add(ROLE_CASK)
            if self._marker_ores is None:
                self._marker_ores = assigned_ores_by_outpost()
            self._sites[site_id] = (roles, self._marker_ores.get(site_id, set()))
        return self._sites[site_id]

    def covers(self, item_id, outpost: "OutpostRef | None"):
        """Whether a dock at `outpost` ships item_id itself (no hauling needed)."""
        item_roles = self.item_roles(item_id)
        if not item_roles:
            return True
        site_roles, ores = self.site(outpost)
        if site_roles is None:
            return True
        return bool(item_roles & site_roles) or (ROLE_MINE in item_roles and item_id in ores)

    def coverage(self, order: "Order", outpost: "OutpostRef | None"):
        """(covered, bound): still-owed role-bound items of order, and how many of them a dock at `outpost` covers."""
        requires = getattr(order, "requires", {}) or {}
        shipped = getattr(order, "shipped", {}) or {}
        covered = bound = 0
        for item_id, req_count in requires.items():
            if req_count - shipped.get(item_id, 0) <= 0 or not self.item_roles(item_id):
                continue
            bound += 1
            if self.covers(item_id, outpost):
                covered += 1
        return covered, bound

    def serves(self, order: "Order", outpost: "OutpostRef | None"):
        """Whether a dock at `outpost` may take order: no role-bound item, or it covers at least one."""
        covered, bound = self.coverage(order, outpost)
        return bound == 0 or covered > 0

    def share(self, order: "Order", outpost: "OutpostRef | None"):
        """Covered fraction of order's role-bound items at `outpost` (1.0 with none)."""
        covered, bound = self.coverage(order, outpost)
        return 1.0 if bound == 0 else covered / bound

    def describe(self, outpost: "OutpostRef | None"):
        """Short role list of a site for debug lines."""
        site_roles, ores = self.site(outpost)
        if site_roles is None:
            return "unknown site"
        parts = sorted(site_roles) + [f"ore:{o}" for o in sorted(ores or ())]
        return ", ".join(parts) if parts else "no roles"


def _order_readiness(order: "Order", reserved, stock=None, cask_stock=None):
    """(items_ready, total_needed) for order -- how much of its still-owed
    requirement is already on hand at home (Lead Casks for hot items), net
    of active Construction Blueprint reservations. Shared by the
    per-instance and central scoring paths so both rank orders identically.
    `stock(item_id)`: a SourceCache's held_stock() (Inventory + home
    Warehouses + home Drone Depots, the same count Fabricator netting uses);
    a fresh SourceCache when None. `cask_stock(item_id)`: hot-item stock,
    default lead_cask.network_cask_stock()."""
    stock = stock or SourceCache().held_stock
    items_ready = 0
    total_needed = 0
    requires = getattr(order, "requires", {}) or {}
    shipped = getattr(order, "shipped", {}) or {}
    for item_id, req_count in requires.items():
        still_needed = max(0, req_count - shipped.get(item_id, 0))
        total_needed += still_needed
        if item_id in lead_cask.HOT_ITEMS:
            in_stock = (cask_stock or lead_cask.network_cask_stock)(item_id)
        else:
            in_stock = max(0, stock(item_id) - reserved.get(item_id, 0))
        items_ready += min(in_stock, still_needed)
    return items_ready, total_needed


def _order_remaining_units(order: "Order"):
    """Total units still owed across every item of order, ignoring stock
    availability entirely -- used for the weekly deadline feasibility check,
    which cares about total shippable volume, not readiness."""
    requires = getattr(order, "requires", {}) or {}
    shipped = getattr(order, "shipped", {}) or {}
    return sum(max(0, req_count - shipped.get(item_id, 0)) for item_id, req_count in requires.items())


def _weekly_infeasible(order: "Order", current_day, dispatch_capacity_per_hour):
    """
    True if order (a Weekly Earth Order) cannot possibly finish shipping its
    remaining amount before `order.expires_day`, given `dispatch_capacity_per_hour`
    units/h of AVAILABLE dock throughput. Deliberately coarse -- this is a
    dispatch-capacity ceiling only ("can the docks physically ship this much in
    time"), not a production-rate forecast ("will we mine/smelt/build enough in
    time"); the latter needs recipe throughput, active worker counts, and
    upstream deficits all folded together and was explicitly punted as a
    "much later" TODO. Returns False (don't block) whenever a required input
    (current day, expiry, capacity) is unavailable -- never blocks an order on
    missing data.
    """
    expires_day = getattr(order, "expires_day", None)
    if expires_day is None or current_day is None or dispatch_capacity_per_hour <= 0:
        return False
    hours_remaining = (expires_day - current_day) * 24.0
    if hours_remaining <= 0:
        return True
    remaining = _order_remaining_units(order)
    if remaining <= 0:
        return False
    max_shippable = dispatch_capacity_per_hour * hours_remaining
    return remaining > max_shippable


def key_unlock_bonus(current_orders, upcoming_orders):
    """
    {current order id: look-ahead bonus}. A current campaign order that is not
    itself a key unlock order gets the weight (early_unlock_weight()) of the
    nearest key order behind it in its contractor's queue (`upcoming_orders`
    keep each queue's sequence), divided by 1 + the orders in front of that
    one. Key orders score their own weight in _score_campaign_order().
    """
    queues = {}
    for order in upcoming_orders or []:
        queues.setdefault(getattr(order, "contractor_id", None), []).append(order.id)
    bonus = {}
    for order in current_orders or []:
        if order.id in EARLY_UNLOCK_ORDER_IDS:
            continue
        for steps, order_id in enumerate(queues.get(getattr(order, "contractor_id", None), []), 1):
            if order_id in EARLY_UNLOCK_ORDER_IDS:
                bonus[order.id] = early_unlock_weight(order_id) / (1 + steps)
                break
    return bonus


def read_order_board(orders_api):
    """(active campaign orders, upcoming campaign orders) of the live board; None when unreadable."""
    try:
        current = [o for o in orders_api.list_orders() if getattr(o, "status", "") == "active"]
        upcoming = orders_api.list_upcoming_orders() if hasattr(orders_api, "list_upcoming_orders") else []
    except Exception as error:
        swallowed("supply_dock.read_order_board: orders_api", error)
        return None
    return current, upcoming


def read_key_unlock_bonus(orders_api):
    """key_unlock_bonus() for the live order board ({} when unreadable)."""
    board = read_order_board(orders_api)
    return key_unlock_bonus(*board) if board else {}


def next_key_orders(upcoming_orders):
    """The first key unlock order (EARLY_UNLOCK_ORDER_IDS) in each contractor's
    upcoming queue (`upcoming_orders` keep each queue's sequence)."""
    seen = set()
    found = []
    for order in upcoming_orders or []:
        contractor = getattr(order, "contractor_id", None)
        if contractor in seen or order.id not in EARLY_UNLOCK_ORDER_IDS:
            continue
        seen.add(contractor)
        found.append(order)
    return found


def key_ahead_items(orders, fabricator_outputs, smelter_outputs):
    """({Fabricator output: units}, {Smelter output: units}) still owed by
    `orders`, summed. Items no unlocked recipe makes yet (raw ore, or a recipe
    an earlier order unlocks) are left out."""
    crafted = {}
    smelted = {}
    for order in orders:
        shipped = getattr(order, "shipped", {}) or {}
        for item_id, required in (getattr(order, "requires", {}) or {}).items():
            units = max(0, required - shipped.get(item_id, 0))
            if not units:
                continue
            if item_id in smelter_outputs:
                smelted[item_id] = smelted.get(item_id, 0) + units
            elif item_id in fabricator_outputs:
                crafted[item_id] = crafted.get(item_id, 0) + units
    return crafted, smelted


def key_ahead_site(orders, docks, roles: "DockRoles"):
    """Outpost id of the dock site most likely to take `orders`, where the
    key-ahead items are consumed: the site whose docks cover the most of the
    orders' role-bound items (DockRoles.coverage()), then the one with the
    most docks, then the lowest id. plan_dock_assignments() ranks orders by
    stock at a dock's outpost (_local_supply()), so items staged there pull
    the order to that dock. NO_CONSUMER_SITE without a dock."""
    sites = {}  # {site_id: [outpost, docks]}
    for dock in docks.values():
        outpost = getattr(dock, "outpost", None)
        site_id = getattr(outpost, "id", None) or home_outpost_id()
        sites.setdefault(site_id, [outpost, 0])[1] += 1
    best = None
    for site_id, (outpost, count) in sites.items():
        covered = sum(roles.coverage(order, outpost)[0] for order in orders)
        rank = (-covered, -count, site_id)
        if best is None or rank < best[0]:
            best = (rank, site_id)
    return best[1] if best else NO_CONSUMER_SITE


def publish_key_ahead(upcoming_orders, cache: "SourceCache", docks, roles: "DockRoles"):
    """Stocks ahead for the next key unlock order of each contractor
    (next_key_orders()), so its items are ready when it becomes current:
    Fabricator and Smelter items as one orders-book entry
    (KEY_AHEAD_REQUESTER) at the ORDER_AHEAD band, which Fabricators and
    Smelters work only when nothing of a higher band is open. Production
    demand otherwise only follows orders a dock holds. Consumed at
    key_ahead_site(), so site supply stages the items at the dock that will
    take the order. Once the order is current a dock takes it and its own
    demand takes over; this entry moves on to the next one."""
    orders = next_key_orders(upcoming_orders)
    smelter_outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()} - {None}
    crafted, smelted = key_ahead_items(orders, fabricator_unlocked_outputs(cache), smelter_outputs)
    ahead = {item_id: [units, ORDER_AHEAD] for item_id, units in list(crafted.items()) + list(smelted.items())}
    site = key_ahead_site(orders, docks, roles) if ahead else None
    set_order(KEY_AHEAD_REQUESTER, ahead, site=site)
    if ahead:
        log.debug(f"key ahead for {[o.id for o in orders]} at '{site}': crafted={crafted} smelted={smelted}")


def _score_campaign_order(order: "Order", reserved, stock=None, cask_stock=None, key_bonus=0):
    prio = 10
    if getattr(order, "reward_kind", "") in ["recipe", "tech"]:
        prio += 50  # Strongly prioritize technology and recipe unlocks!
    prio += early_unlock_weight(getattr(order, "id", None)) + int(key_bonus)
    items_ready, total_needed = _order_readiness(order, reserved, stock, cask_stock)
    if total_needed > 0:
        prio += int((items_ready / total_needed) * CAMPAIGN_READINESS_WEIGHT)
    return prio


def _score_weekly_order(order: "Order", reserved, stock=None, cask_stock=None):
    prio = 5
    items_ready, total_needed = _order_readiness(order, reserved, stock, cask_stock)
    if total_needed > 0:
        prio += int((items_ready / total_needed) * 20)
    return prio


def _servable_at(order: "Order", outpost: "OutpostRef | None", has_cask):
    """False for an order with hot items (Raw Uranium, Fuel Rods) at a dock whose outpost has no
    Lead Cask: hot cargo reaches a dock only from a cask at its own outpost. has_cask: {outpost_id: bool} memo."""
    if not any(item_id in lead_cask.HOT_ITEMS for item_id in (getattr(order, "requires", {}) or {})):
        return True
    return _has_cask(outpost, has_cask)


def _has_cask(outpost: "OutpostRef | None", has_cask):
    """Whether outpost has a Lead Cask. has_cask: {outpost_id: bool} memo."""
    key = getattr(outpost, "id", None)
    if key not in has_cask:
        has_cask[key] = bool(lead_cask.casks_at(outpost))
    return has_cask[key]


def _local_cask_units(order: "Order", outpost: "OutpostRef | None"):
    """Still-owed hot units (Raw Uranium, Fuel Rods) of order that the Lead Casks at
    `outpost` hold right now. Hot cargo loads only from a cask at the dock's own
    outpost, so a dock beside a stocked cask is the one place that can ship it."""
    requires = getattr(order, "requires", {}) or {}
    shipped = getattr(order, "shipped", {}) or {}
    units = 0
    for item_id, req_count in requires.items():
        if item_id in lead_cask.HOT_ITEMS:
            still_needed = max(0, req_count - shipped.get(item_id, 0))
            if still_needed:
                units += min(still_needed, lead_cask.cask_stock(item_id, outpost))
    return units


def _cask_order_ids(candidates, outpost: "OutpostRef | None", has_cask, memo):
    """Ids of candidate orders the Lead Casks at `outpost` can ship from right now
    (_local_cask_units() > 0); a dock there takes these first. Empty without a cask.
    memo: {(outpost_id, order_id): units}."""
    if not _has_cask(outpost, has_cask):
        return set()
    out_id = getattr(outpost, "id", None)
    ids = set()
    for c in candidates:
        order = c["order"]
        key = (out_id, order.id)
        if key not in memo:
            memo[key] = _local_cask_units(order, outpost)
        if memo[key] > 0:
            ids.add(order.id)
    return ids


def _key_rush(docks_on, local):
    """Whether a key unlock order still pulls a dock ahead of other orders: no
    dock holds it yet (one dock is enough to drive its production chain,
    production_docks._all_dock_orders()), or the dock's outpost stocks some of
    it. More docks on a bare key order would only wait while ready orders sit."""
    return docks_on == 0 or local > 0


def _key_order_ids(candidates, outpost: "OutpostRef | None", roles, docks_on, local_of):
    """Ids of key-unlock candidate orders (EARLY_UNLOCK_ORDER_IDS) a dock at `outpost` serves
    and still rushes (_key_rush()); an empty dock leaves any other order for one of these.
    docks_on: {order_id: other docks holding it}; local_of(order): _local_supply() rank."""
    return {c["order"].id for c in candidates if c.get("key") and roles.serves(c["order"], outpost) and (not docks_on.get(c["order"].id, 0) or local_of(c["order"]) > 0)}


def _dock_loaded(dock):
    """Units physically loaded in dock (0 if unreadable)."""
    if not hasattr(dock, "total"):
        return 0
    try:
        return dock.total()
    except Exception as error:
        swallowed("supply_dock._dock_loaded: dock.total", error)
        return 0


def _dock_affinity(order: "Order", outpost: "OutpostRef | None", cache: "SourceCache", site_plan=None):
    """How well a dock at `outpost` suits order: units of its still-owed items
    already held there (cache.held_stock(): Warehouses, Drone Depots, home
    Inventory), plus one per item whose tree the site plan builds there.
    Only breaks ties between equally ranked orders/docks."""
    site_id = getattr(outpost, "id", None) or home_outpost_id()
    site_plan = site_plan or {}
    requires = getattr(order, "requires", {}) or {}
    shipped = getattr(order, "shipped", {}) or {}
    score = 0
    for item_id, req_count in requires.items():
        still_needed = max(0, req_count - shipped.get(item_id, 0))
        if item_id in lead_cask.HOT_ITEMS:
            score += min(still_needed, lead_cask.cask_stock(item_id, outpost))
        else:
            score += min(still_needed, cache.held_stock(item_id, outpost))
        if site_id in (site_plan.get(item_id) or []):
            score += 1
    return score


def _local_supply(order: "Order", outpost: "OutpostRef | None", cache: "SourceCache", reserved=None, promised=None):
    """(rank, claim): how much of order's still-owed units the dock site at
    `outpost` holds unpromised right now, as 0..LOCAL_STOCK_STEPS, and the
    {item_id: units} that covers. Held = cache.held_stock() (Warehouses,
    Drone Depots, home Inventory; a Depot drains to local stores before the
    dock loads). Unpromised = less active Construction Blueprint
    reservations (home only, like step()'s loading) and less units other
    docks at this site already claimed this pass (promised:
    {(site_id, item_id): units}). A weekly order counts only when fully
    covered: shipped in part, it expires unfinished and the units are lost."""
    site_id = getattr(outpost, "id", None) or home_outpost_id()
    at_home = outpost_is_home(outpost)
    reserved = reserved or {}
    promised = promised or {}
    requires = getattr(order, "requires", {}) or {}
    shipped = getattr(order, "shipped", {}) or {}
    total = covered = 0
    claim = {}
    for item_id, req_count in requires.items():
        still_needed = max(0, req_count - shipped.get(item_id, 0))
        if not still_needed:
            continue
        total += still_needed
        if item_id in lead_cask.HOT_ITEMS:
            local = lead_cask.cask_stock(item_id, outpost)
        else:
            local = cache.held_stock(item_id, outpost)
            if at_home:
                local -= reserved.get(item_id, 0)
        units = max(0, min(still_needed, local - promised.get((site_id, item_id), 0)))
        if units:
            claim[item_id] = units
            covered += units
    if total <= 0 or (getattr(order, "kind", "") == "weekly" and covered < total):
        return 0, {}
    return int(covered * LOCAL_STOCK_STEPS / total), claim


def _promise(promised, outpost: "OutpostRef", claim):
    """Adds a dock's _local_supply() claim to promised, so other docks at its site rank on what is left."""
    site_id = getattr(outpost, "id", None) or home_outpost_id()
    for item_id, units in claim.items():
        promised[(site_id, item_id)] = promised.get((site_id, item_id), 0) + units


def plan_signature():
    """
    Cheap fingerprint of what plan_dock_assignments() decides on: every Earth
    Order's (id, status) plus the discovered dock ids. orchestrator_automation.py
    replans when it changes (an order appears, completes or expires; a dock is
    built or removed) and otherwise only on its backstop interval. Left out on
    purpose: shipped progress and stock (they change constantly while docks
    ship and only move ranking) and each dock's current order (a dock switching
    orders passes through old -> none -> new; a finished order already shows in
    its status).
    """
    orders = []
    orders_api = get_component("orders")
    if orders_api:
        for getter in ("list_orders", "list_weekly_orders"):
            try:
                orders.extend((str(getattr(o, "id", "")), str(getattr(o, "status", ""))) for o in getattr(orders_api, getter)())
            except Exception as error:
                swallowed(f"supply_dock.plan_signature: orders_api.{getter}", error)
    return (tuple(sorted(orders)), tuple(sorted(discover_supply_dock_ids())))


def plan_dock_assignments(clock: "Clock | None" = None):
    """
    Central per-cycle decision, run once from orchestrator_automation.py's AUTOMATION section:
    which Earth Order (if any) each discovered Supply Dock should be working.
    Docks already holding a still-fulfillable order keep it (stability -- an
    order mid-shipment shouldn't get cleared over a marginal priority
    difference elsewhere, and clearing loses no progress but does cost a
    drain-then-reassign cycle for nothing). Idle/unfulfillable-order docks
    rank candidates by unpromised stock at their own outpost first
    (_local_supply(): ship what is already there), then by the fewest docks
    at the same outpost already on the order (spread inside an outpost),
    role share, priority, and only then the network-wide dock count -- across
    outposts, local stock and priority beat spreading. Writes the plan to
    archive and returns it.
    """
    log.start("plan_dock_assignments", level="debug")
    orders_api = get_component("orders")
    if not orders_api:
        log.end()
        return {}

    docks = {}
    for dock_id in discover_supply_dock_ids():
        dock = supply_dock(dock_id)
        if dock and hasattr(dock, "current_order"):
            docks[dock_id] = dock
    if not docks:
        log.end()
        return {}

    # Shared across every can_fulfill_order() call and readiness score in this
    # pass (every candidate order, each dock's current order) -- see SourceCache's
    # docstring in lib/production.py. The pass runs from the headless
    # automation/orchestrator_automation.py, never inside a per-tick UI loop.
    cache = SourceCache()
    reserved = get_construction_material_reservations(cache)
    current_day = clock.get_day() if clock and hasattr(clock, "get_day") else None

    total_dispatch_capacity = 0.0
    for dock in docks.values():
        try:
            total_dispatch_capacity += dock.dispatch_rate()
        except Exception as error:
            swallowed("supply_dock.plan_dock_assignments: dock.dispatch_rate", error)

    candidates = []
    # {order_id: can_fulfill_order()} for every active order, so a dock's current order is not re-checked.
    fulfillable = {}
    roles = DockRoles(cache)
    board = read_order_board(orders_api)
    key_bonus = key_unlock_bonus(*board) if board else {}
    if board:
        publish_key_ahead(board[1], cache, docks, roles)
    publish_drone_kit_order(cache)
    overrides = order_overrides()

    def check_order(order: "Order"):
        if order.id not in fulfillable:
            fulfillable[order.id] = can_fulfill_order(order, cache)
        return fulfillable[order.id]

    try:
        for o in orders_api.list_orders():
            if getattr(o, "status", "") == "active" and check_order(o):
                score = _score_campaign_order(o, reserved, cache.held_stock, cache.cask_stock, key_bonus.get(o.id, 0))
                prio = _order_prio(o, score, overrides)
                candidates.append({"order": o, "score": score, "prio": prio, "key": o.id in EARLY_UNLOCK_ORDER_IDS})
                log.debug(f"campaign order '{getattr(o, 'name', o.id)}' is a candidate, score={score} prio={prio}")
    except Exception as error:
        swallowed("supply_dock.plan_dock_assignments: orders_api.list_orders", error)
    try:
        for o in orders_api.list_weekly_orders():
            if getattr(o, "status", "") != "active" or not check_order(o):
                continue
            if _weekly_infeasible(o, current_day, total_dispatch_capacity):
                log.level("warn").print(f"[supply_dock planner] Skipping Weekly Earth Order '{getattr(o, 'name', o.id)}': remaining amount can't ship before it expires on day {o.expires_day}.")
                continue
            score = _score_weekly_order(o, reserved, cache.held_stock, cache.cask_stock)
            prio = _order_prio(o, score, overrides)
            candidates.append({"order": o, "score": score, "prio": prio, "key": False})
            log.debug(f"weekly order '{getattr(o, 'name', o.id)}' is a candidate, score={score} prio={prio}")
    except Exception as error:
        swallowed("supply_dock.plan_dock_assignments: orders_api.list_weekly_orders", error)
    publish_order_prios(candidates, overrides)

    log.debug(f"{len(candidates)} candidate order(s), {len(docks)} discovered dock(s), total_dispatch_capacity={total_dispatch_capacity:.1f} u/h")

    site_plan = archive.get(SITE_PLAN_KEY, {})
    site_plan = site_plan if isinstance(site_plan, dict) else {}
    has_cask = {}
    # {(outpost_id, order_id): _local_cask_units()}, shared by the stability and assignment passes.
    cask_units = {}

    plan = {}
    idle_dock_ids = []
    assigned_counts = {}
    # {(site_id, order_id): docks}: the spread inside one outpost.
    site_counts = {}
    # {(site_id, item_id): units} of local stock claimed by docks already planned this pass.
    promised = {}

    def assign(dock_id, outpost, order):
        site_id = getattr(outpost, "id", None) or home_outpost_id()
        plan[dock_id] = order.id
        assigned_counts[order.id] = assigned_counts.get(order.id, 0) + 1
        site_counts[(site_id, order.id)] = site_counts.get((site_id, order.id), 0) + 1
        _promise(promised, outpost, _local_supply(order, outpost, cache, reserved, promised)[1])

    currents = {}
    for dock_id, dock in docks.items():
        try:
            currents[dock_id] = dock.current_order()
        except Exception as error:
            swallowed("supply_dock.plan_dock_assignments: dock.current_order", error)
            currents[dock_id] = None
    # {order_id: docks holding it}, for _key_order_ids() (other docks only).
    held_counts = {}
    for curr in currents.values():
        if curr:
            held_counts[curr.id] = held_counts.get(curr.id, 0) + 1

    for dock_id, dock in docks.items():
        curr = currents[dock_id]
        if curr and check_order(curr):
            outpost = getattr(dock, "outpost", None)
            loaded = _dock_loaded(dock)
            if loaded == 0 and not roles.serves(curr, outpost):
                log.debug(f"{dock_id} is empty and its site ({roles.describe(outpost)}) covers no item of '{curr.id}', leaves it")
                idle_dock_ids.append(dock_id)
                continue
            cask_ids = _cask_order_ids(candidates, outpost, has_cask, cask_units)
            others = dict(held_counts)
            others[curr.id] -= 1
            key_ids = _key_order_ids(candidates, outpost, roles, others, lambda o: _local_supply(o, outpost, cache, reserved, promised)[0])  # noqa: B023 (called within the iteration)
            if loaded == 0 and key_ids and curr.id not in key_ids and curr.id not in cask_ids:
                log.debug(f"{dock_id} is empty and can serve key order(s) {sorted(key_ids)}, leaves '{curr.id}'")
                idle_dock_ids.append(dock_id)
                continue
            if not cask_ids or curr.id in cask_ids or loaded > 0:
                assign(dock_id, outpost, curr)
                log.debug(f"{dock_id} keeps still-fulfillable current order '{curr.id}' (stability)")
                continue
            log.debug(f"{dock_id} is empty and its Lead Cask holds cargo for {sorted(cask_ids)}, leaves '{curr.id}'")
        else:
            log.debug(f"{dock_id} is idle/unfulfillable ({'no current order' if not curr else 'current order no longer fulfillable'}), needs a new assignment")
        idle_dock_ids.append(dock_id)

    if candidates:
        for dock_id in idle_dock_ids:
            outpost = getattr(docks[dock_id], "outpost", None)
            eligible = [c for c in candidates if _servable_at(c["order"], outpost, has_cask) and roles.serves(c["order"], outpost)]
            if not eligible:
                plan[dock_id] = None
                log.debug(f"{dock_id}: no candidate it can serve (site roles: {roles.describe(outpost)}; hot cargo needs a Lead Cask), left unassigned")
                continue
            # Scored before the sort: _dock_affinity() may read storage (a remote
            # outpost's first local_stock()), which must not run inside a key callback.
            cask_ids = _cask_order_ids(eligible, outpost, has_cask, cask_units)
            site_id = getattr(outpost, "id", None) or home_outpost_id()
            for c in eligible:
                c["affinity"] = _dock_affinity(c["order"], outpost, cache, site_plan)
                c["share"] = roles.share(c["order"], outpost)
                c["local"] = _local_supply(c["order"], outpost, cache, reserved, promised)[0]
                c["rush"] = c["key"] and _key_rush(assigned_counts.get(c["order"].id, 0), c["local"])
            eligible.sort(key=lambda c: (c["order"].id not in cask_ids, not c["rush"], -c["local"], site_counts.get((site_id, c["order"].id), 0), -c["share"], -c["prio"], assigned_counts.get(c["order"].id, 0), -c["affinity"]))
            best = eligible[0]["order"]
            assign(dock_id, outpost, best)
            log.debug(f"assigned {dock_id} -> order '{best.id}' (local stock={eligible[0]['local']}/{LOCAL_STOCK_STEPS}, already {assigned_counts[best.id] - 1} dock(s) on it, role share={eligible[0]['share']:.2f}, prio={eligible[0]['prio']})")
    else:
        for dock_id in idle_dock_ids:
            plan[dock_id] = None
            log.debug(f"no fulfillable candidate orders at all, {dock_id} left unassigned")

    previous_plan = archive.get(ORDER_PLAN_ARCHIVE_KEY, {})
    previous_plan = previous_plan if isinstance(previous_plan, dict) else {}
    if plan != previous_plan:
        log.print(f"[supply_dock planner] Dock assignments changed: {plan}")
    archive.set(ORDER_PLAN_ARCHIVE_KEY, plan)
    _wake_for_plan(plan)
    log.end()
    return plan


def _wake_for_plan(plan):
    """Wakes each parked dock the plan gives an order. The Fabricators and Smelters an order
    may need are woken by the demand publisher once the record carries it
    (demand_publisher.wake_risen()): woken now, they would read the old record and park again."""
    parked = parked_ids("supply_dock")
    for dock_id, order_id in plan.items():
        if order_id and dock_id in parked:
            wake_for_visit(dock_id, reason=f"order assigned: {order_id}", hold=False)


class SupplyDockController(MachineController):
    """
    Automated controller for the Supply Dock.
    Prioritizes recipe/tech-unlocking campaign orders (Spire, Helios, Vestibule),
    loads materials from Inventory, and drives high-efficiency shipping to Earth.
    """

    LABEL = "Supply Dock"
    POLL_S = 3.0

    def online_message(self):
        return f"Supply Dock Controller ({self.name}) online. Initializing logistics loop..."

    def next_sleep(self, result, failed):
        if failed:
            self.idle = False
        self.parker.update(self.idle)
        return self.POLL_S

    def __init__(self, dock):
        self.dock = dock
        self.name = getattr(dock, "id", "supply_dock_1")
        self.orders_api = get_component("orders")
        self.inventory = get_component("inventory")
        self.connected = False
        self._warned_no_local_storage = False
        self._last_report = ""
        self.idle = False  # standing by: no order, no cargo (set by step())
        self.plan_assigned = False  # last desired_order_id() came from the central plan
        self.order_docks: int = 1  # docks the central plan puts on this dock's order (load_chunk() share)
        self._last_step_hours = None  # game hours at the previous step() start (load_chunk() gap)
        self.parker = ParkRequester(self.name, "supply_dock")
        self.log = TreeConsole(module="supply_dock")

    def outpost(self):
        """OutpostRef this dock is deployed at (None if not exposed = home)."""
        return getattr(self.dock, "outpost", None)

    def at_home(self):
        return outpost_is_home(self.outpost())

    def ensure_connected(self):
        """Connects the dock input port to Inventory at home, or to a local
        Warehouse elsewhere (storage.local_port_target())."""
        if self.connected or not hasattr(self.dock, "input"):
            return
        target = local_port_target(self.outpost())
        if target is None:
            if not self._warned_no_local_storage:
                self._warned_no_local_storage = True
                self.log.level("warn").print(f"[{self.name}] No Warehouse at outpost '{machine_outpost_id(self.dock)}' -- a remote Supply Dock can only load from local storage.")
            return
        self._warned_no_local_storage = False
        try:
            self.dock.input.connect(target)
            self.connected = True
        except Exception as error:
            swallowed("supply_dock.SupplyDockController.ensure_connected: self.dock.input.connect", error)

    def drain_dock_cargo(self):
        """
        Ejects any cargo still physically loaded in the dock's slots back to
        Inventory (a local Warehouse off home). clear_order() explicitly does not drain cargo -- it just
        releases the assignment and leaves loaded materials in place -- so
        set_order() for a *new* order keeps rejecting with "cargo_present"
        until something actively empties the dock first.
        """
        if not hasattr(self.dock, "slots") or not hasattr(self.dock, "input"):
            return
        self.log.start(f"[{self.name}] Draining dock cargo")
        ejected = 0
        try:
            for slot in self.dock.slots():
                item_id = getattr(slot, "item_id", None)
                count = getattr(slot, "count", 0)
                if not item_id or count <= 0:
                    continue
                if item_id in lead_cask.HOT_ITEMS:
                    target = lead_cask.unload_target(item_id, self.outpost())
                else:
                    target = "inventory" if self.at_home() else best_unload_target(item_id, 1, outpost=self.outpost())
                if target == "inventory" and inventory_room(item_id) <= 0:
                    target = None
                elif target == "inventory":
                    count = min(count, inventory_room(item_id))
                if target is None:
                    self.log.level("warn").print(f"[{self.name}] No local {'Lead Cask' if item_id in lead_cask.HOT_ITEMS else 'Warehouse'} room for {count}x {item_id} -- left in the dock.")
                    continue
                res = self.dock.input.eject(target, item_id, count)
                if res.status == "ok":
                    ejected += 1
                    self.log.print(f"[{self.name}] Ejected {count}x {item_id} from dock back to {'Inventory' if target == 'inventory' else target}.")
                elif res.status not in ["busy", "no_op"]:
                    self.log.level("warn").print(f"[{self.name}] Eject notice for {item_id}: {res.status} - {res.message}")
        except Exception as error:
            swallowed("supply_dock.SupplyDockController.drain_dock_cargo: self.dock.slots", error)
        self.log.end(f"[{self.name}] Dock drain done: {ejected} slot(s) ejected")

    def pick_best_order(self):
        """
        Fallback order selection used only when no central plan is available
        (see desired_order_id()) -- orchestrator_automation.py's plan_dock_assignments() is
        the normal path and additionally spreads docks across candidates and
        skips weekly orders that can't finish before they expire. This
        per-instance fallback keeps a lone dock functional standalone:
        1. Key unlock orders (EARLY_UNLOCK_ORDER_IDS, in their order), then other
           campaign orders that unlock recipes or technology.
        2. Orders where materials are already available in Inventory.
        3. Other active campaign orders.
        4. Weekly Earth orders.
        """
        self.log.start(f"[{self.name}] pick_best_order", level="debug")
        if not self.orders_api:
            self.log.end()
            return None

        candidates = []
        reserved = get_construction_material_reservations()
        key_bonus = read_key_unlock_bonus(self.orders_api)
        cache = SourceCache()
        overrides = order_overrides()

        try:
            for o in self.orders_api.list_orders():
                if getattr(o, "status", "") == "active" and can_fulfill_order(o, cache):
                    score = _score_campaign_order(o, reserved, cache.held_stock, cache.cask_stock, key_bonus.get(o.id, 0))
                    candidates.append({"order": o, "score": score, "prio": _order_prio(o, score, overrides), "key": o.id in EARLY_UNLOCK_ORDER_IDS})
        except Exception as error:
            swallowed("supply_dock.SupplyDockController.pick_best_order: self.orders_api.list_orders", error)

        try:
            current_day = None
            clock = get_component("clock")
            if clock and hasattr(clock, "get_day"):
                current_day = clock.get_day()
            dispatch_capacity = self.dock.dispatch_rate() if hasattr(self.dock, "dispatch_rate") else 0.0
            for o in self.orders_api.list_weekly_orders():
                if getattr(o, "status", "") != "active" or not can_fulfill_order(o, cache):
                    continue
                if _weekly_infeasible(o, current_day, dispatch_capacity):
                    self.log.level("warn").print(f"[{self.name}] Skipping '{getattr(o, 'name', o.id)}': can't ship remaining amount before it expires on day {o.expires_day}.")
                    continue
                score = _score_weekly_order(o, reserved, cache.held_stock, cache.cask_stock)
                candidates.append({"order": o, "score": score, "prio": _order_prio(o, score, overrides), "key": False})
        except Exception as error:
            swallowed("supply_dock.SupplyDockController.pick_best_order: get_component", error)
        publish_order_prios(candidates, overrides)

        has_cask = {}
        roles = DockRoles()
        candidates = [c for c in candidates if _servable_at(c["order"], self.outpost(), has_cask) and roles.serves(c["order"], self.outpost())]
        if not candidates:
            self.log.debug(f"no fulfillable candidate orders this dock can serve (site roles: {roles.describe(self.outpost())})")
            self.log.end()
            return None

        site_plan = archive.get(SITE_PLAN_KEY, {})
        site_plan = site_plan if isinstance(site_plan, dict) else {}
        cask_ids = _cask_order_ids(candidates, self.outpost(), has_cask, {})
        for c in candidates:
            c["affinity"] = _dock_affinity(c["order"], self.outpost(), cache, site_plan)
            c["share"] = roles.share(c["order"], self.outpost())
            c["local"] = _local_supply(c["order"], self.outpost(), cache, reserved)[0]
        candidates.sort(key=lambda c: (c["order"].id not in cask_ids, not c["key"], -c["local"], -c["share"], -c["prio"], -c["affinity"]))
        winner = candidates[0]["order"]
        self.log.debug(f"picked '{getattr(winner, 'name', winner.id)}' (local stock={candidates[0]['local']}/{LOCAL_STOCK_STEPS}, prio={candidates[0]['prio']}, affinity={candidates[0]['affinity']}, local cask={winner.id in cask_ids}) among {len(candidates)} candidate(s)")
        self.log.end()
        return winner

    def desired_order_id(self):
        """Reads this dock's assignment from the central plan (see
        plan_dock_assignments()); falls back to this dock's own
        pick_best_order() if no plan has been computed yet (or ever)."""
        self.log.start(f"[{self.name}] desired_order_id", level="debug")
        plan = archive.get(ORDER_PLAN_ARCHIVE_KEY, {}) or {}
        if self.name in plan:
            planned_id = plan[self.name]
            if planned_id is None or self.order_is_active(planned_id):
                self.log.debug(f"using central plan assignment -> {planned_id!r}")
                self.log.end()
                self.plan_assigned = True
                self.order_docks = max(1, len([order_id for order_id in plan.values() if order_id == planned_id]))
                return planned_id
            self.log.debug(f"central plan assignment {planned_id!r} is no longer active (plan older than the order's completion)")
        self.plan_assigned = False
        self.order_docks = 1
        best = self.pick_best_order()
        self.log.debug(f"fell back to pick_best_order() -> {getattr(best, 'id', None)!r}")
        self.log.end()
        return best.id if best else None

    def order_is_active(self, order_id):
        """Whether order_id is still an active Earth Order. The central plan is recomputed every few
        seconds (orchestrator_automation DOCK_PLAN_TICK_INTERVAL), so an entry can name an order that completed since."""
        if not self.orders_api:
            return True
        try:
            order = self.orders_api.get_order(order_id)
        except Exception as error:
            swallowed("supply_dock.SupplyDockController.order_is_active: orders_api.get_order", error)
            return True
        return order is not None and getattr(order, "status", "") == "active"

    def assign_order(self, desired_id, order_name, reward_desc):
        """Sets desired_id on the dock; False when it did not take (cargo still loaded, or rejected)."""
        self.log.start(f"[{self.name}] Assigning Earth Order '{order_name}' (ID: {desired_id}, Reward: {reward_desc})...")
        res = self.dock.set_order(desired_id)
        assigned = res.status == "ok"
        if res.status == "cargo_present":
            # Defensive fallback in case cargo appeared between the total()
            # check in step() and this call -- drain and let the next cycle retry.
            self.log.debug(f"[{self.name}] assign_order: cargo appeared since the last check, draining and retrying next cycle")
            self.drain_dock_cargo()
        elif res.status in ("completed", "unknown_order"):
            self.log.debug(f"[{self.name}] assign_order: order already {res.status}, waiting for the next plan")
        elif not assigned:
            self.log.level("warn").print(f"[{self.name}] Could not assign order: {res.status} - {res.message}")
        self.log.end(f"[{self.name}] Order '{order_name}': {'assigned' if assigned else res.status}")
        return assigned

    def step(self):
        self.idle = False
        step_hours = now_hours(None, where="supply_dock.step")
        gap_hours = None if step_hours is None or self._last_step_hours is None else step_hours - self._last_step_hours
        self._last_step_hours = step_hours
        self.ensure_connected()

        curr_order = self.dock.current_order()
        desired_id = self.desired_order_id()

        # Step 1: Assign order if dock is currently idle
        # The central plan keeps a current order only while can_fulfill_order() holds
        # (plan_dock_assignments() stability pass), so a plan naming it skips the re-check:
        # ~40% of a step's interpreter steps (devtools/perf/step_profile.py dock_step).
        planned_current = self.plan_assigned and curr_order is not None and getattr(curr_order, "id", None) == desired_id
        if curr_order and not planned_current and not can_fulfill_order(curr_order):
            loaded = 0
            if hasattr(self.dock, "count"):
                for item_id in getattr(curr_order, "requires", {}) or {}:
                    loaded += self.dock.count(item_id)
            if loaded == 0 and hasattr(self.dock, "clear_order"):
                clear_res = self.dock.clear_order()
                if clear_res.status == "ok":
                    self.log.print(f"[{self.name}] Cleared undeliverable order '{curr_order.name}'.")
                    curr_order = None

        # Only the central plan moves a dock off a still-fulfillable order (it releases an
        # empty dock for an order its Lead Cask can ship, or from an order its site covers
        # no item of -- then the plan entry may be None); the per-dock fallback never does.
        if curr_order and self.plan_assigned and getattr(curr_order, "id", None) != desired_id:
            if _dock_loaded(self.dock) == 0 and hasattr(self.dock, "clear_order"):
                clear_res = self.dock.clear_order()
                if clear_res.status == "ok":
                    if desired_id:
                        self.log.print(f"[{self.name}] Switching from '{curr_order.name}' to planned order '{desired_id}'.")
                    else:
                        self.log.print(f"[{self.name}] Released '{curr_order.name}': planner has no order for this dock's site.")
                    curr_order = None

        if not curr_order:
            # set_order() rejects with "cargo_present" while any cargo is
            # still physically loaded -- including leftovers from a
            # previously cleared/completed/expired order, since clear_order()
            # never drains the dock itself. Drain first and retry next cycle
            # rather than repeatedly failing set_order() forever.
            if hasattr(self.dock, "total") and self.dock.total() > 0:
                self.drain_dock_cargo()
                return

            if not desired_id:
                self.idle = True
                self.report("standby", f"[{self.name}] No active Earth Orders available. Standing by.")
                return

            best = self.orders_api.get_order(desired_id) if self.orders_api else None
            reward_desc = f"{getattr(best, 'reward_credits', '?')} cr" if best else ""
            if best and getattr(best, "reward_kind", None):
                reward_desc += f" + {best.reward_kind} ({getattr(best, 'reward_label', '')})"

            order_name = getattr(best, "name", desired_id) if best else desired_id
            if not self.assign_order(desired_id, order_name, reward_desc):
                return
            curr_order = self.dock.current_order()

        # Step 2: Load required materials from Inventory or a Warehouse, but
        # never take stock an active Construction Blueprint is waiting on --
        # otherwise the Dock can "snack away" materials (e.g. titanium
        # ingots) out from under a Pioneer build the moment they land in
        # storage, well before the build gets a chance to collect them.
        # Sized by load_chunk(): the dispatch until the next step, split
        # over the docks sharing the order (docs/components/supply_dock.md),
        # which may contest the same Inventory/Warehouse stock for the same
        # item -- see the module docstring's note on the fairness fix this
        # mirrors from Fabricator/Smelter loading.
        # Off home only the outpost's own Warehouses count; blueprint
        # reservations hold home stock only.
        if curr_order and hasattr(curr_order, "requires"):
            at_home = self.at_home()
            outpost = None if at_home else self.outpost()
            reserved = get_construction_material_reservations() if at_home else remote_dock_reservations()
            cache = None if at_home else SourceCache()
            shipped = getattr(curr_order, "shipped", {}) or {}
            rate = self.dock.dispatch_rate()
            dock_total = self.dock.total()
            for item_id, req_total in curr_order.requires.items():
                already_shipped = shipped.get(item_id, 0)
                in_dock = self.dock.count(item_id)
                needed = max(0, req_total - already_shipped - in_dock)
                if needed <= 0:
                    continue

                # Hot cargo (Raw Uranium, Fuel Rods) only comes out of this outpost's Lead Casks.
                # Fuel Rods leave the local Reactors' and Mk IV generators' reserve in the casks.
                hot = item_id in lead_cask.HOT_ITEMS
                if item_id == lead_cask.ROD_ITEM:
                    avail, held = lead_cask.rods_for_orders(self.outpost())
                    if held:
                        self.log.debug(f"[{self.name}] {item_id}: {held} held back for local Reactors / Mk IV generators")
                elif hot:
                    avail = lead_cask.cask_stock(item_id, self.outpost())
                else:
                    avail = total_stock(item_id) if cache is None else cache.local_stock(item_id, outpost)
                available_after_reservation = max(0, avail - reserved.get(item_id, 0))
                to_take = min(needed, load_chunk(rate, gap_hours, dock_total, available_after_reservation, self.order_docks))
                self.log.debug(f"[{self.name}] {item_id}: needed={needed} avail={avail} reserved={reserved.get(item_id, 0)} available_after_reservation={available_after_reservation} rate={rate:.0f} gap_h={gap_hours} docks={self.order_docks} -> to_take={to_take}")
                if to_take > 0:
                    if hot:
                        moved = lead_cask.take_from_casks(self.dock.input, item_id, to_take, self.outpost())
                    else:
                        moved = take_item(self.dock.input, item_id, to_take, outpost=outpost)
                    dock_total += moved
                    if moved > 0:
                        self.log.print(f"[{self.name}] Loaded {moved}x {item_id} toward '{curr_order.name}' (Dock holds: {self.dock.count(item_id)}/{req_total}).")
                elif avail > 0 and item_id in reserved:
                    self.log.level("warn").print(f"[{self.name}] Holding back {item_id}: all {avail} unit(s) in storage reserved by active Construction Blueprint(s).")

        # Step 3: Enable continuous dispatch
        if not self.dock.is_enabled() and self.dock.total() > 0:
            e_res = self.dock.set_enabled(True)
            if e_res.status == "ok":
                self.log.print(f"[{self.name}] Dispatch enabled at {self.dock.dispatch_rate():.0f} units/h.")

        # Step 4: Status report
        active_disp = self.dock.current_dispatch()
        if active_disp:
            rate = self.dock.dispatch_rate()
            self.report(f"ship:{active_disp}", f"[{self.name}] Shipping {active_disp} (Rate: {rate:.0f} u/h).")

    def report(self, key, message):
        """Info line only when the dock's state (key) changes: each console write costs 0.1 s of
        simulation time (docs/BENCHMARK.md), so a steady state is not re-printed every poll."""
        if key == self._last_report:
            self.log.trace(message)
            return
        self._last_report = key
        self.log.print(message)
