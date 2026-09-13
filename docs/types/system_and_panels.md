# Data Types: System And Panels

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`Panel`](#panel) (PANELS)
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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `toggle(x, y, on, label?)`

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `pill(x, y, text, color?)`

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

##### `switch(key, x, y, default_on?, label?)`

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

- **Returns** `boolean`

##### `slider(key, x, y, w, default?, label?)`

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

- **Returns** `number`

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `clear()`

Wipe the panel canvas. Call at the top of every `while True:` loop iteration so old paint doesn't ghost behind new paint.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `width()`

Current logical canvas width in pixels: **500** for a one-column card or **1000** for a two-column card. Use for ratio-based positioning.

- **Returns** `number`

##### `height()`

Current logical canvas height in pixels: **200** for a one-row card or **400** for a two-row card. Use for ratio-based positioning.

- **Returns** `number`

*Types / Contracts*

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
