# Contract: data_tablet

## DataTabletContract

Extends `Contract`

**Returned by:** self.contract (data_tablet)

### Related object types

- `DataTablet`

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

##### `.tablet: DataTablet`

The data tablet scanner.

- **Returns** `DataTablet`

*Types / Contracts*

## DataTablet

**Returned by:** .tablet

### Related object types

- `ProbeResult`

### Properties

##### `.rows: int`

Number of rows in the grid.

- **Returns** `int`

##### `.cols: int`

Number of columns in the grid.

- **Returns** `int`

### Methods

##### `.probe(row: int, col: int) → ProbeResult`

Probe a whole-number cell and return a `ProbeResult` with `.char` and whole-number `.distance`. Wrong argument types raise `TypeError`; fractional or out-of-bounds coordinates raise `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `row` | `int` | Whole-number grid row, 0 to rows - 1 |
| `col` | `int` | Whole-number grid column, 0 to cols - 1 |

- **Returns** `ProbeResult`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | The contract probe received an argument or element of the wrong type. |
| `ValueError` | The contract probe received a value, shape, or coordinate outside its documented domain. |

*Types / Contracts*

## ProbeResult

**Returned by:** tablet.probe()

### Properties

##### `.char: str`

Character at this cell.

- **Returns** `str`

##### `.distance: int`

Whole-number Manhattan distance (steps) to the nearest message cell. 0 means this cell IS a message cell.

- **Returns** `int`

*Types / Contracts*
