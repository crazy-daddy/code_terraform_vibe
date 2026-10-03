from swallow import swallowed
import fluid_routing
from production import discover_fluid_sources
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plant_terraformer import PlantTerraformerController

# Plant Terraformer mixin: water supply (lib/plant_terraformer.py). Water
# comes through water_in from one FluidInputRouter, same as the
# Fabricator's: sources are every viable water building on the network, own
# outpost first; a starved port (flow 0 with room left) counts toward the
# stall blacklist.

# Water input routing, same values as the Fabricator's water_in router
# (lib/fabricator.py).
FLUID_STALL_STREAK_BLACKLIST_THRESHOLD = 5
FLUID_RESCAN_INTERVAL_TICKS = 150
FLUID_DISCOVERY_CACHE_INTERVAL_TICKS = 100
FLUID_NEUTRAL_GRACE_STEPS = 5


class PlantTerraformerWaterMixin:

    @property
    def _host(self) -> "PlantTerraformerController":
        return self  # type: ignore[return-value]

    def _init_water(self):
        self._water_router = None

    def water_level(self):
        port = getattr(self._host.machine, "water_in", None)
        if not port or not hasattr(port, "level"):
            return 0.0
        try:
            return float(port.level() or 0.0)
        except Exception as error:
            swallowed("plant_terraformer_water.PlantTerraformerWaterMixin.water_level: port.level", error)
            return 0.0

    def _discover_water_sources(self):
        host = self._host
        host.log.start(f"[{host.name}] _discover_water_sources", level="debug")
        ids = discover_fluid_sources("water_in", host.outpost_id)
        host.log.debug(f"water_in: sources (own outpost first): {ids}.")
        host.log.end()
        return ids

    def ensure_water(self, curr_tick):
        host = self._host
        port = getattr(host.machine, "water_in", None)
        if not port:
            return
        if self._water_router is None:
            self._water_router = fluid_routing.FluidInputRouter(
                discover=self._discover_water_sources,
                rescan_interval_ticks=FLUID_RESCAN_INTERVAL_TICKS,
                discovery_cache_interval_ticks=FLUID_DISCOVERY_CACHE_INTERVAL_TICKS,
                stall_streak_threshold=FLUID_STALL_STREAK_BLACKLIST_THRESHOLD,
                neutral_grace_steps=FLUID_NEUTRAL_GRACE_STEPS,
                label=f"{host.name}.water_in",
                reserve_fluid="water",
            )

        def on_dropped(source_id, reason):
            host.log.level("warn").print(f"[{host.name}] Dropping water source '{source_id}': {reason}. Picking another.")

        def on_connect_notice(source_id, status, message):
            host.log.level("warn").print(f"[{host.name}] water_in connect notice for '{source_id}': {status} - {message}")

        event = self._water_router.ensure(port, curr_tick, fluid_routing.port_starved(port), on_dropped, on_connect_notice)
        if event.kind == "connected":
            host.log.print(f"[{host.name}] Connected water_in -> '{event.source_id}'.")
        elif event.kind == "not_found":
            host.log.debug(f"[{host.name}] no water source on the network.")
