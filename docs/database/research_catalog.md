# Database: research_catalog

> **Category:** Research | **Section:** Research

The complete technology tree for this build. Research remains documented before it unlocks so you can search future systems, understand their thresholds, and plan toward them.

### Terraform Index

##### Camera Feed `research_camera_feed` *(Unlocked)*

Watch Nocturna change in real time. Bring the exterior camera online and watch the world outside through a live feed. Storms cross the basin, ice gives way, strange life takes hold, and the base you built glows against the dark.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 5,000 |
| Tech id | camera_feed_unlock |

##### Ship Computer `research_computer` *(Unlocked)*

Computer dashboard access. Unlocks the Ship → Computer page: a dashboard for system status, script management, the Playground, achievements, and notifications. It also opens the `computer` component to scripts, so deploying, undeploying, decommissioning, and renaming can run from code instead of a button. Further research adds more Computer tabs, starting with the Library.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 10,000 |
| Tech id | ship_computer |

##### Shared Library `research_shared_library` *(Unlocked)*

Reusable code across scripts. Adds the Library tab to the Ship Computer. Write reusable helper functions once in the Library, then import them into any machine script, so shared logic lives in one place instead of being copied everywhere.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 20,000 |
| Tech id | shared_library |

##### Signal Bus `research_signal_bus` *(Unlocked)*

Script-to-script messaging. Adds the Signal Bus tab to the Ship Computer. Scripts coordinate with each other by sending queued messages or broadcasting shared values on named channels: explicit, save-safe shared state instead of hidden globals.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 35,000 |
| Tech id | signal_bus_unlock |

##### Data Archive `research_data_archive` *(Unlocked)*

Persistent learned tables. Adds the Data Archive tab to the Ship Computer. Scripts can store lookup tables, calibration samples, discovered maps, and other learned knowledge that persists across restarts and save/load. Use the Signal Bus for live coordination and the Data Archive for long-lived data.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 70,000 |
| Tech id | data_archive_unlock |

##### Pioneer Chassis `research_pioneer` *(Unlocked)*

Expedition vehicle access. Unlocks the eight-slot Pioneer chassis in the Shop. It has no built-in battery, cargo, or Nav and cannot move until separately purchased hardware is installed.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 100,000 |
| Tech id | pioneer_unlock |

##### Supply Logistics `research_orders_system` *(Unlocked)*

Unlocks Orders and Supply Dock purchasing. A long-range logistics protocol for Earth demand. Supply Docks become available in the Shop and ship **25 units/h** before throughput research; build more docks to serve orders in parallel.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 110,000 |
| Tech id | orders_system_unlock |

##### Outpost Construction `research_outpost_hub` *(Unlocked)*

Found new sites across the planet. Unlocks the Outpost Kit in the shop. Founding also needs Constructor Module research and a Constructor-equipped Pioneer to build the blueprint. Each outpost holds a soft **20** buildings, which Outpost Expansion later raises by **5**. Each kit costs more than the last, **15,000 cr** to **1,000,000 cr**, priced on founded expansion outposts plus unbuilt Outpost Kits held in physical storage.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 120,000 |
| Tech id | outpost_unlock |

##### Fabrication `research_fabricator` *(Unlocked)*

Heavy manufacturing access. Unlocks the Fabricator in the Shop. This industrial assembly press combines refined materials into finished equipment, modules, and vehicle frames.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 130,000 |
| Tech id | fabricator_unlock |

##### Cartography `research_cartography` *(Unlocked)*

Annotate the Planet Map. Adds map markers: named, colored annotations you place in Plan Mode or from any script with `get_component("markers")`. Markers are notes, not construction. They cost nothing, need no Pioneer, and appear the moment you place them, so a survey script can record what it found where it found it.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 140,000 |
| Tech id | cartography_unlock |

##### Control Room `research_custom_panels` *(Unlocked)*

Create script-driven control panels. Opens the Control Room, a top-level page for script-driven dashboard cards. Build clocks, fleet boards, vent-cycle timelines, and recovery controls with drawing and input APIs.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 150,000 |
| Tech id | custom_panels_unlock |

##### Basic Drone Operations `research_drones` *(Unlocked)*

Open aerial logistics before the biosphere era. Unlocks the drone system and its fleet dashboard, the Vehicles / Drones / Support roster under the Planet Map. Electric drones fly up to **300 m/h** and consume **5 Wh/h** at full throttle; burn rises with throttle squared. Drone hardware still requires blueprint recipes earned through Earth Orders. Fabricated facilities and chassis deploy from Inventory into outposts; field Mining Drills use Planet Map blueprints placed in Plan Mode or by script.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 180,000 |
| Tech id | drones_unlock |

##### Biosphere `research_biosphere` *(Unlocked)*

Unlocks biomass supply chain. Unlocks the **Biomass tier** supply chain and makes the Portable Bio Scanner, Portable Bio Extractor, Essence Liquifier, and Biomass Mixer available in the Shop. Scan biome tiles, extract life-form samples, and run them through the chain to produce biomass.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 210,000 |
| Tech id | biosphere_unlock |

##### Bigger Stacks `research_high_density_storage` *(Unlocked)*

Every inventory slot holds twice as much. Rebuilds the shelving at Nocturna Base so each slot takes a taller stack. Items that stack now go up to **20 per slot** instead of **10**. Equipment, modules, and other one-off items still take a slot each. This changes Base Inventory only, not vehicle cargo, Storage Bins, or Warehouses.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 250,000 |
| Tech id | high_density_storage_unlock |

##### Weather Program `research_weather_program` *(Unlocked)*

Track storms and treasure signals. Unlocks the **Weather Network**, installs one free completed Weather Station and its building slot at Nocturna Base, and makes additional stations available in the Shop. Observe local storms, handle live transmissions, and publish optional results to the Signal Board.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 330,000 |
| Tech id | weather_program_unlock |

##### Fast Feeders `research_fast_feeders` *(Unlocked)*

Twice the item-transfer throughput. Reduces the duration of every timed discrete-item transfer by **50%**. Machine endpoints remain occupied until the faster handling cycle finishes. Fluids and manual world actions are unaffected.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 400,000 |
| Tech id | fast_feeders_unlock |

##### Bulk Orders `research_bulk_orders` *(Not yet unlocked)*

Double the weekly board. Earth starts placing bulk weekly contracts. Every Weekly Earth Order asks for **twice** the goods and pays **twice** the credits, raising the board's combined payout ceiling from **20,000 cr** to **40,000 cr**. The change applies from the next refresh, so orders already on the board keep their original size.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 500,000 |
| Tech id | bulk_orders_unlock |

##### Cargo Expansion `research_cargo_expansion` *(Not yet unlocked)*

Buy extra inventory slots. Unlocks the **EXPAND** button on the Inventory page. Each slot costs more than the last, starting at **500 cr** for slot 37 and climbing to ~**146,000 cr** for the final slot, capped at **60** total. Total cost to fully max out: ~**666,000 cr**.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 520,000 |
| Tech id | cargo_expansion_unlock |

##### Weather Forecasting `research_weather_forecasting` *(Not yet unlocked)*

See approaching storms three times further out. Extends new Weather Station reports and Incoming coverage from **8** to **24 world-clock hours**. Forecasts remain local to storms expected to enter powered-station coverage.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 550,000 |
| Tech id | weather_forecasting_unlock |

##### High-Capacity Depot Handling `research_depot_handling` *(Not yet unlocked)*

Faster intake and dispatch at Drone Depots. Automatically improves existing and newly deployed Drone Depots: **2× handling at a base Depot**, **4× at Medium**, and **8× at Large**, stacking with Fast Feeders. Speeds intake and dispatch so several remote machines can share a supply route. Each receiving machine still has its own intake cooldown. Drone speed, cargo capacity and Supply Dock dispatch rates stay the same. No upgrade pack is needed.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 580,000 |
| Tech id | depot_handling_unlock |

##### High-Pressure Fluid Transport `research_high_pressure_fluid_transport` *(Not yet unlocked)*

Triple remote gas and liquid throughput. Retrofits every completed and future Gas Pipe and Liquid Pipe component. Each matched source-side and sink-side attachment link carries up to **6,000 t/h** instead of **2,000 t/h**. Pipe length and interior branches still add no capacity; separate attachment links and independent components retain their own budgets.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 600,000 |
| Tech id | high_pressure_fluid_transport_unlock |

##### Nuclear Program `research_nuclear_program` *(Not yet unlocked)*

The Reactor. Unlocks the **Reactor** in the Shop: Fuel Rods in, cooling water through, **5,000 W** out, day and night, storm or calm. One rod lasts **72 hours** at heat **1.0**, and fuel use follows commanded heat. Keep the core in the green band; push it too hot and it overheats and shuts down safely.

| Field | Value |
| --- | --- |
| Threshold | Terraform Index 650,000 |
| Tech id | nuclear_program_unlock |

### Temperature

##### Storage Bins `research_storage_bin` *(Unlocked)*

Single-material stockpile bins. Unlocks the Storage Bin in the shop. Deployable single-material containers for stockpiling raw and refined materials at an outpost, one material per bin. Keep what you mine, stage what you need. (The Warehouse, researched later, is the larger multi-material depot.)

| Field | Value |
| --- | --- |
| Threshold | Temperature 5 |
| Tech id | storage_bin_unlock |

##### Cargo Rack `research_cargo_rack_small` *(Unlocked)*

Modular vehicle cargo storage access. Unlocks the Small Cargo Rack and Portable Bin in the shop. A **1**-bin rack for modular vehicles, letting them haul mined ore back to base.

| Field | Value |
| --- | --- |
| Threshold | Temperature 8 |
| Tech id | cargo_rack_small_unlock |

##### Constructor Module `research_constructor_module` *(Unlocked)*

Builds Planet Map blueprints. Unlocks the Constructor Module for the Pioneer in the Shop. Plan construction in Planet Map Plan Mode or with `get_component("construction_blueprint")`, load the needed kits, segments, or bridges into the Pioneer's cargo, and drive out to build outposts, pipes, power lines, and machines on site.

| Field | Value |
| --- | --- |
| Threshold | Temperature 10 |
| Tech id | constructor_module_unlock |

##### Battery Holder `research_battery_holder_small` *(Unlocked)*

Portable battery bay access. Unlocks the Small Battery Holder in the shop. Adds a **1**-bay portable battery mount for modular vehicles, essential for any expedition away from the Vehicle Charging Station.

| Field | Value |
| --- | --- |
| Threshold | Temperature 12 |
| Tech id | battery_holder_small_unlock |

##### Heat Generator Mk II `research_heat_mk2_pack` *(Unlocked)*

Higher heat output. Unlocks the Heat Generator Mk II Upgrade Pack in the shop. Retrofits a Mk I heater to Mk II for higher output.

| Field | Value |
| --- | --- |
| Threshold | Temperature 80 |
| Tech id | heat_mk2_pack_unlock |

##### Bioluminescent Infusion `research_luminizer` *(Unlocked)*

Unlocks the Bio Luminizer. Unlocks the Bio Luminizer in the shop, the coastal machine that tunes a bioluminescent fragment's glow to an order's exact target color. Coastal Bio Orders require infused fragments.

| Field | Value |
| --- | --- |
| Threshold | Temperature 90 |
| Tech id | luminizer_unlock |

##### Medium Battery Holder `research_battery_holder_medium` *(Unlocked)*

Double-bay battery mount access. Unlocks the Medium Battery Holder in the shop. Two bays for portable batteries, a compact range upgrade for modular vehicles.

| Field | Value |
| --- | --- |
| Threshold | Temperature 280 |
| Tech id | battery_holder_medium_unlock |

##### Outpost Expansion `research_outpost_expansion` *(Unlocked)*

Increase every outpost's building capacity by 5. Raises the soft building capacity of every current and future outpost by **5**. Nocturna Base increases from **25** to **30** buildings, and founded outposts increase from **20** to **25**. Buildings beyond the new cap still incur the normal overcrowding penalty.

| Field | Value |
| --- | --- |
| Threshold | Temperature 400 |
| Tech id | outpost_expansion_unlock |

##### Large Battery `research_large_battery` *(Unlocked)*

5× grid storage in one cell. Unlocks the Large Battery in the Shop: **2,500 Wh** of base-station storage, five times the base cell. One unit replaces a cluster of Small Batteries.

| Field | Value |
| --- | --- |
| Threshold | Temperature 700 |
| Tech id | large_battery_unlock |

##### Deep-Sea Conditioning `research_bio_conditioner` *(Unlocked)*

Unlocks the Bio Conditioner. Unlocks the Bio Conditioner in the shop, the deep machine that quality-control-inspects a fragment through a 5-stage accept/reject gauntlet against a published rulebook. Deep Bio Orders require conditioned fragments. Power-only, no fluids or materials.

| Field | Value |
| --- | --- |
| Threshold | Temperature 1,200 |
| Tech id | bio_conditioner_unlock |

##### Oil Generator `research_oil_generator` *(Unlocked)*

High-density oil-burning power. Unlocks the Oil Generator in the shop. Burns oil to produce up to **700 W** from one machine (several times a Steam Turbine's peak) with full throttle control via script. Consumes **8 t/h** at full output.

| Field | Value |
| --- | --- |
| Threshold | Temperature 1,500 |
| Tech id | oil_generator_unlock |

##### Heli-Drones `research_heli_drones` *(Not yet unlocked)*

Long-range oil-fueled aerial transport. Allows Heli Thrusters and Oil Tanks to be mounted on drones. Their Fabricator recipes are earned separately through Vestibule orders. Heli drones fly **900 m/h** and consume **5 t/h Oil** at full throttle; burn rises with throttle squared. Three oil-tank sizes set their range, and Drone Service Stations refuel them from their oil input.

| Field | Value |
| --- | --- |
| Threshold | Temperature 6,000 |
| Tech id | heli_drones_unlock |

##### Lightning Rods `research_lightning_rod` *(Not yet unlocked)*

Catch strikes, bank the surge. Unlocks the **Lightning Rod Kit recipe**. This storm-charged bank stores **4,000 Wh**, catches strikes within **600 m**, and feeds the grid behind batteries. Condition falls **0.05 per day**, reducing capture to zero unless a script repairs it with **1 Storm Glass**.

| Field | Value |
| --- | --- |
| Threshold | Temperature 8,000 |
| Tech id | lightning_rod_unlock |

##### Fuel Assembler `research_fuel_assembler` *(Not yet unlocked)*

Raw Uranium + lead → Fuel Rods. Unlocks the Fuel Assembler in the Shop. This nuclear workbench presses Raw Uranium and lead casing into **Fuel Rods** and draws about **1,800 W** while running.

| Field | Value |
| --- | --- |
| Threshold | Temperature 10,000 |
| Tech id | fuel_assembler_unlock |

##### Heat Generator Mk IV `research_heat_mk4_pack` *(Not yet unlocked)*

Nuclear-era heat tier, fuelled by rods. Unlocks the **Heat Upgrade Pack Mk IV recipe** at the Fabricator. This final tier **replaces the steam input entirely** with a **Fuel Rod** magazine fed from a connected Lead Cask and draws roughly 100x Mk I power. **A heater with no rod stops producing** rather than degrading.

| Field | Value |
| --- | --- |
| Threshold | Temperature 42,000 |
| Tech id | heat_mk4_pack_unlock |

### Oxygen

##### Auto Feeders `research_auto_feeders` *(Unlocked)*

Material flow access. Unlocks property-preserving item flow through machine I/O ports. Inventory is a source or destination only at Nocturna Base; other endpoints must be at the machine's outpost or physically present vehicle location. Equal item ids with different properties remain distinct stacks.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 1 |
| Tech id | feeder_unlock |

##### Earth Clearance `research_earth_clearance` *(Unlocked)*

Advanced contract access. Unlocks three advanced contracts as atmospheric oxygen begins to rise.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 3 |
| Tech id | earth_clearance |

##### Ore Refinement `research_smelter` *(Unlocked)*

Refinement access. Unlocks the Smelter in the Shop. This industrial furnace reduces raw ore into refined metals and components suitable for advanced machinery.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 5 |
| Tech id | smelter_unlock |

##### Vehicle Charging Station `research_charging_station` *(Unlocked)*

Vehicle charging access. Unlocks the Vehicle Charging Station in the Shop. Mk I has **1 bay** and a **30 W** charging budget; later packs raise both fleet capacity and pooled solo charging speed.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 9 |
| Tech id | charging_station_unlock |

##### Industrial Drill `research_drill_industrial` *(Unlocked)*

Hardness-3 extraction access. Unlocks the Industrial Drill module in the shop. Extracts minerals up to hardness 3, which adds Titanium, Cobalt and Lead in the mid ring and Rare Earth in the outer ring. Faster dig time than the basic drill, higher power draw.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 30 |
| Tech id | drill_industrial_unlock |

##### Sport Nav `research_nav_sport` *(Unlocked)*

High-performance drivetrain access. Unlocks the Sport Nav module in the shop. One Sport Nav gives 2× top speed with 2.6× movement power draw compared with Basic Nav in the same rig, about 1.3× battery use per meter at full throttle. Further Sport Navs stack at a rising cost, especially on loaded long-haul routes.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 50 |
| Tech id | nav_sport_unlock |

##### Vehicle Charging Station Mk II `research_charging_station_mk2_pack` *(Unlocked)*

Second bay; pools to 120 W solo. Unlocks the Vehicle Charging Station Mk II Upgrade Pack in the shop. Retrofits a deployed station to Mk II, adding a second charging bay.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 60 |
| Tech id | charging_station_mk2_pack_unlock |

##### Oxygen Generator Mk II `research_oxygen_mk2_pack` *(Unlocked)*

Higher oxygen output. Unlocks the Oxygen Generator Mk II Upgrade Pack in the shop. Retrofits a Mk I oxygen generator to Mk II for higher output.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 75 |
| Tech id | oxygen_mk2_pack_unlock |

##### Warehouse `research_warehouse` *(Unlocked)*

Bulk-storage building. Unlocks the Warehouse in the shop. A **10,000-unit** multi-material depot: **5** material-locked slots of **2,000** each. Use it as a buffer for drone deliveries and large vehicle hauls.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 150 |
| Tech id | warehouse_unlock |

##### Verified Contractor `research_verified_contractor` *(Unlocked)*

New contract batch access. Your terraforming output has passed Earth's vetting threshold. A second batch of contracts (denser puzzles, higher rewards) routes to your terminal. Adds new tiers to the Contractor Reputation ladder.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 300 |
| Tech id | verified_contractor_unlock |

##### Volcanic Forge-Casting `research_bio_caster` *(Unlocked)*

Unlocks the Bio Caster. Unlocks the Bio Caster in the shop, the volcanic machine that heat-casts a fragment with fabricated materials. Volcanic Bio Orders require forged fragments.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 350 |
| Tech id | bio_caster_unlock |

##### Liquid Tank `research_liquid_tank` *(Unlocked)*

Buffer any one liquid. Unlocks the Liquid Tank in the Shop, a passive **100**-ton buffer that latches to the first liquid it receives (water, oil, or any biome essence) and holds only that fluid until drained.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 400 |
| Tech id | liquid_tank_unlock |

##### Waste Processing `research_garbage_disposal` *(Unlocked)*

Programmable destruction for unwanted items and fluids. Unlocks the **Waste Processor Kit recipe**. The machine permanently destroys one selected stream: any item through its feeder input, any liquid through `liquid_in`, or any gas through `gas_in`. This provides an explicit overflow path for tar, surplus water, and unwanted gases without recovering power or materials. Fabricate the kit at a Fabricator; its script selects and enables the active mode.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 1,400 |
| Tech id | garbage_disposal_unlock |

##### Petroleum Survey `research_petroleum_survey` *(Unlocked)*

Oil wells visible to Deep Sonar. Unlocks survey of subsurface oil deposits and the **Oil Pump recipe**. **Deep Sonar required**: oil wells are a hidden layer for the late-tier sonar. Fabricate an Oil Pump at a Fabricator, deploy it on a surveyed well, and pipe oil to base for power generation and refining.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 1,500 |
| Tech id | petroleum_survey_unlock |

##### Large Battery Holder `research_battery_holder_large` *(Unlocked)*

Triple-bay battery mount access. Unlocks the Large Battery Holder in the shop. Three bays, enough capacity to sustain Heavy Drill power draw on long edge-ring expeditions.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 1,800 |
| Tech id | battery_holder_large_unlock |

##### Large Cargo Rack `research_cargo_rack_large` *(Unlocked)*

Triple-bin cargo mount access. Unlocks the Large Cargo Rack in the shop. Three bins for maximum haul capacity on large mining runs.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 2,000 |
| Tech id | cargo_rack_large_unlock |

##### Heavy Drill `research_drill_heavy` *(Unlocked)*

Hardness-4 extraction access. Unlocks the Heavy Drill module in the shop. Extracts minerals up to hardness 4, so it cuts every mineral on the planet and is the only drill that can take Neutronium, required for Mk III fabrication.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 2,500 |
| Tech id | drill_heavy_unlock |

##### Shielded Logistics `research_shielded_logistics` *(Not yet unlocked)*

Lead Casks + hot-cargo handling. Hot cargo needs a shielded lane: **Lead Casks** are the only stationary home for Raw Uranium and Fuel Rods, and **Shield Plating** lets a drone extract Raw Uranium without gaining exposure. Unlocks both items' availability; the fabrication recipes come through contractor orders.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 3,000 |
| Tech id | shielded_logistics_unlock |

##### Shielded Depot Operations `research_shielded_depot_ops` *(Not yet unlocked)*

Move nuclear cargo through Drone Depots. Lines every Drone Depot with containment so hot cargo can pass through your logistics network. Until this is researched a depot refuses Raw Uranium and Fuel Rods outright, and a plated drone has nowhere to unload them. Applies to every depot you own and every one you build afterwards.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 8,000 |
| Tech id | shielded_depot_ops_unlock |

##### Oxygen Generator Mk IV `research_oxygen_mk4_pack` *(Not yet unlocked)*

Nuclear-era oxygen tier, fuelled by rods. Unlocks the **Oxygen Upgrade Pack Mk IV recipe** at the Fabricator. This final tier **replaces the water input entirely** with a **Fuel Rod** magazine fed from a connected Lead Cask and draws roughly 100x Mk I power. **A generator with no rod stops producing** rather than degrading.

| Field | Value |
| --- | --- |
| Threshold | Oxygen 40,000 |
| Tech id | oxygen_mk4_pack_unlock |

### Pressure

##### Mining Operations `research_mining` *(Unlocked)*

Planet Map and Vehicles tab access. Unlocks the Planet Map and its Vehicles tab for managing your ground vehicles. Prospect the surface before committing to a vehicle.

| Field | Value |
| --- | --- |
| Threshold | Pressure 0.1 |
| Tech id | mining_unlock |

##### Rover Chassis `research_rover` *(Unlocked)*

First expedition vehicle access. Unlocks the Rover in the Shop. Its integrated **100 Wh** battery and **10-unit** hold are fixed; Nav, Sonar, and Drill use three dedicated module slots.

| Field | Value |
| --- | --- |
| Threshold | Pressure 0.11 |
| Tech id | rover_unlock |

##### Nav Module `research_nav_module` *(Unlocked)*

Drive hardware access. Unlocks Nav modules in the shop. Gives vehicles the ability to navigate and drive from their own script. Stop, completion, or error cancels script-owned movement.

| Field | Value |
| --- | --- |
| Threshold | Pressure 0.12 |
| Tech id | nav_module_unlock |

##### Sonar Module `research_sonar_module` *(Unlocked)*

Survey hardware access. Unlocks Basic Sonar modules in the shop. Sonar performs point sweeps from a vehicle's current position, discovering nearby map sites and recording them in the Journal.

| Field | Value |
| --- | --- |
| Threshold | Pressure 0.15 |
| Tech id | sonar_module_unlock |

##### Drill Module `research_deep_extraction` *(Unlocked)*

Drilling hardware access. Unlocks Drill modules in the shop. Extract raw ore from surveyed mining sites.

| Field | Value |
| --- | --- |
| Threshold | Pressure 0.2 |
| Tech id | deep_extraction_unlock |

##### Pressure Generator Mk II `research_pressure_mk2_pack` *(Unlocked)*

Higher pressure output. Unlocks the Pressure Generator Mk II Upgrade Pack in the shop. Retrofits a Mk I pressure generator to Mk II for higher output.

| Field | Value |
| --- | --- |
| Threshold | Pressure 1.2 |
| Tech id | pressure_mk2_pack_unlock |

##### Wide Sonar `research_sonar_wide` *(Unlocked)*

Mid-ring survey hardware access. Unlocks the Wide Sonar module in the shop. Extends scan range to **180 m** and detects minerals up to hardness 3, including Titanium, Cobalt and Rare Earth, out in the mid and outer rings.

| Field | Value |
| --- | --- |
| Threshold | Pressure 1.8 |
| Tech id | sonar_wide_unlock |

##### Geological Survey `research_geological_survey` *(Unlocked)*

Sonar detects thermal vents. Extends the Sonar Module to detect thermal vents alongside mining sites. Surveyed vents are added to the Journal with their own readings, so you can find where steam can be tapped.

| Field | Value |
| --- | --- |
| Threshold | Pressure 2 |
| Tech id | geological_survey_unlock |

##### Thermal Cap `research_thermal_cap` *(Unlocked)*

Capture steam from vents. Unlocks the Thermal Cap and its **Thermal Cap Kit** recipe. Fabricate the kit at a Fabricator, then build the Cap on a surveyed thermal vent. It captures Steam while the vent is active and releases it to connected destinations over a completed Gas Pipe route. At **100%** the chamber blows away all stored Steam, so its script must release, route, or relieve the pressure.

| Field | Value |
| --- | --- |
| Threshold | Pressure 2.5 |
| Tech id | thermal_cap_unlock |

##### Gas Tank `research_steam_tank` *(Unlocked)*

Buffer one gas between machines. Unlocks the Gas Tank in the Shop, a passive **5000**-ton buffer that latches to the first gas it receives (steam, ammonia, swamp gas, or any gas) and holds only that gas until drained.

| Field | Value |
| --- | --- |
| Threshold | Pressure 2.75 |
| Tech id | steam_tank_unlock |

##### Steam Turbine `research_steam_turbine` *(Unlocked)*

Steam into grid power. Unlocks the Steam Turbine in the Shop. At full throttle it consumes **90 t/h Steam** and produces **108 W**; a script controls the throttle.

| Field | Value |
| --- | --- |
| Threshold | Pressure 3 |
| Tech id | steam_turbine_unlock |

##### Medium Cargo Rack `research_cargo_rack_medium` *(Unlocked)*

Double-bin cargo mount access. Unlocks the Medium Cargo Rack and Heavy Portable Bin in the shop. Two bins for larger hauls per run, with room for a second mineral.

| Field | Value |
| --- | --- |
| Threshold | Pressure 4.5 |
| Tech id | cargo_rack_medium_unlock |

##### Hydrology Survey `research_hydrology_survey` *(Unlocked)*

Water wells visible to sonar. Unlocks survey of subsurface water deposits and the **Water Pump recipe**. Sonar scans now reveal water wells across the map. Wells produce continuous water at their yield tier (1× / 2× / 3×). Fabricate a Water Pump at a Fabricator, deploy it on a surveyed well, and pipe the output to base.

| Field | Value |
| --- | --- |
| Threshold | Pressure 30 |
| Tech id | hydrology_survey_unlock |

##### Deep Sonar `research_sonar_deep` *(Unlocked)*

Edge-ring survey hardware access. Unlocks the Deep Sonar module in the shop. Extends scan range to **280 m** and detects minerals up to hardness 4, which adds Neutronium at the edge ring. Also deepens thermal/exotic survey detail and is required to reveal oil wells after **Petroleum Survey**.

| Field | Value |
| --- | --- |
| Threshold | Pressure 60 |
| Tech id | sonar_deep_unlock |

##### Gene Sequencing `research_dna_sequencer` *(Unlocked)*

Unlocks the DNA Sequencer. Unlocks the DNA Sequencer in the shop, the geothermal machine that reads and rewrites fragment DNA. Geothermal Bio Orders require fragments engineered to carry specific genes.

| Field | Value |
| --- | --- |
| Threshold | Pressure 120 |
| Tech id | dna_sequencer_unlock |

##### Prime Contractor `research_prime_contractor` *(Unlocked)*

Top contract batch access. Unlocks three difficult contracts in the atmosphere-era program. Completing them contributes to Contractor Reputation; the final contract batch arrives with Smart Contractor.

| Field | Value |
| --- | --- |
| Threshold | Pressure 130 |
| Tech id | prime_contractor_unlock |

##### Bulk Logistics II `research_dispatch_mk2` *(Not yet unlocked)*

Quadruple Supply Dock throughput. Quadruples each Supply Dock's per-pulse emission count from **1** to **4** units, so the effective rate jumps from **25 units/h** to **100 units/h**. Pulse cadence is unchanged; only the packet size scales.

| Field | Value |
| --- | --- |
| Threshold | Pressure 150 |
| Tech id | dispatch_mk2_unlock |

##### Pressure Generator Mk IV `research_pressure_mk4_pack` *(Not yet unlocked)*

Nuclear-era pressure tier, fuelled by rods. Unlocks the **Pressure Upgrade Pack Mk IV recipe** at the Fabricator. This final tier **replaces the water input entirely** with a **Fuel Rod** magazine fed from a connected Lead Cask and draws roughly 100x Mk I power. **A generator with no rod stops producing** rather than degrading.

| Field | Value |
| --- | --- |
| Threshold | Pressure 2,000 |
| Tech id | pressure_mk4_pack_unlock |

### Biomass

##### Seed Maker `research_seed_maker` *(Unlocked)*

Combine life-forms into seeds. Opens the **Plants** tier and unlocks the **Seed Maker Kit recipe**. The machine consumes **1 t each of three different harvested life forms** to test for a viable seed. Most combinations come out as sludge and produce nothing; the recipes that work are unique to this planet. Plant the seeds you find into your Harvester field.

| Field | Value |
| --- | --- |
| Threshold | Biomass 500 |
| Tech id | seed_maker_unlock |

##### Plant Terraformer `research_plant_terraformer` *(Unlocked)*

Turn harvested Forage into Plants progress. Unlocks the **Plant Terraformer Kit recipe** at **2,000 t Biomass**. It is the only machine that creates permanent Plants km². Feed it harvested Forage, then satisfy the cumulative phase ladder with Water, Salt, Fertilizer, and Growth Accelerant. Fabricate its kit, deploy it at an outpost, connect its supplies, and enable it from its script. Build as many as your harvest can feed.

| Field | Value |
| --- | --- |
| Threshold | Biomass 2,000 |
| Tech id | plant_terraformer_unlock |

##### Heavy Portable Battery `research_heavy_portable_battery` *(Unlocked)*

High-capacity vehicle cell access. Unlocks the Heavy Portable Battery in the shop. A **100 Wh** portable cell, double a standard battery, that drops into any vehicle holder bay to sustain long-haul fleets far from the Vehicle Charging Station.

| Field | Value |
| --- | --- |
| Threshold | Biomass 3,000 |
| Tech id | heavy_portable_battery_unlock |

##### Smart Contractor `research_smart_contractor` *(Unlocked)*

Final contract batch access. Your Biomass recovery has opened Earth's final contractor channel. Unlocks Beat the System, Core Sample, and Lattice, the three hardest programming contracts, and completes the Contractor Reputation ladder.

| Field | Value |
| --- | --- |
| Threshold | Biomass 20,000 |
| Tech id | smart_contractor_unlock |

##### Large Warehouse `research_high_bay_warehousing` *(Not yet unlocked)*

Fifteen kinds of material in one building. Unlocks the **Large Warehouse** in the shop. It holds **30,000 units** across **15** slots of **2,000**, and each slot sticks to one material. That is enough room for a wide biological and industrial supply chain to keep every material apart, without replacing Drone Depot handoffs or scripted transfers.

| Field | Value |
| --- | --- |
| Threshold | Biomass 30,000 |
| Tech id | high_bay_warehousing_unlock |

##### Biomass Mixer Mk II `research_biomass_mixer_mk2_pack` *(Not yet unlocked)*

87.5% more biomass per ton of essence. Unlocks the Biomass Mixer Mk II Upgrade Pack in the shop. One pack retrofits one deployed Mk I Mixer for **4.5× output** on only **2.4× essence consumption**, with **5× power draw**. That is **87.5%** more biomass per ton of essence, which matters because Liquifier intake is fixed and rare life forms regrow slowly. There is no Mk III.

| Field | Value |
| --- | --- |
| Threshold | Biomass 50,000 |
| Tech id | biomass_mixer_mk2_pack_unlock |

##### Bulk Logistics III `research_dispatch_mk3` *(Not yet unlocked)*

16× Supply Dock throughput. Bumps each Supply Dock's per-pulse emission to **16** units, an effective **400 units/h**. Pulse cadence is unchanged; only the packet size scales.

| Field | Value |
| --- | --- |
| Threshold | Biomass 130,000 |
| Tech id | dispatch_mk3_unlock |

### Plants

##### Sprinkler `research_sprinkler` *(Not yet unlocked)*

Water provider for the grid. Unlocks the **Sprinkler Kit recipe**. Fabricate the kit at a Fabricator, then deploy it in a Harvester field to water the four orthogonally adjacent cells (directly above, below, left, and right) while supplied. Upgrade packs improve the crops it supports.

| Field | Value |
| --- | --- |
| Threshold | Plants 100,000 |
| Tech id | sprinkler_unlock |

##### Dispenser `research_dispenser` *(Not yet unlocked)*

Salt provider for the grid. Unlocks the **Dispenser Kit recipe**. Fabricate the kit at a Fabricator, then deploy it in a Harvester field to salt the four orthogonally adjacent cells (directly above, below, left, and right) while supplied. Salt is a Water Pump byproduct.

| Field | Value |
| --- | --- |
| Threshold | Plants 300,000 |
| Tech id | dispenser_unlock |

##### Grow Lamp `research_grow_lamp` *(Not yet unlocked)*

Light provider for the grid. Unlocks the **Grow Lamp Kit recipe**. Fabricate the kit at a Fabricator, then deploy it in a Harvester field to light the four orthogonally adjacent cells (directly above, below, left, and right). Upgrade packs improve the crops it supports.

| Field | Value |
| --- | --- |
| Threshold | Plants 500,000 |
| Tech id | grow_lamp_unlock |

##### Field Automation `research_field_automation` *(Not yet unlocked)*

Automate harvest, planting, and treatment. Unlocks the **Crop Automator Kit** in the Shop. One automator can queue harvest, plant, and treatment jobs across up to 24 other cells in a centered 5 by 5 area. It executes one at a time in FIFO order by default (first in, first out, so the oldest job runs first), while its script can reorder unfinished work.

| Field | Value |
| --- | --- |
| Threshold | Plants 620,000 |
| Tech id | field_automation_unlock |

##### Large Liquid Tank `research_reservoir_engineering` *(Not yet unlocked)*

Holds 10× what a Liquid Tank does. Unlocks the **Large Liquid Tank** in the shop. It works just like a Liquid Tank, taking whatever liquid reaches it first and holding only that until it runs dry, but it holds **1,000 t** instead of 100 t. Use it where plant, essence, or wildlife supply has to ride out a long gap.

| Field | Value |
| --- | --- |
| Threshold | Plants 900,000 |
| Tech id | reservoir_engineering_unlock |

##### Steam Condensation `research_steam_condenser` *(Not yet unlocked)*

Turn vent steam into clean water. Unlocks the **Steam Condenser** in the shop at **1,000,000 km² Plants**. It consumes up to **250 t/h Steam** and produces the same mass of clean Water, drawing **150 W** at full throttle. Use Gas Tanks to bridge dormant vent phases and decide how much steam becomes water instead of turbine power.

| Field | Value |
| --- | --- |
| Threshold | Plants 1,000,000 |
| Tech id | steam_condenser_unlock |

##### Plant Terraformer Mk II `research_plant_terraformer_mk2` *(Not yet unlocked)*

Fertilizer and Accelerant injectors. Unlocks the **Plant Terraformer Mk II Upgrade Pack recipe** at the Fabricator. A Mk I has no Fertilizer or Growth Accelerant injector, so it converts only up to the **Fields** threshold and then stops. Mk II adds both injectors, raises throughput from **400** to **2,200 Forage/h**, raises input feeder handling from **16** to **80 items per step**, and raises enabled draw from **180 W** to **900 W**. Each machine needs its own pack.

| Field | Value |
| --- | --- |
| Threshold | Plants 1,250,000 |
| Tech id | plant_terraformer_mk2_unlock |

##### Wildlife `research_wildlife` *(Not yet unlocked)*

Revive and house the first fauna. Opens the **Wildlife** tier and makes the **Habitat** and **Feed Maker** available in the Shop. A Habitat revives cataloged creatures and houses a breeding colony, while the Feed Maker crafts species feed from harvested **Forage** plus life forms gathered across the biomes. Hold each colony's feed, gas, and liquid bands and it breeds toward its ceiling. Gated on a thriving Plants field because every feed recipe uses Forage; harvested biome life forms provide the remaining ingredients.

| Field | Value |
| --- | --- |
| Threshold | Plants 2,250,000 |
| Tech id | wildlife_unlock |

##### Advanced Biopolymers `research_advanced_biopolymers` *(Not yet unlocked)*

Make structural composite. Unlocks the Fabricator recipe for **Reinforced Biopolymer**. The composite joins established oil, plant, and water production into a structural material used by large Earth orders and advanced biological chemistry.

| Field | Value |
| --- | --- |
| Threshold | Plants 4,000,000 |
| Tech id | advanced_biopolymers_unlock |

### Wildlife

##### Exotic Husbandry `research_exotic_husbandry` *(Not yet unlocked)*

Source exotic gases and liquids. Unlocks exotic deposit survey, the **Exotic Gas Cap Kit** and **Exotic Spring Tap Kit** recipes, and the **Refiner** in the Shop. Common and uncommon exotic deposits can now appear on sonar; rare deposits wait for **Deep Exotics**. Capture raw exotic gas or liquid, then refine it into the fluid a Habitat band requires. Fabricate the caps and taps at a Fabricator.

| Field | Value |
| --- | --- |
| Threshold | Wildlife 1,000 |
| Tech id | exotic_husbandry_unlock |

##### Enrichment Chemistry `research_habitat_development` *(Not yet unlocked)*

Synthesize a late biological export. Unlocks the Fabricator recipe for **Enrichment Compound** at **2,000 Wildlife**. This advanced biological material is used in late Earth exports; Habitat adaptations are purchased with Insight and do not consume it.

| Field | Value |
| --- | --- |
| Threshold | Wildlife 2,000 |
| Tech id | habitat_development_unlock |

##### Feed Maker Mk II `research_feed_maker_mk2` *(Not yet unlocked)*

Faster feed production with higher power demand. Unlocks the **Feed Maker Mk II Upgrade Pack recipe in the Fabricator** at **250,000 Wildlife**. Craft a pack, then use **Upgrade in Inventory** to apply it to one existing Feed Maker at any outpost. Mk II provides **1.5× crafting and input Auto Feeder speed** with **2× operating power**. Each machine needs its own pack and keeps its existing building slot. Ingredient quantities and feed produced per batch stay the same.

| Field | Value |
| --- | --- |
| Threshold | Wildlife 250,000 |
| Tech id | feed_maker_mk2_unlock |

##### Deep Exotics `research_deep_exotics` *(Not yet unlocked)*

Refine the rarest exotics. Unlocks sonar discovery, extraction, and refining for the **rarest** exotic gases and liquids used by late-stage Habitat requirements.

| Field | Value |
| --- | --- |
| Threshold | Wildlife 500,000 |
| Tech id | deep_exotics_unlock |

##### Habitat Engineering Mk II `research_habitat_pack_mk2` *(Not yet unlocked)*

Double an enclosure's carrying capacity. Unlocks the **Habitat Mk II Upgrade Pack recipe** at the Fabricator at **600,000 Wildlife**, after Deep Exotics. Each pack upgrades one Habitat from Mk I to Mk II, doubling its carrying capacity while increasing mature draw to **144-168 W**. Mk II affects capacity only; Insight adaptations control breeding pace and biological costs.

| Field | Value |
| --- | --- |
| Threshold | Wildlife 600,000 |
| Tech id | habitat_pack_mk2 |

*Types / Core Data*
