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
from production import discover_fluid_sources, home_outpost_id
from storage import take_item
from tree_console import TreeConsole
from swallow import swallowed
from script_parking import ParkRequester
from machine_controller import MachineController

LAYOUT_KEY = "plant.layout"        # same key as harvester_planting.LAYOUT_KEY
RECIPES_KEY = "plant.recipes"      # same key as seed_supply.RECIPES_KEY
STATUS_KEY = "plant.providers"

# Service each machine kind provides (field_layout.CARE_KINDS).
SERVICE = {"grow_lamp": "light", "sprinkler": "water", "dispenser": "salt"}

POLL_INTERVAL_S = 10.0
PUBLISH_INTERVAL_TICKS = 600       # telemetry at most once a minute

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


class FieldProviderController(MachineController):
    """Keeps one Grow Lamp / Sprinkler / Dispenser supplied and switched on only while needed."""
    LABEL = "Field provider"
    POLL_S = POLL_INTERVAL_S

    def online_message(self):
        return f"Field provider ({self.name}, {self.kind}) online at {self.sector()}."

    def next_sleep(self, result, failed):
        if failed:
            self.parker.update(False)
        return self.POLL_S

    def __init__(self, machine, kind):
        self.machine = machine
        self.kind = kind
        self.service = SERVICE.get(kind)
        self.name = getattr(machine, "id", kind)
        self.log = TreeConsole(module="field_provider")
        self._water_router = None
        self._last_status = None
        self._last_enabled = None
        self._last_publish_tick = -PUBLISH_INTERVAL_TICKS
        self.parker = ParkRequester(self.name, "field_provider")

    def sector(self):
        try:
            return self.machine.position()
        except Exception as error:
            swallowed("field_provider.FieldProviderController.sector: self.machine.position", error)
            return None

    # --------------------------------------------------------------- demand

    def is_stray(self, layout=None):
        """True when the full layout doesn't reserve this machine's cell for its kind."""
        layout = archive.get(LAYOUT_KEY, {}) if layout is None else layout
        if not isinstance(layout, dict) or layout.get("mode") != "full":
            return False
        return (layout.get("reserved") or {}).get(self.sector()) != self.kind

    def empty_input(self):
        """Stray: ejects the input buffer (Dispenser salt) to Inventory, so the Harvester can undeploy it (eject() is self-only)."""
        port = getattr(self.machine, "input", None)
        if not port:
            return
        try:
            for stack in port.stacks():
                res = port.eject("inventory", stack.id, stack.count)
                self.log.print(f"[{self.name}] Not in the field layout: ejected {stack.count} {stack.id} to Inventory -> {getattr(res, 'status', '?')}.")
        except Exception as error:
            swallowed("field_provider.FieldProviderController.empty_input: port.eject", error)

    def served_crops(self):
        """
        [(sector, species)] of layout crops beside this machine that need its
        service, or None when there is no stored layout yet (then the machine
        just runs). [] for a machine the full layout doesn't reserve (left
        over from an older layout; the Harvester removes it).
        """
        layout = archive.get(LAYOUT_KEY, {})
        cells = layout.get("cells") if isinstance(layout, dict) else None
        if not isinstance(cells, dict) or not cells:
            return None
        if self.is_stray(layout):
            return []
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
        self.log.start(f"[{self.name}] _discover_water_sources", level="debug")
        # Field machines always stand on the home field.
        ids = discover_fluid_sources("water_in", home_outpost_id())
        self.log.debug(f"water_in: sources (home first): {ids}.")
        self.log.end()
        return ids

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
                reserve_fluid="water",
            )
        fluid_routing.ensure_input_logged(self._water_router, port, curr_tick, fluid_routing.port_starved(port), self.log, self.name, "water_in",
                                          "No water source on the network.")

    def ensure_salt(self):
        self.log.start(f"[{self.name}] ensure_salt", level="debug")
        port = getattr(self.machine, "input", None)
        if not port:
            self.log.end()
            return
        try:
            have = port.count()
        except Exception as error:
            swallowed("field_provider.FieldProviderController.ensure_salt: port.count", error)
            self.log.end()
            return
        if have >= DISPENSER_REFILL_BELOW:
            self.log.debug(f"salt buffer {have} >= {DISPENSER_REFILL_BELOW}; no top-up.")
            self.log.end()
            return
        report = {}
        moved = take_item(port, "salt", DISPENSER_FILL - have, report=report)
        if moved:
            self.log.print(f"[{self.name}] Loaded {moved} salt (buffer {have} -> {have + moved}).")
        else:
            self.log.debug(f"No salt loaded ({report.get('sources')}).")
        self.log.end()

    # ----------------------------------------------------------------- step

    def set_enabled(self, enabled):
        try:
            if self.machine.is_enabled() == enabled:
                return
        except Exception as error:
            swallowed("field_provider.FieldProviderController.set_enabled: self.machine.is_enabled", error)
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
        elif self.is_stray():
            self.empty_input()

        enabled = needed and not shedded
        self.set_enabled(enabled)
        # Switched off (not shed, not a stray the Harvester removes) has nothing to do
        # until the layout or the recipes change: lib/script_parking.py parks it (the
        # breaker keeps set_enabled(False)); harvester_planting / seed_supply wake it.
        self.parker.update(not enabled and not shedded and served is not None and not self.is_stray())
        if enabled != self._last_enabled:
            why = "shed by the Power Guard" if shedded else ("no crop beside it needs " + str(self.service) if not needed else "serving " + ", ".join(f"{sp}@{s}" for s, sp in (served or [])))
            self.log.print(f"[{self.name}] {'On' if enabled else 'Off'}: {why}.")
            self._last_enabled = enabled

        try:
            status = self.machine.status()
        except Exception as error:
            swallowed("field_provider.FieldProviderController.step: self.machine.status", error)
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
        except Exception as error:
            swallowed("field_provider.FieldProviderController.publish: self.machine.buffer", error)
            buffer = None
        entry = {"kind": self.kind, "sector": self.sector(), "status": status,
                 "buffer": buffer, "enabled": enabled}
        archive.publish_status(STATUS_KEY, self.name, entry, curr_tick, self.log)
