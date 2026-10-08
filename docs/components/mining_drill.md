# Component: mining_drill

> **Category:** Production & Storage | **Component Name:** Mining Drill

Mk I static drill for deposits up to hardness 1 (Iron, Silicon): 25 t/h at standard purity and 10 W while extracting.

| Field | Value |
| --- | --- |
| Type | Mining |
| Built on | Mineral sites |
| Power in | -10 W (draws from grid) |
| Stockpile | 2,000 units (mixed) |

### How to obtain

1. The recipe unlocks when you complete **Helios, Cargo Pod Run**.
2. Requires the **Basic Drone Operations** research (Terraform Index 180,000).
3. Fabricate **Mining Drill Kit** on a **Fabricator**: 3× Machine Frame, 1× Control Unit, 1× Circuit Panel, and 2 t Water.
4. Build it on a mineral site with a Pioneer's Constructor.

**Access via:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

##### `.output: PickupOutputSlot`

`PickupOutputSlot` exposing the Drill's stockpile through `count()`, `capacity()`, and `stacks()`. A physically present Rover or Pioneer pulls through its own `input`; a drone flies with `go_to_drill()` and loads with `cargo.load()`. The Drill has no direct item-routing methods.

- **Returns** `PickupOutputSlot`. Exposes stockpile reads. A physically present Rover or Pioneer pulls through its `input`; a drone uses `go_to_drill()` and `cargo.load()`.

### Methods

##### `.site() → MiningSite | None`

The `MiningSite` this drill sits on. Read `.item_id` for the mineral it extracts, and `.purity` and `.hardness` for the deposit under it. `None` when the drill stands on no mineral site.

- **Returns** `MiningSite | None`. A snapshot of the mineral site this drill sits on, or `None` when it stands on none.

##### `.drill_rate() → float`

Mineral extraction rate in t/h right now: the full rate while drilling, and **0** whenever the drill is powered off, has no deposit under it, cannot cut the deposit's hardness, or its stockpile is full. Adjusted for site purity and drill tier.

- **Returns** `float`. t/h being extracted right now, or **0** when not drilling. Accounts for site purity and drill tier.

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

*Components / Production & Storage*
