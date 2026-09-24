# Contract: buried_five

## BuriedFiveContract

Extends `Contract`

**Returned by:** self.contract (buried_five)

### Related object types

- `Analyzer`

### Properties

##### `.id: str`

Contract ID (used for transmitting answers).

- **Returns** `str`
- **Possible values** `"relay_hack"`, `"xenogenetics"`, `"corrupted_archive"`, `"sealed_vault"`, `"data_tablet"`, `"terminal_breach"`, `"drifting_signal"`, `"cold_boot"`, `"three_echoes"`, `"buried_five"`, `"the_loom"`, `"crosstalk"`, `"beat_the_system"`, `"core_sample"`, `"lattice"`

##### `.name: str`

Contract display name.

- **Returns** `str`

##### `.reward: int`

Credit reward for completing this contract.

- **Returns** `int`

##### `.status: str`

Contract status: 'available' or 'completed'.

- **Returns** `str`
- **Possible values** `"available"`, `"completed"`

##### `.transmission: list[str]`

The scrambled transmission: a list of single-character tokens.

- **Returns** `list[str]`

##### `.analyzer: Analyzer`

The recovered analyzer device: collapses a group of five tokens into the single token they were expanded from.

- **Returns** `Analyzer`

##### `.layers: int`

Whole-number count of five-fold wrapping layers applied to the transmission.

- **Returns** `int`

*Types / Contracts*

## Analyzer

**Returned by:** .analyzer

### Methods

##### `.read(group: list[str]) → str`

Read a list of exactly five string tokens and return the single token they were expanded from. A non-list argument or non-string element raises `TypeError`; the wrong length or an unrecognized group raises `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `group` | `list[str]` | Five-string-token group to collapse |

- **Returns** `str`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | Analyzer.read() requires a list containing only string tokens. |
| `ValueError` | Analyzer.read() requires exactly five tokens forming a recognized aligned group. |

*Types / Contracts*
