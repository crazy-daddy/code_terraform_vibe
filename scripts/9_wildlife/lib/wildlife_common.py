# Shared archive keys, tunables and small pure helpers of the Wildlife
# automation: the planner (lib/wildlife_planner.py, run by the Control Room
# Automation), the Habitat controller (lib/habitat.py) and the Feed Maker
# controller (lib/feed_maker.py). Numbers: docs/cheatsheet/wildlife.md §1l-2.
#
# Time: one game day is 600 s (production.DAY_CYCLE_DURATION_SECONDS), so one
# game hour is 25 s of script time and 250 clock ticks.

from wildlife_data import SPECIES, FEED_PER_BIRTH, FEED_PER_CRAFT, FORAGE_PER_CRAFT
from wildlife_model import node_effects, static_bonuses

# {habitat_id: telemetry}, written by each Habitat (lib/habitat.py).
STATUS_KEY = "wildlife.status"
# {feed_maker_id: telemetry incl. unlocked recipe ids}, written by each Feed Maker.
FEED_KEY = "wildlife.feed"
# The planner's decisions: assign / buy / feed_demand / forage_reserve / form_targets / progress / alerts.
PLAN_KEY = "wildlife.plan"
# {missing_creatures: [...], missing_recipes: [...]}.
READINESS_KEY = "wildlife.readiness"
# Operator override: a list of species to revive first (and only those, while non-empty).
TARGETS_KEY = "wildlife.targets"

PLANET_ID = "nocturna"
TICKS_PER_GAME_HOUR = 250
FEED_ITEM_PREFIX = "feed_"
RECIPE_PREFIX = "craft_"
MK2_PACK_ITEM_ID = "habitat_upgrade_pack_mk2"

# Entries of machines that stopped publishing (10 ticks/s: 1 h real).
STATUS_STALE_TICKS = 36000

# Feed staged in the Habitat's own bin before revive(): revive spends one,
# rearing eats none (no births), the rest feeds the first births. Staging it
# in the Habitat's own bin is the reservation: nothing else can take it.
REARING_FEED_EXTRA = 3
# Established colony: top the bin (input buffer 50) up to the target once it
# falls below FEED_TOPUP_AT.
FEED_TOPUP_AT = 30
FEED_TOPUP_TARGET = 50
# Home feed stock target per housed species, in game hours of its current use.
FEED_BUFFER_H = 24.0
# Life-form requests at home: game hours of the planned crafts that use a form,
# at least this many crafts, capped below one 2,000-unit Warehouse slot.
FORM_BUFFER_H = 48.0
FORM_REQUEST_MIN_CRAFTS = 20
FORM_REQUEST_CAP = 1900

# Feed demand priority classes (lower first).
PRIO_RESERVE = 0      # Habitat staging for revive()
PRIO_REARING = 1      # Habitat in the 12 h rearing window
PRIO_GROWING = 2      # established, ordered by hours left to the Mk II ceiling (slowest first)
PRIO_RANK_SCALE = 100  # PRIO_GROWING * scale + rank

# Habitat park reasons (lib/habitat.py publishes `parked`).
PARK_EMPTY = "empty"
PARK_NO_FEED = "no_feed"
PARK_CAPPED = "capped"


def feed_item_of(species):
    return FEED_ITEM_PREFIX + species


def recipe_of(species):
    return RECIPE_PREFIX + FEED_ITEM_PREFIX + species


def species_of_feed(item_id):
    if isinstance(item_id, str) and item_id.startswith(FEED_ITEM_PREFIX):
        species = item_id[len(FEED_ITEM_PREFIX):]
        if species in SPECIES:
            return species
    return None


def feed_multiplier(species, purchased):
    """Feed per birth relative to base, from the purchased nodes (ids) acting on `species`."""
    return static_bonuses(node_effects(purchased, species))["feed_multiplier"]


def feed_per_hour(species, rate, purchased):
    """Feed a colony breeding `rate` individuals/h eats per game hour."""
    return max(0.0, rate) * FEED_PER_BIRTH * feed_multiplier(species, purchased)


def crafts_for(feed_units):
    """Feed Maker crafts that yield at least `feed_units` feed."""
    units = max(0, int(feed_units + 0.999))
    return (units + FEED_PER_CRAFT - 1) // FEED_PER_CRAFT


def forage_for(feed_units):
    return crafts_for(feed_units) * FORAGE_PER_CRAFT


def fresh(entry, curr_tick, stale_ticks=STATUS_STALE_TICKS):
    return isinstance(entry, dict) and curr_tick - (entry.get("tick") or 0) < stale_ticks
