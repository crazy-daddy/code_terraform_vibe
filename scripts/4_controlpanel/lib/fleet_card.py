# Shared layout pieces for the Control Room FLEET card (vehicles_panel.py)
# views: tab buttons, the scrolling roster list and the detail pane beside it. `panel` is the
# card script's injected panel global, passed in.
#
# Roster = one panel.list() (wheel scroll, selection stored by row number on
# the card). Rows are plain text, so per-unit colour lives in the detail
# pane only. Controls (recall, retire, Sport Nav) act on the selected unit
# through fixed widget keys, so the key count stays flat as the fleet grows.

from fleet_status import INTENT_LINE_PX, draw_assignment, wrap_text

# Content area inside panel.card(8, 8, w - 16, h - 16, title): the title bar
# ends near y 32.
CONTENT_X = 24
CONTENT_Y = 40
CONTENT_BOTTOM_PAD = 16

TAB_W = 104
TAB_H = 24
TAB_GAP = 8
LIST_ROW_H = 20
# Share of the content width the roster list takes; the detail pane gets the rest.
LIST_SHARE = 0.58
DETAIL_GAP = 16
# Below this content height the detail pane drops its optional lines.
COMPACT_H = 220
# Detail pane control row: button height (the row sits at the pane's bottom) and Retire width.
BUTTON_H = 22
RETIRE_BTN_W = 70


def tabs(panel, key, x, y, labels):
    """Row of tab buttons; the active index persists on the card under `key`
    (set_selected/get_selected work without drawing a list). Returns it."""
    stored = panel.get_selected(key)
    active = stored if stored is not None and stored < len(labels) else 0
    for index, label in enumerate(labels):
        text = f"> {label} <" if index == active else label
        if panel.button(f"{key}_{index}", x + index * (TAB_W + TAB_GAP), y, TAB_W, TAB_H, text) and index != active:
            panel.set_selected(key, index)
            active = index
    return active


def roster(panel, key, x, y, w, h, rows):
    """panel.list of `rows`; returns the selected row number (clamped), or None while empty."""
    if not rows:
        return None
    panel.list(key, x, y, w, h, rows, LIST_ROW_H)
    index = panel.get_selected(key)
    return min(index or 0, len(rows) - 1)


def split(x, w):
    """(list width, detail x, detail width) for a content row starting at x, w wide."""
    list_w = int(w * LIST_SHARE)
    detail_x = x + list_w + DETAIL_GAP
    return list_w, detail_x, x + w - detail_x


def cell(text, width):
    """text cut or right-padded to `width` characters, for the list's monospace columns."""
    text = str(text)
    return text[:width] + " " * (width - len(text))


def level_cell(level):
    return f"{level * 100:.0f}%".rjust(4)


def status_mark(dot_status):
    """One-character row prefix standing in for the status dot (list rows are plain text)."""
    return {"error": "!", "being_rescued": "?", "paused": "-", "running": ">"}.get(dot_status, " ")


def draw_wrapped(panel, x, y, text, width_px, max_lines, color="text-value"):
    """Intent-style wrapped text from y down; returns the y below the last line."""
    for line in wrap_text(text, width_px, max_lines):
        panel.draw_text(x, y, line, 10, color)
        y += INTENT_LINE_PX
    return y


def counters(panel, x, y, pairs, step):
    """Headline counts as `LABEL n` pairs, `step` px apart."""
    for index, (label, count) in enumerate(pairs):
        cx = x + index * step
        panel.draw_text(cx, y, label, 10, "text-muted")
        panel.draw_text(cx + len(label) * 6 + 6, y, str(count), 12, "text-bright" if count else "text-muted")


def draw_detail_body(panel, unit, entry, names, head, level, flag, x, y, w, h):
    """
    Upper detail pane of one drone or ground vehicle: head = (dot status, name, pill text,
    pill color), the battery/tank `level` bar, status line (docked marked) with the `flag`
    pill ((text, color) or None), the assignment (not when compact) and the wrapped intent
    down to the control row. Returns the control row's y.
    """
    dot, name, pill_text, pill_color = head
    controls_y = y + h - BUTTON_H
    panel.status_dot(x + 6, y + 8, 5, dot)
    panel.draw_text(x + 18, y + 8, name[:16], 13, "text-bright")
    panel.pill(x + w - 80, y, pill_text, pill_color)

    panel.progress_bar(x, y + 22, w - 48, 10, level, "error" if level < 0.2 else "success")
    panel.draw_text(x + w - 40, y + 27, f"{level * 100:.0f}%", 10, "text-value")

    raw_status = str(getattr(unit, "status", "unknown"))
    status_text = f"{raw_status} - docked" if getattr(unit, "is_docked", False) else raw_status
    cy = y + 46
    panel.draw_text(x, cy, status_text[:24], 10, "text-secondary")
    if flag:
        panel.pill(x + w - 8 - len(flag[0]) * 7, cy - 8, flag[0], flag[1])
    cy += 16
    if h >= COMPACT_H and cy + 26 < controls_y:
        draw_assignment(panel, x, cy, entry, names, w)
        cy += 30
    intent = str(entry.get("intent") or "")
    lines = int((controls_y - 6 - cy) // 13)
    if intent and lines > 0:
        draw_wrapped(panel, x, cy, intent, w, min(lines, 4))
    return controls_y
