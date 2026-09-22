# Shared Base Library for Drone Automation (scout/miner roles).
#
# Drones are a FRESH hierarchy, not a VehicleController subclass -- no
# .drive/.nav, no terrain/stall handling, route-based go_to()/go_to_station()/
# go_to_drill() rather than a blocking drive loop, and a different (simpler,
# linear) power/speed model (see lib/drone_energy.py). But DroneController
# follows the exact same mixin-composition philosophy as lib/vehicle.py:
#   - drone_navigation.py: go_to()/go_to_station()/go_to_drill() wrappers, arrival polling
#   - drone_energy.py: battery accounting, linear Wh/meter trip budgeting, drone_service/drone_depot discovery
#   - drone_claims.py: exclusive biosite claims + scout empty-POI cache + mission persistence
#   - drone_cargo.py: cargo accounting/load-unload + home-biome filtering
#   - drone_scout.py / drone_mining.py: role loops
#
# Electric drones only this pass -- heli support (oil_tank instead of
# battery, refuel() instead of charge()) can follow the same pattern later
# without disrupting this design; DroneController assumes .battery is
# readable (see drone_energy.py's get_battery()).

from archive import archive
from drone_navigation import DroneNavigationMixin
from drone_energy import DroneEnergyMixin
from drone_claims import DroneClaimsMixin
from drone_cargo import DroneCargoMixin
from drone_scout import DroneScoutMixin
from drone_mining import DroneMiningMixin
from tree_console import TreeConsole
from version_guard import validate_game_version


class DroneController(
    DroneNavigationMixin,
    DroneEnergyMixin,
    DroneClaimsMixin,
    DroneCargoMixin,
    DroneScoutMixin,
    DroneMiningMixin,
):
    """
    Unified base controller for autonomous electric drones. Resolves
    home_outpost/home_biome from the nearest Drone Depot (a drone has no
    .outpost property of its own, unlike ground vehicles/buildings -- see
    docs/models/vehicles_and_modules.md's DroneSmall/DroneMedium/DroneLarge
    class definitions), detects role from mounted field module
    (bio_scanner -> scout, bio_extractor -> miner), and dispatches to the
    matching loop.
    """
    ROLE_MODULES = {
        "scout": "bio_scanner",
        "miner": "bio_extractor",
    }
    # detect_role() probes by calling this method once per candidate module
    # and reading the result's .status -- see detect_role()'s docstring for
    # why a live call, not hasattr(), is the only available detection here.
    ROLE_PROBE_METHOD = {
        "bio_scanner": "scan",
        "bio_extractor": "extract",
    }

    def __init__(self, drone, cruise_throttle=None):
        self.drone = drone
        self.name = getattr(drone, "id", getattr(drone, "name", "drone"))

        # Created once here (not per-call) since TreeConsole.__init__ reads
        # the console.log_levels archive dict -- see
        # docs/AI_CHEATSHEET.md #0a. Constructed before the home_outpost
        # resolution chain below (rather than after, as in the shape this
        # was ported from) so get_nearest_drone_depot()/_service() -- called
        # during this same __init__ -- can already log through self.log.
        self.log = TreeConsole(module="drone")

        # No self.home_coords yet -- get_nearest_drone_depot()/_service()
        # fall back to (0.0, 0.0) via getattr(self, "home_coords", ...)
        # until it's assigned below (see drone_energy.py's fallback note).
        depot_coords, depot_info = self.get_nearest_drone_depot()
        self.home_coords = depot_coords

        # A drone has no .outpost property (unlike a Rover/Pioneer/building),
        # so home_outpost is resolved from whichever building anchors this
        # drone's home: its nearest Drone Depot first (BuildingRef.outpost),
        # falling back to the nearest drone_service, then to the network's
        # home outpost if neither is deployed yet.
        self.home_outpost = depot_info.get("outpost")
        home_outpost_source = "drone_depot" if self.home_outpost is not None else None
        if self.home_outpost is None:
            _, service_info = self.get_nearest_drone_service()
            self.home_outpost = service_info.get("outpost")
            if self.home_outpost is not None:
                home_outpost_source = "drone_service"
        if self.home_outpost is None:
            network = get_component("outpost_network")
            self.home_outpost = network.home() if network and hasattr(network, "home") else None
            if self.home_outpost is not None:
                home_outpost_source = "outpost_network.home() fallback"
                if hasattr(self.home_outpost, "coords"):
                    try:
                        coords = self.home_outpost.coords()
                        if coords:
                            self.home_coords = (float(coords[0]), float(coords[1]))
                    except Exception:
                        pass

        self.home_biome = getattr(self.home_outpost, "biome", None)
        self.log.debug(f"[{self.name}] home_outpost resolved via {home_outpost_source or 'none (no depot/service/network home found)'}; home_coords={self.home_coords}, home_biome={self.home_biome!r}.")

        self.cruise_throttle = cruise_throttle if cruise_throttle is not None else self.default_cruise_throttle()

        self.state = "INIT"
        self.current_target = None
        self.current_target_key = None

        # Resume an in-progress mission left over from before a script
        # reload, if this drone still owns that target's claim (see
        # drone_claims.py). A drone's go_to() is cancelled by a script
        # restart (drone.md), so the flight leg itself still needs
        # re-issuing -- see drone_mining.py's run_miner_loop() resume path.
        resumed = self.load_mission()
        if resumed:
            self.log.print(f"[{self.name}] Resuming mission '{resumed.get('kind')}' on target '{self.current_target_key}' after reload.")

    def get_current_tick(self):
        clock = get_component("clock")
        if clock and hasattr(clock, "tick"):
            try:
                return clock.tick()
            except Exception:
                pass
        return 0

    def publish_telemetry(self, state, target_desc=None):
        """Publishes live drone status to Data Archive, mirroring
        VehicleController.publish_telemetry()'s shape/key convention."""
        self.state = state
        curr_wh, cap_wh, lvl = self.get_battery()
        pos = self.position()
        telemetry = {
            "name": self.name,
            "state": state,
            "x": round(pos[0], 1),
            "y": round(pos[1], 1),
            "wh": round(curr_wh, 1),
            "level": round(lvl, 2),
            "target": target_desc or (self.current_target.get("name") if self.current_target else "none"),
            "tick": self.get_current_tick(),
        }
        archive.set(f"fleet.status.{self.name}", telemetry)
        archive.set(f"drone.status.{self.name}", telemetry)

    def detect_role(self, role_override=None):
        """
        Probes mounted field modules (ROLE_MODULES) and returns "scout"/
        "miner". Returns None when neither or both modules are mounted --
        caller must treat that as "cannot start".

        NOT a hasattr()-based probe, unlike PioneerController.detect_role().
        Confirmed live (2026-09-22): self.drone always exposes .bio_scanner
        AND .bio_extractor as attributes regardless of which (if either) is
        actually mounted -- hasattr(self.drone, "bio_scanner") and
        hasattr(self.drone, "bio_extractor") both returned True on a drone
        carrying only a Bio Scanner, so hasattr can never tell "mounted"
        from "not mounted" for these two. Drone also has no .modules() to
        enumerate equipment generically (unlike Rover/Pioneer). The only
        available signal is to actually call the module's own method once
        and read whether the result's .status comes back "not_mounted" --
        a real Literal value both PortableBioScanner.scan() and
        PortableBioExtractor.extract() document (docs/models/
        biology_models.md) -- or something else ("ok"/"busy"/"scrambled"/
        "not_at_location"/... all mean the module IS present).

        scan() is documented as a free, repeatable no-cost probe ("Repeat
        scans are free"), so calling it here is harmless. extract() has no
        such guarantee: if this drone happens to be hovering over a live
        biosite the moment this runs (e.g. resuming right where a miner
        left off after a reload), calling it as a probe genuinely extracts
        for real -- accepted as the only available detection mechanism
        (see TODO.md); a resumed miner extracting again at its own resumed
        site is the same outcome run_miner_loop() would produce anyway, not
        a new side effect.
        """
        if role_override is not None:
            self.log.debug(f"[{self.name}] Role override supplied: '{role_override}'; skipping equipment probe.")
            return role_override

        self.log.start(f"[{self.name}] Detecting role from mounted equipment (live scan()/extract() probe)")
        present = []
        for role, attr in self.ROLE_MODULES.items():
            module = getattr(self.drone, attr, None)
            probe_method = self.ROLE_PROBE_METHOD.get(attr)
            mounted = False
            if module is not None and probe_method:
                try:
                    result = getattr(module, probe_method)()
                    mounted = getattr(result, "status", None) != "not_mounted"
                except Exception as exc:
                    self.log.debug(f"{attr}.{probe_method}() probe raised: {exc}")
            self.log.debug(f"{attr} module mounted: {mounted}")
            if mounted:
                present.append(role)

        if len(present) > 1:
            self.log.level("warn").print(
                f"[{self.name}] Multiple role-defining modules mounted ({', '.join(present)}); "
                f"cannot auto-detect a role. Call run(role_override=...) with one of {list(self.ROLE_MODULES)}."
            )
            self.log.end(f"[{self.name}] Role detection failed")
            return None
        if not present:
            self.log.end(f"[{self.name}] No role-defining module mounted")
            return None

        role = present[0]
        self.log.end(f"[{self.name}] Detected role: '{role}'")
        return role

    def run(self, role_override=None):
        """
        Unified entrypoint: detects this drone's role from its mounted field
        module (Bio Scanner -> scout, Bio Extractor -> miner) and dispatches
        to the matching loop. role_override forces a specific role, required
        when both/neither module is mounted (see detect_role()).
        """
        role = self.detect_role(role_override)
        if role is None:
            self.log.level("warn").print(f"[{self.name}] No role-defining module (bio_scanner/bio_extractor) mounted; cannot start. Mount one via couple() at a Drone Depot, or pass run(role_override=...).")
            return

        validate_game_version()
        if role == "scout":
            self.run_scout_loop()
        elif role == "miner":
            self.run_miner_loop()
        else:
            self.log.level("warn").print(f"[{self.name}] Unknown role '{role}'.")
