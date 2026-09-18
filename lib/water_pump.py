import fluid_routing
from version_guard import validate_game_version

# Shared Water Pump automation: keep water_out pointed at a reachable Liquid
# Tank / Large Liquid Tank, load-balancing across whichever ones have room.
# Deliberately much simpler than lib/thermal_cap.py: a Water Pump has no
# internal buffer to overpressure at all (docs/components/water_pump.md --
# no pressure()/is_overpressured()/relief() exist on it), so there's no
# release-valve/relief-valve reactive control to do. The only real job is the
# same "discover tanks network-wide, connect to the least-full one, blacklist
# an unreachable one and try the next" logic thermal_cap.py already has for
# Gas Tanks -- mirrored here for Liquid Tank/Large Liquid Tank, with every
# overpressure-specific bit dropped.

LIQUID_TANK_TYPE_IDS = ("liquid_tank", "large_liquid_tank")

# Only abandon the currently-targeted tank once it's essentially full (not
# merely "over 85%") -- re-evaluated every step(), so a softer threshold can
# ping-pong between two tanks both hovering above it, reconnecting water_out
# every cycle and never giving flow a chance to actually establish on either
# one. See lib/thermal_cap.py's GAS_TANK_REBALANCE_FILL_FRACTION for the full
# reasoning -- identical here, just without an overpressure consequence if it
# ping-pongs (a stalled Water Pump just doesn't draw from the well, nothing
# is lost the way banked steam is on a Thermal Cap).
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

# Caches the network-wide tank list for this many step() calls -- the
# steady-state fast path below (a healthy connection needs only a single
# fill_pct() read on the one id already in use) barely ever reaches this at
# all. See lib/thermal_cap.py's DISCOVERY_CACHE_INTERVAL_STEPS.
DISCOVERY_CACHE_INTERVAL_STEPS = 20


class WaterPumpController:
    """Keeps a Water Pump's water_out pointed at a reachable, non-full Liquid Tank / Large Liquid Tank."""

    def __init__(self, pump):
        self.pump = pump
        self.name = getattr(pump, "id", "water_pump")
        self.clock = get_component("clock")
        # See lib/fluid_routing.py's FluidOutputRouter/PerEntryBlacklist for
        # the full rationale (per-entry blacklist expiry, BuildingRef
        # resolution, id-lookup/connected-id-sync caching) -- this router
        # owns all of it; WaterPumpController only supplies its own tuning
        # constants and print wording.
        self._router = fluid_routing.FluidOutputRouter(
            type_ids=LIQUID_TANK_TYPE_IDS,
            rebalance_fill_fraction=LIQUID_TANK_REBALANCE_FILL_FRACTION,
            connection_grace_ticks=CONNECTION_GRACE_TICKS,
            rescan_interval_ticks=RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_steps=DISCOVERY_CACHE_INTERVAL_STEPS,
        )

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception:
                pass
        return 0

    def ensure_output_connection(self):
        """
        Declares/rebalances water_out's destination among known Liquid Tanks/
        Large Liquid Tanks (discovered network-wide -- see
        fluid_routing.discover_network_buildings()). A tank has no script of
        its own (purely passive), so this Pump's own script must declare the
        link, and water_out only ever holds one destination at a time (per
        docs/components/water_pump.md), so serving several tanks means
        periodically re-pointing it rather than a simultaneous fan-out.

        Any other scripted consumer connecting its OWN water_in to this Pump
        (docs/components/water_pump.md: "additional consumers may connect
        their own water_in ports to this Pump") is independent of whatever
        water_out is currently pointed at -- no coordination needed here,
        same as thermal_cap.py's Steam Turbine relationship.
        """
        port = getattr(self.pump, "water_out", None)
        if not port or not hasattr(port, "connect"):
            return

        curr_tick = self.get_current_tick()
        is_stalled = fluid_routing.safe_is_stalled(self.pump)

        def on_blacklisted(target_id):
            print(f"[{self.name}] '{target_id}' reported stalled (well water available, valve open, nothing transferred) -- likely no completed Liquid Pipe route. Blacklisting and picking a different target.")

        def on_connect_notice(target_id, status, message):
            print(f"[{self.name}] water_out connect notice for '{target_id}': {status} - {message}")

        event = self._router.ensure_connection(port, curr_tick, is_stalled, on_blacklisted, on_connect_notice)
        if event.kind == "connected":
            print(f"[{self.name}] Connected water_out -> '{event.target_id}' ({event.fill_pct*100:.0f}% full).")
        elif event.kind == "waiting":
            print(f"[{self.name}] Every known Liquid Tank is still within its blacklist window; waiting for one to expire.")
        elif event.kind == "not_found":
            print(f"[{self.name}] No Liquid Tank or Large Liquid Tank found network-wide yet; water_out has no destination.")

    def step(self):
        self.ensure_output_connection()

        # No overpressure ceiling to react to (unlike Thermal Cap) -- a Water
        # Pump just doesn't draw from the well when nothing downstream can
        # accept it (docs/components/water_pump.md: pump_rate() reads 0 with
        # throttle open but no destination able to accept), so there's no
        # cost to always requesting full output; actual delivery already
        # self-limits to whatever a connected tank can actually take.
        if hasattr(self.pump, "set_throttle"):
            self.pump.set_throttle(1.0)

        if hasattr(self.pump, "is_stalled") and self.pump.is_stalled():
            print(f"[{self.name}] Stalled: valve open with well water available but nothing downstream is accepting it. Check water_out connection / Liquid Tank / pipe route.")

    def run(self, poll_interval=1.0):
        print(f"Water Pump Controller ({self.name}) online. Routing water to network Liquid Tanks.")
        validate_game_version()
        while True:
            try:
                self.step()
            except Exception as error:
                print(f"[{self.name}] Water Pump exception: {error}")
            sleep(poll_interval)
