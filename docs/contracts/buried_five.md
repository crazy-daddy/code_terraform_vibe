# Contract: buried_five

## BuriedFiveContract

Extends `Contract`

**Returned by:** self.contract (buried_five)

### Related object types

- `Analyzer`

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

##### `.transmission`

The scrambled transmission: a list of single-character tokens.

- **Returns** `list<string>`

##### `.analyzer`

The recovered analyzer device: collapses a group of five tokens into the single token they were expanded from.

- **Returns** `Analyzer`

##### `.layers`

Whole-number count of five-fold wrapping layers applied to the transmission.

- **Returns** `number`

*Types / Contracts*

---

## Analyzer

**Returned by:** .analyzer

### Methods

##### `.read(group)`

Read a list of exactly five string tokens and return the single token they were expanded from. A non-list argument or non-string element raises `TypeError`; the wrong length or an unrecognized group raises `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `group` | `list` | Five-string-token group to collapse |

- **Returns** `string`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | Analyzer.read() requires a list containing only string tokens. |
| `ValueError` | Analyzer.read() requires exactly five tokens forming a recognized aligned group. |

*Types / Contracts*

---
