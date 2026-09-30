# Models: Outpost, Building & Power Grid Models

Granular data models and return types extracted from `__builtins__.pyi`.

## `BuildingRef`

```python
class BuildingRef:
    """outpost.buildings() / outpost_network.outposts()[i].buildings()"""
    id: _str
    name: _str
    type_id: _str
    outpost_id: _str
    outpost: OutpostRef | None
    powered: _bool
    position: _list[_float]
```

## `Computer`

```python
class Computer(Component):
    """Bordcomputer: Verwaltet deine Geräte: Stelle eine Maschine, ein Fahrzeug oder eine Drohne aus dem Inventar an einem Außenposten auf, lege sie wieder ins Inventar, löse einen geleerten Außenposten auf und benenne deine eigenen Objekte um. Das entspricht der Schaltfläche zum Aufstellen auf der Inventarseite und dem Tab „System“ des Computers, ist aber per Skript erreichbar. Jeder Aufruf erfordert die Erforschung des Bordcomputers; die Schaltflächen funktionieren auch davor."""
    name: _str
    def deploy(self, item_id: _str, outpost: _str | Outpost | None = ...) -> ComputerDeployResult[Literal["ok", "no_kit", "locked", "not_deployable", "deploy_limit", "location_not_found", "wrong_biome_for_machine", "duplicate_outpost_machine", "missing_drone_station", "drone_station_full"]]:
        """Stelle ein Exemplar eines Gegenstands aus dem Inventar an einem Außenposten auf; ohne Angabe wird der Heimatposten verwendet. Die Maschine wird ohne Skript aufgestellt und tut nichts, bis du ihr eines zuweist – genau wie eine von Hand aufgestellte Maschine. Kann das Teilnetz des Außenpostens die Maschine noch nicht versorgen, wird sie ausgeschaltet aufgestellt. Fester Ergebnisvertrag: `ComputerDeployResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.machine_id`."""
        ...
    def undeploy(self, machine: _str | Component) -> ActionResult[Literal["ok", "locked", "not_found", "not_undeployable", "self_target", "cargo_present", "docked_drone", "construction_dependency", "inventory_full"]]:
        """Entferne eine aufgestellte Maschine, ein Fahrzeug oder eine Drohne und lege ihren Bausatz, montierte Module, enthaltene Gegenstände und Pakete für Ausbaustufen zurück ins Inventar. Gelagerte Ladung verhindert das Entfernen; leere sie daher zuerst. Selbst verfasste Skripte bleiben als nicht mehr zugeordnete Einträge erhalten. Ausrüstung im Gelände wird vom zugehörigen Harvester geborgen, Bauwerke auf der Karte von einem Pionier – nicht über diese Methode. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def decommission(self, outpost: _str | Outpost) -> ActionResult[Literal["ok", "locked", "not_found", "is_home", "not_empty", "construction_dependency", "inventory_full"]]:
        """Löse einen gegründeten Außenposten auf und lege seinen Außenposten-Bausatz zurück ins Inventar. Im Außenposten dürfen sich keine Maschinen mehr befinden; nichts wird dabei automatisch mit entfernt. Drohnen und Fahrzeuge gehören zu keinem Außenposten und blockieren das Auflösen daher nie. Rohre, Stromleitungen und Brücken, die mit ihm verbunden waren, bleiben auf der Karte und können von einem Pionier geborgen werden. Der Heimatposten bleibt dauerhaft bestehen. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def rename(self, target: _str | Component | Outpost, name: _str) -> ActionResult[Literal["ok", "locked", "not_found", "name_empty", "name_too_long", "name_taken"]]:
        """Ändere den Anzeigenamen einer Maschine oder eines Außenpostens. Jeder Name muss über alle Maschinen, Außenposten und Panels hinweg eindeutig sein. IDs ändern sich nie, daher funktionieren gespeicherte Verweise weiterhin. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
```

## `ComputerDeployResult`

```python
class ComputerDeployResult(Generic[_StatusT]):
    """computer.deploy()"""
    status: _StatusT
    message: _str
    machine_id: _str
```

## `Fleet`

```python
class Fleet:
    """get_component(\"fleet\")"""
    def vehicles(self) -> _list[VehicleRef]:
        """Alle eigenen Bodenfahrzeuge als schreibgeschützte `VehicleRef`-Momentaufnahmen. Verwende `.id`, wenn du ein Fahrzeug an Stations-APIs übergibst. Rufe `vehicles()` erneut auf, um aktuelle Referenzfelder zu erhalten, oder verwende `get_component(ref.id)` für die Live-API des Fahrzeugs."""
        ...
    def drones(self) -> _list[DroneRef]:
        """Alle eigenen Drohnen als schreibgeschützte `DroneRef`-Momentaufnahmen. Verwende `.id`, wenn du eine Drohne an Stations- oder Bergungs-APIs übergibst. Rufe `drones()` erneut auf, um aktuelle Referenzfelder zu erhalten, oder verwende `get_component(ref.id)` für die Live-API der Drohne."""
        ...
    def mobile_units(self) -> _list[MobileUnitRef]:
        """Alle eigenen Fahrzeuge und Drohnen in einer Liste von Momentaufnahmen. Verwende `.category`, um zwischen `\"vehicle\"` und `\"drone\"` zu unterscheiden. Frage die Daten erneut ab, um aktuelle Positionen und Statuswerte zu erhalten."""
        ...
```

## `FleetComponent`

```python
class FleetComponent(Component):
    """Flotte: Schreibgeschütztes Verzeichnis aller eigenen mobilen Einheiten: Bodenfahrzeuge und Drohnen. Nutze es für Übersichten, Ladeskripte, Rettungsschwellen und Einsatzentscheidungen, ohne Namen fest ins Skript einzutragen. Flottenreferenzen sind Momentaufnahmen; gesteuert werden die Einheiten weiterhin über ihr eigenes Skript oder die API der jeweiligen Station."""
    name: _str
    def vehicles(self) -> _list[VehicleRef]:
        """Alle eigenen Bodenfahrzeuge als Momentaufnahmen vom Typ `VehicleRef`. Jede Referenz enthält `.id`, `.name`, `.kind`, `.x`, `.y`, `.battery_level`, `.is_docked`, `.current_station`, `.is_being_rescued` und `.rescue_status`."""
        ...
    def drones(self) -> _list[DroneRef]:
        """Alle eigenen Drohnen als Momentaufnahmen vom Typ `DroneRef`. Jede Referenz enthält `.id`, `.name`, `.kind`, `.engine`, `.current_station`, `.battery_level` oder `.oil_level`, `.is_docked`, `.is_being_rescued` und `.rescue_status`."""
        ...
    def mobile_units(self) -> _list[MobileUnitRef]:
        """Alle eigenen Bodenfahrzeuge und Drohnen in einer Liste. Unterscheide mit `.category` zwischen `\"vehicle\"` und `\"drone\"`."""
        ...
```

## `LatticeGrid`

```python
class LatticeGrid:
    """.grid"""
    def width(self) -> _int:
        """Breite des Gitters in Zellen (32)."""
        ...
    def height(self) -> _int:
        """Höhe des Gitters in Zellen (32)."""
        ...
    def start(self) -> _list[_int]:
        """Eine garantiert sichere Startzelle, zurückgegeben als `[x, y]`. Prüfe sie zuerst, um einen Messwert zu erhalten und mit dem Ableiten weiterer sicherer Zellen zu beginnen."""
        ...
    def reset(self) -> ActionResult[Literal["ok"]]:
        """Behebe eine durch einen ausgelösten Knoten verursachte Störung, damit du im selben Skriptdurchlauf weiter prüfen kannst. Das verborgene Gitter und die garantiert sichere Startzelle bleiben unverändert. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def probe(self, x: _int, y: _int) -> LatticeProbeResult[Literal["ok", "node_tripped", "lattice_tripped"]]:
        """Prüfe eine nachweislich sichere Zelle mit ganzzahligen Koordinaten. Der Messwert ist die ganzzahlige Anzahl benachbarter instabiler Knoten im Bereich **0-8**. Wird ein Knoten ausgelöst, bleibt das Gitter gestört, bis `reset()` aufgerufen wird. Falsche Argumenttypen lösen `TypeError` aus; nicht ganzzahlige, nicht endliche oder außerhalb des Gitters liegende Koordinaten lösen `ValueError` aus, ohne ein intaktes Gitter zu stören. Fester Ergebnisvertrag: `LatticeProbeResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.reading`."""
        ...
```

## `Nocturna`

```python
class Nocturna(Component):
    """Nocturna: Liefert über `get_component(\"nocturna\")` beständige Daten für den gesamten Planeten Nocturna, darunter Kartengrenzen, Biome, Terraforming-Fortschritt und dauerhafte Kartenkontakte. Verborgene Folgen von Wetterereignissen fehlen bewusst; ihre Koordinaten stehen nur in den Sturmpaketen, die dein Stationsnetz auffängt. Sonarentdeckungen und Erkundungsdaten werden separat in `get_component(\"journal\")` gespeichert."""
    name: _str
    def get_name(self) -> _str:
        """Anzeigename dieses Planeten; gibt `\"Nocturna\"` zurück. Du kannst den Namen fest ins Skript schreiben, aber eine Abfrage hält es für eine spätere Umbenennung oder mehrere Planeten offen."""
        ...
    def get_bounds(self) -> Bounds:
        """Grenzen der Oberflächenkoordinaten als `Bounds`-Objekt mit `.min_x`, `.max_x`, `.min_y` und `.max_y`, jeweils in Metern von der Basis aus. Verwende sie, um Navigationsziele auf die zugängliche Oberfläche zu begrenzen oder zufällige gültige Koordinaten zu erzeugen: `import random; b = planet.get_bounds(); x = random.randint(b.min_x, b.max_x); y = random.randint(b.min_y, b.max_y)`. Siehe `Bounds`."""
        ...
    def contains(self, x: _float, y: _float) -> _bool:
        """`True`, wenn der Punkt `(x, y)` innerhalb der Oberflächengrenzen von Nocturna liegt. Nutze die Methode als Sicherheitsprüfung vor `nav.set_target()`: `if nocturna.contains(x, y): self.nav.set_target(x, y)`. Liegt das Ziel außerhalb der Grenzen, kehrt der Aufruf sofort zurück und das Fahrzeug fährt nicht los."""
        ...
    def biome_at(self, x: _float, y: _float) -> Literal["frozen", "coastal", "geothermal", "volcanic", "deep"]:
        """Biom-ID an der Weltkoordinate `(x, y)`. Gibt `\"frozen\"`, `\"coastal\"`, `\"geothermal\"`, `\"volcanic\"` oder `\"deep\"` zurück. Der Wert beschreibt die Geografie und bleibt für dieselbe Koordinate immer gleich. Nutze ihn, um das Verhalten eines Skripts überall auf dem Planeten an das Biom anzupassen: `if nocturna.biome_at(x, y) == \"volcanic\": deploy_heat_resistant()`."""
        ...
    def life_form_biome(self, item_id: _str) -> Literal["frozen", "coastal", "geothermal", "volcanic", "deep"] | None:
        """Ermittelt das heimische Biom einer Lebensform: `\"frozen\"`, `\"coastal\"`, `\"geothermal\"`, `\"volcanic\"` oder `\"deep\"`. Für andere Gegenstände wird `None` zurückgegeben. Eine Art gehört immer zum selben Biom, unabhängig davon, wo ein Exemplar gefunden wurde. Essenzverflüssiger nehmen nur Lebensformen an, die im Biom ihres Außenpostens heimisch sind. Eine Drohne kann das daher vor dem Entladen mit `nocturna.life_form_biome(item) == self.outpost.biome` prüfen."""
        ...
    def biomes(self) -> _list[_str]:
        """Listet alle Biom-IDs des Planeten auf. Nutze die Methode für Schleifen über den ganzen Planeten: `for biome in nocturna.biomes(): print(biome)`. Die Menge der Biome ändert sich während des Spiels nicht."""
        ...
    def terraform_progress(self) -> _float:
        """Fortschritt des Terraforming-Index auf einer Skala von **0–100 %**: **0** bedeutet unberührt; **100** steht für 1.000.000 TP und den Abschluss aller sechs Säulen. Die Atmosphäre macht 70 % des Index aus. Biomasse, Pflanzen und Tierwelt tragen jeweils eigene 10 % bei; keine dieser Säulen kann eine andere ersetzen. Nutze den Wert für Fortschrittsbedingungen: `if nocturna.terraform_progress() >= 50: ...`. Den reinen TP-Wert erhältst du mit `total_tp()`."""
        ...
    def total_tp(self) -> _float:
        """Der begrenzte Terraforming-Index in TP im Bereich von **0–1.000.000**. Temperatur, Sauerstoff und Druck tragen zusammen 700.000 TP bei; Biomasse, Pflanzen und Tierwelt jeweils 100.000 TP, die keine andere Säule ersetzen können. Die zugrunde liegenden Werte können nach ihrer letzten Phase weiter steigen, doch eine abgeschlossene Säule trägt keine weiteren Punkte zum Index bei. Der Wert steuert die Freischaltung systemübergreifender Forschung."""
        ...
    def points_of_interest(self) -> _list[PointOfInterest]:
        """Listet alle dauerhaften „?“-Kontakte auf der Planetenkarte auf, damit Skripte echte Orte ansteuern können. Jeder `PointOfInterest` hat ganzzahlige Koordinaten, ein `scanned`-Kennzeichen und einen `kind`-Wert, der `\"unknown\"` bleibt, bis ein Scanner den Kontakt erreicht. Filtere nach `not point.scanned`, fahre zu den Koordinaten und scanne mit dem Sonar eines Rovers oder Pioniers oder mit dem Bioscanner einer Drohne. Kann das mitgebrachte Gerät einen Kontakt nicht identifizieren, bleibt er auch nach einem erfolgreichen Scan ungescannt. Der Scan führt ihn dann in `scan.blocked` mit denselben Koordinaten und einem Grund auf. Merke dir solche Kontakte, sonst wählt deine Schleife immer wieder denselben aus. Siehe `PointOfInterest`."""
        ...
```

## `Outpost`

```python
class Outpost:
    """get_component(outpost_id) / get_component_by_name(outpost_name)"""
    id: _str
    def name(self) -> _str:
        """Anzeigename. Für den Heimat-Außenposten lautet er standardmäßig `\"Nocturna Base\"`, für gegründete Außenposten wird ein Name nach dem Muster `\"Outpost N\"` erzeugt. Du kannst ihn im Tab „Computersystem“ beliebig ändern. Der Name ist veränderlich; wenn du eine dauerhafte Kennung brauchst, verwende `id`."""
        ...
    def coords(self) -> _list[_int]:
        """Weltkoordinaten des Bezugspunkts des Außenpostens als `[x, y]`. Der Heimat-Außenposten liegt bei `[0, 0]`; gegründete Außenposten haben die im Planungsmodus gewählte Position."""
        ...
    def buildings_used(self) -> _int:
        """Anzahl der an diesem Außenposten errichteten Gebäude. Sensoren, mobile Einheiten, zentrale Strukturbauten und die Förderung an besonderen Orten zählen nicht mit."""
        ...
    def buildings_capacity(self) -> _int:
        """Weiche Obergrenze für Gebäude an diesem Außenposten. Jedes zusätzlich gezählte Gebäude verringert den Durchsatz von Produktion und Diensten. Die Nocturna Base hat einige zusätzliche Bauplätze zum Einstieg; gegründete Außenposten nutzen die reguläre Obergrenze."""
        ...
    def is_full(self) -> _bool:
        """Gibt `True` zurück, wenn dieser Außenposten seine weiche Gebäudeobergrenze erreicht oder überschritten hat. Die Obergrenze selbst verhindert das normale Errichten von Gebäuden nicht."""
        ...
    def is_home(self) -> _bool:
        """Gibt `True` zurück, wenn dies der Heimat-Außenposten ist (Standardname `\"Nocturna Base\"`)."""
        ...
    def buildings(self, type_id: _str = ...) -> _list[BuildingRef]:
        """Aktuelle Liste von `BuildingRef`-Momentaufnahmen mit einem Eintrag für jedes hier errichtete Gebäude. Übergib zum Filtern eine `type_id` (z. B. `\"storage_bin\"`) oder lass sie weg, um alle Gebäude zu erhalten. Jede Referenz enthält `.id` / `.name` / `.type_id` / `.outpost` / `.powered` / `.position`. Für aktuelle, typspezifische Werte (`count()`, `material()`, `recipe` usw.) rufst du `get_component(ref.id)` auf. So erhältst du Zugriff auf die vollständige Komponenten-API."""
        ...
    def harvesting_machines(self, type_id: _str = ...) -> _list[HarvestingMachineRef]:
        """Aktuelle Liste von `HarvestingMachineRef`-Momentaufnahmen für stationäre Maschinen auf dem Erntefeld dieses Außenpostens. Derzeit hat nur der Heimat-Außenposten, die Nocturna Base, ein solches Feld; gegründete Außenposten geben daher eine leere Liste zurück. Die Liste umfasst Pflanzenlampen, Sprinkler, Dosierer und Anbauautomaten. Sie belegen Feldzellen, beanspruchen aber keine Gebäudekapazität und erscheinen nicht in `buildings()`. Der mobile Harvester, Nutzpflanzen, lose Gegenstände, Wasserbrunnen und andere Förderanlagen an besonderen Orten sind nicht enthalten. Übergib zum Filtern eine `type_id` oder lass sie weg, um alle vier stationären Maschinentypen zu erhalten. Für aktuelle, typspezifische Werte verwendest du `get_component(ref.id)`."""
        ...
```

## `OutpostComponent`

```python
class OutpostComponent(Component):
    """Außenposten: Steht für den Heimatstützpunkt oder einen von dir gegründeten Außenposten. Du kannst ihn über seine unveränderliche ID mit `get_component(\"outpost_1\")` oder über seinen Anzeigenamen mit `get_component_by_name(\"Mining Camp\")` abrufen. Außenposten lassen sich auf der Registerkarte „System“ im Computer umbenennen. Verwende daher die ID für Skripte, die auch nach einer Umbenennung funktionieren sollen."""
    def name(self) -> _str:
        """Anzeigename. Der Heimatstützpunkt heißt anfangs `\"Nocturna Base\"`, von dir gegründete Außenposten heißen zunächst `\"Outpost N\"`. Du kannst sie auf der Registerkarte „System“ im Computer jederzeit umbenennen. Der Name ist veränderlich; verwende für dauerhafte Verweise vorzugsweise `id`."""
        ...
    def coords(self) -> _list[_int]:
        """Weltkoordinaten als `[x, y]`. Der Heimat-Außenposten liegt bei `[0, 0]`."""
        ...
    def buildings_used(self) -> _int:
        """Anzahl der an diesem Außenposten errichteten Gebäude. Sensoren, mobile Einheiten, Struktureinrichtungen und Förderung an interessanten Orten zählen nicht mit."""
        ...
    def buildings_capacity(self) -> _int:
        """Weiche Grenze für die Gebäudezahl an diesem Außenposten. Jedes mitgezählte Gebäude darüber verringert den Durchsatz von Produktion und Diensten. Nocturna Base hat anfangs einige zusätzliche Bauplätze; von dir gegründete Außenposten nutzen die Standardgrenze."""
        ...
    def is_full(self) -> _bool:
        """Gibt `True` zurück, wenn dieser Außenposten seine weiche Gebäudegrenze erreicht oder überschritten hat. Die Grenze selbst verhindert das normale Errichten von Gebäuden nicht."""
        ...
    def is_home(self) -> _bool:
        """Gibt `True` zurück, wenn dies der Heimat-Außenposten ist."""
        ...
    def buildings(self, type_id: _str = ...) -> _list[BuildingRef]:
        """Listet die an diesem Außenposten errichteten Gebäude als `BuildingRef`-Momentaufnahmen auf. Rufe `self.outpost.buildings()` auf, um alle zu erhalten, oder übergib zum Filtern eine Gebäude-`type_id`. Jeder Verweis hat `.id`, `.name`, `.type_id`, `.outpost`, `.powered` und `.position`; mit `get_component(ref.id)` erhältst du aktuelle, typspezifische Werte. Die Liste enthält Maschinen, die zur Gebäudekapazität zählen, aber keine Sensoren, mobilen Einheiten, Förderanlagen an interessanten Orten oder fest installierten Maschinen auf dem Erntefeld. Für diese Feldmaschinen verwende `harvesting_machines()`."""
        ...
    def harvesting_machines(self, type_id: _str = ...) -> _list[HarvestingMachineRef]:
        """Listet fest installierte Maschinen auf dem Erntefeld dieses Außenpostens als `HarvestingMachineRef`-Momentaufnahmen auf. Rufe die Methode ohne Argument auf, um dort alle Pflanzenlampen, Sprinkler, Dosierer und Anbauautomaten zu erhalten, oder übergib zum Filtern einen ihrer `type_id`-Werte. Sie belegen Feldzellen, verbrauchen keine Gebäudekapazität und erscheinen nicht in `buildings()`. Der mobile Harvester, Pflanzen, lose Gegenstände, Wasserbrunnen und andere Förderanlagen an interessanten Orten sind ausgeschlossen. Derzeit hat nur Nocturna Base ein Erntefeld; gegründete Außenposten liefern daher eine leere Liste. Mit `get_component(ref.id)` erhältst du aktuelle, typspezifische Werte."""
        ...
```

## `OutpostNetwork`

```python
class OutpostNetwork:
    """get_component(\"outpost_network\")"""
    def outposts(self) -> _list[OutpostRef]:
        """Alle eigenen Außenposten, einschließlich des Heimat-Außenpostens, als schreibgeschützte `OutpostRef`-Momentaufnahmen. Verwende `.id`, wenn du einen Außenposten an eine andere API übergibst. Ruf `outposts()` erneut auf, wenn du aktuelle Anzahlen oder Namen brauchst."""
        ...
    def home(self) -> OutpostRef:
        """Der Heimat-Außenposten als `OutpostRef`-Momentaufnahme."""
        ...
    def nearest(self, x: _float, y: _float) -> OutpostRef:
        """Der eigene Außenposten, der der angegebenen Weltkoordinate am nächsten liegt, als `OutpostRef`-Momentaufnahme."""
        ...
```

## `OutpostNetworkComponent`

```python
class OutpostNetworkComponent(Component):
    """Außenpostennetzwerk: Schreibgeschützter Index aller eigenen Außenposten, einschließlich des Heimat-Außenpostens. Nutze ihn für Routen, Bauplanung, Kapazitätsübersichten und die Wahl des nächsten Serviceorts, ohne `outpost_1`, `outpost_2` usw. fest einzutragen. `.x` und `.y` eines Außenpostens bezeichnen den Bezugspunkt seiner Grundfläche. Für eine Aktion an einem Gebäude wähle dessen `BuildingRef` am Außenposten und navigiere zu `.position`. Die Bauplanung erfolgt im Planungsmodus und über die gemeinsame Komponente `construction_blueprint`; die Arbeiten vor Ort erledigen Konstruktionsskripte."""
    name: _str
    def outposts(self) -> _list[OutpostRef]:
        """Alle eigenen Außenposten als `OutpostRef`-Momentaufnahmen. Jeder Verweis enthält `.id`, `.name`, `.x`, `.y`, `.is_home`, `.buildings_used`, `.buildings_capacity` und `.is_full`. Die Koordinaten bezeichnen die linke obere Ecke der Grundfläche, keinen Andockpunkt eines bestimmten Gebäudes."""
        ...
    def home(self) -> OutpostRef:
        """Der Heimat-Außenposten als `OutpostRef`."""
        ...
    def nearest(self, x: _float, y: _float) -> OutpostRef:
        """Der eigene Außenposten, der der angegebenen Weltkoordinate am nächsten liegt. Nützlich, bevor du ein Fahrzeug zum Aufladen nach Hause schickst oder einen Bereitstellungsort für einen Konstrukteur wählst."""
        ...
```

## `OutpostRef`

```python
class OutpostRef:
    """outpost_network.outposts() / outpost_network.home() / outpost_network.nearest()"""
    id: _str
    name: _str
    x: _int
    y: _int
    def position(self) -> Position:
        """Bezugspunkt oben links an der Fläche des Außenpostens als `Position`-Momentaufnahme. Er kennzeichnet den Außenposten, nicht den Andockpunkt eines bestimmten Gebäudes."""
        ...
    def coords(self) -> _list[_int]:
        """Bezugspunkt oben links an der Fläche des Außenpostens als `[x, y]`. Verwende `buildings()` und `BuildingRef.position`, wenn du zu einem bestimmten Versorgungsgebäude navigieren möchtest."""
        ...
    is_home: _bool
    biome: Literal["frozen", "coastal", "geothermal", "volcanic", "deep"]
    buildings_used: _int
    buildings_capacity: _int
    is_full: _bool
    def buildings(self, type_id: _str = ...) -> _list[BuildingRef]:
        """Aktuelle Liste von `BuildingRef`-Momentaufnahmen mit einem Eintrag für jedes hier errichtete Gebäude. Übergib zum Filtern eine `type_id` (z. B. `\"storage_bin\"`) oder lass sie weg, um alle Gebäude zu erhalten. Jede Referenz enthält `.id` / `.name` / `.type_id` / `.outpost` / `.powered` / `.position`. Für aktuelle, typspezifische Werte (`count()`, `material()`, `recipe` usw.) rufst du `get_component(ref.id)` auf. So erhältst du Zugriff auf die vollständige Komponenten-API."""
        ...
    def harvesting_machines(self, type_id: _str = ...) -> _list[HarvestingMachineRef]:
        """Aktuelle Liste von `HarvestingMachineRef`-Momentaufnahmen für stationäre Maschinen auf dem Erntefeld dieses Außenpostens. Derzeit hat nur der Heimat-Außenposten, die Nocturna Base, ein solches Feld; gegründete Außenposten geben daher eine leere Liste zurück. Die Liste umfasst Pflanzenlampen, Sprinkler, Dosierer und Anbauautomaten. Sie belegen Feldzellen, beanspruchen aber keine Gebäudekapazität und erscheinen nicht in `buildings()`. Der mobile Harvester, Nutzpflanzen, lose Gegenstände, Wasserbrunnen und andere Förderanlagen an besonderen Orten sind nicht enthalten. Übergib zum Filtern eine `type_id` oder lass sie weg, um alle vier stationären Maschinentypen zu erhalten. Für aktuelle, typspezifische Werte verwendest du `get_component(ref.id)`."""
        ...
```

## `PowerControl`

```python
class PowerControl(Component):
    """Stromsteuerung: Entdecke alle unabhängigen Stromnetze, prüfe angeschlossene Außenposten, Gebäude und Stromanlagen im Gelände und lies Erzeugung, Verbrauch, Batterieladung und Blitzreserve ab. Über eine gemeinsame Steuerung kannst du außerdem Maschinenschalter bedienen. Netzobjekte sind Momentaufnahmen der letzten abgeschlossenen Stromverteilung. Frage nach dem Betätigen eines Schalters oder dem Ändern von Leitungen in der nächsten Schleifeniteration erneut ab, damit Netzwerte und Zugehörigkeiten aktuell sind."""
    name: _str
    def grids(self) -> _list[PowerGrid]:
        """Gibt alle unabhängigen Stromnetze des Planeten als neue Liste von `PowerGrid`-Momentaufnahmen zurück. Isolierte fertiggestellte Außenposten und Stromanlagen im Gelände erscheinen als eigene Netze. Skripte müssen daher keine Netz-IDs erraten oder fest eintragen."""
        ...
    def grid(self, target_id: _str) -> PowerGrid | None:
        """Findet das Netz, zu dem `target_id` gehört. Die ID kann einen Außenposten, ein Gebäude oder eine Stromanlage im Gelände bezeichnen. Übergib die `.anchor_id` eines zurückgegebenen Netzes, um es erneut nachzuschlagen. Gibt `None` zurück, wenn das Ziel unbekannt, mobil, noch im Bau, kein Netzteilnehmer oder derzeit keinem Netz zugeordnet ist."""
        ...
    def total(self) -> PowerSummary:
        """Gibt eine planetenweite `PowerSummary` über alle unabhängigen Netze zurück. Herkömmliche Batteriespeicher und die Blitzreserve bleiben getrennt, damit die Automatisierung entscheiden kann, auf welche Energiequelle sie sich stützt."""
        ...
    def is_powered(self, machine_id: _str) -> _bool:
        """Gibt `True` zurück, wenn die angegebene Maschine derzeit eingeschaltet ist. Bei unbekannten Maschinen-IDs wird `False` zurückgegeben. Du kannst die Methode daher aufrufen, bevor du über einen Schaltbefehl entscheidest."""
        ...
    def can_power_off(self, machine_id: _str) -> _bool:
        """Gibt `True` zurück, wenn die angegebene Maschine existiert und einen sichtbaren Schalter hat. Terraforming-Maschinen und viele Produktionsmaschinen lassen sich gewöhnlich schalten; Batterien, passive Tanks, mobile Einheiten und Schiffsausrüstung gewöhnlich nicht."""
        ...
    def set_powered(self, machine_id: _str, on: _bool) -> ActionResult[Literal["ok", "not_found", "not_toggleable", "under_construction", "not_connected", "not_enough_power"]]:
        """Sendet denselben Schaltbefehl wie der Schalter auf der Maschinenkarte. `power.set_powered(\"o2gen_1\", False)` schaltet eine Maschine aus; `True` schaltet sie wieder ein. Das Ausschalten pausiert die zugehörigen Skripte und erhält ihre Sollwerte. Beim Wiedereinschalten werden nur Skripte fortgesetzt, die wegen der Stromabschaltung pausiert wurden. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
```

## `PowerGrid`

```python
class PowerGrid:
    """power_control.grids() / power_control.grid(target_id)"""
    anchor_id: _str
    outpost_ids: _list[_str]
    machine_ids: _list[_str]
    members: _list[PowerGridMember]
    generated: _float
    consumed: _float
    net: _float
    stored: _float
    capacity: _float
    reserve_stored: _float
    reserve_capacity: _float
    has_generator: _bool
```

## `PowerGridMember`

```python
class PowerGridMember:
    """PowerGrid.members"""
    id: _str
    name: _str
    type_id: _str
    outpost_id: _str
    powered: _bool
    roles: _list[_str]
    generated: _float
    consumed: _float
    stored: _float
    capacity: _float
    reserve_stored: _float
    reserve_capacity: _float
```

## `PowerSummary`

```python
class PowerSummary:
    """power_control.total()"""
    grid_count: _int
    generated: _float
    consumed: _float
    net: _float
    stored: _float
    capacity: _float
    reserve_stored: _float
    reserve_capacity: _float
```
