"""
World seed quality: the parts of a world its seed decides (docs/plans/scoring_map_seeds.md).

`recipes`: the 15 Seed Maker recipes are a pure function of the world seed (port of simworker
Bp(seed), PRNG mp as in devtools/headless/field.mjs). Life-form supply is the same on every
world (35 fixed biosites, simworker hy/vU), so a seed's recipes alone decide how many seeds/h
each fill can get. Supply here is the upper bound tons / cooldown per site, travel ignored,
minus each form's peak feed demand: the wildlife schedule for --habitats run to the Wildlife
pillar (devtools/wildlife_optimizer.py, no Feed Maker cap), feed recipes from
docs/database/recipes_feed_maker.md (1 t of each form per 20 feed).
This offline tool may use the game's constants; in-game scripts must measure them.

Usage: python devtools/seed_quality.py recipes --show SEED
       python devtools/seed_quality.py recipes --check SAVE.json
       python devtools/seed_quality.py recipes --seeds 1-20000 [--top 10]
       python devtools/seed_quality.py export [--out devtools/headless/.cache/seed_model.json] [--recipes 1-5000]
       (export: SUPPLY and fill demand for devtools/headless/seedscan.mjs, optional recipes to verify recipes.mjs)
       options: --habitats 16 (wildlife schedule for the feed peak), --no-feed
"""
import argparse
import json
import os
import re
import sys
from itertools import combinations

from savefile import load_save

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "4_controlpanel", "lib"))

import field_layout as fl  # noqa: E402
import wildlife_data as wd  # noqa: E402
import wildlife_model as wm  # noqa: E402

sys.path.insert(0, os.path.join(REPO_ROOT, "devtools"))
import wildlife_optimizer as wo  # noqa: E402

# Simworker _p: per biome common x3, uncommon x2, rare x1.
BIOMES = {
    "frozen": ["ice_algae", "snow_moss", "frost_lichen", "cold_spores", "ice_crust", "frost_fungus"],
    "coastal": ["sea_algae", "tide_moss", "shore_lichen", "brine_plankton", "salt_crust", "coral_fungus"],
    "geothermal": ["vent_algae", "steam_moss", "heat_lichen", "hot_spores", "heat_crust", "vent_fungus"],
    "volcanic": ["sulfur_moss", "cinder_lichen", "ash_spores", "lava_algae", "magma_crust", "black_fungus"],
    "deep": ["cave_moss", "stone_lichen", "crystal_spores", "deep_algae", "stone_mat", "cave_fungus"],
}
FORMS = [f for forms in BIOMES.values() for f in forms]
RARITY = {f: ("common", "common", "common", "uncommon", "uncommon", "rare")[i % 6] for i, f in enumerate(FORMS)}
# Simworker Ip order: recipe s goes to species s.
SPECIES = ["sunpetal", "shadeleaf", "dewmoss", "lonethorn", "packfern", "twinvine", "spitebud", "sunspur",
           "glowvine", "crowncap", "pondmoss", "saltbloom", "brinethorn", "saltmate", "grandbloom"]
MAX_RECIPES_PER_FORM = 4
RECIPE_SALT = 1347174734

# Simworker hy(c1, c2, c3, u1, u2, rare): the 7 biosites of each biome as (slot, tons) lists.
SITES = [[(0, 32), (1, 28)], [(2, 34)], [(0, 30), (3, 45)], [(1, 35), (4, 48)],
         [(2, 29), (3, 42)], [(0, 31), (1, 33), (4, 46)], [(2, 38), (5, 72)]]
COOLDOWN_H = {"common": 9, "uncommon": 18, "rare": 36}  # simworker vU; a site uses its rarest form's
RARITY_RANK = {"common": 0, "uncommon": 1, "rare": 2}
FILLS = ("crowncap", "grandbloom")


def _imul(a, b):
    return ((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF)) & 0xFFFFFFFF


def _i32(x):
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x & 0x80000000 else x


def prng(seed):
    """Game mp(seed): mulberry32-like, floats in [0, 1)."""
    state = [_i32(seed)]

    def rand():
        state[0] = _i32(state[0] + 1831565813)
        t = state[0] & 0xFFFFFFFF
        e = _imul(t ^ (t >> 15), t | 1)
        e = ((e + _imul(e ^ (e >> 7), e | 61)) & 0xFFFFFFFF) ^ e
        return ((e ^ (e >> 14)) & 0xFFFFFFFF) / 4294967296
    return rand


def recipes(seed):
    """{species: sorted [3 forms]}, as the game's Bp(seed)."""
    combos = list(combinations(FORMS, 3))
    rand = prng(_i32(seed) ^ RECIPE_SALT)
    out, used, o = {}, {}, 0
    while len(out) < len(SPECIES) and o < len(combos):
        e = o + int(rand() * (len(combos) - o))
        combos[e], combos[o] = combos[o], combos[e]
        t = combos[o]
        o += 1
        if all(used.get(f, 0) < MAX_RECIPES_PER_FORM for f in t):
            out[SPECIES[len(out)]] = sorted(t)
            for f in t:
                used[f] = used.get(f, 0) + 1
    if len(out) != len(SPECIES):
        raise ValueError("recipe generation exhausted the combination space")
    return out


def supply_per_form():
    """{form: t/h} upper bound: each site refills to full after its cooldown."""
    supply = {f: 0.0 for f in FORMS}
    for forms in BIOMES.values():
        for site in SITES:
            rarest = max((RARITY[forms[slot]] for slot, _ in site), key=lambda r: RARITY_RANK[r])
            for slot, tons in site:
                supply[forms[slot]] += tons / COOLDOWN_H[rarest]
    return supply


def feed_recipes():
    """{creature: [forms]} from the Feed Maker recipe database (fixed on every world)."""
    with open(os.path.join(REPO_ROOT, "docs", "database", "recipes_feed_maker.md"), encoding="utf-8") as fh:
        text = fh.read()
    pattern = r"^##### Forage \+ (.+?) → .+? `craft_feed_(\w+)`"
    return {m.group(2): [f.strip().lower().replace(" ", "_") for f in m.group(1).split("+")]
            for m in re.finditer(pattern, text, re.M)}


def feed_peak_per_form(habitats):
    """{form: t/h}: each form's highest feed demand over the wildlife run (its own peak, not the total's)."""
    recipes_by_creature = feed_recipes()
    scenario = wo.Scenario(habitats=habitats, target=wo.PILLAR_WILDLIFE, feed_makers=0)
    sim = wo.start_sim(scenario)
    sim.run(list(wm.schedule_for(habitats)), wo.default_order(scenario))
    peak = {}
    for _t, per_species in sim.feed_log:
        step = {}
        for creature, feed_h in per_species.items():
            for form in recipes_by_creature[creature]:
                step[form] = step.get(form, 0.0) + feed_h / wd.FEED_PER_CRAFT
        for form, tons in step.items():
            peak[form] = max(peak.get(form, 0.0), tons)
    return peak


RAW_SUPPLY = supply_per_form()
SUPPLY = dict(RAW_SUPPLY)
FEED = {}


def set_feed(habitats):
    """Subtract the feed peak of `habitats` (None: no feed) from SUPPLY."""
    FEED.clear()
    if habitats:
        FEED.update(feed_peak_per_form(habitats))
    for form, raw in RAW_SUPPLY.items():
        SUPPLY[form] = max(1e-6, raw - FEED.get(form, 0.0))


def fill_demand(fill):
    """(seeds/h per species, Forage/h) of the full layout of `fill` at Mk I, garden excluded."""
    rules = fl.rules_from_published({})
    cells, _, garden = fl.full_layout(fl.full_chunk_count(fill), fill)
    garden = set(garden)
    seeds = {}
    for sector, species in cells.items():
        if sector not in garden:
            seeds[species] = seeds.get(species, 0.0) + 1.0 / rules[species]["growth_time"]
    return seeds, fl.forage_per_hour(cells, rules, garden)


DEMAND = {fill: fill_demand(fill) for fill in FILLS}


def fill_score(recipe_map, fill):
    """Share of the full fill the forms can feed (≤ 1), its Forage/h and the bottleneck form."""
    seeds, forage = DEMAND[fill]
    need = {}
    for species, per_h in seeds.items():
        for form in recipe_map[species]:
            need[form] = need.get(form, 0.0) + per_h
    form, load = max(((f, n / SUPPLY[f]) for f, n in need.items()), key=lambda x: x[1])
    share = min(1.0, 1.0 / load)
    return {"share": share, "forage_h": share * forage, "bottleneck": form, "load": load}


def form_need(recipe_map, fill):
    """{form: t/h} the full layout of `fill` needs."""
    need = {}
    for species, per_h in DEMAND[fill][0].items():
        for form in recipe_map[species]:
            need[form] = need.get(form, 0.0) + per_h
    return need


def best_mix(recipe_map, steps=100):
    """Best CC share of the field (rest GB), each share scaling its full layout linearly; ideal, layout borders ignored."""
    cc, gb = form_need(recipe_map, "crowncap"), form_need(recipe_map, "grandbloom")
    best = (0.0, 0.0, 0.0)
    for i in range(steps + 1):
        a = i / steps
        if any(a * n > SUPPLY[f] + 1e-9 for f, n in cc.items()):
            break
        b = min([1.0 - a] + [(SUPPLY[f] - a * cc.get(f, 0.0)) / n for f, n in gb.items()])
        forage = a * DEMAND["crowncap"][1] + max(0.0, b) * DEMAND["grandbloom"][1]
        if forage > best[2]:
            best = (a, max(0.0, b), forage)
    return {"cc": best[0], "gb": best[1], "forage_h": best[2]}


def score(seed):
    recipe_map = recipes(seed)
    fills = {fill: fill_score(recipe_map, fill) for fill in FILLS}
    best = max(fills, key=lambda f: fills[f]["forage_h"])
    return {"seed": seed, "best": best, "forage_h": fills[best]["forage_h"], "fills": fills,
            "mix": best_mix(recipe_map)}


def seed_range(spec):
    out = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


def fmt_fill(name, f):
    return "%-10s %3.0f%% of full, %5.0f Forage/h, bottleneck %s (%s, load %.2f)" % (
        name, f["share"] * 100, f["forage_h"], f["bottleneck"], RARITY[f["bottleneck"]], f["load"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="part", required=True)
    rp = sub.add_parser("recipes")
    rp.add_argument("--show", type=int)
    rp.add_argument("--check")
    rp.add_argument("--seeds")
    rp.add_argument("--top", type=int, default=10)
    rp.add_argument("--habitats", type=int, default=16)
    rp.add_argument("--no-feed", action="store_true")
    ep = sub.add_parser("export")
    ep.add_argument("--out", default=os.path.join(REPO_ROOT, "devtools", "headless", ".cache", "seed_model.json"))
    ep.add_argument("--recipes")
    ep.add_argument("--habitats", type=int, default=16)
    a = ap.parse_args()
    if a.part == "export":
        set_feed(a.habitats)
        out = {"habitats": a.habitats, "forms": FORMS, "species": SPECIES, "supply": [SUPPLY[f] for f in FORMS],
               "demand": {fill: [DEMAND[fill][0].get(sp, 0.0) for sp in SPECIES] for fill in FILLS}}
        if a.recipes:
            out["recipes"] = {str(seed): [sorted(FORMS.index(f) for f in recipes(seed)[sp]) for sp in SPECIES]
                              for seed in seed_range(a.recipes)}
            out["loads"] = {str(seed): [score(seed)["fills"][fill]["load"] for fill in FILLS]
                            for seed in seed_range(a.recipes)[:300]}
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh)
        return
    set_feed(None if a.no_feed else a.habitats)

    if a.check:
        raw = load_save(a.check)
        st = raw.get("state", raw)
        saved = {k: sorted(v) for k, v in st["planet"]["plants"]["recipeMap"].items()}
        wrong = {k: (v, saved.get(k)) for k, v in recipes(st["seed"]).items() if saved.get(k) != v}
        print("seed %s: %s" % (st["seed"], "%d recipes differ: %s" % (len(wrong), wrong) if wrong else "port matches"))
        sys.exit(1 if wrong else 0)
    elif a.show is not None:
        for species, forms in recipes(a.show).items():
            print("%-10s %s" % (species, ", ".join("%s (%s %.1f - feed %.1f t/h)" % (f, RARITY[f], RAW_SUPPLY[f], FEED.get(f, 0.0)) for f in forms)))
        s = score(a.show)
        for name in FILLS:
            print(fmt_fill(name, s["fills"][name]))
        m = s["mix"]
        print("best mix   %.0f%% CC + %.0f%% GB, %5.0f Forage/h" % (m["cc"] * 100, m["gb"] * 100, m["forage_h"]))
    elif a.seeds:
        rows = [score(seed) for seed in seed_range(a.seeds)]
        columns = {
            "single fill Forage/h": lambda r: r["forage_h"],
            "best mix Forage/h": lambda r: r["mix"]["forage_h"],
            "CC load": lambda r: r["fills"]["crowncap"]["load"],
            "GB load": lambda r: r["fills"]["grandbloom"]["load"],
        }
        for key, get in columns.items():
            vals = sorted(get(r) for r in rows)
            q = lambda p: vals[int(p * (len(vals) - 1))]  # noqa: E731
            print("%-20s min %7.2f p10 %7.2f median %7.2f p90 %7.2f max %7.2f" % (key, q(0), q(0.1), q(0.5), q(0.9), q(1)))
        full = {f: sum(r["fills"][f]["share"] >= 1.0 for r in rows) for f in FILLS}
        print("seeds with a full fill: %s of %d" % (full, len(rows)))
        for r in sorted(rows, key=lambda r: -r["forage_h"])[:a.top]:
            print(r["seed"], "; ".join(fmt_fill(n, r["fills"][n]) for n in FILLS))
    else:
        ap.error("one of --show, --check, --seeds")


if __name__ == "__main__":
    main()
