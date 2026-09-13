# Contract: sealed_vault

## SealedVaultContract

Extends `Contract`

**Returned by:** self.contract (sealed_vault)

### Related object types

- `Vault`

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

##### `.vault`

The sealed vault passage system. Its position resets to (0, 0) at the start of each contract script run; the maze layout stays fixed.

- **Returns** `Vault`

*Types / Contracts*

---

## Vault

**Returned by:** .vault

### Related object types

- `VaultPosition`

### Properties

##### `.position`

Current cell as a `VaultPosition` snapshot with `.row` and `.col`. Store it when you need to remember an old cell; read `vault.position` again after `move()` to get the new cell.

- **Returns** `VaultPosition`

##### `.size`

Side length of the (square) maze grid. The maze is `size`×`size` cells; the start is `(0, 0)` and the exit is `(size - 1, size - 1)`.

- **Returns** `number`

### Methods

##### `.move(direction)`

Step one cell in `direction`: `"north"`, `"south"`, `"east"`, or `"west"`. A non-string direction raises `TypeError`; an unknown direction raises `ValueError` without moving.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `direction` | `string` | Direction to step. |

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

##### `.escape()`

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

---

## VaultPosition

**Returned by:** vault.position

### Properties

##### `.row`

Row coordinate.

- **Returns** `number`

##### `.col`

Column coordinate.

- **Returns** `number`

### Methods

##### `.__iter__()`

Iterate over `row`, then `col`, so this position can be unpacked or passed to `list()`.

- **Returns** `iterator<number>`

*Types / Contracts*

---

## VaultEscapeResult

**Returned by:** Vault.escape()

### Properties

##### `.status`

`"ok"` or `"not_at_exit"`.

- **Returns** `string`
- **Possible values** `"ok"`, `"not_at_exit"`

##### `.message`

Player-readable explanation of the escape outcome.

- **Returns** `string`

##### `.key`

Vault key string when `.status == "ok"`; otherwise `None`.

- **Returns** `Optional[string]`

*Types / Built-in Types*

---
