# ct-panel: activity_panel
# Control Room MACHINE ACTIVITY card: the machine activity sample
# (lib/machine_activity.py, docs/cheatsheet/dev_workflow.md §1d-3) that
# control_room_automation.py writes to machine.activity after each script census.
# Draws nothing of its own logic:
#   - overview: one row per machine group, most "retire" first: members now,
#     a stacked bar of the group's machine time per class, spare mean, retire;
#   - click a group row: one row per machine of that group, most spare time
#     first, with its last-sample class, outpost / home, own stacked bar and
#     spare share. "back" returns to the overview.
# Rows are hit-tested with panel.clicks(), the hovered row is highlighted
# from panel.mouse(); a scroll slider appears once rows overflow.
#
# Recommended card size: 2 x 2 (1 x 2 works, the name column narrows).
# New save: create an empty Custom Panel in-game -- see docs/cheatsheet/panels.md §7.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import panel

from machine_activity import CLASSES, group_rows, machine_rows, get
from swallow import swallowed
import fleet_status
from game_clock import now_tick

CLASS_COLORS = {
    "active": "success",
    "running": "accent",
    "waiting": "warning",
    "idle": "text-muted",
    "parked": "#8b7fd6",
    "off": "error",
}
ROW_H = 22
CHAR_PX = 6  # font size 10
# The sample changes every CENSUS_TICK_INTERVAL ticks; re-read the archive this often.
READ_EVERY_TICKS = 50
# Machine names / outposts are re-read at most this often while a group is open.
LABEL_EVERY_TICKS = 600
TICKS_PER_SECOND = 10


def machine_labels():
    """{machine id: (name, outpost or home name)} for buildings, field machines and mobile units."""
    labels = {}
    names = {}
    network = get_component("outpost_network")
    try:
        outposts = list(network.outposts()) if network else []
    except Exception as error:
        swallowed("activity_panel.machine_labels: outposts", error)
        outposts = []
    for outpost in outposts:
        names[outpost.id] = outpost.name
        try:
            refs = [(ref.id, getattr(ref, "name", "")) for ref in outpost.buildings()]
            if hasattr(outpost, "harvesting_machines"):
                refs += [(ref.id, getattr(ref, "name", "")) for ref in outpost.harvesting_machines()]
        except Exception as error:
            swallowed("activity_panel.machine_labels: buildings", error)
            continue
        for ref_id, name in refs:
            labels[ref_id] = (str(name or ref_id), outpost.name)
    fleet = get_component("fleet")
    telemetry = fleet_status.get_all()
    try:
        units = list(fleet.mobile_units()) if fleet else []
    except Exception as error:
        swallowed("activity_panel.machine_labels: mobile_units", error)
        units = []
    for unit in units:
        entry = telemetry.get(unit.id) or telemetry.get(getattr(unit, "name", "")) or {}
        home = entry.get("home") if isinstance(entry, dict) else None
        labels[unit.id] = (str(getattr(unit, "name", "") or unit.id), str(names.get(home, home or "")))
    return labels


def share_bar(x, y, w, h, share):
    """Stacked bar of {class: %} in CLASSES order."""
    panel.fill_rect(x, y, w, h, "bg-surface")
    left = x
    for cls in CLASSES:
        part = w * (share.get(cls) or 0) / 100.0
        if part > 0:
            panel.fill_rect(left, y, part, h, CLASS_COLORS[cls])
            left += part


def draw_legend(x, y, right):
    """Class color keys left to right from x, stopping before `right`."""
    for cls in CLASSES:
        text_w = panel.measure_text(cls, 10).w
        if x + 12 + text_w > right:
            return
        panel.fill_rect(x, y - 4, 8, 8, CLASS_COLORS[cls])
        panel.draw_text(x + 12, y, cls, 10, "text-secondary")
        x += 12 + text_w + 12


def cut(text, width_px):
    chars = max(0, int(width_px // CHAR_PX))
    text = str(text)
    return text if len(text) <= chars else text[:max(0, chars - 2)] + ".."


def scroll_rows(key, rows, max_rows, x, y, label):
    """(first row index, new slider label); draws the slider only when rows overflow."""
    max_start = max(0, len(rows) - max_rows)
    if max_start == 0:
        return 0, label
    value = panel.slider(key, x, y, 100, 0.0, label)
    start = int(max(0, min(max_start, round(value * max_start))))
    return start, f"{start + 1}-{min(start + max_rows, len(rows))}/{len(rows)}"


def hovered_row(mouse: "PanelMouse", top, count, width):
    if not mouse.over or mouse.x < 16 or mouse.x > width - 16 or mouse.y < top:
        return None
    index = int((mouse.y - top) // ROW_H)
    return index if index < count else None


def clicked_row(clicks, top, count, width):
    """Row index of the last click on a row, else None."""
    hit = None
    for c in clicks:
        if 16 <= c.x <= width - 16 and c.y >= top:
            index = int((c.y - top) // ROW_H)
            if index < count:
                hit = index
    return hit


def draw_overview(state, width, height, mouse: "PanelMouse", clicks):
    """Group rows; returns the clicked group or None."""
    global group_scroll_label
    groups = group_rows(state)
    machines = len(state.get("machines") or {})
    age = max(0, now_tick() - (state.get("tick") or 0)) // TICKS_PER_SECOND
    panel.draw_text(24, 40, f"{machines} machines, {len(groups)} groups, {state.get('samples', 0)} samples, {age} s ago", 10, "text-secondary")
    draw_legend(24, 58, width - 24)

    name_w = 150 if width >= 900 else 104
    n_x = 24 + name_w
    bar_x = n_x + 34
    retire_x = width - 24 - 44
    spare_x = retire_x - 58
    bar_w = max(40, spare_x - 12 - bar_x)
    panel.label(24, 78, "GROUP", "caption")
    panel.label(n_x, 78, "N", "caption")
    panel.label(bar_x, 78, "SHARE", "caption")
    panel.label(spare_x, 78, "SPARE", "caption")
    panel.label(retire_x, 78, "RETIRE", "caption")

    top = 90
    max_rows = max(1, int((height - top - 16) // ROW_H))
    start, group_scroll_label = scroll_rows("group_scroll", groups, max_rows, width - 230, 32, group_scroll_label)
    visible = groups[start:start + max_rows]
    hover = hovered_row(mouse, top, len(visible), width)
    for index, (group, entry) in enumerate(visible):
        y = top + index * ROW_H
        retire = entry.get("retire") or 0
        if index == hover:
            panel.fill_rect(16, y, width - 32, ROW_H, "bg-surface")
        panel.draw_text(24, y + 11, cut(group, name_w - 8), 10, "text-bright" if retire else "text-value")
        panel.draw_text(n_x, y + 11, str(entry.get("n", 0)), 10, "text-value")
        share_bar(bar_x, y + 6, bar_w, 10, entry.get("share") or {})
        panel.draw_text(spare_x, y + 11, f"{entry.get('spare_mean', 0):.1f}", 10, "text-value")
        panel.pill(retire_x, y + 2, str(retire), "warning" if retire else "text-muted", 16)
    index = clicked_row(clicks, top, len(visible), width)
    return visible[index][0] if index is not None else None


def draw_group(state, group, width, height, mouse: "PanelMouse", labels):
    """Machine rows of one group; returns True when "back" is pressed."""
    global machine_scroll_label
    back = panel.button("activity_back", 24, 30, 56, 22, "back")
    entry = (state.get("groups") or {}).get(group) or {}
    panel.draw_text(92, 41, cut(f"{group}: {entry.get('n', 0)} machines, spare mean {entry.get('spare_mean', 0):.1f}, retire {entry.get('retire', 0)}", width - 92 - 24), 10, "text-bright")
    share = entry.get("share") or {}
    share_bar(24, 60, width - 48, 8, share)
    panel.draw_text(24, 80, cut("  ".join(f"{cls} {share[cls]:.0f}%" for cls in CLASSES if share.get(cls)), width - 48), 10, "text-secondary")

    rows = machine_rows(state, group)
    name_w = 150 if width >= 900 else 100
    place_x = 40 + name_w
    place_w = 130 if width >= 900 else 0
    bar_x = place_x + place_w
    spare_x = width - 24 - 64
    bar_w = max(40, spare_x - 12 - bar_x)
    panel.label(40, 100, "MACHINE", "caption")
    if place_w:
        panel.label(place_x, 100, "OUTPOST", "caption")
    panel.label(bar_x, 100, "SHARE", "caption")
    panel.label(spare_x, 100, "SPARE", "caption")

    top = 112
    max_rows = max(1, int((height - top - 16) // ROW_H))
    start, machine_scroll_label = scroll_rows("machine_scroll", rows, max_rows, width - 230, 32, machine_scroll_label)
    visible = rows[start:start + max_rows]
    hover = hovered_row(mouse, top, len(visible), width)
    for index, (machine_id, machine_share, last, spare) in enumerate(visible):
        y = top + index * ROW_H
        name, place = labels.get(machine_id, (machine_id, ""))
        if index == hover:
            panel.fill_rect(16, y, width - 32, ROW_H, "bg-surface")
        panel.status_dot(28, y + 11, 4, CLASS_COLORS.get(last, "text-muted"))
        panel.draw_text(40, y + 11, cut(name, name_w - 8), 10, "text-value")
        if place_w:
            panel.draw_text(place_x, y + 11, cut(place, place_w - 8), 10, "text-secondary")
        share_bar(bar_x, y + 6, bar_w, 10, machine_share)
        panel.draw_text(spare_x, y + 11, f"{spare:.0f}%", 10, "text-value")
    return back


group_scroll_label = "scroll"
machine_scroll_label = "scroll"
state = {}
read_tick = None
selected = None
labels = {}
labels_tick = None

while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "MACHINE ACTIVITY")
    tick = now_tick()
    if read_tick is None or tick - read_tick >= READ_EVERY_TICKS:
        state = get()
        read_tick = tick
    mouse = panel.mouse()
    clicks = panel.clicks()

    if selected is not None and selected not in (state.get("groups") or {}):
        selected = None
    if not state.get("groups"):
        panel.label(24, 52, "No activity sample yet: the first one follows the next script census", "muted")
    elif selected is None:
        picked = draw_overview(state, width, height, mouse, clicks)
        if picked is not None:
            selected = picked
            panel.set_slider("machine_scroll", 0.0)
            machine_scroll_label = "scroll"
            labels_tick = None
    else:
        if labels_tick is None or tick - labels_tick >= LABEL_EVERY_TICKS:
            labels = machine_labels()
            labels_tick = tick
        if draw_group(state, selected, width, height, mouse, labels):
            selected = None
