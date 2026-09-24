# Models: Atmosphere, Plant, Seed & Weather Models

Granular data models and return types extracted from `__builtins__.pyi`.

## `Atmosphere`

```python
class Atmosphere(Component):
    """Atmosphere: Planetary atmosphere, read gas composition, pressure, temperature, and the planet's heat-units progression metric (`get_heat()`). Oxygen and pressure reads require their sensors to be repaired."""
    name: _str
    def get_co2(self) -> _float:
        """Current CO2 level in parts per thousand (ppt). Oxygen generation consumes CO2 **1:1**, so this value falls as oxygen rises. CO2 is returned to the atmosphere by burning oil (Oil Generator), incinerating items (Waste Processor), and, at scale, by wildlife respiration (established colonies exhale CO2). A small volcanic outgassing trickle replenishes CO2 when reserves are low."""
        ...
    def get_o2(self) -> _float:
        """Current oxygen level in parts per thousand (ppt). Requires the oxygen sensor to be repaired."""
        ...
    def get_n2(self) -> _float:
        """Current nitrogen level in parts per thousand (ppt)."""
        ...
    def get_pressure(self) -> _float:
        """Current atmospheric pressure in kPa. Requires the pressure sensor to be repaired."""
        ...
    def get_temperature(self) -> _float:
        """Current surface temperature in °C. This is a **display value**, a non-linear transform of the heat-units metric. For terraforming progress or heat cutoffs, use `get_heat()`, not this."""
        ...
    def get_heat(self) -> _float:
        """Current accumulated **heat units**, the temperature pillar's progression metric, the exact value temperature research and phase thresholds compare against (the Research page shows the current targets). Gate heat cutoffs on this, the way `get_o2()` / `get_pressure()` work for those pillars. Unlike `get_temperature()` (surface °C, a non-linear display value), a difference in heat units IS terraforming progress. Starts at **0**."""
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
    """Oxygen Sensor: An atmospheric oxygen probe that landed broken. It reports a raw voltage until a script works out the calibration and repairs it, after which it reads oxygen directly."""
    name: _str
    def get_value(self) -> _float:
        """Before repair, read raw voltage from the uncalibrated probe as a small decimal value. This is not yet a ppt reading; compare it with a known reference to calculate the calibration factor. After repair, read the current atmospheric oxygen level in ppt directly."""
        ...
    def calibrate(self, value: _float) -> ActionResult[Literal["started", "already_repaired", "no_source", "already_testing"]]:
        """Start the black-box calibration suite with the processed value: `result = self.calibrate(raw_value * factor)`. The suite then checks the whole script against several readings. A fully correct suite repairs the sensor; failed test cases remain visible in the console. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
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
    """Plant Terraformer: The sole converter from harvested physical Forage to permanent Plants km². Load its input through ordinary timed item transfers; its high-capacity feeder handles 16 items per step at Mk I and 80 at Mk II. Each phase adds Water, Salt, Fertilizer, then Growth Accelerant. Mk I stops at the Fields threshold; Mk II carries the final two phases."""
    name: _str
    outpost: OutpostRef
    def set_enabled(self, enabled: _bool) -> ActionResult[Literal["ok"]]:
        """Enable or pause conversion. `True` starts a cycle whenever the onboard item holders and Water can supply at least one proportional Forage unit. A cycle runs for **3 hours** at full outpost efficiency. Stopping this machine's script resets the setpoint to `False`; an in-flight batch remains loaded. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def is_enabled(self) -> _bool:
        """`True` when the current machine script has commanded conversion on."""
        ...
    def tier(self) -> _int:
        """Permanently installed Plant Terraformer tier as an integer (**1-2**). Mk II raises batch throughput and enables the late Plants recipes."""
        ...
    def status(self) -> Literal["complete", "disabled", "no_power", "needs_mk2", "no_forage", "no_water", "no_salt", "no_fertilizer", "no_accelerant", "running"]:
        """Exact live state: `\"complete\"`, `\"disabled\"`, `\"no_power\"`, `\"needs_mk2\"`, `\"no_forage\"`, `\"no_water\"`, `\"no_salt\"`, `\"no_fertilizer\"`, `\"no_accelerant\"`, or `\"running\"`."""
        ...
    def is_running(self) -> _bool:
        """`True` while a conversion cycle is running. An unpowered or disabled machine keeps its in-flight batch but reads `False` until it resumes."""
        ...
    def get_progress(self) -> _float:
        """Completion of the current conversion cycle, **0-1**. A full cycle requires **3 hours** of work at 100% outpost efficiency; overcrowding slows its progress proportionally. Reads **0** whenever no batch is loaded."""
        ...
    def batch_size(self) -> _int:
        """Whole Forage items in the running cycle, or the batch that can load now. A full batch is **1,200** at Mk I and **6,600** at Mk II. Limited materials or a nearby phase boundary load less."""
        ...
    def km2_rate(self) -> _float:
        """This machine's current permanent Plants output in km²/h. It combines the loaded batch, its nominal **3 hour** work cycle, the pinned phase exchange rate from **20 km² per Forage** early to **1 km² per 3 Forage** late, and this outpost's overcrowding efficiency. Returns **0** while blocked, disabled, or complete."""
        ...
    def phase(self) -> _int:
        """Current global Plants phase number, **1-6**."""
        ...
    def recipe_tier(self) -> _int | None:
        """Derived production tier of the current cumulative Plants conversion recipe. Returns `None` after Continental completion."""
        ...
    def next_threshold(self) -> _float:
        """Permanent Plants km² required for the next phase. At completion, returns the **5,000,000 km²** ceiling."""
        ...
    def remaining(self) -> _float:
        """Permanent Plants km² still needed for the next phase. Returns **0** when Continental is complete."""
        ...
    def required_inputs(self) -> _list[_str]:
        """Current cumulative material ids. Starts with `forage`, then adds `water`, `salt`, the `fertilizer` category, and `growth_accelerant` across the five conversions."""
        ...
    def batch_requirements(self) -> _dict[_str, _int]:
        """Exact amounts for the largest next batch allowed by this tier and phase. The dict uses `forage`, `water`, `salt`, `fertilizer_potency`, and `growth_accelerant` as needed. Salt and Growth Accelerant are whole-item counts, rounded up per batch. Fertilizer potency is a whole number. It does not shrink when onboard stock is short."""
        ...
    def fertilizer_potency(self, item_id: _str) -> _int:
        """Return one Fertilizer item's whole potency: **10** for Mk I, **30** for Mk II, or **50** for Mk III. Any other item id raises `ValueError`."""
        ...
    input: InputSlot
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

## `PlantsSensor`

```python
class PlantsSensor(Component):
    """Plants Sensor: Reports permanent vegetated km² produced by the Plant Terraformer fleet. Available after the Biosphere research lands. Field growth alone does not change this value."""
    name: _str
    def get_value(self) -> _float:
        """Returns permanent Plants km² as a number. Plant Terraformers are the only writers; repeated crop cycles, diversity, providers, Fertilizer, and Yield Amplifier increase the physical Forage supply they process."""
        ...
```

## `PressureSensor`

```python
class PressureSensor(Component):
    """Pressure Sensor: An atmospheric pressure probe that landed broken. Its readings come out scrambled until a script stabilizes the repair signal, after which it reads pressure directly."""
    name: _str
    def get_value(self) -> _int:
        """Current unstable repair reading as an integer. If the value is odd, add **1**; if it is even, use it unchanged. After repair, this method returns real atmospheric pressure in kPa."""
        ...
    def stabilize(self, value: _float) -> ActionResult[Literal["started", "already_repaired", "no_source", "already_testing"]]:
        """Start the black-box stabilization suite with the corrected even reading: `result = self.stabilize(corrected_value)`. The suite then checks the whole script against several readings. A fully correct suite repairs the sensor; failed test cases remain visible in the console. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
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

## `Recipe`

```python
class Recipe:
    """list_recipes() / find_recipe() on Smelter, Fabricator, Feed Maker, Refiner, and Fuel Assembler"""
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
    """Refiner: Refines raw exotic feedstock into creature-grade gas or liquid, using tar as a reagent. Only uncommon and rare exotics need refining; commons are used directly. Recipes unlock through Biolab orders."""
    name: _str
    outpost: OutpostRef
    def list_recipes(self) -> _list[Recipe]:
        """Lists the refining recipes unlocked through Bio Lab orders, one `Recipe` per exotic fluid. Locked recipes do not appear. Each recipe includes `.tier`, names its exact raw feedstock in `.input_fluid`, gives port tons consumed per run in `.fluid_inputs`, lists tar in `.inputs`, and identifies the refined product and output port through `.output_fluid` / `.fluid_outputs`. Use `for recipe in self.list_recipes(): print(recipe.tier, recipe.id, recipe.input_fluid, recipe.output_fluid)` to discover what is available."""
        ...
    def find_recipe(self, recipe_id: _str) -> Recipe | None:
        """Find one unlocked refining recipe by id without looping through `list_recipes()`. Returns its `Recipe` object, or `None` when the id is unknown, locked, or belongs to another machine."""
        ...
    def set_recipe(self, recipe_or_id: RecipeRef) -> ActionResult[Literal["ok", "unknown_recipe", "offline", "recipe_locked", "busy", "output_busy"]]:
        """Pick which exotic to refine by id or by passing a Recipe from `list_recipes()`, e.g. `self.set_recipe(\"refine_chlorine\")`. Once set, the refiner crafts automatically whenever the raw feedstock + tar are present and the out port has room. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def clear_recipe(self) -> ActionResult[Literal["ok", "busy", "material_present"]]:
        """Unset the selected refine recipe and leave the Refiner idle. Tar and raw feedstock inputs are preserved because they are staged supply. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def purge_input(self) -> ActionResult[Literal["ok", "empty", "busy"]]:
        """Vents whatever raw feedstock is sitting in `gas_in` and `liquid_in`, releasing the port so it can accept a different fluid. The feedstock ports take the first fluid that reaches them and then only accept that one, so a port wired to the wrong Cap holds a fluid the recipe cannot use. Purge it, rewire, and carry on: `self.purge_input()` then `self.gas_in.connect(\"Raw Sulfur Cap\")`. The vented fluid is destroyed, and tar in the input bin is untouched. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def get_recipe(self) -> Literal["", "refine_sulfur_gas", "refine_cryofluid", "refine_chlorine", "refine_quicksilver"]:
        """Returns the current recipe id, or `\"\"` when none is set (or the set recipe is no longer unlocked). Use to check state before re-setting: `if self.get_recipe() == \"\": self.set_recipe(\"refine_sulfur_gas\")`."""
        ...
    def get_recipe_inputs(self) -> _dict[_str, _int]:
        """A dict mapping each input `item_id` → units consumed per craft, for the Refiner this is the **tar** cost, e.g. `{\"tar\": 5}` for a rare exotic. Empty dict if no recipe is set. Read it to keep the tar bin stocked: `for item, qty in self.get_recipe_inputs().items(): self.input.take(item, qty * 5)`. (The raw-feedstock fluid amount is metered on the input ports, not listed here.)"""
        ...
    def is_running(self) -> _bool:
        """`True` while a refine craft is actively advancing this tick (recipe set + unlocked, raw feedstock + tar present, out port has room). `False` when stalled, idle, or powered off."""
        ...
    def is_stalled(self) -> _bool:
        """`True` when the refiner is powered and a recipe is set but the craft can't advance, for example because raw feedstock is missing (check `self.gas_in.level()` / `self.liquid_in.level()`), tar has run out (refill the input bin), or the refined-fluid out port is full (downstream backpressure, drain the out tank). `False` when unpowered, running, or no recipe is set. Poll to diagnose a stuck line."""
        ...
    def get_rate(self) -> _float:
        """Refined exotic produced this tick in t/h. **0** when stalled or idle. Use to confirm throughput while balancing feedstock against demand."""
        ...
    def get_progress(self) -> _float:
        """Fraction **0-1** through the current refine craft. Resets to 0 each time a craft completes (a batch of refined fluid lands in the out port) and starts again if the feedstock + tar remain."""
        ...
    gas_in: FluidPort
    liquid_in: FluidPort
    gas_out: FluidPort
    liquid_out: FluidPort
    input: InputSlot
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

## `SeedMaker`

```python
class SeedMaker(Component):
    """Seed Maker: An outpost processing building that combines three life-form samples into a viable seed. Most blends fail; the working recipes are unique to this planet and found by trial, and a discovered one can be re-run for more."""
    name: _str
    outpost: OutpostRef
    def combine(self, blend: _list[_str]) -> SeedResult[Literal["seed_found", "sludge", "locked", "busy", "missing_life_forms", "output_full"]]:
        """Run the exact three different life-form ids loaded in this machine's reaction chamber. Every accepted trial consumes the chamber's **1 t of each**. The one-seed result bay must be empty before any trial can start. Fixed result contract: `SeedResult`; branch on `.status` and read `.message`. Payload fields: `.seed_id` and `.species`."""
        ...
    def life_forms(self) -> _list[_str]:
        """List of the **30** accepted life-form item ids. For each `blend` from `combinations(self.life_forms(), 3)`, load its three items with `self.input.take(item_id, 1)`, then call `self.combine(blend)`. Enumeration does not move materials. Send any resulting physical seed from `self.output` before continuing."""
        ...
    def is_running(self) -> _bool:
        """`True` while a combine trial is in flight."""
        ...
    def get_progress(self) -> _float:
        """Progress of the current combine trial as **0-1**; returns **0** when idle."""
        ...
    def get_output_count(self) -> _int:
        """Number of physical seeds waiting in the single-result bay: **0** or **1**."""
        ...
    def recipes(self) -> _list[SeedRecipe]:
        """List of `SeedRecipe` for every blend discovered so far, the same discover-once-kept-forever journal the Flora / Seed Recipes tab shows. Each carries `.tier`, the physical `.seed_id`, bare `.species`, `.blend`, `.requirements`, `.requirement`, and `.growth_time`. `.requirements` is the programmable form: every `PlantRequirement` has `.kind` and optional `.species`, so companion and antagonist entries identify the exact related plant. `.requirement` remains a compact string summary. Empty until your first hit; re-run a known `.blend` with `self.combine(...)` to reproduce that seed without re-sweeping."""
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

## `SeedRecipe`

```python
class SeedRecipe:
    """self.recipes() (Seed Maker)"""
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
    """Smelter: Refines raw ore into metal stock, one unit at a time, following a recipe you choose. A script sets the recipe, feeds ore in from a bin, and drains the finished metal out to another."""
    name: _str
    outpost: OutpostRef
    def list_recipes(self) -> _list[Recipe]:
        """Every recipe this smelter has been given a blueprint for. Returns Recipe objects with `.tier`, `.id`, `.name`, `.inputs`, `.output_item`, `.output_count`, `.duration_game_hours`, and `.power_draw`. Locked recipes (no blueprint yet) do not appear, the list reflects what the player can actually run today. Day-1 starts with `\"smelt_iron_ingot\"` only; more arrive as blueprints unlock."""
        ...
    def find_recipe(self, recipe_id: _str) -> Recipe | None:
        """Find one unlocked recipe by id without looping through `list_recipes()`. Returns its `Recipe` object, or `None` when the id is unknown, locked, or belongs to another machine."""
        ...
    def set_recipe(self, recipe_or_id: RecipeRef) -> ActionResult[Literal["ok", "unknown_recipe", "offline", "recipe_locked", "busy", "material_mismatch"]]:
        """Select which recipe the smelter should run. Call `self.set_recipe(\"smelt_iron_ingot\")` or pass a Recipe from `list_recipes()`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def clear_recipe(self) -> ActionResult[Literal["ok", "busy", "material_present"]]:
        """Unset the current recipe and leave the smelter idle. Empty latched buffers clear back to no material. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def get_recipe(self) -> Literal["", "smelt_iron_ingot", "smelt_glass", "smelt_titanium_ingot", "smelt_cobalt_ingot", "smelt_rare_earth_core", "smelt_neutronium_bar", "smelt_lead_ingot"]:
        """Current recipe id as a string, or the empty string if no recipe is set. Use after `set_recipe()` to confirm, or to gate other logic (`if self.get_recipe() == \"\": ...`)."""
        ...
    def get_recipe_inputs(self) -> _dict[_str, _int]:
        """Input requirements for the current recipe as a dict `{item_id: count_per_craft}`. Returns an empty dict if no recipe is set."""
        ...
    def is_running(self) -> _bool:
        """`True` while the smelter is actively processing a unit. Use before `set_recipe()` to avoid the `\"busy\"` rejection: `if not self.is_running(): self.set_recipe(new_id)`. Stays `True` across ticks until the unit completes."""
        ...
    def get_progress(self) -> _float:
        """Progress toward the next completed unit (**0-1**). Resets to **0** when a unit completes and a new one starts. Useful for progress bars and scripts that want to detect completions by watching the value drop."""
        ...
    def get_input_count(self) -> _int:
        """Units currently in the input buffer, waiting to be smelted. Check before `self.input.take(...)` to avoid overfilling, or to decide whether to pull more."""
        ...
    def get_output_count(self) -> _int:
        """Units currently in the output buffer, waiting to be drained. Check before `self.output.send(...)`, if high, unload downstream first; if low, let processing catch up."""
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

## `Storm`

```python
class Storm:
    """WeatherReport.active()"""
    id: _str
    x: _float
    y: _float
    def kind(self) -> Literal["dust", "thunder"]:
        """`\"dust\"` or `\"thunder\"`. Dust events transmit a Raw Uranium aftermath message. Thunder charges eligible Lightning Rods and may produce a Storm Glass message."""
        ...
    def radius_m(self) -> _float:
        """Cell radius in m. A heli drone on a straight route holds once its current position is inside the cell; it does not automatically route around it. Electric drones fly through."""
        ...
    def speed(self) -> _float:
        """Travel speed in m/h."""
        ...
    def heading(self) -> _list[_float]:
        """Unit travel direction as `[dx, dy]`."""
        ...
    def intensity(self) -> _float:
        """Observed strength **0-1** at report time."""
        ...
    def expires_in(self) -> _float:
        """Live hours remaining before this observed cell dissipates."""
        ...
    def eta_to(self, x: _float, y: _float) -> _float | None:
        """Hours until the cell's edge reaches the point. **0** when the point is already inside the cell; `None` when the track never gets there before dissipating."""
        ...
```

## `Thermometer`

```python
class Thermometer(Component):
    """Thermometer: Always-working surface temperature probe, no calibration needed. Reads the planet's current surface temperature in **°C** directly."""
    name: _str
    def get_value(self) -> _float:
        """Current surface temperature in **°C** as a number. Safe to call from any script; no repair step needed. This is the display °C, for the heat-units progression metric that research thresholds compare against, read `get_component(\"atmosphere\").get_heat()`."""
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

## `WeatherEventForecast`

```python
class WeatherEventForecast:
    """WeatherReport.forecast()"""
    id: _str
    def kind(self) -> Literal["dust", "thunder"]:
        """Broad event family: `\"dust\"` or `\"thunder\"`."""
        ...
    def arrival_window(self) -> _list[_float]:
        """`[earliest, latest]` hours after this report's observation time when the cell should enter coverage."""
        ...
    def corridor(self) -> Zone:
        """Coarse predicted travel corridor as a `Zone`; it is storm information, never the hidden aftermath path."""
        ...
    def intensity_range(self) -> _list[_float]:
        """Observed forecast range `[low, high]`, each **0-1**."""
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
        """Live age of this immutable report in world-clock hours."""
        ...
    def coverage(self) -> Zone:
        """The station's local coverage as a `Zone` frozen at observation time."""
        ...
    def active(self) -> _list[Storm]:
        """List of active `Storm` snapshots inside local coverage at observation time."""
        ...
    def forecast(self) -> _list[WeatherEventForecast]:
        """Local `WeatherEventForecast` entries expected to enter coverage within **8 world-clock hours**, or **24** after Weather Forecasting research."""
        ...
```

## `WeatherSignalBoard`

```python
class WeatherSignalBoard:
    """weather_station.signal_board"""
    def reveal(self, transmission: SignalTransmission | TransmissionRecord) -> ActionResult[Literal["ok", "no_power", "duplicate", "invalid_type"]]:
        """Publish one transmission into its declared numbered slot. A different event replaces this station's current board. An already-published slot for the same event is left unchanged. The board checks shape and bounds, not meaning or checksum validity. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def reject(self, transmission: SignalTransmission | TransmissionRecord) -> ActionResult[Literal["ok", "no_power", "invalid_type"]]:
        """Add one to the supplied event's refusal count without opening a slot. A different event replaces this station's current board. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def resolve(self, event_id: _str, info: _dict[_str, object]) -> ActionResult[Literal["ok", "no_power", "invalid_type"]]:
        """Publish up to **6** labelled rows for an event. A different event replaces this station's current board. The board displays supplied values without validating them. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def clear(self) -> ActionResult[Literal["ok", "no_power"]]:
        """Clear the board, its rejection count, and any published conclusion. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def status(self) -> WeatherSignalBoardStatus:
        """This station's current board publication metadata."""
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
    """Weather Station: A programmable local storm station and live receiver. It measures immutable local reports, hears event transmissions on broadcast and biome channels, and may publish to the Signal Board."""
    name: _str
    outpost: OutpostRef
    def observe(self) -> WeatherReport:
        """Measure one immutable local report. The station refreshes at most once per world-clock hour; faster calls return the same report id. The report includes local coverage, active storm snapshots, and a local forecast reaching 8 world-clock hours ahead, or 24 once Weather Forecasting is researched. It never contains an aftermath coordinate."""
        ...
    def last_report(self) -> WeatherReport | None:
        """Read the last measured report without taking a new observation. This is useful for startup recovery and stale-data handling; `None` means this station has never completed `observe()`."""
        ...
    signal_board: WeatherSignalBoard
    signal_receiver: SignalReceiver
    def strikes(self) -> _list[WeatherStrike]:
        """Return this station's bounded strike history. Each `WeatherStrike` includes its event id, observation time, energy, and whether a Lightning Rod banked it. Exact strike positions and Storm Glass eligibility are not included. Only strikes this station physically observed are returned."""
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
    """Wildlife Sensor: Reports total individual fauna across all established Habitat colonies. Available after Biosphere research lands; reads `0` until the first Wildlife colony establishes."""
    name: _str
    def get_value(self) -> _int:
        """Returns the current Wildlife population count as a number, summed from established Habitat colonies."""
        ...
```
