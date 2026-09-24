# Data Types: System And Panels

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`Panel`](#panel) (PANELS)
- [`PanelClick`](#panelclick) (PANELS)
- [`PanelKey`](#panelkey) (PANELS)
- [`PanelMouse`](#panelmouse) (PANELS)
- [`ActionResult`](#actionresult) (SYSTEM)
- [`CommandResult`](#commandresult) (SYSTEM)
- [`CountResult`](#countresult) (SYSTEM)
- [`CropJob`](#cropjob) (SYSTEM)
- [`CropJobResult`](#cropjobresult) (SYSTEM)
- [`JobReceipt`](#jobreceipt) (SYSTEM)

---

## Panel

**Returned by:** panel (panel scripts only). Create one on the **Control Room** page; see `custom_panels`

### Methods

##### `card(x: float, y: float, w: float, h: float, title?: str) → None`

Bordered subsection with optional title bar. Use to group related content visually, mirrors the dashboard's card aesthetic.

```preview
card(8, 8, 264, 64, "Section")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width (pixels) |
| `h` | `float` | Height (pixels) |
| `title` | `str` | Optional card title |

- **Returns** `None`

##### `divider(x1: float, y1: float, x2: float, y2: float) → None`

Horizontal or vertical separator line in the muted border color. Use to break a panel into visual zones.

```preview
divider(10, 40, 270, 40)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x1` | `float` | Start X (pixels) |
| `y1` | `float` | Start Y (pixels) |
| `x2` | `float` | End X (pixels) |
| `y2` | `float` | End Y (pixels) |

- **Returns** `None`

##### `label(x: float, y: float, text: str, style?: str) → None`

Semantically styled text. `style` accepts `"title"` (bright, bold), `"caption"` (muted, uppercase), `"muted"` (secondary), `"value"` (numeric readout). Defaults to `"title"`. Use instead of `draw_text` when you want the dashboard's text hierarchy applied automatically.

```preview
label(10, 30, "OXYGEN", "caption")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `text` | `str` | Label text |
| `style` | `str` | Text style preset. |

- **Returns** `None`

##### `status_dot(x: float, y: float, r: float, status: str) → None`

Colored disc resolved from a status string. Recognized values: `"running"` (green), `"paused"` (warning), `"error"` (error red), `"idle"` (muted). Renders with a subtle outer glow ring. Useful for per-row indicators in machine lists.

```preview
status_dot(0, 0, 5, "running")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `r` | `float` | Radius (pixels) |
| `status` | `str` | Status preset. |

- **Returns** `None`

##### `toggle(x: float, y: float, on: bool, label?: str, size?: float) → None`

Green/grey power-toggle pill matching the dashboard's machine on/off control. This widget only displays the `on` value you pass in; use `panel.switch(...)` for a clickable control.

```preview
toggle(10, 12, true, "powered")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `on` | `bool` | Whether the toggle is on |
| `label` | `str` | Optional label |
| `size` | `float` | Pill height in pixels (default 18). The width, knob and label follow it. |

- **Returns** `None`

##### `pill(x: float, y: float, text: str, color?: str, size?: float) → None`

Rounded badge with text, achievement-style. Color accepts theme tokens (`"accent"`, `"success"`, `"warning"`, `"error"`, `"text-muted"`) or hex. Use for status labels or category tags.

```preview
pill(10, 22, "earned", "success")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `text` | `str` | Pill text |
| `color` | `str` | Theme token (e.g. `"accent"`), or any CSS color (hex, `rgb()`, `hsl()`, named). |
| `size` | `float` | Pill height in pixels (default 18). The text and padding follow it; the width still comes from the text. |

- **Returns** `None`

##### `counter(x: float, y: float, value: object, label?: str, size?: float) → None`

Big-number stat block, large value on top, small uppercase label below. Use for headline numbers (credits, day count, ingot inventory). `size` defaults to **24**.

```preview
counter(16, 38, 87, "shipped", 26)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `value` | `object` | Value to display |
| `label` | `str` | Optional label |
| `size` | `float` | Optional numeric font size in pixels (default 24) |

- **Returns** `None`

##### `progress_bar(x: float, y: float, w: float, h: float, fraction: float, color?: str) → None`

Horizontal fill bar with track + filled accent. `fraction` clamps to **0-1**. Color defaults to `"accent"`; use `"success"`, `"warning"`, `"error"` for traffic-light cues.

```preview
progress_bar(0.72, "success")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width (pixels) |
| `h` | `float` | Height (pixels) |
| `fraction` | `float` | Fill (0-1) |
| `color` | `str` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `vertical_bar(x: float, y: float, w: float, h: float, fraction: float, color?: str) → None`

Vertical fill bar, fills from the bottom up. Same `fraction` and color rules as `progress_bar`. Use when the panel layout favors verticality (multi-tank stacks, atmospheric stacks).

```preview
vertical_bar(110, 10, 30, 60, 0.6)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width (pixels) |
| `h` | `float` | Height (pixels) |
| `fraction` | `float` | Fill (0-1) |
| `color` | `str` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `bar_chart(x: float, y: float, w: float, h: float, values: list[float], max?: float, labels?: list[str]) → None`

Multi-bar comparison chart, themed alternating colors, optional labels under each bar. `max` is optional, omit to auto-scale to the largest value.

```preview
bar_chart(0, 0, 0, 0, [42, 80, 26, 61, 95], 100)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width (pixels) |
| `h` | `float` | Height (pixels) |
| `values` | `list[float]` | Numeric values to plot |
| `max` | `float` | Optional maximum value |
| `labels` | `list[str]` | Optional labels |

- **Returns** `None`

##### `gauge(x: float, y: float, radius: float, fraction: float, label?: str) → None`

Three-quarter-circle dial with arc fill. `fraction` clamps to **0-1**, sweeping **270°** from bottom-left around to bottom-right. Optional center label sits in the middle (typically the value as text).

```preview
gauge(140, 50, 32, 0.62, "62%")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `radius` | `float` | Gauge radius in pixels |
| `fraction` | `float` | Fill fraction in the **0-1** range |
| `label` | `str` | Optional label |

- **Returns** `None`

##### `spark_line(x: float, y: float, w: float, h: float, values: list[float]) → None`

Compact trend line drawn from a numeric series. Player accumulates values into a list and pushes the most recent on each tick, the widget normalizes to the series' min/max range and fills a subtle area below the line. Empty / single-value series no-op.

```preview
spark_line(0, 0, 0, 0)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width (pixels) |
| `h` | `float` | Height (pixels) |
| `values` | `list[float]` | Numeric values to plot |

- **Returns** `None`

##### `button(key: str, x: float, y: float, w?: float, h?: float, label?: str) → bool`

A clickable button. Pass a unique `key` so the click routes back to it. Returns `True` the single tick it's pressed (momentary), branch on it: `if panel.button("shed", 10, 12): power.set_powered(...)`. `w`/`h` default to **90×26**. The first input widget that lets a card *act* on the player's click, not just paint.

```preview
button(10, 12, 90, 26, "shed now")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Unique id for this control |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width in pixels (default 90) |
| `h` | `float` | Height in pixels (default 26) |
| `label` | `str` | Optional label |

- **Returns** `bool`

##### `switch(key: str, x: float, y: float, default_on?: bool, label?: str, size?: float) → bool`

An interactive on/off switch, the player clicks it to flip. Pass a unique `key`; `default_on` sets the starting state the first time the card runs. Returns the current boolean every tick, and the flip persists in the card's state across reloads. Unlike the display `toggle` (which only shows a state you pass in), this one is clickable: `auto = panel.switch("auto_recover", 165, 128, True)`.

```preview
switch(10, 12, true, "auto-recover")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Unique id for this control |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `default_on` | `bool` | Initial on/off state |
| `label` | `str` | Optional label |
| `size` | `float` | Pill height in pixels (default 18). The clickable area follows it. |

- **Returns** `bool`

##### `slider(key: str, x: float, y: float, w: float, default?: float, label?: str, size?: float) → float`

A horizontal slider the player clicks to set a value. Pass a unique `key`; `default` (**0-1**) sets the starting value. Returns the current value as a **0-1** number every tick, persisted in the card's state. Use it for thresholds the player tunes live, a buy-trigger level, a throttle target.

```preview
slider(10, 14, 120, 0.5, "rate")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Unique id for this control |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width (pixels) |
| `default` | `float` | Initial value 0-1 |
| `label` | `str` | Optional label |
| `size` | `float` | Track height in pixels (default 14). The knob, label and clickable area follow it. |

- **Returns** `float`

##### `checkbox(key: str, x: float, y: float, default_on?: bool, label?: str, size?: float) → bool`

A check box the player clicks. Same stored state as `panel.switch(...)`, so `set_switch` drives either one; the difference is the shape. Pass a unique `key`; `default_on` sets the starting state the first time the card runs.

```preview
checkbox(10, 12, true, "night mode")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Unique key this box stores its state under. |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `default_on` | `bool` | Checked state the first time the card runs. |
| `label` | `str` | Optional label drawn to the right. |
| `size` | `float` | Box edge length in pixels (default 14). The tick and label follow it. |

- **Returns** `bool`

##### `radio_group(key: str, x: float, y: float, options: list[str], default?: str | int, row_height?: float) → str | None`

One choice out of several, drawn one option per row. The whole group shares a single `key`, which is why five options cost the card one stored value instead of five: building radio buttons out of five separate switches is what leaves five keys behind. Returns the selected option's text every tick, and `None` while `options` is empty. `default` accepts the option text or its row number.

```preview
radio_group(10, 6, ["ore", "ingots", "both"], 1)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Unique key the whole group stores its choice under. |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `options` | `list[str]` | List of choices, drawn one per row. |
| `default` | `str \| int` | Option text, or row number, selected the first time the card runs. |
| `row_height` | `float` | Row pitch in pixels (default 20). The dot and text follow it. |

- **Returns** `str | None`

##### `combo(key: str, x: float, y: float, w: float, options: list[str], default?: str | int, label?: str, size?: float) → str | None`

A dropdown. Clicking it opens the game's own menu over the card, so the choices stay readable at any card size and never get clipped by the panel edge. Returns the selected option's text every tick, and `None` while `options` is empty. `default` accepts the option text or its row number.

```preview
combo(10, 12, 150, "iron_ingot", "recipe")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Unique key this box stores its choice under. |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width (pixels) |
| `options` | `list[str]` | List of choices shown when the player opens the box. |
| `default` | `str \| int` | Option text, or row number, selected the first time the card runs. |
| `label` | `str` | Optional label drawn to the right. |
| `size` | `float` | Box height in pixels (default 24). The text and caret follow it. |

- **Returns** `str | None`

##### `text_field(key: str, x: float, y: float, w: float, default?: str, placeholder?: str, label?: str, size?: float) → str`

A one-line text box. Clicking it opens a real text editor over the field, so selection, copy, paste and your keyboard's own input method all work; the card shows the committed value. Returns the current text every tick. Up to 1024 characters, saved with the card.

```preview
text_field(10, 12, 180, "outpost_north", "name...")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Unique key this field stores its text under. |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width (pixels) |
| `default` | `str` | Text the field holds the first time the card runs. |
| `placeholder` | `str` | Muted text shown while the field is empty. |
| `label` | `str` | Title shown on the editor the player types into. |
| `size` | `float` | Field height in pixels (default 24). The text follows it. |

- **Returns** `str`

##### `list(key: str, x: float, y: float, w: float, h: float, items: list[str], row_height?: float) → str | None`

A scrolling list of rows the player can pick from. Rows past the box height scroll with the wheel; the selected row is stored with the card and returned every tick, or `None` while `items` is empty. Use it where a card has more entries than space, which is most fleet and inventory boards.

```preview
list(10, 6, 160, 68, ["rover_1", "pioneer_1", "drone_1", "drone_2"], 0)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Unique key this list stores its selected row under. |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width (pixels) |
| `h` | `float` | Height (pixels). Rows past it scroll. |
| `items` | `list[str]` | List of rows to show. |
| `row_height` | `float` | Row pitch in pixels (default 20). The text follows it. |

- **Returns** `str | None`

##### `icon_button(key: str, x: float, y: float, size: float, item_id: str) → bool`

A square button whose label is an item icon. Returns `True` the single tick it is pressed, exactly like `panel.button(...)`. Use it for a toolbar strip where a word would not fit. `panel.icon_ids()` lists every id it can draw.

```preview
icon_button(10, 8, 44, "iron_ingot")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Unique key so the click routes back to this button. |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `size` | `float` | Button edge length in pixels (default 32). |
| `item_id` | `str` | Icon to draw inside the button. `panel.icon_ids()` lists every id. |

- **Returns** `bool`

##### `set_switch(key: str, on: bool) → None`

Force a switch or check box to a state from code, instead of waiting for the player to click it. Use it to build a radio group out of switches, to reset a cockpit to a known layout, or to reflect a state the card read from the world.

```
if not power.is_online():
  panel.set_switch("auto_dispatch", False)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Key of the switch or check box to set. |
| `on` | `bool` | New state. |

- **Returns** `None`

##### `set_slider(key: str, value: float) → None`

Force a slider to a value (0-1) from code.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Key of the slider to set. |
| `value` | `float` | New value, clamped to 0-1. |

- **Returns** `None`

##### `set_selected(key: str, option: str | int) → None`

Force a radio group, combo box, or list to a choice from code. Accepts the option's text or its row number.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Key of the radio group, combo box, or list to set. |
| `option` | `str \| int` | Option text, or row number. |

- **Returns** `None`

##### `set_text(key: str, text: str) → None`

Force a text field's contents from code.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Key of the text field to set. |
| `text` | `str` | New text. |

- **Returns** `None`

##### `forget(key: str) → None`

Drop one stored widget value. The next paint of that widget starts from its declared default again, which is how a card resets one control without disturbing the others.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | Key to drop from the card's stored input state. |

- **Returns** `None`

##### `clear_inputs() → None`

Drop every stored widget value on this card. Widget keys are never swept automatically, because a card that only paints one page at a time would lose the other page's state; this is the deliberate reset. A card is limited to 512 stored keys, and a key built from changing data (a tick count, a name that varies) is what reaches that limit.

- **Returns** `None`

##### `mouse() → PanelMouse`

Where the cursor is on this card, in the same coordinates you draw in. `over` is `False` while the cursor is elsewhere. The sample is taken once per tick and the card repaints at the same rate, so a highlight drawn from it follows the cursor about a frame behind: right for showing what is under the pointer, wrong for anything that must track it exactly.

```
m = panel.mouse()
if m.over and m.x < panel.width() / 2:
  panel.fill_rect(0, 0, panel.width() / 2, panel.height(), "bg-surface")
```

- **Returns** `PanelMouse`

##### `clicks() → list[PanelClick]`

Every click since the last time you asked that did not land on a widget, oldest first. This is what lets a card hit-test its own drawing: a map, a chart, a seating plan. Each click is handed out once. Up to 32 are kept between reads.

```
for c in panel.clicks():
  if c.x > 250:
    print("right half", c.x, c.y)
```

- **Returns** `list[PanelClick]`

##### `capture_keys() → None`

Ask for the keyboard. After this, clicking the card gives it focus and its keystrokes go to `panel.keys()` instead of the game's own shortcuts; Escape or clicking elsewhere hands the keyboard back. Call it once above your loop. A card that never calls it can never take a key.

- **Returns** `None`

##### `keys() → list[PanelKey]`

Every key pressed since the last time you asked, oldest first, for a card that called `panel.capture_keys()` and holds focus. Each press is handed out once. Up to 32 are kept between reads.

```
panel.capture_keys()
while True:
  panel.clear()
  for k in panel.keys():
    if k.key == "ArrowUp":
      cursor = cursor - 1
```

- **Returns** `list[PanelKey]`

##### `draw_text(x: float, y: float, text: str, size?: float, color?: str, wrap?: float) → None`

Text rendered in monospace at the given size. Optional `wrap` (pixel width) enables greedy word-wrapping into a multi-line block, useful for log feeds and order briefings. Color accepts theme tokens or hex.

```preview
draw_text(10, 24, "Hello, panel.", 14, "text-bright")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `text` | `str` | Text to draw |
| `size` | `float` | Font size in pixels |
| `color` | `str` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |
| `wrap` | `float` | Optional wrap width in pixels |

- **Returns** `None`

##### `icon_ids() → list[str]`

List of every id `draw_icon` can render, sorted. Covers more than the items you can hold: fluids, creatures, essences, and machine art all have icons. Use it to build a picker, validate an id before drawing, or just print the catalog once while you are writing a card.

```
for icon in panel.icon_ids():
  print(icon)
```

- **Returns** `list[str]`

##### `draw_icon(x: float, y: float, item_id: str, size?: float) → None`

Render any icon from the game's item catalog at the requested size (default **32** pixels). Item id is the same string you'd pass to `inventory` / `storage_bin` APIs (`"iron_ore"`, `"iron_ingot"`, `"water"`, etc.), plus things you never hold such as fluids and creatures. `panel.icon_ids()` returns the full list, and every item's own page lives under **Database** in this panel. Unknown ids no-op silently.

```preview
draw_icon()
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X coordinate (pixels) |
| `y` | `float` | Y coordinate (pixels) |
| `item_id` | `str` | Item id to draw the icon for |
| `size` | `float` | Icon size in pixels (default 32) |

- **Returns** `None`

##### `draw_rect(x: float, y: float, w: float, h: float, color?: str) → None`

Outlined rectangle in the given color (defaults to `"border"`). Use for custom subsection borders or visual frames.

```preview
draw_rect(10, 10, 260, 60, "accent")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width (pixels) |
| `h` | `float` | Height (pixels) |
| `color` | `str` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `fill_rect(x: float, y: float, w: float, h: float, color?: str) → None`

Filled rectangle in the given color (defaults to `"accent"`). Use for backgrounds, progress fills, color blocks.

```preview
fill_rect(10, 10, 260, 60, "success")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width (pixels) |
| `h` | `float` | Height (pixels) |
| `color` | `str` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `draw_circle(x: float, y: float, r: float, color?: str) → None`

Outlined circle in the given color.

```preview
draw_circle(140, 40, 24, "accent")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `r` | `float` | Radius |
| `color` | `str` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `fill_circle(x: float, y: float, r: float, color?: str) → None`

Filled disc in the given color.

```preview
fill_circle(140, 40, 24, "warning")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `r` | `float` | Radius |
| `color` | `str` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `draw_line(x1: float, y1: float, x2: float, y2: float, color?: str) → None`

Single straight line.

```preview
draw_line(10, 40, 270, 40, "accent")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x1` | `float` | Start X (pixels) |
| `y1` | `float` | Start Y (pixels) |
| `x2` | `float` | End X (pixels) |
| `y2` | `float` | End Y (pixels) |
| `color` | `str` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `draw_polygon(points: list[float], color?: str) → None`

Outlined closed shape through a flat list of coordinates: `[x1, y1, x2, y2, ...]`. Needs at least two points. Up to 4096 points per call.

```preview
draw_polygon([40, 10, 120, 30, 100, 70, 30, 60], "accent")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `points` | `list[float]` | Flat list of coordinates: `[x1, y1, x2, y2, ...]`. |
| `color` | `str` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `fill_polygon(points: list[float], color?: str) → None`

Filled closed shape through a flat list of coordinates. Same input as `draw_polygon`.

```preview
fill_polygon([40, 10, 120, 30, 100, 70, 30, 60], "success")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `points` | `list[float]` | Flat list of coordinates: `[x1, y1, x2, y2, ...]`. |
| `color` | `str` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `polyline(points: list[float], color?: str, width?: float) → None`

Open line through a flat list of coordinates, with an optional width. Use it for a path, a route, or a chart trace your own code computed.

```preview
polyline([10, 60, 60, 20, 110, 50, 160, 15, 210, 40], "accent", 2)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `points` | `list[float]` | Flat list of coordinates: `[x1, y1, x2, y2, ...]`. |
| `color` | `str` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |
| `width` | `float` | Line width in pixels (default 1). |

- **Returns** `None`

##### `clip_rect(x: float, y: float, w: float, h: float) → None`

Confine every later drawing call to a rectangle, until `clear_clip()`. Use it to keep a scrolling or oversized drawing inside its box. A widget drawn under a clip takes clicks only where it shows, so one clipped out of sight takes none. Clips nest up to 16 deep; any left open are closed for you when the frame finishes.

```
panel.clip_rect(10, 10, 200, 80)
panel.draw_text(12, 30, long_line, 12)
panel.clear_clip()
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X (pixels) |
| `y` | `float` | Y (pixels) |
| `w` | `float` | Width (pixels) |
| `h` | `float` | Height (pixels) |

- **Returns** `None`

##### `clear_clip(all?: bool) → None`

Close the innermost `clip_rect`, or every open one when passed `True`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `all` | `bool` | True closes every open clip; omitted closes the innermost one. |

- **Returns** `None`

##### `clear() → None`

Wipe the panel canvas, and with it every widget's clickable area. Call at the top of every `while True:` loop iteration so old paint doesn't ghost behind new paint. Inside a `clip_rect` it wipes only the clipped area, and only the widgets it erased stop taking clicks.

- **Returns** `None`

##### `width() → int`

Current logical canvas width in pixels: **500** for a one-column card or **1000** for a two-column card. Use for ratio-based positioning.

- **Returns** `int`

##### `height() → int`

Current logical canvas height in pixels: **200** for a one-row card or **400** for a two-row card. Use for ratio-based positioning.

- **Returns** `int`

*Types / Panels*

## PanelClick

**Returned by:** `panel.clicks()` (panel scripts only)

### Properties

##### `.x: float`

Click X in panel coordinates.

- **Returns** `float`

##### `.y: float`

Click Y in panel coordinates.

- **Returns** `float`

*Types / Panels*

## PanelKey

**Returned by:** `panel.keys()` (panel scripts only)

### Properties

##### `.key: str`

Key name, such as `"a"`, `"Enter"`, or `"ArrowLeft"`.

- **Returns** `str`

##### `.ctrl: bool`

True when Ctrl was held.

- **Returns** `bool`

##### `.shift: bool`

True when Shift was held.

- **Returns** `bool`

##### `.alt: bool`

True when Alt was held.

- **Returns** `bool`

##### `.meta: bool`

True when Cmd or the Windows key was held.

- **Returns** `bool`

*Types / Panels*

## PanelMouse

**Returned by:** `panel.mouse()` (panel scripts only)

### Properties

##### `.x: float`

Cursor X in panel coordinates.

- **Returns** `float`

##### `.y: float`

Cursor Y in panel coordinates.

- **Returns** `float`

##### `.over: bool`

True while the cursor is over this card.

- **Returns** `bool`

*Types / Contracts*

## ActionResult

**Returned by:** Gameplay commands with no extra result fields

### Properties

##### `.status: str`

Stable result code for scripts to check. `.message` explains what happened.

- **Returns** `str`
- **Possible values** `"ok"`, `"not_mounted"`, `"invalid"`, `"out_of_bounds"`, `"busy"`, `"not_at_site"`, `"not_surveyed"`, `"too_hard"`, `"no_cargo_space"`, `"no_power"`, `"not_enough_power"`, `"not_found"`, `"locked"`, `"already_active"`, `"wrong_position"`, `"insufficient_materials"`, `"paused_no_power"`, `"cargo_present"`, `"blocked"`, `"paused"`, `"canceled"`, `"not_ready"`, `"not_local"`, `"same_endpoint"`, `"unsupported_source"`, `"source_is_vehicle"`, `"unsupported_target"`, `"target_is_vehicle"`, `"incompatible"`, `"duplicate"`, `"invalid_type"`, `"path"`, `"wall"`, `"exit"`, `"in_progress"`, `"ongoing"`, `"win"`, `"loss"`, `"draw"`, `"occupied"`, `"no_game"`, `"rejected"`, `"booting"`, `"already_booted"`, `"activating"`, `"already_online"`, `"boot_required"`, `"initializing"`, `"power_required"`, `"insufficient_credits"`, `"inventory_full"`, `"not_toggleable"`, `"under_construction"`, `"not_connected"`, `"no_script"`, `"script_running"`, `"script_paused"`, `"editor_busy"`, `"variant_not_found"`, `"incompatible_variant"`, `"source_too_large"`, `"already_running"`, `"not_powered"`, `"started"`, `"already_repaired"`, `"no_source"`, `"already_testing"`, `"too_far"`, `"already_here"`, `"overheated"`, `"moving"`, `"dropped"`, `"empty"`, `"invalid_seed"`, `"no_seed"`, `"holding"`, `"not_empty"`, `"base_sector"`, `"no_kit"`, `"invalid_kit"`, `"not_plantable"`, `"insufficient_water"`, `"tank_empty"`, `"already_full"`, `"no_salt"`, `"invalid_input"`, `"no_plant"`, `"already_mature"`, `"tier_conflict"`, `"no_dose"`, `"nothing"`, `"script_present"`, `"partial"`, `"not_mature"`, `"no_forage"`, `"correct"`, `"incorrect"`, `"already_completed_correct"`, `"already_completed_incorrect"`, `"accepted"`, `"wrong_planet"`, `"wrong_contract"`, `"unknown_contract"`, `"key_is_planet"`, `"unknown_key"`, `"not_at_service_point"`, `"item_not_in_inventory"`, `"unknown_module"`, `"slot_not_compatible"`, `"slot_occupied"`, `"invalid_slot"`, `"capability_already_mounted"`, `"slot_empty"`, `"holder_not_empty"`, `"invalid_internal_slot"`, `"not_container"`, `"item_not_accepted"`, `"internal_slot_occupied"`, `"internal_slot_empty"`, `"container_not_empty"`, `"charging"`, `"queued"`, `"target_reached"`, `"not_docked"`, `"station_offline"`, `"already_dispatched"`, `"unknown_recipe"`, `"offline"`, `"recipe_locked"`, `"material_mismatch"`, `"material_present"`, `"invalid_channel"`, `"invalid_value"`, `"channel_limit"`, `"invalid_key"`, `"invalid_coords"`, `"invalid_icon"`, `"invalid_color"`, `"invalid_text"`, `"limit_reached"`, `"entry_limit"`, `"unknown_order"`, `"completed"`, `"station_not_found"`, `"out_of_range"`, `"scrambled"`, `"drill_not_found"`, `"invalid_target"`, `"not_at_station"`, `"wrong_engine_for_module"`, `"cargo_capacity_exceeded"`, `"module_not_mounted"`, `"hot_cargo_requires_plating"`, `"refueling"`, `"no_oil"`, `"not_stranded"`, `"no_rescue"`, `"worker_not_present"`, `"construction_dependency"`, `"not_undeployable"`, `"self_target"`, `"docked_drone"`, `"is_home"`, `"name_empty"`, `"name_too_long"`, `"name_taken"`, `"output_full"`, `"complete"`, `"no_input"`, `"no_active"`, `"cargo_occupied"`, `"no_fragment"`, `"input_occupied"`, `"source_empty"`, `"source_busy"`, `"wrong_outpost"`, `"invalid_source"`, `"invalid_reagent"`, `"invalid_qty"`, `"invalid_properties"`, `"invalid_property_match"`, `"insufficient_input"`, `"recipe_mismatch"`, `"input_empty"`, `"not_analyzed"`, `"invalid_specimen"`, `"chamber_occupied"`, `"not_in_input"`, `"invalid_fragment"`, `"destroyed"`, `"unknown_gene"`, `"invalid_recipe"`, `"wrong_materials"`, `"wrong_fragment"`, `"no_recipe"`, `"conditioned"`, `"burned"`, `"no_run"`, `"species_exists"`, `"unknown_creature"`, `"not_cataloged"`, `"no_target"`, `"wrong_feed"`, `"insufficient_feed"`, `"insufficient_reagents"`, `"no_colony"`, `"not_established"`, `"insufficient_capacity"`, `"unknown_node"`, `"already_purchased"`, `"population_locked"`, `"insufficient_insight"`, `"output_busy"`, `"no_op"`, `"no_material"`

##### `.message: str`

Player-readable explanation of the exact command outcome. Suitable for logs and player-facing diagnostics.

- **Returns** `str`

*Types / System*

## CommandResult

**Returned by:** Component.next_command()

### Properties

##### `.status: str`

`"ok"` when a command was consumed, otherwise `"empty"`.

- **Returns** `str`
- **Possible values** `"ok"`, `"empty"`

##### `.message: str`

Player-readable explanation of the command dequeue result.

- **Returns** `str`

##### `.command: ScriptCommand | None`

Consumed `ScriptCommand`, or `None` when the queue was empty.

- **Returns** `ScriptCommand | None`

*Types / System*

## CountResult

**Returned by:** Queue, discard, clear, and bulk-count commands

### Properties

##### `.status: str`

`"ok"` when one or more entries changed, `"no_op"` when nothing changed, or a command-specific rejection such as `"invalid_channel"` or `"invalid_key"`.

- **Returns** `str`
- **Possible values** `"ok"`, `"no_op"`, `"invalid_channel"`, `"invalid_key"`

##### `.message: str`

Player-readable explanation of the count operation.

- **Returns** `str`

##### `.count: int`

Whole-number entries or units affected by the command.

- **Returns** `int`

*Types / System*

## CropJob

**Returned by:** Crop Automator current_job() and get_queue()

### Properties

##### `.id: int`

Stable whole-number job id.

- **Returns** `int`

##### `.action: str`

Requested work: `"harvest"`, `"plant"`, or `"apply"`.

- **Returns** `str`
- **Possible values** `"harvest"`, `"plant"`, `"apply"`

##### `.sector: str`

Target field sector.

- **Returns** `str`

##### `.item_id: str | None`

Requested seed or treatment item, or `None` for harvest jobs.

- **Returns** `str | None`

##### `.state: str`

`"working"`, `"blocked"`, or `"queued"`.

- **Returns** `str`
- **Possible values** `"working"`, `"blocked"`, `"queued"`

##### `.progress: float`

Completed fraction from **0-1**. Pending jobs read **0**.

- **Returns** `float`

##### `.blocker: str | None`

Exact physical blocker, or `None` while working or queued.

- **Returns** `str | None`
- **Possible values** `"not_placed"`, `"no_power"`, `"no_seed"`, `"no_material"`, `"output_full"`, `"results_full"`

*Types / System*

## CropJobResult

**Returned by:** Crop Automator next_result()

### Properties

##### `.status: str`

Terminal job outcome, or `"empty"` when no completed result was waiting.

- **Returns** `str`
- **Possible values** `"ok"`, `"partial"`, `"empty"`, `"out_of_range"`, `"no_plant"`, `"not_mature"`, `"no_forage"`, `"not_empty"`, `"base_sector"`, `"already_mature"`, `"tier_conflict"`, `"invalid_seed"`, `"invalid_material"`

##### `.message: str`

Player-readable explanation of the terminal outcome.

- **Returns** `str`

##### `.job_id: int | None`

Completed job id, or `None` when empty.

- **Returns** `int | None`

##### `.action: str | None`

Completed action, or `None` when empty.

- **Returns** `str | None`
- **Possible values** `"harvest"`, `"plant"`, `"apply"`

##### `.sector: str | None`

Completed target sector, or `None` when empty.

- **Returns** `str | None`

##### `.item_id: str | None`

Requested seed or treatment item, or `None` for harvest and empty results.

- **Returns** `str | None`

##### `.collected: int`

Whole Forage units committed to the output bin by a harvest. Always **0** otherwise.

- **Returns** `int`

##### `.discarded: int`

Whole Forage units a harvest could not fit and threw away. Non-zero only with `"partial"`; the cell is cleared either way.

- **Returns** `int`

*Types / System*

## JobReceipt

**Returned by:** Crop Automator job submission

### Properties

##### `.status: str`

`"queued"` when the job entered the FIFO, otherwise the exact reason it was not accepted.

- **Returns** `str`
- **Possible values** `"queued"`, `"queue_full"`, `"not_placed"`, `"out_of_range"`, `"invalid_seed"`, `"invalid_material"`

##### `.message: str`

Player-readable explanation of the submission outcome.

- **Returns** `str`

##### `.job_id: int | None`

Stable whole-number job id, or `None` when no job was created.

- **Returns** `int | None`

##### `.queue_position: int | None`

One-based execution position at submission time, including the active job, or `None` when rejected.

- **Returns** `int | None`

*Types / Terraforming*
