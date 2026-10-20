# Documentation Table of Contents & Navigation

Master navigation guide to all modular documentation in `docs/`.

---

## ⚡ Quick References
- **[AI Cheatsheet](AI_CHEATSHEET.md)**: High-density quick reference hub (formulas, `lib/` map, conventions) with a section index into the topic files under [`cheatsheet/`](cheatsheet/).
- **[Design History](DESIGN_HISTORY.md)**: why behind cheatsheet sections (postmortems, rejected approaches). Hub table links per-topic files in [design_history/](design_history/); headings are `## §<id> — Title`; grep, don't read whole.
- **[Benchmark](BENCHMARK.md)**: script interpreter step costs.
- **Full DOCS Manual** (`Code-Terraform-DOCS-Manual-<build>.md`, gitignored): complete monolithic in-game export; the split files below are regenerated from it with `devtools/game_update/split_docs_manual.py`. Current build: see [README](README.md).

---

## 🛠️ 1. Components (`docs/components/` - 90 files)
- **Core Systems**: [clock](components/clock.md) | [commander](components/commander.md) | [console](components/console.md) | [gps](components/gps.md) | [nocturna](components/nocturna.md) | [research](components/research.md) | [shop](components/shop.md) | [transmitter](components/transmitter.md)
- **Sensors**: [biomass_sensor](components/biomass_sensor.md) | [oxygen_sensor](components/oxygen_sensor.md) | [plants_sensor](components/plants_sensor.md) | [pressure_sensor](components/pressure_sensor.md) | [thermometer](components/thermometer.md) | [wildlife_sensor](components/wildlife_sensor.md)
- **Exploration**: [journal](components/journal.md) | [map_markers](components/map_markers.md) | [scanner](components/scanner.md)
- **Power**: [battery](components/battery.md) | [battery_charger](components/battery_charger.md) | [lightning_rod](components/lightning_rod.md) | [oil_generator](components/oil_generator.md) | [reactor](components/reactor.md) | [solar_generator](components/solar_generator.md) | [steam_turbine](components/steam_turbine.md) | [vehicle_charging_station](components/vehicle_charging_station.md)
- **Terraforming**: [atmosphere](components/atmosphere.md) | [bio_caster](components/bio_caster.md) | [bio_collector](components/bio_collector.md) | [bio_conditioner](components/bio_conditioner.md) | [bio_exchange](components/bio_exchange.md) | [bio_lab](components/bio_lab.md) | [bio_luminizer](components/bio_luminizer.md) | [dna_sequencer](components/dna_sequencer.md) | [feed_maker](components/feed_maker.md) | [habitat](components/habitat.md) | [heat_generator](components/heat_generator.md) | [oxygen_generator](components/oxygen_generator.md) | [pressure_generator](components/pressure_generator.md) | [refiner](components/refiner.md) | [terraforming](components/terraforming.md)
- **Production & Storage**: [fabricator](components/fabricator.md) | [fuel_assembler](components/fuel_assembler.md) | [harvester](components/harvester.md) | [inventory](components/inventory.md) | [large_warehouse](components/large_warehouse.md) | [lead_cask](components/lead_cask.md) | [mining_drill](components/mining_drill.md) | [smelter](components/smelter.md) | [storage_bin](components/storage_bin.md) | [warehouse](components/warehouse.md) | [waste_processor](components/waste_processor.md)
- **Vehicles & Modules**: [constructor_module](components/constructor_module.md) | [drill_module](components/drill_module.md) | [drone](components/drone.md) | [fleet](components/fleet.md) | [nav_module](components/nav_module.md) | [pioneer](components/pioneer.md) | [rover](components/rover.md) | [sonar_module](components/sonar_module.md)
- **Logistics & Orders**: [data_archive](components/data_archive.md) | [drone_depot](components/drone_depot.md) | [drone_service_station](components/drone_service_station.md) | [earth_orders](components/earth_orders.md) | [signal_bus](components/signal_bus.md) | [supply_dock](components/supply_dock.md)
- **Infrastructure & Fluids**: [construction_blueprint](components/construction_blueprint.md) | [exotic_gas_cap](components/exotic_gas_cap.md) | [exotic_spring_tap](components/exotic_spring_tap.md) | [gas_tank](components/gas_tank.md) | [large_liquid_tank](components/large_liquid_tank.md) | [liquid_tank](components/liquid_tank.md) | [oil_pump](components/oil_pump.md) | [outpost](components/outpost.md) | [outpost_network](components/outpost_network.md) | [power_control](components/power_control.md) | [run_control](components/run_control.md) | [ship_computer](components/ship_computer.md) | [steam_condenser](components/steam_condenser.md) | [thermal_cap](components/thermal_cap.md) | [water_pump](components/water_pump.md)
- **Biosphere**: [biomass_mixer](components/biomass_mixer.md) | [crop_automator](components/crop_automator.md) | [dispenser](components/dispenser.md) | [essence_liquifier](components/essence_liquifier.md) | [grow_lamp](components/grow_lamp.md) | [plant_terraformer](components/plant_terraformer.md) | [seed_maker](components/seed_maker.md) | [sprinkler](components/sprinkler.md)
- **Storage & Inventory**: [item_catalog](components/item_catalog.md)
- **Weather & Sky**: [weather_station](components/weather_station.md)

---

## 📊 2. Database & Catalogs (`docs/database/` - 25 files)
- **Equipment**: [Atmosphere](database/equipment_atmosphere.md) | [Biology](database/equipment_biology.md) | [Biosphere](database/equipment_biosphere.md) | [Fluids](database/equipment_fluids.md) | [Logistics](database/equipment_logistics.md) | [Mining](database/equipment_mining.md) | [Modules](database/equipment_modules.md) | [Power](database/equipment_power.md) | [Production](database/equipment_production.md)
- **Items & Resources**: [Minerals](database/items_minerals.md) | [Field Resources](database/items_field_resources.md) | [Refined Materials](database/items_refined_materials.md) | [Fabricated Components](database/items_fabricated_components.md) | [Biology Samples](database/items_biology_samples.md) | [Lab Reagents](database/items_lab_reagents.md) | [Life Forms](database/items_life_forms.md) | [Agriculture & Feeds](database/items_agriculture_and_feeds.md) | [Fluids](database/fluids.md)
- **Recipes & Production**: [Smelter](database/recipes_smelter.md) | [Refiner](database/recipes_refiner.md) | [Fabricator](database/recipes_fabricator.md) | [Fuel Assembler](database/recipes_fuel_assembler.md) | [Feed Maker](database/recipes_feed_maker.md) | [Production Tiers](database/production_tiers.md) | [Research Catalog](database/research_catalog.md)

---

## 📜 3. Contracts (`docs/contracts/` - 16 files)
- [Contract Overview](contracts/contract_overview.md) | [Buried Five](contracts/buried_five.md) | [Cold Boot](contracts/cold_boot.md) | [Core Sample](contracts/core_sample.md) | [Corrupted Archive](contracts/corrupted_archive.md) | [Crosstalk](contracts/crosstalk.md) | [Data Tablet](contracts/data_tablet.md) | [Drifting Signal](contracts/drifting_signal.md) | [Lattice](contracts/lattice.md) | [Relay Hack](contracts/relay_hack.md) | [Sealed Vault](contracts/sealed_vault.md) | [Terminal Breach](contracts/terminal_breach.md) | [The Loom](contracts/the_loom.md) | [Three Echoes](contracts/three_echoes.md) | [Xenogenetics](contracts/xenogenetics.md) | [Beat the System](contracts/beat_the_system.md)

---

## 🔠 4. Data Types Reference Manual (`docs/types/` - 13 files)
- [Core Data](types/core_data.md) | [World & Sites](types/world_and_sites.md) | [Storage & Inventory](types/storage_and_inventory.md) | [Fleet & Vehicles](types/fleet_and_vehicles.md) | [Infrastructure & Fluids](types/infrastructure_and_fluids.md) | [Orders & Comms](types/orders_and_comms.md) | [System & Panels](types/system_and_panels.md) | [Contracts](types/contracts.md) | [Built-in Types](types/built_in_types.md) | [Biosphere](types/biosphere.md) | [Exploration](types/exploration.md) | [Terraforming](types/terraforming.md) | [Weather & Sky](types/weather_and_sky.md)

---

## 📖 5. Tutorials & Guides (`docs/guide/` - 49 files)
- **Start Here**: [Getting Started](guide/getting_started.md) | [First Steps](guide/first_steps.md) | [Command Results](guide/command_results.md) | [Long-Running Scripts](guide/long_running_scripts.md) | [FAQ](guide/faq.md)
- **Tutorials**: [How This Game Works](guide/how_this_game_works.md) | [Choosing Credit Path](guide/choosing_credit_path.md) | [Terraform Index](guide/terraform_index.md) | [Power & Terraforming Machines](guide/power_and_terraforming.md) | [First Biology Loop](guide/first_biology_loop.md) | [First Harvesting Route](guide/first_harvesting_route.md) | [Contracts Tutorial](guide/contracts_tutorial.md) | [Contract System Guide](guide/contract_system_guide.md) | [Errors & Console](guide/errors_and_console.md) | [First Pioneer](guide/first_pioneer.md) | [Sonar Scanning](guide/sonar_scanning.md) | [Mining: Discovery to Delivery](guide/mining_discovery_to_delivery.md) | [Plan Mode](guide/plan_mode.md) | [First Outpost](guide/first_outpost.md) | [Remote Outpost Logistics](guide/remote_outpost_logistics.md) | [Industrial Upgrades & Deep Oil](guide/industrial_upgrades_deep_oil.md) | [Nuclear Power](guide/nuclear_power.md) | [Expanding Production](guide/expanding_production.md)
- **Programming**: [Language Reference](guide/language_reference.md) | [Programming Guide](guide/programming_language_reference.md)
- **Editor & Tools**: [Editor & Tools](guide/editor_and_tools.md)
- **Automation Systems**: [Vehicle Service Areas](guide/vehicle_service_areas.md) | [Earth Orders](guide/earth_orders_guide.md) | [Signal Bus](guide/signal_bus_guide.md) | [Automations](guide/automations_guide.md) | [Data Archive](guide/data_archive_guide.md) | [Map Markers](guide/map_markers_guide.md) | [Drone Operations](guide/drone_operations_guide.md)
- **Production & Logistics**: [Batteries & Charging](guide/batteries_and_charging.md) | [Refinement & Storage](guide/refinement_and_storage.md) | [Input & Output Ports](guide/input_and_output_ports.md)
- **World & Infrastructure**: [Biomass Tier](guide/biosphere_biomass_tier.md) | [Plants Tier](guide/biosphere_plants_tier.md) | [Plant Terraformer](guide/plant_terraformer_guide.md) | [Wildlife Overview](guide/wildlife_overview.md) | [Wildlife Supply Fluids](guide/wildlife_supply_fluids.md) | [Wildlife Husbandry](guide/wildlife_husbandry.md) | [Wildlife Progression](guide/wildlife_progression.md) | [Weather System](guide/weather_system.md) | [Flow Networks & Fluids](guide/flow_networks_fluids.md) | [Infrastructure & Pipes](guide/infrastructure_and_pipes.md) | [Power Networks](guide/power_networks.md)
- **Reference**: [Components Overview](guide/components_overview.md)
- **Commands & Built-ins**: [Built-in Functions & Commands](guide/builtins_and_commands.md)

---

## 🧩 6. Data Models & Type Signatures (`docs/models/` - 10 files)
- [Results](models/results.md) | [Biology Models](models/biology_models.md) | [Storage & Items](models/storage_and_items.md) | [Earth Orders](models/earth_orders_models.md) | [Contracts Models](models/contracts_models.md) | [Vehicles & Modules](models/vehicles_and_modules.md) | [Outposts & Power](models/outposts_and_power.md) | [Terraforming & Weather](models/terraforming_and_weather.md) | [Python Builtins](models/python_builtins.md) | [Misc Models](models/misc_models.md)

---

## 🧭 7. Our Notes (not game docs)
- **Cheatsheet topics** (`docs/cheatsheet/`): index in [AI_CHEATSHEET.md](AI_CHEATSHEET.md); grep the `§<id>` heading, read that range only.
- **Game knowledge** (`docs/gameknowledge/`, measured or decompiled mechanics): [biomes](gameknowledge/biomes.md) | [exotics](gameknowledge/exotics.md) | [fluids](gameknowledge/fluids.md) | [pioneer_instantcharge](gameknowledge/pioneer_instantcharge.md) | [solar](gameknowledge/solar.md) | [survey_contacts](gameknowledge/survey_contacts.md) | [unlock_paths](gameknowledge/unlock_paths.md)
- **Walkthroughs** (`docs/autoplay/`): [auto_walkthrough](autoplay/auto_walkthrough.md) | [early_optimization](autoplay/early_optimization.md) | [manual_walkthrough](autoplay/manual_walkthrough.md) | [problem_timeline](autoplay/problem_timeline.md)
- **Headless simulator** (`docs/headless/`): [README](headless/README.md) | [ab_results](headless/ab_results.md) | [anchors](headless/anchors.md) | [scenarios](headless/scenarios.md) | [standins](headless/standins.md)
- **Plans** (`docs/plans/`): work plans linked from `TODO.md`; finished ones in `plans/done/`.
