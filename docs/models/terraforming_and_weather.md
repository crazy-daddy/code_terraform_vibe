# Models: Atmosphere, Plant, Seed & Weather Models

Granular data models and return types extracted from `__builtins__.pyi`.

## `Atmosphere`

```python
class Atmosphere(Component):
    """Atmosphäre: Die Atmosphäre des Planeten. Lies die Gaszusammensetzung, den Druck, die Temperatur und den Fortschrittswert für Wärme-Einheiten (`get_heat()`) aus. Für Sauerstoff- und Druckmessungen müssen die entsprechenden Sensoren repariert sein."""
    name: _str
    def get_co2(self) -> _float:
        """Aktueller CO2-Gehalt in Promille (ppt). Bei der Sauerstofferzeugung wird CO2 im Verhältnis **1:1** verbraucht. Daher sinkt dieser Wert, wenn der Sauerstoffgehalt steigt. CO2 gelangt durch das Verbrennen von Öl (Ölgenerator), das Verbrennen von Gegenständen (Abfallentsorger) und in größerem Maßstab durch die Atmung der Tierwelt (etablierte Kolonien atmen CO2 aus) zurück in die Atmosphäre. Wenn die Vorräte knapp werden, füllt ein geringer vulkanischer Gasausstoß CO2 wieder auf."""
        ...
    def get_o2(self) -> _float:
        """Aktueller Sauerstoffgehalt in Promille (ppt). Dafür muss der Sauerstoffsensor repariert sein."""
        ...
    def get_n2(self) -> _float:
        """Aktueller Stickstoffgehalt in Promille (ppt)."""
        ...
    def get_pressure(self) -> _float:
        """Aktueller Atmosphärendruck in kPa. Dafür muss der Drucksensor repariert sein."""
        ...
    def get_temperature(self) -> _float:
        """Aktuelle Oberflächentemperatur in °C. Dieser **Anzeigewert** wird durch eine nichtlineare Umrechnung der Wärme-Einheiten ermittelt. Verwende für den Terraforming-Fortschritt oder Wärmeschwellen `get_heat()`, nicht diesen Wert."""
        ...
    def get_heat(self) -> _float:
        """Aktuell angesammelte **Wärme-Einheiten**: der Fortschrittswert für die Temperatursäule. Genau diesen Wert vergleichen die Schwellen für Temperaturforschung und Phasen (die aktuellen Ziele stehen auf der Forschungsseite). Prüfe Wärmeschwellen anhand dieses Werts, so wie du für die anderen Säulen `get_o2()` bzw. `get_pressure()` verwendest. Anders als bei `get_temperature()` (Oberflächentemperatur in °C, ein nichtlinearer Anzeigewert) bedeutet ein Unterschied bei den Wärme-Einheiten tatsächlich Terraforming-Fortschritt. Beginnt bei **0**."""
        ...
```

## `Cell`

```python
class Cell:
    """self.cell(sector) / self.cells()"""
    id: _str
    plant: Literal["sunpetal", "shadeleaf", "dewmoss", "lonethorn", "packfern", "twinvine", "spitebud", "sunspur", "glowvine", "crowncap", "pondmoss", "saltbloom", "brinethorn", "saltmate", "grandbloom"] | None
    growth: _float
    status: Literal["unknown", "empty", "item", "base", "growing", "stalled", "mature", "provider"]
    lit: _bool
    watered: _bool
    salted: _bool
    manual_light_remaining: _float
    manual_water_remaining: _float
    manual_salt_remaining: _float
    fertilized: _bool
    fertilizer_remaining: _float
    fertilizer_tier: _int
    accelerated: _bool
    accelerant_remaining: _float
    forage: _int
```

## `OxygenSensor`

```python
class OxygenSensor(Component):
    """Sauerstoffsensor: Eine Sauerstoffsonde für die Atmosphäre, die bei der Landung beschädigt wurde. Sie meldet eine Rohspannung, bis ein Skript die Kalibrierung berechnet und sie repariert. Danach misst sie den Sauerstoff direkt."""
    name: _str
    def get_value(self) -> _float:
        """Lies vor der Reparatur die Rohspannung der unkalibrierten Sonde als kleinen Dezimalwert aus. Das ist noch kein Messwert in ppt; vergleiche ihn mit einem bekannten Referenzwert, um den Kalibrierfaktor zu berechnen. Nach der Reparatur liest du den aktuellen Sauerstoffgehalt der Atmosphäre direkt in ppt aus."""
        ...
    def calibrate(self, value: _float) -> ActionResult[Literal["started", "already_repaired", "no_source", "already_testing"]]:
        """Starte die Blackbox-Kalibrierung mit dem verarbeiteten Wert: `result = self.calibrate(raw_value * factor)`. Anschließend prüft die Testsuite das gesamte Skript anhand mehrerer Messwerte. Besteht es alle Tests, wird der Sensor repariert; fehlgeschlagene Testfälle bleiben in der Konsole sichtbar. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
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

## `PlantRequirement`

```python
class PlantRequirement:
    """SeedRecipe.requirements"""
    kind: Literal["light", "shade", "water", "salt", "spacer", "cluster", "companion", "antagonist"]
    species: Literal["sunpetal", "shadeleaf", "dewmoss", "lonethorn", "packfern", "twinvine", "spitebud", "sunspur", "glowvine", "crowncap", "pondmoss", "saltbloom", "brinethorn", "saltmate", "grandbloom"] | None
```

## `PlantTerraformer`

```python
class PlantTerraformer(Component):
    """Pflanzen-Terraformer: Der einzige Umwandler, der geerntetes physisches Pflanzenfutter in dauerhafte Pflanzen-km² verwandelt. Befülle seinen Eingang über normale, zeitgesteuerte Gegenstandsübertragungen; sein Hochleistungszuführer schafft 16 Gegenstände pro Schritt bei Mk I und 80 bei Mk II. Mit jeder Phase kommt ein weiterer Stoff hinzu: Wasser, Salz, Dünger, dann Wachstumsbeschleuniger. Mk I endet an der Schwelle „Felder“; Mk II übernimmt die letzten beiden Phasen."""
    name: _str
    outpost: OutpostRef
    def set_enabled(self, enabled: _bool) -> ActionResult[Literal["ok"]]:
        """Aktiviere oder pausiere die Umwandlung. `True` startet einen Zyklus, sobald die internen Gegenstandslager und der Wasservorrat die für mindestens eine Einheit Pflanzenfutter benötigten Mengen im richtigen Verhältnis bereitstellen können. Bei voller Effizienz des Außenpostens dauert ein Zyklus **3 Stunden**. Wenn du das Skript dieser Maschine stoppst, wird der Sollwert auf `False` zurückgesetzt; eine bereits geladene Charge bleibt erhalten. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def is_enabled(self) -> _bool:
        """`True`, wenn das aktuelle Skript der Maschine die Umwandlung eingeschaltet hat."""
        ...
    def tier(self) -> _int:
        """Dauerhaft installierte Stufe des Pflanzen-Terraformers als Ganzzahl (**1–2**). Mk II erhöht den Durchsatz pro Charge und schaltet die späteren Rezepte für Pflanzen frei."""
        ...
    def status(self) -> Literal["complete", "disabled", "no_power", "needs_mk2", "no_forage", "no_water", "no_salt", "no_fertilizer", "no_accelerant", "running"]:
        """Exakter aktueller Zustand: `\"complete\"`, `\"disabled\"`, `\"no_power\"`, `\"needs_mk2\"`, `\"no_forage\"`, `\"no_water\"`, `\"no_salt\"`, `\"no_fertilizer\"`, `\"no_accelerant\"` oder `\"running\"`."""
        ...
    def is_running(self) -> _bool:
        """`True`, während ein Umwandlungszyklus läuft. Ohne Strom oder bei deaktivierter Maschine bleibt die angefangene Charge geladen, aber bis zur Wiederaufnahme wird `False` zurückgegeben."""
        ...
    def get_progress(self) -> _float:
        """Fortschritt des aktuellen Umwandlungszyklus von **0–1**. Ein vollständiger Zyklus erfordert bei 100 % Effizienz des Außenpostens **3 Stunden** Arbeit; Überbelegung verlangsamt den Fortschritt proportional. Gibt **0** zurück, wenn keine Charge geladen ist."""
        ...
    def batch_size(self) -> _int:
        """Anzahl ganzer Einheiten Pflanzenfutter im laufenden Zyklus oder in der Charge, die jetzt geladen werden kann. Eine volle Charge umfasst bei Mk I **1.200** und bei Mk II **6.600** Einheiten. Bei Materialmangel oder kurz vor einer Phasengrenze wird weniger geladen."""
        ...
    def km2_rate(self) -> _float:
        """Aktuelle Rate, mit der diese Maschine dauerhafte Pflanzenfläche erzeugt, in km²/h. Sie berücksichtigt die geladene Charge, deren nominellen Arbeitszyklus von **3 Stunden**, den für die Phase festgelegten Umrechnungskurs von anfangs **20 km² pro Einheit Pflanzenfutter** bis zuletzt **1 km² pro 3 Einheiten Pflanzenfutter** sowie die durch Überbelegung verringerte Effizienz dieses Außenpostens. Gibt **0** zurück, wenn die Maschine blockiert oder deaktiviert ist oder die Umwandlung abgeschlossen wurde."""
        ...
    def phase(self) -> _int:
        """Nummer der aktuellen globalen Pflanzenphase, **1–6**."""
        ...
    def recipe_tier(self) -> _int | None:
        """Abgeleitete Produktionsstufe des aktuellen Rezepts für die kumulative Pflanzenumwandlung. Gibt nach Abschluss der Kontinentalphase `None` zurück."""
        ...
    def next_threshold(self) -> _float:
        """Für die nächste Phase benötigte dauerhafte Pflanzenfläche in km². Nach Abschluss wird die Obergrenze von **5.000.000 km²** zurückgegeben."""
        ...
    def remaining(self) -> _float:
        """Bis zur nächsten Phase noch benötigte dauerhafte Pflanzenfläche in km². Gibt **0** zurück, wenn die Kontinentalphase abgeschlossen ist."""
        ...
    def required_inputs(self) -> _list[_str]:
        """Aktuell benötigte kumulative Material-IDs. Beginnt mit `forage`; im Verlauf der fünf Umwandlungen kommen `water`, `salt`, die Kategorie `fertilizer` und `growth_accelerant` hinzu."""
        ...
    def batch_requirements(self) -> _dict[_str, _int]:
        """Exakte Mengen für die größte nächste Charge, die diese Stufe und Phase zulassen. Das dict enthält bei Bedarf `forage`, `water`, `salt`, `fertilizer_potency` und `growth_accelerant`. Salz und Wachstumsbeschleuniger werden als ganze Gegenstände pro Charge gezählt und aufgerundet. Die Düngerwirkung ist eine Ganzzahl. Bei knappem Vorrat in der Maschine werden diese Mengen nicht verringert."""
        ...
    def fertilizer_potency(self, item_id: _str) -> _int:
        """Gibt die ganzzahlige Wirkung eines Dünger-Gegenstands zurück: **10** für Mk I, **30** für Mk II oder **50** für Mk III. Jede andere Gegenstands-ID löst `ValueError` aus."""
        ...
    input: InputSlot
    water_in: FluidPort
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

## `PlantsSensor`

```python
class PlantsSensor(Component):
    """Pflanzensensor: Meldet die dauerhaft bewachsene Fläche in km², die von der Flotte der Pflanzen-Terraformer erzeugt wurde. Verfügbar nach Abschluss der Biosphärenforschung. Wachstum auf Feldern allein verändert diesen Wert nicht."""
    name: _str
    def get_value(self) -> _float:
        """Gibt die dauerhafte Pflanzenfläche in km² als Zahl zurück. Nur Pflanzen-Terraformer erhöhen diesen Wert. Wiederholte Anbauzyklen, Vielfalt, Versorger, Dünger und Ertragsverstärker erhöhen den tatsächlichen Vorrat an Pflanzenfutter, den sie verarbeiten."""
        ...
```

## `PressureSensor`

```python
class PressureSensor(Component):
    """Drucksensor: Eine beschädigt gelandete Sonde für den Atmosphärendruck. Ihre Messwerte sind durcheinander, bis ein Skript das Reparatursignal stabilisiert. Danach misst sie den Druck direkt."""
    name: _str
    def get_value(self) -> _int:
        """Aktueller instabiler Reparaturmesswert als Ganzzahl. Ist der Wert ungerade, addiere **1**; ist er gerade, verwende ihn unverändert. Nach der Reparatur gibt diese Methode den tatsächlichen Atmosphärendruck in kPa zurück."""
        ...
    def stabilize(self, value: _float) -> ActionResult[Literal["started", "already_repaired", "no_source", "already_testing"]]:
        """Starte die Blackbox-Stabilisierung mit dem korrigierten geraden Messwert: `result = self.stabilize(corrected_value)`. Anschließend prüft die Testsuite das gesamte Skript anhand mehrerer Messwerte. Besteht es alle Tests, wird der Sensor repariert. Fehlgeschlagene Testfälle bleiben in der Konsole sichtbar. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
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

## `Recipe`

```python
class Recipe:
    """list_recipes() / find_recipe() bei Schmelzofen, Fabrikator, Futterhersteller, Raffinerie und Brennstofffertiger"""
    tier: _int
    id: _str
    name: _str
    inputs: _dict[_str, _int]
    output_item: _str
    output_count: _int
    duration_game_hours: _float
    power_draw: _float
    fluid_inputs: _dict[_str, _float]
    input_fluid: Literal["raw_sulfur_gas", "raw_cryofluid", "raw_chlorine", "raw_quicksilver"] | None
    fluid_outputs: _dict[_str, _float]
    output_fluid: Literal["sulfur_gas", "cryofluid", "chlorine", "quicksilver"] | None
    byproduct_item: _str | None
    byproduct_count: _int
```

## `Refiner`

```python
class Refiner(Component):
    """Raffinerie: Verarbeitet exotische Rohstoffe mithilfe von Teer zu Gas oder Flüssigkeit für Kreaturen. Nur ungewöhnliche und seltene exotische Stoffe müssen raffiniert werden; gewöhnliche können direkt verwendet werden. Rezepte werden durch Aufträge des Biolabors freigeschaltet."""
    name: _str
    outpost: OutpostRef
    def list_recipes(self) -> _list[Recipe]:
        """Listet die durch Aufträge des Biolabors freigeschalteten Raffinerierezepte auf, je ein `Recipe` pro exotischem Fluid. Gesperrte Rezepte erscheinen nicht. Jedes Rezept enthält mit `.tier` seine Stufe, nennt in `.input_fluid` den genauen Rohstoff, gibt in `.fluid_inputs` die pro Durchlauf an den Anschlüssen verbrauchte Menge in Tonnen an, führt in `.inputs` den Teer auf und bezeichnet mit `.output_fluid` / `.fluid_outputs` das raffinierte Produkt und seinen Ausgangsanschluss. Mit `for recipe in self.list_recipes(): print(recipe.tier, recipe.id, recipe.input_fluid, recipe.output_fluid)` kannst du herausfinden, was verfügbar ist."""
        ...
    def find_recipe(self, recipe_id: _str) -> Recipe | None:
        """Sucht ein freigeschaltetes Raffinerierezept anhand seiner ID, ohne `list_recipes()` zu durchlaufen. Gibt dessen `Recipe`-Objekt zurück oder `None`, wenn die ID unbekannt oder gesperrt ist oder zu einer anderen Maschine gehört."""
        ...
    def set_recipe(self, recipe_or_id: RecipeRef) -> ActionResult[Literal["ok", "unknown_recipe", "offline", "recipe_locked", "busy", "output_busy"]]:
        """Wähle anhand der ID oder durch Übergabe eines Rezepts aus `list_recipes()` aus, welchen exotischen Stoff du raffinieren möchtest, zum Beispiel mit `self.set_recipe(\"refine_chlorine\")`. Nach der Auswahl arbeitet die Raffinerie automatisch, sobald Rohstoff und Teer vorhanden sind und am Ausgangsanschluss Platz ist. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def clear_recipe(self) -> ActionResult[Literal["ok", "busy", "material_present"]]:
        """Hebt die Auswahl des Raffinerierezepts auf und lässt die Raffinerie im Leerlauf. Teer und Rohstoffe an den Eingängen bleiben als bereitgestellter Vorrat erhalten. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def purge_input(self) -> ActionResult[Literal["ok", "empty", "busy"]]:
        """Lässt den Rohstoff aus `gas_in` und `liquid_in` ab und gibt die Anschlüsse damit für ein anderes Fluid frei. Die Rohstoffanschlüsse nehmen das erste Fluid an, das sie erreicht, und danach nur noch dieses. Ist ein Anschluss mit der falschen Förderanlage verbunden, enthält er daher ein Fluid, das das Rezept nicht verwenden kann. Lass es ab und ändere die Verbindung: zuerst `self.purge_input()`, dann `self.gas_in.connect(\"Raw Sulfur Cap\")`. Das abgelassene Fluid wird vernichtet; der Teer im Eingangsbehälter bleibt unberührt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def get_recipe(self) -> Literal["", "refine_sulfur_gas", "refine_cryofluid", "refine_chlorine", "refine_quicksilver"]:
        """Gibt die ID des aktuellen Rezepts zurück oder `\"\"`, wenn keines eingestellt ist oder das eingestellte Rezept nicht mehr freigeschaltet ist. Prüfe damit den Zustand, bevor du erneut ein Rezept einstellst: `if self.get_recipe() == \"\": self.set_recipe(\"refine_sulfur_gas\")`."""
        ...
    def get_recipe_inputs(self) -> _dict[_str, _int]:
        """Ein dict, das jeder Eingabe-`item_id` die pro Herstellung verbrauchte Stückzahl zuordnet. Bei der Raffinerie sind das die **Teer**kosten, zum Beispiel `{\"tar\": 5}` für einen seltenen exotischen Stoff. Ist kein Rezept eingestellt, ist das dict leer. Lies es aus, um den Teervorrat aufzufüllen: `for item, qty in self.get_recipe_inputs().items(): self.input.take(item, qty * 5)`. (Die Menge des flüssigen oder gasförmigen Rohstoffs wird an den Eingangsanschlüssen gemessen und hier nicht aufgeführt.)"""
        ...
    def is_running(self) -> _bool:
        """`True`, wenn in diesem Tick ein Raffineriedurchlauf aktiv voranschreitet: Ein freigeschaltetes Rezept ist eingestellt, Rohstoff und Teer sind vorhanden und am Ausgangsanschluss ist Platz. `False`, wenn die Produktion stockt, die Raffinerie im Leerlauf ist oder keinen Strom hat."""
        ...
    def is_stalled(self) -> _bool:
        """`True`, wenn die Raffinerie Strom hat und ein Rezept eingestellt ist, der Durchlauf aber nicht voranschreiten kann: etwa weil Rohstoff fehlt (prüfe `self.gas_in.level()` / `self.liquid_in.level()`), der Teer aufgebraucht ist (fülle den Eingangsbehälter auf) oder der Ausgangsanschluss für das raffinierte Fluid voll ist (Rückstau; leere den Ausgangstank). `False`, wenn die Raffinerie keinen Strom hat, läuft oder kein Rezept eingestellt ist. Frage den Wert regelmäßig ab, um eine stockende Leitung zu erkennen."""
        ...
    def get_rate(self) -> _float:
        """In diesem Tick produzierter raffinierter exotischer Stoff in t/h. **0**, wenn die Produktion stockt oder die Raffinerie im Leerlauf ist. Damit kannst du den Durchsatz prüfen, während du Rohstoffzufuhr und Bedarf aufeinander abstimmst."""
        ...
    def get_progress(self) -> _float:
        """Fortschritt des aktuellen Raffineriedurchlaufs von **0–1**. Nach jedem abgeschlossenen Durchlauf wird er auf 0 zurückgesetzt: Eine Charge raffinierten Fluids gelangt in den Ausgangsanschluss. Sind weiter Rohstoff und Teer vorhanden, beginnt der nächste Durchlauf."""
        ...
    gas_in: FluidPort
    liquid_in: FluidPort
    gas_out: FluidPort
    liquid_out: FluidPort
    input: InputSlot
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

## `SeedMaker`

```python
class SeedMaker(Component):
    """Saatgutmaschine: Ein Verarbeitungsgebäude für Außenposten, das drei Lebensformproben zu einem keimfähigen Samen kombiniert. Die meisten Mischungen scheitern; die funktionierenden Rezepte gibt es nur auf diesem Planeten, du findest sie durch Ausprobieren, und ein entdecktes Rezept lässt sich für weitere Samen erneut ausführen."""
    name: _str
    outpost: OutpostRef
    def combine(self, blend: _list[_str]) -> SeedResult[Literal["seed_found", "sludge", "locked", "busy", "missing_life_forms", "output_full"]]:
        """Starte einen Versuch mit genau den drei verschiedenen Lebensform-IDs, die in der Reaktionskammer dieser Maschine geladen sind. Jeder angenommene Versuch verbraucht von jeder Lebensform **1 t**. Das Ergebnisfach für einen einzelnen Samen muss leer sein, bevor ein Versuch beginnen kann. Fester Ergebnisvertrag: `SeedResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.seed_id` und `.species`."""
        ...
    def life_forms(self) -> _list[_str]:
        """Liste der **30** zulässigen Gegenstands-IDs für Lebensformen. Lade für jede Kombination `blend` aus `combinations(self.life_forms(), 3)` ihre drei Gegenstände mit `self.input.take(item_id, 1)` und rufe dann `self.combine(blend)` auf. Das Auflisten bewegt keine Materialien. Transportiere jeden dabei entstandenen physischen Samen aus `self.output` ab, bevor du fortfährst."""
        ...
    def is_running(self) -> _bool:
        """`True`, während ein Kombinationsversuch läuft."""
        ...
    def get_progress(self) -> _float:
        """Fortschritt des aktuellen Kombinationsversuchs von **0–1**; gibt im Leerlauf **0** zurück."""
        ...
    def get_output_count(self) -> _int:
        """Anzahl der physischen Samen im Ergebnisfach für einen einzelnen Samen: **0** oder **1**."""
        ...
    def recipes(self) -> _list[SeedRecipe]:
        """Liste von `SeedRecipe` für alle bisher entdeckten Kombinationen – dasselbe dauerhaft gespeicherte Verzeichnis, das der Reiter Flora / Saatgutrezepte zeigt. Jeder Eintrag enthält `.tier`, die ID des physischen Samens in `.seed_id`, die reine Arten-ID in `.species`, außerdem `.blend`, `.requirements`, `.requirement` und `.growth_time`. `.requirements` ist die programmierbare Form: Jede `PlantRequirement` enthält `.kind` und optional `.species`, sodass Einträge für Begleit- und Gegenspielerpflanzen die genaue verwandte Pflanze angeben. `.requirement` bleibt eine kurze Textzusammenfassung. Die Liste ist bis zu deinem ersten Treffer leer. Wiederhole eine bekannte Kombination aus `.blend` mit `self.combine(...)`, um ihren Samen erneut herzustellen, ohne alle Kombinationen nochmals durchzugehen."""
        ...
    input: InputSlot
    output: OutputSlot
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

## `SeedRecipe`

```python
class SeedRecipe:
    """self.recipes() (Saatgutmaschine)"""
    tier: _int
    species: Literal["sunpetal", "shadeleaf", "dewmoss", "lonethorn", "packfern", "twinvine", "spitebud", "sunspur", "glowvine", "crowncap", "pondmoss", "saltbloom", "brinethorn", "saltmate", "grandbloom"]
    seed_id: Literal["seed_sunpetal", "seed_shadeleaf", "seed_dewmoss", "seed_lonethorn", "seed_packfern", "seed_twinvine", "seed_spitebud", "seed_sunspur", "seed_glowvine", "seed_crowncap", "seed_pondmoss", "seed_saltbloom", "seed_brinethorn", "seed_saltmate", "seed_grandbloom"]
    blend: _list[_str]
    requirements: _list[PlantRequirement]
    requirement: Literal["light", "shade", "water", "spacer", "cluster", "companion", "antagonist", "light+spacer", "light+water", "shade+cluster", "water+cluster", "salt", "salt+spacer", "salt+companion", "light+water+spacer"]
    growth_time: _float
    base_yield: _int
```

## `Smelter`

```python
class Smelter(Component):
    """Schmelzofen: Verarbeitet Roherz nach einem von dir gewählten Rezept zu Metall, jeweils eine Einheit auf einmal. Ein Skript legt das Rezept fest, führt Erz aus einem Lagerbehälter zu und transportiert das fertige Metall in einen anderen."""
    name: _str
    outpost: OutpostRef
    def list_recipes(self) -> _list[Recipe]:
        """Alle Rezepte, für die dieser Schmelzofen einen Bauplan erhalten hat. Gibt Rezeptobjekte mit `.tier`, `.id`, `.name`, `.inputs`, `.output_item`, `.output_count`, `.duration_game_hours` und `.power_draw` zurück. Gesperrte Rezepte ohne Bauplan erscheinen nicht; die Liste enthält nur Rezepte, die du derzeit tatsächlich ausführen kannst. Am ersten Tag ist nur `\"smelt_iron_ingot\"` verfügbar. Weitere Rezepte kommen hinzu, sobald ihre Baupläne freigeschaltet sind."""
        ...
    def find_recipe(self, recipe_id: _str) -> Recipe | None:
        """Finde ein freigeschaltetes Rezept anhand seiner ID, ohne `list_recipes()` durchlaufen zu müssen. Gibt das zugehörige `Recipe`-Objekt zurück oder `None`, wenn die ID unbekannt oder gesperrt ist oder zu einer anderen Maschine gehört."""
        ...
    def set_recipe(self, recipe_or_id: RecipeRef) -> ActionResult[Literal["ok", "unknown_recipe", "offline", "recipe_locked", "busy", "material_mismatch"]]:
        """Wähle das Rezept aus, das der Schmelzofen ausführen soll. Rufe `self.set_recipe(\"smelt_iron_ingot\")` auf oder übergib ein Rezept aus `list_recipes()`. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def clear_recipe(self) -> ActionResult[Literal["ok", "busy", "material_present"]]:
        """Entferne das aktuelle Rezept und lasse den Schmelzofen im Leerlauf. Leere, auf ein Material festgelegte Puffer werden dabei wieder auf „kein Material“ zurückgesetzt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def get_recipe(self) -> Literal["", "smelt_iron_ingot", "smelt_glass", "smelt_titanium_ingot", "smelt_cobalt_ingot", "smelt_rare_earth_core", "smelt_neutronium_bar", "smelt_lead_ingot"]:
        """Die ID des aktuellen Rezepts als Zeichenfolge oder eine leere Zeichenfolge, wenn kein Rezept festgelegt ist. Nutze dies nach `set_recipe()` zur Bestätigung oder als Bedingung für weitere Logik (`if self.get_recipe() == \"\": ...`)."""
        ...
    def get_recipe_inputs(self) -> _dict[_str, _int]:
        """Benötigte Eingabematerialien für das aktuelle Rezept als dict `{item_id: count_per_craft}`. Gibt ein leeres dict zurück, wenn kein Rezept festgelegt ist."""
        ...
    def is_running(self) -> _bool:
        """Gibt an, ob der Schmelzofen aktiv arbeitet. Kann `False` sein, während die Verarbeitung einer noch nicht fertigen Einheit pausiert, etwa weil der Ausgabespeicher voll ist. Der Fortschritt bleibt während der Pause erhalten. Prüfe vor einem Rezeptwechsel mit `get_progress()`, ob noch Arbeit unerledigt ist."""
        ...
    def get_progress(self) -> _float:
        """Fortschritt bis zur nächsten fertigen Einheit (**0-1**). Wird auf **0** zurückgesetzt, wenn eine Einheit fertig wird und die nächste beginnt. Nützlich für Fortschrittsbalken und Skripte, die fertige Einheiten erkennen, indem sie auf einen Abfall des Werts achten."""
        ...
    def get_input_count(self) -> _int:
        """Anzahl der Einheiten im Eingabepuffer, die auf das Schmelzen warten. Prüfe den Wert vor `self.input.take(...)`, um den Puffer nicht zu überfüllen oder zu entscheiden, ob du weiteres Material holen solltest."""
        ...
    def get_output_count(self) -> _int:
        """Anzahl der Einheiten im Ausgabepuffer, die auf den Abtransport warten. Prüfe den Wert vor `self.output.send(...)`: Ist er hoch, leere zuerst das nachgelagerte Lager; ist er niedrig, gib der Verarbeitung Zeit."""
        ...
    input: InputSlot
    output: OutputSlot
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

## `Storm`

```python
class Storm:
    """WeatherReport.active()"""
    id: _str
    x: _float
    y: _float
    def kind(self) -> Literal["dust", "thunder"]:
        """`\"dust\"` oder `\"thunder\"`. Staubstürme senden nach ihrem Ende eine Nachricht über Rohuran. Gewitter laden geeignete Blitzableiter auf und können eine Nachricht über Sturmglas erzeugen."""
        ...
    def radius_m(self) -> _float:
        """Radius der Sturmzelle in m. Eine Heli-Drohne auf gerader Route hält an, sobald sie sich innerhalb der Sturmzelle befindet; sie fliegt nicht automatisch darum herum. Elektrodrohnen fliegen hindurch."""
        ...
    def speed(self) -> _float:
        """Bewegungsgeschwindigkeit in m/h."""
        ...
    def heading(self) -> _list[_float]:
        """Normierter Bewegungsrichtungsvektor als `[dx, dy]`."""
        ...
    def intensity(self) -> _float:
        """Zum Zeitpunkt des Berichts beobachtete Stärke von **0-1**."""
        ...
    def expires_in(self) -> _float:
        """In Echtzeit aktualisierte Anzahl der Stunden, bis sich diese beobachtete Sturmzelle auflöst."""
        ...
    def eta_to(self, x: _float, y: _float) -> _float | None:
        """Stunden, bis der Rand der Sturmzelle den Punkt erreicht. **0**, wenn sich der Punkt bereits innerhalb der Zelle befindet; `None`, wenn die Zugbahn ihn vor der Auflösung der Zelle nicht erreicht."""
        ...
```

## `Thermometer`

```python
class Thermometer(Component):
    """Thermometer: Ständig einsatzbereiter Temperaturfühler für die Oberfläche; keine Kalibrierung nötig. Misst direkt die aktuelle Oberflächentemperatur des Planeten in **°C**."""
    name: _str
    def get_value(self) -> _float:
        """Aktuelle Oberflächentemperatur in **°C** als Zahl. Kann aus jedem Skript sicher aufgerufen werden; eine Reparatur ist nicht nötig. Das ist der angezeigte Celsiuswert. Für den Fortschrittswert in Wärmeeinheiten, mit dem Forschungsschwellen verglichen werden, lies `get_component(\"atmosphere\").get_heat()` aus."""
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

## `WeatherEventForecast`

```python
class WeatherEventForecast:
    """WeatherReport.forecast()"""
    id: _str
    def kind(self) -> Literal["dust", "thunder"]:
        """Allgemeine Ereignisart: `\"dust\"` oder `\"thunder\"`."""
        ...
    def arrival_window(self) -> _list[_float]:
        """Zeitfenster `[earliest, latest]` in Stunden nach dem Beobachtungszeitpunkt dieses Berichts, in dem die Wetterzelle voraussichtlich in den Erfassungsbereich gelangt."""
        ...
    def corridor(self) -> Zone:
        """Grob vorhergesagter Zugkorridor als `Zone`. Er beschreibt den Sturm, niemals den verborgenen Verlauf seiner Nachwirkungen."""
        ...
    def intensity_range(self) -> _list[_float]:
        """Beobachteter Vorhersagebereich `[low, high]`; beide Werte liegen im Bereich **0-1**."""
        ...
```

## `WeatherReport`

```python
class WeatherReport:
    """weather_station.observe() / weather_station.last_report()"""
    id: _str
    source_id: _str
    observed_at_gh: _float
    def age_gh(self) -> _float:
        """Aktuelles Alter dieses unveränderlichen Berichts in Stunden der Spielweltzeit."""
        ...
    def coverage(self) -> Zone:
        """Lokaler Erfassungsbereich der Station als `Zone`, festgehalten zum Beobachtungszeitpunkt."""
        ...
    def active(self) -> _list[Storm]:
        """Liste von Momentaufnahmen aktiver `Storm`-Objekte im lokalen Erfassungsbereich zum Beobachtungszeitpunkt."""
        ...
    def forecast(self) -> _list[WeatherEventForecast]:
        """Lokale `WeatherEventForecast`-Einträge für Ereignisse, die den Erfassungsbereich voraussichtlich innerhalb von **8 Stunden der Spielweltzeit** erreichen, nach Erforschung der Wettervorhersage innerhalb von **24 Stunden**."""
        ...
```

## `WeatherSignalBoard`

```python
class WeatherSignalBoard:
    """weather_station.signal_board"""
    def reveal(self, transmission: SignalTransmission | TransmissionRecord) -> ActionResult[Literal["ok", "no_power", "duplicate", "invalid_type"]]:
        """Veröffentliche eine Übertragung in dem darin angegebenen nummerierten Slot. Ein anderes Ereignis ersetzt die aktuelle Tafel dieser Station. Ein bereits veröffentlichter Slot desselben Ereignisses bleibt unverändert. Die Tafel prüft Struktur und Wertebereiche, aber weder die Bedeutung noch die Gültigkeit der Prüfsumme. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def reject(self, transmission: SignalTransmission | TransmissionRecord) -> ActionResult[Literal["ok", "no_power", "invalid_type"]]:
        """Erhöhe die Anzahl der Zurückweisungen für das angegebene Ereignis um eins, ohne einen Slot zu öffnen. Ein anderes Ereignis ersetzt die aktuelle Tafel dieser Station. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def resolve(self, event_id: _str, info: _dict[_str, object]) -> ActionResult[Literal["ok", "no_power", "invalid_type"]]:
        """Veröffentliche bis zu **6** beschriftete Zeilen zu einem Ereignis. Ein anderes Ereignis ersetzt die aktuelle Tafel dieser Station. Die Tafel zeigt die übergebenen Werte an, ohne sie zu validieren. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def clear(self) -> ActionResult[Literal["ok", "no_power"]]:
        """Leere die Tafel und setze ihre Anzahl an Zurückweisungen sowie jede veröffentlichte Schlussfolgerung zurück. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def status(self) -> WeatherSignalBoardStatus:
        """Metadaten zur aktuellen Veröffentlichung auf der Tafel dieser Station."""
        ...
```

## `WeatherSignalBoardStatus`

```python
class WeatherSignalBoardStatus:
    """weather_station.signal_board.status()"""
    has_input: _bool
    published_at_gh: _float | None
    freshness: Literal["no_input", "fresh", "stale"]
    event_id: _str
```

## `WeatherStation`

```python
class WeatherStation(Component):
    """Wetterstation: Programmierbare lokale Sturmstation mit Liveempfang. Sie erstellt unveränderliche lokale Messberichte, empfängt Ereignisübertragungen über Rundfunk- und Biomkanäle und kann Daten auf der Signaltafel veröffentlichen."""
    name: _str
    outpost: OutpostRef
    def observe(self) -> WeatherReport:
        """Erstellt einen unveränderlichen lokalen Messbericht. Die Station aktualisiert ihn höchstens einmal pro Stunde der Weltzeit; häufigere Aufrufe geben dieselbe Berichts-ID zurück. Der Bericht enthält die lokale Abdeckung, Momentaufnahmen aktiver Stürme und eine lokale Vorhersage für die nächsten 8 Stunden der Weltzeit – nach Erforschung der Wettervorhersage für 24 Stunden. Er verrät niemals die Koordinaten eines Fundorts, der nach einem Sturm entstanden ist."""
        ...
    def last_report(self) -> WeatherReport | None:
        """Lies den zuletzt erstellten Messbericht, ohne eine neue Beobachtung vorzunehmen. Das hilft bei der Wiederherstellung nach dem Start und beim Umgang mit veralteten Daten; `None` bedeutet, dass diese Station `observe()` noch nie abgeschlossen hat."""
        ...
    signal_board: WeatherSignalBoard
    signal_receiver: SignalReceiver
    def strikes(self) -> _list[WeatherStrike]:
        """Gibt die begrenzte Aufzeichnung der von dieser Station beobachteten Blitzeinschläge zurück. Jeder `WeatherStrike` enthält seine Ereignis-ID, den Beobachtungszeitpunkt, die Energie und die Angabe, ob ein Blitzableiter sie gespeichert hat. Genaue Einschlagspositionen und Angaben dazu, ob Sturmglas entstehen kann, sind nicht enthalten. Zurückgegeben werden nur Einschläge, die diese Station selbst beobachtet hat."""
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

## `WeatherStrike`

```python
class WeatherStrike:
    """weather_station.strikes()"""
    id: _str
    event_id: _str
    observed_at_gh: _float
    energy_wh: _float
    caught: _bool
```

## `WildlifeSensor`

```python
class WildlifeSensor(Component):
    """Tierweltsensor: Meldet die Gesamtzahl einzelner Tiere in allen etablierten Habitatkolonien. Verfügbar nach Erforschung der Biosphäre; gibt `0` zurück, bis die erste Tierkolonie etabliert ist."""
    name: _str
    def get_value(self) -> _int:
        """Gibt die aktuelle Anzahl der Tiere als Zahl zurück, summiert über alle etablierten Habitatkolonien."""
        ...
```
