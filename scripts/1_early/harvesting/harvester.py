# ==============================================================================
# OPTIMAL HARVESTER - Heat-Aware & Value-Weighted Autonomous Collector
# ==============================================================================
# Thermal mechanics from Code: Terraform engine:
#   - Move onto an ITEM sector   -> +1 heat (sheds 1.5h during 0.5h move -> net cooling!)
#   - Move onto an EMPTY sector  -> +7 heat (sheds 1.5h -> net +5.5 heat)
#   - Collect on an EMPTY sector -> +9 heat (never do this; map is verified live)
#   - Max heat: 100. Heat drains at 3.0 per world-hour passively.
#   - RSPH = clock.real_seconds_per_hour() (~30s real per world hour)
#
# Key Optimizations:
#   1. Value-density target selection: Chooses target maximizing (value / Manhattan distance).
#   2. Axis-smart pathfinding: When stepping towards target, chooses the axis landing
#      on an item sector (+1 heat instead of +7 heat).
#   3. Exact-need cooling: Travels up to heat 97. Only cools when the next step would
#      cross 97, and calculates the exact sleep duration needed.
#   4. Instant liquidation: Deposits via store() and immediately sells all via shop
#      to maximize credit velocity and keep outpost inventory 100% clear.
#   5. Two-mode targeting: value-density scoring (val / d^1.35) maximizes early credit
#      velocity while the base build-out is still funding-critical - but it never lets
#      go of that bias, so a low-value item sitting far from the pack can keep losing
#      every scoring round to nearer/richer newcomers indefinitely (starvation, not just
#      delay - the map never actually finishes clearing while fresher, better-scoring
#      targets keep appearing). Once Nocturna Base's building slots hit 25/25 for the
#      first time, the credit-funded buildout (batteries, solar, generators, ...) is
#      essentially done and slot occupancy will only fluctuate around full from here
#      (recycle-and-rebuild between phases) - not grow again - so that first full-25
#      reading is a clean, one-way signal that credit velocity no longer needs to win
#      over completeness. Deliberately NOT tied to scanner coverage: the scanner sweeps
#      its ~192 local sectors well before the multi-phase, multi-day buildout is done,
#      which would flip modes too early and blunt the credit rush while it still matters.
# ==============================================================================

SCANNER_ID    = "scanner_1"
HEAT_MAX      = 100
HEAT_SAFETY   = 3       # Never plan a hop that exceeds 97 heat
COOL_PER_HOUR = 3.0     # Heat drained per world-hour
COST_ITEM     = 1       # Heat cost moving to item sector
COST_EMPTY    = 7       # Heat cost moving to empty sector
IDLE_HOURS    = 0.5     # World-hours to wait when no targets are known

scanner = get_component(SCANNER_ID)
shop = get_component("shop")
home = get_component("outpost_home")

try:
    clock = get_component("clock")
    RSPH = clock.real_seconds_per_hour()
except Exception:
    RSPH = 30.0

def base_is_full():
    # True once Nocturna Base's building slots have ever hit capacity (25, or 30 post
    # outpost_expansion_unlock) - mirrors solar.py's get_free_base_slots() slot reading.
    if not home:
        return False
    try:
        cap = home.buildings_capacity() if callable(getattr(home, "buildings_capacity", None)) else getattr(home, "buildings_capacity", 25)
        used = home.buildings_used() if callable(getattr(home, "buildings_used", None)) else getattr(home, "buildings_used", 0)
        return int(used) >= int(cap)
    except Exception:
        return False

def parse(sid: str):
    return (ord(sid[0].upper()) - 64, int(sid[1:]))

def fmt(p):
    return chr(64 + p[0]) + str(p[1])

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

def choose_target(pos, pts, clearing_mode=False):
    pr, pc = pos

    # Priority 1: Clear immediate local items (d <= 2)
    # Moving onto an item sheds heat (net cooling!), so clearing local items is free and fast!
    local_cands = []
    for p, val in pts.items():
        d = abs(p[0] - pr) + abs(p[1] - pc)
        if d == 0:
            return p
        if d <= 2:
            local_cands.append((d, -val, p))
    if local_cands:
        local_cands.sort()
        return local_cands[0][2]

    # Priority 2 (CLEARING MODE): once the map is basically fully surveyed, whatever
    # is left is what value-density scoring kept skipping over - sweep nearest-first,
    # ignoring value entirely, so the field actually finishes clearing.
    if clearing_mode:
        best = None
        best_d = None
        for p in pts:
            d = abs(p[0] - pr) + abs(p[1] - pc)
            if best_d is None or d < best_d:
                best_d = d
                best = p
        return best

    # Priority 2 (CREDIT RUSH): For farther items, penalize empty-space distance (d^1.35)
    # Empty hops (+7 heat) build up heat and force cooling naps, making long trips costly.
    best = None
    best_score = -1.0
    for p, val in pts.items():
        d = abs(p[0] - pr) + abs(p[1] - pc)
        score = val / (d ** 1.35)
        if score > best_score:
            best_score = score
            best = p
    return best

def next_hop(pos, tgt, pts):
    dr = tgt[0] - pos[0]
    dc = tgt[1] - pos[1]
    cands = []
    if dr > 0:
        cands.append((pos[0] + 1, pos[1]))
    elif dr < 0:
        cands.append((pos[0] - 1, pos[1]))
    if dc > 0:
        cands.append((pos[0], pos[1] + 1))
    elif dc < 0:
        cands.append((pos[0], pos[1] - 1))
    
    # Priority 1: Pick an axis that lands on an item cell (+1 heat vs +7 heat!)
    for q in cands:
        if q in pts:
            return q
    if not cands:
        return None
    # Priority 2: Stay near diagonal to maximize future options
    if len(cands) == 2 and abs(dc) > abs(dr):
        return cands[1]
    return cands[0]

def put_away():
    waited = 0
    while True:
        if not self.get_held():
            return True
        r = self.store()
        if r.status == "ok":
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
    cost = COST_ITEM if q in pts else COST_EMPTY
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

# Wait for scanner to survey an initial radius around base before harvesting
min_scanned_sectors = 60
while True:
    try:
        scanned_count = len(scanner.get_scanned())
    except Exception:
        scanned_count = 0
    if scanned_count >= min_scanned_sectors:
        break
    print(f"[harvester] Waiting for scanner to map base sector ({scanned_count}/{min_scanned_sectors} sectors)...")
    sleep(2.0)

clearing_mode = False

while True:
    pts = read_map()

    if not clearing_mode and base_is_full():
        clearing_mode = True
        print("[harvester] Base build-out at full slot capacity - switching to CLEARING MODE (nearest-first, full field sweep).")

    if not pts:
        sleep(IDLE_HOURS * RSPH)
        continue

    pos = parse(self.get_position())
    if self.get_held():
        put_away()

    # If standing on an item, pick it up
    if pos in pts:
        take(pos, pts)
        continue

    tgt = choose_target(pos, pts, clearing_mode)
    if not tgt:
        sleep(IDLE_HOURS * RSPH)
        continue

    q = next_hop(pos, tgt, pts)
    if not q:
        continue

    if not go(q, pts):
        pts.pop(q, None)
