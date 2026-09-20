# Drone mixin: .cargo accounting/load-unload helpers and home-biome sample
# filtering. Shared by scout/miner roles via DroneController.
#
# A drone's cargo moves straight into whatever it is physically docked at
# (DroneCargo.load()/unload(), docs/models/storage_and_items.md) -- there is
# no output PORT to route through like VehicleCargoMixin's unload_cargo()
# (Rover/Pioneer), so this mixin's unload helper is deliberately simpler and
# does not reuse vehicle_cargo.py's implementation.


class DroneCargoMixin:
    """Cargo accounting and Drone Depot unload behavior mixed into DroneController."""

    def cargo_count(self, item_id=None):
        """Total units aboard, or units of a specific item_id if given."""
        if not hasattr(self.drone, "cargo"):
            return 0
        try:
            if item_id is None:
                return self.drone.cargo.count()
            return self.drone.cargo.contents().get(item_id, 0)
        except Exception:
            return 0

    def cargo_capacity(self):
        try:
            return self.drone.cargo.capacity()
        except Exception:
            return 0

    def cargo_full(self):
        try:
            return self.drone.cargo.full()
        except Exception:
            return False

    def space_for(self, item_id):
        """Free cargo room for item_id specifically -- each Cargo Pod/the Bio
        Extractor chamber holds one material, so this can be 0 even while
        cargo_count() < cargo_capacity() (docs/components/drone.md)."""
        if not hasattr(self.drone, "cargo"):
            return 0
        try:
            return self.drone.cargo.space_for(item_id)
        except Exception:
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
        if not life_form_item_id or not self.home_biome:
            return False
        nocturna = get_component("nocturna")
        if not nocturna:
            return False
        try:
            return nocturna.life_form_biome(life_form_item_id) == self.home_biome
        except Exception:
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
        if not hasattr(self.drone, "cargo"):
            return 0
        try:
            contents = dict(self.drone.cargo.contents())
        except Exception:
            contents = {}
        if not contents:
            return 0

        unloaded = 0
        depot_full = False
        for item_id, count in contents.items():
            if count <= 0:
                continue
            try:
                res = self.drone.cargo.unload(item_id, count)
            except Exception:
                continue
            moved = getattr(res, "moved", 0) or 0
            unloaded += moved
            if res.status in ("slots_full", "target_full") or moved < count:
                depot_full = True
                print(f"[{self.name}] Drone Depot notice for {item_id}: {res.status} - {res.message}")

        return -1 if depot_full and unloaded == 0 else unloaded
