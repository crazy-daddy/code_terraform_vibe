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


def discover_network_buildings(type_ids):
    """
    All building *objects* of the given type_id(s) (a single string or an
    iterable of them -- a Water Pump can fill either a Liquid Tank or a
    Large Liquid Tank) across every known outpost. A Water Pump has no
    .outpost of its own (built on a surveyed Water Well out in the field,
    not necessarily inside a founded outpost), so candidates must be
    discovered network-wide rather than scoped to "this building's outpost"
    -- see lib/thermal_cap.py's identically-reasoned discover_network_buildings().

    Resolves each BuildingRef to its full component via get_component(ref.id)
    before returning, same as thermal_cap.py -- outpost.buildings(type_id)
    hands back BuildingRef *snapshots* which lack fill_pct()/is_full()/etc.,
    only the resolved component has those.
    """
    if isinstance(type_ids, str):
        type_ids = (type_ids,)

    buildings = []
    seen_ids = set()
    network = get_component("outpost_network")
    if network and hasattr(network, "outposts"):
        try:
            for outpost in network.outposts():
                for type_id in type_ids:
                    for building in outpost.buildings(type_id):
                        b_id = getattr(building, "id", None)
                        if not b_id or b_id in seen_ids:
                            continue
                        try:
                            resolved = get_component(b_id) or building
                        except Exception:
                            resolved = building
                        seen_ids.add(b_id)
                        buildings.append(resolved)
        except Exception:
            pass
    return buildings


def _fill_pct_of_building(building):
    """fill_pct() of an already-resolved tank object, or 1.0 (treated as "full, deprioritize") if unreadable."""
    if not building or not hasattr(building, "fill_pct"):
        return 1.0
    try:
        return building.fill_pct()
    except Exception:
        return 1.0


class WaterPumpController:
    """Keeps a Water Pump's water_out pointed at a reachable, non-full Liquid Tank / Large Liquid Tank."""

    def __init__(self, pump):
        self.pump = pump
        self.name = getattr(pump, "id", "water_pump")
        self.clock = get_component("clock")
        # tank_id -> the simulation tick it was blacklisted at, NOT a plain
        # set -- see RESCAN_INTERVAL_TICKS for why per-entry timestamps
        # matter here. Same mechanism as thermal_cap.py's unreachable_targets.
        self.unreachable_targets = {}
        self.ticks_since_connect = 0
        self._cached_tanks = None
        self._ticks_since_discovery = 0
        # id -> resolved building object, merged across rediscovery, never
        # wholesale-cleared -- see thermal_cap.py's _tank_lookup.
        self._tank_lookup = {}
        # Tracked locally instead of re-querying port.connected_to() every
        # step -- seeded once from the real port state so a script reload
        # recovers an already-working connection. See thermal_cap.py's
        # _connected_tank_id/_tank_id_synced.
        self._connected_tank_id = None
        self._tank_id_synced = False

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception:
                pass
        return 0

    def is_blacklisted(self, tank_id, curr_tick):
        """Whether tank_id is still within its own blacklist window -- per-entry, not a shared clock. See lib/thermal_cap.py's identical is_blacklisted()."""
        blacklisted_at = self.unreachable_targets.get(tank_id)
        if blacklisted_at is None:
            return False
        age = curr_tick - blacklisted_at
        return curr_tick == 0 or age < RESCAN_INTERVAL_TICKS

    def _discover_tanks_cached(self):
        """Liquid Tank / Large Liquid Tank objects network-wide, refreshed at most every DISCOVERY_CACHE_INTERVAL_STEPS calls."""
        if self._cached_tanks is None or self._ticks_since_discovery >= DISCOVERY_CACHE_INTERVAL_STEPS:
            self._cached_tanks = discover_network_buildings(LIQUID_TANK_TYPE_IDS)
            for building in self._cached_tanks:
                self._tank_lookup[building.id] = building
            self._ticks_since_discovery = 0
        else:
            self._ticks_since_discovery += 1
        return self._cached_tanks

    def _resolve_tank(self, tank_id):
        """Building object for tank_id, preferring the cache filled by discovery over a fresh get_component() round trip."""
        building = self._tank_lookup.get(tank_id)
        if building is not None:
            return building
        try:
            building = get_component(tank_id)
        except Exception:
            building = None
        if building:
            self._tank_lookup[tank_id] = building
        return building

    def ensure_output_connection(self):
        """
        Declares/rebalances water_out's destination among known Liquid Tanks/
        Large Liquid Tanks (discovered network-wide). A tank has no script of
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

        if not self._tank_id_synced:
            try:
                self._connected_tank_id = port.connected_to() if hasattr(port, "connected_to") else None
            except Exception:
                self._connected_tank_id = None
            self._tank_id_synced = True
        current_id = self._connected_tank_id

        self.ticks_since_connect += 1

        # A stalled pump with an open throttle and well water available means
        # the currently connected target can't actually be reached by pipe --
        # connect() never verified that, it only accepted the pairing.
        # Blacklist it and force a reselect below. Skipped for the first
        # CONNECTION_GRACE_TICKS after connecting -- flow can take a tick to
        # register.
        is_stalled = False
        if hasattr(self.pump, "is_stalled"):
            try:
                is_stalled = self.pump.is_stalled()
            except Exception:
                is_stalled = False
        if is_stalled and current_id and not self.is_blacklisted(current_id, curr_tick) and self.ticks_since_connect >= CONNECTION_GRACE_TICKS:
            self.unreachable_targets[current_id] = curr_tick
            print(f"[{self.name}] '{current_id}' reported stalled (well water available, valve open, nothing transferred) -- likely no completed Liquid Pipe route. Blacklisting and picking a different target.")
            current_id = None
            self._connected_tank_id = None

        # Fast path: a connection already judged healthy needs no network
        # scan, and no fresh component resolution either.
        if current_id and not self.is_blacklisted(current_id, curr_tick) and _fill_pct_of_building(self._resolve_tank(current_id)) < LIQUID_TANK_REBALANCE_FILL_FRACTION:
            return

        all_known_tanks = self._discover_tanks_cached()
        tanks = [t for t in all_known_tanks if not self.is_blacklisted(t.id, curr_tick)]
        if not tanks:
            # Every known tank is still within its own blacklist window (or
            # none exist at all) -- deliberately do NOT wipe the blacklist
            # here; each entry expires on its own schedule (is_blacklisted()).
            if all_known_tanks:
                print(f"[{self.name}] Every known Liquid Tank is still within its blacklist window; waiting for one to expire.")
            else:
                print(f"[{self.name}] No Liquid Tank or Large Liquid Tank found network-wide yet; water_out has no destination.")
            return

        # Try the least-full known tank first (load-balances across several),
        # falling through to the next since not every tank is necessarily
        # physically pipe-reachable from this Pump's field location.
        for tank in sorted(tanks, key=_fill_pct_of_building):
            if tank.id == current_id:
                continue
            try:
                res = port.connect(tank.id)
            except Exception:
                continue
            if res.status == "ok":
                self.ticks_since_connect = 0
                self._connected_tank_id = tank.id
                print(f"[{self.name}] Connected water_out -> '{tank.id}' ({_fill_pct_of_building(tank)*100:.0f}% full).")
                return
            elif res.status != "busy":
                print(f"[{self.name}] water_out connect notice for '{tank.id}': {res.status} - {res.message}")

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
        while True:
            try:
                self.step()
            except Exception as error:
                print(f"[{self.name}] Water Pump exception: {error}")
            sleep(poll_interval)
