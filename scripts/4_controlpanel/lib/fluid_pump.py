import fluid_routing
from version_guard import validate_game_version
from tree_console import TreeConsole

# Shared well-pump automation (Water Pump, Oil Pump): keep <fluid>_out pointed
# at a reachable Liquid Tank / Large Liquid Tank, load-balancing across
# whichever ones have room. Both pumps expose the same API
# (docs/components/water_pump.md, docs/components/oil_pump.md) apart from the
# port name (water_out / oil_out) and the Oil Pump's extra well_active() --
# oil wells pulse between active and dormant phases, water wells don't.
#
# Deliberately much simpler than lib/thermal_cap.py: a pump has no internal
# buffer to overpressure at all (no pressure()/is_overpressured()/relief()
# exist on it), so there's no release-valve/relief-valve reactive control to
# do. The only real job is the same "discover tanks network-wide, connect to
# the least-full one, blacklist an unreachable one and try the next" logic
# thermal_cap.py already has for Gas Tanks -- mirrored here for Liquid Tank/
# Large Liquid Tank, with every overpressure-specific bit dropped.
#
# Water and oil never share a tank: the router passes fluid_id to
# fluid_routing.discover_network_buildings(), whose tank_is_eligible_target()
# rejects a tank latched to another fluid and accepts an empty tank only when
# fluid_routing.tank_assignments reserves it for this fluid.

LIQUID_TANK_TYPE_IDS = ("liquid_tank", "large_liquid_tank")

# Display names per fluid_id, for log lines only.
PUMP_LABELS = {"water": "Water Pump", "oil": "Oil Pump"}

# Only abandon the currently-targeted tank once it's essentially full (not
# merely "over 85%") -- re-evaluated every step(), so a softer threshold can
# ping-pong between two tanks both hovering above it, reconnecting <fluid>_out
# every cycle and never giving flow a chance to actually establish on either
# one. See lib/thermal_cap.py's GAS_TANK_REBALANCE_FILL_FRACTION for the full
# reasoning -- identical here, just without an overpressure consequence if it
# ping-pongs (a stalled pump just doesn't draw from the well, nothing is lost
# the way banked steam is on a Thermal Cap).
LIQUID_TANK_REBALANCE_FILL_FRACTION = 0.98

# Skip trusting is_stalled() as "target unreachable" evidence for this many
# ticks right after (re)connecting -- flow can take a tick to register. See
# lib/thermal_cap.py's CONNECTION_GRACE_TICKS.
CONNECTION_GRACE_TICKS = 2

# A target blacklisted as unreachable might become reachable later (a new
# Liquid Pipe route gets built) -- tracked per-entry (tank_id -> the tick it
# was blacklisted at), not as one shared "clear everything at once" timer.
# See lib/thermal_cap.py's RESCAN_INTERVAL_TICKS for the full reasoning
# (per-entry expiry prevents one shared clock from wiping elimination
# progress against several simultaneously-unreachable candidates at once).
RESCAN_INTERVAL_TICKS = 300

# Caches the network-wide tank list for this many simulation ticks -- the
# steady-state fast path below (a healthy connection needs only a single
# fill_pct() read on the one id already in use) barely ever reaches this at
# all. See lib/thermal_cap.py's DISCOVERY_CACHE_INTERVAL_TICKS.
DISCOVERY_CACHE_INTERVAL_TICKS = 100


class FluidPumpController:
    """Keeps a well pump's <fluid_id>_out pointed at a reachable, non-full Liquid Tank / Large Liquid Tank."""

    def __init__(self, pump, fluid_id):
        self.pump = pump
        self.fluid_id = fluid_id
        self.port_name = f"{fluid_id}_out"
        self.label = PUMP_LABELS.get(fluid_id, f"{fluid_id} pump")
        self.name = getattr(pump, "id", f"{fluid_id}_pump")
        self.clock = get_component("clock")
        self.log = TreeConsole(module="fluid_pump")
        self._was_dormant = None
        # See lib/fluid_routing.py's FluidOutputRouter/PerEntryBlacklist for
        # the full rationale (per-entry blacklist expiry, BuildingRef
        # resolution, id-lookup/connected-id-sync caching) -- this router
        # owns all of it; FluidPumpController only supplies its own tuning
        # constants and print wording.
        self._router = fluid_routing.FluidOutputRouter(
            type_ids=LIQUID_TANK_TYPE_IDS,
            rebalance_fill_fraction=LIQUID_TANK_REBALANCE_FILL_FRACTION,
            connection_grace_ticks=CONNECTION_GRACE_TICKS,
            rescan_interval_ticks=RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=DISCOVERY_CACHE_INTERVAL_TICKS,
            fluid_id=fluid_id,
        )

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception:
                pass
        return 0

    def well_dormant(self):
        """True only when the pump reports a dormant well (Oil Pump's well_active()). A Water Pump has no such method and is never dormant."""
        if not hasattr(self.pump, "well_active"):
            return False
        try:
            return not self.pump.well_active()
        except Exception:
            return False

    def ensure_output_connection(self):
        """
        Declares/rebalances <fluid>_out's destination among known Liquid
        Tanks/Large Liquid Tanks (discovered network-wide -- see
        fluid_routing.discover_network_buildings()). A tank has no script of
        its own (purely passive), so this Pump's own script must declare the
        link, and the output port only ever holds one destination at a time
        (per docs/components/water_pump.md / oil_pump.md), so serving several
        tanks means periodically re-pointing it rather than a simultaneous
        fan-out.

        Any other scripted consumer connecting its OWN <fluid>_in to this Pump
        (e.g. an Oil Generator's oil_in) is independent of whatever the output
        port is currently pointed at -- no coordination needed here, same as
        thermal_cap.py's Steam Turbine relationship.
        """
        port = getattr(self.pump, self.port_name, None)
        if not port or not hasattr(port, "connect"):
            return

        curr_tick = self.get_current_tick()
        is_stalled = fluid_routing.safe_is_stalled(self.pump)
        self.log.debug(f"[{self.name}] Evaluating {self.port_name} connection at tick {curr_tick} (stalled={is_stalled}, known candidates cached={len(self._router._cached_targets) if self._router._cached_targets is not None else 0}).")

        def on_blacklisted(target_id):
            self.log.level("warn").print(f"[{self.name}] '{target_id}' reported stalled ({self.fluid_id} available, valve open, nothing transferred) -- likely no completed Liquid Pipe route. Blacklisting and picking a different target.")

        def on_connect_notice(target_id, status, message):
            self.log.level("warn").print(f"[{self.name}] {self.port_name} connect notice for '{target_id}': {status} - {message}")

        event = self._router.ensure_connection(port, curr_tick, is_stalled, on_blacklisted, on_connect_notice)
        if event.kind == "connected":
            self.log.print(f"[{self.name}] Connected {self.port_name} -> '{event.target_id}' ({event.fill_pct*100:.0f}% full).")
        elif event.kind == "healthy":
            self.log.debug(f"[{self.name}] Current {self.port_name} target still healthy; no rebalance needed this cycle.")
        elif event.kind == "waiting":
            self.log.debug(f"[{self.name}] Every known {self.fluid_id} tank is still within its blacklist window; waiting for one to expire.")
            for tid, blacklisted_at in self._router.blacklist._blacklisted_at.items():
                remaining = max(0, self._router.blacklist.rescan_interval_ticks - (curr_tick - blacklisted_at))
                self.log.debug(f"[{self.name}] Blacklisted target '{tid}': {remaining} tick(s) remaining until retry-eligible.")
        elif event.kind == "not_found":
            self.log.debug(f"[{self.name}] No Liquid Tank or Large Liquid Tank eligible for {self.fluid_id} found network-wide yet (an empty tank needs a fluid_routing.tank_assignments entry); {self.port_name} has no destination.")

    def step(self):
        # A dormant oil well delivers nothing at any throttle
        # (docs/components/oil_pump.md), so idle the pump to save its 5 W and
        # skip routing -- is_stalled() stays False while dormant anyway, so
        # there is no reachability evidence to gather until the well wakes.
        dormant = self.well_dormant()
        if dormant != self._was_dormant:
            if dormant:
                self.log.print(f"[{self.name}] Well dormant -- throttle 0 until it becomes active again.")
            elif self._was_dormant:
                self.log.print(f"[{self.name}] Well active again -- resuming pumping.")
            self._was_dormant = dormant
        if dormant:
            if hasattr(self.pump, "set_throttle"):
                self.pump.set_throttle(0.0)
            return

        self.ensure_output_connection()

        # No overpressure ceiling to react to (unlike Thermal Cap) -- a pump
        # just doesn't draw from the well when nothing downstream can accept
        # it (pump_rate() reads 0 with throttle open but no destination able
        # to accept), so there's no cost to always requesting full output;
        # actual delivery already self-limits to whatever a connected tank
        # can actually take.
        if hasattr(self.pump, "set_throttle"):
            self.pump.set_throttle(1.0)

        if hasattr(self.pump, "is_stalled") and self.pump.is_stalled():
            self.log.level("warn").print(f"[{self.name}] Stalled: valve open with {self.fluid_id} available but nothing downstream is accepting it. Check {self.port_name} connection / Liquid Tank / pipe route.")

    def run(self, poll_interval=1.0):
        self.log.print(f"{self.label} Controller ({self.name}) online. Routing {self.fluid_id} to network Liquid Tanks.")
        validate_game_version()
        while True:
            try:
                self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] {self.label} exception: {error}")
            sleep(poll_interval)
