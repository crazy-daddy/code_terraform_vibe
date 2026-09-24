# Data Types: Terraforming

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`AnalyzeInfo`](#analyzeinfo) (TERRAFORMING)
- [`BioCasterRecipe`](#biocasterrecipe) (TERRAFORMING)
- [`BioOrder`](#bioorder) (TERRAFORMING)
- [`ChamberFragment`](#chamberfragment) (TERRAFORMING)
- [`ChamberSample`](#chambersample) (TERRAFORMING)
- [`FragmentLocation`](#fragmentlocation) (TERRAFORMING)
- [`HabitatBonusNode`](#habitatbonusnode) (TERRAFORMING)
- [`HabitatBonusTree`](#habitatbonustree) (TERRAFORMING)
- [`HabitatInsight`](#habitatinsight) (TERRAFORMING)
- [`Specimen`](#specimen) (TERRAFORMING)
- [`WasteDumpResult`](#wastedumpresult) (TERRAFORMING)

---

## AnalyzeInfo

**Returned by:** bio_lab.analyze().info after status == "ok"

### Properties

##### `.fragment_id: str`

Discovered fragment id (e.g. `"gw_cranial_plate"`). Use as the inventory key for the resulting sample: Bio Orders ask for fragments by this id.

- **Returns** `str`
- **Possible values** `"gw_cranial_plate"`, `"gw_caudal_fin"`, `"gw_cardiac_node"`, `"gw_jaw_fang"`, `"gw_spinal_vertebra"`, `"vc_dorsal_carapace"`, `"vc_mandible_claw"`, `"vc_antenna_cluster"`, `"vc_walking_leg"`, `"vc_eye_stalk"`, `"oc_cranium"`, `"oc_tentacle_arm"`, `"oc_chitin_beak"`, `"oc_ink_sac"`, `"oc_lens_eye"`, `"bw_skull"`, `"bw_foreclaw"`, `"bw_ribcage"`, `"bw_hindlimb"`, `"bw_tail_spike"`, `"vd_bell"`, `"vd_nematocyst"`, `"vd_neural_mesh"`, `"vd_photophore"`, `"vd_tendril"`, `"mh_fruiting_body"`, `"mh_spore_pod"`, `"mh_mycelium_root"`, `"mh_chitin_node"`, `"mh_stigmatic_disc"`, `"hs_mandible"`, `"hs_wing_membrane"`, `"hs_thorax_plate"`, `"hs_abdomen_segment"`, `"hs_compound_eye"`, `"ms_chelicera"`, `"ms_leg_tarsus"`, `"ms_pedipalp"`, `"ms_abdomen_sclerite"`, `"ms_eye_cluster"`, `"hc_aperture_lip"`, `"hc_shell_whorl"`, `"hc_septum_plate"`, `"hc_beak"`, `"hc_tentacle_crown"`, `"ma_cranial_papilla"`, `"ma_cuticle_molt"`, `"ma_ganglion_node"`, `"ma_chitinous_seta"`, `"ma_luminous_ring"`, `"gm_compound_eye"`, `"gm_folded_wing"`, `"gm_raptorial_claw"`, `"gm_abdominal_sheath"`, `"gm_antennal_whip"`, `"fs_calyx_plate"`, `"fs_arm_segment"`, `"fs_stalk_columnal"`, `"fs_oral_tegmen"`, `"fs_holdfast_rootlet"`, `"sd_cranial_crest"`, `"sd_wing_membrane"`, `"sd_obsidian_scale"`, `"sd_tail_barb"`, `"sd_talon"`, `"ce_stalked_eye"`, `"ce_swimmeret_lobe"`, `"ce_mouth_disc"`, `"ce_great_appendage"`, `"ce_cephalic_photophore"`, `"st_scute_plate"`, `"st_plastron_shard"`, `"st_limb_claw"`, `"st_beak"`, `"st_carapace_neural"`, `"vm_cephalic_horn"`, `"vm_wing_sheet"`, `"vm_gill_filament"`, `"vm_tail_barb"`, `"vm_ventral_photophore"`

##### `.name: str`

Display name of the analyzed fragment.

- **Returns** `str`

##### `.rarity: str`

Rarity tier: `"common" | "uncommon" | "rare" | "legendary"`.

- **Returns** `str`
- **Possible values** `"common"`, `"uncommon"`, `"rare"`, `"legendary"`

##### `.required_recipe: dict[str, int]`

Required reagents to extract a sample: dict `{reagent_id: qty}`. Iterate `.items()` and call `lab.load(rid, qty)` for each pair, then `lab.extract()`.

- **Returns** `dict[str, int]`

##### `.coords: list[float]`

World coordinates `[x, y]` the specimen was collected from.

- **Returns** `list[float]`

##### `.distance: float`

Straight-line distance in meters from this outpost (set at collect time).

- **Returns** `float`

*Types / Terraforming*

## BioCasterRecipe

**Returned by:** bio_caster.list_recipes() / bio_caster.find_recipe(fragment_id)

### Properties

##### `.fragment_id: str`

Volcanic fragment id this recipe forges. In the Caster's own script, pass it to `self.set_recipe(recipe.fragment_id)` when that fragment is ready to process.

- **Returns** `str`
- **Possible values** `"gw_jaw_fang"`, `"vc_walking_leg"`, `"oc_ink_sac"`, `"bw_hindlimb"`, `"vd_photophore"`, `"mh_chitin_node"`, `"hs_abdomen_segment"`, `"ms_abdomen_sclerite"`, `"hc_beak"`, `"ma_chitinous_seta"`, `"gm_abdominal_sheath"`, `"fs_oral_tegmen"`, `"sd_tail_barb"`, `"ce_great_appendage"`, `"st_beak"`, `"vm_tail_barb"`

##### `.tier: int`

Derived production tier of this forge recipe.

- **Returns** `int`

##### `.materials: dict[str, int]`

Exact fabricated-material shopping list as `{item_id: count}`. A supply script can iterate `.items()` without selecting the recipe or possessing its fragment.

- **Returns** `dict[str, int]`

##### `.temperature_range: list[float]`

Inclusive target temperature range `[low, high]` in °C for this recipe.

- **Returns** `list[float]`

*Types / Terraforming*

## BioOrder

**Returned by:** bio_exchange.orders() / bio_exchange.active_order() / get_component("bio_exchange_1").orders()

### Properties

##### `.id: str`

Stable Bio Order id (e.g. `"bio_order_03"`). Pass to `bio_exchange.set_order(id)` to make this the active Bio Order.

- **Returns** `str`

##### `.name: str`

Display name of the Bio Order (e.g. `"Cryophyte Spore Panel"`).

- **Returns** `str`

##### `.biome: str`

Biome the required fragments belong to (e.g. `"frozen"`). Orders for biomes you have no outpost in can't be filled yet.

- **Returns** `str`
- **Possible values** `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`

##### `.requires: dict[str, int]`

The fragment shopping list: dict `{fragment_id: count}`. Iterate `.items()` to see what to deliver and how many of each.

- **Returns** `dict[str, int]`

##### `.reward: int`

Credits paid when every requirement is met. Paid once: orders are one-time.

- **Returns** `int`

##### `.status: str`

Status relative to this Bio Exchange: `"available"` (not currently selected here), `"active"` (selected here), or `"complete"` (completed globally). Global completion takes priority over selection; an available order may already have delivery progress.

- **Returns** `str`
- **Possible values** `"available"`, `"active"`, `"complete"`

##### `.delivered: dict[str, int]`

Per-fragment delivery progress: dict `{fragment_id: count}`, shared across every Bio Exchange serving this order. Compare against `.requires` to see what's left to deliver.

- **Returns** `dict[str, int]`

##### `.in_transit: dict[str, int]`

Samples committed to delivery as `{fragment_id: count}`, shared across every Exchange serving this order. Includes qualifying samples already staged in an Exchange input and timed deliveries underway. A sample stays counted while `deliver()` moves it into delivery, then leaves after completion or when staged for refund in `self.output`. Query the order again for current values. `.percent` counts completed deliveries only.

- **Returns** `dict[str, int]`

##### `.percent: float`

Overall completion: **0-100**, samples delivered divided by total required across every fragment.

- **Returns** `float`

##### `.target_glow: list[int] | None`

Coastal infusion orders only: the exact glow `[r,g,b]` (0-255) the required fragment must be infused to via the Bio Luminizer. `None` for non-coastal orders. `deliver()` only matches a Luminous fragment whose glow equals this.

- **Returns** `list[int] | None`

##### `.required_genes: dict[str, list[str]] | None`

Required gene sets for geothermal orders as `{fragment_id: [attribute_id, ...]}`, or `None` for other orders. Each fragment must carry exactly its listed **1-3** genes. Engineer it with the DNA Sequencer; raw fragments and fragments with extra genes are not accepted.

- **Returns** `dict[str, list[str]] | None`

*Types / Terraforming*

## ChamberFragment

**Returned by:** dna_sequencer.chamber

### Properties

##### `.fragment_id: str`

The geothermal fragment id loaded in the chamber (e.g. `"gw_cardiac_node"`).

- **Returns** `str`
- **Possible values** `"gw_cardiac_node"`, `"vc_antenna_cluster"`, `"oc_chitin_beak"`, `"bw_ribcage"`, `"vd_neural_mesh"`, `"mh_mycelium_root"`, `"hs_thorax_plate"`, `"ms_pedipalp"`, `"hc_septum_plate"`, `"ma_ganglion_node"`, `"gm_raptorial_claw"`, `"fs_stalk_columnal"`, `"sd_obsidian_scale"`, `"ce_mouth_disc"`, `"st_limb_claw"`, `"vm_gill_filament"`

##### `.name: str`

Player-facing name of the geothermal fragment loaded in the chamber.

- **Returns** `str`

##### `.genes: list[str]`

The genes the chambered fragment currently carries (e.g. `["cold_tolerance", "pressure_tolerance"]`). Same as calling `genes()`.

- **Returns** `list[str]`

##### `.spliced: bool`

`True` after this fragment has used its one safe splice. Calling `splice()` again destroys it. `False` means the fragment can still be engineered once.

- **Returns** `bool`

*Types / Terraforming*

## ChamberSample

**Returned by:** bio_luminizer.chamber

### Properties

##### `.fragment_id: str`

The coastal fragment id loaded in the chamber (e.g. `"gw_caudal_fin"`).

- **Returns** `str`
- **Possible values** `"gw_caudal_fin"`, `"vc_mandible_claw"`, `"oc_tentacle_arm"`, `"bw_foreclaw"`, `"vd_nematocyst"`, `"mh_spore_pod"`, `"hs_wing_membrane"`, `"ms_leg_tarsus"`, `"hc_shell_whorl"`, `"ma_cuticle_molt"`, `"gm_folded_wing"`, `"fs_arm_segment"`, `"sd_wing_membrane"`, `"ce_swimmeret_lobe"`, `"st_plastron_shard"`, `"vm_wing_sheet"`

##### `.name: str`

Player-facing name of the coastal fragment loaded in the chamber.

- **Returns** `str`

##### `.glow: list[int]`

The sample's current glow `[r,g,b]` (0-255): the dim start color before tuning. Read it, the order's `target_glow`, and `lamp_signature(...)` to solve the lamp settings.

- **Returns** `list[int]`

*Types / Terraforming*

## FragmentLocation

**Returned by:** bio_collector.scan()

### Properties

##### `.coords: list[float]`

World coordinates `[x, y]` of this fragment. Pass to `bio_collector.collect(coords)` to retrieve.

- **Returns** `list[float]`

##### `.distance: float`

Straight-line distance in meters from this outpost. Sorted ascending in the scan result: `result[0]` is the nearest.

- **Returns** `float`

##### `.cataloged: bool`

`True` if this fragment has already been analyzed and added to the Journal; `False` for still-unknown dots. Gates the optional `.fragment_id`, `.name`, and `.rarity` fields.

- **Returns** `bool`

##### `.fragment_id: str | None`

Known fragment id once `.cataloged` is `True`; `None` for still-unknown dots. Matches the keys in `BioOrder.requires`.

- **Returns** `str | None`
- **Possible values** `"gw_cranial_plate"`, `"gw_caudal_fin"`, `"gw_cardiac_node"`, `"gw_jaw_fang"`, `"gw_spinal_vertebra"`, `"vc_dorsal_carapace"`, `"vc_mandible_claw"`, `"vc_antenna_cluster"`, `"vc_walking_leg"`, `"vc_eye_stalk"`, `"oc_cranium"`, `"oc_tentacle_arm"`, `"oc_chitin_beak"`, `"oc_ink_sac"`, `"oc_lens_eye"`, `"bw_skull"`, `"bw_foreclaw"`, `"bw_ribcage"`, `"bw_hindlimb"`, `"bw_tail_spike"`, `"vd_bell"`, `"vd_nematocyst"`, `"vd_neural_mesh"`, `"vd_photophore"`, `"vd_tendril"`, `"mh_fruiting_body"`, `"mh_spore_pod"`, `"mh_mycelium_root"`, `"mh_chitin_node"`, `"mh_stigmatic_disc"`, `"hs_mandible"`, `"hs_wing_membrane"`, `"hs_thorax_plate"`, `"hs_abdomen_segment"`, `"hs_compound_eye"`, `"ms_chelicera"`, `"ms_leg_tarsus"`, `"ms_pedipalp"`, `"ms_abdomen_sclerite"`, `"ms_eye_cluster"`, `"hc_aperture_lip"`, `"hc_shell_whorl"`, `"hc_septum_plate"`, `"hc_beak"`, `"hc_tentacle_crown"`, `"ma_cranial_papilla"`, `"ma_cuticle_molt"`, `"ma_ganglion_node"`, `"ma_chitinous_seta"`, `"ma_luminous_ring"`, `"gm_compound_eye"`, `"gm_folded_wing"`, `"gm_raptorial_claw"`, `"gm_abdominal_sheath"`, `"gm_antennal_whip"`, `"fs_calyx_plate"`, `"fs_arm_segment"`, `"fs_stalk_columnal"`, `"fs_oral_tegmen"`, `"fs_holdfast_rootlet"`, `"sd_cranial_crest"`, `"sd_wing_membrane"`, `"sd_obsidian_scale"`, `"sd_tail_barb"`, `"sd_talon"`, `"ce_stalked_eye"`, `"ce_swimmeret_lobe"`, `"ce_mouth_disc"`, `"ce_great_appendage"`, `"ce_cephalic_photophore"`, `"st_scute_plate"`, `"st_plastron_shard"`, `"st_limb_claw"`, `"st_beak"`, `"st_carapace_neural"`, `"vm_cephalic_horn"`, `"vm_wing_sheet"`, `"vm_gill_filament"`, `"vm_tail_barb"`, `"vm_ventral_photophore"`

##### `.name: str | None`

Player-facing fragment name once `.cataloged` is `True`; `None` for still-unknown dots. Use for readable logs and UI-facing decisions while retaining `.fragment_id` as the stable automation key.

- **Returns** `str | None`

##### `.rarity: str | None`

Rarity tier once `.cataloged` is `True`; `None` for still-unknown dots. Scan results never expose recipe or creature identity.

- **Returns** `str | None`
- **Possible values** `"common"`, `"uncommon"`, `"rare"`, `"legendary"`

*Types / Terraforming*

## HabitatBonusNode

**Returned by:** Habitat.get_bonus_tree().nodes and Habitat.get_active_bonuses()

### Properties

##### `.id: str`

Stable node id accepted by `unlock_bonus(...)`.

- **Returns** `str`

##### `.source_species: str`

Creature id whose tree owns this node. Global breakthroughs are still earned from one source species.

- **Returns** `str`

##### `.slot: str`

Tree position: `"adaptation"` or `"breakthrough"`.

- **Returns** `str`
- **Possible values** `"adaptation"`, `"breakthrough"`

##### `.scope: str`

Effect scope: `"species"` affects only `source_species`; `"global"` affects every current and future Habitat colony.

- **Returns** `str`
- **Possible values** `"species"`, `"global"`

##### `.depth: int`

Tree depth **1-2**.

- **Returns** `int`

##### `.name: str`

Player-readable authored node name.

- **Returns** `str`

##### `.description: str`

Exact authored effect summary.

- **Returns** `str`

##### `.state: str`

Current purchase state.

- **Returns** `str`
- **Possible values** `"purchased"`, `"available"`, `"unaffordable"`, `"population_locked"`

##### `.purchased: bool`

Whether this node is permanently purchased.

- **Returns** `bool`

##### `.active: bool`

Whether this purchased node currently has at least one effect applying to the Habitat that returned it. Unpurchased nodes are always `False`.

- **Returns** `bool`

##### `.insight_cost: int`

Whole shared Insight cost.

- **Returns** `int`

##### `.local_population: int`

Minimum local colony population: **0** for the adaptation or **10,000** for the breakthrough.

- **Returns** `int`

##### `.unmet: list[str]`

All currently unmet requirements: at most `"population"` and `"insight"`.

- **Returns** `list[str]`

*Types / Terraforming*

## HabitatBonusTree

**Returned by:** Habitat.get_bonus_tree()

### Properties

##### `.species: str`

Creature id whose authored tree is shown, or an empty string before a target is selected.

- **Returns** `str`

##### `.shared_insight: float`

Exact shared Insight currently available for purchases, including retained fractions.

- **Returns** `float`

##### `.purchased_count: int`

Number of permanent nodes purchased from this species' tree.

- **Returns** `int`

##### `.nodes: list[HabitatBonusNode]`

The species-only adaptation and all-species breakthrough in stable order, including locked and purchased nodes.

- **Returns** `list[HabitatBonusNode]`

*Types / Terraforming*

## HabitatInsight

**Returned by:** Habitat.get_insight()

### Properties

##### `.shared: float`

Exact shared Insight currently spendable by any Habitat, including retained fractions.

- **Returns** `float`

##### `.shared_exact: float`

Alias of `shared`, retained for scripts that already read the explicitly named exact balance.

- **Returns** `float`

##### `.rate_per_hour: float`

This colony's projected Insight production per hour at current growth and supply.

- **Returns** `float`

##### `.lifetime_produced: float`

Insight this colony has produced over its lifetime, including fractions.

- **Returns** `float`

##### `.producing: bool`

Whether this colony is producing positive Insight at its current growth rate.

- **Returns** `bool`

*Types / Terraforming*

## Specimen

**Returned by:** bio_collector.cargo / bio_lab.specimen

### Properties

##### `.coords: list[float]`

World coordinates `[x, y]` the specimen was collected from. Stable across save/load.

- **Returns** `list[float]`

##### `.distance: float`

Straight-line distance in meters from the collecting outpost (set at collect time).

- **Returns** `float`

##### `.stage: str`

Workflow stage: `"collected"` before analysis, `"analyzed"` after `lab.analyze()` reveals the fragment and recipe.

- **Returns** `str`
- **Possible values** `"collected"`, `"analyzed"`

##### `.fragment_id: str | None`

Fragment id (e.g. `"gw_cranial_plate"`). Bio Collector cargo reveals it once the fragment is cataloged; Bio Lab input reveals it only after that specimen reaches `"analyzed"`, even if the fragment was already cataloged. Otherwise `None`.

- **Returns** `str | None`
- **Possible values** `"gw_cranial_plate"`, `"gw_caudal_fin"`, `"gw_cardiac_node"`, `"gw_jaw_fang"`, `"gw_spinal_vertebra"`, `"vc_dorsal_carapace"`, `"vc_mandible_claw"`, `"vc_antenna_cluster"`, `"vc_walking_leg"`, `"vc_eye_stalk"`, `"oc_cranium"`, `"oc_tentacle_arm"`, `"oc_chitin_beak"`, `"oc_ink_sac"`, `"oc_lens_eye"`, `"bw_skull"`, `"bw_foreclaw"`, `"bw_ribcage"`, `"bw_hindlimb"`, `"bw_tail_spike"`, `"vd_bell"`, `"vd_nematocyst"`, `"vd_neural_mesh"`, `"vd_photophore"`, `"vd_tendril"`, `"mh_fruiting_body"`, `"mh_spore_pod"`, `"mh_mycelium_root"`, `"mh_chitin_node"`, `"mh_stigmatic_disc"`, `"hs_mandible"`, `"hs_wing_membrane"`, `"hs_thorax_plate"`, `"hs_abdomen_segment"`, `"hs_compound_eye"`, `"ms_chelicera"`, `"ms_leg_tarsus"`, `"ms_pedipalp"`, `"ms_abdomen_sclerite"`, `"ms_eye_cluster"`, `"hc_aperture_lip"`, `"hc_shell_whorl"`, `"hc_septum_plate"`, `"hc_beak"`, `"hc_tentacle_crown"`, `"ma_cranial_papilla"`, `"ma_cuticle_molt"`, `"ma_ganglion_node"`, `"ma_chitinous_seta"`, `"ma_luminous_ring"`, `"gm_compound_eye"`, `"gm_folded_wing"`, `"gm_raptorial_claw"`, `"gm_abdominal_sheath"`, `"gm_antennal_whip"`, `"fs_calyx_plate"`, `"fs_arm_segment"`, `"fs_stalk_columnal"`, `"fs_oral_tegmen"`, `"fs_holdfast_rootlet"`, `"sd_cranial_crest"`, `"sd_wing_membrane"`, `"sd_obsidian_scale"`, `"sd_tail_barb"`, `"sd_talon"`, `"ce_stalked_eye"`, `"ce_swimmeret_lobe"`, `"ce_mouth_disc"`, `"ce_great_appendage"`, `"ce_cephalic_photophore"`, `"st_scute_plate"`, `"st_plastron_shard"`, `"st_limb_claw"`, `"st_beak"`, `"st_carapace_neural"`, `"vm_cephalic_horn"`, `"vm_wing_sheet"`, `"vm_gill_filament"`, `"vm_tail_barb"`, `"vm_ventral_photophore"`

##### `.name: str | None`

Player-facing fragment name (e.g. `"Beak"`). `None` while the fragment identity is still unknown.

- **Returns** `str | None`

##### `.rarity: str | None`

Rarity tier: `"common" | "uncommon" | "rare" | "legendary"`. `None` until analyzed.

- **Returns** `str | None`
- **Possible values** `"common"`, `"uncommon"`, `"rare"`, `"legendary"`

##### `.recipe: dict[str, int] | None`

Required reagent recipe: dict `{reagent_id: qty}`. `None` until analyzed.

- **Returns** `dict[str, int] | None`

##### `.production_tier: int | None`

Derived tier of this specimen's Bio Lab extraction recipe, or `None` while its identity and reagent recipe are unknown.

- **Returns** `int | None`

##### `.glow: list[int] | None`

Bioluminescent glow `[r,g,b]` (0-255) for **coastal** specimens: the dim start color the Bio Luminizer tunes to an order's target. `None` for every other biome.

- **Returns** `list[int] | None`

##### `.genes: list[str]`

The genes this **geothermal** specimen carries (e.g. `["heat_resistance", "acid_resistance"]`). The DNA strand itself is internal: you work at the gene level. Empty for non-geothermal specimens.

- **Returns** `list[str]`

*Types / Terraforming*

## WasteDumpResult

**Returned by:** oxygen_generator.dump_waste()

### Properties

##### `.status: str`

Always `"ok"` after the waste chamber is dumped.

- **Returns** `str`
- **Possible values** `"ok"`

##### `.message: str`

Player-readable explanation of the dump and its resulting efficiency penalty.

- **Returns** `str`

##### `.penalty: float`

Efficiency penalty applied by this dump, in the **0-1** range.

- **Returns** `float`

*Types / Weather & Sky*
