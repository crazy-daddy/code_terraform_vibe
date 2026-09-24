# Database: items_fabricated_components

> **Category:** Items | **Section:** Fabricated Components

Fabricator output: machined parts, infrastructure segments, deploy kits, and oil-derived polymers. Earth contractors order many of these, check each card's Requested By row.

##### Gas Pipe Segment `gas_pipe_segment`

A 10 m run of gas pipe. A Pioneer's Constructor consumes one per planned segment when laying gas lines.

| Field | Value |
| --- | --- |
| Sells for | 20 cr |
| Produced by | Iron → Gas Pipe Segment |
| Used in | Gas Segments + Valve → Gas Bridge, Titanium + Pipes → Thermal Cap Kit, Frame + Control + Gas Pipe Segments + Liquid Pipe Segments → Drone Depot Kit, and Titanium + Gas Pipe Segments → Exotic Gas Cap Kit |
| Requested by | Vestibule, Gas Pipe Order, Vestibule, Pipe Network Run, and Vestibule, Pipe Order |

##### Liquid Pipe Segment `liquid_pipe_segment`

A 10 m run of liquid pipe. A Pioneer's Constructor consumes one per planned segment when laying liquid lines.

| Field | Value |
| --- | --- |
| Sells for | 20 cr |
| Produced by | Iron + Silicon → Liquid Pipe Segment |
| Used in | Liquid Segments + Valve → Liquid Bridge, Iron + Glass + Liquid Pipe Segment → Water Pump, Frame + Control + Gas Pipe Segments + Liquid Pipe Segments → Drone Depot Kit, Frame + Control + Panel + Cell + Liquid Pipe Segment → Drone Service Station Kit, Pipes + Valves + Rare Earth + Titanium + Tar → Coolant Loop, Frames + Controls + Panels + Liquid Pipe Segments → Plant Terraformer Kit, Frame + Pipes + Valve → Sprinkler Kit, and Titanium + Liquid Pipe Segments + Valve → Exotic Spring Tap Kit |
| Requested by | Vestibule, Liquid Pipe Order, Vestibule, Pressure Network Trial, Vestibule, Pipe Network Run, Vestibule, Pipe Order, Vestibule, Pipe & Lubricant Order, Vestibule, Refueling Hardware Build, and Vestibule, Continental Pipe Build |

##### Power Line Segment `power_line_segment`

A 10 m run of power line. A Pioneer's Constructor consumes one per planned segment when wiring outposts and machines.

| Field | Value |
| --- | --- |
| Sells for | 20 cr |
| Produced by | Iron + Titanium → Power Line Segment |
| Used in | Power Segments + Circuit → Power Bridge |

##### Gas Pipe Bridge `gas_pipe_bridge`

A 3-tile gas overpass that lets one line cross another without joining networks.

| Field | Value |
| --- | --- |
| Produced by | Gas Segments + Valve → Gas Bridge |

##### Liquid Pipe Bridge `liquid_pipe_bridge`

A 3-tile liquid overpass that lets one line cross another without joining networks.

| Field | Value |
| --- | --- |
| Produced by | Liquid Segments + Valve → Liquid Bridge |

##### Power Line Bridge `power_line_bridge`

A 3-tile power overpass that lets one line cross another without joining networks.

| Field | Value |
| --- | --- |
| Produced by | Power Segments + Circuit → Power Bridge |

##### Pressure Valve `pressure_valve`

Machined flow-control valve used across pumps, tanks, and atmospheric hardware.

| Field | Value |
| --- | --- |
| Produced by | Iron + Glass → Pressure Valve |
| Used in | Gas Segments + Valve → Gas Bridge, Liquid Segments + Valve → Liquid Bridge, Iron + Titanium + Valve + Panel → Oil Pump, Pipes + Valves + Rare Earth + Titanium + Tar → Coolant Loop, Frame + Pipes + Valve → Sprinkler Kit, Titanium + Liquid Pipe Segments + Valve → Exotic Spring Tap Kit, Controls + Panels + Rare Earth + Valves → Plant Terraformer Pack Mk II, Plastic + Coolant + Valves → Sprinkler Pack Mk II, and Frames + Controls + Panels + Valves → Feed Maker Pack Mk II |
| Requested by | Spire, Pressure Hardware and Vestibule, Pressure Network Trial |

##### Machine Frame `machine_frame`

Standard structural chassis most mid-tier machines are assembled on.

| Field | Value |
| --- | --- |
| Produced by | Iron + Titanium → Machine Frame |
| Used in | Frame + Control + Gas Pipe Segments + Liquid Pipe Segments → Drone Depot Kit, Frame + Control + Panel → Drone Depot Kit (Medium), Frame + Control + Panel → Drone Depot Kit (Large), Frame + Control + Panel + Cell + Liquid Pipe Segment → Drone Service Station Kit, Frame + Control + Panel → Mining Drill Kit, Frame + Control + Panel + Rotor → Industrial Mining Drill Kit, Frame + Control + Panel + Rotors → Heavy Mining Drill Kit, Frame + Control + Panel → Seed Maker Kit, Frames + Controls + Panels + Liquid Pipe Segments → Plant Terraformer Kit, Frame + Panel + Glass → Grow Lamp Kit, Frame + Pipes + Valve → Sprinkler Kit, Frame + Control + Panel → Dispenser Kit, Frame + Iron + Panel → Waste Processor Kit, Frames + Controls + Panels + Valves → Feed Maker Pack Mk II, Oxygen Upgrade Pack Mk IV, Heat Upgrade Pack Mk IV, Pressure Upgrade Pack Mk IV, Lead Cask, Shield Plating, and Lightning Rod |
| Requested by | Helios, Frame Order, Helios, Bulk Iron Run, Helios, Reservoir Build, Helios, Cargo Pod Run, Helios, Bulk Frame Run, and Helios, Reactor Vessel Chain |

##### Circuit Panel `circuit_panel`

Printed control circuitry for machine logic and instrumentation.

| Field | Value |
| --- | --- |
| Produced by | Iron + Glass → Circuit Panel |
| Used in | Power Segments + Circuit → Power Bridge, Panel + Titanium + Glass → Control Unit, Iron + Titanium + Valve + Panel → Oil Pump, Frame + Control + Panel → Drone Depot Kit (Medium), Frame + Control + Panel → Drone Depot Kit (Large), Frame + Control + Panel + Cell + Liquid Pipe Segment → Drone Service Station Kit, Frame + Control + Panel → Mining Drill Kit, Frame + Control + Panel + Rotor → Industrial Mining Drill Kit, Frame + Control + Panel + Rotors → Heavy Mining Drill Kit, Titanium + Glass + Panel → Cargo Pod (Medium), Titanium + Glass + Panel → Cargo Pod (Large), Frame + Control + Panel → Seed Maker Kit, Frames + Controls + Panels + Liquid Pipe Segments → Plant Terraformer Kit, Frame + Panel + Glass → Grow Lamp Kit, Frame + Control + Panel → Dispenser Kit, Frame + Iron + Panel → Waste Processor Kit, Tar + Glass + Panel → Fertilizer Mk II, Controls + Panels + Rare Earth + Valves → Plant Terraformer Pack Mk II, Panel + Glass + Rare Earth → Grow Lamp Pack Mk II, Controls + Panels + Coolant → Sprinkler Pack Mk III, Frames + Controls + Panels + Valves → Feed Maker Pack Mk II, Oxygen Upgrade Pack Mk IV, Heat Upgrade Pack Mk IV, Pressure Upgrade Pack Mk IV, and Lightning Rod |
| Requested by | Spire, Circuit Order, Spire, Avionics Run, Spire, Avionics Megabuild, Spire, Polymer Optics Run, Spire, Optics Stockpile, and Spire, Avionics Megastock |

##### Control Unit `control_unit`

Sealed processing module that drives advanced machines and vehicles.

| Field | Value |
| --- | --- |
| Produced by | Panel + Titanium + Glass → Control Unit |
| Used in | Frame + Control + Gas Pipe Segments + Liquid Pipe Segments → Drone Depot Kit, Frame + Control + Panel → Drone Depot Kit (Medium), Frame + Control + Panel → Drone Depot Kit (Large), Frame + Control + Panel + Cell + Liquid Pipe Segment → Drone Service Station Kit, Frame + Control + Panel → Mining Drill Kit, Frame + Control + Panel + Rotor → Industrial Mining Drill Kit, Frame + Control + Panel + Rotors → Heavy Mining Drill Kit, Rare Earth + Titanium + Control → Drone (Small), Rare Earth + Titanium + Control → Drone (Medium), Rare Earth + Titanium + Control → Drone (Large), Rare Earth + Control + Lubricant + Rubber → Heli Thruster, Neutronium + Cells + Controls + Rare Earth + Tar → Neutron Capacitor, Frame + Control + Panel → Seed Maker Kit, Frames + Controls + Panels + Liquid Pipe Segments → Plant Terraformer Kit, Frame + Control + Panel → Dispenser Kit, Capacitor + Controls + Rare Earth + Coolant → Yield Amplifier, Controls + Panels + Rare Earth + Valves → Plant Terraformer Pack Mk II, Capacitor + Rare Earth + Controls → Grow Lamp Pack Mk III, Controls + Panels + Coolant → Sprinkler Pack Mk III, Frames + Controls + Panels + Valves → Feed Maker Pack Mk II, and Capacitors + Rare Earth + Controls + Coolant → Habitat Pack Mk II |
| Requested by | Spire, Avionics Run, Spire, Control Run, Spire, Avionics Megabuild, Spire, Magnetic Stator Build, Spire, Propulsion Control Run, Spire, Neutron Capacitor Order, and Spire, Avionics Megastock |

##### Battery Cell `battery_cell`

Cobalt-chemistry storage cell, the building block of battery packs and grid storage.

| Field | Value |
| --- | --- |
| Produced by | Cobalt + Iron + Glass → Battery Cell |
| Used in | Frame + Control + Panel + Cell + Liquid Pipe Segment → Drone Service Station Kit, Titanium + Glass + Cell → Battery Pack, Neutronium + Cells + Controls + Rare Earth + Tar → Neutron Capacitor, and Lightning Rod |
| Requested by | Helios, Battery Order, Helios, Drone Chassis Build, and Helios, Mid-Cargo Build |

##### Thermal Cap Kit `thermal_cap_kit`

Constructor-deployed kit that caps a surveyed thermal vent with a `thermal_cap` and captures Steam. If its chamber reaches **100%**, it blows all stored Steam into the atmosphere; a script must release, route, or relieve the pressure.

| Field | Value |
| --- | --- |
| Sells for | 800 cr |
| Produced by | Titanium + Pipes → Thermal Cap Kit |
| Requested by | Helios, Cap Kit Order |
| Deploys | Thermal Cap |

##### Turbine Rotor `turbine_rotor`

Precision-balanced titanium rotor for steam turbines.

| Field | Value |
| --- | --- |
| Produced by | Titanium + Cobalt + Rare Earth → Turbine Rotor |
| Used in | Frame + Control + Panel + Rotor → Industrial Mining Drill Kit, Frame + Control + Panel + Rotors → Heavy Mining Drill Kit, and Rare Earth + Rotor → Electric Thruster |
| Requested by | Helios, Rotor Run |

##### Tank Lining `tank_lining`

Corrosion-proof lining for gas and liquid tanks.

| Field | Value |
| --- | --- |
| Produced by | Iron + Titanium + Glass → Tank Lining |
| Used in | Titanium + Lubricant + Rubber + Lining → Oil Tank (Medium) and Titanium + Lubricant + Rubber + Lining → Oil Tank (Large) |
| Requested by | Helios, Drone Chassis Build, Helios, Reservoir Build, and Helios, Mid-Cargo Build |

##### Lubricant `lubricant`

Refined oil derivative that keeps drives and rotors running smoothly.

| Field | Value |
| --- | --- |
| Produced by | Iron + Oil → Lubricant + Tar |
| Used in | Rare Earth + Control + Lubricant + Rubber → Heli Thruster, Titanium + Lubricant + Rubber → Oil Tank (Small), Titanium + Lubricant + Rubber + Lining → Oil Tank (Medium), and Titanium + Lubricant + Rubber + Lining → Oil Tank (Large) |
| Requested by | Vestibule, Polymer Stockpile, Vestibule, Bulk Polymer Run, Vestibule, Polymer Run, Vestibule, Pipe & Lubricant Order, Vestibule, Refueling Hardware Build, Vestibule, Polymer Bulk Order, Vestibule, Polymer Megaorder, Vestibule, Tether Megahaul, and Vestibule, Shielded Transport Trial |

##### Plastic `plastic`

Oil-derived polymer stock for housings and insulation.

| Field | Value |
| --- | --- |
| Produced by | Glass + Oil → Plastic + Tar |
| Used in | Plastic + Forage + Water → Reinforced Biopolymer, Plastic + Rare Earth → Growth Accelerant, and Plastic + Coolant + Valves → Sprinkler Pack Mk II |
| Requested by | Spire, Polymer Optics Run, Spire, Polymer Megastock, and Spire, Polymer Megaorder |

##### Rubber `rubber`

Flexible oil-derived stock for gaskets and seals.

| Field | Value |
| --- | --- |
| Produced by | Cobalt + Oil → Rubber + Tar |
| Used in | Rare Earth + Control + Lubricant + Rubber → Heli Thruster, Titanium + Lubricant + Rubber → Oil Tank (Small), Titanium + Lubricant + Rubber + Lining → Oil Tank (Medium), and Titanium + Lubricant + Rubber + Lining → Oil Tank (Large) |
| Requested by | Vestibule, Polymer Stockpile, Vestibule, Bulk Polymer Run, Vestibule, Polymer Run, Vestibule, Refueling Hardware Build, Vestibule, Polymer Bulk Order, Vestibule, Polymer Megaorder, and Vestibule, Flexible Habitat Liners |

##### Tar `tar`

Heavy oil residue used in fertilizer, advanced components, and the `refiner`. Oil-product recipes create it as a byproduct; Heavy Oil Cracking produces it directly.

| Field | Value |
| --- | --- |
| Produced by | Heavy Oil Cracking: Oil → Tar |
| Byproduct of | Iron + Oil → Lubricant + Tar, Glass + Oil → Plastic + Tar, and Cobalt + Oil → Rubber + Tar |
| Used in | Pipes + Valves + Rare Earth + Titanium + Tar → Coolant Loop, Neutronium + Cells + Controls + Rare Earth + Tar → Neutron Capacitor, Tar + Glass → Fertilizer, Tar + Glass + Panel → Fertilizer Mk II, Tar + Glass + Capacitor + Rare Earth → Fertilizer Mk III, Raw Sulfur Gas + Tar → Sulfur Gas, Raw Cryofluid + Tar → Cryofluid, Raw Chlorine + Tar → Chlorine, and Raw Quicksilver + Tar → Quicksilver |

##### Reinforced Biopolymer `reinforced_biopolymer`

Structural biological composite made from plastic, plant forage, and water. Used in late Earth exports and advanced biological chemistry.

| Field | Value |
| --- | --- |
| Produced by | Plastic + Forage + Water → Reinforced Biopolymer |
| Used in | Biopolymer + Forage + Water → Enrichment Compound |
| Requested by | Spire, Biopolymer Thermal Stock, Vestibule, Flexible Habitat Liners, Helios, Enriched Habitat Trial, and Spire, Biosphere Export Program |

##### Enrichment Compound `enrichment_compound`

Concentrated biological material made from Reinforced Biopolymer, forage, and water for late Earth exports.

| Field | Value |
| --- | --- |
| Produced by | Biopolymer + Forage + Water → Enrichment Compound |
| Requested by | Helios, Enriched Habitat Trial and Spire, Biosphere Export Program |

##### Coolant Loop `coolant_loop`

Closed-circuit coolant assembly for reactor-grade heat loads.

| Field | Value |
| --- | --- |
| Produced by | Pipes + Valves + Rare Earth + Titanium + Tar → Coolant Loop |
| Used in | Capacitor + Controls + Rare Earth + Coolant → Yield Amplifier, Plastic + Coolant + Valves → Sprinkler Pack Mk II, Controls + Panels + Coolant → Sprinkler Pack Mk III, and Capacitors + Rare Earth + Controls + Coolant → Habitat Pack Mk II |
| Requested by | Spire, Polymer Megastock, Spire, T4 Reactor Build, and Spire, Biopolymer Thermal Stock |

##### Neutron Capacitor `neutron_capacitor`

Neutronium storage device for extreme energy applications.

| Field | Value |
| --- | --- |
| Produced by | Neutronium + Cells + Controls + Rare Earth + Tar → Neutron Capacitor |
| Used in | Tar + Glass + Capacitor + Rare Earth → Fertilizer Mk III, Capacitor + Controls + Rare Earth + Coolant → Yield Amplifier, Capacitor + Rare Earth + Controls → Grow Lamp Pack Mk III, and Capacitors + Rare Earth + Controls + Coolant → Habitat Pack Mk II |
| Requested by | Spire, Neutron Capacitor Order, Spire, Capacitor Bulk Order, and Spire, T4 Reactor Build |

##### Fertilizer `fertilizer`

Basic soil nutrient blend. One field dose gives a growing crop **2×** base Forage yield on its own (**+100%**) for **8 hours**. Same-tier doses extend duration; switch tiers after the active dose expires. Its yield bonus adds to provider and Yield Amplifier bonuses. A Plant Terraformer consumes each item for **10 potency** toward its recipe. Unused potency stays in the machine for later batches.

| Field | Value |
| --- | --- |
| Produced by | Tar + Glass → Fertilizer |

##### Fertilizer Mk II `fertilizer_mk2`

Concentrated nutrient blend. One field dose gives a growing crop **3×** base Forage yield on its own (**+200%**) for **8 hours**. Same-tier doses extend duration; switch tiers after the active dose expires. Its yield bonus adds to provider and Yield Amplifier bonuses. A Plant Terraformer consumes each item for **30 potency** toward its recipe. Unused potency stays in the machine for later batches.

| Field | Value |
| --- | --- |
| Produced by | Tar + Glass + Panel → Fertilizer Mk II |

##### Fertilizer Mk III `fertilizer_mk3`

Top-grade nutrient blend. One field dose gives a growing crop **5×** base Forage yield on its own (**+400%**) for **8 hours**. Same-tier doses extend duration; switch tiers after the active dose expires. Its yield bonus adds to provider and Yield Amplifier bonuses. A Plant Terraformer consumes each item for **50 potency** toward its recipe. Unused potency stays in the machine for later batches.

| Field | Value |
| --- | --- |
| Produced by | Tar + Glass + Capacitor + Rare Earth → Fertilizer Mk III |

##### Growth Accelerant `growth_accelerant`

One field dose doubles a growing crop's growth speed for **8 hours**, reaching the same yield sooner while its requirements are met. Additional doses extend duration. Also consumed as a whole-item input for the Plant Terraformer's final conversion recipe; it has no potency tiers.

| Field | Value |
| --- | --- |
| Produced by | Plastic + Rare Earth → Growth Accelerant |

##### Yield Amplifier `yield_amplifier`

One dose adds **+200% base Forage yield** (**3×** on its own) to growing crops across the whole field for **24 hours**. Its bonus adds to provider and Fertilizer bonuses. Additional doses extend duration. Mature crops keep their already banked Forage.

| Field | Value |
| --- | --- |
| Produced by | Capacitor + Controls + Rare Earth + Coolant → Yield Amplifier |

##### Grow Lamp Mk II Upgrade Pack `grow_lamp_upgrade_pack_mk2`

Upgrades one Grow Lamp to Mk II: **2×** base Forage yield on its own (**+100%**) and **25 W** draw while enabled. The bonus applies during growth to crops that require light in the four orthogonally adjacent cells, while the lamp is powered and enabled. Coverage and growth speed stay the same. Only the strongest covering lamp counts; its bonus adds to other yield bonuses.

| Field | Value |
| --- | --- |
| Produced by | Panel + Glass + Rare Earth → Grow Lamp Pack Mk II |
| Component docs | Grow Lamp |

##### Grow Lamp Mk III Upgrade Pack `grow_lamp_upgrade_pack_mk3`

Upgrades one Grow Lamp to Mk III: **4×** base Forage yield on its own (**+300%**) and **100 W** draw while enabled. The bonus applies during growth to crops that require light in the four orthogonally adjacent cells, while the lamp is powered and enabled. Coverage and growth speed stay the same. Only the strongest covering lamp counts; its bonus adds to other yield bonuses.

| Field | Value |
| --- | --- |
| Produced by | Capacitor + Rare Earth + Controls → Grow Lamp Pack Mk III |
| Component docs | Grow Lamp |

##### Sprinkler Mk II Upgrade Pack `sprinkler_upgrade_pack_mk2`

Upgrades one Sprinkler to Mk II: **2×** base Forage yield on its own (**+100%**), **25 W** draw while enabled, and **4 t/h Water** use while supplied. The bonus applies during growth to crops that require water in the four orthogonally adjacent cells, while the sprinkler is powered, enabled, and supplied. Coverage and growth speed stay the same. Only the strongest covering sprinkler counts; its bonus adds to other yield bonuses.

| Field | Value |
| --- | --- |
| Produced by | Plastic + Coolant + Valves → Sprinkler Pack Mk II |
| Component docs | Sprinkler |

##### Sprinkler Mk III Upgrade Pack `sprinkler_upgrade_pack_mk3`

Upgrades one Sprinkler to Mk III: **4×** base Forage yield on its own (**+300%**), **100 W** draw while enabled, and **8 t/h Water** use while supplied. The bonus applies during growth to crops that require water in the four orthogonally adjacent cells, while the sprinkler is powered, enabled, and supplied. Coverage and growth speed stay the same. Only the strongest covering sprinkler counts; its bonus adds to other yield bonuses.

| Field | Value |
| --- | --- |
| Produced by | Controls + Panels + Coolant → Sprinkler Pack Mk III |
| Component docs | Sprinkler |

##### Lead Plate `lead_plate`

Rolled lead shielding plate for casks, fuel rods, and reactor internals.

| Field | Value |
| --- | --- |
| Produced by | Lead Plate |
| Used in | Oxygen Upgrade Pack Mk IV, Heat Upgrade Pack Mk IV, Pressure Upgrade Pack Mk IV, Lead Cask, Shield Plating, Fuel Rod, and Nuclear Battery |
| Requested by | Helios, Plate Order, Vestibule, Shielded Transport Trial, and Helios, Reactor Vessel Chain |

##### Raw Uranium `raw_uranium`

Storm-dealt fissile ore. Hot cargo: Lead Casks are its only stationary home. Any drone can risk extraction, but each unplated batch adds 40 exposure; Shield Plating makes that gain zero.

| Field | Value |
| --- | --- |
| Used in | Fuel Rod and Nuclear Battery |
| Requested by | Vestibule, Hot Freight Proof |

##### Fuel Rod `fuel_rod`

Pressed reactor fuel, enriched uranium in a lead jacket. Hot cargo, cask-to-cask handling only.

| Field | Value |
| --- | --- |
| Produced by | Fuel Rod |
| Requested by | Vestibule, Fuel Rod Contract (Crown) |

*Database / Items*
