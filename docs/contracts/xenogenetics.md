# Contract: xenogenetics

## XenogeneticsContract

Extends `Contract`

**Returned by:** self.contract (xenogenetics)

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

##### `.earth_ref: list[str]`

50 known Earth gene sequences (list of strings).

- **Returns** `list[str]`

##### `.samples: list[str]`

1000 collected DNA samples (list of strings).

- **Returns** `list[str]`

*Types / Contracts*
