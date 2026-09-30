# Models: Vehicles, Modules, Harvester & Navigation Models

Granular data models and return types extracted from `__builtins__.pyi`.

## `ConstructorModule`

```python
class ConstructorModule:
    """self.constructor (Pionier)"""
    def execute(self, blueprint_id: _str) -> ActionResult[Literal["ok", "not_mounted", "not_found", "locked", "already_active", "busy", "wrong_position", "insufficient_materials", "paused_no_power", "cargo_present", "blocked", "paused", "canceled", "not_ready"]]:
        """Führe einen Bau- oder Rückbauplan aus dem Planungsmodus aus. Fahre den Pionier in Interaktionsreichweite von `blueprint.position` und übergib dann eine Bauplan-ID aus `get_component(\"construction_blueprint\").pending_constructions()`, `.active_constructions()` oder `.paused_constructions()`. Während die Feldaktion ausgeführt wird, gibt der Aufruf die Kontrolle vorübergehend ab. Ein Pionier führt jeweils nur eine Feldaktion aus. Das Stoppen des Skripts, Stromausfall, Verlassen der Baustelle, Rettung oder Entfernen des Konstruktionsmoduls pausieren bereits bezahlte Arbeiten, ohne Fortschritt oder Material zu verlieren. Der zuständige Pionier kann aktive Arbeiten wieder aufnehmen, auch nach dem Speichern und Laden; ein anderer Pionier kann einen zugewiesenen Auftrag nicht übernehmen. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
```

## `ConstructorModuleComponent`

```python
class ConstructorModuleComponent(Component):
    """Konstruktionsmodul: Ein ausschließlich für Pioniere bestimmtes Modul für Bau- und Abrisspläne aus dem Planungsmodus oder aus Skripten: Gas- und Flüssigkeitsrohre, Versorgungsbrücken, Stromleitungen, Außenposten, Pumpen, Dampfsammler, Sammler für exotisches Gas und Bergbaubohrer. Passt in einen `universal`-Steckplatz. Lade für Bauaufträge die benötigten Bausätze, Segmente oder Brückenteile in den Frachtraum des Pioniers, fahre in Interaktionsreichweite der Bauplanposition und rufe dann `execute(blueprint_id)` auf. Beim Abriss gelangt der zerlegte Bausatz oder das Segment in den Frachtraum des Pioniers. Maschinen innerhalb eines Außenpostens, einschließlich Drohneneinrichtungen, werden direkt aus dem Inventar aufgestellt und sind keine Aufträge für das Konstruktionsmodul."""
    name: _str
    def execute(self, blueprint_id: _str) -> ActionResult[Literal["ok", "not_mounted", "not_found", "locked", "already_active", "busy", "wrong_position", "insufficient_materials", "paused_no_power", "cargo_present", "blocked", "paused", "canceled", "not_ready"]]:
        """Nimm einen Bauauftrag aus der gemeinsamen Planungswarteschlange an und baue oder zerlege das Ziel. Planungsmodus und `get_component(\"construction_blueprint\")` erzeugen gleichwertige Aufträge. Fahre den Pionier zuerst in Interaktionsreichweite von `blueprint.position`; mit `get_component(\"construction_blueprint\").pending_constructions()` siehst du, welche Aufträge bereitstehen. Ein Pionier führt immer nur eine Arbeit im Gelände aus. Wird sein Skript gestoppt, fällt der Strom aus, verlässt er den Ort, wird er gerettet oder wird das Konstruktionsmodul entfernt, pausiert bereits bezahlte Arbeit, ohne dass Fortschritt oder Material verloren gehen. Setze denselben Auftrag anhand seiner ID aus `get_component(\"construction_blueprint\").paused_constructions()` fort. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
```

## `DrillModule`

```python
class DrillModule:
    """self.drill (Fahrzeuge)"""
    def mine(self) -> ActionResult[Literal["ok", "not_mounted", "not_at_site", "not_surveyed", "too_hard", "no_cargo_space", "no_power", "not_enough_power", "busy"]]:
        """Im Stillstand eine Einheit abbauen. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def hardness_limit(self) -> _int:
        """Maximale Mineralhärte, die dieser Bohrer abbauen kann (**1** beim einfachen, **3** beim Industriebohrer, **4** beim schweren Bohrer). Eine veraltete, zuvor gespeicherte Modulreferenz löst `ReferenceError` aus."""
        ...
    def speed_multiplier(self) -> _float:
        """Multiplikator für die Bohrzeit (**1.0** beim einfachen, **0.75** beim Industriebohrer, **0.6** beim schweren Bohrer: niedriger ist schneller). Eine veraltete, zuvor gespeicherte Modulreferenz löst `ReferenceError` aus."""
        ...
```

## `DrillModuleComponent`

```python
class DrillModuleComponent(Component):
    """Bohrmodul: Fördert Mineralien über `self.drill`. Jeder Bohrer kann Mineralien bis zu seiner Härtegrenze fördern: Der einfache Bohrer erreicht Härte **1** (Eisen, Silizium) mit **1,0×** Geschwindigkeit und **10 W**; der Industriebohrer erreicht **3** (zusätzlich Titan, Kobalt, Blei und Seltene Erden) mit **0,75×** und **20 W**; der schwere Bohrer erreicht **4** (zusätzlich Neutronium) mit **0,6×** und **30 W**. Es gibt keinen Bohrer für Härte 2: Titan und Kobalt werden vom Industriebohrer gefördert. Ohne montiertes Bohrmodul kann das Fahrzeug keine Mineralien fördern."""
    name: _str
    def mine(self) -> ActionResult[Literal["ok", "not_mounted", "not_at_site", "not_surveyed", "too_hard", "no_cargo_space", "no_power", "not_enough_power", "busy"]]:
        """Fördert **1** Einheit des Minerals am aktuellen Standort in den Frachtraum des Fahrzeugs. Der Abbau dauert `mineral_base_minutes × drill.speed_multiplier() / site_purity` Minuten Spielzeit; das Skript pausiert bis zum Abschluss. Grunddauer in Minuten: Eisen und Silizium **15**, Blei **18**, Titan und Kobalt **20**, Seltene Erden **25**, Neutronium **30**. Für `site_purity` gilt: **1** normal, **2** reichhaltig, **3** rein. Der Bohrer benötigt während des gesamten Abbaus Strom. Der Energieverbrauch pro Einheit entspricht daher seiner Leistung in Watt multipliziert mit der Abbaudauer: Wenn der einfache Bohrer (**10 W**) **15** Minuten lang abbaut, verbraucht er **2,5 Wh**. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def hardness_limit(self) -> _int:
        """Höchste Mineralhärte, die dieser Bohrer fördern kann."""
        ...
    def speed_multiplier(self) -> _float:
        """Zeitfaktor pro Einheit (niedriger = schneller)."""
        ...
```

## `DroneBattery`

```python
class DroneBattery:
    """self.battery (elektrische Drohnen)"""
    def level(self) -> _float:
        """Aktuelle Ladung aller montierten Batteriepacks in Wh. Löst `ReferenceError` aus, wenn diese Drohne keinen elektrischen Antrieb hat."""
        ...
    def capacity(self) -> _float:
        """Gesamte Ladekapazität in Wh. Löst `ReferenceError` aus, wenn diese Drohne keinen elektrischen Antrieb hat."""
        ...
    def percent(self) -> _float:
        """Ladung als Anteil zwischen **0-1** (`level / capacity`). Löst `ReferenceError` aus, wenn diese Drohne keinen elektrischen Antrieb hat."""
        ...
```

## `DroneLarge`

```python
class DroneLarge(Component):
    """Drohne (groß): Schwere Industriedrohne, 1 Triebwerk + 5 Module."""
    name: _str
    def go_to_station(self, name: _str) -> ActionResult[Literal["ok", "station_not_found", "out_of_range", "busy", "scrambled"]]:
        """Legt eine Route zum benannten Drohnendepot oder zur benannten Drohnenservicestation in die Warteschlange und kehrt sofort zurück, ohne das Andocken abzuwarten. Bei einer angenommenen Route mit verfügbarer Antriebsenergie wird sofort `\"traveling\"` gemeldet. Position und Andockstatus ändern sich erst, wenn die Simulation fortschreitet. Stoppen, Abschluss oder Fehler brechen den Flug ab und löschen die Route. Vergleiche `current_station()` mit der stabilen ID des Ziels, um die Ankunft zu bestätigen. Der Wechsel zwischen Drohnengebäuden innerhalb desselben Außenpostens erfolgt vor Ort und verbraucht keinen Flugtreibstoff. An Drohnenservicestationen können Drohnen auch ohne Stromversorgung ankommen und parken. Ist ein Drohnendepot voll, bleibt die Drohne mit `\"waiting_bay\"` unangedockt, bis ein Stellplatz frei wird. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def undock(self) -> ActionResult[Literal["ok", "not_docked", "busy"]]:
        """Gibt den Stellplatz an der Station frei, ohne irgendwohin zu fliegen. Die Drohne behält ihre exakte Weltposition, Fracht, Module, ihren Treibstoff und ihre Belastung. Eine ruhende Route wird gelöscht, der Schub auf **0** zurückgesetzt und die Drohne wird inaktiv. Bei einer laufenden Bergung oder einem laufenden beziehungsweise vorgemerkten Lade- oder Tankauftrag der Drohnenservicestation behält die Station die Kontrolle, bis ihre Arbeit abgeschlossen ist. Verwende `go_to_station(...)`, wenn die Drohne erneut einen Stellplatz belegen soll. Nur für die eigene Drohne. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def go_to_drill(self, name: _str) -> ActionResult[Literal["ok", "drill_not_found", "out_of_range", "busy", "scrambled"]]:
        """Fliegt zu einem benannten Bergbaubohrer im Feld, um Erz abzuholen. Für den Transport ist kein Feldmodul erforderlich. Bei einer angenommenen Route mit verfügbarer Antriebsenergie wird sofort `\"traveling\"` gemeldet. Danach fliegt die Drohne geradeaus und schwebt bei der Ankunft auf der Stelle. Vergleiche `current_drill()` mit der stabilen ID des Ziels, um zu bestätigen, dass Fracht geladen werden kann. Das Stoppen oder Abschließen des Skripts, ein Fehler oder der Aufruf von `go_to_station()` bricht diese Route ab. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def current_station(self) -> _str:
        """Stabile ID der Station, an der die Drohne tatsächlich angedockt ist. Gibt einen leeren String zurück, wenn die Drohne zu Koordinaten fliegt, zwischen Stationen unterwegs ist oder vor einem vollen Drohnendepot wartet. Der Vergleich mit der Ziel-ID ist die maßgebliche Prüfung für die Ankunft an einer Station, auch wenn `go_to_station()` mit einem Anzeigenamen aufgerufen wurde."""
        ...
    def current_drill(self) -> _str:
        """Stabile ID des Bergbaubohrers, bei dem die Drohne derzeit Fracht laden kann, oder ein leerer String, wenn kein Bohrer verfügbar ist. Die Drohne muss sich ohne aktive Route im Ladebereich des Bohrers befinden. Es reicht nicht, ihn nur zu überfliegen oder eine Route bei Schub null beizubehalten. Der Vergleich dieses Werts mit der Ziel-ID ist die maßgebliche Prüfung für die Ankunft beim Bohrer, auch wenn `go_to_drill()` mit einem Anzeigenamen aufgerufen wurde."""
        ...
    def position(self) -> Position:
        """Weltkoordinaten `(.x, .y)`: Während des Flugs werden sie bei jedem Simulationsschritt durch DroneSystem interpoliert; beim Andocken werden sie auf die Stationskoordinaten gesetzt."""
        ...
    def get_distance_to(self, x: _float, y: _float) -> _float:
        """Luftlinienentfernung in Metern von der aktuellen Position der Drohne zu den angegebenen Weltkoordinaten. Verwende sie, um mögliche Ziele zu vergleichen, die verbleibende Streckenlänge zu prüfen oder sie vor dem Start mit `range_remaining()` abzugleichen. Die Funktion misst nur die geometrische Entfernung; sie wählt kein Ziel aus und berücksichtigt den verfügbaren Treibstoff nicht."""
        ...
    battery: DroneBattery
    oil_tank: DroneOilTank
    cargo: DroneCargo
    def go_to(self, x: _float, y: _float) -> ActionResult[Literal["ok", "invalid_target", "out_of_bounds", "out_of_range", "busy", "scrambled"]]:
        """Fliegt als Grundfunktion der Drohne zu beliebigen Weltkoordinaten; ein Feldmodul ist nicht erforderlich. Bei einer angenommenen Route mit verfügbarer Antriebsenergie wird sofort `\"traveling\"` gemeldet. Danach fliegt die Drohne geradeaus und schwebt bei der Ankunft auf der Stelle. Das Stoppen oder Abschließen des Skripts, ein Fehler oder der Aufruf von `go_to_station()` bricht diese Route ab. Verwende für Wetterereignisse die exakten x- und y-Werte aus Sturmpaketen mit gültiger Prüfsumme. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    bio_scanner: PortableBioScanner
    bio_extractor: PortableBioExtractor
    def collect(self) -> CollectResult[Literal["ok", "moving", "busy", "nothing_here", "no_cargo_space", "scrambled"]]:
        """Sammelt an den exakten aktuellen Koordinaten der Drohne eine Charge Material, das nach einem Wetterereignis zurückgeblieben ist. Eine erfolgreiche Sammlung lädt höchstens **5** Einheiten Sturmglas oder Rohuran. Das Sammeln von Rohuran erhöht die Belastung ohne Schutzpanzerung um **40**, mit Schutzpanzerung um **0**. Die Charge bleibt an Bord, selbst wenn dadurch die Störschwelle erreicht wird. Fester Ergebnisvertrag: `CollectResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.item_id` und `.collected`."""
        ...
    def exposure(self) -> _float:
        """Aktuelle Belastung durch die Förderung, von **0** bis `exposure_capacity()`. Sie ändert sich nur beim Sammeln von Rohuran oder durch die Versorgung an einer Drohnenservicestation. Der bloße Flug über eine verborgene Stelle, an der ein Wetterereignis Material hinterlassen hat, hat keine Wirkung. Bei einer funktionierenden Drohne, die an einer mit Strom versorgten Drohnenservicestation angedockt ist, sinkt die Belastung um **10 pro Stunde**. Bei maximaler Belastung ist die Drohne gestört und muss von einer Drohnenservicestation geborgen werden."""
        ...
    def exposure_capacity(self) -> _float:
        """Die Störschwelle bei **100** Belastung. Eine Drohne ohne Schutzpanzerung kann zwei Chargen zu je 5 Einheiten sicher sammeln. Die dritte Charge bleibt an Bord und versetzt die Drohne anschließend in den Störzustand."""
        ...
    def is_plated(self) -> _bool:
        """`True`, wenn eine Schutzpanzerung montiert ist. Sie senkt die Belastung bei der Förderung von Rohuran auf null, halbiert die Kapazität jedes Frachtbehälters und erhöht wegen des schweren Bleis den Treibstoffverbrauch auf das **1,5-Fache**."""
        ...
    def range_remaining(self) -> _float:
        """Geschätzte Flugstrecke in Metern bei aktuellem Energievorrat und Schub. Bei vollem Schub verbrauchen elektrische Drohnen **5 Wh/h**, Heli-Drohnen **5 t/h Öl**. Bei beiden steigt der Verbrauch mit dem Quadrat des Schubs; langsameres Fliegen erhöht daher die Reichweite."""
        ...
    def throttle(self) -> _float:
        """Aktueller Schub (**0-1**). Bei vollem Schub verbraucht der elektrische Antrieb **5 Wh/h**, der Heli-Antrieb **5 t/h Öl**. Bei beiden steigt der Verbrauch mit dem Quadrat des Schubs. Nach dem Stoppen, dem Abschluss oder einem Fehler wird **0** angezeigt."""
        ...
    def set_throttle(self, rate: _float) -> ActionResult[Literal["ok"]]:
        """Setzt den Schub (**0-1**). Bei vollem Schub fliegen elektrische Drohnen **300 m/h** und verbrauchen **5 Wh/h**; Heli-Drohnen fliegen **900 m/h** und verbrauchen **5 t/h Öl**. Ein geringerer Schub senkt den Verbrauch quadratisch. Stoppen, Abschluss oder Fehler setzen den Schub auf **0** zurück. Nur für die eigene Drohne. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def modules(self) -> _list[MountSlot]:
        """Prüfe, welche Module angekoppelt sind. Gibt eine Liste von `MountSlot`-Objekten zurück, eines pro Steckplatz am Chassis. Jedes Objekt hat `.index` (an `couple` / `uncouple` übergeben), `.type` (`\"thruster\"` für Steckplatz 0, `\"drone_module\"` für die übrigen) und `.module_id` (das angekoppelte Modul oder `None` bei einem leeren Steckplatz). Funktioniert bei jeder Drohne, nicht nur bei `self`. Siehe `MountSlot`."""
        ...
    def couple(self, slot_index: _int, module_id: _str) -> ActionResult[Literal["ok", "not_at_station", "item_not_in_inventory", "unknown_module", "slot_not_compatible", "slot_occupied", "invalid_slot", "locked", "wrong_engine_for_module", "cargo_capacity_exceeded"]]:
        """Fordert einen Hardware-Serviceauftrag aus dem Inventar für einen ausdrücklich angegebenen ganzzahligen Steckplatz an: `self.couple(0, \"electric_thruster\")` für den Antriebssteckplatz oder `self.couple(1, \"battery_pack\")` für einen Modulsteckplatz. Die Drohne muss an einem betriebsbereiten Drohnendepot angedockt sein. Diese Ausnahme für spezielle Hardware ermöglicht an diesem Außenposten keinen Zugriff auf gewöhnliche Fracht aus dem Inventar. Nur für die eigene Drohne. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def uncouple(self, slot_index: _int) -> ActionResult[Literal["ok", "invalid_slot", "module_not_mounted", "not_at_station", "cargo_capacity_exceeded", "container_not_empty", "hot_cargo_requires_plating", "inventory_full"]]:
        """Fordert einen Hardware-Serviceauftrag an, der das Modul aus einem ausdrücklich angegebenen ganzzahligen Steckplatz ins Inventar zurückführt: `self.uncouple(1)`. Die Drohne muss an einem betriebsbereiten Drohnendepot angedockt sein. Frachtbehälter müssen vor dem Entfernen leer sein. Die Schutzpanzerung kann nicht entfernt werden, solange Rohuran oder Brennstäbe an Bord sind. Module mit Treibstoff behalten ihren Inhalt. Nur für die eigene Drohne. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def status(self) -> Literal["idle", "traveling", "charging", "refueling", "waiting_service", "waiting_oil", "waiting_bay", "being_rescued", "holding_weather", "scrambled", "stalled_no_battery", "stalled_no_oil", "stalled_no_route"]:
        """Aktuelle Betriebsaktivität zur Überwachung des Fortschritts und zur Behandlung von Blockaden; keine Ankunftsprüfung. `\"idle\"` kann bedeuten, dass die Drohne angedockt ist, an Feldkoordinaten schwebt oder eine vorgemerkte Route bei Schub null hält. Das Laden oder Betanken kann unmittelbar nach dem Andocken beginnen. `\"waiting_bay\"` bedeutet, dass die Drohne ein volles Depot erreicht hat, aber nicht angedockt ist. `\"holding_weather\"` bezeichnet einen vorübergehenden wetterbedingten Halt einer Heli-Drohne. Bei festgefahrenen oder gestörten Zuständen musst du eingreifen. Verwende `current_station()` oder `current_drill()`, um die Ankunft an einem Interaktionspunkt zu bestätigen."""
        ...
    def is_being_rescued(self) -> _bool:
        """`True`, während das Bergungsfahrzeug einer Drohnenservicestation zu dieser Drohne unterwegs ist, sie versorgt oder transportiert. Verwende dies, um Routenskripte anzuhalten, solange das Bergungsfahrzeug die Kontrolle hat."""
        ...
    def rescue_status(self) -> Literal["none", "outbound", "charging", "carrying", "returning"]:
        """Aktuelle Phase der Bergungsmission für diese Drohne: `\"none\"`, `\"outbound\"`, `\"charging\"`, `\"carrying\"` oder `\"returning\"`. Bei `\"returning\"` fährt das Bergungsfahrzeug zur Station zurück; die Drohne steht nicht mehr unter seiner Kontrolle."""
        ...
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

## `DroneMedium`

```python
class DroneMedium(Component):
    """Drohne (mittel): Mittelgroße Frachtdrohne, 1 Triebwerk + 3 Module."""
    name: _str
    def go_to_station(self, name: _str) -> ActionResult[Literal["ok", "station_not_found", "out_of_range", "busy", "scrambled"]]:
        """Legt eine Route zum benannten Drohnendepot oder zur benannten Drohnenservicestation in die Warteschlange und kehrt sofort zurück, ohne das Andocken abzuwarten. Bei einer angenommenen Route mit verfügbarer Antriebsenergie wird sofort `\"traveling\"` gemeldet. Position und Andockstatus ändern sich erst, wenn die Simulation fortschreitet. Stoppen, Abschluss oder Fehler brechen den Flug ab und löschen die Route. Vergleiche `current_station()` mit der stabilen ID des Ziels, um die Ankunft zu bestätigen. Der Wechsel zwischen Drohnengebäuden innerhalb desselben Außenpostens erfolgt vor Ort und verbraucht keinen Flugtreibstoff. An Drohnenservicestationen können Drohnen auch ohne Stromversorgung ankommen und parken. Ist ein Drohnendepot voll, bleibt die Drohne mit `\"waiting_bay\"` unangedockt, bis ein Stellplatz frei wird. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def undock(self) -> ActionResult[Literal["ok", "not_docked", "busy"]]:
        """Gibt den Stellplatz an der Station frei, ohne irgendwohin zu fliegen. Die Drohne behält ihre exakte Weltposition, Fracht, Module, ihren Treibstoff und ihre Belastung. Eine ruhende Route wird gelöscht, der Schub auf **0** zurückgesetzt und die Drohne wird inaktiv. Bei einer laufenden Bergung oder einem laufenden beziehungsweise vorgemerkten Lade- oder Tankauftrag der Drohnenservicestation behält die Station die Kontrolle, bis ihre Arbeit abgeschlossen ist. Verwende `go_to_station(...)`, wenn die Drohne erneut einen Stellplatz belegen soll. Nur für die eigene Drohne. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def go_to_drill(self, name: _str) -> ActionResult[Literal["ok", "drill_not_found", "out_of_range", "busy", "scrambled"]]:
        """Fliegt zu einem benannten Bergbaubohrer im Feld, um Erz abzuholen. Für den Transport ist kein Feldmodul erforderlich. Bei einer angenommenen Route mit verfügbarer Antriebsenergie wird sofort `\"traveling\"` gemeldet. Danach fliegt die Drohne geradeaus und schwebt bei der Ankunft auf der Stelle. Vergleiche `current_drill()` mit der stabilen ID des Ziels, um zu bestätigen, dass Fracht geladen werden kann. Das Stoppen oder Abschließen des Skripts, ein Fehler oder der Aufruf von `go_to_station()` bricht diese Route ab. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def current_station(self) -> _str:
        """Stabile ID der Station, an der die Drohne tatsächlich angedockt ist. Gibt einen leeren String zurück, wenn die Drohne zu Koordinaten fliegt, zwischen Stationen unterwegs ist oder vor einem vollen Drohnendepot wartet. Der Vergleich mit der Ziel-ID ist die maßgebliche Prüfung für die Ankunft an einer Station, auch wenn `go_to_station()` mit einem Anzeigenamen aufgerufen wurde."""
        ...
    def current_drill(self) -> _str:
        """Stabile ID des Bergbaubohrers, bei dem die Drohne derzeit Fracht laden kann, oder ein leerer String, wenn kein Bohrer verfügbar ist. Die Drohne muss sich ohne aktive Route im Ladebereich des Bohrers befinden. Es reicht nicht, ihn nur zu überfliegen oder eine Route bei Schub null beizubehalten. Der Vergleich dieses Werts mit der Ziel-ID ist die maßgebliche Prüfung für die Ankunft beim Bohrer, auch wenn `go_to_drill()` mit einem Anzeigenamen aufgerufen wurde."""
        ...
    def position(self) -> Position:
        """Weltkoordinaten `(.x, .y)`: Während des Flugs werden sie bei jedem Simulationsschritt durch DroneSystem interpoliert; beim Andocken werden sie auf die Stationskoordinaten gesetzt."""
        ...
    def get_distance_to(self, x: _float, y: _float) -> _float:
        """Luftlinienentfernung in Metern von der aktuellen Position der Drohne zu den angegebenen Weltkoordinaten. Verwende sie, um mögliche Ziele zu vergleichen, die verbleibende Streckenlänge zu prüfen oder sie vor dem Start mit `range_remaining()` abzugleichen. Die Funktion misst nur die geometrische Entfernung; sie wählt kein Ziel aus und berücksichtigt den verfügbaren Treibstoff nicht."""
        ...
    battery: DroneBattery
    oil_tank: DroneOilTank
    cargo: DroneCargo
    def go_to(self, x: _float, y: _float) -> ActionResult[Literal["ok", "invalid_target", "out_of_bounds", "out_of_range", "busy", "scrambled"]]:
        """Fliegt als Grundfunktion der Drohne zu beliebigen Weltkoordinaten; ein Feldmodul ist nicht erforderlich. Bei einer angenommenen Route mit verfügbarer Antriebsenergie wird sofort `\"traveling\"` gemeldet. Danach fliegt die Drohne geradeaus und schwebt bei der Ankunft auf der Stelle. Das Stoppen oder Abschließen des Skripts, ein Fehler oder der Aufruf von `go_to_station()` bricht diese Route ab. Verwende für Wetterereignisse die exakten x- und y-Werte aus Sturmpaketen mit gültiger Prüfsumme. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    bio_scanner: PortableBioScanner
    bio_extractor: PortableBioExtractor
    def collect(self) -> CollectResult[Literal["ok", "moving", "busy", "nothing_here", "no_cargo_space", "scrambled"]]:
        """Sammelt an den exakten aktuellen Koordinaten der Drohne eine Charge Material, das nach einem Wetterereignis zurückgeblieben ist. Eine erfolgreiche Sammlung lädt höchstens **5** Einheiten Sturmglas oder Rohuran. Das Sammeln von Rohuran erhöht die Belastung ohne Schutzpanzerung um **40**, mit Schutzpanzerung um **0**. Die Charge bleibt an Bord, selbst wenn dadurch die Störschwelle erreicht wird. Fester Ergebnisvertrag: `CollectResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.item_id` und `.collected`."""
        ...
    def exposure(self) -> _float:
        """Aktuelle Belastung durch die Förderung, von **0** bis `exposure_capacity()`. Sie ändert sich nur beim Sammeln von Rohuran oder durch die Versorgung an einer Drohnenservicestation. Der bloße Flug über eine verborgene Stelle, an der ein Wetterereignis Material hinterlassen hat, hat keine Wirkung. Bei einer funktionierenden Drohne, die an einer mit Strom versorgten Drohnenservicestation angedockt ist, sinkt die Belastung um **10 pro Stunde**. Bei maximaler Belastung ist die Drohne gestört und muss von einer Drohnenservicestation geborgen werden."""
        ...
    def exposure_capacity(self) -> _float:
        """Die Störschwelle bei **100** Belastung. Eine Drohne ohne Schutzpanzerung kann zwei Chargen zu je 5 Einheiten sicher sammeln. Die dritte Charge bleibt an Bord und versetzt die Drohne anschließend in den Störzustand."""
        ...
    def is_plated(self) -> _bool:
        """`True`, wenn eine Schutzpanzerung montiert ist. Sie senkt die Belastung bei der Förderung von Rohuran auf null, halbiert die Kapazität jedes Frachtbehälters und erhöht wegen des schweren Bleis den Treibstoffverbrauch auf das **1,5-Fache**."""
        ...
    def range_remaining(self) -> _float:
        """Geschätzte Flugstrecke in Metern bei aktuellem Energievorrat und Schub. Bei vollem Schub verbrauchen elektrische Drohnen **5 Wh/h**, Heli-Drohnen **5 t/h Öl**. Bei beiden steigt der Verbrauch mit dem Quadrat des Schubs; langsameres Fliegen erhöht daher die Reichweite."""
        ...
    def throttle(self) -> _float:
        """Aktueller Schub (**0-1**). Bei vollem Schub verbraucht der elektrische Antrieb **5 Wh/h**, der Heli-Antrieb **5 t/h Öl**. Bei beiden steigt der Verbrauch mit dem Quadrat des Schubs. Nach dem Stoppen, dem Abschluss oder einem Fehler wird **0** angezeigt."""
        ...
    def set_throttle(self, rate: _float) -> ActionResult[Literal["ok"]]:
        """Setzt den Schub (**0-1**). Bei vollem Schub fliegen elektrische Drohnen **300 m/h** und verbrauchen **5 Wh/h**; Heli-Drohnen fliegen **900 m/h** und verbrauchen **5 t/h Öl**. Ein geringerer Schub senkt den Verbrauch quadratisch. Stoppen, Abschluss oder Fehler setzen den Schub auf **0** zurück. Nur für die eigene Drohne. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def modules(self) -> _list[MountSlot]:
        """Prüfe, welche Module angekoppelt sind. Gibt eine Liste von `MountSlot`-Objekten zurück, eines pro Steckplatz am Chassis. Jedes Objekt hat `.index` (an `couple` / `uncouple` übergeben), `.type` (`\"thruster\"` für Steckplatz 0, `\"drone_module\"` für die übrigen) und `.module_id` (das angekoppelte Modul oder `None` bei einem leeren Steckplatz). Funktioniert bei jeder Drohne, nicht nur bei `self`. Siehe `MountSlot`."""
        ...
    def couple(self, slot_index: _int, module_id: _str) -> ActionResult[Literal["ok", "not_at_station", "item_not_in_inventory", "unknown_module", "slot_not_compatible", "slot_occupied", "invalid_slot", "locked", "wrong_engine_for_module", "cargo_capacity_exceeded"]]:
        """Fordert einen Hardware-Serviceauftrag aus dem Inventar für einen ausdrücklich angegebenen ganzzahligen Steckplatz an: `self.couple(0, \"electric_thruster\")` für den Antriebssteckplatz oder `self.couple(1, \"battery_pack\")` für einen Modulsteckplatz. Die Drohne muss an einem betriebsbereiten Drohnendepot angedockt sein. Diese Ausnahme für spezielle Hardware ermöglicht an diesem Außenposten keinen Zugriff auf gewöhnliche Fracht aus dem Inventar. Nur für die eigene Drohne. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def uncouple(self, slot_index: _int) -> ActionResult[Literal["ok", "invalid_slot", "module_not_mounted", "not_at_station", "cargo_capacity_exceeded", "container_not_empty", "hot_cargo_requires_plating", "inventory_full"]]:
        """Fordert einen Hardware-Serviceauftrag an, der das Modul aus einem ausdrücklich angegebenen ganzzahligen Steckplatz ins Inventar zurückführt: `self.uncouple(1)`. Die Drohne muss an einem betriebsbereiten Drohnendepot angedockt sein. Frachtbehälter müssen vor dem Entfernen leer sein. Die Schutzpanzerung kann nicht entfernt werden, solange Rohuran oder Brennstäbe an Bord sind. Module mit Treibstoff behalten ihren Inhalt. Nur für die eigene Drohne. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def status(self) -> Literal["idle", "traveling", "charging", "refueling", "waiting_service", "waiting_oil", "waiting_bay", "being_rescued", "holding_weather", "scrambled", "stalled_no_battery", "stalled_no_oil", "stalled_no_route"]:
        """Aktuelle Betriebsaktivität zur Überwachung des Fortschritts und zur Behandlung von Blockaden; keine Ankunftsprüfung. `\"idle\"` kann bedeuten, dass die Drohne angedockt ist, an Feldkoordinaten schwebt oder eine vorgemerkte Route bei Schub null hält. Das Laden oder Betanken kann unmittelbar nach dem Andocken beginnen. `\"waiting_bay\"` bedeutet, dass die Drohne ein volles Depot erreicht hat, aber nicht angedockt ist. `\"holding_weather\"` bezeichnet einen vorübergehenden wetterbedingten Halt einer Heli-Drohne. Bei festgefahrenen oder gestörten Zuständen musst du eingreifen. Verwende `current_station()` oder `current_drill()`, um die Ankunft an einem Interaktionspunkt zu bestätigen."""
        ...
    def is_being_rescued(self) -> _bool:
        """`True`, während das Bergungsfahrzeug einer Drohnenservicestation zu dieser Drohne unterwegs ist, sie versorgt oder transportiert. Verwende dies, um Routenskripte anzuhalten, solange das Bergungsfahrzeug die Kontrolle hat."""
        ...
    def rescue_status(self) -> Literal["none", "outbound", "charging", "carrying", "returning"]:
        """Aktuelle Phase der Bergungsmission für diese Drohne: `\"none\"`, `\"outbound\"`, `\"charging\"`, `\"carrying\"` oder `\"returning\"`. Bei `\"returning\"` fährt das Bergungsfahrzeug zur Station zurück; die Drohne steht nicht mehr unter seiner Kontrolle."""
        ...
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

## `DroneRef`

```python
class DroneRef:
    """fleet.drones()"""
    category: Literal["drone"]
    id: _str
    name: _str
    kind: Literal["drone_small", "drone_medium", "drone_large"]
    engine: Literal["", "electric", "heli"]
    status: Literal["idle", "traveling", "charging", "refueling", "waiting_service", "waiting_oil", "waiting_bay", "being_rescued", "holding_weather", "scrambled", "stalled_no_battery", "stalled_no_oil", "stalled_no_route"]
    x: _float
    y: _float
    def position(self) -> Position:
        """Momentaufnahme der Position zum Zeitpunkt der Rückgabe dieser Referenz."""
        ...
    current_station: _str
    is_docked: _bool
    battery_level: _float | None
    battery_wh: _float | None
    battery_capacity: _float | None
    oil_level: _float | None
    oil_tons: _float | None
    oil_capacity: _float | None
    is_being_rescued: _bool
    rescue_status: Literal["none", "outbound", "charging", "carrying", "returning"]
```

## `DroneServiceStation`

```python
class DroneServiceStation(Component):
    """Drohnenservicestation: Lädt Elektrodrohnen unterwegs auf und holt Helidrohnen zur Betankung per Warteschlange zurück. Am Stromnetz angeschlossen."""
    name: _str
    outpost: OutpostRef
    def get_docked(self) -> _list[_str]:
        """Liste der IDs aller Drohnen, die derzeit an dieser Station parken, sowohl elektrischer als auch Heli-Drohnen. Lies den Zustand jeder Drohne mit `get_component(id)`."""
        ...
    def charge(self, drone_id: _str, target_level: _float = ...) -> ActionResult[Literal["charging", "queued", "target_reached", "not_docked", "station_offline", "invalid"]]:
        """Reiht eine geparkte elektrische Drohne zum Laden ein, bis ihre Batterie `target_level` erreicht. Der Wert muss größer als **0** und höchstens **1** sein; Standardwert ist **1.0**. Ladeaufträge für elektrische Drohnen und Tankaufträge für Heli-Drohnen teilen sich eine FIFO-Warteschlange und dieselben Serviceplätze. Einer Heli-Drohne ohne verfügbare Ölzufuhr bleibt ihr Platz in der Warteschlange erhalten, sie belegt aber keinen Serviceplatz. Deshalb können bereite Ladeaufträge sie überholen. Beispiel: `self.charge(\"drone_small_1\", 0.8)`. Nur für diese Station. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def refuel(self, drone_id: _str, target_level: _float = ...) -> ActionResult[Literal["refueling", "queued", "target_reached", "not_docked", "station_offline", "no_oil", "invalid"]]:
        """Reiht eine geparkte Heli-Drohne zum Betanken ein, bis ihr Öltank `target_level` erreicht. Der Wert muss größer als **0** und höchstens **1** sein; Standardwert ist **1.0**. Ladeaufträge für elektrische Drohnen und Tankaufträge für Heli-Drohnen teilen sich eine FIFO-Warteschlange und dieselben Serviceplätze. Das Öl wird aus `self.oil_in` bezogen. Nur für diese Station. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def dispatch_rescue(self, drone_name: _str, target_level: _float = ...) -> ActionResult[Literal["ok", "already_dispatched", "station_offline", "not_found", "not_stranded", "invalid"]]:
        """Schickt das Bergungsfahrzeug zu einer Drohne im Feld, die dein Skript auswählt; es gibt keinen verborgenen Grenzwert für den Treibstoffstand. Elektrische Drohnen werden vor Ort bis `target_level` geladen und setzen ihre Route fort. Heli-Drohnen werden zur Station zurückgebracht und dann in die reguläre Tankwarteschlange eingereiht. Gestörte Drohnen werden ebenfalls zurückgebracht, damit ihre Elektronik beim Andocken zurückgesetzt werden kann. `target_level` muss größer als **0** und höchstens **1** sein; Standardwert ist **1.0**. Für den Start braucht die Station Strom, die Mission kann aber auch bei einem späteren Stromausfall abgeschlossen werden. Nur für diese Station. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def cancel_rescue(self) -> ActionResult[Literal["ok", "no_rescue"]]:
        """Bricht die laufende Bergung ab. Die Drohne wird an ihrer aktuellen Position freigegeben und behält bereits erhaltene Ladung. Das Bergungsfahrzeug kehrt zur Station zurück. Nur für diese Station. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def is_rescuing(self) -> _bool:
        """`True`, während das Bergungsfahrzeug auf einer Bergungsmission ist."""
        ...
    def get_rescue_target(self) -> _str:
        """Anzeigename des Missionsziels, während das Bergungsfahrzeug zum Ziel unterwegs ist, es versorgt, transportiert oder zurückkehrt. Im Ruhezustand ein leerer String."""
        ...
    def stop(self, drone_id: _str) -> ActionResult[Literal["ok", "not_found", "invalid"]]:
        """Bricht einen laufenden oder vorgemerkten Auftrag an dieser Station ab, unabhängig davon, ob er zum Laden oder Betanken dient. Die Drohne behält bereits erhaltene Energie beziehungsweise bereits eingefülltes Öl. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def clear_queue(self) -> CountResult[Literal["ok", "no_op"]]:
        """Löscht alle laufenden und vorgemerkten Lade- und Tankaufträge an dieser Station. Angedockte Drohnen bleiben geparkt und behalten ihren aktuellen Batterie- und Ölstand. Fester Ergebnisvertrag: `CountResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.count`."""
        ...
    def get_active(self) -> _list[_str]:
        """Liste der Drohnen-IDs, die derzeit aktive Serviceplätze zum Laden oder Betanken belegen. Eine Heli-Drohne ohne verfügbare Ölzufuhr wartet und gilt nicht als aktiv."""
        ...
    def get_queue(self) -> _list[_str]:
        """Eine gemeinsame FIFO-Liste der Drohnen-IDs für das Laden elektrischer Drohnen und das Betanken von Heli-Drohnen. Heli-Drohnen ohne verfügbare Ölzufuhr behalten ihren Platz in der Reihenfolge, während spätere bereite Aufträge sonst ungenutzte Serviceplätze belegen können."""
        ...
    def status(self, drone_id: _str) -> _dict[_str, JsonValue]:
        """Detaillierter Status des Serviceauftrags einer Drohne. Elektrische Drohnen geben ein dict mit `state`, `target_level`, `battery_wh`, `capacity_wh`, `rate_w`, `bay_index` und `queue_index` zurück. Heli-Drohnen geben `state`, `target_level`, `oil_tons`, `capacity_tons`, `rate_tons_per_hour`, `bay_index` und `queue_index` zurück."""
        ...
    def get_bay_count(self) -> _int:
        """Anzahl gleichzeitig nutzbarer Serviceplätze."""
        ...
    def get_charge_rate(self, drone_id: _str) -> _float:
        """Gibt die Ladungsmenge in Wh/h zurück, die der benannten elektrischen Drohne derzeit zugeführt wird (**0**, wenn sie keinen aktiven Serviceplatz belegt)."""
        ...
    def get_refuel_rate(self, drone_id: _str) -> _float:
        """Gibt die Ölmenge in t/h zurück, die der benannten Heli-Drohne derzeit zugeführt wird (**0**, wenn sie keinen aktiven Serviceplatz belegt oder die Station kein Öl hat)."""
        ...
    oil_in: FluidPort
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

## `DroneSmall`

```python
class DroneSmall(Component):
    """Drohne (klein): Kleine Luftfrachtdrohne, 1 Triebwerk + 2 Module."""
    name: _str
    def go_to_station(self, name: _str) -> ActionResult[Literal["ok", "station_not_found", "out_of_range", "busy", "scrambled"]]:
        """Legt eine Route zum benannten Drohnendepot oder zur benannten Drohnenservicestation in die Warteschlange und kehrt sofort zurück, ohne das Andocken abzuwarten. Bei einer angenommenen Route mit verfügbarer Antriebsenergie wird sofort `\"traveling\"` gemeldet. Position und Andockstatus ändern sich erst, wenn die Simulation fortschreitet. Stoppen, Abschluss oder Fehler brechen den Flug ab und löschen die Route. Vergleiche `current_station()` mit der stabilen ID des Ziels, um die Ankunft zu bestätigen. Der Wechsel zwischen Drohnengebäuden innerhalb desselben Außenpostens erfolgt vor Ort und verbraucht keinen Flugtreibstoff. An Drohnenservicestationen können Drohnen auch ohne Stromversorgung ankommen und parken. Ist ein Drohnendepot voll, bleibt die Drohne mit `\"waiting_bay\"` unangedockt, bis ein Stellplatz frei wird. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def undock(self) -> ActionResult[Literal["ok", "not_docked", "busy"]]:
        """Gibt den Stellplatz an der Station frei, ohne irgendwohin zu fliegen. Die Drohne behält ihre exakte Weltposition, Fracht, Module, ihren Treibstoff und ihre Belastung. Eine ruhende Route wird gelöscht, der Schub auf **0** zurückgesetzt und die Drohne wird inaktiv. Bei einer laufenden Bergung oder einem laufenden beziehungsweise vorgemerkten Lade- oder Tankauftrag der Drohnenservicestation behält die Station die Kontrolle, bis ihre Arbeit abgeschlossen ist. Verwende `go_to_station(...)`, wenn die Drohne erneut einen Stellplatz belegen soll. Nur für die eigene Drohne. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def go_to_drill(self, name: _str) -> ActionResult[Literal["ok", "drill_not_found", "out_of_range", "busy", "scrambled"]]:
        """Fliegt zu einem benannten Bergbaubohrer im Feld, um Erz abzuholen. Für den Transport ist kein Feldmodul erforderlich. Bei einer angenommenen Route mit verfügbarer Antriebsenergie wird sofort `\"traveling\"` gemeldet. Danach fliegt die Drohne geradeaus und schwebt bei der Ankunft auf der Stelle. Vergleiche `current_drill()` mit der stabilen ID des Ziels, um zu bestätigen, dass Fracht geladen werden kann. Das Stoppen oder Abschließen des Skripts, ein Fehler oder der Aufruf von `go_to_station()` bricht diese Route ab. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def current_station(self) -> _str:
        """Stabile ID der Station, an der die Drohne tatsächlich angedockt ist. Gibt einen leeren String zurück, wenn die Drohne zu Koordinaten fliegt, zwischen Stationen unterwegs ist oder vor einem vollen Drohnendepot wartet. Der Vergleich mit der Ziel-ID ist die maßgebliche Prüfung für die Ankunft an einer Station, auch wenn `go_to_station()` mit einem Anzeigenamen aufgerufen wurde."""
        ...
    def current_drill(self) -> _str:
        """Stabile ID des Bergbaubohrers, bei dem die Drohne derzeit Fracht laden kann, oder ein leerer String, wenn kein Bohrer verfügbar ist. Die Drohne muss sich ohne aktive Route im Ladebereich des Bohrers befinden. Es reicht nicht, ihn nur zu überfliegen oder eine Route bei Schub null beizubehalten. Der Vergleich dieses Werts mit der Ziel-ID ist die maßgebliche Prüfung für die Ankunft beim Bohrer, auch wenn `go_to_drill()` mit einem Anzeigenamen aufgerufen wurde."""
        ...
    def position(self) -> Position:
        """Weltkoordinaten `(.x, .y)`: Während des Flugs werden sie bei jedem Simulationsschritt durch DroneSystem interpoliert; beim Andocken werden sie auf die Stationskoordinaten gesetzt."""
        ...
    def get_distance_to(self, x: _float, y: _float) -> _float:
        """Luftlinienentfernung in Metern von der aktuellen Position der Drohne zu den angegebenen Weltkoordinaten. Verwende sie, um mögliche Ziele zu vergleichen, die verbleibende Streckenlänge zu prüfen oder sie vor dem Start mit `range_remaining()` abzugleichen. Die Funktion misst nur die geometrische Entfernung; sie wählt kein Ziel aus und berücksichtigt den verfügbaren Treibstoff nicht."""
        ...
    battery: DroneBattery
    oil_tank: DroneOilTank
    cargo: DroneCargo
    def go_to(self, x: _float, y: _float) -> ActionResult[Literal["ok", "invalid_target", "out_of_bounds", "out_of_range", "busy", "scrambled"]]:
        """Fliegt als Grundfunktion der Drohne zu beliebigen Weltkoordinaten; ein Feldmodul ist nicht erforderlich. Bei einer angenommenen Route mit verfügbarer Antriebsenergie wird sofort `\"traveling\"` gemeldet. Danach fliegt die Drohne geradeaus und schwebt bei der Ankunft auf der Stelle. Das Stoppen oder Abschließen des Skripts, ein Fehler oder der Aufruf von `go_to_station()` bricht diese Route ab. Verwende für Wetterereignisse die exakten x- und y-Werte aus Sturmpaketen mit gültiger Prüfsumme. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    bio_scanner: PortableBioScanner
    bio_extractor: PortableBioExtractor
    def collect(self) -> CollectResult[Literal["ok", "moving", "busy", "nothing_here", "no_cargo_space", "scrambled"]]:
        """Sammelt an den exakten aktuellen Koordinaten der Drohne eine Charge Material, das nach einem Wetterereignis zurückgeblieben ist. Eine erfolgreiche Sammlung lädt höchstens **5** Einheiten Sturmglas oder Rohuran. Das Sammeln von Rohuran erhöht die Belastung ohne Schutzpanzerung um **40**, mit Schutzpanzerung um **0**. Die Charge bleibt an Bord, selbst wenn dadurch die Störschwelle erreicht wird. Fester Ergebnisvertrag: `CollectResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.item_id` und `.collected`."""
        ...
    def exposure(self) -> _float:
        """Aktuelle Belastung durch die Förderung, von **0** bis `exposure_capacity()`. Sie ändert sich nur beim Sammeln von Rohuran oder durch die Versorgung an einer Drohnenservicestation. Der bloße Flug über eine verborgene Stelle, an der ein Wetterereignis Material hinterlassen hat, hat keine Wirkung. Bei einer funktionierenden Drohne, die an einer mit Strom versorgten Drohnenservicestation angedockt ist, sinkt die Belastung um **10 pro Stunde**. Bei maximaler Belastung ist die Drohne gestört und muss von einer Drohnenservicestation geborgen werden."""
        ...
    def exposure_capacity(self) -> _float:
        """Die Störschwelle bei **100** Belastung. Eine Drohne ohne Schutzpanzerung kann zwei Chargen zu je 5 Einheiten sicher sammeln. Die dritte Charge bleibt an Bord und versetzt die Drohne anschließend in den Störzustand."""
        ...
    def is_plated(self) -> _bool:
        """`True`, wenn eine Schutzpanzerung montiert ist. Sie senkt die Belastung bei der Förderung von Rohuran auf null, halbiert die Kapazität jedes Frachtbehälters und erhöht wegen des schweren Bleis den Treibstoffverbrauch auf das **1,5-Fache**."""
        ...
    def range_remaining(self) -> _float:
        """Geschätzte Flugstrecke in Metern bei aktuellem Energievorrat und Schub. Bei vollem Schub verbrauchen elektrische Drohnen **5 Wh/h**, Heli-Drohnen **5 t/h Öl**. Bei beiden steigt der Verbrauch mit dem Quadrat des Schubs; langsameres Fliegen erhöht daher die Reichweite."""
        ...
    def throttle(self) -> _float:
        """Aktueller Schub (**0-1**). Bei vollem Schub verbraucht der elektrische Antrieb **5 Wh/h**, der Heli-Antrieb **5 t/h Öl**. Bei beiden steigt der Verbrauch mit dem Quadrat des Schubs. Nach dem Stoppen, dem Abschluss oder einem Fehler wird **0** angezeigt."""
        ...
    def set_throttle(self, rate: _float) -> ActionResult[Literal["ok"]]:
        """Setzt den Schub (**0-1**). Bei vollem Schub fliegen elektrische Drohnen **300 m/h** und verbrauchen **5 Wh/h**; Heli-Drohnen fliegen **900 m/h** und verbrauchen **5 t/h Öl**. Ein geringerer Schub senkt den Verbrauch quadratisch. Stoppen, Abschluss oder Fehler setzen den Schub auf **0** zurück. Nur für die eigene Drohne. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def modules(self) -> _list[MountSlot]:
        """Prüfe, welche Module angekoppelt sind. Gibt eine Liste von `MountSlot`-Objekten zurück, eines pro Steckplatz am Chassis. Jedes Objekt hat `.index` (an `couple` / `uncouple` übergeben), `.type` (`\"thruster\"` für Steckplatz 0, `\"drone_module\"` für die übrigen) und `.module_id` (das angekoppelte Modul oder `None` bei einem leeren Steckplatz). Funktioniert bei jeder Drohne, nicht nur bei `self`. Siehe `MountSlot`."""
        ...
    def couple(self, slot_index: _int, module_id: _str) -> ActionResult[Literal["ok", "not_at_station", "item_not_in_inventory", "unknown_module", "slot_not_compatible", "slot_occupied", "invalid_slot", "locked", "wrong_engine_for_module", "cargo_capacity_exceeded"]]:
        """Fordert einen Hardware-Serviceauftrag aus dem Inventar für einen ausdrücklich angegebenen ganzzahligen Steckplatz an: `self.couple(0, \"electric_thruster\")` für den Antriebssteckplatz oder `self.couple(1, \"battery_pack\")` für einen Modulsteckplatz. Die Drohne muss an einem betriebsbereiten Drohnendepot angedockt sein. Diese Ausnahme für spezielle Hardware ermöglicht an diesem Außenposten keinen Zugriff auf gewöhnliche Fracht aus dem Inventar. Nur für die eigene Drohne. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def uncouple(self, slot_index: _int) -> ActionResult[Literal["ok", "invalid_slot", "module_not_mounted", "not_at_station", "cargo_capacity_exceeded", "container_not_empty", "hot_cargo_requires_plating", "inventory_full"]]:
        """Fordert einen Hardware-Serviceauftrag an, der das Modul aus einem ausdrücklich angegebenen ganzzahligen Steckplatz ins Inventar zurückführt: `self.uncouple(1)`. Die Drohne muss an einem betriebsbereiten Drohnendepot angedockt sein. Frachtbehälter müssen vor dem Entfernen leer sein. Die Schutzpanzerung kann nicht entfernt werden, solange Rohuran oder Brennstäbe an Bord sind. Module mit Treibstoff behalten ihren Inhalt. Nur für die eigene Drohne. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def status(self) -> Literal["idle", "traveling", "charging", "refueling", "waiting_service", "waiting_oil", "waiting_bay", "being_rescued", "holding_weather", "scrambled", "stalled_no_battery", "stalled_no_oil", "stalled_no_route"]:
        """Aktuelle Betriebsaktivität zur Überwachung des Fortschritts und zur Behandlung von Blockaden; keine Ankunftsprüfung. `\"idle\"` kann bedeuten, dass die Drohne angedockt ist, an Feldkoordinaten schwebt oder eine vorgemerkte Route bei Schub null hält. Das Laden oder Betanken kann unmittelbar nach dem Andocken beginnen. `\"waiting_bay\"` bedeutet, dass die Drohne ein volles Depot erreicht hat, aber nicht angedockt ist. `\"holding_weather\"` bezeichnet einen vorübergehenden wetterbedingten Halt einer Heli-Drohne. Bei festgefahrenen oder gestörten Zuständen musst du eingreifen. Verwende `current_station()` oder `current_drill()`, um die Ankunft an einem Interaktionspunkt zu bestätigen."""
        ...
    def is_being_rescued(self) -> _bool:
        """`True`, während das Bergungsfahrzeug einer Drohnenservicestation zu dieser Drohne unterwegs ist, sie versorgt oder transportiert. Verwende dies, um Routenskripte anzuhalten, solange das Bergungsfahrzeug die Kontrolle hat."""
        ...
    def rescue_status(self) -> Literal["none", "outbound", "charging", "carrying", "returning"]:
        """Aktuelle Phase der Bergungsmission für diese Drohne: `\"none\"`, `\"outbound\"`, `\"charging\"`, `\"carrying\"` oder `\"returning\"`. Bei `\"returning\"` fährt das Bergungsfahrzeug zur Station zurück; die Drohne steht nicht mehr unter seiner Kontrolle."""
        ...
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

## `DroneStation`

```python
class DroneStation(Component):
    """Drohnendepot: Logistik-Endpunkt mit 1 Andockplatz an einem Außenposten. Fracht-Ein- und -Ausgabe."""
    name: _str
    outpost: OutpostRef
    input: InputSlot
    output: OutputSlot
    def get_docked(self) -> _list[_str]:
        """Liste der IDs der Drohnen, die derzeit an diesem Depot angedockt sind, in stabiler ID-Reihenfolge. Lies den Zustand jeder Drohne mit `get_component(id)`."""
        ...
    def bay_count(self) -> _int:
        """Gesamtzahl der Stellplätze an dieser Station: **1** (einfach) / **2** (mittel) / **4** (groß). Wenn du das Depot vor Ort mit einem größeren Bausatz aufrüstest, steigt die Zahl sofort."""
        ...
    def bays_occupied(self) -> _int:
        """Stellplätze, die derzeit von angedockten Drohnen belegt sind. Entspricht ihre Zahl `bay_count`, warten ankommende Drohnen im Luftraum."""
        ...
    def slots_used(self) -> _int:
        """Anzahl unterschiedlicher Materialien, die der Vorrat derzeit enthält. Ein Material belegt unabhängig von der gelagerten Menge einen einzigen Platz. Daher belegen **50** Einheiten desselben Materials nur einen Platz."""
        ...
    def slot_capacity(self) -> _int:
        """Anzahl unterschiedlicher Materialien, die dieses Depot gleichzeitig aufnehmen kann. Ein Depot dient zum Umladen, nicht als Lagerhaus: Sind alle Plätze belegt, bewegt `cargo.unload()` bei einem neuen Material **0** Einheiten und meldet, dass kein Platz frei ist – selbst wenn noch Raum für weitere Einheiten vorhanden wäre. Entferne ein Material aus dem Vorrat, um seinen Platz freizugeben."""
        ...
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

## `DroneStationLarge`

```python
class DroneStationLarge(Component):
    """Drohnendepot (groß): Großer Drohnenknotenpunkt mit 4 Andockplätzen."""
    name: _str
    outpost: OutpostRef
    input: InputSlot
    output: OutputSlot
    def get_docked(self) -> _list[_str]:
        """Liste der IDs der Drohnen, die derzeit an diesem Depot angedockt sind, in stabiler ID-Reihenfolge. Lies den Zustand jeder Drohne mit `get_component(id)`."""
        ...
    def bay_count(self) -> _int:
        """Gesamtzahl der Stellplätze an dieser Station: **1** (einfach) / **2** (mittel) / **4** (groß). Wenn du das Depot vor Ort mit einem größeren Bausatz aufrüstest, steigt die Zahl sofort."""
        ...
    def bays_occupied(self) -> _int:
        """Stellplätze, die derzeit von angedockten Drohnen belegt sind. Entspricht ihre Zahl `bay_count`, warten ankommende Drohnen im Luftraum."""
        ...
    def slots_used(self) -> _int:
        """Anzahl unterschiedlicher Materialien, die der Vorrat derzeit enthält. Ein Material belegt unabhängig von der gelagerten Menge einen einzigen Platz. Daher belegen **50** Einheiten desselben Materials nur einen Platz."""
        ...
    def slot_capacity(self) -> _int:
        """Anzahl unterschiedlicher Materialien, die dieses Depot gleichzeitig aufnehmen kann. Ein Depot dient zum Umladen, nicht als Lagerhaus: Sind alle Plätze belegt, bewegt `cargo.unload()` bei einem neuen Material **0** Einheiten und meldet, dass kein Platz frei ist – selbst wenn noch Raum für weitere Einheiten vorhanden wäre. Entferne ein Material aus dem Vorrat, um seinen Platz freizugeben."""
        ...
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

## `DroneStationMedium`

```python
class DroneStationMedium(Component):
    """Drohnendepot (mittel): Logistik-Endpunkt mit 2 Andockplätzen. Paralleles Andocken."""
    name: _str
    outpost: OutpostRef
    input: InputSlot
    output: OutputSlot
    def get_docked(self) -> _list[_str]:
        """Liste der IDs der Drohnen, die derzeit an diesem Depot angedockt sind, in stabiler ID-Reihenfolge. Lies den Zustand jeder Drohne mit `get_component(id)`."""
        ...
    def bay_count(self) -> _int:
        """Gesamtzahl der Stellplätze an dieser Station: **1** (einfach) / **2** (mittel) / **4** (groß). Wenn du das Depot vor Ort mit einem größeren Bausatz aufrüstest, steigt die Zahl sofort."""
        ...
    def bays_occupied(self) -> _int:
        """Stellplätze, die derzeit von angedockten Drohnen belegt sind. Entspricht ihre Zahl `bay_count`, warten ankommende Drohnen im Luftraum."""
        ...
    def slots_used(self) -> _int:
        """Anzahl unterschiedlicher Materialien, die der Vorrat derzeit enthält. Ein Material belegt unabhängig von der gelagerten Menge einen einzigen Platz. Daher belegen **50** Einheiten desselben Materials nur einen Platz."""
        ...
    def slot_capacity(self) -> _int:
        """Anzahl unterschiedlicher Materialien, die dieses Depot gleichzeitig aufnehmen kann. Ein Depot dient zum Umladen, nicht als Lagerhaus: Sind alle Plätze belegt, bewegt `cargo.unload()` bei einem neuen Material **0** Einheiten und meldet, dass kein Platz frei ist – selbst wenn noch Raum für weitere Einheiten vorhanden wäre. Entferne ein Material aus dem Vorrat, um seinen Platz freizugeben."""
        ...
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

## `Harvester`

```python
class Harvester(Component):
    """Harvester: Ein langsames, vielseitiges Oberflächenfahrzeug: Es sammelt lose Gegenstände ein, sät Pflanzen und pflegt sie, erntet Pflanzenfutter und stellt fest installierte Feldmaschinen auf. Fahrten und Feldarbeit kosten Zeit und erzeugen Hitze. Plane auf langen Routen daher Pausen zum Abkühlen ein."""
    name: _str
    def move(self, sector: _str) -> ActionResult[Literal["ok", "invalid", "too_far", "already_here", "overheated", "moving", "busy"]]:
        """Bewege dich mit `self.move(\"E14\")` um einen Sektor nach oben, unten, links oder rechts. Diagonale Bewegungen sind ungültig. Die Fahrt dauert **0,5 Stunden** und pausiert das Skript. `self.get_position()` zeigt das Ziel sofort an, physische Aktionen sind aber bis zur Ankunft gesperrt. Die Fahrt in einen Sektor mit einem Gegenstand erzeugt **1** Hitze, die in einen leeren Sektor **7**. Scanne also zuerst. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def collect(self) -> ScanResult[Literal["ok", "empty", "holding", "overheated", "moving", "busy", "collecting"]]:
        """Sammle den Gegenstand im aktuellen Sektor in den einzigen Trageplatz des Harvesters ein, nicht ins Inventar. Das Einsammeln dauert **0,25 Stunden** und pausiert das Skript. Auch in leeren Sektoren kostet der Versuch Zeit und erzeugt **9** Hitze. Fester Ergebnisvertrag: `ScanResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.id`, `.name` und `.value`."""
        ...
    def store(self) -> ItemResult[Literal["ok", "empty", "inventory_full"]]:
        """Lege den Gegenstand, den der Harvester trägt, in den ersten freien Inventarplatz. So wird sein Trageplatz für den nächsten Gegenstand frei. Das funktioniert in jedem Sektor; zum Abladen muss der Harvester nicht zur Basis zurückkehren. Ist das Inventar voll, behält er den Gegenstand. Lass ihn fallen oder schaffe Platz, indem du etwas über den Shop verkaufst. Fester Ergebnisvertrag: `ItemResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.item_id`."""
        ...
    def drop(self) -> ActionResult[Literal["dropped", "empty", "occupied", "moving", "busy"]]:
        """Lass den getragenen Gegenstand im aktuellen Sektor des Harvesters fallen. Der Gegenstand kann danach wieder eingesammelt werden. So kannst du Gegenstände für später ablegen oder den Trageplatz freimachen, ohne etwas einzulagern. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def get_held(self) -> _str:
        """ID des Gegenstands, den der Harvester gerade trägt, oder eine leere Zeichenfolge, wenn sein Trageplatz frei ist. Rufe `self.get_held()` vor `collect()` auf: Ist das Ergebnis nicht leer, ist der Platz belegt. Rufe es auch vor `self.store()` auf: Ist das Ergebnis leer, gibt es nichts einzulagern. Ein unverzichtbarer erster Schritt in jeder Sammelschleife."""
        ...
    def get_position(self) -> _str:
        """ID des aktuellen Sektors als Zeichenfolge (z. B. `\"E14\"`). Nutze sie, um das nächste Ziel für `move()` zu planen. Bewegungen sind nur in benachbarte Zellen möglich. Das Skript muss daher die aktuelle Position kennen, um erreichbare Ziele zu berechnen."""
        ...
    def get_heat(self) -> _float:
        """Genauer aktueller Hitzewert (**0–100**), einschließlich anteiliger Abkühlung zwischen ganzzahligen Hitzekosten. Jede Bewegung mit `move()` erzeugt Hitze; auch ein Versuch mit `collect()` in einem leeren Sektor erzeugt Hitze. Während Spielzeit vergeht, kühlt der Harvester ständig passiv ab, auch während der Fahrt und beim Einsammeln. Prüfe den Wert vor der Fahrt. Liegt er nahe bei **100** und führt deine Route durch leere Zellen (jeweils +7 Hitze), halte zum Abkühlen an. Wenn die Route mitten beim Absuchen wegen `\"overheated\"` abbricht, verlierst du Stunden."""
        ...
    def get_max_heat(self) -> _int:
        """Maximaler Hitzewert, immer **100**. Sobald er erreicht ist, sind Bewegung und Einsammeln gesperrt, bis die Hitze wieder unter diesen Wert fällt. Die Methode ermöglicht es Skripten, Grenzwerte zu berücksichtigen, ohne die Zahl fest einzutragen."""
        ...
    def is_overheated(self) -> _bool:
        """`True`, wenn die Hitze `>= 100` beträgt. Kurzform für `self.get_heat() >= self.get_max_heat()`. Nutze die Abfrage als Bedingung für einen frühen Ausstieg, wenn du den Harvester gezielt abkühlen lassen willst: `if self.is_overheated(): sleep(1)`. Der Harvester kühlt passiv ab, sobald Spielzeit vergeht."""
        ...
    def water_level(self) -> _float:
        """Lies ab, wie viel Wasser sich derzeit im Tank des Harvesters befindet, in Tonnen und einschließlich Bruchteilen. Jede Bewässerung verbraucht **1 t**. Vergleiche den Wert mit `water_capacity()`, um das Nachfüllen aus den Wassertanks des Heimat-Außenpostens zu planen."""
        ...
    def water_capacity(self) -> _float:
        """Lies die maximale Wassermenge ab, die der Harvester mitführen kann, in Tonnen; derzeit **5 t**. Vergleiche den Wert mit `water_level()`, um den Füllstand des Tanks zu prüfen."""
        ...
    def load_seed(self, seed: _str) -> ActionResult[Literal["ok", "locked", "invalid_seed", "no_seed", "holding", "overheated", "moving", "busy"]]:
        """Übertrage von überall im Raster einen Samen einer Pflanzenart aus dem Inventar des Heimat-Außenpostens in den einzigen Trageplatz des Harvesters. Verwende nach der Fahrt zu einer leeren Feldzelle dieselbe Samen-ID mit `plant(seed)`. Das Laden schlägt fehl, solange der Harvester einen anderen Gegenstand trägt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def plant(self, seed: _str) -> ActionResult[Literal["ok", "locked", "invalid_seed", "no_seed", "not_empty", "base_sector", "overheated", "moving", "busy"]]:
        """Säe den Samen, den der Harvester gerade in seinem Trageplatz hält, in diese leere Zelle. Das Argument muss diesen mitgeführten Samen bezeichnen. Der Basissektor dient als Depotgelände; dort kann nicht gesät werden. Die Aussaat dauert **0,5 Stunden**. Der mitgeführte Samen wird verbraucht und die neue Pflanze erscheint erst, wenn die Aktion abgeschlossen ist. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def deploy(self, kit: _str) -> ActionResult[Literal["ok", "locked", "no_kit", "not_empty", "invalid_kit", "overheated", "moving", "busy"]]:
        """Stelle einen unterstützten Feldmaschinen-Bausatz in der aktuellen leeren Zelle auf. Dabei wird ein Bausatz aus dem Inventar verbraucht. Die Installation dauert **0,25 Stunden** und pausiert das Skript. Mit `deployables()` erhältst du die IDs der verfügbaren Bausätze. Saatgutmaschinen und andere Außenpostengebäude stellst du über das Inventar auf. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def deployables(self) -> _list[_str]:
        """Liste der durch deine aktuelle Forschung freigeschalteten Bausatz-IDs für fest installierte Feldmaschinen. Sie zeigt grundsätzlich verfügbare Möglichkeiten und prüft keine konkrete Aufstellung: `deploy(...)` prüft weiterhin den Inventarbestand, die aktuelle Zelle, Bewegung, Hitze und ob der Harvester beschäftigt ist."""
        ...
    def light(self) -> ActionResult[Literal["ok", "locked", "not_plantable", "overheated", "moving", "busy"]]:
        """Beleuchte die aktuelle bepflanzbare Zelle mit der Arbeitslampe des Harvesters, auch wenn sie bereits beleuchtet wird oder im Bereich einer Pflanzenlampe liegt. Jede Anwendung setzt die Wirkungsdauer nach Abschluss der Arbeit auf **24 Stunden** und ersetzt die verbleibende Zeit. Das Beleuchten dauert **0,25 Stunden** und pausiert das Skript. Später kannst du mit einer Pflanzenlampe vier direkt benachbarte Zellen (oben, unten, links und rechts) dauerhaft beleuchten. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def water(self) -> ActionResult[Literal["ok", "locked", "insufficient_water", "not_plantable", "overheated", "moving", "busy"]]:
        """Bewässere die aktuelle bepflanzbare Zelle aus dem Vorrat des Harvesters, auch wenn sie bereits bewässert wurde oder im Bereich eines Sprinklers liegt. Jede Bewässerung verbraucht **1 t** und setzt die Wirkungsdauer nach Abschluss der Arbeit auf **24 Stunden**; die verbleibende Zeit wird ersetzt. Das Bewässern dauert **0,25 Stunden** und pausiert das Skript. Mit `refill_water()` kannst du an jeder Stelle des lokalen Rasters Wasser aus den Tanks des Heimat-Außenpostens nachfüllen. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def refill_water(self) -> ActionResult[Literal["ok", "locked", "moving", "overheated", "tank_empty", "already_full", "busy"]]:
        """Fülle den Wasservorrat des Harvesters von überall im Raster aus den Wassertanks des Heimat-Außenpostens auf. Das Nachfüllen dauert **0,25 Stunden** und pausiert das Skript. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def dispense_salt(self) -> ActionResult[Literal["ok", "locked", "no_salt", "not_plantable", "overheated", "moving", "busy"]]:
        """Behandle die aktuelle bepflanzbare Zelle mit einer Einheit `salt` aus dem Inventar, auch wenn sie bereits gesalzen wurde oder im Bereich eines Dosierers liegt. Jede Anwendung setzt die Wirkungsdauer nach Abschluss der Arbeit auf **24 Stunden** und ersetzt die verbleibende Zeit. Das Ausbringen dauert **0,25 Stunden** und pausiert das Skript. Wasserpumpen erzeugen Salz als Nebenprodukt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def fertilize(self, item_id: _str = ...) -> ActionResult[Literal["ok", "invalid_input", "locked", "no_plant", "already_mature", "tier_conflict", "no_dose", "overheated", "moving", "busy"]]:
        """Gib der wachsenden Pflanze in der aktuellen Zelle eine Dosis Dünger Mk I, II oder III. Jede Einheit steigert den Ertrag für **8 Stunden**. Weitere Einheiten derselben Stufe verlängern die Wirkung. Warte, bis die aktive Dosis aufgebraucht ist, bevor du die Stufe wechselst. Das Dosieren beschäftigt den Harvester **0,25 Stunden** lang. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def accelerate(self) -> ActionResult[Literal["ok", "locked", "no_plant", "already_mature", "no_dose", "overheated", "moving", "busy"]]:
        """Gib der wachsenden Pflanze in der aktuellen Zelle eine Dosis `growth_accelerant`, um ihre Wachstumsgeschwindigkeit für **8 Stunden** zu verdoppeln. Das Dosieren beschäftigt den Harvester **0,25 Stunden** lang. Eine bereits ausgewachsene Pflanze wird von der Dosis nicht beeinflusst. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def amplify(self) -> ActionResult[Literal["ok", "locked", "no_dose", "overheated", "moving", "busy"]]:
        """Wende eine Einheit `yield_amplifier` an: die abschließende Verstärkung des Ertrags an Pflanzenfutter für das **gesamte Feld**. Dafür ist keine bestimmte Zelle nötig. Die Anwendung beschäftigt den Harvester **0,25 Stunden** lang. Die Dosis klingt im Verlauf von ungefähr einem Spieltag ab; rufe die Methode erneut auf, um die Wirkung aufrechtzuerhalten. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def amplifier_remaining(self) -> _float:
        """Verbleibende Wirkungsdauer des feldweiten Ertragsverstärkers in Stunden. Jede angewendete Einheit fügt **24 Stunden** hinzu. Gibt **0** zurück, wenn das Feld nicht verstärkt ist."""
        ...
    def uproot(self) -> ActionResult[Literal["ok", "no_plant", "inventory_full", "locked", "overheated", "moving", "busy"]]:
        """Entferne die Pflanze aus der aktuellen Zelle und lege einen passenden Samen ins Inventar. Das Ausgraben dauert **0,5 Stunden** und pausiert das Skript. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def undeploy(self) -> ActionResult[Literal["ok", "nothing", "not_empty", "script_present", "inventory_full", "overheated", "moving", "busy"]]:
        """Entferne die fest installierte Feldmaschine aus der aktuellen Zelle und lege ihren Bausatz zurück ins Inventar. Nur so lassen sich Pflanzenlampen, Sprinkler, Dosierer und Anbauautomaten entfernen. Der Speicher der Maschine muss leer sein, im Inventar muss Platz für die zurückgegebene Hardware sein und ihr zugewiesenes Skript darf nicht laufen. Selbst verfasste Skripte werden angehalten und unter Computer > Skripte > Nicht zugewiesen aufbewahrt. Unfertige Maschinenarbeiten und der nur für diese Maschine gespeicherte Ergebnisverlauf werden verworfen. Für vorgemerkte Aufträge des Anbauautomaten wurden noch kein Saatgut und keine Behandlungsmaterialien verbraucht. Das Entfernen dauert **0,25 Stunden** und pausiert das Skript des Harvesters. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def harvest(self) -> ActionResult[Literal["ok", "partial", "locked", "no_plant", "not_mature", "no_forage", "inventory_full", "overheated", "moving", "busy"]]:
        """Ernte die erntereife Pflanze in der aktuellen Zelle. Die Aktion dauert **0,5 Stunden**; bis zu ihrem Abschluss wird nichts übertragen. Danach wird so viel von `cell.forage` ins Inventar übertragen, wie hineinpasst. Ist der Ertrag größer als der freie Platz, bleibt der Rest gespeichert und die Pflanze stehen. Leere das Inventar und ernte erneut, um den Rest einzusammeln. Erst wenn der gesamte Ertrag eingesammelt wurde, wird die Pflanze entfernt und die Zelle für einen neuen physischen Samen frei. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def cell(self, sector: _str) -> Cell | None:
        """Lies einen Sektor des Rasters als Momentaufnahme vom Typ `Cell` aus. Nicht gescannter natürlicher Boden hat bis zum Scannen den Status `\"unknown\"`; das Depot sowie von Spielern angelegte Pflanzen und Versorgungsmaschinen bleiben sichtbar. Die Momentaufnahme enthält Pflanze, Wachstum, Bedingungen und die verbleibende Wirkungsdauer von Behandlungen. Für einen ungültigen Sektor wird `None` zurückgegeben."""
        ...
    def cells(self) -> _list[Cell]:
        """Lies alle Sektoren des Harvester-Rasters als Liste von `Cell`-Momentaufnahmen aus. Nicht gescannter natürlicher Boden meldet den Status `\"unknown\"`; scanne Sektoren, bevor du ihre Belegung bei der Planung berücksichtigst. Nutze die Liste, um die Aussaat im ganzen Feld, Behandlungsrouten, das Ausgraben, das Entfernen von Feldmaschinen und die Ernte zu planen."""
        ...
    def position(self) -> _str:
        """ID des aktuellen Sektors als Zeichenfolge. Dieselbe Positionsangabe wie bei `get_position()`, hier als Zugriff im Stil einer Eigenschaft für Raster-Skripte verfügbar."""
        ...
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

## `MiningDrill`

```python
class MiningDrill(Component):
    """Bergbaubohrer: Stationärer Mk-I-Bohrer für Vorkommen bis Härte 1 (Eisen, Silizium): 25 t/h bei Standardreinheit und 10 W während des Abbaus."""
    name: _str
    def drill_rate(self) -> _float:
        """Aktuelle Förderrate für Mineralien in t/h: die volle Rate während des Bohrens und **0**, wenn der Bohrer ausgeschaltet ist, sich unter ihm keine Lagerstätte befindet, er deren Härte nicht bewältigen kann oder sein Lager voll ist. Der Wert berücksichtigt den Reinheitsgrad des Standorts und die Stufe des Bohrers."""
        ...
    output: PickupOutputSlot
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

## `MiningDrillHeavy`

```python
class MiningDrillHeavy(Component):
    """Schwerer Bergbaubohrer: Stationärer Mk-III-Bohrer für Vorkommen bis Härte 4, also alle Mineralien einschließlich Neutronium: 200 t/h bei Standardreinheit und 100 W während des Abbaus."""
    name: _str
    def drill_rate(self) -> _float:
        """Aktuelle Förderrate für Mineralien in t/h: die volle Rate während des Bohrens und **0**, wenn der Bohrer ausgeschaltet ist, sich unter ihm keine Lagerstätte befindet, er deren Härte nicht bewältigen kann oder sein Lager voll ist. Der Wert berücksichtigt den Reinheitsgrad des Standorts und die Stufe des Bohrers."""
        ...
    output: PickupOutputSlot
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

## `MiningDrillIndustrial`

```python
class MiningDrillIndustrial(Component):
    """Industrieller Bergbaubohrer: Stationärer Mk-II-Bohrer für Vorkommen bis Härte 3, wodurch Titan, Kobalt, Blei und Seltene Erden hinzukommen: 75 t/h bei Standardreinheit und 35 W während des Abbaus."""
    name: _str
    def drill_rate(self) -> _float:
        """Aktuelle Förderrate für Mineralien in t/h: die volle Rate während des Bohrens und **0**, wenn der Bohrer ausgeschaltet ist, sich unter ihm keine Lagerstätte befindet, er deren Härte nicht bewältigen kann oder sein Lager voll ist. Der Wert berücksichtigt den Reinheitsgrad des Standorts und die Stufe des Bohrers."""
        ...
    output: PickupOutputSlot
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

## `NavModule`

```python
class NavModule:
    """self.nav (Fahrzeuge)"""
    def set_target(self, x: _float, y: _float) -> ActionResult[Literal["ok", "not_mounted", "invalid", "out_of_bounds", "busy"]]:
        """Lege die Zielkoordinaten fest, zu denen das Fahrzeug fahren soll. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def set_throttle(self, power: _float) -> ActionResult[Literal["ok", "not_mounted", "busy"]]:
        """Stelle die Gasstellung ein (0,0-1,0; Werte außerhalb des Bereichs werden begrenzt). Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def throttle(self) -> _float:
        """Aktuell eingestellte Gasstellung (**0,0-1,0**). Gibt den Wert zurück, den das Skript zuletzt mit `set_throttle(...)` gesetzt hat. Anders als `get_speed()` beschreibt `throttle()` die Vorgabe, die sich nicht von Tick zu Tick ändert; `get_speed()` gibt an, wie schnell sich das Fahrzeug im letzten Tick tatsächlich bewegt hat."""
        ...
    def brake(self) -> ActionResult[Literal["ok", "not_mounted"]]:
        """Halte das Fahrzeug an (Gasstellung auf 0 gesetzt). Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def get_position(self) -> Position:
        """Fahrzeugposition als `Position`-Objekt mit `.x` und `.y`."""
        ...
    def get_speed(self) -> _float:
        """Fahrzeuggeschwindigkeit in m/h."""
        ...
    def get_distance_to(self, x: _float, y: _float) -> _float:
        """Entfernung des Fahrzeugs zum angegebenen Punkt in Metern. Das Fahrzeug ist angekommen, sobald der Wert 2 oder weniger beträgt; exakt null wird selten erreicht. Eine Warteschleife läuft deshalb mit `while self.nav.get_distance_to(x, y) > 2:` weiter. Wenn die nächste Aktion ein Gebäude betrifft, fahre zu dessen `BuildingRef.position`."""
        ...
    def speed_multiplier(self) -> _float:
        """Höchstgeschwindigkeitsfaktor: **1,0** in der Grundausstattung oder **1 + Anzahl montierter Sport-Navigationen** beim Pionier. Das beeinflusst nur die Geschwindigkeit; die Reichweite hängt weiterhin von Batterie, Gasstellung, Ladung und Energieverbrauch bei der Fortbewegung ab."""
        ...
```

## `NavModuleComponent`

```python
class NavModuleComponent(Component):
    """Navigationsmodul: Ermöglicht einem Fahrzeug die Fahrt über `self.nav`. Ein einfaches Modul bietet **1,0×** Höchstgeschwindigkeit. Eine Sport-Navigation am selben Fahrzeug bietet **2×** Höchstgeschwindigkeit bei **2,6×** Leistungsaufnahme für die Bewegung; bei Vollgas entspricht das etwa **1,3×** Batterieverbrauch pro Meter. Jede weitere Sport-Navigation erhöht die Höchstgeschwindigkeit um **1,0×** der Basisgeschwindigkeit und lässt die Leistungsaufnahme noch schneller steigen. Das Modul passt in einen `nav`- oder `universal`-Platz. Lass das Skript bis zur Ankunft weiterlaufen. Wenn es gestoppt wird, endet oder einen Fehler ausgibt, hält das Fahrzeug an und verwirft seine Route."""
    name: _str
    def set_target(self, x: _float, y: _float) -> ActionResult[Literal["ok", "not_mounted", "invalid", "out_of_bounds"]]:
        """Legt die Zielkoordinaten für die Fahrt fest. Die Methode **kehrt sofort zurück**; das Fahrzeug fährt in den folgenden Ticks weiter, solange dieses Skript aktiv bleibt. Frage `get_distance_to(x, y)` oder `get_position()` in einer Warteschleife ab, um zu erkennen, wann es nahe genug am Ziel ist. Verwende einen Spielraum, normalerweise `while self.nav.get_distance_to(x, y) > 2:`, statt auf einen Abstand von exakt null zu warten. Rufe danach `self.nav.brake()` auf, bevor du `drill.mine()` oder eine andere Aktion im Stand ausführst. Für eine Aktion an einem Gebäude steuere dessen `BuildingRef.position` an, nicht den Ankerpunkt der Außenpostenfläche. Wenn das Skript gestoppt wird, endet oder einen Fehler ausgibt, hält das Fahrzeug an und verwirft seine Route. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def set_throttle(self, power: _float) -> ActionResult[Literal["ok", "not_mounted"]]:
        """Stellt das Fahrtempo ein (**0,0–1,0**; Werte außerhalb des Bereichs werden begrenzt). Mit `self.nav.set_throttle(0.5)` fährt das Fahrzeug gleichmäßig; bei `1.0` fährt es schnell, verbraucht aber mehr Batterie pro Meter. Nutze die Einstellung auf langen Fahrten, um Geschwindigkeit gegen Reichweite abzuwägen. Bei einem Stopp, dem Skriptende, einem Fehler oder `brake()` wird sie auf **0** zurückgesetzt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def throttle(self) -> _float:
        """Aktuell eingestelltes Fahrtempo (**0,0–1,0**). Gibt den Wert zurück, den das Skript zuletzt mit `self.nav.set_throttle(...)` gesetzt hat, oder **0** nach einem Stopp, dem Skriptende, einem Fehler oder `brake()`. Anders als `get_speed()` zeigt `throttle()` die gewünschte Einstellung; `get_speed()` zeigt, wie schnell sich das Fahrzeug im letzten Tick tatsächlich bewegt hat."""
        ...
    def brake(self) -> ActionResult[Literal["ok", "not_mounted"]]:
        """Hält das Fahrzeug sofort an, setzt Fahrtempo und Geschwindigkeit auf **0** und setzt das aktuelle Ziel auf die momentane Fahrzeugposition zurück. Verwende die Methode, wenn ein Skript eine Fahrt unterwegs abbrechen muss, etwa um zu einem näheren Standort umzuleiten. Das verbraucht weniger Batterie, als bis zum bisherigen Ziel zu fahren. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def get_position(self) -> Position:
        """Aktuelle Position als `Position`-Objekt mit `.x` und `.y` in Metern von der Basis aus. Lies sie bei jedem Durchlauf einer Fahrschleife, um die Ankunft zu erkennen, das nächste Teilziel zu planen oder die Route zu protokollieren. Siehe `Position`."""
        ...
    def get_speed(self) -> _float:
        """Geschwindigkeit in Metern pro Stunde, gemessen im letzten Fahrtick. Im Stillstand oder nach dem Bremsen **0**; bei Fahrtempo **1,0** bis zur Höchstgeschwindigkeit des Navigationsmoduls. Prüfe damit, ob das Fahrzeug tatsächlich fährt. Zeigt die Methode `0`, obwohl du eine Fahrt erwartest, liegt ein Problem mit der Stromversorgung oder dem Ziel vor. Ein gerade ausgeführtes `set_throttle(...)` wirkt sich erst nach dem nächsten Fahrtick auf diesen Wert aus."""
        ...
    def get_distance_to(self, x: _float, y: _float) -> _float:
        """Luftlinienentfernung in Metern von der aktuellen Fahrzeugposition zum angegebenen Punkt. Verwende sie in einer Warteschleife, um die Nähe zum Ziel zu erkennen. Das Fahrzeug ist angekommen, sobald die Entfernung 2 oder weniger beträgt (warte nie auf exakt null). Die Schleife läuft daher weiter, solange der Wert `> 2` ist. Bei der Ankunft hält das Fahrzeug nicht von selbst an. Rufe vor einer Aktion im Stand am Zielort `brake()` auf. Für eine Aktion an einem Gebäude steuere dessen `BuildingRef.position` an. `set_target()` wartet nicht, während das Fahrzeug fährt. Die Fahrt wird abgebrochen, wenn das Skript gestoppt wird, endet oder einen Fehler ausgibt. Der Wert ist die reine Luftlinienentfernung und berücksichtigt keine Hindernisse."""
        ...
    def speed_multiplier(self) -> _float:
        """Aktueller Multiplikator für die Höchstgeschwindigkeit: **1,0** mit einfacher Navigation und ohne Sport-Navigation oder **1 + Anzahl montierter Sport-Navigationen** beim Pionier. Nutze ihn, um Fahrzeiten und Erkundungsfahrzeuge zu planen. Er beschreibt nur die Geschwindigkeit; die Reichweite hängt weiterhin von Batterie, Fahrtempo, Ladung und Leistungsaufnahme für die Bewegung ab."""
        ...
```

## `Pioneer`

```python
class Pioneer(Component):
    """Pionier: Ein modulares Langstreckenfahrzeug, mit dem du im Gelände fahren, scannen, Rohstoffe abbauen und bauen kannst. Das nackte Fahrgestell kann nichts; seine Fähigkeiten hängen vollständig von den Modulen, Batterien und der Fracht ab, die du in seine acht Steckplätze einsetzt."""
    name: _str
    def status(self) -> Literal["idle", "moving", "stranded", "scanning", "surveying", "drilling", "discarding", "constructing", "transferring", "charging", "queued", "being_rescued"]:
        """Lies die aktuelle physische Tätigkeit des Pioniers aus. Jeder Aufruf liefert den neuesten Zustand, auch über `get_component(...)`. Ein untätiger Pionier kann trotzdem ein laufendes Skript oder einen zugewiesenen Auftrag haben."""
        ...
    battery: Battery
    cargo: Cargo
    nav: NavModule
    sonar: SonarModule
    drill: DrillModule
    constructor: ConstructorModule
    input: VehicleInputSlot
    output: OutputSlot
    def is_being_rescued(self) -> _bool:
        """`True`, während eine Rettungsdrohne einer Fahrzeugladestation diesen Pionier aktiv birgt. Nutze den Wert, um Fahr-, Bergbau- oder Bauskripte zu pausieren, auch wenn der Batteriestand bereits wieder über null steigt."""
        ...
    def rescue_status(self) -> Literal["none", "outbound", "charging", "returning"]:
        """Aktuelle Phase der Rettungsmission für diesen Pionier: `\"none\"`, `\"outbound\"`, `\"charging\"` oder `\"returning\"`. `\"returning\"` bedeutet, dass die Rettungsdrohne zurückkehrt und der Pionier wieder frei ist."""
        ...
    def dock(self, station: _str) -> ActionResult[Literal["ok", "station_not_found", "under_construction", "not_at_station"]]:
        """Wähle, an welcher Fahrzeugladestation dieser geparkte Pionier andockt: `self.dock(\"charging_station_2\")`. Jede Station innerhalb eines Außenpostens versorgt den gesamten Außenposten; so kannst du zwischen ihnen wählen. Ohne Auswahl dockt der Pionier an der infrage kommenden Station an, deren Position bzw. Außenpostenmitte am nächsten liegt. Bei gleichem Abstand gewinnt die Station, deren ID alphabetisch zuerst kommt. Die Auswahl gilt, bis der Pionier wegfährt oder die Station entfernt wird. Beim Wechsel zu einer anderen Station endet jeder Ladevorgang an der alten. Die neue Station lädt den Pionier, sobald ihr eigenes Skript `charge()` aufruft. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def current_station(self) -> _str:
        """Feste ID der Fahrzeugladestation, an der dieser Pionier angedockt ist – unabhängig davon, ob er sie mit `dock()` gewählt hat oder standardmäßig dort angedockt ist. Leere Zeichenfolge, während der Pionier fährt oder abseits aller Stationen parkt."""
        ...
    def modules(self) -> _list[MountSlot]:
        """Prüfe jeden Steckplatz am Fahrgestell. Gibt eine Liste von `MountSlot` zurück, beim Pionier mit acht Einträgen. Jeder Eintrag hat `.index` (an `mount` / `unmount` übergeben), `.type` (beim Pionier immer `\"universal\"`), `.module_id` (montiertes Modul oder `None` bei einem leeren Platz), `.internal_count` (bei Batteriehaltern und Frachtgestellen ungleich null) sowie `.internal_items` (Liste der IDs installierter tragbarer Gegenstände). Rufe die Methode vor `self.mount(...)` oder `self.install(...)` auf, um einen freien Zielplatz zu finden. Siehe `MountSlot`."""
        ...
    def mount(self, slot_index: _int, item_id: _str) -> ActionResult[Literal["ok", "not_at_service_point", "locked", "item_not_in_inventory", "unknown_module", "slot_not_compatible", "slot_occupied", "invalid_slot", "capability_already_mounted"]]:
        """Fordere einen Hardware-Serviceauftrag an, um ein Modul aus dem Inventar am Steckplatz mit dem ganzzahligen Index `slot_index` zu montieren: `self.mount(0, \"nav_module\")`. Biologische Feldmodule sind nur für Drohnen geeignet. Der Pionier muss im Servicebereich der Heimatbasis oder eines gegründeten, betriebsbereiten Außenpostens geparkt sein. Dieser auf Hardware beschränkte Service macht das Inventar an entfernten Außenposten nicht zu einem Frachtendpunkt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def unmount(self, slot_index: _int) -> ActionResult[Literal["ok", "not_at_service_point", "slot_empty", "invalid_slot", "holder_not_empty", "inventory_full"]]:
        """Fordere einen Hardware-Serviceauftrag an, der das Modul am Steckplatz mit dem ganzzahligen Index `slot_index` ins Inventar zurückgibt: `self.unmount(0)`. Der Pionier muss im Servicebereich der Heimatbasis oder eines gegründeten, betriebsbereiten Außenpostens geparkt sein. Leere alle internen Fächer, bevor du einen Halter oder ein Gestell entfernst. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def install(self, slot_index: _int, internal_index: _int, item_id: _str) -> ActionResult[Literal["ok", "not_at_service_point", "locked", "invalid_slot", "invalid_internal_slot", "slot_empty", "not_container", "item_not_accepted", "internal_slot_occupied", "item_not_in_inventory"]]:
        """Fordere einen Serviceauftrag an, der eine tragbare Batterie oder einen leeren tragbaren Lagerbehälter aus dem Inventar in einen internen Steckplatz eines Behälters einsetzt; der Steckplatzindex muss ganzzahlig sein. `self.install(0, 1, \"portable_battery\")` verwendet Fach **1** des Batteriehalters am Steckplatz **0** des Chassis. `self.install(4, 0, \"portable_bin\")` verwendet Fach **0** des Frachtgestells am Steckplatz **4** des Chassis. Der Pionier muss im Servicebereich der Heimatbasis oder eines gegründeten, betriebsbereiten Außenpostens geparkt sein. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def uninstall(self, slot_index: _int, internal_index: _int) -> ActionResult[Literal["ok", "not_at_service_point", "invalid_slot", "invalid_internal_slot", "slot_empty", "not_container", "internal_slot_empty", "inventory_full", "container_not_empty"]]:
        """Fordere einen Serviceauftrag an, der den tragbaren Gegenstand aus einem internen Steckplatz eines Behälters ins Inventar zurückgibt; der Steckplatzindex muss ganzzahlig sein: `self.uninstall(0, 1)`. Der Pionier muss im Servicebereich der Heimatbasis oder eines gegründeten, betriebsbereiten Außenpostens geparkt sein, und tragbare Lagerbehälter müssen leer sein. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
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

## `Position`

```python
class Position:
    """self.nav.get_position()"""
    x: _float
    y: _float
    def __iter__(self) -> Iterator[_float]:
        """Durchläuft zuerst `x`, dann `y`, damit du diese Position entpacken oder an `list()` übergeben kannst."""
        ...
```

## `Rover`

```python
class Rover(Component):
    """Rover: Dein erstes Expeditionsfahrzeug zum Fahren, Scannen und Abbauen. Das nackte Fahrgestell kann allein nichts; alle Fähigkeiten stammen von den Modulen in seinen drei festen Steckplätzen."""
    name: _str
    def status(self) -> Literal["idle", "moving", "stranded", "scanning", "surveying", "drilling", "discarding", "constructing", "transferring", "charging", "queued", "being_rescued"]:
        """Liest aus, was der Rover gerade tatsächlich tut. Jeder Aufruf erfasst den aktuellen Zustand, auch über `get_component(...)`. Ein Rover im Leerlauf kann trotzdem ein laufendes Skript oder einen zugewiesenen Auftrag haben."""
        ...
    battery: Battery
    cargo: Cargo
    nav: NavModule
    sonar: SonarModule
    drill: DrillModule
    input: VehicleInputSlot
    output: OutputSlot
    def is_being_rescued(self) -> _bool:
        """`True`, während eine Rettungsdrohne einer Fahrzeugladestation diesen Rover aktiv birgt. Damit kannst du Fahr- oder Abbauskripte pausieren, selbst wenn die Batterieladung bereits wieder über null gestiegen ist."""
        ...
    def rescue_status(self) -> Literal["none", "outbound", "charging", "returning"]:
        """Aktuelle Phase des Rettungseinsatzes für diesen Rover: `\"none\"`, `\"outbound\"`, `\"charging\"` oder `\"returning\"`. Bei `\"returning\"` fliegt die Rettungsdrohne nach Hause und der Rover ist wieder frei."""
        ...
    def dock(self, station: _str) -> ActionResult[Literal["ok", "station_not_found", "under_construction", "not_at_station"]]:
        """Wähle aus, an welcher Fahrzeugladestation dieser geparkte Rover andocken soll: `self.dock(\"charging_station_2\")`. Jede Station innerhalb eines Außenpostens deckt den gesamten Außenposten ab; so kannst du zwischen ihnen wählen. Ohne Auswahl dockt der Rover an der infrage kommenden Station an, deren Position bzw. Außenpostenmitte am nächsten liegt. Bei gleichem Abstand gewinnt die Station, deren ID alphabetisch zuerst kommt. Die Auswahl gilt, bis der Rover wegfährt oder die Station entfernt wird. Beim Wechsel zu einer anderen Station endet jeder Ladeauftrag an der alten. Die neue Station lädt den Rover, sobald ihr eigenes Skript `charge()` aufruft. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def current_station(self) -> _str:
        """Feste ID der Fahrzeugladestation, an der dieser Rover angedockt ist, ob durch Auswahl mit `dock()` oder automatisch. Ein leerer String, während der Rover fährt oder abseits aller Stationen parkt."""
        ...
    def modules(self) -> _list[MountSlot]:
        """Zeigt die montierten Module an. Gibt eine Liste von `MountSlot` zurück, einen Eintrag pro Steckplatz am Fahrgestell. Jeder Eintrag enthält `.index` (für `mount` / `unmount`), `.type` (welche Module passen), `.module_id` (die ID des montierten Moduls oder `None`) und `.internal_items` (bei den Funktionssteckplätzen des Rovers leer). Rufe die Methode vor `self.mount(...)` auf, um einen freien Steckplatz zu finden und zu prüfen, ob dessen Typ das gewünschte Modul aufnimmt. Siehe `MountSlot`."""
        ...
    def mount(self, slot_index: _int, item_id: _str) -> ActionResult[Literal["ok", "not_at_service_point", "locked", "item_not_in_inventory", "unknown_module", "slot_not_compatible", "slot_occupied", "invalid_slot", "capability_already_mounted"]]:
        """Fordere einen Hardware-Serviceauftrag an, um ein Modul aus dem Inventar am Steckplatz mit dem ganzzahligen Index `slot_index` zu montieren: `self.mount(0, \"nav_module\")`. Biologische Feldmodule sind nur für Drohnen geeignet. Der Rover muss im Servicebereich der Heimatbasis oder eines gegründeten, betriebsbereiten Außenpostens geparkt sein. Dieser auf Hardware beschränkte Service macht das Inventar an entfernten Außenposten nicht zu einem Frachtendpunkt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def unmount(self, slot_index: _int) -> ActionResult[Literal["ok", "not_at_service_point", "slot_empty", "invalid_slot", "holder_not_empty", "inventory_full"]]:
        """Fordere einen Hardware-Serviceauftrag an, der das Modul am Steckplatz mit dem ganzzahligen Index `slot_index` ins Inventar zurückgibt: `self.unmount(0)`. Der Rover muss im Servicebereich der Heimatbasis oder eines gegründeten, betriebsbereiten Außenpostens geparkt sein, und Containermodule müssen leer sein. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def install(self, slot_index: _int, internal_index: _int, item_id: _str) -> ActionResult[Literal["ok", "not_at_service_point", "locked", "invalid_slot", "invalid_internal_slot", "slot_empty", "not_container", "item_not_accepted", "internal_slot_occupied", "item_not_in_inventory"]]:
        """Installiert einen tragbaren Gegenstand (Tragbare Batterie / Tragbarer Lagerbehälter) im internen Steckplatz eines Containermoduls. **Beim Rover nicht verwendbar**: Seine festen Steckplätze nehmen nur Navigations-, Sonar- und Bohrmodule auf, keine Containermodule. Die modulare Variante ist der Pionier. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def uninstall(self, slot_index: _int, internal_index: _int) -> ActionResult[Literal["ok", "not_at_service_point", "invalid_slot", "invalid_internal_slot", "slot_empty", "not_container", "internal_slot_empty", "inventory_full", "container_not_empty"]]:
        """Entfernt einen tragbaren Gegenstand aus dem internen Steckplatz eines Containermoduls. **Beim Rover nicht verwendbar**, aus demselben Grund wie `install`. Die modulare Variante ist der Pionier. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
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

## `SonarModule`

```python
class SonarModule:
    """self.sonar (Fahrzeuge)"""
    def scan(self) -> SonarScanResult[Literal["ok", "too_hard", "tier_too_low", "research_required", "wrong_scanner", "busy", "no_power"]]:
        """Punktweise Sonarsuche nach Standorten in der Nähe. Eine abgeschlossene Suche kann keine passenden Kontakte finden. Für Mineralkontakte gelten Sonarreichweite und Härtegrenze; für thermische, Wasser-, Öl- und exotische Kontakte muss außerdem die passende Forschung abgeschlossen sein. Auch nach einer erfolgreichen Suche kann ein Kontakt unidentifiziert bleiben: Er wird mit seinen Koordinaten und einem Grund getrennt gemeldet und bleibt ungescannt, bis das richtige Instrument ihn erreicht. Die Suche ergänzt neu klassifizierte Standorte im Logbuch. Eine veraltete gespeicherte Modulreferenz löst `ReferenceError` aus. Fester Ergebnisvertrag: `SonarScanResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.sites` und `.blocked`."""
        ...
    def survey(self, site: SiteRef) -> SurveyResult[Literal["ok", "busy", "not_discovered", "research_required", "tier_too_low", "out_of_range", "too_hard", "no_power"]]:
        """Decke die verfügbaren Details eines ergiebigen Standorts auf. Eine inerte `GeologicalAnomaly` ist bereits identifiziert, daher kostet ihre Erkundung nichts. Auch eine erneute Erkundung ist kostenlos, sofern nicht eine tiefere Sonarstufe weitere Details aufdecken kann. Ungültige Standortwerte lösen `ValueError` aus; eine veraltete gespeicherte Modulreferenz löst `ReferenceError` aus. Fester Ergebnisvertrag: `SurveyResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.site`."""
        ...
    def range(self) -> _float:
        """Sonarreichweite in Metern (**50** Basis, **180** Weit, **280** Tief). Eine veraltete gespeicherte Modulreferenz löst `ReferenceError` aus."""
        ...
    def hardness_limit(self) -> _int:
        """Maximale Mineralhärte, die dieses Sonar identifizieren kann (**1** Basis, **3** Weit, **4** Tief). Eine veraltete gespeicherte Modulreferenz löst `ReferenceError` aus."""
        ...
    def tier(self) -> Literal["basic", "wide", "deep"]:
        """Erkundungstiefenstufe des montierten Sonars: `\"basic\"` / `\"wide\"` / `\"deep\"`. Sie bestimmt, welche Details zu thermischen und exotischen Standorten aufgedeckt werden; `\"deep\"` ist außerdem nötig, um nach Freischaltung der **Erdölerkundung** Ölquellen zu entdecken. Eine veraltete gespeicherte Modulreferenz löst `ReferenceError` aus."""
        ...
```

## `SonarModuleComponent`

```python
class SonarModuleComponent(Component):
    """Sonarmodul: Findet und untersucht Fundorte in der Welt über `self.sonar`. Ein Scan prüft die Umgebung des Fahrzeugs; bloßes Fahren scannt nicht. Nutze `get_component(\"nocturna\").points_of_interest()`, um ungescannte „?“-Markierungen zu finden. Fahre in die Nähe einer Markierung und rufe dann `scan()` und `survey(site)` auf. Jede Sonarstufe erfasst Mineralien bis zu ihrer Härtegrenze: Einfach **50 m**, Härte **1**; Weit **180 m**, Härte **3** (erfasst zusätzlich Titan und Kobalt); Tief **280 m**, Härte **4**. Forschung schaltet Dampfschlote, Brunnen und exotische Vorkommen frei. Die Ergebnisse werden im Logbuch gespeichert. Die lokalen Sektoren des Harvesters, biologische Fundorte und Strahlungsfelder werden mit anderen Scannern erfasst."""
    name: _str
    def scan(self) -> SonarScanResult[Literal["ok", "too_hard", "tier_too_low", "research_required", "wrong_scanner", "busy", "no_power"]]:
        """Suche im Umkreis der aktuellen Fahrzeugposition nach kompatiblen `Site`-Fundorten. Zu den Kontakttypen gehören `MiningSite`, `ThermalVent`, `WaterWell`, `OilWell`, `ExoticDeposit` und `GeologicalAnomaly`. Ein abgeschlossener Suchlauf trägt neu klassifizierte Kontakte ins Logbuch ein. Fester Ergebnisvertrag: `SonarScanResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.sites` und `.blocked`."""
        ...
    def survey(self, site: SiteRef) -> SurveyResult[Literal["ok", "busy", "not_discovered", "research_required", "tier_too_low", "out_of_range", "too_hard", "no_power"]]:
        """Decke die verfügbaren Details eines ergiebigen `Site`-Fundorts auf. Übergib entweder seine ID als Zeichenfolge oder ein `Site`-Objekt aus `scan()`. Eine erneute Untersuchung ist kostenlos und sofort abgeschlossen, sofern eine bessere Sonarstufe nicht noch mehr aufdecken kann. Inaktive `GeologicalAnomaly`-Kontakte sind bereits durch den Scan vollständig erfasst. Fester Ergebnisvertrag: `SurveyResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.site`."""
        ...
    def range(self) -> _float:
        """Aktuelle Sonarreichweite in Metern."""
        ...
    def hardness_limit(self) -> _int:
        """Maximale Mineralhärte, die dieses Sonar erkennen kann."""
        ...
    def tier(self) -> Literal["basic", "wide", "deep"]:
        """Sonarstufe für die Untersuchungstiefe: `\"basic\"` / `\"wide\"` / `\"deep\"`. Sie bestimmt, wie viel `survey()` von einem Dampf­schlot oder exotischen Vorkommen aufdeckt. Für die Entdeckung von Ölquellen ist außerdem `\"deep\"` erforderlich."""
        ...
```

## `VehicleRef`

```python
class VehicleRef:
    """fleet.vehicles()"""
    category: Literal["vehicle"]
    id: _str
    name: _str
    kind: Literal["rover", "pioneer"]
    status: Literal["idle", "moving", "stranded", "scanning", "surveying", "drilling", "discarding", "constructing", "transferring", "charging", "queued", "being_rescued"]
    x: _float
    y: _float
    def position(self) -> Position:
        """Momentaufnahme der Position zum Zeitpunkt, als diese Referenz zurückgegeben wurde."""
        ...
    battery_level: _float
    battery_wh: _float
    battery_capacity: _float
    is_docked: _bool
    docked_at: _str
    current_station: _str
    is_being_rescued: _bool
    rescue_status: Literal["none", "outbound", "charging", "returning"]
```
