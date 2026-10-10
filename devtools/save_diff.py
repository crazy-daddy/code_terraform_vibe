"""
Diff and annotate consecutive saves of one recorded run (docs/plans/save_database.md, phases 2-3).

    python devtools/save_diff.py RUN_DIR --out DIR   # every pair of kept saves in RUN_DIR/saves
    python devtools/save_diff.py A.json.gz B.json.gz # one pair, report to stdout

RUN_DIR is a devtools/decision_recorder.py run folder (saves/, events.jsonl, KEEP.md).
Per pair the report lists what changed (buildings per outpost against the building cap,
tiers, tech, orders, purchases, power, fluids, running scripts, stock) and matches each
owner reason recorded between the two saves to the change rows it explains. Decision
rows no reason explains are listed as "unexplained": the decision points the planners
have to cover. State rows (power, fluids, scripts, stock) are facts, never unexplained.

Reads saves only. Reports carry save details: write them to private storage (project
files, the private internals submodule), never into this repo.
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEVTOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(DEVTOOLS))

import decision_recorder as recorder  # noqa: E402
from savefile import load_save  # noqa: E402

GAME_SPEC = DEVTOOLS.parent / "tests" / "game_spec.json"
HOME = "outpost_home"
# Building cap (simworker Ky(), e1986ce): home 25, founded 20, +5 Outpost Expansion, +1 Weather program at home.
HOME_CAP, FOUNDED_CAP, EXPANSION_BONUS, WEATHER_BONUS = 25, 20, 5, 1
EXPANSION_TECH, WEATHER_TECH = "outpost_expansion_unlock", "weather_program_unlock"
RUNNING_STATUSES = ("running", "waiting", "flushing")  # count toward the step budget (dev_workflow §1d-1)
SCARCE_MARKERS = ("salt", "uranium", "fuel_rod")  # world-limited inputs: always reported
STOCK_TOP = 12  # other stock rows: largest changes only
DECISION_SECTIONS = ("outposts", "buildings", "tiers", "infra")  # tech follows from pillar choices: a fact
SAVE_NAME = re.compile(r"^(\d+)_t(\d+)\.json(\.gz)?$")
IDENT = re.compile(r"[a-z][a-z0-9_]*")


def machine_table(path=GAME_SPEC):
    """{type_id: (counts toward the cap, penalized over the cap)} from the extracted machine table."""
    rows = json.loads(Path(path).read_text("utf-8"))["machines"]
    return {t: (r.get("building") is True, r.get("overcrowding") == "throughput") for t, r in rows.items()}


# ---------- pure part (tested) ----------

def building_cap(outpost_id, tech):
    home = outpost_id == HOME
    cap = HOME_CAP if home else FOUNDED_CAP
    if EXPANSION_TECH in tech:
        cap += EXPANSION_BONUS
    if home and WEATHER_TECH in tech:
        cap += WEATHER_BONUS
    return cap


def _add(d, key, n):
    d[key] = d.get(key, 0) + n


def stock_totals(state):
    """{item_id: units} in Inventory and every machine bin (Warehouses, Storage Bins)."""
    out = {}
    for slot in (state.get("inventory") or {}).get("slots") or []:
        if slot and slot.get("id"):
            _add(out, slot["id"], slot.get("count", 0))
    for m in state["machines"].values():
        for b in (m.get("bins") or {}).values():
            for st in b.get("stacks") or []:
                _add(out, st["id"], st.get("count", 0))
    return out


def summarize(save, table):
    """decision_recorder.summarize() plus caps, orders, power, fluids, scripts and stock.

    Takes a game save or a headless run's bare final_save.json state.
    """
    if "state" not in save:
        save = {"state": save}
    out = recorder.summarize(save)
    s = save["state"]
    pl, player = s["planet"], s["player"]
    tech = set(out["tech"])
    caps = {}
    for loc, types in out["counts"].items():
        if loc == recorder.MAP:
            continue
        counted = sum(n for t, n in types.items() if table.get(t, (False, False))[0])
        penalized = sum(n for t, n in types.items() if table.get(t, (False, False))[1])
        caps[loc] = {"counted": counted, "penalized": penalized, "cap": building_cap(loc, tech)}
    orders = s.get("orders") or {}
    power = pl.get("power") or {}
    fluids = {}
    for p in (pl.get("infrastructure") or {}).get("pipes") or []:
        row = fluids.setdefault(f"pipes {p.get('type')}", {"count": 0, "flowing": 0})
        row["count"] += 1
        row["flowing"] += p.get("state") == "flowing"
    for m in s["machines"].values():
        fluid = (m.get("stringData") or {}).get("fluid")
        data = m.get("data") or {}
        if fluid and "capacity" in data:
            row = fluids.setdefault(f"tanks {fluid}", {"count": 0, "level": 0, "capacity": 0})
            row["count"] += 1
            row["level"] += data.get("level", 0)
            row["capacity"] += data["capacity"]
    scripts = {}
    for sc in (s.get("scripts") or {}).values():
        _add(scripts, sc.get("status") or "?", 1)
    out.update({
        "credits_earned": player.get("totalCreditsEarned"),
        "credits_spent": player.get("totalCreditsSpent"),
        "caps": caps,
        "orders_done": list(orders.get("completed") or []),
        "weekly_done": sum((d or {}).get("completedCount", 0) for d in (orders.get("docks") or {}).values()),
        "power": {sid: {k: sub.get(k, 0) for k in ("generated", "consumed", "stored", "capacity")}
                  for sid, sub in (power.get("subnets") or {}).items()},
        "fluids": fluids,
        "scripts": scripts,
        "running": sum(scripts.get(k, 0) for k in RUNNING_STATUSES),
        "stock": stock_totals(s),
        "purchased": dict(player.get("purchasedItemCounts") or {}),
    })
    return out


def _row(section, text, *keys):
    return {"section": section, "text": text, "keys": sorted(k for k in keys if k)}


def diff_rows(a, b):
    """Change rows between two summaries: {section, text, keys}; keys name what the row is about."""
    rows = []
    for oid in sorted(set(b["outposts"]) - set(a["outposts"])):
        rows.append(_row("outposts", f"new outpost {oid} ({b['outposts'][oid]})", oid))
    for oid in sorted(set(a["outposts"]) - set(b["outposts"])):
        rows.append(_row("outposts", f"outpost gone {oid}", oid))
    for loc in sorted(set(a["caps"]) | set(b["caps"])):
        ca, cb = a["caps"].get(loc), b["caps"].get(loc)
        if cb and (not ca or (ca["counted"], ca["cap"]) != (cb["counted"], cb["cap"])):
            was = f"{ca['counted']}/{ca['cap']}" if ca else "-"
            over = " OVER CAP" if cb["counted"] > cb["cap"] and cb["penalized"] else ""
            rows.append(_row("caps", f"{loc}: {was} -> {cb['counted']}/{cb['cap']} buildings"
                                     f" ({cb['penalized']} penalized){over}", loc))
    for loc in sorted(set(a["counts"]) | set(b["counts"])):
        ta, tb = a["counts"].get(loc, {}), b["counts"].get(loc, {})
        for t in sorted(set(ta) | set(tb)):
            if ta.get(t, 0) != tb.get(t, 0):
                rows.append(_row("buildings", f"{loc}: {t} {ta.get(t, 0)} -> {tb.get(t, 0)}", f"{loc}/{t}", t))
    for key in sorted(set(a["tiers"]) | set(b["tiers"])):
        na, nb = a["tiers"].get(key, 0), b["tiers"].get(key, 0)
        if na != nb:
            rows.append(_row("tiers", f"{key} {na} -> {nb}", key.split("@")[0]))
    for t in sorted(set(b["tech"]) - set(a["tech"])):
        rows.append(_row("tech", f"tech {t}", t))
    for o in [o for o in b["orders_done"] if o not in a["orders_done"]]:
        rows.append(_row("orders", f"order done {o}", o))
    if b["weekly_done"] != a["weekly_done"]:
        rows.append(_row("orders", f"supply dock orders done {a['weekly_done']} -> {b['weekly_done']}"))
    for item in sorted(set(a["purchased"]) | set(b["purchased"])):
        n = b["purchased"].get(item, 0) - a["purchased"].get(item, 0)
        if n:
            rows.append(_row("purchases", f"bought {n} {item}", item))
    for k in sorted(set(a["infra"]) | set(b["infra"])):
        na, nb = a["infra"].get(k, 0), b["infra"].get(k, 0)
        if na != nb:
            rows.append(_row("infra", f"{k} {na} -> {nb}", k))
    if a["blueprints"] != b["blueprints"]:
        rows.append(_row("infra", f"blueprints {a['blueprints']} -> {b['blueprints']}", "blueprints"))
    sugg = []
    recorder._diff_suggestions(a, b, sugg, sugg)
    rows += [_row("proposals", line) for line in sugg]
    rows += _state_rows(a, b)
    return rows


def _state_rows(a, b):
    rows = []
    for sid in sorted(set(a["power"]) | set(b["power"])):
        pa, pb = a["power"].get(sid), b["power"].get(sid)
        if not pb:
            rows.append(_row("power", f"{sid} gone"))
            continue
        was = f"{pa['generated']:.0f}/{pa['consumed']:.0f} W" if pa else "-"
        rows.append(_row("power", f"{sid}: generated/consumed {was} -> {pb['generated']:.0f}/{pb['consumed']:.0f} W,"
                                  f" stored {pb['stored']:.0f}/{pb['capacity']:.0f} Wh"))
    for k in sorted(set(a["fluids"]) | set(b["fluids"])):
        fa, fb = a["fluids"].get(k), b["fluids"].get(k)
        if fa != fb:
            rows.append(_row("fluids", f"{k}: {_fluid(fa)} -> {_fluid(fb)}"))
    if (a["running"], sum(a["scripts"].values())) != (b["running"], sum(b["scripts"].values())):
        rows.append(_row("scripts", f"running {a['running']} -> {b['running']}"
                                    f" (of {sum(a['scripts'].values())} -> {sum(b['scripts'].values())} scripts)"))
    deltas = {i: b["stock"].get(i, 0) - a["stock"].get(i, 0) for i in set(a["stock"]) | set(b["stock"])}
    scarce = sorted(i for i in deltas if any(m in i for m in SCARCE_MARKERS))
    rest = sorted((i for i in deltas if i not in scarce and deltas[i]), key=lambda i: (-abs(deltas[i]), i))
    for i in scarce + rest[:STOCK_TOP]:
        rows.append(_row("stock", f"{i} {a['stock'].get(i, 0)} -> {b['stock'].get(i, 0)}", i))
    return rows


def _fluid(f):
    if not f:
        return "-"
    if "flowing" in f:
        return f"{f['count']} ({f['flowing']} flowing)"
    return f"{f['count']} tanks {f['level']:.0f}/{f['capacity']:.0f}"


def line_keys(line):
    """Keys an events.jsonl change line names: identifiers, plus outpost/type for count lines."""
    keys = set(IDENT.findall(line.lower()))
    m = re.match(r"^([a-z0-9_]+): ([a-z0-9_]+) \d+ -> \d+", line)
    if m:
        keys.add(f"{m.group(1)}/{m.group(2)}")
    return keys - {"first", "last", "gone", "tech", "new", "outpost", "tier", "at", "achievement", "infra"}


def annotate(rows, events, tick_a, tick_b):
    """(notes, unexplained): each owner reason recorded in (tick_a, tick_b] with the rows it explains,
    and the decision rows no reason explains."""
    by_id = {e["id"]: e for e in events if e.get("id") is not None}
    notes = []
    for e in events:
        ref = by_id.get(e.get("ref")) if e.get("kind") == "why" else e if e.get("kind") == "note" else None
        if not ref or not (tick_a < (ref.get("tick") or 0) <= tick_b):
            continue
        lines = (ref.get("major") or []) + (ref.get("minor") or []) if e.get("kind") == "why" else []
        keys = set().union(*(line_keys(x) for x in lines)) if lines else set()
        hits = [i for i, r in enumerate(rows) if r["section"] in DECISION_SECTIONS and keys & set(r["keys"])]
        notes.append({"ref": ref.get("id"), "day": ref.get("day"), "text": e.get("text", ""),
                      "lines": lines, "rows": hits})
    explained = {i for n in notes for i in n["rows"]}
    unexplained = [i for i, r in enumerate(rows) if r["section"] in DECISION_SECTIONS and i not in explained]
    return notes, unexplained


def report(name_a, name_b, a, b, rows, notes, unexplained, keep_reason=""):
    days = (b["day"] or 0) - (a["day"] or 0)
    tp_a, tp_b = a["tp"] or 0, b["tp"] or 0
    rate = f", {(tp_b - tp_a) / days:,.0f} TP/day" if days > 0 else ""
    out = [f"# {name_a} -> {name_b}", ""]
    if keep_reason:
        out += [f"Kept because: {keep_reason}", ""]
    out += [f"- {recorder.game_time(a)} -> {recorder.game_time(b)}",
            f"- TP {tp_a:,.0f} -> {tp_b:,.0f}{rate}",
            f"- credits {a['credits'] or 0:,.0f} -> {b['credits'] or 0:,.0f}"
            f" (earned +{(b['credits_earned'] or 0) - (a['credits_earned'] or 0):,.0f},"
            f" spent +{(b['credits_spent'] or 0) - (a['credits_spent'] or 0):,.0f})",
            "- pillars " + ", ".join(f"{k} {_num(a['pillars'][k])} -> {_num(b['pillars'][k])}"
                                     for k in b["pillars"] if a["pillars"][k] != b["pillars"][k]), ""]
    sections = []
    for r in rows:
        if r["section"] not in sections:
            sections.append(r["section"])
    for sec in sections:
        out.append(f"## {sec}")
        out += [f"- {r['text']}" for r in rows if r["section"] == sec]
        out.append("")
    out.append("## Owner reasons")
    if not notes:
        out.append("- none recorded")
    for n in notes:
        hit = "; ".join(rows[i]["text"] for i in n["rows"]) or "no matching row"
        where = f"#{n['ref']} day {n['day']}"
        out.append(f"- {where}: \"{n['text']}\"")
        if n["lines"]:
            out.append(f"  - recorded: {'; '.join(n['lines'])}")
        out.append(f"  - explains: {hit}")
    out += ["", "## Unexplained decision rows"]
    out += [f"- {rows[i]['text']}" for i in unexplained] or ["- none"]
    return "\n".join(out) + "\n"


def _num(x):
    if x is None:
        return "-"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.2f}"


# ---------- I/O part ----------

def kept_saves(run):
    saves = []
    for p in (run / "saves").iterdir():
        m = SAVE_NAME.match(p.name)
        if m:
            saves.append((int(m.group(2)), p))
    return [p for _, p in sorted(saves)]


def keep_reasons(run):
    """{save stem: why} from KEEP.md's table."""
    out = {}
    path = run / "KEEP.md"
    if path.is_file():
        for line in path.read_text("utf-8").splitlines():
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) == 3 and SAVE_NAME.match(cells[0] + ".json"):
                out[cells[0]] = cells[2]
    return out


def read_events(run):
    path = run / "events.jsonl"
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def stem(p):
    return p.name.split(".json")[0]


def pair_report(pa, pb, table, events=(), keep=""):
    a, b = summarize(load_save(pa), table), summarize(load_save(pb), table)
    rows = diff_rows(a, b)
    notes, unexplained = annotate(rows, list(events), a["tick"] or 0, b["tick"] or 0)
    return report(stem(pa), stem(pb), a, b, rows, notes, unexplained, keep), len(notes), len(unexplained)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="RUN_DIR, or two save files")
    ap.add_argument("--out", help="folder for the per-pair reports (RUN_DIR mode)")
    args = ap.parse_args()
    table = machine_table()
    if len(args.paths) == 2:
        text, _, _ = pair_report(Path(args.paths[0]), Path(args.paths[1]), table)
        sys.stdout.write(text)
        return
    run = Path(args.paths[0])
    if not args.out:
        sys.exit("--out is required with a run folder")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    saves, events, keep = kept_saves(run), read_events(run), keep_reasons(run)
    index = [f"# Save pair annotations: {run.name}", "",
             "| pair | owner reasons | unexplained decision rows |", "|---|---|---|"]
    for pa, pb in zip(saves, saves[1:]):
        text, n_notes, n_unexp = pair_report(pa, pb, table, events, keep.get(stem(pb), ""))
        name = f"{stem(pa)}__{stem(pb)}.md"
        (out / name).write_text(text, "utf-8")
        index.append(f"| [{stem(pa)} -> {stem(pb)}]({name}) | {n_notes} | {n_unexp} |")
        print(f"{name}: {n_notes} reasons, {n_unexp} unexplained")
    (out / "index.md").write_text("\n".join(index) + "\n", "utf-8")


if __name__ == "__main__":
    main()
