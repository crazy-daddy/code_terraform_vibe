# Control Room production card: live Smelter/Fabricator/Supply Dock roster.
# Discovers every deployed instance of each (production.discover_smelter_ids()/
# discover_fabricator_ids()/discover_supply_dock_ids()) rather than assuming a
# single "smelter_1"/"fabricator_1"/"supply_dock_1" -- a second instance of any
# of the three used to be entirely invisible to this card, mirroring the same
# hardcoded-id bug production.py itself had until fixed alongside this card
# (see docs/AI_CHEATSHEET.md's Multi-Smelter/Multi-Fabricator/Multi-Dock notes).
# Inventory removed on purpose -- storage gets its own dedicated card later
# (with history graphs), this one is just live machine roster + status.
# Recommended card size: 2 columns x 1 row for a handful of machines, 2 x 2
# once you have more -- same sizing guidance as panel_2.py (FLEET). Scrolls the
# same way once the combined machine+dock list exceeds what fits (see
# panel_2.py's own comment for why a horizontal slider is repurposed as a
# scrollbar: there's no vertical slider/scroll widget in the panel API).

from production import discover_smelter_ids, discover_fabricator_ids, discover_supply_dock_ids

ROLE_COLORS = {
    "SMELTER": "accent",
    "FABRICATOR": "warning",
    "DOCK": "success",
}

# Persists across loop iterations (this script is one continuous while-loop
# process, not re-invoked per tick) -- see panel_2.py's matching comment for
# why the scroll slider's own label can only be built from the PREVIOUS
# tick's result (computed after slider() already returns a value for this
# one), and why that one-tick lag is invisible in practice.
scroll_label = "scroll"


def machine_row(machine_id, role):
    machine = get_component(machine_id)
    if machine is None:
        return None
    recipe = machine.get_recipe() if hasattr(machine, "get_recipe") else ""
    running = machine.is_running() if hasattr(machine, "is_running") else False
    input_count = machine.get_input_count() if hasattr(machine, "get_input_count") else 0
    output_count = machine.get_output_count() if hasattr(machine, "get_output_count") else 0
    return {
        "id": machine_id,
        "role": role,
        "status_pill": "RUNNING" if running else "IDLE",
        "status_color": "success" if running else "text-muted",
        "dot": "running" if running else "idle",
        "detail": recipe or "no recipe",
        "footer": f"in {input_count}  out {output_count}",
    }


def dock_row(dock_id):
    dock = get_component(dock_id)
    if dock is None:
        return None
    order = dock.current_order() if hasattr(dock, "current_order") else None
    if order is None:
        return {
            "id": dock_id,
            "role": "DOCK",
            "status_pill": "IDLE",
            "status_color": "text-muted",
            "dot": "idle",
            "detail": "no active order",
            "footer": "",
        }

    shipped = getattr(order, "shipped", {}) or {}
    requirements = getattr(order, "requires", {}) or {}
    pending = []
    for item_id, required in requirements.items():
        in_dock = dock.count(item_id) if hasattr(dock, "count") else 0
        remaining = max(0, required - shipped.get(item_id, 0) - in_dock)
        if remaining > 0:
            pending.append((item_id, remaining))

    order_name = str(getattr(order, "name", getattr(order, "id", "order")))
    if not pending:
        footer = "all items shipped"
    else:
        first_item, first_remaining = pending[0]
        footer = f"{first_item}: {first_remaining} needed"
        if len(pending) > 1:
            footer += f" (+{len(pending) - 1} more)"

    return {
        "id": dock_id,
        "role": "DOCK",
        "status_pill": "ACTIVE" if pending else "READY",
        "status_color": "warning" if pending else "success",
        "dot": "running" if pending else "idle",
        "detail": order_name,
        "footer": footer,
    }


while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "PRODUCTION")  # card() already renders its own title bar text

    rows = []
    for machine_id in discover_smelter_ids():
        row = machine_row(machine_id, "SMELTER")
        if row:
            rows.append(row)
    for machine_id in discover_fabricator_ids():
        row = machine_row(machine_id, "FABRICATOR")
        if row:
            rows.append(row)
    for dock_id in discover_supply_dock_ids():
        row = dock_row(dock_id)
        if row:
            rows.append(row)

    wide = width >= 900

    if not rows:
        panel.label(24, 64, "No Smelter, Fabricator, or Supply Dock owned", "muted")
    else:
        # Reserve the scroll-row's vertical space unconditionally (even on a
        # tick where the roster currently fits without it) so the row grid
        # below never jumps as the count crosses the scrollable threshold
        # from one tick to the next -- see panel_2.py's matching comment.
        top = 82
        row_height = 46 if wide else 60
        max_rows = max(1, (height - top - 16) // row_height)

        max_start = max(0, len(rows) - max_rows)
        start_index = 0
        if max_start > 0:
            scroll_w = min(140, max(60, width - 300))
            scroll_value = panel.slider("production_scroll", 24, 54, scroll_w, 0.0, scroll_label)
            start_index = int(max(0, min(max_start, round(scroll_value * max_start))))
            shown_last = min(start_index + max_rows, len(rows))
            scroll_label = f"scroll {start_index + 1}-{shown_last}/{len(rows)}"

        visible_rows = rows[start_index:start_index + max_rows]
        for index, row in enumerate(visible_rows):
            y = top + index * row_height

            panel.status_dot(24, y + 11, 5, row["dot"])
            panel.draw_text(40, y + 15, row["id"][:16], 12, "text-bright")
            panel.pill(40, y + 22, row["role"], ROLE_COLORS.get(row["role"], "text-muted"))

            detail_x = 190
            panel.draw_text(detail_x, y + 15, row["detail"][:28], 11, "text-value", width * 0.30)
            if row["footer"]:
                panel.draw_text(detail_x, y + 34, row["footer"][:36], 10, "text-secondary", width * 0.34)

            status_x = width - 110
            panel.pill(status_x, y + 4, row["status_pill"], row["status_color"])
