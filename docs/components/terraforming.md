# Component: terraforming

> **Category:** Terraforming | **Component Name:** Terraforming

Read progress, completion targets, and milestones for the six terraforming pillars through `get_component("terraforming")`. The Terraform Index combines their capped contributions toward a fixed 1,000,000 TP goal.

**Access via:** `get_component("terraforming")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

### Methods

##### `.pillars() → list[TerraformPillar]`

Read fresh snapshots of the available pillars in order: temperature, oxygen, pressure, then biomass, plants, and wildlife. The three Biosphere pillars appear together after Biosphere research. Call again to read updated progress.

- **Returns** `list[TerraformPillar]`. Fresh `TerraformPillar` snapshots for the unlocked pillars.

##### `.get_pillar(pillar_id: str) → TerraformPillar | None`

Read a fresh snapshot of one pillar, for example `terraforming.get_pillar("biomass")`. Returns `None` only when that pillar is locked by Biosphere research. Unknown ids raise `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pillar_id` | `str` | One of `"temperature"`, `"oxygen"`, `"pressure"`, `"biomass"`, `"plants"`, or `"wildlife"`. |

- **Returns** `TerraformPillar | None`. A fresh `TerraformPillar` snapshot, or `None` for a pillar locked by Biosphere research.

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The supplied `pillar_id` is not one of the six terraforming pillar ids. |

##### `.index_progress() → float`

Read the overall Terraform Index percentage toward its fixed 1,000,000 TP goal. Atmosphere accounts for 70% and Biosphere for 30%; unlocking Biosphere does not change the goal.

- **Returns** `float`. Terraform Index percentage on a **0-100** scale, with a fixed 1,000,000 TP goal.

##### `.total_tp() → int`

Read the Terraform Index in whole TP, capped at 1,000,000. Completing one pillar cannot replace progress in another.

- **Returns** `int`. Whole Terraform Index points in the **0-1,000,000** range.

*Components / Production & Storage*
