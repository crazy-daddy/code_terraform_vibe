# Sourceability: SourceCache (per-pass stock/recipe/survey snapshot) and
# can_source_item()/can_fulfill_order().
from storage import crop_automator_forage_total, CROP_AUTOMATOR_ITEM_ID, discover_storage_buildings, outpost_is_home
from outpost_mining import HOME_OUTPOST_ID
from logistics_requests import aboard_units, DRONE_DEPOT_TYPE_IDS
from swallow import swallowed
from production_core import log, _all_outposts, _component, _default_fabricator, _default_fuel_assembler, _default_smelter, _uranium_aftermath_pending
from production_fluids import can_source_fluid
import lead_cask


class SourceCache:
    """
    Per-pass memo for can_source_item()/can_source_fluid()'s underlying
    game-API lookups (Smelter/Fabricator discovery + list_recipes(),
    outpost.buildings() for fluid sources, journal.surveyed_sites(), a
    one-shot Inventory+Warehouse stock snapshot) plus the
    can_source_item()/can_source_fluid() results themselves.

    Each of those lookups is a real call across the script/game boundary.
    Threading a shared SourceCache through multiple checks (Supply Dock's
    plan_dock_assignments() across every order and dock, Fabricator's
    choose_recipe() across every candidate recipe) means each underlying
    game call happens at most once per pass. A sub-item shared by several
    recipes/orders (e.g. Steel) gets resolved once instead of re-walked from
    scratch down every branch.

    Discard it once the pass finishes -- it's a snapshot of build/tech state
    that can change between ticks, not something to hold onto across calls.
    """

    def __init__(self):
        self._smelter_recipes = None
        self._fabricator_recipes = None
        self._fluid_results = {}
        self._item_results = {}
        self._item_stack = set()
        self._surveyed_sites = None
        self._surveyed_minerals = None  # surveyed_minerals() memo
        self._sourcing_index = None  # {output_item: [recipes]}, sourcing_recipes() memo
        self._stock_map = None
        self._building_stock = None  # {source_id: {item_id: units}}, filled alongside _stock_map
        self._fabricator_targets = None  # get_fabricator_targets() memo -- see its docstring
        self._root_targets = None  # fabricator_root_targets() memo
        self._site_targets = {}  # {site_id: get_site_fabricator_targets()} memo
        self._site_base_targets = {}  # {site_id: _site_base_targets()} memo
        self._site_ship_plan = {}  # {site_id: {item_id: units}}, filled by get_site_fabricator_targets()
        self._spare_elsewhere = {}  # {"site_id|item_id": units}, site_spare_elsewhere() memo
        self._site_machines = {}  # {"outpost_id|kind": bool}, _site_has_machine() memo
        self._requests = None  # logistics_requests.active_requests() snapshot
        self._fab_sites = None  # fab_site_counts() memo
        self._pipeline_by_site = None  # {site_id: {item_id: units}}, get_fabricator_pipeline() memo
        self._outpost_stock = {}  # {outpost_id: {item_id: units}} for non-home outposts, see local_stock()
        self._depot_stock = {}  # {outpost_id: {item_id: units}} in Drone Depot stockpiles, see held_stock()
        self._remote_outposts = None  # non-home OutpostRefs, see network_stock()
        self._aboard = None  # logistics_requests.aboard_units() snapshot, see network_stock()
        self._blueprint_demand = None  # _cascade_blueprint_demand() memo
        self._blueprint_seeds = None  # blueprint_required_items() memo
        self._recipe_index = None  # _recipe_index() for this pass
        self._fuel_assembler_recipes = None
        self._cask_stock = {}  # {item_id: units in every Lead Cask}

    def _build_stock_map(self):
        log.start("SourceCache._build_stock_map", level="debug")
        log.trace("one-shot stock scan across Inventory + Warehouses starting")
        """One .stacks() call per Inventory/Warehouse -- each returns that
        building's ENTIRE contents in one shot -- summed by item id into a
        single {item_id: total_units} snapshot for the whole pass. Calling
        stock(item_id) per distinct item instead (total_stock()'s normal
        per-item .count(item_id) shape) would still cost one call per
        building per distinct item; a single .stacks() sweep per building up
        front replaces that with one call per building, period, no matter how
        many distinct items this pass ends up checking. The same sweep also
        fills the per-building breakdown building_stock() serves (used by
        storage.take_item() to pick which holder to pull from), at no extra
        game calls."""
        totals = {}
        per_building = {}
        sources = [("inventory", _component("inventory"))] + [(b["id"], b["component"]) for b in discover_storage_buildings()]
        for source_id, component in sources:
            if not component or not hasattr(component, "stacks"):
                continue
            held = per_building.setdefault(source_id, {})
            try:
                for stack in component.stacks():
                    stack_item_id = getattr(stack, "id", None)
                    if stack_item_id:
                        count = getattr(stack, "count", 0)
                        totals[stack_item_id] = totals.get(stack_item_id, 0) + count
                        held[stack_item_id] = held.get(stack_item_id, 0) + count
            except Exception as error:
                swallowed("production_source.SourceCache._build_stock_map: component.stacks", error)
        # Crop Automators keep their Forage in their own output (lib/storage.py),
        # which take_item() pulls from directly. Counted in totals only:
        # building_stock() stays Inventory/Warehouse.
        forage = crop_automator_forage_total()
        if forage > 0:
            totals[CROP_AUTOMATOR_ITEM_ID] = totals.get(CROP_AUTOMATOR_ITEM_ID, 0) + forage
        self._building_stock = per_building
        log.trace(f"scanned {len(sources)} storage components, {len(totals)} distinct items")
        log.end()
        return totals

    def stock(self, item_id):
        """Item's total units across Inventory + every Warehouse (+ Crop
        Automator outputs for Forage), from this pass's one-shot stock
        snapshot -- see _build_stock_map()."""
        if self._stock_map is None:
            self._stock_map = self._build_stock_map()
        return self._stock_map.get(item_id, 0)

    def building_stock(self, item_id):
        """[(source_id, units), ...] for every home storage endpoint ("inventory"
        or a Warehouse id) holding item_id, from the same one-shot snapshot as
        stock(). Unordered -- storage.take_item() applies its own priority."""
        if self._stock_map is None:
            self._stock_map = self._build_stock_map()
        return [
            (source_id, held[item_id])
            for source_id, held in (self._building_stock or {}).items()
            if held.get(item_id, 0) > 0
        ]

    def local_stock(self, item_id, outpost=None):
        """Units of item_id a machine at `outpost` can reach: stock() at home
        (Inventory + home Warehouses), only that outpost's own Warehouses
        elsewhere (Inventory is home-only). One .stacks() sweep per remote
        outpost per pass, like _build_stock_map()."""
        if outpost_is_home(outpost):
            return self.stock(item_id)
        outpost_id = getattr(outpost, "id", None)
        held = self._outpost_stock.get(outpost_id)
        if held is None:
            held = {}
            for building in discover_storage_buildings(outpost):
                component = building["component"]
                if not component or not hasattr(component, "stacks"):
                    continue
                try:
                    for stack in component.stacks():
                        stack_item_id = getattr(stack, "id", None)
                        if stack_item_id:
                            held[stack_item_id] = held.get(stack_item_id, 0) + getattr(stack, "count", 0)
                except Exception as error:
                    swallowed("production_source.SourceCache.local_stock: component.stacks", error)
            self._outpost_stock[outpost_id] = held
        return held.get(item_id, 0)

    def depot_stock(self, item_id, outpost=None):
        """Units of item_id in the Drone Depot stockpiles at `outpost` (home
        when None). One .stacks() sweep per outpost per pass."""
        outpost_id = HOME_OUTPOST_ID if outpost_is_home(outpost) else getattr(outpost, "id", None)
        held = self._depot_stock.get(outpost_id)
        if held is None:
            held = {}
            for depot in discover_storage_buildings(outpost, DRONE_DEPOT_TYPE_IDS):
                port = getattr(depot["component"], "output", None)
                if not port or not hasattr(port, "stacks"):
                    continue
                try:
                    for stack in port.stacks():
                        stack_item_id = getattr(stack, "id", None)
                        if stack_item_id:
                            held[stack_item_id] = held.get(stack_item_id, 0) + getattr(stack, "count", 0)
                except Exception as error:
                    swallowed("production_source.SourceCache.depot_stock: port.stacks", error)
            self._depot_stock[outpost_id] = held
        return held.get(item_id, 0)

    def held_stock(self, item_id, outpost=None):
        """local_stock() plus the outpost's Drone Depot stockpiles: units
        already made and sitting at `outpost`. For netting demand; a loader
        uses local_stock(), since take_item() doesn't reach Depots."""
        return self.local_stock(item_id, outpost) + self.depot_stock(item_id, outpost)

    def network_stock(self, item_id):
        """held_stock() at every outpost (Warehouses, Drone Depots, home
        Inventory) plus cargo loaded aboard a hauler
        (logistics_requests.aboard_units()): units anywhere on the network,
        moving ones included."""
        if self._remote_outposts is None:
            self._remote_outposts = [o for o in _all_outposts() if not outpost_is_home(o)]
        if self._aboard is None:
            self._aboard = aboard_units()
        total = self.held_stock(item_id) + self._aboard.get(item_id, 0)
        for outpost in self._remote_outposts:
            total += self.held_stock(item_id, outpost)
        return total

    def smelter_recipes(self):
        if self._smelter_recipes is None:
            component = _default_smelter()
            try:
                self._smelter_recipes = list(component.list_recipes()) if component and hasattr(component, "list_recipes") else []
            except Exception as error:
                swallowed("production_source.SourceCache.smelter_recipes: component.list_recipes", error)
                self._smelter_recipes = []
        return self._smelter_recipes

    def fabricator_recipes(self):
        if self._fabricator_recipes is None:
            component = _default_fabricator()
            try:
                self._fabricator_recipes = list(component.list_recipes()) if component and hasattr(component, "list_recipes") else []
            except Exception as error:
                swallowed("production_source.SourceCache.fabricator_recipes: component.list_recipes", error)
                self._fabricator_recipes = []
        return self._fabricator_recipes

    def fuel_assembler_recipes(self):
        """The first Fuel Assembler's unlocked recipes ([] without one). Only can_source_item() reads
        them: the recipe index and the Fabricator cascades stay Fabricator/Smelter-only."""
        if self._fuel_assembler_recipes is None:
            component = _default_fuel_assembler()
            try:
                self._fuel_assembler_recipes = list(component.list_recipes()) if component and hasattr(component, "list_recipes") else []
            except Exception as error:
                swallowed("production_source.SourceCache.fuel_assembler_recipes: component.list_recipes", error)
                self._fuel_assembler_recipes = []
        return self._fuel_assembler_recipes

    def sourcing_recipes(self, item_id):
        """Smelter, Fabricator and Fuel Assembler recipes that output item_id, in that order.
        The output index is built once per pass."""
        if self._sourcing_index is None:
            index = {}
            for recipes in (self.smelter_recipes(), self.fabricator_recipes(), self.fuel_assembler_recipes()):
                for recipe in recipes:
                    index.setdefault(getattr(recipe, "output_item", None), []).append(recipe)
            self._sourcing_index = index
        return self._sourcing_index.get(item_id, [])

    def cask_stock(self, item_id):
        if item_id not in self._cask_stock:
            self._cask_stock[item_id] = lead_cask.network_cask_stock(item_id)
        return self._cask_stock[item_id]

    def surveyed_sites(self):
        if self._surveyed_sites is None:
            journal = _component("journal")
            try:
                self._surveyed_sites = list(journal.surveyed_sites("nocturna")) if journal and hasattr(journal, "surveyed_sites") else []
            except Exception as error:
                swallowed("production_source.SourceCache.surveyed_sites: journal.surveyed_sites", error)
                self._surveyed_sites = []
        return self._surveyed_sites

    def surveyed_minerals(self):
        """Item ids of every surveyed mineral site, read once per pass (one kind() call per site)."""
        if self._surveyed_minerals is None:
            try:
                self._surveyed_minerals = {
                    getattr(site, "item_id", None)
                    for site in self.surveyed_sites()
                    if getattr(site, "kind", lambda: "")() == "mineral"
                }
            except Exception as error:
                swallowed("production_source.SourceCache.surveyed_minerals: site.kind", error)
                self._surveyed_minerals = set()
        return self._surveyed_minerals


def _has_surveyed_mineral(item_id, cache):
    return item_id in cache.surveyed_minerals()


def can_source_item(item_id, cache=None):
    """Whether an item has storage (Inventory/Warehouse), surveyed-source, or unlocked recipe supply.

    Pass a shared `cache` (SourceCache) when checking several items/recipes/
    orders in one pass -- see SourceCache's docstring for why that matters.
    """
    # Memo hit returns before any logging: choose_recipe() and the dock
    # planner re-ask shared inputs once per recipe/order, and an empty debug
    # block costs more than the lookup.
    if cache is None:
        cache = SourceCache()
    else:
        known = cache._item_results.get(item_id)
        if known is not None:
            return known
    log.start(f"can_source_item({item_id})", level="debug")
    if cache.stock(item_id) > 0 or (item_id in lead_cask.HOT_ITEMS and cache.cask_stock(item_id) > 0):
        if log.verbose:
            log.trace(f"already in stock ({cache.stock(item_id)}, casks {cache.cask_stock(item_id) if item_id in lead_cask.HOT_ITEMS else 0}) -> sourceable")
        cache._item_results[item_id] = True
        log.end()
        return True
    if item_id in cache._item_stack:
        log.trace("recipe cycle guard hit, treating as not-yet-sourceable")
        log.end()
        return False  # cycle guard -- not memoized, this item's own answer is still being computed higher up
    cache._item_stack.add(item_id)

    try:
        result = _has_surveyed_mineral(item_id, cache)
        if result:
            log.trace("surveyed mineral site found -> sourceable")
        if not result and item_id == lead_cask.URANIUM_ITEM and _uranium_aftermath_pending():
            result = True
            log.trace("live uranium aftermath site -> sourceable")
        if not result:
            for recipe in cache.sourcing_recipes(item_id):
                inputs = getattr(recipe, "inputs", {}) or {}
                fluid_inputs = getattr(recipe, "fluid_inputs", {}) or {}
                if all(can_source_fluid(fk, cache) for fk in fluid_inputs) and all(can_source_item(input_id, cache) for input_id in inputs):
                    result = True
                    log.trace(f"sourceable via recipe {getattr(recipe, 'id', '?')} (inputs={list(inputs.keys())}, fluids={list(fluid_inputs.keys())})")
                    break
            if not result:
                log.trace("no stock, no surveyed mineral, no sourceable recipe -> not sourceable")
    finally:
        cache._item_stack.discard(item_id)

    cache._item_results[item_id] = result
    log.end()
    return result


def can_fulfill_order(order, cache=None):
    """Checks whether every remaining order item has a currently known source.

    Pass a shared `cache` (SourceCache) when checking several orders in one
    pass (e.g. Supply Dock's plan_dock_assignments()) -- see SourceCache's
    docstring for why that matters.
    """
    log.start("can_fulfill_order", level="debug")
    if not order or not hasattr(order, "requires"):
        log.end()
        return False
    cache = SourceCache() if cache is None else cache
    shipped = getattr(order, "shipped", {}) or {}
    for item_id, required in order.requires.items():
        remaining = max(0, required - shipped.get(item_id, 0))
        if remaining > 0 and not can_source_item(item_id, cache):
            log.debug(f"{item_id} (remaining={remaining}) has no known source -> order not fulfillable")
            log.end()
            return False
    log.debug("all remaining requirements have a known source -> fulfillable")
    log.end()
    return True
