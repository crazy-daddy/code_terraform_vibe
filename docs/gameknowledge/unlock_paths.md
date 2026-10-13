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
| Power Line Segment | Earth Order `vestibule_01` (200 Iron Ingots) | Iron + Titanium Ingot, so `helios_01` must come first (owner, 2026-10-07). |

Older notes said Wide Sonar at 6.0 kPa and the Industrial Drill at 100 ppt; those values are from an earlier game build. With 1.8 kPa and 30 ppt, titanium and steam move into the 100k-150k TP window, right after the Pioneer (100k TP).

## Early Earth Order queues

Each contractor shows one current order; `orders.list_upcoming_orders()` returns the rest in queue order. Orders with a recipe reward on the titanium/steam/electronics path (docks rank `EARLY_UNLOCK_ORDER_IDS` first, [production_logistics.md](../cheatsheet/production_logistics.md) "Key unlock orders"):

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

`spire_intake_3` asks for raw titanium, so the Spire queue waits on a Pioneer with the Industrial Drill before Glass unlocks. A dock holding it requests the titanium at its outpost at need tier (`site_supply.dock_raw_wants()`), so Pioneers mine it first once their drill cuts H2.

## Drone path

After the power line unlocks, the key order list (`EARLY_UNLOCK_ORDER_IDS`) follows the electric drone path: Drone (Small) chassis, Electric Thruster, Battery Pack, Small Cargo Pod, a Drone Depot and a Drone Service Station (owner, 2026-10-10). Each contractor works its queue in order, so the list only decides which contractor's current order docks serve first. After `helios_09` and `spire_10` it continues with the Helios queue (below).

| Order | Requires | Unlocks | Drone use |
| :--- | :--- | :--- | :--- |
| `helios_03` | 60 Titanium Ingot | Battery Cell | Battery Pack, Service Station kit |
| `helios_04` | 200 Iron + 80 Titanium Ingot | Charging Station Mk III pack (tech) | none, in the queue |
| `helios_05` | 60 Battery Cell + 160 Iron Ingot | Machine Frame | Depot and Service Station kits |
| `helios_06` | 60 Machine Frame | Drone Depot Kit | Depot |
| `helios_07` | 60 Thermal Cap Kit | Turbine Rotor | Electric Thruster |
| `helios_08` | 60 Turbine Rotor | Drone (Small) | chassis |
| `helios_09` | 10 Drone (Small) | Cargo Pod (Small) | hauler module |
| `spire_01` … `spire_03` | Silicon, Glass, Circuit Panel | Glass, Circuit Panel, Control Unit | chassis, kits |
| `spire_04` | 80 Circuit Panel + 60 Control Unit | smelt Cobalt Ingot | Battery Cell, Turbine Rotor |
| `spire_05` | 60 Cobalt Ingot | Pressure Valve | needed by `spire_06` |
| `spire_06` | 80 Pressure Valve + 80 Glass | Battery Pack | energy module |
| `spire_07` | 80 Control Unit | smelt Rare Earth Core | chassis, thruster |
| `spire_08` | 60 Rare Earth Core | Electric Thruster | thruster |
| `spire_09` | 120 Circuit Panel + 80 Control Unit | Heat Mk III pack (tech) | none, in the queue |
| `spire_10` | 80 Battery Pack + 60 Rare Earth Core | Drone Service Station Kit | charging |

Vestibule past `vestibule_01` is off the path: Lubricant (`vestibule_03`) and Rubber (`vestibule_05`) only feed the Heli Thruster (`vestibule_12`). The Liquid Pipe for the Depot and Service Station kits comes from `spire_intake_2`. `spire_11` unlocks Plastic, which no drone part uses.

Once the Depot and Service Station kit recipes are unlocked, `lib/drone_kit_stock.py` keeps one kit of each in stock while some outpost lacks that building.

## Helios after the drone path

After `spire_10` the key order list follows the Helios queue to `helios_25`: Mining Drill Kit, Drone (Large), Heavy Mining Drill Kit (owner, 2026-10-12). Orders without a reward stay in the list, since the queue only moves in order. Every input recipe comes from an order earlier in the list: Glass, Circuit Panel, Control Unit and Rare Earth Core from `spire_01` … `spire_07`, Machine Frame, Battery Cell, Turbine Rotor and Drone (Small) from Helios. No Vestibule order past `vestibule_01` is needed.

| Order | Requires | Unlocks |
| :--- | :--- | :--- |
| `helios_10` | 10 Drone Depot Kit | Oxygen Mk III pack (tech) |
| `helios_11` | 600 Iron Ingot + 80 Machine Frame | Tank Lining (needs Glass, Titanium Ingot) |
| `helios_12` | 120 Battery Cell + 80 Tank Lining | nothing |
| `helios_13` | 80 Machine Frame + 60 Tank Lining | nothing |
| `helios_14` | 200 Cargo Pod (Small) + 300 Machine Frame | Mining Drill Kit |
| `helios_15` | 100 Mining Drill Kit | nothing |
| `helios_16` | 500 Machine Frame + 3000 Iron Ingot | nothing |
| `helios_17` | 600 Battery Cell + 400 Tank Lining | Cargo Pod (Medium) |
| `helios_18` | 200 Cargo Pod (Medium) | Drone Depot Kit (Medium) |
| `helios_19` | 200 Drone (Small) + 100 Cargo Pod (Medium) | Drone (Medium) |
| `helios_20` | 50 Mining Drill Kit | Industrial Mining Drill Kit |
| `helios_21` | 200 Cargo Pod (Medium) | Cargo Pod (Large) |
| `helios_22` | 100 Drone (Medium) + 100 Cargo Pod (Large) | Drone (Large) |
| `helios_23` | 400 Drone (Small) + 200 Drone (Medium) | nothing |
| `helios_24` | 200 Drone Depot Kit (Medium) | Drone Depot Kit (Large) |
| `helios_25` | 50 Industrial Mining Drill Kit | Heavy Mining Drill Kit |

## Yield Amplifier and heli path

After `helios_25` the key order list follows the Spire queue to `spire_18` (Yield Amplifier; the in-game list labels it 21, since the three `spire_intake_*` orders come first), then the Vestibule queue to `vestibule_15` (Large Oil Tank) (owner, 2026-10-13). The Spire orders after `spire_18` only unlock Mk III Grow Lamp and Sprinkler packs, so they stay off the list. Every input recipe comes from an order earlier in the list: Electric Thruster (`spire_08`), Pressure Valve (`spire_05`), Battery Cell (`helios_03`), Tank Lining (`helios_11`) and the Drone Service Station Kit (`spire_10`). Lubricant and Rubber also need oil (Oil Pump research).

| Order | Requires | Unlocks |
| :--- | :--- | :--- |
| `spire_11` | 120 Cobalt Ingot + 160 Control Unit | Plastic |
| `spire_12` | 60 Plastic + 40 Circuit Panel | Neutronium Bar |
| `spire_13` | 60 Neutronium Bar | Coolant Loop |
| `spire_14` | 200 Electric Thruster | nothing |
| `spire_15` | 100 Electric Thruster + 200 Control Unit | nothing |
| `spire_16` | 600 Circuit Panel + 800 Glass | nothing |
| `spire_17` | 800 Cobalt Ingot | Neutron Capacitor |
| `spire_18` | 100 Neutron Capacitor + 200 Control Unit | Yield Amplifier |
| `vestibule_02` | 60 Gas Pipe Segment | nothing |
| `vestibule_03` | 60 Liquid Pipe Segment | Lubricant |
| `vestibule_04` | 60 Pressure Valve + 60 Liquid Pipe Segment | nothing |
| `vestibule_05` | 300 Gas Pipe Segment + 300 Liquid Pipe Segment | Rubber |
| `vestibule_06` | 200 Lubricant + 200 Rubber | nothing |
| `vestibule_07` | 300 Liquid Pipe Segment + 300 Gas Pipe Segment | nothing |
| `vestibule_08` | 400 Lubricant + 400 Rubber | nothing |
| `vestibule_09` | 600 Rubber + 600 Lubricant | nothing |
| `vestibule_10` | 600 Liquid Pipe Segment + 800 Lubricant | nothing |
| `vestibule_11` | 300 Liquid Pipe Segment + 200 Lubricant + 100 Rubber | nothing |
| `vestibule_12` | 50 Drone Service Station Kit | Heli Thruster |
| `vestibule_13` | 100 Heli Thruster | Oil Tank (Small) |
| `vestibule_14` | 200 Oil Tank (Small) | Oil Tank (Medium) |
| `vestibule_15` | 200 Oil Tank (Medium) | Oil Tank (Large) |

## Rovers

Rover chassis 0.11 kPa, Nav 0.12, Sonar 0.15, Drill module 0.2 kPa, Charging Station at Oxygen 9 ppt. A Rover mines iron and silicon only. The build order fills pressure last, so Rovers would arrive close to the 100k TP scout Pioneers; the early buyer buys none by default (`ROVERS = 0`, owner 2026-10-07).
