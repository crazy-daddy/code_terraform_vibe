# Models: Action & Operation Result Contracts

Granular data models and return types extracted from `__builtins__.pyi`.

## `ActionResult`

```python
class ActionResult(Generic[_StatusT]):
    """Gameplay commands with no extra result fields"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
```

## `AnalyzeResult`

```python
class AnalyzeResult(Generic[_StatusT]):
    """bio_lab.analyze()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    info: AnalyzeInfo | None
```

## `BioExtractionResult`

```python
class BioExtractionResult(Generic[_StatusT]):
    """PortableBioExtractor.extract()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    extracted: _float
```

## `BioScanResult`

```python
class BioScanResult(Generic[_StatusT]):
    """PortableBioScanner.scan()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    scan: LifeFormScanResult | None
```

## `BlockedContact`

```python
class BlockedContact:
    """SonarScanResult.blocked"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    x: _int
    y: _int
    reason: Literal["wrong_scanner", "too_hard", "tier_too_low", "research_required"]
    message: _str
```

## `BlueprintPlanResult`

```python
class BlueprintPlanResult(Generic[_StatusT]):
    """`construction_blueprint` planning commands"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    blueprint_ids: _list[_str]
```

## `CollectResult`

```python
class CollectResult(Generic[_StatusT]):
    """drone_small.collect(), drone_medium.collect(), drone_large.collect()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    item_id: _str | None
    collected: _int
```

## `CommandResult`

```python
class CommandResult(Generic[_StatusT]):
    """Component.next_command()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    command: ScriptCommand | None
```

## `CountResult`

```python
class CountResult(Generic[_StatusT]):
    """Queue, discard, clear, and bulk-count commands"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    count: _int
```

## `CropJobResult`

```python
class CropJobResult(Generic[_StatusT]):
    """Crop Automator `next_result()`"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    job_id: _int | None
    action: Literal["harvest", "plant", "apply"] | None
    sector: _str | None
    item_id: _str | None
    collected: _int
    discarded: _int
```

## `DiscardResult`

```python
class DiscardResult(Generic[_StatusT]):
    """Cargo.discard(), DroneCargo.discard()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    requested: _int
    discarded: _int
```

## `GuessResult`

```python
class GuessResult:
    """terminal.guess()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    correct: _int
    misplaced: _int
```

## `ItemResult`

```python
class ItemResult(Generic[_StatusT]):
    """harvester.store(), inventory.drop()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    item_id: _str | None
```

## `LatticeProbeResult`

```python
class LatticeProbeResult(Generic[_StatusT]):
    """LatticeGrid.probe()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    reading: _int | None
```

## `LifeFormScanResult`

```python
class LifeFormScanResult:
    """`PortableBioScanner.scan().scan` after `status == \"ok\"` / journal biosite queries"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    coord: _list[_int]
    life_forms: _list[LifeFormSample]
    is_empty: _bool
```

## `ProbeResult`

```python
class ProbeResult:
    """tablet.probe()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    char: _str
    distance: _int
```

## `ReceiveResult`

```python
class ReceiveResult(Generic[_StatusT]):
    """comms.receive(); comms.wait()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    packet: CommsMessage | None
```

## `SaleResult`

```python
class SaleResult(Generic[_StatusT]):
    """shop.sell(), shop.sell_all()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    item_id: _str
    units: _int
    credits: _int
```

## `ScanResult`

```python
class ScanResult(Generic[_StatusT]):
    """scanner.scan(), harvester.collect()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    id: _str
    name: _str
    value: _float
```

## `SeedResult`

```python
class SeedResult(Generic[_StatusT]):
    """seed_maker.combine()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    seed_id: Literal["seed_sunpetal", "seed_shadeleaf", "seed_dewmoss", "seed_lonethorn", "seed_packfern", "seed_twinvine", "seed_spitebud", "seed_sunspur", "seed_glowvine", "seed_crowncap", "seed_pondmoss", "seed_saltbloom", "seed_brinethorn", "seed_saltmate", "seed_grandbloom"] | None
    species: Literal["sunpetal", "shadeleaf", "dewmoss", "lonethorn", "packfern", "twinvine", "spitebud", "sunspur", "glowvine", "crowncap", "pondmoss", "saltbloom", "brinethorn", "saltmate", "grandbloom"] | None
```

## `SendResult`

```python
class SendResult(Generic[_StatusT]):
    """comms.send()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    message_id: _int | None
```

## `SonarScanResult`

```python
class SonarScanResult(Generic[_StatusT]):
    """SonarModule.scan()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    sites: _list[Site]
    blocked: _list[BlockedContact]
```

## `SurveyResult`

```python
class SurveyResult(Generic[_StatusT]):
    """SonarModule.survey()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    site: Site | None
```

## `TransferResult`

```python
class TransferResult(Generic[_StatusT]):
    """`InputSlot.take()`, `InputSlot.eject()`, `InputSlot.flush()`, `VehicleInputSlot.take()`, `OutputSlot.send()`, `Cargo.compact()`, `storage_bin` transfer methods, `warehouse.compact()`"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    requested: _int
    moved: _int
```

## `VaultEscapeResult`

```python
class VaultEscapeResult(Generic[_StatusT]):
    """Vault.escape()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    key: _str | None
```

## `WaitAnyResult`

```python
class WaitAnyResult(Generic[_StatusT]):
    """comms.wait_any()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    channel: _str | None
    packet: CommsMessage | None
```

## `WaitBroadcastResult`

```python
class WaitBroadcastResult(Generic[_StatusT]):
    """comms.wait_broadcast()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    broadcast: BroadcastInfo | None
```

## `WasteDumpResult`

```python
class WasteDumpResult(Generic[_StatusT]):
    """oxygen_generator.dump_waste()"""
    def __new__(cls, _game_api_only: Never, /) -> Never: ...
    status: _StatusT
    message: _str
    penalty: _float
```
