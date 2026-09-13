# Contract: three_echoes

## ThreeEchoesContract

Extends `Contract`

**Returned by:** self.contract (three_echoes)

### Related object types

- `ThreeEchoesBroadcast`

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

##### `.broadcast`

The intercepted broadcast: three frequency fragments.

- **Returns** `ThreeEchoesBroadcast`

*Types / Contracts*

---

## ThreeEchoesBroadcast

**Returned by:** .broadcast

### Properties

##### `.freq_a`

Ordered fragment containing the 1st, 4th, 7th, and later every-third characters of the original signal.

- **Returns** `string`

##### `.freq_b`

Ordered fragment containing the 2nd, 5th, 8th, and later every-third characters of the original signal.

- **Returns** `string`

##### `.freq_c`

Ordered fragment containing the 3rd, 6th, 9th, and later every-third characters of the original signal.

- **Returns** `string`

*Types / Contracts*

---
