# Contract: xenogenetics

## XenogeneticsContract

Extends `Contract`

**Returned by:** self.contract (xenogenetics)

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

##### `.earth_ref`

50 known Earth gene sequences (list of strings).

- **Returns** `list<string>`

##### `.samples`

1000 collected DNA samples (list of strings).

- **Returns** `list<string>`

*Types / Contracts*

---
