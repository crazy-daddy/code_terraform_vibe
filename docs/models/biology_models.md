# Models: Biology Pipeline Models (Specimens, Fragments, Orders, Recipes)

Granular data models and return types extracted from `__builtins__.pyi`.

## `BioCaster`

```python
class BioCaster(Component):
 """Bio Caster: Forges a volcanic fragment by holding the crucible in a target temperature band while the recipe's materials are loaded, then casting. Steam and water use separate 20 t internal process buffers. Connect each input port to a compatible source; local sources transfer directly, while remote sources also need a completed conflict-free pipe route between both locations. A script drives the heat and cooling; casting out of band or with the wrong materials burns the whole charge."""
 name: _str
 outpost: OutpostRef
 def list_recipes(self) -> _list[BioCasterRecipe]:
 """List all 16 forge recipes without changing the selected recipe, `self.list_recipes()`. Each `BioCasterRecipe` includes its fragment id, tier, exact material shopping list, and target temperature range. The read works through `get_component(...)`, so another machine can plan supplies without possessing every fragment."""
 ...
 def find_recipe(self, fragment_id: _str) -> BioCasterRecipe | None:
 """Look up one forge recipe by volcanic fragment id without selecting it, `self.find_recipe(fragment_id)`. Returns `None` for an unknown id."""
 ...
 def catalog(self) -> _list[_str]:
 """The 16 forgeable volcanic fragment ids, `self.catalog()`. Pass one to `set_recipe(...)`, or use `list_recipes()` when you also need every recipe's material and temperature requirements. Fixed hardware; read it once."""
 ...
 def recipe_tier(self, fragment_id: _str) -> _int | None:
 """Derived production tier for one recipe from `catalog()`. Returns `None` for an unknown fragment id."""
 ...
 def set_recipe(self, fragment_id: _str) -> ActionResult[Literal["ok", "invalid_recipe", "busy"]]:
 """Select which volcanic fragment to forge, `self.set_recipe(\"sd_tail_barb\")`. After this, `required_range()` and `required_materials()` describe that recipe. The selection persists like a Smelter recipe. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def recipe(self) -> Literal["ma_chitinous_seta", "st_beak", "ms_abdomen_sclerite", "mh_chitin_node", "gm_abdominal_sheath", "vm_tail_barb", "vc_walking_leg", "oc_ink_sac", "bw_hindlimb", "vd_photophore", "hs_abdomen_segment", "hc_beak", "fs_oral_tegmen", "ce_great_appendage", "gw_jaw_fang", "sd_tail_barb"] | None:
 """The recipe you've selected, `self.recipe()` returns the volcanic fragment id you're set to forge (also the raw fragment to `load`), or `None` if none is set."""
 ...
 def required_range(self) -> _tuple[_float, _float] | None:
 """The selected recipe's target band `[low, high]` in °C, `self.required_range()`. `cast()` must fire with `temperature()` inside it (inclusive). `None` if no recipe is set."""
 ...
 def required_materials(self) -> _dict[_str, Any]:
 """Lists the fabricated materials required by the selected recipe as `{item_id: count}`. Load exactly those amounts before casting. Iterate with `.items()`. Returns an empty dict when no recipe is selected."""
 ...
 def required_fragment(self) -> Literal["ma_chitinous_seta", "st_beak", "ms_abdomen_sclerite", "mh_chitin_node", "gm_abdominal_sheath", "vm_tail_barb", "vc_walking_leg", "oc_ink_sac", "bw_hindlimb", "vd_photophore", "hs_abdomen_segment", "hc_beak", "fs_oral_tegmen", "ce_great_appendage", "gw_jaw_fang", "sd_tail_barb"] | None:
 """The raw fragment id the recipe consumes, `self.required_fragment()` (identical to `recipe()`). `None` if no recipe is set."""
 ...
 def temperature(self) -> _float:
 """Current crucible temperature in °C, `self.temperature()`, ranging **100** (cold baseline) to **1000** (max). Drive it into `required_range()` with the knobs before casting."""
 ...
 def temp_rate(self) -> _float:
 """Net temperature change in °C/h right now, `self.temp_rate()`. Positive = heating and negative = cooling. Full heat is +2400 °C/h and full cool is -2400 °C/h; with both knobs at 0, an unlocked crucible above baseline cools naturally at -20 °C/h. Returns 0 at the 100 °C baseline or while a cast is in progress."""
 ...
 def heat(self) -> _float:
 """Current heat-knob setting **0-100 %**, `self.heat()`. At 100 % temperature rises **+2400 °C/h** (burning steam); use a lower setting near the target band."""
 ...
 def cool(self) -> _float:
 """Current cool-knob setting **0-100 %**, `self.cool()`. At 100 % temperature falls **-2400 °C/h** (burning water); use a lower setting near the target band."""
 ...
 def fragment(self) -> Literal["ma_chitinous_seta", "st_beak", "ms_abdomen_sclerite", "mh_chitin_node", "gm_abdominal_sheath", "vm_tail_barb", "vc_walking_leg", "oc_ink_sac", "bw_hindlimb", "vd_photophore", "hs_abdomen_segment", "hc_beak", "fs_oral_tegmen", "ce_great_appendage", "gw_jaw_fang", "sd_tail_barb"] | None:
 """The raw fragment id loaded in the chamber, `self.fragment()`, or `None` if the chamber is empty."""
 ...
 def materials(self) -> _dict[_str, Any]:
 """The materials currently loaded in the crucible, `self.materials()` returns `{item_id: count}`. Compare against `required_materials()` before `cast()`. Iterate with `.items()`."""
 ...
 def set_heat(self, pct: _float) -> ActionResult[Literal["ok", "empty", "busy"]]:
 """Set the heat knob (steam to temperature up), `self.set_heat(100)` for +2400 °C/h, then use a lower percentage for the final approach. Range **0-100**, clamped. Open-loop: it keeps heating and burning steam until you set it back. With both knobs at 0, the crucible cools naturally at 20 °C/h, so cast after entering the band. Re-idles to 0 when the chamber empties or the script stops. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def set_cool(self, pct: _float) -> ActionResult[Literal["ok", "empty", "busy"]]:
 """Set the cool knob (water to temperature down), `self.set_cool(100)` for -2400 °C/h, then use a lower percentage for the final approach. Range **0-100**, clamped. Open-loop: keeps cooling and burning water until you set it back. Both knobs may run at once, but that burns both fluids for little movement. With both knobs at 0, the crucible still cools naturally at 20 °C/h. Re-idles to 0 when the chamber empties or the script stops. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def load(self, fragment_id: _str, properties: Any = ..., property_match: _str | None = ...) -> ActionResult[Literal["ok", "chamber_occupied", "not_in_input", "invalid_fragment", "invalid_properties", "invalid_property_match", "busy"]]:
 """Pull a raw volcanic sample of `fragment_id` from `self.input` into the chamber, usually `self.load(self.recipe())`. Optional `properties` and `property_match` select a specific identity using the standard any, subset, or exact convention. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def eject(self) -> ActionResult[Literal["ok", "empty", "busy", "output_full"]]:
 """Stage the chamber sample and all loaded materials in `self.output` without changing their properties. A single-material output may require a send/eject cycle for each item type. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def cast(self) -> ActionResult[Literal["ok", "out_of_range", "wrong_materials", "wrong_fragment", "empty", "no_recipe", "busy", "output_full"]]:
 """Forge the loaded fragment, `self.cast()`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 input: InputSlot
 output: OutputSlot
 steam_in: FluidPort
 water_in: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `BioCasterRecipe`

```python
class BioCasterRecipe:
 """bio_caster.list_recipes() / bio_caster.find_recipe(fragment_id)"""
 fragment_id: Literal["gw_jaw_fang", "vc_walking_leg", "oc_ink_sac", "bw_hindlimb", "vd_photophore", "mh_chitin_node", "hs_abdomen_segment", "ms_abdomen_sclerite", "hc_beak", "ma_chitinous_seta", "gm_abdominal_sheath", "fs_oral_tegmen", "sd_tail_barb", "ce_great_appendage", "st_beak", "vm_tail_barb"]
 tier: _int
 materials: _dict[_str, _int]
 temperature_range: _tuple[_float, _float]
```

## `BioCollector`

```python
class BioCollector(Component):
 """Bio Collector: Automates the Collect step of the biology loop, fetching a field specimen into its cargo slot on its own. It does nothing until a script tells it where to collect."""
 name: _str
 outpost: OutpostRef
 def scan(self) -> _list[FragmentLocation]:
 """Lists fragment locations in this outpost's biome, nearest first. Each `FragmentLocation` includes `coords`, distance, and whether it has been cataloged. Cataloged locations also reveal their fragment id, name, and rarity; unknown locations leave those details as `None`. To identify an unknown location, collect it with `bio_collector.collect(location.coords)` and analyze it at a Bio Lab. Recipes and creature identity are not revealed here. Analyzed fragments also appear in `journal.cataloged_fragments(...)`."""
 ...
 def collect(self, coords: _list[Any]) -> ActionResult[Literal["ok", "busy", "cargo_occupied", "invalid_coords", "no_fragment"]]:
 """Retrieve the fragment at `coords` from `scan()` and place it in the collector's cargo slot. The trip takes **~0.1-0.3 h** in every biome, depending on distance; the script pauses until collection finishes. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def discard(self) -> ActionResult[Literal["ok", "empty", "busy"]]:
 """Discard the specimen currently held in collector cargo. Use this when the collector picked up a specimen you do not want to send to a Bio Lab. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 cargo: Specimen | None
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `BioConditioner`

```python
class BioConditioner(Component):
 """Bio Conditioner: Inspects a deep-biome fragment against a fixed rulebook, quizzing your script on its properties one at a time. Judge each one correctly to pass the fragment; a single wrong call burns the whole specimen."""
 name: _str
 outpost: OutpostRef
 def report(self) -> _dict[_str, Any]:
 """The loaded fragment's full condition report, `self.report()` returns `{property: value}` for all 10 properties (`glow`, `brightness`, `smell`, `gunk`, `cracks`, `feel`, `twitch`, `bugs`, `weight`, `sound`). Read the whole thing: the combo rules need siblings (brightness reads glow, weight reads gunk, sound reads cracks). Word properties are strings, numbers are numbers. `{}` if nothing is loaded. Iterate with `.items()` or index `report[\"gunk\"]`."""
 ...
 def properties(self) -> _list[_str]:
 """Lists the ten property ids in their fixed inspection order, from `\"glow\"` through `\"sound\"`. The order is the same for every Deep fragment, making it suitable for a general inspection loop."""
 ...
 def fragment(self) -> Literal["gw_spinal_vertebra", "vc_eye_stalk", "oc_lens_eye", "bw_tail_spike", "vd_tendril", "mh_stigmatic_disc", "hs_compound_eye", "ms_eye_cluster", "hc_tentacle_crown", "ma_luminous_ring", "gm_antennal_whip", "fs_holdfast_rootlet", "sd_talon", "ce_cephalic_photophore", "st_carapace_neural", "vm_ventral_photophore"] | None:
 """The raw deep fragment id loaded in the chamber, `self.fragment()`, or `None` if empty."""
 ...
 def stage(self) -> _int:
 """The current QC stage, `self.stage()` returns **1-5** while a run is live, or **0** when none is active (nothing loaded, or the run just resolved). Each stage quizzes one property."""
 ...
 def current(self) -> Literal["glow", "brightness", "smell", "gunk", "cracks", "feel", "twitch", "bugs", "weight", "sound"] | None:
 """The property this stage is quizzing, `self.current()` returns one of the 10 ids (look its value up in `report()`, apply its rule, then `accept()`/`reject()`), or `None` if no run is active. You can't predict which 5 of the 10 come up, so encode every rule."""
 ...
 def lights(self) -> _list[_str]:
 """The 5 stage results so far, `self.lights()` returns a list of `\"green\"` (correct call), `\"red\"` (a miss, run over), and `\"pending\"` (not reached). They light one at a time as you answer."""
 ...
 def is_running(self) -> _bool:
 """`True` while a 5-stage run is live (a fragment is loaded with stages left), `self.is_running()`. Drive the gauntlet with `while cond.is_running(): prop = cond.current(); ...`. Goes `False` when the run finishes, burns, or nothing is loaded."""
 ...
 def load(self, fragment_id: _str, properties: Any = ..., property_match: _str | None = ...) -> ActionResult[Literal["ok", "chamber_occupied", "not_in_input", "invalid_fragment", "invalid_properties", "invalid_property_match", "busy"]]:
 """Pull one raw deep sample from `self.input` into the chamber and start a fresh 5-stage run. Optional `properties` and `property_match` select a specific identity using the standard any, subset, or exact convention. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def eject(self) -> ActionResult[Literal["ok", "empty", "busy", "output_full"]]:
 """Stage the unchanged chamber sample in `self.output` and end the run. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def accept(self) -> ActionResult[Literal["ok", "conditioned", "burned", "no_run", "busy", "output_full"]]:
 """Stamp the current property as passing. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def reject(self) -> ActionResult[Literal["ok", "conditioned", "burned", "no_run", "busy", "output_full"]]:
 """Stamp the current property as damaged. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 input: InputSlot
 output: OutputSlot
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `BioExchange`

```python
class BioExchange(Component):
 """Bio Exchange: Delivers biology samples to fulfill a Bio Order, the biology counterpart to the Supply Dock. A script assigns an order and delivers its required fragments until the reward pays out."""
 name: _str
 outpost: OutpostRef
 def orders(self) -> _list[BioOrder]:
 """Lists every `BioOrder`, including orders you cannot fill yet. Each order includes its id, biome, requirements, reward, status, delivered samples, samples already `in_transit`, completion percent, and any required `target_glow`. Progress is shared by every Bio Exchange serving that order. Use `requires - delivered - in_transit` to avoid making samples that are already committed, then pass the chosen `order.id` to `set_order(...)`. From another script, call `get_component(\"bio_exchange_1\").orders()`. `get_component(\"orders\")` is for Earth Orders."""
 ...
 def set_order(self, order_id: _str) -> ActionResult[Literal["ok", "unknown_order", "completed"]]:
 """Pick the Bio Order this Exchange will fill. `self.set_order(\"bio_order_03\")`. Several Exchanges may activate the **same** Bio Order, they cooperate on one shared delivery count, so big Bio Orders can be served from multiple outposts at once. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def clear_order(self) -> ActionResult[Literal["ok", "busy"]]:
 """Clear this Exchange's active Bio Order assignment. Already delivered progress stays recorded on the Bio Order, completed Bio Orders stay completed, and no samples are moved. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def active_order(self) -> BioOrder | None:
 """A snapshot of the active `BioOrder` object, its `requires`, completed `delivered` progress, live `in_transit` commitments, `percent`, and `target_glow` (coastal infusion target) at the moment you call it, or `None` if no order is set. `in_transit` includes qualifying samples already staged in serving Exchange inputs plus active timed deliveries. Call `active_order()` again to read fresh progress."""
 ...
 def matches_order(self, item_id: _str, properties: Any = ...) -> _bool:
 """Check whether one exact item matches this Exchange's active Bio Order without moving it. Pass the `id` and `properties` from an `ItemStack`. `True` means that variant satisfies the order's glow, genes, Forged, Conditioned, or plain-sample requirement. Use it with Inventory, Storage Bin, or Warehouse `stacks()` before an exact `self.input.take(...)`. Returns `False` when there is no active order, the order is complete, or the item does not qualify."""
 ...
 def deliver(self) -> ActionResult[Literal["ok", "complete", "no_input", "output_full", "no_active", "busy"]]:
 """Deliver one matching sample from `self.input` toward the active Bio Order, `self.deliver()` (a short timed action). Progress is **shared across every Bio Exchange** serving the Bio Order. Connect the ports to Inventory at Nocturna Base, or to a same-outpost Storage Bin/Warehouse elsewhere, then use `take(...)` and `send(...)` to route samples. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def lifetime_credits(self) -> _float:
 """Total credits this Exchange has earned across every completed Bio Order."""
 ...
 input: InputSlot
 output: OutputSlot
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `BioLab`

```python
class BioLab(Component):
 """Bio Lab: Automates the Analyze and Extract steps of the biology loop, studying a specimen and pulling a usable sample from it. It stays idle until a script drives it."""
 name: _str
 outpost: OutpostRef
 def take_from(self, collector: Any) -> ActionResult[Literal["ok", "busy", "input_occupied", "not_found", "source_empty", "source_busy", "wrong_outpost", "invalid_source"]]:
 """Pull the specimen out of a Bio Collector's cargo into this lab's specimen chamber. The source Collector must be at the same outpost as this Lab; pass an explicit collector reference: `self.take_from(get_component(\"bio_collector_1\"))`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def analyze(self) -> AnalyzeResult[Literal["ok", "busy", "input_empty", "invalid_specimen"]]:
 """Identify the lab's current fragment and reveal its extraction recipe. Analysis takes **~0.1 h** in every biome; the script pauses until it finishes. A successful analysis adds the fragment to `journal.cataloged_fragments(planet_id)`. Creature identity stays hidden until all five fragments are cataloged, then the creature appears in `journal.cataloged_creatures(planet_id)`. Fixed result contract: `AnalyzeResult`; branch on `.status` and read `.message`. Payload fields: `.info`."""
 ...
 def load(self, reagent_id: _str, qty: _float, properties: Any = ..., property_match: _str | None = ...) -> ActionResult[Literal["ok", "busy", "invalid_reagent", "invalid_qty", "invalid_properties", "invalid_property_match", "insufficient_input"]]:
 """Stage a whole-number reagent quantity for the next `extract()` by consuming it from `self.input`. `self.load(\"alkaline_buffer\", 4)`. Reagents are sold by the `shop`; both UI purchases and `shop.buy(reagent_id)` place them in base Inventory. Optional `properties` and `property_match` select a specific item identity using the standard any, subset, or exact convention. Fractional or negative quantities raise an argument error. Calling `extract()` with a mismatched recipe destroys the loaded reagents. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def unload_reagents(self) -> ActionResult[Literal["ok", "empty", "busy", "output_full"]]:
 """Stage all loaded reagents in `self.output` without touching the specimen. Use this when you staged the wrong recipe. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def extract(self) -> ActionResult[Literal["ok", "output_full", "recipe_mismatch", "busy", "input_empty", "not_analyzed", "invalid_specimen"]]:
 """Consume `loaded_reagents` and place **1 sample** of the analyzed specimen in `self.output`, preserving its exact properties. Extraction takes **~0.1 + 0.05 × units h** in every biome; the script pauses until it finishes. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def discard(self) -> ActionResult[Literal["ok", "input_empty", "busy", "output_full"]]:
 """Drop the current specimen and stage any loaded reagents in `self.output`. Use it after `analyze()` reveals a fragment you do not need. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 specimen: Specimen | None
 loaded_reagents: _dict[_str, Any]
 input: InputSlot
 output: OutputSlot
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `BioLuminizer`

```python
class BioLuminizer(Component):
 """Bio Luminizer: Tints a coastal fragment's glow to a target color using three built-in colored lamps. The lamps bleed into each other, so a script solves the brightness mix that lands on the exact target."""
 name: _str
 outpost: OutpostRef
 def load(self, fragment_id: _str, properties: Any = ..., property_match: _str | None = ...) -> ActionResult[Literal["ok", "chamber_occupied", "not_in_input", "invalid_fragment", "invalid_properties", "invalid_property_match", "busy"]]:
 """Pull a raw glowing coastal sample of `fragment_id` from `self.input` into the chamber, `self.load(\"gw_caudal_fin\")`. Optional `properties` and `property_match` select a specific identity using the standard any, subset, or exact convention. Read its start color with `self.chamber.glow`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 chamber: ChamberSample | None
 def lamp_signature(self, channel: _str) -> _tuple[_float, _float, _float] | None:
 """The RGB-per-unit `[r,g,b]` a lamp adds per brightness step, its impurity. `self.lamp_signature(\"red\")` is roughly `[6, 1, 1]`: mostly red, but it bleeds a little into green and blue. Read all three (`\"red\"`, `\"green\"`, `\"blue\"`) to build the 3×3 you invert. Fixed hardware, read once and reuse. `None` for an unknown channel."""
 ...
 def glow(self) -> _tuple[_float, _float, _float] | None:
 """The chamber's **current** resulting glow `[r,g,b]` given the lamps set right now, it reflects `set_lamps(...)` immediately, so use it to verify your solve before committing: `if self.glow() == target: self.infuse()`. `None` when the chamber is empty."""
 ...
 def set_lamps(self, r: _float, g: _float, b: _float) -> ActionResult[Literal["ok", "busy"]]:
 """Set the three lamp brightnesses, `self.set_lamps(7, 13, 4)`. Each is a **whole number 0-40**; the exact answer is always an integer, so `round()` your computed values. Fractional or out-of-range values raise an argument error (not silently floored). Re-idles to 0 when the script stops. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def infuse(self) -> ActionResult[Literal["ok", "output_full", "empty", "busy"]]:
 """Produce a **Luminous** sample at the current glow in `self.output`, preserving every existing property and adding the tuned glow. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def discard(self) -> ActionResult[Literal["ok", "empty", "busy", "output_full"]]:
 """Stage the unchanged chamber sample in `self.output`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 input: InputSlot
 output: OutputSlot
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `BioOrder`

```python
class BioOrder:
 """bio_exchange.orders() / bio_exchange.active_order() / get_component(\"bio_exchange_1\").orders()"""
 id: _str
 name: _str
 biome: Literal["frozen", "coastal", "geothermal", "volcanic", "deep"]
 requires: _dict[_str, Any]
 reward: _float
 status: Literal["available", "active", "complete"]
 delivered: _dict[_str, Any]
 in_transit: _dict[_str, _int]
 percent: _float
 target_glow: _tuple[_float, _float, _float] | None
 required_genes: _dict[_str, _list[_str]] | None
```

## `BiomassMixer`

```python
class BiomassMixer(Component):
 """Biomass Mixer: Blends biome essences into biomass. The global Biomass phase sets the minimum diversity, while every additional well-balanced essence can raise output. Mk II raises output 4.5× while essence demand rises only 2.4×, at five times the power draw."""
 name: _str
 outpost: OutpostRef
 def biomass_rate(self) -> _float:
 """Biomass tons produced last tick, in **t/h**. Sum across every Biomass Mixer on the planet = total biomass production rate."""
 ...
 def active_essences(self) -> _int:
 """Number of essence input buffers currently carrying supply (**0-5**). The current phase decides the minimum required by `required_essences()`. Extra balanced essence types can increase output."""
 ...
 def mixing_essences(self) -> _int:
 """Number of supplied essence types selected for the strongest balanced mix on the last tick (**0-5**). The Mixer evaluates every diversity level from the phase minimum upward, so a weak extra feed can never reduce output."""
 ...
 def tier(self) -> _int:
 """Installed Mixer tier: **1** for Mk I or **2** for Mk II. Mk II produces **4.5×** biomass while consuming only **2.4×** as much of every selected essence, with **5×** power draw, so it yields **87.5%** more biomass per ton of essence."""
 ...
 def is_stalled(self) -> _bool:
 """`True` if the mixer is powered and fewer input buffers contain usable essence than the current Biomass phase requires. Buffered essence counts even without new inflow. `False` when unpowered or enough essence types are available. Connect each missing essence input to a compatible source and complete a remote Liquid Pipe route where needed; Biomass phases only advance and never drop."""
 ...
 def phase(self) -> _int:
 """The global Biomass phase (**1-6**), derived from cumulative biomass tons, using the same thresholds as the Sensors phase badge. The phase sets the minimum essence diversity but does not directly multiply output."""
 ...
 def required_essences(self) -> _int:
 """How many distinct biome essences must be supplied this phase (**1-5**, equal to the phase, capped at 5). Below this the Mixer stalls. Supplying more can raise output when the larger mix is balanced enough."""
 ...
 frozen_essence_in: FluidPort
 coastal_essence_in: FluidPort
 geothermal_essence_in: FluidPort
 volcanic_essence_in: FluidPort
 deep_essence_in: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `BiomassSensor`

```python
class BiomassSensor(Component):
 """Biomass Sensor: Reports cultivated biomass on the planet, in tons. Updates live as Biomass Mixers produce. Available after the Biosphere research lands; no calibration step."""
 name: _str
 def get_value(self) -> _float:
 """Returns total biomass tonnage on the planet as a number. `0` before any Biomass Mixer has produced."""
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
 coords: _tuple[_float, _float]
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
 """DNA Sequencer: Splices genes into geothermal fragments so they carry what an order needs. You work at the gene level, load a fragment, read the genes it has and the genes it needs, splice the target set in, the machine composes the DNA for you. One splice per fragment."""
 name: _str
 outpost: OutpostRef
 def load(self, fragment_id: _str, properties: Any = ..., property_match: _str | None = ...) -> ActionResult[Literal["ok", "chamber_occupied", "not_in_input", "invalid_fragment", "invalid_properties", "invalid_property_match", "busy"]]:
 """Pull a geothermal sample of `fragment_id` from `self.input` into the chamber, `self.load(\"gw_cardiac_node\")`. Optional `properties` and `property_match` select a specific identity using the standard any, subset, or exact convention. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 chamber: ChamberFragment | None
 def genes(self) -> _list[_str] | None:
 """Lists the genes currently carried by the chambered fragment, such as `[\"cold_tolerance\", \"pressure_tolerance\"]`, or returns `None` when empty. `splice()` takes time. On completion, the fragment moves to output and the chamber becomes empty. If output is full, the spliced fragment stays in the chamber until space is available."""
 ...
 def gene_catalog(self) -> _list[_str]:
 """Every gene id the machine can splice, `self.gene_catalog()` returns the full list (e.g. `[\"heat_resistance\", \"acid_resistance\", \"cold_tolerance\", \"pressure_tolerance\", \"toxin_resistance\", \"radiation_shield\"]`), the valid values to pass to `splice()`."""
 ...
 def splice(self, genes: _list[Any]) -> ActionResult[Literal["ok", "destroyed", "empty", "unknown_gene", "busy", "output_full"]]:
 """Replace the chambered fragment's gene set with exactly `genes`, then place it in `self.output` while preserving every unrelated property. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def discard(self) -> ActionResult[Literal["ok", "empty", "busy", "output_full"]]:
 """Stage the chamber fragment in `self.output` without splicing. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 input: InputSlot
 output: OutputSlot
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `FeedMaker`

```python
class FeedMaker(Component):
 """Feed Maker: Crafts the creature feeds that Habitat colonies eat, working like the Fabricator from a recipe you choose. Each creature's recipe unlocks through a Biolab order, so it only makes what you've unlocked."""
 name: _str
 outpost: OutpostRef
 def list_recipes(self) -> _list[Recipe]:
 """Lists the feed recipes unlocked through Bio Lab orders, one `Recipe` per creature whose feed you can craft. Locked recipes do not appear. Each recipe includes its tier, id, name, inputs, output, duration, and power draw. Use `for recipe in self.list_recipes(): print(recipe.tier, recipe.id)` to discover what is available."""
 ...
 def find_recipe(self, recipe_id: _str) -> Recipe | None:
 """Find one unlocked feed recipe by id without looping through `list_recipes()`. Returns its `Recipe` object, or `None` when the id is unknown, locked, or belongs to another machine."""
 ...
 def set_recipe(self, recipe_or_id: Any) -> ActionResult[Literal["ok", "unknown_recipe", "offline", "recipe_locked", "busy", "material_mismatch"]]:
 """Pick which creature feed to craft by id or by passing a Recipe from `list_recipes()`, e.g. `self.set_recipe(\"craft_feed_salt_tortoise\")`. Once set, ProcessingSystem crafts automatically whenever the stockpile holds the inputs and the output bin has room. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def clear_recipe(self) -> ActionResult[Literal["ok", "busy", "material_present"]]:
 """Unset the selected feed recipe and leave the Feed Maker idle. The input stockpile stays loaded. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def get_recipe(self) -> Literal["", "craft_feed_salt_tortoise", "craft_feed_magmatic_annelid", "craft_feed_mycelial_husk", "craft_feed_mantle_strider", "craft_feed_glasswing_mantis", "craft_feed_veil_mantle", "craft_feed_vault_crab", "craft_feed_tidal_cephalopod", "craft_feed_bone_walker", "craft_feed_vent_drifter", "craft_feed_hive_sentinel", "craft_feed_hollow_choir", "craft_feed_ferric_sea_lily", "craft_feed_crustal_echo", "craft_feed_glacial_wyrm", "craft_feed_spire_drake"]:
 """Returns the current recipe id, or `\"\"` when none is set (or the set recipe is no longer unlocked). Use to check state before re-setting: `if self.get_recipe() == \"\": self.set_recipe(...)`."""
 ...
 def get_recipe_inputs(self) -> _dict[_str, _int]:
 """Dict mapping each input `item_id` → units consumed per craft for the current recipe (empty dict if no recipe set). Iterate it to know what to stock: `for item, qty in self.get_recipe_inputs().items(): self.input.take(item, qty * 5)`."""
 ...
 def get_stockpile(self) -> _dict[_str, _int]:
 """Dict mapping each `item_id` currently in the input stockpile → its unit count. Read it to see what's loaded before crafting."""
 ...
 def get_stockpile_used(self) -> _int:
 """Total units across every material in the input stockpile. Compare to `get_stockpile_capacity()` to avoid overfilling."""
 ...
 def get_stockpile_capacity(self) -> _int:
 """Combined unit cap across all materials in the input stockpile. The cap is shared, many materials sum against one limit."""
 ...
 def is_running(self) -> _bool:
 """`True` while a craft is actively advancing this tick (recipe set, inputs present, output has room). `False` when starved, output-full, idle, or powered off. Poll to detect a stalled line."""
 ...
 def get_progress(self) -> _float:
 """Fraction **0-1** through the current craft. Resets to 0 each time a craft completes (a batch of feed lands in the output bin) and starts again if inputs remain."""
 ...
 def get_output_count(self) -> _int:
 """Completed feed units waiting in the output bin for pickup. Push them onward with `self.output.send(...)` before the bin fills (a full output bin stalls crafting)."""
 ...
 input: InputSlot
 output: OutputSlot
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `FragmentLocation`

```python
class FragmentLocation:
 """bio_collector.scan()"""
 coords: _tuple[_float, _float]
 distance: _float
 cataloged: _bool
 fragment_id: Literal["gw_cranial_plate", "gw_caudal_fin", "gw_cardiac_node", "gw_jaw_fang", "gw_spinal_vertebra", "vc_dorsal_carapace", "vc_mandible_claw", "vc_antenna_cluster", "vc_walking_leg", "vc_eye_stalk", "oc_cranium", "oc_tentacle_arm", "oc_chitin_beak", "oc_ink_sac", "oc_lens_eye", "bw_skull", "bw_foreclaw", "bw_ribcage", "bw_hindlimb", "bw_tail_spike", "vd_bell", "vd_nematocyst", "vd_neural_mesh", "vd_photophore", "vd_tendril", "mh_fruiting_body", "mh_spore_pod", "mh_mycelium_root", "mh_chitin_node", "mh_stigmatic_disc", "hs_mandible", "hs_wing_membrane", "hs_thorax_plate", "hs_abdomen_segment", "hs_compound_eye", "ms_chelicera", "ms_leg_tarsus", "ms_pedipalp", "ms_abdomen_sclerite", "ms_eye_cluster", "hc_aperture_lip", "hc_shell_whorl", "hc_septum_plate", "hc_beak", "hc_tentacle_crown", "ma_cranial_papilla", "ma_cuticle_molt", "ma_ganglion_node", "ma_chitinous_seta", "ma_luminous_ring", "gm_compound_eye", "gm_folded_wing", "gm_raptorial_claw", "gm_abdominal_sheath", "gm_antennal_whip", "fs_calyx_plate", "fs_arm_segment", "fs_stalk_columnal", "fs_oral_tegmen", "fs_holdfast_rootlet", "sd_cranial_crest", "sd_wing_membrane", "sd_obsidian_scale", "sd_tail_barb", "sd_talon", "ce_stalked_eye", "ce_swimmeret_lobe", "ce_mouth_disc", "ce_great_appendage", "ce_cephalic_photophore", "st_scute_plate", "st_plastron_shard", "st_limb_claw", "st_beak", "st_carapace_neural", "vm_cephalic_horn", "vm_wing_sheet", "vm_gill_filament", "vm_tail_barb", "vm_ventral_photophore"] | None
 name: _str | None
 rarity: Literal["common", "uncommon", "rare", "legendary"] | None
```

## `LifeFormSample`

```python
class LifeFormSample:
 """PortableBioScanner.scan().scan.life_forms[i] after status == \"ok\""""
 type: Literal["ice_algae", "snow_moss", "frost_lichen", "cold_spores", "ice_crust", "frost_fungus", "sea_algae", "tide_moss", "shore_lichen", "brine_plankton", "salt_crust", "coral_fungus", "vent_algae", "steam_moss", "heat_lichen", "hot_spores", "heat_crust", "vent_fungus", "sulfur_moss", "cinder_lichen", "ash_spores", "lava_algae", "magma_crust", "black_fungus", "cave_moss", "stone_lichen", "crystal_spores", "deep_algae", "stone_mat", "cave_fungus"]
 tons: _float
 remaining_tons: _float
 rarity: Literal["common", "uncommon", "rare"]
 biome: Literal["frozen", "coastal", "geothermal", "volcanic", "deep"]
```

## `OilGenerator`

```python
class OilGenerator(Component):
 """Oil Generator: Burns oil into strong buffered bridge power. Oil wells pulse between active and dormant phases, so bank their output in Liquid Tanks for continuous generation. Idle until a script runs it."""
 name: _str
 outpost: OutpostRef
 def power_output(self) -> _float:
 """Watts fed to the grid on the last power tick. **0** when throttled to 0 OR oil_in buffer is starved. The generator scales output proportionally to available oil, so a partially-starved generator produces partial power. Updates once per power tick, a fresh `set_throttle(...)` is reflected on the next tick."""
 ...
 def oil_consumption(self) -> _float:
 """Actual oil consumed on the last power tick, in t/h. With enough oil supplied, demand scales linearly with throttle from **0 t/h** at 0 to **8 t/h** at 1. Partial or total oil starvation lowers the actual rate."""
 ...
 def throttle(self) -> _float:
 """Current throttle (**0-1**). **0** by default, generator idles until scripted."""
 ...
 def set_throttle(self, rate: _float) -> ActionResult[Literal["ok"]]:
 """Set the generator throttle (**0-1**). Power output and oil consumption scale linearly with the throttle. This script-owned setpoint resets to **0** when the script stops, ends, or errors, so keep the control loop running while the Generator should operate. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 oil_in: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `OxygenGenerator`

```python
class OxygenGenerator(Component):
 """Oxygen Generator: Draws CO2 from the atmosphere and turns it into breathable oxygen, one of the core steps toward a livable planet. It runs only when a script sets its intake."""
 name: _str
 outpost: OutpostRef
 input: InputSlot
 water_in: FluidPort
 def set_intake(self, value: _float) -> ActionResult[Literal["ok"]]:
 """Set CO2 intake rate for this tick. Call `self.set_intake(atmosphere.get_co2() / 10)` each iteration, the chamber's peak-efficiency sweet spot is exactly **1/10th** of ambient CO2. Values above or below that point reduce efficiency smoothly; there is no precision-sensitive cutoff. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def waste(self) -> _float:
 """Current carbon waste level (**0-100**). Production runs clean below **60**, drops linearly **60-100**, and stalls (zero output) at **100**. Check this each iteration before calling `dump_waste()`, dumping between **50-60** is penalty-free; dumping elsewhere costs efficiency."""
 ...
 def dump_penalty(self) -> _float:
 """Current efficiency penalty from the last `dump_waste()` call (**0-1**). `0` means no active waste-clearing penalty; `0.25` means output is reduced by 25%. A bad dump remains visible here until the next `dump_waste()` call."""
 ...
 def dump_waste(self) -> WasteDumpResult[Literal["ok"]]:
 """Clear accumulated carbon waste. Call `result = self.dump_waste()` when `waste()` is in the **50-60** sweet spot for a clean dump. The penalty lingers until the next dump. Fixed result contract: `WasteDumpResult`; branch on `.status` and read `.message`. Payload fields: `.penalty`."""
 ...
 def efficiency(self) -> _float:
 """Current conversion efficiency (**0-100%**). Hits **100%** when intake matches **CO2/10**, CO2 is available, waste is at or below **60**, and no dump penalty is active. Waste above **60** reduces efficiency; waste at **100** stalls production. The **50-60** range is the clean window for `dump_waste()`, dumping outside it applies an efficiency penalty you can read with `dump_penalty()`."""
 ...
 def output(self) -> _float:
 """Current O2 production rate in **ppt/h** at the current settings. Reflects `efficiency() × tier multiplier`, capped by available CO2. Reads `0` if the machine is unpowered, no script is running, CO2 is exhausted, or waste has stalled production. Recomputed live on every read, a fresh `set_intake(...)` is reflected immediately. Use this for live dashboards or to detect degradation mid-loop."""
 ...
 def tier(self) -> _int:
 """Permanently installed Mk tier as an integer (**1-4**). Upgrade packs raise this value; temporary Mk III fluid starvation does not. Compare with `effective_tier()` when diagnosing a supplied or degraded generator."""
 ...
 def is_degraded(self) -> _bool:
 """`True` when a Mk III pack is starved of its required fluid input and the machine has fallen back to the previous tier multiplier for this tick. Check after applying a Mk III pack and before trusting `output()` to meet your Mk III projections, if `True`, check `self.water_in.level()` and the upstream pipe."""
 ...
 def effective_tier(self) -> _int:
 """The tier actually in effect this tick: `tier()` normally, previous tier while `is_degraded()` is `True`. Scripts that decide whether to route more water toward this generator should compare `effective_tier()` with `tier()`."""
 ...
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `PortableBioExtractor`

```python
class PortableBioExtractor:
 """self.bio_extractor (drones)"""
 def extract(self) -> BioExtractionResult[Literal["ok", "not_mounted", "scrambled", "busy", "not_at_location", "not_scanned", "cooling", "no_cargo_space"]]:
 """Yielding harvest at the discovered permanent biosite under a hovering drone. The drone stays occupied until completion, including across a script stop and restart. The module has a 25 t chamber for one life-form type; Cargo Pods add capacity. Partial depletion persists and cooldown starts only when the site is empty. Fixed result contract: `BioExtractionResult`; branch on `.status` and read `.message`. Payload fields: `.extracted`."""
 ...
```

## `PortableBioScanner`

```python
class PortableBioScanner:
 """self.bio_scanner (drones)"""
 def scan(self) -> BioScanResult[Literal["ok", "not_mounted", "scrambled", "busy", "not_at_location"]]:
 """Yielding scan at the hovering drone's current whole-number coordinate. A valid non-site coordinate completes with an empty biological scan. Repeat scans are free. Fixed result contract: `BioScanResult`; branch on `.status` and read `.message`. Payload fields: `.scan`."""
 ...
```

## `PressureGenerator`

```python
class PressureGenerator(Component):
 """Pressure Generator: Compresses the thin atmosphere to raise surface pressure. It runs best when a script catches each sync window as its gauge sweeps; missed windows cost efficiency."""
 name: _str
 outpost: OutpostRef
 input: InputSlot
 water_in: FluidPort
 def gauge(self) -> _float:
 """Current value on the resonance sweep (**0-100**). Rises each tick and wraps at **100**. Compare it to `next_window_low()` and `next_window_high()`; when the gauge is inside that range, call `sync()`."""
 ...
 def next_window_low(self) -> _float:
 """Lower edge of the current sweep's sync window. Use with `next_window_high()` and `gauge()`; call `sync()` when the gauge is inside the range. The value changes when the sweep wraps to the next cycle."""
 ...
 def next_window_high(self) -> _float:
 """Upper edge of the current sweep's sync window. Use with `next_window_low()` and `gauge()`; call `sync()` when the gauge is inside the range. The value changes when the sweep wraps to the next cycle."""
 ...
 def sync(self) -> ActionResult[Literal["ok"]]:
 """Try to sync this sweep. First call per sweep counts; later calls before the gauge wraps do nothing. Hit (gauge in window) -> **+25%** efficiency. Miss (outside window, or no sync before the sweep ends) -> **-10%**. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def efficiency(self) -> _float:
 """Current compression efficiency (**0-100%**). Climbs with hits, drops with misses, floored at **0**. A well-tuned script holds this at or near **100%** by hitting every cycle's window. Use it to detect a script that's out of sync with the shifting window."""
 ...
 def output(self) -> _float:
 """Current **kPa/h** production rate at the current `efficiency()`. Proportional to `efficiency() × tier multiplier`. The resonance gauge advances slowly, so pressure progress is best judged from `efficiency()` and the per-day projection on the sensor display rather than from a single `output()` read."""
 ...
 def tier(self) -> _int:
 """Permanently installed Mk tier as an integer (**1-4**). Upgrade packs raise this value; temporary Mk III fluid starvation does not. Compare with `effective_tier()` when diagnosing a supplied or degraded generator."""
 ...
 def is_degraded(self) -> _bool:
 """`True` when a Mk III pack is starved of its required fluid input and the machine has fallen back to the previous tier multiplier for this tick. Check after applying a Mk III pack, if `True`, the pack is in fallback; investigate `self.water_in.level()` and the upstream supply."""
 ...
 def effective_tier(self) -> _int:
 """The tier actually in effect this tick: `tier()` normally, previous tier while `is_degraded()` is `True`. Scripts rebalancing water flow between generators should compare `effective_tier()` with `tier()`."""
 ...
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `SolarGenerator`

```python
class SolarGenerator(Component):
 """Solar Generator: Turns sunlight into up to **50 W** for the grid when a script tracks the Sun. Poor tilt reduces daytime output, and night produces **0 W**."""
 name: _str
 outpost: OutpostRef
 def set_tilt(self, degrees: _float) -> ActionResult[Literal["ok"]]:
 """Set the panel tilt angle in degrees. Range is **0°** (flat) to **90°** (vertical); values outside are clamped. A well-tuned tracker holds output near its maximum throughout the day; a fixed tilt wastes a large fraction. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def tilt(self) -> _float:
 """Current panel tilt setpoint in degrees (**0-90**). Returns the value the script last wrote via `self.set_tilt(...)`, or the default rest angle for an idle panel. Use to verify your sweep loop or to step a tilt search against the previous value."""
 ...
 def get_output(self) -> _float:
 """Current power output in watts for this specific generator. Returns **0** if powered off. Computed live from sun elevation vs panel tilt, use it to verify the tracker is holding peak (compare current output against the panel's rated max)."""
 ...
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `Specimen`

```python
class Specimen:
 """bio_collector.cargo / bio_lab.specimen"""
 coords: _tuple[_float, _float]
 distance: _float
 stage: Literal["collected", "analyzed"]
 fragment_id: Literal["gw_cranial_plate", "gw_caudal_fin", "gw_cardiac_node", "gw_jaw_fang", "gw_spinal_vertebra", "vc_dorsal_carapace", "vc_mandible_claw", "vc_antenna_cluster", "vc_walking_leg", "vc_eye_stalk", "oc_cranium", "oc_tentacle_arm", "oc_chitin_beak", "oc_ink_sac", "oc_lens_eye", "bw_skull", "bw_foreclaw", "bw_ribcage", "bw_hindlimb", "bw_tail_spike", "vd_bell", "vd_nematocyst", "vd_neural_mesh", "vd_photophore", "vd_tendril", "mh_fruiting_body", "mh_spore_pod", "mh_mycelium_root", "mh_chitin_node", "mh_stigmatic_disc", "hs_mandible", "hs_wing_membrane", "hs_thorax_plate", "hs_abdomen_segment", "hs_compound_eye", "ms_chelicera", "ms_leg_tarsus", "ms_pedipalp", "ms_abdomen_sclerite", "ms_eye_cluster", "hc_aperture_lip", "hc_shell_whorl", "hc_septum_plate", "hc_beak", "hc_tentacle_crown", "ma_cranial_papilla", "ma_cuticle_molt", "ma_ganglion_node", "ma_chitinous_seta", "ma_luminous_ring", "gm_compound_eye", "gm_folded_wing", "gm_raptorial_claw", "gm_abdominal_sheath", "gm_antennal_whip", "fs_calyx_plate", "fs_arm_segment", "fs_stalk_columnal", "fs_oral_tegmen", "fs_holdfast_rootlet", "sd_cranial_crest", "sd_wing_membrane", "sd_obsidian_scale", "sd_tail_barb", "sd_talon", "ce_stalked_eye", "ce_swimmeret_lobe", "ce_mouth_disc", "ce_great_appendage", "ce_cephalic_photophore", "st_scute_plate", "st_plastron_shard", "st_limb_claw", "st_beak", "st_carapace_neural", "vm_cephalic_horn", "vm_wing_sheet", "vm_gill_filament", "vm_tail_barb", "vm_ventral_photophore"] | None
 name: _str | None
 rarity: Literal["common", "uncommon", "rare", "legendary"] | None
 recipe: _dict[_str, Any] | None
 production_tier: _int | None
 glow: _tuple[_float, _float, _float] | None
 genes: _list[_str]
```

## `generator`

```python
class generator:
 """calling a function containing `yield` · generator expressions"""
 def send(self, value: Any) -> Any:
 """Resume the generator and make `value` the result of its paused `yield`. Returns the next yielded value. Sending a non-`None` value before the first yield raises `TypeError`; completion raises `StopIteration`."""
 ...
 def throw(self, exception: Any) -> Any:
 """Raise an exception at the generator's paused `yield`. Returns the next value if the generator catches it and yields again; otherwise the exception propagates."""
 ...
 def close(self) -> None:
 """Stop the generator by raising `GeneratorExit` at its paused yield. `finally` cleanup runs before this returns. A generator that yields while closing raises `RuntimeError`."""
 ...
 def __iter__(self) -> generator:
 """Return this generator. Generators are one-shot iterators."""
 ...
 def __next__(self) -> Any:
 """Resume the generator with `None` and return its next yielded value. Completion raises `StopIteration`."""
 ...
 __name__: _str
 __qualname__: _str

# Component interfaces
```
