# Models: Biology Pipeline Models (Specimens, Fragments, Orders, Recipes)

Granular data models and return types extracted from `__builtins__.pyi`.

## `BioCaster`

```python
class BioCaster(Component):
    """Biogussanlage: Schmiedet ein vulkanisches Fragment: Lade die Materialien des Rezepts, halte den Schmelztiegel im vorgegebenen Temperaturbereich und führe dann den Guss aus. Für Dampf und Wasser gibt es getrennte interne Prozessspeicher mit je 20 t Kapazität. Verbinde jeden Eingangsanschluss mit einer passenden Quelle. Lokale Quellen übertragen direkt; bei entfernten Quellen brauchst du außerdem eine fertiggestellte, konfliktfreie Rohrleitung zwischen beiden Standorten. Ein Skript steuert Heizung und Kühlung. Ein Guss außerhalb des Temperaturbereichs oder mit falschen Materialien verbraucht die gesamte Füllung."""
    name: _str
    outpost: OutpostRef
    def list_recipes(self) -> _list[BioCasterRecipe]:
        """Liste alle 16 Schmiederezepte auf, ohne das ausgewählte Rezept zu ändern: `self.list_recipes()`. Jedes `BioCasterRecipe` enthält seine Fragment-ID, Produktionsstufe, genaue Materialliste und den Zieltemperaturbereich. Die Abfrage funktioniert über `get_component(...)`. So kann eine andere Maschine den Nachschub planen, ohne alle Fragmente zu besitzen."""
        ...
    def find_recipe(self, fragment_id: _str) -> BioCasterRecipe | None:
        """Schlage ein Schmiederezept anhand der ID eines vulkanischen Fragments nach, ohne es auszuwählen: `self.find_recipe(fragment_id)`. Gibt bei einer unbekannten ID `None` zurück."""
        ...
    def catalog(self) -> _list[_str]:
        """Die IDs der 16 schmiedbaren vulkanischen Fragmente: `self.catalog()`. Übergib eine davon an `set_recipe(...)`. Wenn du auch die Material- und Temperaturanforderungen aller Rezepte brauchst, verwende `list_recipes()`. Die Hardware ist fest vorgegeben; lies den Katalog einmal aus."""
        ...
    def recipe_tier(self, fragment_id: _str) -> _int | None:
        """Die aus `catalog()` abgeleitete Produktionsstufe eines Rezepts. Gibt bei einer unbekannten Fragment-ID `None` zurück."""
        ...
    def set_recipe(self, fragment_id: _str) -> ActionResult[Literal["ok", "invalid_recipe", "busy", "output_full"]]:
        """Wähle mit `self.set_recipe(\"sd_tail_barb\")` das vulkanische Fragment, das geschmiedet werden soll. Danach beschreiben `required_range()` und `required_materials()` dieses Rezept. Die Auswahl bleibt wie bei einem Rezept des Schmelzofens erhalten. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def recipe(self) -> Literal["ma_chitinous_seta", "st_beak", "ms_abdomen_sclerite", "mh_chitin_node", "gm_abdominal_sheath", "vm_tail_barb", "vc_walking_leg", "oc_ink_sac", "bw_hindlimb", "vd_photophore", "hs_abdomen_segment", "hc_beak", "fs_oral_tegmen", "ce_great_appendage", "gw_jaw_fang", "sd_tail_barb"] | None:
        """Das ausgewählte Rezept: `self.recipe()` gibt die ID des vulkanischen Fragments zurück, das geschmiedet werden soll (zugleich das rohe Fragment für `load`), oder `None`, wenn kein Rezept ausgewählt ist."""
        ...
    def required_range(self) -> _list[_float] | None:
        """Der Zieltemperaturbereich `[low, high]` des ausgewählten Rezepts in °C: `self.required_range()`. Beim Aufruf von `cast()` muss `temperature()` innerhalb dieses Bereichs liegen, einschließlich der Grenzwerte. Gibt `None` zurück, wenn kein Rezept ausgewählt ist."""
        ...
    def required_materials(self) -> _dict[_str, _int]:
        """Listet die für das ausgewählte Rezept benötigten verarbeiteten Materialien als `{item_id: count}` auf. Lade vor dem Guss genau diese Mengen. Durchlaufe die Einträge mit `.items()`. Gibt ein leeres dict zurück, wenn kein Rezept ausgewählt ist."""
        ...
    def required_fragment(self) -> Literal["ma_chitinous_seta", "st_beak", "ms_abdomen_sclerite", "mh_chitin_node", "gm_abdominal_sheath", "vm_tail_barb", "vc_walking_leg", "oc_ink_sac", "bw_hindlimb", "vd_photophore", "hs_abdomen_segment", "hc_beak", "fs_oral_tegmen", "ce_great_appendage", "gw_jaw_fang", "sd_tail_barb"] | None:
        """Die ID des rohen Fragments, das das Rezept verbraucht: `self.required_fragment()` (identisch mit `recipe()`). Gibt `None` zurück, wenn kein Rezept ausgewählt ist."""
        ...
    def temperature(self) -> _float:
        """Aktuelle Temperatur des Schmelztiegels in °C: `self.temperature()`. Sie reicht von **100** (kalter Ausgangswert) bis **1000** (Maximum). Bring sie vor dem Guss mit den Reglern in den von `required_range()` vorgegebenen Bereich."""
        ...
    def temp_rate(self) -> _float:
        """Aktuelle Nettoänderung der Temperatur in °C/h: `self.temp_rate()`. Positive Werte bedeuten Erwärmung, negative Abkühlung. Bei voller Heizleistung beträgt sie +2400 °C/h, bei voller Kühlung -2400 °C/h. Stehen beide Regler auf 0, kühlt ein nicht gesperrter Schmelztiegel oberhalb des Ausgangswerts von selbst mit -20 °C/h ab. Beim Ausgangswert von 100 °C und während eines Gusses wird 0 zurückgegeben."""
        ...
    def heat(self) -> _float:
        """Aktuelle Einstellung des Heizreglers **0-100 %**: `self.heat()`. Bei 100 % steigt die Temperatur mit **+2400 °C/h** (dabei wird Dampf verbraucht). Verwende nahe dem Zielbereich eine niedrigere Einstellung."""
        ...
    def cool(self) -> _float:
        """Aktuelle Einstellung des Kühlreglers **0-100 %**: `self.cool()`. Bei 100 % sinkt die Temperatur mit **-2400 °C/h** (dabei wird Wasser verbraucht). Verwende nahe dem Zielbereich eine niedrigere Einstellung."""
        ...
    def fragment(self) -> Literal["ma_chitinous_seta", "st_beak", "ms_abdomen_sclerite", "mh_chitin_node", "gm_abdominal_sheath", "vm_tail_barb", "vc_walking_leg", "oc_ink_sac", "bw_hindlimb", "vd_photophore", "hs_abdomen_segment", "hc_beak", "fs_oral_tegmen", "ce_great_appendage", "gw_jaw_fang", "sd_tail_barb"] | None:
        """Die ID des rohen Fragments in der Kammer: `self.fragment()`. Ist die Kammer leer, wird `None` zurückgegeben."""
        ...
    def materials(self) -> _dict[_str, _int]:
        """Die derzeit im Schmelztiegel geladenen Materialien: `self.materials()` gibt `{item_id: count}` zurück. Vergleiche die Werte vor `cast()` mit `required_materials()`. Durchlaufe die Einträge mit `.items()`."""
        ...
    def set_heat(self, pct: _float) -> ActionResult[Literal["ok", "empty", "busy", "output_full"]]:
        """Stelle den Heizregler ein (Dampf erhöht die Temperatur): `self.set_heat(100)` bewirkt +2400 °C/h. Verwende für die letzte Annäherung eine niedrigere Prozentzahl. Bereich: **0-100**; Werte außerhalb werden begrenzt. Die Regelung erfolgt ohne Rückkopplung: Der Schmelztiegel heizt weiter und verbraucht Dampf, bis du den Regler zurückstellst. Stehen beide Regler auf 0, kühlt er von selbst mit 20 °C/h ab. Gieße daher, sobald die Temperatur im Zielbereich liegt. Wenn die Kammer leer wird oder das Skript stoppt, wird der Regler wieder auf 0 gestellt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def set_cool(self, pct: _float) -> ActionResult[Literal["ok", "empty", "busy", "output_full"]]:
        """Stelle den Kühlregler ein (Wasser senkt die Temperatur): `self.set_cool(100)` bewirkt -2400 °C/h. Verwende für die letzte Annäherung eine niedrigere Prozentzahl. Bereich: **0-100**; Werte außerhalb werden begrenzt. Die Regelung erfolgt ohne Rückkopplung: Der Schmelztiegel kühlt weiter und verbraucht Wasser, bis du den Regler zurückstellst. Beide Regler können gleichzeitig laufen, doch dabei werden beide Flüssigkeiten verbraucht, ohne die Temperatur wesentlich zu ändern. Auch wenn beide Regler auf 0 stehen, kühlt der Schmelztiegel von selbst mit 20 °C/h ab. Wenn die Kammer leer wird oder das Skript stoppt, wird der Regler wieder auf 0 gestellt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def load(self, fragment_id: _str, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> ActionResult[Literal["ok", "chamber_occupied", "not_in_input", "invalid_fragment", "invalid_properties", "invalid_property_match", "busy", "output_full"]]:
        """Hole eine rohe vulkanische Probe mit der ID `fragment_id` aus `self.input` in die Kammer, meist mit `self.load(self.recipe())`. Mit den optionalen Parametern `properties` und `property_match` kannst du nach der üblichen Konvention eine bestimmte Identität auswählen: beliebige Übereinstimmung, Teilmenge oder exakte Übereinstimmung. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def eject(self) -> ActionResult[Literal["ok", "empty", "busy", "output_full"]]:
        """Lege die Probe aus der Kammer und alle geladenen Materialien in `self.output` bereit, ohne ihre Eigenschaften zu verändern. Wenn der Ausgang nur einen Materialtyp aufnehmen kann, ist möglicherweise für jeden Gegenstandstyp ein eigener Sende- und Auswurfzyklus nötig. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def cast(self) -> ActionResult[Literal["ok", "out_of_range", "wrong_materials", "wrong_fragment", "empty", "no_recipe", "busy", "output_full"]]:
        """Schmiede das geladene Fragment mit `self.cast()`. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    input: InputSlot
    output: OutputSlot
    steam_in: FluidPort
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

## `BioCasterRecipe`

```python
class BioCasterRecipe:
    """bio_caster.list_recipes() / bio_caster.find_recipe(fragment_id)"""
    fragment_id: Literal["gw_jaw_fang", "vc_walking_leg", "oc_ink_sac", "bw_hindlimb", "vd_photophore", "mh_chitin_node", "hs_abdomen_segment", "ms_abdomen_sclerite", "hc_beak", "ma_chitinous_seta", "gm_abdominal_sheath", "fs_oral_tegmen", "sd_tail_barb", "ce_great_appendage", "st_beak", "vm_tail_barb"]
    tier: _int
    materials: _dict[_str, _int]
    temperature_range: _list[_float]
```

## `BioCollector`

```python
class BioCollector(Component):
    """Biosammler: Automatisiert den Sammelschritt des Biologiekreislaufs und holt selbstständig eine Probe aus dem Gelände in seinen Frachtslot. Er tut nichts, bis ein Skript ihm sagt, wo er sammeln soll."""
    name: _str
    outpost: OutpostRef
    def scan(self) -> _list[FragmentLocation]:
        """Listet die Fundorte von Fragmenten im Biom dieses Außenpostens auf, beginnend mit dem nächstgelegenen. Jeder Eintrag vom Typ `FragmentLocation` enthält `coords`, die Entfernung und die Information, ob der Fundort katalogisiert wurde. Bei katalogisierten Fundorten werden auch Fragment-ID, Name und Seltenheit angezeigt; bei unbekannten Fundorten stehen diese Angaben auf `None`. Um das Fragment an einem unbekannten Fundort zu identifizieren, sammle es mit `bio_collector.collect(location.coords)` und analysiere es in einem Biolabor. Rezepte und die Identität von Kreaturen werden hier nicht angezeigt. Analysierte Fragmente erscheinen auch in `journal.cataloged_fragments(...)`."""
        ...
    def collect(self, coords: _list[_float]) -> ActionResult[Literal["ok", "busy", "cargo_occupied", "invalid_coords", "no_fragment"]]:
        """Hole das Fragment an `coords` aus `scan()` und lege es in den Frachtslot des Sammlers. Die Fahrt dauert je nach Entfernung in jedem Biom **~0,1-0,3 h**; das Skript pausiert, bis das Sammeln abgeschlossen ist. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def discard(self) -> ActionResult[Literal["ok", "empty", "busy"]]:
        """Entsorge die Probe, die sich gerade im Frachtslot des Sammlers befindet. Verwende dies, wenn der Sammler eine Probe aufgenommen hat, die du nicht an ein Biolabor schicken möchtest. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    cargo: Specimen | None
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

## `BioConditioner`

```python
class BioConditioner(Component):
    """Biokonditionierer: Prüft ein Tiefsee-Fragment nach einem festen Regelwerk und fragt dein Skript nacheinander nach seinen Eigenschaften. Beurteile jede richtig, damit das Fragment die Prüfung besteht. Eine einzige falsche Entscheidung verbrennt die ganze Probe."""
    name: _str
    outpost: OutpostRef
    def report(self) -> _dict[_str, JsonValue]:
        """Der vollständige Zustandsbericht des geladenen Fragments: `self.report()` gibt für alle 10 Eigenschaften `{property: value}` zurück (`glow`, `brightness`, `smell`, `gunk`, `cracks`, `feel`, `twitch`, `bugs`, `weight`, `sound`). Lies den ganzen Bericht: Für manche Regeln brauchst du weitere Eigenschaften (Helligkeit hängt vom Leuchten ab, Gewicht von Ablagerungen und Klang von Rissen). Textwerte sind Strings, Zahlenwerte sind Zahlen. Wenn nichts geladen ist, wird `{}` zurückgegeben. Durchlaufe den Bericht mit `.items()` oder greife mit `report[\"gunk\"]` auf einen Wert zu."""
        ...
    def properties(self) -> _list[_str]:
        """Listet alle zehn Eigenschafts-IDs in einer festen Katalogreihenfolge auf, von `\"glow\"` bis `\"sound\"`. Die Liste ist bei jedem Tiefsee-Fragment gleich. Jede Prüfung fragt fünf Eigenschaften in zufälliger Reihenfolge ab; nutze `self.current()`, um die Eigenschaft der jeweiligen Stufe zu ermitteln."""
        ...
    def fragment(self) -> Literal["gw_spinal_vertebra", "vc_eye_stalk", "oc_lens_eye", "bw_tail_spike", "vd_tendril", "mh_stigmatic_disc", "hs_compound_eye", "ms_eye_cluster", "hc_tentacle_crown", "ma_luminous_ring", "gm_antennal_whip", "fs_holdfast_rootlet", "sd_talon", "ce_cephalic_photophore", "st_carapace_neural", "vm_ventral_photophore"] | None:
        """Die ID des unbehandelten Tiefsee-Fragments in der Kammer, abrufbar mit `self.fragment()`, oder `None`, wenn die Kammer leer ist."""
        ...
    def stage(self) -> _int:
        """Die aktuelle Stufe der Qualitätsprüfung: `self.stage()` gibt während eines laufenden Durchgangs **1-5** zurück, sonst **0** (wenn nichts geladen ist oder der Durchgang gerade abgeschlossen wurde). In jeder Stufe wird eine Eigenschaft geprüft."""
        ...
    def current(self) -> Literal["glow", "brightness", "smell", "gunk", "cracks", "feel", "twitch", "bugs", "weight", "sound"] | None:
        """Die Eigenschaft, die in dieser Stufe geprüft wird: `self.current()` gibt eine der 10 IDs zurück (schlage ihren Wert in `report()` nach, wende ihre Regel an und rufe dann `accept()` oder `reject()` auf). Wenn kein Durchgang läuft, gibt die Funktion `None` zurück. Welche 5 der 10 Eigenschaften drankommen, lässt sich nicht vorhersagen. Programmiere daher jede Regel."""
        ...
    def lights(self) -> _list[_str]:
        """Die bisherigen Ergebnisse der 5 Stufen: `self.lights()` gibt eine Liste mit `\"green\"` (richtige Entscheidung), `\"red\"` (Fehler, Durchgang beendet) und `\"pending\"` (noch nicht erreicht) zurück. Mit jeder Antwort leuchtet ein weiteres Licht auf."""
        ...
    def is_running(self) -> _bool:
        """`True`, solange ein Durchgang mit 5 Stufen läuft (ein Fragment ist geladen und es sind noch Stufen offen), abrufbar mit `self.is_running()`. Durchlaufe die Prüfung mit `while cond.is_running(): prop = cond.current(); ...`. Wird zu `False`, wenn der Durchgang erfolgreich endet, die Probe verbrennt oder nichts geladen ist."""
        ...
    def load(self, fragment_id: _str, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> ActionResult[Literal["ok", "chamber_occupied", "not_in_input", "invalid_fragment", "invalid_properties", "invalid_property_match", "busy", "output_full"]]:
        """Entnimmt `self.input` eine unbehandelte Tiefsee-Probe, legt sie in die Kammer und startet einen neuen Durchgang mit 5 Stufen. Mit den optionalen Parametern `properties` und `property_match` wählst du anhand der üblichen Modi „any“, „subset“ oder „exact“ eine bestimmte Variante aus. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def eject(self) -> ActionResult[Literal["ok", "empty", "busy", "output_full"]]:
        """Legt die unveränderte Probe aus der Kammer in `self.output` bereit und beendet den Durchgang. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def accept(self) -> ActionResult[Literal["ok", "conditioned", "burned", "no_run", "busy", "output_full"]]:
        """Markiert die aktuelle Eigenschaft als bestanden. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def reject(self) -> ActionResult[Literal["ok", "conditioned", "burned", "no_run", "busy", "output_full"]]:
        """Markiert die aktuelle Eigenschaft als beschädigt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
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

## `BioExchange`

```python
class BioExchange(Component):
    """Biobörse: Liefert Biologieproben für einen Bioauftrag und erfüllt damit in der Biologie die Funktion des Versorgungsdocks. Ein Skript weist der Biobörse einen Auftrag zu und liefert die benötigten Fragmente, bis die Belohnung ausgezahlt wird."""
    name: _str
    outpost: OutpostRef
    def orders(self) -> _list[BioOrder]:
        """Listet alle `BioOrder`-Objekte auf, auch Aufträge, die du noch nicht erfüllen kannst. Jeder Auftrag enthält seine ID, sein Biom, seine Anforderungen, Belohnung und seinen Status sowie gelieferte Proben, bereits `in_transit` befindliche Proben, den Fortschritt in Prozent und gegebenenfalls einen erforderlichen `target_glow`. Alle Biobörsen, die denselben Auftrag bedienen, teilen sich den Fortschritt. Berechne mit `requires - delivered - in_transit`, wie viele Proben noch fehlen, damit du keine bereits zugesagten Proben erneut herstellst. Übergib dann die gewählte `order.id` an `set_order(...)`. Aus einem anderen Skript rufst du `get_component(\"bio_exchange_1\").orders()` auf. `get_component(\"orders\")` ist für Aufträge der Erde vorgesehen."""
        ...
    def set_order(self, order_id: _str) -> ActionResult[Literal["ok", "unknown_order", "completed"]]:
        """Wählt den Bioauftrag aus, den diese Biobörse erfüllen soll. `self.set_order(\"bio_order_03\")`. Mehrere Biobörsen können **denselben** Bioauftrag aktivieren. Sie arbeiten mit einem gemeinsamen Lieferzähler, sodass große Bioaufträge gleichzeitig von mehreren Außenposten aus bedient werden können. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def clear_order(self) -> ActionResult[Literal["ok", "busy", "output_full"]]:
        """Hebt die Zuweisung des aktiven Bioauftrags für diese Biobörse auf. Bereits gelieferte Proben bleiben beim Bioauftrag erfasst, abgeschlossene Bioaufträge bleiben abgeschlossen und es werden keine Proben bewegt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def active_order(self) -> BioOrder | None:
        """Eine Momentaufnahme des aktiven `BioOrder`-Objekts mit `requires`, dem abgeschlossenen Fortschritt `delivered`, den aktuellen Zusagen `in_transit`, `percent` und `target_glow` (Zielfarbe der Küsteninfusion) zum Zeitpunkt des Aufrufs. Ist kein Auftrag zugewiesen, gibt die Funktion `None` zurück. `in_transit` umfasst passende Proben, die bereits in den Eingängen der beteiligten Biobörsen liegen, sowie laufende Lieferungen. Rufe `active_order()` erneut auf, um den neuesten Fortschritt zu lesen."""
        ...
    def matches_order(self, item_id: _str, properties: ItemProperties | None = ...) -> _bool:
        """Prüft, ob ein bestimmtes Item zum aktiven Bioauftrag dieser Biobörse passt, ohne es zu bewegen. Übergib `id` und `properties` eines `ItemStack`. `True` bedeutet, dass diese Variante die Anforderungen des Auftrags an Leuchten, Gene, geschmiedete oder konditionierte Proben beziehungsweise einfache Proben erfüllt. Verwende die Funktion mit `stacks()` des Inventars, eines Lagerbehälters oder eines Lagerhauses, bevor du eine genau bestimmte Variante mit `self.input.take(...)` entnimmst. Sie gibt `False` zurück, wenn kein Auftrag aktiv ist, der Auftrag abgeschlossen ist oder das Item nicht passt."""
        ...
    def deliver(self) -> ActionResult[Literal["ok", "complete", "no_input", "output_full", "no_active", "busy"]]:
        """Sendet eine passende Probe aus `self.input` zum aktiven Bioauftrag. `self.deliver()` bewegt pro Aufruf genau eine Probe und benötigt etwas Zeit; rufe die Funktion daher in einer Skriptschleife auf, bis der Auftrag erfüllt ist. Eine Probe zählt nur, wenn sie die genaue Anforderung des Auftrags erfüllt. In manchen Biomen reicht die richtige Fragment-ID allein nicht: Es wird eine bestimmte Leuchtfarbe, Genausstattung oder verarbeitete Variante verlangt. Mit `self.matches_order(item_id, properties)` kannst du einen Stapel vor der Entnahme prüfen. Der Fortschritt ist für **alle Biobörsen mit demselben Bioauftrag gemeinsam**. Eine andere Biobörse kann die letzte Probe zuerst liefern; eine überschüssige Probe wird dann zurückgegeben. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def lifetime_credits(self) -> _int:
        """Alle Credits, die diese Biobörse mit abgeschlossenen Bioaufträgen insgesamt verdient hat."""
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

## `BioLab`

```python
class BioLab(Component):
    """Biolabor: Automatisiert die Schritte Analysieren und Extrahieren des Biologieablaufs: Das Labor untersucht ein Exemplar und gewinnt daraus eine nutzbare Probe. Es bleibt untätig, bis ein Skript es steuert."""
    name: _str
    outpost: OutpostRef
    def take_from(self, collector: Component | IdRecord) -> ActionResult[Literal["ok", "busy", "input_occupied", "not_found", "source_empty", "source_busy", "wrong_outpost", "invalid_source", "output_full"]]:
        """Holt das Exemplar aus der Fracht eines Biosammlers in die Probenkammer dieses Labors. Der Quell-Biosammler muss sich am selben Außenposten wie das Labor befinden. Übergib eine ausdrückliche Referenz auf ihn: `self.take_from(get_component(\"bio_collector_1\"))`. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def analyze(self) -> AnalyzeResult[Literal["ok", "busy", "output_full", "input_empty", "invalid_specimen"]]:
        """Identifiziert das aktuelle Fragment im Labor und zeigt sein Extraktionsrezept an. Die Analyse dauert in jedem Biom **~0.1 h**; das Skript wartet, bis sie abgeschlossen ist. Nach einer erfolgreichen Analyse wird das Fragment zu `journal.cataloged_fragments(planet_id)` hinzugefügt. Die Identität des Lebewesens bleibt verborgen, bis alle fünf Fragmente katalogisiert sind. Danach erscheint es in `journal.cataloged_creatures(planet_id)`. Fester Ergebnisvertrag: `AnalyzeResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.info`."""
        ...
    def load(self, reagent_id: _str, qty: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> ActionResult[Literal["ok", "busy", "invalid_reagent", "invalid_qty", "invalid_properties", "invalid_property_match", "insufficient_input", "output_full"]]:
        """Stellt für das nächste `extract()` eine ganzzahlige Reagenzienmenge bereit und entnimmt sie aus `self.input`. `self.load(\"alkaline_buffer\", 4)`. Reagenzien werden im `shop` verkauft; sowohl Käufe über die Oberfläche als auch `shop.buy(reagent_id)` legen sie ins Basisinventar. Mit den optionalen Parametern `properties` und `property_match` wählst du anhand der üblichen Modi „any“, „subset“ oder „exact“ eine bestimmte Item-Variante aus. Bruchteile und negative Mengen lösen einen Argumentfehler aus. Wenn du `extract()` mit einem unpassenden Rezept aufrufst, werden die geladenen Reagenzien zerstört. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def unload_reagents(self) -> ActionResult[Literal["ok", "empty", "busy", "output_full"]]:
        """Legt alle geladenen Reagenzien in `self.output` bereit, ohne das Exemplar anzutasten. Verwende dies, wenn du das falsche Rezept vorbereitet hast. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def extract(self) -> ActionResult[Literal["ok", "output_full", "recipe_mismatch", "busy", "input_empty", "not_analyzed", "invalid_specimen"]]:
        """Verbraucht `loaded_reagents` und legt **1 Probe** des analysierten Exemplars in `self.output` ab. Ihre genauen Eigenschaften bleiben erhalten. Die Extraktion dauert in jedem Biom **~0.1 + 0.05 × units h**; das Skript wartet, bis sie abgeschlossen ist. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def discard(self) -> ActionResult[Literal["ok", "input_empty", "busy", "output_full"]]:
        """Verwirft das aktuelle Exemplar und legt alle geladenen Reagenzien in `self.output` bereit. Verwende dies, wenn `analyze()` ein Fragment aufdeckt, das du nicht brauchst. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    specimen: Specimen | None
    loaded_reagents: _dict[_str, _int]
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

## `BioLuminizer`

```python
class BioLuminizer(Component):
    """Bioluminisierer: Färbt das Leuchten eines Küstenfragments mit drei eingebauten Farblampen auf eine Zielfarbe. Jede Lampe trägt zu mehreren Farbkanälen bei. Ein Skript muss daher die Helligkeitswerte berechnen, die genau die Zielfarbe ergeben."""
    name: _str
    outpost: OutpostRef
    def load(self, fragment_id: _str, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> ActionResult[Literal["ok", "chamber_occupied", "not_in_input", "invalid_fragment", "invalid_properties", "invalid_property_match", "busy", "output_full"]]:
        """Entnimmt `self.input` eine unbehandelte, leuchtende Küstenprobe mit der ID `fragment_id` und legt sie in die Kammer: `self.load(\"gw_caudal_fin\")`. Mit den optionalen Parametern `properties` und `property_match` wählst du anhand der üblichen Modi „any“, „subset“ oder „exact“ eine bestimmte Variante aus. Lies ihre Ausgangsfarbe mit `self.chamber.glow`. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    chamber: ChamberSample | None
    def lamp_signature(self, channel: _str) -> _list[_int] | None:
        """Der RGB-Beitrag `[r,g,b]`, den eine Lampe pro Helligkeitsstufe hinzufügt, einschließlich ihrer Farbabweichung. `self.lamp_signature(\"red\")` ist ungefähr `[6, 1, 1]`: überwiegend Rot, aber auch ein wenig Grün und Blau. Lies alle drei Kanäle (`\"red\"`, `\"green\"`, `\"blue\"`), um die invertierbare 3×3-Matrix aufzubauen. Die Hardwarewerte sind fest: Lies sie einmal und verwende sie erneut. Für einen unbekannten Kanal wird `None` zurückgegeben."""
        ...
    def glow(self) -> _list[_int] | None:
        """Das **aktuelle** Leuchten der Kammer als `[r,g,b]` bei den momentan eingestellten Lampen. Änderungen durch `set_lamps(...)` werden sofort angezeigt. Prüfe damit deine Berechnung vor der endgültigen Verarbeitung: `if self.glow() == target: self.infuse()`. Bei leerer Kammer wird `None` zurückgegeben."""
        ...
    def set_lamps(self, r: _int, g: _int, b: _int) -> ActionResult[Literal["ok", "busy", "output_full"]]:
        """Stellt die Helligkeit der drei Lampen ein: `self.set_lamps(7, 13, 4)`. Jeder Wert muss eine **ganze Zahl von 0-40** sein. Die genaue Lösung ist immer ganzzahlig; runde deine berechneten Werte daher mit `round()`. Bruchteile oder Werte außerhalb des Bereichs lösen einen Argumentfehler aus, statt stillschweigend abgerundet zu werden. Wenn das Skript stoppt, werden die Lampen wieder auf 0 gesetzt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def infuse(self) -> ActionResult[Literal["ok", "output_full", "empty", "busy"]]:
        """Erzeuge in `self.output` eine **Leuchtende** Probe. Ihre übrigen Eigenschaften bleiben erhalten, und ihr bisheriges Leuchten wird durch das eingestellte Leuchten ersetzt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def discard(self) -> ActionResult[Literal["ok", "empty", "busy", "output_full"]]:
        """Legt die unveränderte Probe aus der Kammer in `self.output` bereit. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
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

## `BioOrder`

```python
class BioOrder:
    """bio_exchange.orders() / bio_exchange.active_order() / get_component(\"bio_exchange_1\").orders()"""
    id: _str
    name: _str
    biome: Literal["frozen", "coastal", "geothermal", "volcanic", "deep"]
    requires: _dict[_str, _int]
    reward: _int
    status: Literal["available", "active", "complete"]
    delivered: _dict[_str, _int]
    in_transit: _dict[_str, _int]
    percent: _float
    target_glow: _list[_int] | None
    required_genes: _dict[_str, _list[_str]] | None
```

## `BiomassMixer`

```python
class BiomassMixer(Component):
    """Biomassemischer: Mischt Biom-Essenzen zu Biomasse. Die globale Biomassephase legt die Mindestvielfalt fest, und jede weitere ausgewogene Essenz kann die Ausbeute steigern. Mk II liefert das 4,5-Fache an Biomasse, während der Essenzbedarf nur auf das 2,4-Fache steigt, bei fünffachem Stromverbrauch."""
    name: _str
    outpost: OutpostRef
    def biomass_rate(self) -> _float:
        """Beim letzten Tick erzeugte Biomasse in **t/h**. Die Summe über alle Biomassemischer auf dem Planeten ergibt die gesamte Biomasse-Produktionsrate."""
        ...
    def active_essences(self) -> _int:
        """Anzahl der Essenz-Eingangspuffer, die gerade Vorrat enthalten (**0-5**). Die aktuelle Phase bestimmt mit `required_essences()`, wie viele mindestens nötig sind. Zusätzliche, ausgewogen zugeführte Essenztypen können die Produktion steigern."""
        ...
    def mixing_essences(self) -> _int:
        """Anzahl der zugeführten Essenztypen, die beim letzten Tick für die stärkste ausgewogene Mischung ausgewählt wurden (**0-5**). Der Mischer prüft jede Vielfaltstufe ab dem Minimum der aktuellen Phase. Eine schwache zusätzliche Zufuhr kann die Produktion deshalb nie verringern."""
        ...
    def tier(self) -> _int:
        """Installierte Stufe des Mischers: **1** für Mk I oder **2** für Mk II. Mk II erzeugt **4,5×** so viel Biomasse, verbraucht dabei von jeder ausgewählten Essenz nur **2,4×** so viel und benötigt **5×** so viel Strom. Damit liefert Mk II pro Tonne Essenz **87,5 %** mehr Biomasse."""
        ...
    def is_stalled(self) -> _bool:
        """`True`, wenn der Mischer mit Strom versorgt wird, aber weniger Eingangspuffer nutzbare Essenz enthalten, als die aktuelle Biomassephase erfordert. Essenz im Puffer zählt auch ohne neuen Zufluss. Bei fehlender Stromversorgung oder ausreichend vielen verfügbaren Essenztypen ist der Wert `False`. Verbinde jeden noch fehlenden Essenzeingang mit einer passenden Quelle und stelle bei Bedarf eine Flüssigkeitsrohrleitung zwischen dem Eingang und einer weiter entfernten Quelle fertig. Die Biomassephase kann nur steigen, nie sinken."""
        ...
    def phase(self) -> _int:
        """Die globale Biomassephase (**1-6**), abgeleitet aus der insgesamt erzeugten Biomasse in Tonnen. Sie verwendet dieselben Schwellenwerte wie die Phasenanzeige der Sensoren. Die Phase bestimmt die Mindestzahl verschiedener Essenztypen, erhöht die Produktion aber nicht unmittelbar durch einen Multiplikator."""
        ...
    def required_essences(self) -> _int:
        """Wie viele verschiedene Biom-Essenzen in dieser Phase zugeführt werden müssen (**1-5**; entspricht der Phase, höchstens jedoch 5). Bei weniger Essenztypen steht der Mischer still. Zusätzliche Essenztypen können die Produktion steigern, wenn die größere Mischung ausgewogen genug ist."""
        ...
    frozen_essence_in: FluidPort
    coastal_essence_in: FluidPort
    geothermal_essence_in: FluidPort
    volcanic_essence_in: FluidPort
    deep_essence_in: FluidPort
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

## `BiomassSensor`

```python
class BiomassSensor(Component):
    """Biomassesensor: Meldet die kultivierte Biomasse auf dem Planeten in Tonnen. Der Wert wird laufend aktualisiert, während Biomassemischer produzieren. Verfügbar, sobald die Biosphärenforschung abgeschlossen ist; eine Kalibrierung ist nicht nötig."""
    name: _str
    def get_value(self) -> _float:
        """Gibt die gesamte Biomasse auf dem Planeten in Tonnen als Zahl zurück. Der Wert ist `0`, bevor ein Biomassemischer erstmals produziert hat."""
        ...
```

## `CatalogedCreature`

```python
class CatalogedCreature:
    """journal.cataloged_creatures(planet_id)"""
    creature_id: Literal["salt_tortoise", "magmatic_annelid", "mycelial_husk", "mantle_strider", "glasswing_mantis", "veil_mantle", "vault_crab", "tidal_cephalopod", "bone_walker", "vent_drifter", "hive_sentinel", "hollow_choir", "ferric_sea_lily", "crustal_echo", "glacial_wyrm", "spire_drake"]
    name: _str
    rarity: Literal["common", "uncommon", "rare", "legendary"]
    fragment_ids: _list[_str]
    feed_item_id: Literal["feed_salt_tortoise", "feed_magmatic_annelid", "feed_mycelial_husk", "feed_mantle_strider", "feed_glasswing_mantis", "feed_veil_mantle", "feed_vault_crab", "feed_tidal_cephalopod", "feed_bone_walker", "feed_vent_drifter", "feed_hive_sentinel", "feed_hollow_choir", "feed_ferric_sea_lily", "feed_crustal_echo", "feed_glacial_wyrm", "feed_spire_drake"]
    feed_recipe_id: Literal["craft_feed_salt_tortoise", "craft_feed_magmatic_annelid", "craft_feed_mycelial_husk", "craft_feed_mantle_strider", "craft_feed_glasswing_mantis", "craft_feed_veil_mantle", "craft_feed_vault_crab", "craft_feed_tidal_cephalopod", "craft_feed_bone_walker", "craft_feed_vent_drifter", "craft_feed_hive_sentinel", "craft_feed_hollow_choir", "craft_feed_ferric_sea_lily", "craft_feed_crustal_echo", "craft_feed_glacial_wyrm", "craft_feed_spire_drake"]
    revive_feed_required: _int
    revive_reagents: _dict[_str, _int]
```

## `CatalogedFragment`

```python
class CatalogedFragment:
    """journal.cataloged_fragments(planet_id)"""
    fragment_id: Literal["gw_cranial_plate", "gw_caudal_fin", "gw_cardiac_node", "gw_jaw_fang", "gw_spinal_vertebra", "vc_dorsal_carapace", "vc_mandible_claw", "vc_antenna_cluster", "vc_walking_leg", "vc_eye_stalk", "oc_cranium", "oc_tentacle_arm", "oc_chitin_beak", "oc_ink_sac", "oc_lens_eye", "bw_skull", "bw_foreclaw", "bw_ribcage", "bw_hindlimb", "bw_tail_spike", "vd_bell", "vd_nematocyst", "vd_neural_mesh", "vd_photophore", "vd_tendril", "mh_fruiting_body", "mh_spore_pod", "mh_mycelium_root", "mh_chitin_node", "mh_stigmatic_disc", "hs_mandible", "hs_wing_membrane", "hs_thorax_plate", "hs_abdomen_segment", "hs_compound_eye", "ms_chelicera", "ms_leg_tarsus", "ms_pedipalp", "ms_abdomen_sclerite", "ms_eye_cluster", "hc_aperture_lip", "hc_shell_whorl", "hc_septum_plate", "hc_beak", "hc_tentacle_crown", "ma_cranial_papilla", "ma_cuticle_molt", "ma_ganglion_node", "ma_chitinous_seta", "ma_luminous_ring", "gm_compound_eye", "gm_folded_wing", "gm_raptorial_claw", "gm_abdominal_sheath", "gm_antennal_whip", "fs_calyx_plate", "fs_arm_segment", "fs_stalk_columnal", "fs_oral_tegmen", "fs_holdfast_rootlet", "sd_cranial_crest", "sd_wing_membrane", "sd_obsidian_scale", "sd_tail_barb", "sd_talon", "ce_stalked_eye", "ce_swimmeret_lobe", "ce_mouth_disc", "ce_great_appendage", "ce_cephalic_photophore", "st_scute_plate", "st_plastron_shard", "st_limb_claw", "st_beak", "st_carapace_neural", "vm_cephalic_horn", "vm_wing_sheet", "vm_gill_filament", "vm_tail_barb", "vm_ventral_photophore"]
    name: _str
    biome: Literal["frozen", "coastal", "geothermal", "volcanic", "deep"]
    coords: _list[_float]
    rarity: Literal["common", "uncommon", "rare", "legendary"]
```

## `ChamberFragment`

```python
class ChamberFragment:
    """dna_sequencer.chamber"""
    fragment_id: Literal["gw_cardiac_node", "vc_antenna_cluster", "oc_chitin_beak", "bw_ribcage", "vd_neural_mesh", "mh_mycelium_root", "hs_thorax_plate", "ms_pedipalp", "hc_septum_plate", "ma_ganglion_node", "gm_raptorial_claw", "fs_stalk_columnal", "sd_obsidian_scale", "ce_mouth_disc", "st_limb_claw", "vm_gill_filament"]
    name: _str
    genes: _list[_str]
    spliced: _bool
```

## `DnaSequencer`

```python
class DnaSequencer(Component):
    """DNA-Sequenzierer: Fügt Gene in geothermische Fragmente ein, damit sie die Anforderungen eines Auftrags erfüllen. Du arbeitest mit einzelnen Genen: Lade ein Fragment, lies seine vorhandenen und benötigten Gene ab und setze die gewünschte Genauswahl ein. Die Maschine stellt daraus die DNA zusammen. Jedes Fragment kann nur einmal gespleißt werden."""
    name: _str
    outpost: OutpostRef
    def load(self, fragment_id: _str, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> ActionResult[Literal["ok", "chamber_occupied", "not_in_input", "invalid_fragment", "invalid_properties", "invalid_property_match", "busy", "output_full"]]:
        """Hole mit `fragment_id` eine geothermische Probe aus `self.input` in die Kammer, etwa mit `self.load(\"gw_cardiac_node\")`. Mit den optionalen Parametern `properties` und `property_match` wählst du eine bestimmte Variante: Bei any bleiben Eigenschaften unberücksichtigt, bei subset müssen alle angegebenen Eigenschaften übereinstimmen und bei exact muss die gesamte Eigenschaftsmenge exakt übereinstimmen. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    chamber: ChamberFragment | None
    def genes(self) -> _list[_str] | None:
        """Listet die Gene auf, die das Fragment in der Kammer derzeit trägt, zum Beispiel `[\"cold_tolerance\", \"pressure_tolerance\"]`; bei leerer Kammer wird `None` zurückgegeben. `splice()` braucht Zeit. Danach wandert das Fragment zum Ausgang und die Kammer ist leer. Ist der Ausgang voll, bleibt das gespleißte Fragment in der Kammer, bis Platz frei wird."""
        ...
    def gene_catalog(self) -> _list[_str]:
        """Alle Gen-IDs, die die Maschine spleißen kann. `self.gene_catalog()` gibt die vollständige Liste zurück (z. B. `[\"heat_resistance\", \"acid_resistance\", \"cold_tolerance\", \"pressure_tolerance\", \"toxin_resistance\", \"radiation_shield\"]`). Diese Werte kannst du an `splice()` übergeben."""
        ...
    def splice(self, genes: _list[_str]) -> ActionResult[Literal["ok", "destroyed", "empty", "unknown_gene", "busy", "output_full"]]:
        """Ersetze die Genkombination des Fragments in der Kammer durch genau `genes` und lege es dann in `self.output` ab. Alle Eigenschaften, die nichts damit zu tun haben, bleiben erhalten. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def discard(self) -> ActionResult[Literal["ok", "empty", "busy", "output_full"]]:
        """Lege das Fragment aus der Kammer ohne Spleißen in `self.output` ab. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
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

## `FeedMaker`

```python
class FeedMaker(Component):
    """Futterhersteller: Stellt nach einem von dir gewählten Rezept das Futter für die Kolonien in Habitaten her, ähnlich wie der Fabrikator. Das Rezept für jede Kreatur wird durch einen Biolabor-Auftrag freigeschaltet; die Maschine kann nur bereits freigeschaltetes Futter herstellen. Für die Aufrüstung auf Mk II benötigt jede Maschine ein eigenes, im Fabrikator hergestelltes Upgrade-Paket, das bei 250.000 Tierwelt freigeschaltet wird. Mk II beschleunigt sowohl die Herstellung als auch die automatische Zuführung am Eingang um das 1,5-Fache und verdoppelt den Stromverbrauch im Betrieb. Die Herstellung kann weiterlaufen, während die Zuführung abkühlt."""
    name: _str
    outpost: OutpostRef
    def tier(self) -> _int:
        """Aufrüstungsstufe der Maschine: 1 für Mk I oder 2 für Mk II."""
        ...
    def list_recipes(self) -> _list[Recipe]:
        """Listet die durch Aufträge im Biolabor freigeschalteten Futterrezepte auf: ein `Recipe` pro Tierart, deren Futter du herstellen kannst. Gesperrte Rezepte erscheinen nicht. Jedes Rezept enthält Stufe, ID, Name, Eingaben, Ausgabe, Dauer und Stromverbrauch. Mit `for recipe in self.list_recipes(): print(recipe.tier, recipe.id)` siehst du, was verfügbar ist."""
        ...
    def find_recipe(self, recipe_id: _str) -> Recipe | None:
        """Findet ein freigeschaltetes Futterrezept anhand seiner ID, ohne `list_recipes()` durchlaufen zu müssen. Gibt das zugehörige `Recipe`-Objekt zurück oder `None`, wenn die ID unbekannt oder das Rezept gesperrt ist oder zu einer anderen Maschine gehört."""
        ...
    def set_recipe(self, recipe_or_id: RecipeRef) -> ActionResult[Literal["ok", "unknown_recipe", "offline", "recipe_locked", "busy", "material_mismatch"]]:
        """Wähle anhand der ID oder mit einem Rezept aus `list_recipes()` aus, welches Tierfutter hergestellt werden soll, zum Beispiel mit `self.set_recipe(\"craft_feed_salt_tortoise\")`. Sobald ein Rezept ausgewählt ist, stellt ProcessingSystem automatisch Futter her, wenn die Zutaten im Vorrat liegen und im Ausgabebehälter Platz ist. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def clear_recipe(self) -> ActionResult[Literal["ok", "busy", "material_present"]]:
        """Hebe die Auswahl des Futterrezepts auf und versetze den Futterhersteller in den Leerlauf. Der Eingangsvorrat bleibt gefüllt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def get_recipe(self) -> Literal["", "craft_feed_salt_tortoise", "craft_feed_magmatic_annelid", "craft_feed_mycelial_husk", "craft_feed_mantle_strider", "craft_feed_glasswing_mantis", "craft_feed_veil_mantle", "craft_feed_vault_crab", "craft_feed_tidal_cephalopod", "craft_feed_bone_walker", "craft_feed_vent_drifter", "craft_feed_hive_sentinel", "craft_feed_hollow_choir", "craft_feed_ferric_sea_lily", "craft_feed_crustal_echo", "craft_feed_glacial_wyrm", "craft_feed_spire_drake"]:
        """Gibt die aktuelle Rezept-ID zurück oder `\"\"`, wenn kein Rezept ausgewählt ist oder das ausgewählte Rezept nicht mehr freigeschaltet ist. Prüfe den Zustand, bevor du erneut ein Rezept festlegst: `if self.get_recipe() == \"\": self.set_recipe(...)`."""
        ...
    def get_recipe_inputs(self) -> _dict[_str, _int]:
        """Ein dict, das jeder Eingabe-`item_id` die pro Herstellungsvorgang verbrauchte Stückzahl zuordnet (ein leeres dict, wenn kein Rezept ausgewählt ist). Durchlaufe es, um zu bestimmen, was eingelagert werden muss: `for item, qty in self.get_recipe_inputs().items(): self.input.take(item, qty * 5)`."""
        ...
    def get_stockpile(self) -> _dict[_str, _int]:
        """Ein dict, das jeder `item_id` im Eingangsvorrat ihre aktuelle Stückzahl zuordnet. Lies es ab, um vor der Herstellung zu sehen, was bereits bereitliegt."""
        ...
    def get_stockpile_used(self) -> _int:
        """Gesamtzahl der Einheiten aller Materialien im Eingangsvorrat. Vergleiche sie mit `get_stockpile_capacity()`, um eine Überfüllung zu vermeiden."""
        ...
    def get_stockpile_capacity(self) -> _int:
        """Gemeinsame Obergrenze für die Anzahl der Einheiten aller Materialien im Eingangsvorrat. Alle Materialien teilen sich diese Grenze; ihre Mengen werden zusammengerechnet."""
        ...
    def is_running(self) -> _bool:
        """`True`, wenn die Herstellung in diesem Tick voranschreitet (ein Rezept ist ausgewählt, Zutaten sind vorhanden und im Ausgabebehälter ist Platz). `False`, wenn Zutaten fehlen, der Ausgang voll ist, die Maschine im Leerlauf ist oder keinen Strom hat. Frage den Wert regelmäßig ab, um eine stockende Produktionslinie zu erkennen."""
        ...
    def get_progress(self) -> _float:
        """Fortschritt des aktuellen Herstellungsvorgangs als Anteil von **0-1**. Wird bei jedem Abschluss auf 0 zurückgesetzt (eine Futtercharge landet im Ausgabebehälter) und steigt erneut, wenn weitere Zutaten vorhanden sind."""
        ...
    def get_output_count(self) -> _int:
        """Anzahl fertiger Futtereinheiten, die im Ausgabebehälter auf Abholung warten. Transportiere sie mit `self.output.send(...)` weiter, bevor der Behälter voll ist (ein voller Ausgabebehälter stoppt die Herstellung)."""
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

## `FragmentLocation`

```python
class FragmentLocation:
    """bio_collector.scan()"""
    coords: _list[_float]
    distance: _float
    cataloged: _bool
    fragment_id: Literal["gw_cranial_plate", "gw_caudal_fin", "gw_cardiac_node", "gw_jaw_fang", "gw_spinal_vertebra", "vc_dorsal_carapace", "vc_mandible_claw", "vc_antenna_cluster", "vc_walking_leg", "vc_eye_stalk", "oc_cranium", "oc_tentacle_arm", "oc_chitin_beak", "oc_ink_sac", "oc_lens_eye", "bw_skull", "bw_foreclaw", "bw_ribcage", "bw_hindlimb", "bw_tail_spike", "vd_bell", "vd_nematocyst", "vd_neural_mesh", "vd_photophore", "vd_tendril", "mh_fruiting_body", "mh_spore_pod", "mh_mycelium_root", "mh_chitin_node", "mh_stigmatic_disc", "hs_mandible", "hs_wing_membrane", "hs_thorax_plate", "hs_abdomen_segment", "hs_compound_eye", "ms_chelicera", "ms_leg_tarsus", "ms_pedipalp", "ms_abdomen_sclerite", "ms_eye_cluster", "hc_aperture_lip", "hc_shell_whorl", "hc_septum_plate", "hc_beak", "hc_tentacle_crown", "ma_cranial_papilla", "ma_cuticle_molt", "ma_ganglion_node", "ma_chitinous_seta", "ma_luminous_ring", "gm_compound_eye", "gm_folded_wing", "gm_raptorial_claw", "gm_abdominal_sheath", "gm_antennal_whip", "fs_calyx_plate", "fs_arm_segment", "fs_stalk_columnal", "fs_oral_tegmen", "fs_holdfast_rootlet", "sd_cranial_crest", "sd_wing_membrane", "sd_obsidian_scale", "sd_tail_barb", "sd_talon", "ce_stalked_eye", "ce_swimmeret_lobe", "ce_mouth_disc", "ce_great_appendage", "ce_cephalic_photophore", "st_scute_plate", "st_plastron_shard", "st_limb_claw", "st_beak", "st_carapace_neural", "vm_cephalic_horn", "vm_wing_sheet", "vm_gill_filament", "vm_tail_barb", "vm_ventral_photophore"] | None
    name: _str | None
    rarity: Literal["common", "uncommon", "rare", "legendary"] | None
```

## `LifeFormSample`

```python
class LifeFormSample:
    """PortableBioScanner.scan().scan.life_forms[i] nach status == \"ok\""""
    type: Literal["ice_algae", "snow_moss", "frost_lichen", "cold_spores", "ice_crust", "frost_fungus", "sea_algae", "tide_moss", "shore_lichen", "brine_plankton", "salt_crust", "coral_fungus", "vent_algae", "steam_moss", "heat_lichen", "hot_spores", "heat_crust", "vent_fungus", "sulfur_moss", "cinder_lichen", "ash_spores", "lava_algae", "magma_crust", "black_fungus", "cave_moss", "stone_lichen", "crystal_spores", "deep_algae", "stone_mat", "cave_fungus"]
    tons: _float
    remaining_tons: _float
    rarity: Literal["common", "uncommon", "rare"]
    biome: Literal["frozen", "coastal", "geothermal", "volcanic", "deep"]
```

## `OilGenerator`

```python
class OilGenerator(Component):
    """Ölgenerator: Verbrennt Öl zu kräftigem, gepuffertem Überbrückungsstrom. Ölquellen wechseln zwischen aktiven und ruhenden Phasen, also puffere ihre Förderung in Flüssigkeitstanks, um durchgehend Strom zu erzeugen. Bleibt im Leerlauf, bis ein Skript ihn betreibt."""
    name: _str
    outpost: OutpostRef
    def power_output(self) -> _float:
        """Watt, die beim letzten Stromtick ins Netz eingespeist wurden. **0**, wenn die Drosselung auf 0 steht ODER der Eingangspuffer oil_in nicht genug Öl enthält. Die Leistung des Generators richtet sich nach der verfügbaren Ölmenge: Bei teilweisem Ölmangel liefert er entsprechend weniger Strom. Der Wert wird einmal pro Stromtick aktualisiert; ein neuer Aufruf von `set_throttle(...)` wirkt sich im nächsten Tick aus."""
        ...
    def oil_consumption(self) -> _float:
        """Tatsächlicher Ölverbrauch beim letzten Stromtick in t/h. Bei ausreichender Ölversorgung steigt der Bedarf linear mit der Drosselung: von **0 t/h** bei 0 auf **8 t/h** bei 1. Teilweiser oder vollständiger Ölmangel senkt den tatsächlichen Verbrauch."""
        ...
    def throttle(self) -> _float:
        """Aktuelle Drosselung (**0-1**). Standardmäßig **0**; der Generator läuft im Leerlauf, bis ein Skript ihn steuert."""
        ...
    def set_throttle(self, rate: _float) -> ActionResult[Literal["ok"]]:
        """Stelle die Drosselung des Generators ein (**0-1**). Stromerzeugung und Ölverbrauch steigen linear mit der Drosselung. Dieser vom Skript gesteuerte Sollwert wird auf **0** zurückgesetzt, wenn das Skript angehalten wird, endet oder einen Fehler auslöst. Lass die Regelschleife daher laufen, solange der Generator arbeiten soll. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
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

## `OxygenGenerator`

```python
class OxygenGenerator(Component):
    """Sauerstoffgenerator: Entnimmt der Atmosphäre CO2 und wandelt es in atembaren Sauerstoff um – ein wichtiger Schritt hin zu einem bewohnbaren Planeten. Er läuft nur, wenn ein Skript seine Ansaugrate einstellt."""
    name: _str
    outpost: OutpostRef
    input: InputSlot
    water_in: FluidPort
    def set_intake(self, value: _float) -> ActionResult[Literal["ok"]]:
        """Stelle die CO2-Ansaugrate für diesen Tick ein. Rufe in jedem Durchlauf `self.set_intake(atmosphere.get_co2() / 10)` auf: Die Kammer erreicht ihre höchste Effizienz bei genau **1/10** des CO2-Gehalts der Umgebung. Höhere oder niedrigere Werte senken die Effizienz gleichmäßig; es gibt keinen Grenzwert, der eine besonders genaue Einstellung erfordert. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def waste(self) -> _float:
        """Aktueller Kohlenstoffabfallwert (**0-100**). Unter **60** läuft die Produktion ohne Einbußen, zwischen **60-100** sinkt sie linear und bei **100** kommt sie zum Stillstand (keine Produktion). Prüfe den Wert vor jedem Aufruf von `dump_waste()`: Das Entsorgen zwischen **50-60** verursacht keine Einbußen, außerhalb dieses Bereichs kostet es Effizienz."""
        ...
    def dump_penalty(self) -> _float:
        """Aktueller Effizienzabzug durch den letzten Aufruf von `dump_waste()` (**0-1**). `0` bedeutet, dass kein Abzug durch das Entsorgen aktiv ist; `0.25` bedeutet 25 % weniger Produktion. Ein ungünstiger Entsorgungsvorgang bleibt hier bis zum nächsten Aufruf von `dump_waste()` sichtbar."""
        ...
    def dump_waste(self) -> WasteDumpResult[Literal["ok"]]:
        """Entsorge angesammelten Kohlenstoffabfall. Rufe `result = self.dump_waste()` auf, wenn `waste()` im günstigen Bereich von **50-60** liegt, um ihn ohne Einbußen zu entsorgen. Ein Effizienzabzug bleibt bis zum nächsten Entsorgungsvorgang bestehen. Fester Ergebnisvertrag: `WasteDumpResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.penalty`."""
        ...
    def efficiency(self) -> _float:
        """Aktuelle Umwandlungseffizienz (**0-100%**). Sie erreicht **100%**, wenn die Ansaugrate **CO2/10** entspricht, CO2 vorhanden ist, der Abfallwert höchstens **60** beträgt und kein Effizienzabzug durch das Entsorgen aktiv ist. Über **60** senkt der Abfallwert die Effizienz; bei **100** kommt die Produktion zum Stillstand. Der Bereich **50-60** erlaubt das Entsorgen mit `dump_waste()` ohne Einbußen. Außerhalb davon entsteht ein Effizienzabzug, den du mit `dump_penalty()` auslesen kannst."""
        ...
    def output(self) -> _float:
        """Aktuelle O2-Produktionsrate in **ppt/h** bei den derzeitigen Einstellungen. Sie ergibt sich aus `efficiency()` × Stufenmultiplikator und ist durch das verfügbare CO2 begrenzt. Der Wert ist `0`, wenn die Maschine keinen Strom hat, kein Skript läuft, das CO2 aufgebraucht ist oder der Abfall die Produktion zum Stillstand gebracht hat. Bei jedem Abruf wird er neu berechnet; ein neuer Aufruf von `set_intake(...)` wirkt sich sofort aus. Nutze den Wert für aktuelle Übersichten oder um einen Leistungsabfall während der Regelschleife zu erkennen."""
        ...
    def tier(self) -> _int:
        """Dauerhaft installierte Mk-Stufe als ganze Zahl (**1-4**). Upgradepakete erhöhen diesen Wert; ein vorübergehender Flüssigkeitsmangel bei Mk III ändert ihn nicht. Vergleiche ihn mit `effective_tier()`, wenn du die Versorgung oder verminderte Leistung des Generators untersuchst."""
        ...
    def is_degraded(self) -> _bool:
        """`True`, wenn einem Mk-III-Paket die benötigte Flüssigkeit fehlt und die Maschine in diesem Tick auf den Multiplikator der vorherigen Stufe zurückgefallen ist. Prüfe den Wert nach der Installation eines Mk-III-Pakets, bevor du dich darauf verlässt, dass `output()` deine Prognose für Mk III erreicht. Bei `True` prüfe `self.water_in.level()` und die vorgelagerte Leitung."""
        ...
    def effective_tier(self) -> _int:
        """Die in diesem Tick tatsächlich wirksame Stufe: normalerweise `tier()`, bei `True` für `is_degraded()` die vorherige Stufe. Skripte, die über eine zusätzliche Wasserzufuhr zu diesem Generator entscheiden, sollten `effective_tier()` mit `tier()` vergleichen."""
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

## `PortableBioExtractor`

```python
class PortableBioExtractor:
    """self.bio_extractor (Drohnen)"""
    def extract(self) -> BioExtractionResult[Literal["ok", "not_mounted", "scrambled", "busy", "not_at_location", "not_scanned", "cooling", "no_cargo_space"]]:
        """An dem entdeckten dauerhaften Biostandort wird unter einer schwebenden Drohne Material geerntet. Die Drohne bleibt bis zum Abschluss beschäftigt, auch wenn das Skript zwischenzeitlich gestoppt und neu gestartet wird. Das Modul hat eine Kammer für 25 t eines Lebensformtyps; Frachtkapseln erhöhen die Kapazität. Wird der Standort nur teilweise abgeerntet, bleibt sein Bestand reduziert, und die Abklingzeit beginnt erst, wenn er leer ist. Fester Ergebnisvertrag: `BioExtractionResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.extracted`."""
        ...
```

## `PortableBioScanner`

```python
class PortableBioScanner:
    """self.bio_scanner (Drohnen)"""
    def scan(self) -> BioScanResult[Literal["ok", "not_mounted", "scrambled", "busy", "not_at_location"]]:
        """Scan mit Wartezeit an der aktuellen ganzzahligen Koordinate der schwebenden Drohne. An einer gültigen Koordinate ohne Standort endet er mit einem leeren biologischen Scan. Wiederholte Scans sind kostenlos. Fester Ergebnisvertrag: `BioScanResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.scan`."""
        ...
```

## `PressureGenerator`

```python
class PressureGenerator(Component):
    """Druckgenerator: Verdichtet die dünne Atmosphäre, um den Oberflächendruck zu erhöhen. Am besten arbeitet er, wenn ein Skript bei jedem Durchlauf der Anzeige das Synchronisationsfenster trifft. Verpasste Fenster kosten Effizienz."""
    name: _str
    outpost: OutpostRef
    input: InputSlot
    water_in: FluidPort
    def gauge(self) -> _float:
        """Aktueller Wert der Resonanzanzeige beim Durchlauf (**0–100**). Er steigt mit jedem Tick und springt nach **100** wieder an den Anfang. Vergleiche ihn mit `next_window_low()` und `next_window_high()`. Liegt er einschließlich der beiden Grenzwerte in diesem Bereich, rufe `sync()` auf."""
        ...
    def next_window_low(self) -> _float:
        """Untere Grenze des Synchronisationsfensters im aktuellen Durchlauf; sie gehört zum Fenster. Verwende den Wert mit `next_window_high()` und `gauge()` und rufe `sync()` auf, wenn die Anzeige innerhalb des Bereichs liegt. Der Wert ändert sich, wenn die Anzeige am Ende des Durchlaufs wieder an den Anfang springt."""
        ...
    def next_window_high(self) -> _float:
        """Obere Grenze des Synchronisationsfensters im aktuellen Durchlauf; sie gehört zum Fenster. Verwende den Wert mit `next_window_low()` und `gauge()` und rufe `sync()` auf, wenn die Anzeige innerhalb des Bereichs liegt. Der Wert ändert sich, wenn die Anzeige am Ende des Durchlaufs wieder an den Anfang springt."""
        ...
    def sync(self) -> ActionResult[Literal["ok"]]:
        """Versucht, diesen Durchlauf zu synchronisieren. Nur der erste Aufruf pro Durchlauf zählt; weitere Aufrufe vor dem Rücksprung der Anzeige bewirken nichts. Treffer (Anzeige im Fenster) → **+25 %** Effizienz. Fehlschlag (Anzeige außerhalb des Fensters oder keine Synchronisation vor Ende des Durchlaufs) → **−10 %**. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def efficiency(self) -> _float:
        """Aktuelle Verdichtungseffizienz (**0–100 %**). Sie steigt bei Treffern und sinkt bei Fehlschlägen, jedoch nie unter **0**. Ein gut abgestimmtes Skript hält sie bei oder nahe **100 %**, indem es in jedem Durchlauf das Fenster trifft. An diesem Wert erkennst du, ob ein Skript das wechselnde Fenster verfehlt."""
        ...
    def output(self) -> _float:
        """Aktuelle Produktionsrate in **kPa/h** bei der derzeitigen `efficiency()`. Sie ist proportional zu `efficiency()` × Stufenmultiplikator. Da die Resonanzanzeige nur langsam voranschreitet, beurteilst du den Druckfortschritt am besten anhand von `efficiency()` und der Tagesprognose auf der Sensoranzeige statt anhand eines einzelnen Aufrufs von `output()`."""
        ...
    def tier(self) -> _int:
        """Dauerhaft installierte Mk-Stufe als Ganzzahl (**1–4**). Upgrade-Pakete erhöhen diesen Wert; ein vorübergehender Flüssigkeitsmangel bei Mk III tut das nicht. Vergleiche ihn mit `effective_tier()`, wenn du einen versorgten oder in der Leistung verringerten Generator untersuchst."""
        ...
    def is_degraded(self) -> _bool:
        """`True`, wenn einem Mk-III-Paket der benötigte Flüssigkeitszufluss fehlt und die Maschine für diesen Tick auf den Multiplikator der vorherigen Stufe zurückgefallen ist. Prüfe den Wert nach der Installation eines Mk-III-Pakets. Ist er `True`, arbeitet das Paket mit verringerter Leistung; untersuche `self.water_in.level()` und die vorgelagerte Versorgung."""
        ...
    def effective_tier(self) -> _int:
        """Die in diesem Tick tatsächlich wirksame Stufe: normalerweise `tier()`, bei `is_degraded()` gleich `True` die vorherige Stufe. Skripte, die den Wasserfluss zwischen Generatoren neu verteilen, sollten `effective_tier()` mit `tier()` vergleichen."""
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

## `SolarGenerator`

```python
class SolarGenerator(Component):
    """Solargenerator: Wandelt Sonnenlicht in bis zu **50 W** für das Stromnetz um, wenn ein Skript die Sonne verfolgt. Eine ungünstige Neigung verringert die Leistung am Tag; nachts beträgt sie **0 W**."""
    name: _str
    outpost: OutpostRef
    def set_tilt(self, degrees: _float) -> ActionResult[Literal["ok"]]:
        """Stelle den Neigungswinkel des Solarpanels in Grad ein. Der Bereich reicht von **0°** (flach) bis **90°** (senkrecht); Werte außerhalb werden auf die jeweilige Grenze gesetzt. Eine gut eingestellte Nachführung hält die Leistung den ganzen Tag nahe am Maximum. Bei fester Neigung geht ein großer Teil der möglichen Leistung verloren. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def tilt(self) -> _float:
        """Aktueller Sollwert für die Panelneigung in Grad (**0-90**). Gibt den Wert zurück, den das Skript zuletzt mit `self.set_tilt(...)` gesetzt hat, oder bei einem inaktiven Panel den standardmäßigen Ruhewinkel. Nutze den Wert, um deine Schwenkschleife zu prüfen oder die nächste Neigung anhand des vorherigen Werts zu bestimmen."""
        ...
    def get_output(self) -> _float:
        """Aktuelle Leistung dieses Generators in Watt. Gibt **0** zurück, wenn er ausgeschaltet ist. Der Wert wird laufend aus Sonnenhöhe und Panelneigung berechnet. Vergleiche ihn mit der Nennleistung des Panels, um zu prüfen, ob die Nachführung die maximale Leistung hält."""
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

## `Specimen`

```python
class Specimen:
    """bio_collector.cargo / bio_lab.specimen"""
    coords: _list[_float]
    distance: _float
    stage: Literal["collected", "analyzed"]
    fragment_id: Literal["gw_cranial_plate", "gw_caudal_fin", "gw_cardiac_node", "gw_jaw_fang", "gw_spinal_vertebra", "vc_dorsal_carapace", "vc_mandible_claw", "vc_antenna_cluster", "vc_walking_leg", "vc_eye_stalk", "oc_cranium", "oc_tentacle_arm", "oc_chitin_beak", "oc_ink_sac", "oc_lens_eye", "bw_skull", "bw_foreclaw", "bw_ribcage", "bw_hindlimb", "bw_tail_spike", "vd_bell", "vd_nematocyst", "vd_neural_mesh", "vd_photophore", "vd_tendril", "mh_fruiting_body", "mh_spore_pod", "mh_mycelium_root", "mh_chitin_node", "mh_stigmatic_disc", "hs_mandible", "hs_wing_membrane", "hs_thorax_plate", "hs_abdomen_segment", "hs_compound_eye", "ms_chelicera", "ms_leg_tarsus", "ms_pedipalp", "ms_abdomen_sclerite", "ms_eye_cluster", "hc_aperture_lip", "hc_shell_whorl", "hc_septum_plate", "hc_beak", "hc_tentacle_crown", "ma_cranial_papilla", "ma_cuticle_molt", "ma_ganglion_node", "ma_chitinous_seta", "ma_luminous_ring", "gm_compound_eye", "gm_folded_wing", "gm_raptorial_claw", "gm_abdominal_sheath", "gm_antennal_whip", "fs_calyx_plate", "fs_arm_segment", "fs_stalk_columnal", "fs_oral_tegmen", "fs_holdfast_rootlet", "sd_cranial_crest", "sd_wing_membrane", "sd_obsidian_scale", "sd_tail_barb", "sd_talon", "ce_stalked_eye", "ce_swimmeret_lobe", "ce_mouth_disc", "ce_great_appendage", "ce_cephalic_photophore", "st_scute_plate", "st_plastron_shard", "st_limb_claw", "st_beak", "st_carapace_neural", "vm_cephalic_horn", "vm_wing_sheet", "vm_gill_filament", "vm_tail_barb", "vm_ventral_photophore"] | None
    name: _str | None
    rarity: Literal["common", "uncommon", "rare", "legendary"] | None
    recipe: _dict[_str, _int] | None
    production_tier: _int | None
    glow: _list[_int] | None
    genes: _list[_str]
```

## `generator`

```python
class generator:
    """Aufruf einer Funktion mit `yield` · Generatorausdrücke"""
    def send(self, value: object) -> Any:
        """Setzt den Generator fort und macht `value` zum Ergebnis seiner pausierten `yield`-Anweisung. Gibt den nächsten gelieferten Wert zurück. Wird vor dem ersten yield ein anderer Wert als `None` gesendet, wird `TypeError` ausgelöst; beim Abschluss wird `StopIteration` ausgelöst."""
        ...
    def throw(self, exception: BaseException | _type) -> Any:
        """Löst an der pausierten `yield`-Anweisung des Generators eine Ausnahme aus. Fängt der Generator sie ab und liefert erneut einen Wert, wird dieser zurückgegeben; andernfalls wird die Ausnahme weitergegeben."""
        ...
    def close(self) -> None:
        """Beendet den Generator, indem an seiner pausierten yield-Anweisung `GeneratorExit` ausgelöst wird. Der Aufräumcode in `finally` läuft, bevor der Aufruf zurückkehrt. Liefert der Generator während des Schließens einen Wert, wird `RuntimeError` ausgelöst."""
        ...
    def __iter__(self) -> generator:
        """Gibt diesen Generator zurück. Generatoren sind Iteratoren, die nur einmal durchlaufen werden können."""
        ...
    def __next__(self) -> Any:
        """Setzt den Generator mit `None` fort und gibt den nächsten von ihm gelieferten Wert zurück. Beim Abschluss wird `StopIteration` ausgelöst."""
        ...
    __name__: _str
    __qualname__: _str
```
