# Contract: relay_hack

## RelayHackContract

Extends `Contract`

**Returned by:** self.contract (relay_hack)

### Related object types

- `RelayLock`

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

##### `.lock: RelayLock`

The relay lock to crack.

- **Returns** `RelayLock`

*Types / Contracts*

## RelayLock

**Returned by:** .lock

### Properties

##### `.tumblers: int`

Number of tumblers (6).

- **Returns** `int`

##### `.range: int`

Range per tumbler (100 = 0-99).

- **Returns** `int`

### Methods

##### `.intercept(code: list[int]) → list[bool]`

Test a list of exactly 6 whole-number values in the **0-99** range and return one True/False value per tumbler. Wrong argument types raise `TypeError`; wrong list length, non-finite or fractional values, and values outside the range raise `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `code` | `list[int]` | Candidate list of 6 whole numbers, each 0-99 |

- **Returns** `list[bool]`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | The contract probe received an argument or element of the wrong type. |
| `ValueError` | The contract probe received a value, shape, or coordinate outside its documented domain. |

*Types / Contracts*
