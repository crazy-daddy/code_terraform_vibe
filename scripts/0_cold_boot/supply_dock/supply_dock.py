# =============================================================================
# Early Game Self-Contained Supply Dock Controller (no external lib imports)
# Picks the best Earth Order, loads it from Inventory, and ships it -- the
# small early-game slice of what lib/supply_dock.py does after the 150k TP
# migration (no multi-dock planning, no construction-material reservations:
# at 110k TP there's realistically one dock and nothing else contending for
# stock yet). Point is to knock out the first few Earth Orders for credits
# the moment Supply Logistics unlocks, instead of waiting for lib/.
# =============================================================================

STORE = "inventory"
LOAD_CHUNK = 10   # units per take() call, keeps a single cycle cheap
IDLE_SLEEP = 3.0
POLL = 1.0

orders = get_component("orders")
inventory = get_component("inventory")
clock = get_component("clock")


def order_readiness(order):
    # (ready, remaining) -- ready is how much of the still-owed requirement
    # Inventory can already cover; remaining ignores stock entirely.
    ready = 0
    remaining = 0
    for item_id, req_count in order.requires.items():
        still_needed = req_count - order.shipped.get(item_id, 0)
        if still_needed <= 0:
            continue
        remaining += still_needed
        ready += min(inventory.count(item_id), still_needed)
    return ready, remaining


def weekly_infeasible(order, current_day, rate):
    # Coarse dispatch-capacity ceiling: can this dock physically ship the
    # rest before expiry. Never blocks on missing data.
    if order.expires_day is None or current_day is None or rate <= 0:
        return False
    hours_left = (order.expires_day - current_day) * 24.0
    if hours_left <= 0:
        return True
    _, remaining = order_readiness(order)
    return remaining > rate * hours_left


def score(order):
    prio = 5 if order.kind == "weekly" else 10
    if order.reward_kind in ("recipe", "tech"):
        prio += 50  # unlocking a recipe/tech beats plain credits
    ready, remaining = order_readiness(order)
    if remaining > 0:
        prio += int((ready / remaining) * 30)
    return prio


def pick_best_order():
    candidates = []

    for o in orders.list_orders():
        if o.status != "active":
            continue
        _, remaining = order_readiness(o)
        if remaining <= 0:
            continue
        candidates.append((score(o), o))

    current_day = clock.get_day() if clock and hasattr(clock, "get_day") else None
    rate = self.dispatch_rate()
    for o in orders.list_weekly_orders():
        if o.status != "active":
            continue
        _, remaining = order_readiness(o)
        if remaining <= 0:
            continue
        if weekly_infeasible(o, current_day, rate):
            print("[supply_dock] skipping", o.name, "- can't ship remaining before it expires on day", o.expires_day)
            continue
        candidates.append((score(o), o))

    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates[0][1]


def ensure_connected():
    if self.input.connected_id() != STORE:
        result = self.input.connect(STORE)
        if result.status != "ok":
            print("[supply_dock] input connect failed:", result.message)
            return False
    return True


def drain_cargo():
    # clear_order() leaves loaded cargo in place -- eject it back to
    # Inventory so set_order() for the next pick doesn't reject on
    # "cargo_present".
    for slot in self.slots():
        if not slot.item_id or slot.count <= 0:
            continue
        result = self.input.eject(STORE, slot.item_id, slot.count)
        if result.status == "ok":
            print("[supply_dock] ejected", slot.count, "x", slot.item_id, "back to Inventory")
        elif result.status not in ("busy", "no_op"):
            print("[supply_dock] eject", slot.item_id, ":", result.status, "-", result.message)


last_active = ""

while True:
    if not ensure_connected():
        sleep(IDLE_SLEEP)
        continue

    curr = self.current_order()

    if not curr:
        if self.total() > 0:
            drain_cargo()
            sleep(POLL)
            continue

        best = pick_best_order()
        if not best:
            if last_active != "idle":
                print("[supply_dock] no active Earth Orders available - standing by")
                last_active = "idle"
            sleep(IDLE_SLEEP)
            continue

        reward = f"{best.reward_credits:.0f} cr"
        if best.reward_kind:
            reward += f" + {best.reward_kind} ({best.reward_label})"
        print("[supply_dock] assigning", best.name, "(reward:", reward, ")")

        result = self.set_order(best.id)
        if result.status == "cargo_present":
            drain_cargo()
            sleep(POLL)
            continue
        if result.status != "ok":
            print("[supply_dock] could not assign order:", result.status, "-", result.message)
            sleep(IDLE_SLEEP)
            continue

        curr = self.current_order()
        last_active = curr.id if curr else ""

    if curr:
        for item_id, req_total in curr.requires.items():
            already_shipped = curr.shipped.get(item_id, 0)
            in_dock = self.count(item_id)
            needed = req_total - already_shipped - in_dock
            if needed <= 0:
                continue

            to_take = min(inventory.count(item_id), needed, LOAD_CHUNK)
            if to_take <= 0:
                continue

            result = self.input.take(item_id, to_take)
            if result.status == "ok" and result.moved > 0:
                print("[supply_dock] loaded", result.moved, "x", item_id, "-", self.count(item_id), "/", req_total)

        if not self.is_enabled() and self.total() > 0:
            result = self.set_enabled(True)
            if result.status == "ok":
                print("[supply_dock] dispatch enabled at", f"{self.dispatch_rate():.0f}", "units/h")

        active_disp = self.current_dispatch()
        if active_disp:
            print("[supply_dock] shipping", curr.name, "-", active_disp,
                  f"({self.dispatch_progress()*100:.0f}%, {self.dispatch_rate():.0f} u/h)")

    sleep(POLL)
