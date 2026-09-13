# Contract: beat_the_system

## BeatTheSystemContract

Extends `Contract`

**Returned by:** self.contract (beat_the_system)

### Related object types

- `Arbiter`

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

##### `.arbiter`

The alien Arbiter. It takes an immediate win, otherwise blocks your immediate win, otherwise prefers centre, then corners, then edges; tied choices are random.

- **Returns** `Arbiter`

*Types / Contracts*

---

## Arbiter

**Returned by:** .arbiter

### Methods

##### `.new_game()`

Start a fresh 3×3 game on an empty board; you move first. After a finished game this call pauses about half a second before the next board is ready.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"in_progress"` | transient | The operation is still in progress. |

##### `.restart()`

Abandon any game in progress and start fresh; you move first. Abandoning a game mid-play counts as a non-win and resets your current-run streak to 0. Like new_game(), it pauses about half a second between games.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.play(cell)`

Place your mark in a whole-number cell in the **0-8** range (row-major), then the Arbiter responds. Three marks in a row, column, or diagonal wins. A non-number cell raises `TypeError`; a non-finite, fractional, or out-of-range cell raises `ValueError` before game state is considered.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `cell` | `number` | Whole-number board cell to mark, 0-8 |

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

##### `.board()`

The 9 board cells as a list, index 0-8 row-major. Each cell is "" (empty), "you", or "arbiter".

- **Returns** `list<string>`

##### `.result()`

Current game outcome: "ongoing", "win", "loss", "draw", or "no_game" (no game started yet).

- **Returns** `string`
- **Possible values** `"ongoing"`, `"win"`, `"loss"`, `"draw"`, `"no_game"`

##### `.streak()`

Consecutive wins in the current script run. Resets to 0 on a loss, draw, abandonment, or fresh script run.

- **Returns** `number`

##### `.target()`

The consecutive-win count needed to complete the contract.

- **Returns** `number`

##### `.token()`

The passcode to transmit: a non-empty string once streak() reaches target(), otherwise an empty string.

- **Returns** `string`

*Types / Contracts*

---
