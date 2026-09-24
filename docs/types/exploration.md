# Data Types: Exploration

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`CatalogedCreature`](#catalogedcreature) (EXPLORATION)
- [`CatalogedFragment`](#catalogedfragment) (EXPLORATION)
- [`Marker`](#marker) (EXPLORATION)

---

## CatalogedCreature

**Returned by:** journal.cataloged_creatures(planet_id)

### Properties

##### `.creature_id: str`

Stable creature id accepted by `habitat.set_revival_target(creature_id)`.

- **Returns** `str`
- **Possible values** `"salt_tortoise"`, `"magmatic_annelid"`, `"mycelial_husk"`, `"mantle_strider"`, `"glasswing_mantis"`, `"veil_mantle"`, `"vault_crab"`, `"tidal_cephalopod"`, `"bone_walker"`, `"vent_drifter"`, `"hive_sentinel"`, `"hollow_choir"`, `"ferric_sea_lily"`, `"crustal_echo"`, `"glacial_wyrm"`, `"spire_drake"`

##### `.name: str`

Player-facing creature name. Use for readable output; use `.creature_id` for automation.

- **Returns** `str`

##### `.rarity: str`

Rarity tier: `"common" | "uncommon" | "rare" | "legendary"`. Rarity determines the revival reagent quantities.

- **Returns** `str`
- **Possible values** `"common"`, `"uncommon"`, `"rare"`, `"legendary"`

##### `.fragment_ids: list[str]`

The five analyzed fragment ids that completed this creature's catalog entry, in biome order.

- **Returns** `list[str]`

##### `.feed_item_id: str`

The exact feed item this creature accepts. Stage at least `.revive_feed_required` units in the Habitat before revival.

- **Returns** `str`
- **Possible values** `"feed_salt_tortoise"`, `"feed_magmatic_annelid"`, `"feed_mycelial_husk"`, `"feed_mantle_strider"`, `"feed_glasswing_mantis"`, `"feed_veil_mantle"`, `"feed_vault_crab"`, `"feed_tidal_cephalopod"`, `"feed_bone_walker"`, `"feed_vent_drifter"`, `"feed_hive_sentinel"`, `"feed_hollow_choir"`, `"feed_ferric_sea_lily"`, `"feed_crustal_echo"`, `"feed_glacial_wyrm"`, `"feed_spire_drake"`

##### `.feed_recipe_id: str`

The Feed Maker recipe id that produces `.feed_item_id`. The matching recipe must still be unlocked through Bio Orders; find its current `Recipe` in `feed_maker.list_recipes()` for ingredient quantities.

- **Returns** `str`
- **Possible values** `"craft_feed_salt_tortoise"`, `"craft_feed_magmatic_annelid"`, `"craft_feed_mycelial_husk"`, `"craft_feed_mantle_strider"`, `"craft_feed_glasswing_mantis"`, `"craft_feed_veil_mantle"`, `"craft_feed_vault_crab"`, `"craft_feed_tidal_cephalopod"`, `"craft_feed_bone_walker"`, `"craft_feed_vent_drifter"`, `"craft_feed_hive_sentinel"`, `"craft_feed_hollow_choir"`, `"craft_feed_ferric_sea_lily"`, `"craft_feed_crustal_echo"`, `"craft_feed_glacial_wyrm"`, `"craft_feed_spire_drake"`

##### `.revive_feed_required: int`

Minimum whole feed units that must be staged in the Habitat after selecting this creature and before `revive()` can start.

- **Returns** `int`

##### `.revive_reagents: dict[str, int]`

Exact revival shopping list as `{reagent_id: quantity}` for this creature's rarity. Stage every listed amount through the Habitat's `reagents` input.

- **Returns** `dict[str, int]`

*Types / Exploration*

## CatalogedFragment

**Returned by:** journal.cataloged_fragments(planet_id)

### Properties

##### `.fragment_id: str`

Stable fragment id (e.g. `"gw_cranial_plate"`). Matches the keys in `BioOrder.requires`, so this is what scripts use to plan order fulfillment.

- **Returns** `str`
- **Possible values** `"gw_cranial_plate"`, `"gw_caudal_fin"`, `"gw_cardiac_node"`, `"gw_jaw_fang"`, `"gw_spinal_vertebra"`, `"vc_dorsal_carapace"`, `"vc_mandible_claw"`, `"vc_antenna_cluster"`, `"vc_walking_leg"`, `"vc_eye_stalk"`, `"oc_cranium"`, `"oc_tentacle_arm"`, `"oc_chitin_beak"`, `"oc_ink_sac"`, `"oc_lens_eye"`, `"bw_skull"`, `"bw_foreclaw"`, `"bw_ribcage"`, `"bw_hindlimb"`, `"bw_tail_spike"`, `"vd_bell"`, `"vd_nematocyst"`, `"vd_neural_mesh"`, `"vd_photophore"`, `"vd_tendril"`, `"mh_fruiting_body"`, `"mh_spore_pod"`, `"mh_mycelium_root"`, `"mh_chitin_node"`, `"mh_stigmatic_disc"`, `"hs_mandible"`, `"hs_wing_membrane"`, `"hs_thorax_plate"`, `"hs_abdomen_segment"`, `"hs_compound_eye"`, `"ms_chelicera"`, `"ms_leg_tarsus"`, `"ms_pedipalp"`, `"ms_abdomen_sclerite"`, `"ms_eye_cluster"`, `"hc_aperture_lip"`, `"hc_shell_whorl"`, `"hc_septum_plate"`, `"hc_beak"`, `"hc_tentacle_crown"`, `"ma_cranial_papilla"`, `"ma_cuticle_molt"`, `"ma_ganglion_node"`, `"ma_chitinous_seta"`, `"ma_luminous_ring"`, `"gm_compound_eye"`, `"gm_folded_wing"`, `"gm_raptorial_claw"`, `"gm_abdominal_sheath"`, `"gm_antennal_whip"`, `"fs_calyx_plate"`, `"fs_arm_segment"`, `"fs_stalk_columnal"`, `"fs_oral_tegmen"`, `"fs_holdfast_rootlet"`, `"sd_cranial_crest"`, `"sd_wing_membrane"`, `"sd_obsidian_scale"`, `"sd_tail_barb"`, `"sd_talon"`, `"ce_stalked_eye"`, `"ce_swimmeret_lobe"`, `"ce_mouth_disc"`, `"ce_great_appendage"`, `"ce_cephalic_photophore"`, `"st_scute_plate"`, `"st_plastron_shard"`, `"st_limb_claw"`, `"st_beak"`, `"st_carapace_neural"`, `"vm_cephalic_horn"`, `"vm_wing_sheet"`, `"vm_gill_filament"`, `"vm_tail_barb"`, `"vm_ventral_photophore"`

##### `.name: str`

Player-facing fragment name (e.g. `"Beak"`). Use for readable output; use `.fragment_id` when matching `BioOrder.requires` or moving the item.

- **Returns** `str`

##### `.biome: str`

Biome where this fragment is found: `"frozen"` for Nocturna's starter biome. Filter the result list by biome to scope to a specific outpost's biome.

- **Returns** `str`
- **Possible values** `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`

##### `.coords: list[float]`

World coordinates `[x, y]` where the fragment can be collected. Pass to `bio_collector.collect(coords)` from the Bio Collector at the matching outpost.

- **Returns** `list[float]`

##### `.rarity: str`

Rarity tier: `"common" | "uncommon" | "rare" | "legendary"`. Inherited from the parent creature.

- **Returns** `str`
- **Possible values** `"common"`, `"uncommon"`, `"rare"`, `"legendary"`

*Types / Exploration*

## Marker

**Returned by:** markers.get() / markers.list()

### Properties

##### `.id: str`

Stable identity you passed to `markers.place(...)`. Pass it back to `markers.get(...)` or `markers.remove(...)`, and use its prefix to group families of markers.

- **Returns** `str`

##### `.x: float`

World X coordinate in meters. Feed it straight to `self.nav.set_target(m.x, m.y)`, a drone `self.go_to(m.x, m.y)`, or `construction_blueprint.plan_structure(kind, m.x, m.y)`.

- **Returns** `float`

##### `.y: float`

World Y coordinate in meters.

- **Returns** `float`

##### `.label: str`

Display text shown on the map and in the Markers list. Empty string means the marker was placed without one, and the map shows its id instead.

- **Returns** `str`

##### `.note: str`

Longer note shown when you hover the marker. Empty string means no note was written.

- **Returns** `str`

##### `.icon: str`

Glyph drawn inside the marker pin, such as `"x"`, `"check"`, or `"hammer"`.

- **Returns** `str`
- **Possible values** `"pin"`, `"x"`, `"check"`, `"circle"`, `"flag"`, `"crosshair"`, `"warning"`, `"hammer"`, `"resource"`, `"power"`, `"fluid"`, `"star"`

##### `.color: str`

Marker color, such as `"accent"` or `"error"`.

- **Returns** `str`
- **Possible values** `"neutral"`, `"accent"`, `"success"`, `"warning"`, `"error"`, `"violet"`

*Types / Infrastructure*
