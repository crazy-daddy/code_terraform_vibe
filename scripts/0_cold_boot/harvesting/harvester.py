# ==============================================================================
# EARLY HARVESTER - credits-per-time collector for the surface field
# ==============================================================================
# Heat (docs/components/harvester.md): move onto an item cell (or the base pad) +1,
# onto an empty cell +7, collect on an empty cell +9; max 100; passive cooling
# 3 per world hour, also while moving.
#
# Route policy, re-planned before every hop and every collect except on arrival at
# the target (tuned offline with devtools/headless/harvest_policies.mjs, policy
# "hybrid"; constants: docs/cheatsheet/vehicles_drones.md §2, "Early Harvester"):
#   1. Routes: the cheapest monotone route (no detours) from the current cell to
#      every cell. A hop costs its travel time plus a heat price (LAM_COLD ticks
#      per heat unit when cool, rising to LAM_HOT at the limit), so routes run over
#      item cells (+1) rather than empty ones (+7).
#   2. Target: the item with the best credits per tick, value / (route + collect),
#      among the PAIR_TOP best of those re-rated by the best two-item trip from it
#      (second leg by Manhattan distance).
#   3. Collect gate: an item the Harvester stands on is collected only if it is
#      worth K_COLLECT x (a collect's time at the best target's rate). Cheaper
#      items stay on the field as +1 stepping stones and are taken later, once
#      the rate has dropped.
#   4. Rest only right before a hop that would pass HEAT_MAX - HEAT_SAFETY, for
#      exactly as long as that needs.
#   5. store() and sell at once after every collect.
# Times are in ticks at 1x (1 world hour = 250 ticks).
# ==============================================================================

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import harvester as self

SCANNER_ID    = "scanner_1"
HEAT_MAX      = 100
HEAT_SAFETY   = 3       # Never plan a hop that exceeds 97 heat
COOL_PER_HOUR = 3.0     # Heat drained per world-hour
COST_ITEM     = 1       # Heat of a move onto an item cell or the base pad
COST_EMPTY    = 7       # Heat of a move onto an empty cell
IDLE_HOURS    = 0.5     # World-hours to wait when no targets are known
MOVE_TICKS    = 125     # 0.5 world h
COLLECT_TICKS = 63      # 0.25 world h
LAM_COLD      = 20      # heat price, ticks per heat unit at heat 0 ...
LAM_HOT       = 100     # ... rising linearly to this at the heat limit
K_COLLECT     = 0.5     # collect gate factor
PAIR_TOP      = 6       # first targets re-rated by a two-item trip
PAIR_HEAT     = 4       # expected heat per hop of the second leg
ROWS, COLS    = 8, 24
CELLS         = ROWS * COLS
BASE          = 4 * COLS + 12   # E13, the base pad

def need(component):
    # Core component this script cannot run without; fail loudly at start if missing.
    assert component is not None
    return component


scanner = need(get_component(SCANNER_ID))
shop = need(get_component("shop"))

# No lib/ access in this tier: local stand-in for lib/swallow.py's swallowed().
# Logs a caught-and-recovered error at debug level (repeats at one site once).
_SWALLOW_LAST = {}


def _swallowed(where, error):
    message = f"{error!r}"
    if _SWALLOW_LAST.get(where) == message:
        return
    _SWALLOW_LAST[where] = message
    console = get_component("console")
    if console:
        console.debug(f"[swallowed] {where}: {message}")


try:
    clock = need(get_component("clock"))
    RSPH = clock.real_seconds_per_hour()
except Exception as error:
    _swallowed("harvester: get_component", error)
    RSPH = 30.0

def parse(sid: str):
    return (ord(sid[0].upper()) - 65) * COLS + int(sid[1:]) - 1

def fmt(p):
    return chr(65 + p // COLS) + str(p % COLS + 1)

def read_map():
    pts = {}
    data = scanner.get_scanned()
    for sid, res in data.items():
        if getattr(res, "status", None) == "ok":
            pts[parse(sid)] = getattr(res, "value", 1)
    return pts

def cool_to(target):
    n = 0
    while self.get_heat() > target and n < 6:
        n += 1
        excess = self.get_heat() - target
        hours = max(0.1, excess / COOL_PER_HOUR)
        print(f"[harvester] Heat {self.get_heat():.1f} - cooling {hours:.2f}h to reach {target}...")
        sleep(hours * RSPH + 0.2)

# Planning runs as a few map() callbacks: each runs in one tick without the
# per-tick step check, capped at 10,000 steps (StepLimitError ends the script),
# docs/cheatsheet/dev_workflow.md §1d-1. Chunks are sized to stay below ~4,000
# steps on a full field (191 items), measured in headless runs. ATOMIC = False
# runs them directly.
ATOMIC = True
ROUTE_ROWS = 3          # grid rows per route callback (~1,000 steps per row)
PAIR_WORK = 150         # candidates x items per pair callback (~20 steps each)

def atomic(fn, *args):
    if not ATOMIC:
        return fn(*args)
    return list(map(lambda _: fn(*args), (0,)))[0]

def route_rows(pos, cost, dist, prev, rows):
    # Cheapest monotone routes (steps toward the cell only, no detours) from pos
    # to every cell of `rows` (pos's row or rows on one side, outward from pos),
    # by DP; ties take the row step. Fills dist/prev in ticks.
    pr, pc = pos // COLS, pos % COLS
    for r in rows:
        row = r * COLS
        up = COLS if r > pr else -COLS
        for sc in (-1, 1):  # pos's column first, then left, then right of it
            for c in (range(pc, -1, -1) if sc < 0 else range(pc + 1, COLS)):
                q = row + c
                if r == pr:
                    if c == pc:
                        continue
                    p = q - sc
                elif c == pc:
                    p = q - up
                else:
                    p = q - up
                    if dist[q - sc] < dist[p]:
                        p = q - sc
                dist[q] = dist[p] + cost[q]
                prev[q] = p

def ranked(pos, pts, dist):
    # Items by value / (route + collect), best first, as (-rate, cell): ties lower cell first.
    out = [(-v / (dist[u] + COLLECT_TICKS), u) for u, v in pts.items() if u != pos]
    out.sort()
    return out

def pair_rates(cands, pts, dist, others, hop_ticks):
    # Best two-item trip rate starting with each candidate: (v1 + v2) / (T1 + T2),
    # second leg by Manhattan distance x hop_ticks; at least the single-item rate.
    out = []
    for neg, q1 in cands:
        v1 = pts[q1]
        t1 = dist[q1] + COLLECT_TICKS * 2
        r1, c1 = q1 // COLS, q1 % COLS
        rates = [(v1 + v) / (t1 + (abs(qr - r1) + abs(qc - c1)) * hop_ticks) for qr, qc, v, q in others if q != q1]
        out.append(max(rates + [-neg]))
    return out

def plan(pos, pts, heat):
    # -> (target, first hop, best single-item rate); target None when no item is left.
    lam = int(LAM_COLD + (LAM_HOT - LAM_COLD) * min(1.0, heat / (HEAT_MAX - HEAT_SAFETY)) + 0.5)
    cost = [MOVE_TICKS + lam * COST_EMPTY] * CELLS
    cheap = MOVE_TICKS + lam * COST_ITEM
    for q in pts:
        cost[q] = cheap
    cost[BASE] = cheap
    dist = [0] * CELLS
    prev = [-1] * CELLS
    pr = pos // COLS
    for rows in (range(pr, -1, -1), range(pr + 1, ROWS)):
        rows = list(rows)
        for i in range(0, len(rows), ROUTE_ROWS):
            atomic(route_rows, pos, cost, dist, prev, rows[i:i + ROUTE_ROWS])
    top = atomic(ranked, pos, pts, dist)[:PAIR_TOP]
    if not top:
        return None, None, 0.0
    hop_ticks = MOVE_TICKS + lam * PAIR_HEAT
    others = [(q // COLS, q % COLS, v, q) for q, v in pts.items() if q != pos]
    step = max(1, PAIR_WORK // len(others))
    rates = []
    for i in range(0, len(top), step):
        rates += atomic(pair_rates, top[i:i + step], pts, dist, others, hop_ticks)
    k = rates.index(max(rates))     # first best: candidate order breaks ties
    best = top[k][1]
    q = best
    while prev[q] != pos:
        q = prev[q]
    return best, q, -top[0][0]

def put_away():
    waited = 0
    while True:
        if not self.get_held():
            return True
        r = self.store()
        if r.status == "ok" and r.item_id:
            try:
                sale = shop.sell_all(r.item_id)
                if sale.status == "ok":
                    print(f"[harvester] Sold {sale.units}x {sale.item_id} (+{sale.credits} cr)")
                else:
                    print(f"[harvester] Stored {r.item_id} (shop status: {sale.status})")
            except Exception as e:
                print(f"[harvester] Stored {r.item_id} (shop exception: {e})")
            return True
        elif r.status == "empty":
            return True
        elif r.status == "inventory_full":
            if waited % 5 == 0:
                print(f"[harvester] Inventory full! Holding {self.get_held()}, retrying...")
            waited += 1
            sleep(IDLE_HOURS * RSPH)
            continue
        print(f"[harvester] Store error: {r.message}")
        return False

def go(q, pts):
    cost = COST_ITEM if q in pts or q == BASE else COST_EMPTY
    if self.get_heat() + cost > HEAT_MAX - HEAT_SAFETY:
        cool_to(HEAT_MAX - HEAT_SAFETY - cost)

    sid = fmt(q)
    for _ in range(8):
        r = self.move(sid)
        if r.status in ("ok", "already_here"):
            return True
        elif r.status == "overheated":
            cool_to(HEAT_MAX - HEAT_SAFETY - cost)
        elif r.status in ("moving", "busy"):
            sleep(0.25 * RSPH)
        else:
            print(f"[harvester] Move {sid} -> {r.status}: {r.message}")
            return False
    return False

def take(p, pts):
    if self.get_held():
        if not put_away():
            return False
    for _ in range(8):
        res = self.collect()
        s = res.status
        if s == "ok":
            pts.pop(p, None)
            val = getattr(res, "value", "?")
            name = getattr(res, "name", getattr(res, "id", "item"))
            print(f"[harvester] + {name} ({val} cr) at {fmt(p)} | heat {self.get_heat():.1f}")
            return put_away()
        elif s == "holding":
            put_away()
        elif s == "overheated":
            cool_to(HEAT_MAX - HEAT_SAFETY - 9)
        elif s in ("moving", "busy", "collecting"):
            sleep(0.25 * RSPH)
        else:
            pts.pop(p, None) # empty / stale
            return False
    return False

print(f"[harvester] Online at {self.get_position()}, heat {self.get_heat():.1f}")

# Wait for the scanner's first sectors around the base before harvesting
min_scanned_sectors = 10
while True:
    try:
        scanned_count = len(scanner.get_scanned())
    except Exception as error:
        _swallowed("harvester: scanner.get_scanned", error)
        scanned_count = 0
    if scanned_count >= min_scanned_sectors:
        break
    print(f"[harvester] Waiting for scanner to map base sector ({scanned_count}/{min_scanned_sectors} sectors)...")
    sleep(2.0)

target = None
while True:
    pts = read_map()
    if not pts:
        sleep(IDLE_HOURS * RSPH)
        continue

    pos = parse(self.get_position())
    if self.get_held():
        put_away()

    # Arrived on the target: collect it without planning.
    if pos == target and pos in pts:
        take(pos, pts)
        continue
    target, q, rate = plan(pos, pts, self.get_heat())
    if pos in pts and (target is None or pts[pos] >= K_COLLECT * COLLECT_TICKS * rate):
        take(pos, pts)
        continue
    if target is None:
        sleep(IDLE_HOURS * RSPH)
        continue

    if not go(q, pts):
        pts.pop(q, None)
