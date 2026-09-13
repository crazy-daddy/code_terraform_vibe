# Contract: data_tablet

## DataTabletContract

Extends `Contract`

**Returned by:** self.contract (data_tablet)

### Related object types

- `DataTablet`

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

##### `.tablet`

The data tablet scanner.

- **Returns** `DataTablet`

*Types / Contracts*

---

## DataTablet

**Returned by:** .tablet

### Related object types

- `ProbeResult`

### Properties

##### `.rows`

Number of rows in the grid.

- **Returns** `number`

##### `.cols`

Number of columns in the grid.

- **Returns** `number`

### Methods

##### `.probe(row, col)`

Probe a whole-number cell and return a `ProbeResult` with `.char` and whole-number `.distance`. Wrong argument types raise `TypeError`; fractional or out-of-bounds coordinates raise `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `row` | `number` | Whole-number grid row, 0 to rows - 1 |
| `col` | `number` | Whole-number grid column, 0 to cols - 1 |

- **Returns** `ProbeResult`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | The contract probe received an argument or element of the wrong type. |
| `ValueError` | The contract probe received a value, shape, or coordinate outside its documented domain. |

*Types / Contracts*

---

## ProbeResult

**Returned by:** tablet.probe()

### Properties

##### `.char`

Character at this cell.

- **Returns** `string`

##### `.distance`

Whole-number Manhattan distance (steps) to the nearest message cell. 0 means this cell IS a message cell.

- **Returns** `number`

*Types / Contracts*

---
