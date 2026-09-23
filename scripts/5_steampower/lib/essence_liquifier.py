import fluid_routing
import logistics_requests
from archive import archive
from storage import take_item, warehouse_stock, discover_storage_buildings
from version_guard import validate_game_version
from tree_console import TreeConsole

# Shared Essence Liquifier automation. No production decisions to make -- the
# machine turns whatever native life form sits in its input bin into its
# outpost biome's essence (docs/components/essence_liquifier.md). The two
# jobs are:
#   1. Feed: pull native-biome life-form samples from the local Drone Depot
#      stockpile (where miner drones unload -- lib/drone_cargo.py) into
#      .input via InputSlot.take(). Item transfers are explicit, never passive
#      (docs/types/storage_and_inventory.md), so something must call take();
#      the Depot's own output wiring (lib/drone_depot.py) only declares the
#      link. Every candidate is checked against
#      nocturna.life_form_biome(item_id) == liquifier.biome() first, so
#      non-life-form cargo and foreign-biome samples are never touched.
#      Items requested via lib/logistics_requests.py (e.g. by the Seed Maker)
#      are held back up to logistics_requests.retain_amount(). Second source:
#      the local Warehouse buffer the Drone Depot fills (one stack per form).
#   2. Drain: keep the single biome-named <biome>_essence_out port pointed at
#      a reachable Liquid Tank latched/assigned to that essence, via the same
#      FluidOutputRouter Water Pump uses (lib/fluid_routing.py). A Biomass
#      Mixer may also declare its own input straight onto this port
#      (lib/biomass_mixer.py); that is an independent peer link and needs no
#      coordination here.

DRONE_DEPOT_TYPE_ID = "drone_station"  # typeId, not the "Drone Depot" display name -- see lib/drone_energy.py

# Only take() once the input bin has at least this much room. take() blocks
# for time proportional to units moved, so topping up one sample at a time
# every cycle would spend most of the loop waiting on tiny transfers.
FEED_MIN_ROOM_UNITS = 5

# Same meaning/values as lib/fluid_pump.py's constants of the same names --
# see there and lib/thermal_cap.py for the reasoning.
ESSENCE_TANK_REBALANCE_FILL_FRACTION = 0.98
CONNECTION_GRACE_TICKS = 2
RESCAN_INTERVAL_TICKS = 300
DISCOVERY_CACHE_INTERVAL_TICKS = 100

# stall_reason() values that mean "the output side can't take the next
# yield" -- the only ones that say anything about the current tank. "no_input"
# (just waiting for drones) must NOT count, or an idle Liquifier would
# blacklist a perfectly good tank.
OUTPUT_BLOCKED_STALL_REASONS = ("output_full", "unconnected")

# One shared dict {liquifier_id: telemetry} (not one key per liquifier, CLAUDE.md
# rule 7). Old per-liquifier "essence_liquifier.status.<id>" keys are purged by
# ArchiveCleaner.clean_retired_keys().
STATUS_KEY = "essence_liquifier.status"


class EssenceLiquifierController:
    """Feeds an Essence Liquifier from its outpost's Drone Depot and routes its essence to a Liquid Tank."""

    def __init__(self, liquifier):
        self.liquifier = liquifier
        self.name = getattr(liquifier, "id", "essence_liquifier")
        self.clock = get_component("clock")
        self.nocturna = get_component("nocturna")
        self.log = TreeConsole(module="essence_liquifier")
        self.biome = None
        self.fluid_id = None
        self._router = None
        self._warned_foreign = set()
        self._warned_research = False
        self._last_fed = None
        self._resolve_biome()

    def _resolve_biome(self):
        """Latches biome/fluid_id/router once liquifier.biome() answers. Retried each step while None ("no_biome")."""
        if self.biome:
            return True
        try:
            biome = self.liquifier.biome()
        except Exception:
            biome = None
        if not biome:
            return False
        self.biome = biome
        self.fluid_id = f"{biome}_essence"
        self._router = fluid_routing.FluidOutputRouter(
            type_ids=fluid_routing.LIQUID_TANK_TYPE_IDS,
            rebalance_fill_fraction=ESSENCE_TANK_REBALANCE_FILL_FRACTION,
            connection_grace_ticks=CONNECTION_GRACE_TICKS,
            rescan_interval_ticks=RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=DISCOVERY_CACHE_INTERVAL_TICKS,
            fluid_id=self.fluid_id,
        )
        self.log.debug(f"[{self.name}] Host biome '{biome}' -> output port '{self.fluid_id}_out', routing to Liquid Tanks latched/assigned to '{self.fluid_id}'.")
        return True

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception:
                pass
        return 0

    def stall_reason(self):
        try:
            return self.liquifier.stall_reason()
        except Exception:
            return "ok"

    # ------------------------------------------------------------------ feed

    def sample_biome(self, item_id):
        """nocturna.life_form_biome(item_id): the native biome of a life form, None for any other item (or on failure)."""
        if not self.nocturna:
            return None
        try:
            return self.nocturna.life_form_biome(item_id)
        except Exception:
            return None

    def _local_depots(self):
        """Resolved same-outpost Drone Depots. InputSlot sources must share the outpost, so remote ones are useless."""
        outpost = getattr(self.liquifier, "outpost", None)
        if not outpost or not hasattr(outpost, "buildings"):
            return []
        try:
            refs = outpost.buildings(DRONE_DEPOT_TYPE_ID)
        except Exception:
            return []
        depots = []
        for ref in refs:
            try:
                depot = get_component(ref.id)
            except Exception:
                depot = None
            if depot:
                depots.append(depot)
        return depots

    def _depot_stock(self, depot):
        """{item_id: units} of the Depot's shared stockpile, summed across property-distinct stacks."""
        stock = {}
        port = getattr(depot, "output", None)
        if not port or not hasattr(port, "stacks"):
            return stock
        try:
            for stack in port.stacks():
                stock[stack.id] = stock.get(stack.id, 0) + stack.count
        except Exception:
            return {}
        return stock

    def _loaded_item_ids(self):
        try:
            return {stack.id for stack in self.liquifier.input.stacks() if stack.count > 0}
        except Exception:
            return set()

    def _input_room(self):
        try:
            return self.liquifier.input.capacity() - self.liquifier.input.count()
        except Exception:
            return 0

    def feed_from_depot(self):
        """Pulls native samples from the local Depot(s) into .input while there's at least FEED_MIN_ROOM_UNITS of room."""
        room = self._input_room()
        if room < FEED_MIN_ROOM_UNITS:
            self.log.trace(f"[{self.name}] feed: input room {room} < {FEED_MIN_ROOM_UNITS}; not topping up yet.")
            return

        depots = self._local_depots()
        if not depots:
            self.log.debug(f"[{self.name}] feed: no Drone Depot at this outpost; nothing to take from.")
            return

        input_slot = self.liquifier.input
        loaded = self._loaded_item_ids()
        requests = logistics_requests.active_requests()
        outpost = getattr(self.liquifier, "outpost", None)
        outpost_id = getattr(outpost, "id", None)
        for depot in depots:
            stock = self._depot_stock(depot)
            native = []
            for item_id, units in stock.items():
                if units <= 0:
                    continue
                item_biome = self.sample_biome(item_id)
                if item_biome == self.biome:
                    retain = logistics_requests.retain_amount(item_id, outpost_id, requests) if requests else 0
                    if retain > 0:
                        # Keep what the local Warehouse stash still lacks; lib/drone_depot.py stages it there.
                        held = max(0, retain - warehouse_stock(item_id, outpost))
                        stock[item_id] = units - held
                        self.log.debug(f"[{self.name}] feed: '{item_id}' requested (retain {retain}); holding back {held}, {stock[item_id]} usable.")
                        if stock[item_id] <= 0:
                            continue
                    native.append(item_id)
                elif item_biome and item_id not in self._warned_foreign:
                    # A foreign-biome life form parked here can never be processed locally and
                    # permanently eats one of the Depot's few material slots.
                    self._warned_foreign.add(item_id)
                    self.log.level("warn").print(f"[{self.name}] '{depot.id}' holds '{item_id}', which is not native to '{self.biome}' -- this Liquifier can't process it. Move it to a matching-biome outpost.")
            if not native:
                self.log.debug(f"[{self.name}] feed: '{depot.id}' has no native '{self.biome}' samples (stock={stock}).")
                continue

            # Whatever species is already in the bin first -- a different one may be refused until it drains.
            native.sort(key=lambda i: (i not in loaded, -stock[i]))
            self.log.debug(f"[{self.name}] feed: '{depot.id}' native candidates {[(i, stock[i]) for i in native]}, input room {room}, loaded={sorted(loaded)}.")

            if self._ensure_input_source(input_slot, depot.id) is False:
                continue

            for item_id in native:
                want = min(room, stock[item_id])
                try:
                    res = input_slot.take(item_id, want, None, "any")
                except Exception as e:
                    self.log.level("error").print(f"[{self.name}] take('{item_id}', {want}) from '{depot.id}' failed: {e}")
                    continue
                status = getattr(res, "status", "")
                moved = getattr(res, "moved", 0) or 0
                if status in ("ok", "partial") and moved > 0:
                    self.log.print(f"[{self.name}] Loaded {moved}x '{item_id}' from '{depot.id}'.")
                    self._last_fed = item_id
                    room -= moved
                    if room < FEED_MIN_ROOM_UNITS:
                        return
                elif status == "research_required":
                    if not self._warned_research:
                        self._warned_research = True
                        self.log.level("warn").print(f"[{self.name}] Cannot pull samples: {res.message} (Auto Feeders research).")
                    return
                elif status == "busy":
                    self.log.debug(f"[{self.name}] feed: input busy with another transfer; retrying next cycle.")
                    return
                else:
                    # target_wrong_material / slots_full: bin still holds another species -- expected, try the next.
                    self.log.debug(f"[{self.name}] feed: take('{item_id}', {want}) -> {status}: {getattr(res, 'message', '')}")

    def feed_from_warehouse(self):
        """
        Liquifies native life forms from the local Warehouse buffer (filled by
        lib/drone_depot.py stage_life_forms(), one stack per form) beyond what
        is still requested (retain_amount()). Runs after the Depot feed, so
        the Depot's small stockpile is emptied first.
        """
        room = self._input_room()
        if room < FEED_MIN_ROOM_UNITS:
            return
        outpost = getattr(self.liquifier, "outpost", None)
        outpost_id = getattr(outpost, "id", None)
        if not outpost_id or not self.nocturna:
            return
        requests = logistics_requests.active_requests()
        loaded = self._loaded_item_ids()
        stored = set()
        for building in discover_storage_buildings(outpost):
            try:
                stored.update(building["component"].materials())
            except Exception:
                continue
        forms = [f for f in stored if self.sample_biome(f) == self.biome]
        forms.sort(key=lambda f: f not in loaded)
        for item_id in forms:
            surplus = warehouse_stock(item_id, outpost) - logistics_requests.retain_amount(item_id, outpost_id, requests)
            if surplus <= 0:
                continue
            want = min(room, surplus)
            moved = take_item(self.liquifier.input, item_id, want, outpost=outpost)
            if moved > 0:
                self.log.print(f"[{self.name}] Loaded {moved}x '{item_id}' from Warehouse buffer.")
                self._last_fed = item_id
                room -= moved
                if room < FEED_MIN_ROOM_UNITS:
                    return
            else:
                self.log.debug(f"[{self.name}] feed: Warehouse surplus {surplus}x '{item_id}' but take() moved nothing (bin holds another species?).")

    def _ensure_input_source(self, input_slot, depot_id):
        """Points .input at depot_id if it isn't already. Returns False only on a hard connect rejection."""
        try:
            if input_slot.connected_id() == depot_id:
                return True
            res = input_slot.connect(depot_id)
        except Exception as e:
            self.log.level("error").print(f"[{self.name}] Could not connect input to '{depot_id}': {e}")
            return False
        if res.status != "ok":
            self.log.level("warn").print(f"[{self.name}] input connect to '{depot_id}': {res.status} - {res.message}")
            return False
        self.log.debug(f"[{self.name}] input source -> '{depot_id}'.")
        return True

    # ----------------------------------------------------------------- drain

    def output_port(self):
        return getattr(self.liquifier, f"{self.fluid_id}_out", None) if self.fluid_id else None

    def ensure_output_connection(self):
        port = self.output_port()
        if self._router is None or not port or not hasattr(port, "connect"):
            self.log.debug(f"[{self.name}] No '{self.fluid_id}_out' port exposed; skipping output routing.")
            return

        curr_tick = self.get_current_tick()
        reason = self.stall_reason()
        own_state = fluid_routing.declared_connection_state(port)
        # Output-side stall, or the engine itself says our declared tank can't be reached -- either
        # way the router should move on. no_input is explicitly NOT evidence (see OUTPUT_BLOCKED_STALL_REASONS).
        blocked = reason in OUTPUT_BLOCKED_STALL_REASONS or own_state in fluid_routing.BROKEN_CONNECTION_STATES
        self.log.debug(f"[{self.name}] output: stall_reason={reason!r}, declared link state={own_state!r} -> blocked={blocked}.")

        def on_blacklisted(target_id):
            self.log.level("warn").print(f"[{self.name}] '{target_id}' can't take essence (stall={reason}, link={own_state}) -- likely no completed Liquid Pipe route or tank full. Trying another tank.")

        def on_connect_notice(target_id, status, message):
            self.log.level("warn").print(f"[{self.name}] {self.fluid_id}_out connect notice for '{target_id}': {status} - {message}")

        event = self._router.ensure_connection(port, curr_tick, blocked, on_blacklisted, on_connect_notice)
        if event.kind == "connected":
            self.log.print(f"[{self.name}] Connected {self.fluid_id}_out -> '{event.target_id}' ({event.fill_pct*100:.0f}% full).")
        elif event.kind == "not_found":
            peer = fluid_routing.healthy_peer_id(port)
            if peer:
                self.log.debug(f"[{self.name}] No '{self.fluid_id}' Liquid Tank, but '{peer}' already draws from this port directly.")
            else:
                self.log.debug(f"[{self.name}] No Liquid Tank latched/assigned to '{self.fluid_id}' network-wide (see fluid_routing.tank_assignments).")
        else:
            self.log.debug(f"[{self.name}] output router: {event.kind}.")

    # ------------------------------------------------------------- telemetry

    def publish_telemetry(self):
        port = self.output_port()
        try:
            rate = self.liquifier.essence_rate()
        except Exception:
            rate = 0.0
        try:
            input_count = self.liquifier.input.count()
        except Exception:
            input_count = 0
        try:
            output_target = port.connected_id() if port else ""
        except Exception:
            output_target = ""
        archive.set_entry(STATUS_KEY, self.name, {
            "name": self.name,
            "biome": self.biome,
            "fluid": self.fluid_id,
            "stall_reason": self.stall_reason(),
            "essence_rate": rate,
            "input_count": input_count,
            "last_fed": self._last_fed,
            "output_target": output_target,
        })

    def step(self):
        if not self._resolve_biome():
            self.log.level("warn").print(f"[{self.name}] No valid host biome (stall_reason={self.stall_reason()!r}); waiting.")
            return
        self.feed_from_depot()
        self.feed_from_warehouse()
        self.ensure_output_connection()
        self.publish_telemetry()

    def run(self, poll_interval=5.0):
        self.log.print(f"Essence Liquifier Controller ({self.name}) online. Biome: {self.biome or 'unknown'}.")
        validate_game_version()
        while True:
            try:
                self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Essence Liquifier exception: {error}")
            sleep(poll_interval)
