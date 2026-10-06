"""
Rough time model: Plants from Field Automation (620,000 km²) to the Wildlife unlock (2,250,000),
then Plants to 5,000,000 with Wildlife sharing the Forage (docs/plans/plants_wildlife_timeline.md).

Phase A: every Forage of the full Crowncap field + garden goes into Plant Terraformers, which are
never the limit. Phase B: Wildlife takes Forage first (the planner's forage_reserve), Terraformers
get the rest. Wildlife runs the optimizer's Sim (devtools/wildlife_optimizer.py) on the
WILDLIFE_SCHEDULES entry for the Habitat count, with unlimited Feed Makers; feed is capped only by
the field's Forage. Fluids, salt, life forms, kits, cash and slots are assumed available.

Usage: python devtools/plants_wildlife_timeline.py [--forage 2831] [--habitats 16]
       (--forage defaults to field_layout.forage_per_hour() of the full crowncap layout;
        about 3x that with the Yield Amplifier always on)
"""
import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "devtools"))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "4_controlpanel", "lib"))

import field_layout as fl  # noqa: E402
import wildlife_data as wd  # noqa: E402
import wildlife_optimizer as wo  # noqa: E402

PLANTS_START = 620000          # Field Automation research
PLANTS_WILDLIFE = 2250000      # Wildlife research; Mk I Terraformers stop here
PLANTS_MK2 = 1250000           # Plant Terraformer Mk II research
PLANTS_DONE = 5000000
BANDS = ((500000, 20.0), (1250000, 5.0), (2250000, 5.0 / 3), (3500000, 1.0), (5000000, 1.0 / 3))  # (upper km², km² per Forage)
SUPPORT = {"water_t": (500000, 0.05), "salt": (1250000, 0.002), "fertilizer_potency": (2250000, 0.004)}
STARTER_FORAGE_H = 380.0       # starter block (~9,100/day) until the first Crowncap matures
RAMP_START_H, RAMP_END_H = 48.0, 120.0   # Crowncap growth time; field complete
TERRAFORMER_MK2_BATCH = 6600   # Growth Accelerant: 1 item per Mk II batch
STEP_H = 0.25
POWER_W = {"terraformer_mk1": 180, "terraformer_mk2": 900, "crop_automator": 60, "habitat_mk1": 40, "habitat_mk2": 144,
           "feed_maker_mk1": 30, "feed_maker_mk2": 60}
FEED_PER_FORAGE = wd.FEED_PER_CRAFT / wd.FORAGE_PER_CRAFT


def full_field_forage():
    cells, _reserved, garden = fl.full_layout(fl.full_chunk_count("crowncap"), "crowncap")
    return fl.forage_per_hour(cells, None, garden)


def km2_per_forage(plants):
    for upper, rate in BANDS:
        if plants < upper:
            return rate
    return 0.0


def field_at(t, full):
    if t < RAMP_START_H:
        return STARTER_FORAGE_H
    if t < RAMP_END_H:
        return STARTER_FORAGE_H + (full - STARTER_FORAGE_H) * (t - RAMP_START_H) / (RAMP_END_H - RAMP_START_H)
    return full


def phase_a(full):
    t, plants, use, marks = 0.0, float(PLANTS_START), dict.fromkeys(SUPPORT, 0.0), {}
    while plants < PLANTS_WILDLIFE:
        forage = field_at(t, full)
        for key, (start, per) in SUPPORT.items():
            if plants >= start:
                use[key] += forage * per * STEP_H
        plants += forage * km2_per_forage(plants) * STEP_H
        t += STEP_H
        for m in (1000000, PLANTS_MK2, PLANTS_WILDLIFE):
            if plants >= m:
                marks.setdefault(m, t)
    return marks, use


class SharedForageSim(wo.Sim):
    """Optimizer Sim whose feed is capped by the field; Plants take the Forage Wildlife leaves."""

    def __init__(self, scenario, forage):
        super().__init__(scenario)
        self.forage = forage
        self.plants = float(PLANTS_WILDLIFE)
        self.plants_marks = {}
        self.terra_forage = 0.0
        self.wild_forage = 0.0
        self.series = []   # (t_end, dt, wildlife Forage/h, Terraformer Forage/h, habitat W, feed maker W)
        self._feed = 0.0

    def _feed_scale(self, rates):
        demand = sum(r * wd.FEED_PER_BIRTH * self.colonies[s]["static"]["feed_multiplier"] for s, (r, _cap) in rates.items())
        self.feed_peak = max(self.feed_peak, demand)
        supply = self.forage * FEED_PER_FORAGE
        scale = 1.0 if demand <= supply else supply / demand
        self._feed = demand * scale
        return scale

    def advance(self):
        t0, self._feed = self.t, 0.0
        progressed = super().advance()
        self.step_plants(self.t - t0, self._feed / FEED_PER_FORAGE)
        return progressed

    def step_plants(self, dt, wild_forage):
        terra = max(0.0, self.forage - wild_forage) if self.plants < PLANTS_DONE else 0.0
        if self.plants < PLANTS_DONE:
            self.plants += terra * km2_per_forage(self.plants) * dt
            for m in (3500000, PLANTS_DONE):
                if self.plants >= m:
                    self.plants_marks.setdefault(m, self.t)
        self.terra_forage += terra * dt
        self.wild_forage += wild_forage * dt
        mk2 = self.mk2_ready is not None and self.t >= self.mk2_ready
        habitat_w = sum(POWER_W["habitat_mk2" if mk2 else "habitat_mk1"] + min(24.0, c["pop"] / 1000.0 * 2)
                        for c in self.colonies.values() if c["finished"] is None)
        feed_mk2 = self.wildlife() >= wd.FEED_MAKER_MK2_WILDLIFE
        busy_makers = wild_forage * FEED_PER_FORAGE / (wd.FEED_PER_CRAFT / wd.feed_cycle_hours(wd.FEED_MAKER_MK2_SPEED if feed_mk2 else 1.0))
        feed_w = busy_makers * POWER_W["feed_maker_mk2" if feed_mk2 else "feed_maker_mk1"]
        self.series.append((self.t, dt, wild_forage, terra, habitat_w, feed_w))


def window_rows(series, start, end):
    rows = [r for r in series if start <= r[0] - r[1] and r[0] <= end and r[1] > 0]
    total = sum(r[1] for r in rows)
    if not total:
        return None
    return (sum(r[2] * r[1] for r in rows) / total, max(r[2] for r in rows), sum(r[3] * r[1] for r in rows) / total)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--forage", type=float, default=None, help="full-field Forage/h (default: full crowncap layout)")
    ap.add_argument("--habitats", type=int, default=16)
    args = ap.parse_args()
    forage = args.forage or full_field_forage()

    marks, use = phase_a(forage)
    ta = marks[PLANTS_WILDLIFE]
    print("Phase A, field %.0f Forage/h (hours from Field Automation, Plants %s):" % (forage, format(PLANTS_START, ",")))
    for m, t in sorted(marks.items()):
        print("  Plants %s @ %.0f h (%.1f d)" % (format(m, ","), t, t / 24))
    print("  water %.0f t, salt %.0f; Terraformers: %d Mk I (%.0f W enabled)" % (
        use["water_t"], use["salt"], -(-forage // 400), -(-forage // 400) * POWER_W["terraformer_mk1"]))

    scenario = wo.Scenario(habitats=args.habitats, target=wo.PILLAR_WILDLIFE, horizon_h=20000.0, common_lead_h=120.0,
                           refined_lead_h=240.0, deep_lead_h=240.0, feed_makers=0, mk2_lead_h=72.0)
    sim = SharedForageSim(scenario, forage)
    for s in wo.BOOTSTRAP:
        sim._revive(s)
    schedule = wd.WILDLIFE_SCHEDULES[max(k for k in wd.WILDLIFE_SCHEDULES if k <= args.habitats)]
    sim.run(list(schedule), wo.default_order(scenario))
    while sim.plants < PLANTS_DONE and sim.t < scenario.horizon_h:   # Wildlife finished first
        sim.t += 1.0
        sim.step_plants(1.0, 0.0)

    print("\nPhase B, %d Habitats (hours from the Wildlife unlock; add %.0f h for hours from Field Automation):" % (args.habitats, ta))
    events = [("Plants %s" % format(m, ","), t) for m, t in sim.plants_marks.items()]
    events += [("Wildlife %s" % format(m, ","), t) for m, t in sim.milestones.items()]
    for name, t in sorted(events, key=lambda e: e[1]):
        print("  %-18s @ %5.0f h (%5.0f h, day %.0f from Field Automation)" % (name, t, t + ta, (t + ta) / 24))
    lowers = (0,) + tuple(upper for upper, _rate in BANDS[:-1])
    plants_alone = sum((upper - max(lower, PLANTS_WILDLIFE)) / rate
                       for lower, (upper, rate) in zip(lowers, BANDS) if upper > PLANTS_WILDLIFE) / forage
    print("  Plants 5M with all Forage (no Wildlife): %.0f h" % plants_alone)
    print("  Forage: Wildlife %.0f, Terraformers %.0f; salt %.0f, fertilizer potency %.0f, Growth Accelerant ~%.0f" % (
        sim.wild_forage, sim.terra_forage, sim.terra_forage * 0.002, sim.terra_forage * 0.004,
        4500000 / TERRAFORMER_MK2_BATCH))
    makers = sim.feed_peak / (wd.FEED_PER_CRAFT / wd.feed_cycle_hours(wd.FEED_MAKER_MK2_SPEED))
    print("  peak feed %.0f/h (%.0f Forage/h): %.1f Mk II Feed Makers; Mk II Terraformers needed: %d" % (
        sim.feed_peak, sim.feed_peak / FEED_PER_FORAGE, makers, -(-forage // 2200)))

    print("\n  window (h after unlock)   Wildlife Forage/h avg (peak)   Terraformers avg")
    for start, end in zip(range(0, 5000, 500), range(500, 5500, 500)):
        w = window_rows(sim.series, start, end)
        if w:
            print("  %5d-%5d               %6.0f (%5.0f)                  %6.0f" % (start, end, *w))

    rows = [r for r in sim.series if r[1] > 0]
    total_h = sum(r[1] for r in rows)
    terra_w = [r[3] / 2200.0 * POWER_W["terraformer_mk2"] for r in rows]
    autom_w = 8 * POWER_W["crop_automator"]
    avg = sum((r[4] + r[5] + tw + autom_w) * r[1] for r, tw in zip(rows, terra_w)) / total_h
    peak = max(r[4] for r in rows) + max(r[5] for r in rows) + -(-forage // 2200) * POWER_W["terraformer_mk2"] + autom_w
    print("\n  power (Habitats + Feed Makers + Terraformers + 8 Crop Automators): avg %.0f W, coincident peak %.0f W" % (avg, peak))
    seeds_h = forage / (60 * 15)
    print("  life forms: Crowncap seeds %.1f/h = %.1f t/h; feed forms avg %.1f t/h, peak %.1f t/h" % (
        seeds_h, seeds_h * 3, sim.wild_forage / max(1.0, sim.t) / wd.FORAGE_PER_CRAFT * 3,
        max(r[2] for r in rows) / wd.FORAGE_PER_CRAFT * 3))


if __name__ == "__main__":
    main()
