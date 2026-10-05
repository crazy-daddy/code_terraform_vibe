import fluid_routing
import logistics_requests
from archive import archive
from storage import take_item, warehouse_stock, discover_storage_buildings, best_unload_target
from biomass_retire import biomass_complete
from tree_console import TreeConsole, method_block
from swallow import swallowed
from game_clock import now_tick
from machine_controller import MachineController

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
#      the local Warehouse buffer the Drone Depot fills (LIFEFORM_BUFFER_SLOTS stacks per form).
#   2. Drain: keep the single biome-named <biome>_essence_out port pointed at
#      a reachable Liquid Tank latched/assigned to that essence, via the same
#      FluidOutputRouter Water Pump uses (lib/fluid_routing.py). A Biomass
#      Mixer may also declare its own input straight onto this port
#      (lib/biomass_mixer.py); that is an independent peer link and needs no
#      coordination here.
# Once biomass_complete() (lib/biomass_retire.py) the Liquifier retires:
# no feeding, its input bin is ejected to local storage so undeploy() can
# take it, and control_room_automation.py switches its breaker off once the bin is empty.

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

# One shared dict {liquifier_id: telemetry} (not one key per liquifier, CODE_GUIDES.md
# #archive). Old per-liquifier "essence_liquifier.status.<id>" keys are purged by
# ArchiveCleaner.clean_retired_keys().
STATUS_KEY = "essence_liquifier.status"


class EssenceLiquifierController(MachineController):
    """Feeds an Essence Liquifier from its outpost's Drone Depot and routes its essence to a Liquid Tank."""
    LABEL = "Essence Liquifier"
    POLL_S = 5.0

    def online_message(self):
        return f"Essence Liquifier Controller ({self.name}) online. Biome: {self.biome or 'unknown'}."

    def __init__(self, liquifier):
        self.liquifier = liquifier
        self.name = getattr(liquifier, "id", "essence_liquifier")
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
        except Exception as error:
            swallowed("essence_liquifier.EssenceLiquifierController._resolve_biome: self.liquifier.biome", error)
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
            label=f"{self.name}.{self.fluid_id}_out",
            local_outpost_id=getattr(getattr(self.liquifier, "outpost", None), "id", None),
        )
        self.log.debug(f"[{self.name}] Host biome '{biome}' -> output port '{self.fluid_id}_out', routing to Liquid Tanks latched/assigned to '{self.fluid_id}'.")
        return True

    def stall_reason(self):
        try:
            return self.liquifier.stall_reason()
        except Exception as error:
            swallowed("essence_liquifier.EssenceLiquifierController.stall_reason: self.liquifier.stall_reason", error)
            return "ok"

    # ------------------------------------------------------------------ feed

    def sample_biome(self, item_id):
        """nocturna.life_form_biome(item_id): the native biome of a life form, None for any other item (or on failure)."""
        if not self.nocturna:
            return None
        try:
            return self.nocturna.life_form_biome(item_id)
        except Exception as error:
            swallowed("essence_liquifier.EssenceLiquifierController.sample_biome: self.nocturna.life_form_biome", error)
            return None

    def _loaded_item_ids(self):
        try:
            return {stack.id for stack in self.liquifier.input.stacks() if stack.count > 0}
        except Exception as error:
            swallowed("essence_liquifier.EssenceLiquifierController._loaded_item_ids: self.liquifier.input.stacks", error)
            return set()

    def _input_room(self):
        try:
            return self.liquifier.input.capacity() - self.liquifier.input.count()
        except Exception as error:
            swallowed("essence_liquifier.EssenceLiquifierController._input_room: self.liquifier.input.capacity", error)
            return 0

    @method_block(lambda self, *_, **__: f"[{self.name}] feed_from_depot")
    def feed_from_depot(self):
        """Pulls native samples from the local Depot(s) into .input while there's at least FEED_MIN_ROOM_UNITS of room."""
        room = self._input_room()
        if room < FEED_MIN_ROOM_UNITS:
            self.log.trace(f"feed: input room {room} < {FEED_MIN_ROOM_UNITS}; not topping up yet.")
            return

        depots = logistics_requests.local_depots(getattr(self.liquifier, "outpost", None))
        if not depots:
            self.log.debug("feed: no Drone Depot at this outpost; nothing to take from.")
            return

        input_slot = self.liquifier.input
        loaded = self._loaded_item_ids()
        requests = logistics_requests.active_requests()
        outpost = getattr(self.liquifier, "outpost", None)
        outpost_id = getattr(outpost, "id", None)
        for depot in depots:
            stock = logistics_requests.depot_stock(depot)
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
                        self.log.debug(f"feed: '{item_id}' requested (retain {retain}); holding back {held}, {stock[item_id]} usable.")
                        if stock[item_id] <= 0:
                            continue
                    native.append(item_id)
                elif item_biome and item_id not in self._warned_foreign:
                    # A foreign-biome life form parked here can never be processed locally and
                    # permanently eats one of the Depot's few material slots.
                    self._warned_foreign.add(item_id)
                    self.log.level("warn").print(f"[{self.name}] '{depot.id}' holds '{item_id}', which is not native to '{self.biome}' -- this Liquifier can't process it. Move it to a matching-biome outpost.")
            if not native:
                self.log.debug(f"feed: '{depot.id}' has no native '{self.biome}' samples (stock={stock}).")
                continue

            # Whatever species is already in the bin first -- a different one may be refused until it drains.
            native.sort(key=lambda i: (i not in loaded, -stock[i]))
            self.log.debug(f"feed: '{depot.id}' native candidates {[(i, stock[i]) for i in native]}, input room {room}, loaded={sorted(loaded)}.")

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
                    self.log.debug("feed: input busy with another transfer; retrying next cycle.")
                    return
                else:
                    # target_wrong_material / slots_full: bin still holds another species -- expected, try the next.
                    self.log.debug(f"feed: take('{item_id}', {want}) -> {status}: {getattr(res, 'message', '')}")

    def feed_from_warehouse(self):
        """
        Liquifies native life forms from the local Warehouse buffer (filled by
        lib/drone_depot.py stage_life_forms(), LIFEFORM_BUFFER_SLOTS stacks per form) beyond what
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
            except Exception as error:
                swallowed("essence_liquifier.EssenceLiquifierController.feed_from_warehouse: stored.update", error)
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
        event = fluid_routing.ensure_output_logged(
            self._router, port, curr_tick, blocked, self.log, self.name, f"{self.fluid_id}_out",
            f"can't take essence (stall={reason}, link={own_state}) -- likely no completed Liquid Pipe route or tank full")
        if event.kind == "not_found":
            peer = fluid_routing.healthy_peer_id(port)
            if peer:
                self.log.debug(f"[{self.name}] No '{self.fluid_id}' Liquid Tank, but '{peer}' already draws from this port directly.")
            else:
                self.log.debug(f"[{self.name}] No Liquid Tank latched/assigned to '{self.fluid_id}' network-wide (see fluid_routing.tank_assignments).")

    # ------------------------------------------------------------- telemetry

    def publish_telemetry(self):
        port = self.output_port()
        try:
            rate = self.liquifier.essence_rate()
        except Exception as error:
            swallowed("essence_liquifier.EssenceLiquifierController.publish_telemetry: self.liquifier.essence_rate", error)
            rate = 0.0
        try:
            input_count = self.liquifier.input.count()
        except Exception as error:
            swallowed("essence_liquifier.EssenceLiquifierController.publish_telemetry: self.liquifier.input.count", error)
            input_count = 0
        try:
            output_target = port.connected_id() if port else ""
        except Exception as error:
            swallowed("essence_liquifier.EssenceLiquifierController.publish_telemetry: port.connected_id", error)
            output_target = ""
        archive.publish_status(STATUS_KEY, self.name, {
            "name": self.name,
            "biome": self.biome,
            "fluid": self.fluid_id,
            "stall_reason": self.stall_reason(),
            "essence_rate": rate,
            "input_count": input_count,
            "last_fed": self._last_fed,
            "output_target": output_target,
            "retired": biomass_complete(),
        }, now_tick(), self.log)

    # ---------------------------------------------------------------- retire

    def retire_step(self):
        """Biomass complete: ejects every staged life form to local storage (Warehouse, else a local Depot)."""
        try:
            stacks = [(s.id, s.count) for s in self.liquifier.input.stacks() if s.count > 0]
        except Exception as error:
            swallowed("essence_liquifier.EssenceLiquifierController.retire_step: self.liquifier.input.stacks", error)
            stacks = []
        if not stacks:
            self.log.debug(f"[{self.name}] retired: input empty; waiting for the breaker/undeploy.")
            return
        outpost = getattr(self.liquifier, "outpost", None)
        self.log.start(f"[{self.name}] Retiring: ejecting {len(stacks)} staged life form stack(s)")
        ejected = 0
        for item_id, count in stacks:
            target = best_unload_target(item_id, 1, outpost=outpost)
            if target is None:
                depots = logistics_requests.local_depots(outpost)
                target = depots[0].id if depots else None
            if target is None:
                self.log.level("warn").print(f"[{self.name}] retired: no local store has room for {count}x '{item_id}'; retrying.")
                continue
            try:
                res = self.liquifier.input.eject(target, item_id, count)
            except Exception as e:
                self.log.level("warn").print(f"[{self.name}] retired: eject({target!r}, '{item_id}', {count}) failed: {e}")
                continue
            moved = getattr(res, "moved", 0) or 0
            if moved > 0:
                ejected += 1
                self.log.print(f"[{self.name}] Biomass complete: ejected {moved}x '{item_id}' -> '{target}'.")
            else:
                self.log.debug(f"[{self.name}] retired: eject '{item_id}' -> '{target}': {getattr(res, 'status', '?')} {getattr(res, 'message', '')}")
        self.log.end(f"[{self.name}] Retire pass: ejected {ejected}/{len(stacks)} stack(s)")

    def step(self):
        if biomass_complete():
            self.retire_step()
            self.publish_telemetry()
            return
        if not self._resolve_biome():
            self.log.level("warn").print(f"[{self.name}] No valid host biome (stall_reason={self.stall_reason()!r}); waiting.")
            return
        self.feed_from_depot()
        self.feed_from_warehouse()
        self.ensure_output_connection()
        self.publish_telemetry()
