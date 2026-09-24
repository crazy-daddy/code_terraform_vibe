# Data Types: Contracts

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`Contract`](#contract) (CONTRACTS)
- [`BeatTheSystemContract`](#beatthesystemcontract) (CONTRACTS)
- [`Arbiter`](#arbiter) (CONTRACTS)
- [`BuriedFiveContract`](#buriedfivecontract) (CONTRACTS)
- [`Analyzer`](#analyzer) (CONTRACTS)
- [`ColdBootContract`](#coldbootcontract) (CONTRACTS)
- [`CoreSampleContract`](#coresamplecontract) (CONTRACTS)
- [`CoreDevice`](#coredevice) (CONTRACTS)
- [`CorruptedArchiveContract`](#corruptedarchivecontract) (CONTRACTS)
- [`Archive`](#archive) (CONTRACTS)
- [`CrosstalkContract`](#crosstalkcontract) (CONTRACTS)
- [`DataTabletContract`](#datatabletcontract) (CONTRACTS)
- [`DataTablet`](#datatablet) (CONTRACTS)
- [`ProbeResult`](#proberesult) (CONTRACTS)
- [`DriftingSignalContract`](#driftingsignalcontract) (CONTRACTS)
- [`SlabDevice`](#slabdevice) (CONTRACTS)
- [`LatticeContract`](#latticecontract) (CONTRACTS)
- [`LatticeGrid`](#latticegrid) (CONTRACTS)
- [`RelayHackContract`](#relayhackcontract) (CONTRACTS)
- [`RelayLock`](#relaylock) (CONTRACTS)
- [`SealedVaultContract`](#sealedvaultcontract) (CONTRACTS)
- [`Vault`](#vault) (CONTRACTS)
- [`VaultPosition`](#vaultposition) (CONTRACTS)
- [`TerminalBreachContract`](#terminalbreachcontract) (CONTRACTS)
- [`AlienTerminal`](#alienterminal) (CONTRACTS)
- [`GuessResult`](#guessresult) (CONTRACTS)
- [`TheLoomContract`](#theloomcontract) (CONTRACTS)
- [`Loom`](#loom) (CONTRACTS)
- [`ThreeEchoesContract`](#threeechoescontract) (CONTRACTS)
- [`ThreeEchoesBroadcast`](#threeechoesbroadcast) (CONTRACTS)
- [`XenogeneticsContract`](#xenogeneticscontract) (CONTRACTS)
- [`ContractScript`](#contractscript) (CONTRACTS)
- [`LatticeProbeResult`](#latticeproberesult) (CONTRACTS)
- [`VaultEscapeResult`](#vaultescaperesult) (CONTRACTS)

---

## Contract

**Returned by:** self.contract

### Concrete subtypes

- `BeatTheSystemContract`
- `BuriedFiveContract`
- `ColdBootContract`
- `CoreSampleContract`
- `CorruptedArchiveContract`
- `CrosstalkContract`
- `DataTabletContract`
- `DriftingSignalContract`
- `LatticeContract`
- `RelayHackContract`
- `SealedVaultContract`
- `TerminalBreachContract`
- `TheLoomContract`
- `ThreeEchoesContract`
- `XenogeneticsContract`

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

*Types / Contracts*

## BeatTheSystemContract

Extends `Contract`

**Returned by:** self.contract (beat_the_system)

### Related object types

- `Arbiter`

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

##### `.arbiter: Arbiter`

The alien Arbiter. It takes an immediate win, otherwise blocks your immediate win, otherwise prefers centre, then corners, then edges; tied choices are random.

- **Returns** `Arbiter`

*Types / Contracts*

## Arbiter

**Returned by:** .arbiter

### Methods

##### `.new_game() → ActionResult`

Start a fresh 3×3 game on an empty board; you move first. After a finished game this call pauses about half a second before the next board is ready.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"in_progress"` | transient | The operation is still in progress. |

##### `.restart() → ActionResult`

Abandon any game in progress and start fresh; you move first. Abandoning a game mid-play counts as a non-win and resets your current-run streak to 0. Like new_game(), it pauses about half a second between games.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.play(cell: int) → ActionResult`

Place your mark in a whole-number cell in the **0-8** range (row-major), then the Arbiter responds. Three marks in a row, column, or diagonal wins. A non-number cell raises `TypeError`; a non-finite, fractional, or out-of-range cell raises `ValueError` before game state is considered.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `cell` | `int` | Whole-number board cell to mark, 0-8 |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ongoing"` | success | The game remains in progress. |
| `"win"` | success | The game ended in a win. |
| `"loss"` | success | The game ended in a loss. |
| `"draw"` | success | The game ended in a draw. |
| `"occupied"` | rejection | The requested cell, sector, or Habitat is already occupied. |
| `"no_game"` | rejection | There is no active game. |

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | Arbiter.play() requires a numeric cell. |
| `ValueError` | Arbiter.play() requires a finite whole-number cell in the **0-8** range. |

##### `.board() → list[str]`

The 9 board cells as a list, index 0-8 row-major. Each cell is "" (empty), "you", or "arbiter".

- **Returns** `list[str]`

##### `.result() → str`

Current game outcome: "ongoing", "win", "loss", "draw", or "no_game" (no game started yet).

- **Returns** `str`
- **Possible values** `"ongoing"`, `"win"`, `"loss"`, `"draw"`, `"no_game"`

##### `.streak() → int`

Consecutive wins in the current script run. Resets to 0 on a loss, draw, abandonment, or fresh script run.

- **Returns** `int`

##### `.target() → int`

The consecutive-win count needed to complete the contract.

- **Returns** `int`

##### `.token() → str`

The passcode to transmit: a non-empty string once streak() reaches target(), otherwise an empty string.

- **Returns** `str`

*Types / Contracts*

## BuriedFiveContract

Extends `Contract`

**Returned by:** self.contract (buried_five)

### Related object types

- `Analyzer`

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

##### `.transmission: list[str]`

The scrambled transmission: a list of single-character tokens.

- **Returns** `list[str]`

##### `.analyzer: Analyzer`

The recovered analyzer device: collapses a group of five tokens into the single token they were expanded from.

- **Returns** `Analyzer`

##### `.layers: int`

Whole-number count of five-fold wrapping layers applied to the transmission.

- **Returns** `int`

*Types / Contracts*

## Analyzer

**Returned by:** .analyzer

### Methods

##### `.read(group: list[str]) → str`

Read a list of exactly five string tokens and return the single token they were expanded from. A non-list argument or non-string element raises `TypeError`; the wrong length or an unrecognized group raises `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `group` | `list[str]` | Five-string-token group to collapse |

- **Returns** `str`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | Analyzer.read() requires a list containing only string tokens. |
| `ValueError` | Analyzer.read() requires exactly five tokens forming a recognized aligned group. |

*Types / Contracts*

## ColdBootContract

Extends `Contract`

**Returned by:** self.contract (cold_boot)

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

##### `.program: list[int]`

The artifact's bytecode: a list of whole numbers. Copy it before running: `memory = list(program)`.

- **Returns** `list[int]`

*Types / Contracts*

## CoreSampleContract

Extends `Contract`

**Returned by:** self.contract (core_sample)

### Related object types

- `CoreDevice`

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

##### `.cores: list[list[int | None]]`

The 10 damaged cores, as a list of byte lists. A byte destroyed in transit reads as None: recover it from the construction rules.

- **Returns** `list[list[int | None]]`

##### `.device: CoreDevice`

The reconstruction device: submit your rebuilt cores to it. See CoreDevice.

- **Returns** `CoreDevice`

*Types / Contracts*

## CoreDevice

**Returned by:** .device

### Methods

##### `.submit(index: int, bytes: list[int]) → ActionResult`

Submit a rebuilt core for whole-number slot `index` (0-9). Wrong container or element types raise `TypeError`; a fractional or out-of-range index, wrong list length, or numeric value outside the **0-255** range raises `ValueError`. A rejected submission does not lock the slot.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `int` | Whole-number core slot, 0-9 |
| `bytes` | `list[int]` | The rebuilt core as a list of whole-number bytes in the **0-255** range |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"locked"` | success | The rebuilt core satisfies every construction rule and preserves all surviving bytes. |
| `"rejected"` | rejection | The submitted byte content is well formed but violates one or more core construction rules. |

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | CoreDevice.submit() requires a numeric index and a list containing only numeric bytes. |
| `ValueError` | CoreDevice.submit() requires a whole-number slot in the **0-9** range and a correctly sized list of whole-number bytes in the **0-255** range. |

##### `.recovered() → int`

How many of the 10 cores are locked in the current script run. A fresh run starts at 0.

- **Returns** `int`

##### `.target() → int`

The number of cores you must recover to complete the contract: 10.

- **Returns** `int`

##### `.token() → str`

The passcode to transmit: a non-empty string once recovered() reaches target(), otherwise an empty string.

- **Returns** `str`

*Types / Contracts*

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

## CrosstalkContract

Extends `Contract`

**Returned by:** self.contract (crosstalk)

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

##### `.input_x: str`

First intercepted signal: a string of letters with 0s and 1s scattered through. Some bits are decoys.

- **Returns** `str`

##### `.input_y: str`

Second intercepted signal: same shape as input_x.

- **Returns** `str`

##### `.min_length: int`

Minimum palindrome length for a bit to count: a bit qualifies only if the letters mirror to this span centred on it.

- **Returns** `int`

*Types / Contracts*

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

## RelayHackContract

Extends `Contract`

**Returned by:** self.contract (relay_hack)

### Related object types

- `RelayLock`

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

##### `.lock: RelayLock`

The relay lock to crack.

- **Returns** `RelayLock`

*Types / Contracts*

## RelayLock

**Returned by:** .lock

### Properties

##### `.tumblers: int`

Number of tumblers (6).

- **Returns** `int`

##### `.range: int`

Range per tumbler (100 = 0-99).

- **Returns** `int`

### Methods

##### `.intercept(code: list[int]) → list[bool]`

Test a list of exactly 6 whole-number values in the **0-99** range and return one True/False value per tumbler. Wrong argument types raise `TypeError`; wrong list length, non-finite or fractional values, and values outside the range raise `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `code` | `list[int]` | Candidate list of 6 whole numbers, each 0-99 |

- **Returns** `list[bool]`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | The contract probe received an argument or element of the wrong type. |
| `ValueError` | The contract probe received a value, shape, or coordinate outside its documented domain. |

*Types / Contracts*

## SealedVaultContract

Extends `Contract`

**Returned by:** self.contract (sealed_vault)

### Related object types

- `Vault`

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

##### `.vault: Vault`

The sealed vault passage system. Its position resets to (0, 0) at the start of each contract script run; the maze layout stays fixed.

- **Returns** `Vault`

*Types / Contracts*

## Vault

**Returned by:** .vault

### Related object types

- `VaultPosition`

### Properties

##### `.position: VaultPosition`

Current cell as a `VaultPosition` snapshot with `.row` and `.col`. Store it when you need to remember an old cell; read `vault.position` again after `move()` to get the new cell.

- **Returns** `VaultPosition`

##### `.size: int`

Side length of the (square) maze grid. The maze is `size`×`size` cells; the start is `(0, 0)` and the exit is `(size - 1, size - 1)`.

- **Returns** `int`

### Methods

##### `.move(direction: str) → ActionResult`

Step one cell in `direction`: `"north"`, `"south"`, `"east"`, or `"west"`. A non-string direction raises `TypeError`; an unknown direction raises `ValueError` without moving.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `direction` | `str` | Direction to step. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"path"` | success | The move entered an ordinary path cell. |
| `"wall"` | rejection | A wall blocked the move and the position did not change. |
| `"exit"` | success | The move entered the exit cell. |

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | Vault.move() requires a string direction. |
| `ValueError` | Vault.move() accepts only north, south, east, or west. |

##### `.escape() → VaultEscapeResult`

Open the vault from its exit cell.

- **Returns** `VaultEscapeResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.key`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The vault opened and released its key. |
| `"not_at_exit"` | rejection | The vault can open only from the exit cell. |

*Types / Contracts*

## VaultPosition

**Returned by:** vault.position

### Properties

##### `.row: int`

Row coordinate.

- **Returns** `int`

##### `.col: int`

Column coordinate.

- **Returns** `int`

### Methods

##### `.__iter__() → Iterator[int]`

Iterate over `row`, then `col`, so this position can be unpacked or passed to `list()`.

- **Returns** `Iterator[int]`

*Types / Contracts*

## TerminalBreachContract

Extends `Contract`

**Returned by:** self.contract (terminal_breach)

### Related object types

- `AlienTerminal`

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

##### `.terminal: AlienTerminal`

The alien security terminal.

- **Returns** `AlienTerminal`

*Types / Contracts*

## AlienTerminal

**Returned by:** .terminal

### Related object types

- `GuessResult`

### Properties

##### `.length: int`

Whole-number code length (15).

- **Returns** `int`

### Methods

##### `.guess(digits: list[int]) → GuessResult`

Test a list of exactly 15 whole-number digits in the **1-5** range and return `GuessResult`. Exact-position matches are removed first; `.misplaced` then counts shared remaining occurrences without over-counting duplicates. Wrong argument or element types raise `TypeError`; wrong length, fractional values, or out-of-range digits raise `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `digits` | `list[int]` | Candidate list of 15 whole-number digits, each 1-5 |

- **Returns** `GuessResult`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | The contract probe received an argument or element of the wrong type. |
| `ValueError` | The contract probe received a value, shape, or coordinate outside its documented domain. |

*Types / Contracts*

## GuessResult

**Returned by:** terminal.guess()

### Properties

##### `.correct: int`

Number of digits in the correct position.

- **Returns** `int`

##### `.misplaced: int`

Number of correct digits in wrong positions.

- **Returns** `int`

*Types / Contracts*

## TheLoomContract

Extends `Contract`

**Returned by:** self.contract (the_loom)

### Related object types

- `Loom`

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

##### `.loom: Loom`

The recovered alien loom, your probe tool. Call `loom.weave(a, b)` to learn how it braids two strings into one.

- **Returns** `Loom`

##### `.record: str`

A 42-character woven record made from two equal-length 21-character threads. Reverse the loom's rule to un-weave it; one thread is the message.

- **Returns** `str`

*Types / Contracts*

## Loom

**Returned by:** .loom

### Methods

##### `.weave(a: str, b: str) → str`

Braid two strings into one and return it. Each character is one token. Deterministic: the same inputs always weave the same way, so probe it freely. A non-string argument raises `TypeError`; either input longer than 30 characters raises `ValueError`. The loom only weaves forward; build the reverse yourself.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `str` | First input string |
| `b` | `str` | Second input string |

- **Returns** `str`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | Loom.weave() requires two strings. |
| `ValueError` | Loom.weave() accepts at most 30 characters in each input. |

*Types / Contracts*

## ThreeEchoesContract

Extends `Contract`

**Returned by:** self.contract (three_echoes)

### Related object types

- `ThreeEchoesBroadcast`

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

##### `.broadcast: ThreeEchoesBroadcast`

The intercepted broadcast: three frequency fragments.

- **Returns** `ThreeEchoesBroadcast`

*Types / Contracts*

## ThreeEchoesBroadcast

**Returned by:** .broadcast

### Properties

##### `.freq_a: str`

Ordered fragment containing the 1st, 4th, 7th, and later every-third characters of the original signal.

- **Returns** `str`

##### `.freq_b: str`

Ordered fragment containing the 2nd, 5th, 8th, and later every-third characters of the original signal.

- **Returns** `str`

##### `.freq_c: str`

Ordered fragment containing the 3rd, 6th, 9th, and later every-third characters of the original signal.

- **Returns** `str`

*Types / Contracts*

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

## ContractScript

**Returned by:** self (in contract scripts)

### Properties

##### `.name: str`

Script name.

- **Returns** `str`

##### `.contract: Contract`

The contract object with ID, name, reward, and contract-specific API.

- **Returns** `Contract`

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

## VaultEscapeResult

**Returned by:** Vault.escape()

### Properties

##### `.status: str`

`"ok"` or `"not_at_exit"`.

- **Returns** `str`
- **Possible values** `"ok"`, `"not_at_exit"`

##### `.message: str`

Player-readable explanation of the escape outcome.

- **Returns** `str`

##### `.key: str | None`

Vault key string when `.status == "ok"`; otherwise `None`.

- **Returns** `str | None`

*Types / Built-in Types*
