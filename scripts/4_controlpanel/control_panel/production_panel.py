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
# PILLAR SWAP strip on the right (SWAP_W): pick a "from" and a "to" pillar,
# Swap queues lib/pillar_swap.py's machine-by-machine swap (worked off by
# builder_automation.py), Stop ends it after the machine in flight.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import panel

from components import supply_dock
from production import discover_smelter_ids, discover_fabricator_ids, discover_supply_dock_ids
import pillar_swap

# Singular/plural noun per role for the idle summary lines.
ROLE_NOUNS = {
    "SMELTER": ("smelter", "smelters"),
    "FABRICATOR": ("fabricator", "fabricators"),
    "DOCK": ("dock", "docks"),
}

SORT_BLOCKED = 0
SORT_RUNNING = 1
SORT_IDLE = 2

SWAP_W = 272                # PILLAR SWAP card width, right of the roster
SWAP_BUTTON_W = 66
SWAP_BUTTON_H = 22
SWAP_BUTTON_GAP = 4
SWAP_REFRESH_LOOPS = 20     # loops between machine counts / swap status reads


def short_id(machine_id):
    # "smelter_3" -> "3"; an id without a numeric suffix stays whole.
    tail = machine_id.rsplit("_", 1)[-1]
    return tail if tail.isdigit() else machine_id


def outpost_tag(building):
    # Owning outpost as "H" (home) or "O3" ("outpost_3"), the vehicle-name tag
    # from fleet_commission.commission_name(); "" when unreadable.
    outpost = getattr(building, "outpost", None)
    outpost_id = str(getattr(outpost, "id", "") or "")
    if not outpost_id:
        return ""
    if outpost_id == "outpost_home":
        return "H"
    return "O" + short_id(outpost_id)


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
    tag = outpost_tag(dock)
    label = f"DOC {short_id(dock_id)} @ {tag}" if tag else f"DOC {short_id(dock_id)}"
    if not pending:
        row["sort"] = SORT_RUNNING
        row["text"] = f"{label}  {order_name}  READY all items shipped"
        return row
    first_item, first_remaining = pending[0]
    more = f" (+{len(pending) - 1} more)" if len(pending) > 1 else ""
    row["sort"] = SORT_BLOCKED
    row["text"] = f"{label}  {order_name}  NEEDS {first_item} x{first_remaining}{more}"
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


def pillar_counts():
    # {pillar: deployed generator count}, every outpost.
    counts = {key: 0 for key in pillar_swap.PILLAR_ORDER}
    network = get_component("outpost_network")
    for outpost in network.outposts() if network else []:
        for key in pillar_swap.PILLAR_ORDER:
            counts[key] += len(outpost.buildings(pillar_swap.PILLARS[key]))
    return counts


def pillar_row(key, x, y, label, running):
    # One row of pillar buttons; the pick persists on the card under `key`
    # and is frozen while a swap runs. Returns the picked pillar.
    picked = panel.get_selected(key)
    if picked is None or picked >= len(pillar_swap.PILLAR_ORDER):
        picked = 1 if key == "swap_from" else 0
    panel.draw_text(x, y + 5, label, 11, "text-secondary")
    for index, pillar in enumerate(pillar_swap.PILLAR_ORDER):
        text = pillar_swap.PILLAR_LABELS[pillar]
        if index == picked:
            text = f"> {text} <"
        bx = x + 38 + index * (SWAP_BUTTON_W + SWAP_BUTTON_GAP)
        if panel.button(f"{key}_{index}", bx, y, SWAP_BUTTON_W, SWAP_BUTTON_H, text) and not running:
            panel.set_selected(key, index)
            picked = index
    return pillar_swap.PILLAR_ORDER[picked]


def draw_swap_card(x, y, h, counts, swap_state, swap_text):
    panel.card(x, y, SWAP_W, h, "PILLAR SWAP")
    left = x + 12
    running = swap_state == "running"
    totals = "  ".join(f"{pillar_swap.PILLAR_LABELS[k]} {counts.get(k, 0)}" for k in pillar_swap.PILLAR_ORDER)
    panel.draw_text(left, y + 36, totals, 11, "text-secondary")
    source = pillar_row("swap_from", left, y + 52, "from", running)
    target = pillar_row("swap_to", left, y + 80, "to", running)
    if running:
        if panel.button("swap_go", left, y + 110, 100, 24, "Stop"):
            pillar_swap.request_stop()
    elif source != target:
        if panel.button("swap_go", left, y + 110, 100, 24, "Swap"):
            pillar_swap.request_swap(source, target)
    else:
        panel.draw_text(left, y + 116, "pick two pillars", 11, "text-muted")
    color = "warning" if swap_state == "blocked" else "text-secondary"
    panel.draw_text(left, y + 144, swap_text[:40], 10, color)


loops = 0
counts = {}
swap_state, swap_text = "", ""
while True:
    if loops % SWAP_REFRESH_LOOPS == 0:
        counts = pillar_counts()
        swap_state, swap_text = pillar_swap.panel_status()
    loops += 1
    panel.clear()
    width = panel.width()
    height = panel.height()
    roster_w = width - 24 - SWAP_W
    panel.card(8, 8, roster_w, height - 16, "PRODUCTION")  # card() already renders its own title bar text
    draw_swap_card(width - 8 - SWAP_W, 8, height - 16, counts, swap_state, swap_text)

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
        panel.list("production_list", 20, list_y, roster_w - 24, list_h, items, row_h)
