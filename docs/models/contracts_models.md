# Models: Contracts, Devices & Puzzle State Models

Granular data models and return types extracted from `__builtins__.pyi`.

## `Archive`

```python
class Archive:
    """.archive"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    def flip(self, row: _int, col: _int) -> _str:
        """Reveal and return the word at a whole-number grid cell. Wrong argument types raise `TypeError`; fractional, non-finite, or out-of-bounds coordinates raise `ValueError`."""
        ...
    rows: _int
    cols: _int
```

## `BeatTheSystemContract`

```python
class BeatTheSystemContract(Contract):
    """self.contract (beat_the_system)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    arbiter: Arbiter
```

## `BuriedFiveContract`

```python
class BuriedFiveContract(Contract):
    """self.contract (buried_five)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    transmission: _list[_str]
    analyzer: Analyzer
    layers: _int
```

## `ColdBootContract`

```python
class ColdBootContract(Contract):
    """self.contract (cold_boot)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    program: _list[_int]
```

## `Contract`

```python
class Contract:
    """self.contract"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
```

## `ContractScript`

```python
class ContractScript:
    """`self` (in contract scripts)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    name: _str
    contract: Contract
```

## `CoreSampleContract`

```python
class CoreSampleContract(Contract):
    """self.contract (core_sample)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    cores: _list[_list[_int | None]]
    device: CoreDevice
```

## `CorruptedArchiveContract`

```python
class CorruptedArchiveContract(Contract):
    """self.contract (corrupted_archive)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    archive: Archive
```

## `CrosstalkContract`

```python
class CrosstalkContract(Contract):
    """self.contract (crosstalk)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    input_x: _str
    input_y: _str
    min_length: _int
```

## `DataTablet`

```python
class DataTablet:
    """.tablet"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    def probe(self, row: _int, col: _int) -> ProbeResult:
        """Probe a whole-number cell and return a `ProbeResult` with `.char` and whole-number `.distance`. Wrong argument types raise `TypeError`; fractional or out-of-bounds coordinates raise `ValueError`."""
        ...
    rows: _int
    cols: _int
```

## `DataTabletContract`

```python
class DataTabletContract(Contract):
    """self.contract (data_tablet)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    tablet: DataTablet
```

## `DriftingSignalContract`

```python
class DriftingSignalContract(Contract):
    """self.contract (drifting_signal)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    device: SlabDevice
```

## `LatticeContract`

```python
class LatticeContract(Contract):
    """self.contract (lattice)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    grid: LatticeGrid
```

## `RelayHackContract`

```python
class RelayHackContract(Contract):
    """self.contract (relay_hack)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    lock: RelayLock
```

## `RelayLock`

```python
class RelayLock:
    """.lock"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    def intercept(self, code: _list[_int]) -> _list[_bool]:
        """Test a list of exactly 6 whole-number values in the **0-99** range and return one `True`/`False` value per tumbler. Wrong argument types raise `TypeError`; wrong list length, non-finite or fractional values, and values outside the range raise `ValueError`."""
        ...
    tumblers: _int
    range: _int
```

## `SealedVaultContract`

```python
class SealedVaultContract(Contract):
    """self.contract (sealed_vault)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    vault: Vault
```

## `SlabDevice`

```python
class SlabDevice:
    """.device"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    slabs: _str
```

## `TerminalBreachContract`

```python
class TerminalBreachContract(Contract):
    """self.contract (terminal_breach)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    terminal: AlienTerminal
```

## `TheLoomContract`

```python
class TheLoomContract(Contract):
    """self.contract (the_loom)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    loom: Loom
    record: _str
```

## `ThreeEchoesBroadcast`

```python
class ThreeEchoesBroadcast:
    """.broadcast"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    freq_a: _str
    freq_b: _str
    freq_c: _str
```

## `ThreeEchoesContract`

```python
class ThreeEchoesContract(Contract):
    """self.contract (three_echoes)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    broadcast: ThreeEchoesBroadcast
```

## `Vault`

```python
class Vault:
    """.vault"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    def move(self, direction: _str) -> ActionResult[Literal["path", "wall", "exit"]]:
        """Step one cell in `direction`: `\"north\"`, `\"south\"`, `\"east\"`, or `\"west\"`. A non-string direction raises `TypeError`; an unknown direction raises `ValueError` without moving. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    position: VaultPosition
    def escape(self) -> VaultEscapeResult[Literal["ok", "not_at_exit"]]:
        """Open the vault from its exit cell. Fixed result contract: `VaultEscapeResult`; branch on `.status` and read `.message`. Payload fields: `.key`."""
        ...
    size: _int
```

## `VaultPosition`

```python
class VaultPosition:
    """vault.position"""
    def __init__(self, row: _int, col: _int) -> None:
        """Create a local `VaultPosition` value for your script. Creating this value does not change the world."""
        ...
    row: _int
    col: _int
    def __iter__(self) -> Iterator[_int]:
        """Iterate over `row`, then `col`, so this position can be unpacked or passed to `list()`."""
        ...
```

## `XenogeneticsContract`

```python
class XenogeneticsContract(Contract):
    """self.contract (xenogenetics)"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    id: Literal["relay_hack", "xenogenetics", "corrupted_archive", "sealed_vault", "data_tablet", "terminal_breach", "drifting_signal", "cold_boot", "three_echoes", "buried_five", "the_loom", "crosstalk", "beat_the_system", "core_sample", "lattice"]
    name: _str
    reward: _int
    status: Literal["available", "completed"]
    earth_ref: _list[_str]
    samples: _list[_str]
```
