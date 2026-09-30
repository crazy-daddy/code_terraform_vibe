# Models: Miscellaneous Game Objects & Sub-structures

Granular data models and return types extracted from `__builtins__.pyi`.

## `AlienTerminal`

```python
class AlienTerminal:
    """.terminal"""
    def guess(self, digits: _list[_int]) -> GuessResult:
        """Prüft eine Liste mit genau 15 ganzzahligen Ziffern im Bereich **1-5** und gibt `GuessResult` zurück. Übereinstimmungen an derselben Position werden zuerst entfernt; danach zählt `.misplaced` die übrigen gemeinsamen Vorkommen, ohne einzelne Vorkommen doppelt zu zählen. Ein Argument oder Element des falschen Typs löst `TypeError` aus; eine falsche Länge, gebrochene Zahlen oder Ziffern außerhalb des Bereichs lösen `ValueError` aus."""
        ...
    length: _int
```

## `AnalyzeInfo`

```python
class AnalyzeInfo:
    """bio_lab.analyze().info nach status == \"ok\""""
    fragment_id: Literal["gw_cranial_plate", "gw_caudal_fin", "gw_cardiac_node", "gw_jaw_fang", "gw_spinal_vertebra", "vc_dorsal_carapace", "vc_mandible_claw", "vc_antenna_cluster", "vc_walking_leg", "vc_eye_stalk", "oc_cranium", "oc_tentacle_arm", "oc_chitin_beak", "oc_ink_sac", "oc_lens_eye", "bw_skull", "bw_foreclaw", "bw_ribcage", "bw_hindlimb", "bw_tail_spike", "vd_bell", "vd_nematocyst", "vd_neural_mesh", "vd_photophore", "vd_tendril", "mh_fruiting_body", "mh_spore_pod", "mh_mycelium_root", "mh_chitin_node", "mh_stigmatic_disc", "hs_mandible", "hs_wing_membrane", "hs_thorax_plate", "hs_abdomen_segment", "hs_compound_eye", "ms_chelicera", "ms_leg_tarsus", "ms_pedipalp", "ms_abdomen_sclerite", "ms_eye_cluster", "hc_aperture_lip", "hc_shell_whorl", "hc_septum_plate", "hc_beak", "hc_tentacle_crown", "ma_cranial_papilla", "ma_cuticle_molt", "ma_ganglion_node", "ma_chitinous_seta", "ma_luminous_ring", "gm_compound_eye", "gm_folded_wing", "gm_raptorial_claw", "gm_abdominal_sheath", "gm_antennal_whip", "fs_calyx_plate", "fs_arm_segment", "fs_stalk_columnal", "fs_oral_tegmen", "fs_holdfast_rootlet", "sd_cranial_crest", "sd_wing_membrane", "sd_obsidian_scale", "sd_tail_barb", "sd_talon", "ce_stalked_eye", "ce_swimmeret_lobe", "ce_mouth_disc", "ce_great_appendage", "ce_cephalic_photophore", "st_scute_plate", "st_plastron_shard", "st_limb_claw", "st_beak", "st_carapace_neural", "vm_cephalic_horn", "vm_wing_sheet", "vm_gill_filament", "vm_tail_barb", "vm_ventral_photophore"]
    name: _str
    rarity: Literal["common", "uncommon", "rare", "legendary"]
    required_recipe: _dict[_str, _int]
    coords: _list[_float]
    distance: _float
```

## `Analyzer`

```python
class Analyzer:
    """.analyzer"""
    def read(self, group: _list[_str]) -> _str:
        """Liest eine Liste mit genau fünf Zeichenfolgen-Tokens und gibt das einzelne Token zurück, aus dem sie erweitert wurden. Ein Argument, das keine Liste ist, oder ein Element, das keine Zeichenfolge ist, löst `TypeError` aus; eine falsche Länge oder eine unbekannte Gruppe löst `ValueError` aus."""
        ...
```

## `Arbiter`

```python
class Arbiter:
    """.arbiter"""
    def new_game(self) -> ActionResult[Literal["ok", "in_progress"]]:
        """Starte ein neues 3×3-Spiel auf einem leeren Spielfeld. Du ziehst zuerst. Nach einem beendeten Spiel wartet dieser Aufruf etwa eine halbe Sekunde, bevor das nächste Spielfeld bereit ist. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def restart(self) -> ActionResult[Literal["ok"]]:
        """Brich ein laufendes Spiel ab und starte ein neues. Du ziehst zuerst. Ein Abbruch während des Spiels zählt nicht als Sieg und setzt deine Siegesserie im aktuellen Skriptdurchlauf auf 0 zurück. Wie new_game() wartet auch dieser Aufruf zwischen den Spielen etwa eine halbe Sekunde. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def play(self, cell: _int) -> ActionResult[Literal["ongoing", "win", "loss", "draw", "occupied", "no_game"]]:
        """Setze dein Zeichen auf ein Spielfeld mit ganzzahligem Index im Bereich **0-8** (zeilenweise nummeriert). Danach antwortet der Arbiter. Drei Zeichen in einer Reihe, Spalte oder Diagonale gewinnen. Ein nicht numerischer Feldwert löst `TypeError` aus; ein nicht endlicher, gebrochener oder außerhalb des Bereichs liegender Wert löst `ValueError` aus, noch bevor der Spielzustand berücksichtigt wird. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def board(self) -> _list[_str]:
        """Die 9 Spielfelder als Liste, mit den Indizes 0–8 zeilenweise angeordnet. Jedes Feld enthält \"\" (leer), \"you\" oder \"arbiter\"."""
        ...
    def result(self) -> Literal["ongoing", "win", "loss", "draw", "no_game"]:
        """Ergebnis des aktuellen Spiels: \"ongoing\", \"win\", \"loss\", \"draw\" oder \"no_game\" (noch kein Spiel gestartet)."""
        ...
    def streak(self) -> _int:
        """Siege in Folge im aktuellen Skriptdurchlauf. Wird bei einer Niederlage, einem Unentschieden, einem Abbruch oder einem neuen Skriptdurchlauf auf 0 zurückgesetzt."""
        ...
    def target(self) -> _int:
        """Anzahl der Siege in Folge, die zum Abschluss des Auftrags nötig sind."""
        ...
    def token(self) -> _str:
        """Der zu übertragende Zugangscode: eine nicht leere Zeichenfolge, sobald streak() den Wert von target() erreicht, andernfalls eine leere Zeichenfolge."""
        ...
```

## `Battery`

```python
class Battery:
    """self.battery (Fahrzeuge)"""
    def level(self) -> _float:
        """Ladestand als Anteil, **0-1**."""
        ...
    def wh(self) -> _float:
        """Aktuelle Ladung in Wh (über alle Batterien hinweg)."""
        ...
    def capacity(self) -> _float:
        """Maximale Kapazität in Wh."""
        ...
    def holders(self) -> _list[Holder]:
        """Liste aller derzeit am Fahrzeug montierten Batteriehalter. Beim Rover ist sie leer (versiegelte Batterie)."""
        ...
```

## `BatteryComponent`

```python
class BatteryComponent(Component):
    """Batterie: Energiespeicher der Basisstation. Er lädt sich von selbst, wenn mehr Strom erzeugt als verbraucht wird, und entlädt sich, wenn das Netz zu wenig Strom liefert. Ist er leer, schalten sich Maschinen ab und ihre Skripte pausieren."""
    name: _str
    outpost: OutpostRef
    def get_level(self) -> _float:
        """Aktuell gespeicherte Energie in Wattstunden (**Wh**). Der Wert sinkt, wenn der Verbrauch die Erzeugung übersteigt, steigt bei einem Erzeugungsüberschuss und bleibt bei einem Gleichgewicht konstant. Nähert er sich **0**, droht dem Stromnetz ein Spannungsabfall."""
        ...
    def get_capacity(self) -> _float:
        """Gesamtkapazität der Batterie in Wattstunden (**Wh**). Der Wert lässt sich abfragen, statt ihn fest im Skript zu hinterlegen, damit künftige Verbesserungen Skripte nicht außer Funktion setzen. Verwende ihn zusammen mit `get_level()`, um den Ladestand in Prozent zu berechnen."""
        ...
```

## `Bounds`

```python
class Bounds:
    """planet.get_bounds()"""
    min_x: _float
    max_x: _float
    min_y: _float
    max_y: _float
```

## `BroadcastInfo`

```python
class BroadcastInfo:
    """comms.latest_info(channel); comms.wait_broadcast(channel).broadcast nach status == \"ok\""""
    value: JsonValue
    sender: _str | None
    age_seconds: _float | None
```

## `BulkLiquidReservoir`

```python
class BulkLiquidReservoir(Component):
    """Großer Flüssigkeitstank: Ein großer passiver Tank für 1.000 t einer einzigen Flüssigkeit. Wie bei einem Flüssigkeitstank legt die erste hineingeleitete Flüssigkeit fest, welchen Flüssigkeitstyp er annimmt. Einen anderen Flüssigkeitstyp nimmt er erst an, wenn er vollständig leergelaufen ist."""
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

## `CacheInfo`

```python
class CacheInfo:
    """`functools.lru_cache(fn).cache_info()` · `functools.cache(fn).cache_info()`"""
    hits: _int
    misses: _int
    maxsize: _int
    currsize: _int
```

## `ChamberSample`

```python
class ChamberSample:
    """bio_luminizer.chamber"""
    fragment_id: Literal["gw_caudal_fin", "vc_mandible_claw", "oc_tentacle_arm", "bw_foreclaw", "vd_nematocyst", "mh_spore_pod", "hs_wing_membrane", "ms_leg_tarsus", "hc_shell_whorl", "ma_cuticle_molt", "gm_folded_wing", "fs_arm_segment", "sd_wing_membrane", "ce_swimmeret_lobe", "st_plastron_shard", "vm_wing_sheet"]
    name: _str
    glow: _list[_int]
```

## `ChargingStation`

```python
class ChargingStation(Component):
    """Fahrzeugladestation: Lädt Fahrzeuge aus dem Stromnetz: Mk I bietet **1 Ladeplatz / 30 W**, Mk II **2 Ladeplätze / 120 W** und Mk III **4 Ladeplätze / 240 W**. Freie Ladeplätze bündeln ihre Leistung für ein Fahrzeug; mehrere Fahrzeuge teilen sich die verfügbare Leistung. Ein Skript reiht Ladevorgänge ein oder schickt eine Rettungsdrohne los."""
    name: _str
    outpost: OutpostRef
    def get_docked(self) -> _list[_str]:
        """Liste der IDs aller Fahrzeuge, die innerhalb des lokalen Servicebereichs der Station samt einem Rand von **~2 m** oder innerhalb des gemeinsamen Servicebereichs des zugehörigen Außenpostens abgestellt sind. Jedes dort abgestellte Fahrzeug ist nur an einer Station angedockt: an der Station, die es mit `dock()` selbst gewählt hat, andernfalls an der infrage kommenden Station, deren Position bzw. Außenpostenmitte am nächsten liegt. Bei gleichem Abstand gewinnt die Station, deren ID alphabetisch zuerst kommt. Die Liste enthält IDs, keine Fahrzeuge. Mit `get_component(id)` kannst du für jede ID den Batteriestand, die Fracht oder andere Daten abrufen. Eine leere Liste bedeutet, dass keine Fahrzeuge angedockt sind. Rufe die Methode in jedem Durchlauf auf: Die Liste kann sich zwischen Ticks ändern, wenn Fahrzeuge ankommen oder wegfahren."""
        ...
    def charge(self, vehicle_id: _str, target_level: _float = ...) -> ActionResult[Literal["charging", "queued", "target_reached", "not_docked", "station_offline", "invalid"]]:
        """Reihe einen angedockten Rover oder Pionier zum Laden ein, bis seine Batterie `target_level` erreicht (größer als **0** und höchstens **1**; Standardwert **1.0**). Die Station entscheidet, ob der Ladevorgang sofort beginnt oder hinter einem anderen Fahrzeug warten muss: Mk I lädt ein Fahrzeug gleichzeitig, Mk II zwei und Mk III vier. Je weniger Fahrzeuge gleichzeitig laden, desto schneller lädt jedes einzelne, weil freie Ladeplätze ihre Leistung beisteuern. Beispiel: `self.charge(\"pioneer_1\", 0.8)` bedeutet „Lade dieses Fahrzeug auf 80 %“. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def stop(self, vehicle_id: _str) -> ActionResult[Literal["ok", "not_found", "invalid"]]:
        """Entferne ein Fahrzeug aus der Ladewarteschlange dieser Station. Das Fahrzeug wird dadurch weder bewegt noch ändert sich sein aktueller Batteriestand. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def clear_queue(self) -> CountResult[Literal["ok", "no_op"]]:
        """Entferne alle eingereihten Ladevorgänge dieser Station. Einsätze der Rettungsdrohne sind davon getrennt und werden dadurch nicht abgebrochen. Fester Ergebnisvertrag: `CountResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.count`."""
        ...
    def get_active(self) -> _list[_str]:
        """Liste der Fahrzeug-IDs, die gerade aktive Ladeplätze belegen. Mk I gibt höchstens eine ID zurück, Mk II zwei und Mk III vier. Diese Fahrzeuge teilen sich in diesem Tick die verfügbare Leistung der Station."""
        ...
    def get_queue(self) -> _list[_str]:
        """Liste der Fahrzeug-IDs in der Reihenfolge der Ladewarteschlange. Die ersten `get_bay_count()` Einträge können gerade geladen werden, sofern die Fahrzeuge noch angedockt sind und ihren Zielwert noch nicht erreicht haben."""
        ...
    def status(self, vehicle_id: _str) -> _dict[_str, JsonValue]:
        """Detaillierter Status eines Fahrzeugs: ein dict mit `state` (`\"charging\"`, `\"queued\"`, `\"docked\"`, `\"target_reached\"`, `\"not_docked\"`, `\"station_offline\"` oder `\"missing\"`), `target_level`, `battery_wh`, `capacity_wh`, `rate_w` (die Leistung in Watt, die dieses Fahrzeug tatsächlich erhält; sie steigt, wenn sich weniger Fahrzeuge die Ladeplätze teilen), `bay_index` und `queue_index`. Nutze diese Daten für Übersichten oder zur Verwaltung der Warteschlange."""
        ...
    def tier(self) -> _int:
        """Dauerhaft installierte Ausbaustufe der Ladestation als Ganzzahl (**1-3**). Mk II erhöht die Anzahl der Ladeplätze und die Leistung je Ladeplatz; Mk III erhöht die Anzahl der Ladeplätze erneut."""
        ...
    def get_bay_count(self) -> _int:
        """Anzahl der Ladeplätze, an denen Fahrzeuge gleichzeitig geladen werden können. Mk I hat **1**, Mk II **2** und Mk III **4**."""
        ...
    def get_bay_rate(self) -> _float:
        """Leistung eines einzelnen Ladeplatzes (**30 W** bei Mk I, **60 W** bei Mk II/III). Lädt nur ein Fahrzeug, erhält es auch die Leistung aller freien Ladeplätze. Seine tatsächliche Ladeleistung beträgt daher bis zu `get_bay_count() × get_bay_rate()`. Mit `get_charge_rate(id)` erfährst du, welche Leistung ein bestimmtes Fahrzeug tatsächlich erhält. Sobald ein Fahrzeug lädt, bezieht die Station insgesamt `get_bay_count() × get_bay_rate()` aus dem Stromnetz; ist eine Rettungsdrohne unterwegs, kommt deren Verbrauch hinzu."""
        ...
    def get_charge_rate(self, vehicle_id: _str) -> _float:
        """Leistung in Watt, mit der das angegebene Fahrzeug gerade tatsächlich geladen wird. Die Gesamtleistung der Station (`get_bay_count() × get_bay_rate()`) wird gleichmäßig auf alle aktiv ladenden Fahrzeuge verteilt. Ein einzelnes Fahrzeug erhält die gesamte Leistung (Mk III: **240 W**); je mehr Fahrzeuge laden, desto kleiner ist der Anteil jedes Fahrzeugs. Gibt **0** zurück, wenn das Fahrzeug keinen aktiven Ladeplatz belegt."""
        ...
    def dispatch_rescue(self, vehicle_name: _str, target_level: _float = ...) -> ActionResult[Literal["ok", "already_dispatched", "station_offline", "not_found", "invalid"]]:
        """Schicke eine Servicedrohne zu einem Rover oder Pionier. Gib dazu seinen Anzeigenamen oder seine ID an. `target_level` ist ein Anteil der Batteriekapazität, der größer als **0** und höchstens **1** ist; der Standardwert beträgt **1.0**. Beim Aussenden wird das Zielfahrzeug angehalten, damit die Drohne es erreichen kann. Die Station muss beim Start mit Strom versorgt sein; die Drohne kann ihren Einsatz auch dann abschließen, wenn später der Strom ausfällt. Erreicht das Ziel zuerst eine mit Strom versorgte Ladestation, wird der verbleibende Ladeauftrag in deren Warteschlange eingereiht. Es kann immer nur ein Rettungseinsatz gleichzeitig laufen. Mit `cancel_rescue()` rufst du die Drohne zurück. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def cancel_rescue(self) -> ActionResult[Literal["ok", "not_found"]]:
        """Rufe die aktive Servicedrohne dieser Station zurück. War die Drohne auf dem Hinflug oder beim langsamen Laden, kann das Zielfahrzeug sofort wieder fahren und behält die bereits erhaltene Ladung, während die Drohne zur Station zurückkehrt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def is_rescuing(self) -> _bool:
        """`True`, solange eine Rettungsdrohne im Einsatz ist (auf dem Hinflug, beim Ziel oder auf dem Rückflug). Auch eine zurückgerufene Drohne zählt bis zu ihrer Ankunft an der Station als im Einsatz. Das Zielfahrzeug wird jedoch freigegeben, sobald `cancel_rescue()` erfolgreich war. Prüfe dies vor `dispatch_rescue()`, um die Ablehnung `\"already_dispatched\"` zu vermeiden: `if not self.is_rescuing(): self.dispatch_rescue(name)`. Es kann immer nur eine Drohne im Einsatz sein; weitere Rettungseinsätze musst du selbst in eine Warteschlange einreihen."""
        ...
    def get_rescue_target(self) -> _str:
        """Anzeigename des Fahrzeugs, dem gerade geholfen wird, oder eine leere Zeichenfolge, wenn die Drohne nicht im Einsatz ist. Nutze ihn für Übersichten („Rover 1 wird gerettet“) oder um zu entscheiden, ob du wartest oder ein anderes Fahrzeug als Unterstützung schickst."""
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

## `Clock`

```python
class Clock(Component):
    """Uhr: Die Uhr des Schiffs. Sie erfasst die Tageszeit, die Anzahl der Tage und den Sonnenstand – alles, was ein Skript für Abläufe nach Tageszeit und die Ausrichtung auf die Sonne braucht."""
    name: _str
    def get_time(self) -> _list[_int]:
        """Aktuelle Uhrzeit als **Liste mit 3 Elementen** `[hours, minutes, seconds]` im 24-Stunden-Format. Greife mit `t[0]`, `t[1]` und `t[2]` auf die Elemente zu. Nutze die Uhrzeit für tageszeitabhängige Abläufe oder um auf bestimmte Stunden zu warten."""
        ...
    def get_day(self) -> _int:
        """Aktuelle Tagesnummer. Sie beginnt bei **1** und steigt, wenn die Uhr der Spielwelt Mitternacht überschreitet. Nutze sie für tägliche Budgets, etwa um Zähler zu Tagesbeginn zurückzusetzen, oder um Tageswechsel bei Maschinen wie dem Wärmegenerator zu erkennen, dessen Zustand sich täglich ändert."""
        ...
    def get_time_of_day(self) -> Literal["dawn", "day", "dusk", "night"]:
        """Aktuelle Tageslichtphase als Zeichenfolge: `\"dawn\"`, `\"day\"`, `\"dusk\"` oder `\"night\"`. Diese Simulationsphase steuert die Solar- und Tag-Nacht-Logik. In der Kopfzeile kann `\"day\"` zur Atmosphäre zusätzlich als Morgen, Nachmittag oder Abend bezeichnet werden."""
        ...
    def get_elevation(self) -> _float:
        """Höhe der Sonne über dem Horizont (**0-90** Grad). Nachts beträgt sie **0**, steigt bis zum Sonnenhöchststand auf **90** (am Äquator) und sinkt bis zur Abenddämmerung wieder auf **0**. Solarmodule liefern die höchste Leistung, wenn ihre Neigung zusammen mit der aktuellen Sonnenhöhe 90 Grad ergibt."""
        ...
    def tick(self) -> _int:
        """Deterministischer Simulationstick seit Beginn des Spielstands. Bei normaler Geschwindigkeit erhält die Simulation mit jedem Tick ein neues Schrittkontingent für Skripte (**10 Ticks/Sek.**; ein Tick entspricht also **0,1** Simulationssekunden). Nutze die Differenz zwischen Ticks, um die Laufzeit von Skripten zu messen, statt Millisekunden der Echtzeituhr zu verwenden."""
        ...
    def elapsed_seconds(self) -> _float:
        """Vergangene Simulationssekunden seit Beginn des Spielstands. Das ist dieselbe Zeitbasis, nach der `sleep(seconds)` wartet, nicht die Echtzeituhr des Browsers."""
        ...
    def elapsed_game_hours(self) -> _float:
        """Vergangene Stunden auf der Spielweltuhr seit Beginn des Spielstands. Nützlich für Berechnungen von Raten und für Protokolle, die dem verkürzten Tag-Nacht-Zyklus statt realen Sekunden folgen sollen."""
        ...
    def real_seconds_per_hour(self) -> _float:
        """Anzahl realer Sekunden pro Stunde auf der Spielweltuhr. Der Tageszyklus fasst **24** Spielweltstunden in einer festen Echtzeitspanne zusammen. Daher wartet `sleep(clock.real_seconds_per_hour())` genau eine Spielweltstunde; mit **24** multipliziert ergibt sich ein ganzer Tag. So können Skripte Wartezeiten in Spielweltzeit angeben, ohne die Umrechnung fest einzubauen."""
        ...
```

## `Commander`

```python
class Commander(Component):
    """Kommandant: Lies mit `get_component(\"me\")` oder `get_component(\"commander\")` den Namen des Spielers und seinen aktuellen Creditstand aus. Skripte können keinen der beiden Werte ändern."""
    name: _str
    def get_name(self) -> _str:
        """Dein Kommandantenname als Zeichenfolge. Er wird bei der anfänglichen Charaktererstellung festgelegt oder erhält einen Standardwert. Nutze ihn für persönliche Meldungen in Übersichten."""
        ...
    def get_credits(self) -> _int:
        """Aktueller Creditstand. Er ändert sich bei Aufrufen von `shop.buy()` / `shop.sell()`, Auszahlungen der Biobörse, erfolgreichen Vertragsübertragungen und abgeschlossenen Aufträgen. Prüfe ihn vor teuren Aufrufen von `shop.buy()`."""
        ...
```

## `Comms`

```python
class Comms(Component):
    """Signalbus: Koordiniert Skripte über gemeinsam genutzte, JSON-kompatible Werte. Nach der Freischaltung durch Forschung greifst du mit `get_component(\"comms\")` auf den Signalbus zu. Nutze `send()` und `receive()` für Aufgaben, die nur einmal bearbeitet werden sollen, und `broadcast()` und `latest()` für den neuesten gemeinsam genutzten Wert."""
    name: _str
    def send(self, channel: _str, value: JsonValue) -> SendResult[Literal["ok", "invalid_channel", "channel_limit", "queue_full", "id_exhausted", "invalid_value"]]:
        """Füge einer benannten Kanalwarteschlange einen JSON-kompatiblen Wert hinzu. Bewahre die Sendebestätigung auf, um genau diesen Auftrag später zu identifizieren oder abzubrechen, auch wenn mehrere Aufträge denselben Wert enthalten. Kanal-IDs dürfen Buchstaben, Ziffern, `_`, `.`, `:` und `-` enthalten. Nutze Warteschlangen für Aufgaben, die nur einmal bearbeitet werden sollen. Fester Ergebnisvertrag: `SendResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.message_id`."""
        ...
    def receive(self, channel: _str, message_id: _int | None = ...) -> ReceiveResult[Literal["ok", "empty", "not_found", "invalid_channel"]]:
        """Entnimm eine Nachricht aus der Warteschlange. Lasse `message_id` weg oder übergib `None`, um die älteste Nachricht zu entnehmen. Mit einer Nachrichten-ID entnimmst du genau den zugehörigen Auftrag. Auswahl und Entfernen geschehen gemeinsam, sodass nur einer von mehreren konkurrierenden Empfängern die Nachricht entnehmen kann. Die übrigen Nachrichten behalten ihre Reihenfolge; Broadcasts bleiben erhalten. Mit `pending()` kannst du Aufgaben vor dem Empfang nach Priorität, Standort oder Fähigkeit auswählen. Fester Ergebnisvertrag: `ReceiveResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.packet`."""
        ...
    def wait(self, channel: _str) -> ReceiveResult[Literal["ok", "invalid_channel"]]:
        """Warte auf die älteste Nachricht in der Warteschlange und entnimm sie. Ist die Warteschlange leer, pausiert nur dieses Skript, bis eine Aufgabe verfügbar ist; das Spiel und andere Skripte laufen weiter. Bereits eingereihte Nachrichten werden sofort entnommen. Broadcasts beenden das Warten nicht. Wenn du das Skript pausierst, bleibt der Wartezustand erhalten. Wenn du es stoppst, wird das Warten beendet, ohne eine Nachricht zu verbrauchen. Fester Ergebnisvertrag: `ReceiveResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.packet`."""
        ...
    def wait_any(self, channels: _list[_str]) -> WaitAnyResult[Literal["ok", "invalid_channel"]]:
        """Warte auf eine Nachricht aus einem der aufgeführten Kanäle und entnimm sie. Die zuerst aufgeführten Kanäle haben bei der Auswahl Vorrang; innerhalb jedes Kanals wird die älteste Nachricht zuerst entnommen. Sind alle Warteschlangen leer, wartet nur dieses Skript. Broadcasts beenden das Warten nicht. Die Kanalliste wird beim Aufruf kopiert; mehrfach aufgeführte Namen zählen nur an ihrer ersten Position. Pausieren erhält den Wartezustand, Stoppen beendet ihn, ohne eine Aufgabe zu entnehmen. Fester Ergebnisvertrag: `WaitAnyResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.channel` und `.packet`."""
        ...
    def wait_broadcast(self, channel: _str) -> WaitBroadcastResult[Literal["ok", "invalid_channel"]]:
        """Warte auf den nächsten Broadcast auf einem Kanal. Jedes Skript, das bereits wartet, erhält diese Veröffentlichung, auch wenn sie einen wiederholten Wert oder None enthält. Vorhandene Broadcasts beenden ein neu begonnenes Warten nicht. Nur dieses Skript pausiert; Nachrichten in Warteschlangen bleiben unangetastet. Die erste Veröffentlichung bleibt erhalten, auch wenn danach ein weiterer Broadcast folgt oder der Kanal geleert wird. Pausieren erhält das Signal für die Fortsetzung; Stoppen beendet das Warten. Fester Ergebnisvertrag: `WaitBroadcastResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.broadcast`."""
        ...
    def pending(self, channel: _str) -> _list[CommsMessage]:
        """Sieh dir alle wartenden Nachrichten eines Kanals in Empfangsreihenfolge an, ohne sie zu entnehmen. Nutze die Momentaufnahme, um anstehende Aufgaben auf einer Karte im Kontrollraum anzuzeigen oder alle offenen Aufträge zu zählen. Jede Nachricht und ihr enthaltener Wert werden kopiert. Änderungen an der zurückgegebenen Liste oder ihren Nachrichten ändern den Signalbus nicht. Broadcasts und bereits empfangene Nachrichten sind nicht enthalten. Rufe die Methode erneut auf, um die Momentaufnahme zu aktualisieren."""
        ...
    def cancel(self, channel: _str, message_id: _int) -> ActionResult[Literal["ok", "not_found", "invalid_channel"]]:
        """Brich eine wartende Nachricht über `.message_id` aus ihrer Sendebestätigung oder über ihre `.id` aus `pending(channel)` ab. So kannst du einen überholten Auftrag entfernen oder eine Abbrechen-Schaltfläche für eine Aufgabenübersicht im Kontrollraum hinzufügen. Andere Nachrichten behalten ihre IDs, Werte und Empfangsreihenfolge, auch wenn sie erst nach der Momentaufnahme gesendet wurden. Der letzte Broadcast bleibt erhalten. Das Abbrechen entfernt nur wartende Aufgaben; es kann keinen Empfänger stoppen, der die Nachricht bereits entnommen hat. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def update(self, channel: _str, message_id: _int, value: JsonValue) -> ActionResult[Literal["ok", "not_found", "invalid_channel", "invalid_value"]]:
        """Ersetze den gesamten Wert einer wartenden Nachricht. Nutze ihre Sendebestätigung oder eine ID aus `pending()`, um eine Lieferung, Priorität oder ein Ziel per Skript oder über eine Karte im Kontrollraum zu ändern. ID, Position in der Warteschlange, ursprünglicher Absender und Sendezeit bleiben unverändert. Der Wert wird in einem einzigen Vorgang ersetzt, auch wenn die Warteschlange voll ist. Bereits empfangene Nachrichten lassen sich nicht ändern. Rufe `pending()` erneut auf, um eine frühere Momentaufnahme zu aktualisieren. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def broadcast(self, channel: _str, value: JsonValue) -> ActionResult[Literal["ok", "invalid_channel", "channel_limit", "invalid_value"]]:
        """Speichere den neuesten JSON-kompatiblen Wert eines Kanals, ohne Plätze in der Warteschlange zu belegen. Wörterbücher müssen Zeichenfolgen als Schlüssel verwenden. Nutze Broadcasts für gemeinsam genutzte Statusinformationen wie Flottenmodus, Zielsektor oder aktuelle Priorität. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def latest(self, channel: _str) -> JsonValue | None:
        """Gibt den zuletzt auf einem Kanal per Broadcast veröffentlichten Wert zurück oder `None`, wenn der Kanal keinen aktuellen Wert hat. Das Lesen verbraucht den Wert nicht."""
        ...
    def latest_info(self, channel: _str) -> BroadcastInfo | None:
        """Sieh dir die letzte Broadcast-Nachricht an: wer sie gesendet hat und wie lange ihre letzte Aktualisierung zurückliegt. Nutze diese Momentaufnahme, um veraltete Meldungen von Workern zu erkennen oder ihre Aktualität auf einer Karte im Kontrollraum anzuzeigen. Das Auslesen verbraucht keine Nachrichten und verändert den Kanal nicht. Lies die Daten erneut aus, um den Wert und sein Alter zu aktualisieren."""
        ...
    def queue_size(self, channel: _str) -> _int:
        """Anzahl der Nachrichten, die in der Warteschlange des Kanals warten."""
        ...
    def channels(self) -> _list[_str]:
        """Alle Kanal-IDs, deren Kanäle derzeit Nachrichten in der Warteschlange oder einen letzten Broadcast-Wert enthalten."""
        ...
    def clear(self, channel: _str) -> CountResult[Literal["ok", "no_op", "invalid_channel"]]:
        """Entferne die Nachrichten in der Warteschlange eines Kanals und seinen letzten Broadcast. Fester Ergebnisvertrag: `CountResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.count`."""
        ...
```

## `CommsMessage`

```python
class CommsMessage:
    """Einträge in der Liste von comms.pending(channel); comms.receive(channel).packet, comms.wait(channel).packet oder comms.wait_any(channels).packet nach status == \"ok\""""
    id: _int
    sender: _str
    tick: _int
    value: JsonValue
```

## `Component`

```python
class Component:
    """get_component / self"""
    id: _str
    type_id: _str
```

## `Console`

```python
class Console(Component):
    """Konsole: Schreibt strukturierte Skriptausgaben in dieselbe Konsole wie `print()`. Greife mit `get_component(\"console\")` darauf zu; dafür ist keine Forschung nötig. Nachrichten können eine Dringlichkeitsstufe, einen benannten Kanal, eine Farbe und einen Zeitstempel haben."""
    name: _str
    def print(self, message: object, level: _str = ..., channel: _str = ..., color: _str = ..., timestamp: _bool = ...) -> ActionResult[Literal["ok"]]:
        """Gib eine Zeile aus und steuere alle Einstellungen selbst. `level` ist `info`, `warn`, `error` oder `debug` (diese Werte speisen die Filter WARNINGS und ERRORS). Jede andere nicht leere Zeichenfolge erzeugt eine eigene Stufe, die als farbiges Abzeichen angezeigt wird. Ein leerer Wert verhält sich wie `info`. `channel` leitet die Zeile an einen benannten Tab weiter (leer = Hauptausgabe). `color` ist ein Farbwert des Designs (`\"warning\"`, `\"success\"`, `\"accent\"`), der sich mit dem Design ändert, oder eine beliebige CSS-Farbe: Hex (`\"#aabbcc\"`), `\"rgb(255,100,0)\"`, `\"hsl(30,100%,50%)\"` oder ein Name wie `\"orange\"`. Ist `timestamp` wahr, wird die Tageszeit im Spiel vorangestellt. Beispiel: `get_component(\"console\").print(\"Overheat\", \"alert\", \"alarms\", \"warning\", True)`. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def info(self, message: object, channel: _str = ..., color: _str = ..., timestamp: _bool = ...) -> ActionResult[Literal["ok"]]:
        """Gib eine Infozeile aus (die Standardstufe). Die optionalen Parameter für Kanal, Farbe und Zeitstempel funktionieren wie bei `print`. Entspricht `print(message)`. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def warn(self, message: object, channel: _str = ..., color: _str = ..., timestamp: _bool = ...) -> ActionResult[Literal["ok"]]:
        """Gib eine Warnungszeile aus, die im Filter WARNINGS der Konsole erscheint. Die optionalen Parameter für Kanal, Farbe und Zeitstempel steuern Ausgabeort und Darstellung. Für ein auffälliges Pop-up verwende stattdessen die globale Funktion `notify(text, \"warn\")`. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def error(self, message: object, channel: _str = ..., color: _str = ..., timestamp: _bool = ...) -> ActionResult[Literal["ok"]]:
        """Gib eine Fehlerzeile aus, die im Filter ERRORS der Konsole erscheint. Die optionalen Parameter für Kanal, Farbe und Zeitstempel steuern Ausgabeort und Darstellung. Dies ist deine eigene Nachricht mit Fehlerstufe, keine unbehandelte Ausnahme. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def debug(self, message: object, channel: _str = ..., color: _str = ..., timestamp: _bool = ...) -> ActionResult[Literal["ok"]]:
        """Gib eine Debugzeile mit niedriger Priorität aus. Sie bleibt in der Ansicht ALL verborgen, bis der Spieler die Debugausgabe aktiviert. Die optionalen Parameter für Kanal, Farbe und Zeitstempel steuern Ausgabeort und Darstellung. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def now(self) -> _str:
        """Gibt die aktuelle Tageszeit im Spiel als Zeichenfolge im Format `\"HH:MM:SS\"` zurück. Damit kannst du Zeilen eigene Präfixe voranstellen und deren Formatierung selbst steuern."""
        ...
    def clear(self, channel: _str = ...) -> ActionResult[Literal["ok"]]:
        """Lösche die Ausgaben dieses Skripts. Mit dem Argument `channel` werden nur die Zeilen dieses Skripts im angegebenen Kanal gelöscht; ohne Argument alle Ausgaben dieses Skripts. Ausgaben anderer Skripte und Systemmeldungen bleiben erhalten. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
```

## `Construction`

```python
class Construction:
    """.pending_constructions() / .active_constructions() / .paused_constructions()"""
    id: _str
    kind: Literal["pipe", "power_line", "gas_bridge", "liquid_bridge", "power_bridge", "deconstruct", "outpost", "thermal_cap", "water_pump", "oil_pump", "exotic_gas_cap", "exotic_spring_tap", "mining_drill", "mining_drill_industrial", "mining_drill_heavy"]
    medium: Literal["gas", "liquid", "power"] | None
    position: Position
    progress: _float
    required_item: _str | None
    required_count: _int
```

## `ConstructionBlueprint`

```python
class ConstructionBlueprint(Component):
    """Bauplan: Verwaltet geplante Bau- und Abrissarbeiten. Planungsmodus und Skripte nutzen dieselbe Warteschlange. Skripte können Bauwerke, Rohre, Stromleitungen und Brücken platzieren oder bestehende Bauwerke zum Abriss markieren. Beim Planen erscheint die Markierung sofort auf der Karte, auch wenn kein Fahrzeug vor Ort ist. Ein Pionier mit Konstruktionsmodul muss trotzdem zu jedem Auftrag fahren und `self.constructor.execute(construction.id)` aufrufen, um die Arbeit auszuführen."""
    name: _str
    def plan_structure(self, kind: _str, x: _float, y: _float, rotation: _int = ...) -> BlueprintPlanResult[Literal["ok", "locked", "invalid_kind", "invalid_rotation", "out_of_bounds", "wrong_target", "unsurveyed_target", "too_hard", "target_claimed", "occupied", "clearance", "blocked"]]:
        """Erstelle anhand von Skriptkoordinaten eine Bauvorschau für ein einzelnes Bauwerk. Unterstützte Arten sind `\"outpost\"`, `\"thermal_cap\"`, `\"water_pump\"`, `\"oil_pump\"`, `\"exotic_gas_cap\"`, `\"exotic_spring_tap\"`, `\"mining_drill\"`, `\"mining_drill_industrial\"` und `\"mining_drill_heavy\"`. Für Bohrerarten ist jeweils das passende Bausatzrezept aus Erdaufträgen nötig. Koordinaten rasten am Kartenraster ein. Förderanlagen rasten auf dem exakt passenden, erkundeten Vorkommen ein; bei Außenposten wird der eingerastete Ankerpunkt ihrer Grundfläche verwendet. Die optionale Drehung im Uhrzeigersinn beträgt `0`, `90`, `180` oder `270`. Die Bauvorschau kommt sofort in die gemeinsame Warteschlange; gebaut wird sie später von einem Pionier. Fester Ergebnisvertrag: `BlueprintPlanResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.blueprint_ids`."""
        ...
    def plan_pipe(self, medium: _str, x1: _float, y1: _float, x2: _float, y2: _float) -> BlueprintPlanResult[Literal["ok", "locked", "invalid_medium", "out_of_bounds", "invalid_route", "blocked", "already_exists"]]:
        """Erstelle Rohrbauaufträge anhand von Skriptkoordinaten. Dafür muss das Konstruktionsmodul erforscht sein. `medium` ist `\"gas\"`, `\"liquid\"` oder eine registrierte Flüssigkeits-ID wie `\"steam\"`, `\"water\"` oder `\"oil\"`. Koordinaten rasten auf Bahnen durch die Kachelmitten ein. Ein Bauwerk im Gelände verwendet seine Standortkoordinaten. Bei einer Maschine im Außenposten dient ihr Außenposten als Anschlusspunkt: Lege die Leitung daher zu einem Punkt auf der Grundfläche von `building.outpost`, etwa `[building.outpost.x, building.outpost.y]`, und nicht zum Fahrzeugandockpunkt in `building.position`. Passende vorhandene Abschnitte werden automatisch wiederverwendet. Fester Ergebnisvertrag: `BlueprintPlanResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.blueprint_ids`."""
        ...
    def plan_power_line(self, x1: _float, y1: _float, x2: _float, y2: _float) -> BlueprintPlanResult[Literal["ok", "locked", "out_of_bounds", "invalid_route", "blocked", "already_exists"]]:
        """Erstelle Stromleitungsbauaufträge anhand von Skriptkoordinaten. Dafür muss das Konstruktionsmodul erforscht sein. Koordinaten rasten auf Bahnen durch die Kachelmitten ein. Bei Wegen, die nicht entlang einer Achse verlaufen, wird die gültige L-förmige Biegung mit dem geringsten Neubau gewählt. Ein Bauwerk im Gelände verwendet seine Standortkoordinaten. Bei einer Maschine im Außenposten dient ihr Außenposten als Anschlusspunkt: Lege die Leitung daher zu einem Punkt auf der Grundfläche von `building.outpost`, etwa `[building.outpost.x, building.outpost.y]`, und nicht zum Fahrzeugandockpunkt in `building.position`. Passende vorhandene Abschnitte werden automatisch wiederverwendet. Fester Ergebnisvertrag: `BlueprintPlanResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.blueprint_ids`."""
        ...
    def plan_bridge(self, medium: _str, x: _float, y: _float, axis: _str) -> BlueprintPlanResult[Literal["ok", "locked", "invalid_medium", "invalid_axis", "out_of_bounds", "blocked", "already_exists"]]:
        """Erstelle anhand von Skriptkoordinaten einen Bauauftrag für eine Versorgungsbrücke. Dafür muss das Konstruktionsmodul erforscht sein. `medium` ist `\"gas\"`, `\"liquid\"`, `\"power\"` oder eine registrierte Flüssigkeits-ID. `x`/`y` geben die mittlere Kachel der Brücke an, `axis` ist `\"horizontal\"` oder `\"vertical\"`. Fester Ergebnisvertrag: `BlueprintPlanResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.blueprint_ids`."""
        ...
    def mark_deconstruct(self, x: _float, y: _float, layer: _str = ..., target_id: _str = ...) -> BlueprintPlanResult[Literal["ok", "locked", "nothing_here", "already_queued", "ambiguous_target", "out_of_bounds", "invalid_layer", "blocked"]]:
        """Markiere gebaute Infrastruktur oder ein gewöhnliches Kartengebäude an den angegebenen Koordinaten zum Abriss. Dafür muss das Konstruktionsmodul erforscht sein. Basis und Außenposten sind geschützt. Wenn sich mehrere unabhängige Kartenebenen überlagern, wähle die Ebene `\"building\"`, `\"gas\"`, `\"liquid\"` oder `\"power\"`; der Standardwert `\"auto\"` erfordert ein eindeutiges Ziel. An einer Kreuzung innerhalb derselben Ebene kannst du optional die genaue Ziel-ID angeben. Ein Pionier führt den Auftrag weiterhin mit `self.constructor.execute(id)` an der gemeldeten `position` aus. Fester Ergebnisvertrag: `BlueprintPlanResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.blueprint_ids`."""
        ...
    def cancel(self, blueprint_id: _str) -> ActionResult[Literal["ok", "not_found", "worker_not_present", "no_cargo_space", "construction_dependency"]]:
        """Storniere einen wartenden, aktiven oder pausierten Bauplan anhand seiner ID. Aufträge, für die noch kein Material bezahlt wurde, werden sofort storniert. Bei einem bezahlten Auftrag bleibt das Material am Bauort: Stelle dort einen Pionier ab, um es in seinen Frachtraum zurückzuholen. Scheitert die Rückholung, bleiben Auftrag und Material erhalten. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def pending_constructions(self) -> _list[Construction]:
        """Gibt Baupläne, die auf einen Arbeiter warten, als `list[Construction]` zurück. Gezeichnete Rohr- und Stromleitungswege sowie zum Abriss markierte Ziele werden in einzelne Aufträge aufgeteilt, meist in der Reihenfolge ihrer Platzierung. Übergib jede `c.id` an `self.constructor.execute(c.id)`, um den jeweiligen Auftrag auszuführen. Lies `c.required_item` und `c.required_count`, damit du vorher genau die benötigte Fracht lädst; leite das Material niemals aus `c.kind` ab. Filtere nach `c.kind`, um einen Pionier auf bestimmte Aufgaben zu spezialisieren, und unterscheide dann mit `c.medium` zwischen Versorgungsaufträgen für `\"gas\"`, `\"liquid\"` und `\"power\"`. Einzelne Bauwerke haben `c.medium == None`; die vollständige Artenliste findest du unter `Construction.kind`."""
        ...
    def active_constructions(self) -> _list[Construction]:
        """Gibt Baupläne zurück, an denen gerade gebaut wird (ein Pionier arbeitet daran). Für Überwachungsskripte kannst du an `c.progress` ablesen, wie weit die Arbeit fortgeschritten ist."""
        ...
    def paused_constructions(self) -> _list[Construction]:
        """Gibt begonnene und dann unterbrochene Baupläne zurück (weil der Arbeiter zerstört wurde, ihm der Treibstoff ausging oder das Skript stoppte). Jeder Pionier kann die Arbeit fortsetzen, indem er zu `c.position` fährt und `self.constructor.execute(c.id)` aufruft."""
        ...
```

## `CoreDevice`

```python
class CoreDevice:
    """.device"""
    def submit(self, index: _int, bytes: _list[_int]) -> ActionResult[Literal["locked", "rejected"]]:
        """Übermittle einen wiederhergestellten Kern für den ganzzahligen Steckplatz `index` (0-9). Falsche Container- oder Elementtypen lösen `TypeError` aus. Ein nicht ganzzahliger oder außerhalb des Bereichs liegender Index, eine falsche Listenlänge oder ein Zahlenwert außerhalb von **0-255** löst `ValueError` aus. Eine abgelehnte Übermittlung sperrt den Steckplatz nicht. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def recovered(self) -> _int:
        """Wie viele der 10 Kerne im aktuellen Skriptlauf gesichert sind. Ein neuer Lauf beginnt bei 0."""
        ...
    def target(self) -> _int:
        """Anzahl der Kerne, die du zum Abschluss des Auftrags wiederherstellen musst: 10."""
        ...
    def token(self) -> _str:
        """Der zu übermittelnde Zugangscode: eine nicht leere Zeichenfolge, sobald recovered() den Wert von target() erreicht, andernfalls eine leere Zeichenfolge."""
        ...
```

## `CropAutomator`

```python
class CropAutomator(Component):
    """Anbauautomat: Stellt Ernte-, Pflanz- und Behandlungsaufgaben für bis zu 24 weitere Zellen in einem zentrierten 5×5-Arbeitsbereich in die Warteschlange und führt sie dann nacheinander mit einer kurzen Pause dazwischen aus. Skripte finden ihn über `outpost.harvesting_machines()`."""
    name: _str
    def harvest(self, sector: _str) -> JobReceipt[Literal["queued", "queue_full", "not_placed", "out_of_range"]]:
        """Reiche einen Ernteauftrag für einen Sektor im Wirkungsbereich ein. Das Einreichen erfolgt sofort; die eigentliche Feldarbeit dauert später **0,1 Stunden**. Fehlt Platz für die Ernte, pausiert der erste Auftrag der FIFO-Warteschlange und kann nicht übersprungen werden. Stimmt das Ziel nicht überein, endet der Auftrag endgültig ohne Arbeitszeit und die Warteschlange rückt weiter. Fester Ergebnisvertrag: `JobReceipt`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.job_id` und `.queue_position`."""
        ...
    def plant(self, sector: _str, seed_id: _str) -> JobReceipt[Literal["queued", "queue_full", "not_placed", "out_of_range", "invalid_seed"]]:
        """Reiche einen Pflanzauftrag mit dem Samen einer bestimmten Art ein. Das Einreichen erfolgt sofort; der Samen muss noch nicht geladen sein. Die Aufträge werden nacheinander ausgeführt: Dieser erste Auftrag der FIFO-Warteschlange pausiert, bis der Samen vorhanden ist. Danach dauert die Arbeit **0,1 Stunden**; vor dem Abschluss wird das Ziel erneut geprüft. Fester Ergebnisvertrag: `JobReceipt`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.job_id` und `.queue_position`."""
        ...
    def apply(self, sector: _str, item_id: _str) -> JobReceipt[Literal["queued", "queue_full", "not_placed", "out_of_range", "invalid_material"]]:
        """Reiche einen Auftrag für Dünger Mk I/II/III oder Wachstumsbeschleuniger ein. Das Einreichen erfolgt sofort; das Material muss noch nicht geladen sein. Die Aufträge werden nacheinander ausgeführt: Dieser erste Auftrag der FIFO-Warteschlange pausiert, bis das Material vorhanden ist. Danach dauert die Arbeit **0,1 Stunden**; vor dem Abschluss wird das Ziel erneut geprüft. Fester Ergebnisvertrag: `JobReceipt`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.job_id` und `.queue_position`."""
        ...
    def position(self) -> _str:
        """Rastersektor, in dem dieser Automat steht. Aufträge können bis zu 24 weitere Zellen in seinem mittig angeordneten 5-mal-5-Wirkungsbereich betreffen."""
        ...
    def cell(self, sector: _str) -> Cell | None:
        """Lies einen Sektor im Wirkungsbereich dieses Automaten als Momentaufnahme vom Typ `Cell` aus. Sie enthält Pflanze, Status, Wachstum, Bedingungen und die verbleibenden Behandlungsstunden. Es lassen sich genau die Sektoren ansprechen, die auch `harvest()`, `plant()` und `apply()` akzeptieren. Gibt diese Funktion für einen Sektor `None` zurück, kann daher auch kein Auftrag ihn zum Ziel haben."""
        ...
    def cells(self) -> _list[Cell]:
        """Lies alle von diesem Automaten versorgten Sektoren als Liste von `Cell`-Momentaufnahmen aus, um den gesamten Wirkungsbereich in einem Durchgang zu prüfen. Nicht gescannter natürlicher Boden meldet den Status `\"unknown\"`."""
        ...
    def status(self) -> Literal["not_placed", "no_power", "working", "no_seed", "no_material", "output_full", "results_full", "idle"]:
        """Genauer Ausführungsstatus: `\"not_placed\"`, `\"no_power\"`, `\"working\"`, `\"no_seed\"`, `\"no_material\"`, `\"output_full\"`, `\"results_full\"` oder `\"idle\"`."""
        ...
    def current_job(self) -> CropJob | None:
        """Der aktive erste Auftrag der FIFO-Warteschlange als `CropJob`, einschließlich Aktion, Ziel, Fortschritt und Hinderungsgrund. Gibt im Leerlauf `None` zurück."""
        ...
    def get_queue(self) -> _list[CropJob]:
        """Momentaufnahme der wartenden `CropJob`-Werte in exakter FIFO-Reihenfolge (zuerst eingereiht, zuerst ausgeführt). Der aktive Auftrag wird separat von `current_job()` gemeldet."""
        ...
    def queue_count(self) -> _int:
        """Gesamtzahl der noch nicht abgeschlossenen Aufträge, einschließlich des aktiven und aller wartenden Aufträge. Höchstens **50**."""
        ...
    def result_count(self) -> _int:
        """Anzahl der abgeschlossenen Endergebnisse im Ergebniseingang. Bei **50** pausiert die Ausführung, bis Ergebnisse abgeholt werden."""
        ...
    def next_result(self) -> CropJobResult[Literal["ok", "partial", "empty", "out_of_range", "no_plant", "not_mature", "no_forage", "not_empty", "base_sector", "already_mature", "tier_conflict", "invalid_seed", "invalid_material"]]:
        """Hole das älteste Endergebnis ab. Ein leerer Ergebniseingang wird gemeldet, ohne den Maschinenstatus zu ändern. Fester Ergebnisvertrag: `CropJobResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.job_id`, `.action`, `.sector`, `.item_id`, `.collected` und `.discarded`."""
        ...
    def cancel_job(self, job_id: _int) -> ActionResult[Literal["ok", "not_found"]]:
        """Storniere einen aktiven oder wartenden Auftrag anhand seiner ID. Beim Stornieren aktiver Arbeit geht nur deren Fortschritt verloren; Eingabematerial und Zustand des Feldes bleiben unverändert. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def move_job(self, job_id: _int, position: _int) -> ActionResult[Literal["ok", "not_found", "invalid"]]:
        """Verschiebe einen noch nicht abgeschlossenen Auftrag an eine Ausführungsposition, beginnend bei eins. Dabei zählt zuerst der aktive Auftrag, danach folgen die wartenden Aufträge. Werden nur wartende Aufträge umgeordnet, bleibt der aktive Fortschritt erhalten. Wird bei einem aktiven Auftrag geändert, welcher Auftrag zuerst kommt, wird der Arbeitsarm unterbrochen: Der verdrängte Auftrag behält seine ID und seine Anforderung, verliert aber seinen Fortschritt und erzeugt kein Endergebnis. Position **1** ist die erste; `queue_count()` liefert die letzte Position. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def clear_queue(self) -> CountResult[Literal["ok", "no_op"]]:
        """Storniere den aktiven Auftrag und alle wartenden Aufträge. Abgeschlossene Ergebnisse bleiben über `next_result()` verfügbar. Fester Ergebnisvertrag: `CountResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.count`."""
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

## `CropJob`

```python
class CropJob:
    """current_job() und get_queue() des Anbauautomaten"""
    id: _int
    action: Literal["harvest", "plant", "apply"]
    sector: _str
    item_id: _str | None
    state: Literal["working", "blocked", "queued"]
    progress: _float
    blocker: Literal["not_placed", "no_power", "no_seed", "no_material", "output_full", "results_full"] | None
```

## `Dispenser`

```python
class Dispenser(Component):
    """Dosierer: Salzt die vier direkt angrenzenden Feldzellen (oben, unten, links und rechts), solange Strom und Salz vorhanden sind und die Maschine aktiviert ist. Skripte finden sie über `outpost.harvesting_machines()`."""
    name: _str
    def set_enabled(self, enabled: _bool) -> ActionResult[Literal["ok"]]:
        """Schalte das Salzen ein oder aus. Bei Stromausfall pausiert das Skript, die Einstellung bleibt aber erhalten; wenn das Maschinenskript gestoppt wird, wird sie auf `False` zurückgesetzt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def is_enabled(self) -> _bool:
        """`True`, wenn das laufende Skript das Salzen eingeschaltet hat."""
        ...
    def is_active(self) -> _bool:
        """`True`, wenn das Salzen eingeschaltet ist und Strom sowie Salz verfügbar sind."""
        ...
    def is_supplied(self) -> _bool:
        """`True`, wenn der Dosierer eingeschaltet sein soll, mit Strom versorgt wird und Salz in seinem Eingangspuffer hat. Ist er deaktiviert, ohne Strom oder leer, verlieren die erfassten Zellen den Status `salted`."""
        ...
    def status(self) -> Literal["not_placed", "disabled", "no_power", "no_salt", "active"]:
        """Genauer Betriebsstatus: `\"not_placed\"`, `\"disabled\"`, `\"no_power\"`, `\"no_salt\"` oder `\"active\"`."""
        ...
    def buffer(self) -> _float:
        """Aktueller Füllstand des eingebauten Salzpuffers als Anteil (**0–1**). Beim Dosieren in Zellen sinkt er; über `self.input` füllt er sich wieder."""
        ...
    def tier(self) -> _int:
        """Immer **1**. Der Dosierer wird als Mk I geliefert und hat kein Upgradepaket. Salzlieferanten haben keine Stufen, daher gibt jeder aufgestellte Dosierer **1** zurück."""
        ...
    def position(self) -> _str:
        """Rastersektor, in dem dieser Dosierer steht, zum Beispiel `\"E14\"`."""
        ...
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

## `EssenceLiquifier`

```python
class EssenceLiquifier(Component):
    """Essenzverflüssiger: Verflüssigt Proben einheimischer Lebensformen zur flüssigen Essenz ihres Bioms. Nimmt nur Lebensformen aus dem Biom des eigenen Außenpostens an und erzeugt die Essenz dieses Bioms."""
    name: _str
    outpost: OutpostRef
    input: InputSlot
    def essence_rate(self) -> _float:
        """Aktuelle Ausgaberate für Biom-Essenz in **t/h**. Bei 100 % Effizienz des Außenpostens verarbeitet der Essenzverflüssiger grundsätzlich **1 t/h** an Lebensformen. Dieser Wert berücksichtigt sowohl die Effizienz des Außenpostens als auch den Seltenheitsfaktor der geladenen Lebensform (gewöhnlich **×5**, ungewöhnlich **×10**, selten **×25**). Er beträgt **0**, wenn die Maschine nicht arbeiten oder ihre nächste vollständige Ausgabe nicht zwischenspeichern kann."""
        ...
    def yield_multiplier(self) -> _float:
        """Unskalierte Menge erzeugter Essenz in Tonnen pro Tonne der Lebensform im Eingabefach: **5** bei gewöhnlichen, **10** bei ungewöhnlichen und **25** bei seltenen Lebensformen. Gibt **0** zurück, wenn das Eingabefach leer ist. Bei 100 % Effizienz des Außenpostens entspricht `essence_rate()` diesem Multiplikator, solange die Maschine Strom und Nachschub hat und ihre nächste vollständige Ausgabe zwischenspeichern kann. Überfüllung kann die tatsächliche Ausgaberate senken."""
        ...
    def is_stalled(self) -> _bool:
        """`True`, wenn `stall_reason()` nicht `\"ok\"` ist: kein gültiges Biom des beherbergenden Außenpostens, kein Eingangsmaterial oder zu wenig Platz für die nächste vollständige, nach Seltenheit skalierte Ausgabe. Verwende `stall_reason()`, um die genaue Ursache zu ermitteln."""
        ...
    def stall_reason(self) -> Literal["ok", "no_biome", "no_input", "output_full", "unconnected"]:
        """Gibt als String zurück, warum der Essenzverflüssiger stillsteht; du kannst danach verzweigen: `\"no_biome\"` (die Maschine gehört zu keinem gültigen Außenposten), `\"no_input\"` (das Eingabefach ist leer; führe heimische Lebensformen des Bioms zu), `\"output_full\"` (die nächste vollständige, nach Seltenheit skalierte Ausgabe passt nicht hinein und ein konfigurierter Ausgang kann derzeit nichts abführen), `\"unconnected\"` (die nächste vollständige Ausgabe passt nicht hinein und der Essenzausgang hat keine wirksame Verbindung) oder `\"ok\"` (die Maschine läuft, ist bereit oder kann die nächste vollständige Ausgabe zwischenspeichern). Genauer als `is_stalled()`."""
        ...
    def biome(self) -> Literal["frozen", "coastal", "geothermal", "volcanic", "deep"] | None:
        """Gibt das Biom zurück, in dem sich der Außenposten der Maschine befindet: `\"frozen\"`, `\"coastal\"`, `\"geothermal\"`, `\"volcanic\"` oder `\"deep\"`. Gibt `None` zurück, wenn die Maschine keinem gültigen Außenposten angehört. Das Biom bestimmt, welche Lebensformen der Essenzverflüssiger annimmt; Gegenstände aus einem anderen Biom werden vom Eingabeanschluss zurückgewiesen."""
        ...
    frozen_essence_out: FluidPort
    coastal_essence_out: FluidPort
    geothermal_essence_out: FluidPort
    volcanic_essence_out: FluidPort
    deep_essence_out: FluidPort
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

## `ExoticDeposit`

```python
class ExoticDeposit(Site):
    """jede API, die eine Site zurückgibt, bei der `kind() == \"exotic\"` gilt (z. B. `exotic_gas_cap.deposit()`, `exotic_spring_tap.deposit()`, Sonar- oder Logbuchabfragen)"""
    def fluid(self) -> Literal["ammonia", "swamp_gas", "raw_sulfur_gas", "raw_chlorine", "brine", "raw_cryofluid", "raw_quicksilver"] | None:
        """ID der Flüssigkeit oder des Gases, die bzw. das diese Lagerstätte ausstößt, z. B. `\"ammonia\"` (häufig, direkt nutzbar) oder `\"raw_chlorine\"` (selten, muss in die Raffinerie). Bis `surveyed` gilt `None`."""
        ...
    def medium(self) -> Literal["gas", "liquid"] | None:
        """`\"gas\"` (Förderung mit einem **Sammler für exotisches Gas**) oder `\"liquid\"` (Förderung mit einer **Zapfanlage für exotische Quellen**). Bis `surveyed` gilt `None`."""
        ...
    def rarity(self) -> Literal["common", "uncommon", "rare"] | None:
        """`\"common\"` stößt eine ohne Raffinierung nutzbare Flüssigkeit oder ein solches Gas aus; `\"uncommon\"` und `\"rare\"` stoßen einen Rohstoff aus, den die Raffinerie mit Teer verarbeitet. Seltenere Lagerstätten liegen weiter auseinander und bleiben länger in der Ruhephase. Bis `surveyed` gilt `None`."""
        ...
    def survey_level(self) -> Literal["basic", "wide", "deep"] | None:
        """Höchste für diese Lagerstätte erreichte Erkundungsstufe: `\"basic\"` / `\"wide\"` / `\"deep\"` oder `None`, falls sie noch nicht erkundet wurde. Der Wert wird live ausgelesen: Eine erneute Erkundung auf einer höheren Stufe aktualisiert auch bereits vorhandene Site-Objekte. Höhere Stufen schalten weitere der folgenden Felder frei. Ein Sonarergebnis von vor der Erkundung bleibt verborgen; rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def current_phase(self) -> Literal["active", "dormant"] | None:
        """Aktuelle Phase der Lagerstätte: `\"active\"` (stößt Material aus) oder `\"dormant\"` (ruht). Wird live ausgelesen: Frage den Wert über ein gespeichertes Site-Objekt ab, um den Phasenwechseln zu folgen. Vor der Erkundung der Lagerstätte wird `None` zurückgegeben. Ein Sonarergebnis von vor der Erkundung zeigt die erkundeten Details auch danach nicht an; rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def cycle_active_minutes(self) -> _float | None:
        """Dauer der aktiven Phase in Minuten. Erfordert eine **gründliche** Erkundung; andernfalls wird `None` zurückgegeben."""
        ...
    def cycle_dormant_minutes(self) -> _float | None:
        """Dauer der Ruhephase in Minuten (seltene Lagerstätten ruhen am längsten). Erfordert eine **gründliche** Erkundung; andernfalls wird `None` zurückgegeben."""
        ...
    def next_phase_in(self) -> _float | None:
        """Spielminuten bis zum nächsten Phasenwechsel. Wird live ausgelesen: Frage den Wert in einer Steuerschleife ab, um vor Beginn der Ruhephase zu reagieren. Erfordert eine **gründliche** Erkundung; andernfalls wird `None` zurückgegeben. Ein Sonarergebnis von vor der Erkundung zeigt die erkundeten Details auch danach nicht an; rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def base_rate(self) -> _float | None:
        """Höchste Förderrate während der aktiven Phase (t/h). Erfordert eine **großflächige** Erkundung; bei einer einfachen Erkundung wird `None` zurückgegeben."""
        ...
    def current_rate(self) -> _float | None:
        """Aktuelle Förderrate (t/h: während der Ruhephase **0**). Wird live ausgelesen. Erfordert eine **großflächige** Erkundung; bei einer einfachen Erkundung wird `None` zurückgegeben. Ein Sonarergebnis von vor der Erkundung zeigt die erkundeten Details auch danach nicht an; rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def has_cap(self) -> _bool:
        """Boolescher Wert: `True`, wenn derzeit ein Sammler für exotisches Gas oder eine Zapfanlage für exotische Quellen auf dieser Lagerstätte aufgestellt ist. Wird live ausgelesen. Ein Sonarergebnis von vor der Erkundung zeigt die erkundeten Details auch danach nicht an; rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def cap_id(self) -> _str:
        """Maschinen-ID des derzeit aufgestellten Sammlers bzw. der Zapfanlage oder eine leere Zeichenfolge, wenn keines von beiden vorhanden ist. Wird live ausgelesen. Ein Sonarergebnis von vor der Erkundung zeigt die erkundeten Details auch danach nicht an; rufe nach der Erkundung ein neues Objekt ab."""
        ...
```

## `ExoticGasCap`

```python
class ExoticGasCap(Component):
    """Sammler für exotisches Gas: Fängt während der aktiven Phase Gas aus einer zyklischen exotischen Lagerstätte auf. Verbinde `self.gas_out` mit einem Abnehmer, baue eine durchgehende Gasleitung vom Gasaufsatz im Feld bis zu diesem Ziel und stelle dann mit `self.set_throttle(value)` eine Abgaberate von **0-1** ein. Ist der Puffer voll, pausiert die Sammlung, ohne dass Gas verloren geht."""
    name: _str
    def deposit(self) -> ExoticDeposit | None:
        """Die `ExoticDeposit`, auf der dieser Gasaufsatz befestigt ist, mit `.id`, `position()`, `fluid()`, `current_phase()` und Zykluszeiten. Welche Felder verfügbar sind, hängt von der Sonarstufe ab, mit der die Lagerstätte zuletzt untersucht wurde: Die Grundstufe zeigt nur die Phase, die Weitbereichsstufe zusätzlich die Raten und die Tiefenstufe auch die Zykluszeiten. `None`, wenn der Gasaufsatz auf keiner Lagerstätte sitzt. Prüfe mit `deposit.current_phase()`, ob die Quelle aktiv ist. Siehe `ExoticDeposit`."""
        ...
    def capture_rate(self) -> _float:
        """Exotisches Gas, das beim letzten Durchflusstick aus der Lagerstätte aufgefangen wurde, in t/h. **0** während der Ruhephase der Lagerstätte oder wenn der Puffer voll ist und die Sammlung pausiert (siehe `is_venting()`). Die aktuelle Phase und der freie Platz im Puffer sind bereits berücksichtigt; lies diesen Wert ab, statt ihn aus der Förderrate der Lagerstätte zu berechnen. Wird einmal pro Durchflusstick aktualisiert."""
        ...
    def is_venting(self) -> _bool:
        """`True`, wenn die aktive Gasproduktion beim letzten Durchflusstick den freien Platz im Auffangpuffer überschritten hat. Der Überschuss bleibt an der Quelle, ohne dass Gas verloren geht. Während der Ruhephase wird auch bei vollem Puffer `False` zurückgegeben, ebenso bei Stromausfall. Das zeigt eine begrenzte Aufnahmekapazität an; `is_stalled()` meldet dagegen eine blockierte Abgabe. Öffne mit `self.set_throttle(...)` das Ventil in Richtung eines Tanks mit freiem Platz."""
        ...
    def is_stalled(self) -> _bool:
        """`True`, wenn der Gasaufsatz beim letzten Durchflusstick mit Strom versorgt war, das Abgabeventil geöffnet hatte und Gas im Puffer zur Abgabe bereitstand, aber über keine seiner verbundenen Routen etwas übertragen konnte. Ein leerer Puffer, ein geschlossenes Ventil oder fehlender Strom wird nicht als Blockade gemeldet."""
        ...
    def throttle(self) -> _float:
        """Aktuelle Einstellung des Abgabeventils von `0.0` (Abgabe angehalten) bis `1.0` (vollständig geöffnet). Lies den Wert nach `set_throttle(...)` erneut ab."""
        ...
    def set_throttle(self, t: _float) -> ActionResult[Literal["ok"]]:
        """Öffne das Abgabeventil des Gasaufsatzes mit einem Wert von `0.0` bis `1.0` (Werte außerhalb des Bereichs werden auf den nächsten Grenzwert begrenzt). Bei `0` bleibt das Gas im Puffer; bei `1.0` wird es so schnell an erreichbare, angeschlossene Ziele abgegeben, wie Puffervorrat, freie Kapazität der Ziele und Durchsatz es zulassen. Dieser vom Skript gesetzte Sollwert wird auf `0` zurückgesetzt, wenn das Skript angehalten wird, endet oder einen Fehler auslöst. `[self only]` Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    gas_out: FluidPort
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

## `ExoticSpringTap`

```python
class ExoticSpringTap(Component):
    """Zapfanlage für exotische Quellen: Fängt während der aktiven Phase Flüssigkeit aus einer zyklischen exotischen Quelle auf. Verbinde `self.liquid_out` mit einem Abnehmer, baue eine durchgehende Flüssigkeitsleitung vom Quellhahn im Feld bis zu diesem Ziel und stelle dann mit `self.set_throttle(value)` eine Abgaberate von **0-1** ein. Ist der Puffer voll, pausiert die Sammlung, ohne dass Flüssigkeit verloren geht."""
    name: _str
    def deposit(self) -> ExoticDeposit | None:
        """Die `ExoticDeposit`, auf der dieser Quellhahn befestigt ist, mit `.id`, `position()`, `fluid()`, `current_phase()` und Zykluszeiten. Welche Felder verfügbar sind, hängt von der Sonarstufe ab, mit der die Lagerstätte zuletzt untersucht wurde (Grundstufe / Weitbereich / Tiefe). `None`, wenn der Quellhahn auf keiner Lagerstätte sitzt. Prüfe mit `deposit.current_phase()`, ob die Quelle aktiv ist. Siehe `ExoticDeposit`."""
        ...
    def capture_rate(self) -> _float:
        """Exotische Flüssigkeit, die beim letzten Durchflusstick aus der Quelle aufgefangen wurde, in t/h. **0** während der Ruhephase der Lagerstätte oder wenn der Puffer voll ist und die Sammlung pausiert (siehe `is_venting()`). Die aktuelle Phase und der freie Platz im Puffer sind bereits berücksichtigt. Wird einmal pro Durchflusstick aktualisiert."""
        ...
    def is_venting(self) -> _bool:
        """`True`, wenn die aktive Flüssigkeitsproduktion beim letzten Durchflusstick den freien Platz im Auffangpuffer überschritten hat. Der Überschuss bleibt an der Quelle, ohne dass Flüssigkeit verloren geht. Während der Ruhephase wird auch bei vollem Puffer `False` zurückgegeben, ebenso bei Stromausfall. Das zeigt eine begrenzte Aufnahmekapazität an; `is_stalled()` meldet dagegen eine blockierte Abgabe. Öffne mit `self.set_throttle(...)` das Ventil in Richtung eines Tanks mit freiem Platz."""
        ...
    def is_stalled(self) -> _bool:
        """`True`, wenn der Quellhahn beim letzten Durchflusstick mit Strom versorgt war, das Abgabeventil geöffnet hatte und Flüssigkeit im Puffer zur Abgabe bereitstand, aber über keine seiner verbundenen Routen etwas übertragen konnte. Ein leerer Puffer, ein geschlossenes Ventil oder fehlender Strom wird nicht als Blockade gemeldet."""
        ...
    def throttle(self) -> _float:
        """Aktuelle Einstellung des Abgabeventils von `0.0` (Abgabe angehalten) bis `1.0` (vollständig geöffnet). Lies den Wert nach `set_throttle(...)` erneut ab."""
        ...
    def set_throttle(self, t: _float) -> ActionResult[Literal["ok"]]:
        """Öffne das Abgabeventil des Quellhahns mit einem Wert von `0.0` bis `1.0` (Werte außerhalb des Bereichs werden auf den nächsten Grenzwert begrenzt). Bei `0` bleibt die Flüssigkeit im Puffer; bei `1.0` wird sie so schnell an erreichbare, angeschlossene Ziele abgegeben, wie Puffervorrat, freie Kapazität der Ziele und Durchsatz es zulassen. Dieser vom Skript gesetzte Sollwert wird auf `0` zurückgesetzt, wenn das Skript angehalten wird, endet oder einen Fehler auslöst. `[self only]` Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    liquid_out: FluidPort
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

## `Fabricator`

```python
class Fabricator(Component):
    """Fabrikator: Setzt fertige Teile aus mehreren veredelten Materialien gleichzeitig zusammen. Ein Skript wählt ein Rezept aus, holt alle Zutaten in den gemeinsamen Materialvorrat und transportiert die fertigen Gegenstände ab."""
    name: _str
    outpost: OutpostRef
    def list_recipes(self) -> _list[Recipe]:
        """Alle Rezepte, für die dieser Fabrikator einen Bauplan erhalten hat. Gibt Rezeptobjekte mit `.tier`, `.id`, `.name`, `.inputs`, `.output_item`, `.output_count`, `.duration_game_hours`, `.power_draw`, `.fluid_inputs` (verbrauchte Tonnen pro Durchlauf) und optionalen Feldern für Nebenprodukte zurück. Gesperrte Rezepte ohne Bauplan erscheinen nicht; die Liste zeigt, was du derzeit tatsächlich herstellen kannst. `sorted(self.list_recipes(), key=lambda recipe: recipe.tier)` sortiert die verfügbaren Rezepte von den Grundlagen aufwärts."""
        ...
    def find_recipe(self, recipe_id: _str) -> Recipe | None:
        """Findet ein freigeschaltetes Rezept anhand seiner ID, ohne `list_recipes()` durchlaufen zu müssen. Gibt das zugehörige `Recipe`-Objekt zurück oder `None`, wenn die ID unbekannt oder das Rezept gesperrt ist oder zu einer anderen Maschine gehört."""
        ...
    def set_recipe(self, recipe_or_id: RecipeRef) -> ActionResult[Literal["ok", "unknown_recipe", "offline", "recipe_locked", "busy", "material_mismatch"]]:
        """Wähle das Rezept aus, das hergestellt werden soll: `self.set_recipe(\"craft_gas_pipe_segment\")`. Du kannst auch ein Rezept aus `list_recipes()` übergeben. Beim Wechsel des Rezepts wird der Materialvorrat nicht geleert. Reste eines früheren Rezepts bleiben liegen, bis sie verbraucht oder mit `self.input.flush()` verworfen werden. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def clear_recipe(self) -> ActionResult[Literal["ok", "busy", "material_present"]]:
        """Hebe die Auswahl des Rezepts auf und versetze den Fabrikator in den Leerlauf. Der Eingangsvorrat bleibt erhalten, da er allgemein bereitgestelltes Material enthält und nicht an das ausgewählte Rezept gebunden ist. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def get_recipe(self) -> Literal["", "craft_gas_pipe_segment", "craft_liquid_pipe_segment", "craft_power_line_segment", "craft_gas_pipe_bridge", "craft_liquid_pipe_bridge", "craft_power_line_bridge", "craft_pressure_valve", "craft_machine_frame", "craft_circuit_panel", "craft_control_unit", "craft_battery_cell", "craft_thermal_cap_kit", "craft_turbine_rotor", "craft_tank_lining", "craft_water_pump", "craft_oil_pump", "craft_lubricant", "craft_plastic", "craft_rubber", "craft_tar", "craft_reinforced_biopolymer", "craft_enrichment_compound", "craft_drone_station_kit", "craft_drone_station_kit_medium", "craft_drone_station_kit_large", "craft_drone_service_station_kit", "craft_mining_drill_kit", "craft_mining_drill_industrial_kit", "craft_mining_drill_heavy_kit", "craft_drone_small", "craft_drone_medium", "craft_drone_large", "craft_electric_thruster", "craft_heli_thruster", "craft_cargo_pod_small", "craft_cargo_pod_medium", "craft_cargo_pod_large", "craft_battery_pack", "craft_oil_tank_small", "craft_oil_tank_medium", "craft_oil_tank_large", "craft_coolant_loop", "craft_neutron_capacitor", "craft_seed_maker_kit", "craft_plant_terraformer_kit", "craft_grow_lamp_kit", "craft_sprinkler_kit", "craft_dispenser_kit", "craft_garbage_disposal_kit", "craft_exotic_gas_cap_kit", "craft_exotic_spring_tap_kit", "craft_fertilizer", "craft_fertilizer_mk2", "craft_fertilizer_mk3", "craft_growth_accelerant", "craft_yield_amplifier", "craft_plant_terraformer_pack_mk2", "craft_grow_lamp_pack_mk2", "craft_grow_lamp_pack_mk3", "craft_sprinkler_pack_mk2", "craft_sprinkler_pack_mk3", "craft_feed_maker_pack_mk2", "craft_habitat_pack_mk2", "craft_lead_plate", "craft_oxygen_upgrade_pack_mk4", "craft_heat_upgrade_pack_mk4", "craft_pressure_upgrade_pack_mk4", "craft_lead_cask", "craft_shield_plating", "craft_lightning_rod_kit"]:
        """Die ID des aktuellen Rezepts als Zeichenfolge oder eine leere Zeichenfolge, wenn kein Rezept ausgewählt ist. Verwende sie, um andere Abläufe davon abhängig zu machen oder die Auswahl nach `set_recipe()` zu bestätigen."""
        ...
    def get_recipe_inputs(self) -> _dict[_str, _int]:
        """Benötigte Eingaben für das aktuelle Rezept als dict `{item_id: count_per_craft}`. Gibt ein leeres dict zurück, wenn kein Rezept ausgewählt ist. Nutze `.keys()` / `.values()` / `.items()`, um eine Schleife zu steuern: `for mat, need in self.get_recipe_inputs().items(): self.input.connect(bin_for(mat)); self.input.take(mat, need)`."""
        ...
    def get_stockpile(self) -> _dict[_str, _int]:
        """Aktueller Materialvorrat als dict `{item_id: count_currently_stored}`. Durchlaufe mit `.items()` alle Materialien oder lies mit `self.get_stockpile()[\"iron_ingot\"]` direkt die Menge eines Materials ab. So erkennst du, was noch herangeholt werden muss."""
        ...
    def get_stockpile_used(self) -> _int:
        """Gesamtzahl der Einheiten aller Materialien im Vorrat. Vergleiche sie mit `get_stockpile_capacity()`, um zu erkennen, wann der Vorrat voll ist. Dann werden weitere Eingaben blockiert, bis der laufende Herstellungsvorgang Material verbraucht."""
        ...
    def get_stockpile_capacity(self) -> _int:
        """Gemeinsame Obergrenze für die Anzahl der Einheiten aller Materialien (für diesen Fabrikator festgelegt). Der Wert lässt sich abfragen, statt ihn fest ins Skript einzutragen, denn die Obergrenze kann unabhängig von deinem Skript angepasst werden. Nutze `used / capacity` für eine prozentuale Füllstandsanzeige."""
        ...
    def is_running(self) -> _bool:
        """`True`, während ein Herstellungsvorgang läuft. Prüfe dies vor `set_recipe()`, um `\"busy\"` zu vermeiden, oder zeige damit den Status an. Der Wert bleibt über mehrere Ticks hinweg `True`, bis die Herstellung abgeschlossen ist."""
        ...
    def get_progress(self) -> _float:
        """Fortschritt des aktuellen Herstellungsvorgangs bis zum Abschluss (**0-1**). Wird nach Abschluss auf **0** zurückgesetzt. Nutze den Wert für Fortschrittsbalken oder erkenne einen Abschluss daran, dass er wieder sinkt."""
        ...
    def get_output_count(self) -> _int:
        """Anzahl fertiger Einheiten im Ausgabepuffer. Transportiere sie mit `self.output.send(...)` ab, bevor der Puffer voll ist. Bei vollem Ausgabepuffer stockt die Verarbeitung."""
        ...
    input: InputSlot
    output: OutputSlot
    byproduct: OutputSlot
    steam_in: FluidPort
    water_in: FluidPort
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

## `Field`

```python
class Field:
    """`dataclasses.fields()`"""
    name: _str
    default: Any
    default_factory: Callable[..., Any]
    init: _bool
    repr: _bool
    compare: _bool
    kw_only: _bool
```

## `FluidConnection`

```python
class FluidConnection:
    """FluidPort.connections()"""
    machine_id: _str
    machine_name: _str
    fluid: Literal["steam", "water", "oil", "frozen_essence", "coastal_essence", "geothermal_essence", "volcanic_essence", "deep_essence", "ammonia", "swamp_gas", "raw_sulfur_gas", "sulfur_gas", "raw_chlorine", "chlorine", "brine", "raw_cryofluid", "cryofluid", "raw_quicksilver", "quicksilver"] | None
    declared_by: Literal["self", "peer", "both"]
    state: Literal["local", "ready", "unreachable", "conflict", "neutral", "incompatible"]
```

## `FluidPort`

```python
class FluidPort:
    """jede Eigenschaft `<fluid>_in` / `<fluid>_out` einer Maschine im Flussnetz"""
    def connect(self, target: _str) -> ActionResult[Literal["ok", "not_found", "incompatible"]]:
        """Erfasse oder ersetze das eine deklarierte Ziel dieses Anschlusses anhand einer stabilen Maschinen-ID oder eines Anzeigenamens. Das Ziel muss einen kompatiblen Anschluss mit entgegengesetzter Flussrichtung haben. Sowohl der Anbieter als auch der Abnehmer kann die Verbindung deklarieren; eine Deklaration genügt. Maschinen am selben Außenposten übertragen direkt. Bei entfernten Zielen wartet die Verbindung auf eine fertiggestellte, konfliktfreie Komponente für dasselbe Medium, die beide Endpunkte erreicht. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def disconnect(self) -> ActionResult[Literal["ok"]]:
        """Entfernt nur das von diesem Anschluss deklarierte Ziel. Gepufferte Flüssigkeit bleibt erhalten. Hat die Gegenstelle dieselbe Verbindung unabhängig deklariert, bleibt diese Deklaration in Gegenrichtung aktiv. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def connected_to(self) -> _str:
        """Anzeigename des von diesem Anschluss deklarierten Ziels oder eine leere Zeichenfolge. Kompatible Deklarationen in Gegenrichtung, die anderen Anschlüssen gehören, werden nicht aufgeführt."""
        ...
    def connected_id(self) -> _str:
        """Stabile ID des von diesem Anschluss deklarierten Ziels oder eine leere Zeichenfolge. `connect()` akzeptiert eine ID oder einen Anzeigenamen, aber dieser Wert ist die aufgelöste stabile ID. Vergleiche ihn mit der stabilen ID des Ziels; `connected_to()` liefert dessen änderbaren Anzeigenamen. Verwende `connections()` für alle wirksamen Gegenstellen, auch wenn die andere Seite die Verbindung deklariert hat."""
        ...
    def connections(self) -> _list[FluidConnection]:
        """Schreibgeschützte Momentaufnahmen aller wirksamen Verbindungen dieses Anschlusses zu Gegenstellen, einschließlich der von anderen Anschlüssen deklarierten Verbindungen. Jede `FluidConnection` gibt die Gegenstelle, die genaue Flüssigkeit, sofern bekannt, den Besitzer der Deklaration und den strukturellen Status an. Rohr-IDs werden bewusst weder offengelegt noch ausgewählt."""
        ...
    def level(self) -> _float:
        """Aktuell an diesem Anschluss gepufferte Flüssigkeitsmenge in Tonnen. Durchlaufende Quellanschlüsse wie Pumpenausgänge speichern nichts und liefern daher **0**."""
        ...
    def capacity(self) -> _float:
        """Maximale Flüssigkeitsmenge in Tonnen, die der Puffer dieses Anschlusses aufnehmen kann."""
        ...
    def flow_rate(self) -> _float:
        """Aktueller gesamter Durchfluss in **t/h**. **0** kann bedeuten, dass die Verbindung inaktiv, unterversorgt, voll, unerreichbar oder von einem Konflikt betroffen ist oder an einer zeitlichen Grenze der Simulation wartet. Die Verbindung oder Rohridentität wird dadurch nicht gelöscht."""
        ...
```

## `FuelAssembler`

```python
class FuelAssembler(Component):
    """Brennstofffertiger: Presst Rohuran und Bleiplatten zu Brennstäben oder Nuklearbatterien, ähnlich wie der Fabrikator. Während des Betriebs benötigt die Maschine für ihre Rezepte viel Strom. Lass sie daher am besten in kurzen Intervallen laufen, wenn deine Blitzspeicher voll sind."""
    name: _str
    outpost: OutpostRef
    def list_recipes(self) -> _list[Recipe]:
        """Freigeschaltete Rezepte, die diese Maschine ausführen kann, jeweils mit dem abgeleiteten Wert für `.tier`. Das Brennstab-Rezept wird über die Warteschlange von Vestibule freigeschaltet, das Nuklearbatterie-Rezept über die von Helios."""
        ...
    def find_recipe(self, recipe_id: _str) -> Recipe | None:
        """Findet ein freigeschaltetes Brennstoffrezept anhand seiner ID, ohne `list_recipes()` zu durchlaufen. Gibt das zugehörige `Recipe`-Objekt zurück oder `None`, wenn die ID unbekannt oder gesperrt ist oder zu einer anderen Maschine gehört."""
        ...
    def set_recipe(self, recipe_or_id: RecipeRef) -> ActionResult[Literal["ok", "unknown_recipe", "recipe_locked", "offline", "busy", "material_mismatch"]]:
        """Wählt ein Rezept für Brennstäbe oder Nuklearbatterien anhand seiner ID oder durch Übergabe eines Recipe aus `list_recipes()` aus. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def clear_recipe(self) -> ActionResult[Literal["ok", "busy", "material_present"]]:
        """Hebt die Rezeptauswahl auf, sobald die aktuelle Herstellung ruht und der Ausgabepuffer leer ist. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def get_recipe(self) -> Literal["", "craft_fuel_rod", "craft_nuclear_battery"]:
        """Die ID des festgelegten Rezepts; leer, wenn keines festgelegt ist."""
        ...
    def get_recipe_inputs(self) -> _dict[_str, _int]:
        """Benötigte Eingaben für das festgelegte Rezept als dict `{item_id: count_per_craft}`. Gibt ein leeres dict zurück, wenn kein Rezept festgelegt ist."""
        ...
    def is_running(self) -> _bool:
        """`True`, während die aktuelle Herstellung tatsächlich voranschreitet und Strom, Zutaten und Platz im Ausgabepuffer vorhanden sind."""
        ...
    def get_progress(self) -> _float:
        """Fortschritt der aktuellen Herstellung von **0-1**. Der Fortschritt bleibt bei Stromausfällen erhalten; danach geht die Herstellung weiter."""
        ...
    def get_stockpile(self) -> _dict[_str, _int]:
        """Bereitgestellte Zutaten nach Gegenstands-ID als dict im Format `{\"raw_uranium\": 12, \"lead_plate\": 4}`."""
        ...
    def get_output_count(self) -> _int:
        """Fertige Produkte des ausgewählten Rezepts, die im kleinen Ausgabepuffer warten."""
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

## `GarbageDisposal`

```python
class GarbageDisposal(Component):
    """Abfallentsorger: Vernichtet dauerhaft einen per Skript gewählten Abfallstrom: Gegenstände, Flüssigkeiten oder Gase. Nutze den Gegenstandseingang für unerwünschte Bestände, `liquid_in` für überschüssiges Wasser oder andere Flüssigkeiten und `gas_in` für Gase. Vernichtet wird nur, solange das Skript, das die Anlage aktiviert hat, noch läuft. Es gibt keinen Ausgang, und nichts wird verwertet."""
    name: _str
    outpost: OutpostRef
    def set_enabled(self, enabled: _bool) -> ActionResult[Literal["ok"]]:
        """Aktiviere oder pausiere die Vernichtung im ausgewählten Modus. Der Prozessor vernichtet nur Abfall, solange das Skript läuft, das ihn aktiviert hat. Wenn dieses Skript angehalten wird, endet oder einen Fehler auslöst, wird die Einstellung wieder deaktiviert und `status()` liefert `\"disabled\"`. Ein Schmelzofen arbeitet mit seinem festgelegten Rezept weiter, diese Maschine nicht. Bereitgestellte Gegenstände und Flüssigkeiten oder Gase bleiben erhalten. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def is_enabled(self) -> _bool:
        """Liest aus, ob der Prozessor derzeit aktiviert ist. Die Aktivierung ist an ein laufendes Skript gebunden; sobald es endet, wird wieder `False` zurückgegeben."""
        ...
    def set_mode(self, mode: _str) -> ActionResult[Literal["ok"]]:
        """Wählt genau einen Abfallstrom zur Vernichtung aus: `\"items\"`, `\"liquid\"` oder `\"gas\"`. Beim Wechsel des Modus werden die anderen Puffer pausiert, ohne ihren Inhalt zu löschen. Der ausgewählte Flüssigkeits- oder Gasanschluss nimmt nur im aktivierten Zustand Material an. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def mode(self) -> Literal["items", "liquid", "gas"]:
        """Liest den ausgewählten Abfallstrom aus."""
        ...
    def status(self) -> Literal["disabled", "no_power", "idle", "processing"]:
        """Liest den genauen aktuellen Zustand aus: `\"disabled\"`, `\"no_power\"`, `\"idle\"` oder `\"processing\"`. `\"disabled\"` bedeutet, dass kein laufendes Skript den Prozessor aktiviert hat. Bereitgestellter Abfall bleibt dann unberührt."""
        ...
    def throughput(self) -> _float:
        """Liest die aktuelle Vernichtungsrate des ausgewählten Modus aus. Im Gegenstandsmodus wird sie in Einheiten/h angegeben, im Flüssigkeits- und Gasmodus in t/h."""
        ...
    def item_throughput(self) -> _float:
        """Liest die aktuelle Vernichtungsrate für Gegenstände in Einheiten/h aus. Bei 100 % Effizienz des Außenpostens beträgt das Maximum **60 Einheiten/h**."""
        ...
    def liquid_throughput(self) -> _float:
        """Liest die zuletzt gemessene Vernichtungsrate für Flüssigkeiten in t/h aus. Bei 100 % Effizienz des Außenpostens beträgt das Maximum **120 t/h**."""
        ...
    def gas_throughput(self) -> _float:
        """Liest die zuletzt gemessene Vernichtungsrate für Gase in t/h aus. Bei 100 % Effizienz des Außenpostens beträgt das Maximum **120 t/h**."""
        ...
    def is_running(self) -> _bool:
        """Liest aus, ob im ausgewählten Modus derzeit bereitgestelltes Material vernichtet wird."""
        ...
    input: InputSlot
    liquid_in: FluidPort
    gas_in: FluidPort
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

## `GeologicalAnomaly`

```python
class GeologicalAnomaly(Site):
    """jede API, die eine Site zurückgibt, bei der `kind() == \"inert\"` gilt"""
    ...
```

## `Gps`

```python
class Gps(Component):
    """GPS: Ein Schiffssensor, der meldet, welchen Außenposten du gerade betrachtest, wie er heißt, wo er liegt und wie viele Gebäude dort aufgestellt sind. Wenn du in der Übersicht den Außenposten wechselst, richtet sich der Sensor auf ihn aus."""
    name: _str
    def planet(self) -> Nocturna:
        """Gibt die aktuelle Planetenkomponente zurück. Verwende `gps.planet().id` für unveränderliche IDs wie `\"nocturna\"` beim Aufruf von Logbuch-APIs und `gps.planet().get_name()` für den Anzeigenamen `\"Nocturna\"`."""
        ...
    def site_name(self) -> _str:
        """Gibt den Anzeigenamen des aktuellen Außenpostens zurück: standardmäßig `\"Nocturna Base\"` für den Heimat-Außenposten (Spieler können ihn umbenennen) und `\"Outpost 1\"`, `\"Outpost 2\"`, ... für von Spielern gegründete Außenposten."""
        ...
    def coords(self) -> _list[_int]:
        """Gibt die Weltkoordinaten des aktuellen Außenpostens als **Liste mit 2 Elementen** `[x, y]` zurück. Der Heimat-Außenposten liegt bei `[0, 0]`; gegründete Außenposten haben die Position, die der Spieler im Planungsmodus gewählt hat."""
        ...
    def buildings_used(self) -> _int:
        """Gibt die Anzahl der am **aktuellen** Außenposten aufgestellten Gebäude zurück. Sensoren, mobile Einheiten, zentrale Bauten und Fördermaschinen an interessanten Orten zählen nicht mit, sondern nur im Shop gekaufte, aufstellbare Gebäude."""
        ...
    def buildings_capacity(self) -> _int:
        """Gibt den Richtwert für Gebäude am aktuellen Außenposten zurück. Jedes mitgezählte Gebäude über diesem Wert verringert den Durchsatz bei Produktion und Versorgung. Die Nocturna Base hat zu Beginn einige zusätzliche Bauplätze; gegründete Außenposten verwenden den üblichen Richtwert."""
        ...
    def is_full(self) -> _bool:
        """Gibt `True` zurück, wenn der aktuelle Außenposten seinen Richtwert für Gebäude erreicht oder überschritten hat. Der Richtwert verhindert das gewöhnliche Aufstellen weiterer Gebäude nicht."""
        ...
    def is_home(self) -> _bool:
        """Gibt `True` zurück, wenn der aktuelle Außenposten der Heimat-Außenposten ist, an dem du begonnen hast (Standardname: `\"Nocturna Base\"`). Nützlich, wenn dein Skript zwischen dem Startort und einem entfernten Außenposten unterscheiden soll."""
        ...
```

## `GrowLamp`

```python
class GrowLamp(Component):
    """Pflanzenlampe: Beleuchtet bei Stromversorgung und im eingeschalteten Zustand die vier direkt angrenzenden Feldzellen (oben, unten, links und rechts). Skripte finden die Lampe über `outpost.harvesting_machines()`."""
    name: _str
    def set_enabled(self, enabled: _bool) -> ActionResult[Literal["ok"]]:
        """Schaltet die Lampe ein oder aus. Bei einem Stromausfall pausiert das Skript, die Einstellung bleibt jedoch erhalten. Wenn das Maschinenskript angehalten wird, wird sie auf `False` zurückgesetzt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def is_enabled(self) -> _bool:
        """`True`, wenn das laufende Skript die Lampe eingeschaltet hat."""
        ...
    def is_active(self) -> _bool:
        """`True`, wenn die Lampe eingeschaltet werden soll und mit Strom versorgt wird."""
        ...
    def is_supplied(self) -> _bool:
        """`True`, wenn die Lampe eingeschaltet werden soll, mit Strom versorgt wird und die von ihr abgedeckten Felder tatsächlich beleuchtet. Ist sie deaktiviert oder ohne Strom, verlieren diese Felder `lit` und ihre Pflanzen pausieren."""
        ...
    def status(self) -> Literal["not_placed", "disabled", "no_power", "active"]:
        """Genauer Betriebszustand: `\"not_placed\"`, `\"disabled\"`, `\"no_power\"` oder `\"active\"`."""
        ...
    def tier(self) -> _int:
        """Aufgestellte Stufe (**1-4**). Mk I/II/III/IV ermöglichen bei versorgten Pflanzen die **1×/2×/4×/8×**-fache Produktion und verbrauchen im aktiven Zustand **5/25/100/500 W**."""
        ...
    def position(self) -> _str:
        """Rastersektor, in dem diese Lampe steht, zum Beispiel `\"E14\"`."""
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

## `Habitat`

```python
class Habitat(Component):
    """Habitat: Belebt eine Art mit Biologie-Reagenzien wieder, die im eigenen lokalen Eingang dieses Habitats bereitliegen, und züchtet daraus eine Kolonie. Pro Art ist nur eine lebende Kolonie erlaubt. Etablierte Kolonien behalten ihren Fortschritt, wenn sie zwischen Habitaten umziehen."""
    name: _str
    outpost: OutpostRef
    def set_revival_target(self, creature_id: _str) -> ActionResult[Literal["ok", "occupied", "species_exists", "unknown_creature", "not_cataloged"]]:
        """Wähle mit `self.set_revival_target(\"salt_tortoise\")`, welches katalogisierte Tier dieses Habitat vorbereitet. Das geprüfte Ziel bleibt erhalten, wenn das Skript stoppt oder eine Prüfung der Voraussetzungen oder ein Aufzuchtversuch scheitert. So kann die Habitatkarte das Tier und die aktuellen Anforderungen für seine Vorbereitung anzeigen, bevor eine Kolonie existiert. Wenn du ein anderes gültiges Tier wählst, ersetzt es das Ziel, ohne Materialien zu verbrauchen. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def revive(self) -> ActionResult[Literal["ok", "occupied", "no_target", "species_exists", "not_cataloged", "wrong_feed", "insufficient_feed", "insufficient_reagents"]]:
        """Erwecke das ausgewählte Wiederbelebungsziel dieses Habitats mit `self.revive()` zum Leben. Lagere zuvor mindestens **2** Einheiten seines Futters ein: Die Wiederbelebung verbraucht eine Einheit, und eine weitere muss für die Aufzucht übrig bleiben. Lege genau die nach Seltenheit bemessenen Biolabor-Reagenzien bereit, die das Habitat oder `journal.cataloged_creatures(...)` anzeigt. Tierboni ändern dieses einmalige Rezept nicht. Fehlgeschlagene Prüfungen verbrauchen nichts und behalten das ausgewählte Ziel bei. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def rehouse(self, creature_id: _str) -> ActionResult[Literal["ok", "occupied", "no_colony", "not_established", "insufficient_capacity", "unknown_creature"]]:
        """Bringe mit `self.rehouse(\"salt_tortoise\")` eine etablierte Kolonie dieser Art in diesem Habitat unter. Das Zielhabitat muss leer sein und seine aktuelle Kapazität muss für die gesamte Kolonie reichen. Derselbe Aufruf verlegt eine Kolonie direkt aus einem anderen Habitat oder bringt sie wieder unter, nachdem ihr früheres Habitat abgebaut wurde. Population, Lebensphase, Brutfortschritt, Erkenntnisverlauf und gekaufte Boni bleiben erhalten; die Population fließt weiterhin in die Gesamtzahl der Tierwelt ein. Nur das Wachstum pausiert, solange die Kolonie kein Habitat hat. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def set_gas_intake(self, rate: _float) -> ActionResult[Literal["ok"]]:
        """Stelle den Gaszufluss in **t/h** ein. Das Gas wird aus dem verbundenen Gastank (verbinde ihn mit `self.gas_in.connect(\"gas_tank_1\")`) in den Gasvorrat des Geheges geleitet. Damit regelst du den Zufluss: Lies `gas_level()`, vergleiche den Wert mit `gas_band()` und erhöhe den Zufluss unterhalb des Bereichs oder senke ihn oberhalb des Bereichs. Im Leerlauf beträgt er **0**. Werte werden auf `>= 0` begrenzt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def purge_intake(self, port: _str | None = ...) -> ActionResult[Literal["ok", "empty"]]:
        """Entlüftet einen Rohstoffeingang, damit er ein anderes Gas oder eine andere Flüssigkeit aufnehmen kann. Übergib `\"gas_in\"` oder `\"liquid_in\"`, um einen Eingang zu entlüften, oder lass den Wert weg, um beide zu entlüften. Wenn du nur den tatsächlich blockierten Eingang entlüftest, bleibt ein intakter Puffer unberührt. Die Eingänge nehmen das erste ankommende Gas beziehungsweise die erste Flüssigkeit auf und weisen danach alle anderen zurück. Wird ein Gehege mit dem falschen Gas versorgt, enthält es schließlich Gas, das es nicht nutzen kann, und kann das richtige nicht aufnehmen. Entlüfte den Eingang und ändere die Verbindung; mit der nächsten Lieferung des richtigen Gases wird die Luft im Gehege ersetzt: `self.purge_intake()`, dann `self.gas_in.connect(\"Sulfur Refiner\")`. Das abgelassene Gas oder die abgelassene Flüssigkeit wird vernichtet; Futter und Koloniefortschritt bleiben unberührt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def purge_reserve(self, medium: _str) -> ActionResult[Literal["ok", "empty"]]:
        """Leert den gewählten Vorrat des Geheges sofort: `self.purge_reserve(\"gas\")` oder `self.purge_reserve(\"liquid\")`. Die Flüssigkeit oder das Gas wird vernichtet. Der andere Vorrat, die Eingangspuffer, Verbindungen, Zuflusseinstellungen, Futter und der Koloniefortschritt bleiben erhalten. Der Vorrat kann sich in späteren Ticks wieder füllen, wenn der Zufluss offen bleibt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def set_liquid_intake(self, rate: _float) -> ActionResult[Literal["ok"]]:
        """Stelle den Flüssigkeitszufluss in **t/h** ein. Die Flüssigkeit wird aus dem verbundenen Flüssigkeitstank (`self.liquid_in.connect(\"liquid_tank_1\")`) in den Flüssigkeitsvorrat des Geheges geleitet. Regle den Zufluss so, dass der Wert im Bereich von `liquid_band()` bleibt. Im Leerlauf beträgt er **0**. Werte werden auf `>= 0` begrenzt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def unlock_bonus(self, node_id: _str) -> ActionResult[Literal["ok", "unknown_node", "already_purchased", "population_locked", "insufficient_insight"]]:
        """Kaufe dauerhaft einen Knoten aus dem Baum dieses Tiers. Übergib eine Knoten-ID aus `get_bonus_tree().nodes`. Die Anpassung für **1 Erkenntnis** wirkt nur auf diese Art. Der Durchbruch für **4 Erkenntnis** wirkt auf alle Arten und setzt außerdem voraus, dass diese Ursprungskolonie eine Population von **10.000** erreicht. Ein abgelehnter Kauf verbraucht nichts. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def tier(self) -> _int:
        """Dauerhaft installierte Habitat-Stufe als ganze Zahl (**1–2**). Mk II verdoppelt nur die Kapazität; Zuchtgeschwindigkeit und biologische Kosten ergeben sich aus Anpassungen."""
        ...
    def population(self) -> _int:
        """Aktuelle Anzahl der Individuen in der Kolonie. Gibt **0** zurück, wenn das Habitat leer ist oder die Kolonie noch in der Aufzuchtphase „Gegründet“ steckt. Eine Kolonie zählt hier und beim Tierweltsensor erst, wenn sie etabliert ist. Sie wächst bis zur Kapazität von `carrying_capacity()` und schrumpft nie."""
        ...
    def species(self) -> Literal["", "salt_tortoise", "magmatic_annelid", "mycelial_husk", "mantle_strider", "glasswing_mantis", "veil_mantle", "vault_crab", "tidal_cephalopod", "bone_walker", "vent_drifter", "hive_sentinel", "hollow_choir", "ferric_sea_lily", "crustal_echo", "glacial_wyrm", "spire_drake"]:
        """Die ID des untergebrachten Tiers (z. B. `\"glacial_wyrm\"`) oder `\"\"`, wenn das Habitat leer ist. Nutze sie, um das Tier nachzuschlagen oder deinen Regler je nach Art unterschiedlich zu steuern."""
        ...
    def revival_target(self) -> Literal["", "salt_tortoise", "magmatic_annelid", "mycelial_husk", "mantle_strider", "glasswing_mantis", "veil_mantle", "vault_crab", "tidal_cephalopod", "bone_walker", "vent_drifter", "hive_sentinel", "hollow_choir", "ferric_sea_lily", "crustal_echo", "glacial_wyrm", "spire_drake"]:
        """Die mit `set_revival_target(...)` ausdrücklich ausgewählte Tier-ID oder `\"\"` vor der Auswahl und nach der Etablierung. Nach fehlgeschlagenen Prüfungen der Voraussetzungen und Aufzuchtversuchen bleibt dieser Wert erhalten, während `species()` leer bleibt, bis die Wiederbelebung tatsächlich beginnt."""
        ...
    def life_stage(self) -> Literal["empty", "founded", "first_breeding", "self_sustaining", "thriving", "abundant"]:
        """Die Lebensphase der Kolonie als Zeichenfolge: `\"empty\"`, `\"founded\"`, `\"first_breeding\"`, `\"self_sustaining\"`, `\"thriving\"` oder `\"abundant\"`. Die Kolonie erreicht die nächste Phase, sobald ihre Population die jeweilige Schwelle überschreitet. Spätere Phasen können die Anforderungen an die Versorgung ändern. In früheren Phasen steigt mit jedem Aufstieg die Grundkapazität, beim Eintritt in „Reichlich“ jedoch nicht. Verzweige nach der Lebensphase, um deine Versorgung auszubauen: `if self.life_stage() == \"thriving\": self.set_liquid_intake(...)`."""
        ...
    def is_established(self) -> _bool:
        """`True`, sobald die Kolonie die Aufzuchtphase „Gegründet“ abgeschlossen hat und vom Sensor erfasst wird; `False` während der Aufzucht oder wenn das Habitat leer ist. Mache die Zuchtlogik davon abhängig: `if self.is_established(): regulate()`."""
        ...
    def rearing_progress(self) -> _float:
        """Anteil der Aufzuchtphase „Gegründet“ zwischen **0–1**, während der alle Werte in ihren zulässigen Bereichen lagen. Steigt nur, solange alle aktiven Bereiche eingehalten werden, und erreicht bei erfolgreicher Etablierung **1,0**. Gibt **0** zurück, wenn das Habitat leer oder die Kolonie etabliert ist. Wird ein Bereich verlassen, schlägt die Aufzucht fehl und der Wert wird auf 0 zurückgesetzt. Beobachte ihn nach einer neuen Wiederbelebung, um zu prüfen, ob dein Regler die Werte im Bereich hält."""
        ...
    def rearing_failed(self) -> _bool:
        """`True`, nachdem bei einem Aufzuchtversuch die zulässigen Bereiche verlassen wurden und das Habitat wieder in die Vorbereitung zurückgekehrt ist. Genom und ausgewähltes Ziel bleiben erhalten. Korrigiere deinen Regler und rufe `revive()` erneut auf. Der Wert wird zurückgesetzt, wenn du ein Ziel auswählst oder die Wiederbelebung neu startest."""
        ...
    def brood_size(self) -> _int:
        """Anzahl ganzer Individuen, die der nächste abgeschlossene Zuchtzyklus hervorbringt. Normalerweise **1**; Brutboni sammeln sich an, bis ein zusätzliches Individuum garantiert ist, sodass der Wert regelmäßig **2** beträgt. Gibt **0** zurück, wenn keine etablierte Kolonie vorhanden oder die Kapazität ausgeschöpft ist."""
        ...
    def breeding_rate(self) -> _float:
        """Erwartete Individuen pro Stunde bei der aktuellen Population, freien Kapazität, Lebenserhaltung, Seltenheit, den Auswirkungen von Anpassungen und den verfügbaren lokalen Ressourcen. Oberhalb von 10 Individuen bringt zusätzliche Population immer weniger Geschwindigkeit, während Brutertrag und gekaufte Geschwindigkeitsboni innerhalb ihrer jeweiligen Gesamtgrenzen bleiben. Dies ist die Anzeige der Zuchtrate; `breeding_efficiency()` gibt nur den Faktor der Lebenserhaltung an."""
        ...
    def feed_level(self) -> _float:
        """Verbleibende nutzbare Futtereinheiten nach teilweisem Verbrauch. Futter wird nur dann automatisch verbraucht, wenn Individuen geboren werden. Fülle den Vorrat mit `self.input.take(...)` auf; zu viel einzulagern schadet nicht."""
        ...
    def gas_level(self) -> _float:
        """Aktuelle Gasmenge im Gehege in **Tonnen**. Vergleiche sie mit `gas_band()` und regle mit `set_gas_intake(...)` den Zufluss, damit sie im zulässigen Bereich bleibt. Sie sinkt, wenn die Kolonie beim Züchten Gas verbraucht, und steigt durch den Zufluss."""
        ...
    def liquid_level(self) -> _float:
        """Aktuelle Flüssigkeitsmenge im Gehege in **Tonnen**. Vergleiche sie mit `liquid_band()` und regle mit `set_liquid_intake(...)` den Zufluss, damit sie im zulässigen Bereich bleibt."""
        ...
    def get_insight(self) -> HabitatInsight:
        """Lies den gemeinsamen Erkenntnisstand der Tierwelt sowie den aktuellen und gesamten Beitrag dieser Kolonie. Erkenntnis entsteht direkt durch eine Zunahme der Population. Eine unveränderte Population und verstrichene Zeit allein bringen nichts ein."""
        ...
    def get_bonus_tree(self) -> HabitatBonusTree:
        """Lies die nur für diese Art geltende Anpassung und den für alle Arten geltenden Durchbruch dieses Tiers. Für jeden Knoten werden `.scope`, `.source_species`, der dauerhafte Kaufstatus, ob seine Wirkung derzeit aktiv ist, die Erkenntniskosten und unerfüllte Voraussetzungen angezeigt. Der Baum erscheint, sobald du ein Wiederbelebungsziel auswählst; seine Knoten bleiben auch im gesperrten Zustand sichtbar."""
        ...
    def get_active_bonuses(self) -> _list[HabitatBonusNode]:
        """Lies alle gekauften Knoten, die dieses Habitat derzeit beeinflussen, einschließlich globaler Durchbrüche, die mit anderen Arten erzielt wurden. Jedes Ergebnis enthält `.scope` und `.source_species`. Ein bedingter Knoten verschwindet, solange seine lokale Bedingung nicht erfüllt ist. Ob er dauerhaft erworben wurde, kannst du mit `get_bonus_tree()` am Habitat seiner Ursprungsart prüfen."""
        ...
    def gas_band(self) -> _list[_float]:
        """Sicherer Bereich `[low, high]` für den Gasvorrat in **Tonnen** während der aktuellen Lebensphase der Kolonie. Innerhalb dieses Bereichs unterstützt das Gas die Zucht vollständig; bei zu wenig Gas ist die Kolonie unterversorgt, zu viel Gas ist giftig. Gibt eine leere Liste zurück, solange kein Gas benötigt wird. Lies den Bereich in jedem Durchlauf erneut, denn er wird mit dem Wachstum der Kolonie enger."""
        ...
    def liquid_band(self) -> _list[_float]:
        """Sicherer Bereich `[low, high]` für den Flüssigkeitsvorrat in **Tonnen** während der aktuellen Lebensphase der Kolonie. Gibt eine leere Liste zurück, solange keine Flüssigkeit benötigt wird. Lies den Bereich in jedem Durchlauf erneut, denn er wird mit dem Wachstum der Kolonie enger."""
        ...
    def feed_ok(self) -> _bool:
        """`True`, wenn das von `required_feed()` angegebene Futter vorrätig ist. Futter wird automatisch verbraucht, wenn Individuen geboren werden. `False` bedeutet, dass der Behälter leer ist oder das falsche Futter enthält. Fehlendes Futter hält die Zucht an, verringert aber nicht die etablierte Population."""
        ...
    def gas_ok(self) -> _bool:
        """`True`, wenn die Gasanforderungen erfüllt sind oder noch kein Gas benötigt wird. `False` bedeutet, dass der Füllstand außerhalb von `gas_band()` liegt oder das Gehege das falsche Gas enthält. Liegt der Füllstand im Bereich, vergleiche `gas_fluid()` mit `required_gas()`."""
        ...
    def liquid_ok(self) -> _bool:
        """`True`, wenn die Flüssigkeitsanforderungen erfüllt sind oder noch keine Flüssigkeit benötigt wird. `False` bedeutet, dass der Füllstand außerhalb von `liquid_band()` liegt oder das Gehege die falsche Flüssigkeit enthält. Vergleiche `liquid_fluid()` mit `required_liquid()`, um die Ursache zu erkennen."""
        ...
    def breeding_efficiency(self) -> _float:
        """Aktueller Lebenserhaltungsfaktor von **0–100 %**, nicht die Wachstumsrate der Population. Die schwächste aktive Versorgung bestimmt ihn; **100 %** bedeutet, dass alle Eingänge bereit sind. Das Wachstum hängt außerdem von der Populationsdynamik, Seltenheit und Boni ab. Die Kapazität stoppt das Wachstum erst, wenn sie vollständig ausgeschöpft ist, und verlangsamt die Zucht zuvor nicht. Schlechte Bedingungen verringern die Population nie."""
        ...
    def gas_fluid(self) -> Literal["", "steam", "ammonia", "swamp_gas", "raw_sulfur_gas", "sulfur_gas", "raw_chlorine", "chlorine"]:
        """Das derzeit im Gehege enthaltene exotische Gas, etwa `\"chlorine\"`, oder `\"\"`, wenn es leer ist. Damit der Gasbereich als erfüllt gilt, muss es mit `required_gas()` übereinstimmen. Liegt `gas_level()` im Bereich, aber `gas_ok()` ist `False`, enthält das Gehege das falsche Gas."""
        ...
    def liquid_fluid(self) -> Literal["", "water", "oil", "frozen_essence", "coastal_essence", "geothermal_essence", "volcanic_essence", "deep_essence", "brine", "raw_cryofluid", "cryofluid", "raw_quicksilver", "quicksilver"]:
        """Die derzeit im Gehege enthaltene exotische Flüssigkeit oder `\"\"`, wenn es leer ist. Damit der Flüssigkeitsbereich als erfüllt gilt, muss sie mit `required_liquid()` übereinstimmen."""
        ...
    def required_feed(self) -> Literal["", "feed_salt_tortoise", "feed_magmatic_annelid", "feed_mycelial_husk", "feed_mantle_strider", "feed_glasswing_mantis", "feed_veil_mantle", "feed_vault_crab", "feed_tidal_cephalopod", "feed_bone_walker", "feed_vent_drifter", "feed_hive_sentinel", "feed_hollow_choir", "feed_ferric_sea_lily", "feed_crustal_echo", "feed_glacial_wyrm", "feed_spire_drake"]:
        """Die genaue Futtergegenstands-ID für das ausgewählte Wiederbelebungsziel oder das untergebrachte Tier, oder `\"\"`, wenn beides fehlt. Vergleiche sie beim Bereitstellen oder Prüfen des Futters mit `self.input.stacks()`."""
        ...
    def required_gas(self) -> Literal["", "swamp_gas", "ammonia", "sulfur_gas", "chlorine"]:
        """Das exotische Gas, das die Kolonie in ihrer aktuellen Lebensphase benötigt, etwa `\"swamp_gas\"`, oder `\"\"`, solange sie noch kein Gas braucht. In späteren Phasen steigen die Anforderungen; prüfe den Wert daher erneut, wenn die Kolonie wächst. Andere Gase erfüllen den erforderlichen Bereich nicht."""
        ...
    def required_liquid(self) -> Literal["", "brine", "cryofluid", "quicksilver"]:
        """Die exotische Flüssigkeit, die dieses Tier in seiner aktuellen Lebensphase benötigt, z. B. `\"brine\"`. In späteren Phasen steigen die Anforderungen (`\"brine\"` → `\"cryofluid\"` → `\"quicksilver\"`). `liquid_fluid()` muss damit übereinstimmen. Gibt `\"\"` zurück, solange noch keine Flüssigkeit benötigt wird."""
        ...
    def next_required_gas(self) -> Literal["", "swamp_gas", "ammonia", "sulfur_gas", "chlorine"]:
        """Das Gas, das nach dem nächsten Wechsel der Lebensphase benötigt wird, oder `\"\"`, wenn die nächste Phase kein Gas erfordert oder es keine nächste Phase gibt. Lies den Wert zusammen mit `next_gas_band()`, bevor die Population die Schwelle erreicht."""
        ...
    def next_required_liquid(self) -> Literal["", "brine", "cryofluid", "quicksilver"]:
        """Die Flüssigkeit, die nach dem nächsten Wechsel der Lebensphase benötigt wird, oder `\"\"`, wenn die nächste Phase keine Flüssigkeit erfordert oder es keine nächste Phase gibt. Lies den Wert zusammen mit `next_liquid_band()`, bevor die Population die Schwelle erreicht."""
        ...
    def next_gas_band(self) -> _list[_float]:
        """Der genaue Gasbereich der nächsten Lebensphase als `[low, high]` in **Tonnen**. Gibt `[]` zurück, wenn diese Phase kein Gas erfordert oder die Kolonie bereits in der Phase „Reichlich“ ist. Nutze den Wert zusammen mit `next_required_gas()`, um die richtige Versorgung und den Regler im Voraus vorzubereiten."""
        ...
    def next_liquid_band(self) -> _list[_float]:
        """Der genaue Flüssigkeitsbereich der nächsten Lebensphase als `[low, high]` in **Tonnen**. Gibt `[]` zurück, wenn diese Phase keine Flüssigkeit erfordert oder die Kolonie bereits in der Phase „Reichlich“ ist. Nutze den Wert zusammen mit `next_required_liquid()`."""
        ...
    def carrying_capacity(self) -> _int:
        """Die aktuelle Populationsobergrenze der Kolonie. Die Population wächst bis zu dieser Grenze und bleibt dann konstant; eine Kolonie an der Obergrenze verbraucht nichts. In früheren Lebensphasen steigt mit jedem Aufstieg die Grundkapazität, aber „Gedeihend“ und „Zahlreich“ haben beide einen Grundwert von **175.000**. Habitat Mk II verdoppelt den Grundwert; Überbelegung kann die aktuelle Obergrenze senken. Anpassungen ändern die Kapazität nie. Gibt **0** zurück, wenn das Habitat leer ist."""
        ...
    def headroom(self) -> _int:
        """Anzahl der Individuen, die bis zur aktuellen Obergrenze noch gezüchtet werden können (`carrying_capacity() - population()`, mindestens **0**). **0** bedeutet, dass diese Kolonie ihre Obergrenze erreicht hat und im Leerlauf ist. Baue ein Habitat Mk I in der Phase „Gedeihend“ auf Mk II aus, damit die Schwelle von **175.001** für „Zahlreich“ erreichbar wird. Verringere die Überbelegung, wenn sie die Obergrenze unter eine Phasenschwelle senkt. Ist eine Kolonie in der Phase „Zahlreich“ an ihrer Obergrenze, vermehre eine andere Art."""
        ...
    def next_stage_population(self) -> _int:
        """Die genaue Population, die die nächste Lebensphase eröffnet: **250**, **2.500**, **25.000** oder **175.001**. Gibt **0** zurück, wenn das Habitat leer ist oder die Kolonie bereits in der Phase „Zahlreich“ ist. Mk I ist bei **175.000** ausgeschöpft; für die Phase „Zahlreich“ ist daher Mk II erforderlich. Vergleiche den Wert mit `population()`, damit dein Skript die nächste Versorgung vor dem Übergang vorbereiten kann."""
        ...
    def next_requirement(self) -> Literal["capacity", "gas", "liquid", "switch_gas", "switch_liquid", "tighter_bands", "none"]:
        """Was sich in der nächsten Lebensphase der Kolonie ändert: `\"capacity\"`, `\"gas\"`, `\"liquid\"`, `\"switch_gas\"`, `\"switch_liquid\"`, `\"tighter_bands\"` oder `\"none\"` in der Phase „Reichlich“. Nutze den Wert zusammen mit `next_stage_population()`, um zu erfahren, wann der Übergang stattfindet und was du vorbereiten musst."""
        ...
    gas_in: FluidPort
    liquid_in: FluidPort
    input: InputSlot
    reagents: InputSlot
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

## `HabitatBonusNode`

```python
class HabitatBonusNode:
    """Habitat.get_bonus_tree().nodes und Habitat.get_active_bonuses()"""
    id: _str
    source_species: _str
    slot: Literal["adaptation", "breakthrough"]
    scope: Literal["species", "global"]
    depth: _int
    name: _str
    description: _str
    state: Literal["purchased", "available", "unaffordable", "population_locked"]
    purchased: _bool
    active: _bool
    insight_cost: _int
    local_population: _int
    unmet: _list[_str]
```

## `HabitatBonusTree`

```python
class HabitatBonusTree:
    """Habitat.get_bonus_tree()"""
    species: _str
    shared_insight: _float
    purchased_count: _int
    nodes: _list[HabitatBonusNode]
```

## `HabitatInsight`

```python
class HabitatInsight:
    """Habitat.get_insight()"""
    shared: _float
    shared_exact: _float
    rate_per_hour: _float
    lifetime_produced: _float
    producing: _bool
```

## `HarvestingMachineRef`

```python
class HarvestingMachineRef:
    """outpost.harvesting_machines() / outpost_network.home().harvesting_machines()"""
    id: _str
    name: _str
    type_id: Literal["grow_lamp", "sprinkler", "dispenser", "crop_automator"]
    powered: _bool
    position: _str
```

## `Holder`

```python
class Holder:
    """self.battery.holders()"""
    id: _str
    size: Literal["small", "medium", "large"]
    capacity: _float
    wh: _float
    batteries: _list[PortableBattery | None]
```

## `JobReceipt`

```python
class JobReceipt(Generic[_StatusT]):
    """Einreichen eines Arbeitsauftrags beim Anbauautomaten"""
    status: _StatusT
    message: _str
    job_id: _int | None
    queue_position: _int | None
```

## `Journal`

```python
class Journal(Component):
    """Logbuch: Speichert Orte, die per Sonar gefunden oder vermessen wurden, und Fragmente, die in Biolaboren katalogisiert wurden. Greife mit `get_component(\"journal\")` darauf zu, um Fahrten und Bio-Aufträge zu planen, ohne erneut zu scannen. Die Einträge sind nach Planeten getrennt und bleiben nach Skriptneustarts, Fahrzeugwechseln sowie dem Speichern und Laden erhalten."""
    name: _str
    def discovered_sites(self, planet_id: _str) -> _list[Site]:
        """Listet alle Orte auf `planet_id` auf, die das Sonar eingeordnet hat. Rufe für Nocturna `journal.discovered_sites(\"nocturna\")` auf. Je nach `kind()` ist jeder Eintrag ein `MiningSite`, `ThermalVent`, `WaterWell`, `OilWell`, `ExoticDeposit` oder `GeologicalAnomaly`. Bei noch nicht vermessenen produktiven Orten bleiben die Detailfelder `None`; inaktive Formationen werden durch Scannen bestimmt. Wiederholte Scans erzeugen keine doppelten Einträge. Solange keine Orte gefunden wurden, wird eine leere Liste zurückgegeben. Siehe `Site`."""
        ...
    def surveyed_sites(self, planet_id: _str) -> _list[Site]:
        """Alle vollständig bestimmten Orte auf `planet_id` als `list[Site]`, im selben Format wie bei `discovered_sites()`, gefiltert nach `surveyed == True`. Dazu gehören auch inaktive Kontakte vom Typ `GeologicalAnomaly`, weil das Sonar sie ohne zweite Vermessung bestimmt. Unterscheide mit `kind()` die verfügbaren Felder: `MiningSite` bietet `.item_id`, `.hardness` und `.purity`; `ThermalVent` bietet Phase, Rate und Zykluszeiten (abhängig von der Sonarstufe); `WaterWell` und `OilWell` bieten `.yield_tier` und `.flow_rate`. Siehe `Site`."""
        ...
    def cataloged_fragments(self, planet_id: _str) -> _list[CatalogedFragment]:
        """Listet die in einem Biolabor auf `planet_id` analysierten Fragmente auf, das neueste zuerst. Jedes `CatalogedFragment` enthält eine dauerhafte Fragment-ID, einen Anzeigenamen, ein Biom, Koordinaten und eine Seltenheit. Vergleiche `entry.fragment_id` mit `BioOrder.requires` und übergib `entry.coords` an `bio_collector.collect(...)`. Nicht analysierte Fragmente und die Identität der Kreatur bleiben verborgen. Sobald alle fünf Fragmente katalogisiert sind, erscheint die vollständige Kreatur in `journal.cataloged_creatures(planet_id)`. Für einen anderen Planeten wird eine leere Liste zurückgegeben."""
        ...
    def cataloged_creatures(self, planet_id: _str) -> _list[CatalogedCreature]:
        """Listet Kreaturen auf, deren fünf Fragmente auf `planet_id` vollständig analysiert wurden, die zuletzt vervollständigte zuerst. Jedes `CatalogedCreature` enthält die dauerhafte Kreaturen-ID, die IDs ihrer fünf Fragmente, den benötigten Futtergegenstand samt Rezept des Futterherstellers, die Mindestmenge an Futter für den Start und die genauen, nach Seltenheit gestaffelten Reagenzien für die Wiederbelebung. Verwende `.creature_id` mit `habitat.set_revival_target(...)`. Suche mit `.feed_recipe_id` das passende freigeschaltete `Recipe` in `feed_maker.list_recipes()`; die Rezeptzutaten sind weiterhin in diesem Recipe hinterlegt. Für einen anderen Planeten wird eine leere Liste zurückgegeben."""
        ...
    def coord_info(self, x: _int, y: _int) -> LifeFormScanResult | None:
        """Lies das gespeicherte `LifeFormScanResult` für die Koordinate einer entdeckten dauerhaften Biofundstelle aus. Gibt für unberührte Biofundstellen und gescannte Koordinaten ohne Fundstelle `None` zurück. Die Abfrage liefert das Ergebnis sofort."""
        ...
    def biomass_coords(self) -> _list[LifeFormScanResult]:
        """Listet jede entdeckte dauerhafte Biofundstelle als `LifeFormScanResult` auf. Damit können Harvester-Drohnen auch nach einem Neustart ihre Routen planen: Prüfe vor dem Einsatz `.coord`, `.remaining_tons` jeder Probe und `is_ready(x, y)`."""
        ...
    def has_scanned(self, x: _int, y: _int) -> _bool:
        """`True`, nachdem die ganzzahlige Koordinate `(x, y)` gescannt wurde. Nutze die Abfrage, um Biofundstellen auszulassen, die eine nach einem Skriptneustart fortgesetzte Route bereits besucht hat."""
        ...
    def is_empty(self, x: _int, y: _int) -> _bool:
        """Nur dann `True`, wenn diese Kachel mit ganzzahligen Koordinaten gescannt wurde und keine Lebensformen enthielt. Gibt sowohl für belegte als auch für unberührte Kacheln `False` zurück; verwende die Abfrage daher zusammen mit `has_scanned()`."""
        ...
    def is_ready(self, x: _int, y: _int) -> _bool:
        """`True`, wenn an einer entdeckten Biofundstelle jetzt Material entnommen werden kann. Gibt `False` zurück, während dort eine andere Drohne Material entnimmt, wenn die Fundstelle erschöpft ist oder während ihrer von der Seltenheit abhängigen Abklingzeit. Die Abfrage nutzt den aktuellen Zustand der Fundstelle und liefert das Ergebnis sofort."""
        ...
    def next_ready_at(self, x: _int, y: _int) -> _float | None:
        """Absolute Stunde, zu der die Abklingzeit nach einer Entnahme endet. Der Zeitstempel einer erschöpften Fundstelle bleibt auch nach Ablauf dieser Stunde bestehen, bis sich ihr entnehmbares Material wieder aufgefüllt hat. Gibt `None` zurück, wenn die Biofundstelle nicht erfasst ist, noch Material enthält oder noch nie Material entnommen wurde. Prüfe mit `is_ready(x, y)`, ob jetzt eine Entnahme beginnen kann."""
        ...
```

## `LightningRod`

```python
class LightningRod(Component):
    """Blitzableiter: Eine Notreserve mit **4.000 Wh**, die Blitze im Umkreis von **600 m** auffängt und Strom liefert, wenn die Batterien leer sind. Der Zustand sinkt um **0,05 pro Tag**. Dadurch fällt die aufgefangene Energiemenge schließlich auf null, sofern kein laufendes Skript den Blitzableiter mit **1 Sturmglas** repariert."""
    name: _str
    outpost: OutpostRef
    def bank(self) -> _float:
        """Aktuell gespeicherte Energie in Wh, von **0** bis `capacity()`. Der Wert steigt nur, wenn ein Blitz in Reichweite dieses Blitzableiters einschlägt. Er sinkt automatisch, wenn dem Stromnetz Energie fehlt und die Batterien leer sind. Überschüssiger Strom aus dem Netz lädt die Reserve nie auf."""
        ...
    def capacity(self) -> _float:
        """Speicherkapazität in Wh, ein Mehrfaches der Kapazität einer einfachen Batterie. Frage den Wert ab, statt eine feste Zahl ins Skript zu schreiben."""
        ...
    def last_strike(self) -> _float:
        """Zeitstempel in Stunden für den letzten Blitz, aus dem dieser Blitzableiter Energie aufgenommen hat, oder **-1**, falls es noch keinen gab. Ein Blitz, der keine Energie hinzufügt, etwa weil der Speicher voll oder der Zustand bei null ist, aktualisiert diesen Wert nicht. Vergleiche ihn mit der aktuellen Uhrzeit, um zu sehen, wie lange die letzte Energieaufnahme zurückliegt."""
        ...
    input: InputSlot
    def integrity(self) -> _float:
        """Der Zustand dieses Blitzableiters von **0** bis **1** bestimmt zugleich, wie viel Energie er auffängt. Durch ständige Korrosion sinkt er um **0,05 pro Tag**; Blitze verursachen keinen zusätzlichen Schaden. Bei **0,5** speichert der Blitzableiter die Hälfte der Energie jedes aufgefangenen Blitzes. Bei **0** speichert er nichts mehr, bleibt aber stehen und kann weiterhin repariert werden."""
        ...
    def repair(self) -> ActionResult[Literal["ok", "no_op", "no_material"]]:
        """Stellt den vollen Zustand dieses Blitzableiters wieder her. Ist er abgenutzt, verbraucht ein Aufruf **1 Sturmglas** aus seinem Eingang und setzt den Zustand auf **1**. Bei vollem Zustand wird kein Material verbraucht. Ohne Sturmglas im Eingang bleibt der Zustand unverändert. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
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

## `Loom`

```python
class Loom:
    """.loom"""
    def weave(self, a: _str, b: _str) -> _str:
        """Verflechte zwei Zeichenfolgen zu einer und gib sie zurück. Jedes Zeichen ist ein Token. Das Ergebnis ist deterministisch: Dieselben Eingaben werden immer auf dieselbe Weise verflochten. Du kannst es also bedenkenlos ausprobieren. Ein Argument, das keine Zeichenfolge ist, löst `TypeError` aus; ist eine der Eingaben länger als 30 Zeichen, wird `ValueError` ausgelöst. Der Webstuhl verflicht nur vorwärts; die Umkehrung musst du selbst erstellen."""
        ...
```

## `Marker`

```python
class Marker:
    """markers.get() / markers.list()"""
    id: _str
    x: _float
    y: _float
    label: _str
    note: _str
    icon: Literal["pin", "x", "check", "circle", "flag", "crosshair", "warning", "hammer", "resource", "power", "fluid", "star"]
    color: Literal["neutral", "accent", "success", "warning", "error", "violet"]
```

## `Markers`

```python
class Markers(Component):
    """Kartenmarkierungen: Setzt über deine Skripte Anmerkungen auf die Planetenkarte. Greife nach der Freischaltung der Kartografie mit `get_component(\"markers\")` darauf zu und setze dann mit `markers.place(\"survey.rover_1.empty:120:-40\", 120, -40, \"No contact\", \"x\")` sofort und ohne Fahrzeug oder Material einen Marker an einer beliebigen Stelle der Welt. Marker sind Notizen, keine Baupläne: Wenn du an einem Ort tatsächlich etwas bauen willst, übergib die Koordinaten an `construction_blueprint.plan_structure(...)`. Speichere strukturierte Daten unter derselben ID im Datenarchiv."""
    name: _str
    def place(self, id: _str, x: _float, y: _float, label: _str = ..., icon: _str = ..., color: _str = ..., note: _str = ...) -> ActionResult[Literal["ok", "invalid_key", "invalid_coords", "out_of_bounds", "invalid_icon", "invalid_color", "invalid_text", "limit_reached"]]:
        """Erstellt oder überschreibt einen Marker. Wenn du eine ID erneut verwendest, wird der vorhandene Marker verschoben und sein Aussehen geändert, statt einen zweiten anzulegen. So füllt ein Skript nach dem Laden eines Spielstands die Karte nicht mit Duplikaten. Koordinaten sind Weltkoordinaten in Metern; Nachkommastellen bleiben erhalten. Ordne zusammengehörige Marker über ein gemeinsames ID-Präfix und nimm die steuernde Maschine darin auf, etwa `\"survey.rover_1.\"`, damit zwei Skripte einander nichts überschreiben. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def get(self, id: _str) -> Marker | None:
        """Liest einen Marker anhand seiner ID."""
        ...
    def list(self, prefix: _str = ...) -> _list[Marker]:
        """Liest Marker als nach ID sortierte Liste. Übergib ein Präfix wie `\"build.\"`, um nur eine zusammengehörige Gruppe zu lesen. Durchlaufe das Ergebnis, um ein Fahrzeug zu steuern: `for m in markers.list(\"build.\"): self.nav.set_target(m.x, m.y)`."""
        ...
    def remove(self, id: _str) -> ActionResult[Literal["ok", "not_found", "invalid_key"]]:
        """Löscht einen Marker anhand seiner ID. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def clear(self, prefix: _str) -> CountResult[Literal["ok", "no_op", "invalid_key"]]:
        """Löscht eine ganze Gruppe von Markern anhand ihres ID-Präfixes. Setze anschließend die aktuellen Marker erneut, damit die Gruppe dem Wissensstand deines Skripts entspricht. Das Präfix ist erforderlich: `markers.clear(\"\")` löscht sämtliche Marker auf dem Planeten, auch die von dir manuell gesetzten. Es wird nirgends festgehalten, wer welchen Marker gesetzt hat. Fester Ergebnisvertrag: `CountResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.count`."""
        ...
```

## `MiningSite`

```python
class MiningSite(Site):
    """jede API, die eine Site zurückgibt, bei der `kind() == \"mineral\"` gilt"""
    item_id: Literal["iron_ore", "silicon", "titanium", "cobalt", "rare_earth", "neutronium", "lead_ore"] | None
    hardness: _int | None
    purity: Literal["standard", "rich", "pure"] | None
```

## `MobileUnitRef`

```python
class MobileUnitRef:
    """fleet.mobile_units()"""
    category: Literal["vehicle", "drone"]
    id: _str
    name: _str
    kind: Literal["rover", "pioneer", "drone_small", "drone_medium", "drone_large"]
    status: Literal["idle", "moving", "stranded", "scanning", "surveying", "drilling", "discarding", "constructing", "transferring", "charging", "queued", "being_rescued", "traveling", "refueling", "waiting_service", "waiting_oil", "waiting_bay", "holding_weather", "scrambled", "stalled_no_battery", "stalled_no_oil", "stalled_no_route"]
    x: _float
    y: _float
    def position(self) -> Position:
        """Momentaufnahme der Position zum Zeitpunkt der Rückgabe dieser Referenz."""
        ...
    is_docked: _bool
    is_being_rescued: _bool
    rescue_status: Literal["none", "outbound", "charging", "carrying", "returning"]
```

## `Notebook`

```python
class Notebook(Component):
    """Datenarchiv: Speichert JSON-kompatible Daten, die Skriptneustarts sowie das Speichern und Laden von Spielständen überdauern. Greife nach der entsprechenden Freischaltung durch Forschung mit `get_component(\"notebook\")` auf das Datenarchiv zu. Verwende Bibliotheken, um Code zu teilen, und den Signalbus für gemeinsam genutzte, vorübergehende Live-Daten."""
    name: _str
    def set(self, key: _str, value: JsonValue) -> ActionResult[Literal["ok", "invalid_key", "entry_limit", "invalid_value"]]:
        """Speichert einen JSON-kompatiblen Wert unter einem benannten Schlüssel. Enthaltene Wörterbücher müssen Zeichenfolgen als Schlüssel verwenden. Das Archiv fasst bis zu 2.048 Einträge. Jeder Wert darf höchstens 8 verschachtelte Ebenen, insgesamt 16.384 Knoten einschließlich Werten und Containern sowie 4.096 Zeichen je Zeichenfolge oder Wörterbuchschlüssel enthalten. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def transaction(self, key: _str, default: _J, updater: Callable[[_J], Any]) -> ActionResult[Literal["ok", "invalid_key", "entry_limit", "invalid_value", "busy"]]:
        """Ändert einen gespeicherten Wert atomar innerhalb derselben Grenzen für Archivwerte. Für die Aktualisierung kannst du jede Funktion oder jedes andere aufrufbare Objekt ohne Nebenwirkungen verwenden. Der Updater erhält den neuesten Wert oder den angegebenen Standardwert und darf weder pausieren noch zwischendurch die Kontrolle abgeben oder die Spielwelt verändern. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def get(self, key: _str, default: JsonValue | None = ...) -> JsonValue:
        """Liest einen gespeicherten Wert anhand seines Schlüssels. Fehlt der Schlüssel, wird der optionale Standardwert zurückgegeben; wurde keiner angegeben, wird `None` zurückgegeben. Das Lesen verbraucht oder verändert den Eintrag nicht."""
        ...
    def has(self, key: _str) -> _bool:
        """Gibt `True` zurück, wenn das Archiv den Schlüssel enthält, andernfalls `False`."""
        ...
    def delete(self, key: _str) -> ActionResult[Literal["ok", "not_found", "invalid_key"]]:
        """Entfernt einen Schlüssel. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def keys(self, prefix: _str = ...) -> _list[_str]:
        """Gibt die Schlüssel des Archivs als sortierte Liste zurück. Übergib ein Präfix wie `\"rover.\"`, um nur passende Schlüssel aufzulisten."""
        ...
    def clear(self, prefix: _str = ...) -> CountResult[Literal["ok", "no_op", "invalid_key"]]:
        """Entfernt archivierte Einträge. Ohne Präfix wird das gesamte Archiv geleert; mit einem Präfix werden nur passende Schlüssel entfernt. Fester Ergebnisvertrag: `CountResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.count`."""
        ...
```

## `OilPump`

```python
class OilPump(Component):
    """Ölpumpe: Fördert Öl aus einer erkundeten Quelle mit der Leistungsstufe, die dein Skript festlegt. Ölquellen haben aktive und ruhende Phasen, also puffere die Förderung über einen Flüssigkeitstank, um Trockenphasen zu überbrücken."""
    name: _str
    def well(self) -> OilWell:
        """Die `OilWell`, an der diese Pumpe befestigt ist. Hat dieselbe Struktur wie `WaterWell`: Förderstufe (1×/2×/3×) und Basisdurchfluss."""
        ...
    def pump_rate(self) -> _float:
        """Gesamtrate in t/h, mit der die Pumpe in diesem Tick Öl an alle erreichbaren, angeschlossenen Ziele liefert. Der Wert ist **0**, wenn der Drosselwert **0** beträgt, die Ölquelle ruht oder kein Ziel Öl aufnehmen kann. Mit `is_stalled()` erkennst du, ob die Förderwege blockiert sind oder die Ölquelle ruht."""
        ...
    def well_active(self) -> _bool:
        """Liest die Förderphase der Quelle aus. Bei `True` ist die Quelle darunter aktiv und fördert mit voller Rate. Bei `False` ruht sie: unabhängig von der Drosselung fließt kein Öl, meist mehrere Stunden lang. Lagere Öl in einem nachgeschalteten Flüssigkeitstank und drossele die Pumpe während der Pause, um Strom zu sparen."""
        ...
    def is_stalled(self) -> _bool:
        """Gibt `True` zurück, wenn die Pumpe bei der letzten Berechnung des Ölflusses Strom hatte, Öl aus ihrer aktiven Quelle verfügbar war und der Drosselwert über 0 lag, sie aber über keinen ihrer angeschlossenen Wege Öl fördern konnte. Eine ruhende Ölquelle, ein Drosselwert von 0 oder fehlender Strom werden nicht als Blockade gemeldet. Gib mit `self.oil_out.connect(...)` ein Ziel an oder lass Verbraucher ihre eigenen `oil_in`-Anschlüsse mit dieser Pumpe verbinden."""
        ...
    def throttle(self) -> _float:
        """Aktuelle Drosselung (**0-1**). Standardmäßig **0**."""
        ...
    def set_throttle(self, rate: _float) -> ActionResult[Literal["ok"]]:
        """Stelle die gesamte Förderrate der Pumpe zu erreichbaren verbundenen Zielen ein (**0-1**). Bei `0` läuft die Pumpe im Leerlauf; bei `1` kann sie die volle Menge der aktiven Quelle fördern, soweit freie Kapazität und Durchsatz es zulassen. Dieser vom Skript gesteuerte Sollwert wird auf `0` zurückgesetzt, wenn das Skript angehalten wird, endet oder einen Fehler auslöst. Lass die Regelschleife daher laufen, solange die Pumpe arbeiten soll. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    oil_out: FluidPort
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

## `OilWell`

```python
class OilWell(Site):
    """jede API, die eine Site zurückgibt, bei der `kind() == \"oil\"` gilt (z. B. `oil_pump.well()`, Sonar- oder Logbuchabfragen)"""
    def yield_tier(self) -> Literal["standard", "rich", "pure"] | None:
        """Einer der Werte `\"standard\"` (**1×**) / `\"rich\"` (**2×**) / `\"pure\"` (**3×**). Bis zur Erkundung `None`. Der Wert berücksichtigt den aktuellen Erkundungsfortschritt, außer bei einem Sonarergebnis von vor der Erkundung: Dort bleibt er `None`. Rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def flow_rate(self) -> _float | None:
        """Maximale Ölförderung in Tonnen pro Stunde: **8 / 16 / 24** bei standardmäßiger / ergiebiger / reiner Lagerstätte. Ölquellen wechseln zwischen aktiven und inaktiven Phasen. Eine inaktive Quelle liefert bei keiner Gasstellung Öl (prüfe `well_active()` der Pumpe). Bis zur Erkundung `None`. Der Wert wird laufend aktualisiert, außer bei einem Sonarergebnis von vor der Erkundung: Dort bleibt er `None`. Rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def has_pump(self) -> _bool:
        """Boolescher Wert: `True`, wenn an dieser Quelle derzeit eine Ölpumpe aufgestellt ist. Ein Sonarergebnis von vor der Erkundung gibt immer `False` zurück. Rufe nach der Erkundung ein neues Objekt ab, um aktuelle Werte zu erhalten."""
        ...
    def pump_id(self) -> _str:
        """Aktuelle Maschinen-ID der Ölpumpe an dieser Quelle oder eine leere Zeichenfolge, wenn keine Pumpe vorhanden ist. Ein Sonarergebnis von vor der Erkundung gibt immer eine leere Zeichenfolge zurück. Rufe nach der Erkundung ein neues Objekt ab, um aktuelle Werte zu erhalten."""
        ...
```

## `Panel`

```python
class Panel:
    """panel (nur in Panel-Skripten). Erstelle eines auf der Seite **Kontrollraum**; siehe `custom_panels`"""
    def card(self, x: _float, y: _float, w: _float, h: _float, title: _str = ...) -> None:
        """Umrandeter Unterabschnitt mit optionaler Titelleiste. Damit gruppierst du zusammengehörige Inhalte optisch; das Aussehen entspricht den Karten der Übersicht.

        `preview
        card(8, 8, 264, 64, \"Section\")
        `
        """
        ...
    def divider(self, x1: _float, y1: _float, x2: _float, y2: _float) -> None:
        """Horizontale oder vertikale Trennlinie in der gedämpften Rahmenfarbe. Damit teilst du ein Panel in optische Bereiche auf.

        `preview
        divider(10, 40, 270, 40)
        `
        """
        ...
    def label(self, x: _float, y: _float, text: _str, style: _str = ..., color: _str = ...) -> None:
        """Text mit semantischer Formatierung. `style` akzeptiert `\"title\"` (hell, fett), `\"caption\"` (gedämpft, Großbuchstaben), `\"muted\"` (zweitrangig) und `\"value\"` (Zahlenanzeige). Standard ist `\"title\"`. Verwende es statt `draw_text`, wenn die Texthierarchie der Übersicht automatisch angewendet werden soll.

        `preview
        label(10, 30, \"OXYGEN\", \"caption\")
        `
        """
        ...
    def status_dot(self, x: _float, y: _float, r: _float, status: _str) -> None:
        """Farbige Scheibe, deren Farbe aus einer Statuszeichenfolge bestimmt wird. Erkannte Werte: `\"running\"` (grün), `\"paused\"` (Warnfarbe), `\"error\"` (Fehlerrot), `\"idle\"` (gedämpft). Akzeptiert auch jede Farbe, die ein `color`-Parameter akzeptiert, etwa `\"success\"` oder `\"#ff8800\"`. Wird mit einem dezenten äußeren Leuchtring dargestellt. Nützlich als Statusanzeige für einzelne Zeilen in Maschinenlisten.

        `preview
        status_dot(0, 0, 5, \"running\")
        `
        """
        ...
    def toggle(self, x: _float, y: _float, on: _bool, label: _str = ..., size: _float = ...) -> None:
        """Grün-grauer Ein/Aus-Schalter in Pillenform, passend zur Ein/Aus-Steuerung der Maschinen in der Übersicht. Dieses Widget zeigt nur den übergebenen Wert `on` an; für ein anklickbares Bedienelement verwende `panel.switch(...)`.

        `preview
        toggle(10, 12, true, \"powered\")
        `
        """
        ...
    def pill(self, x: _float, y: _float, text: _str, color: _str = ..., size: _float = ...) -> None:
        """Abgerundetes Abzeichen mit Text im Stil der Erfolge. Die Farbe akzeptiert Theme-Tokens (`\"accent\"`, `\"success\"`, `\"warning\"`, `\"error\"`, `\"text-muted\"`) oder Hex-Werte. Verwende es für Statusbeschriftungen oder Kategorie-Tags.

        `preview
        pill(10, 22, \"earned\", \"success\")
        `
        """
        ...
    def counter(self, x: _float, y: _float, value: object, label: _str = ..., size: _float = ..., color: _str = ...) -> None:
        """Kennzahlenblock mit großer Zahl: großer Wert oben, kleine Beschriftung in Großbuchstaben darunter. Verwende ihn für wichtige Kennzahlen (Credits, Tageszähler, Barrenbestand). `size` ist standardmäßig **24**.

        `preview
        counter(16, 38, 87, \"shipped\", 26)
        `
        """
        ...
    def progress_bar(self, x: _float, y: _float, w: _float, h: _float, fraction: _float, color: _str = ...) -> None:
        """Horizontaler Füllbalken mit Hintergrundspur und farbiger Füllung. `fraction` wird auf **0-1** begrenzt. Die Farbe ist standardmäßig `\"accent\"`; verwende `\"success\"`, `\"warning\"` oder `\"error\"` für Ampelsignale.

        `preview
        progress_bar(0.72, \"success\")
        `
        """
        ...
    def vertical_bar(self, x: _float, y: _float, w: _float, h: _float, fraction: _float, color: _str = ...) -> None:
        """Vertikaler Füllbalken, der sich von unten nach oben füllt. Für `fraction` und die Farbe gelten dieselben Regeln wie bei `progress_bar`. Verwende ihn, wenn das Panel-Layout eine vertikale Anordnung begünstigt (mehrere Tanks übereinander, gestapelte Atmosphärenwerte).

        `preview
        vertical_bar(110, 10, 30, 60, 0.6)
        `
        """
        ...
    def bar_chart(self, x: _float, y: _float, w: _float, h: _float, values: _list[_float], max: _float = ..., labels: _list[_str] = ..., color: _str = ...) -> None:
        """Balkendiagramm zum Vergleichen mehrerer Werte, mit abwechselnden Theme-Farben und optionalen Beschriftungen unter jedem Balken. `max` ist optional; ohne Angabe wird die Skala am größten Wert ausgerichtet. Mit `color` erhalten stattdessen alle Balken dieselbe Farbe.

        `preview
        bar_chart(0, 0, 0, 0, [42, 80, 26, 61, 95], 100)
        `
        """
        ...
    def gauge(self, x: _float, y: _float, radius: _float, fraction: _float, label: _str = ..., color: _str = ...) -> None:
        """Dreiviertelkreisförmige Anzeige mit gefülltem Bogen. `fraction` wird auf **0-1** begrenzt und füllt den Bogen über **270°** von links unten über oben nach rechts unten. Eine optionale Beschriftung in der Mitte zeigt meist den Wert als Text. Die Bogenfarbe ist standardmäßig `\"accent\"`; verwende `\"success\"`, `\"warning\"` oder `\"error\"` für Ampelfarben.

        `preview
        gauge(140, 50, 32, 0.62, \"62%\")
        `
        """
        ...
    def spark_line(self, x: _float, y: _float, w: _float, h: _float, values: _list[_float], color: _str = ..., axis: _bool = ...) -> None:
        """Kompakte Trendlinie aus einer Zahlenreihe. Du sammelst Werte in einer Liste und fügst bei jedem Tick den neuesten hinzu. Das Widget skaliert sie auf den Bereich zwischen dem kleinsten und größten Wert der Reihe und füllt die Fläche unter der Linie dezent aus. Linie und Schattierung verwenden standardmäßig `\"accent\"`; mit `color` änderst du beide. Übergib für `axis` den Wert `True`, um am linken Rand den oberen, mittleren und unteren Skalenwert zu beschriften. Die Linie rückt zur Seite, um Platz zu schaffen. Bei einer leeren Reihe oder nur einem Wert passiert nichts.

        `preview
        spark_line(0, 0, 0, 0)
        `

        `preview
        spark_line(0, 0, 0, 0, None, \"accent\", True)
        `
        """
        ...
    def button(self, key: _str, x: _float, y: _float, w: _float = ..., h: _float = ..., label: _str = ...) -> _bool:
        """Ein anklickbarer Button. Übergib einen eindeutigen `key`, damit der Klick zu ihm zurückgeleitet wird. Gibt genau in dem einen Tick `True` zurück, in dem er gedrückt wird (Tastfunktion); verwende den Rückgabewert als Bedingung: `if panel.button(\"shed\", 10, 12): power.set_powered(...)`. `w`/`h` sind standardmäßig **90×26**. Das erste Eingabe-Widget, mit dem eine Karte auf deinen Klick *reagieren* kann, statt nur zu zeichnen.

        `preview
        button(10, 12, 90, 26, \"shed now\")
        `
        """
        ...
    def switch(self, key: _str, x: _float, y: _float, default_on: _bool = ..., label: _str = ..., size: _float = ...) -> _bool:
        """Ein interaktiver Ein/Aus-Schalter, den du per Klick umlegst. Übergib einen eindeutigen `key`; `default_on` legt den Anfangszustand fest, wenn die Karte zum ersten Mal läuft. Gibt in jedem Tick den aktuellen booleschen Wert zurück, und die Schalterstellung wird im Zustand der Karte gespeichert, sodass sie auch nach dem Neuladen erhalten bleibt. Anders als die Anzeige `toggle` (die nur einen übergebenen Zustand darstellt) ist dieser Schalter anklickbar: `auto = panel.switch(\"auto_recover\", 165, 128, True)`.

        `preview
        switch(10, 12, true, \"auto-recover\")
        `
        """
        ...
    def slider(self, key: _str, x: _float, y: _float, w: _float, default: _float = ..., label: _str = ..., size: _float = ...) -> _float:
        """Ein horizontaler Schieberegler, mit dem du per Klick einen Wert einstellst. Übergib einen eindeutigen `key`; `default` (**0-1**) legt den Anfangswert fest. Gibt in jedem Tick den aktuellen Wert als Zahl im Bereich **0-1** zurück, gespeichert im Zustand der Karte. Verwende ihn für Schwellenwerte, die du live anpasst, etwa eine Kaufschwelle oder einen Drosselungszielwert.

        `preview
        slider(10, 14, 120, 0.5, \"rate\")
        `
        """
        ...
    def checkbox(self, key: _str, x: _float, y: _float, default_on: _bool = ..., label: _str = ..., size: _float = ...) -> _bool:
        """Eine Checkbox zum Anklicken. Sie teilt sich den gespeicherten Zustand mit `panel.switch(...)`, daher steuert `set_switch` beide; der Unterschied ist nur die Form. Übergib einen eindeutigen `key`; `default_on` legt den Startzustand fest, wenn die Karte zum ersten Mal läuft.

        `preview
        checkbox(10, 12, true, \"night mode\")
        `
        """
        ...
    def radio_group(self, key: _str, x: _float, y: _float, options: _list[_str], default: _str | _int = ..., row_height: _float = ...) -> _str | None:
        """Eine Auswahl aus mehreren Optionen, eine Option pro Zeile. Die ganze Gruppe teilt sich einen einzigen `key`, deshalb kosten fünf Optionen die Karte nur einen gespeicherten Wert statt fünf: Baust du Radio-Buttons aus fünf einzelnen Schaltern, bleiben fünf Schlüssel zurück. Gibt in jedem Tick den Text der gewählten Option zurück und `None`, solange `options` leer ist. `default` akzeptiert den Text der Option oder ihre Zeilennummer.

        `preview
        radio_group(10, 6, [\"ore\", \"ingots\", \"both\"], 1)
        `
        """
        ...
    def combo(self, key: _str, x: _float, y: _float, w: _float, options: _list[_str], default: _str | _int = ..., label: _str = ..., size: _float = ...) -> _str | None:
        """Ein Dropdown-Menü. Ein Klick darauf öffnet das spieleigene Menü über der Karte, sodass die Optionen bei jeder Kartengröße lesbar bleiben und nie vom Rand des Panels abgeschnitten werden. Gibt in jedem Tick den Text der gewählten Option zurück und `None`, solange `options` leer ist. `default` akzeptiert den Text der Option oder ihre Zeilennummer.

        `preview
        combo(10, 12, 150, \"iron_ingot\", \"recipe\")
        `
        """
        ...
    def text_field(self, key: _str, x: _float, y: _float, w: _float, default: _str = ..., placeholder: _str = ..., label: _str = ..., size: _float = ...) -> _str:
        """Ein einzeiliges Textfeld. Ein Klick darauf öffnet einen echten Texteditor über dem Feld, sodass Markieren, Kopieren, Einfügen und die Eingabemethode deiner Tastatur funktionieren; die Karte zeigt den bestätigten Wert an. Gibt in jedem Tick den aktuellen Text zurück. Bis zu 1024 Zeichen, die mit der Karte gespeichert werden.

        `preview
        text_field(10, 12, 180, \"outpost_north\", \"name...\")
        `
        """
        ...
    def list(self, key: _str, x: _float, y: _float, w: _float, h: _float, items: _list[_str], row_height: _float = ...) -> _str | None:
        """Eine scrollbare Liste von Zeilen, aus denen der Spieler eine auswählen kann. Zeilen, die über die Höhe des Felds hinausgehen, lassen sich mit dem Mausrad scrollen; die gewählte Zeile wird mit der Karte gespeichert und in jedem Tick zurückgegeben, oder `None`, solange `items` leer ist. Nutze sie, wenn eine Karte mehr Einträge als Platz hat, was auf die meisten Flotten- und Inventarübersichten zutrifft.

        `preview
        list(10, 6, 160, 68, [\"rover_1\", \"pioneer_1\", \"drone_1\", \"drone_2\"], 0)
        `
        """
        ...
    def icon_button(self, key: _str, x: _float, y: _float, size: _float, item_id: _str) -> _bool:
        """Ein quadratischer Button, der statt einer Beschriftung ein Gegenstandssymbol zeigt. Gibt genau in dem einen Tick `True` zurück, in dem er gedrückt wird, genau wie `panel.button(...)`. Nutze ihn für eine Werkzeugleiste, in die kein Wort passen würde. `panel.icon_ids()` listet jede ID auf, die er zeichnen kann.

        `preview
        icon_button(10, 8, 44, \"iron_ingot\")
        `
        """
        ...
    def set_switch(self, key: _str, on: _bool) -> None:
        """Setzt einen Schalter oder eine Checkbox per Code auf einen Zustand, statt darauf zu warten, dass der Spieler klickt. Damit kannst du eine Radio-Button-Gruppe aus Schaltern bauen, ein Cockpit auf ein bekanntes Layout zurücksetzen oder einen Zustand anzeigen, den die Karte aus der Welt gelesen hat.

        `
        if not power.is_online():
          panel.set_switch(\"auto_dispatch\", False)
        `
        """
        ...
    def set_slider(self, key: _str, value: _float) -> None:
        """Setzt einen Schieberegler per Code auf einen Wert (0 bis 1)."""
        ...
    def set_selected(self, key: _str, option: _str | _int) -> None:
        """Setzt eine Radio-Button-Gruppe, ein Dropdown-Menü oder eine Liste per Code auf eine Auswahl. Akzeptiert den Text der Option oder ihre Zeilennummer."""
        ...
    def set_text(self, key: _str, text: _str) -> None:
        """Setzt den Inhalt eines Textfelds per Code."""
        ...
    def get_switch(self, key: _str) -> _bool | None:
        """Der gespeicherte Zustand eines Schalters oder Kontrollkästchens, ohne das Steuerelement zu zeichnen. Verwende ihn für ein Steuerelement auf einer Seite, die die Karte gerade nicht anzeigt. Gibt `None` zurück, solange für den Schlüssel kein Zustand gespeichert ist."""
        ...
    def get_slider(self, key: _str) -> _float | None:
        """Der gespeicherte Wert (0-1) eines Schiebereglers, ohne ihn zu zeichnen. Gibt `None` zurück, solange für den Schlüssel kein Wert gespeichert ist."""
        ...
    def get_selected(self, key: _str) -> _int | None:
        """Die gespeicherte Zeilennummer einer Optionsgruppe, eines Kombinationsfelds oder einer Liste, ohne das Steuerelement zu zeichnen. Schlage sie in derselben Optionsliste nach, mit der du das Steuerelement zeichnest. Gibt `None` zurück, solange für den Schlüssel keine Auswahl gespeichert ist."""
        ...
    def get_text(self, key: _str) -> _str | None:
        """Der gespeicherte Text eines Textfelds, ohne es zu zeichnen. Gibt `None` zurück, solange für den Schlüssel kein Text gespeichert ist."""
        ...
    def forget(self, key: _str) -> None:
        """Verwirft einen einzelnen gespeicherten Widget-Wert. Beim nächsten Zeichnen startet dieses Widget wieder mit seinem angegebenen Standardwert; so setzt eine Karte ein einzelnes Bedienelement zurück, ohne die anderen zu verändern."""
        ...
    def clear_inputs(self) -> None:
        """Verwirft alle gespeicherten Widget-Werte dieser Karte. Widget-Schlüssel werden nie automatisch aufgeräumt, weil eine Karte, die immer nur eine Seite zeichnet, sonst den Zustand der anderen Seite verlieren würde; dies ist das bewusste Zurücksetzen. Eine Karte kann höchstens 512 gespeicherte Schlüssel haben, und gerade Schlüssel, die aus sich ändernden Daten gebildet werden (ein Tick-Zähler, ein wechselnder Name), erreichen diese Grenze."""
        ...
    def mouse(self) -> PanelMouse:
        """Die Position des Mauszeigers auf dieser Karte, im selben Koordinatensystem, in dem du zeichnest. `over` ist `False`, solange sich der Mauszeiger außerhalb befindet. Die Position wird einmal pro Tick erfasst. Eine daraus gezeichnete Hervorhebung folgt dem Mauszeiger daher um etwa einen Frame verzögert. `pressed` gibt an, ob die linke Maustaste seit deinem letzten Aufruf auf dieser Karte gedrückt wurde. `released` gibt an, ob sie seit deinem letzten Aufruf wieder losgelassen wurde, auch außerhalb der Karte. Jedes Ereignis wird nur einmal geliefert, also lies die Maus einmal pro Frame aus. Zusammen ermöglichen sie das Ziehen von Elementen auf einer Karte.

        `
        m = panel.mouse()
        if m.over and m.x < panel.width() / 2:
          panel.fill_rect(0, 0, panel.width() / 2, panel.height(), \"bg-surface\")
        `
        """
        ...
    def clicks(self) -> _list[PanelClick]:
        """Alle Klicks seit deiner letzten Abfrage, die kein Widget getroffen haben, die ältesten zuerst. Damit kann eine Karte selbst auswerten, welcher Teil ihrer eigenen Zeichnung getroffen wurde: eine Landkarte, ein Diagramm, ein Sitzplan. Jeder Klick wird nur einmal ausgegeben. Zwischen zwei Abfragen werden bis zu 32 aufbewahrt.

        `
        for c in panel.clicks():
          if c.x > 250:
            print(\"right half\", c.x, c.y)
        `
        """
        ...
    def capture_keys(self) -> None:
        """Fordert die Tastatur an. Danach erhält die Karte beim Anklicken den Fokus, und ihre Tastendrücke gehen an `panel.keys()` statt an die Tastenkürzel des Spiels; Esc oder ein Klick woandershin gibt die Tastatur wieder zurück. Rufe es einmal oberhalb deiner Schleife auf. Eine Karte, die es nie aufruft, kann nie eine Taste empfangen."""
        ...
    def keys(self) -> _list[PanelKey]:
        """Alle Tasten, die seit deiner letzten Abfrage gedrückt wurden, die ältesten zuerst, für eine Karte, die `panel.capture_keys()` aufgerufen hat und den Fokus hält. Jeder Tastendruck wird nur einmal ausgegeben. Zwischen zwei Abfragen werden bis zu 32 aufbewahrt.

        `
        panel.capture_keys()
        while True:
          panel.clear()
          for k in panel.keys():
            if k.key == \"ArrowUp\":
              cursor = cursor - 1
        `
        """
        ...
    def draw_text(self, x: _float, y: _float, text: _str, size: _float = ..., color: _str = ..., wrap: _float = ...) -> None:
        """Text in Monospace-Schrift in der angegebenen Größe. Das optionale `wrap` (Breite in Pixeln) bricht den Text wortweise in einen mehrzeiligen Block um, wobei jede Zeile so weit wie möglich gefüllt wird; nützlich für Log-Feeds und Auftragsbeschreibungen. Die Farbe akzeptiert Theme-Tokens oder Hex-Werte.

        `preview
        draw_text(10, 24, \"Hello, panel.\", 14, \"text-bright\")
        `
        """
        ...
    def icon_ids(self) -> _list[_str]:
        """Sortierte Liste aller IDs, die `draw_icon` darstellen kann. Sie umfasst mehr als die Gegenstände, die du besitzen kannst: Auch Flüssigkeiten, Kreaturen, Essenzen und Maschinengrafiken haben Symbole. Verwende sie, um eine Auswahl zu bauen oder eine ID vor dem Zeichnen zu prüfen, oder gib den Katalog einfach einmal aus, während du eine Karte schreibst.

        `
        for icon in panel.icon_ids():
          print(icon)
        `
        """
        ...
    def draw_icon(self, x: _float, y: _float, item_id: _str, size: _float = ...) -> None:
        """Zeichnet ein beliebiges Symbol aus dem Gegenstandskatalog des Spiels in der gewünschten Größe (standardmäßig **32** Pixel). Die Gegenstands-ID ist derselbe String, den du an die APIs von `inventory` / `storage_bin` übergibst (`\"iron_ore\"`, `\"iron_ingot\"`, `\"water\"` usw.), dazu kommen Dinge, die du nie besitzt, etwa Flüssigkeiten und Kreaturen. `panel.icon_ids()` gibt die vollständige Liste zurück, und jeder Gegenstand hat unter **Datenbank** in diesem Panel eine eigene Seite. Unbekannte IDs werden stillschweigend ignoriert.

        `preview
        draw_icon()
        `
        """
        ...
    def draw_rect(self, x: _float, y: _float, w: _float, h: _float, color: _str = ..., width: _float = ...) -> None:
        """Umrandetes Rechteck in der angegebenen Farbe (standardmäßig `\"border\"`). Verwende es für eigene Rahmen um Unterabschnitte oder als optischen Rahmen.

        `preview
        draw_rect(10, 10, 260, 60, \"accent\")
        `
        """
        ...
    def fill_rect(self, x: _float, y: _float, w: _float, h: _float, color: _str = ...) -> None:
        """Gefülltes Rechteck in der angegebenen Farbe (standardmäßig `\"accent\"`). Verwende es für Hintergründe, Fortschrittsfüllungen und Farbflächen.

        `preview
        fill_rect(10, 10, 260, 60, \"success\")
        `
        """
        ...
    def draw_circle(self, x: _float, y: _float, r: _float, color: _str = ..., width: _float = ...) -> None:
        """Umrandeter Kreis in der angegebenen Farbe.

        `preview
        draw_circle(140, 40, 24, \"accent\")
        `
        """
        ...
    def fill_circle(self, x: _float, y: _float, r: _float, color: _str = ...) -> None:
        """Gefüllte Kreisscheibe in der angegebenen Farbe.

        `preview
        fill_circle(140, 40, 24, \"warning\")
        `
        """
        ...
    def draw_line(self, x1: _float, y1: _float, x2: _float, y2: _float, color: _str = ..., width: _float = ...) -> None:
        """Eine einzelne gerade Linie.

        `preview
        draw_line(10, 40, 270, 40, \"accent\")
        `
        """
        ...
    def draw_polygon(self, points: _list[_float], color: _str = ..., width: _float = ...) -> None:
        """Umriss einer geschlossenen Form durch eine flache Liste von Koordinaten: `[x1, y1, x2, y2, ...]`. Braucht mindestens zwei Punkte. Bis zu 4096 Punkte pro Aufruf.

        `preview
        draw_polygon([40, 10, 120, 30, 100, 70, 30, 60], \"accent\")
        `
        """
        ...
    def fill_polygon(self, points: _list[_float], color: _str = ...) -> None:
        """Gefüllte geschlossene Form durch eine flache Liste von Koordinaten. Gleiche Eingabe wie bei `draw_polygon`.

        `preview
        fill_polygon([40, 10, 120, 30, 100, 70, 30, 60], \"success\")
        `
        """
        ...
    def polyline(self, points: _list[_float], color: _str = ..., width: _float = ...) -> None:
        """Offene Linie durch eine flache Liste von Koordinaten, mit optionaler Linienstärke. Nutze sie für einen Pfad, eine Route oder eine Diagrammkurve, die dein eigener Code berechnet hat.

        `preview
        polyline([10, 60, 60, 20, 110, 50, 160, 15, 210, 40], \"accent\", 2)
        `
        """
        ...
    def texture(self, key: _str, rows: _list[_str], palette: _dict[_str, _str | None]) -> None:
        """Erstellt ein kleines Bild, das du mit `draw_texture` zeichnen kannst. `rows` enthält das Bild, mit einer Zeichenfolge pro Zeile. Jedes Zeichen wird in `palette` nachgeschlagen, wo ihm eine Hexfarbe oder `None` für ein transparentes Pixel zugeordnet ist. Alle Zeilen sind gleich lang; das Bild ist höchstens **128** mal **128** Pixel groß. Wenn du denselben Schlüssel erneut verwendest, wird die zugehörige Textur ersetzt. Eine Karte kann bis zu **32** Texturen mit insgesamt **131.072** Pixeln enthalten. Texturen gehören zum laufenden Skript. Erstelle sie deshalb am Anfang, vor deiner Schleife.

        `
        panel.texture(\"floor\", [
          \"abab\",
          \"baba\",
        ], {\"a\": \"#1b2230\", \"b\": \"#26314a\"})
        `
        """
        ...
    def draw_texture(self, key: _str, x: _float, y: _float, w: _float = ..., h: _float = ...) -> None:
        """Zeichnet eine mit `panel.texture()` erstellte Textur. Ohne `w` und `h` wird sie in ihrer ursprünglichen Größe gezeichnet. Mit diesen Parametern wird sie gestreckt, wobei ihre Pixel scharf bleiben. So kann eine kleine Kachel die ganze Karte ausfüllen.

        `
        panel.draw_texture(\"floor\", 0, 0, panel.width(), panel.height())
        `
        """
        ...
    def clip_rect(self, x: _float, y: _float, w: _float, h: _float) -> None:
        """Beschränkt alle folgenden Zeichenaufrufe auf ein Rechteck, bis `clear_clip()` aufgerufen wird. So bleibt eine scrollende oder übergroße Zeichnung in ihrem Feld. Ein Widget, das innerhalb eines Clipping-Bereichs gezeichnet wird, nimmt Klicks nur dort an, wo es sichtbar ist; ein vollständig abgeschnittenes Widget nimmt also gar keine an. Clipping-Bereiche lassen sich bis zu 16 Ebenen tief verschachteln; noch offene werden automatisch geschlossen, wenn der Frame fertig ist.

        `
        panel.clip_rect(10, 10, 200, 80)
        panel.draw_text(12, 30, long_line, 12)
        panel.clear_clip()
        `
        """
        ...
    def clear_clip(self, all: _bool = ...) -> None:
        """Schließt den innersten `clip_rect`-Bereich oder alle offenen, wenn `True` übergeben wird."""
        ...
    def clear(self) -> None:
        """Löscht die Zeichenfläche des Panels und damit den klickbaren Bereich jedes Widgets. Rufe es am Anfang jedes Durchlaufs der `while True:`-Schleife auf, damit alte Zeichnungen nicht hinter neuen durchscheinen. Innerhalb eines `clip_rect` löscht es nur den Clipping-Bereich, und nur die dabei gelöschten Widgets nehmen keine Klicks mehr an."""
        ...
    def last_bounds(self) -> PanelBounds | None:
        """Das Rechteck des zuletzt gezeichneten Widgets mit `.x`, `.y`, `.w` und `.h`. `.x` und `.y` bezeichnen seine linke obere Ecke, unabhängig davon, über welchen Punkt das Widget platziert wurde. So kannst du das nächste Widget hinter einem Widget platzieren, dessen Größe vom Text abhängt, etwa einem `pill` oder `draw_text`, ohne dessen Breite zu schätzen. Gibt `None` zurück, bis die Karte ihr erstes Widget zeichnet.

        `
        panel.pill(10, 10, \"online\", \"success\")
        b = panel.last_bounds()
        panel.pill(b.x + b.w + 6, 10, \"docked\")
        `
        """
        ...
    def measure_text(self, text: _str, size: _float = ..., wrap: _float = ...) -> PanelSize:
        """Die Größe, die `draw_text` diesem Text geben würde, als `.w` und `.h`, ohne ihn zu zeichnen. Übergib dieselben Werte für `size` und `wrap`, die du beim Zeichnen verwenden wirst. So kannst du Text vor dem Zeichnen rechtsbündig ausrichten oder zentrieren.

        `
        s = panel.measure_text(\"42 kWh\", 14)
        panel.draw_text(panel.width() - s.w - 10, 20, \"42 kWh\", 14)
        `
        """
        ...
    def width(self) -> _int:
        """Aktuelle logische Breite der Zeichenfläche in Pixeln: **500** bei einer einspaltigen Karte oder **1000** bei einer zweispaltigen. Nützlich für proportionale Positionierung."""
        ...
    def height(self) -> _int:
        """Aktuelle logische Höhe der Zeichenfläche in Pixeln: **200** bei einer einzeiligen Karte oder **400** bei einer zweizeiligen. Nützlich für proportionale Positionierung."""
        ...
```

## `PanelBounds`

```python
class PanelBounds:
    """`panel.last_bounds()` (nur Panel-Skripte)"""
    x: _float
    y: _float
    w: _float
    h: _float
```

## `PanelClick`

```python
class PanelClick:
    """`panel.clicks()` (nur in Panel-Skripten)"""
    x: _float
    y: _float
```

## `PanelKey`

```python
class PanelKey:
    """`panel.keys()` (nur in Panel-Skripten)"""
    key: _str
    ctrl: _bool
    shift: _bool
    alt: _bool
    meta: _bool
```

## `PanelMouse`

```python
class PanelMouse:
    """`panel.mouse()` (nur in Panel-Skripten)"""
    x: _float
    y: _float
    over: _bool
    pressed: _bool
    released: _bool
```

## `PanelSize`

```python
class PanelSize:
    """`panel.measure_text()` (nur Panel-Skripte)"""
    w: _float
    h: _float
```

## `Pipe`

```python
class Pipe:
    """list_pipes() / get_pipe(pipe_id)"""
    id: _str
    def start(self) -> Position | None:
        """Geometrische Startkoordinate dieses Rohrstücks als `Position`. Sie beschreibt die Baugeometrie, nicht die Fließrichtung. Gibt `None` nur zurück, wenn ein fehlerhafter Zustand keine Segmentgeometrie enthält."""
        ...
    def end(self) -> Position | None:
        """Geometrische Endkoordinate dieses Rohrstücks als `Position`. Sie beschreibt die Baugeometrie, nicht die Fließrichtung. Gibt `None` nur zurück, wenn ein fehlerhafter Zustand keine Segmentgeometrie enthält."""
        ...
    def type(self) -> Literal["gas", "liquid"]:
        """Für das Rohr ausgelegtes Medium: `\"gas\"` oder `\"liquid\"`. Mit `contents()` erhältst du den konkreten Stoff, der durch vollständige Erzeuger-Verbraucher-Verbindungen bestimmt wurde."""
        ...
    def contents(self) -> Literal["steam", "water", "oil", "frozen_essence", "coastal_essence", "geothermal_essence", "volcanic_essence", "deep_essence", "ammonia", "swamp_gas", "raw_sulfur_gas", "sulfur_gas", "raw_chlorine", "chlorine", "brine", "raw_cryofluid", "cryofluid", "raw_quicksilver", "quicksilver"] | None:
        """Der eine konkrete Stoff, den vollständige Verbindungen des Spielers an den von dieser physischen Komponente erreichbaren Stellen festlegen, etwa `\"steam\"`, `\"water\"` oder `\"oil\"`. Gibt `None` zurück, wenn keine vollständige Verbindung besteht oder mehrere konkrete Stoffe miteinander in Konflikt stehen. Aktivität, Stromversorgung, Drosselung, Durchfluss und freie Kapazität ändern diese Zuordnung nicht."""
        ...
    def conflicting_contents(self) -> _list[_str]:
        """Sortierte Liste der konkreten Stoffe, die durch vollständige Erzeuger-Verbraucher-Verbindungen bestimmt wurden, wenn mehr als ein Stoff diese physische Komponente nutzt; andernfalls eine leere Liste. Eine nicht leere Liste bedeutet, dass der Durchfluss gestoppt ist."""
        ...
    def connections(self) -> _list[_dict[_str, _str]]:
        """Diagnosedaten zu den Maschinenanschlüssen an dieser physischen Komponente. Jedes Dictionary enthält `machine_id`, `port`, `direction`, `fluid` und eine repräsentative `pipe_id` der Komponente. Mit dieser Rohr-ID verbinden Spieler nie direkt etwas."""
        ...
    def incompatible_sinks(self) -> _list[_str]:
        """IDs der direkt angeschlossenen Verbraucher, die `contents()` nicht annehmen können. Diese Verbraucher erhalten nichts; durch kompatible Zweige fließt der Stoff weiter. Live-Abfrage."""
        ...
    def is_complete(self) -> _bool:
        """Boolescher Wert: `True`, sobald der Konstruktor das Rohr fertig verlegt hat und der Durchfluss beginnen kann. Live-Abfrage."""
        ...
    def length(self) -> _int:
        """Gesamtlänge des Rohrs in Metern, summiert über alle horizontalen und vertikalen Segmente."""
        ...
    def laying_head(self) -> _list[_int] | None:
        """`[x, y]`-Koordinaten des aktuellen Verlegekopfs, solange das Rohr unvollständig ist; danach `None`. Live-Abfrage."""
        ...
    def flow_rate(self) -> _float:
        """Tonnen pro Spielweltstunde (`t/h`), die derzeit durch das Rohr fließen. **0**, wenn die Verbindung unvollständig ist, der Durchfluss stockt, die Quelle leer ist oder ein Konflikt besteht. Live-Abfrage."""
        ...
    def state(self) -> Literal["flowing", "stalled", "incomplete", "no_source", "conflict"]:
        """Aktueller Rohrzustand: `\"flowing\"`, `\"stalled\"`, `\"incomplete\"`, `\"no_source\"` oder `\"conflict\"`. Live-Abfrage."""
        ...
```

## `Planet`

```python
class Planet:
    """transmitter.list_planets()"""
    id: _str
    name: _str
    description: _str
```

## `PointOfInterest`

```python
class PointOfInterest:
    """nocturna.points_of_interest()"""
    x: _int
    y: _int
    scanned: _bool
    kind: Literal["unknown", "mineral", "biomass", "thermal", "water", "oil", "exotic", "inert"]
```

## `PortableBattery`

```python
class PortableBattery:
    """self.battery.holders()[...].batteries[...]"""
    id: Literal["portable_battery", "heavy_portable_battery"]
    def level(self) -> _float:
        """Ladezustand als Anteil, **0–1**."""
        ...
    def wh(self) -> _float:
        """Aktuelle Ladung in Wh."""
        ...
    def capacity(self) -> _float:
        """Nennkapazität in Wh."""
        ...
```

## `Rack`

```python
class Rack:
    """self.cargo.racks()"""
    id: _str
    size: Literal["small", "medium", "large"]
    bins: _list[Bin | None]
```

## `Reactor`

```python
class Reactor(Component):
    """Reaktor: Erzeugt mit Brennstäben und Kühlwasser bis zu **5.000 W**. Bei der Hitzestufe **1,0** hält ein Brennstab **72 Stunden**; der Brennstoffverbrauch richtet sich nach der eingestellten Hitzestufe, auch während der Reaktor noch aufheizt oder außerhalb seines effizienten Bereichs arbeitet."""
    name: _str
    outpost: OutpostRef
    def set_heat(self, value: _float) -> ActionResult[Literal["ok"]]:
        """Stellt die Hitzestufe des Reaktors auf einen Wert von **0–1** ein. Werte außerhalb dieses Bereichs werden auf den nächstliegenden Grenzwert begrenzt. Wenn das zugehörige Skript stoppt, wird die Einstellung auf **0** zurückgesetzt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def heat(self) -> _float:
        """Aktuell eingestellte Hitzestufe von **0–1**."""
        ...
    def temperature(self) -> _float:
        """Aktuelle Temperatur in °C. Die Stromerzeugung beginnt bei **300**, erreicht bei **900** ihr Maximum und fällt im roten Bereich von **900–950** wieder auf null. Bei **950** wird der Reaktor wegen Überhitzung automatisch abgeschaltet."""
        ...
    def fuel_level(self) -> _float:
        """Restlebensdauer des aktiven Brennstabs von **0–1**. Bei Hitzestufe **1,0** hält ein voller Brennstab **72 Stunden**; bei geringerer Hitze entsprechend länger. Der nächste Brennstab wird bei Bedarf automatisch aus `input` entnommen."""
        ...
    def power_output(self) -> _float:
        """In diesem Tick ins Stromnetz eingespeiste Leistung in Watt."""
        ...
    def status(self) -> Literal["running", "overheated", "no_fuel", "no_coolant"]:
        """Aktueller Betriebszustand: `running`, `overheated`, `no_fuel` oder `no_coolant`. Nach dem Abkühlen oder sobald die Versorgung wiederhergestellt ist, nimmt der Reaktor den Betrieb automatisch wieder auf."""
        ...
    water_in: FluidPort
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

## `Research`

```python
class Research(Component):
    """Forschung: Prüft den globalen Forschungsfortschritt über `get_component(\"research\")`. Verwende die öffentlichen IDs auf der Forschungsseite, zum Beispiel `\"research_auto_feeders\"`. Von Beginn an verfügbar und schreibgeschützt."""
    name: _str
    def is_unlocked(self, research_id: _str) -> _bool:
        """Gibt `True` nur zurück, wenn `research_id` bekannt und freigeschaltet ist. Für bekannte, aber gesperrte Forschung wird `False` zurückgegeben. Auch eine unbekannte ID ergibt `False`, ohne eine Ausgabe zu erzeugen. So können Skripte jedes Abfrageergebnis selbst verarbeiten."""
        ...
    def unlocked(self) -> _list[_str]:
        """Gibt eine neue Liste der öffentlichen Forschungs-IDs zurück, die freigeschaltet und in der aktuellen Spielversion verfügbar sind. Die Reihenfolge entspricht der festen Registrierung auf der Forschungsseite. Interne Fähigkeits-IDs sind nicht enthalten. Du kannst die Liste ändern, ohne den Spielzustand zu verändern."""
        ...
```

## `RunControl`

```python
class RunControl(Component):
    """Ablaufsteuerung: Untersuche Maschinenskripte, finde gespeicherte Varianten, wende sie an und steuere die Ausführung aus der Ferne. Diese gemeinsame Start-Stopp-Steuerung für Maschinenskripte entspricht den Schaltflächen „Starten“ und „Stoppen“ auf einer Maschinenkarte. Baue damit ein Überwachungsskript, das die Basis beobachtet und bei einer Störung eine andere Maschine abschaltet, ohne deren Skript dauerhaft in einer `sleep`-Schleife zu halten. Dies ist die **Start-Stopp-Steuerung**, getrennt von `power_control` (dem Schutzschalter): `stop` beendet ein Skript und hält es ausgeschaltet, während eine Änderung der Stromversorgung es nur pausiert und später automatisch fortsetzt."""
    name: _str
    def variants(self, machine_id: _str, slot: _int = ...) -> _list[ScriptVariantRef]:
        """Listet die gespeicherten Varianten auf, die für ein bestimmtes Maschinenskript verfügbar sind: seine private Main-Variante und passende gemeinsame Varianten. Der optionale Skriptplatz wird ab null gezählt; der Standardwert ist 0. Die Ergebnisse sind Momentaufnahmen. Wird eine ID angewendet, lädt das System den zuletzt unter dieser ID gespeicherten Code."""
        ...
    def status(self, machine_id: _str, slot: _int = ...) -> RunControlStatus:
        """Zeigt den Ausführungszustand und die zugewiesene Variante eines Maschinenskripts an. Der optionale Skriptplatz wird ab null gezählt; der Standardwert ist 0. Die Ergebnisse sind Momentaufnahmen. Rufe die Methode erneut auf, um aktuelle Informationen zu erhalten."""
        ...
    def apply_variant(self, machine_id: _str, variant_id: _str, slot: _int = ...) -> ActionResult[Literal["ok", "not_found", "no_script", "under_construction", "script_running", "script_paused", "editor_busy", "variant_not_found", "incompatible_variant", "source_too_large"]]:
        """Wendet eine gespeicherte Variante auf ein Maschinenskript an, ohne es zu starten. Die Zielmaschine muss vollständig gebaut sein; ihr Skript muss gestoppt, abgeschlossen oder durch einen Fehler beendet sein. Laufende und pausierte Skripte müssen zuerst gestoppt werden. Ausstehende Änderungen im Editor und ungelöste Konflikte verhindern den Austausch. Beim Wechsel von Main zu einer anderen Variante bleibt Main erhalten. Gemeinsame Varianten kopieren ihren aktuellen Code in das Ziel; spätere Änderungen an anderer Stelle aktualisieren ihn nicht automatisch. Der optionale Slot hat den Standardwert 0. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def is_running(self, machine_id: _str) -> _bool:
        """Gibt `True` zurück, wenn das Skript der angegebenen Maschine aktiv für die Ausführung eingeplant ist, auch während es sich mitten in `sleep` oder einer Aktion befindet. Für pausierte, gestoppte, abgeschlossene oder durch einen Fehler beendete Skripte sowie unbekannte Maschinen-IDs wird `False` zurückgegeben. Frage den Wert vor `start`/`stop` ab, um überflüssige Befehle zu vermeiden."""
        ...
    def stop(self, machine_id: _str) -> ActionResult[Literal["ok", "not_found", "no_script"]]:
        """Stoppt das Skript der angegebenen Maschine wie die Schaltfläche „Stoppen“ auf ihrer Karte: `run.stop(\"o2gen_1\")` beendet das Skript, setzt seine Sollwerte auf Leerlauf und seine aktuellen Messwerte auf null. Der strukturelle Zustand (Rezepte, Fortschritt laufender Vorgänge und geladene Materialien) bleibt erhalten. Der Stopp ist **dauerhaft**, anders als eine Unterbrechung der Stromversorgung: Das Skript setzt sich nicht automatisch fort. Starte es mit `start` erneut. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def start(self, machine_id: _str) -> ActionResult[Literal["ok", "not_found", "no_script", "already_running", "not_powered", "under_construction"]]:
        """Startet das Skript der angegebenen Maschine wie die Schaltfläche „Starten“ auf ihrer Karte von Anfang an: `run.start(\"o2gen_1\")`. Bei einem neuen Start beginnt es wieder in der ersten Zeile und setzt sich nicht mitten im Skript fort. Die Maschine muss mit Strom versorgt und vollständig gebaut sein. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
```

## `RunControlStatus`

```python
class RunControlStatus:
    """run.status()"""
    script_id: _str
    state: Literal["idle", "running", "paused", "error", "completed"]
    variant_id: _str
    variant_name: _str
    modified: _bool
    source_pending: _bool
    editor_busy: _bool
```

## `Scanner`

```python
class Scanner(Component):
    """Scanner: Deckt die Sektoren des Harvester-Rasters rund um die Basis auf, damit der Harvester weiß, wo er sammeln kann. Der Scanner kartiert nur das Raster der Heimatbasis; für die Erkundung des übrigen Planeten ist das Sonar eines Fahrzeugs zuständig."""
    name: _str
    def scan(self, sector: _str) -> ScanResult[Literal["ok", "empty"]]:
        """Scanne mit `self.scan(\"E14\")` einen lokalen Sektor. Der Scan dauert einige Ticks und pausiert das Skript. Ungültig formatierte oder außerhalb des Rasters liegende Sektor-IDs lösen `ValueError` aus. Dieser Scanner für das lokale Raster findet Gegenstände an der Oberfläche, keine planetaren `Site`-Kontakte. Fester Ergebnisvertrag: `ScanResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.id`, `.name` und `.value`."""
        ...
    def get_scanned(self) -> _dict[_str, ScanResult]:
        """Gibt alle bisher gescannten Sektoren als neues dict `{sector_id: ScanResult}` zurück. Durchlaufe es mit `.keys()` / `.values()` / `.items()` oder greife über die Sektor-ID zu: `self.get_scanned()[\"E14\"]`. Jeder Sektor muss nur einmal tatsächlich gescannt werden; diese Information bleibt über Skriptläufe hinweg erhalten. Jeder Aufruf von `get_scanned()` zeigt den aktuellen Inhalt dieser Sektoren, einschließlich der seit dem letzten Aufruf eingesammelten oder abgelegten Gegenstände. Ein bereits in deinem Skript gespeichertes dict oder `ScanResult` aktualisiert sich nicht von selbst. Rufe `get_scanned()` deshalb erneut auf, bevor du das nächste Ziel wählst. Gibt ein leeres dict zurück, wenn noch nichts gescannt wurde."""
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

## `ScriptCommand`

```python
class ScriptCommand:
    """self.peek_command() / self.next_command().command nach status == \"ok\""""
    id: _str
    name: _str
    args: _dict[_str, JsonValue]
    source: Literal["editor", "script", "signal", "system"]
    created_at: _float
    tick: _int | None
```

## `ScriptVariantRef`

```python
class ScriptVariantRef:
    """run.variants()"""
    id: _str
    name: _str
    description: _str
```

## `Shop`

```python
class Shop(Component):
    """Shop: Kauft von der Erde und verkauft an sie. Mit `get_component(\"shop\")` kannst du Überschüsse automatisch verkaufen oder bei Erreichen eines Schwellenwerts einkaufen. Dabei gelten derselbe Katalog und dieselben Preise wie in der Shop-Oberfläche."""
    name: _str
    def sell(self, item_id: _str, quantity: _int = ...) -> SaleResult[Literal["ok", "not_sellable", "no_stock"]]:
        """Verkaufe eine positive ganzzahlige `quantity` von `item_id`; der Standardwert ist **1**. Die gesamte Menge wird in einer Transaktion aus den passenden Inventarplätzen mit den niedrigsten Indizes entnommen. Sind im Inventar weniger Einheiten vorhanden, wird nichts verkauft. Bei Batterien richtet sich der Verkaufserlös nach ihrem Ladestand in Prozent, beträgt aber mindestens **50%** des normalen Werts. Voll geladene Batterien erzielen den vollen normalen Wert. Wenn du eine bestimmte Batterie auswählen möchtest, nutze die Inventarseite. Fester Ergebnisvertrag: `SaleResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.item_id`, `.units` und `.credits`."""
        ...
    def sell_all(self, item_id: _str) -> SaleResult[Literal["ok", "not_sellable", "no_stock"]]:
        """Verkaufe alle Einheiten von `item_id`, die sich gerade im Inventar befinden, in einer Transaktion. Zwischen einzelnen Einheiten gibt es keine Abklingzeit. Jede Batterie wird anhand ihres eigenen verbleibenden Ladestands bewertet: mindestens mit **50%** und bei voller Ladung mit dem vollen normalen Wert. Fester Ergebnisvertrag: `SaleResult`; verzweige anhand von `.status` und lies `.message`. Nutzdatenfelder: `.item_id`, `.units` und `.credits`."""
        ...
    def buy(self, item_id: _str, quantity: _int = ...) -> ActionResult[Literal["ok", "not_found", "locked", "insufficient_credits", "inventory_full"]]:
        """Kaufe eine positive ganzzahlige `quantity` von `item_id`; der Standardwert ist **1**. Du musst dir die gesamte Menge leisten können, und sie muss ins Basisinventar passen. Andernfalls wird nichts berechnet oder geliefert. Einkäufe landen im Basisinventar und werden nicht direkt an eine Maschine oder einen entfernten Außenposten geliefert. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def get_catalogue(self) -> _list[ShopItem]:
        """Alle verfügbaren Katalogeinträge als Liste von `{id, name, cost}`-Objekten. Damit kannst du ein Ziel dynamisch auswählen oder in einem Skript eine gefilterte Auswahl anzeigen. Die Artikel im Shop auf der Erde gehen nie aus; durch Forschung gesperrte Einträge erscheinen nicht."""
        ...
```

## `SignalReceiver`

```python
class SignalReceiver:
    """weather_station.signal_receiver"""
    def transmissions(self) -> _list[SignalTransmission]:
        """Rohe Übertragungen, die diese mit Strom versorgte Station gerade empfängt. Es können mehrere Ereignisse vorliegen. Die Reihenfolge ist stabil, aber Kopien mit derselben Paketnummer sind nicht nach Gültigkeit sortiert. Der Empfänger speichert keinen Verlauf."""
        ...
```

## `SignalTransmission`

```python
class SignalTransmission:
    """SignalReceiver.transmissions()"""
    event_id: _str
    number: _int
    total: _int
    channel: Literal["broadcast", "frozen", "coastal", "geothermal", "volcanic", "deep"]
    data: _str
    checksum: _int
    emitted_at_gh: _float
    expires_at_gh: _float
    source_station_id: _str
```

## `Site`

```python
class Site:
    """SonarModule.scan().sites / SonarModule.survey().site / Abfragen im Logbuch und bei an Fundstellen gebundenen Maschinen"""
    id: _str
    name: _str
    x: _float
    y: _float
    def kind(self) -> Literal["mineral", "thermal", "water", "oil", "exotic", "inert"]:
        """Einer der Werte `\"mineral\"` / `\"thermal\"` / `\"water\"` / `\"oil\"` / `\"exotic\"` / `\"inert\"`. Verwende ihn, um den konkreten Untertyp zu bestimmen: Nach `if site.kind() == \"mineral\":` zeigt der Editor die spezifischen Felder von `MiningSite` für `site` an. `\"inert\"` bedeutet, dass das Sonar eine physische Formation ohne förderbares Signal identifiziert hat."""
        ...
    def position(self) -> Position:
        """`Position`-Momentaufnahme mit den Weltkoordinaten `.x` / `.y`."""
        ...
    surveyed: _bool
```

## `Sprinkler`

```python
class Sprinkler(Component):
    """Sprinkler: Bewässert die vier direkt angrenzenden Feldzellen (direkt darüber, darunter, links und rechts), solange das Gerät Strom und Wasser erhält und eingeschaltet ist. Skripte finden es über `outpost.harvesting_machines()`."""
    name: _str
    def set_enabled(self, enabled: _bool) -> ActionResult[Literal["ok"]]:
        """Schalte die Bewässerung ein oder aus. Bei einem Stromausfall pausiert das Skript, die Einstellung bleibt aber erhalten. Wenn das Maschinenskript gestoppt wird, wird sie auf `False` zurückgesetzt. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def is_enabled(self) -> _bool:
        """`True`, wenn das laufende Skript die Bewässerung eingeschaltet hat."""
        ...
    def is_active(self) -> _bool:
        """`True`, wenn die Bewässerung eingeschaltet ist und Strom sowie Wasser verfügbar sind."""
        ...
    def is_supplied(self) -> _bool:
        """`True`, wenn der Sprinkler eingeschaltet ist, Strom hat und sich Wasser in seinem `water_in`-Puffer befindet. Ist er deaktiviert, ohne Strom oder ohne Wasser, verlieren die abgedeckten Felder den Status `watered`."""
        ...
    def status(self) -> Literal["not_placed", "disabled", "no_power", "no_water", "active"]:
        """Genauer Betriebszustand: `\"not_placed\"`, `\"disabled\"`, `\"no_power\"`, `\"no_water\"` oder `\"active\"`."""
        ...
    def buffer(self) -> _float:
        """Aktueller Füllstand des eingebauten Wasserpuffers als Anteil (**0-1**). Er sinkt während der Bewässerung und wird aus der verbundenen `water_in`-Quelle wieder aufgefüllt."""
        ...
    def tier(self) -> _int:
        """Installierte Stufe (**1-4**). Mk I/II/III/IV ermöglichen einen unterstützten Pflanzenertrag von **1×/2×/4×/8×**, benötigen **5/25/100/500 W** und verbrauchen im Betrieb **2/4/8/16 t/h Wasser**."""
        ...
    def position(self) -> _str:
        """Rastersektor, in dem dieser Sprinkler steht, zum Beispiel `\"E14\"`."""
        ...
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

## `SteamCondenser`

```python
class SteamCondenser(Component):
    """Dampfkondensator: Wandelt eintreffenden Dampf im Massenverhältnis 1:1 in sauberes Wasser um. Ein vom Skript gesteuerter Leistungsregler bestimmt den Spitzendurchsatz von 250 t/h und die Leistungsaufnahme von 150 W."""
    name: _str
    outpost: OutpostRef
    def condensation_rate(self) -> _float:
        """Im letzten Simulationstick erzeugtes sauberes Wasser in t/h. Bei voller Leistung werden **250 t/h** erreicht, wenn am Dampfeingang genug Dampf anliegt, am Wasserausgang Platz ist und der Außenposten, in dem die Maschine steht, nicht überfüllt ist."""
        ...
    def efficiency(self) -> _float:
        """Anteil der für den letzten Tick angeforderten Kondensation, der tatsächlich abgeschlossen wurde (**0.0-1.0**). Niedrige Werte bedeuten, dass am Dampfeingang nicht genug Dampf vorhanden war oder der Wasserausgang vor Ende des Ticks voll wurde."""
        ...
    def is_stalled(self) -> _bool:
        """`True`, wenn der Leistungsregler über null steht, die Kondensation aber wegen eines leeren `steam_in` oder eines vollen `water_out` blockiert ist. Der Wert wird unmittelbar aus beiden Anschlüssen abgeleitet. Mit `status()` kannst du die Ursachen unterscheiden."""
        ...
    def status(self) -> Literal["idle", "no_power", "no_steam", "output_full", "running"]:
        """Aktueller, für die Steuerung relevanter Zustand: `\"idle\"`, `\"no_power\"`, `\"no_steam\"`, `\"output_full\"` oder `\"running\"`. Er wird laufend aus der Reglerstellung, der Stromversorgung und beiden Flüssigkeitspuffern abgeleitet. Sobald der Regler auf **0** steht, wird `\"idle\"` gemeldet. Prüfe die Füllstände der Anschlüsse, um zu entscheiden, wann du ihn wieder öffnen solltest."""
        ...
    def throttle(self) -> _float:
        """Aktueller Sollwert für die Kondensationsleistung (**0.0-1.0**). Dampfverbrauch, Wasserausstoß und Strombedarf steigen damit linear."""
        ...
    def set_throttle(self, t: _float) -> ActionResult[Literal["ok"]]:
        """Stelle die Kondensationsleistung auf einen Wert von **0.0-1.0** ein (Werte außerhalb werden auf die jeweilige Grenze gesetzt). Bei **0** läuft die Maschine im Leerlauf, wandelt nichts um und hat keinen variablen Strombedarf. **1.0** fordert **250 t/h** und **150 W** an. Der Strombedarf folgt der Reglerstellung auch dann, wenn kein Dampf vorhanden oder der Ausgang voll ist. Stelle den Wert daher auf **0**, um während einer Blockade Strom zu sparen. Dieser vom Skript gesetzte Sollwert wird auf **0** zurückgesetzt, wenn das Skript gestoppt wird, endet oder einen Fehler auslöst. Rufe die Methode aus dem eigenen Skript dieses Kondensators auf. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    steam_in: FluidPort
    water_out: FluidPort
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

## `SupplyDock`

```python
class SupplyDock(Component):
    """Versorgungsdock: Verschickt fertige Waren vor der Durchsatzforschung mit **25 Einheiten/h** zur Erde. Ein Skript weist einen Auftragnehmer oder einen wöchentlichen Erdauftrag zu, lädt die benötigten Waren und aktiviert den Versand; nach Abschluss oder Ablauf bleibt das Dock bis zur nächsten Zuweisung stehen."""
    name: _str
    outpost: OutpostRef
    def capacity(self) -> _int:
        """Gesamtzahl der noch ausstehenden Einheiten über alle Gegenstände des aktiven Auftrags hinweg, also der verbleibende Bedarf des Docks. Gibt **0** zurück, wenn kein Auftrag zugewiesen ist. Nutze den Wert als Obergrenze für die Menge, die du noch laden und versenden musst."""
        ...
    def total(self) -> _int:
        """Summe der derzeit in allen Plätzen geladenen Einheiten. Vergleiche sie mit `capacity()`, um zu sehen, wie viel das Dock noch aufnehmen muss; `total() == 0` bedeutet, dass alle Plätze leer sind."""
        ...
    def count(self, item_id: _str) -> _int:
        """Anzahl der derzeit über alle Plätze des Docks verteilten Einheiten von `item_id`. Gibt **0** zurück, wenn das Dock keinen solchen Gegenstand enthält. Prüfe dies vor weiterem Beladen, um unnötige `take()`-Aufrufe zu vermeiden: `if self.count(\"iron_ore\") < 20: self.input.take(\"iron_ore\", 20)`."""
        ...
    def slots(self) -> _list[DockSlot]:
        """Die physischen Ladeplätze des Docks als Liste von `DockSlot`-Objekten (`.index`, `.item_id`, `.count`). Immer **5** Einträge mit Indizes von **0-4**; Plätze, die der aktuelle Auftrag nicht freigibt, haben `.item_id == None` und `.count == 0`. Siehe `DockSlot`."""
        ...
    def current_order(self) -> Order | None:
        """Gibt den aktiven Erdauftrag dieses Docks als `Order` zurück oder `None`, wenn kein Erdauftrag zugewiesen ist. Nach Abschluss des Erdauftrags wechselt der Wert automatisch zu `None`. Lies vor der Entscheidung über die Ladung `.requires` und `.shipped` aus."""
        ...
    def set_order(self, order_id: _str) -> ActionResult[Literal["ok", "unknown_order", "completed", "cargo_present"]]:
        """Weise diesem Dock einen Erdauftrag zu. Ermittle IDs mit `orders.list_orders()` oder `orders.list_weekly_orders()` und übergib dann eine davon an `self.set_order(id)`. Mehrere Docks können **denselben** Auftrag bedienen und teilen sich den Versandfortschritt. Die Ladung ist physisch vorhanden: Leere dieses Dock über eine lokale Maschine oder ein Fahrzeug, bevor du den Auftrag wechselst. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def clear_order(self) -> ActionResult[Literal["ok"]]:
        """Hebe die Zuweisung dieses Docks auf und stoppe den Versand. Geladene Fracht bleibt im Dock. Hole sie direkt mit `self.input.eject(destination, item_id, count)` zurück oder indem du den Eingang einer lokalen Maschine oder eines Fahrzeugs mit diesem Versorgungsdock verbindest. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def set_enabled(self, on: _bool) -> ActionResult[Literal["ok"]]:
        """Schalte den kontinuierlichen Versand ein oder aus. `True` setzt den Versand fort; `False` pausiert ihn. Das Beladen bleibt in beiden Fällen möglich: Der Eingangsanschluss nimmt weiterhin Material an. Bei Abschluss des zugewiesenen Auftrags wird der Versand **automatisch ausgeschaltet**; nach dem nächsten Aufruf von `set_order` muss das Skript ihn wieder einschalten. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def is_enabled(self) -> _bool:
        """`True`, solange der Versand aktiv ist. Der Wert wird nach `set_enabled(False)` oder nach Abschluss des zugewiesenen Auftrags zu `False`. Ein neues Dock ist anfangs aktiviert; weist du ihm bei geladener Fracht einen Auftrag zu, beginnt der Versand sofort."""
        ...
    def dispatch_rate(self) -> _float:
        """Aktueller effektiver Durchsatz des Versands in **Einheiten/h**; berücksichtigt bereits Durchsatzforschung und etwaige Abzüge wegen Überfüllung des Außenpostens. Die Grundrate beträgt **25** (eine Einheit alle **2,4** Minuten); **Großmengenlogistik II** multipliziert sie mit **4**, **Großmengenlogistik III** mit **16**. Multipliziere den Rückgabewert mit der verstrichenen Zeit in Stunden, um die voraussichtlich versandte Menge zu berechnen."""
        ...
    def current_dispatch(self) -> _str | None:
        """Die `item_id`, die gerade versandt wird, oder `None` im Leerlauf (keine Stromversorgung, kein Auftrag, Versand über `set_enabled(False)` pausiert oder keine versandfähige Einheit geladen). Nützlich für Skripte, die wissen sollen, welches Material gerade fließt."""
        ...
    def dispatch_progress(self) -> _float:
        """Anteil **0-1** des Fortschrittszählers bis zum Versand der aktuellen Einheit. Bleibt bei **0**, solange das Dock keine versandfähige Einheit geladen hat; der Zähler startet, sobald eine solche Einheit eintrifft. Steuert die umlaufende Uhranimation auf der Dockkarte; Skripte können daraus „nächster Start in X Stunden“ abschätzen."""
        ...
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

## `TempHeater`

```python
class TempHeater(Component):
    """Wärmegenerator: Erwärmt die Planetenoberfläche, indem er Wärme erzeugt. Die optimale Leistungseinstellung ändert sich mit dem Wetter des Tages; ein Skript liest die Bedingungen aus und hält den Heizer auf der passenden Stufe."""
    name: _str
    outpost: OutpostRef
    input: InputSlot
    steam_in: FluidPort
    def set_power(self, watts: _float) -> ActionResult[Literal["ok"]]:
        """Stelle die Grundleistung des Heizers auf einen Wert zwischen **0-10** ein; Werte außerhalb dieses Bereichs werden begrenzt. `0` schaltet die Heizung aus. Die beste positive Einstellung hängt vom aktuellen `thermal_state()` ab. Passe sie daher mit `self.set_power(value)` an, wenn sich die Bedingungen ändern. Höhere Mk-Stufen vervielfachen den Strombedarf, ohne die optimale Grundeinstellung zu ändern. Eine schlechte Einstellung verschwendet Energie und verringert die Wärmeproduktion. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def thermal_state(self) -> Literal["clear", "dust_storm", "heat_bleed", "dust_veil"]:
        """Aktueller täglicher thermischer Zustand des Heizers: einer von `\"clear\"`, `\"dust_storm\"`, `\"heat_bleed\"` und `\"dust_veil\"`. Jeder Zustand hat einen eigenen optimalen positiven Wert für `set_power()`. Der Zustand bleibt den ganzen Tag konstant und ändert sich erst am nächsten Tag. Lies ihn daher zu Beginn jedes Durchlaufs aus und verzweige, wenn sich die Zeichenfolge ändert: `if state == \"clear\": self.set_power(5)` usw. Deine Aufgabe ist es, die vier optimalen Werte herauszufinden."""
        ...
    def efficiency(self) -> _float:
        """Aktueller Heizwirkungsgrad (**0-100%**). Erreicht **100%** nur, wenn `set_power()` genau dem Optimum des aktuellen `thermal_state()` entspricht, und fällt in dessen Umgebung *steil* ab (nicht linear): etwa **31%** bei einer Stufe Abweichung, dann ein Mindestwert von **10%** bei zwei oder mehr Stufen. **0%** wird nur angezeigt, wenn die Leistung auf `0` steht. Prüfe die positiven Leistungswerte und wähle für jeden Zustand den Wert, bei dem **100%** angezeigt werden."""
        ...
    def output(self) -> _float:
        """Aktuelle Produktionsrate von Wärmeeinheiten pro Stunde bei den derzeitigen Einstellungen. Wärme sammelt sich über viele Tage an und erhöht die Oberflächentemperatur; die Ratenanzeige des Sensors rechnet den Wert auf einen Tag hoch. Die Produktionsrate ergibt sich aus `efficiency()` × Stufenmultiplikator. Gibt `0` zurück, wenn kein Strom anliegt oder kein Skript läuft. Der Wert wird bei jedem Abruf neu berechnet; eine Änderung durch `set_power(...)` erscheint sofort."""
        ...
    def tier(self) -> _int:
        """Dauerhaft installierte Mk-Stufe als Ganzzahl (**1-4**). Upgrade-Pakete erhöhen diesen Wert; ein vorübergehender Dampfmangel bei Mk III nicht. Vergleiche ihn mit `effective_tier()`, wenn du die Versorgung oder einen Leistungsabfall des Heizers untersuchst."""
        ...
    def is_degraded(self) -> _bool:
        """`True`, wenn einem Mk-III-Paket die benötigte Flüssigkeit fehlt und die Maschine in diesem Tick auf den Multiplikator der vorherigen Stufe zurückfällt. Prüfe den Wert nach dem Einbau eines Mk-III-Pakets. Falls er `True` ist, läuft dein Wärmegenerator der Stufe 3 vorübergehend wie Mk II; prüfe `self.steam_in.level()` und den vorgeschalteten Dampfsammler."""
        ...
    def effective_tier(self) -> _int:
        """Die in diesem Tick tatsächlich wirksame Stufe: normalerweise `tier()`, bei `is_degraded()` gleich `True` die vorherige Stufe. Skripte, die den Dampfstrom zwischen Heizern neu verteilen, sollten `effective_tier()` mit `tier()` vergleichen."""
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

## `ThermalCap`

```python
class ThermalCap(Component):
    """Dampfsammler: Fängt Dampf aus einem Thermalschlot auf. Erreicht die Kammer 100 %, entweicht jede gespeicherte Tonne in die Atmosphäre; ein Skript muss Dampf abgeben, weiterleiten oder den Druck ablassen."""
    name: _str
    def vent(self) -> ThermalVent:
        """Der `ThermalVent`, auf dem dieser Dampfsammler sitzt. Welche Felder verfügbar sind, hängt von der Sonarstufe ab, mit der der Dampfschlot zuletzt erkundet wurde: Die einfache Stufe zeigt die Phase, die weite zusätzlich Dampfraten und die tiefe auch Zykluszeiten. Mit `self.vent().current_phase()` oder der eigenen Methode `phase()` erfährst du, wann Dampf strömt. Siehe `ThermalVent`."""
        ...
    def phase(self) -> Literal["active", "dormant"] | None:
        """`\"active\"`, während der Dampfschlot Dampf erzeugt und sich deine Kammer füllt, oder `\"dormant\"`, während er ruht und sich die Kammer nur leert. Bis zur Erkundung des Dampfschlots gilt `None`. Richte deine Abgabeschleife danach aus: Öffne die Drossel in der aktiven Phase und schließe sie in der Ruhephase ein Stück, damit nachgelagerte Verbraucher nicht trockenlaufen."""
        ...
    def next_phase_in(self) -> _float | None:
        """Spielminuten, bis der Dampfschlot zwischen aktiver und Ruhephase wechselt. So kannst du vor einem Dampfstoß weiter öffnen oder vor einer Flaute drosseln. Gibt `None` zurück, solange der Dampfschlot nicht per **Tiefensonar** erkundet wurde; eine vorausschauende Schleife ist also der Lohn für die tiefe Sonarerfassung."""
        ...
    def pressure(self) -> _float:
        """Füllstand der Kammer von `0.0` bis `1.0`. Er steigt, während der Dampfsammler Dampf aus dem Dampfschlot auffängt, und sinkt, wenn du Dampf über `steam_out` abgibst. Bei `1.0` entsteht **Überdruck**: Der gesamte Kammerinhalt entweicht in die Atmosphäre, und die Kammer füllt sich wieder von null an. Halte den Füllstand unter der Obergrenze: Frage ihn in jedem Tick ab und öffne das Abgabeventil, wenn er steigt."""
        ...
    def capture_rate(self) -> _float:
        """Im letzten Tick aus dem Dampfschlot aufgenommener Dampf in t/h. Während der Ruhephase **0**, in der aktiven Phase bis zur aktuellen Förderrate des Dampfschlots. Die Phase des Dampfschlots ist bereits berücksichtigt; lies daher diesen Wert ab, statt ihn aus der Förderrate zu berechnen. Wird einmal pro Durchflusstick aktualisiert."""
        ...
    def is_overpressured(self) -> _bool:
        """`True` in dem Tick, in dem die Kammer voll wird und ihren gesamten Inhalt in die Atmosphäre abbläst. Danach ist sie leer und muss sich erst wieder aus dem Dampfschlot füllen, bevor du erneut Dampf erhältst: Der ganze Vorrat ist verloren. Wenn du diesen Wert siehst, hast du zu langsam Dampf abgegeben; öffne die Drossel früher."""
        ...
    def is_stalled(self) -> _bool:
        """`True`, wenn der mit Strom versorgte Dampfsammler im letzten Durchflusstick ein geöffnetes Ventil und Dampf in der Kammer hatte, aber über die verbundenen Leitungen nichts übertragen konnte. Eine leere Kammer, ein geschlossenes Ventil oder fehlender Strom gelten nicht als Stillstand. Lege mit `self.steam_out.connect(...)` ein Ziel fest oder lass Verbraucher ihre eigenen `steam_in`-Anschlüsse mit diesem Dampfsammler verbinden."""
        ...
    def throttle(self) -> _float:
        """Aktuelle Einstellung des Abgabeventils von `0.0` (geschlossen) bis `1.0` (ganz geöffnet). Lies sie nach `set_throttle(...)` erneut aus."""
        ...
    def set_throttle(self, t: _float) -> ActionResult[Literal["ok"]]:
        """Öffne das Abgabeventil des Dampfsammlers mit einem Wert von `0.0` bis `1.0` (Werte außerhalb des Bereichs werden auf den nächsten Grenzwert begrenzt). `0` verschließt die Kammer, sodass sie sich füllt; bei `1.0` wird Dampf so schnell an alle erreichbaren, angeschlossenen Ziele abgegeben, wie Dampfvorrat in der Kammer, freie Kapazität der Ziele und Durchsatz es zulassen. Das ist dein wichtigster Regler gegen Überdruck: Rufe die Funktion in jedem Tick entsprechend `pressure()` auf. Dieser vom Skript gesetzte Sollwert wird auf `0` zurückgesetzt, wenn das Skript angehalten wird, endet oder einen Fehler auslöst. Wenn kein Ziel genug Dampf aufnehmen kann und `pressure()` weiter steigt, leite den Überschuss mit `set_relief(...)` ab. `[self only]` Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def relief(self) -> _float:
        """Aktuelle Einstellung des Überdruckventils von `0.0` (geschlossen) bis `1.0` (ganz geöffnet). Lies sie nach `set_relief(...)` erneut aus."""
        ...
    def relief_rate(self) -> _float:
        """In diesem Tick über das Überdruckventil in die Atmosphäre abgegebener Dampf in t/h. Bei geschlossenem Ventil `0`. Beobachte den Wert, um zu sehen, wie viel Überschuss du ablässt."""
        ...
    def set_relief(self, t: _float) -> ActionResult[Literal["ok"]]:
        """Öffne das Überdruckventil auf einen Wert zwischen **0-1**, um überschüssigen Dampf aus der Kammer in die Atmosphäre abzulassen. Nutze es, wenn angeschlossene Verbraucher nicht mithalten können und `pressure()` weiter steigt. Bei `0` bleibt der gesamte Dampf für Verbraucher verfügbar. Werte außerhalb des Bereichs werden begrenzt. Rufe diese Methode nur im eigenen Skript des Dampfsammlers auf. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    steam_out: FluidPort
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

## `ThermalVent`

```python
class ThermalVent(Site):
    """jede API, die eine Site zurückgibt, bei der `kind() == \"thermal\"` gilt (z. B. `thermal_cap.vent()`, Sonar- oder Logbuchabfragen)"""
    def survey_level(self) -> Literal["basic", "wide", "deep"] | None:
        """Höchste an dieser Dampfquelle erreichte Erkundungsstufe: `\"basic\"` / `\"wide\"` / `\"deep\"` oder `None`, wenn sie noch nicht erkundet wurde. Wird live ausgelesen: Eine erneute Erkundung auf einer höheren Stufe aktualisiert auch bereits abgerufene Standortobjekte. Höhere Stufen schalten weitere der unten aufgeführten Felder frei. Ein Sonarergebnis von vor der Erkundung bleibt unverändert und zeigt diese Information nicht an; rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def cycle_active_minutes(self) -> _float | None:
        """Dauer der aktiven Phase in Minuten. Erfordert eine **tiefgehende** Erkundung; andernfalls wird `None` zurückgegeben."""
        ...
    def cycle_dormant_minutes(self) -> _float | None:
        """Dauer der Ruhephase in Minuten. Erfordert eine **tiefgehende** Erkundung; andernfalls wird `None` zurückgegeben."""
        ...
    def current_phase(self) -> Literal["active", "dormant"] | None:
        """Aktuelle Phase der Dampfquelle: `\"active\"` oder `\"dormant\"`. Wird live ausgelesen: Frage den Wert an einem bereits abgerufenen Standortobjekt wiederholt ab, um den Phasenwechsel zu verfolgen. Vor der Erkundung der Dampfquelle wird `None` zurückgegeben. Ein Sonarergebnis von vor der Erkundung bleibt unverändert und zeigt diese Information nicht an; rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def next_phase_in(self) -> _float | None:
        """Spielminuten bis zum nächsten Phasenwechsel. Wird live ausgelesen: Frage den Wert in einer Steuerschleife wiederholt ab, um vor Beginn der Ruhephase zu handeln. Erfordert eine **tiefgehende** Erkundung; andernfalls wird `None` zurückgegeben. Ein Sonarergebnis von vor der Erkundung bleibt unverändert und zeigt diese Information nicht an; rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def base_steam_rate(self) -> _float | None:
        """Maximale Dampfmenge pro Stunde während der aktiven Phase (t/h). Erfordert eine **weitreichende** Erkundung; bei einer einfachen Erkundung wird `None` zurückgegeben."""
        ...
    def current_steam_rate(self) -> _float | None:
        """Aktuelle Dampfmenge pro Stunde (t/h: **0** während der Ruhephase). Wird live ausgelesen. Erfordert eine **weitreichende** Erkundung; bei einer einfachen Erkundung wird `None` zurückgegeben. Ein Sonarergebnis von vor der Erkundung bleibt unverändert und zeigt diese Information nicht an; rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def has_cap(self) -> _bool:
        """Boolescher Wert: `True`, wenn derzeit ein Dampfsammler an dieser Dampfquelle eingesetzt ist. Wird live ausgelesen. Ein Sonarergebnis von vor der Erkundung bleibt unverändert und zeigt diese Information nicht an; rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def cap_id(self) -> _str:
        """Maschinen-ID des derzeit an dieser Dampfquelle eingesetzten Dampfsammlers oder eine leere Zeichenfolge, wenn keiner vorhanden ist. Wird live ausgelesen. Ein Sonarergebnis von vor der Erkundung bleibt unverändert und zeigt diese Information nicht an; rufe nach der Erkundung ein neues Objekt ab."""
        ...
```

## `Transmitter`

```python
class Transmitter(Component):
    """Sender: Sendet Daten an andere Planeten. Nutze den Sender, um der Erde Sensorwerte zu melden oder Antworten auf Verträge einzureichen. Wähle mit `connect()` einen Planeten und sende dann mit `transmit(key, value)` Daten; `disconnect()` trennt die Verbindung. Sie gilt nur für die aktuelle Ausführung des Skripts, daher muss sich jedes sendende Skript zuerst verbinden. Speichere `get_component(\"transmitter\")` in einer Variablen und verwende sie für beide Aufrufe."""
    name: _str
    def list_planets(self) -> _list[Planet]:
        """Alle verfügbaren Sendeziele als Liste von `Planet`-Objekten (jeweils mit `.id`, `.name` usw.). Rufe die Methode einmal beim Start des Skripts auf, um die Ziele zu sehen, und übergib eine zurückgegebene `.id` an `connect(id)`."""
        ...
    def connect(self, planet: _str) -> ActionResult[Literal["ok", "not_found"]]:
        """Öffne einen Kanal zum Planeten mit der angegebenen ID: `result = transmitter.connect(\"earth\")`. Die ID muss kleingeschrieben sein und aus `list_planets()` stammen. Lies nach erfolgreicher Verbindung `transmitter.get_info().target` aus. Die Verbindung gilt nur für die aktuelle Skriptausführung; startet dein Skript neu, rufe vor `transmit()` erneut `connect()` auf. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def disconnect(self) -> ActionResult[Literal["ok"]]:
        """Schließe den Kanal der aktuellen Skriptausführung. Das wirkt sich weder auf Verträge noch auf andere Skripte aus; es löscht nur das aktive Ziel dieses Senderobjekts. Für spätere `transmit()`-Aufrufe musst du erneut `connect()` aufrufen. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    def get_info(self) -> TransmitterInfo:
        """Aktueller Verbindungsstatus. Gibt ein Objekt mit `.connected` (boolescher Wert) und `.target` (ID des verbundenen Planeten oder `\"none\"`) zurück. Prüfe den Status vor `transmit()` so: `if transmitter.get_info().connected: transmitter.transmit(...)`."""
        ...
    def transmit(self, key: _str, value: JsonValue) -> ActionResult[Literal["correct", "incorrect", "already_completed_correct", "already_completed_incorrect", "accepted", "rejected", "not_connected", "wrong_planet", "wrong_contract", "locked", "unknown_contract", "key_is_planet", "unknown_key"]]:
        """Sende mit `transmitter.transmit(key, value)` einen benannten Wert an den verbundenen Planeten. Die erste Übertragung von Sensordaten ist erst möglich, wenn die Einführungsschritte für Stromversorgung und Sensoren abgeschlossen sind und der Uplink-Schritt aktiv ist. Verwende für Sensorwerte den von der Erde angeforderten Namen, etwa `\"current_temperature\"`. Für Vertragsantworten nutze `self.contract.id`. Die Daten kommen im selben Tick an. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
```

## `TransmitterInfo`

```python
class TransmitterInfo:
    """transmitter.get_info()"""
    connected: _bool
    target: Literal["none"]
```

## `WaterPump`

```python
class WaterPump(Component):
    """Wasserpumpe: Fördert Wasser aus einem erkundeten Brunnen mit der Leistung, die dein Skript einstellt. Ihren Bauplan auf der Planetenkarte kannst du im Planungsmodus oder per Skript platzieren; ein Pionier muss sie trotzdem auf dem Brunnen errichten."""
    name: _str
    def well(self) -> WaterWell:
        """Der `WaterWell`, an dem diese Pumpe befestigt ist. Lies `.yield_tier()`, um zu sehen, ob die Quelle `\"standard\"` / `\"rich\"` / `\"pure\"` ist (Multiplikator 1×/2×/3×), und `.flow_rate()` für die stündliche Fördermenge der Quelle. Nützlich für Skripte, die Fördermengen innerhalb der Flotte vergleichen und Prioritäten setzen."""
        ...
    def pump_rate(self) -> _float:
        """Gesamtmenge Wasser, die in diesem Tick an verbundene Ziele geliefert wurde, in t/h. Gibt **0** zurück, wenn die Drosselung auf **0** steht oder kein Ziel Wasser aufnehmen kann. Wenn eine ergiebige Quelle trotzdem 0 meldet, prüfe die Verbindungen, fertiggestellte Rohrleitungen, Konflikte, die Stromversorgung und die Kapazität der Ziele."""
        ...
    def is_stalled(self) -> _bool:
        """`True`, wenn die mit Strom versorgte Pumpe im letzten Durchflusstick bei einer Drosseleinstellung über 0 Wasser aus ihrer Quelle zur Verfügung hatte, aber über die verbundenen Leitungen nichts übertragen konnte. Ohne verfügbares Wasser, bei einer Drosseleinstellung von 0 oder ohne Strom wird kein Stillstand gemeldet. Lege mit `self.water_out.connect(...)` ein Ziel fest oder lass Verbraucher ihre eigenen `water_in`-Anschlüsse mit dieser Pumpe verbinden."""
        ...
    def throttle(self) -> _float:
        """Aktuelle Drosseleinstellung (**0-1**). Standardmäßig **0**: Die Pumpe bleibt inaktiv, bis ein Skript `set_throttle()` aufruft."""
        ...
    def set_throttle(self, rate: _float) -> ActionResult[Literal["ok"]]:
        """Stelle die gesamte Förderrate der Pumpe (**0-1**) für erreichbare verbundene Ziele ein. Bei **0** bleibt die Pumpe inaktiv (keine Förderung, kein Stromverbrauch); **1** erlaubt die volle Fördermenge der Quelle, soweit Kapazität und Durchsatz dies zulassen. Dieser vom Skript gesetzte Sollwert wird auf **0** zurückgesetzt, wenn das Skript stoppt, endet oder einen Fehler auslöst. Lass die Regelschleife daher laufen, solange die Pumpe arbeiten soll. Fester Ergebnisvertrag: `ActionResult`; verzweige anhand von `.status` und lies `.message`."""
        ...
    output: PickupOutputSlot
    water_out: FluidPort
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

## `WaterWell`

```python
class WaterWell(Site):
    """jede API, die eine Site zurückgibt, bei der `kind() == \"water\"` gilt (z. B. `water_pump.well()`, Sonar- oder Logbuchabfragen)"""
    def yield_tier(self) -> Literal["standard", "rich", "pure"] | None:
        """Einer der Werte `\"standard\"` (**1×**) / `\"rich\"` (**2×**) / `\"pure\"` (**3×**). Bis zur Erkundung `None`. Der Wert richtet sich nach dem aktuellen Erkundungsfortschritt, außer bei einem Sonarergebnis von vor der Erkundung: Dort bleibt er `None`. Rufe nach der Erkundung ein neues Objekt ab. Brunnen werden bereits bei der grundlegenden Erkundung vollständig aufgedeckt."""
        ...
    def flow_rate(self) -> _float | None:
        """Wassermenge, die dieser Brunnen pro Stunde fördert, in Tonnen. **10 / 20 / 30** bei normalem / ergiebigem / reinem Vorkommen. Bis zur Erkundung `None`. Der Wert wird laufend aktualisiert, außer bei einem Sonarergebnis von vor der Erkundung: Dort bleibt er `None`. Rufe nach der Erkundung ein neues Objekt ab."""
        ...
    def has_pump(self) -> _bool:
        """Boolescher Wert: `True`, wenn an diesem Brunnen derzeit eine Wasserpumpe aufgestellt ist. Ein Sonarergebnis von vor der Erkundung gibt immer `False` zurück. Rufe nach der Erkundung ein neues Objekt ab, um aktuelle Werte zu erhalten."""
        ...
    def pump_id(self) -> _str:
        """Aktuelle Maschinen-ID der Wasserpumpe an diesem Brunnen oder ein leerer String, wenn keine Pumpe vorhanden ist. Ein Sonarergebnis von vor der Erkundung gibt immer einen leeren String zurück. Rufe nach der Erkundung ein neues Objekt ab, um aktuelle Werte zu erhalten."""
        ...
```

## `Zone`

```python
class Zone:
    """WeatherReport.coverage() und WeatherEventForecast.corridor()"""
    def intersect(self, other: Zone) -> Zone:
        """Behalte nur die Geometrie, die beide Zonen gemeinsam haben."""
        ...
    def union(self, other: Zone) -> Zone:
        """Behalte alles, was von mindestens einer der beiden Zonen abgedeckt wird."""
        ...
    def subtract(self, other: Zone) -> Zone:
        """Entferne die Geometrie der anderen Zone aus dieser Zone."""
        ...
    def diff(self, other: Zone) -> Zone:
        """Behalte nur die Geometrie, die in genau einer der beiden Zonen vorhanden ist."""
        ...
    def center(self) -> _list[_float] | None:
        """Flächenschwerpunkt als `[x, y]` in m oder `None` bei einer leeren Zone. Dies beschreibt die sichtbare Geometrie des Sturms, nicht seine verborgenen Nachwirkungen."""
        ...
    def area(self) -> _float:
        """Abgedeckte Fläche in m²."""
        ...
    def contains(self, x: _float, y: _float) -> _bool:
        """`True`, wenn der Punkt innerhalb der Zone liegt."""
        ...
    def is_empty(self) -> _bool:
        """`True`, wenn die Zone keine Fläche abdeckt."""
        ...
```
