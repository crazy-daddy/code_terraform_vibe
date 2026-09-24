# Contract: sealed_vault

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
