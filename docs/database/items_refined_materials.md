# Database: items_refined_materials

> **Category:** Items | **Section:** Refined Materials

Smelter output: the standard stock every Fabricator blueprint builds on.

##### Iron Ingot `iron_ingot`

Smelted iron stock. The universal structural input: frames, segments, valves, and half the Fabricator catalogue start here.

| Field | Value |
| --- | --- |
| Produced by | Iron Ore → Iron Ingot |
| Used in | Iron → Gas Pipe Segment, Iron + Silicon → Liquid Pipe Segment, Iron + Titanium → Power Line Segment, Iron + Glass → Pressure Valve, Iron + Titanium → Machine Frame, Iron + Glass → Circuit Panel, Cobalt + Iron + Glass → Battery Cell, Iron + Titanium + Glass → Tank Lining, Iron + Glass + Liquid Pipe Segment → Water Pump, Iron + Titanium + Valve + Panel → Oil Pump, Iron + Oil → Lubricant + Tar, and Frame + Iron + Panel → Waste Processor Kit |
| Requested by | Helios, Iron Bootstrap, Helios, Iron Production, Helios, Mixed Alloy Order, Helios, Battery Order, Helios, Bulk Iron Run, Helios, Bulk Frame Run, Vestibule, Utility Conduit Stock, and Helios, Lead Survey Stock |

##### Glass `glass`

Smelted silicon sheet stock for panels, housings, and optics.

| Field | Value |
| --- | --- |
| Produced by | Silicon → Glass |
| Used in | Iron + Glass → Pressure Valve, Iron + Glass → Circuit Panel, Panel + Titanium + Glass → Control Unit, Cobalt + Iron + Glass → Battery Cell, Iron + Titanium + Glass → Tank Lining, Iron + Glass + Liquid Pipe Segment → Water Pump, Glass + Oil → Plastic + Tar, Titanium + Glass → Cargo Pod (Small), Titanium + Glass + Panel → Cargo Pod (Medium), Titanium + Glass + Panel → Cargo Pod (Large), Titanium + Glass + Cell → Battery Pack, Frame + Panel + Glass → Grow Lamp Kit, Tar + Glass → Fertilizer, Tar + Glass + Panel → Fertilizer Mk II, Tar + Glass + Capacitor + Rare Earth → Fertilizer Mk III, and Panel + Glass + Rare Earth → Grow Lamp Pack Mk II |
| Requested by | Spire, Optical Glass, Spire, Pressure Hardware, Spire, Optics Stockpile, and Spire, Silicon Megahaul |

##### Titanium Ingot `titanium_ingot`

High-strength, lightweight stock for rotors, thrusters, and pressure hardware.

| Field | Value |
| --- | --- |
| Produced by | Titanium → Titanium Ingot |
| Used in | Iron + Titanium → Power Line Segment, Iron + Titanium → Machine Frame, Panel + Titanium + Glass → Control Unit, Titanium + Pipes → Thermal Cap Kit, Titanium + Cobalt + Rare Earth → Turbine Rotor, Iron + Titanium + Glass → Tank Lining, Iron + Titanium + Valve + Panel → Oil Pump, Rare Earth + Titanium + Control → Drone (Small), Rare Earth + Titanium + Control → Drone (Medium), Rare Earth + Titanium + Control → Drone (Large), Titanium + Glass → Cargo Pod (Small), Titanium + Glass + Panel → Cargo Pod (Medium), Titanium + Glass + Panel → Cargo Pod (Large), Titanium + Glass + Cell → Battery Pack, Titanium + Lubricant + Rubber → Oil Tank (Small), Titanium + Lubricant + Rubber + Lining → Oil Tank (Medium), Titanium + Lubricant + Rubber + Lining → Oil Tank (Large), Pipes + Valves + Rare Earth + Titanium + Tar → Coolant Loop, Titanium + Gas Pipe Segments → Exotic Gas Cap Kit, and Titanium + Liquid Pipe Segments + Valve → Exotic Spring Tap Kit |
| Requested by | Helios, Titanium Run, Helios, Mixed Alloy Order, and Helios, Lead Survey Stock |

##### Cobalt Ingot `cobalt_ingot`

Battery-grade stock. Every `battery_cell` is built around it.

| Field | Value |
| --- | --- |
| Produced by | Cobalt → Cobalt Ingot |
| Used in | Cobalt + Iron + Glass → Battery Cell, Titanium + Cobalt + Rare Earth → Turbine Rotor, Cobalt + Oil → Rubber + Tar, Oxygen Upgrade Pack Mk IV, Heat Upgrade Pack Mk IV, and Pressure Upgrade Pack Mk IV |
| Requested by | Spire, Cobalt Run, Spire, Magnetic Stator Build, and Spire, Cobalt Stockpile |

##### Rare Earth Core `rare_earth_core`

Precision magnetic core stock for control units and advanced electronics.

| Field | Value |
| --- | --- |
| Produced by | Rare Earth → Rare Earth Core |
| Used in | Titanium + Cobalt + Rare Earth → Turbine Rotor, Rare Earth + Titanium + Control → Drone (Small), Rare Earth + Titanium + Control → Drone (Medium), Rare Earth + Titanium + Control → Drone (Large), Rare Earth + Rotor → Electric Thruster, Rare Earth + Control + Lubricant + Rubber → Heli Thruster, Pipes + Valves + Rare Earth + Titanium + Tar → Coolant Loop, Neutronium + Cells + Controls + Rare Earth + Tar → Neutron Capacitor, Tar + Glass + Capacitor + Rare Earth → Fertilizer Mk III, Plastic + Rare Earth → Growth Accelerant, Capacitor + Controls + Rare Earth + Coolant → Yield Amplifier, Controls + Panels + Rare Earth + Valves → Plant Terraformer Pack Mk II, Panel + Glass + Rare Earth → Grow Lamp Pack Mk II, Capacitor + Rare Earth + Controls → Grow Lamp Pack Mk III, and Capacitors + Rare Earth + Controls + Coolant → Habitat Pack Mk II |
| Requested by | Spire, Rare Earth Order, Spire, Drone Power Trial, and Spire, Capacitor Bulk Order |

##### Neutronium Bar `neutronium_bar`

Ultra-dense bar stock for neutron capacitors and advanced hardware.

| Field | Value |
| --- | --- |
| Produced by | Neutronium → Neutronium Bar |
| Used in | Neutronium + Cells + Controls + Rare Earth + Tar → Neutron Capacitor |
| Requested by | Spire, Neutronium Order and Spire, Neutronium Megastock |

##### Lead Ingot `lead_ingot`

Soft, dense shielding stock. Rolls into `lead_plate` for casks and reactor hardware.

| Field | Value |
| --- | --- |
| Produced by | Lead Ore → Lead Ingot |
| Used in | Lead Plate |
| Requested by | Helios, Lead Consignment |

*Database / Items*
