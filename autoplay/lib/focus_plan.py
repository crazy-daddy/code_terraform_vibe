# Atmosphere focus of the building pass (docs/plans/building_planner.md):
# which atmosphere pillar the generators should push, and whether a pillar
# swap (lib/pillar_swap.py) is worth proposing. Pure over a game_phase
# snapshot plus the open wants; the readers at the end feed it in game.
#
# Rule (operator, run 2): first toward the research the open needs wait for,
# later keep the pillars growing evenly.
#   score(pillar) = sum over wants on that pillar of URGENCY_WEIGHT / eta hours
#                   (eta from game_phase.research_eta_ticks(); no rate yet =
#                   NO_RATE_ETA_H; floored at ETA_FLOOR_H), complete pillars 0;
#   with no want scoring, the lowest incomplete pillar by share of its target
#   scores EVEN_SCORE ("even growth").
# A swap current -> best is proposed when best scores at least
# SWAP_MARGIN[current] times the current pillar (pressure generators ramp
# up, so leaving pressure needs a larger margin; a current pillar scoring 0
# still needs best >= MIN_SWAP_SCORE), the target kit's pack can be had at
# the tier the swap would buy (pillar_swap lowers the tier while a pack is
# neither in the Shop catalogue nor in Inventory, so only a target stuck at
# Mk I below a Mk II+ current blocks; Mk IV packs are craft-only), no swap
# runs, and the early buyer is done (game_phase "cold_boot" / "early"
# phases: lib/early_buyer.py owns that order). In even-growth mode the
# lowest pillar must lag the current one by more than EVEN_LAG share points.
# Each research id counts once, whichever want names it first.
#
# Wants: {"research": research_id, "urgency": now | soon | later, "why"}.
# CHAIN_WANTS are the fixed early unlocks of docs/gameknowledge/unlock_paths.md
# (ids only; the thresholds come from research_thresholds); the planners'
# needs add theirs through wants_from_needs() (need["blocked_by"]).
#
# Archive autoplay.focus (rewritten only on change):
#   {"pillar": swap key of the pillar to push, "current": swap key of the
#    generators standing, "swap": bool, "why": [...], "scores": {key: score},
#    "mode": "research" | "even" | "done", "tick"}

import game_phase
from components import component, machine_tier
from pillar_swap import MAX_SWAP_TIER, PILLAR_LABELS, PILLARS, is_running, pack_id
from storage import inventory_count
from swallow import swallowed

FOCUS_KEY = "autoplay.focus"
PILLAR_KEYS = {"temperature": "heat", "oxygen": "o2", "pressure": "pressure"}  # TerraformPillar id -> pillar_swap key
KEY_PILLARS = {key: pillar for pillar, key in PILLAR_KEYS.items()}
URGENCY_WEIGHT = {"now": 3.0, "soon": 1.0, "later": 0.3}
HOUR_TICKS = 36000
ETA_FLOOR_H = 1.0  # a want closer than this counts as one hour away
NO_RATE_ETA_H = 48.0  # a want on a pillar with no rate yet
EVEN_SCORE = 1.0
EVEN_LAG = 10.0  # share points the lowest pillar must lag the current one by
MIN_SWAP_SCORE = 0.25  # score the best pillar needs to pull generators off a pillar scoring 0 (a "now" want within 12 h)
SWAP_MARGIN = {"pressure": 2.0, "heat": 1.5, "o2": 1.5}  # keyed on the current pillar
EARLY_PHASES = ("cold_boot", "early")
# Fixed early chain the base always waits for (unlock_paths.md); needs add the rest.
CHAIN_WANTS = (
    {"research": "research_sonar_wide", "urgency": "later", "why": "titanium sites need the Wide Sonar"},
    {"research": "research_drill_industrial", "urgency": "later", "why": "titanium ore needs the Industrial Drill"},
    {"research": "research_thermal_cap", "urgency": "later", "why": "steam power needs Thermal Caps"},
    {"research": "research_steam_turbine", "urgency": "later", "why": "steam power needs turbines"},
    {"research": "research_warehouse", "urgency": "later", "why": "bulk storage needs Warehouses"},
    {"research": "research_hydrology_survey", "urgency": "later", "why": "water needs the Hydrology Survey"},
    {"research": "research_liquid_tank", "urgency": "later", "why": "oil and water need Liquid Tanks"},
    {"research": "research_petroleum_survey", "urgency": "later", "why": "oil needs the Petroleum Survey"},
    {"research": "research_oil_generator", "urgency": "later", "why": "oil power needs the Oil Generator"},
)


def wants_from_needs(open_needs):
    """Wants of needs that name the research they wait for (need["blocked_by"])."""
    out = []
    for need in open_needs or []:
        research_id = need.get("blocked_by")
        if research_id:
            out.append({"research": research_id, "urgency": need.get("urgency", "later"), "why": f"{need.get('role')}: {need.get('why')}"})
    return out


def share(snap, pillar):
    """Share of the pillar's target reached, 0..100."""
    entry = (snap.get("pillars") or {}).get(pillar) or {}
    target = float(entry.get("target") or 0.0)
    if target <= 0:
        return 0.0
    return min(100.0, 100.0 * float(entry.get("value") or 0.0) / target)


def open_pillars(snap):
    """Swap keys of the atmosphere pillars not complete yet."""
    return [PILLAR_KEYS[pillar] for pillar in game_phase.ATMOSPHERE if not game_phase.complete(snap, pillar)]


def want_rows(snap, wants):
    """[(key, score, why)] one row per want on an open atmosphere pillar, strongest first."""
    rows = []
    seen = set()
    for want in wants:
        research_id = want.get("research")
        row = game_phase.threshold(research_id)
        if row is None or row[0] not in PILLAR_KEYS or game_phase.unlocked(snap, research_id) or research_id in seen:
            continue
        seen.add(research_id)
        key = PILLAR_KEYS[row[0]]
        if game_phase.complete(snap, row[0]):
            continue
        eta = game_phase.research_eta_ticks(snap, research_id)
        eta_h = NO_RATE_ETA_H if eta is None else eta / float(HOUR_TICKS)
        score = URGENCY_WEIGHT.get(want.get("urgency"), URGENCY_WEIGHT["later"]) / max(eta_h, ETA_FLOOR_H)
        rows.append((key, score, f"{research_id} in ~{eta_h:.1f} h ({want.get('urgency')}): {want.get('why')}"))
    rows.sort(key=lambda row: -row[1])
    return rows


def scores(snap, wants):
    """({key: score}, mode, [why]) for the open pillars: "research" wants, else "even" growth, "done" when none is open."""
    keys = open_pillars(snap)
    if not keys:
        return ({}, "done", ["every atmosphere pillar is complete"])
    totals = {key: 0.0 for key in keys}
    why = []
    for key, score, text in want_rows(snap, wants):
        if key in totals:
            totals[key] += score
            if len(why) < 3:
                why.append(text)
    if any(totals.values()):
        return (totals, "research", why)
    lowest = min(keys, key=lambda key: (share(snap, KEY_PILLARS[key]), key))
    totals[lowest] = EVEN_SCORE
    return (totals, "even", [f"even growth: {PILLAR_LABELS[lowest]} at {share(snap, KEY_PILLARS[lowest]):.0f} % of its target is lowest"])


def current_pillar(generators):
    """Swap key of the pillar with the most generators standing ({type_id: [tiers]}); None without any."""
    best = None
    for key, type_id in PILLARS.items():
        count = len(generators.get(type_id) or [])
        if count and (best is None or count > best[1] or (count == best[1] and key < best[0])):
            best = (key, count)
    return best[0] if best else None


def swap_tier(generators, current):
    """Tier the swap would buy: the current generators' highest tier, capped at MAX_SWAP_TIER."""
    tiers = generators.get(PILLARS.get(current, ""), []) or [1]
    return min(max(tiers), MAX_SWAP_TIER)


def target_tier(type_id, tier, pack_ok):
    """pillar_swap's rule: `tier`, lowered while the pack of that tier can be had neither way."""
    target = min(tier, MAX_SWAP_TIER)
    while target > 1 and not pack_ok(type_id, target):
        target -= 1
    return target


def decide(snap, wants, generators, pack_ok, swap_running=False):
    """
    {"pillar", "current", "swap", "why", "scores", "mode"}: the pillar to push
    and whether a swap current -> pillar is proposed. pack_ok(type_id, tier)
    says whether the target kit's pack of that tier can be had.
    """
    totals, mode, why = scores(snap, wants)
    current = current_pillar(generators)
    out = {"pillar": None, "current": current, "swap": False, "why": list(why), "scores": {key: round(score, 3) for key, score in totals.items()}, "mode": mode}
    if not totals:
        return out
    best = max(sorted(totals), key=lambda key: totals[key])
    out["pillar"] = best
    if current is None or best == current:
        return out
    if game_phase.phase_name(snap) in EARLY_PHASES:
        out["why"].append("early buyer owns the opening order")
        return out
    if swap_running:
        out["why"].append("a swap is running")
        return out
    score_now = totals.get(current, 0.0)
    if score_now > 0 and totals[best] < SWAP_MARGIN.get(current, 1.5) * score_now:
        out["why"].append(f"{PILLAR_LABELS[best]} not ahead of {PILLAR_LABELS[current]} by x{SWAP_MARGIN.get(current, 1.5)}")
        return out
    if score_now <= 0 and totals[best] < MIN_SWAP_SCORE:
        out["why"].append(f"{PILLAR_LABELS[best]} scores under {MIN_SWAP_SCORE}")
        return out
    if mode == "even" and current in totals:
        lag = share(snap, KEY_PILLARS[current]) - share(snap, KEY_PILLARS[best])
        if lag <= EVEN_LAG:
            out["why"].append(f"{PILLAR_LABELS[best]} lags {PILLAR_LABELS[current]} by {lag:.0f} points, under {EVEN_LAG:.0f}")
            return out
    tier = swap_tier(generators, current)
    target = target_tier(PILLARS[best], tier, pack_ok)
    if tier > 1 and target == 1:
        out["why"].append(f"{PILLAR_LABELS[best]} packs up to Mk {tier} not available")
        return out
    if target < tier:
        out["why"].append(f"{PILLAR_LABELS[best]} swap lands at Mk {target}")
    out["swap"] = True
    return out


def swap_entry(focus):
    """The BUILD-card proposal for a decided swap, or None."""
    if not focus.get("swap") or not focus.get("current") or not focus.get("pillar"):
        return None
    source, target = focus["current"], focus["pillar"]
    why = "; ".join(focus.get("why") or [])
    return {"kind": "swap", "from": source, "to": target, "outpost": None, "type_id": PILLARS[target], "provider": "focus", "why": f"focus {PILLAR_LABELS[target]} ({focus.get('mode')}): {why}", "kit_source": None, "blocked": None}


def proposal_id(focus):
    return f"focus:{focus['current']}:{focus['pillar']}"


# ---------- game readers ----------


def read_generators():
    """{generator type_id: [tier, ...]} over every outpost; {} when unreadable."""
    network = component("outpost_network")
    out = {}
    if network is None:
        return out
    try:
        for ref in network.outposts() or []:
            for type_id in PILLARS.values():
                for building in ref.buildings(type_id) or []:
                    out.setdefault(type_id, []).append(machine_tier(building.id))
    except Exception as error:
        swallowed("focus_plan.read_generators: outpost_network", error)
        return {}  # a partial count could name the wrong current pillar
    return out


def read_prices():
    shop = component("shop")
    if shop is None:
        return {}
    try:
        return {entry.id: int(entry.cost) for entry in shop.get_catalogue() or []}
    except Exception as error:
        swallowed("focus_plan.read_prices: shop.get_catalogue", error)
        return {}


def pack_available(prices):
    """pack_ok(type_id, tier) over the Shop catalogue and Inventory."""

    def ok(type_id, tier):
        item = pack_id(type_id, tier)
        return item in prices or inventory_count(item) > 0

    return ok


def run(snap, wants, tick):
    """decide() over the in-game reads; returns the focus dict with its tick."""
    focus = decide(snap, list(CHAIN_WANTS) + list(wants), read_generators(), pack_available(read_prices()), is_running())
    focus["tick"] = int(tick)
    return focus
