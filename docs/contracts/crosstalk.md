# Contract: crosstalk

## CrosstalkContract

Extends `Contract`

**Returned by:** self.contract (crosstalk)

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

##### `.input_x: str`

First intercepted signal: a string of letters with 0s and 1s scattered through. Some bits are decoys.

- **Returns** `str`

##### `.input_y: str`

Second intercepted signal: same shape as input_x.

- **Returns** `str`

##### `.min_length: int`

Minimum palindrome length for a bit to count: a bit qualifies only if the letters mirror to this span centred on it.

- **Returns** `int`

*Types / Contracts*
