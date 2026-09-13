# Guide: wildlife_husbandry

## Wildlife, Husbandry

Husbandry means keeping every active life-support input ready. The worst active input sets `breeding_efficiency()`, a life-support multiplier rather than the population growth rate. Established populations never decay.

### Revival setup check

Call `set_revival_target(creature_id)` first and branch on its `ActionResult`. It checks the creature, catalog, and one-colony-per-species rule, then saves the target without spending materials. Stage at least **2** correct feed units and every rarity-scaled Biology reagent in the dedicated `reagents` input. Then call parameterless `revive()` and branch on `.status` (`"ok"`, `"occupied"`, `"no_target"`, `"species_exists"`, `"not_cataloged"`, `"wrong_feed"`, `"insufficient_feed"`, or `"insufficient_reagents"`). Any rejected result spends nothing and keeps the target selected. Once revival starts, every active input must stay healthy for **12 world hours** of rearing.

### Relocate an established colony

The colony belongs to its species, not its enclosure. Undeploying an established colony's Habitat leaves that colony awaiting housing while its population, life stage, brood progress, Insight history, and bonuses remain intact. Its Wildlife and species-breadth contributions pause until it is rehoused. From an empty Habitat, call `result = self.rehouse(creature_id)` and branch on the returned `ActionResult`. The same call can transfer a colony directly from another deployed Habitat. The destination's current capacity must fit the whole colony; `"insufficient_capacity"` moves nothing.

### Feed is automatic

`feed_ok()` is true when the input bin holds the creature's exact feed. Revival spends one feed and leaves one for rearing. Established colonies consume feed only when individuals are actually born; a full colony idles without consuming it. `feed_level()` reports usable feed after partial consumption, so scripts can restock from local storage without guessing.

### Gas and liquid are two-sided bands

`gas_band()` and `liquid_band()` return `[low, high]` in tons when active, or `[]` before that input opens. Too little and too much both reduce efficiency. The fluid identity must also match: compare `gas_fluid()` with `required_gas()` and the liquid equivalents. Cutting intake lets an overfilled enclosure bleed back down. For a large excess, explicitly empty that reserve with `purge_reserve("gas")` or `purge_reserve("liquid")`, then refill it correctly. The discarded fluid is lost, while the colony and its other supplies stay intact.

### Complete regulator pattern

```
def regulate_fluid(band, level, set_intake):
  if len(band) == 0:
    set_intake(0)
  elif level < band[0]:
    set_intake(5)
  elif level > band[1]:
    set_intake(0)
  else:
    set_intake(1)

while True:
  regulate_fluid(self.gas_band(), self.gas_level(), self.set_gas_intake)
  regulate_fluid(self.liquid_band(), self.liquid_level(), self.set_liquid_intake)

  if not self.feed_ok():
    print("Feed missing or wrong; need " + self.required_feed())
  if self.gas_band() and self.gas_fluid() != self.required_gas():
    print("Wrong gas, need " + self.required_gas())
  if self.liquid_band() and self.liquid_fluid() != self.required_liquid():
    print("Wrong liquid, need " + self.required_liquid())

  print("efficiency", self.breeding_efficiency())
  sleep(1)
```

Connect and stock the Habitat's feed and dedicated `reagents` inputs from local storage. Connect the gas and liquid ports to tanks containing the exact required exotic. Fluid intake setters change policy immediately, but the buffer and efficiency change only after simulation advances and material arrives.

### Read the transition before it happens

`next_stage_population()` gives the exact threshold and `next_requirement()` names the kind of change. For the actual supply plan, `next_required_gas()` and `next_required_liquid()` name the fluids that will be required immediately after the transition. `next_gas_band()` and `next_liquid_band()` return their exact future `[low, high]` windows. Empty strings or lists mean that input will not be active. This makes prospecting, refining, piping, and regulator tuning possible before the crossing.

### Recovery

A failed rearing attempt costs the staged materials but never the Habitat. Fix the supply or the script, then retry `revive()`.

For excess gas already inside the enclosure, stop intake and explicitly discard that reserve:

```
self.set_gas_intake(0)
result = self.purge_reserve("gas")
print(result.status, result.message)
```

Then refill with the required gas and resume regulation. For liquid, use `set_liquid_intake(0)` and `purge_reserve("liquid")`. Each purge destroys only the chosen enclosure reserve and clears its fluid identity. It preserves the other reserve, feed, colony progress, inlet buffers, connections, and intake settings. `purge_intake("gas_in")` or `purge_intake("liquid_in")` remains the separate tool for clearing an inlet that holds the wrong fluid.

*Guide / World & Infrastructure*

---
