# Contract: lattice

## LatticeContract

Extends `Contract`

**Returned by:** self.contract (lattice)

### Related object types

- `LatticeGrid`

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

##### `.grid: LatticeGrid`

The alien deep-scan lattice. Probe only proven-clear cells to map the volatile nodes; a trip blocks further probes until the grid is reset. See LatticeGrid.

- **Returns** `LatticeGrid`

*Types / Contracts*

## LatticeGrid

**Returned by:** .grid

### Methods

##### `.width() → int`

The grid width in cells (32).

- **Returns** `int`

##### `.height() → int`

The grid height in cells (32).

- **Returns** `int`

##### `.start() → list[int]`

A guaranteed-clear foothold cell, returned as `[x, y]`. Probe it first to get a reading and begin the deduction.

- **Returns** `list[int]`

##### `.reset() → ActionResult`

Clear a tripped fault so probing can continue in the same script run. The hidden board and guaranteed-clear starting cell do not change.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The lattice fault was cleared. The hidden board and starting cell are unchanged. |

##### `.probe(x: int, y: int) → LatticeProbeResult`

Probe a proven clear whole-number cell. The reading is the whole-number count of neighboring volatile nodes in the **0-8** range. Tripping a node faults the lattice until `reset()` is called. Wrong argument types raise `TypeError`; fractional, non-finite, or out-of-bounds coordinates raise `ValueError` without tripping an intact lattice.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `int` | Whole-number column, 0-31 |
| `y` | `int` | Whole-number row, 0-31 |

- **Returns** `LatticeProbeResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.reading`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Neighboring volatile nodes in the clear cell: `.reading`. |
| `"node_tripped"` | rejection | The probed cell contained a volatile node and faulted the lattice. |
| `"lattice_tripped"` | rejection | An earlier volatile-node probe faulted the lattice. |

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | LatticeGrid.probe() requires numeric x and y coordinates. |
| `ValueError` | LatticeGrid.probe() requires finite whole-number coordinates inside the 32 by 32 grid. |

*Types / Contracts*

## LatticeProbeResult

**Returned by:** LatticeGrid.probe()

### Properties

##### `.status: str`

`"ok"`, `"node_tripped"`, or `"lattice_tripped"`.

- **Returns** `str`
- **Possible values** `"ok"`, `"node_tripped"`, `"lattice_tripped"`

##### `.message: str`

Player-readable explanation of the probe outcome.

- **Returns** `str`

##### `.reading: int | None`

Whole-number neighboring-node count in the **0-8** range when `.status == "ok"`; otherwise `None`.

- **Returns** `int | None`

*Types / Contracts*
