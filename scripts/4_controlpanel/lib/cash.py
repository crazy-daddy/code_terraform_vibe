# Cash manager: one budget owner for every credit consumer (docs/AI_CHEATSHEET.md §2l).
#
# Two halves, one archive dict (cash.budget, CODE_GUIDES.md#archive):
#   - CashManager.step(), run by the headless orchestrator_automation.py every storage
#     tick: samples the credit balance, measures gross income and operating
#     (reagent) burn from the balance history + spend log, sets the dynamic
#     floor, reads the Earth Order pipeline, and publishes the ask queue with
#     an ETA per ask for control_panel/cash_panel.py.
#   - can_spend() / spent() / release(), called by each consumer right before
#     and after a Shop purchase. The decision is made live, inside one
#     archive transaction, so two consumers can't both spend the same credits.
#
# Rules (owner, 2026-09-29):
#   - Operating consumers (OPERATING: Bio Lab reagents, Pioneer reagent Shop
#     pulls) go first: they may spend down to 0. The floor exists for them.
#   - Capital consumers spend only above the floor, in priority order
#     (cash.budget["priority"], reorderable on the CASH card, default
#     DEFAULT_PRIORITY). The highest-priority ask that has no hold yet is the
#     savings goal: a lower one may spend only if the goal stays affordable
#     too, or if its cost is at most SMALL_RATIO of the goal's.
#   - No prespending: only cash on hand is granted. Income and the order
#     pipeline only drive the ETAs.
#   - Floor = max(MIN_FLOOR, operating burn/h x FLOOR_HOURS).
#
# A granted can_spend() leaves a hold for the consumer (HOLD_TICKS) that
# other checks subtract; spent() or release() clears it. Consumers call
# can_spend() every pass while they want something, which refreshes their
# ask; an ask not refreshed for ASK_STALE_TICKS is dropped.
#
# Without a fresh manager pass (orchestrator_automation.py not running, or tier < 4),
# the floor for capital consumers is LEGACY_RESERVE, the flat reserve every
# upgrader used before, so nothing overspends while the manager is down.

from archive import archive
from tree_console import TreeConsole
from components import component
from swallow import swallowed
from game_clock import now_tick

BUDGET_KEY = "cash.budget"

# Consumer ids are "<kind>" or "<kind>:<instance>" (one ask per Pioneer or
# Bio Lab); priority and OPERATING match on the kind.
# Operating consumers: never blocked by the floor or the savings goal.
OPERATING = ("bio_reagents", "pioneer_reagents", "wildlife_reagents")
# Capital consumers, highest priority first. Unknown ids rank after these.
DEFAULT_PRIORITY = ["crop_automator", "bin_upgrade", "warehouse_upgrade", "pioneer_commission", "drone_commission", "tank_upgrade", "pioneer_upgrade"]
CONSUMER_LABELS = {
    "bio_reagents": "Bio Lab reagents",
    "pioneer_reagents": "Pioneer reagent pulls",
    "wildlife_reagents": "Habitat revival reagents",
    "crop_automator": "Crop Automators",
    "bin_upgrade": "Warehouse (bin swap)",
    "warehouse_upgrade": "Large Warehouse",
    "pioneer_commission": "Pioneer commission",
    "drone_commission": "Drone commission",
    "tank_upgrade": "Large Liquid Tank",
    "pioneer_upgrade": "Pioneer tier upgrades",
}

MIN_FLOOR = 20000               # credits capital consumers always leave
FLOOR_HOURS = 12.0              # game hours of operating burn the floor covers
LEGACY_RESERVE = 100000         # capital floor while the manager is stale
SMALL_RATIO = 0.10              # below the goal, a buy this small next to it may skip
HOLD_TICKS = 600                # a granted can_spend() is held this long (~1 min)
ASK_STALE_TICKS = 3000          # an ask not refreshed this long is dropped (~5 min)
MANAGER_STALE_TICKS = 1200      # manager pass older than this -> LEGACY_RESERVE (~2 min)
HISTORY_STEP_H = 0.25           # game hours between balance samples
INCOME_WINDOW_H = 24.0          # game hours of history the rates are measured over
MIN_RATE_SPAN_H = 1.0           # no rate until the history spans this long
SPEND_LOG_LEN = 200             # spend log entries kept (also pruned to the window)

log = TreeConsole(module="cash")


def _hours():
    clock = component("clock")
    try:
        return float(clock.elapsed_game_hours()) if clock and hasattr(clock, "elapsed_game_hours") else 0.0
    except Exception as error:
        swallowed("cash._hours: clock.elapsed_game_hours", error)
        return 0.0


def balance():
    """Current credit balance, 0 if the commander can't be read."""
    commander = component("commander")
    try:
        return int(commander.get_credits()) if commander else 0
    except Exception as error:
        swallowed("cash.balance: commander.get_credits", error)
        return 0


_prices = {}


def shop_price(item_id, fallback=0):
    """Shop catalogue price of item_id, cached per script run (prices are static)."""
    if item_id in _prices:
        return _prices[item_id]
    shop = component("shop")
    try:
        for entry in (shop.get_catalogue() if shop else []):
            _prices[entry.id] = int(entry.cost)
    except Exception as error:
        swallowed("cash.shop_price: shop.get_catalogue", error)
    return _prices.get(item_id, fallback)


def budget():
    """cash.budget, or {} when missing."""
    state = archive.get(BUDGET_KEY, {})
    return state if isinstance(state, dict) else {}


def priority_order(state=None):
    """Capital consumer ids, highest priority first: the stored order, then any default id it lacks."""
    state = budget() if state is None else state
    stored = [c for c in (state.get("priority") or []) if isinstance(c, str)]
    return stored + [c for c in DEFAULT_PRIORITY if c not in stored]


def kind_of(consumer):
    """Consumer kind: the id before any ':' ("pioneer_upgrade:pioneer_2" -> "pioneer_upgrade")."""
    return consumer.split(":")[0]


def is_operating(consumer):
    return kind_of(consumer) in OPERATING


def _rank(consumer, order):
    kind = kind_of(consumer)
    return order.index(kind) if kind in order else len(order)


def _prune(state, now):
    asks = {c: a for c, a in (state.get("asks") or {}).items() if isinstance(a, dict) and now - int(a.get("tick", 0)) <= ASK_STALE_TICKS}
    holds = {c: h for c, h in (state.get("holds") or {}).items() if isinstance(h, dict) and now - int(h.get("tick", 0)) <= HOLD_TICKS}
    state["asks"] = asks
    state["holds"] = holds


def floor_for(consumer, state, now):
    """Credits consumer must leave: 0 for operating ones, else the manager's floor (LEGACY_RESERVE when stale)."""
    if is_operating(consumer):
        return 0
    fresh = now - int(state.get("tick", -MANAGER_STALE_TICKS - 1)) <= MANAGER_STALE_TICKS
    return int(state.get("floor", MIN_FLOOR)) if fresh else LEGACY_RESERVE


def savings_goal(consumer, state):
    """(goal consumer, its ask) for consumer: the highest-priority other capital ask ranked above it with no hold, else (None, None)."""
    if is_operating(consumer):
        return None, None
    order = priority_order(state)
    mine = _rank(consumer, order)
    holds = state.get("holds") or {}
    best = None
    for other, ask in (state.get("asks") or {}).items():
        if other == consumer or is_operating(other) or other in holds:
            continue
        rank = _rank(other, order)
        if rank < mine and (best is None or rank < best[0]):
            best = (rank, other, ask)
    return (best[1], best[2]) if best else (None, None)


def decide(consumer, cost, state, have, now):
    """(ok, reason) for consumer spending cost now; state already pruned."""
    held = sum(int(h.get("amount", 0)) for c, h in (state.get("holds") or {}).items() if c != consumer)
    floor = floor_for(consumer, state, now)
    free = have - held - floor
    if cost > free:
        return False, f"needs {cost} cr, {max(0, free)} free ({have} - {held} held - {floor} floor)"
    goal, ask = savings_goal(consumer, state)
    if goal and ask:
        goal_cost = int(ask.get("cost", 0))
        if cost + goal_cost > free and cost > SMALL_RATIO * goal_cost:
            return False, f"saving for {goal} ({goal_cost} cr)"
    return True, f"ok ({free - cost} cr free after)"


def can_spend(consumer, cost, planned=None, label=""):
    """
    True if consumer may spend `cost` credits now; then a hold for it is set
    until spent()/release() or HOLD_TICKS. Always refreshes consumer's ask
    (cost = the next purchase, planned = everything it still means to buy).
    """
    cost = max(0, int(cost))
    have = balance()
    now = now_tick()
    result = {"ok": False, "reason": ""}

    def updater(state):
        state = state if isinstance(state, dict) else {}
        _prune(state, now)
        state["asks"][consumer] = {"cost": cost, "planned": max(cost, int(planned or cost)), "label": label, "tick": now}
        ok, reason = decide(consumer, cost, state, have, now)
        result["ok"], result["reason"] = ok, reason
        if ok:
            state["holds"][consumer] = {"amount": cost, "tick": now}
        return state

    try:
        archive.transaction(BUDGET_KEY, {}, updater)
    except Exception as error:
        swallowed("cash.can_spend: archive.transaction", error)
        return have - cost >= (0 if is_operating(consumer) else LEGACY_RESERVE)
    log.debug(f"[cash] {consumer} can_spend({cost}) -> {result['ok']}: {result['reason']}")
    return result["ok"]


def spent(consumer, amount):
    """Logs a completed purchase and clears consumer's hold and ask."""
    amount = int(amount)
    hours = _hours()

    def updater(state):
        state = state if isinstance(state, dict) else {}
        (state.setdefault("holds", {})).pop(consumer, None)
        (state.setdefault("asks", {})).pop(consumer, None)
        entries = state.get("spent") or []
        entries.append([round(hours, 3), consumer, amount])
        state["spent"] = entries[-SPEND_LOG_LEN:]
        return state

    try:
        archive.transaction(BUDGET_KEY, {}, updater)
    except Exception as error:
        swallowed("cash.spent: archive.transaction", error)
    log.debug(f"[cash] {consumer} spent {amount} cr.")


def release(consumer):
    """Drops consumer's hold and ask (it no longer wants to buy anything)."""
    state = budget()
    if consumer not in (state.get("asks") or {}) and consumer not in (state.get("holds") or {}):
        return

    def updater(current):
        current = current if isinstance(current, dict) else {}
        (current.setdefault("holds", {})).pop(consumer, None)
        (current.setdefault("asks", {})).pop(consumer, None)
        return current

    try:
        archive.transaction(BUDGET_KEY, {}, updater)
    except Exception as error:
        swallowed("cash.release: archive.transaction", error)


def set_priority(order):
    """Stores the capital priority order (CASH card reorder)."""
    order = [c for c in order if isinstance(c, str)]
    try:
        archive.transaction(BUDGET_KEY, {}, lambda s: dict(s if isinstance(s, dict) else {}, priority=order))
    except Exception as error:
        swallowed("cash.set_priority: archive.transaction", error)


def move_priority(consumer, step):
    """Moves consumer step places in the priority order (negative = up)."""
    order = priority_order()
    if consumer not in order:
        return
    i = order.index(consumer)
    j = max(0, min(len(order) - 1, i + step))
    order[i], order[j] = order[j], order[i]
    set_priority(order)


# ---------------------------------------------------------------- manager


def rates(history, spend_log, now_h):
    """(gross income/h, operating burn/h, span h) over the history window; rates None below MIN_RATE_SPAN_H."""
    if not history:
        return None, None, 0.0
    start_h, start_bal = history[0][0], history[0][1]
    end_h, end_bal = history[-1][0], history[-1][1]
    span = end_h - start_h
    if span < MIN_RATE_SPAN_H:
        return None, None, span
    window = [e for e in spend_log if start_h < e[0] <= end_h]
    spend = sum(e[2] for e in window)
    operating = sum(e[2] for e in window if is_operating(e[1]))
    return (end_bal - start_bal + spend) / span, operating / span, span


def order_pipeline():
    """{"campaign": remaining cr, "campaign_shipped": cr already earned in progress, "weekly": cr} from the Earth Order boards."""
    orders = component("orders")
    out = {"campaign": 0, "campaign_shipped": 0, "weekly": 0}
    if not orders:
        return out
    boards = (("campaign", "list_orders"), ("weekly", "list_weekly_orders"))
    for kind, method in boards:
        try:
            listed = getattr(orders, method)() if hasattr(orders, method) else []
        except Exception as error:
            swallowed(f"cash.order_pipeline: orders.{method}", error)
            listed = []
        for order in listed:
            if getattr(order, "status", "active") != "active":
                continue
            reward = int(getattr(order, "reward_credits", 0) or 0)
            requires = getattr(order, "requires", {}) or {}
            shipped = getattr(order, "shipped", {}) or {}
            need = sum(requires.values())
            frac = (sum(min(shipped.get(i, 0), n) for i, n in requires.items()) / need) if need else 0.0
            if kind == "campaign":
                out["campaign"] += int(reward * (1.0 - frac))
                out["campaign_shipped"] += int(reward * frac)
            else:
                out["weekly"] += int(reward * (1.0 - frac))
    return out


def queue(state, have, income):
    """[{consumer, cost, planned, label, eta_h, held}] of every ask: operating first, then capital by priority; eta_h None = no income measured."""
    order = priority_order(state)
    asks = state.get("asks") or {}
    holds = state.get("holds") or {}
    ids = sorted(asks, key=lambda c: (not is_operating(c), _rank(c, order), c))
    floor = int(state.get("floor", MIN_FLOOR))
    needed = sum(int(h.get("amount", 0)) for h in holds.values())
    rows = []
    for consumer in ids:
        ask = asks[consumer]
        held = consumer in holds
        if not held:
            needed += int(ask.get("cost", 0))
        gap = needed + (0 if is_operating(consumer) else floor) - have
        if gap <= 0 or held:
            eta = 0.0
        else:
            eta = (gap / income) if income and income > 0 else None
        rows.append({"consumer": consumer, "cost": int(ask.get("cost", 0)), "planned": int(ask.get("planned", 0)), "label": ask.get("label", ""), "eta_h": eta, "held": held})
    return rows


class CashManager:
    """Headless budget pass for orchestrator_automation.py. Stateless between passes (state lives in cash.budget)."""

    def step(self, now=None):
        now = now_tick() if now is None else now
        now_h = _hours()
        have = balance()
        pipeline = order_pipeline()
        summary = {"text": ""}

        def updater(state):
            state = state if isinstance(state, dict) else {}
            _prune(state, now)
            history = [e for e in (state.get("history") or []) if now_h - e[0] <= INCOME_WINDOW_H]
            if not history or now_h - history[-1][0] >= HISTORY_STEP_H:
                history.append([round(now_h, 3), have])
            state["history"] = history
            spend_log = [e for e in (state.get("spent") or []) if now_h - e[0] <= INCOME_WINDOW_H]
            state["spent"] = spend_log[-SPEND_LOG_LEN:]
            # Rates run to the live sample, not the last stored one.
            income, burn, span = rates(history + [[now_h, have]], spend_log, now_h)
            floor = max(MIN_FLOOR, int((burn or 0.0) * FLOOR_HOURS))
            state.update({
                "tick": now, "hours": round(now_h, 3), "balance": have, "floor": floor,
                "income_h": None if income is None else round(income, 1),
                "burn_h": None if burn is None else round(burn, 1),
                "span_h": round(span, 2), "pipeline": pipeline,
            })
            rows = queue(state, have, income)
            state["queue"] = rows
            planned = sum(r["planned"] for r in rows)
            state["planned"] = planned
            rate = "?" if income is None else f"{income:+.0f}/h"
            summary["text"] = f"cash {have} cr, floor {floor}, {rate}, {len(rows)} ask(s) {planned} cr planned"
            return state

        try:
            archive.transaction(BUDGET_KEY, {}, updater)
        except Exception as error:
            swallowed("cash.CashManager.step: archive.transaction", error)
            return "cash manager error"
        log.debug(f"[cash] {summary['text']}; pipeline {pipeline}.")
        return summary["text"]
