# Models: Action & Operation Result Contracts

Granular data models and return types extracted from `__builtins__.pyi`.

## `ActionResult`

```python
class ActionResult(Generic[_StatusT]):
    """Gameplay commands with no extra result fields"""
    status: _StatusT
    message: _str
```

## `AnalyzeResult`

```python
class AnalyzeResult(Generic[_StatusT]):
    """bio_lab.analyze()"""
    status: _StatusT
    message: _str
    info: AnalyzeInfo | None
```

## `BioExtractionResult`

```python
class BioExtractionResult(Generic[_StatusT]):
    """PortableBioExtractor.extract()"""
    status: _StatusT
    message: _str
    extracted: _float
```

## `BioScanResult`

```python
class BioScanResult(Generic[_StatusT]):
    """PortableBioScanner.scan()"""
    status: _StatusT
    message: _str
    scan: LifeFormScanResult | None
```

## `BlockedContact`

```python
class BlockedContact:
    """SonarScanResult.blocked"""
    x: _int
    y: _int
    reason: Literal["wrong_scanner", "too_hard", "tier_too_low", "research_required"]
    message: _str
```

## `BlueprintPlanResult`

```python
class BlueprintPlanResult(Generic[_StatusT]):
    """construction_blueprint planning commands"""
    status: _StatusT
    message: _str
    blueprint_ids: _list[_str]
```

## `CollectResult`

```python
class CollectResult(Generic[_StatusT]):
    """drone_small.collect(), drone_medium.collect(), drone_large.collect()"""
    status: _StatusT
    message: _str
    item_id: _str | None
    collected: _int
```

## `CommandResult`

```python
class CommandResult(Generic[_StatusT]):
    """Component.next_command()"""
    status: _StatusT
    message: _str
    command: ScriptCommand | None
```

## `CountResult`

```python
class CountResult(Generic[_StatusT]):
    """Queue, discard, clear, and bulk-count commands"""
    status: _StatusT
    message: _str
    count: _int
```

## `CropJobResult`

```python
class CropJobResult(Generic[_StatusT]):
    """Crop Automator next_result()"""
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
    status: _StatusT
    message: _str
    requested: _int
    discarded: _int
```

## `GuessResult`

```python
class GuessResult:
    """terminal.guess()"""
    correct: _int
    misplaced: _int
```

## `ItemResult`

```python
class ItemResult(Generic[_StatusT]):
    """harvester.store(), inventory.drop()"""
    status: _StatusT
    message: _str
    item_id: _str | None
```

## `LatticeProbeResult`

```python
class LatticeProbeResult(Generic[_StatusT]):
    """LatticeGrid.probe()"""
    status: _StatusT
    message: _str
    reading: _int | None
```

## `LifeFormScanResult`

```python
class LifeFormScanResult:
    """PortableBioScanner.scan().scan after status == \"ok\" / journal biosite queries"""
    coord: _list[_int]
    life_forms: _list[LifeFormSample]
    is_empty: _bool
```

## `ProbeResult`

```python
class ProbeResult:
    """tablet.probe()"""
    char: _str
    distance: _int
```

## `ReceiveResult`

```python
class ReceiveResult(Generic[_StatusT]):
    """comms.receive(); comms.wait()"""
    status: _StatusT
    message: _str
    packet: CommsMessage | None
```

## `SaleResult`

```python
class SaleResult(Generic[_StatusT]):
    """shop.sell(), shop.sell_all()"""
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
    status: _StatusT
    message: _str
    seed_id: Literal["seed_sunpetal", "seed_shadeleaf", "seed_dewmoss", "seed_lonethorn", "seed_packfern", "seed_twinvine", "seed_spitebud", "seed_sunspur", "seed_glowvine", "seed_crowncap", "seed_pondmoss", "seed_saltbloom", "seed_brinethorn", "seed_saltmate", "seed_grandbloom"] | None
    species: Literal["sunpetal", "shadeleaf", "dewmoss", "lonethorn", "packfern", "twinvine", "spitebud", "sunspur", "glowvine", "crowncap", "pondmoss", "saltbloom", "brinethorn", "saltmate", "grandbloom"] | None
```

## `SendResult`

```python
class SendResult(Generic[_StatusT]):
    """comms.send()"""
    status: _StatusT
    message: _str
    message_id: _int | None
```

## `SonarScanResult`

```python
class SonarScanResult(Generic[_StatusT]):
    """SonarModule.scan()"""
    status: _StatusT
    message: _str
    sites: _list[Site]
    blocked: _list[BlockedContact]
```

## `SurveyResult`

```python
class SurveyResult(Generic[_StatusT]):
    """SonarModule.survey()"""
    status: _StatusT
    message: _str
    site: Site | None
```

## `TransferResult`

```python
class TransferResult(Generic[_StatusT]):
    """InputSlot.take(), InputSlot.eject(), InputSlot.flush(), VehicleInputSlot.take(), OutputSlot.send(), Cargo.compact(), storage_bin transfer methods, warehouse.compact()"""
    status: _StatusT
    message: _str
    requested: _int
    moved: _int
```

## `VaultEscapeResult`

```python
class VaultEscapeResult(Generic[_StatusT]):
    """Vault.escape()"""
    status: _StatusT
    message: _str
    key: _str | None
```

## `WaitAnyResult`

```python
class WaitAnyResult(Generic[_StatusT]):
    """comms.wait_any()"""
    status: _StatusT
    message: _str
    channel: _str | None
    packet: CommsMessage | None
```

## `WaitBroadcastResult`

```python
class WaitBroadcastResult(Generic[_StatusT]):
    """comms.wait_broadcast()"""
    status: _StatusT
    message: _str
    broadcast: BroadcastInfo | None
```

## `WasteDumpResult`

```python
class WasteDumpResult(Generic[_StatusT]):
    """oxygen_generator.dump_waste()"""
    status: _StatusT
    message: _str
    penalty: _float
```
