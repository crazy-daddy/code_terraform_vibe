# Formulas, Biome Colors, Hardware Catalog, Invocation Pattern (§1, §3, §5, §6)

Part of [`AI_CHEATSHEET.md`](../AI_CHEATSHEET.md). Topic detail (§1a onward) lives in the other `cheatsheet/` files.

## §1 Core Terraforming & Physics Formulas

| System | Component | Key Formula / Setpoint | Limits & Constraints |
| :--- | :--- | :--- | :--- |
| **Solar Tracking** | `solar_generator` | `tilt = 90 - sun_elevation` | 0° (flat) to 90° (vertical). Night output = 0 W. Peak = 50 W. Day curve, output formula, night sizing: [gameknowledge/solar.md](../gameknowledge/solar.md). |
| **Oxygen Generation** | `oxygen_generator` | `intake = atmosphere.get_co2() / 10.0` | Power: -8 W. Dump waste when `50 <= waste < 60` (clean dump, 0 penalty). Stalls at 100 waste. |
| **Heat Calibration** | `heat_generator` | `power = 1..10 W` (sweep / cache by weather) | Power: -10 W max. Re-eval optimal power on day/weather change. |
| **Pressure Sync** | `pressure_generator` | Sync pulse with resonance window peak | Power: -7 W (Mk I; tiers in §5). 100% efficiency on exact resonance window hit. |
| **Power Grid & Brownout** | `power_control`, `battery` | Battery = 500 Wh (300 cr). Safe floor: 15-20% | Configurable shedding tiers (`power.shedding_tiers`) — see §1a for full tier/threshold breakdown. |

## §3 Planet Map Biome Colors (player-observed, verify with `nocturna.biome_at(x, y)`)

| Map Color | Biome |
| :--- | :--- |
| Blue (incl. base's slightly-green patch) | `frozen` |
| Green | `coastal` |
| Dark brown / red | `volcanic` |
| Light brown | `geothermal` |
| Purple | `deep` |

## §5 Hardware Catalog & Production Specs

| Machine | Price | Power Profile | Storage / Capacity | Primary Function |
| :--- | :--- | :--- | :--- | :--- |
| `solar_generator` | 500 cr | +50 W (Day peak) | N/A | Primary green power gen. |
| `battery` | 300 cr | 0 W (Buffer) | 500 Wh | Grid buffer & night survival. |
| `heat_generator` | 800 cr | -1 to -10 W (power setting) × tier multiplier | N/A | Surface warming. |
| `oxygen_generator` | 1,000 cr | -8 W × tier multiplier | 4 units input | Atmospheric CO2 -> O2 conversion. |
| `pressure_generator` | 1,000 cr | -7 W × tier multiplier | N/A | Atmospheric pressure builder. |
| `smelter` | 1,500 cr | -20 to -45 W (per active recipe; 0 W idle/not running) | In/Out slots | Ore -> ingots (Iron, Glass, Titanium). No breaker cycling needed. |
| `bio_collector` | 2,500 cr | -5 W | 30 units | Autonomous bio specimen harvesting. |
| `bio_lab` | 5,000 cr | -5 W | 30 in / 30 stock | Specimen analysis, sample extraction. |
| `bio_exchange` | 2,000 cr | -5 W | Orders queue | Earth bio order fulfillment & credit rewards. |
| `bio_luminizer` | 60,000 cr | -12 W | 10 in / 10 out | Coastal glow-tinting (3-lamp mix solve, §1e). |
| `bio_caster` | 150,000 cr | -15 W | 30 out, 20t steam/water buffers | Volcanic forge-casting (heat/cool band control, §1g). |
| `bio_conditioner` | 225,000 cr | -25 W | 10 in / 10 out | Deep QC quiz (automated, §1g). |
| `dna_sequencer` | 100,000 cr | -20 W | 10 in / 10 out | Geothermal gene-splicing (§1g). |
| `supply_dock` | 3,000 cr | -15 W | 50 units | Earth / Contractor campaign bulk order shipping. |
| `vehicle_charging_station`| 2,000 cr | -50 W max | Pad + Rescue drone| Vehicle fast-charge & auto rescue dispatch. |

Terraformer tier power (`oxygen_generator`, `heat_generator`, `pressure_generator`): Mk I draw × 1 / 5 / 20 / 100 for Mk I / II / III / IV (simworker `gm()`, table `[1, 5, 20, 100]`). Pressure: 7 / 35 / 140 / 700 W. O2: 8 / 40 / 160 / 800 W. Heater: power setting × the same factor. Draw is 0 while no script runs on the machine. Solar sizing for these loads: [gameknowledge/solar.md](../gameknowledge/solar.md).

## §6 Standard Component Invocation Patterns

```python
# 1. Connect to standard components
atmosphere = get_component("atmosphere")
clock = get_component("clock")
power = get_component("power_control")
comms = get_component("comms")

# 2. Reusable controller pattern
from terraforming import HeatController, OxygenController, PressureController
from solar import SolarController
from power import PowerGridManager
from rover import RoverController
from bio import BioCollectorController, BioLabController, BioExchangeController
from bio_coastal import BioLuminizerController
from harvesting import HarvesterController

# Execute main loop
controller = SolarController(self)
controller.run()
```
