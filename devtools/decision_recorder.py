"""
Record a manual run's decisions from the save file, outside the game (no script slot).

Polls the save's state file (the game rewrites it every 30-60 s), diffs each new write
against the last one and appends the result to a run folder
internals/sample_saves/<YYYYMMDD>_<commit>/ (start date, repo HEAD at start; private
submodule, falls back to devtools/.decision-runs/ without it). A restart resumes the run
folder that already records this save. Files:
    run.json       save id, seed, start time and commit
    events.jsonl   one record per change, note and reason (append-only); each change
                   record carries the commit seen then (scripts change during a run)
    log.md         the same, readable
    saves/         gzipped save copies (.json.gz) at major changes (and every --copy-every minutes),
                   start points for devtools/headless/run.mjs --save
    last.json      last seen summary, so a restarted recorder diffs against it

Major change (opens a "why" prompt): new outpost, outpost gone, new tech, milestone
achievement (phase_*, tp_*, biomass_*, plants_*, wildlife_*), first machine of a type,
last machine of a type gone, first machine of a type at a new tier, outpost suggestion
deleted while its proposal is still open (a rejection), OK added to a suggestion's label
(an approval). Everything else (more of an existing type, first of a type at another
outpost, infrastructure, other achievements, suggestions placed or removed by the
planner, proposal status changes) is logged as minor, without a prompt (--outpost-types-major promotes
"first of a type at an outpost").

Terminal input, any time:
    <text>        reason for the open entry; with no open entry, a free note
    #N <text>     reason for entry N (late answers are fine)
    /n <text>     free note even while an entry is open
    (empty line)  close the open entry without a reason
    /s            status      /q  quit
An open entry stays open until you answer it or the next major change arrives.

Usage: python devtools/decision_recorder.py [--save save_x | PATH] [--poll 2]
                                            [--copy-every 30] [--outpost-types-major]
Reads the save only; never writes into the game folder.
"""
import argparse
import datetime
import gzip
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

DEVTOOLS = Path(__file__).resolve().parent
REPO = DEVTOOLS.parent
SAMPLE_SAVES = REPO / "internals" / "sample_saves"
RUNS_ROOT = SAMPLE_SAVES if SAMPLE_SAVES.is_dir() else DEVTOOLS / ".decision-runs"
GAME_DIR = Path(os.environ.get("APPDATA", "")) / "io.codeterraform.game"
SAVE_FILE = re.compile(r"^save_[a-z0-9]+_[a-z0-9]+\.json$")
MILESTONE_PREFIXES = ("phase_", "tp_", "biomass_", "plants_", "wildlife_")
MAP = "map"  # machines without locationId: map-deployed pumps, drills, caps, base sensors
GAME_DAY_S = 600  # planet.clock.elapsedTime per dayNumber
SUGGESTION_PREFIX = "autoplay.outpost."  # outpost planner markers, docs/cheatsheet/autoplay.md §11j
PROPOSALS_KEY = "autoplay.outpost_proposals"
OPEN_STATUSES = ("proposed", "approved")


# ---------- pure part (tested) ----------

def summarize(save):
    """The parts of a save that decisions change, as plain JSON."""
    s = save["state"]
    pl = s["planet"]
    counts, tiers = {}, {}
    for m in s["machines"].values():
        loc = m.get("locationId") or MAP
        t = m["typeId"]
        counts.setdefault(loc, {})
        counts[loc][t] = counts[loc].get(t, 0) + 1
        tier = (m.get("data") or {}).get("tier")
        if tier is not None:
            key = f"{t}@{tier}"
            tiers[key] = tiers.get(key, 0) + 1
    infra = pl.get("infrastructure") or {}
    clock = pl.get("clock") or {}
    rates = s.get("researchRates") or {}
    markers = (s.get("mapAnnotations") or {}).get("markers") or {}
    entry = ((s.get("notebook") or {}).get("entries") or {}).get(PROPOSALS_KEY) or {}
    proposals = entry.get("value") if isinstance(entry, dict) else None
    return {
        "write_seq": save.get("writeSequence"),
        "tick": s.get("tickCount"),
        "playtime": s.get("playtime"),
        "day": clock.get("dayNumber"),
        "day_frac": clock.get("normalized"),
        "credits": s["player"].get("credits"),
        "tp": (rates.get("terraform") or {}).get("lastValue"),
        "pillars": {
            "heat": (pl.get("temperature") or {}).get("heatUnits"),
            "o2": (pl.get("atmosphere") or {}).get("oxygen"),
            "pressure": (pl.get("atmosphere") or {}).get("pressure"),
            "biomass": (pl.get("biomass") or {}).get("totalTons"),
            "plants": (pl.get("plants") or {}).get("km2"),
            "wildlife": (pl.get("wildlife") or {}).get("population"),
        },
        "outposts": {o["id"]: o.get("name", o["id"]) for o in pl.get("outposts", [])},
        "tech": sorted(s.get("unlockedTech", [])),
        "achievements": sorted(s["player"].get("unlockedAchievements", [])),
        "counts": counts,
        "tiers": tiers,
        "infra": {k: len(v) for k, v in infra.items() if isinstance(v, (list, dict))},
        "blueprints": len(pl.get("constructionBlueprints", [])),
        "suggestions": {k[len(SUGGESTION_PREFIX):]: {"label": v.get("label", ""), "note": v.get("note", "")}
                        for k, v in markers.items() if k.startswith(SUGGESTION_PREFIX)},
        "proposals": {k: p.get("status") for k, p in (proposals or {}).items() if isinstance(p, dict)},
    }


def _totals(counts):
    out = {}
    for per_loc in counts.values():
        for t, n in per_loc.items():
            out[t] = out.get(t, 0) + n
    return out


def diff(old, new, outpost_types_major=False):
    """(major, minor) lists of short change strings between two summaries."""
    major, minor = [], []
    for oid in sorted(set(new["outposts"]) - set(old["outposts"])):
        major.append(f"new outpost {oid} ({new['outposts'][oid]})")
    for oid in sorted(set(old["outposts"]) - set(new["outposts"])):
        major.append(f"outpost gone {oid}")
    for t in sorted(set(new["tech"]) - set(old["tech"])):
        major.append(f"tech {t}")
    for a in sorted(set(new["achievements"]) - set(old["achievements"])):
        (major if a.startswith(MILESTONE_PREFIXES) else minor).append(f"achievement {a}")

    old_tot, new_tot = _totals(old["counts"]), _totals(new["counts"])
    for t in sorted(set(new_tot) - set(old_tot)):
        major.append(f"first {t}")
    for t in sorted(set(old_tot) - set(new_tot)):
        major.append(f"last {t} gone")
    for key in sorted(set(new["tiers"]) - set(old["tiers"])):
        t, tier = key.split("@")
        if t in old_tot:  # a brand-new type is already reported as "first"
            major.append(f"first {t} at tier {tier}")

    for loc in sorted(set(old["counts"]) | set(new["counts"])):
        o, n = old["counts"].get(loc, {}), new["counts"].get(loc, {})
        for t in sorted(set(o) | set(n)):
            a, b = o.get(t, 0), n.get(t, 0)
            if a == b:
                continue
            line = f"{loc}: {t} {a} -> {b}"
            if a == 0 and t in old_tot and loc != MAP:
                (major if outpost_types_major else minor).append(f"{line} (first at outpost)")
            else:
                minor.append(line)
    for key in sorted(set(old["tiers"]) | set(new["tiers"])):
        a, b = old["tiers"].get(key, 0), new["tiers"].get(key, 0)
        if a != b and key in old["tiers"]:
            minor.append(f"tier {key} {a} -> {b}")
    for k in sorted(set(old["infra"]) | set(new["infra"])):
        a, b = old["infra"].get(k, 0), new["infra"].get(k, 0)
        if a != b:
            minor.append(f"infra {k} {a} -> {b}")
    if old["blueprints"] != new["blueprints"]:
        minor.append(f"blueprints {old['blueprints']} -> {new['blueprints']}")
    _diff_suggestions(old, new, major, minor)
    return major, minor


def _has_ok(label):
    return re.search(r"\bok\b", label or "", re.I) is not None


def _diff_suggestions(old, new, major, minor):
    """Outpost planner markers: a deleted marker whose proposal is still open is the
    operator's rejection, OK added to the label the approval; the rest is the planner's."""
    o_sug, n_sug = old.get("suggestions") or {}, new.get("suggestions") or {}
    o_prop, n_prop = old.get("proposals") or {}, new.get("proposals") or {}
    for pid in sorted(set(o_sug) - set(n_sug)):
        note = o_sug[pid].get("note", "")
        if n_prop.get(pid) in OPEN_STATUSES:
            major.append(f"outpost suggestion {pid} deleted (rejected): {note}")
        else:
            minor.append(f"outpost suggestion {pid} removed by planner")
    for pid in sorted(set(n_sug) - set(o_sug)):
        minor.append(f"outpost suggestion {pid} placed: {n_sug[pid].get('note', '')}")
    for pid in sorted(set(o_sug) & set(n_sug)):
        if _has_ok(n_sug[pid].get("label")) and not _has_ok(o_sug[pid].get("label")):
            major.append(f"outpost suggestion {pid} approved (OK): {n_sug[pid].get('note', '')}")
    for pid in sorted(set(o_prop) | set(n_prop)):
        a, b = o_prop.get(pid), n_prop.get(pid)
        if a != b:
            minor.append(f"proposal {pid} {a or '-'} -> {b or '-'}")


def game_time(summary):
    """'day 212 14:24, run 35.3 h' from a summary."""
    day, frac, pt = summary.get("day"), summary.get("day_frac"), summary.get("playtime")
    parts = []
    if day is not None:
        hhmm = ""
        if frac is not None:
            minutes = int(frac * 24 * 60)
            hhmm = f" {minutes // 60:02d}:{minutes % 60:02d}"
        parts.append(f"day {day}{hhmm}")
    if pt is not None:
        parts.append(f"run {pt / 3600:.2f} h")
    return ", ".join(parts)


# ---------- I/O part ----------

def resolve_save(arg):
    if arg:
        p = Path(arg)
        if not p.suffix:
            p = GAME_DIR / f"{arg}.json"
        if not p.is_file():
            sys.exit(f"save not found: {p}")
        return p
    saves = [p for p in GAME_DIR.glob("save_*.json") if SAVE_FILE.match(p.name)]
    if not saves:
        sys.exit(f"no save in {GAME_DIR}")
    return max(saves, key=lambda p: p.stat().st_mtime)


def read_save(path, tries=5):
    for _ in range(tries):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            time.sleep(0.5)  # caught mid-write: retry
    return None


def git_head():
    """(short HEAD hash, True when scripts/ or autoplay/ have uncommitted changes)."""
    def git(*args):
        r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    return git("rev-parse", "--short", "HEAD") or "nogit", bool(git("status", "--porcelain", "scripts", "autoplay"))


def run_dir(save_id, seed):
    """The run folder that already records save_id, else a new <YYYYMMDD>_<commit> one."""
    for meta in sorted(RUNS_ROOT.glob("*/run.json")):
        try:
            if json.loads(meta.read_text("utf-8")).get("save_id") == save_id:
                return meta.parent
        except (json.JSONDecodeError, OSError):
            continue
    commit, dirty = git_head()
    base = f"{datetime.date.today():%Y%m%d}_{commit}"
    d, n = RUNS_ROOT / base, 2
    while d.exists():
        d, n = RUNS_ROOT / f"{base}_{n}", n + 1
    d.mkdir(parents=True)
    meta = {"save_id": save_id, "seed": seed, "started": datetime.datetime.now().isoformat(timespec="seconds"),
            "commit": commit, "scripts_dirty": dirty}
    (d / "run.json").write_text(json.dumps(meta, indent=1), "utf-8")
    return d


class Recorder:
    def __init__(self, save_path, copy_every_min, outpost_types_major, seed=None):
        self.save_path = save_path
        self.save_id = save_path.stem
        self.dir = run_dir(self.save_id, seed)
        (self.dir / "saves").mkdir(parents=True, exist_ok=True)
        self.events = self.dir / "events.jsonl"
        self.log = self.dir / "log.md"
        self.last_path = self.dir / "last.json"
        self.copy_every_s = copy_every_min * 60
        self.outpost_types_major = outpost_types_major
        self.last = json.loads(self.last_path.read_text("utf-8")) if self.last_path.exists() else None
        self.next_id = self._max_id() + 1
        self.open_id = None
        self.last_copy = 0.0

    def _max_id(self):
        if not self.events.exists():
            return 0
        best = 0
        for line in self.events.read_text("utf-8").splitlines():
            try:
                best = max(best, json.loads(line).get("id") or 0)
            except json.JSONDecodeError:
                pass
        return best

    def _append(self, rec, md):
        with open(self.events, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(md + "\n")

    def _copy(self, eid, summary):
        # gzip: ~10x smaller (repeated console history); run.mjs and co. read it via savefile.
        name = f"{eid:04d}_t{summary['tick']}.json.gz"
        with open(self.save_path, "rb") as src, gzip.open(self.dir / "saves" / name, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        self.last_copy = time.time()
        return f"saves/{name}"

    def _stamp(self, summary):
        commit, dirty = git_head()
        return {
            "wall": datetime.datetime.now().isoformat(timespec="seconds"),
            "commit": commit, "scripts_dirty": dirty,
            "tick": summary["tick"], "day": summary["day"], "playtime": summary["playtime"],
            "tp": summary["tp"], "credits": summary["credits"], "pillars": summary["pillars"],
        }

    def on_save(self, summary):
        if self.last is None:
            eid = self._new_id()
            rec = {"id": eid, "kind": "start", **self._stamp(summary),
                   "counts": summary["counts"], "save": self._copy(eid, summary)}
            self._append(rec, f"\n## #{eid} start  {rec['wall']}  {game_time(summary)}  TP {summary['tp']}")
            say(f"#{eid} baseline recorded ({game_time(summary)}, TP {summary['tp']})")
        elif summary["write_seq"] == self.last.get("write_seq"):
            return
        else:
            major, minor = diff(self.last, summary, self.outpost_types_major)
            periodic = self.copy_every_s and time.time() - self.last_copy >= self.copy_every_s
            if major or minor or periodic:
                self._record(summary, major, minor, periodic)
        self.last = summary
        self.last_path.write_text(json.dumps(summary), "utf-8")

    def _new_id(self):
        eid = self.next_id
        self.next_id += 1
        return eid

    def _record(self, summary, major, minor, periodic):
        eid = self._new_id()
        save = self._copy(eid, summary) if major or periodic else None
        kind = "major" if major else "minor"
        rec = {"id": eid, "kind": kind, **self._stamp(summary), "major": major, "minor": minor,
               "save": save}
        if major:
            rec["counts"] = summary["counts"]
        head = f"\n## #{eid} {kind}  {rec['wall']}  {game_time(summary)}  TP {summary['tp']}"
        body = [f"- **{m}**" for m in major] + [f"- {m}" for m in minor]
        if save:
            body.append(f"- save: `{save}`")
        self._append(rec, "\n".join([head] + body))
        if major:
            if self.open_id is not None:
                say(f"(#{self.open_id} closed without reason)")
            self.open_id = eid
            say(f"\n#{eid}  {rec['wall'][11:]}  {game_time(summary)}  TP {summary['tp']}")
            for m in major:
                say(f"  * {m}")
            if minor:
                say(f"  + {len(minor)} minor")
            say("why> ", end="")
        # Minor changes go to the log only: printing them would cut into a reason being typed.

    def on_line(self, line):
        line = line.rstrip("\n")
        if line == "/q":
            return False
        if line == "/s":
            say(f"save {self.save_id}, next #{self.next_id}, open #{self.open_id}, "
                f"{game_time(self.last or {})}, dir {self.dir}")
            return True
        m = re.match(r"^#(\d+)\s+(.+)$", line)
        if m:
            self._why(int(m.group(1)), m.group(2))
        elif line.startswith("/n "):
            self._note(line[3:])
        elif not line.strip():
            if self.open_id is not None:
                say(f"(#{self.open_id} skipped)")
                self.open_id = None
        elif self.open_id is not None:
            self._why(self.open_id, line)
        else:
            self._note(line)
        return True

    def _why(self, eid, text):
        rec = {"id": None, "kind": "why", "ref": eid,
               "wall": datetime.datetime.now().isoformat(timespec="seconds"), "text": text}
        self._append(rec, f"- why (#{eid}, {rec['wall'][11:]}): {text}")
        if eid == self.open_id:
            self.open_id = None
        say(f"(saved for #{eid})")

    def _note(self, text):
        eid = self._new_id()
        stamp = self._stamp(self.last) if self.last else {
            "wall": datetime.datetime.now().isoformat(timespec="seconds")}
        rec = {"id": eid, "kind": "note", **stamp, "text": text}
        self._append(rec, f"\n## #{eid} note  {rec['wall']}  {game_time(self.last or {})}\n- {text}")
        say(f"(note #{eid})")


_print_lock = threading.Lock()


def say(msg, end="\n"):
    with _print_lock:
        print(msg, end=end, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--save", help="save id (save_x_y) or path to its .json; default: newest save")
    ap.add_argument("--poll", type=float, default=2.0, help="seconds between file checks")
    ap.add_argument("--copy-every", type=float, default=30.0,
                    help="also copy the save every N real minutes (0: only at major changes)")
    ap.add_argument("--outpost-types-major", action="store_true",
                    help="first machine of a type at an outpost opens a prompt too")
    a = ap.parse_args()

    path = resolve_save(a.save)
    first = read_save(path)
    seed = first["state"].get("seed") if first else None
    rec = Recorder(path, a.copy_every, a.outpost_types_major, seed)
    say(f"watching {path}\nrun dir {rec.dir}\n(text = reason/note, #N text, /n note, empty = skip, /s, /q)")

    lines = queue.Queue()

    def reader():
        for line in sys.stdin:
            lines.put(line)
        lines.put("/q")

    threading.Thread(target=reader, daemon=True).start()

    last_mtime = None
    while True:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None
        if mtime is not None and mtime != last_mtime:
            last_mtime = mtime
            save = read_save(path)
            if save is not None:
                rec.on_save(summarize(save))
        deadline = time.time() + a.poll
        while time.time() < deadline:
            try:
                line = lines.get(timeout=max(0.05, deadline - time.time()))
            except queue.Empty:
                break
            if not rec.on_line(line):
                say("bye")
                return


if __name__ == "__main__":
    main()
