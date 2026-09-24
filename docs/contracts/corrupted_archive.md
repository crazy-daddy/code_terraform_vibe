# Contract: corrupted_archive

## CorruptedArchiveContract

Extends `Contract`

**Returned by:** self.contract (corrupted_archive)

### Related object types

- `Archive`

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

##### `.archive: Archive`

The scrambled data archive.

- **Returns** `Archive`

*Types / Contracts*

## Archive

**Returned by:** .archive

### Properties

##### `.rows: int`

Number of rows in the grid.

- **Returns** `int`

##### `.cols: int`

Number of columns in the grid.

- **Returns** `int`

### Methods

##### `.flip(row: int, col: int) → str`

Reveal and return the word at a whole-number grid cell. Wrong argument types raise `TypeError`; fractional, non-finite, or out-of-bounds coordinates raise `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `row` | `int` | Whole-number grid row, 0 to rows - 1 |
| `col` | `int` | Whole-number grid column, 0 to cols - 1 |

- **Returns** `str`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | Archive.flip() requires numeric row and column coordinates. |
| `ValueError` | Archive.flip() requires finite whole-number coordinates inside the archive grid. |

*Types / Contracts*
