# ct-panel: production_panel
# Control Room production card: live Smelter/Fabricator/Supply Dock roster.
# Discovers every deployed instance of each (production.discover_smelter_ids()/
# discover_fabricator_ids()/discover_supply_dock_ids()) rather than assuming a
# single "smelter_1"/"fabricator_1"/"supply_dock_1" to avoid hardcoded-id issues
# (see docs/AI_CHEATSHEET.md's Multi-Smelter/Multi-Fabricator/Multi-Dock notes).
# Inventory removed on purpose -- storage gets its own dedicated card later
# (with history graphs), this one is just live machine roster + status.
# Recommended card size: 2 columns x 2 rows; degrades to 2 x 1 because the
# roster is one panel.list() (wheel scroll) under a one-line header.
# Only machines that need attention get their own row: blocked first, then
# running. Idle machines sharing a reason collapse into one summary line per
# type ("6 smelters idle (no recipe): 1,2,4,5,7,8"), so an idle fleet costs
# one or two lines instead of a screenful.
# Per-machine reads are the cheap ones already used before (recipe, running,
# input/output counts, progress); the recipe's input list is read only for a
# machine that has a recipe but is not running.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import panel

from components import supply_dock
from production import discover_smelter_ids, discover_fabricator_ids, discover_supply_dock_ids

# Singular/plural noun per role for the idle summary lines.
ROLE_NOUNS = {
    "SMELTER": ("smelter", "smelters"),
    "FABRICATOR": ("fabricator", "fabricators"),
    "DOCK": ("dock", "docks"),
}

SORT_BLOCKED = 0
SORT_RUNNING = 1
SORT_IDLE = 2


def short_id(machine_id):
    # "smelter_3" -> "3"; an id without a numeric suffix stays whole.
    tail = machine_id.rsplit("_", 1)[-1]
    return tail if tail.isdigit() else machine_id


def machine_row(machine_id, role):
    machine = get_component(machine_id)
    if machine is None:
        return None
    recipe = machine.get_recipe() if hasattr(machine, "get_recipe") else ""
    running = machine.is_running() if hasattr(machine, "is_running") else False
    input_count = machine.get_input_count() if hasattr(machine, "get_input_count") else 0
    output_count = machine.get_output_count() if hasattr(machine, "get_output_count") else 0
    counts = f"in {input_count} out {output_count}"
    row = {"id": machine_id, "role": role, "reason": "", "text": "", "sort": SORT_IDLE}
    if running:
        progress = machine.get_progress() if hasattr(machine, "get_progress") else 0.0
        row["sort"] = SORT_RUNNING
        row["text"] = f"{role[:3]} {short_id(machine_id)}  {recipe}  RUN {int(progress * 100)}%  {counts}"
        return row
    if not recipe:
        # Leftover items with no recipe are worth a row; an empty machine is not.
        if input_count > 0 or output_count > 0:
            row["sort"] = SORT_BLOCKED
            row["text"] = f"{role[:3]} {short_id(machine_id)}  no recipe, holding items  {counts}"
        else:
            row["reason"] = "no recipe"
        return row
    if output_count > 0:
        row["sort"] = SORT_BLOCKED
        row["text"] = f"{role[:3]} {short_id(machine_id)}  {recipe}  BLOCKED output waiting  {counts}"
        return row
    needed = machine.get_recipe_inputs() if hasattr(machine, "get_recipe_inputs") else {}
    needed_total = sum(needed.values()) if needed else 0
    if input_count > 0 and input_count < needed_total:
        row["sort"] = SORT_BLOCKED
        row["text"] = f"{role[:3]} {short_id(machine_id)}  {recipe}  WAIT input {input_count}/{needed_total}"
        return row
    row["reason"] = "no input" if needed_total > 0 else "idle"
    return row


def dock_row(dock_id):
    dock = supply_dock(dock_id)
    if dock is None:
        return None
    order = dock.current_order() if hasattr(dock, "current_order") else None
    row = {"id": dock_id, "role": "DOCK", "reason": "", "text": "", "sort": SORT_IDLE}
    if order is None:
        row["reason"] = "no order"
        return row

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
        row["sort"] = SORT_RUNNING
        row["text"] = f"DOC {short_id(dock_id)}  {order_name}  READY all items shipped"
        return row
    first_item, first_remaining = pending[0]
    more = f" (+{len(pending) - 1} more)" if len(pending) > 1 else ""
    row["sort"] = SORT_BLOCKED
    row["text"] = f"DOC {short_id(dock_id)}  {order_name}  NEEDS {first_item} x{first_remaining}{more}"
    return row


def idle_summaries(rows):
    # One line per (role, reason): "6 smelters idle (no recipe): 1,2,4,5,7,8".
    groups = {}
    order = []
    for row in rows:
        key = (row["role"], row["reason"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(short_id(row["id"]))
    lines = []
    for role, reason in order:
        ids = groups[(role, reason)]
        singular, plural = ROLE_NOUNS.get(role, ("machine", "machines"))
        noun = singular if len(ids) == 1 else plural
        lines.append(f"{len(ids)} {noun} idle ({reason}): {','.join(ids)}")
    return lines


while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "PRODUCTION")  # card() already renders its own title bar text

    rows = []
    for machine_id in discover_smelter_ids():
        rows.append(machine_row(machine_id, "SMELTER"))
    for machine_id in discover_fabricator_ids():
        rows.append(machine_row(machine_id, "FABRICATOR"))
    for dock_id in discover_supply_dock_ids():
        rows.append(dock_row(dock_id))
    rows = [row for row in rows if row]

    if not rows:
        panel.label(24, 64, "No Smelter, Fabricator, or Supply Dock owned", "muted")
    else:
        blocked = [row for row in rows if row["sort"] == SORT_BLOCKED]
        working = [row for row in rows if row["sort"] == SORT_RUNNING]
        idle = [row for row in rows if row["sort"] == SORT_IDLE]
        header = f"{len(working)} active   {len(blocked)} need attention   {len(idle)} idle"
        panel.draw_text(24, 52, header, 12, "warning" if blocked else "text-secondary")

        items = [row["text"] for row in blocked] + [row["text"] for row in working] + idle_summaries(idle)
        row_h = 20
        list_y = 62
        list_h = max(row_h, height - list_y - 16)
        # Wheel-scrolls once the lines exceed the box; the pick itself is unused.
        panel.list("production_list", 20, list_y, width - 40, list_h, items, row_h)
