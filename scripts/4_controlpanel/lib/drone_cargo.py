# Drone mixin: .cargo accounting/load-unload helpers, home-biome sample
# filtering and the home-Depot unload trip (return_and_unload(), shared by
# the miner and aftermath jobs; the floating hauler delivers with
# drone_hauler.deliver() instead).
#
# A drone's cargo moves straight into whatever it is physically docked at
# (DroneCargo.load()/unload(), docs/models/storage_and_items.md) -- there is
# no output PORT to route through like VehicleCargoMixin's unload_cargo()
# (Rover/Pioneer), so this mixin's unload helper is deliberately simpler and
# does not reuse vehicle_cargo.py's implementation. The unload trip calls
# navigation (fly_to_station, leave_station, hover_wait), energy
# (get_home_depot), claims (release_biosite_claim), charging
# (return_to_service_for_charge) and upgrade (maintain_modules_at_depot),
# like vehicle_cargo.py's drive-and-act layer.
from dataclasses import dataclass
from typing import TYPE_CHECKING

from swallow import swallowed
from tree_console import method_block

if TYPE_CHECKING:
    from drone import DroneController

# cargo.unload() calls per item and unload: hot cargo fills one Lead Cask per call.
UNLOAD_MAX_ROUNDS = 4
# Wait before retrying an unload at a full Drone Depot (10 ticks/s, so
# ~30 s). The drone hovers at the Depot meanwhile (hover_wait()), flying to
# a drone_service only below LAUNCH_MIN_SOC.
DEPOT_FULL_RETRY_TICKS = 300


@dataclass
class DepotFull:
    """Full home Depot backoff (unload_and_leave()): next retry tick, failures in a row, the Depot concerned."""

    retry_tick: int = 0
    count: int = 0
    depot_id: str | None = None

    def clear(self):
        self.retry_tick = 0
        self.count = 0
        self.depot_id = None


class DroneCargoMixin:
    """Cargo accounting and Drone Depot unload behavior mixed into DroneController."""

    DEPOT_FULL_RETRY_TICKS = DEPOT_FULL_RETRY_TICKS

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    def cargo_count(self, item_id=None):
        """Total units aboard, or units of a specific item_id if given."""
        if not hasattr(self._host.drone, "cargo"):
            return 0
        try:
            if item_id is None:
                return self._host.drone.cargo.count()
            return self._host.drone.cargo.contents().get(item_id, 0)
        except Exception as error:
            swallowed("drone_cargo.DroneCargoMixin.cargo_count: self._host.drone.cargo.count", error)
            return 0

    def cargo_capacity(self):
        try:
            return self._host.drone.cargo.capacity()
        except Exception as error:
            swallowed("drone_cargo.DroneCargoMixin.cargo_capacity: self._host.drone.cargo.capacity", error)
            return 0

    def cargo_full(self):
        try:
            return self._host.drone.cargo.full()
        except Exception as error:
            swallowed("drone_cargo.DroneCargoMixin.cargo_full: self._host.drone.cargo.full", error)
            return False

    def space_for(self, item_id):
        """Free cargo room for item_id specifically -- each Cargo Pod/the Bio
        Extractor chamber holds one material, so this can be 0 even while
        cargo_count() < cargo_capacity() (docs/components/drone.md)."""
        if not hasattr(self._host.drone, "cargo"):
            return 0
        try:
            return self._host.drone.cargo.space_for(item_id)
        except Exception as error:
            swallowed("drone_cargo.DroneCargoMixin.space_for: self._host.drone.cargo.space_for", error)
            return 0

    @method_block(lambda self, *_, **__: f"[{self._host.name}] is_home_biome_sample")
    def is_home_biome_sample(self, life_form_item_id):
        """
        True when life_form_item_id's native biome (nocturna.life_form_biome())
        matches this drone's home_biome. The Essence Liquifier at this
        drone's home outpost only accepts native-biome samples (see
        docs/components/essence_liquifier.md), so a non-home-biome sample
        dropped off here would simply be rejected -- the plan's v1 rule
        skips any biosite carrying a non-home-biome sample entirely (see
        lib/drone_mining.py); cross-outpost ferrying of foreign samples is a
        deferred TODO.
        """
        if not life_form_item_id or not self._host.home_biome:
            self._host.log.trace(f"missing item_id ({life_form_item_id!r}) or home_biome ({self._host.home_biome!r}); rejecting.")
            return False
        nocturna = get_component("nocturna")
        if not nocturna:
            self._host.log.trace(f"'nocturna' component unavailable; rejecting '{life_form_item_id}'.")
            return False
        try:
            native_biome = nocturna.life_form_biome(life_form_item_id)
            accepted = native_biome == self._host.home_biome
            self._host.log.trace(f"'{life_form_item_id}' native biome '{native_biome}' vs home_biome '{self._host.home_biome}' -> {'accepted' if accepted else 'rejected'}.")
            return accepted
        except Exception:
            self._host.log.trace(f"life_form_biome() lookup failed for '{life_form_item_id}'; rejecting.")
            return False

    def unload_cargo_at_depot(self):
        """
        Unloads all cargo into the docked Drone Depot's stockpile via
        cargo.unload() (DroneCargo.unload() -- moves straight into whatever
        Depot this drone is physically docked at, not through an output port
        like VehicleCargoMixin.unload_cargo()). Returns total units
        unloaded, or -1 if a slot-capacity rejection left cargo aboard
        (mirrors VehicleCargoMixin.unload_cargo()'s -1 "storage full"
        convention so callers can share the same "wait for space" branch
        shape).
        """
        self._host.log.start(f"[{self._host.name}] unload_cargo_at_depot", level="debug")
        if not hasattr(self._host.drone, "cargo"):
            self._host.log.end()
            return 0
        try:
            contents = dict(self._host.drone.cargo.contents())
        except Exception as error:
            swallowed("drone_cargo.DroneCargoMixin.unload_cargo_at_depot: self._host.drone.cargo.contents", error)
            contents = {}
        if not contents:
            self._host.log.debug("no cargo aboard; nothing to unload.")
            self._host.log.end()
            return 0

        unloaded = 0
        depot_full = False
        for item_id, count in contents.items():
            if count <= 0:
                continue
            # Hot cargo (Raw Uranium) goes into one Lead Cask per call, so
            # repeat while a call still moves something.
            left = count
            res = None
            for _round in range(UNLOAD_MAX_ROUNDS):
                try:
                    res = self._host.drone.cargo.unload(item_id, left)
                except Exception as error:
                    swallowed("drone_cargo.DroneCargoMixin.unload_cargo_at_depot: self._host.drone.cargo.unload", error)
                    break
                moved = getattr(res, "moved", 0) or 0
                unloaded += moved
                left -= moved
                self._host.log.debug(f"{item_id} moved {moved}/{count}, {left} left (status={res.status}).")
                if moved <= 0 or left <= 0:
                    break
            if res is not None and left > 0:
                depot_full = True
                self._host.log.level("warn").print(f"[{self._host.name}] Drone Depot notice for {item_id}: {res.status} - {res.message}")

        self._host.log.debug(f"total unloaded={unloaded} unit(s) across {len(contents)} item type(s), depot_full={depot_full}.")
        self._host.log.end()
        return -1 if depot_full and unloaded == 0 else unloaded

    # ------------------------------------------------------------ home Depot unload trip

    def wait_for_depot_space(self, depot_id, ticks_left):
        """
        Depot-full backoff: hover in place off the berth (free) and report
        WAITING_DEPOT_SPACE for depot_id, which lets that Depot flush surplus
        (lib/drone_depot.py flush_surplus()). Charges at a drone_service
        only when below LAUNCH_MIN_SOC.
        """
        host = self._host
        host.log.start(f"[{host.name}] wait_for_depot_space", level="debug")
        _, _, lvl = host.get_battery()
        if lvl < host.LAUNCH_MIN_SOC:
            host.log.debug(f"Depot full backoff: {ticks_left} ticks left, {lvl * 100:.0f}% charge; charging at drone_service meanwhile.")
            host.return_to_service_for_charge(host.log, "Waiting for Drone Depot space")
            host.publish_telemetry("WAITING_DEPOT_SPACE", depot_id)
            host.log.end()
            return
        host.log.debug(f"Depot full backoff: {ticks_left} ticks left; hovering off the berth.")
        host.hover_wait("WAITING_DEPOT_SPACE", depot_id)
        host.log.end()

    def unload_and_leave(self, depot_id):
        """
        Unloads at the docked Depot, releases every biosite claim (and the
        mission), maintains modules, leaves the berth; returns the unloaded
        count (negative when the Depot is full: host.depot_full records the
        backoff and the drone hovers until its retry tick).
        """
        host = self._host
        unloaded = self.unload_cargo_at_depot()
        if unloaded < 0:
            host.log.level("warn").print(f"[{host.name}] Drone Depot has no free slot for this cargo; leaving aboard until space opens.")
            host.publish_telemetry("WAITING_DEPOT_SPACE")
        elif unloaded > 0:
            host.log.print(f"[{host.name}] Unloaded {unloaded} units at Drone Depot.")

        backoff = host.depot_full
        if unloaded < 0:
            backoff.retry_tick = host.get_current_tick() + self.DEPOT_FULL_RETRY_TICKS
            backoff.count += 1
            backoff.depot_id = depot_id
            host.log.debug(f"[{host.name}] Depot '{depot_id}' full ({backoff.count}x in a row); next unload attempt in {self.DEPOT_FULL_RETRY_TICKS} ticks.")
        elif self.cargo_count() == 0:
            backoff.count = 0
            backoff.depot_id = None

        host.release_biosite_claim()
        if unloaded >= 0 and self.cargo_count() == 0:
            # Docked and empty: the one moment couple()/uncouple() can run.
            host.maintain_modules_at_depot()
        # Leave the berth now, even with no next target picked yet -- a drone
        # otherwise sits docked here between trips, occupying a bay a peer
        # drone (or this one, on a later retry) may be waiting in line for.
        # Also releases the bay when the Depot is full (unloaded < 0):
        # staying docked wouldn't make its stuck cargo unloadable any sooner,
        # but it would keep the bay from a drone unloading a different item
        # that DOES have space.
        host.leave_station()
        if unloaded < 0:
            # Re-docking at a full depot every few seconds burns time and
            # battery for nothing; hover here until the retry tick passes.
            self.wait_for_depot_space(depot_id, self.DEPOT_FULL_RETRY_TICKS)
        else:
            host.publish_telemetry("READY_AT_DEPOT")
        return unloaded

    def return_and_unload(self):
        """Flies to the home Depot and unloads (unload_and_leave()). True on success, False when the caller should back off before retrying."""
        host = self._host
        host.log.trace(f"[{host.name}] return_and_unload() entry.")
        depot_coords, depot_info = host.get_home_depot()
        depot_id = depot_info.get("id")
        host.publish_telemetry("RETURNING_TO_DEPOT")

        reached = bool(depot_id) and host.fly_to_station(depot_id, target_coords=depot_coords)
        if not reached and host.status() == "waiting_bay":
            # Arrived, but the bay got taken. With a pool home a sibling
            # depot may be free now: re-pick once and transfer (same coords,
            # no flight cost).
            alt_coords, alt_info = host.get_home_depot(prefer_id=depot_id)
            alt_id = alt_info.get("id")
            if alt_id and alt_id != depot_id:
                host.log.debug(f"[{host.name}] Depot '{depot_id}' bay taken; switching to free sibling '{alt_id}'.")
                depot_coords, depot_id = alt_coords, alt_id
                reached = host.fly_to_station(depot_id, target_coords=depot_coords)
        if not reached and host.status() == "waiting_bay":
            # Every home depot's bay is occupied. Falling back to fly_to()
            # would "arrive" instantly (same coords) and then unload into
            # nothing, since cargo.unload() needs a docked berth. Stay
            # queued and retry. Warn once per wait, not on every retry.
            already_waiting = host.state == "WAITING_DEPOT_BAY"
            msg = f"[{host.name}] Drone Depot '{depot_id}' has no free bay (waiting_bay); a docked drone is holding it. Retrying."
            if already_waiting:
                host.log.debug(msg)
            else:
                host.log.level("warn").print(msg)
            host.publish_telemetry("WAITING_DEPOT_BAY")
            return False
        if not reached:
            host.log.debug(f"[{host.name}] fly_to_station({depot_id}) unavailable or failed; falling back to direct fly_to({depot_coords}).")
            reached = host.fly_to(depot_coords[0], depot_coords[1], precision=1.5)
        if not reached:
            host.log.level("warn").print(f"[{host.name}] Could not reach Drone Depot to unload; will retry.")
            return False

        host.log.start(f"[{host.name}] Unloading at Drone Depot '{depot_id}'")
        unloaded = self.unload_and_leave(depot_id)
        host.log.end("depot full, cargo kept aboard" if unloaded < 0 else f"unloaded {unloaded} unit(s)")
        host.log.trace(f"[{host.name}] return_and_unload() exit: unloaded={unloaded}.")
        # Depot full counts as failure: cargo is still aboard, so the caller
        # should back off before retrying.
        return unloaded >= 0
