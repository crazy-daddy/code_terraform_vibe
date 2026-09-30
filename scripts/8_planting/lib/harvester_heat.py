from swallow import swallowed
# Harvester mixin: heat-aware movement. Composed by FieldKeeperController
# (lib/field_keeper.py); overrides HarvesterController's move_to()/cool_down().
#
# Heat facts (docs/components/harvester.md, inspirations/vakermit harvester):
#   move onto an item cell   -> +1 heat, onto an empty cell -> +7
#   collect on an empty cell -> +9
#   passive cooling ~3 heat per world-hour, also DURING actions (a 0.5 h move
#   sheds ~1.5), max heat 100.
# Cooling is the real budget: ~72 heat per day, i.e. only ~13 net empty-cell
# hops a day without resting. So:
#   - Routes minimise heat over the whole field (Dijkstra, single source), so
#     a detour over plant/item cells (+1) beats crossing empty cells (+7).
#     HOP_TIME_WEIGHT prices each hop's 0.5 h, so a detour only wins when it
#     saves real heat.
#   - Rest only right before a hop/action that would cross the cap, and only
#     as long as that hop needs (not down to a fixed low level). Heat left
#     over cools during idle time anyway.
#   - Never drive back to the base pad just to park: every hop costs heat and
#     nothing needs the base (load_seed/refill_water work from anywhere).
# Plant/provider cell costs aren't documented, so the per-status move cost
# and the cooling rate are measured on every hop/rest (EMA) and kept in
# `plant.status[<id>]["heat"]` across restarts.

from typing import TYPE_CHECKING
from tree_console import flush_all

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

HEAT_SAFETY = 3.0             # never plan a hop that lands within this of the cap
COOL_PER_HOUR_DEFAULT = 3.0   # measured live, see cool_to()
MOVE_HOURS = 0.5
ACTION_HEAT_RESERVE = 9.0     # headroom kept before a field action (empty collect = +9)
HOP_TIME_WEIGHT = 1.5         # route cost of one hop's 0.5 h, in heat units
DEFAULT_MOVE_COST = 7.0       # entering a cell whose status has no measurement yet
# Plant cells cost about +1; the game charges +7 for entering an empty cell.
# Unmeasured statuses (provider, base) start at DEFAULT_MOVE_COST and are
# learned on the first visit.
MOVE_COST_SEED = {
    "item": 1.0, "empty": 7.0, "unknown": 7.0,
    "growing": 1.0, "stalled": 1.0, "mature": 1.0,
}
COST_SCALE = 2                # Dial buckets: hop costs rounded to 1/COST_SCALE heat
CALIBRATION_ALPHA = 0.3       # EMA weight of a new measurement
# Field work heats the Harvester too (undocumented amounts). Work hours per
# action (docs/components/harvester.md) let the measured heat rise be
# corrected for cooling during the action; actions without a known duration
# (load_seed, drop, store) are neither budgeted nor measured.
ACTION_HOURS = {
    "plant": 0.5, "harvest": 0.5, "uproot": 0.5,
    "light": 0.25, "water": 0.25, "dispense_salt": 0.25, "collect": 0.25,
    "refill_water": 0.25, "deploy": 0.25, "undeploy": 0.25,
    "fertilize": 0.25, "accelerate": 0.25, "amplify": 0.25,
}
ACTION_COST_DEFAULT = 3.0     # heat budgeted for an action not measured yet
MAX_REST_ROUNDS = 6


_NEIGHBOURS = {}   # {sector: (orthogonal neighbours)}, built once: the script has a step budget per tick
_GRID = []         # [(sectors, {sector: index}, neighbour index tuples)] once built, see _grid()
INFINITE_COST = 1 << 30
_NO_STATUS = "~no-status~"   # statuses.get() default: a sector missing from the statuses dict


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed("harvester_heat._now_tick: get_component", error)
        return 0


def field_neighbours(host, sector):
    """Orthogonal neighbours of `sector` on the 8 x 24 field (memoised)."""
    found = _NEIGHBOURS.get(sector)
    if found is not None:
        return found
    r, c = host.sector_to_rc(sector)
    out = []
    if r is not None and c is not None:
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            n = host.rc_to_sector(r + dr, c + dc)
            if n:
                out.append(n)
    found = tuple(out)
    _NEIGHBOURS[sector] = found
    return found


def _grid(host):
    """
    (sectors, {sector: grid index}, neighbours) of the whole field, built
    once. sectors is row-major (A1..A24, B1, ...); neighbours[i] is the tuple
    of neighbour indices of sectors[i] in field_neighbours() order.
    """
    if not _GRID:
        sectors = [host.rc_to_sector(r, c) for r in range(host.NUM_ROWS) for c in range(1, host.NUM_COLS + 1)]
        index = {sector: i for i, sector in enumerate(sectors)}
        neighbours = [tuple([index[n] for n in field_neighbours(host, sector)]) for sector in sectors]
        neighbours.append(())
        _GRID.append((sectors, index, neighbours))
    return _GRID[0]


class HarvesterHeatMixin:
    """Heat-cheapest routing, just-in-time resting and live heat calibration."""

    @property
    def _host(self) -> "FieldKeeperController":
        return self  # type: ignore[return-value]

    # ------------------------------------------------------------ model

    def init_heat_model(self, saved):
        saved = saved if isinstance(saved, dict) else {}
        self.move_costs = dict(MOVE_COST_SEED)
        self.move_costs.update({k: float(v) for k, v in (saved.get("costs") or {}).items()})
        self.cool_per_hour = float(saved.get("cool_per_hour") or COOL_PER_HOUR_DEFAULT)
        self.action_costs = {k: float(v) for k, v in (saved.get("actions") or {}).items()}
        clock = get_component("clock")
        try:
            self.real_seconds_per_hour = float(clock.real_seconds_per_hour()) if clock else 25.0
        except Exception as error:
            swallowed("harvester_heat.HarvesterHeatMixin.init_heat_model: clock.real_seconds_per_hour", error)
            self.real_seconds_per_hour = 25.0

    def game_time(self, ticks):
        """World-clock duration of `ticks` simulation ticks (10 per real second), e.g. "30 min" or "1.2 h"."""
        minutes = ticks / 10.0 / max(0.1, self.real_seconds_per_hour) * 60.0
        return f"{minutes:.0f} min" if minutes < 60 else f"{minutes / 60.0:.1f} h"

    def heat_model(self):
        return {
            "costs": {k: round(v, 2) for k, v in self.move_costs.items()},
            "actions": {k: round(v, 2) for k, v in self.action_costs.items()},
            "cool_per_hour": round(self.cool_per_hour, 2),
        }

    def heat_cap(self):
        try:
            return float(self._host.harvester.get_max_heat()) - HEAT_SAFETY
        except Exception as error:
            swallowed("harvester_heat.HarvesterHeatMixin.heat_cap: self._host.harvester.get_max_heat", error)
            return 100.0 - HEAT_SAFETY

    def move_cost(self, status):
        return self.move_costs.get(status or "unknown", DEFAULT_MOVE_COST)

    def _learn(self, table_key, observed):
        if table_key == "cool":
            self.cool_per_hour += CALIBRATION_ALPHA * (observed - self.cool_per_hour)
            return
        old = self.move_costs.get(table_key, DEFAULT_MOVE_COST)
        self.move_costs[table_key] = old + CALIBRATION_ALPHA * (observed - old)

    def action_cost(self, method):
        if method not in ACTION_HOURS:
            return 0.0
        return max(0.0, self.action_costs.get(method, ACTION_COST_DEFAULT))

    def learn_action(self, method, before, after):
        hours = ACTION_HOURS.get(method)
        if hours is None:
            return
        observed = after - before + self.cool_per_hour * hours
        if -1.0 <= observed <= 30.0:
            old = self.action_costs.get(method, ACTION_COST_DEFAULT)
            self.action_costs[method] = old + CALIBRATION_ALPHA * (observed - old)

    # ------------------------------------------------------------ resting

    def cool_to(self, target):
        """Rests exactly long enough to drain heat down to `target` (measures the cooling rate)."""
        target = max(0.0, target)
        for _ in range(MAX_REST_ROUNDS):
            heat = self._host.get_heat()
            if heat <= target:
                return
            hours = (heat - target) / max(0.5, self.cool_per_hour)
            self._host.log.debug(f"[{self._host.name}] Heat {heat:.1f}: resting {hours:.2f} h to {target:.1f}.")
            flush_all()
            sleep(hours * self.real_seconds_per_hour + 0.5)
            after = self._host.get_heat()
            if after > 0.5:  # a reading floored at 0 says nothing about the rate
                self._learn("cool", (heat - after) / hours)

    def cool_down(self, target_level=None):
        """Override: rest only as far as the next action needs, not to a fixed low level."""
        self.cool_to(self.heat_cap() - ACTION_HEAT_RESERVE)

    def ensure_headroom(self, cost):
        if self._host.get_heat() + cost > self.heat_cap():
            self.cool_to(self.heat_cap() - cost)

    # ------------------------------------------------------------ routing

    def heat_search(self, start, statuses):
        """
        Search state from `start`: Dijkstra with Dial buckets (hop cost = move
        cost of the entered cell + HOP_TIME_WEIGHT, scaled to integers) over
        lists indexed by grid position (_grid()). It only expands as far as a
        caller needs (expand_until()), and the step's target choice and route
        continue the same search: cached for the same start and the same
        statuses dict (identity, not contents: comparing 192 entries costs
        steps too). State: [dist, prev, buckets, next bucket, bucket count];
        dist[i] is INFINITE_COST while unreached (and always for the extra
        last slot, which stands for any sector off the grid), prev[i] the
        previous grid index (-1 at the start). Every cell with dist < the next
        bucket is final.
        """
        cached = getattr(self, "_heat_map_cache", None)
        if cached is not None and cached[0] == start and cached[1] is statuses:
            return cached[2]
        sectors, index, neighbours = _grid(self._host)
        default_w = int(round((DEFAULT_MOVE_COST + HOP_TIME_WEIGHT) * COST_SCALE))
        status_weight = {}
        for status in set(statuses.values()):
            status_weight[status] = max(1, int(round((self.move_cost(status) + HOP_TIME_WEIGHT) * COST_SCALE)))
        status_of = statuses.get
        weight = [status_weight.get(status_of(sector, _NO_STATUS), default_w) for sector in sectors]
        weight.append(default_w)
        dist = [INFINITE_COST] * (len(sectors) + 1)
        prev = [-1] * (len(sectors) + 1)
        first = index.get(start)
        buckets = []
        if first is not None:
            dist[first] = 0
            buckets.append([first])
        state = [dist, prev, buckets, 0, len(buckets), weight]
        self._heat_map_cache = (start, statuses, state)
        return state

    def expand_until(self, state, goals, first_only=False):
        """
        Continues the search until every grid index in `goals` is final, or
        (first_only) until the first of them is, finishing that bucket so every
        goal at the same cost is final too. Unreachable goals run it to the end.
        """
        dist, prev, buckets, d, size, weight = state
        neighbours = _grid(self._host)[2]
        mark = [False] * len(dist)
        remaining = 0
        for g in goals:
            if dist[g] >= d and not mark[g]:
                mark[g] = True
                remaining += 1
        if remaining == 0 or (first_only and remaining < len(set(goals))):
            return
        hit = False
        while d < size:
            for x in buckets[d]:
                if dist[x] != d:
                    continue
                if mark[x]:
                    mark[x] = False
                    remaining -= 1
                    hit = True
                for n in neighbours[x]:
                    nd = d + weight[n]
                    if nd < dist[n]:
                        dist[n] = nd
                        prev[n] = x
                        if nd >= size:
                            buckets.extend([[] for _ in range(nd + 1 - size)])
                            size = nd + 1
                        buckets[nd].append(n)
            d += 1
            if remaining == 0 or (first_only and hit):
                break
        state[3] = d
        state[4] = size

    def route(self, start, target, statuses):
        """(path, cost in heat units): the heat-cheapest route from start to target."""
        if start == target:
            return [], 0.0
        state = self.heat_search(start, statuses)
        sectors, index, _ = _grid(self._host)
        goal = index.get(target, len(sectors))
        self.expand_until(state, [goal])
        dist, prev = state[0], state[1]
        if dist[goal] >= INFINITE_COST:
            return [], 1e9
        first = index[start]
        path = []
        x = goal
        while x != first:
            path.append(sectors[x])
            x = prev[x]
        path.reverse()
        return path, dist[goal] / float(COST_SCALE)

    def cheapest(self, sectors, statuses):
        """
        The target with the lowest route cost from the current position (ties:
        sector id). The search stops at the first target it settles: every
        target still open then costs more.
        """
        here = self._host.get_position()
        state = self.heat_search(here, statuses)
        grid_sectors, index, _n = _grid(self._host)
        off_grid = len(grid_sectors)
        goals = [index.get(s, off_grid) for s in sectors]
        self.expand_until(state, goals, first_only=True)
        dist = state[0]
        return min([(dist[g], s) for g, s in zip(goals, sectors)])[1]

    # ----------------------------------------------------------- movement

    def hop(self, sector, status):
        """One cardinal move with just-in-time resting; measures the move's heat cost."""
        cost = self.move_cost(status)
        self.ensure_headroom(cost)
        h = self._host.harvester
        for _ in range(8):
            before = self._host.get_heat()
            res = h.move(sector)
            st = getattr(res, "status", "")
            if st == "ok":
                after = self._host.get_heat()
                observed = after - before + self.cool_per_hour * MOVE_HOURS
                if 0.0 <= observed <= 20.0:
                    self._learn(status or "unknown", observed)
                self._host.log.trace(f"Hop -> {sector} ({status}): heat {before:.1f} -> {after:.1f}.")
                return True
            if st == "already_here":
                return True
            if st == "overheated":
                self.cool_to(self.heat_cap() - cost)
            elif st in ("moving", "busy"):
                flush_all()
                sleep(1.0)
            else:
                self._host.log.level("warn").print(f"[{self._host.name}] move {sector} -> {st}: {getattr(res, 'message', '')}")
                return False
        return False

    def move_to(self, target_sector):
        """Override: follows the heat-cheapest route, using the step's cell statuses when set."""
        here = self._host.get_position()
        if here == target_sector:
            return True
        statuses = getattr(self, "step_statuses", None)
        if statuses is None:
            statuses = {s: getattr(c, "status", None) for s, c in self._host.read_cells().items()}
        path, cost = self.route(here, target_sector, statuses)
        log = self._host.log
        if not path:
            log.debug(f"[{self._host.name}] No route {here} -> {target_sector}.")
            return False
        log.start(f"[{self._host.name}] Move {here} -> {target_sector}", level="debug")
        start_tick, start_heat = _now_tick(), self._host.get_heat()
        log.debug(f"Route: {len(path)} hop(s) (~{len(path) * MOVE_HOURS:.1f} h), cost {cost:.1f}, heat {start_heat:.1f}.")
        for sector in path:
            if not self.hop(sector, statuses.get(sector)):
                log.end(f"Stopped at {self._host.get_position()} after {self.game_time(_now_tick() - start_tick)}")
                return False
            if sector != target_sector:
                self._host.work_on_pass(sector, statuses.get(sector))
        arrived = self._host.get_position() == target_sector
        log.end(f"{'Arrived' if arrived else 'Ended at ' + str(self._host.get_position())} after {self.game_time(_now_tick() - start_tick)}, "
                f"heat {start_heat:.1f} -> {self._host.get_heat():.1f}")
        return arrived
