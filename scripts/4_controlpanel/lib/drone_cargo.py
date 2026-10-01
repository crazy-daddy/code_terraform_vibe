from swallow import swallowed
# Drone mixin: .cargo accounting/load-unload helpers and home-biome sample
# filtering. Shared by scout/miner roles via DroneController.
#
# A drone's cargo moves straight into whatever it is physically docked at
# (DroneCargo.load()/unload(), docs/models/storage_and_items.md) -- there is
# no output PORT to route through like VehicleCargoMixin's unload_cargo()
# (Rover/Pioneer), so this mixin's unload helper is deliberately simpler and
# does not reuse vehicle_cargo.py's implementation.


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drone import DroneController

# cargo.unload() calls per item and unload: hot cargo fills one Lead Cask per call.
UNLOAD_MAX_ROUNDS = 4


class DroneCargoMixin:
    """Cargo accounting and Drone Depot unload behavior mixed into DroneController."""

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
        self._host.log.start(f"[{self._host.name}] is_home_biome_sample", level="debug")
        if not life_form_item_id or not self._host.home_biome:
            self._host.log.trace(f"missing item_id ({life_form_item_id!r}) or home_biome ({self._host.home_biome!r}); rejecting.")
            self._host.log.end()
            return False
        nocturna = get_component("nocturna")
        if not nocturna:
            self._host.log.trace(f"'nocturna' component unavailable; rejecting '{life_form_item_id}'.")
            self._host.log.end()
            return False
        try:
            native_biome = nocturna.life_form_biome(life_form_item_id)
            accepted = native_biome == self._host.home_biome
            self._host.log.trace(f"'{life_form_item_id}' native biome '{native_biome}' vs home_biome '{self._host.home_biome}' -> {'accepted' if accepted else 'rejected'}.")
            self._host.log.end()
            return accepted
        except Exception:
            self._host.log.trace(f"life_form_biome() lookup failed for '{life_form_item_id}'; rejecting.")
            self._host.log.end()
            return False
        self._host.log.end()

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
