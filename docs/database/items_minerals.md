# Database: items_minerals

> **Category:** Items | **Section:** Minerals

Raw ore mined from surveyed mineral sites. Hardness (**H1** to **H4**) gates which sonar detects a site and which drill can work it; each ore smelts 1:1 into its refined form at the `smelter`.

##### Iron Ore `iron_ore`

Common structural ore from the inner mineral sites. The backbone of early industry: nearly every frame, segment, and machine part starts as iron.
Time per unit with each drill module that can cut it, on a standard site. Rich sites dig 2× faster and pure sites 3× faster. Field Mining Drills don't use these times.

| Field | Value |
| --- | --- |
| Hardness | H1 |
| Dig time | Drill Module: 15 min per unit, Industrial Drill: 11.25 min per unit, Heavy Drill: 9 min per unit |
| Used in | Iron Ore → Iron Ingot |
| Requested by | Spire, Raw Iron Intake |

##### Silicon `silicon`

Glassmaking ore abundant across the inner rings. Smelts into `glass` for panels, housings, and electronics.
Time per unit with each drill module that can cut it, on a standard site. Rich sites dig 2× faster and pure sites 3× faster. Field Mining Drills don't use these times.

| Field | Value |
| --- | --- |
| Hardness | H1 |
| Dig time | Drill Module: 15 min per unit, Industrial Drill: 11.25 min per unit, Heavy Drill: 9 min per unit |
| Used in | Silicon → Glass and Iron + Silicon → Liquid Pipe Segment |
| Requested by | Spire, Silicon Stock, Spire, Silicon Bootstrap, and Spire, Silicon Megahaul |

##### Titanium `titanium`

Light, strong mid-ring ore. Smelts into `titanium_ingot` for rotors, thrusters, and high-stress parts.
Time per unit with each drill module that can cut it, on a standard site. Rich sites dig 2× faster and pure sites 3× faster. Field Mining Drills don't use these times.

| Field | Value |
| --- | --- |
| Hardness | H2 |
| Dig time | Industrial Drill: 15 min per unit, Heavy Drill: 12 min per unit |
| Used in | Titanium → Titanium Ingot |
| Requested by | Spire, Titanium Consignment |

##### Cobalt `cobalt`

Battery-chemistry ore from the mid rings. Smelts into `cobalt_ingot`, the heart of every battery cell.
Time per unit with each drill module that can cut it, on a standard site. Rich sites dig 2× faster and pure sites 3× faster. Field Mining Drills don't use these times.

| Field | Value |
| --- | --- |
| Hardness | H2 |
| Dig time | Industrial Drill: 15 min per unit, Heavy Drill: 12 min per unit |
| Used in | Cobalt → Cobalt Ingot |

##### Rare Earth `rare_earth`

Scarce magnetic ore from the outer rings. Smelts into `rare_earth_core` for control electronics and precision drives.
Time per unit with each drill module that can cut it, on a standard site. Rich sites dig 2× faster and pure sites 3× faster. Field Mining Drills don't use these times.

| Field | Value |
| --- | --- |
| Hardness | H3 |
| Dig time | Industrial Drill: 18.75 min per unit, Heavy Drill: 15 min per unit |
| Used in | Rare Earth → Rare Earth Core |

##### Neutronium `neutronium`

The hardest known ore on the planet, found far from base. Smelts into `neutronium_bar` for capacitors and deep-tier hardware.
Time per unit with each drill module that can cut it, on a standard site. Rich sites dig 2× faster and pure sites 3× faster. Field Mining Drills don't use these times.

| Field | Value |
| --- | --- |
| Hardness | H4 |
| Dig time | Heavy Drill: 18 min per unit |
| Used in | Neutronium → Neutronium Bar |

##### Lead Ore `lead_ore`

Dense, soft ore from mineral sites. Smelts into `lead_ingot`, the base of all radiation shielding.
Time per unit with each drill module that can cut it, on a standard site. Rich sites dig 2× faster and pure sites 3× faster. Field Mining Drills don't use these times.

| Field | Value |
| --- | --- |
| Hardness | H2 |
| Dig time | Industrial Drill: 13.5 min per unit, Heavy Drill: 10.8 min per unit |
| Used in | Lead Ore → Lead Ingot |

*Database / Items*
