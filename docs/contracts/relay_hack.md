# Contract: relay_hack

## RelayHackContract

Extends `Contract`

**Returned by:** self.contract (relay_hack)

### Related object types

- `RelayLock`

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

##### `.lock`

The relay lock to crack.

- **Returns** `RelayLock`

*Types / Contracts*

---

## RelayLock

**Returned by:** .lock

### Properties

##### `.tumblers`

Number of tumblers (6).

- **Returns** `number`

##### `.range`

Range per tumbler (100 = 0-99).

- **Returns** `number`

### Methods

##### `.intercept(code)`

Test a list of exactly 6 whole-number values in the **0-99** range and return one True/False value per tumbler. Wrong argument types raise `TypeError`; wrong list length, non-finite or fractional values, and values outside the range raise `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `code` | `list` | Candidate list of 6 whole numbers, each 0-99 |

- **Returns** `list[boolean]`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | The contract probe received an argument or element of the wrong type. |
| `ValueError` | The contract probe received a value, shape, or coordinate outside its documented domain. |

*Types / Contracts*

---
