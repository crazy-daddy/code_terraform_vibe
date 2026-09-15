# Shared Steam Turbine automation: throttle for peak power while a healthy
# steam buffer is available, ease off before the buffer runs dry (avoid
# is_stalled()), and keep running through the night since steam is the only
# generation source while solar is out.
#
# Reads grid state the same way lib/power.py's PowerGridManager does
# (power_control.grid(self.name)), but does not run shedding/master-election
# itself -- that's the grid's existing solar Master's job (see lib/power.py,
# lib/solar.py). This controller only decides its own throttle.

# Buffer-health bands, read as a fraction of steam_in.capacity() (not a fixed
# tonnage) so they hold regardless of any future buffer-capacity upgrades.
STEAM_BUFFER_LOW_FRACTION = 0.15       # below this: ease off to avoid a dry stall
STEAM_BUFFER_HEALTHY_FRACTION = 0.40   # above this: safe to run at full/peak
THROTTLE_LOW_BUFFER = 0.15             # gentle draw while buffer is thin
THROTTLE_MARGINAL_BUFFER = 0.5         # moderate draw while buffer is rebuilding

# Daytime easing: once the grid's battery is this full and generation already
# meets consumption, there's no benefit to burning banked steam for power
# nobody needs -- ease off to save it for the night instead.
BATTERY_FULL_FRACTION = 0.98
THROTTLE_DEMAND_MET = 0.3


def discover_network_building_ids(type_id):
    """
    All building ids of type_id across every known outpost. Same pattern as
    lib/thermal_cap.py's helper of the same name -- a reachable Gas Tank or
    Thermal Cap isn't guaranteed to share this Turbine's own outpost (a
    Thermal Cap in particular may have no outpost at all, built directly on
    a vent out in the field), so candidates are gathered network-wide;
    physical Gas Pipe topology, not outpost membership, decides which
    actually succeed via connect().
    """
    ids = []
    network = get_component("outpost_network")
    if network and hasattr(network, "outposts"):
        try:
            for outpost in network.outposts():
                for building in outpost.buildings(type_id):
                    b_id = getattr(building, "id", None)
                    if b_id:
                        ids.append(b_id)
        except Exception:
            pass
    return ids


class SteamTurbineController:
    """Throttles a Steam Turbine based on its own steam buffer and grid state."""

    def __init__(self, turbine):
        self.turbine = turbine
        self.name = getattr(turbine, "id", "steam_turbine")
        self.clock = get_component("clock")
        self.power = get_component("power_control")
        self.connected_input = False

    def ensure_input_connection(self):
        """
        Declares steam_in's source if not already connected. A Gas Tank has no
        script of its own (purely passive -- see docs/components/gas_tank.md),
        so nothing ever calls connect() on its side of the pipe; this Turbine's
        own script must declare the link instead, same as it declares its own
        source for any other input port. Per docs/guide/infrastructure_and_pipes.md,
        a Turbine is exactly the kind of "additional consumer" that may connect
        its own steam_in straight to a Thermal Cap, independent of whatever the
        Cap's own steam_out currently points at -- so this tries every known
        Gas Tank first (the larger, shared buffer), then falls through to
        every known Thermal Cap directly if no tank connection succeeds.
        Candidates are gathered network-wide (see discover_network_building_ids()),
        since a reachable source isn't guaranteed to share this Turbine's own
        outpost, and physical Gas Pipe topology decides which one actually works.
        """
        if self.connected_input:
            return
        port = getattr(self.turbine, "steam_in", None)
        if not port or not hasattr(port, "connect"):
            return
        try:
            if hasattr(port, "connected_to") and port.connected_to():
                self.connected_input = True
                return
        except Exception:
            pass

        for type_id in ("gas_tank", "thermal_cap"):
            for source_id in discover_network_building_ids(type_id):
                try:
                    res = port.connect(source_id)
                except Exception:
                    continue
                if res.status == "ok":
                    self.connected_input = True
                    print(f"[{self.name}] Connected steam_in -> '{source_id}'.")
                    return
                elif res.status != "busy":
                    print(f"[{self.name}] steam_in connect notice for '{source_id}': {res.status} - {res.message}")

    def buffer_fraction(self):
        """Fraction (0-1) of steam_in's own buffer currently filled."""
        port = getattr(self.turbine, "steam_in", None)
        if not port or not hasattr(port, "level") or not hasattr(port, "capacity"):
            return 0.0
        try:
            capacity = port.capacity()
            if not capacity:
                return 0.0
            return port.level() / capacity
        except Exception:
            return 0.0

    def get_grid(self):
        if self.power and hasattr(self.power, "grid"):
            try:
                return self.power.grid(self.name)
            except Exception:
                pass
        return None

    def is_night(self):
        if self.clock and hasattr(self.clock, "get_elevation"):
            try:
                return self.clock.get_elevation() <= 0
            except Exception:
                pass
        return False

    def choose_throttle(self):
        fraction = self.buffer_fraction()

        # A thin buffer always wins -- running flat out against a near-empty
        # pipe is exactly what produces is_stalled(), regardless of day/night
        # or grid demand.
        if fraction < STEAM_BUFFER_LOW_FRACTION:
            return THROTTLE_LOW_BUFFER
        if fraction < STEAM_BUFFER_HEALTHY_FRACTION:
            return THROTTLE_MARGINAL_BUFFER

        # Buffer is healthy: steam is the only generator at night, so run flat
        # out to carry the grid regardless of current battery/demand state.
        if self.is_night():
            return 1.0

        # Daytime with a healthy buffer: ease off once the battery is full and
        # generation already covers consumption, so banked steam isn't burned
        # for power nobody currently needs -- save it for the coming night.
        grid = self.get_grid()
        if grid:
            stored = getattr(grid, "stored", 0.0)
            capacity = getattr(grid, "capacity", 0.0)
            generated = getattr(grid, "generated", 0.0)
            consumed = getattr(grid, "consumed", 0.0)
            battery_full = capacity > 0 and stored >= (capacity * BATTERY_FULL_FRACTION)
            demand_met = generated >= consumed
            if battery_full and demand_met:
                return THROTTLE_DEMAND_MET

        return 1.0

    def step(self):
        self.ensure_input_connection()

        throttle = self.choose_throttle()
        if hasattr(self.turbine, "set_throttle"):
            self.turbine.set_throttle(throttle)

        if hasattr(self.turbine, "is_stalled") and self.turbine.is_stalled():
            print(f"[{self.name}] Stalled: throttle is up but no steam is arriving. Check the feeding Cap's vent phase and the steam_in connection.")

    def run(self, poll_interval=2.0):
        print(f"Steam Turbine Controller ({self.name}) online.")
        while True:
            try:
                self.step()
            except Exception as error:
                print(f"[{self.name}] Steam Turbine exception: {error}")
            sleep(poll_interval)
