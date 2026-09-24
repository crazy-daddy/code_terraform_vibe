# Component: habitat

> **Category:** Terraforming | **Component Name:** Habitat

Revives one species from Biology reagents staged in this Habitat's dedicated local input, then breeds it into a colony. One living colony is allowed per species. Established colonies keep their progress when moved between Habitats.

| Field | Value |
| --- | --- |
| Type | Biosphere |
| Power in | Variable (draws from grid) |
| Input buffer | 50 units |
| Stockpile | 25 units (mixed) |
| Tiers | Mk II |

### How to obtain

1. Requires the **Wildlife** research (Plants 2,250,000).
2. Buy from the Shop for 100,000 cr.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.outpost: OutpostRef`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef` for the outpost where this building is deployed.

##### `.gas_in: FluidPort`

Supplies the Habitat with gas. Connect a Gas Tank with `self.gas_in.connect("gas_tank_1")`, then use `set_gas_intake(...)` to meter gas from this port into the enclosure. See `FluidPort` for level, capacity, flow, and connection queries.

- **Returns** `FluidPort`: `connect()`, `connected_to()`, `level()`, `capacity()`, `flow_rate()`. Wire to a Gas Tank: `self.gas_in.connect("gas_tank_1")`. The tank fills this port; `set_gas_intake(...)` meters it into the enclosure.

##### `.liquid_in: FluidPort`

Supplies the Habitat with liquid. Connect a Liquid Tank with `self.liquid_in.connect("liquid_tank_1")`. See `FluidPort` for level, capacity, flow, and connection queries.

- **Returns** `FluidPort`: `connect()`, `connected_to()`, `level()`, `capacity()`, `flow_rate()`. Wire to a Liquid Tank: `self.liquid_in.connect("liquid_tank_1")`.

##### `.input: InputSlot`

Stores feed for the colony. Connect a source with `self.input.connect("Feed Bin")`, then pull feed with `self.input.take("feed_salt_tortoise", 20)`. Compare `self.input.stacks()` with `required_feed()` after revival; only the colony's own feed item is useful. See `InputSlot`.

- **Returns** `InputSlot`: `connect()`, `take()`, `eject()`, `count()`, `capacity()`, `stacks()`, `connected_to()`. Stock the colony's feed: `self.input.connect("Feed Bin")` then `self.input.take("feed_salt_tortoise", 20)`. Compare `stacks()` with `required_feed()` after revival; recover the wrong feed to local freight with `eject(...)`.

##### `.reagents: InputSlot`

Dedicated local `InputSlot` for revival reagents. Select a revival target, then connect a Storage Bin or Warehouse at this Habitat's outpost and stage all five Bio Lab reagents shown on the card before `revive()`. A Habitat at Nocturna Base may connect Base Inventory; a remote Habitat cannot.

- **Returns** Dedicated local `InputSlot` for the five Biology reagents consumed by `revive()`. Select a target, then connect a store at this Habitat's outpost and stage the rarity-scaled quantity shown on the card. Base Inventory is a valid source only for a Habitat at Nocturna Base. Recover unused reagents with `eject(...)`.

### Methods

##### `.set_revival_target(creature_id: str) → ActionResult` *(self only)*

Select which cataloged creature this Habitat is preparing with `self.set_revival_target("salt_tortoise")`. The validated target persists when the script stops and after a failed setup check or rearing attempt, so the Habitat card can show the creature and its live preparation requirements before a colony exists. Selecting another valid creature replaces the target without consuming materials.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `creature_id` | `str` | Cataloged creature id to prepare in this Habitat (e.g. `"salt_tortoise"`). |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"occupied"` | rejection | The requested cell, sector, or Habitat is already occupied. |
| `"species_exists"` | rejection | A living colony of this species already exists. |
| `"unknown_creature"` | rejection | The supplied creature identifier does not exist. |
| `"not_cataloged"` | rejection | The requested biological identity has not been cataloged. |

##### `.revive() → ActionResult` *(self only)*

Bring this Habitat's selected revival target to life with `self.revive()`. Stock at least **2** of its feed first: revival spends one and one must remain for rearing. Stage the exact rarity-scaled Bio Lab reagents shown by the Habitat or `journal.cataloged_creatures(...)`. Creature bonuses do not change this one-time recipe. Failed checks spend nothing and keep the selected target.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"occupied"` | rejection | The requested cell, sector, or Habitat is already occupied. |
| `"no_target"` | rejection | No target has been selected for this operation. |
| `"species_exists"` | rejection | A living colony of this species already exists. |
| `"not_cataloged"` | rejection | The requested biological identity has not been cataloged. |
| `"wrong_feed"` | rejection | The Habitat input contains feed for a different creature. |
| `"insufficient_feed"` | rejection | The Habitat does not contain enough of the required feed to start revival. |
| `"insufficient_reagents"` | rejection | The staged reagents do not satisfy the required recipe. |

##### `.rehouse(creature_id: str) → ActionResult` *(self only)*

Attach an established species colony to this Habitat with `self.rehouse("salt_tortoise")`. The destination must be empty and its current capacity must fit the entire colony. The same call moves a colony directly from another Habitat or restores one after its former Habitat was undeployed. Population, life stage, brood progress, Insight history, and purchased bonuses are preserved, and the population keeps counting toward Wildlife. Only growth pauses while a colony is unhoused.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `creature_id` | `str` | Established creature colony to attach to this Habitat (e.g. `"salt_tortoise"`). |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"occupied"` | rejection | The requested cell, sector, or Habitat is already occupied. |
| `"no_colony"` | rejection | No living colony exists for the requested species. |
| `"not_established"` | rejection | The requested colony has not completed rearing. |
| `"insufficient_capacity"` | rejection | The destination does not have enough capacity for the requested operation. |
| `"unknown_creature"` | rejection | The supplied creature identifier does not exist. |

##### `.set_gas_intake(rate: float) → ActionResult` *(self only)*

Set the gas inflow rate in **t/h**, pulled from the connected Gas Tank (wire it with `self.gas_in.connect("gas_tank_1")`) into the enclosure's gas reserve. This is the regulator actuator: read `gas_level()`, compare it with `gas_band()`, and raise intake below the band or lower it above the band. Idle at **0**. Clamps to `>= 0`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `rate` | `float` | Gas inflow rate in t/h, pulled from the connected Gas Tank into the enclosure's gas reserve. Meter this to hold `gas_band()`. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.purge_intake(port: str | None = None) → ActionResult` *(self only)*

Vents a feedstock inlet so it can accept a different fluid. Pass `"gas_in"` or `"liquid_in"` to vent one, or omit to vent both, venting only what is actually blocked leaves a healthy buffer alone. The inlets take the first fluid that reaches them and then refuse any other, so an enclosure supplied the wrong gas ends up holding one it cannot use with no way to take the right one. Purge, rewire, and the next correct delivery replaces the enclosure air: `self.purge_intake()` then `self.gas_in.connect("Sulfur Refiner")`. The vented fluid is destroyed; feed and colony progress are untouched.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `port` | `str \| None` | Inlet to vent: `"gas_in"` or `"liquid_in"`. Omit to vent both. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"empty"` | rejection | The relevant source or queue is empty. |

##### `.purge_reserve(medium: str) → ActionResult` *(self only)*

Empties the selected enclosure reserve immediately: `self.purge_reserve("gas")` or `self.purge_reserve("liquid")`. The fluid is destroyed. The other reserve, inlet buffers, connections, intake settings, feed, and colony progress stay intact. The reserve can refill on later ticks if intake remains open.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `medium` | `str` | Enclosure reserve to empty: `"gas"` or `"liquid"`. The selected fluid is destroyed. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The selected enclosure reserve was emptied and its fluid discarded. |
| `"empty"` | success | The selected enclosure reserve was already empty. |

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | medium must be "gas" or "liquid". |

##### `.set_liquid_intake(rate: float) → ActionResult` *(self only)*

Set the liquid inflow rate in **t/h**, pulled from the connected Liquid Tank (`self.liquid_in.connect("liquid_tank_1")`) into the enclosure's liquid reserve. Meter it to hold `liquid_band()`. Idle at **0**. Clamps to `>= 0`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `rate` | `float` | Liquid inflow rate in t/h, pulled from the connected Liquid Tank into the enclosure's liquid reserve. Meter this to hold `liquid_band()`. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.unlock_bonus(node_id: str) → ActionResult` *(self only)*

Permanently purchase one node from this creature's tree. Pass a node id from `get_bonus_tree().nodes`. The **1 Insight** Adaptation affects this species only. The **4 Insight** Breakthrough affects every species and also requires this source colony to reach **10,000** population. A rejected purchase spends nothing.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `node_id` | `str` | Node id from `get_bonus_tree().nodes`. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"unknown_node"` | rejection | The supplied Habitat bonus node identifier does not exist for this creature. |
| `"already_purchased"` | rejection | The Habitat bonus node is already permanently purchased. |
| `"population_locked"` | rejection | The local colony has not reached the required population. |
| `"insufficient_insight"` | rejection | The shared Wildlife Insight balance is below the node cost. |

##### `.tier() → int`

Permanently installed Habitat tier as an integer (**1-2**). Mk II doubles carrying capacity only; breeding speed and biological costs come from adaptations.

- **Returns** Integer: permanently installed Habitat tier (**1-2**).

##### `.population() → int`

Current colony head count (individuals). Reads **0** for an empty Habitat OR one still in the Founded rearing window, a colony only counts (here and on the Wildlife sensor) once it's established. Breeds up toward `carrying_capacity()` and never falls.

- **Returns** Number: current colony head count (individuals). **0** for an empty Habitat or one still in the Founded rearing window (not yet established / counted on the sensor).

##### `.species() → str`

The housed creature id (e.g. `"glacial_wyrm"`), or `""` when the Habitat is empty. Use to look the creature up or branch your regulator per species.

- **Returns** String: the housed creature id, or `""` when the Habitat is empty.
- **Possible values** `""`, `"salt_tortoise"`, `"magmatic_annelid"`, `"mycelial_husk"`, `"mantle_strider"`, `"glasswing_mantis"`, `"veil_mantle"`, `"vault_crab"`, `"tidal_cephalopod"`, `"bone_walker"`, `"vent_drifter"`, `"hive_sentinel"`, `"hollow_choir"`, `"ferric_sea_lily"`, `"crustal_echo"`, `"glacial_wyrm"`, `"spire_drake"`

##### `.revival_target() → str`

The creature id explicitly selected with `set_revival_target(...)`, or `""` before selection and after establishment. Failed setup checks and rearing attempts retain this value, while `species()` remains empty until revival actually starts.

- **Returns** String: the creature id explicitly selected for preparation, or `""` when no target is selected or the colony is established. A failed setup check or rearing attempt keeps the target selected.
- **Possible values** `""`, `"salt_tortoise"`, `"magmatic_annelid"`, `"mycelial_husk"`, `"mantle_strider"`, `"glasswing_mantis"`, `"veil_mantle"`, `"vault_crab"`, `"tidal_cephalopod"`, `"bone_walker"`, `"vent_drifter"`, `"hive_sentinel"`, `"hollow_choir"`, `"ferric_sea_lily"`, `"crustal_echo"`, `"glacial_wyrm"`, `"spire_drake"`

##### `.life_stage() → str`

The colony's stage as a string: `"empty"`, `"founded"`, `"first_breeding"`, `"self_sustaining"`, `"thriving"`, or `"abundant"`. The colony climbs as its own population crosses each stage threshold; each climb opens a harder requirement and raises the ceiling. Branch on it to scale up your supply: `if self.life_stage() == "thriving": self.set_liquid_intake(...)`.

- **Returns** String: one of `"empty"`, `"founded"`, `"first_breeding"`, `"self_sustaining"`, `"thriving"`, `"abundant"`. The colony climbs as its own population crosses each stage threshold.
- **Possible values** `"empty"`, `"founded"`, `"first_breeding"`, `"self_sustaining"`, `"thriving"`, `"abundant"`

##### `.is_established() → bool`

`True` once the colony cleared the Founded rearing window and is counting on the sensor; `False` during rearing or when empty. Gate breeding logic on it: `if self.is_established(): regulate()`.

- **Returns** Boolean: `True` once the colony cleared the Founded rearing window and counts on the sensor; `False` during rearing or when empty.

##### `.rearing_progress() → float`

Fraction **0-1** of the Founded rearing window held in-band. Climbs only while every active band is satisfied; reaches **1.0** to establish. Reads **0** when empty/established, and resets to 0 if a band is lost (rearing fails). Watch it during a fresh revive to confirm your regulator is holding.

- **Returns** Number in **0-1**: fraction of the Founded rearing window held in-band. Reaches **1.0** to establish. **0** when empty/established. Resets to 0 on a band loss (rearing fails: see `rearing_failed()`).

##### `.rearing_failed() → bool`

`True` after a rearing attempt lost its bands and reverted the Habitat to preparation. The genome and selected target are kept, fix your regulator and call `revive()` again. Clears when a target is selected or revival restarts.

- **Returns** Boolean: `True` after a rearing attempt lost its bands and reverted the Habitat to preparation. The genome and selected target are kept; fix your regulator and call `revive()` again. Clears when a target is selected or revival restarts.

##### `.brood_size() → int`

Whole individuals produced by the next completed breeding cycle. Normally **1**; brood bonuses build toward a guaranteed extra individual and periodically make it **2**. Reads **0** without an established colony or carrying-capacity space.

- **Returns** Whole individuals produced by the next completed breeding cycle. Normally **1**; brood bonuses build toward a guaranteed extra individual and periodically make it **2**. Reads **0** without an established colony or carrying-capacity space.

##### `.breeding_rate() → float`

Expected individuals/h at the current population, remaining capacity (headroom), life support, rarity, adaptation effects, and available local inputs. Population adds less and less extra speed above 10 individuals, while brood yield and purchased speed effects stay within their overall limits. This is the rate readout; `breeding_efficiency()` is only the life-support factor.

- **Returns** Expected individuals/h at current conditions. **0** before establishment or while blocked.

##### `.feed_level() → float`

Usable feed units remaining after partial consumption. Feed is consumed automatically only when individuals are born. Top it up with `self.input.take(...)`; over-stocking is harmless.

- **Returns** Number: usable feed units remaining after partial consumption. Feed is drawn automatically only when individuals are born. Keep it above the next birth's cost; over-stocking is harmless.

##### `.gas_level() → float`

Current gas held in the enclosure, in **tons**. Compare it with `gas_band()` and meter `set_gas_intake(...)` to hold it inside the window. It drops as the colony consumes gas while breeding and rises with intake.

- **Returns** Number: current gas held in the enclosure, in tons. Compare to `gas_band()`; meter `set_gas_intake(...)` to hold it inside the window.

##### `.liquid_level() → float`

Current liquid held in the enclosure, in **tons**. Compare it with `liquid_band()` and meter `set_liquid_intake(...)` to hold the window.

- **Returns** Number: current liquid held in the enclosure, in tons. Compare to `liquid_band()`; meter `set_liquid_intake(...)` to hold it inside the window.

##### `.get_insight() → HabitatInsight`

Read the shared Wildlife Insight balance and this colony's current and lifetime contribution. Insight accrues directly from positive population change. Static population and elapsed time alone produce nothing.

- **Returns** `HabitatInsight`: the shared balance, this colony's current production rate, and its lifetime contribution.

##### `.get_bonus_tree() → HabitatBonusTree`

Read this creature's species-only Adaptation and all-species Breakthrough, including each node's `.scope`, `.source_species`, permanent purchase state, current effect activity, Insight cost, and unmet requirements. The tree appears after selecting a revival target and its nodes remain visible while locked.

- **Returns** `HabitatBonusTree`: one species-only Adaptation and one all-species Breakthrough, with scope, source species, costs, gate, activity, and purchase state.

##### `.get_active_bonuses() → list[HabitatBonusNode]`

Read every purchased node currently affecting this Habitat, including global Breakthroughs earned from other species. Each result exposes `.scope` and `.source_species`. A conditional node disappears while its local condition is unmet; use its source Habitat's `get_bonus_tree()` to inspect permanent ownership.

- **Returns** List of purchased `HabitatBonusNode` objects currently affecting this Habitat, including global Breakthroughs earned from other species.

##### `.gas_band() → list[float]`

Safe gas-inventory range `[low, high]` in **tons** for the colony's current stage. Breeding receives full gas support inside the range; too little starves the colony and too much is toxic. Returns an empty list before gas is required. Read it each loop because the range tightens as the colony grows.

- **Returns** List `[low, high]` (tons): the safe gas-inventory window for the colony's CURRENT life-stage. `gas_level()` inside `[low, high]` = breeding at 100% for gas; outside (too low OR too high) throttles. Empty list `[]` when gas isn't an active requirement yet (early stages).

##### `.liquid_band() → list[float]`

Safe liquid-inventory range `[low, high]` in **tons** for the colony's current stage. Returns an empty list before liquid is required. Read it each loop because the range tightens as the colony grows.

- **Returns** List `[low, high]` (tons): the safe liquid-inventory window for the colony's CURRENT life-stage. Empty list `[]` when liquid isn't an active requirement yet.

##### `.feed_ok() → bool`

`True` when the feed named by `required_feed()` is stocked. Feed is consumed automatically as individuals are born. `False` means the bin is empty or contains the wrong feed. Missing feed stalls breeding but does not reduce the established population.

- **Returns** Boolean: `True` when the feed named by `required_feed()` is stocked. Feed is consumed automatically as individuals are born. `False` (✗ on the card) means the bin is empty or holds the wrong feed.

##### `.gas_ok() → bool`

`True` when gas requirements are met or gas is not required yet. `False` means the level is outside `gas_band()` or the enclosure holds the wrong gas. If the level is inside the range, compare `gas_fluid()` with `required_gas()`.

- **Returns** Boolean: `True` when gas is in-band (or not yet required). `False` means EITHER `gas_level()` is outside `gas_band()` (adjust `set_gas_intake(...)`) OR the enclosure holds the wrong gas (`gas_fluid()` ≠ `required_gas()`: re-pipe the right exotic). Check both.

##### `.liquid_ok() → bool`

`True` when liquid requirements are met or liquid is not required yet. `False` means the level is outside `liquid_band()` or the enclosure holds the wrong liquid. Compare `liquid_fluid()` with `required_liquid()` to tell which.

- **Returns** Boolean: `True` when liquid is in-band (or not yet required). `False` means EITHER `liquid_level()` is outside `liquid_band()` OR the wrong liquid is held (`liquid_fluid()` ≠ `required_liquid()`). Check both.

##### `.breeding_efficiency() → float`

Current life-support multiplier from **0-100%**, not the population growth rate. The weakest active input sets it; **100%** means every input is ready. Growth also scales with population momentum, rarity, and bonuses. Capacity stops growth only when full and never slows breeding beforehand. Poor conditions never reduce population.

- **Returns** Life-support multiplier from **0-100%**, not the population growth rate. The weakest active input sets it; **100%** means every input is ready. Growth also scales with population momentum, rarity, and bonuses. Capacity stops growth only when full and never slows breeding beforehand. Poor conditions never reduce population.

##### `.gas_fluid() → str`

The exotic gas currently held in the enclosure, such as `"chlorine"`, or `""` when empty. It must equal `required_gas()` for the gas range to count. If `gas_level()` is in range but `gas_ok()` is `False`, the enclosure holds the wrong gas.

- **Returns** String: the exotic gas currently HELD in the enclosure (the fluid you piped in), or `""` when empty. The band only counts when this equals `required_gas()`; if `gas_level()` reads in-band but `gas_ok()` is `False`, you're holding the WRONG gas: compare these two to spot it.
- **Possible values** `""`, `"steam"`, `"ammonia"`, `"swamp_gas"`, `"raw_sulfur_gas"`, `"sulfur_gas"`, `"raw_chlorine"`, `"chlorine"`

##### `.liquid_fluid() → str`

The exotic liquid currently held in the enclosure, or `""` when empty. It must equal `required_liquid()` for the liquid range to count.

- **Returns** String: the exotic liquid currently HELD in the enclosure, or `""` when empty. Must equal `required_liquid()` for the band to count; compare them to diagnose a wrong-liquid supply.
- **Possible values** `""`, `"water"`, `"oil"`, `"frozen_essence"`, `"coastal_essence"`, `"geothermal_essence"`, `"volcanic_essence"`, `"deep_essence"`, `"brine"`, `"raw_cryofluid"`, `"cryofluid"`, `"raw_quicksilver"`, `"quicksilver"`

##### `.required_feed() → str`

The exact feed item id required by the selected revival target or housed creature, or `""` when neither exists. Compare it with `self.input.stacks()` while staging or diagnosing feed.

- **Returns** String: the exact feed item id required by the selected revival target or housed creature, or `""` when neither exists. Compare it with `self.input.stacks()` while staging or diagnosing feed.
- **Possible values** `""`, `"feed_salt_tortoise"`, `"feed_magmatic_annelid"`, `"feed_mycelial_husk"`, `"feed_mantle_strider"`, `"feed_glasswing_mantis"`, `"feed_veil_mantle"`, `"feed_vault_crab"`, `"feed_tidal_cephalopod"`, `"feed_bone_walker"`, `"feed_vent_drifter"`, `"feed_hive_sentinel"`, `"feed_hollow_choir"`, `"feed_ferric_sea_lily"`, `"feed_crustal_echo"`, `"feed_glacial_wyrm"`, `"feed_spire_drake"`

##### `.required_gas() → str`

The exotic gas required at the colony's current stage, such as `"swamp_gas"`, or `""` before gas is needed. The requirement becomes more demanding at later stages, so check it again as the colony grows. Other gases do not satisfy the required range.

- **Returns** String: the exotic gas this creature needs at its CURRENT stage (some species switch to a deeper exotic at later stages, e.g. `"sulfur_gas"` → `"chlorine"`; a purchased Adaptation may retain the base gas instead), or `""` when gas isn't required yet. Pipe exactly this fluid; `gas_fluid()` must match it.
- **Possible values** `""`, `"swamp_gas"`, `"ammonia"`, `"sulfur_gas"`, `"chlorine"`

##### `.required_liquid() → str`

The exotic liquid this creature needs at its current stage, e.g. `"brine"`; escalates at later stages (`"brine"` → `"cryofluid"` → `"quicksilver"`). `liquid_fluid()` must match it. `""` when liquid isn't required yet.

- **Returns** String: the exotic liquid this creature needs at its current stage (some species switch to a deeper exotic at later stages, e.g. `"cryofluid"` → `"quicksilver"`; a purchased Adaptation may retain the base liquid instead), or `""` when liquid isn't required yet. `liquid_fluid()` must match it.
- **Possible values** `""`, `"brine"`, `"cryofluid"`, `"quicksilver"`

##### `.next_required_gas() → str`

The gas required after the next life-stage transition, or `""` if the next stage needs no gas or there is no next stage. Read it with `next_gas_band()` before the population reaches the threshold.

- **Returns** String, the exact gas required immediately AFTER the next life-stage transition, or `""` when that next stage has no gas requirement or no next stage exists. Pair with `next_gas_band()` to prepare before crossing.
- **Possible values** `""`, `"swamp_gas"`, `"ammonia"`, `"sulfur_gas"`, `"chlorine"`

##### `.next_required_liquid() → str`

The liquid required after the next life-stage transition, or `""` if the next stage needs no liquid or there is no next stage. Read it with `next_liquid_band()` before the population reaches the threshold.

- **Returns** String, the exact liquid required immediately AFTER the next life-stage transition, or `""` when that next stage has no liquid requirement or no next stage exists. Pair with `next_liquid_band()`.
- **Possible values** `""`, `"brine"`, `"cryofluid"`, `"quicksilver"`

##### `.next_gas_band() → list[float]`

The next life stage's exact gas window as `[low, high]` in **tons**. Returns `[]` if that stage needs no gas or the colony is already Abundant. Pair with `next_required_gas()` to prepare the correct supply and regulator in advance.

- **Returns** List `[low, high]` (tons), the exact gas band immediately AFTER the next life-stage transition. Empty list `[]` when that stage has no gas requirement or no next stage exists.

##### `.next_liquid_band() → list[float]`

The next life stage's exact liquid window as `[low, high]` in **tons**. Returns `[]` if that stage needs no liquid or the colony is already Abundant. Pair with `next_required_liquid()`.

- **Returns** List `[low, high]` (tons), the exact liquid band immediately AFTER the next life-stage transition. Empty list `[]` when that stage has no liquid requirement or no next stage exists.

##### `.carrying_capacity() → int`

The colony's ceiling at its current life stage. Population breeds toward it and plateaus there; a maxed colony consumes nothing. Life-stage advancement raises the base ceiling, and Habitat Mk II doubles it. Adaptations never change capacity. Reads **0** when empty.

- **Returns** Number: the colony's ceiling at its current life stage. Stage advancement raises the base; Habitat Mk II doubles it. Adaptations never change capacity. **0** when empty.

##### `.headroom() → int`

Individuals still breedable before the current ceiling (`carrying_capacity() - population()`, floored at **0**). **0** means this colony is capped and idling. Before Abundant, reach the next stage; at Abundant Mk I, apply the sole Habitat Mk II pack or grow another species.

- **Returns** Number: individuals still breedable before the colony hits its current ceiling (`carrying_capacity() - population()`, floored at **0**). **0** means this colony is capped and idling.

##### `.next_stage_population() → int`

Exact population that opens the next life stage: **250**, **2,500**, **25,000**, or **175,001**. Returns **0** when the Habitat is empty or already Abundant. Mk I stops at **175,000**, so entering Abundant requires Mk II. Compare the result with `population()` so your script can prepare the next supply before the transition.

- **Returns** Whole-number population threshold that opens the next life-stage (**250**, **2,500**, **25,000**, or **175,001**). **0** when empty or already Abundant. Compare with `population()` to plan the next supply change.

##### `.next_requirement() → str`

What changes at the colony's next stage: `"capacity"`, `"gas"`, `"liquid"`, `"switch_gas"`, `"switch_liquid"`, `"tighter_bands"`, or `"none"` at Abundant. Pair it with `next_stage_population()` to learn when the transition happens and what to prepare.

- **Returns** What changes at the next stage: more `"capacity"`, a new `"gas"` or `"liquid"`, `"switch_gas"`, `"switch_liquid"`, `"tighter_bands"`, or `"none"` at Abundant. Pair with `next_stage_population()` to prepare before the transition.
- **Possible values** `"capacity"`, `"gas"`, `"liquid"`, `"switch_gas"`, `"switch_liquid"`, `"tighter_bands"`, `"none"`

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Terraforming*
