# Shared production-demand planning for mining and refining automation.

def _component(component_id):
    try:
        return get_component(component_id)
    except Exception:
        return None


def _add_demand(demands, item_id, quantity):
    if item_id and quantity > 0:
        demands[item_id] = demands.get(item_id, 0) + quantity


def get_material_demands():
    """Returns material quantities currently requested by production and shipping."""
    demands = {}
    inventory = _component("inventory")

    # A selected Fabricator recipe is an explicit production intention.
    fabricator = _component("fabricator_1")
    if fabricator and hasattr(fabricator, "get_recipe_inputs"):
        try:
            stockpile = fabricator.get_stockpile() or {}
            for item_id, required in (fabricator.get_recipe_inputs() or {}).items():
                missing = required - stockpile.get(item_id, 0)
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
    inventory = _component("inventory")
    raw_demands = {}

    # Raw items requested directly by an order are mined as-is.
    for item_id, quantity in demands.items():
        if item_id.endswith("_ore") or item_id in ["silicon", "rare_earth"]:
            current = inventory.count(item_id) if inventory and hasattr(inventory, "count") else 0
            _add_demand(raw_demands, item_id, max(0, quantity - current))

    # Only unlocked smelter recipes can create demand. Locked silicon recipes
    # therefore cannot cause either refining or rover mining.
    if smelter is None:
        smelter = _component("smelter_1")
    if smelter and hasattr(smelter, "list_recipes"):
        try:
            for recipe in smelter.list_recipes():
                output_item = getattr(recipe, "output_item", None)
                output_need = demands.get(output_item, 0)
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