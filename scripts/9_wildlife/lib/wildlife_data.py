# Wildlife game constants (docs/cheatsheet/wildlife.md §1l), read from the
# decompiled simworker. They are the same on every world; they are not our
# tunables. Live reads stay authoritative where the game exposes them
# (journal.cataloged_creatures() rarity/feed/reagents, Habitat bands and
# requirements, get_bonus_tree()). This table drives projections: the offline
# optimizer (devtools/wildlife_optimizer.py) and the growth estimates of
# lib/wildlife_model.py.

# Breeding rate multiplier by rarity (simworker `Iq`).
RARITY_BREEDING = {"common": 1.0, "uncommon": 0.75, "rare": 0.5, "legendary": 0.3}

# Revival reagents: quantity of EACH of the five Shop lab reagents (`yk`, `vk`).
RARITY_REAGENTS = {"common": 1, "uncommon": 2, "rare": 3, "legendary": 5}
REVIVAL_REAGENT_IDS = ("alkaline_buffer", "cryo_solvent", "protein_marker", "chelating_agent", "enzyme_solution")
REVIVE_FEED_REQUIRED = 2

# Population that opens stage 1..4 (`Oq`), and base capacity per stage (`dE`).
STAGE_THRESHOLDS = (250, 2500, 25000, 175001)
STAGE_CAPACITY = (500, 5000, 50000, 175000, 175000)
STAGE_NAMES = ("founded", "first_breeding", "self_sustaining", "thriving", "abundant")

FOUNDING_POPULATION = 4
REARING_HOURS = 12.0

# Natural growth: rate = BREED_BASE * F(pop) * ...; F(p) = p up to 10,
# 10 * (p/10)^GROWTH_EXPONENT up to GROWTH_SATURATION_POP, then saturates so
# the rate tops out at NATURAL_RATE_CEILING/h (x (1 + rate-ceiling bonus)).
BREED_BASE = 0.0144
GROWTH_EXPONENT = 0.85
GROWTH_SATURATION_POP = 5000
NATURAL_RATE_CEILING = 150.0

# Full-support momentum reaches 1 after this many hours (decays twice as fast).
MOMENTUM_RAMP_HOURS = 24.0

# Consumption per new individual (before trait reductions), buffer bleed.
FEED_PER_BIRTH = 0.1
GAS_PER_BIRTH_T = 0.0008
LIQUID_PER_BIRTH_T = 0.0008
BUFFER_BLEED_T_PER_H = 0.5

# Bands: centre and half-width by tightness 0..4 (`Lq`).
BAND_CENTRE_T = 450.0
BAND_HALF_WIDTH_T = (200.0, 150.0, 100.0, 60.0, 40.0)

# Cumulative Insight earned by a colony along its population (`SG`), linear between.
INSIGHT_CURVE = ((4, 0.0), (10, 1.0), (100, 1.5), (1000, 2.25), (10000, 3.0), (50000, 4.0), (175000, 5.5), (350000, 7.0))

ADAPTATION_COST = 1
BREAKTHROUGH_COST = 4
BREAKTHROUGH_POPULATION = 10000

# Global caps on stacked bonuses (`xG`). feed_multiplier_floor = 1 - 0.75.
BONUS_CAPS = {"speed": 1.5, "brood": 0.35, "momentum": 0.3, "rate_ceiling": 0.5, "band_tolerance": 0.5, "feed_multiplier_floor": 0.25}

# Wildlife-total research gates (simworker research table).
EXOTIC_HUSBANDRY_WILDLIFE = 1000
FEED_MAKER_MK2_WILDLIFE = 250000
DEEP_EXOTICS_WILDLIFE = 500000
HABITAT_MK2_WILDLIFE = 600000
HABITAT_MK2_CAPACITY_FACTOR = 2

# Feed Maker recipe: 100 Forage + 1 of each life form -> 20 feed in ~0.3 h
# (0.34 h for three-form recipes); Mk II crafts 1.5x faster.
FEED_PER_CRAFT = 20
FORAGE_PER_CRAFT = 100
FEED_CRAFT_HOURS = 0.3
FEED_MAKER_MK2_SPEED = 1.5
# Auto Feeder (simworker `ioTransport`): 0.01 game h per unit moved, x0.5 with
# Fast Feeders, / Mk II speed. Input and output share one feeder endpoint, so
# per craft it is busy for Forage + forms + feed out (~0.62 h Mk I with Fast
# Feeders), longer than the craft: Feed Maker output is feeder-bound.
FEEDER_HOURS_PER_UNIT = 0.01
FAST_FEEDERS_MULTIPLIER = 0.5
FORMS_PER_CRAFT = 3


def feed_cycle_hours(speed=1.0, fast_feeders=True):
    """Game hours per craft for one Feed Maker: the longer of craft and feeder time."""
    units = FORAGE_PER_CRAFT + FORMS_PER_CRAFT + FEED_PER_CRAFT
    feeder = units * FEEDER_HOURS_PER_UNIT * (FAST_FEEDERS_MULTIPLIER if fast_feeders else 1.0)
    return max(FEED_CRAFT_HOURS, feeder) / speed

# Species: rarity plus gas/liquid base -> apex (`bk`); None = never required.
SPECIES = {
    "salt_tortoise": {"rarity": "common", "gas": ("swamp_gas", "swamp_gas"), "liquid": None},
    "magmatic_annelid": {"rarity": "common", "gas": ("ammonia", "ammonia"), "liquid": None},
    "mycelial_husk": {"rarity": "uncommon", "gas": ("swamp_gas", "swamp_gas"), "liquid": ("brine", "brine")},
    "mantle_strider": {"rarity": "uncommon", "gas": ("ammonia", "ammonia"), "liquid": ("brine", "brine")},
    "glasswing_mantis": {"rarity": "uncommon", "gas": ("swamp_gas", "swamp_gas"), "liquid": ("brine", "brine")},
    "veil_mantle": {"rarity": "uncommon", "gas": ("ammonia", "ammonia"), "liquid": ("brine", "brine")},
    "vault_crab": {"rarity": "rare", "gas": ("ammonia", "sulfur_gas"), "liquid": ("brine", "cryofluid")},
    "tidal_cephalopod": {"rarity": "rare", "gas": ("swamp_gas", "sulfur_gas"), "liquid": ("brine", "cryofluid")},
    "bone_walker": {"rarity": "rare", "gas": ("ammonia", "sulfur_gas"), "liquid": ("brine", "cryofluid")},
    "vent_drifter": {"rarity": "rare", "gas": ("swamp_gas", "sulfur_gas"), "liquid": ("brine", "cryofluid")},
    "hive_sentinel": {"rarity": "rare", "gas": ("ammonia", "sulfur_gas"), "liquid": ("brine", "cryofluid")},
    "hollow_choir": {"rarity": "rare", "gas": ("swamp_gas", "sulfur_gas"), "liquid": ("brine", "cryofluid")},
    "ferric_sea_lily": {"rarity": "rare", "gas": ("ammonia", "sulfur_gas"), "liquid": ("brine", "cryofluid")},
    "crustal_echo": {"rarity": "rare", "gas": ("swamp_gas", "sulfur_gas"), "liquid": ("brine", "cryofluid")},
    "glacial_wyrm": {"rarity": "legendary", "gas": ("sulfur_gas", "chlorine"), "liquid": ("cryofluid", "quicksilver")},
    "spire_drake": {"rarity": "legendary", "gas": ("sulfur_gas", "chlorine"), "liquid": ("cryofluid", "quicksilver")},
}

# Fluid tiers: common is tapped directly; refined needs the Refiner + tar
# (Exotic Husbandry); deep needs Deep Exotics.
FLUID_TIER = {
    "swamp_gas": "common", "ammonia": "common", "brine": "common",
    "sulfur_gas": "refined", "cryofluid": "refined",
    "chlorine": "deep", "quicksilver": "deep",
}


def _effect(kind, amount, condition=None, threshold=None, cap=None, per_other=False, resources=()):
    return {"kind": kind, "amount": amount, "condition": condition, "threshold": threshold, "cap": cap, "per_other": per_other, "resources": resources}


def _speed(amount, condition=None, threshold=None, cap=None, per_other=False):
    return _effect("speed", amount, condition, threshold, cap, per_other)


# Bonus trees (`MG`): {species: {"adaptation": (node_id, effects), "breakthrough": (node_id, effects)}}.
# Effect kinds: speed (multiplicative), stage_speed (amount x stage, capped),
# brood, momentum, rate_ceiling (additive), feed (demand reduction),
# founding (+individuals at establishment), band (tolerance), retain (base fluid).
BONUS_TREES = {
    "salt_tortoise": {
        "adaptation": ("saltwise_digestion", (_effect("feed", 0.6),)),
        "breakthrough": ("ancient_nest", (_speed(0.15, "population_below", 2500),)),
    },
    "magmatic_annelid": {
        "adaptation": ("efficient_gut", (_effect("brood", 0.15),)),
        "breakthrough": ("chain_fission", (_effect("brood", 0.05),)),
    },
    "mycelial_husk": {
        "adaptation": ("symbiotic_digestion", (_effect("feed", 0.4), _effect("band", 0.25, resources=("gas", "liquid")))),
        "breakthrough": ("planetary_mycelium", (_speed(0.01, "other_established", cap=0.12, per_other=True),)),
    },
    "mantle_strider": {
        "adaptation": ("lean_grazer", (_speed(0.35, "population_below", 2500),)),
        "breakthrough": ("continental_stride", (_effect("rate_ceiling", 0.1),)),
    },
    "glasswing_mantis": {
        "adaptation": ("prismatic_tolerance", (_effect("band", 0.4, resources=("gas", "liquid")),)),
        "breakthrough": ("perfect_stillness", (_effect("momentum", 0.08),)),
    },
    "veil_mantle": {
        "adaptation": ("pliable_enclosure", (_effect("momentum", 0.18),)),
        "breakthrough": ("complete_veil", (_effect("band", 0.15, resources=("gas", "liquid")), _effect("founding", 2))),
    },
    "vault_crab": {
        "adaptation": ("sealed_rations", (_effect("feed", 0.6),)),
        "breakthrough": ("ancestral_vault", (_effect("feed", 0.15),)),
    },
    "tidal_cephalopod": {
        "adaptation": ("tidal_recycling", (_effect("retain", 1, resources=("liquid",)), _effect("band", 0.25, resources=("liquid",)))),
        "breakthrough": ("ocean_mind", (_speed(0.1, "population_above", 10000),)),
    },
    "bone_walker": {
        "adaptation": ("adaptive_marrow", (_effect("retain", 1, resources=("gas", "liquid")),)),
        "breakthrough": ("walking_colony", (_effect("stage_speed", 0.015, cap=0.06),)),
    },
    "vent_drifter": {
        "adaptation": ("vent_exchange", (_effect("retain", 1, resources=("gas",)), _effect("band", 0.25, resources=("gas",)))),
        "breakthrough": ("endless_current", (_effect("momentum", 0.07),)),
    },
    "hive_sentinel": {
        "adaptation": ("many_chambers", (_effect("feed", 0.5), _effect("founding", 4), _effect("brood", 0.2))),
        "breakthrough": ("planetary_sentinel", (_effect("founding", 2), _speed(0.01, "other_established", cap=0.12, per_other=True))),
    },
    "hollow_choir": {
        "adaptation": ("harmonic_structure", (_speed(0.3),)),
        "breakthrough": ("worldsong", (_speed(0.1),)),
    },
    "ferric_sea_lily": {
        "adaptation": ("ferric_recycling", (_effect("feed", 0.5), _effect("band", 0.2, resources=("gas", "liquid")))),
        "breakthrough": ("iron_garden", (_effect("band", 0.1, resources=("gas", "liquid")),)),
    },
    "crustal_echo": {
        "adaptation": ("recorded_generation", (_effect("founding", 6), _effect("stage_speed", 0.03, cap=0.12))),
        "breakthrough": ("recursive_brood", (_effect("brood", 0.05),)),
    },
    "glacial_wyrm": {
        "adaptation": ("sealed_metabolism", (_effect("feed", 0.5), _effect("retain", 1, resources=("liquid",)))),
        "breakthrough": ("worldcoil", (_effect("rate_ceiling", 0.1),)),
    },
    "spire_drake": {
        "adaptation": ("spire_nursery", (_effect("founding", 2), _speed(0.45, "population_below", 2500))),
        "breakthrough": ("sky_dominion", (_speed(0.12),)),
    },
}

# Revival and Insight order from devtools/wildlife_optimizer.py
# --allow-unadapted --target 5000000 --common-lead 120 --refined-lead 240
# --deep-lead 240 (results in docs/cheatsheet/wildlife.md §1l-1), keyed by
# Habitat count. The planner uses the entry with the largest key not above the
# live Habitat count. The Commons in WILDLIFE_BOOTSTRAP revive first, without
# an Adaptation. Steps run strictly in order: ("revive", S) buys S's
# Adaptation, then revives; ("revive_raw", S) revives without it; ("adapt", S)
# buys the Adaptation of a revived species; ("break", S) buys S's Breakthrough
# once S has 10,000 individuals (Insight is held until then). A revive step
# waits for a free Habitat: colonies park at the Mk I ceiling (175,000) until
# Mk II and at 350,000 for good, and parked Mk I colonies are rehoused before
# any revival once Mk II is installed.
WILDLIFE_BOOTSTRAP = ("magmatic_annelid", "salt_tortoise")
WILDLIFE_SCHEDULES = {
    5: (
        ("revive_raw", "hollow_choir"),
        ("revive", "spire_drake"),
        ("revive", "hive_sentinel"),
        ("adapt", "magmatic_annelid"),
        ("adapt", "hollow_choir"),
        ("revive", "tidal_cephalopod"),
        ("adapt", "salt_tortoise"),
        ("break", "hive_sentinel"),
        ("break", "hollow_choir"),
        ("break", "magmatic_annelid"),
        ("break", "salt_tortoise"),
        ("revive_raw", "glasswing_mantis"),
        ("break", "spire_drake"),
        ("break", "glasswing_mantis"),
        ("break", "tidal_cephalopod"),
        ("revive", "mycelial_husk"),
        ("adapt", "glasswing_mantis"),
        ("revive", "mantle_strider"),
        ("revive", "veil_mantle"),
        ("break", "mycelial_husk"),
        ("break", "mantle_strider"),
        ("break", "veil_mantle"),
        ("revive", "crustal_echo"),
        ("break", "crustal_echo"),
        ("revive", "bone_walker"),
        ("revive", "ferric_sea_lily"),
        ("revive", "vault_crab"),
        ("revive", "vent_drifter"),
        ("break", "bone_walker"),
        ("break", "ferric_sea_lily"),
        ("break", "vault_crab"),
        ("break", "vent_drifter"),
        ("revive", "glacial_wyrm"),
    ),
    10: (
        ("revive_raw", "glacial_wyrm"),
        ("revive", "spire_drake"),
        ("revive_raw", "tidal_cephalopod"),
        ("revive", "hive_sentinel"),
        ("revive_raw", "mycelial_husk"),
        ("revive_raw", "vent_drifter"),
        ("revive", "hollow_choir"),
        ("revive_raw", "glasswing_mantis"),
        ("adapt", "magmatic_annelid"),
        ("adapt", "salt_tortoise"),
        ("break", "magmatic_annelid"),
        ("break", "salt_tortoise"),
        ("break", "mycelial_husk"),
        ("break", "glasswing_mantis"),
        ("break", "hollow_choir"),
        ("break", "hive_sentinel"),
        ("break", "tidal_cephalopod"),
        ("break", "vent_drifter"),
        ("revive", "mantle_strider"),
        ("break", "spire_drake"),
        ("break", "glacial_wyrm"),
        ("break", "mantle_strider"),
        ("revive", "veil_mantle"),
        ("revive", "crustal_echo"),
        ("revive", "bone_walker"),
        ("revive", "ferric_sea_lily"),
        ("revive", "vault_crab"),
        ("break", "veil_mantle"),
        ("break", "crustal_echo"),
        ("break", "bone_walker"),
        ("break", "ferric_sea_lily"),
        ("break", "vault_crab"),
    ),
    16: (
        ("revive_raw", "mycelial_husk"),
        ("revive_raw", "tidal_cephalopod"),
        ("revive_raw", "vent_drifter"),
        ("revive_raw", "bone_walker"),
        ("revive_raw", "glasswing_mantis"),
        ("revive_raw", "hollow_choir"),
        ("revive_raw", "veil_mantle"),
        ("revive_raw", "ferric_sea_lily"),
        ("revive", "glacial_wyrm"),
        ("revive_raw", "vault_crab"),
        ("revive", "hive_sentinel"),
        ("adapt", "hollow_choir"),
        ("revive", "mantle_strider"),
        ("revive", "crustal_echo"),
        ("adapt", "magmatic_annelid"),
        ("adapt", "salt_tortoise"),
        ("revive", "spire_drake"),
        ("adapt", "mycelial_husk"),
        ("adapt", "glasswing_mantis"),
        ("adapt", "veil_mantle"),
        ("adapt", "vault_crab"),
        ("adapt", "tidal_cephalopod"),
        ("adapt", "bone_walker"),
        ("adapt", "vent_drifter"),
        ("adapt", "ferric_sea_lily"),
        ("break", "magmatic_annelid"),
        ("break", "salt_tortoise"),
        ("break", "veil_mantle"),
        ("break", "mantle_strider"),
        ("break", "mycelial_husk"),
        ("break", "glasswing_mantis"),
        ("break", "hollow_choir"),
        ("break", "hive_sentinel"),
        ("break", "crustal_echo"),
        ("break", "tidal_cephalopod"),
        ("break", "vault_crab"),
        ("break", "bone_walker"),
        ("break", "vent_drifter"),
        ("break", "ferric_sea_lily"),
        ("break", "spire_drake"),
        ("break", "glacial_wyrm"),
    ),
}
