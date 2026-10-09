# Sourceability: SourceCache (per-pass stock/recipe/survey snapshot) and
# can_source_item()/can_fulfill_order().
from storage import outpost_is_home
from stock_scan import scan, scan_key, LOCAL, HELD, DEPOTS, STORES, INVENTORY
from logistics_requests import aboard_units
import components
from swallow import swallowed
from production_core import claim_site_id, discover_fabricator_ids, discover_smelter_ids, home_outpost_id, log, _all_outposts, _default_fabricator, _default_fuel_assembler, _default_smelter, _uranium_aftermath_pending
from production_fluids import can_source_fluid
import lead_cask
from game_clock import now_tick


def _staged_reads(machine):
    """{item_id: units} in a recipe machine's input: get_stockpile() (Fabricator), else its input slot's stacks() (Smelter)."""
    if hasattr(machine, "get_stockpile"):
        return dict(machine.get_stockpile() or {})
    staged = {}
    port = getattr(machine, "input", None)
    if port is not None and hasattr(port, "stacks"):
        for stack in port.stacks():
            item_id = getattr(stack, "id", None)
            if item_id:
                staged[item_id] = staged.get(item_id, 0) + (getattr(stack, "count", 0) or 0)
    return staged


def _machine_holdings(machine_ids):
    """(pipeline, staged) {site_id: {item_id: units}} over the recipe machines in machine_ids,
    by claim_site_id(): output-slot stacks plus one craft's output per running craft, and
    the input contents (_staged_reads())."""
    pipeline_by_site = {}
    staged_by_site = {}
    for machine_id in machine_ids:
        machine = components.component(machine_id)
        if not machine:
            continue
        site_id = claim_site_id(machine)
        pipeline = pipeline_by_site.setdefault(site_id, {})
        staged = staged_by_site.setdefault(site_id, {})
        try:
            output = getattr(machine, "output", None)
            if output and hasattr(output, "stacks"):
                for stack in output.stacks():
                    stack_item_id = getattr(stack, "id", None)
                    if stack_item_id:
                        pipeline[stack_item_id] = pipeline.get(stack_item_id, 0) + (getattr(stack, "count", 0) or 0)
            if hasattr(machine, "is_running") and machine.is_running():
                recipe_id = machine.get_recipe()
                recipe = machine.find_recipe(recipe_id) if recipe_id and hasattr(machine, "find_recipe") else None
                output_item = getattr(recipe, "output_item", None) if recipe else None
                if output_item:
                    pipeline[output_item] = pipeline.get(output_item, 0) + max(1, getattr(recipe, "output_count", 1))
        except Exception as error:
            swallowed("production_source._machine_holdings: output.stacks", error)
        try:
            for item_id, count in _staged_reads(machine).items():
                if count > 0:
                    staged[item_id] = staged.get(item_id, 0) + count
        except Exception as error:
            swallowed("production_source._machine_holdings: _staged_reads", error)
    log.trace(f"_machine_holdings: pipeline {pipeline_by_site}, staged {staged_by_site}")
    return pipeline_by_site, staged_by_site


class SourceCache:
    """
    Per-pass memo for can_source_item()/can_source_fluid()'s underlying
    game-API lookups (Smelter/Fabricator discovery + list_recipes(),
    outpost.buildings() for fluid sources, journal.surveyed_sites(), one
    stock_scan.scan() per outpost) plus the
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
    `born` is the tick it was created (0 without a clock): its reads are no
    newer than that, so a result shared from it is stamped with it.
    """

    def __init__(self):
        self.born = now_tick("production_source.SourceCache")
        self._smelter_recipes = None
        self._fabricator_recipes = None
        self._fluid_results = {}
        self._item_results = {}
        self._item_stack = set()
        self._surveyed_sites = None
        self._surveyed_minerals = None  # surveyed_minerals() memo
        self._sourcing_index = None  # {output_item: [recipes]}, sourcing_recipes() memo
        self._scans = {}  # {stock_scan.scan_key(outpost): StockScan}, see scan()
        self._fabricator_targets: "dict[str, int] | None" = None  # get_fabricator_targets() memo -- see its docstring
        self._root_targets: "tuple[dict[str, int], dict[str, dict[str, int]], set[str]] | None" = None  # fabricator_root_targets() memo
        self._site_targets = {}  # {site_id: get_site_fabricator_targets()} memo
        self._site_base_targets = {}  # {site_id: _site_base_targets()} memo
        self._site_ship_plan = {}  # {site_id: {item_id: units}}, filled by get_site_fabricator_targets()
        self._spare_elsewhere = {}  # {"site_id|item_id": units}, site_spare_elsewhere() memo
        self._spare_contribution = {}  # {"outpost_id|item_id": units}, one outpost's share of site_spare_elsewhere()
        self._network_stock = {}  # {item_id: units}, network_stock() memo
        self._site_machines = {}  # {"outpost_id|kind": speed}, _site_speed() memo (0 = no machine)
        self._requests: "dict[str, dict] | None" = None  # logistics_requests.active_requests() snapshot
        self._fab_sites: "dict[str, int] | None" = None  # fab_site_counts() memo
        self._pipeline_by_site: "dict[str, dict[str, int]] | None" = None  # {site_id: {item_id: units}}, see fabricator_holdings()
        self._staged_by_site: "dict[str, dict[str, int]] | None" = None  # {site_id: {item_id: units}}, see fabricator_holdings()
        self._smelter_holdings: "tuple[dict[str, dict[str, int]], dict[str, dict[str, int]]] | None" = None  # see smelter_holdings()
        self._smelter_items = None  # every Smelter recipe input and output, see _held_in_machines()
        self._home_site_id = None  # production_core.home_outpost_id() memo
        self._remote_outposts = None  # non-home OutpostRefs, see network_stock()
        self._aboard = None  # logistics_requests.aboard_units() snapshot, see network_stock()
        self._blueprint_demand: "dict[str, int] | None" = None  # _cascade_blueprint_demand() memo
        self._blueprint_seeds: "dict[str, int] | None" = None  # blueprint_required_items() memo
        self._recipe_index: "dict[str, dict[str, float]] | None" = None  # _recipe_index() for this pass
        self._fuel_assembler_recipes = None
        self._cask_stock = {}  # {item_id: units in every Lead Cask}

    def scan(self, outpost: "OutpostRef | None" = None):
        """stock_scan.scan() of `outpost` (None = home), one per outpost per pass."""
        key = scan_key(outpost)
        held = self._scans.get(key)
        if held is None:
            held = scan(outpost)
            self._scans[key] = held
        return held

    def stock(self, item_id):
        """LOCAL units of item_id at home: Inventory + home Warehouses and Bins
        (+ Crop Automator outputs for Forage)."""
        return self.scan().units(item_id, LOCAL)

    def building_stock(self, item_id):
        """[(source_id, units), ...] for every home storage endpoint ("inventory"
        or a Warehouse id) holding item_id, from the same scan as stock().
        Unordered -- storage.take_item() applies its own priority."""
        return self.scan().holders(item_id, (INVENTORY,) + STORES)

    def local_stock(self, item_id, outpost: "OutpostRef | None" = None):
        """LOCAL units of item_id a machine at `outpost` can take(): stock() at
        home, only that outpost's own Warehouses and Bins elsewhere (Inventory
        is home-only)."""
        return self.scan(outpost).units(item_id, LOCAL)

    def depot_stock(self, item_id, outpost: "OutpostRef | None" = None):
        """Units of item_id in the Drone Depot stockpiles at `outpost` (home when None)."""
        return self.scan(outpost).units(item_id, DEPOTS)

    def held_stock(self, item_id, outpost: "OutpostRef | None" = None):
        """HELD units: local_stock() plus the outpost's Drone Depot stockpiles,
        what is on hand at `outpost` for netting demand. A loader uses
        local_stock(): a Depot pushes its freight out, machines never pull from it."""
        return self.scan(outpost).units(item_id, HELD)

    def network_stock(self, item_id):
        """held_stock() at every outpost (Warehouses, Drone Depots, home
        Inventory) plus cargo loaded aboard a hauler
        (logistics_requests.aboard_units()): units anywhere on the network,
        moving ones included. Memoized per item for the pass."""
        if item_id in self._network_stock:
            return self._network_stock[item_id]
        if self._remote_outposts is None:
            self._remote_outposts = [o for o in _all_outposts() if not outpost_is_home(o)]
        if self._aboard is None:
            self._aboard = aboard_units()
        total = self.held_stock(item_id) + self._aboard.get(item_id, 0)
        for outpost in self._remote_outposts:
            total += self.held_stock(item_id, outpost)
        self._network_stock[item_id] = total
        return total

    def fabricator_holdings(self):
        """(pipeline, staged), each {site_id: {item_id: units}} over every Fabricator
        by its claim_site_id(), one read of each per pass (_machine_holdings()).
        pipeline: output-buffer stacks plus one craft's output per craft in progress,
        built but not yet in storage. staged: the input stockpiles, units taken out
        of storage for crafts not yet run."""
        if self._pipeline_by_site is None or self._staged_by_site is None:
            self._pipeline_by_site, self._staged_by_site = _machine_holdings(discover_fabricator_ids())
        return self._pipeline_by_site, self._staged_by_site

    def smelter_holdings(self):
        """fabricator_holdings() for every Smelter: refined output not yet in storage,
        ore in its input slot."""
        if self._smelter_holdings is None:
            self._smelter_holdings = _machine_holdings(discover_smelter_ids())
        return self._smelter_holdings

    def _held_in_machines(self, item_id, site_id, part):
        """Units of item_id in part 0 (pipeline) or 1 (staged) of the Fabricator and Smelter holdings,
        site_id None = every site. Smelters are read only for an item a Smelter recipe takes or makes."""
        if self._smelter_items is None:
            items = set()
            for recipe in self.smelter_recipes():
                items |= set(getattr(recipe, "inputs", {}) or {})
                items.add(getattr(recipe, "output_item", None))
            self._smelter_items = items
        kinds = (self.fabricator_holdings(), self.smelter_holdings()) if item_id in self._smelter_items else (self.fabricator_holdings(),)
        total = 0
        for holdings in kinds:
            by_site = holdings[part]
            if site_id is not None:
                total += (by_site.get(site_id) or {}).get(item_id, 0)
            else:
                total += sum([units.get(item_id, 0) for units in by_site.values()])
        return total

    def pipeline_units(self, item_id, site_id=None):
        """Units of item_id built or being built inside the Fabricators and Smelters at
        site_id (every site when None), not yet in storage."""
        return self._held_in_machines(item_id, site_id, 0)

    def staged_units(self, item_id, site_id=None):
        """Units of item_id loaded into the Fabricators' stockpiles and the Smelters' input
        slots at site_id (every site when None): out of storage, for crafts not yet run."""
        return self._held_in_machines(item_id, site_id, 1)

    def fab_have(self, item_id, outpost: "OutpostRef | None" = None):
        """What Fabricator netting counts as on hand at `outpost` (home when None):
        held_stock() plus the site's producer pipeline and staged inputs
        (pipeline_units(), staged_units()). Moving a unit from storage into a stockpile or
        from a craft into storage leaves it unchanged, so loading inputs never
        reads as a new shortfall of them."""
        site_id = getattr(outpost, "id", None) if outpost is not None else None
        if site_id is None:
            if self._home_site_id is None:
                self._home_site_id = home_outpost_id()
            site_id = self._home_site_id
        return self.held_stock(item_id, outpost) + self.pipeline_units(item_id, site_id) + self.staged_units(item_id, site_id)

    def network_have(self, item_id):
        """fab_have() over the whole network: network_stock() plus every
        producer's pipeline and staged inputs."""
        return self.network_stock(item_id) + self.pipeline_units(item_id) + self.staged_units(item_id)

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
            journal = components.component("journal")
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


def _has_surveyed_mineral(item_id, cache: "SourceCache"):
    return item_id in cache.surveyed_minerals()


def can_source_item(item_id, cache: "SourceCache | None" = None):
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
    if cache.held_stock(item_id) > 0 or (item_id in lead_cask.HOT_ITEMS and cache.cask_stock(item_id) > 0):
        if log.verbose:
            log.trace(f"already in stock ({cache.held_stock(item_id)}, casks {cache.cask_stock(item_id) if item_id in lead_cask.HOT_ITEMS else 0}) -> sourceable")
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


def can_fulfill_order(order: "Order", cache: "SourceCache | None" = None):
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
