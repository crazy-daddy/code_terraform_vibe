# One priority scale for every demand on the network, from a final product
# (Earth order, blueprint, manual order, fleet part, standing stock) down to
# the ore it needs. An integer 0-999: the hundreds digit is the band, ranked
# lexicographically (a unit of a higher band always goes first), the rest a
# fine value that only breaks ties inside a band (dock score, blueprint
# priority). Haulers rank by band only (logistics_requests.haul_rank()).
#
# The one demand shape is a ladder: [[prio, cum_units], ...], prio descending,
# cum_units non-decreasing. "At least cum units should exist; the units up to
# the first level are wanted at its prio, the next ones at the next level's."
# A request's (target, min, urgent), a Fabricator target and a Smelter demand
# are all ladders, stored as is in the archive (JSON-safe). Stock covers the
# highest level first (ladder_deficits()), so a stock top-up never rides on
# a higher band. Ladders stay short (1-4 levels); every helper is one walk.
#
# Bands, highest first. Which root writes which band: cheatsheet
# production_logistics.md "Priority bands".

BLOCKER = 900      # operations stalled: a settled unit a consumer waits on, nothing more arrives by waiting (hauling only)
MANUAL = 800       # the operator asked: manual orders, operator-placed blueprints
BUILD = 700        # autoplay construction blocking progress now
ORDER = 600        # current Earth orders a Supply Dock holds (fine = dock score or override)
UPGRADE = 500      # one-off parts a job waits on (fleet kits, modules)
NEED = 400         # a machine or role cannot run without it; need levels of stock tables
BUILD_AHEAD = 300  # plan-ahead construction
ORDER_AHEAD = 200  # the next key unlock orders
STOCK = 100        # buffers
NONE = 0

BANDS = (BLOCKER, MANUAL, BUILD, ORDER, UPGRADE, NEED, BUILD_AHEAD, ORDER_AHEAD, STOCK)
# Bands whose deficits are split between competing outposts in proportion
# (logistics_requests.fair_share_tiers()); higher bands are served in full.
FAIR_BANDS = (BUILD_AHEAD, ORDER_AHEAD, STOCK)
BAND_NAMES = {
    BLOCKER: "blocker", MANUAL: "manual", BUILD: "build", ORDER: "order", UPGRADE: "upgrade",
    NEED: "need", BUILD_AHEAD: "build-ahead", ORDER_AHEAD: "order-ahead", STOCK: "stock", NONE: "none",
}


def band(prio):
    """Band value of `prio` (its hundreds)."""
    return prio - prio % 100


def fine(prio):
    """Tie-break value of `prio` inside its band (0-99)."""
    return prio % 100


def band_name(prio):
    return BAND_NAMES.get(band(prio), "none")


def clamp(prio):
    return max(0, min(999, int(prio)))


def order_prio(score, override=None, score_max=1):
    """ORDER-band prio for a Supply Dock order score (0..score_max mapped to
    the band's 0-99), or the operator override (any 0-999) when set."""
    if override is not None:
        return clamp(override)
    score_max = max(1, score_max)
    return ORDER + min(99, max(0, int(score)) * 99 // score_max)


def blueprint_prio(planned, priority):
    """Prio of a Construction Blueprint's material: MANUAL for one the operator
    placed (not in autoplay.planned), BUILD for an autoplay job at
    construction.priority 0, BUILD_AHEAD for plan-ahead jobs (lower for a
    higher priority number)."""
    if not planned:
        return MANUAL + 99
    k = int(priority or 0)
    if k <= 0:
        return BUILD + 99
    return BUILD_AHEAD + max(0, 99 - 10 * (k - 1))


def ceil_units(value):
    """Smallest int >= value (value >= 0)."""
    n = int(value)
    return n if n >= value else n + 1


# ------------------------------------------------------------------ ladders

def ladder(value):
    """A valid ladder from an archive value: 2-item lists of numbers, sorted by
    prio descending with non-decreasing cum; anything else gives []."""
    if not isinstance(value, list):
        return []
    levels = []
    for entry in value:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            continue
        prio, cum = entry
        if isinstance(prio, (int, float)) and isinstance(cum, (int, float)) and cum > 0:
            levels.append([clamp(prio), int(cum)])
    levels.sort(key=lambda level: -level[0])
    return _normalize(levels)


def _normalize(levels):
    """Drops levels that add nothing (cum not above the level before) and merges equal prios."""
    out = []
    for prio, cum in levels:
        if cum <= 0:
            continue
        if out and out[-1][0] == prio:
            out[-1][1] = max(out[-1][1], cum)
            continue
        if out and cum <= out[-1][1]:
            continue
        out.append([prio, cum])
    return out


def ladder_level(levels, prio):
    """Units wanted at `prio` or higher: the cum of the lowest level at or above it (0 when none)."""
    wanted = 0
    for p, cum in levels:
        if p >= prio:
            wanted = cum
        else:
            break
    return wanted


def ladder_total(levels):
    """The flat target: the last level's cum (0 for an empty ladder)."""
    return levels[-1][1] if levels else 0


def ladder_raise(levels, prio, cum):
    """`levels` with a floor of `cum` units at `prio` (max-fold: a root's level
    for the same item from another source). Lower levels rise to at least
    `cum`; higher ones keep theirs. In place; returns `levels`."""
    if cum <= 0:
        return levels
    out = []
    placed = False
    for p, c in levels:
        if p > prio:
            out.append([p, c])
        elif p == prio:
            out.append([p, max(c, cum)])
            placed = True
        else:
            if not placed:
                out.append([prio, cum])
                placed = True
            out.append([p, max(c, cum)])
    if not placed:
        out.append([prio, cum])
    levels[:] = _normalize(out)
    return levels


def ladder_add(levels, prio, units):
    """`levels` with `units` more wanted at `prio` (sum-fold: a cascade
    contribution from one more parent). Every level at or below `prio`
    grows by `units`. In place; returns `levels`."""
    if units <= 0:
        return levels
    out = []
    placed = False
    base = 0
    for p, c in levels:
        if p > prio:
            out.append([p, c])
            base = c
        elif p == prio:
            out.append([p, c + units])
            placed = True
        else:
            if not placed:
                out.append([prio, base + units])
                placed = True
            out.append([p, c + units])
    if not placed:
        out.append([prio, base + units])
    levels[:] = _normalize(out)
    return levels


def ladder_max(a, b):
    """A new ladder wanting, at every prio, the larger of what `a` and `b` want."""
    out = [list(level) for level in a]
    for prio, cum in b:
        ladder_raise(out, prio, cum)
    return out


def ladder_add_levels(levels, other):
    """`levels` with every level of `other` summed in (ladder_add() of each
    level's own increment at its prio). In place; returns `levels`."""
    before = 0
    for prio, cum in other:
        ladder_add(levels, prio, cum - before)
        before = cum
    return levels


def ladder_lower(levels, units):
    """A new ladder with `units` fewer wanted at every level (units that
    arrived or were consumed count against the highest levels first, like
    stock in ladder_deficits()); levels that drop to 0 go."""
    if units <= 0:
        return [list(level) for level in levels]
    return _normalize([[p, c - units] for p, c in levels])


def ladder_promote(levels, min_band, prio):
    """A new ladder with every level of band >= `min_band` moved to `prio`
    (a settled want lifted to BLOCKER); lower levels keep theirs."""
    return _normalize(sorted([[prio if band(p) >= min_band else p, c] for p, c in levels], key=lambda level: -level[0]))


def ladder_scale(levels, ratio):
    """A new ladder with every cum scaled by `ratio`, rounded up."""
    return _normalize([[p, ceil_units(c * ratio)] for p, c in levels])


def ladder_deficits(levels, arriving):
    """[(prio, missing)], highest prio first, positive only: each level's
    missing units after `arriving` (stock plus in flight) and the higher
    levels' shares are taken off."""
    out = []
    covered = arriving
    for prio, cum in levels:
        missing = cum - covered
        if missing > 0:
            out.append((prio, missing))
            covered = cum
    return out


def band_deficits(levels, arriving):
    """{band: missing} of ladder_deficits(), levels folded per band."""
    out = {}
    for prio, missing in ladder_deficits(levels, arriving):
        b = band(prio)
        out[b] = out.get(b, 0) + missing
    return out


def top_deficit(levels, arriving):
    """(prio, missing) of the highest level still short, or (NONE, 0)."""
    for prio, cum in levels:
        if cum > arriving:
            return prio, cum - arriving
    return NONE, 0


def from_levels(target, need=None, need_prio=NEED, target_prio=STOCK):
    """The ladder of a (target, min) request: `need` units at need_prio, the
    rest up to `target` at target_prio. No need (None, 0 or >= target) puts
    the whole target at need_prio."""
    if target <= 0:
        return []
    if need is None or need >= target:
        return [[need_prio, int(target)]]
    if need <= 0:
        return [[target_prio, int(target)]]
    return _normalize([[need_prio, int(need)], [target_prio, int(target)]])


def deficits_text(deficits):
    """"<band> <missing>, ..." for a log line, from ladder_deficits() output."""
    return ", ".join(f"{band_name(prio)}({prio}) {missing}" for prio, missing in deficits) or "none"
