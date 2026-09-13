# Component: console

> **Category:** Core Systems | **Component Name:** Console

Writes structured script output to the same Console used by `print()`. Access it with `get_component("console")`; no research is required. Messages can have a severity, named channel, color, and timestamp.

**Returned by:** `get_component("console")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.print(message, level="info", channel="", color="", timestamp=False)`

Print a line with full control. `level` is `info` / `warn` / `error` / `debug` (which feed the WARNINGS / ERRORS filters), or any other non-empty string for a custom level shown as a colored badge. An empty level behaves like `info`. `channel` routes the line to a named tab (empty = the main stream). `color` is a theme token (`"warning"`, `"success"`, `"accent"`), which recolors with the theme, or any CSS color: hex (`"#aabbcc"`), `"rgb(255,100,0)"`, `"hsl(30,100%,50%)"`, or a name like `"orange"`. A true `timestamp` value prepends the game time-of-day. Example: `get_component("console").print("Overheat", "alert", "alarms", "warning", True)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Value to print. |
| `level` | `string` | Severity or custom level. Built-ins: `info` / `warn` / `error` / `debug`. An empty string behaves like `info`; any other non-empty string is a custom level shown as a colored badge. |
| `channel` | `string` | Channel/tab name. Empty = the main stream. |
| `color` | `string` | Theme token (recolors with the theme), or any CSS color: hex (`"#aabbcc"`), `"rgb(255,100,0)"`, `"hsl(...)"`, or a name like `"orange"`. |
| `timestamp` | `boolean` | Prepend the game time-of-day. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.info(message, channel="", color="", timestamp=False)`

Print an info line (the default level). Its optional channel, color, and timestamp parameters behave like those on `print`. Equivalent to `print(message)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Value to print. |
| `channel` | `string` | Channel/tab name. Empty = the main stream. |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, or a named color). |
| `timestamp` | `boolean` | Prepend the game time-of-day. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.warn(message, channel="", color="", timestamp=False)`

Print a warning line, appears in the console's WARNINGS filter. Its optional channel, color, and timestamp parameters control routing and presentation. For an interruptive popup instead, use the global `notify(text, "warn")`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Value to print. |
| `channel` | `string` | Channel/tab name. Empty = the main stream. |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, or a named color). |
| `timestamp` | `boolean` | Prepend the game time-of-day. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.error(message, channel="", color="", timestamp=False)`

Print an error line, appears in the console's ERRORS filter. Its optional channel, color, and timestamp parameters control routing and presentation. This is your own message at error severity, not an uncaught exception.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Value to print. |
| `channel` | `string` | Channel/tab name. Empty = the main stream. |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, or a named color). |
| `timestamp` | `boolean` | Prepend the game time-of-day. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.debug(message, channel="", color="", timestamp=False)`

Print a low-priority debug line, hidden from the ALL view unless the player enables debug output. Its optional channel, color, and timestamp parameters control routing and presentation.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Value to print. |
| `channel` | `string` | Channel/tab name. Empty = the main stream. |
| `color` | `string` | Theme token, or any CSS color (hex, `rgb()`, `hsl()`, or a named color). |
| `timestamp` | `boolean` | Prepend the game time-of-day. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.now()`

Return the current game time-of-day as a `"HH:MM:SS"` string, for building your own line prefixes when you want full control over formatting.

- **Returns** String: game time-of-day as `"HH:MM:SS"`.

##### `.clear(channel="")`

Clear output produced by this script. With a `channel` argument, clears only this script's lines in that channel; with no argument, clears all output from this script. Other scripts and system messages are preserved.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Optional channel from this script to clear. Empty = every channel from this script. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

*Components / Core Systems*
