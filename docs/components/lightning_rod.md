# Component: lightning_rod

> **Category:** Power | **Component Name:** Lightning Rod

A **4,000 Wh** emergency reserve that catches lightning within **600 m** and discharges behind batteries. Condition falls **0.05 per day**, reducing capture to zero unless a running script repairs it with **1 Storm Glass**.

| Field | Value |
| --- | --- |
| Type | Power |
| Energy | 4,000 Wh |
| Input buffer | 5 units |

### How to obtain

1. The recipe unlocks with the **Lightning Rods** research (Temperature 8,000).
2. Fabricate a **Lightning Rod** on a **Fabricator**: 1× Machine Frame, 4× Battery Cell, and 2× Circuit Panel.
3. Deploy it from your Inventory.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.outpost`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef` for the outpost where this building is deployed.

##### `.input`

The rod's material slot. Feed it Storm Glass with your ordinary logistics, then spend one with `repair()` to restore full condition.

- **Returns** `InputSlot`: `connect()`, `take()`, `eject()`, `flush()`, `count()`, `capacity()`, `connected_to()`. Holds the Storm Glass that `repair()` spends.

### Methods

##### `.bank()`

Wh currently banked, **0** up to `capacity()`. Rises only when a strike lands within catch range of this rod; falls automatically when its grid is short and the batteries are empty. It never charges from grid surplus.

- **Returns** Number: Wh currently banked, **0** up to `capacity()`. Fills only when a thunderstorm strike lands within catch range of this rod; drains automatically when its grid runs short and the batteries are empty. Never charges from grid surplus.

##### `.capacity()`

Bank capacity in Wh, several times a base battery. Query this instead of hardcoding the number.

- **Returns** Number: bank capacity in Wh.

##### `.last_strike()`

Hour timestamp of the last strike from which this rod accepted energy, or **-1** if none. A strike that adds no energy, for example when the bank is full or integrity is zero, does not update this record. Compare with the clock's current time to see how long it has been since energy was last captured.

- **Returns** Number: hour timestamp of the last strike from which this rod accepted energy, or **-1** if none. A strike that adds no energy, for example when the bank is full or integrity is zero, does not update this record.

##### `.integrity()`

This rod's condition from **0** to **1**, which is also its capture efficiency. Continuous corrosion lowers it by **0.05 per day**; strikes do not cause separate damage. A rod at **0.5** banks half of every strike it catches, and one at **0** banks nothing while still standing and still repairable.

- **Returns** Number (**0-1**): this rod's condition, which is also its capture efficiency. A rod at **0.5** banks half of every strike it catches; at **0** it banks nothing and still stands.

##### `.repair()` *(self only)*

Restore this rod to full condition. If it is worn, one call consumes **1 Storm Glass** from its input and sets condition to **1**. At full condition, no material is consumed. Without Storm Glass in the input, condition does not change.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"no_op"` | rejection | The operation was already satisfied, so no state changed and nothing was consumed. |
| `"no_material"` | rejection | The required quantity of material is not available in the machine's input. |

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Power*
