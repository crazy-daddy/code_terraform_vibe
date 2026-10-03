from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from drill_sites import STATUS_KEY, DRILL_TYPE_IDS, advertised_drills

# Field Mining Drill telemetry (standard / Industrial / Heavy share one API,
# docs/components/mining_drill.md). A drill needs no control: it extracts on
# its own and the only script surface is drill_rate() plus a read-only
# PickupOutputSlot stockpile. What it can't do is tell anyone it stopped --
# drill_rate() silently drops to 0 once the stockpile is full, so this
# controller publishes fill level / time-to-full and warns on state changes.
#
# States (from drill_rate() and the stockpile, the only signals available):
#   "drilling" -- drill_rate() > 0
#   "full"     -- rate 0 and stockpile at capacity (needs a pickup)
#   "stalled"  -- rate 0 with room left: unpowered, no deposit under it, or a
#                 deposit harder than this drill cuts. The API can't tell
#                 these apart, so the warning lists all three.
#
# The published entry doubles as the drill's pickup advertisement: the pull
# hauler (lib/vehicle_cargo.py run_pull_loop()) reads "items" as free stock;
# where the drill stands comes from drill.positions (lib/drill_sites.py).

# One shared dict {drill_id: telemetry} (not one key per drill, CLAUDE.md
# rule 7). Drills live on mineral sites, not on the outpost network, so
# ArchiveCleaner's network-based pruning can't see them; entries not
# refreshed within STATUS_STALE_TICKS (10 ticks/s -> 1 h) are pruned here on
# every publish instead.
STATUS_STALE_TICKS = 36000

# Stockpile fills in hours (Mk I: 2,000 units at 25 t/h = ~80 h; Heavy:
# 5,000 at 200 t/h = ~25 h), so a minute between polls loses nothing.
POLL_INTERVAL_S = 60.0

# A drill extracts with no script running, and every reading here works from
# any script, so control_room_automation.py publishes every drill through
# publish_all_drills() and each drill's own script publishes once and ends:
# a running script shrinks every script's step budget (docs/cheatsheet/dev_workflow.md §1d-1).

# Fill fraction at which the drill is flagged "near_full" and warned about
# once, leaving a hauler time to get there before extraction stops.
NEAR_FULL_FRACTION = 0.8


class MiningDrillController:
    """Publishes one field Mining Drill's rate/fill/state to drill.status and warns on stalls."""

    def __init__(self, drill, drill_type="mining_drill"):
        self.drill = drill
        self.drill_type = drill_type
        self.name = getattr(drill, "id", "mining_drill")
        self.clock = get_component("clock")
        self.log = TreeConsole(module="mining_drill")
        self._last_state = None
        self._warned_near_full = False

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception as error:
                swallowed("mining_drill.MiningDrillController.get_current_tick: self.clock.tick", error)
        return 0

    def read_snapshot(self):
        """Live readings: rate (t/h), stockpile count/capacity and {item_id: units}."""
        try:
            rate = float(self.drill.drill_rate() or 0.0)
        except Exception as exc:
            swallowed("mining_drill.MiningDrillController.read_snapshot: self.drill.drill_rate", exc)
            rate = 0.0
        port = getattr(self.drill, "output", None)
        count, capacity, items = 0, 0, {}
        if port:
            try:
                count = int(port.count() or 0)
                capacity = int(port.capacity() or 0)
                for stack in port.stacks():
                    items[stack.id] = items.get(stack.id, 0) + stack.count
            except Exception as error:
                self.log.debug(f"[{self.name}] stockpile read failed: {error}")
        return rate, count, capacity, items

    @staticmethod
    def classify(rate, count, capacity):
        if rate > 0:
            return "drilling"
        if capacity > 0 and count >= capacity:
            return "full"
        return "stalled"

    @staticmethod
    def hours_to_full(rate, count, capacity):
        """Estimate at the current rate, assuming 1 stockpile unit = 1 t of ore; None when not drilling."""
        if rate <= 0 or capacity <= 0:
            return None
        return max(capacity - count, 0) / rate

    def report_transitions(self, state, fill, eta_h):
        self.log.start(f"[{self.name}] report_transitions", level="debug")
        if state != self._last_state:
            if state == "full":
                self.log.level("warn").print(f"[{self.name}] Stockpile full ({fill:.0%}); extraction stopped until a vehicle or drone picks up.")
            elif state == "stalled":
                self.log.level("warn").print(
                    f"[{self.name}] Not drilling with room left ({fill:.0%}): unpowered, no deposit under it, "
                    "or deposit too hard for this drill."
                )
            elif self._last_state is not None:
                self.log.print(f"[{self.name}] Drilling again.")
            self.log.debug(f"state {self._last_state} -> {state}.")
            self._last_state = state

        if fill >= NEAR_FULL_FRACTION and state == "drilling" and not self._warned_near_full:
            eta_text = f", full in ~{eta_h:.1f} h" if eta_h is not None else ""
            self.log.level("warn").print(f"[{self.name}] Stockpile {fill:.0%}{eta_text}. Schedule a pickup.")
            self._warned_near_full = True
        elif fill < NEAR_FULL_FRACTION and self._warned_near_full:
            self.log.debug(f"fill back under {NEAR_FULL_FRACTION:.0%}; near-full warning re-armed.")
            self._warned_near_full = False
        self.log.end()

    def publish_telemetry(self, entry, curr_tick):
        pruned = []
        if not archive.set_entry_pruned(STATUS_KEY, self.name, entry, curr_tick, STATUS_STALE_TICKS, pruned):
            self.log.level("warn").print(f"[{self.name}] {STATUS_KEY} write rejected; telemetry not published this cycle.")
            return
        for other_id in pruned:
            self.log.debug(f"[{self.name}] pruned stale {STATUS_KEY}['{other_id}'].")

    def step(self):
        curr_tick = self.get_current_tick()
        rate, count, capacity, items = self.read_snapshot()
        fill = count / capacity if capacity > 0 else 0.0
        state = self.classify(rate, count, capacity)
        eta_h = self.hours_to_full(rate, count, capacity)
        self.log.debug(
            f"[{self.name}] rate={rate:.2f} t/h, stockpile {count}/{capacity} ({fill:.0%}), "
            f"items={items}, state={state}, eta={'n/a' if eta_h is None else f'{eta_h:.1f} h'}."
        )
        self.report_transitions(state, fill, eta_h)
        self.publish_telemetry({
            "name": getattr(self.drill, "name", self.name),
            "type": self.drill_type,
            "state": state,
            "rate": round(rate, 2),
            "count": count,
            "capacity": capacity,
            "fill": round(fill, 3),
            "near_full": fill >= NEAR_FULL_FRACTION,
            "eta_h": None if eta_h is None else round(eta_h, 1),
            "items": items,
            "tick": curr_tick,
        }, curr_tick)

    def run(self):
        """Publishes once and ends; publish_all_drills() in control_room_automation.py keeps it current."""
        validate_game_version()
        reset_all()
        try:
            self.step()
        except Exception as error:
            self.log.level("error").print(f"[{self.name}] Mining Drill exception: {error}")
        self.log.print(f"[{self.name}] Telemetry published; control_room_automation.py keeps it current. Script ends (the drill keeps mining).")
        flush_all()


# {drill_id: MiningDrillController}, kept across publish_all_drills() calls so
# state-transition and near-full warnings fire once per change, not every pass.
_CONTROLLERS = {}


def drill_types():
    """{drill_id: type_id} of deployed drills: power grid members plus drill.status publishers."""
    found = {}
    power = get_component("power_control")
    try:
        grids = power.grids() if power else []
    except Exception as error:
        swallowed("mining_drill.drill_types: power.grids", error)
        grids = []
    for grid in grids:
        for member in getattr(grid, "members", []) or []:
            member_type = getattr(member, "type_id", "")
            if member_type in DRILL_TYPE_IDS:
                found[member.id] = member_type
    for drill_id, entry in advertised_drills().items():
        found.setdefault(drill_id, entry.get("type") or "mining_drill")
    return found


def publish_all_drills():
    """Publishes every deployed drill's telemetry (MiningDrillController.step()); returns how many were read."""
    published = 0
    types = drill_types()
    for drill_id, drill_type in types.items():
        controller = _CONTROLLERS.get(drill_id)
        if controller is None:
            drill = get_component(drill_id)
            if drill is None:
                continue
            controller = MiningDrillController(drill, drill_type=drill_type)
            _CONTROLLERS[drill_id] = controller
        try:
            controller.step()
            published += 1
        except Exception as error:
            swallowed("mining_drill.publish_all_drills: controller.step", error)
    for drill_id in [d for d in _CONTROLLERS if d not in types]:
        del _CONTROLLERS[drill_id]
    return published
