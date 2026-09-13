# Database: fluids

> **Category:** Fluids | **Section:** Fluids

Every substance that flows through pipes, one entry per fluid. Gas Pipes carry gases and Liquid Pipes carry liquids. Complete machine `connect()` relationships establish one exact substance per physical component; different exact substances on one component conflict. See **Flow Networks, Fluids** for the complete routing model.

### Industrial Fluids

The three working fluids of the power and production economy.

##### Steam `steam`

Superheated vapor from the planet's thermal vents. Captured by a `thermal_cap`, then spent by a `steam_turbine` for grid power or a `steam_condenser` for clean water.

| Field | Value |
| --- | --- |
| Type | Gas |
| Produced by | Thermal Cap |
| Consumed by | Fabricator, Steam Turbine, Steam Condenser, and Bio Caster and Titanium + Cobalt + Rare Earth → Turbine Rotor, Rare Earth + Rotor → Electric Thruster, Titanium + Glass → Cargo Pod (Small), Titanium + Glass + Panel → Cargo Pod (Medium), Titanium + Glass + Panel → Cargo Pod (Large), and Neutronium + Cells + Controls + Rare Earth + Tar → Neutron Capacitor |
| Tier input | Heat Generator Mk III, 12 t/h |

##### Water `water`

Fresh liquid water raised from underground wells by a `water_pump`, or recovered from steam by a `steam_condenser`. Pumped groundwater leaves `salt` behind as a byproduct. Feeds fluid-hungry machine tiers and industry.

| Field | Value |
| --- | --- |
| Type | Liquid |
| Produced by | Steam Condenser and Water Pump |
| Consumed by | Fabricator, Bio Caster, Plant Terraformer, Sprinkler, and Reactor and Iron + Titanium → Machine Frame, Iron + Glass → Circuit Panel, Panel + Titanium + Glass → Control Unit, Cobalt + Iron + Glass → Battery Cell, Iron + Titanium + Glass → Tank Lining, Plastic + Forage + Water → Reinforced Biopolymer, Biopolymer + Forage + Water → Enrichment Compound, Frame + Control + Gas Pipe Segments + Liquid Pipe Segments → Drone Depot Kit, Frame + Control + Panel → Drone Depot Kit (Medium), Frame + Control + Panel → Drone Depot Kit (Large), Frame + Control + Panel → Mining Drill Kit, Frame + Control + Panel + Rotor → Industrial Mining Drill Kit, Frame + Control + Panel + Rotors → Heavy Mining Drill Kit, Rare Earth + Titanium + Control → Drone (Small), Rare Earth + Titanium + Control → Drone (Medium), Rare Earth + Titanium + Control → Drone (Large), Rare Earth + Control + Lubricant + Rubber → Heli Thruster, Titanium + Lubricant + Rubber → Oil Tank (Small), Titanium + Lubricant + Rubber + Lining → Oil Tank (Medium), Titanium + Lubricant + Rubber + Lining → Oil Tank (Large), Pipes + Valves + Rare Earth + Titanium + Tar → Coolant Loop, Neutronium + Cells + Controls + Rare Earth + Tar → Neutron Capacitor, Frame + Control + Panel → Seed Maker Kit, Frames + Controls + Panels + Liquid Pipe Segments → Plant Terraformer Kit, Frame + Pipes + Valve → Sprinkler Kit, Tar + Glass → Fertilizer, Tar + Glass + Panel → Fertilizer Mk II, Tar + Glass + Capacitor + Rare Earth → Fertilizer Mk III, Plastic + Rare Earth → Growth Accelerant, Capacitor + Controls + Rare Earth + Coolant → Yield Amplifier, Controls + Panels + Rare Earth + Valves → Plant Terraformer Pack Mk II, Capacitor + Rare Earth + Controls → Grow Lamp Pack Mk III, Controls + Panels + Coolant → Sprinkler Pack Mk III, Frames + Controls + Panels + Valves → Feed Maker Pack Mk II, and Capacitors + Rare Earth + Controls + Coolant → Habitat Pack Mk II |
| Tier input | Oxygen Generator Mk III, 8 t/h and Pressure Generator Mk III, 5 t/h |

##### Oil `oil`

Heavy crude drawn from oil wells by an `oil_pump`. Burned by the `oil_generator` for power and processed into polymers, `lubricant`, and `tar`.

| Field | Value |
| --- | --- |
| Type | Liquid |
| Produced by | Oil Pump |
| Consumed by | Fabricator, Oil Generator, and Drone Service Station and Iron + Oil → Lubricant + Tar, Glass + Oil → Plastic + Tar, Cobalt + Oil → Rubber + Tar, and Heavy Oil Cracking: Oil → Tar |

### Biome Essences

Biological concentrates pressed from native life forms. Each biome yields its own essence.

##### Frozen Essence `frozen_essence`

Pale crystalline concentrate liquified from Frozen-biome life forms at the `essence_liquifier`.

| Field | Value |
| --- | --- |
| Type | Liquid |
| Produced by | Essence Liquifier |
| Consumed by | Biomass Mixer |

##### Coastal Essence `coastal_essence`

Brackish green concentrate liquified from Coastal-biome life forms at the `essence_liquifier`.

| Field | Value |
| --- | --- |
| Type | Liquid |
| Produced by | Essence Liquifier |
| Consumed by | Biomass Mixer |

##### Geothermal Essence `geothermal_essence`

Warm mineral concentrate liquified from Geothermal-biome life forms at the `essence_liquifier`.

| Field | Value |
| --- | --- |
| Type | Liquid |
| Produced by | Essence Liquifier |
| Consumed by | Biomass Mixer |

##### Volcanic Essence `volcanic_essence`

Deep red sulfurous concentrate liquified from Volcanic-biome life forms at the `essence_liquifier`.

| Field | Value |
| --- | --- |
| Type | Liquid |
| Produced by | Essence Liquifier |
| Consumed by | Biomass Mixer |

##### Deep Essence `deep_essence`

Violet subterranean concentrate liquified from Deep-biome life forms at the `essence_liquifier`.

| Field | Value |
| --- | --- |
| Type | Liquid |
| Produced by | Essence Liquifier |
| Consumed by | Biomass Mixer |

### Exotic Gases

Gases tapped from cyclic vent deposits with an `exotic_gas_cap`. Common gases flow straight to use; rarer ones arrive raw and need refining.

##### Ammonia `ammonia`

Common alkaline exotic gas, tapped straight from its vent deposits. Usable as-is, no refining needed.

| Field | Value |
| --- | --- |
| Type | Gas |

##### Swamp Gas `swamp_gas`

Common marsh gas tapped from lowland vent deposits. Usable as-is, no refining needed.

| Field | Value |
| --- | --- |
| Type | Gas |

##### Raw Sulfur Gas `raw_sulfur_gas`

Unrefined sulfur feedstock from volcanic gas vents. The `refiner` purifies it into `sulfur_gas`, burning `tar` in the process.

| Field | Value |
| --- | --- |
| Type | Gas |
| Refines into | Sulfur Gas |
| Consumed by | Raw Sulfur Gas + Tar → Sulfur Gas |

##### Sulfur Gas `sulfur_gas`

Refined sulfur gas, purified from `raw_sulfur_gas` at the `refiner`.

| Field | Value |
| --- | --- |
| Type | Gas |
| Refined from | Raw Sulfur Gas |
| Recipe output | Raw Sulfur Gas + Tar → Sulfur Gas |

##### Raw Chlorine `raw_chlorine`

Unrefined chlorine feedstock from gas vents. Refines into `chlorine` at a heavy `tar` cost.

| Field | Value |
| --- | --- |
| Type | Gas |
| Refines into | Chlorine |
| Consumed by | Raw Chlorine + Tar → Chlorine |

##### Chlorine `chlorine`

Refined caustic chlorine, the rarest of the exotic gases.

| Field | Value |
| --- | --- |
| Type | Gas |
| Refined from | Raw Chlorine |
| Recipe output | Raw Chlorine + Tar → Chlorine |

### Exotic Liquids

Liquids tapped from spring deposits with an `exotic_spring_tap`. Common liquids flow straight to use; rarer ones arrive raw and need refining.

##### Brine `brine`

Common mineral-heavy liquid tapped from spring deposits. Usable as-is, no refining needed.

| Field | Value |
| --- | --- |
| Type | Liquid |

##### Raw Cryofluid `raw_cryofluid`

Unrefined supercooled feedstock from spring taps. The `refiner` purifies it into `cryofluid`.

| Field | Value |
| --- | --- |
| Type | Liquid |
| Refines into | Cryofluid |
| Consumed by | Raw Cryofluid + Tar → Cryofluid |

##### Cryofluid `cryofluid`

Refined supercooled fluid, purified from `raw_cryofluid` at the `refiner`.

| Field | Value |
| --- | --- |
| Type | Liquid |
| Refined from | Raw Cryofluid |
| Recipe output | Raw Cryofluid + Tar → Cryofluid |

##### Raw Quicksilver `raw_quicksilver`

Unrefined liquid-metal amalgam from spring taps. Refines into `quicksilver` at a heavy `tar` cost.

| Field | Value |
| --- | --- |
| Type | Liquid |
| Refines into | Quicksilver |
| Consumed by | Raw Quicksilver + Tar → Quicksilver |

##### Quicksilver `quicksilver`

Refined liquid metal, the rarest of the exotic liquids.

| Field | Value |
| --- | --- |
| Type | Liquid |
| Refined from | Raw Quicksilver |
| Recipe output | Raw Quicksilver + Tar → Quicksilver |

*Database / Research*
