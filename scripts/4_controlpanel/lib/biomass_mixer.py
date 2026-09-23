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
# phase needs" flag and can't say which input is broken.

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

# Candidate list cache, in ensure() calls on the slow path.
DISCOVERY_CACHE_INTERVAL_STEPS = 20

STATUS_KEY_PREFIX = "biomass_mixer.status."


class EssenceInputRouter:
    """Keeps one <biome>_essence_in port connected to a reachable tank or Liquifier of that essence."""

    def __init__(self, mixer, biome, log):
        self.mixer = mixer
        self.biome = biome
        self.fluid_id = f"{biome}_essence"
        self.port_name = f"{self.fluid_id}_in"
        self.log = log
        self.name = getattr(mixer, "id", "biomass_mixer")
        self.blacklist = fluid_routing.PerEntryBlacklist(RESCAN_INTERVAL_TICKS)
        # Starts at 0 on (re)start so a link that's merely neutral after a power cycle gets its grace period too.
        self.steps_since_connect = 0
        self._cached_candidates = None
        self._steps_since_discovery = 0

    def port(self):
        return getattr(self.mixer, self.port_name, None)

    def _discover_candidates(self):
        """Source ids: essence tanks first, then same-biome Liquifiers; own outpost first within each group."""
        if self._cached_candidates is not None and self._steps_since_discovery < DISCOVERY_CACHE_INTERVAL_STEPS:
            self._steps_since_discovery += 1
            return self._cached_candidates

        own_outpost_id = getattr(getattr(self.mixer, "outpost", None), "id", None)
        tanks = fluid_routing.discover_network_buildings(fluid_routing.LIQUID_TANK_TYPE_IDS, resolve=False, fluid_id=self.fluid_id)
        tanks.sort(key=lambda p: p[1] != own_outpost_id)

        liquifiers = []
        for building, outpost_id in fluid_routing.discover_network_buildings(LIQUIFIER_TYPE_ID, resolve=True):
            try:
                biome = building.biome()
            except Exception:
                biome = None
            if biome == self.biome:
                liquifiers.append((building.id, outpost_id))
        liquifiers.sort(key=lambda p: p[1] != own_outpost_id)

        self._cached_candidates = [b_id for b_id, _ in tanks] + [b_id for b_id, _ in liquifiers]
        self._steps_since_discovery = 0
        self.log.debug(f"[{self.name}] {self.port_name}: discovered {len(tanks)} tank(s) + {len(liquifiers)} Liquifier(s) -> {self._cached_candidates}.")
        return self._cached_candidates

    def ensure(self, curr_tick):
        """Returns one of "no_port"/"healthy"/"pending"/"connected"/"waiting"/"not_found"/"exhausted"."""
        port = self.port()
        if not port or not hasattr(port, "connect"):
            return "no_port"

        # Any healthy peer, including a Liquifier that declared itself onto this port, is enough.
        peer = fluid_routing.healthy_peer_id(port)
        if peer:
            self.log.trace(f"[{self.name}] {self.port_name}: healthy via '{peer}'.")
            return "healthy"

        self.steps_since_connect += 1
        try:
            own_id = port.connected_id()
        except Exception:
            own_id = ""
        own_state = fluid_routing.declared_connection_state(port)

        candidates = self.blacklist.filter_reachable(self._discover_candidates(), curr_tick)
        alternatives = [c for c in candidates if c != own_id]

        if own_id:
            broken = own_state in fluid_routing.BROKEN_CONNECTION_STATES
            if not broken and self.steps_since_connect < NEUTRAL_GRACE_STEPS:
                self.log.debug(f"[{self.name}] {self.port_name}: '{own_id}' is {own_state!r}, within grace ({self.steps_since_connect}/{NEUTRAL_GRACE_STEPS}).")
                return "pending"
            if not broken and not alternatives:
                # Still neutral (e.g. the only tank is empty) and nothing else to try -- keep it.
                self.log.debug(f"[{self.name}] {self.port_name}: '{own_id}' still {own_state!r} but no alternative source; keeping it.")
                return "pending"
            self.blacklist.blacklist(own_id, curr_tick)
            self.log.level("warn").print(f"[{self.name}] {self.port_name}: '{own_id}' link is {own_state!r} -- {'no completed Liquid Pipe route?' if broken else 'no essence arriving'}. Trying another source.")

        if not alternatives:
            known = self._cached_candidates or []
            if known:
                self.log.debug(f"[{self.name}] {self.port_name}: every known source is blacklisted; waiting for expiry.")
                return "waiting"
            self.log.debug(f"[{self.name}] {self.port_name}: no '{self.fluid_id}' tank or '{self.biome}' Liquifier anywhere yet.")
            return "not_found"

        for source_id in alternatives:
            try:
                res = port.connect(source_id)
            except Exception:
                continue
            if res.status == "ok":
                self.steps_since_connect = 0
                self.log.print(f"[{self.name}] Connected {self.port_name} -> '{source_id}'.")
                return "connected"
            if res.status != "busy":
                self.log.level("warn").print(f"[{self.name}] {self.port_name} connect notice for '{source_id}': {res.status} - {res.message}")
        return "exhausted"


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
