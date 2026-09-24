# Guide: wildlife_supply_fluids

## Wildlife, Supply (Gases & Liquids)

The harder a colony climbs, the rarer the gas and liquid it demands. Exotic fluids come from a **prospect → capture → refine → meter** chain. Common fluids skip the Refiner; uncommon and rare fluids use raw feedstock plus tar.

### Fluids by rarity

Four gases and three liquids appear in Habitat requirements:

- **Common (tap and use directly):** `swamp_gas`, `ammonia` (gases); `brine` (liquid).
- **Uncommon (raw → Refiner + tar):** `sulfur_gas` (gas); `cryofluid` (liquid).
- **Rare (raw → Refiner + heavy tar):** `chlorine` (gas); `quicksilver` (liquid).

Uncommon and rare exotics have a **raw** deposit form (`raw_sulfur_gas`, `raw_cryofluid`, `raw_chlorine`, `raw_quicksilver`) and a **refined** Habitat-ready form. Most colonies never need the rare pair `chlorine` + `quicksilver`, so demand for those deposits stays low.

### 1. Prospect

Exotic deposits follow the same model as thermal vents:

- discover and **survey by sonar** (basic = active?, wide = rate, deep = cycle timing),
- collect with a **cap** (gas vents) or **tap** (liquid springs),
- pipe the output into gas or liquid storage.

Deposits alternate active and dormant phases. Stockpile during the active phase, then feed Habitats from tanks during dormancy. Deep-sonar timing lets you predict dormant phases and size the buffer first. Deposits do not deplete; multiple deposits help cover each other's dormant gaps.

### 2. Refine (uncommon / rare only)

Raw feedstock is not ready for Habitats. The **Refiner** converts `raw feedstock + tar → refined exotic` via a recipe (unlocked through Biolab orders). Pick the exotic with `self.set_recipe(...)`; wire raw feedstock into `gas_in` / `liquid_in`, tar into `self.input`, and the refined product out of `gas_out` / `liquid_out`.

### Tar, the refining reagent

Refining eats **tar** alongside the raw feedstock. Tar is an oil-refining byproduct that otherwise mostly goes to the Waste Processor. Tar cost scales with rarity:

- **Common**, no tar (tapped direct, no Refiner).
- **Uncommon**, moderate tar.
- **Rare (Chlorine / Quicksilver)**, heavy tar.

Tar is a running cost on the liquid pipe network carrying oil, not a hard gate. If you run short, expand oil production or slow the Habitat intake until the Refiner catches up.

### 3. Meter

The refined gas/liquid flows into a Gas/Liquid Tank. Your Habitat script meters it in with `self.set_gas_intake(...)` / `self.set_liquid_intake(...)` to hold the band. See the **Husbandry** page.

### When each step matters

A freshly-founded colony needs only **feed**. Mid-stage colonies add a **basic gas/liquid**. Thriving colonies can demand **rare refined exotics**, which pushes you into farther prospecting and heavier refining. Research **Exotic Husbandry** unlocks survey/cap/tap + Refiner for uncommon exotics. **Deep Exotics** unlocks at **500,000 Wildlife** and opens the rarest extraction and refining. An early legendary colony may pause at its rare-fluid transition until the broader menagerie reaches that total; this is recoverable and costs no population. Read the Habitat's exact next-stage methods and grow other species while preparing the rare supply.

*Guide / World & Infrastructure*
