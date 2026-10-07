"""Early-game build-order search on the headless sim (docs/plans/buildorder_search.md).

Generates macro plans (devtools/headless/policy.mjs format), runs each from a checkpoint
with devtools/headless/run.mjs, one Node process per core, and prints the Pareto front over
game hours to 150k TP (with the scout Pioneer ready), POIs discovered and net worth.

A macro plan fills the base with one pillar's generators at a time, in a given order, each up
to a target (the pillar's phase-1 cap by default: TP slope drops 13-22x past it), then keeps
the last pillar's generators for the phase-2 tail. Generators of earlier pillars are sold
(full refund) when the next pillar starts. The Charging Station is first in every keep list
(the Pioneer's home; it unlocks at O2 9 ppt), so the generators take the slots left over.

Usage: python devtools/buildorder_search.py --save devtools/headless/.cache/checkpoints/early_h2.json [--suite macro]
       python devtools/buildorder_search.py --save devtools/headless/.cache/checkpoints/early_h1.json --suite opening
       [--jobs 12] [--hours 9] [--only SUBSTRING,SUBSTRING] [--out devtools/headless/.cache/search]
"""
import argparse
import itertools
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HEADLESS = REPO / "devtools" / "headless"
TEMPLATES = REPO / "scripts" / "0_cold_boot"
LIB_TIER = REPO / "scripts" / "4_controlpanel"  # run.mjs --lib-tier: tier-4 scripts from Data Archive on

GENERATOR = {"o2": "oxygen_generator", "pressure": "pressure_generator", "heat": "temp_heater"}
CAP = {"o2": 10, "pressure": 0.3, "heat": 11}
# Unlock gates the Pioneer needs: Charging Station (O2 9), Battery Holder (Heat 12).
GATE = {"o2": 9, "pressure": 0.2, "heat": 12}
BIO = ("bio_collector", "bio_lab", "bio_exchange")
FILL = 25  # "as many as the free slots allow"


def run_low_priority(cmd, **kwargs):
    """subprocess.run below normal priority: runs fill every core, the desktop stays responsive."""
    if sys.platform == "win32":
        return subprocess.run(cmd, creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS, **kwargs)
    return subprocess.run(cmd, preexec_fn=lambda: os.nice(10), **kwargs)


def macro_plan(order, targets, power=(6, 3), sell_bio=False, rovers=2, industry=False):
    solar, battery = power
    stages = []
    for i, pillar in enumerate(order):
        keep = {"battery": battery, "solar_generator": solar, "charging_station": 1}
        if industry:
            # Rover ore -> ingots -> Earth Orders (Supply Dock unlocks at 110k TP).
            keep.update({"smelter": 1, "supply_dock": 1})
        if sell_bio:
            keep.update({b: 0 for b in BIO})
        for other in order:
            if other != pillar:
                keep[GENERATOR[other]] = 0
        keep[GENERATOR[pillar]] = FILL
        until = {pillar: targets[pillar]} if i < len(order) - 1 else {}
        stages.append({"until": until, "keep": keep})
    name = "%s %s pw%d/%d%s" % (">".join(order), "/".join("%g" % targets[p] for p in order), solar, battery,
                                " -bio" if sell_bio else "") + (" +ind" if industry else "")
    return {"name": name, "stages": stages, "pioneer": True, "rovers": rovers}


def candidates():
    plans = []
    for order in itertools.permutations(("pressure", "o2", "heat")):
        # Heat must reach the Battery Holder gate even when it is not the tail pillar.
        targets = dict(CAP, heat=GATE["heat"]) if order[-1] != "heat" else CAP
        for sell_bio in (False, True):
            power = (7, 4) if sell_bio else (6, 3)
            plans.append(macro_plan(order, targets, power, sell_bio))
        plans.append(macro_plan(order, targets, industry=True))
    # The current speedrun targets in the current order, as a macro plan.
    plans.append(macro_plan(("o2", "pressure", "heat"), GATE))
    return plans


# Opening buy sequences (before the stages start), for --suite opening. Each is followed by
# the best macro plan of the macro suite; the 2 O2 Generators of the h1 checkpoint are sold
# once the stages start.
H, S, B = "temp_heater", "solar_generator", "battery"
OPENINGS = {
    "power-first": [],                                      # stage keep order: batteries, solar, then heaters
    "jit": [S, H, H, H, H, S, B, H, H, H, H, S, B],          # power just ahead of the load
    "solar-first": [S, S, S, H, H, H, H, H, H, B, B],        # daytime output first, night buffer later
    "heater-rush": [S, H, H, H, H, H, H, B],                 # one panel, then all heaters
}


def opening_candidates():
    plans = []
    for name, opening in OPENINGS.items():
        for power in ((6, 3), (5, 2), (4, 2)):
            plan = macro_plan(("heat", "o2", "pressure"), dict(CAP, heat=GATE["heat"]), power)
            plan["opening"] = opening
            plan["name"] = "open:%s %s" % (name, plan["name"])
            plans.append(plan)
    return plans


def feeder_candidates():
    """O2 to 1 ppt first (Auto Feeders: the Bio-Loop starts earning), then the best macro plan."""
    plans = []
    for power in ((6, 3), (7, 4)):
        best = macro_plan(("heat", "o2", "pressure"), dict(CAP, heat=GATE["heat"]), power)
        plans.append(best)
        plans.append(dict(best, contracts=True, name="contracts " + best["name"]))
        # 2.2 ppt: 10k TP (Ship Computer) from O2 alone; 3 ppt: Earth Clearance Contracts too
        for o2 in (1, 2.2, 3):
            first = macro_plan(("o2", "heat", "o2", "pressure"), dict(CAP, heat=GATE["heat"]), power)
            first["stages"][0]["until"] = {"o2": o2}
            first["name"] = "feeders%g: %s" % (o2, best["name"])
            plans.append(first)
            solved = dict(first, contracts=True, name="contracts " + first["name"])
            plans.append(solved)
    return plans


MK2 = "pressure_upgrade_pack_mk2"
MK2_GATE = 1.2  # kPa: research_pressure_mk2_pack


def mk2_candidates():
    """The feeders2.2 plan, plus a tail from 1.2 kPa on: more power, Mk II packs (12,000 cr each, 5x output, 5x power)."""
    plans = []
    targets = dict(CAP, heat=GATE["heat"])
    for power in ((6, 3), (8, 4), (10, 5), (12, 6)):
        for sell_bio in (False,):
            for n_mk2 in (0, 4, 8, FILL):
                if n_mk2 == 0 and power != (6, 3):
                    continue
                plan = macro_plan(("o2", "heat", "o2", "pressure"), targets, (6, 3), sell_bio)
                plan["stages"][0]["until"] = {"o2": 2.2}
                body = plan["stages"][-1]
                body["until"] = {"pressure": MK2_GATE}
                tail = {"until": {}, "keep": dict(body["keep"], solar_generator=power[0], battery=power[1])}
                # Power before generators: keep order is the buy order.
                tail["keep"] = {k: tail["keep"][k] for k in ("battery", "solar_generator", *(k for k in tail["keep"] if k not in ("battery", "solar_generator")))}
                if n_mk2:
                    tail["upgrade"] = {MK2: n_mk2}
                plan["stages"].append(tail)
                plan["name"] = "mk2x%d pw%d/%d%s" % (n_mk2, power[0], power[1], " -bio" if sell_bio else "")
                plans.append(plan)
    return plans


def away_candidates():
    """Best mk2 plan (8 packs, pw10/5) with and without selling the Charging Station while the Pioneer is away."""
    plans = []
    for radius in (0, 5, 20):
        plan = [p for p in mk2_candidates() if p["name"] == "mk2x8 pw10/5"][0]
        if radius:
            plan["stationAway"] = radius
            plan["name"] += " away>%dm" % radius
        plans.append(plan)
    return plans


SUITES = {"away": away_candidates, "macro": candidates, "opening": opening_candidates, "feeders": feeder_candidates, "mk2": mk2_candidates}


def run(plan, args, out_root):
    slug = "".join(c if c.isalnum() else "_" for c in plan["name"])
    out = out_root / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan, indent=1))
    cmd = ["node", str(HEADLESS / "run.mjs"), "--save", args.save, "--deploy-templates", str(TEMPLATES),
           "--lib-tier", str(LIB_TIER), "--policy", str(out / "plan.json"), "--hours", str(args.hours), "--until-tp", "150000", "--until-pioneer",
           "--report-every", str(args.report_every), "--park", "--out", str(out)]
    with open(out / "run.out", "w") as fh:
        run_low_priority(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=HEADLESS)
    try:
        s = json.loads((out / "summary.json").read_text())
    except (OSError, ValueError):
        return {"name": plan["name"], "error": "no summary"}
    return {"name": plan["name"], "hours": s["reachedH"], "tpH": s.get("tpH"), "tp": s["tp"], "pois": s["pois"]["discovered"],
            "netWorth": s["netWorth"], "brownoutS": s["brownoutS"], "crashed": s["crashed"]}


def pareto(rows):
    ok = [r for r in rows if r.get("hours") is not None]

    def dominated(a):
        return any(b is not a and b["hours"] <= a["hours"] and b["pois"] >= a["pois"] and b["netWorth"] >= a["netWorth"]
                   and (b["hours"], -b["pois"], -b["netWorth"]) != (a["hours"], -a["pois"], -a["netWorth"]) for b in ok)
    return [r for r in ok if not dominated(r)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", required=True)
    ap.add_argument("--suite", choices=sorted(SUITES), default="macro")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--hours", type=float, default=9.0, help="cap per run (game hours); slower plans count as failed")
    ap.add_argument("--report-every", type=float, default=15, help="metrics interval (game minutes)")
    ap.add_argument("--only", default="", help="comma-separated name substrings; a plan runs if any matches")
    ap.add_argument("--out", default=str(HEADLESS / ".cache" / "search"))
    args = ap.parse_args()
    args.save = str(Path(args.save).resolve())
    only = [o for o in args.only.split(",")]
    plans = [p for p in SUITES[args.suite]() if any(o in p["name"] for o in only)]
    out_root = Path(args.out).resolve()
    print("%d plans, %d jobs" % (len(plans), args.jobs), flush=True)
    with ThreadPoolExecutor(args.jobs) as pool:
        rows = []
        for r in pool.map(lambda p: run(p, args, out_root), plans):
            rows.append(r)
            print(json.dumps(r), flush=True)
    front = {r["name"] for r in pareto(rows)}
    rows.sort(key=lambda r: (r.get("hours") is None, r.get("hours") or 0))
    print("\n%-46s %6s %6s %8s %5s %9s %s" % ("plan", "hours", "tpH", "tp", "pois", "netWorth", ""))
    for r in rows:
        if "error" in r:
            print("%-46s %s" % (r["name"], r["error"]))
            continue
        hours, tp_h = ("%.2f" % v if v is not None else "-" for v in (r["hours"], r["tpH"]))
        print("%-46s %6s %6s %8d %5d %9d %s%s" % (r["name"], hours, tp_h, r["tp"], r["pois"], r["netWorth"],
                                             "*" if r["name"] in front else "", " CRASH" if r["crashed"] else ""))
    (out_root / "results.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    sys.exit(main())
