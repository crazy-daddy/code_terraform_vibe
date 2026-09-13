# Database: items_agriculture_and_feeds

> **Category:** Items | **Section:** Agriculture & Feeds

Goods of the Plants and Wildlife chains: `salt`, manufactured seeds, `forage`, creature feeds, and field equipment kits.

##### Salt `salt`

Mineral byproduct of water pumping. Wells produce it alongside fresh water.

##### Seed Maker Kit `seed_maker_kit`

Fabricated deployment bundle for a `seed_maker`. Deploy it from Inventory to an operational outpost, then manage the building under Biosphere, Plants.

| Field | Value |
| --- | --- |
| Produced by | Frame + Control + Panel → Seed Maker Kit |
| Deploys | Seed Maker |

##### Grow Lamp Kit `grow_lamp_kit`

Field kit for a `grow_lamp`. Carry it in Inventory and deploy it from the mobile Harvester; the deployed light provider services surrounding harvester-grid cells.

| Field | Value |
| --- | --- |
| Produced by | Frame + Panel + Glass → Grow Lamp Kit |
| Deploys | Grow Lamp |

##### Sprinkler Kit `sprinkler_kit`

Field kit for a `sprinkler`. Carry it in Inventory and deploy it from the mobile Harvester; the deployed water provider services surrounding harvester-grid cells.

| Field | Value |
| --- | --- |
| Produced by | Frame + Pipes + Valve → Sprinkler Kit |
| Deploys | Sprinkler |

##### Dispenser Kit `dispenser_kit`

Field kit for a `dispenser`. Carry it in Inventory and deploy it from the mobile Harvester; the deployed salt provider services surrounding harvester-grid cells.

| Field | Value |
| --- | --- |
| Produced by | Frame + Control + Panel → Dispenser Kit |
| Deploys | Dispenser |

##### Waste Processor Kit `garbage_disposal_kit`

Fabricated deployment bundle for a `garbage_disposal`, displayed as a Waste Processor. Deploy it from Inventory to an operational outpost. Its script can permanently destroy items, liquids, or gases, one selected stream at a time.

| Field | Value |
| --- | --- |
| Produced by | Frame + Iron + Panel → Waste Processor Kit |
| Deploys | Waste Processor |

##### Sunpetal Seed `seed_sunpetal`

Banked Sunpetal seed line from the `seed_maker`. Needs **Light**, matures after **12 h** of met conditions, and has a base yield of **10 Forage**.

##### Shadeleaf Seed `seed_shadeleaf`

Banked Shadeleaf seed line from the `seed_maker`. Needs **Shade**, matures after **12 h** of met conditions, and has a base yield of **10 Forage**.

##### Dewmoss Seed `seed_dewmoss`

Banked Dewmoss seed line from the `seed_maker`. Needs **Water**, matures after **12 h** of met conditions, and has a base yield of **10 Forage**.

##### Lonethorn Seed `seed_lonethorn`

Banked Lonethorn seed line from the `seed_maker`. Needs every orthogonally adjacent cell empty (directly above, below, left, and right), matures after **24 h** of met conditions, and has a base yield of **25 Forage**.

##### Packfern Seed `seed_packfern`

Banked Packfern seed line from the `seed_maker`. Needs at least two orthogonally adjacent Packferns (directly above, below, left, or right), matures after **24 h** of met conditions, and has a base yield of **25 Forage**.

##### Twinvine Seed `seed_twinvine`

Banked Twinvine seed line from the `seed_maker`. Needs an orthogonally adjacent Dewmoss (directly above, below, left, or right), matures after **24 h** of met conditions, and has a base yield of **25 Forage**.

##### Spitebud Seed `seed_spitebud`

Banked Spitebud seed line from the `seed_maker`. Needs no orthogonally adjacent Packfern (directly above, below, left, or right), matures after **24 h** of met conditions, and has a base yield of **25 Forage**.

##### Sunspur Seed `seed_sunspur`

Banked Sunspur seed line from the `seed_maker`. Needs **Light** and every orthogonally adjacent cell empty (directly above, below, left, and right), matures after **24 h** of met conditions, and has a base yield of **25 Forage**.

##### Glowvine Seed `seed_glowvine`

Banked Glowvine seed line from the `seed_maker`. Needs **Light** and **Water**, matures after **48 h** of met conditions, and has a base yield of **60 Forage**.

##### Crowncap Seed `seed_crowncap`

Banked Crowncap seed line from the `seed_maker`. Needs **Shade** and at least two orthogonally adjacent Crowncaps (directly above, below, left, or right), matures after **48 h** of met conditions, and has a base yield of **60 Forage**.

##### Pondmoss Seed `seed_pondmoss`

Banked Pondmoss seed line from the `seed_maker`. Needs **Water** and at least two orthogonally adjacent Pondmoss plants (directly above, below, left, or right), matures after **48 h** of met conditions, and has a base yield of **60 Forage**.

##### Saltbloom Seed `seed_saltbloom`

Banked Saltbloom seed line from the `seed_maker`. Needs **Salt**, matures after **72 h** of met conditions, and has a base yield of **120 Forage**.

##### Brinethorn Seed `seed_brinethorn`

Banked Brinethorn seed line from the `seed_maker`. Needs **Salt** and every orthogonally adjacent cell empty (directly above, below, left, and right), matures after **72 h** of met conditions, and has a base yield of **120 Forage**.

##### Saltmate Seed `seed_saltmate`

Banked Saltmate seed line from the `seed_maker`. Needs **Salt** and an orthogonally adjacent Saltbloom (directly above, below, left, or right), matures after **72 h** of met conditions, and has a base yield of **120 Forage**.

##### Grandbloom Seed `seed_grandbloom`

Banked Grandbloom seed line from the `seed_maker`. Needs **Light**, **Water**, and every orthogonally adjacent cell empty (directly above, below, left, and right), matures after **72 h** of met conditions, and has a base yield of **150 Forage**.

##### Plant Forage `forage`

Physical crop yield collected when a ready plant is harvested and removed. The calorie base of every creature feed and the bulk input for Plant Terraformer batches.

| Field | Value |
| --- | --- |
| Used in | Plastic + Forage + Water → Reinforced Biopolymer, Biopolymer + Forage + Water → Enrichment Compound, Forage + Sea Algae + Snow Moss → Salt Tortoise Feed, Forage + Lava Algae + Cave Moss → Magmatic Annelid Feed, Forage + Cave/Frost/Coral Fungus → Mycelial Husk Feed, Forage + Magma Crust + Stone Mat → Mantle Strider Feed, Forage + Heat Lichen + Frost Lichen → Glasswing Mantis Feed, Forage + Cold Spores + Hot Spores → Veil Mantle Feed, Forage + Stone Lichen + Salt Crust → Vault Crab Feed, Forage + Brine Plankton + Deep Algae + Tide Moss → Tidal Cephalopod Feed, Forage + Ice Crust + Ash Spores → Bone Walker Feed, Forage + Vent Algae + Steam Moss + Sea Algae → Vent Drifter Feed, Forage + Hot Spores + Crystal Spores → Hive Sentinel Feed, Forage + Cave Moss + Heat Crust → Hollow Choir Feed, Forage + Shore Lichen + Crystal Spores + Vent Fungus → Ferric Sea-Lily Feed, Forage + Stone Mat + Cinder Lichen → Crustal Echo Feed, Forage + Ice Algae + Frost Lichen + Vent Algae + Black Fungus → Glacial Wyrm Feed, and Forage + Sulfur Moss + Cinder Lichen + Cold Spores + Stone Lichen → Spire Drake Feed |

##### Salt Tortoise Feed `feed_salt_tortoise`

Feed pressed for the Salt Tortoise, a coastal species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Sea Algae + Snow Moss → Salt Tortoise Feed |

##### Magmatic Annelid Feed `feed_magmatic_annelid`

Feed pressed for the Magmatic Annelid, a volcanic species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Lava Algae + Cave Moss → Magmatic Annelid Feed |

##### Mycelial Husk Feed `feed_mycelial_husk`

Feed pressed for the Mycelial Husk, a deep-cavern species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Cave/Frost/Coral Fungus → Mycelial Husk Feed |

##### Mantle Strider Feed `feed_mantle_strider`

Feed pressed for the Mantle Strider, a volcanic species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Magma Crust + Stone Mat → Mantle Strider Feed |

##### Glasswing Mantis Feed `feed_glasswing_mantis`

Feed pressed for the Glasswing Mantis, a geothermal species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Heat Lichen + Frost Lichen → Glasswing Mantis Feed |

##### Veil Mantle Feed `feed_veil_mantle`

Feed pressed for the Veil Mantle, a frozen-plains species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Cold Spores + Hot Spores → Veil Mantle Feed |

##### Vault Crab Feed `feed_vault_crab`

Feed pressed for the Vault Crab, a deep-cavern species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Stone Lichen + Salt Crust → Vault Crab Feed |

##### Tidal Cephalopod Feed `feed_tidal_cephalopod`

Feed pressed for the Tidal Cephalopod, a coastal species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Brine Plankton + Deep Algae + Tide Moss → Tidal Cephalopod Feed |

##### Bone Walker Feed `feed_bone_walker`

Feed pressed for the Bone Walker, a frozen-plains species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Ice Crust + Ash Spores → Bone Walker Feed |

##### Vent Drifter Feed `feed_vent_drifter`

Feed pressed for the Vent Drifter, a geothermal species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Vent Algae + Steam Moss + Sea Algae → Vent Drifter Feed |

##### Hive Sentinel Feed `feed_hive_sentinel`

Feed pressed for the Hive Sentinel, a geothermal species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Hot Spores + Crystal Spores → Hive Sentinel Feed |

##### Hollow Choir Feed `feed_hollow_choir`

Feed pressed for the Hollow Choir, a deep-cavern species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Cave Moss + Heat Crust → Hollow Choir Feed |

##### Ferric Sea-Lily Feed `feed_ferric_sea_lily`

Feed pressed for the Ferric Sea Lily, a coastal species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Shore Lichen + Crystal Spores + Vent Fungus → Ferric Sea-Lily Feed |

##### Crustal Echo Feed `feed_crustal_echo`

Feed pressed for the Crustal Echo, a deep-cavern species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Stone Mat + Cinder Lichen → Crustal Echo Feed |

##### Glacial Wyrm Feed `feed_glacial_wyrm`

Feed pressed for the Glacial Wyrm, a frozen-plains species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Ice Algae + Frost Lichen + Vent Algae + Black Fungus → Glacial Wyrm Feed |

##### Spire Drake Feed `feed_spire_drake`

Feed pressed for the Spire Drake, a volcanic species. A Habitat colony accepts only its own formulation.

| Field | Value |
| --- | --- |
| Produced by | Forage + Sulfur Moss + Cinder Lichen + Cold Spores + Stone Lichen → Spire Drake Feed |

*Database / Items*
