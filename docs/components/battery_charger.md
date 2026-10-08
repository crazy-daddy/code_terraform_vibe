# Component: battery_charger

> **Category:** Power | **Component Name:** Battery Charger

Charges loose **Portable Batteries (50 Wh)** and **Heavy Portable Batteries (100 Wh)** from the local grid. Mk I has **4 shared slots**, **1 charging bay**, and a **30 W** budget. Place at Base or a founded outpost. Park a Pioneer in its service area for a timed battery exchange. Charging is script-controlled; idle draw is 0 W.

| Field | Value |
| --- | --- |
| Type | Mining |
| Tiers | Mk II |

### How to obtain

1. Requires the **Battery Charger** research (Oxygen 25).
2. Buy from the Shop for 1,500 cr.

**Access via:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

##### `.outpost: OutpostRef`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef`. The outpost where this building is deployed.

##### `.input: InputSlot`

Standard local input port. Both ports share the physical socket store. Only portable vehicle batteries are accepted. `eject()` recovers unqueued cells; `flush()` discards unqueued cells permanently.

- **Returns** `InputSlot`

##### `.output: OutputSlot`

Standard local output port. Only unqueued cells can be sent or pulled out. Item properties and stored charge are preserved.

- **Returns** `OutputSlot`

### Methods

##### `.slots() → list[BatteryChargerSlot]`

Read snapshots of every physical socket. Waiting, charging, and ready cells share the same capacity.

- **Returns** `list[BatteryChargerSlot]`

##### `.status(slot_index: int) → BatteryChargerSlot`

Read one socket snapshot. Raises `ValueError` for an out-of-range index.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `slot_index` | `int` | Zero-based physical socket index, from 0 to the slot count minus one. |

- **Returns** `BatteryChargerSlot`

##### `.charge(slot_index: int, target_level: float = 1.0) → ActionResult` *(self only)*

Queue this exact cell to a target charge fraction. Repeating the call updates its existing target without duplicating or reordering the job. Completed jobs release their socket automatically. Power loss pauses work. Removing or swapping the cell never transfers its job to its replacement.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `slot_index` | `int` | Zero-based physical socket index, from 0 to the slot count minus one. |
| `target_level` | `float` | Required charge fraction greater than 0 and at most 1; defaults to 1.0. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"queued"` | success | The battery has an unfinished charging job. |
| `"target_reached"` | success | The cell already meets the requested target. |
| `"empty"` | rejection | The socket contains no battery. |
| `"under_construction"` | rejection | Construction is not complete. |

##### `.stop(slot_index: int) → ActionResult` *(self only)*

Cancel this socket's charging job and release the cell, preserving all stored charge.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `slot_index` | `int` | Zero-based physical socket index, from 0 to the slot count minus one. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed. |
| `"no_op"` | success | No changes were needed. |

##### `.clear_queue() → CountResult` *(self only)*

Cancel all charging jobs, retain all cells and their stored charge, and return the number canceled.

- **Returns** `CountResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.count`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Command completed. Affected entries or units: `.count`. |
| `"no_op"` | success | The command affected no entries or units. |

##### `.get_queue() → list[int]`

Read ordered unfinished socket indices, including active jobs.

- **Returns** `list[int]`

##### `.get_active() → list[int]`

Read the socket indices receiving power now. Empty during an outage or battery handling.

- **Returns** `list[int]`

##### `.tier() → int`

Read the installed tier (1 or 2).

- **Returns** `int`

##### `.get_slot_count() → int`

Read the shared physical storage capacity: 4 at Mk I or 8 at Mk II.

- **Returns** `int`

##### `.get_bay_count() → int`

Read simultaneous charging capacity: 1 at Mk I or 2 at Mk II.

- **Returns** `int`

##### `.get_bay_rate() → float`

Read the nominal power per bay in watts. Idle bay power is pooled among active cells.

- **Returns** `float`

##### `.get_charge_rate(slot_index: int) → float`

Read this socket's actual charging watts, including pooling and overcrowding. Zero when inactive.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `slot_index` | `int` | Zero-based physical socket index, from 0 to the slot count minus one. |

- **Returns** `float`

##### `.set_status(message: str, level: str = "info") → None` *(self only)*

Show a status message for this machine's current script run. Use `self.set_status(message, "info")`. The same reporting capability is available as `set_status()` in every script. Messages follow the current execution, independently of machine state and game warnings.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `str` | Non-empty plain text, at most 240 characters. Null characters are not accepted. |
| `level` | `str` | Presentation severity: `info`, `warn`, or `error`. Defaults to `info`. |

- **Returns** `None`. `None`.

##### `.clear_status() → None` *(self only)*

Clear the current script run's status message. Clearing an absent message has no effect. Does not wait or change machine behaviour.

- **Returns** `None`. `None`.

##### `.get_status_report() → ScriptStatusReport | None`

Read this machine's script status report from any script. Returns `None` when it has no report. The returned snapshot includes `message`, `level`, `active`, and `run_id`.

- **Returns** `ScriptStatusReport | None`. Read this machine's script status report from any script. Returns `None` when it has no report. The returned snapshot includes `message`, `level`, `active`, and `run_id`.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

```python
while True:
    for cell in self.slots():
        if cell.item_id and cell.level < 1.0 and cell.target is None:
            result = self.charge(cell.index)
            if result.status != "queued":
                print(result.message)
    sleep(1)
```

*Components / Power*
