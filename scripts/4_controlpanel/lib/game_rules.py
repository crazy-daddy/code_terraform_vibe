# Game rules: fixed facts of this game build with no logic attached (ids,
# sizes, rates from docs/ and the simworker). Our own tunables never go here.
#
# Before adding a constant anywhere, look here first. A constant that belongs
# to one piece of logic lives with that logic instead (Plants bands:
# plant_terraformer_common; hardware tier ladders: item_tiers).
#
# No imports, so any lib can import from here without a cycle
# (tests/test_game_rules.py keeps it that way). One-line imports only in game.


##############################################################################
#                                  TIMING                                    #
##############################################################################

# Real seconds per 24 world-clock hours (simworker planet.dayCycleDuration,
# this build). A live reading: game_clock.real_seconds_per_hour().
DAY_CYCLE_DURATION_SECONDS = 600

# Simulation ticks per real second at normal speed (docs/components/clock.md).
TICKS_PER_SECOND = 10

# Derived: 25 real seconds / 250 ticks per world-clock hour.
SECONDS_PER_GAME_HOUR = DAY_CYCLE_DURATION_SECONDS / 24.0
TICKS_PER_GAME_HOUR = int(SECONDS_PER_GAME_HOUR * TICKS_PER_SECOND)


##############################################################################
#                            ORES AND SMELTING                               #
##############################################################################

# Every mineable raw ore (docs/types/world_and_sites.md MiningSite.item_id).
RAW_ORE_ITEM_IDS = ("iron_ore", "silicon", "titanium", "cobalt", "rare_earth", "neutronium", "lead_ore")

# Smelter recipes as {ore: product} (docs/database/recipes_smelter.md). The
# recipe id is "smelt_" + product. Covers every RAW_ORE_ITEM_IDS entry.
SMELT_PRODUCTS = {
    "iron_ore": "iron_ingot",
    "silicon": "glass",
    "titanium": "titanium_ingot",
    "cobalt": "cobalt_ingot",
    "rare_earth": "rare_earth_core",
    "neutronium": "neutronium_bar",
    "lead_ore": "lead_ingot",
}


##############################################################################
#                                  WORLD                                     #
##############################################################################

# Nocturna's biomes (nocturna.biome_at). The Biomass Mixer has one essence
# port per biome.
BIOMES = ("frozen", "coastal", "geothermal", "volcanic", "deep")

# World tile size in metres. Every pipe or power-line piece spans one tile.
TILE_M = 10


##############################################################################
#                           BUILDINGS AND STORAGE                            #
##############################################################################

# Tank building types that hold liquids (water, oil, essence).
LIQUID_TANK_TYPE_IDS = ("liquid_tank", "bulk_liquid_reservoir")

# Units per Warehouse slot (docs/components/warehouse.md: 5 slots x 2,000).
WAREHOUSE_SLOT_UNITS = 2000

# Crop Automator output buffer in units (docs/components/crop_automator.md).
CROP_AUTOMATOR_OUTPUT_CAP = 50000
