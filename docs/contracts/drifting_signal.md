# Contract: drifting_signal

## DriftingSignalContract

Extends `Contract`

**Returned by:** self.contract (drifting_signal)

### Related object types

- `SlabDevice`

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

##### `.device`

The recovered slab contraption.

- **Returns** `SlabDevice`

*Types / Contracts*

---

## SlabDevice

**Returned by:** .device

### Properties

##### `.slabs`

Current state of the letter slabs. Uppercase letters, spaces preserved.

- **Returns** `string`

*Types / Contracts*

---
