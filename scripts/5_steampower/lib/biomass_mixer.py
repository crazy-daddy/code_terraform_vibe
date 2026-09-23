import fluid_routing
from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole

# Shared Biomass Mixer automation. Nothing to tune -- the Mixer picks its own
# strongest balanced mix every tick (docs/components/biomass_mixer.md), and
# extra balanced essences only ever help. The only job is to keep every one
# of its five <biome>_essence_in ports fed from a reachable source:
#   1. a Liquid Tank latched/assigned to that essence (the shared buffer the
#      Liquifiers' own FluidOutputRouter fills -- lib/essence_liquifier.py),
#   2. failing that, a same-biome Essence Liquifier directly (its output port
#      explicitly accepts a "matching Mixer input" as a peer).
# Own-outpost candidates are tried first within each group (a local link
# needs no pipe at all), same ranking as lib/steam_turbine.py.
#
# Consumer-side, like Steam Turbine, so it composes fluid_routing's primitives
# rather than FluidOutputRouter. Reachability comes straight from
# port.connections()' per-peer FluidConnection.state instead of is_stalled()
# -- a Mixer's is_stalled() is one machine-wide "fewer essences than the
# phase needs" flag and can't say which input is broken. Starvation is judged
# per port instead (see _port_starved()): a link can read "ready" to a remote
# Liquifier that has run dry while a same-essence tank sits full next to the
# Mixer, and link state alone would keep that dead link forever.

ESSENCE_BIOMES = ("frozen", "coastal", "geothermal", "volcanic", "deep")
LIQUIFIER_TYPE_ID = "essence_liquifier"

# A freshly declared link to an empty, not-yet-latched tank reads "neutral"
# (no fluid established) rather than healthy or broken. Give it this many
# step() calls to start flowing before giving up on it -- and even then only
# when some other untried candidate exists (see EssenceInputRouter.ensure()).
NEUTRAL_GRACE_STEPS = 6

# Per-entry blacklist expiry for a source found unreachable (a new Liquid
# Pipe may get built later) -- see fluid_routing.PerEntryBlacklist.
RESCAN_INTERVAL_TICKS = 300

# Candidate list cache in simulation ticks, not calls -- see
# fluid_routing.TickedDiscoveryCache.
DISCOVERY_CACHE_INTERVAL_TICKS = 100

# Per-port starvation: buffer below STARVED_LEVEL_T with flow_rate() == 0.
# A well-stocked buffer that isn't flowing (Mixer not selecting that essence
# right now) is not starved. After STALL_STREAK_THRESHOLD consecutive starved
# step() calls (~30 s at the 5 s poll) the source is dropped and blacklisted,
# so the router moves on to the next candidate (e.g. a full tank).
STARVED_LEVEL_T = 1.0
STALL_STREAK_THRESHOLD = 6

STATUS_KEY_PREFIX = "biomass_mixer.status."


class EssenceInputRouter:
    """Keeps one <biome>_essence_in port connected to a reachable tank or Liquifier of that essence,
    via the shared consumer-side fluid_routing.FluidInputRouter."""

    def __init__(self, mixer, biome, log):
        self.mixer = mixer
        self.biome = biome
        self.fluid_id = f"{biome}_essence"
        self.port_name = f"{self.fluid_id}_in"
        self.log = log
        self.name = getattr(mixer, "id", "biomass_mixer")
        self._router = fluid_routing.FluidInputRouter(
            discover=self._discover_candidates,
            rescan_interval_ticks=RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=DISCOVERY_CACHE_INTERVAL_TICKS,
            # Starvation comes from this port's own buffer (_port_starved()), not the Mixer's
            # machine-wide is_stalled().
            stall_streak_threshold=STALL_STREAK_THRESHOLD,
            neutral_grace_steps=NEUTRAL_GRACE_STEPS,
            label=f"{self.name}.{self.port_name}",
        )

    def port(self):
        return getattr(self.mixer, self.port_name, None)

    def _port_starved(self, port):
        """Buffer nearly empty and nothing flowing in -- the linked source has nothing to give."""
        try:
            level = port.level()
            flow = port.flow_rate()
        except Exception:
            return False
        starved = level < STARVED_LEVEL_T and flow == 0
        if starved:
            self.log.debug(f"[{self.name}] {self.port_name}: starved (level {level:.2f} t < {STARVED_LEVEL_T} t, flow 0).")
        return starved

    def _discover_candidates(self):
        """Source ids: essence tanks first, then same-biome Liquifiers; own outpost first within each group."""
        own_outpost_id = getattr(getattr(self.mixer, "outpost", None), "id", None)
        tanks = fluid_routing.discover_network_buildings(fluid_routing.LIQUID_TANK_TYPE_IDS, resolve=False, fluid_id=self.fluid_id)

        liquifiers = []
        for building, outpost_id in fluid_routing.discover_network_buildings(LIQUIFIER_TYPE_ID, resolve=True):
            try:
                biome = building.biome()
            except Exception:
                biome = None
            if biome == self.biome:
                liquifiers.append((building.id, outpost_id))

        candidates = fluid_routing.rank_own_outpost_first(tanks, own_outpost_id) + fluid_routing.rank_own_outpost_first(liquifiers, own_outpost_id)
        self.log.debug(f"[{self.name}] {self.port_name}: discovered {len(tanks)} tank(s) + {len(liquifiers)} Liquifier(s) -> {candidates}.")
        return candidates

    def ensure(self, curr_tick):
        """Returns one of "no_port"/"healthy"/"pending"/"connected"/"waiting"/"not_found"/"exhausted"."""
        def on_dropped(source_id, reason):
            self.log.level("warn").print(f"[{self.name}] {self.port_name}: dropping '{source_id}' ({reason}). Trying another source.")

        def on_connect_notice(source_id, status, message):
            self.log.level("warn").print(f"[{self.name}] {self.port_name} connect notice for '{source_id}': {status} - {message}")

        port = self.port()
        is_starved = bool(port) and self._port_starved(port)
        event = self._router.ensure(port, curr_tick, is_starved=is_starved, on_dropped=on_dropped, on_connect_notice=on_connect_notice)
        if event.kind == "healthy":
            self.log.trace(f"[{self.name}] {self.port_name}: healthy via '{event.source_id}'.")
        elif event.kind == "connected":
            self.log.print(f"[{self.name}] Connected {self.port_name} -> '{event.source_id}'.")
        elif event.kind == "waiting":
            self.log.debug(f"[{self.name}] {self.port_name}: every known source is blacklisted; waiting for expiry.")
        elif event.kind == "not_found":
            self.log.debug(f"[{self.name}] {self.port_name}: no '{self.fluid_id}' tank or '{self.biome}' Liquifier anywhere yet.")
        return event.kind


class BiomassMixerController:
    """Keeps every essence input of a Biomass Mixer connected; reports phase/diversity status."""

    def __init__(self, mixer):
        self.mixer = mixer
        self.name = getattr(mixer, "id", "biomass_mixer")
        self.clock = get_component("clock")
        self.log = TreeConsole(module="biomass_mixer")
        self.routers = [EssenceInputRouter(mixer, biome, self.log) for biome in ESSENCE_BIOMES]
        self._was_stalled = False

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception:
                pass
        return 0

    def _read(self, method, default):
        try:
            return getattr(self.mixer, method)()
        except Exception:
            return default

    def ensure_input_connections(self):
        curr_tick = self.get_current_tick()
        fluid_routing.warn_about_unassigned_tanks(curr_tick)
        results = {router.biome: router.ensure(curr_tick) for router in self.routers}
        self.log.debug(f"[{self.name}] input routing: {results}.")
        return results

    def check_stall(self):
        """Warn once on entering a stall (fewer essences than the phase needs), note once on recovery."""
        stalled = bool(self._read("is_stalled", False))
        if stalled and not self._was_stalled:
            self.log.level("warn").print(
                f"[{self.name}] Stalled: {self._read('active_essences', 0)} essence type(s) supplied, "
                f"phase {self._read('phase', '?')} needs {self._read('required_essences', '?')}. "
                "Bring another biome's Liquifier/tank online."
            )
        elif not stalled and self._was_stalled:
            self.log.print(f"[{self.name}] Mixing again ({self._read('mixing_essences', 0)} essences, {self._read('biomass_rate', 0.0):.2f} t/h).")
        self._was_stalled = stalled

    def publish_telemetry(self, results):
        inputs = {}
        for router in self.routers:
            port = router.port()
            try:
                level = port.level() if port else 0.0
            except Exception:
                level = 0.0
            inputs[router.biome] = {
                "source": fluid_routing.healthy_peer_id(port) if port else None,
                "route": results.get(router.biome),
                "level": level,
            }
        archive.set(f"{STATUS_KEY_PREFIX}{self.name}", {
            "name": self.name,
            "tier": self._read("tier", 1),
            "phase": self._read("phase", 0),
            "required": self._read("required_essences", 0),
            "active": self._read("active_essences", 0),
            "mixing": self._read("mixing_essences", 0),
            "biomass_rate": self._read("biomass_rate", 0.0),
            "stalled": self._was_stalled,
            "inputs": inputs,
        })

    def step(self):
        results = self.ensure_input_connections()
        self.check_stall()
        self.publish_telemetry(results)

    def run(self, poll_interval=5.0):
        self.log.print(f"Biomass Mixer Controller ({self.name}) online (Mk {self._read('tier', 1)}, phase {self._read('phase', '?')}).")
        validate_game_version()
        while True:
            try:
                self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Biomass Mixer exception: {error}")
            sleep(poll_interval)
