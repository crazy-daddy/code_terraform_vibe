# Contract: crosstalk

## CrosstalkContract

Extends `Contract`

**Returned by:** self.contract (crosstalk)

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

##### `.input_x`

First intercepted signal: a string of letters with 0s and 1s scattered through. Some bits are decoys.

- **Returns** `string`

##### `.input_y`

Second intercepted signal: same shape as input_x.

- **Returns** `string`

##### `.min_length`

Minimum palindrome length for a bit to count: a bit qualifies only if the letters mirror to this span centred on it.

- **Returns** `number`

*Types / Contracts*

---
