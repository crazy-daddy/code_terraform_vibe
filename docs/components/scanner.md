# Component: scanner

> **Category:** Exploration | **Component Name:** Scanner

Reveals the sectors of the Harvester grid around base so the Harvester knows where to collect. It maps the home grid only; exploring the wider planet is a job for a vehicle's sonar.

| Field | Value |
| --- | --- |
| Type | Harvesting |

**Returned by:** `get_component("scanner_1")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.scan(sector: str) → ScanResult` *(self only)*

Scan one local sector with `self.scan("E14")`. The scan takes a few ticks and pauses the script. Malformed or out-of-bounds sector ids raise `ValueError`. This local-grid scanner finds surface items, not planetary `Site` contacts.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sector` | `str` | Local grid sector id (e.g. `"E14"`). |

- **Returns** `ScanResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.id`, `.name`, `.value`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The sector scan found `item_id`. |
| `"empty"` | success | The sector scan completed and found no item. |

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The sector argument is not a valid local grid sector id. |

##### `.get_scanned() → dict[str, ScanResult]`

Every previously scanned sector as a fresh dict `{sector_id: ScanResult}`. Iterate with `.keys()` / `.values()` / `.items()`, or index by sector id: `self.get_scanned()["E14"]`. A sector only needs to be physically scanned once, and that history persists across script runs. Each `get_scanned()` call reflects the current contents of those sectors, including items collected or dropped since the last call. A dict or `ScanResult` already saved in your script does not update itself, so call `get_scanned()` again before choosing another target. Returns an empty dict if nothing has been scanned yet.

- **Returns** A dict (sector ID → ScanResult)

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Power*
