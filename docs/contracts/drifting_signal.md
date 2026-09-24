# Contract: drifting_signal

## DriftingSignalContract

Extends `Contract`

**Returned by:** self.contract (drifting_signal)

### Related object types

- `SlabDevice`

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

##### `.device: SlabDevice`

The recovered slab contraption.

- **Returns** `SlabDevice`

*Types / Contracts*

## SlabDevice

**Returned by:** .device

### Properties

##### `.slabs: str`

Current state of the letter slabs. Uppercase letters, spaces preserved.

- **Returns** `str`

*Types / Contracts*
