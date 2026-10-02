import math
from wildlife_data import SPECIES, RARITY_BREEDING, STAGE_THRESHOLDS, STAGE_CAPACITY, INSIGHT_CURVE, BONUS_TREES, BONUS_CAPS, BREED_BASE, GROWTH_EXPONENT, GROWTH_SATURATION_POP, NATURAL_RATE_CEILING, FOUNDING_POPULATION, HABITAT_MK2_CAPACITY_FACTOR, WILDLIFE_SCHEDULES

# Pure wildlife growth model mirroring the simworker (docs/cheatsheet/wildlife.md
# §1l): stage, capacity, required fluids, bonus resolution, breeding rate and
# the Insight curve. No game calls, so the in-game planner and the offline
# optimizer (devtools/wildlife_optimizer.py) share it.

_SATURATION_F = GROWTH_SATURATION_POP / 10.0


def natural_growth(population, ceiling_multiplier=1.0):
    """F(p): population momentum term of the breeding rate (simworker `Fq`)."""
    p = max(population, FOUNDING_POPULATION)
    if p <= 10:
        return p
    f = (p / 10.0) ** GROWTH_EXPONENT * 10.0
    if p <= GROWTH_SATURATION_POP:
        return f
    knee = _SATURATION_F ** GROWTH_EXPONENT * 10.0
    span = max(1.0, ceiling_multiplier) * NATURAL_RATE_CEILING / BREED_BASE - knee
    return knee + span * (1.0 - math.exp(-max(0.0, f - knee) / span))


def insight_at(population):
    """Cumulative Insight a colony has earned by reaching `population`."""
    points = INSIGHT_CURVE
    if population <= points[0][0]:
        return points[0][1]
    for i in range(1, len(points)):
        low_pop, low_insight = points[i - 1]
        high_pop, high_insight = points[i]
        if population <= high_pop:
            return low_insight + (population - low_pop) / (high_pop - low_pop) * (high_insight - low_insight)
    return points[-1][1]


def insight_between(start, end):
    return max(0.0, insight_at(end) - insight_at(start))


def stage_of(population):
    stage = 0
    while stage < 4 and population >= STAGE_THRESHOLDS[stage]:
        stage += 1
    return stage


def capacity(stage, tier=1, crowding=1.0):
    base = STAGE_CAPACITY[max(0, min(4, stage))]
    return int(base * (HABITAT_MK2_CAPACITY_FACTOR if tier >= 2 else 1) * crowding)


def stage_inputs(rarity, stage):
    """{gas, liquid: (active, tightness, apex)} for a rarity at a stage (simworker `Hq`)."""
    s = max(0, min(4, stage))
    gas = (False, 0, False)
    liquid = (False, 0, False)
    if rarity == "common":
        if s >= 3:
            gas = (True, 0, False)
    elif rarity == "uncommon":
        if s >= 1:
            gas = (True, max(0, s - 1), False)
        if s >= 3:
            liquid = (True, s - 3, False)
    elif rarity == "rare":
        if s >= 1:
            gas = (True, max(0, s - 1), s >= 2)
        if s >= 3:
            liquid = (True, s - 3, s >= 4)
    elif rarity == "legendary":
        if s >= 1:
            gas = (True, max(0, s - 1), s >= 3)
        if s >= 2:
            liquid = (True, max(0, s - 2), s >= 4)
    return {"gas": gas, "liquid": liquid}


def required_fluids(species, stage, retain_gas=False, retain_liquid=False):
    """(gas or None, liquid or None) the species needs at `stage`."""
    info = SPECIES[species]
    inputs = stage_inputs(info["rarity"], stage)
    out = []
    for medium, retain in (("gas", retain_gas), ("liquid", retain_liquid)):
        active, _tightness, apex = inputs[medium]
        pair = info[medium]
        if not active or pair is None:
            out.append(None)
        else:
            out.append(pair[1] if apex and not retain else pair[0])
    return out[0], out[1]


def breakthrough_effects(purchased):
    """Effects of every purchased Breakthrough (they act on all species). `purchased`: a set of node ids."""
    effects = []
    for tree in BONUS_TREES.values():
        node_id, node_fx = tree["breakthrough"]
        if node_id in purchased:
            effects.extend(node_fx)
    return effects


def adaptation_effects(purchased, species):
    """Effects of `species`' own Adaptation when purchased. `purchased`: a set of node ids."""
    tree = BONUS_TREES.get(species)
    if not tree or tree["adaptation"][0] not in purchased:
        return []
    return list(tree["adaptation"][1])


def node_effects(purchased, species):
    """Effects of purchased nodes acting on `species`: every Breakthrough plus its own Adaptation.

    `purchased` is an iterable of node ids."""
    owned = set(purchased)
    return breakthrough_effects(owned) + adaptation_effects(owned, species)


def feed_factor(effects, feed=1.0):
    """`feed` times (1 - amount) of each feed effect, before the floor."""
    for fx in effects:
        if fx["kind"] == "feed":
            feed *= 1.0 - min(1.0, max(0.0, fx["amount"]))
    return feed


def static_bonuses(effects):
    """Condition-free parts: feed multiplier, founding, retained fluids, band tolerance."""
    feed = feed_factor(effects)
    founding = 0
    retain_gas = False
    retain_liquid = False
    band = {"gas": 0.0, "liquid": 0.0}
    for fx in effects:
        kind = fx["kind"]
        if kind == "founding":
            founding += int(fx["amount"])
        elif kind == "retain":
            retain_gas = retain_gas or "gas" in fx["resources"]
            retain_liquid = retain_liquid or "liquid" in fx["resources"]
        elif kind == "band":
            for medium in fx["resources"]:
                band[medium] += fx["amount"]
    return {
        "feed_multiplier": max(BONUS_CAPS["feed_multiplier_floor"], feed),
        "founding": founding,
        "retain_gas": retain_gas,
        "retain_liquid": retain_liquid,
        "band_gas": min(BONUS_CAPS["band_tolerance"], band["gas"]),
        "band_liquid": min(BONUS_CAPS["band_tolerance"], band["liquid"]),
    }


def _effect_value(fx, population, stage, other_established):
    condition = fx["condition"]
    if condition == "population_below" and not population < fx["threshold"]:
        return 0.0
    if condition == "population_above" and not population > fx["threshold"]:
        return 0.0
    if condition == "other_established" and other_established < 1:
        return 0.0
    if fx["kind"] == "stage_speed":
        value = fx["amount"] * max(0, stage)
    elif fx["per_other"]:
        value = fx["amount"] * other_established
    else:
        value = fx["amount"]
    return value if fx["cap"] is None else min(fx["cap"], value)


def dynamic_bonuses(effects, population, stage, other_established):
    """(speed, brood, momentum, rate_ceiling) bonuses after conditions and global caps (simworker `Sq`)."""
    speed = 1.0
    brood = 0.0
    momentum = 0.0
    ceiling = 0.0
    for fx in effects:
        kind = fx["kind"]
        if kind == "speed" or kind == "stage_speed":
            speed *= 1.0 + _effect_value(fx, population, stage, other_established)
        elif kind == "brood":
            brood += _effect_value(fx, population, stage, other_established)
        elif kind == "momentum":
            momentum += _effect_value(fx, population, stage, other_established)
        elif kind == "rate_ceiling":
            ceiling += _effect_value(fx, population, stage, other_established)
    return (
        min(BONUS_CAPS["speed"], max(0.0, speed - 1.0)),
        min(BONUS_CAPS["brood"], brood),
        min(BONUS_CAPS["momentum"], momentum),
        min(BONUS_CAPS["rate_ceiling"], ceiling),
    )


def breeding_rate(species, population, effects, other_established=0, efficiency=1.0, momentum=1.0):
    """Expected individuals/h, brood yield included; capacity is not applied here."""
    stage = stage_of(population)
    speed, brood, momentum_bonus, ceiling = dynamic_bonuses(effects, population, stage, other_established)
    rarity = SPECIES[species]["rarity"]
    return (
        BREED_BASE * natural_growth(population, 1.0 + ceiling) * efficiency * RARITY_BREEDING[rarity]
        * (1.0 + speed) * (1.0 + momentum_bonus * max(0.0, min(1.0, momentum))) * (1.0 + brood)
    )


def founding_population(effects):
    return FOUNDING_POPULATION + static_bonuses(effects)["founding"]


def schedule_for(habitats):
    """WILDLIFE_SCHEDULES entry for the largest Habitat count not above `habitats` (smallest if none)."""
    keys = sorted(WILDLIFE_SCHEDULES)
    chosen = keys[0]
    for key in keys:
        if key <= habitats:
            chosen = key
    return WILDLIFE_SCHEDULES[chosen]
