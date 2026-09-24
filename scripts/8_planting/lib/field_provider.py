# Field providers: one controller for Grow Lamp, Sprinkler and Dispenser
# scripts (thin entrypoints in harvesting/grow_lamp.py, sprinkler.py,
# dispenser.py). Deployed by the Harvester onto the cells the field layout
# keeps free for them (lib/harvester_machines.py).
#
# Each step:
#   1. find the layout crops beside this machine that need its service
#      (light / water / salt, from `plant.layout` + `plant.recipes`)
#   2. keep the supply up: Sprinkler water_in through a FluidInputRouter
#      (same as the Fabricator / Plant Terraformer), Dispenser salt topped up
#      from Inventory / home Warehouses (storage.take_item)
#   3. enabled only while a neighbour needs the service and the Power Guard
#      hasn't shed it (`power.shedded`). A Sprinkler drinks Water even with
#      no crops beside it, so an unneeded one is switched off.
# The Harvester stops treating a cell by hand once the provider covers it
# (harvester_care.care_due(): flag set with 0 manual time).
#
# Telemetry: `plant.providers` = {machine_id: {"kind", "sector", "status",
# "buffer", "enabled", "tick"}} (one shared dict, stale entries pruned).

from archive import archive
import field_layout
import fluid_routing
from production import FLUID_SOURCE_TYPE_IDS, fluid_building_is_viable
from storage import take_item
from tree_console import TreeConsole
from version_guard import validate_game_version

LAYOUT_KEY = "plant.layout"        # same key as harvester_planting.LAYOUT_KEY
RECIPES_KEY = "plant.recipes"      # same key as seed_supply.RECIPES_KEY
STATUS_KEY = "plant.providers"

# Service each machine kind provides (field_layout.CARE_KINDS).
SERVICE = {"grow_lamp": "light", "sprinkler": "water", "dispenser": "salt"}

POLL_INTERVAL_S = 10.0
PUBLISH_INTERVAL_TICKS = 600       # telemetry at most once a minute
STATUS_STALE_TICKS = 36000         # a provider silent this long (~1 h) is dropped from telemetry

# Dispenser: top the 50-unit buffer up to DISPENSER_FILL once it drops below
# DISPENSER_REFILL_BELOW. Kept small so the Harvester's own salt (hand care
# of uncovered cells) isn't drained into buffers.
DISPENSER_REFILL_BELOW = 3
DISPENSER_FILL = 8

# Water input routing, same values as the Fabricator's water_in router
# (lib/fabricator.py) and the Plant Terraformer's.
FLUID_STALL_STREAK_BLACKLIST_THRESHOLD = 5
FLUID_RESCAN_INTERVAL_TICKS = 150
FLUID_DISCOVERY_CACHE_INTERVAL_TICKS = 100
FLUID_NEUTRAL_GRACE_STEPS = 5


class FieldProviderController:
    """Keeps one Grow Lamp / Sprinkler / Dispenser supplied and switched on only while needed."""

    def __init__(self, machine, kind):
        self.machine = machine
        self.kind = kind
        self.service = SERVICE.get(kind)
        self.name = getattr(machine, "id", kind)
        self.clock = get_component("clock")
        self.log = TreeConsole(module="field_provider")
        self._water_router = None
        self._last_status = None
        self._last_enabled = None
        self._last_publish_tick = -PUBLISH_INTERVAL_TICKS

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception:
                pass
        return 0

    def sector(self):
        try:
            return self.machine.position()
        except Exception:
            return None

    # --------------------------------------------------------------- demand

    def served_crops(self):
        """
        [(sector, species)] of layout crops beside this machine that need its
        service, or None when there is no stored layout yet (then the machine
        just runs).
        """
        layout = archive.get(LAYOUT_KEY, {})
        cells = layout.get("cells") if isinstance(layout, dict) else None
        if not isinstance(cells, dict) or not cells:
            return None
        rules = field_layout.rules_from_published(archive.get(RECIPES_KEY, {}))
        out = []
        for n in field_layout.neighbours(self.sector()):
            species = cells.get(n)
            if species and self.service in field_layout.care_kinds(rules, species):
                out.append((n, species))
        return out

    def is_shedded(self):
        shedded = archive.get("power.shedded", [])
        return isinstance(shedded, list) and self.name in shedded

    # --------------------------------------------------------------- supply

    def _discover_water_sources(self):
        type_ids = FLUID_SOURCE_TYPE_IDS["water_in"]
        pairs = []
        home_id = None
        network = get_component("outpost_network")
        if network and hasattr(network, "outposts"):
            try:
                for outpost in network.outposts():
                    o_id = getattr(outpost, "id", None)
                    if getattr(outpost, "is_home", False):
                        home_id = o_id
                    for type_id in type_ids:
                        for building in outpost.buildings(type_id):
                            b_id = getattr(building, "id", None)
                            if b_id and fluid_building_is_viable("water_in", type_id, building):
                                pairs.append((b_id, o_id))
            except Exception as error:
                self.log.debug(f"[{self.name}] water source discovery failed: {error}")
        # Field machines always stand on the home field.
        ids = fluid_routing.rank_own_outpost_first(pairs, home_id)
        self.log.debug(f"[{self.name}] water_in: sources (home first): {ids}.")
        return ids

    @staticmethod
    def _port_starved(port):
        """flow_rate() == 0 with room left -- a full port also reads 0, not a stall."""
        try:
            level = port.level() if hasattr(port, "level") else 0
            capacity = port.capacity() if hasattr(port, "capacity") else 0
            flow = port.flow_rate() if hasattr(port, "flow_rate") else 0
            return flow == 0 and (not capacity or level < capacity)
        except Exception:
            return False

    def ensure_water(self, curr_tick):
        port = getattr(self.machine, "water_in", None)
        if not port:
            return
        if self._water_router is None:
            self._water_router = fluid_routing.FluidInputRouter(
                discover=self._discover_water_sources,
                rescan_interval_ticks=FLUID_RESCAN_INTERVAL_TICKS,
                discovery_cache_interval_ticks=FLUID_DISCOVERY_CACHE_INTERVAL_TICKS,
                stall_streak_threshold=FLUID_STALL_STREAK_BLACKLIST_THRESHOLD,
                neutral_grace_steps=FLUID_NEUTRAL_GRACE_STEPS,
                label=f"{self.name}.water_in",
            )

        def on_dropped(source_id, reason):
            self.log.level("warn").print(f"[{self.name}] Dropping water source '{source_id}': {reason}. Picking another.")

        def on_connect_notice(source_id, status, message):
            self.log.level("warn").print(f"[{self.name}] water_in connect notice for '{source_id}': {status} - {message}")

        event = self._water_router.ensure(port, curr_tick, self._port_starved(port), on_dropped, on_connect_notice)
        if event.kind == "connected":
            self.log.print(f"[{self.name}] Connected water_in -> '{event.source_id}'.")
        elif event.kind == "not_found":
            self.log.debug(f"[{self.name}] no water source on the network.")

    def ensure_salt(self):
        port = getattr(self.machine, "input", None)
        if not port:
            return
        try:
            have = port.count()
        except Exception:
            return
        if have >= DISPENSER_REFILL_BELOW:
            self.log.debug(f"[{self.name}] salt buffer {have} >= {DISPENSER_REFILL_BELOW}; no top-up.")
            return
        report = {}
        moved = take_item(port, "salt", DISPENSER_FILL - have, report=report)
        if moved:
            self.log.print(f"[{self.name}] Loaded {moved} salt (buffer {have} -> {have + moved}).")
        else:
            self.log.debug(f"[{self.name}] No salt loaded ({report.get('sources')}).")

    # ----------------------------------------------------------------- step

    def set_enabled(self, enabled):
        try:
            if self.machine.is_enabled() == enabled:
                return
        except Exception:
            pass
        res = self.machine.set_enabled(enabled)
        self.log.debug(f"[{self.name}] set_enabled({enabled}) -> {getattr(res, 'status', '?')}")

    def step(self):
        curr_tick = self.get_current_tick()
        served = self.served_crops()
        needed = served is None or bool(served)
        shedded = self.is_shedded()
        self.log.debug(f"[{self.name}] {self.kind} at {self.sector()}: serves {served}, shedded {shedded}.")

        if needed and self.kind == "sprinkler":
            self.ensure_water(curr_tick)
        elif needed and self.kind == "dispenser":
            self.ensure_salt()

        enabled = needed and not shedded
        self.set_enabled(enabled)
        if enabled != self._last_enabled:
            why = "shed by the Power Guard" if shedded else ("no crop beside it needs " + str(self.service) if not needed else "serving " + ", ".join(f"{sp}@{s}" for s, sp in (served or [])))
            self.log.print(f"[{self.name}] {'On' if enabled else 'Off'}: {why}.")
            self._last_enabled = enabled

        try:
            status = self.machine.status()
        except Exception:
            status = "?"
        if status != self._last_status:
            if enabled and status not in ("active", "?"):
                self.log.level("warn").print(f"[{self.name}] Status {status}.")
            else:
                self.log.debug(f"[{self.name}] Status {self._last_status} -> {status}.")
            self._last_status = status
        self.publish(curr_tick, status, enabled)

    def publish(self, curr_tick, status, enabled):
        if curr_tick - self._last_publish_tick < PUBLISH_INTERVAL_TICKS:
            return
        self._last_publish_tick = curr_tick
        try:
            buffer = round(float(self.machine.buffer()), 3)
        except Exception:
            buffer = None
        entry = {"kind": self.kind, "sector": self.sector(), "status": status,
                 "buffer": buffer, "enabled": enabled, "tick": curr_tick}

        def updater(state):
            if not isinstance(state, dict):
                state = {}
            state[self.name] = entry
            for k in [k for k, e in state.items()
                      if k != self.name and (not isinstance(e, dict) or curr_tick - (e.get("tick") or 0) > STATUS_STALE_TICKS)]:
                state.pop(k, None)
            return state

        archive.transaction(STATUS_KEY, {}, updater)

    def run(self):
        self.log.print(f"Field provider ({self.name}, {self.kind}) online at {self.sector()}.")
        validate_game_version()
        while True:
            try:
                self.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Field provider exception: {e}")
            sleep(POLL_INTERVAL_S)
