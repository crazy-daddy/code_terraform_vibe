# Contract: the_loom

## TheLoomContract

Extends `Contract`

**Returned by:** self.contract (the_loom)

### Related object types

- `Loom`

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

##### `.loom: Loom`

The recovered alien loom, your probe tool. Call `loom.weave(a, b)` to learn how it braids two strings into one.

- **Returns** `Loom`

##### `.record: str`

A 42-character woven record made from two equal-length 21-character threads. Reverse the loom's rule to un-weave it; one thread is the message.

- **Returns** `str`

*Types / Contracts*

## Loom

**Returned by:** .loom

### Methods

##### `.weave(a: str, b: str) → str`

Braid two strings into one and return it. Each character is one token. Deterministic: the same inputs always weave the same way, so probe it freely. A non-string argument raises `TypeError`; either input longer than 30 characters raises `ValueError`. The loom only weaves forward; build the reverse yourself.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `str` | First input string |
| `b` | `str` | Second input string |

- **Returns** `str`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | Loom.weave() requires two strings. |
| `ValueError` | Loom.weave() accepts at most 30 characters in each input. |

*Types / Contracts*
