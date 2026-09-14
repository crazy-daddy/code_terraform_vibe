# Shared production-demand planning for mining and refining automation.
from archive import archive


def _component(component_id):
    try:
        return get_component(component_id)
    except Exception:
        return None


def _add_demand(demands, item_id, quantity):
    if item_id and quantity > 0:
        demands[item_id] = demands.get(item_id, 0) + quantity


# Defaults only seed the Data Archive once; edit the archived key afterward
# (Data Archive Notebook) to change stock targets without touching this file.
FABRICATOR_STOCK_TARGETS_KEY = "fabricator.stock_targets"
DEFAULT_FABRICATOR_STOCK_TARGETS = {
    "gas_pipe_segment": 10,
    "power_line_segment": 10,
    "liquid_pipe_segment": 10,
}


def get_fabricator_stock_targets():
    """Seeds the Data Archive with default stock targets on first run, then reads them back."""
    if not archive.has(FABRICATOR_STOCK_TARGETS_KEY):
        archive.set(FABRICATOR_STOCK_TARGETS_KEY, dict(DEFAULT_FABRICATOR_STOCK_TARGETS))
    stored = archive.get(FABRICATOR_STOCK_TARGETS_KEY, DEFAULT_FABRICATOR_STOCK_TARGETS)
    if not isinstance(stored, dict):
        return dict(DEFAULT_FABRICATOR_STOCK_TARGETS)
    return {
        item_id: int(qty) for item_id, qty in stored.items()
        if isinstance(qty, (int, float)) and qty >= 0
    }


def get_fabricator_targets():
    """Returns desired finished-goods quantities for Fabricator planning."""
    targets = get_fabricator_stock_targets()

    fabricator_outputs = set()
    fabricator = _component("fabricator_1")
    if fabricator and hasattr(fabricator, "list_recipes"):
        try:
            for recipe in fabricator.list_recipes():
                output_item = getattr(recipe, "output_item", None)
                if output_item:
                    fabricator_outputs.add(output_item)
        except Exception:
            pass

    dock = _component("supply_dock_1")
    if dock and hasattr(dock, "current_order"):
        try:
            order = dock.current_order()
            if order and hasattr(order, "requires"):
                shipped = getattr(order, "shipped", {}) or {}
                for item_id, required in order.requires.items():
                    # Only order items the Fabricator can actually build become
                    # targets; other order items (raw/mined) are handled by
                    # the dock demand loop in get_material_demands() and must
                    # not be double-counted here.
                    if item_id not in targets and item_id not in fabricator_outputs:
                        continue
                    remaining = required - shipped.get(item_id, 0)
                    targets[item_id] = max(targets.get(item_id, 0), remaining)
        except Exception:
            pass
    return targets


def get_fabricator_active_recipe(fabricator=None):
    """Returns (recipe, crafts_remaining) for the Fabricator's selected recipe,
    where crafts_remaining covers the full remaining shortfall against its
    output target/order (not just one craft's worth)."""
    if fabricator is None:
        fabricator = _component("fabricator_1")
    if not fabricator or not hasattr(fabricator, "get_recipe") or not hasattr(fabricator, "list_recipes"):
        return None, 0
    try:
        current_recipe_id = fabricator.get_recipe()
        if not current_recipe_id:
            return None, 0
        recipe = next((r for r in fabricator.list_recipes() if getattr(r, "id", None) == current_recipe_id), None)
        if not recipe:
            return None, 0
        output_item = getattr(recipe, "output_item", None)
        output_count = max(1, getattr(recipe, "output_count", 1))
        inventory = _component("inventory")
        current = inventory.count(output_item) if inventory and hasattr(inventory, "count") else 0
        output_buffer = fabricator.get_output_count() if hasattr(fabricator, "get_output_count") else 0
        target = get_fabricator_targets().get(output_item, 0)
        still_needed = max(0, target - current - output_buffer)
        crafts_remaining = -(-still_needed // output_count)  # ceil division
        return recipe, crafts_remaining
    except Exception:
        return None, 0


def get_material_demands():
    """Returns material quantities currently requested by production and shipping."""
    demands = {}
    inventory = _component("inventory")

    # Finished fabricated goods have a standing building-stock target and
    # may also be required by the active Supply Dock order.
    for item_id, target in get_fabricator_targets().items():
        current = inventory.count(item_id) if inventory and hasattr(inventory, "count") else 0
        _add_demand(demands, item_id, max(0, target - current))

    # A selected Fabricator recipe is an explicit production intention; scale
    # by every remaining craft still needed to reach the target, not just one
    # craft's worth, or demand collapses to 0 as soon as a single unit of an
    # input is on hand even though hundreds more crafts remain.
    fabricator = _component("fabricator_1")
    recipe, crafts_remaining = get_fabricator_active_recipe(fabricator)
    if recipe and crafts_remaining > 0:
        try:
            stockpile = fabricator.get_stockpile() or {}
            for item_id, required in (getattr(recipe, "inputs", {}) or {}).items():
                missing = (required * crafts_remaining) - stockpile.get(item_id, 0)
                if inventory and hasattr(inventory, "count"):
                    missing -= inventory.count(item_id)
                _add_demand(demands, item_id, max(0, missing))
        except Exception:
            pass

    # The active dock order is the current downstream shipping requirement.
    dock = _component("supply_dock_1")
    if dock and hasattr(dock, "current_order"):
        try:
            order = dock.current_order()
            if order and hasattr(order, "requires"):
                shipped = getattr(order, "shipped", {}) or {}
                for item_id, required in order.requires.items():
                    missing = required - shipped.get(item_id, 0)
                    if hasattr(dock, "count"):
                        missing -= dock.count(item_id)
                    if inventory and hasattr(inventory, "count"):
                        missing -= inventory.count(item_id)
                    _add_demand(demands, item_id, max(0, missing))
        except Exception:
            pass

    return demands


def get_raw_material_demands(smelter=None):
    """Converts refined-material demand into raw ore demand for mining."""
    demands = get_material_demands()
    refined_demands = dict(demands)
    inventory = _component("inventory")
    raw_demands = {}

    # Raw items requested directly by an order are mined as-is.
    for item_id, quantity in demands.items():
        if item_id.endswith("_ore") or item_id in ["silicon", "rare_earth"]:
            current = inventory.count(item_id) if inventory and hasattr(inventory, "count") else 0
            _add_demand(raw_demands, item_id, max(0, quantity - current))

    # Expand Fabricator output demand into refined-material demand before
    # asking the Smelter to expand refined materials into raw ore.
    fabricator = _component("fabricator_1")
    if fabricator and hasattr(fabricator, "list_recipes"):
        try:
            for recipe in fabricator.list_recipes():
                output_item = getattr(recipe, "output_item", None)
                output_need = demands.get(output_item, 0)
                if output_need <= 0:
                    continue
                output_count = max(1, getattr(recipe, "output_count", 1))
                for input_id, units_per_run in (getattr(recipe, "inputs", {}) or {}).items():
                    current = inventory.count(input_id) if inventory and hasattr(inventory, "count") else 0
                    needed = (output_need * units_per_run + output_count - 1) // output_count
                    _add_demand(refined_demands, input_id, max(0, needed - current))
        except Exception:
            pass

    # Only unlocked smelter recipes can create demand. Locked silicon recipes
    # therefore cannot cause either refining or rover mining.
    if smelter is None:
        smelter = _component("smelter_1")
    if smelter and hasattr(smelter, "list_recipes"):
        try:
            for recipe in smelter.list_recipes():
                output_item = getattr(recipe, "output_item", None)
                output_need = refined_demands.get(output_item, 0)
                if output_need <= 0:
                    continue
                for raw_item, units_per_run in (getattr(recipe, "inputs", {}) or {}).items():
                    current = inventory.count(raw_item) if inventory and hasattr(inventory, "count") else 0
                    _add_demand(raw_demands, raw_item, max(0, output_need * units_per_run - current))
        except Exception:
            pass

    return raw_demands


def _has_surveyed_mineral(item_id):
    journal = _component("journal")
    if not journal or not hasattr(journal, "surveyed_sites"):
        return False
    try:
        return any(
            getattr(site, "kind", lambda: "")() == "mineral"
            and getattr(site, "item_id", None) == item_id
            for site in journal.surveyed_sites("nocturna")
        )
    except Exception:
        return False


def can_source_item(item_id, seen=None):
    """Whether an item has Inventory, surveyed-source, or unlocked recipe supply."""
    inventory = _component("inventory")
    if inventory and hasattr(inventory, "count") and inventory.count(item_id) > 0:
        return True

    seen = set() if seen is None else seen
    if item_id in seen:
        return False
    seen.add(item_id)

    if _has_surveyed_mineral(item_id):
        return True

    for component_id in ["smelter_1", "fabricator_1"]:
        component = _component(component_id)
        if not component or not hasattr(component, "list_recipes"):
            continue
        try:
            recipes = component.list_recipes()
        except Exception:
            continue
        for recipe in recipes:
            if getattr(recipe, "output_item", None) != item_id:
                continue
            inputs = getattr(recipe, "inputs", {}) or {}
            if all(can_source_item(input_id, seen.copy()) for input_id in inputs):
                return True

    return False


def can_fulfill_order(order):
    """Checks whether every remaining order item has a currently known source."""
    if not order or not hasattr(order, "requires"):
        return False
    shipped = getattr(order, "shipped", {}) or {}
    for item_id, required in order.requires.items():
        remaining = max(0, required - shipped.get(item_id, 0))
        if remaining > 0 and not can_source_item(item_id):
            return False
    return True


def get_raw_material_reason(raw_item, smelter=None):
    """Describes the active downstream consumer driving a raw-material demand."""
    inventory = _component("inventory")
    fabricator = _component("fabricator_1")
    dock = _component("supply_dock_1")

    if dock and hasattr(dock, "current_order"):
        try:
            order = dock.current_order()
            if order and raw_item in (getattr(order, "requires", {}) or {}):
                return f"Supply Dock Order {getattr(order, 'name', getattr(order, 'id', 'active'))}"
        except Exception:
            pass

    if smelter is None:
        smelter = _component("smelter_1")
    if smelter and hasattr(smelter, "list_recipes"):
        try:
            for recipe in smelter.list_recipes():
                inputs = getattr(recipe, "inputs", {}) or {}
                if raw_item not in inputs:
                    continue
                output_item = getattr(recipe, "output_item", None)
                if dock and hasattr(dock, "current_order"):
                    order = dock.current_order()
                    if order and output_item in (getattr(order, "requires", {}) or {}):
                        return f"Supply Dock Order {getattr(order, 'name', getattr(order, 'id', 'active'))} via {getattr(recipe, 'id', 'Smelter')}"
                if fabricator and hasattr(fabricator, "get_recipe_inputs"):
                    fabricator_inputs = fabricator.get_recipe_inputs() or {}
                    if output_item in fabricator_inputs:
                        return f"Fabricator via {getattr(recipe, 'id', 'Smelter')}"
        except Exception:
            pass

    if fabricator and hasattr(fabricator, "get_recipe_inputs"):
        try:
            if raw_item in (fabricator.get_recipe_inputs() or {}):
                return f"Fabricator recipe {getattr(fabricator, 'get_recipe', lambda: 'active')()}"
        except Exception:
            pass

    if inventory and hasattr(inventory, "count") and inventory.count(raw_item) > 0:
        return "existing Inventory demand"
    return "active production demand"