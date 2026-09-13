# Database: equipment_power

> **Category:** Equipment | **Section:** Power Equipment

Power generation, storage, charging, and grid hardware from the Shop. Research-gated equipment is documented here before it appears in the Shop.

##### Solar Generator `solar_generator`

Script-tracked photovoltaic panel producing up to **50 W** in sunlight and **0 W** at night. Poor tilt reduces daytime output.

| Field | Value |
| --- | --- |
| Sells for | 500 cr |
| Shop price | 500 cr |

##### Small Battery `battery`

Base-station energy storage.

| Field | Value |
| --- | --- |
| Sells for | 300 cr |
| Shop price | 300 cr |

##### Large Battery `battery_large`

High-capacity base-station energy storage.

| Field | Value |
| --- | --- |
| Sells for | 15,000 cr |
| Shop price | 15,000 cr |
| Component docs | Battery |

##### Oil Generator `oil_generator`

Burns oil to generate power.

| Field | Value |
| --- | --- |
| Sells for | 2,000 cr |
| Shop price | 2,000 cr |
| Component docs | Oil Generator |

##### Reactor `reactor`

Fission plant producing up to **5,000 W** from Fuel Rods and cooling water. One rod lasts **72 hours** at heat **1.0**; fuel use follows commanded heat even before the core reaches efficient temperature.

| Field | Value |
| --- | --- |
| Sells for | 750,000 cr |
| Shop price | 750,000 cr |

##### Nuclear Battery `nuclear_battery`

Uranium-core storage cell holding thirty times a base battery's charge.

| Field | Value |
| --- | --- |
| Produced by | Nuclear Battery |
| Requested by | Helios, Battery Contract (Crown) |

##### Lightning Rod `lightning_rod`

Deploys a **4,000 Wh**, **600 m** lightning reserve. Condition falls **0.05 per day**, reducing capture to zero unless a script repairs it with Storm Glass.

| Field | Value |
| --- | --- |
| Produced by | Lightning Rod |

*Database / Equipment*
