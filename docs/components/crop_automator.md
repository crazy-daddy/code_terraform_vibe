# Component: crop_automator

> **Category:** Biosphere | **Component Name:** Crop Automator

Queues harvest, plant, and treatment jobs across up to 24 other cells in a centered 5 by 5 service area, then executes one job at a time with a short pause between them. Scripts find it with `outpost.harvesting_machines()`.

| Field | Value |
| --- | --- |
| Type | Biosphere |
| Power in | -60 W (draws from grid) |
| Output buffer | 50,000 units |
| Stockpile | 400 units (mixed) |

### How to obtain

1. Requires the **Field Automation** research (Plants 620,000).
2. Buy from the Shop for 30,000 cr.
3. Deploy the kit on an empty field cell with a Harvester's `deploy()`.

**Returned by:** `self`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.input: InputSlot`

Standard multi-material `InputSlot` accepting species seeds, Fertilizer Mk I/II/III, and Growth Accelerant.

- **Returns** `InputSlot`

##### `.output: OutputSlot`

Standard `OutputSlot` containing collected Forage. Send to a local destination through this slot, or let a local Plant Terraformer pull from it through its standard input. Every route uses normal timed transfers.

- **Returns** `OutputSlot`

### Methods

##### `.harvest(sector: str) → JobReceipt` *(self only)*

Submit one harvest job for a covered sector. Submission is immediate; valid field work later takes **0.1 hours**. Missing output space pauses this FIFO head without bypassing it. A target mismatch is terminal, takes no work time, and advances the queue.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sector` | `str` | One of the cells in the automator's service area. |

- **Returns** `JobReceipt`
- **Result fields** `.status`, `.message`
- **Success payload** `.job_id`, `.queue_position`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"queued"` | success | Queued job `.job_id` at execution position `.queue_position`. |
| `"queue_full"` | transient | The Crop Automator's 50-job queue is full. |
| `"not_placed"` | rejection | The Crop Automator is not deployed on the field. |
| `"out_of_range"` | rejection | The requested sector is outside the Crop Automator's service area. |

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The sector argument is not a valid field sector id. |

##### `.plant(sector: str, seed_id: str) → JobReceipt` *(self only)*

Submit one planting job with a specific species seed. Submission is immediate and does not require the seed to be loaded yet. The serial executor pauses at this FIFO head until the seed is present, then spends **0.1 hours** and rechecks the target before committing.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sector` | `str` | One of the cells in the automator's service area. |
| `seed_id` | `str` | A species-specific seed item id. |

- **Returns** `JobReceipt`
- **Result fields** `.status`, `.message`
- **Success payload** `.job_id`, `.queue_position`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"queued"` | success | Queued job `.job_id` at execution position `.queue_position`. |
| `"queue_full"` | transient | The Crop Automator's 50-job queue is full. |
| `"not_placed"` | rejection | The Crop Automator is not deployed on the field. |
| `"out_of_range"` | rejection | The requested sector is outside the Crop Automator's service area. |
| `"invalid_seed"` | rejection | The requested item is not a species seed. |

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The sector argument is not a valid field sector id. |

##### `.apply(sector: str, item_id: str) → JobReceipt` *(self only)*

Submit one Fertilizer Mk I/II/III or Growth Accelerant job. Submission is immediate and does not require the material to be loaded yet. The serial executor pauses at this FIFO head until the material is present, then spends **0.1 hours** and rechecks the target before committing.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sector` | `str` | One of the cells in the automator's service area. |
| `item_id` | `str` | Fertilizer Mk I/II/III or Growth Accelerant. |

- **Returns** `JobReceipt`
- **Result fields** `.status`, `.message`
- **Success payload** `.job_id`, `.queue_position`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"queued"` | success | Queued job `.job_id` at execution position `.queue_position`. |
| `"queue_full"` | transient | The Crop Automator's 50-job queue is full. |
| `"not_placed"` | rejection | The Crop Automator is not deployed on the field. |
| `"out_of_range"` | rejection | The requested sector is outside the Crop Automator's service area. |
| `"invalid_material"` | rejection | The requested item is not a supported crop treatment. |

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The sector argument is not a valid field sector id. |

##### `.position() → str`

Grid sector occupied by this automator. Jobs can target up to 24 other cells in its centered 5 by 5 service area.

- **Returns** The automator's own field sector. Jobs can target up to 24 other cells in its centered 5 by 5 service area.

##### `.cell(sector: str) → Cell | None`

Read one sector inside this automator's service area as a `Cell` snapshot, covering plant, status, growth, conditions, and remaining treatment hours. The addressable set is exactly the set `harvest()`, `plant()`, and `apply()` accept, so a sector this returns `None` for is one no job can target either.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sector` | `str` | One of the cells in the automator's service area. |

- **Returns** `Cell | None`
- **None means** `None` means this automator cannot address that sector: it is outside the service area, or not a valid field sector.

*Outcomes*

| Status | Meaning |
| --- | --- |
| `None` | `None` means this automator cannot address that sector: it is outside the service area, or not a valid field sector. |

##### `.cells() → list[Cell]`

Read every sector this automator serves as a list of `Cell` snapshots, for sweeping the whole service area in one pass. Unscanned natural ground reports status `"unknown"`.

- **Returns** List of the `Cell` snapshots this automator serves, one per addressable sector. Empty while the automator is not placed on the field.

##### `.status() → str`

Exact executor state: `"not_placed"`, `"no_power"`, `"working"`, `"no_seed"`, `"no_material"`, `"output_full"`, `"results_full"`, or `"idle"`.

- **Returns** `str`
- **Possible values** `"not_placed"`, `"no_power"`, `"working"`, `"no_seed"`, `"no_material"`, `"output_full"`, `"results_full"`, `"idle"`

##### `.current_job() → CropJob | None`

Active FIFO head as a `CropJob`, including action, target, progress, and blocker. Returns `None` while idle.

- **Returns** `CropJob | None`
- **None means** `None` means the Crop Automator has no active job.

*Outcomes*

| Status | Meaning |
| --- | --- |
| `None` | `None` means the Crop Automator has no active job. |

##### `.get_queue() → list[CropJob]`

Snapshot of pending `CropJob` values in exact FIFO order (first in, first out). The active job is reported separately by `current_job()`.

- **Returns** `list[CropJob]`

##### `.queue_count() → int`

Total unfinished jobs, counting the active job and every pending job. Maximum **50**.

- **Returns** `int`

##### `.result_count() → int`

Completed terminal results waiting in the result inbox. At **50**, execution pauses until results are consumed.

- **Returns** `int`

##### `.next_result() → CropJobResult` *(self only)*

Consume the oldest terminal result. An empty inbox is reported without changing machine state.

- **Returns** `CropJobResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.job_id`, `.action`, `.sector`, `.item_id`, `.collected`, `.discarded`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Job `.job_id` completed at `.sector`; the world mutation committed successfully. |
| `"partial"` | partial | Job `.job_id` harvested `.sector` but the output bin only had room for `.collected` Forage; `.discarded` was discarded and the cell was cleared. |
| `"empty"` | success | No completed Crop Automator result is waiting. |
| `"out_of_range"` | rejection | The target left this Crop Automator's service area before execution. |
| `"no_plant"` | rejection | The target sector held no plant when the job reached the executor. |
| `"not_mature"` | rejection | The target plant was not mature when the harvest job reached the executor. |
| `"no_forage"` | rejection | The ready crop held no whole Forage when the harvest job reached the executor. |
| `"not_empty"` | rejection | The target sector was not empty when the planting job reached the executor. |
| `"base_sector"` | rejection | The Harvester base sector cannot be planted. |
| `"already_mature"` | rejection | The target plant was already mature when the treatment job reached the executor. |
| `"tier_conflict"` | rejection | The requested Fertilizer tier conflicted with the active dose on the target plant. |
| `"invalid_seed"` | rejection | The planting job referred to an invalid species seed. |
| `"invalid_material"` | rejection | The treatment job referred to an unsupported material. |

##### `.cancel_job(job_id: int) → ActionResult` *(self only)*

Cancel one active or pending job by id. Canceling active work discards only its progress; inputs and field state remain unchanged.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `job_id` | `int` | Job id returned by harvest(), plant(), or apply(). |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |

##### `.move_job(job_id: int, position: int) → ActionResult` *(self only)*

Move one unfinished job to a one-based execution position, counting the active job first and then pending jobs. Reordering only pending work preserves active progress. While a job is active, changing which job is first preempts the arm: the displaced job keeps its id and request, loses its progress, and creates no terminal result. Position **1** is first; `queue_count()` is the last position.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `job_id` | `int` | Stable id of an active or pending job. |
| `position` | `int` | One-based execution position across the active and pending jobs. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The unfinished job now occupies the requested execution position. |
| `"not_found"` | rejection | No active or pending job has the supplied id. |
| `"invalid"` | rejection | The supplied position is outside the one-based range from **1** through `queue_count()`. |

##### `.clear_queue() → CountResult` *(self only)*

Cancel the active job and every pending job. Completed results remain available through `next_result()`.

- **Returns** `CountResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.count`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The command affected `.count` entries or units. |
| `"no_op"` | success | The command affected no entries or units. |

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Biosphere*
