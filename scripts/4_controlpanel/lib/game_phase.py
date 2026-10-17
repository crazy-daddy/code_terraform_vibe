# Game phase, derived from in-game reads: which pillars are active fronts,
# which research thresholds are next, how far away they are and when they
# arrive at the current rate. Pure predicates over one snapshot (snapshot()
# reads it; tests build it), so the planners (autoplay/lib/focus_plan.py,
# outpost_needs.py, building_plan.py) and machine scripts share one rule set
# (docs/plans/building_planner.md "Phase: one shared, derived module").
#
# Snapshot:
#   {"tick", "tp",
#    "pillars": {pillar_id: {"value", "target", "next_target", "progress", "complete", "phase"}},
#    "research": set of unlocked research ids (research.unlocked()),
#    "drills": any mining drill stands (drone_upgrade.upgrade_phase_reached()),
#    "done": {"biomass", "plants", "wildlife"} completion flags of the retire modules,
#    "history": {pillar_id: [[tick, value], ...]} the HISTORY_KEY ring}
#
# Thresholds come from research_thresholds (generated from the research
# catalog); research.is_unlocked() stays the truth once one is reached. The
# rate of a pillar is the slope over its history ring, recorded by the planner
# loop through record() about every HISTORY_MIN_TICKS.

from archive import archive
from components import component
from research_thresholds import ORDER, THRESHOLDS
from swallow import swallowed

ATMOSPHERE = ("temperature", "oxygen", "pressure")
BIOSPHERE = ("biomass", "plants", "wildlife")
PILLARS = ATMOSPHERE + BIOSPHERE
HISTORY_KEY = "phase.history"  # {pillar: [[tick, value], ...]}, newest last
HISTORY_LEN = 12  # samples kept per pillar
HISTORY_MIN_TICKS = 3000  # a new sample only this long after the last one (12 samples span about 1 sim h)
BIOSPHERE_RESEARCH = "research_biosphere"
WILDLIFE_RESEARCH = "research_wildlife"
PLANTS_RESEARCH = "research_plant_terraformer"
CONTROL_ROOM_RESEARCH = "research_custom_panels"
# Phase names in order; phase_name() returns the furthest one whose condition holds.
PHASES = ("cold_boot", "early", "expansion", "biomass", "plants", "wildlife", "finish")


def value(snap, pillar):
    """Current reading of `pillar` ("tp" included); 0.0 when the pillar is not in the snapshot."""
    if pillar == "tp":
        return float(snap.get("tp") or 0.0)
    entry = (snap.get("pillars") or {}).get(pillar) or {}
    return float(entry.get("value") or 0.0)


def unlocked(snap, research_id):
    return research_id in (snap.get("research") or set())


def complete(snap, pillar):
    """True when the game reports the pillar complete, or the retire module's done flag is set."""
    entry = (snap.get("pillars") or {}).get(pillar) or {}
    return bool(entry.get("complete")) or bool((snap.get("done") or {}).get(pillar))


def drills(snap):
    return bool(snap.get("drills"))


def wildlife_unlocked(snap):
    return unlocked(snap, WILDLIFE_RESEARCH)


def biosphere_unlocked(snap):
    return unlocked(snap, BIOSPHERE_RESEARCH)


NUCLEAR_RESEARCH = "research_nuclear_program"


def nuclear_ahead(snap):
    """
    True once the Nuclear Program may be planned for: Wildlife research is
    unlocked (the program sits at the end of the TP ladder; the TP rate of the
    atmosphere phases would put it hours away) or the program itself is.
    """
    return unlocked(snap, NUCLEAR_RESEARCH) or wildlife_unlocked(snap)


def fronts(snap):
    """
    Pillars worth pushing now: "atmosphere" until every atmosphere pillar is
    complete, each biosphere pillar while its research is unlocked and it is
    not complete (biomass from Biosphere, plants from Plant Terraformer,
    wildlife from Wildlife research).
    """
    out = []
    if not all(complete(snap, pillar) for pillar in ATMOSPHERE):
        out.append("atmosphere")
    gates = {"biomass": BIOSPHERE_RESEARCH, "plants": PLANTS_RESEARCH, "wildlife": WILDLIFE_RESEARCH}
    for pillar in BIOSPHERE:
        if unlocked(snap, gates[pillar]) and not complete(snap, pillar):
            out.append(pillar)
    return out


def phase_name(snap):
    """The furthest phase reached (PHASES); fronts() tells what is still open inside it."""
    if not unlocked(snap, "research_data_archive"):
        return "cold_boot"
    if not unlocked(snap, CONTROL_ROOM_RESEARCH):
        return "early"
    if not biosphere_unlocked(snap):
        return "expansion"
    if all(complete(snap, pillar) for pillar in BIOSPHERE):
        return "finish"
    if unlocked(snap, WILDLIFE_RESEARCH):
        return "wildlife"
    if unlocked(snap, PLANTS_RESEARCH):
        return "plants"
    return "biomass"


def threshold(research_id):
    """(pillar, value) of a research id, or None for an unknown id."""
    row = THRESHOLDS.get(research_id)
    return (row[0], row[1]) if row else None


def distance(snap, research_id):
    """Pillar units left to the threshold (0.0 when reached or unlocked); None for an unknown id."""
    row = threshold(research_id)
    if row is None:
        return None
    if unlocked(snap, research_id):
        return 0.0
    return max(0.0, float(row[1]) - value(snap, row[0]))


def locked_thresholds(snap, pillar=None):
    """
    [(research_id, pillar, threshold, distance)] of research not unlocked yet
    whose threshold lies ahead of the pillar's reading, nearest first (then
    catalog order). `pillar` filters to one pillar id ("tp" allowed). A
    threshold already passed but not unlocked (the game's unlock lag) is left
    out: pushing the pillar further cannot bring it.
    """
    out = []
    for index, research_id in enumerate(ORDER):
        row = THRESHOLDS[research_id]
        if pillar is not None and row[0] != pillar:
            continue
        if unlocked(snap, research_id):
            continue
        left = float(row[1]) - value(snap, row[0])
        if left <= 0:
            continue
        out.append((left, index, research_id, row[0], row[1]))
    out.sort()
    return [(research_id, pillar_id, limit, left) for left, _index, research_id, pillar_id, limit in out]


def _samples(rows):
    """[[tick, value], ...] of the well-formed numeric rows of a history ring."""
    out = []
    for row in rows or []:
        if isinstance(row, (list, tuple)) and len(row) == 2 and isinstance(row[0], (int, float)) and isinstance(row[1], (int, float)):
            out.append([int(row[0]), float(row[1])])
    return out


def rate(snap, pillar):
    """Pillar units per tick over the history ring; None with fewer than two samples or no time span."""
    samples = _samples((snap.get("history") or {}).get(pillar))
    if len(samples) < 2:
        return None
    (tick_a, value_a), (tick_b, value_b) = samples[0], samples[-1]
    span = float(tick_b) - float(tick_a)
    if span <= 0:
        return None
    return (float(value_b) - float(value_a)) / span


def eta_ticks(snap, pillar, limit):
    """Ticks until `pillar` reaches `limit` at its history rate: 0 when reached, None when unknown or not rising."""
    left = float(limit) - value(snap, pillar)
    if left <= 0:
        return 0
    slope = rate(snap, pillar)
    if slope is None or slope <= 0:
        return None
    return int(left / slope)


def research_eta_ticks(snap, research_id):
    """eta_ticks() for a research id's threshold; 0 when unlocked, None for an unknown id or no rate."""
    row = threshold(research_id)
    if row is None:
        return None
    if unlocked(snap, research_id):
        return 0
    return eta_ticks(snap, row[0], row[1])


def with_sample(history, snap, now):
    """`history` with one sample per pillar appended when the last one is older than HISTORY_MIN_TICKS; rings cut to HISTORY_LEN."""
    out = {}
    pillars = dict(snap.get("pillars") or {})
    readings = {pillar: float(entry.get("value") or 0.0) for pillar, entry in pillars.items()}
    readings["tp"] = float(snap.get("tp") or 0.0)
    for pillar, reading in readings.items():
        ring = _samples(history.get(pillar))
        if ring and now < ring[-1][0]:
            ring = []  # the clock went back (older save loaded): the old samples would span bad data
        if not ring or now - ring[-1][0] >= HISTORY_MIN_TICKS:
            ring.append([int(now), reading])
        out[pillar] = ring[-HISTORY_LEN:]
    return out


# --- game readers (thin) ---


def read_pillars():
    """{pillar_id: fields} from terraforming.pillars(); {} when unreadable."""
    terraforming = component("terraforming")
    out = {}
    if terraforming is None:
        return out
    try:
        rows = list(terraforming.pillars() or [])
    except Exception as error:
        swallowed("game_phase.read_pillars: terraforming.pillars", error)
        return out
    for pillar in rows:
        try:
            out[str(pillar.id)] = {
                "value": float(pillar.value),
                "target": float(pillar.target),
                "next_target": None if pillar.next_target is None else float(pillar.next_target),
                "progress": float(pillar.progress),
                "complete": bool(pillar.complete),
                "phase": int(pillar.phase),
            }
        except Exception as error:
            swallowed("game_phase.read_pillars: pillar fields", error)
    return out


def read_research():
    """
    Unlocked research ids: research.unlocked(); when that fails or answers
    None, is_unlocked() over the catalog ORDER. None when neither read works
    (callers keep their last snapshot rather than reading "nothing unlocked").
    """
    research = component("research")
    if research is None:
        return None
    try:
        listed = research.unlocked()
    except Exception as error:
        swallowed("game_phase.read_research: research.unlocked", error)
        listed = None
    if listed is not None:
        return set(listed)
    out = set()
    for research_id in ORDER:
        try:
            if research.is_unlocked(research_id):
                out.add(research_id)
        except Exception as error:
            swallowed("game_phase.read_research: research.is_unlocked", error)
            return None
    return out


def read_tp():
    nocturna = component("nocturna")
    if nocturna is None:
        return 0.0
    try:
        return float(nocturna.total_tp())
    except Exception as error:
        swallowed("game_phase.read_tp: nocturna.total_tp", error)
        return 0.0


def read_history():
    raw = archive.get(HISTORY_KEY, {})
    return raw if isinstance(raw, dict) else {}


def snapshot(now, last=None):
    """The phase snapshot read in game (module header); `last` supplies the research set when the read fails."""
    from biomass_retire import biomass_complete  # imported here, not at module level: the lib import chain of the planner runs as one capped execution (dev_workflow §1d-1 "Import-time code")
    from drone_upgrade import upgrade_phase_reached
    from plants_retire import plants_complete
    from wildlife_common import wildlife_complete

    research = read_research()
    if research is None:
        research = set((last or {}).get("research") or set())
    return {
        "tick": int(now),
        "tp": read_tp(),
        "pillars": read_pillars(),
        "research": research,
        "drills": upgrade_phase_reached(),
        "done": {"biomass": biomass_complete(), "plants": plants_complete(), "wildlife": wildlife_complete()},
        "history": read_history(),
    }


def record(snap, now):
    """Append the snapshot's readings to the HISTORY_KEY rings (planner loop, once per pass); returns the new history."""
    history = with_sample(read_history(), snap, now)
    if history != snap.get("history"):
        archive.set(HISTORY_KEY, history)
        snap["history"] = history
    return history
