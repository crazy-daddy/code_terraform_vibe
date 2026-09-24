# Contract: terminal_breach

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
