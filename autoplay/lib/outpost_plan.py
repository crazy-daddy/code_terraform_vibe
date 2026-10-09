# Proposals of the outpost founding planner (docs/plans/outpost_founding_planner.md):
# turns the need model (outpost_needs.plan_hosts()) and the site search
# (outpost_sites.rank_sites()) into at most MAX_PROPOSALS proposals, shows each
# as a map marker and reads the operator's answer back from it.
#
# Archive autoplay.outpost_proposals {proposal_id: entry}, rewritten only on change:
#   kind      "found" (new outpost at x, y) or "designate" (roles onto an
#             existing outpost, `outpost`)
#   x, y      anchor (NW corner); a designate sits on its outpost's anchor
#   roles, needs, ores, urgency, why, lock (bundle biome lock), biome (at x, y)
#   score, confidence, survey, over_cap, price (kit price, 0 for designate)
#   status    proposed | approved | built | rejected
#   ok        the marker label holds the word OK
#   moved     the operator dragged the marker: x, y are theirs and are kept
#   blocked   reason the anchor fails placement (check()), else None
#   placed    the marker was placed once (a missing marker then = rejected)
#   tick      proposed / rejected at
# Proposal ids: "d-<outpost>" (designate), "f-<biome lock | mining | general>"
# (found, one per founding bundle). A rejected entry is kept under
# "<id>~<tick>" for REJECT_HOLD_TICKS: a rejected designation holds its
# (role, outpost) pairs out of plan_hosts() ("refused"), a rejected site holds
# anchors within REJECT_RADIUS_M for the same bundle.
#
# Map markers (id MARKER_PREFIX + proposal id) are the approval UI:
#   approve  add OK to the label (whole word, any case); approval needs the
#            anchor to pass placement, no survey pending and no over-cap bundle
#   move     drag the marker: the anchor is re-checked and re-scored, a
#            failed check goes into the note and blocks approval
#   reject   delete the marker
# The planner re-places a marker only when its content changes, keeps an
# operator label holding OK, and removes markers of proposals that drop out.
# An approved designate writes its roles into autoplay.outpost_roles at once
# (status built). An approved found proposal stays approved; nothing is
# bought or queued yet.
#
# Survey requests (survey_requests.REQUESTS_KEY, rewritten only on change):
# every open found proposal whose site wants a survey first asks the scouts
# for its area, centred on the placement square, radius = the widest scoring
# range of its bundle (BIOSITE_RANGE_M when not known). Its id is the proposal
# id; it goes once the proposal is approvable, built, rejected or dropped.

from swallow import swallowed
from archive import archive
from atomic import run_batched
from game_clock import is_fresh
import autoplay_roles
import outpost_needs
import outpost_sites
from outpost_needs import URGENCIES, needs, plan_hosts, log_plan
from outpost_sites import REFINE_TOP, DETAIL_CHUNK, check, score, detail_slice, prepare, prepare_want, wants
from outpost_sites import rank_sites, log_sites, read_world
from infra_topology import Topology
from grid_geom import tile_xy
import survey_requests
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_console import TreeConsole

PROPOSALS_KEY = "autoplay.outpost_proposals"
MARKER_PREFIX = "autoplay.outpost."
MARKER_LABEL = "Outpost Suggestion"
KIT_ID = "outpost_kit"
MAX_PROPOSALS = 5
MAX_REJECTED = 10            # rejected entries kept on hold, newest first
REJECT_HOLD_TICKS = 864000   # 24 sim hours a rejected proposal stays out
REJECT_RADIUS_M = 100        # a rejected site holds anchors this close for its bundle
REPLAN_TICKS = 6000          # needs re-read at least this often while only watching markers
RERANK_TICKS = 36000         # sites re-ranked at least this often with an unchanged need set
MOVE_EPS_M = 0.5             # marker offset that counts as a drag
LABEL_MAX = 48
NOTE_MAX = 240
OPEN = ("proposed", "approved")


def _rank(urgency):
    return URGENCIES.index(urgency) if urgency in URGENCIES else len(URGENCIES)


def _dist(ax, ay, bx, by):
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def safe_id(text):
    """Marker-safe id part: letters, digits, `_`, `.`, `:`, `-` kept, others as `_`; at most 40 characters."""
    out = ""
    for ch in str(text):
        out += ch if ch.isalnum() or ch in "_.:-" else "_"
    return out[:40]


def marker_id(proposal_id):
    return MARKER_PREFIX + proposal_id


def ok_label(label):
    """True when the label holds the word OK (any case, delimited by anything but letters and digits)."""
    word = ""
    for ch in str(label or "") + " ":
        if ch.isalnum():
            word += ch
        else:
            if word.upper() == "OK":
                return True
            word = ""
    return False


def bundle_key(bundle):
    """Stable key of a founding bundle: its biome lock, else mining / general."""
    if bundle.get("biome"):
        return bundle["biome"]
    return "mining" if "mining" in bundle.get("needs", []) else "general"


# --- holds ---

def held(proposals, tick):
    """Rejected entries still on hold."""
    return [entry for entry in proposals.values()
            if entry.get("status") == "rejected" and is_fresh(entry, tick, REJECT_HOLD_TICKS)]


def refused_pairs(proposals, tick):
    """[[role, outpost_id], ...] of held designate rejections (outpost_needs snapshot "refused")."""
    out = []
    for entry in held(proposals, tick):
        if entry.get("kind") == "designate":
            for role in entry.get("needs", []):
                pair = [role, entry.get("outpost")]
                if pair not in out:
                    out.append(pair)
    return out


def pick_site(rows, proposal_id, proposals, tick):
    """First ranked row not within REJECT_RADIUS_M of a held rejected site of the same proposal; None without one."""
    holds = [entry for entry in held(proposals, tick) if entry.get("id") == proposal_id]
    for row in rows:
        if not any(_dist(row["x"], row["y"], entry["x"], entry["y"]) < REJECT_RADIUS_M for entry in holds):
            return row
    return None


def survey_areas(proposals, radius_of):
    """
    {proposal_id: {"x", "y", "radius", "why"}} survey requests of the open
    found proposals that want a survey; radius_of(entry) = scoring radius.
    """
    out = {}
    for pid, entry in open_entries(proposals):
        if entry["kind"] != "found" or not entry.get("survey"):
            continue
        cx, cy = outpost_sites.centre(entry["x"], entry["y"])
        out[pid] = {"x": float(cx), "y": float(cy), "radius": float(radius_of(entry)),
                    "why": f"outpost proposal {pid}: {', '.join(entry['roles'])}"[:120]}
    return out


# --- proposals ---

def designate_proposal(item, entry, tick):
    """Proposal of one plan_hosts() designate item on outpost snapshot `entry`."""
    return {"id": "d-" + safe_id(item["outpost"]), "kind": "designate", "outpost": item["outpost"],
            "x": float(entry["x"]), "y": float(entry["y"]), "biome": entry.get("biome"), "lock": None,
            "roles": list(item["roles"]), "needs": list(item["needs"]), "ores": [], "urgency": item["urgency"],
            "why": list(item["why"]), "score": None, "confidence": 1.0, "survey": False, "over_cap": False,
            "price": 0, "status": "proposed", "ok": False, "moved": False, "blocked": None, "placed": False,
            "tick": tick}


def found_proposal(bundle, row, price, tick):
    """Proposal of one founding bundle at ranked site `row`."""
    return {"id": "f-" + safe_id(bundle_key(bundle)), "kind": "found", "outpost": None,
            "x": float(row["x"]), "y": float(row["y"]), "biome": row.get("biome"), "lock": bundle.get("biome"),
            "roles": list(bundle["roles"]), "needs": list(bundle["needs"]), "ores": list(bundle.get("ores", [])),
            "urgency": bundle["urgency"], "why": list(bundle["why"]), "score": round(row["score"], 1),
            "confidence": round(row["confidence"], 2), "survey": bool(row.get("survey")),
            "over_cap": bool(bundle.get("over_cap")), "price": price, "status": "proposed", "ok": False,
            "moved": False, "blocked": None, "placed": False, "tick": tick}


def fresh_proposals(plan, outposts, ranked, price, proposals, tick):
    """
    {proposal_id: entry} of every proposal the plan makes now: one per
    designate item, one per founding bundle with a ranked site off hold.
    ranked: {bundle_key: rank_sites() rows}.
    """
    by_id = {entry["id"]: entry for entry in outposts}
    out = {}
    for item in plan.get("designate", []):
        entry = by_id.get(item["outpost"])
        if entry is not None:
            proposal = designate_proposal(item, entry, tick)
            out[proposal["id"]] = proposal
    for bundle in plan.get("found", []):
        pid = "f-" + safe_id(bundle_key(bundle))
        row = pick_site(ranked.get(bundle_key(bundle), []), pid, proposals, tick)
        if row is not None:
            out[pid] = found_proposal(bundle, row, price, tick)
    return out


def order_key(entry):
    """Proposal order: operator OK first, then urgency, designate before found, best score."""
    return (0 if entry.get("ok") else 1, _rank(entry.get("urgency")), 0 if entry["kind"] == "designate" else 1,
            -(entry.get("score") or 0.0), entry["id"])


def merge(old, fresh, tick):
    """
    New proposals dict: the best MAX_PROPOSALS fresh proposals, each keeping
    the marker state of its open predecessor (placed, ok, moved, tick) and,
    when moved or OK'd, its anchor; plus rejected entries on hold (newest
    MAX_REJECTED). Built and dropped entries go.
    """
    out = {}
    chosen = []
    for pid, entry in fresh.items():
        new = dict(entry)
        prev = old.get(pid)
        if prev is not None and prev.get("status") in OPEN:
            for name in ("placed", "ok", "moved", "tick", "blocked"):
                new[name] = prev.get(name, new[name])
            if new["kind"] == "found" and (prev.get("moved") or prev.get("ok")):
                for name in ("x", "y", "biome", "score", "confidence", "survey"):
                    new[name] = prev.get(name, new[name])
                new["recheck"] = prev.get("recheck", False)
            new["status"] = prev["status"]
        chosen.append(new)
    for entry in sorted(chosen, key=order_key)[:MAX_PROPOSALS]:
        out[entry["id"]] = entry
    holds = sorted(held(old, tick), key=lambda entry: -entry.get("tick", 0))[:MAX_REJECTED]
    for entry in holds:
        out[entry["id"] + "~" + str(entry.get("tick", 0))] = entry
    return out


def reconcile(proposals, listing, tick):
    """
    Reads the operator's answers from the markers (listing: {marker_id:
    {"x", "y", "label"}}) into the open placed proposals: OK flag, drags
    (found only; x, y taken, recheck set), deleted marker = rejected (moved
    to a "<id>~<tick>" key). Returns [(event, proposal_id), ...].
    """
    events = []
    rejected = []
    for pid in sorted(proposals):
        entry = proposals[pid]
        if entry.get("status") not in OPEN or not entry.get("placed"):
            continue
        mark = listing.get(marker_id(pid))
        if mark is None:
            rejected.append(pid)
            events.append(("rejected", pid))
            continue
        ok = ok_label(mark["label"])
        if ok and not entry.get("ok"):
            events.append(("ok", pid))
        entry["ok"] = ok
        if entry["kind"] == "found" and _dist(mark["x"], mark["y"], entry["x"], entry["y"]) > MOVE_EPS_M:
            entry["x"] = float(mark["x"])
            entry["y"] = float(mark["y"])
            entry["moved"] = True
            entry["recheck"] = True
            events.append(("moved", pid))
    for pid in rejected:
        entry = proposals.pop(pid)
        entry["status"] = "rejected"
        entry["tick"] = tick
        entry["placed"] = False
        proposals[pid + "~" + str(tick)] = entry
    return events


def blockers(entry):
    """Reasons an open proposal cannot be approved ([] = approvable)."""
    out = []
    if entry.get("blocked"):
        out.append(entry["blocked"])
    if entry.get("recheck"):
        out.append("re-check pending")
    if entry.get("survey"):
        out.append("survey first")
    if entry.get("over_cap"):
        out.append("over the building cap")
    return out


def resolve(entry):
    """Status of an open proposal from its OK flag and blockers."""
    if entry.get("status") in OPEN:
        entry["status"] = "approved" if entry.get("ok") and not blockers(entry) else "proposed"


def pipe_tiles(log: "TreeConsole"):
    """(tx, ty) of every gas and liquid pipe and pipe job on the map (infra_topology.Topology read)."""
    occ = Topology().read(log).occ
    return [tile_xy(tile) for layer in ("gas", "liquid") for tile in occ.get(layer, {})]


def recheck(entry, ctx, want):
    """
    Placement check (and, after a drag, a re-score) of a found proposal
    against `ctx` (outpost_sites.prepare()); want = its bundle's
    prepare_want(), None to skip the re-score.
    """
    entry["blocked"] = check(ctx, entry["x"], entry["y"], entry.get("lock"), autoplay_roles.keeps_buffer(entry.get("roles", [])))
    entry["biome"] = outpost_sites.biome(ctx, entry["x"], entry["y"])
    if entry.get("recheck") and want is not None:
        if entry["blocked"] is None:
            row = run_batched(detail_slice, [score(ctx, entry["x"], entry["y"], want)], DETAIL_CHUNK, ctx, want)[0]
            entry["score"] = round(row["score"], 1)
            entry["confidence"] = round(row["confidence"], 2)
            entry["survey"] = row["confidence"] < outpost_sites.MIN_CONFIDENCE
        entry["recheck"] = False


def _fmt_price(price):
    return "price unknown" if price is None else f"{price:,} cr"


def note_text(entry):
    """Marker note: what, why, price, score and what the operator can do (NOTE_MAX characters)."""
    if entry["kind"] == "designate":
        head = f"Designate {entry['outpost']}: +{', '.join(entry['roles'])}."
    else:
        head = f"Found {entry.get('biome') or '?'}: {', '.join(entry['roles'])}."
    parts = [head, f"{entry['urgency']}: {'; '.join(entry['why'])}."]
    if entry["kind"] == "found":
        parts.append(f"{_fmt_price(entry.get('price'))}, score {entry.get('score')}, "
                     f"conf {int(round((entry.get('confidence') or 0) * 100))}%.")
    reasons = blockers(entry)
    if reasons:
        parts.append("Blocked: " + ", ".join(reasons) + ".")
    elif entry.get("status") == "approved":
        parts.append("Approved.")
    else:
        parts.append("Add OK to the label to approve.")
    text = " ".join(parts)
    return text if len(text) <= NOTE_MAX else text[:NOTE_MAX - 3] + "..."


def marker_view(entry, current_label):
    """Wanted marker fields {"x", "y", "label", "icon", "color", "note"}; an operator label holding OK is kept."""
    label = current_label if ok_label(current_label) else MARKER_LABEL
    if entry.get("status") == "approved":
        color = "success"
    elif blockers(entry):
        color = "warning"
    else:
        color = "violet" if entry["kind"] == "designate" else "accent"
    return {"x": entry["x"], "y": entry["y"], "label": label[:LABEL_MAX],
            "icon": "star" if entry["kind"] == "designate" else "flag", "color": color, "note": note_text(entry)}


def same_view(mark, view):
    """True when the marker read back already shows `view`."""
    if mark is None:
        return False
    if _dist(mark["x"], mark["y"], view["x"], view["y"]) > 0.01:
        return False
    return all(mark.get(name) == view[name] for name in ("label", "icon", "color", "note"))


def open_entries(proposals):
    return [(pid, proposals[pid]) for pid in sorted(proposals) if proposals[pid].get("status") in OPEN]


def log_events(log: "TreeConsole", events, proposals):
    """Info lines for the operator's answers (inside the caller's block)."""
    for event, pid in events:
        if event == "rejected":
            log.print(f"Outpost proposal {pid} rejected (marker deleted).")
        elif event == "moved":
            entry = proposals.get(pid) or {}
            log.print(f"Outpost proposal {pid} moved to ({entry.get('x', 0):.0f}, {entry.get('y', 0):.0f}).")
        elif event == "ok":
            log.debug(f"Outpost proposal {pid}: OK on the label.")


# --- game side ---

def _tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed("outpost_plan._tick: clock.tick", error)
        return 0


def load():
    """autoplay.outpost_proposals as {id: entry copy} ({} when missing or malformed)."""
    raw = archive.get(PROPOSALS_KEY, {})
    if not isinstance(raw, dict):
        return {}
    return {pid: dict(entry) for pid, entry in raw.items() if isinstance(entry, dict)}


def save(proposals):
    def updater(_old):
        return proposals
    archive.transaction(PROPOSALS_KEY, {}, updater)


def read_markers(markers: "Markers"):
    """{marker_id: {"x", "y", "label", "icon", "color", "note"}} of our family; None when unreadable."""
    try:
        rows = markers.list(MARKER_PREFIX) or []
    except Exception as error:
        swallowed("outpost_plan.read_markers: markers.list", error)
        return None
    out = {}
    for mark in rows:
        try:
            out[mark.id] = {"x": float(mark.x), "y": float(mark.y), "label": mark.label or "",
                            "icon": mark.icon, "color": mark.color, "note": mark.note or ""}
        except Exception as error:
            swallowed("outpost_plan.read_markers: marker read", error)
    return out


def kit_price():
    """Next outpost kit's Shop price (the catalogue's cost rises per kit owned); None when not listed."""
    shop = get_component("shop")
    if shop is None:
        return None
    try:
        for item in shop.get_catalogue() or []:
            if item.id == KIT_ID:
                return int(item.cost)
    except Exception as error:
        swallowed("outpost_plan.kit_price: shop.get_catalogue", error)
    return None


def apply_designation(entry):
    """Adds a designate proposal's roles to autoplay.outpost_roles."""
    outpost_id = entry["outpost"]
    roles = list(entry["roles"])

    def updater(current):
        if not isinstance(current, dict):
            current = {}
        names = autoplay_roles.role_list(current.get(outpost_id))
        current[outpost_id] = names + [name for name in roles if name not in names]
        return current

    archive.transaction(autoplay_roles.ROLES_KEY, {}, updater)


class OutpostPlanner:
    """
    The founding pass of planner_loop.run_planner(). run_pass(full) returns
    "locked" (no Map Markers), "idle" (no open proposal), "waiting"
    (proposals wait for the operator) or "changed" (a designation was
    written: the infrastructure passes have work). full=False only reads the
    markers (watch mode); due() says when a full pass is needed anyway.
    """

    def __init__(self, log: "TreeConsole"):
        self.log = log
        self.ctx = None
        self.ranked = {}
        self.wants = {}
        self.signature = None
        self.rank_tick = None
        self.full_tick = None
        self.locked_noted = False

    def due(self):
        return self.full_tick is None or _tick() - self.full_tick >= REPLAN_TICKS

    def run_pass(self, full=True):
        markers = get_component("markers")
        if markers is None:
            if not self.locked_noted:
                self.log.debug("Outposts: Map Markers locked (Cartography); founding proposals off.")
                self.locked_noted = True
            return "locked"
        tick = _tick()
        stored = load()
        proposals = dict([(pid, dict(entry)) for pid, entry in stored.items()])
        listing = read_markers(markers)
        if listing is None:
            self.log.debug("Outposts: markers unreadable; pass skipped.")
            return "waiting" if open_entries(proposals) else "idle"
        events = reconcile(proposals, listing, tick)
        if full:
            proposals = self._replan(proposals, tick)
        self._recheck_all(proposals, full)
        for _pid, entry in open_entries(proposals):
            resolve(entry)
        lines = []
        before = dict([(pid, entry["status"]) for pid, entry in open_entries(stored)])
        applied = 0
        for pid, entry in open_entries(proposals):
            if entry["kind"] == "designate" and entry["status"] == "approved":
                apply_designation(entry)
                entry["status"] = "built"
                applied += 1
                lines.append(f"Designated {entry['outpost']} +{entry['roles']} ({'; '.join(entry['why'])}).")
            elif entry["status"] == "approved" and before.get(pid) != "approved":
                lines.append(f"Outpost proposal {pid} approved: found {entry['roles']} at "
                             f"({entry['x']:.0f}, {entry['y']:.0f}), {_fmt_price(entry.get('price'))}.")
        calls = self._sync_markers(markers, proposals, listing, lines)
        if events or lines or calls:
            self.log.start("Outpost proposals")
            log_events(self.log, events, proposals)
            for line in lines:
                self.log.print(line)
            self.log.end(f"{len(open_entries(proposals))} open, {calls} marker change(s)")
        if proposals != stored:
            save(proposals)
        requests = survey_areas(proposals, self._radius)
        if survey_requests.write_requests(requests):
            self.log.debug(f"Outposts: survey requests now {sorted(requests)}.")
        if applied:
            return "changed"
        return "waiting" if open_entries(proposals) else "idle"

    def _replan(self, proposals, tick):
        """Needs, hosts, site ranking and the merged proposals dict."""
        snap = outpost_needs.snapshot()
        snap["refused"] = refused_pairs(proposals, tick)
        open_needs = needs(snap)
        plan = plan_hosts(open_needs, snap)
        log_plan(self.log, open_needs, plan)
        self._rank(plan, snap, tick)
        price = kit_price() if plan["found"] else None
        fresh = fresh_proposals(plan, snap["outposts"], self.ranked, price, proposals, tick)
        self.full_tick = tick
        self.log.debug(f"Outposts: {len(open_needs)} need(s), {len(plan['designate'])} designation(s), "
                       f"{len(plan['found'])} founding bundle(s), {len(fresh)} proposal(s), next kit {_fmt_price(price)}.")
        return merge(proposals, fresh, tick)

    def _rank(self, plan, snap, tick):
        """Re-ranks the founding bundles' sites when the bundles changed or RERANK_TICKS passed."""
        signature = [[bundle_key(bundle), bundle["roles"], bundle["ores"]] for bundle in plan["found"]]
        if not signature:
            self.ranked = {}
            self.signature = signature
            return
        fresh = self.rank_tick is not None and tick - self.rank_tick < RERANK_TICKS
        if signature == self.signature and self.ctx is not None and fresh:
            return
        pipes = []
        if any(autoplay_roles.keeps_buffer(bundle["roles"]) for bundle in plan["found"]):
            pipes = pipe_tiles(self.log)
            self.log.debug(f"Outposts: {len(pipes)} pipe tile(s) read for the storage buffer check.")
        world = read_world(snap["outposts"], snap["kits"], snap["range_m"], pipes)
        planet = get_component("nocturna")
        if world is None or planet is None:
            self.log.debug("Outposts: planet unreadable; sites not ranked.")
            return
        self.ctx = prepare(world, planet.biome_at)
        presets = autoplay_roles.presets()
        self.ranked = {}
        self.wants = {}
        for bundle in plan["found"]:
            key = bundle_key(bundle)
            want = prepare_want(self.ctx, wants(bundle, presets))
            self.wants[key] = want
            rows = rank_sites(bundle, self.ctx, presets, REFINE_TOP, want)
            log_sites(self.log, bundle, rows)
            self.ranked[key] = rows
        self.signature = signature
        self.rank_tick = tick

    def _want(self, entry):
        key = entry["id"][2:]
        if key not in self.wants and self.ctx is not None:
            bundle = {"roles": entry["roles"], "ores": entry.get("ores", []), "biome": entry.get("lock")}
            self.wants[key] = prepare_want(self.ctx, wants(bundle, autoplay_roles.presets()))
        return self.wants.get(key)

    def _radius(self, entry):
        """Scoring radius of a found proposal's bundle (BIOSITE_RANGE_M when its want is not prepared)."""
        want = self.wants.get(entry["id"][2:])
        return want["radius"] if want else outpost_sites.BIOSITE_RANGE_M

    def _recheck_all(self, proposals, full):
        """Placement check of every open found proposal (full pass) or only the dragged ones (watch mode)."""
        if self.ctx is None:
            return
        for pid, entry in open_entries(proposals):
            if entry["kind"] != "found" or not (full or entry.get("recheck")):
                continue
            was = entry.get("blocked")
            recheck(entry, self.ctx, self._want(entry) if entry.get("recheck") else None)
            if entry["blocked"] != was:
                self.log.debug(f"Outposts: {pid} at ({entry['x']:.0f}, {entry['y']:.0f}) "
                               f"{'blocked: ' + entry['blocked'] if entry['blocked'] else 'passes placement'}.")

    def _sync_markers(self, markers: "Markers", proposals, listing, lines):
        """
        Removes markers of proposals no longer open, places changed ones;
        returns the number of calls made. A first placement adds an info
        line to `lines`.
        """
        wanted = {}
        for pid, entry in open_entries(proposals):
            wanted[marker_id(pid)] = (pid, entry)
        calls = 0
        for mid in sorted(listing):
            if mid not in wanted:
                try:
                    markers.remove(mid)
                    calls += 1
                except Exception as error:
                    swallowed("outpost_plan._sync_markers: markers.remove", error)
        for mid in sorted(wanted):
            pid, entry = wanted[mid]
            mark = listing.get(mid)
            view = marker_view(entry, mark["label"] if mark else "")
            if same_view(mark, view):
                entry["placed"] = True
                continue
            try:
                result = markers.place(id=mid, x=view["x"], y=view["y"], label=view["label"], icon=view["icon"],
                                       color=view["color"], note=view["note"])
            except Exception as error:
                swallowed("outpost_plan._sync_markers: markers.place", error)
                continue
            calls += 1
            if getattr(result, "status", "") == "ok":
                if not entry.get("placed"):
                    lines.append(f"Outpost proposal {pid}: {view['note']}")
                entry["placed"] = True
            else:
                self.log.debug(f"Outposts: marker {mid} not placed ({getattr(result, 'status', '?')} "
                               f"{getattr(result, 'message', '')}).")
        return calls
