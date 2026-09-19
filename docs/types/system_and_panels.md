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

##### `card(x, y, w, h, title?)`

Bordered subsection with optional title bar. Use to group related content visually, mirrors the dashboard's card aesthetic.

```preview
card(8, 8, 264, 64, "Section")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width (pixels) |
| `h` | `number` | Height (pixels) |
| `title` | `string` | Optional card title |

- **Returns** `None`

##### `divider(x1, y1, x2, y2)`

Horizontal or vertical separator line in the muted border color. Use to break a panel into visual zones.

```preview
divider(10, 40, 270, 40)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x1` | `number` | Start X (pixels) |
| `y1` | `number` | Start Y (pixels) |
| `x2` | `number` | End X (pixels) |
| `y2` | `number` | End Y (pixels) |

- **Returns** `None`

##### `label(x, y, text, style?)`

Semantically styled text. `style` accepts `"title"` (bright, bold), `"caption"` (muted, uppercase), `"muted"` (secondary), `"value"` (numeric readout). Defaults to `"title"`. Use instead of `draw_text` when you want the dashboard's text hierarchy applied automatically.

```preview
label(10, 30, "OXYGEN", "caption")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `text` | `string` | Label text |
| `style` | `string` | Text style preset. |

- **Returns** `None`

##### `status_dot(x, y, r, status)`

Colored disc resolved from a status string. Recognized values: `"running"` (green), `"paused"` (warning), `"error"` (error red), `"idle"` (muted). Renders with a subtle outer glow ring. Useful for per-row indicators in machine lists.

```preview
status_dot(0, 0, 5, "running")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `r` | `number` | Radius (pixels) |
| `status` | `string` | Status preset. |

- **Returns** `None`

##### `toggle(x, y, on, label?, size?)`

Green/grey power-toggle pill matching the dashboard's machine on/off control. This widget only displays the `on` value you pass in; use `panel.switch(...)` for a clickable control.

```preview
toggle(10, 12, true, "powered")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `on` | `boolean` | Whether the toggle is on |
| `label` | `string` | Optional label |
| `size` | `number` | Pill height in pixels (default 18). The width, knob and label follow it. |

- **Returns** `None`

##### `pill(x, y, text, color?, size?)`

Rounded badge with text, achievement-style. Color accepts theme tokens (`"accent"`, `"success"`, `"warning"`, `"error"`, `"text-muted"`) or hex. Use for status labels or category tags.

```preview
pill(10, 22, "earned", "success")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `text` | `string` | Pill text |
| `color` | `string` | Theme token (e.g. `"accent"`), or any CSS color (hex, `rgb()`, `hsl()`, named). |
| `size` | `number` | Pill height in pixels (default 18). The text and padding follow it; the width still comes from the text. |

- **Returns** `None`

##### `counter(x, y, value, label?, size?)`

Big-number stat block, large value on top, small uppercase label below. Use for headline numbers (credits, day count, ingot inventory). `size` defaults to **24**.

```preview
counter(16, 38, 87, "shipped", 26)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `value` | `any` | Value to display |
| `label` | `string` | Optional label |
| `size` | `number` | Optional numeric font size in pixels (default 24) |

- **Returns** `None`

##### `progress_bar(x, y, w, h, fraction, color?)`

Horizontal fill bar with track + filled accent. `fraction` clamps to **0-1**. Color defaults to `"accent"`; use `"success"`, `"warning"`, `"error"` for traffic-light cues.

```preview
progress_bar(0.72, "success")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width (pixels) |
| `h` | `number` | Height (pixels) |
| `fraction` | `number` | Fill (0-1) |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `vertical_bar(x, y, w, h, fraction, color?)`

Vertical fill bar, fills from the bottom up. Same `fraction` and color rules as `progress_bar`. Use when the panel layout favors verticality (multi-tank stacks, atmospheric stacks).

```preview
vertical_bar(110, 10, 30, 60, 0.6)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width (pixels) |
| `h` | `number` | Height (pixels) |
| `fraction` | `number` | Fill (0-1) |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `bar_chart(x, y, w, h, values, max?, labels?)`

Multi-bar comparison chart, themed alternating colors, optional labels under each bar. `max` is optional, omit to auto-scale to the largest value.

```preview
bar_chart(0, 0, 0, 0, [42, 80, 26, 61, 95], 100)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width (pixels) |
| `h` | `number` | Height (pixels) |
| `values` | `any` | Numeric values to plot |
| `max` | `number` | Optional maximum value |
| `labels` | `any` | Optional labels |

- **Returns** `None`

##### `gauge(x, y, radius, fraction, label?)`

Three-quarter-circle dial with arc fill. `fraction` clamps to **0-1**, sweeping **270°** from bottom-left around to bottom-right. Optional center label sits in the middle (typically the value as text).

```preview
gauge(140, 50, 32, 0.62, "62%")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `radius` | `number` | Gauge radius in pixels |
| `fraction` | `number` | Fill fraction in the **0-1** range |
| `label` | `string` | Optional label |

- **Returns** `None`

##### `spark_line(x, y, w, h, values)`

Compact trend line drawn from a numeric series. Player accumulates values into a list and pushes the most recent on each tick, the widget normalizes to the series' min/max range and fills a subtle area below the line. Empty / single-value series no-op.

```preview
spark_line(0, 0, 0, 0)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width (pixels) |
| `h` | `number` | Height (pixels) |
| `values` | `any` | Numeric values to plot |

- **Returns** `None`

##### `button(key, x, y, w?, h?, label?)`

A clickable button. Pass a unique `key` so the click routes back to it. Returns `True` the single tick it's pressed (momentary), branch on it: `if panel.button("shed", 10, 12): power.set_powered(...)`. `w`/`h` default to **90×26**. The first input widget that lets a card *act* on the player's click, not just paint.

```preview
button(10, 12, 90, 26, "shed now")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Unique id for this control |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width in pixels (default 90) |
| `h` | `number` | Height in pixels (default 26) |
| `label` | `string` | Optional label |

- **Returns** `boolean`

##### `switch(key, x, y, default_on?, label?, size?)`

An interactive on/off switch, the player clicks it to flip. Pass a unique `key`; `default_on` sets the starting state the first time the card runs. Returns the current boolean every tick, and the flip persists in the card's state across reloads. Unlike the display `toggle` (which only shows a state you pass in), this one is clickable: `auto = panel.switch("auto_recover", 165, 128, True)`.

```preview
switch(10, 12, true, "auto-recover")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Unique id for this control |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `default_on` | `boolean` | Initial on/off state |
| `label` | `string` | Optional label |
| `size` | `number` | Pill height in pixels (default 18). The clickable area follows it. |

- **Returns** `boolean`

##### `slider(key, x, y, w, default?, label?, size?)`

A horizontal slider the player clicks to set a value. Pass a unique `key`; `default` (**0-1**) sets the starting value. Returns the current value as a **0-1** number every tick, persisted in the card's state. Use it for thresholds the player tunes live, a buy-trigger level, a throttle target.

```preview
slider(10, 14, 120, 0.5, "rate")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Unique id for this control |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width (pixels) |
| `default` | `number` | Initial value 0-1 |
| `label` | `string` | Optional label |
| `size` | `number` | Track height in pixels (default 14). The knob, label and clickable area follow it. |

- **Returns** `number`

##### `checkbox(key, x, y, default_on?, label?, size?)`

A check box the player clicks. Same stored state as `panel.switch(...)`, so `set_switch` drives either one; the difference is the shape. Pass a unique `key`; `default_on` sets the starting state the first time the card runs.

```preview
checkbox(10, 12, true, "night mode")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Unique key this box stores its state under. |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `default_on` | `boolean` | Checked state the first time the card runs. |
| `label` | `string` | Optional label drawn to the right. |
| `size` | `number` | Box edge length in pixels (default 14). The tick and label follow it. |

- **Returns** `boolean`

##### `radio_group(key, x, y, options, default?, row_height?)`

One choice out of several, drawn one option per row. The whole group shares a single `key`, which is why five options cost the card one stored value instead of five: building radio buttons out of five separate switches is what leaves five keys behind. Returns the selected option's text every tick. `default` accepts the option text or its row number.

```preview
radio_group(10, 6, ["ore", "ingots", "both"], 1)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Unique key the whole group stores its choice under. |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `options` | `any` | List of choices, drawn one per row. |
| `default` | `any` | Option text, or row number, selected the first time the card runs. |
| `row_height` | `number` | Row pitch in pixels (default 20). The dot and text follow it. |

- **Returns** `string`

##### `combo(key, x, y, w, options, default?, label?, size?)`

A dropdown. Clicking it opens the game's own menu over the card, so the choices stay readable at any card size and never get clipped by the panel edge. Returns the selected option's text every tick, and `None` while `options` is empty. `default` accepts the option text or its row number.

```preview
combo(10, 12, 150, "iron_ingot", "recipe")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Unique key this box stores its choice under. |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width (pixels) |
| `options` | `any` | List of choices shown when the player opens the box. |
| `default` | `any` | Option text, or row number, selected the first time the card runs. |
| `label` | `string` | Optional label drawn to the right. |
| `size` | `number` | Box height in pixels (default 24). The text and caret follow it. |

- **Returns** `string`

##### `text_field(key, x, y, w, default?, placeholder?, label?, size?)`

A one-line text box. Clicking it opens a real text editor over the field, so selection, copy, paste and your keyboard's own input method all work; the card shows the committed value. Returns the current text every tick. Up to 1024 characters, saved with the card.

```preview
text_field(10, 12, 180, "outpost_north", "name...")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Unique key this field stores its text under. |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width (pixels) |
| `default` | `string` | Text the field holds the first time the card runs. |
| `placeholder` | `string` | Muted text shown while the field is empty. |
| `label` | `string` | Title shown on the editor the player types into. |
| `size` | `number` | Field height in pixels (default 24). The text follows it. |

- **Returns** `string`

##### `list(key, x, y, w, h, items, row_height?)`

A scrolling list of rows the player can pick from. Rows past the box height scroll with the wheel; the selected row is stored with the card and returned every tick, or `None` while `items` is empty. Use it where a card has more entries than space, which is most fleet and inventory boards.

```preview
list(10, 6, 160, 68, ["rover_1", "pioneer_1", "drone_1", "drone_2"], 0)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Unique key this list stores its selected row under. |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width (pixels) |
| `h` | `number` | Height (pixels). Rows past it scroll. |
| `items` | `any` | List of rows to show. |
| `row_height` | `number` | Row pitch in pixels (default 20). The text follows it. |

- **Returns** `string`

##### `icon_button(key, x, y, size, item_id)`

A square button whose label is an item icon. Returns `True` the single tick it is pressed, exactly like `panel.button(...)`. Use it for a toolbar strip where a word would not fit. `panel.icon_ids()` lists every id it can draw.

```preview
icon_button(10, 8, 44, "iron_ingot")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Unique key so the click routes back to this button. |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `size` | `number` | Button edge length in pixels (default 32). |
| `item_id` | `string` | Icon to draw inside the button. `panel.icon_ids()` lists every id. |

- **Returns** `boolean`

##### `set_switch(key, on)`

Force a switch or check box to a state from code, instead of waiting for the player to click it. Use it to build a radio group out of switches, to reset a cockpit to a known layout, or to reflect a state the card read from the world.

```
if not power.is_online():
  panel.set_switch("auto_dispatch", False)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Key of the switch or check box to set. |
| `on` | `boolean` | New state. |

- **Returns** `None`

##### `set_slider(key, value)`

Force a slider to a value (0-1) from code.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Key of the slider to set. |
| `value` | `number` | New value, clamped to 0-1. |

- **Returns** `None`

##### `set_selected(key, option)`

Force a radio group, combo box, or list to a choice from code. Accepts the option's text or its row number.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Key of the radio group, combo box, or list to set. |
| `option` | `any` | Option text, or row number. |

- **Returns** `None`

##### `set_text(key, text)`

Force a text field's contents from code.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Key of the text field to set. |
| `text` | `string` | New text. |

- **Returns** `None`

##### `forget(key)`

Drop one stored widget value. The next paint of that widget starts from its declared default again, which is how a card resets one control without disturbing the others.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `string` | Key to drop from the card's stored input state. |

- **Returns** `None`

##### `clear_inputs()`

Drop every stored widget value on this card. Widget keys are never swept automatically, because a card that only paints one page at a time would lose the other page's state; this is the deliberate reset. A card is limited to 512 stored keys, and a key built from changing data (a tick count, a name that varies) is what reaches that limit.

- **Returns** `None`

##### `mouse()`

Where the cursor is on this card, in the same coordinates you draw in. `over` is `False` while the cursor is elsewhere. The sample is taken once per tick and the card repaints at the same rate, so a highlight drawn from it follows the cursor about a frame behind: right for showing what is under the pointer, wrong for anything that must track it exactly.

```
m = panel.mouse()
if m.over and m.x < panel.width() / 2:
  panel.fill_rect(0, 0, panel.width() / 2, panel.height(), "bg-surface")
```

- **Returns** `PanelMouse`

##### `clicks()`

Every click since the last time you asked that did not land on a widget, oldest first. This is what lets a card hit-test its own drawing: a map, a chart, a seating plan. Each click is handed out once. Up to 32 are kept between reads.

```
for c in panel.clicks():
  if c.x > 250:
    print("right half", c.x, c.y)
```

- **Returns** `list<PanelClick>`

##### `capture_keys()`

Ask for the keyboard. After this, clicking the card gives it focus and its keystrokes go to `panel.keys()` instead of the game's own shortcuts; Escape or clicking elsewhere hands the keyboard back. Call it once above your loop. A card that never calls it can never take a key.

- **Returns** `None`

##### `keys()`

Every key pressed since the last time you asked, oldest first, for a card that called `panel.capture_keys()` and holds focus. Each press is handed out once. Up to 32 are kept between reads.

```
panel.capture_keys()
while True:
  panel.clear()
  for k in panel.keys():
    if k.key == "ArrowUp":
      cursor = cursor - 1
```

- **Returns** `list<PanelKey>`

##### `draw_text(x, y, text, size?, color?, wrap?)`

Text rendered in monospace at the given size. Optional `wrap` (pixel width) enables greedy word-wrapping into a multi-line block, useful for log feeds and order briefings. Color accepts theme tokens or hex.

```preview
draw_text(10, 24, "Hello, panel.", 14, "text-bright")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `text` | `string` | Text to draw |
| `size` | `number` | Font size in pixels |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |
| `wrap` | `number` | Optional wrap width in pixels |

- **Returns** `None`

##### `icon_ids()`

List of every id `draw_icon` can render, sorted. Covers more than the items you can hold: fluids, creatures, essences, and machine art all have icons. Use it to build a picker, validate an id before drawing, or just print the catalog once while you are writing a card.

```
for icon in panel.icon_ids():
  print(icon)
```

- **Returns** `list<string>`

##### `draw_icon(x, y, item_id, size?)`

Render any icon from the game's item catalog at the requested size (default **32** pixels). Item id is the same string you'd pass to `inventory` / `storage_bin` APIs (`"iron_ore"`, `"iron_ingot"`, `"water"`, etc.), plus things you never hold such as fluids and creatures. `panel.icon_ids()` returns the full list, and every item's own page lives under **Database** in this panel. Unknown ids no-op silently.

```preview
draw_icon()
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X coordinate (pixels) |
| `y` | `number` | Y coordinate (pixels) |
| `item_id` | `string` | Item id to draw the icon for |
| `size` | `number` | Icon size in pixels (default 32) |

- **Returns** `None`

##### `draw_rect(x, y, w, h, color?)`

Outlined rectangle in the given color (defaults to `"border"`). Use for custom subsection borders or visual frames.

```preview
draw_rect(10, 10, 260, 60, "accent")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width (pixels) |
| `h` | `number` | Height (pixels) |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `fill_rect(x, y, w, h, color?)`

Filled rectangle in the given color (defaults to `"accent"`). Use for backgrounds, progress fills, color blocks.

```preview
fill_rect(10, 10, 260, 60, "success")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width (pixels) |
| `h` | `number` | Height (pixels) |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `draw_circle(x, y, r, color?)`

Outlined circle in the given color.

```preview
draw_circle(140, 40, 24, "accent")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `r` | `number` | Radius |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `fill_circle(x, y, r, color?)`

Filled disc in the given color.

```preview
fill_circle(140, 40, 24, "warning")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `r` | `number` | Radius |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `draw_line(x1, y1, x2, y2, color?)`

Single straight line.

```preview
draw_line(10, 40, 270, 40, "accent")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x1` | `number` | Start X (pixels) |
| `y1` | `number` | Start Y (pixels) |
| `x2` | `number` | End X (pixels) |
| `y2` | `number` | End Y (pixels) |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `draw_polygon(points, color?)`

Outlined closed shape through a flat list of coordinates: `[x1, y1, x2, y2, ...]`. Needs at least two points. Up to 4096 points per call.

```preview
draw_polygon([40, 10, 120, 30, 100, 70, 30, 60], "accent")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `points` | `any` | Flat list of coordinates: `[x1, y1, x2, y2, ...]`. |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `fill_polygon(points, color?)`

Filled closed shape through a flat list of coordinates. Same input as `draw_polygon`.

```preview
fill_polygon([40, 10, 120, 30, 100, 70, 30, 60], "success")
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `points` | `any` | Flat list of coordinates: `[x1, y1, x2, y2, ...]`. |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |

- **Returns** `None`

##### `polyline(points, color?, width?)`

Open line through a flat list of coordinates, with an optional width. Use it for a path, a route, or a chart trace your own code computed.

```preview
polyline([10, 60, 60, 20, 110, 50, 160, 15, 210, 40], "accent", 2)
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `points` | `any` | Flat list of coordinates: `[x1, y1, x2, y2, ...]`. |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, named). |
| `width` | `number` | Line width in pixels (default 1). |

- **Returns** `None`

##### `clip_rect(x, y, w, h)`

Confine every later drawing call to a rectangle, until `clear_clip()`. Use it to keep a scrolling or oversized drawing inside its box. Clips nest up to 16 deep; any left open are closed for you when the frame finishes.

```
panel.clip_rect(10, 10, 200, 80)
panel.draw_text(12, 30, long_line, 12)
panel.clear_clip()
```

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | X (pixels) |
| `y` | `number` | Y (pixels) |
| `w` | `number` | Width (pixels) |
| `h` | `number` | Height (pixels) |

- **Returns** `None`

##### `clear_clip(all?)`

Close the innermost `clip_rect`, or every open one when passed `True`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `all` | `boolean` | True closes every open clip; omitted closes the innermost one. |

- **Returns** `None`

##### `clear()`

Wipe the panel canvas. Call at the top of every `while True:` loop iteration so old paint doesn't ghost behind new paint.

- **Returns** `None`

##### `width()`

Current logical canvas width in pixels: **500** for a one-column card or **1000** for a two-column card. Use for ratio-based positioning.

- **Returns** `number`

##### `height()`

Current logical canvas height in pixels: **200** for a one-row card or **400** for a two-row card. Use for ratio-based positioning.

- **Returns** `number`

*Types / Panels*

---

## PanelClick

**Returned by:** `panel.clicks()` (panel scripts only)

### Properties

##### `.x`

Click X in panel coordinates.

- **Returns** `number`

##### `.y`

Click Y in panel coordinates.

- **Returns** `number`

*Types / Panels*

---

## PanelKey

**Returned by:** `panel.keys()` (panel scripts only)

### Properties

##### `.key`

Key name, such as `"a"`, `"Enter"`, or `"ArrowLeft"`.

- **Returns** `string`

##### `.ctrl`

True when Ctrl was held.

- **Returns** `boolean`

##### `.shift`

True when Shift was held.

- **Returns** `boolean`

##### `.alt`

True when Alt was held.

- **Returns** `boolean`

##### `.meta`

True when Cmd or the Windows key was held.

- **Returns** `boolean`

*Types / Panels*

---

## PanelMouse

**Returned by:** `panel.mouse()` (panel scripts only)

### Properties

##### `.x`

Cursor X in panel coordinates.

- **Returns** `number`

##### `.y`

Cursor Y in panel coordinates.

- **Returns** `number`

##### `.over`

True while the cursor is over this card.

- **Returns** `boolean`

*Types / Panels*

---

## ActionResult

**Returned by:** Gameplay commands with no extra result fields

### Properties

##### `.status`

Stable result code for scripts to check. `.message` explains what happened.

- **Returns** `string`
- **Possible values** `"ok"`, `"not_mounted"`, `"invalid"`, `"out_of_bounds"`, `"busy"`, `"not_at_site"`, `"not_surveyed"`, `"too_hard"`, `"no_cargo_space"`, `"no_power"`, `"not_enough_power"`, `"not_found"`, `"locked"`, `"already_active"`, `"wrong_position"`, `"insufficient_materials"`, `"paused_no_power"`, `"cargo_present"`, `"blocked"`, `"paused"`, `"canceled"`, `"not_ready"`, `"not_local"`, `"same_endpoint"`, `"unsupported_source"`, `"source_is_vehicle"`, `"unsupported_target"`, `"target_is_vehicle"`, `"incompatible"`, `"duplicate"`, `"invalid_type"`, `"path"`, `"wall"`, `"exit"`, `"in_progress"`, `"ongoing"`, `"win"`, `"loss"`, `"draw"`, `"occupied"`, `"no_game"`, `"rejected"`, `"booting"`, `"already_booted"`, `"activating"`, `"already_online"`, `"boot_required"`, `"initializing"`, `"power_required"`, `"insufficient_credits"`, `"inventory_full"`, `"not_toggleable"`, `"under_construction"`, `"not_connected"`, `"no_script"`, `"already_running"`, `"not_powered"`, `"started"`, `"already_repaired"`, `"no_source"`, `"already_testing"`, `"too_far"`, `"already_here"`, `"overheated"`, `"moving"`, `"dropped"`, `"empty"`, `"invalid_seed"`, `"no_seed"`, `"holding"`, `"not_empty"`, `"base_sector"`, `"no_kit"`, `"invalid_kit"`, `"not_plantable"`, `"insufficient_water"`, `"tank_empty"`, `"already_full"`, `"no_salt"`, `"invalid_input"`, `"no_plant"`, `"already_mature"`, `"tier_conflict"`, `"no_dose"`, `"nothing"`, `"script_present"`, `"partial"`, `"not_mature"`, `"no_forage"`, `"correct"`, `"incorrect"`, `"already_completed_correct"`, `"already_completed_incorrect"`, `"accepted"`, `"wrong_planet"`, `"wrong_contract"`, `"unknown_contract"`, `"key_is_planet"`, `"unknown_key"`, `"not_at_service_point"`, `"item_not_in_inventory"`, `"unknown_module"`, `"slot_not_compatible"`, `"slot_occupied"`, `"invalid_slot"`, `"capability_already_mounted"`, `"slot_empty"`, `"holder_not_empty"`, `"invalid_internal_slot"`, `"not_container"`, `"item_not_accepted"`, `"internal_slot_occupied"`, `"internal_slot_empty"`, `"container_not_empty"`, `"charging"`, `"queued"`, `"target_reached"`, `"not_docked"`, `"station_offline"`, `"already_dispatched"`, `"unknown_recipe"`, `"offline"`, `"recipe_locked"`, `"material_mismatch"`, `"material_present"`, `"invalid_channel"`, `"invalid_value"`, `"channel_limit"`, `"invalid_key"`, `"invalid_coords"`, `"invalid_icon"`, `"invalid_color"`, `"invalid_text"`, `"limit_reached"`, `"entry_limit"`, `"unknown_order"`, `"completed"`, `"station_not_found"`, `"out_of_range"`, `"scrambled"`, `"drill_not_found"`, `"invalid_target"`, `"not_at_station"`, `"wrong_engine_for_module"`, `"cargo_capacity_exceeded"`, `"module_not_mounted"`, `"hot_cargo_requires_plating"`, `"refueling"`, `"no_oil"`, `"not_stranded"`, `"no_rescue"`, `"worker_not_present"`, `"construction_dependency"`, `"output_full"`, `"complete"`, `"no_input"`, `"no_active"`, `"cargo_occupied"`, `"no_fragment"`, `"input_occupied"`, `"source_empty"`, `"source_busy"`, `"wrong_outpost"`, `"invalid_source"`, `"invalid_reagent"`, `"invalid_qty"`, `"invalid_properties"`, `"invalid_property_match"`, `"insufficient_input"`, `"recipe_mismatch"`, `"input_empty"`, `"not_analyzed"`, `"invalid_specimen"`, `"chamber_occupied"`, `"not_in_input"`, `"invalid_fragment"`, `"destroyed"`, `"unknown_gene"`, `"invalid_recipe"`, `"wrong_materials"`, `"wrong_fragment"`, `"no_recipe"`, `"conditioned"`, `"burned"`, `"no_run"`, `"species_exists"`, `"unknown_creature"`, `"not_cataloged"`, `"no_target"`, `"wrong_feed"`, `"insufficient_feed"`, `"insufficient_reagents"`, `"no_colony"`, `"not_established"`, `"insufficient_capacity"`, `"unknown_node"`, `"already_purchased"`, `"population_locked"`, `"insufficient_insight"`, `"output_busy"`, `"no_op"`, `"no_material"`

##### `.message`

Player-readable explanation of the exact command outcome. Suitable for logs and player-facing diagnostics.

- **Returns** `string`

*Types / System*

---

## CommandResult

**Returned by:** Component.next_command()

### Properties

##### `.status`

`"ok"` when a command was consumed, otherwise `"empty"`.

- **Returns** `string`
- **Possible values** `"ok"`, `"empty"`

##### `.message`

Player-readable explanation of the command dequeue result.

- **Returns** `string`

##### `.command`

Consumed `ScriptCommand`, or `None` when the queue was empty.

- **Returns** `Optional[ScriptCommand]`

*Types / System*

---

## CountResult

**Returned by:** Queue, discard, clear, and bulk-count commands

### Properties

##### `.status`

`"ok"` when one or more entries changed, `"no_op"` when nothing changed, or a command-specific rejection such as `"invalid_channel"` or `"invalid_key"`.

- **Returns** `string`
- **Possible values** `"ok"`, `"no_op"`, `"invalid_channel"`, `"invalid_key"`

##### `.message`

Player-readable explanation of the count operation.

- **Returns** `string`

##### `.count`

Whole-number entries or units affected by the command.

- **Returns** `number`

*Types / System*

---

## CropJob

**Returned by:** Crop Automator current_job() and get_queue()

### Properties

##### `.id`

Stable whole-number job id.

- **Returns** `number`

##### `.action`

Requested work: `"harvest"`, `"plant"`, or `"apply"`.

- **Returns** `string`
- **Possible values** `"harvest"`, `"plant"`, `"apply"`

##### `.sector`

Target field sector.

- **Returns** `string`

##### `.item_id`

Requested seed or treatment item, or `None` for harvest jobs.

- **Returns** `Optional[string]`

##### `.state`

`"working"`, `"blocked"`, or `"queued"`.

- **Returns** `string`
- **Possible values** `"working"`, `"blocked"`, `"queued"`

##### `.progress`

Completed fraction from **0-1**. Pending jobs read **0**.

- **Returns** `number`

##### `.blocker`

Exact physical blocker, or `None` while working or queued.

- **Returns** `Optional[string]`
- **Possible values** `"not_placed"`, `"no_power"`, `"no_seed"`, `"no_material"`, `"output_full"`, `"results_full"`

*Types / System*

---

## CropJobResult

**Returned by:** Crop Automator next_result()

### Properties

##### `.status`

Terminal job outcome, or `"empty"` when no completed result was waiting.

- **Returns** `string`
- **Possible values** `"ok"`, `"partial"`, `"empty"`, `"out_of_range"`, `"no_plant"`, `"not_mature"`, `"no_forage"`, `"not_empty"`, `"base_sector"`, `"already_mature"`, `"tier_conflict"`, `"invalid_seed"`, `"invalid_material"`

##### `.message`

Player-readable explanation of the terminal outcome.

- **Returns** `string`

##### `.job_id`

Completed job id, or `None` when empty.

- **Returns** `Optional[number]`

##### `.action`

Completed action, or `None` when empty.

- **Returns** `Optional[string]`
- **Possible values** `"harvest"`, `"plant"`, `"apply"`

##### `.sector`

Completed target sector, or `None` when empty.

- **Returns** `Optional[string]`

##### `.item_id`

Requested seed or treatment item, or `None` for harvest and empty results.

- **Returns** `Optional[string]`

##### `.collected`

Whole Forage units committed to the output bin by a harvest. Always **0** otherwise.

- **Returns** `number`

##### `.discarded`

Whole Forage units a harvest could not fit and threw away. Non-zero only with `"partial"`; the cell is cleared either way.

- **Returns** `number`

*Types / System*

---

## JobReceipt

**Returned by:** Crop Automator job submission

### Properties

##### `.status`

`"queued"` when the job entered the FIFO, otherwise the exact reason it was not accepted.

- **Returns** `string`
- **Possible values** `"queued"`, `"queue_full"`, `"not_placed"`, `"out_of_range"`, `"invalid_seed"`, `"invalid_material"`

##### `.message`

Player-readable explanation of the submission outcome.

- **Returns** `string`

##### `.job_id`

Stable whole-number job id, or `None` when no job was created.

- **Returns** `Optional[number]`

##### `.queue_position`

One-based execution position at submission time, including the active job, or `None` when rejected.

- **Returns** `Optional[number]`

*Types / Terraforming*

---
