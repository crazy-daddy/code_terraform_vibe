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
# called once per cycle from control_room_automation.py's AUTOMATION section (this script's own
# `set_order()`/`clear_order()`/`set_enabled()` are all `*(self only)*` hardware
# calls per docs/components/supply_dock.md, so the plan itself has to be computed
# somewhere else and handed to each dock via Archive; each dock's own
# `SupplyDockController` then reads its assignment and performs the self-only
# calls on itself). `desired_order_id()` falls back to this dock's own
# `pick_best_order()` if no plan is available yet (control_room_automation not running this
# cycle, or not running at all) so a dock never sits idle waiting on a planner
# that may not be online.
#
# Docks at any outpost (production.discover_supply_dock_ids() is network-wide):
# a dock off home loads from and drains to its own outpost's Warehouses
# (Inventory is home-only), and plan_dock_assignments() breaks priority ties
# toward the dock whose outpost already holds or plans to build (production
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
# (5_steampower lib/site_supply.py). An empty dock leaves an order it covers
# nothing of, so a dock at a nuclear site without Fabricators never waits on
# a crafted-only order.
from production import can_fulfill_order, get_construction_material_reservations, discover_supply_dock_ids, discover_fabricator_ids, discover_smelter_ids, machine_outpost_id, home_outpost_id, SourceCache, SITE_PLAN_KEY
from storage import take_item, total_stock, warehouse_stock, local_port_target, best_unload_target, outpost_is_home
from outpost_mining import assigned_ores_by_outpost, RAW_ORE_ITEM_IDS
import lead_cask
from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from script_parking import ParkRequester

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

# Dock site roles (module comment).
ROLE_FAB = "fab"
ROLE_MINE = "mine"
ROLE_CASK = "cask"


class DockRoles:
    """Per-pass memo of dock site roles and item kinds (module comment).
    Never held across passes: a new building changes a site's roles."""

    def __init__(self, cache=None):
        self.cache = cache if cache is not None else SourceCache()
        self._fab_items = None
        self._mine_items = None
        self._marker_ores = None
        self._sites = {}

    def item_roles(self, item_id):
        """Roles that ship item_id; empty = any dock ships it."""
        if item_id in lead_cask.HOT_ITEMS:
            return {ROLE_CASK}
        if self._fab_items is None:
            self._fab_items = {getattr(r, "output_item", None) for r in self.cache.fabricator_recipes()} - {None}
            self._mine_items = set(RAW_ORE_ITEM_IDS) | ({getattr(r, "output_item", None) for r in self.cache.smelter_recipes()} - {None})
        roles = set()
        if item_id in self._fab_items:
            roles.add(ROLE_FAB)
        if item_id in self._mine_items:
            roles.add(ROLE_MINE)
        return roles

    def site(self, outpost):
        """(roles, marker ores) of the dock site `outpost` (None = home); (None, None) when the site can't be resolved."""
        if outpost is None:
            outpost = lead_cask.home_outpost()
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

    def covers(self, item_id, outpost):
        """Whether a dock at `outpost` ships item_id itself (no hauling needed)."""
        item_roles = self.item_roles(item_id)
        if not item_roles:
            return True
        site_roles, ores = self.site(outpost)
        if site_roles is None:
            return True
        return bool(item_roles & site_roles) or (ROLE_MINE in item_roles and item_id in ores)

    def coverage(self, order, outpost):
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

    def serves(self, order, outpost):
        """Whether a dock at `outpost` may take order: no role-bound item, or it covers at least one."""
        covered, bound = self.coverage(order, outpost)
        return bound == 0 or covered > 0

    def share(self, order, outpost):
        """Covered fraction of order's role-bound items at `outpost` (1.0 with none)."""
        covered, bound = self.coverage(order, outpost)
        return 1.0 if bound == 0 else covered / bound

    def describe(self, outpost):
        """Short role list of a site for debug lines."""
        site_roles, ores = self.site(outpost)
        if site_roles is None:
            return "unknown site"
        parts = sorted(site_roles) + [f"ore:{o}" for o in sorted(ores or ())]
        return ", ".join(parts) if parts else "no roles"


def _order_readiness(order, reserved, stock=total_stock, cask_stock=None):
    """(items_ready, total_needed) for order -- how much of its still-owed
    requirement is already coverable from current Inventory/Warehouse stock
    (Lead Casks for hot items), net of active Construction Blueprint
    reservations. Shared by the per-instance and central scoring paths so
    both rank orders identically. `stock(item_id)`: storage.total_stock(),
    or a SourceCache's stock() snapshot (same Inventory + home Warehouses,
    one .stacks() sweep). `cask_stock(item_id)`: hot-item stock, default
    lead_cask.network_cask_stock()."""
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


def _order_remaining_units(order):
    """Total units still owed across every item of order, ignoring stock
    availability entirely -- used for the weekly deadline feasibility check,
    which cares about total shippable volume, not readiness."""
    requires = getattr(order, "requires", {}) or {}
    shipped = getattr(order, "shipped", {}) or {}
    return sum(max(0, req_count - shipped.get(item_id, 0)) for item_id, req_count in requires.items())


def _weekly_infeasible(order, current_day, dispatch_capacity_per_hour):
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


def _score_campaign_order(order, reserved, stock=total_stock, cask_stock=None):
    prio = 10
    if getattr(order, "reward_kind", "") in ["recipe", "tech"]:
        prio += 50  # Strongly prioritize technology and recipe unlocks!
    items_ready, total_needed = _order_readiness(order, reserved, stock, cask_stock)
    if total_needed > 0:
        prio += int((items_ready / total_needed) * 30)
    return prio


def _score_weekly_order(order, reserved, stock=total_stock, cask_stock=None):
    prio = 5
    items_ready, total_needed = _order_readiness(order, reserved, stock, cask_stock)
    if total_needed > 0:
        prio += int((items_ready / total_needed) * 20)
    return prio


def _servable_at(order, outpost, has_cask):
    """False for an order with hot items (Raw Uranium, Fuel Rods) at a dock whose outpost has no
    Lead Cask: hot cargo reaches a dock only from a cask at its own outpost. has_cask: {outpost_id: bool} memo."""
    if not any(item_id in lead_cask.HOT_ITEMS for item_id in (getattr(order, "requires", {}) or {})):
        return True
    return _has_cask(outpost, has_cask)


def _has_cask(outpost, has_cask):
    """Whether outpost has a Lead Cask. has_cask: {outpost_id: bool} memo."""
    key = getattr(outpost, "id", None)
    if key not in has_cask:
        has_cask[key] = bool(lead_cask.casks_at(outpost))
    return has_cask[key]


def _local_cask_units(order, outpost):
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


def _cask_order_ids(candidates, outpost, has_cask, memo):
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


def _dock_loaded(dock):
    """Units physically loaded in dock (0 if unreadable)."""
    if not hasattr(dock, "total"):
        return 0
    try:
        return dock.total()
    except Exception as error:
        swallowed("supply_dock._dock_loaded: dock.total", error)
        return 0


def _dock_affinity(order, outpost, cache=None, site_plan=None):
    """How well a dock at `outpost` suits order: units of its still-owed items
    already stocked there, plus one per item whose tree the site plan builds
    there. Only breaks ties between equally ranked orders/docks. Without
    `cache` (per-dock fallback) local stock is read from storage directly."""
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
            if cache is not None:
                local = cache.local_stock(item_id, outpost)
            elif outpost_is_home(outpost):
                local = total_stock(item_id)
            else:
                local = warehouse_stock(item_id, outpost)
            score += min(still_needed, local)
        if site_id in (site_plan.get(item_id) or []):
            score += 1
    return score


def plan_signature():
    """
    Cheap fingerprint of what plan_dock_assignments() decides on: every Earth
    Order's (id, status) plus the discovered dock ids. control_room_automation.py
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


def plan_dock_assignments(clock=None):
    """
    Central per-cycle decision, run once from control_room_automation.py's AUTOMATION section:
    which Earth Order (if any) each discovered Supply Dock should be working.
    Docks already holding a still-fulfillable order keep it (stability -- an
    order mid-shipment shouldn't get cleared over a marginal priority
    difference elsewhere, and clearing loses no progress but does cost a
    drain-then-reassign cycle for nothing). Idle/unfulfillable-order docks are
    handed the best-ranked candidate order that currently has the FEWEST docks
    already assigned to it -- spreads docks across several needed orders
    instead of piling every idle dock onto a single top-priority one, while
    still letting every dock share one order when it's the only good
    candidate (mirrors production.get_fabricator_worker_count()'s
    spread-then-join pattern). Writes the plan to archive and returns it.
    """
    log.start("plan_dock_assignments", level="debug")
    orders_api = get_component("orders")
    if not orders_api:
        log.end()
        return {}

    docks = {}
    for dock_id in discover_supply_dock_ids():
        dock = get_component(dock_id)
        if dock and hasattr(dock, "current_order"):
            docks[dock_id] = dock
    if not docks:
        log.end()
        return {}

    # Shared across every can_fulfill_order() call and readiness score in this
    # pass (every candidate order, each dock's current order) -- see SourceCache's
    # docstring in lib/production.py. The pass runs from the headless
    # automation/control_room_automation.py, never inside a per-tick UI loop.
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
    try:
        for o in orders_api.list_orders():
            if getattr(o, "status", "") == "active" and can_fulfill_order(o, cache):
                priority = _score_campaign_order(o, reserved, cache.stock, cache.cask_stock)
                candidates.append({"order": o, "priority": priority})
                log.debug(f"campaign order '{getattr(o, 'name', o.id)}' is a candidate, priority={priority}")
    except Exception as error:
        swallowed("supply_dock.plan_dock_assignments: orders_api.list_orders", error)
    try:
        for o in orders_api.list_weekly_orders():
            if getattr(o, "status", "") != "active" or not can_fulfill_order(o, cache):
                continue
            if _weekly_infeasible(o, current_day, total_dispatch_capacity):
                log.level("warn").print(f"[supply_dock planner] Skipping Weekly Earth Order '{getattr(o, 'name', o.id)}': "
                      f"remaining amount can't ship before it expires on day {o.expires_day}.")
                continue
            priority = _score_weekly_order(o, reserved, cache.stock, cache.cask_stock)
            candidates.append({"order": o, "priority": priority})
            log.debug(f"weekly order '{getattr(o, 'name', o.id)}' is a candidate, priority={priority}")
    except Exception as error:
        swallowed("supply_dock.plan_dock_assignments: orders_api.list_weekly_orders", error)

    log.debug(f"{len(candidates)} candidate order(s), {len(docks)} discovered dock(s), total_dispatch_capacity={total_dispatch_capacity:.1f} u/h")

    site_plan = archive.get(SITE_PLAN_KEY, {})
    site_plan = site_plan if isinstance(site_plan, dict) else {}
    has_cask = {}
    # {(outpost_id, order_id): _local_cask_units()}, shared by the stability and assignment passes.
    cask_units = {}
    roles = DockRoles(cache)

    plan = {}
    idle_dock_ids = []
    assigned_counts = {}
    for dock_id, dock in docks.items():
        try:
            curr = dock.current_order()
        except Exception as error:
            swallowed("supply_dock.plan_dock_assignments: dock.current_order", error)
            curr = None
        if curr and can_fulfill_order(curr, cache):
            outpost = getattr(dock, "outpost", None)
            loaded = _dock_loaded(dock)
            if loaded == 0 and not roles.serves(curr, outpost):
                log.debug(f"{dock_id} is empty and its site ({roles.describe(outpost)}) covers no item of '{curr.id}', leaves it")
                idle_dock_ids.append(dock_id)
                continue
            cask_ids = _cask_order_ids(candidates, outpost, has_cask, cask_units)
            if not cask_ids or curr.id in cask_ids or loaded > 0:
                plan[dock_id] = curr.id
                assigned_counts[curr.id] = assigned_counts.get(curr.id, 0) + 1
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
            for c in eligible:
                c["affinity"] = _dock_affinity(c["order"], outpost, cache, site_plan)
                c["share"] = roles.share(c["order"], outpost)
            eligible.sort(key=lambda c: (c["order"].id not in cask_ids, assigned_counts.get(c["order"].id, 0), -c["share"], -c["priority"], -c["affinity"]))
            best = eligible[0]["order"]
            plan[dock_id] = best.id
            assigned_counts[best.id] = assigned_counts.get(best.id, 0) + 1
            log.debug(f"assigned {dock_id} -> order '{best.id}' (already {assigned_counts[best.id] - 1} dock(s) on it, role share={eligible[0]['share']:.2f}, priority={eligible[0]['priority']})")
    else:
        for dock_id in idle_dock_ids:
            plan[dock_id] = None
            log.debug(f"no fulfillable candidate orders at all, {dock_id} left unassigned")

    previous_plan = archive.get(ORDER_PLAN_ARCHIVE_KEY, {})
    if plan != previous_plan:
        log.print(f"[supply_dock planner] Dock assignments changed: {plan}")
    archive.set(ORDER_PLAN_ARCHIVE_KEY, plan)
    log.end()
    return plan


class SupplyDockController:
    """
    Automated controller for the Supply Dock.
    Prioritizes recipe/tech-unlocking campaign orders (Spire, Helios, Vestibule),
    loads materials from Inventory, and drives high-efficiency shipping to Earth.
    """
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
        (see desired_order_id()) -- control_room_automation.py's plan_dock_assignments() is
        the normal path and additionally spreads docks across candidates and
        skips weekly orders that can't finish before they expire. This
        per-instance fallback keeps a lone dock functional standalone:
        1. Campaign orders that unlock recipes or technology.
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

        try:
            for o in self.orders_api.list_orders():
                if getattr(o, "status", "") == "active" and can_fulfill_order(o):
                    candidates.append({"order": o, "priority": _score_campaign_order(o, reserved)})
        except Exception as error:
            swallowed("supply_dock.SupplyDockController.pick_best_order: self.orders_api.list_orders", error)

        try:
            current_day = None
            clock = get_component("clock")
            if clock and hasattr(clock, "get_day"):
                current_day = clock.get_day()
            dispatch_capacity = self.dock.dispatch_rate() if hasattr(self.dock, "dispatch_rate") else 0.0
            for o in self.orders_api.list_weekly_orders():
                if getattr(o, "status", "") != "active" or not can_fulfill_order(o):
                    continue
                if _weekly_infeasible(o, current_day, dispatch_capacity):
                    self.log.level("warn").print(f"[{self.name}] Skipping '{getattr(o, 'name', o.id)}': can't ship remaining amount before it expires on day {o.expires_day}.")
                    continue
                candidates.append({"order": o, "priority": _score_weekly_order(o, reserved)})
        except Exception as error:
            swallowed("supply_dock.SupplyDockController.pick_best_order: get_component", error)

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
            c["affinity"] = _dock_affinity(c["order"], self.outpost(), None, site_plan)
            c["share"] = roles.share(c["order"], self.outpost())
        candidates.sort(key=lambda c: (c["order"].id not in cask_ids, -c["share"], -c["priority"], -c["affinity"]))
        winner = candidates[0]["order"]
        self.log.debug(f"picked '{getattr(winner, 'name', winner.id)}' (priority={candidates[0]['priority']}, affinity={candidates[0]['affinity']}, local cask={winner.id in cask_ids}) among {len(candidates)} candidate(s)")
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
                return planned_id
            self.log.debug(f"central plan assignment {planned_id!r} is no longer active (plan older than the order's completion)")
        self.plan_assigned = False
        best = self.pick_best_order()
        self.log.debug(f"fell back to pick_best_order() -> {getattr(best, 'id', None)!r}")
        self.log.end()
        return best.id if best else None

    def order_is_active(self, order_id):
        """Whether order_id is still an active Earth Order. The central plan is recomputed every few
        seconds (control_room_automation DOCK_PLAN_TICK_INTERVAL), so an entry can name an order that completed since."""
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
        self.ensure_connected()

        curr_order = self.dock.current_order()

        # Step 1: Assign order if dock is currently idle
        if curr_order and not can_fulfill_order(curr_order):
            loaded = 0
            if hasattr(self.dock, "count"):
                for item_id in getattr(curr_order, "requires", {}) or {}:
                    loaded += self.dock.count(item_id)
            if loaded == 0 and hasattr(self.dock, "clear_order"):
                clear_res = self.dock.clear_order()
                if clear_res.status == "ok":
                    self.log.print(f"[{self.name}] Cleared undeliverable order '{curr_order.name}'.")
                    curr_order = None

        desired_id = self.desired_order_id()
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
        # Chunked per SUPPLY_DOCK_LOAD_CHUNK_SIZE: several docks can now share
        # the same order (docs/components/supply_dock.md), so a sibling dock
        # may be contesting the same Inventory/Warehouse stock for the same
        # item -- see the module docstring's note on the fairness fix this
        # mirrors from Fabricator/Smelter loading.
        # Off home only the outpost's own Warehouses count; blueprint
        # reservations hold home stock only.
        if curr_order and hasattr(curr_order, "requires"):
            at_home = self.at_home()
            outpost = None if at_home else self.outpost()
            reserved = get_construction_material_reservations() if at_home else {}
            cache = None if at_home else SourceCache()
            shipped = getattr(curr_order, "shipped", {}) or {}
            for item_id, req_total in curr_order.requires.items():
                already_shipped = shipped.get(item_id, 0)
                in_dock = self.dock.count(item_id)
                needed = max(0, req_total - already_shipped - in_dock)
                if needed <= 0:
                    continue

                # Hot cargo (Raw Uranium, Fuel Rods) only comes out of this outpost's Lead Casks.
                hot = item_id in lead_cask.HOT_ITEMS
                if hot:
                    avail = lead_cask.cask_stock(item_id, self.outpost())
                else:
                    avail = total_stock(item_id) if cache is None else cache.local_stock(item_id, outpost)
                available_after_reservation = max(0, avail - reserved.get(item_id, 0))
                to_take = min(available_after_reservation, needed, SUPPLY_DOCK_LOAD_CHUNK_SIZE)
                self.log.debug(f"[{self.name}] {item_id}: needed={needed} avail={avail} reserved={reserved.get(item_id, 0)} available_after_reservation={available_after_reservation} -> to_take={to_take}")
                if to_take > 0:
                    if hot:
                        moved = lead_cask.take_from_casks(self.dock.input, item_id, to_take, self.outpost())
                    else:
                        moved = take_item(self.dock.input, item_id, to_take, outpost=outpost)
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

    def run(self, poll_interval=3.0):
        self.log.print(f"Supply Dock Controller ({self.name}) online. Initializing logistics loop...")
        validate_game_version()
        while True:
            reset_all()
            try:
                self.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Exception in supply dock loop: {e}")
                self.idle = False
            self.parker.update(self.idle)
            flush_all()
            sleep(poll_interval)
