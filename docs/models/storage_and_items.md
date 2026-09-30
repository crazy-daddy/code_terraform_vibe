# Models: Storage, Slots, Stacks & Item Structures

Granular data models and return types extracted from `__builtins__.pyi`.

## `Bin`

```python
class Bin:
    """Rack.bins"""
    id: Literal["portable_bin", "heavy_portable_bin"]
    capacity: _int
    count: _int
    item_id: _str | None
    stacks: _list[ItemStack]
```

## `Cargo`

```python
class Cargo:
    """self.cargo (Fahrzeuge)"""
    def count(self) -> _int:
        """Gesamtzahl der Einheiten, die das Fahrzeug derzeit transportiert."""
        ...
    def capacity(self) -> _int:
        """Gesamtzahl der Einheiten, die das Fahrzeug im integrierten Frachtraum oder in montierten Frachtgestellen transportieren kann."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Momentaufnahme aller nach Eigenschaften getrennten `ItemStack`-Stapel in der Fahrzeugfracht. Damit kannst du Varianten mit derselben Gegenstands-ID unterscheiden."""
        ...
    def full(self) -> _bool:
        """`True`, wenn der integrierte Frachtraum oder alle montierten Frachtbehälter voll sind. Ein Pionier ohne montierte Behälter gilt ebenfalls als voll."""
        ...
    def racks(self) -> _list[Rack]:
        """Liste aller derzeit montierten Frachtgestelle. Beim Rover ist sie leer."""
        ...
    def compact(self) -> TransferResult[Literal["ok", "already_compact", "research_required", "busy", "source_changed", "target_full"]]:
        """Fasse auf einem Pionier Gegenstände mit gleicher ID in möglichst wenigen montierten tragbaren Behältern zusammen, die sie aufnehmen können. Varianten mit unterschiedlichen Eigenschaften bleiben erhalten. Um die physische Umlagerung zu minimieren, belässt die Planung möglichst volle kompatible Behälter an ihrem Platz. Erfordert **Automatische Zuführungen**, wartet eine zur Anzahl der umgelagerten Einheiten proportionale Zeit und hält den Pionier während dieses Vorgangs als Materialendpunkt an Ort und Stelle. Die Reihenfolge, in der `send()` Behälter leert, ändert sich dadurch nicht. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def discard(self, rack_index: _int) -> DiscardResult[Literal["ok", "empty", "busy", "invalid_rack"]]:
        """Wirf den gesamten Inhalt des durch den ganzzahligen, bei null beginnenden `rack_index` bezeichneten Frachtgestells dauerhaft ab. Beim Rover ohne Frachtgestelle bezeichnet `self.cargo.discard(0)` den integrierten Frachtraum. Ein bereits leerer Frachtraum oder ein leeres Gestell ist sofort fertig; das Vernichten von Fracht dauert **1 Stunde** und hält das Skript an. Dies ist die API zum Vernichten von Fahrzeugfracht. Fester Ergebnisvertrag: `DiscardResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.discarded`."""
        ...
```

## `DockSlot`

```python
class DockSlot:
    """supply_dock.slots()"""
    index: _int
    item_id: _str | None
    count: _int
```

## `DroneCargo`

```python
class DroneCargo:
    """self.cargo (Drohnen)"""
    def count(self) -> _int:
        """Gesamtzahl der Einheiten in allen Frachtkapseln und der Kammer des Bioextraktors."""
        ...
    def capacity(self) -> _int:
        """Gesamte physische Kapazität aller Behälter: jede montierte Frachtkapsel (klein **100**, mittel **250**, groß **500**) plus die **25-t**-Kammer des Bioextraktors. Schutzpanzerung halbiert die Kapazität jeder Frachtkapsel."""
        ...
    def contents(self) -> _dict[_str, _int]:
        """Ein dict, das für jedes derzeit in der Fracht befindliche Material `item_id` → Anzahl der Einheiten zuordnet. Mit `.keys()` / `.items()` durchlaufen."""
        ...
    def space_for(self, item_id: _str) -> _int:
        """Freier Platz für dieses bestimmte Material. **Jede Frachtkapsel fasst nur ein Material**. Eine Kapsel zählt daher nur, wenn sie leer ist oder bereits `item_id` enthält; die 25-t-Kammer des Bioextraktors zählt nur für Lebensformen. Gibt für ein Material **0** zurück, wenn keine leere oder passende Kapsel vorhanden ist, auch wenn andere Kapseln noch Platz für ihre jeweiligen Materialien haben."""
        ...
    def full(self) -> _bool:
        """`True`, wenn `count() >= capacity()`. Sind alle Frachtkapseln bereits einem Material zugeordnet, kann eine Drohne trotz `False` bei `full()` möglicherweise keinen neuen Gegenstandstyp laden. Verwende `space_for(item_id)` für einen bestimmten Gegenstand."""
        ...
    def load(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "invalid_properties", "invalid_property_match", "research_required", "target_moving", "not_at_source", "source_empty", "slots_full", "target_full", "needs_plating", "cask_missing", "source_changed", "target_changed"]]:
        """Bis zu `count` ganze Einheiten in die Fracht dieser Drohne laden, ohne ihre Eigenschaften zu verändern. Die Ladung stammt aus dem Vorrat des angedockten Drohnendepots oder aus einem Bergbaubohrer im Feld, nachdem die Drohne ihre Route dorthin abgeschlossen hat. Heiße Fracht wird aus einem Bleibehälter vor Ort geladen und erfordert Schutzpanzerung. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def unload(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "invalid_properties", "invalid_property_match", "research_required", "not_at_target", "source_empty", "slots_full", "target_full", "cask_missing", "source_changed", "target_changed"]]:
        """Bis zu `count` ganze Einheiten aus der Fracht dieser Drohne in ihr angedocktes Drohnendepot entladen, ohne ihre Eigenschaften zu verändern. Heiße Fracht wird in einen passenden Bleibehälter entladen. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def discard(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> DiscardResult[Literal["ok", "partial", "empty", "no_op", "invalid_properties", "invalid_property_match", "source_changed"]]:
        """Bis zu `count` ganze Einheiten aus der Fracht dieser Drohne dauerhaft vernichten. Für diesen Abwurf ist keine Station nötig; eine geleerte Frachtkapsel wird für ein neues Material freigegeben. Fester Ergebnisvertrag: `DiscardResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.discarded`."""
        ...
```

## `DroneOilTank`

```python
class DroneOilTank:
    """self.oil_tank (Helikopterdrohnen)"""
    def level(self) -> _float:
        """Aktuelle Ölmenge aller montierten Öltanks in Tonnen. Löst `ReferenceError` aus, wenn diese Drohne keinen Heli-Antrieb hat."""
        ...
    def capacity(self) -> _float:
        """Gesamte Ölkapazität in Tonnen. Löst `ReferenceError` aus, wenn diese Drohne keinen Heli-Antrieb hat."""
        ...
    def percent(self) -> _float:
        """Ölmenge als Anteil zwischen **0-1**. Löst `ReferenceError` aus, wenn diese Drohne keinen Heli-Antrieb hat."""
        ...
```

## `GasTank`

```python
class GasTank(Component):
    """Gastank: Ein passiver Puffer, der sich auf das erste eingeleitete Gas festlegt (Dampf, Ammoniak, Sumpfgas) und nur dieses speichert, bis er leer ist. Zwischen einer Quelle und ihrem Verbraucher gleicht er Versorgungslücken aus."""
    name: _str
    outpost: OutpostRef
    def fluid(self) -> Literal["", "steam", "ammonia", "swamp_gas", "raw_sulfur_gas", "sulfur_gas", "raw_chlorine", "chlorine"]:
        """Die ID des Gases, auf das der Tank festgelegt ist (z. B. `\"steam\"`, `\"ammonia\"`), oder `\"\"`, solange er leer ist. Der Tank legt sich auf das erste zugeführte Gas fest und speichert nur dieses, bis sein Füllstand auf **0** sinkt. Danach kann er sich auf ein neues Gas festlegen."""
        ...
    def level(self) -> _float:
        """Aktuell gespeicherte Gasmenge in Tonnen, von **0** bis `capacity()`. Lies den Wert bei jedem Durchlauf aus, um den Puffer einzuschätzen: Nahe **0** droht den nachgeschalteten Verbrauchern das Gas auszugehen; nahe `capacity()` staut sich das Gas vor dem Tank. Bei **0** löst sich die Festlegung des Tanks, sodass er als Nächstes ein anderes Gas annehmen kann."""
        ...
    def capacity(self) -> _float:
        """Maximale Gasmenge in Tonnen, die dieser Tank fasst. Der Wert lässt sich abfragen, statt ihn fest im Skript einzutragen, damit Anpassungen am Tank keine Skripte beschädigen. Verwende ihn zusammen mit `level()` für eine Füllstandsanzeige in Prozent oder nutze direkt `fill_pct()`."""
        ...
    def fill_pct(self) -> _float:
        """Füllanteil (**0.0-1.0**), Kurzform für `level() / capacity()`. Verwende ihn für Schwellenwertprüfungen: `if self.fill_pct() < 0.2: # boost throttle upstream`."""
        ...
    def inflow_rate(self) -> _float:
        """Gaszufluss in t/h. **0** bedeutet, dass kein Gas von der vorgeschalteten Seite einströmt, etwa weil die Quelle inaktiv, die Verbindung nicht verfügbar, die Fernroute unvollständig oder der Tank voll ist. Vergleiche den Wert mit `outflow_rate()`, um zu sehen, ob sich der Tank füllt oder leert."""
        ...
    def outflow_rate(self) -> _float:
        """Gasabfluss in t/h. **0** bedeutet, dass ein nachgeschalteter Verbraucher gesättigt oder die Rohrverbindung getrennt ist."""
        ...
    def is_full(self) -> _bool:
        """`True`, wenn `level() == capacity()` gilt, sich das Gas vor dem Tank staut und ein vorgeschalteter Dampfsammler möglicherweise beginnt, Dampf in die Atmosphäre abzulassen. Prüfe den Wert, um zu erkennen, wann angeschlossene Ziele die aktuelle Produktion nicht aufnehmen können."""
        ...
    def is_empty(self) -> _bool:
        """`True`, wenn `level() == 0` gilt. Der Tank ist dann auf kein Gas festgelegt und kann nichts an nachgeschaltete Verbraucher abgeben. Wenn die Quelle noch aktiv ist und der Tank trotzdem leer bleibt, prüfe die Quelle und ihre Rohrverbindung."""
        ...
    gas_in: FluidPort
    gas_out: FluidPort
    steam_in: FluidPort
    steam_out: FluidPort
    ammonia_in: FluidPort
    ammonia_out: FluidPort
    swamp_gas_in: FluidPort
    swamp_gas_out: FluidPort
    raw_sulfur_gas_in: FluidPort
    raw_sulfur_gas_out: FluidPort
    sulfur_gas_in: FluidPort
    sulfur_gas_out: FluidPort
    raw_chlorine_in: FluidPort
    raw_chlorine_out: FluidPort
    chlorine_in: FluidPort
    chlorine_out: FluidPort
```

## `InputSlot`

```python
class InputSlot:
    """self.input bei stationären Maschinen mit Eingabepuffer"""
    def connect(self, name: _str) -> ActionResult[Literal["ok", "not_found", "not_local", "same_endpoint", "unsupported_source", "source_is_vehicle"]]:
        """Lege anhand einer stabilen ID oder eines Anzeigenamens eine kompatible Gegenstandsquelle fest. Zwei stationäre Endpunkte müssen sich am selben Außenposten befinden. Ein Rover oder Pionier ist von jedem Außenposten aus erreichbar, jedoch nur, solange er im Versorgungsbereich dieser Maschine geparkt ist. Abholausgänge von Feldextraktoren können nur von einem Rover oder Pionier entnommen werden. Die Fracht einer Drohne wird über ihr Drohnendepot transportiert. `\"inventory\"` ist nur dann eine Frachtquelle, wenn sich der Endpunkt an der Nocturna-Basis befindet. Entfernte stationäre Anschlüsse verwenden lokale Lagerbehälter, Lagerhäuser oder Maschinenpuffer. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def disconnect(self) -> ActionResult[Literal["ok"]]:
        """Entfernt die aktuelle Quellenverbindung. Gepufferte Gegenstände werden weder verschoben noch verworfen. Verwende `eject(...)`, um sie zurückzuholen, oder `flush()`, um sie zu vernichten. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def connected_to(self) -> _str:
        """Anzeigename der aktuell verbundenen Quelle oder eine leere Zeichenfolge."""
        ...
    def connected_id(self) -> _str:
        """Stabile ID der aktuell verbundenen Quelle oder eine leere Zeichenfolge. `connect()` akzeptiert eine ID oder einen Anzeigenamen, aber dieser Wert ist die aufgelöste stabile ID. Vergleiche ihn mit der stabilen ID der Quelle; `connected_to()` liefert deren änderbaren Anzeigenamen."""
        ...
    def take(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "no_connection", "inventory_not_local", "same_endpoint", "source_missing", "source_under_construction", "source_is_vehicle", "source_not_local", "not_at_source", "unsupported_source", "source_wrong_material", "source_empty", "source_reserved", "source_changed", "buffer_full", "slots_full", "target_wrong_material", "wrong_biome", "target_unconfigured", "hot_cargo_requires_cask", "order_item_not_required", "order_slots_full", "order_fulfilled", "target_full", "target_complete", "target_changed", "same_vehicle", "source_moving", "target_moving", "out_of_range"]]:
        """Entnimm bis zu `count` ganze Einheiten von `item_id` aus der verbundenen Quelle. Ein Eigenschaften-dict wählt standardmäßig Stapel aus, die diese Teilmenge enthalten. Übergib `\"exact\"` als viertes Argument, um eine vollständige Identität auszuwählen; `None, \"exact\"` wählt nur Gegenstände ohne Eigenschaften aus. `\"any\"` ignoriert Eigenschaften. Die genauen Eigenschaften der Quelle bleiben immer erhalten. Die Übertragung wartet automatisch eine zur verschobenen Menge proportionale Zeit und erfordert die Erforschung der Automatischen Zuführungen. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def eject(self, destination: _str, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "inventory_not_local", "same_endpoint", "source_under_construction", "source_wrong_material", "source_empty", "source_reserved", "source_changed", "target_missing", "target_under_construction", "target_is_vehicle", "target_not_local", "unsupported_target", "target_wrong_material", "wrong_biome", "target_unconfigured", "hot_cargo_requires_cask", "cask_accepts_hot_only", "order_item_not_required", "order_slots_full", "order_fulfilled", "slots_full", "target_full", "target_complete", "target_changed"]]:
        """Hole bis zu `count` ganze Einheiten von `item_id` aus diesem Puffer zurück, ohne seine Quellenverbindung zu ändern. Verwende `\"inventory\"` an der Nocturna-Basis oder ein kompatibles Lager, einen Maschineneingang oder ein geparktes Bodenfahrzeug am selben Außenposten. Für optionale Eigenschaften gelten die üblichen Auswahlregeln für beliebige Eigenschaften, Teilmengen oder exakte Übereinstimmung; die genauen Gegenstandseigenschaften bleiben erhalten. Die Kapazität des Ziels kann die übertragene Menge begrenzen. Bei aktiver oder reservierter Arbeit wird der Vorgang abgelehnt, ohne etwas zu verschieben. Ein erfolgreicher Auswurf verwirft den bisherigen Teilfortschritt bei der Verarbeitung der gepufferten Gegenstände. Die Übertragung wartet automatisch eine zur verschobenen Menge proportionale Zeit und erfordert die Erforschung der Automatischen Zuführungen. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def flush(self) -> TransferResult[Literal["ok", "no_op"]]:
        """Verwirft dauerhaft alles, was derzeit in diesem Eingangsanschluss gepuffert ist. Verworfene Gegenstände werden nicht ins Inventar zurückgegeben. Bei Verarbeitungsmaschinen bricht das Leeren außerdem jeden laufenden Herstellungsvorgang ab. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def count(self) -> _int:
        """Gesamtzahl der Einheiten, die sich derzeit im Puffer dieses Anschlusses befinden."""
        ...
    def capacity(self) -> _int:
        """Maximale Anzahl an Einheiten, die der Puffer dieses Anschlusses aufnehmen kann."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Liste von Momentaufnahmen der derzeit gepufferten `ItemStack`-Werte mit unterschiedlichen Eigenschaften. Zwei Einträge können dieselbe ID haben, wenn sich ihre Eigenschaften unterscheiden."""
        ...
```

## `Inventory`

```python
class Inventory(Component):
    """Inventar: Das Inventar ist der physische Lagerraum der **Nocturna-Basis**. Seine Seite und die schreibgeschützten Skriptmethoden sind überall auf dem Planeten sichtbar. Gewöhnliche Fracht von Maschinen oder Fahrzeugen erreicht das Inventar jedoch nur am Heimat-Außenposten; abgelegene Standorte nutzen lokale Lager und Fahrzeuge. Einkäufe landen hier.

    Steuerbefehle zum Aufstellen, Entfernen, Stilllegen und Aufrüsten sowie Hardware-Befehle für leere Anlagen sind ausdrückliche Inbetriebnahme- oder Wartungsaufträge, keine Frachtrouten. Bei manueller Biologiearbeit wird am Heimat-Außenposten das Inventar und andernorts ein ausgewähltes Lagerhaus desselben Außenpostens genutzt. Reagenzien für das Habitat werden vor Ort bereitgestellt.
    """
    name: _str
    def stacks(self) -> _list[ItemStack]:
        """Listet alle vorhandenen Gegenstandsstapel als `ItemStack` mit `.id`, `.count` und den genauen `.properties` auf. Gegenstände mit derselben ID, aber unterschiedlichen Eigenschaften erscheinen getrennt. Lagerbehälter und Lagerhäuser verwenden dasselbe Format. So können Transportskripte alle drei Lagerarten auf dieselbe Weise prüfen und den Transfermethoden die genauen Eigenschaften übergeben."""
        ...
    def get_slots(self) -> _list[Slot]:
        """Listet alle aktuellen Plätze des Inventars auf. Das Inventar beginnt mit **36** Plätzen; durch Frachterweiterung können es bis zu **60** werden. Stapelbare Gegenstände fassen **10** Einheiten pro Platz, nach **Größere Stapel** sind es **20**. Jeder `Slot` hat einen nullbasierten Index von `0` bis `get_size() - 1` sowie Gegenstands-ID, Namen, Wert, Anzahl und Eigenschaften. Die Eigenschaften sind ein dict mit der genauen Identität oder bei gewöhnlichen Gegenständen `None`. Nutze sie, um Varianten mit derselben ID zu unterscheiden und bei Transfers genau den gewünschten Gegenstand auszuwählen."""
        ...
    def count(self, item_id: _str) -> _int:
        """Anzahl der Einheiten von `item_id`, die derzeit über alle Plätze hinweg gelagert sind. Gibt **0** zurück, wenn kein Platz diesen Gegenstand enthält. Lagerbehälter, Lagerhäuser und Bleibehälter bieten dieselbe Abfrage `count(item_id)`, sodass eine Hilfsfunktion alle Lager durchsuchen kann."""
        ...
    def has_space(self, item_id: _str | None = ..., properties: ItemProperties | None = ...) -> _bool:
        """Prüfe, ob im Inventar Platz ist. Ohne Argument ist `has_space()` gleich `True`, wenn irgendein Platz frei ist. Übergibst du eine Gegenstands-ID und Eigenschaften, wird genau diese Variante geprüft: Ein teilweise gefüllter Stapel zählt nur, wenn beides übereinstimmt; ein leerer Platz kann die Variante aufnehmen. Übergib `slot.properties`, wenn du einen Gegenstand mit Eigenschaften prüfst."""
        ...
    def space_for(self, item_id: _str, properties: ItemProperties | None = ...) -> _int:
        """Wie viele Einheiten einer genau bestimmten Gegenstandsvariante **jetzt** hineinpassen: der freie Platz in teilweise gefüllten Stapeln mit derselben ID und denselben Eigenschaften plus die Anzahl leerer Plätze, multipliziert mit der aktuellen Stapelgröße. **Größere Stapel** erhöht diese Größe bei stapelbaren Gegenständen von **10** auf **20**. Verwende für einen Gegenstand mit Eigenschaften `inventory.space_for(slot.id, slot.properties)`. Ohne Eigenschaften wird die gewöhnliche Variante ohne Eigenschaften geprüft."""
        ...
    def transfer_to(self, target: _str, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "target_missing", "unsupported_target", "same_storage", "target_not_local", "source_under_construction", "source_wrong_material", "source_empty", "source_changed", "target_under_construction", "target_wrong_material", "hot_cargo_requires_cask", "cask_accepts_hot_only", "slots_full", "target_full", "target_changed"]]:
        """Erfordert die Forschung **Automatische Zuführungen**. Verschiebe bis zu `count` ganze Einheiten von `item_id` aus diesem Lager zu einem anderen Lagerbehälter, einem Lagerhaus, einem großen Lagerhaus, einem Bleibehälter oder dem Inventar. Übergib den Anzeigenamen oder die Instanz-ID eines Lagergebäudes oder `\"inventory\"`. Das Inventar kann nur in **Nocturna Base** teilnehmen. Der Aufruf wartet, bis der Zuführzyklus des physischen Lagers abgeschlossen ist; alle beteiligten Lagergebäude bleiben währenddessen beschäftigt. Die genauen Gegenstandseigenschaften bleiben erhalten; mit den optionalen Parametern `properties` und `property_match` wählst du eine Variante aus. Das aufrufende Skript kann überall laufen, aber Fracht überschreitet bei dieser Methode keine Außenpostengrenzen. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def drop(self, slot: _int) -> ItemResult[Literal["ok", "empty", "invalid_slot"]]:
        """Entferne **1** Einheit aus einem bestimmten Platz anhand seines nullbasierten Index. Gültige Indizes reichen von `0` bis `get_size() - 1`, einschließlich der durch Frachterweiterung hinzugefügten Plätze. Weggeworfene Gegenstände werden gelöscht und gelangen nicht zurück in die Welt. Wenn du Credits erhalten willst, verwende `shop.sell(item_id)`. Fester Ergebnisvertrag: `ItemResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.item_id`."""
        ...
    def drop_all(self, item_id: _str) -> CountResult[Literal["ok", "no_op"]]:
        """Entferne alle Einheiten von `item_id` aus dem Inventar. Wenn du Credits erhalten willst, verwende `shop.sell_all(item_id)`. Fester Ergebnisvertrag: `CountResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.count`."""
        ...
    def get_size(self) -> _int:
        """Aktuelle Anzahl der Inventarplätze. Das Inventar beginnt mit **36** Plätzen; Frachterweiterung kann die Anzahl Platz für Platz auf **60** erhöhen. Verwende diesen Wert, statt eine feste Anzahl von Plätzen im Skript einzutragen."""
        ...
    def get_used(self) -> _int:
        """Anzahl der belegten Plätze. `get_used() == get_size()` bedeutet, dass das Inventar voll ist."""
        ...
```

## `ItemCatalog`

```python
class ItemCatalog(Component):
    """Gegenstandskatalog: Ruft feste Angaben zur Identität jeder bekannten Gegenstands-ID ab. Verwende `get_component(\"item_catalog\")`, wenn ein Skript einen Gegenstand einordnen soll, ohne ein eigenes Datenarchiv zu führen."""
    name: _str
    def lookup(self, item_id: _str) -> ItemInfo | None:
        """Gibt ein `ItemInfo` mit `.id`, `.name`, `.category`, `.stackable`, `.biome`, `.rarity` und `.production_tier` zurück. Die Kategorien unterscheiden `\"mineral\"`, `\"refined\"`, `\"crafted\"`, `\"agriculture\"`, `\"life_form\"`, `\"field_resource\"`, `\"biology_sample\"`, `\"reagent\"`, `\"equipment\"`, `\"module\"`, `\"portable\"`, `\"upgrade_pack\"` und `\"construction_kit\"`. Bei Ausgangsmaterialien ist die Produktionsstufe `None`; Biome und Seltenheit sind `None`, wenn sie nicht zutreffen. Eine unbekannte Gegenstands-ID liefert `None`."""
        ...
```

## `ItemInfo`

```python
class ItemInfo:
    """item_catalog.lookup(item_id)"""
    id: _str
    name: _str
    category: Literal["mineral", "refined", "crafted", "agriculture", "life_form", "field_resource", "biology_sample", "reagent", "equipment", "module", "portable", "upgrade_pack", "construction_kit"]
    stackable: _bool
    biome: Literal["frozen", "coastal", "geothermal", "volcanic", "deep"] | None
    rarity: Literal["common", "uncommon", "rare", "legendary"] | None
    production_tier: _int | None
```

## `ItemStack`

```python
class ItemStack:
    """InputSlot.stacks(), VehicleInputSlot.stacks(), OutputSlot.stacks(), PickupOutputSlot.stacks(), Cargo.stacks(), Bin.stacks, storage_bin.stacks(), warehouse.stacks()"""
    id: _str
    count: _int
    properties: ItemProperties | None
```

## `LargeWarehouse`

```python
class LargeWarehouse(Component):
    """Großes Lagerhaus: Hochregaldepot für mehrere Materialien mit 15 materialgebundenen Plätzen zu je 2.000 (insgesamt 30.000). Groß genug, um einen vollständigen biologischen Katalog vorzuhalten."""
    name: _str
    outpost: OutpostRef
    def count(self, item_id: _str) -> _int:
        """Anzahl der Einheiten von `item_id` in allen Lagerplätzen. Gibt **0** zurück, wenn kein Lagerplatz den Gegenstand enthält. Inventar, Lagerbehälter und Bleibehälter bieten dieselbe Abfrage. `wh.count(\"iron_ore\")`."""
        ...
    def total(self) -> _int:
        """Gesamtzahl der Einheiten in allen Lagerplätzen, über sämtliche Materialien hinweg. Verwende für ein einzelnes Material `count(item_id)`."""
        ...
    def capacity(self) -> _int:
        """Gesamtkapazität aller physischen Lagerplätze. Ein Lagerhaus gibt **10.000** zurück (**5** × **2.000**), ein Großes Lagerhaus **30.000** (**15** × **2.000**). Frage diesen Wert ab, statt eine Ausbaustufe fest im Code zu hinterlegen."""
        ...
    def fill_percent(self) -> _float:
        """Füllstand des gesamten Lagerhauses als Anteil zwischen **0-1**: `total() / capacity()`."""
        ...
    def is_empty(self) -> _bool:
        """`True`, wenn alle Lagerplätze leer sind."""
        ...
    def materials(self) -> _list[_str]:
        """Liste der IDs aktuell gelagerter Gegenstände (ein Eintrag pro Material, von dem Einheiten in einem Lagerplatz liegen). Durchlaufe sie mit `for m in wh.materials():`."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Listet die in allen physischen Lagerplätzen gelagerten Gegenstandsvarianten als `ItemStack`-Werte auf. Gegenstände mit derselben ID, aber unterschiedlichen Eigenschaften belegen getrennte Lagerplätze. Rufe die Methode erneut auf, wenn du den aktuellen Inhalt brauchst."""
        ...
    def space_for(self, item_id: _str, properties: ItemProperties | None = ...) -> _int:
        """Wie viele weitere Einheiten einer bestimmten Gegenstandsvariante **im Moment** Platz haben. Berücksichtigt freien Platz in Lagerplätzen mit identischer Variante sowie alle leeren Lagerplätze. Lass `properties` bei gewöhnlichen Gegenständen ohne Eigenschaften weg oder übergib das vollständige von `stacks()` zurückgegebene `.properties`-dict. Freier Platz für eine Variante mit anderen Eigenschaften zählt nie mit."""
        ...
    def has_space(self, item_id: _str, amount: _int, properties: ItemProperties | None = ...) -> _bool:
        """`True`, wenn mindestens `amount` weitere ganze Einheiten genau dieser Gegenstandsvariante Platz haben. Lass `properties` bei Gegenständen ohne Eigenschaften weg oder übergib das vollständige Eigenschafts-dict. Prüfe dies vor einem Transfer, um Teiltransfers zu vermeiden."""
        ...
    def slots(self) -> _list[WarehouseSlot]:
        """Alle physischen Lagerplätze als `WarehouseSlot`-Datensätze mit `.index`, `.item`, `.count`, `.capacity` und `.properties`. Varianten mit unterschiedlichen Eigenschaften belegen getrennte Lagerplätze."""
        ...
    def compact(self) -> TransferResult[Literal["ok", "already_compact", "research_required", "busy", "source_under_construction", "source_changed", "slots_full", "target_full"]]:
        """Erfordert die Forschung **Automatische Zuführungen**. Fasst jede Gegenstandsvariante in so wenigen Lagerplätzen des Lagerhauses wie möglich zusammen. Die kleinsten überzähligen Stapel werden in größere kompatible Stapel verschoben, um den physischen Aufwand zu minimieren. Gegenstände mit gleicher ID, aber unterschiedlichen Eigenschaften bleiben stets getrennt. Der Aufruf wartet eine Zeit, die proportional zur Anzahl der umgelagerten Einheiten ist, und sperrt dieses Lagerhaus für die Dauer des Zyklus als Materialendpunkt. Porttransfers und manuelle Biologieaktionen über dieses Lagerhaus warten, bis der Zyklus abgeschlossen ist. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def transfer_to(self, target: _str, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "target_missing", "unsupported_target", "same_storage", "target_not_local", "source_under_construction", "source_wrong_material", "source_empty", "source_changed", "target_under_construction", "target_wrong_material", "hot_cargo_requires_cask", "cask_accepts_hot_only", "slots_full", "target_full", "target_changed"]]:
        """Erfordert die Forschung **Automatische Zuführungen**. Verschiebe bis zu `count` ganze Einheiten von `item_id` aus diesem Lager zu einem anderen Lagerbehälter, einem Lagerhaus, einem großen Lagerhaus, einem Bleibehälter oder dem Inventar. Übergib den Anzeigenamen oder die Instanz-ID eines Lagergebäudes oder `\"inventory\"`. Das Inventar kann nur in **Nocturna Base** teilnehmen. Der Aufruf wartet, bis der Zuführzyklus des physischen Lagers abgeschlossen ist; alle beteiligten Lagergebäude bleiben währenddessen beschäftigt. Die genauen Gegenstandseigenschaften bleiben erhalten; mit den optionalen Parametern `properties` und `property_match` wählst du eine Variante aus. Das aufrufende Skript kann überall laufen, aber Fracht überschreitet bei dieser Methode keine Außenpostengrenzen. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
```

## `LeadCask`

```python
class LeadCask(Component):
    """Bleibehälter: Abgeschirmter stationärer Lagerort für radioaktive Fracht. Drohnen legen Rohuran darin ab, der Brennstofffertiger entnimmt es und gibt fertige Brennstäbe zurück, und der Reaktor bezieht daraus seinen Brennstoff."""
    name: _str
    outpost: OutpostRef
    def count(self, item_id: _str) -> _int:
        """Anzahl der derzeit im Bleibehälter gelagerten Einheiten von `item_id`. Gibt **0** zurück, wenn der Behälter leer oder auf den anderen heißen Gegenstand festgelegt ist. Inventar, Lagerbehälter und Lagerhäuser bieten dieselbe Abfrage `count(item_id)`."""
        ...
    def fill_percent(self) -> _float:
        """Füllstand als Anteil von **0–1**. Behalte deine strategische Reserve im Blick."""
        ...
    def capacity(self) -> _int:
        """Maximale Anzahl heißer Einheiten (**100**)."""
        ...
    def material(self) -> Literal["", "raw_uranium", "fuel_rod"]:
        """Material, auf das der Behälter festgelegt ist: `\"raw_uranium\"`, `\"fuel_rod\"` oder leer. Wie jeder Lagerbehälter nimmt er jeweils nur ein Material auf."""
        ...
    def transfer_to(self, target: _str, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "target_missing", "unsupported_target", "same_storage", "target_not_local", "source_under_construction", "source_wrong_material", "source_empty", "source_changed", "target_under_construction", "target_wrong_material", "hot_cargo_requires_cask", "cask_accepts_hot_only", "slots_full", "target_full", "target_changed"]]:
        """Erfordert die Forschung **Automatische Zuführungen**. Verschiebe bis zu `count` ganze Einheiten von `item_id` aus diesem Lager zu einem anderen Lagerbehälter, einem Lagerhaus, einem großen Lagerhaus, einem Bleibehälter oder dem Inventar. Übergib den Anzeigenamen oder die Instanz-ID eines Lagergebäudes oder `\"inventory\"`. Das Inventar kann nur in **Nocturna Base** teilnehmen. Der Aufruf wartet, bis der Zuführzyklus des physischen Lagers abgeschlossen ist; alle beteiligten Lagergebäude bleiben währenddessen beschäftigt. Die genauen Gegenstandseigenschaften bleiben erhalten; mit den optionalen Parametern `properties` und `property_match` wählst du eine Variante aus. Das aufrufende Skript kann überall laufen, aber Fracht überschreitet bei dieser Methode keine Außenpostengrenzen. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
```

## `LiquidTank`

```python
class LiquidTank(Component):
    """Flüssigkeitstank: Passiver Puffer, der eine beliebige einzelne Flüssigkeit aufnimmt: Wasser, Öl oder eine Biom-Essenz. Er legt sich auf die erste eingeleitete Flüssigkeit fest."""
    name: _str
    outpost: OutpostRef
    def fluid(self) -> Literal["", "water", "oil", "frozen_essence", "coastal_essence", "geothermal_essence", "volcanic_essence", "deep_essence", "brine", "raw_cryofluid", "cryofluid", "raw_quicksilver", "quicksilver"]:
        """Die festgelegte Flüssigkeits-ID (z. B. `\"water\"`, `\"oil\"`, `\"frozen_essence\"`) oder `\"\"`, solange der Tank leer ist. Der Tank legt sich auf die erste aufgenommene Flüssigkeit fest und nimmt bis zur vollständigen Entleerung auf **0** nur diese Flüssigkeit auf. Danach kann er sich auf eine andere festlegen."""
        ...
    def level(self) -> _float:
        """Aktuell gespeicherte Flüssigkeitsmenge in Tonnen, von **0** bis `capacity()`. Bei **0** ist der Tank nicht mehr auf eine Flüssigkeit festgelegt und kann als Nächstes eine andere aufnehmen."""
        ...
    def capacity(self) -> _float:
        """Maximale Füllmenge dieses Tanks in Tonnen. Der Wert lässt sich abfragen und muss nicht fest ins Skript geschrieben werden. Verwende ihn mit `level()` oder `fill_pct()`, um Grenzwerte zu prüfen."""
        ...
    def fill_pct(self) -> _float:
        """Füllanteil (**0,0–1,0**), eine Kurzform für `level() / capacity()`. Häufiger Grenzwert in Skripten zur Versorgungssteuerung."""
        ...
    def inflow_rate(self) -> _float:
        """Zufließende Flüssigkeit in t/h. **0** = kein Zufluss von vorgelagerten Quellen."""
        ...
    def outflow_rate(self) -> _float:
        """Abfließende Flüssigkeit in t/h. **0** = kein Verbrauch durch nachgelagerte Abnehmer."""
        ...
    def is_full(self) -> _bool:
        """`True`, wenn `level() == capacity()`; der Rückstau bremst die vorgelagerte Quelle."""
        ...
    def is_empty(self) -> _bool:
        """`True`, wenn `level() == 0`; der Tank ist nicht auf eine Flüssigkeit festgelegt und nachgelagerte Abnehmer erhalten keinen Nachschub."""
        ...
    liquid_in: FluidPort
    liquid_out: FluidPort
    water_in: FluidPort
    water_out: FluidPort
    oil_in: FluidPort
    oil_out: FluidPort
    frozen_essence_in: FluidPort
    frozen_essence_out: FluidPort
    coastal_essence_in: FluidPort
    coastal_essence_out: FluidPort
    geothermal_essence_in: FluidPort
    geothermal_essence_out: FluidPort
    volcanic_essence_in: FluidPort
    volcanic_essence_out: FluidPort
    deep_essence_in: FluidPort
    deep_essence_out: FluidPort
    brine_in: FluidPort
    brine_out: FluidPort
    raw_cryofluid_in: FluidPort
    raw_cryofluid_out: FluidPort
    cryofluid_in: FluidPort
    cryofluid_out: FluidPort
    raw_quicksilver_in: FluidPort
    raw_quicksilver_out: FluidPort
    quicksilver_in: FluidPort
    quicksilver_out: FluidPort
```

## `MountSlot`

```python
class MountSlot:
    """modules() bei einem Rover, Pionier oder einer Drohne"""
    index: _int
    type: Literal["nav", "sonar_basic", "drill_basic", "universal", "thruster", "drone_module"]
    module_id: _str | None
    internal_count: _int
    internal_items: _list[_str | None]
```

## `OutputSlot`

```python
class OutputSlot:
    """self.output (Maschinen mit Ausgabeanschluss)"""
    def connect(self, name: _str) -> ActionResult[Literal["ok", "not_found", "not_local", "same_endpoint", "unsupported_target", "target_is_vehicle"]]:
        """Lege ein kompatibles Ziel für Gegenstände über dessen dauerhafte ID oder Anzeigenamen fest. Zwei stationäre Endpunkte müssen zum selben Außenposten gehören. Ein Rover oder Pionier ist von jedem Außenposten aus erreichbar, aber nur, solange er im Versorgungsbereich dieser Maschine parkt. Die Fracht einer Drohne wird über ihr Drohnendepot transportiert. `\"inventory\"` ist nur dann ein Frachtziel, wenn sich der Endpunkt an der Nocturna Base befindet. Stationäre Anschlüsse entfernter Außenposten nutzen örtliche Lagerbehälter, Lagerhäuser oder Maschineneingänge. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def disconnect(self) -> ActionResult[Literal["ok"]]:
        """Trennt die aktuelle Verbindung zum Ziel. Gepufferte Erzeugnisse werden dabei weder bewegt noch verworfen. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def connected_to(self) -> _str:
        """Anzeigename des aktuell verbundenen Ziels oder eine leere Zeichenfolge."""
        ...
    def connected_id(self) -> _str:
        """Stabile ID des aktuell verbundenen Ziels oder eine leere Zeichenfolge. `connect()` akzeptiert eine ID oder einen Anzeigenamen, aber dieser Wert ist die aufgelöste stabile ID. Vergleiche ihn mit der stabilen ID des Ziels; `connected_to()` liefert dessen änderbaren Anzeigenamen."""
        ...
    def send(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "no_connection", "inventory_not_local", "same_endpoint", "source_wrong_material", "source_empty", "source_changed", "target_missing", "target_under_construction", "target_is_vehicle", "target_not_local", "not_at_target", "unsupported_target", "target_wrong_material", "wrong_biome", "target_unconfigured", "mixed_materials", "hot_cargo_requires_cask", "cask_accepts_hot_only", "order_item_not_required", "order_slots_full", "order_fulfilled", "slots_full", "target_full", "target_complete", "target_changed", "same_vehicle", "source_moving", "target_moving", "out_of_range"]]:
        """Sende bis zu `count` ganze Einheiten von `item_id` an das verbundene Ziel. Ein Eigenschaften-dict wählt standardmäßig Stapel aus, die die angegebenen Eigenschaften enthalten. Übergib `\"exact\"` als viertes Argument, um nur Gegenstände mit genau diesen Eigenschaften auszuwählen; `None, \"exact\"` wählt ausschließlich Gegenstände ohne Eigenschaften aus. `\"any\"` ignoriert Eigenschaften. Die genauen Eigenschaften der gesendeten Gegenstände bleiben erhalten. Der Aufruf wartet automatisch; die Wartezeit ist proportional zur Anzahl der übertragenen Einheiten. Die Nutzung erfordert die Erforschung von Automatischen Zuführungen. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def count(self) -> _int:
        """Gesamtzahl der Einheiten, die sich derzeit im Puffer dieses Anschlusses befinden."""
        ...
    def capacity(self) -> _int:
        """Maximale Anzahl an Einheiten, die der Puffer dieses Anschlusses aufnehmen kann."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Liste von Momentaufnahmen der derzeit gepufferten `ItemStack`-Werte, getrennt nach Eigenschaften. Verwende `.properties`, um Varianten vor `send()` zu prüfen und auszuwählen."""
        ...
```

## `PickupOutputSlot`

```python
class PickupOutputSlot:
    """self.output bei Wasserpumpen und Bergbaubohrern im Gelände"""
    def count(self) -> _int:
        """Gesamtzahl der Gegenstandseinheiten, die auf die Abholung durch einen Transporter warten."""
        ...
    def capacity(self) -> _int:
        """Maximale Anzahl an Gegenstandseinheiten, die dieser Abholvorrat aufnehmen kann."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Momentaufnahme der Liste von `ItemStack`-Werten mit unterschiedlichen Eigenschaften, die auf die Abholung durch einen Transporter warten."""
        ...
```

## `ShopItem`

```python
class ShopItem:
    """shop.get_catalogue()"""
    id: _str
    name: _str
    cost: _int
```

## `Slot`

```python
class Slot:
    """inventory.get_slots()"""
    slot: _int
    id: _str
    name: _str
    value: _float
    count: _int
    properties: ItemProperties | None
    genes: _list[_str]
    glow: _list[_int] | None
    spliced: _bool
```

## `SteamTurbine`

```python
class SteamTurbine(Component):
    """Dampfturbine: Erzeugt bis zu 108 W aus 90 t/h Dampf. Der vom Skript gesteuerte Leistungsregler skaliert Verbrauch und Stromerzeugung gleichermaßen."""
    name: _str
    outpost: OutpostRef
    def power_output(self) -> _float:
        """Im letzten Stromtick ins Netz eingespeiste Leistung in Watt. Sie hängt von `throttle()` und der tatsächlich verfügbaren Dampfmenge ab. Bei Leerlauf oder Dampfmangel beträgt sie **0**. Der Wert wird einmal pro Stromtick aktualisiert: Ein neuer Aufruf von `set_throttle(...)` wirkt sich erst im nächsten Tick aus, nicht im selben. Nutze den Wert für Live-Übersichten oder vergleiche ihn mit dem Sauerstoff- und Wärmeverbrauch, um die Strombilanz auszugleichen."""
        ...
    def efficiency(self) -> _float:
        """Anteil des vom Regler angeforderten Dampfs, der im letzten Stromtick tatsächlich entnommen wurde (**0.0-1.0**). **1.0** bedeutet, dass die Turbine den gesamten angeforderten Dampf erhalten hat. Ein Wert unter **1** weist auf Dampfmangel hin: Der Schlot ist inaktiv oder die vorgelagerte Versorgung reicht nicht aus. Nutze den Wert, um zu erkennen, ob die Turbine genug Dampf erhält."""
        ...
    def is_stalled(self) -> _bool:
        """`True`, wenn der Regler aufgedreht ist, aber kein Dampf ankommt (der Schlot ist inaktiv oder die Dampfleitung ist getrennt). Prüfe zur Diagnose `self.steam_in.level()` auf der Zufuhrseite und die Schlotphase des speisenden Dampfsammlers. Es gibt keinen Wasserausgang mehr, an dem sich etwas stauen könnte."""
        ...
    def throttle(self) -> _float:
        """Aktuelle Reglerstellung (**0.0-1.0**). **0** bedeutet aus: Die Turbine verbraucht keinen Dampf und erzeugt keinen Strom. Das ist der Standardwert; bis zum Aufruf von `set_throttle()` bleibt sie im Leerlauf. Höhere Werte erhöhen Dampfverbrauch und Stromerzeugung bis zum Maximum bei **1.0**. Dieser schreibgeschützte Wert zeigt die zuletzt mit `set_throttle()` übernommene Einstellung."""
        ...
    def set_throttle(self, t: _float) -> ActionResult[Literal["ok"]]:
        """Stelle den Leistungsregler der Turbine ein (**0.0-1.0**; Werte außerhalb werden auf die jeweilige Grenze gesetzt). **0** schaltet die Turbine aus: Sie verbraucht keinen Dampf und erzeugt keinen Strom. Bei **1.0** nutzt sie den vollen Dampfstrom für die maximale Leistung. Mit `self.set_throttle(1.0)` läuft sie auf voller Leistung. Drehe den Regler zurück, wenn der Dampfpuffer leer wird, damit die Turbine nicht ohne Dampf läuft, zum Beispiel: `if self.steam_in.level() < 5: self.set_throttle(0.3)`. Dieser vom Skript gesetzte Sollwert wird auf **0** zurückgesetzt, wenn das Skript gestoppt wird, endet oder einen Fehler auslöst. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    steam_in: FluidPort
    def peek_command(self) -> ScriptCommand | None:
        """Liest den nächsten Befehl in der Warteschlange, ohne ihn zu entfernen. Nutze dies, wenn du einen Befehl prüfen möchtest, bevor du entscheidest, ob du ihn verarbeitest."""
        ...
    def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
        """Entnimmt den ältesten Befehl aus dem Postfach dieses Skripts. Fester Ergebnisvertrag: `CommandResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.command`."""
        ...
    def command_count(self) -> _int:
        """Gibt zurück, wie viele Befehle im Postfach dieses Skripts warten."""
        ...
    def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
        """Entfernt alle wartenden Befehle für dieses Skript. Fester Ergebnisvertrag: `CountResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.count`."""
        ...
```

## `StorageBin`

```python
class StorageBin(Component):
    """Lagerbehälter: Ein passiver Behälter an der Basis, der jeweils nur ein Material lagert. Die erste Einlagerung legt fest, welches Material er aufnimmt; diese Bindung wird erst aufgehoben, wenn er vollständig geleert ist. Andere Skripte können seinen Inhalt abfragen und verschieben."""
    name: _str
    outpost: OutpostRef
    def count(self, item_id: _str) -> _int:
        """Anzahl der derzeit gelagerten Einheiten von `item_id`. Gibt **0** zurück, wenn der Behälter leer oder auf einen anderen Gegenstand festgelegt ist. Inventar, Lagerhäuser und Bleibehälter bieten dieselbe Abfrage `count(item_id)`."""
        ...
    def get_capacity(self) -> _int:
        """Maximale Kapazität des Behälters in Einheiten, standardmäßig **500**. Der Wert ist abfragbar statt fest einprogrammiert, damit eine spätere Anpassung keine Skripte beschädigt. Mit `fill_percent()` erhältst du den aktuellen Füllgrad."""
        ...
    def get_material(self) -> _str:
        """Die aktuell festgelegte Material-ID oder eine leere Zeichenfolge, wenn der Behälter leer ist und bei der nächsten Einlagerung jedes Material aufnehmen kann. Prüfe damit das Material vor dem Weiterleiten von Transfers: `if bin.get_material() in (\"\", \"iron_ore\"): # safe to deposit iron`."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Listet die in diesem Behälter gelagerten Gegenstandsvarianten als `ItemStack`-Werte auf. Gegenstände mit derselben ID, aber unterschiedlichen Eigenschaften bleiben getrennt. Rufe die Methode erneut auf, wenn du den aktuellen Inhalt brauchst."""
        ...
    def is_empty(self) -> _bool:
        """`True`, wenn der Behälter nichts enthält. Ein leerer Behälter ist auf kein Material festgelegt; bei der nächsten Einlagerung kann jedes Material den Platz belegen. Das unterscheidet sich von `has_space(0)`, das immer `True` ergibt."""
        ...
    def has_space(self, amount: _int) -> _bool:
        """`True`, wenn im Behälter Platz für `amount` weitere Einheiten ist, wobei die Anzahl ganzzahlig sein muss. Prüfe das vor einem Transfer, um Teilmengen zu vermeiden."""
        ...
    def space(self) -> _int:
        """Noch freie Kapazität in Einheiten. Damit lässt sich ein Transfer mit einem Aufruf bemessen: `n = bin.space()`, dann bis zu `n` Einheiten verschieben."""
        ...
    def fill_percent(self) -> _float:
        """Füllgrad als Wert zwischen **0-1**. Ein häufiger Schwellenwert für Skripte zum Umverteilen: `if bin.fill_percent() < 0.2: # route more here`."""
        ...
    def transfer_from_inventory(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "inventory_not_local", "source_empty", "source_changed", "target_wrong_material", "hot_cargo_requires_cask", "target_full", "target_changed"]]:
        """Erfordert die Forschung **Automatische Zuführungen** und einen Lagerbehälter am Heimat-Außenposten. Verschiebt bis zu `count` ganze Einheiten von `item_id` aus dem Inventar in den Behälter und erhält dabei alle Eigenschaften exakt. Der Aufruf wartet, bis der Zuführungszyklus abgeschlossen ist; währenddessen kann der Behälter keinen weiteren Transfer starten. Ein dict mit Eigenschaften wählt standardmäßig anhand der angegebenen Eigenschaften eine Teilmenge aus. Übergib `\"exact\"` als `property_match`, um die vollständige Identität abzugleichen, einschließlich `None` bei Gegenständen ohne Eigenschaften. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def transfer_to_inventory(self, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "source_empty", "source_changed", "inventory_not_local", "target_full", "target_changed"]]:
        """Erfordert die Forschung **Automatische Zuführungen** und einen Lagerbehälter am Heimat-Außenposten. Verschiebt bis zu `count` ganze Einheiten zurück ins Inventar und erhält dabei alle Eigenschaften exakt. Der Aufruf wartet, bis der Zuführungszyklus abgeschlossen ist; währenddessen kann der Behälter keinen weiteren Transfer starten. Ein dict mit Eigenschaften wählt standardmäßig anhand der angegebenen Eigenschaften eine Teilmenge aus. Übergib `\"exact\"` als `property_match`, um die vollständige Identität abzugleichen, einschließlich `None` bei Gegenständen ohne Eigenschaften. Wenn der Behälter vollständig geleert wird, verliert er seine Festlegung auf eine Gegenstands-ID. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def transfer_to(self, target: _str, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "target_missing", "unsupported_target", "same_storage", "target_not_local", "source_under_construction", "source_wrong_material", "source_empty", "source_changed", "target_under_construction", "target_wrong_material", "hot_cargo_requires_cask", "cask_accepts_hot_only", "slots_full", "target_full", "target_changed"]]:
        """Erfordert die Forschung **Automatische Zuführungen**. Verschiebe bis zu `count` ganze Einheiten von `item_id` aus diesem Lager zu einem anderen Lagerbehälter, einem Lagerhaus, einem großen Lagerhaus, einem Bleibehälter oder dem Inventar. Übergib den Anzeigenamen oder die Instanz-ID eines Lagergebäudes oder `\"inventory\"`. Das Inventar kann nur in **Nocturna Base** teilnehmen. Der Aufruf wartet, bis der Zuführzyklus des physischen Lagers abgeschlossen ist; alle beteiligten Lagergebäude bleiben währenddessen beschäftigt. Die genauen Gegenstandseigenschaften bleiben erhalten; mit den optionalen Parametern `properties` und `property_match` wählst du eine Variante aus. Das aufrufende Skript kann überall laufen, aber Fracht überschreitet bei dieser Methode keine Außenpostengrenzen. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
```

## `VehicleInputSlot`

```python
class VehicleInputSlot:
    """self.input bei Rover und Pionier"""
    def connect(self, name: _str) -> ActionResult[Literal["ok", "not_found", "same_endpoint", "unsupported_source", "source_is_vehicle"]]:
        """Lege eine kompatible Frachtquelle über ihre beständige ID oder ihren Anzeigenamen fest. Ein Rover oder Pionier muss innerhalb des Servicebereichs einer stationären Quelle parken. Vorräte von Feld-Bergbaubohrern und Wasserpumpen können von Transportfahrzeugen abgeholt werden. Für eine Übergabe zwischen Fahrzeugen müssen beide Fahrzeuge stillstehen und nahe beieinander sein. `\"inventory\"` ist nur verfügbar, wenn das Fahrzeug an der Nocturna-Basis parkt; entfernte Außenposten nutzen ihre örtlichen Lagerbehälter, Lagerhäuser oder Maschinenpuffer. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def disconnect(self) -> ActionResult[Literal["ok"]]:
        """Trenne die Verbindung zur aktuellen Frachtquelle. Dabei wird keine Fracht bewegt oder verworfen. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def connected_to(self) -> _str:
        """Anzeigename der aktuell verbundenen Frachtquelle oder eine leere Zeichenfolge."""
        ...
    def connected_id(self) -> _str:
        """Beständige ID der aktuell verbundenen Frachtquelle oder eine leere Zeichenfolge. `connect()` akzeptiert eine ID oder einen Anzeigenamen. Vergleiche daher mit diesem Wert, wenn die Identität auch nach einer Umbenennung erkennbar bleiben muss."""
        ...
    def take(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "no_connection", "inventory_not_local", "same_endpoint", "source_missing", "source_under_construction", "source_is_vehicle", "source_not_local", "not_at_source", "unsupported_source", "source_wrong_material", "source_empty", "source_reserved", "source_changed", "buffer_full", "slots_full", "target_wrong_material", "wrong_biome", "target_unconfigured", "hot_cargo_requires_cask", "order_item_not_required", "order_slots_full", "order_fulfilled", "target_full", "target_complete", "target_changed", "same_vehicle", "source_moving", "target_moving", "out_of_range"]]:
        """Lade aus der verbundenen Quelle bis zu `count` Einheiten von `item_id` in den Frachtraum des Fahrzeugs; die Anzahl muss ganzzahlig sein. Ein Eigenschaften-dict wählt standardmäßig Stapel aus, die alle angegebenen Eigenschaften enthalten. Übergib `\"exact\"` als viertes Argument, um nur eine vollständige Übereinstimmung auszuwählen; `None, \"exact\"` wählt nur Gegenstände ohne Eigenschaften aus. `\"any\"` ignoriert Eigenschaften. Die genauen Eigenschaften aus der Quelle bleiben erhalten. Die Übertragung wartet automatisch für eine Dauer, die proportional zur Anzahl der bewegten Einheiten ist, und erfordert die Forschung Automatische Zuführungen. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def count(self) -> _int:
        """Gesamtzahl der derzeit im Frachtraum des Fahrzeugs transportierten Einheiten."""
        ...
    def capacity(self) -> _int:
        """Maximale Anzahl an Einheiten, die der Frachtraum des Fahrzeugs aufnehmen kann."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Momentaufnahme der Liste aktuell transportierter `ItemStack`-Werte mit unterschiedlichen Eigenschaften. Zwei Einträge können dieselbe ID haben, wenn sich ihre Eigenschaften unterscheiden."""
        ...
```

## `Warehouse`

```python
class Warehouse(Component):
    """Lagerhaus: Massenlager für mehrere Materialien mit 5 materialgebundenen Plätzen zu je 2.000 (insgesamt 10.000). Nimmt Transportmengen im Drohnenmaßstab auf."""
    name: _str
    outpost: OutpostRef
    def count(self, item_id: _str) -> _int:
        """Anzahl der Einheiten von `item_id` in allen Lagerplätzen. Gibt **0** zurück, wenn kein Lagerplatz den Gegenstand enthält. Inventar, Lagerbehälter und Bleibehälter bieten dieselbe Abfrage. `wh.count(\"iron_ore\")`."""
        ...
    def total(self) -> _int:
        """Gesamtzahl der Einheiten in allen Lagerplätzen, über sämtliche Materialien hinweg. Verwende für ein einzelnes Material `count(item_id)`."""
        ...
    def capacity(self) -> _int:
        """Gesamtkapazität aller physischen Lagerplätze. Ein Lagerhaus gibt **10.000** zurück (**5** × **2.000**), ein Großes Lagerhaus **30.000** (**15** × **2.000**). Frage diesen Wert ab, statt eine Ausbaustufe fest im Code zu hinterlegen."""
        ...
    def fill_percent(self) -> _float:
        """Füllstand des gesamten Lagerhauses als Anteil zwischen **0-1**: `total() / capacity()`."""
        ...
    def is_empty(self) -> _bool:
        """`True`, wenn alle Lagerplätze leer sind."""
        ...
    def materials(self) -> _list[_str]:
        """Liste der IDs aktuell gelagerter Gegenstände (ein Eintrag pro Material, von dem Einheiten in einem Lagerplatz liegen). Durchlaufe sie mit `for m in wh.materials():`."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Listet die in allen physischen Lagerplätzen gelagerten Gegenstandsvarianten als `ItemStack`-Werte auf. Gegenstände mit derselben ID, aber unterschiedlichen Eigenschaften belegen getrennte Lagerplätze. Rufe die Methode erneut auf, wenn du den aktuellen Inhalt brauchst."""
        ...
    def space_for(self, item_id: _str, properties: ItemProperties | None = ...) -> _int:
        """Wie viele weitere Einheiten einer bestimmten Gegenstandsvariante **im Moment** Platz haben. Berücksichtigt freien Platz in Lagerplätzen mit identischer Variante sowie alle leeren Lagerplätze. Lass `properties` bei gewöhnlichen Gegenständen ohne Eigenschaften weg oder übergib das vollständige von `stacks()` zurückgegebene `.properties`-dict. Freier Platz für eine Variante mit anderen Eigenschaften zählt nie mit."""
        ...
    def has_space(self, item_id: _str, amount: _int, properties: ItemProperties | None = ...) -> _bool:
        """`True`, wenn mindestens `amount` weitere ganze Einheiten genau dieser Gegenstandsvariante Platz haben. Lass `properties` bei Gegenständen ohne Eigenschaften weg oder übergib das vollständige Eigenschafts-dict. Prüfe dies vor einem Transfer, um Teiltransfers zu vermeiden."""
        ...
    def slots(self) -> _list[WarehouseSlot]:
        """Alle physischen Lagerplätze als `WarehouseSlot`-Datensätze mit `.index`, `.item`, `.count`, `.capacity` und `.properties`. Varianten mit unterschiedlichen Eigenschaften belegen getrennte Lagerplätze."""
        ...
    def compact(self) -> TransferResult[Literal["ok", "already_compact", "research_required", "busy", "source_under_construction", "source_changed", "slots_full", "target_full"]]:
        """Erfordert die Forschung **Automatische Zuführungen**. Fasst jede Gegenstandsvariante in so wenigen Lagerplätzen des Lagerhauses wie möglich zusammen. Die kleinsten überzähligen Stapel werden in größere kompatible Stapel verschoben, um den physischen Aufwand zu minimieren. Gegenstände mit gleicher ID, aber unterschiedlichen Eigenschaften bleiben stets getrennt. Der Aufruf wartet eine Zeit, die proportional zur Anzahl der umgelagerten Einheiten ist, und sperrt dieses Lagerhaus für die Dauer des Zyklus als Materialendpunkt. Porttransfers und manuelle Biologieaktionen über dieses Lagerhaus warten, bis der Zyklus abgeschlossen ist. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
    def transfer_to(self, target: _str, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "target_missing", "unsupported_target", "same_storage", "target_not_local", "source_under_construction", "source_wrong_material", "source_empty", "source_changed", "target_under_construction", "target_wrong_material", "hot_cargo_requires_cask", "cask_accepts_hot_only", "slots_full", "target_full", "target_changed"]]:
        """Erfordert die Forschung **Automatische Zuführungen**. Verschiebe bis zu `count` ganze Einheiten von `item_id` aus diesem Lager zu einem anderen Lagerbehälter, einem Lagerhaus, einem großen Lagerhaus, einem Bleibehälter oder dem Inventar. Übergib den Anzeigenamen oder die Instanz-ID eines Lagergebäudes oder `\"inventory\"`. Das Inventar kann nur in **Nocturna Base** teilnehmen. Der Aufruf wartet, bis der Zuführzyklus des physischen Lagers abgeschlossen ist; alle beteiligten Lagergebäude bleiben währenddessen beschäftigt. Die genauen Gegenstandseigenschaften bleiben erhalten; mit den optionalen Parametern `properties` und `property_match` wählst du eine Variante aus. Das aufrufende Skript kann überall laufen, aber Fracht überschreitet bei dieser Methode keine Außenpostengrenzen. Fester Ergebnisvertrag: `TransferResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.requested` und `.moved`."""
        ...
```

## `WarehouseSlot`

```python
class WarehouseSlot:
    """warehouse.slots()"""
    index: _int
    item: _str
    count: _int
    capacity: _int
    properties: ItemProperties | None
```
