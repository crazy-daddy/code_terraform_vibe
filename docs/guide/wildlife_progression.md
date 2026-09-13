# Guide: wildlife_progression

## Wildlife, Progression

Wildlife has three linked progress scales: each colony's life stage, shared Insight, and planet-wide established population.

### Colony stages

| Current stage | Shared population range | Habitat access |
|---|---:|---|
| Founded | 4-249 | Mk I and Mk II |
| First Breeding | 250-2,499 | Mk I and Mk II |
| Self-Sustaining | 2,500-24,999 | Mk I and Mk II |
| Thriving | 25,000-175,000 | Mk I and Mk II |
| Abundant | 175,001-350,000 | Mk II only |

Both Habitat tiers display this same five-stage ladder. Mk I reaches its **175,000** capacity at the end of Thriving. Mk II unlocks at **600,000 Wildlife** after Deep Exotics and raises capacity to **350,000**, allowing the colony to cross into Abundant. The upgrade changes capacity only. Mature draw is **40-64 W** at Mk I and **144-168 W** at Mk II.

### Breeding

Each creature completes breeding cycles. Population supplies natural momentum: a Common colony produces about **28 individuals/h** naturally at 5,000 population, then the population contribution smoothly flattens toward **150 individuals/h**. Life-support efficiency and rarity change that natural rate: Common **1.0x**, Uncommon **0.75x**, Rare **0.50x**, Legendary **0.30x**. Purchased bonuses improve selected parts of this curve while hard caps keep even a complete tree to a few times untreated output. Some brood bonuses save fractional progress across cycles and eventually guarantee an extra individual. Full-support momentum takes **24 world hours** to reach maximum and loses progress twice as quickly while support is imperfect. Capacity never slows breeding; it only stops growth when the Habitat is full. `breeding_efficiency()` is only the life-support multiplier, not the population rate. Read `breeding_rate()` for expected individuals per hour.

### Adaptations and Insight

Every species has two independent permanent nodes. Its **1 Insight Adaptation** affects that species only. Its **4 Insight Breakthrough** affects every species and also requires its source colony to reach **10,000 population**. Neither node requires research, Compound, planet-wide Wildlife, or the other node. Insight accrues from population delta along diminishing milestones: **1.00** by 10, **1.50** by 100, **2.25** by 1,000, **3.00** by 10,000, **4.00** by 50,000, **5.50** by 175,000, and **7.00** by 350,000.

Only established colonies count toward the planet-wide phases. Failed rearing never touches the sensor, and established population never decreases.

*Guide / World & Infrastructure*

---

## Habitat Development

Every established colony learns from successful generations. Positive population change adds **Insight** directly to one shared Wildlife balance; elapsed time and static population add nothing. `self.get_insight()` reports the shared balance, this Habitat's current rate, and its lifetime contribution.

### Two permanent nodes per creature

Each creature has exactly two authored nodes. Its early **Adaptation** affects that species only and gives strong recurring relief tailored to its life support or breeding pace. Its later **Breakthrough** affects every current and future species. The complete set is deliberately bounded: it improves a well-supported late colony by a few times its untreated output, not by an order of magnitude. Bonuses include speed boosts for different parts of the growth curve, brood bonuses that guarantee extra offspring over time, a reward for one full day of uninterrupted support, feed efficiency, wider fluid bands, a larger founding population, and a higher late-stage rate limit. Rearing always takes 12 world hours. Scripts inspect `.scope` and `.source_species` through `self.get_bonus_tree()` and purchase with `self.unlock_bonus(node_id)`; there is no purchase control outside code.

### Costs and gates

The species-only Adaptation has exactly one requirement: **1 shared Insight**. It becomes purchasable after `set_revival_target(...)`, before revival. The all-species Breakthrough has exactly two requirements: **4 Insight** and its source creature reaching **10,000 population**. It does not require the first node, research, a planet-wide Wildlife total, or purchase materials. Every check is atomic; a rejected purchase spends nothing.

### Why more Habitats matter

The cumulative Insight curve has diminishing per-individual yield. A creature has generated **3 Insight** at 10,000 population, while its two nodes cost **5** total, so no creature can self-fund its entire tree at the breakthrough gate. The player must pool growth from several species. Full Mk II populations across all 16 creatures generate **112 Insight** against **80** needed to own all 32 nodes, leaving 32 spare. That is a 1.4 times lifetime budget, while 15 full Mk II species still provide 105 Insight. A full or stalled colony cannot mint currency forever.

*Guide / World & Infrastructure*

---

## Wildlife, Creature Profiles

Every creature has a feed recipe and, as it climbs, a gas (and for rarer ones, a liquid) requirement. Only one living colony of each species can exist. A colony can be housed at any outpost and later moved without losing progress when the destination Habitat has enough capacity.

### Forage, the calorie base

Every feed builds on **Forage**: physical yield collected when a ready crop is harvested and its field cell is cleared. Keeping feed supplied therefore depends on continued seed production, planting, cultivation, harvesting, and replanting. Recipes use **cross-biome combinations**; across the 16 creatures they use all 30 life-forms, so every biome is worth harvesting. A creature's biome tag does not affect placement or requirements.

### How to read a creature's needs

- **Feed**, complete the creature's **Biolab order** to unlock its feed recipe, then build it at the **Feed Maker**, whose recipe lists the exact life-form ingredients.
- **Current gas / liquid**, `self.required_gas()` / `self.required_liquid()` name the exact exotic and `self.gas_band()` / `self.liquid_band()` give its target window.
- **Next gas / liquid**, `self.next_required_gas()` / `self.next_required_liquid()` and `self.next_gas_band()` / `self.next_liquid_band()` reveal the exact post-transition supply before the colony crosses its next threshold. Empty strings or lists mean that input will not be active.

### Rarity and requirements

How far a creature climbs is set by its **rarity** (read from the Biology Lab catalog):

- **Common**, mostly feed-based; one common gas; no liquid.
- **Uncommon**, one common gas; a liquid opens at Thriving.
- **Rare**, its gas escalates to a refined gas and its liquid tightens.
- **Legendary**, reaches the rarest exotics at the tightest bands.

The full stage-by-stage table lives on **Wildlife, Progression**. The two legendaries are the hardest to keep in-band, bring one to **Abundant** for the *Apex Husbandry* achievement, and revive, establish, and house all 16 for *Nocturna Reborn*.

*Guide / World & Infrastructure*

---
