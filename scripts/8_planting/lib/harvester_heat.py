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

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

HEAT_SAFETY = 3.0             # never plan a hop that lands within this of the cap
COOL_PER_HOUR_DEFAULT = 3.0   # measured live, see cool_to()
MOVE_HOURS = 0.5
ACTION_HEAT_RESERVE = 9.0     # headroom kept before a field action (empty collect = +9)
HOP_TIME_WEIGHT = 1.5         # route cost of one hop's 0.5 h, in heat units
DEFAULT_MOVE_COST = 7.0       # entering a cell whose status has no measurement yet
# Plant cells measured live at about +1 (2026-09-24): the game charges +7 only
# for entering an empty cell. Unmeasured statuses (provider, base) start at
# DEFAULT_MOVE_COST and are learned on the first visit.
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
        except Exception:
            self.real_seconds_per_hour = 25.0

    def heat_model(self):
        return {
            "costs": {k: round(v, 2) for k, v in self.move_costs.items()},
            "actions": {k: round(v, 2) for k, v in self.action_costs.items()},
            "cool_per_hour": round(self.cool_per_hour, 2),
        }

    def heat_cap(self):
        try:
            return float(self._host.harvester.get_max_heat()) - HEAT_SAFETY
        except Exception:
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

    def heat_map(self, start, statuses):
        """
        (dist, prev) from `start` to every cell: Dijkstra with Dial buckets
        (hop cost = move cost of the entered cell + HOP_TIME_WEIGHT, scaled to
        integers), so one pass over the 192 cells serves both target choice
        and the route. Cached for the same start and the same statuses dict
        (identity, not contents: comparing 192 entries costs steps too), so
        the step's target choice and the route share one pass.
        """
        cached = getattr(self, "_heat_map_cache", None)
        if cached is not None and cached[0] == start and cached[1] is statuses:
            return cached[2], cached[3]
        status_weight = {}
        weight = {}
        for sector, status in statuses.items():
            w = status_weight.get(status)
            if w is None:
                w = max(1, int(round((self.move_cost(status) + HOP_TIME_WEIGHT) * COST_SCALE)))
                status_weight[status] = w
            weight[sector] = w
        default_w = int(round((DEFAULT_MOVE_COST + HOP_TIME_WEIGHT) * COST_SCALE))
        dist = {start: 0}
        prev = {}
        buckets = [[start]]
        d = 0
        while d < len(buckets):
            for x in buckets[d]:
                if dist.get(x) != d:
                    continue
                for n in field_neighbours(self._host, x):
                    nd = d + weight.get(n, default_w)
                    if nd < dist.get(n, 1 << 30):
                        dist[n] = nd
                        prev[n] = x
                        while len(buckets) <= nd:
                            buckets.append([])
                        buckets[nd].append(n)
            d += 1
        self._heat_map_cache = (start, statuses, dist, prev)
        return dist, prev

    def route(self, start, target, statuses):
        """(path, cost in heat units): the heat-cheapest route from start to target."""
        if start == target:
            return [], 0.0
        dist, prev = self.heat_map(start, statuses)
        if target not in dist:
            return [], 1e9
        path = []
        x = target
        while x != start:
            path.append(x)
            x = prev[x]
        path.reverse()
        return path, dist[target] / float(COST_SCALE)

    def cheapest(self, sectors, statuses):
        """The target with the lowest route cost from the current position."""
        here = self._host.get_position()
        dist, _ = self.heat_map(here, statuses)
        return min(sectors, key=lambda s: (dist.get(s, 1 << 30), s))

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
                observed = self._host.get_heat() - before + self.cool_per_hour * MOVE_HOURS
                if 0.0 <= observed <= 20.0:
                    self._learn(status or "unknown", observed)
                return True
            if st == "already_here":
                return True
            if st == "overheated":
                self.cool_to(self.heat_cap() - cost)
            elif st in ("moving", "busy"):
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
        if not path:
            return False
        self._host.log.debug(f"[{self._host.name}] Route {here} -> {target_sector}: {len(path)} hop(s), cost {cost:.1f}, heat {self._host.get_heat():.1f}.")
        for sector in path:
            if not self.hop(sector, statuses.get(sector)):
                return False
            if sector != target_sector:
                self._host.work_on_pass(sector, statuses.get(sector))
        return self._host.get_position() == target_sector
