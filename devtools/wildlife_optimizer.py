"""
Offline optimizer for the wildlife revival and Insight schedule (Phase 9, docs/plans/phase9_wildlife.md).

Every input is a game constant that is the same on every world (docs/cheatsheet/wildlife.md §1l),
so the best order of revivals, Adaptations and Breakthroughs is solved here once instead of
simulated in game. The in-game planner walks the resulting WILDLIFE_SCHEDULES entry.

Model (scripts/4_controlpanel/lib/wildlife_model.py, the same code the game loads):
  - Both Commons (BOOTSTRAP) revive at t=0 without an Adaptation; every other revival buys its
    Adaptation first (1 Insight), then rears 12 h and establishes at 4 + founding bonuses.
  - Colonies grow by the simworker breeding rate with full support (momentum ramps over 24 h).
    A colony stalls when its current stage needs a fluid that isn't available yet: common fluids
    COMMON_LEAD_H after Exotic Husbandry (1,000 Wildlife), refined ones REFINED_LEAD_H after it,
    chlorine/quicksilver DEEP_LEAD_H after Deep Exotics (500,000). Habitats are Mk I (175,000 cap).
  - Optional feed limit: the Feed Makers' output caps total births (prorated over colonies).
  - Insight comes from each colony's population along the Insight curve.

A schedule is an ordered list of steps: ("revive", S), ("adapt", S) for a bootstrap species, and
("break", S). Steps run strictly in order, each as soon as it is affordable and allowed (a free
Habitat, source colony at 10,000 for a Breakthrough), so a Breakthrough step waiting for its gate
holds the Insight (saving). A step that can never run (no Habitat left, species never revived) is
skipped. Search: beam search over schedule prefixes; a prefix is scored by simulating it followed
by a default tail policy. Score: hours until total Wildlife reaches TARGET_WILDLIFE.

Usage: python devtools/wildlife_optimizer.py [--habitats 10] [--beam 6] [--target 600000]
       [--common-lead 72] [--refined-lead 168] [--deep-lead 168] [--feed-makers 2] [--allow-unadapted]
"""
import argparse
import os
import sys
from multiprocessing import Pool

sys.dont_write_bytecode = True
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "4_controlpanel", "lib"))

import wildlife_data as wd  # noqa: E402
import wildlife_model as wm  # noqa: E402

BOOTSTRAP = wd.WILDLIFE_BOOTSTRAP
PILLAR_WILDLIFE = 5000000     # "Wildlife Teeming": the Wildlife pillar complete
MILESTONES = (wd.EXOTIC_HUSBANDRY_WILDLIFE, wd.FEED_MAKER_MK2_WILDLIFE, wd.DEEP_EXOTICS_WILDLIFE, wd.HABITAT_MK2_WILDLIFE, 2000000, PILLAR_WILDLIFE)
FULL_POPULATION = 350000       # Mk II capacity at Abundant: a colony here is finished
MAX_GROWTH_FRACTION = 0.02   # a step grows no colony by more than this share
MAX_DT_H = 24.0
MIN_DT_H = 0.25

RARITY_ORDER = {"common": 0, "uncommon": 1, "rare": 2, "legendary": 3}


class Scenario:
    def __init__(self, habitats=10, target=wd.HABITAT_MK2_WILDLIFE, horizon_h=20000.0, common_lead_h=72.0,
                 refined_lead_h=168.0, deep_lead_h=168.0, feed_makers=2, allow_unadapted=False, mk2_lead_h=72.0,
                 park_finished=True):
        self.habitats = habitats
        self.target = target
        self.horizon_h = horizon_h
        self.common_lead_h = common_lead_h
        self.refined_lead_h = refined_lead_h
        self.deep_lead_h = deep_lead_h
        self.feed_makers = feed_makers
        self.allow_unadapted = allow_unadapted
        self.mk2_lead_h = mk2_lead_h
        self.park_finished = park_finished


def all_items(scenario):
    items = [("adapt", s) for s in (BOOTSTRAP + tuple(s for s in wd.SPECIES if s not in BOOTSTRAP) if scenario.allow_unadapted else BOOTSTRAP)]
    items += [("revive", s) for s in wd.SPECIES if s not in BOOTSTRAP]
    if scenario.allow_unadapted:
        items += [("revive_raw", s) for s in wd.SPECIES if s not in BOOTSTRAP]
    items += [("break", s) for s in wd.SPECIES]
    return items


def _founding_first(species):
    """Default tail order key: rarity, then founding/early bonuses first."""
    rarity = RARITY_ORDER[wd.SPECIES[species]["rarity"]]
    fx = wd.BONUS_TREES[species]["adaptation"][1]
    early = sum(f["amount"] for f in fx if f["kind"] == "founding") + sum(10 * f["amount"] for f in fx if f["condition"] == "population_below")
    return (rarity, -early, species)


def default_order(scenario):
    items = [("adapt", s) for s in BOOTSTRAP]
    items += [("revive", s) for s in sorted((s for s in wd.SPECIES if s not in BOOTSTRAP), key=_founding_first)]
    items += [("break", s) for s in wd.SPECIES]
    if scenario.allow_unadapted:
        # Idle Insight buys the Adaptation of any species revived without it.
        items += [("adapt", s) for s in wd.SPECIES if s not in BOOTSTRAP]
    return items


class Sim:
    def __init__(self, scenario):
        self.sc = scenario
        self.t = 0.0
        self.insight = 0.0
        self.purchased = set()
        self.colonies = {}      # species -> dict(pop, rearing_until, momentum_since, effects, ver)
        self.habitats_used = 0
        self.fluid_ready = {"common": None, "refined": None, "deep": None}
        self.mk2_ready = None
        self.milestones = {}
        self.log = []           # (t, item, insight_after)
        self._ver = 0
        self.feed_peak = 0.0

    # ---------------------------------------------------------------- state
    def wildlife(self):
        return sum(c["pop"] for c in self.colonies.values() if c["rearing_until"] is None)

    def established(self):
        return sum(1 for c in self.colonies.values() if c["rearing_until"] is None)

    def fluid_available(self, fluid):
        if fluid is None:
            return True
        ready = self.fluid_ready[wd.FLUID_TIER[fluid]]
        return ready is not None and self.t >= ready

    def _effects(self, species, colony):
        if colony["ver"] != self._ver:
            colony["effects"] = wm.node_effects(self.purchased, species)
            colony["static"] = wm.static_bonuses(colony["effects"])
            colony["ver"] = self._ver
        return colony["effects"]

    # ---------------------------------------------------------------- actions
    def feasible(self, item):
        """'now', 'later' or 'never'."""
        kind, s = item
        if kind in ("revive", "revive_raw"):
            if s in self.colonies:
                return "never"
            if self.habitats_used >= self.sc.habitats:
                return "later" if self.sc.park_finished else "never"
            cost = wd.ADAPTATION_COST if kind == "revive" else 0
            return "now" if self.insight >= cost - 1e-9 else "later"
        node = wd.BONUS_TREES[s]["adaptation" if kind == "adapt" else "breakthrough"][0]
        if node in self.purchased:
            return "never"
        if kind == "adapt":
            if s not in self.colonies:
                return "later"
            return "now" if self.insight >= wd.ADAPTATION_COST - 1e-9 else "later"
        colony = self.colonies.get(s)
        if colony is None:
            return "never" if self.habitats_used >= self.sc.habitats and not self.sc.park_finished else "later"
        if colony["pop"] < wd.BREAKTHROUGH_POPULATION or self.insight < wd.BREAKTHROUGH_COST - 1e-9:
            return "later"
        return "now"

    def apply(self, item):
        kind, s = item
        if kind in ("revive", "revive_raw"):
            if kind == "revive":
                self._buy(wd.BONUS_TREES[s]["adaptation"][0], wd.ADAPTATION_COST)
            self._revive(s)
        elif kind == "adapt":
            self._buy(wd.BONUS_TREES[s]["adaptation"][0], wd.ADAPTATION_COST)
        else:
            self._buy(wd.BONUS_TREES[s]["breakthrough"][0], wd.BREAKTHROUGH_COST)
        self.log.append((self.t, item, self.insight))

    def _buy(self, node, cost):
        self.insight -= cost
        self.purchased.add(node)
        self._ver += 1

    def _revive(self, species):
        self.habitats_used += 1
        self.colonies[species] = {"pop": 0.0, "rearing_until": self.t + wd.REARING_HOURS, "momentum_since": None, "effects": None, "static": None, "ver": -1, "parked": False, "finished": None}

    # ---------------------------------------------------------------- time
    def _establish_due(self):
        for s, c in self.colonies.items():
            if c["rearing_until"] is not None and self.t >= c["rearing_until"] - 1e-9:
                self._effects(s, c)
                pop = wd.FOUNDING_POPULATION + c["static"]["founding"]
                c["rearing_until"] = None
                c["pop"] = float(pop)
                c["momentum_since"] = self.t
                self.insight += wm.insight_between(wd.FOUNDING_POPULATION, pop)

    def _update_gates(self):
        w = self.wildlife()
        for m in MILESTONES:
            if m not in self.milestones and w >= m:
                self.milestones[m] = self.t
        if self.fluid_ready["common"] is None and wd.EXOTIC_HUSBANDRY_WILDLIFE in self.milestones:
            base = self.milestones[wd.EXOTIC_HUSBANDRY_WILDLIFE]
            self.fluid_ready["common"] = base + self.sc.common_lead_h
            self.fluid_ready["refined"] = base + self.sc.refined_lead_h
        if self.mk2_ready is None and wd.HABITAT_MK2_WILDLIFE in self.milestones:
            self.mk2_ready = self.milestones[wd.HABITAT_MK2_WILDLIFE] + self.sc.mk2_lead_h
        if self.fluid_ready["deep"] is None and wd.DEEP_EXOTICS_WILDLIFE in self.milestones:
            self.fluid_ready["deep"] = self.milestones[wd.DEEP_EXOTICS_WILDLIFE] + self.sc.deep_lead_h
        if self.sc.target not in self.milestones and w >= self.sc.target:
            self.milestones[self.sc.target] = self.t

    def _rates(self):
        """{species: (rate, cap)} of colonies that can grow now."""
        others = max(0, self.established() - 1)
        out = {}
        for s, c in self.colonies.items():
            if c["rearing_until"] is not None:
                continue
            if c["parked"]:
                continue
            if c["pop"] >= FULL_POPULATION - 1e-6:
                c["finished"] = self.t
                if self.sc.park_finished:
                    c["parked"] = True
                    self.habitats_used -= 1
                continue
            effects = self._effects(s, c)
            stage = wm.stage_of(c["pop"])
            tier = 2 if self.mk2_ready is not None and self.t >= self.mk2_ready else 1
            cap = wm.capacity(stage, tier)
            if c["pop"] >= cap:
                if tier == 1 and stage == 3 and self.sc.park_finished:
                    # Mk I ceiling (175,000): park until Mk II, then rehouse first (_rehouse_waiting()).
                    c["parked"] = True
                    self.habitats_used -= 1
                continue
            gas, liquid = wm.required_fluids(s, stage, c["static"]["retain_gas"], c["static"]["retain_liquid"])
            if not (self.fluid_available(gas) and self.fluid_available(liquid)):
                c["momentum_since"] = None
                continue
            if c["momentum_since"] is None:
                c["momentum_since"] = self.t
            momentum = min(1.0, (self.t - c["momentum_since"]) / wd.MOMENTUM_RAMP_HOURS)
            out[s] = (wm.breeding_rate(s, c["pop"], effects, others, 1.0, momentum), cap)
        return out

    def _rehouse_waiting(self):
        """After Mk II, colonies parked at the Mk I ceiling take free Habitats before any revival."""
        if self.mk2_ready is None or self.t < self.mk2_ready:
            return
        for c in self.colonies.values():
            if self.habitats_used >= self.sc.habitats:
                return
            if c["parked"] and c["finished"] is None:
                c["parked"] = False
                c["momentum_since"] = self.t
                self.habitats_used += 1

    def _feed_scale(self, rates):
        if not self.sc.feed_makers:
            return 1.0
        speed = wd.FEED_MAKER_MK2_SPEED if wd.FEED_MAKER_MK2_WILDLIFE in self.milestones else 1.0
        supply = self.sc.feed_makers * wd.FEED_PER_CRAFT / wd.feed_cycle_hours(speed)
        demand = sum(r * wd.FEED_PER_BIRTH * self.colonies[s]["static"]["feed_multiplier"] for s, (r, _cap) in rates.items())
        self.feed_peak = max(self.feed_peak, demand)
        return 1.0 if demand <= supply else supply / demand

    def _next_event(self):
        times = [c["rearing_until"] for c in self.colonies.values() if c["rearing_until"] is not None]
        times += [v for v in self.fluid_ready.values() if v is not None and v > self.t]
        if self.mk2_ready is not None and self.mk2_ready > self.t:
            times.append(self.mk2_ready)
        return min(times) if times else None

    def advance(self):
        rates = self._rates()
        if rates:
            dt = MAX_DT_H
            for s, (r, _cap) in rates.items():
                if r > 0:
                    dt = min(dt, max(MIN_DT_H, MAX_GROWTH_FRACTION * self.colonies[s]["pop"] / r))
        else:
            dt = None
        event = self._next_event()
        if event is not None and event > self.t:
            dt = min(dt, event - self.t) if dt is not None else event - self.t
        if dt is None:
            return False
        scale = self._feed_scale(rates)
        for s, (r, cap) in rates.items():
            c = self.colonies[s]
            new = min(cap, c["pop"] + r * scale * dt)
            self.insight += wm.insight_between(c["pop"], new)
            c["pop"] = new
        self.t += dt
        self._establish_due()
        self._update_gates()
        return True

    # ---------------------------------------------------------------- run
    def run(self, prefix, tail):
        """Strict prefix, then the tail policy (first feasible remaining item, in order)."""
        queue = list(prefix)
        rest = [i for i in tail if i not in set(prefix)]
        self._update_gates()
        while self.t < self.sc.horizon_h and self.sc.target not in self.milestones:
            self._rehouse_waiting()
            progressed = True
            while progressed:
                progressed = False
                while queue:
                    state = self.feasible(queue[0])
                    if state == "never":
                        queue.pop(0)
                        continue
                    if state == "now":
                        self.apply(queue.pop(0))
                        progressed = True
                        continue
                    break
                if not queue:
                    for item in list(rest):
                        state = self.feasible(item)
                        if state == "never":
                            rest.remove(item)
                        elif state == "now":
                            rest.remove(item)
                            self.apply(item)
                            progressed = True
                            break
            if not self.advance():
                break
        return self.score()

    def score(self):
        if self.sc.target in self.milestones:
            return self.milestones[self.sc.target]
        return self.sc.horizon_h + (self.sc.target - self.wildlife()) / 100.0


def start_sim(scenario):
    sim = Sim(scenario)
    for s in BOOTSTRAP:
        sim._revive(s)
    return sim


def evaluate(args):
    scenario, prefix = args
    return start_sim(scenario).run(prefix, default_order(scenario)), prefix


def beam_search(scenario, width, pool):
    items = all_items(scenario)
    beam = [(evaluate((scenario, []))[0], [])]
    best = beam[0]
    for _depth in range(len(items)):
        jobs = []
        for _score, prefix in beam:
            used = set(prefix)
            for item in items:
                if item in used:
                    continue
                if item[0] == "revive_raw" and ("revive", item[1]) in used or item[0] == "revive" and ("revive_raw", item[1]) in used:
                    continue
                jobs.append((scenario, prefix + [item]))
        if not jobs:
            break
        results = pool.map(evaluate, jobs)
        results.sort(key=lambda r: (r[0], len(r[1])))
        seen = set()
        beam = []
        for score, prefix in results:
            key = (round(score, 3), tuple(sorted(prefix)))
            if key in seen:
                continue
            seen.add(key)
            beam.append((score, prefix))
            if len(beam) >= width:
                break
        print("  depth %2d: best %.0f h  %s" % (len(beam[0][1]), beam[0][0], fmt_item(beam[0][1][-1])), flush=True)
        if beam[0][0] < best[0] - 1e-6:
            best = beam[0]
        elif len(beam[0][1]) > len(best[1]) + 4:
            break
    return best


def fmt_item(item):
    return "%s %s" % item


def report(name, scenario, prefix):
    sim = start_sim(scenario)
    score = sim.run(prefix, default_order(scenario))
    print("\n== %s: %.0f h (%.1f d) to %s Wildlife" % (name, score, score / 24, format(scenario.target, ",")))
    print("   milestones: " + ", ".join("%s @ %.0f h" % (format(m, ","), t) for m, t in sorted(sim.milestones.items())))
    print("   fluids ready: " + ", ".join("%s @ %s" % (k, "-" if v is None else "%.0f h" % v) for k, v in sim.fluid_ready.items()))
    print("   peak feed demand %.0f/h (%.0f Forage/h); Insight left %.2f" % (sim.feed_peak, sim.feed_peak * wd.FORAGE_PER_CRAFT / wd.FEED_PER_CRAFT, sim.insight))
    for t, item, ins in sim.log:
        print("   %7.0f h  %-24s insight after %.2f" % (t, fmt_item(item), ins))
    pops = sorted(((c["pop"], s) for s, c in sim.colonies.items()), reverse=True)
    print("   colonies: " + ", ".join("%s %s%s" % (s, format(int(p), ","), "" if sim.colonies[s]["finished"] is None else " (full @ %.0f h)" % sim.colonies[s]["finished"]) for p, s in pops))
    print("   Mk II ready @ %s" % ("-" if sim.mk2_ready is None else "%.0f h" % sim.mk2_ready))
    return sim


def gut_order(scenario):
    head = [("revive", "hive_sentinel"), ("revive", "veil_mantle"), ("adapt", "salt_tortoise"), ("adapt", "magmatic_annelid"), ("break", "salt_tortoise")]
    return head + [i for i in default_order(scenario) if i not in head]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--habitats", type=int, default=10)
    ap.add_argument("--beam", type=int, default=6)
    ap.add_argument("--target", type=int, default=wd.HABITAT_MK2_WILDLIFE)
    ap.add_argument("--common-lead", type=float, default=72.0)
    ap.add_argument("--refined-lead", type=float, default=168.0)
    ap.add_argument("--deep-lead", type=float, default=168.0)
    ap.add_argument("--mk2-lead", type=float, default=72.0)
    ap.add_argument("--horizon", type=float, default=20000.0)
    ap.add_argument("--no-park", action="store_true", help="keep finished (350k) colonies housed")
    ap.add_argument("--feed-makers", type=int, default=2)
    ap.add_argument("--allow-unadapted", action="store_true")
    ap.add_argument("--baselines-only", action="store_true")
    args = ap.parse_args()
    scenario = Scenario(args.habitats, args.target, args.horizon, args.common_lead, args.refined_lead, args.deep_lead, args.feed_makers,
                        args.allow_unadapted, args.mk2_lead, not args.no_park)

    report("default order (rarity, founding first)", scenario, default_order(scenario))
    report("gut order (hive_sentinel, veil_mantle, salt_tortoise Breakthrough early)", scenario, gut_order(scenario))
    if args.baselines_only:
        return
    with Pool() as pool:
        print("\nbeam search (width %d):" % args.beam)
        score, prefix = beam_search(scenario, args.beam, pool)
    sim = report("beam best", scenario, prefix)
    print("\nWILDLIFE_SCHEDULES entry:\n    %d: (" % scenario.habitats)
    for _t, item, _ins in sim.log:
        print("        (%r, %r)," % item)
    print("    ),")


if __name__ == "__main__":
    main()
