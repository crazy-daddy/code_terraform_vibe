# Contract: core_sample

## CoreSampleContract

Extends `Contract`

**Returned by:** self.contract (core_sample)

### Related object types

- `CoreDevice`

### Properties

##### `.id`

Contract ID (used for transmitting answers).

- **Returns** `string`
- **Possible values** `"relay_hack"`, `"xenogenetics"`, `"corrupted_archive"`, `"sealed_vault"`, `"data_tablet"`, `"terminal_breach"`, `"drifting_signal"`, `"cold_boot"`, `"three_echoes"`, `"buried_five"`, `"the_loom"`, `"crosstalk"`, `"beat_the_system"`, `"core_sample"`, `"lattice"`

##### `.name`

Contract display name.

- **Returns** `string`

##### `.reward`

Credit reward for completing this contract.

- **Returns** `number`

##### `.status`

Contract status: 'available' or 'completed'.

- **Returns** `string`
- **Possible values** `"available"`, `"completed"`

##### `.cores`

The 10 damaged cores, as a list of byte lists. A byte destroyed in transit reads as None: recover it from the construction rules.

- **Returns** `list`

##### `.device`

The reconstruction device: submit your rebuilt cores to it. See CoreDevice.

- **Returns** `CoreDevice`

*Types / Contracts*

---

## CoreDevice

**Returned by:** .device

### Methods

##### `.submit(index, bytes)`

Submit a rebuilt core for whole-number slot `index` (0-9). Wrong container or element types raise `TypeError`; a fractional or out-of-range index, wrong list length, or numeric value outside the **0-255** range raises `ValueError`. A rejected submission does not lock the slot.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `number` | Whole-number core slot, 0-9 |
| `bytes` | `list` | The rebuilt core as a list of whole-number bytes in the **0-255** range |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"locked"` | success | The rebuilt core satisfies every construction rule and preserves all surviving bytes. |
| `"rejected"` | rejection | The submitted byte content is well formed but violates one or more core construction rules. |

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | CoreDevice.submit() requires a numeric index and a list containing only numeric bytes. |
| `ValueError` | CoreDevice.submit() requires a whole-number slot in the **0-9** range and a correctly sized list of whole-number bytes in the **0-255** range. |

##### `.recovered()`

How many of the 10 cores are locked in the current script run. A fresh run starts at 0.

- **Returns** `number`

##### `.target()`

The number of cores you must recover to complete the contract: 10.

- **Returns** `number`

##### `.token()`

The passcode to transmit: a non-empty string once recovered() reaches target(), otherwise an empty string.

- **Returns** `string`

*Types / Contracts*

---
