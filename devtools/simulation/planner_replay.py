"""
Replay the autoplay planners over the kept saves of a recorded run and compare
their proposals with what the operator did next (docs/plans/building_planner.md
"Training data", outpost_founding_planner.md "Revision 2").

    python devtools/simulation/planner_replay.py RUN_DIR [--accept] [--out DIR] [--window 3] [--no-sites]

RUN_DIR is a devtools/play/decision_recorder.py run folder (saves/, KEEP.md).
Per kept save the outpost planner (needs, hosts, site ranking), the atmosphere
focus and the building providers run over replay_snapshot.py's offline
snapshots. The real decisions between one kept save and the next come from
devtools/play/save_diff.py's change rows: new outposts, machine counts up or
down, tier counts up, generator-type shifts (pillar swaps) and fleet role
counts. Each real decision is matched against the proposals of that save or
the WINDOW saves before it:

    match    proposed at this save
    early    proposed at an earlier save within the window
    missed   no proposal in the window
    early buyer  a building or swap before the Control Room (lib/early_buyer.py owns that order)
    loose    a founding matched by any found proposal of that save (other biome)
    extra    a proposal at this save the operator never did within the window

Counts are per decision and per save, not one-to-one: N identical real deploys
all match one proposal key, a proposal that stays open over several saves is
an extra at each of them, and an action the planner first proposes one save
later counts as missed there and extra here. Read the per-save tables for the
decisions that matter; the summary ranks kinds, it is no score.

--accept carries the planner's own designations and founded outposts forward
as virtual state (roles, a virtual outpost at the best ranked site), so a
later save sees them covered; virtual deploys are not simulated.

Output: REPORT.md (per save tables, summary) in --out (default: the run folder,
planner_replay_<head>.md) and a JSON next to it. Reads saves only.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import replay_snapshot as rs  # noqa: E402  (installs the stub world and lib paths)

# isort: split
import autoplay_roles  # noqa: E402
import building_plan  # noqa: E402
import focus_plan  # noqa: E402
import outpost_needs  # noqa: E402
import outpost_sites  # noqa: E402
import save_diff  # noqa: E402
from savefile import load_save  # noqa: E402

GENERATORS = {"oxygen_generator": "o2", "temp_heater": "heat", "pressure_generator": "pressure"}
ROLE_TYPES = {
    "smelter": "smelter",
    "factory": "fabricator",
    "power": "steam_turbine",
    "terraform": None,
    "storage": None,
    "reactor": "reactor",
}


def git_head():
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=str(rs.REPO), check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


# ---------- planner run over one save ----------


def plan_save(state, sites, table, history, virtual, roles_map, rank):
    """Planner outputs for one save: needs, plan, found sites, focus, build proposals."""
    rs.load_archive(state)
    roles = dict(autoplay_roles.outpost_roles())
    roles.update(roles_map)
    snap = rs.needs_snapshot(state, table, sites, roles, history, virtual)
    needs = outpost_needs.needs(snap)
    plan = outpost_needs.plan_hosts(needs, snap)
    ranked = {}
    if rank and plan["found"]:
        world = rs.world_of(snap, sites, state)
        ctx = outpost_sites.prepare(world, rs.biome_at)
        presets = autoplay_roles.presets()
        for bundle in plan["found"]:
            rows = outpost_sites.rank_sites(bundle, ctx, presets)
            ranked[tuple(bundle["roles"])] = rows[0] if rows else None
    generators = {}
    for machine in rs.finished_machines(state):
        if machine["typeId"] in GENERATORS:
            generators.setdefault(machine["typeId"], []).append(rs.tier_of(machine))
    prices = rs.pack_prices(state)
    focus = focus_plan.decide(
        snap["phase"],
        list(focus_plan.CHAIN_WANTS) + focus_plan.wants_from_needs(needs),
        generators,
        lambda type_id, tier: focus_plan.pack_id(type_id, tier) in prices,
    )
    ctx = rs.context_of(state, snap, focus, table)
    proposals = building_plan.provider_proposals(ctx, ctx["inventory"])
    base = building_plan.fresh_proposals(snap, ctx["inventory"], {}, focus)
    base.update(proposals)
    return {"snap": snap, "needs": needs, "plan": plan, "ranked": ranked, "focus": focus, "proposals": base}


# ---------- real decisions between two saves ----------


BUILDING_ROW = re.compile(r"^(?P<loc>[^:]+): (?P<type>\S+) (?P<a>\d+) -> (?P<b>\d+)$")
TIER_ROW = re.compile(r"^(?P<type>\S+)@(?P<tier>\d+) (?P<a>\d+) -> (?P<b>\d+)$")


def real_decisions(a, b, state_b):
    """[{"kind", "what", "outpost", "type", "text"}] from save_diff rows a -> b plus generator shifts (pillar swaps)."""
    rows = save_diff.diff_rows(a, b)
    out = []
    gens = {}
    for row in rows:
        text = row["text"]
        if row["section"] == "outposts" and text.startswith("new outpost "):
            oid = row["keys"][0]
            pos = next(((o["x"], o["y"]) for o in state_b["planet"].get("outposts") or [] if o["id"] == oid), (0, 0))
            out.append({"kind": "found", "what": oid, "outpost": oid, "type": rs.biome_at(*pos), "text": text})
        elif row["section"] == "buildings":
            found = BUILDING_ROW.match(text)
            if not found:
                continue
            loc, type_id, before, after = (
                found.group("loc"),
                found.group("type"),
                int(found.group("a")),
                int(found.group("b")),
            )
            if type_id in GENERATORS:
                gens[type_id] = gens.get(type_id, 0) + (after - before)
            if loc == save_diff.recorder.MAP:
                continue
            kind = "deploy" if after > before else "retire"
            out.append(
                {"kind": kind, "what": f"{type_id} {before}->{after}", "outpost": loc, "type": type_id, "text": text}
            )
        elif row["section"] == "tiers":
            found = TIER_ROW.match(text)
            if found and int(found.group("b")) > int(found.group("a")) and int(found.group("tier")) > 1:
                out.append(
                    {"kind": "upgrade", "what": text, "outpost": None, "type": found.group("type"), "text": text}
                )
    up = [t for t, n in gens.items() if n > 0]
    down = [t for t, n in gens.items() if n < 0]
    if up and down:
        # One pillar swap: the generator rows it moved are the swap, not deploys and retires of their own.
        out = [d for d in out if d.get("type") not in GENERATORS]
        out.append(
            {
                "kind": "swap",
                "what": f"{GENERATORS[down[0]]} -> {GENERATORS[up[0]]}",
                "outpost": None,
                "type": GENERATORS[up[0]],
                "text": "pillar swap " + GENERATORS[down[0]] + " -> " + GENERATORS[up[0]],
            }
        )
    return out


def fleet_roles(state):
    counts = {}
    for name, entry in (rs.notebook(state).get("fleet.status") or {}).items():
        if isinstance(entry, dict) and entry.get("role"):
            kind = building_plan.unit_kind(name)
            if kind:
                counts[(kind, entry["role"])] = counts.get((kind, entry["role"]), 0) + 1
    return counts


def fleet_decisions(state_a, state_b):
    a, b = fleet_roles(state_a), fleet_roles(state_b)
    out = []
    for key in sorted(set(a) | set(b)):
        delta = b.get(key, 0) - a.get(key, 0)
        if delta:
            out.append(
                {
                    "kind": "fleet",
                    "what": f"{key[0]} {key[1]} {delta:+d}",
                    "outpost": None,
                    "type": f"{key[0]}:{key[1]}:{'+' if delta > 0 else '-'}",
                    "text": f"fleet {key[0]} {key[1]} {a.get(key, 0)} -> {b.get(key, 0)}",
                }
            )
    return out


# ---------- matching ----------


def proposal_keys(result):
    """Set of (kind, type) keys a save's planner output offers, with found rows keyed by biome and roles."""
    keys = set()
    for entry in result["proposals"].values():
        kind = entry.get("kind")
        if kind == "deploy":
            keys.add(("deploy", entry["type_id"]))
        elif kind == "upgrade":
            keys.add(("upgrade", entry["type_id"]))
        elif kind == "retire":
            keys.add(("retire", entry["type_id"]))
        elif kind == "swap":
            keys.add(("swap", entry["to"]))
        elif kind == "fleet":
            keys.add(("fleet", f"{entry['fleet_kind']}:{entry['role']}:{'+' if entry['delta'] > 0 else '-'}"))
    for bundle in result["plan"]["found"]:
        row = result["ranked"].get(tuple(bundle["roles"]))
        biome = bundle.get("biome") or (row.get("biome") if row else None)
        keys.add(("found", biome))
        keys.add(("found", "any"))
    for item in result["plan"]["designate"]:
        for role in item["roles"]:
            type_id = ROLE_TYPES.get(role)
            if type_id:
                keys.add(("deploy", type_id))
    return keys


def decision_key(decision):
    if decision["kind"] == "found":
        return ("found", decision["type"])
    return (decision["kind"], decision["type"])


def match(decision, offers, index, window):
    """(status, save index) of a real decision against the offers of saves [index - window, index]."""
    key = decision_key(decision)
    loose = ("found", "any") if decision["kind"] == "found" else None
    for back in range(window + 1):
        at = index - back
        if at < 0:
            break
        keys = offers[at]
        if key in keys:
            return ("match" if back == 0 else "early", at)
        if loose and loose in keys and back == 0:
            return ("match (other biome)", at)
    return ("missed", None)


def extras(result, decisions_ahead):
    """Proposal keys of this save no real decision within the window shares."""
    done = {decision_key(d) for d in decisions_ahead}
    done_kinds = {d["kind"] for d in decisions_ahead}
    out = []
    for key in sorted(proposal_keys(result), key=str):
        if key[1] == "any":
            continue
        if key in done or (key[0] == "found" and "found" in done_kinds):
            continue
        out.append(key)
    return out


# ---------- report ----------


def fmt_proposals(result):
    lines = []
    for item in result["plan"]["designate"]:
        lines.append(
            f"designate {item['outpost']} +{', '.join(item['roles'])} ({item['urgency']}): {'; '.join(item['why'])}"
        )
    for bundle in result["plan"]["found"]:
        row = result["ranked"].get(tuple(bundle["roles"]))
        site = (
            f"at ({row['x']:.0f}, {row['y']:.0f}) {row['biome']} score {row['score']:.1f}" if row else "no site ranked"
        )
        lines.append(f"found {', '.join(bundle['roles'])} ({bundle['urgency']}) {site}: {'; '.join(bundle['why'])}")
    focus = result["focus"]
    lines.append(
        f"focus {focus.get('pillar')} ({focus.get('mode')}), generators on {focus.get('current')}, swap {focus.get('swap')}: {'; '.join(focus.get('why') or [])}"
    )
    for pid in sorted(result["proposals"]):
        entry = result["proposals"][pid]
        blocked = f" [blocked: {entry['blocked']}]" if entry.get("blocked") else ""
        lines.append(f"{pid}{blocked}: {entry.get('why')}")
    return lines


def write_report(path, run, head, rows, summary, accept):
    out = [f"# Planner replay of {run.name} at {head}{' (accept mode)' if accept else ''}", ""]
    out.append(
        "Real decisions between consecutive kept saves against the planner's proposals at the earlier save (window: the saves before it)."
    )
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append("| kind | match | loose | early | missed | early buyer | extra |")
    out.append("|---|---|---|---|---|---|---|")
    for kind in sorted(summary):
        s = summary[kind]
        out.append(
            f"| {kind} | {s.get('match', 0)} | {s.get('loose', 0)} | {s.get('early', 0)} | {s.get('missed', 0)} | {s.get('early buyer', 0)} | {s.get('extra', 0)} |"
        )
    out.append("")
    for row in rows:
        out.append(f"## {row['save']} (day {row['day']}, TP {row['tp']:,.0f}, phase {row['phase']})")
        out.append("")
        out.append("Planner:")
        out.append("")
        for line in row["proposals"]:
            out.append(f"- {line}")
        out.append("")
        if row["decisions"]:
            out.append("Real decisions until the next kept save:")
            out.append("")
            out.append("| decision | verdict |")
            out.append("|---|---|")
            for decision, verdict, at in row["decisions"]:
                out.append(
                    f"| {decision['text']} | {verdict}{'' if at is None else ' (save ' + rows[at]['save'] + ')'} |"
                )
            out.append("")
        if row["extras"]:
            out.append("Proposed, not done within the window: " + ", ".join(f"{k[0]} {k[1]}" for k in row["extras"]))
            out.append("")
    path.write_text("\n".join(out) + "\n", "utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path)
    parser.add_argument(
        "--accept", action="store_true", help="carry the planner's designations and foundings forward as virtual state"
    )
    parser.add_argument("--out", type=Path, help="report folder (default: the run folder)")
    parser.add_argument("--window", type=int, default=3, help="earlier saves whose proposals still count (default 3)")
    parser.add_argument("--no-sites", action="store_true", help="skip site ranking (faster)")
    parser.add_argument("--limit", type=int, help="only the first N kept saves")
    args = parser.parse_args()
    head = git_head()
    table = rs.machine_table()
    sites = rs.mineral_sites()
    paths = save_diff.kept_saves(args.run)
    if args.limit:
        paths = paths[: args.limit]
    states = []
    summaries = []
    for path in paths:
        save = load_save(path)
        states.append(rs.state_of(save))
        summaries.append(save_diff.summarize(save, table))
    results = []
    offers = []
    history = {}
    virtual = []
    roles_map = {}
    for index, state in enumerate(states):
        readings = rs.pillar_readings(state)
        tick = int(state.get("tickCount") or 0)
        for pillar, value in readings.items():
            ring = history.setdefault(pillar, [])
            ring.append([tick, value])
            del ring[:-12]
        result = plan_save(
            state,
            sites,
            table,
            {k: [list(v) for v in ring] for k, ring in history.items()},
            list(virtual),
            dict(roles_map),
            not args.no_sites,
        )
        results.append(result)
        offers.append(proposal_keys(result))
        if args.accept:
            for item in result["plan"]["designate"]:
                roles_map[item["outpost"]] = sorted(set(roles_map.get(item["outpost"], [])) | set(item["roles"]))
            for bundle in result["plan"]["found"]:
                row = result["ranked"].get(tuple(bundle["roles"]))
                if row is None:
                    continue
                vid = f"virtual_{len(virtual) + 1}"
                virtual.append(
                    {
                        "id": vid,
                        "x": float(row["x"]),
                        "y": float(row["y"]),
                        "biome": row["biome"],
                        "home": False,
                        "roles": list(bundle["roles"]),
                        "types": {},
                        "used": 0,
                        "capacity": 20,
                    }
                )
                roles_map[vid] = list(bundle["roles"])
        print(
            f"{paths[index].name}: {len(result['needs'])} need(s), {len(result['plan']['designate'])} designation(s), {len(result['plan']['found'])} founding(s), {len(result['proposals'])} proposal(s), focus {result['focus'].get('pillar')}",
            flush=True,
        )
    rows = []
    summary = {}
    for index, result in enumerate(results):
        decisions = []
        if index + 1 < len(states):
            decisions = real_decisions(summaries[index], summaries[index + 1], states[index + 1]) + fleet_decisions(
                states[index], states[index + 1]
            )
        verdicts = []
        early_phase = building_plan.game_phase.phase_name(result["snap"]["phase"]) in ("cold_boot", "early")
        for decision in decisions:
            verdict, at = match(decision, offers, index, args.window)
            if verdict == "missed" and early_phase and decision["kind"] in ("deploy", "retire", "swap", "upgrade"):
                verdict = (
                    "early buyer"  # lib/early_buyer.py owns the base before the Control Room; the planners stay out
                )
            verdicts.append((decision, verdict, at))
            summary.setdefault(decision["kind"], {})
            bucket = (
                "early buyer"
                if verdict == "early buyer"
                else ("loose" if "other biome" in verdict else verdict.split(" ")[0])
            )
            summary[decision["kind"]][bucket] = summary[decision["kind"]].get(bucket, 0) + 1
        ahead = []
        for later in range(index, min(len(states), index + args.window + 1)):
            if later + 1 < len(states):
                ahead += real_decisions(summaries[later], summaries[later + 1], states[later + 1]) + fleet_decisions(
                    states[later], states[later + 1]
                )
        extra = extras(result, ahead) if index + 1 < len(states) else []
        for key in extra:
            summary.setdefault(key[0], {})
            summary[key[0]]["extra"] = summary[key[0]].get("extra", 0) + 1
        phase = result["snap"]["phase"]
        rows.append(
            {
                "save": save_diff.stem(paths[index]),
                "day": summaries[index].get("day"),
                "tp": summaries[index].get("tp") or 0,
                "phase": building_plan.game_phase.phase_name(phase),
                "proposals": fmt_proposals(result),
                "decisions": verdicts,
                "extras": extra,
            }
        )
    out_dir = args.out or args.run
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"planner_replay_{head}{'_accept' if args.accept else ''}"
    write_report(out_dir / (name + ".md"), args.run, head, rows, summary, args.accept)
    (out_dir / (name + ".json")).write_text(
        json.dumps(
            {
                "summary": summary,
                "saves": [
                    {
                        "save": r["save"],
                        "proposals": r["proposals"],
                        "decisions": [[d["text"], v] for d, v, _ in r["decisions"]],
                        "extras": [list(k) for k in r["extras"]],
                    }
                    for r in rows
                ],
            },
            indent=1,
        ),
        "utf-8",
    )
    print(json.dumps(summary, indent=1))
    print(f"report: {out_dir / (name + '.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
