# Unlock paths: titanium, steam and the first Earth Orders

Source: research table, mineral table, sonar/drill hardness limits and the campaign order queues in `internals/terraform_decompiled/simworker/deobfuscated.js` (search `research_sonar_wide`, `hardness: 2`, `function W_e(`, `helios_01`). Checked 2026-10-07 against `docs/database/` (research thresholds match). Recheck after a game update.

## Titanium comes early

Titanium ore is hardness **2** (Cobalt and Lead too; Rare Earth 3, Neutronium 4). Tool limits jump from 1 to 3: basic Sonar/Drill reach H1, Wide Sonar and the Industrial Drill module H3, Deep/Heavy H4. So titanium needs the H3 tools:

| Step | Gate | Notes |
| :--- | :--- | :--- |
| Find titanium sites | Wide Sonar, **Pressure 1.8 kPa** | Basic sonar reports H2+ contacts as `too_hard` (a mineral, [survey_contacts.md](survey_contacts.md)). |
| Mine titanium ore | Industrial Drill module, **Oxygen 30 ppt** | On a Pioneer (universal slot). Rovers carry only basic modules, so they never mine titanium. The static Mk I Mining Drill is H1 only; the Mk II kit comes from order `helios_20`. |
| Smelt Titanium Ingot | Earth Order `helios_01` (150 Iron Ingots) | Recipe reward, the first Helios order. |
| Thermal Cap Kit | Thermal Cap research (Pressure 2.5 kPa) | 2 Titanium Ingot + 2 Gas Pipe Segment. Gas Pipe comes from `helios_02` (300 Iron Ingots). |
| Power Line Segment | Earth Order `vestibule_01` (200 Iron Ingots) | Iron + Titanium. |

Older notes said Wide Sonar at 6.0 kPa and the Industrial Drill at 100 ppt; those values are from an earlier game build. With 1.8 kPa and 30 ppt, titanium and steam move into the 100k-150k TP window, right after the Pioneer (100k TP).

## Early Earth Order queues

Each contractor shows one current order; `orders.list_upcoming_orders()` returns the rest in queue order. Orders with a recipe reward on the titanium/steam/electronics path (weights in `KEY_UNLOCK_ORDERS`, [production_logistics.md](../cheatsheet/production_logistics.md) "Key unlock orders"):

| Contractor | Order | Requires | Unlocks |
| :--- | :--- | :--- | :--- |
| Helios | `helios_01` | 150 Iron Ingot | smelt Titanium Ingot |
| Helios | `helios_02` | 300 Iron Ingot | Gas Pipe Segment |
| Helios | `helios_03` | 60 Titanium Ingot | Battery Cell |
| Spire | `spire_intake_1` | 50 Iron Ore | nothing (opens the queue) |
| Spire | `spire_intake_2` | 75 Silicon | Liquid Pipe Segment |
| Spire | `spire_intake_3` | 60 Titanium (ore) | nothing |
| Spire | `spire_01` | 150 Silicon | smelt Glass |
| Spire | `spire_02` | 60 Glass | Circuit Panel |
| Spire | `spire_03` | 60 Circuit Panel | Control Unit |
| Vestibule | `vestibule_01` | 200 Iron Ingot | Power Line Segment |

`spire_intake_3` asks for raw titanium, so the Spire queue waits on a Pioneer with the Industrial Drill before Glass unlocks.

## Rovers

Rover chassis 0.11 kPa, Nav 0.12, Sonar 0.15, Drill module 0.2 kPa, Charging Station at Oxygen 9 ppt. A Rover mines iron and silicon only. When the cold-boot build order fills pressure last, the Rovers arrive close to the 100k TP Pioneer and add little.
