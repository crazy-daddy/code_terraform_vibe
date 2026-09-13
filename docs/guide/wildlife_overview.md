# Guide: wildlife_overview

## Wildlife, Overview

**Wildlife** counts established species colonies currently attached to deployed Habitats. A powered-off Habitat still counts its housed population but pauses growth.

### End-to-end loop

1. Catalog all 5 fragments of a creature and unlock its feed recipe through its Bio Order.
2. Select it with `self.set_revival_target(creature_id)`. This exposes that creature's two-node tree before revival.
3. Stage the exact species feed and rarity-scaled Biology reagents shown by the Habitat or Journal. Creature bonuses never change this one-time reagent recipe.
4. Call `self.revive()`, keep every active need healthy through rearing, then regulate later gas and liquid ranges as the colony advances.
5. Each completed breeding cycle normally adds **1 individual**. Brood bonuses build toward guaranteed extra offspring across breeding cycles. Other nodes can accelerate a part of the population curve, reward uninterrupted support, reduce feed demand, widen fluid bands, retain a base fluid, or improve the founding population.
6. Positive population change automatically produces shared **Insight**. Static population and elapsed time produce none. Use `unlock_bonus(node_id)` for the real spending decision; there is no purchase control outside code.
7. At **600,000 Wildlife**, fabricate Habitat Mk II packs. Mk I stops at **175,000**, the top of Thriving. Mk II raises the ceiling to **350,000**, allowing the colony to enter and complete Abundant without changing any breeding statistic.

One Habitat houses one species, with no Wildlife-specific limit on how many Habitats an outpost may hold. Habitats follow the ordinary outpost overcrowding rules, so concentrating them is allowed while distributing them can improve throughput. The species owns its colony progress; the enclosure is replaceable. Undeploying an established colony's Habitat preserves population, life stage, brood progress, Insight history, and bonuses, while pausing growth and removing that colony from active Wildlife and species-breadth bonuses. Call `self.rehouse(creature_id)` from an empty Habitat whose current capacity fits the whole colony, or use the same call to transfer it directly from another Habitat. Fifteen full Mk II species reach **5,250,000** Wildlife while fourteen reach **4,900,000**. All 16 full Mk II species generate **112 Insight** against **80 Insight** needed for every node, leaving 32 spare. Feed, gas, and liquid are consumed only for individuals actually produced; a capped colony idles.

*Guide / World & Infrastructure*

---
