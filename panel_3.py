# Control Room production card: compact recipe, storage, and active-order view.

while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "PRODUCTION")

    inventory = get_component("inventory")
    used = inventory.get_used() if inventory and hasattr(inventory, "get_used") else 0
    slots = inventory.get_size() if inventory and hasattr(inventory, "get_size") else 0

    left = 24
    right = width * 0.52
    panel.label(left, 42, "INVENTORY", "caption")
    panel.progress_bar(left, 66, width * 0.25, 12, used / slots if slots else 0.0, "error" if slots and used >= slots else "accent")
    panel.label(left, 88, f"{used} / {slots} slots", "muted")

    dock = get_component("supply_dock_1")
    order = dock.current_order() if dock and hasattr(dock, "current_order") else None
    panel.label(left, 116, "ACTIVE ORDER", "caption")
    if order is None:
        panel.label(left, 140, "No active order", "muted")
    else:
        panel.draw_text(left, 140, str(getattr(order, "name", getattr(order, "id", "order"))), 11, "text-bright", width * 0.40)
        shipped = getattr(order, "shipped", {}) or {}
        requirements = getattr(order, "requires", {}) or {}
        shown = 0
        for item_id, required in requirements.items():
            if shown >= 2:
                break
            in_dock = dock.count(item_id) if hasattr(dock, "count") else 0
            remaining = max(0, required - shipped.get(item_id, 0) - in_dock)
            panel.draw_text(left, 158 + shown * 18, f"{item_id}: {remaining} needed", 10, "text-secondary")
            shown += 1

    panel.label(right, 42, "MACHINES", "caption")
    machine_y = 66
    for machine_id, label in [("smelter_1", "SMELTER"), ("fabricator_1", "FABRICATOR")]:
        machine = get_component(machine_id)
        if machine is None:
            continue
        recipe = machine.get_recipe() if hasattr(machine, "get_recipe") else ""
        active = machine.is_running() if hasattr(machine, "is_running") else False
        panel.status_dot(right, machine_y + 7, 5, "running" if active else "idle")
        panel.draw_text(right + 14, machine_y + 11, label, 10, "text-secondary")
        panel.draw_text(right, machine_y + 29, recipe or "no recipe", 11, "text-value", width * 0.42)
        input_count = machine.get_input_count() if hasattr(machine, "get_input_count") else 0
        output_count = machine.get_output_count() if hasattr(machine, "get_output_count") else 0
        panel.draw_text(right, machine_y + 47, f"in {input_count}  out {output_count}", 10, "text-muted")
        machine_y += 66