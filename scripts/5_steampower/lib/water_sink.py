from waste_sink import WasteSinkController, STATUS_KEY
from archive import archive
import fluid_routing
from swallow import swallowed

# Water overflow on top of the Waste Processor's item duty
# (docs/components/waste_processor.md "liquid" mode, 120 t/h at 100 %).
#
# Water Pumps stall once every reachable Water tank is full (lib/fluid_pump.py
# stops at LIQUID_TANK_REBALANCE_FILL_FRACTION), and a stalled pump makes no
# salt. Salt is the Plant Terraformer's phase-3 input and the Dispensers'
# treatment, so the pumps should run even when nothing downstream wants the
# water. The processor drains its outpost's fullest Water tank from
# WATER_SINK_HIGH_FILL down to WATER_SINK_LOW_FILL: the pumps never see a full
# tank, and consumers on the same tank (Sprinklers, Terraformer water_in) keep
# at least the low mark.
#
# One processor has one mode at a time. While draining it stays in "liquid";
# otherwise it runs WasteSinkController's items duty. The staged items or
# liquid of the paused mode stay in their buffer. With several processors at
# one outpost only the lowest id drains water, so the others keep destroying
# items. Only same-outpost tanks are used: a remote tank needs its own Liquid
# Pipe route to the processor, which this outpost's processor can't check.

WASTE_PROCESSOR_TYPE_ID = "garbage_disposal"
WATER_FLUID_ID = "water"

# Start draining at this tank fill (below the pumps' 0.98 give-up mark), stop at
# WATER_SINK_LOW_FILL.
WATER_SINK_HIGH_FILL = 0.90
WATER_SINK_LOW_FILL = 0.60


class WaterAwareWasteSinkController(WasteSinkController):
    """WasteSinkController that switches to "liquid" mode to keep the outpost's Water tank below full."""

    def __init__(self, processor):
        super().__init__(processor)
        self._draining = False
        self._tank_id = None
        self._tank_fill = None

    def _water_duty(self):
        """True when this is the lowest-id Waste Processor at its outpost."""
        outpost = self._outpost()
        if not outpost or not hasattr(outpost, "buildings"):
            return True
        try:
            ids = sorted(getattr(ref, "id", "") for ref in outpost.buildings(WASTE_PROCESSOR_TYPE_ID))
        except Exception as error:
            swallowed("water_sink.WaterAwareWasteSinkController._water_duty: outpost.buildings", error)
            return True
        ids = [i for i in ids if i]
        return not ids or ids[0] == self.name

    def _fullest_water_tank(self):
        """(tank, fill 0-1) of the fullest Water-latched tank at this outpost, else (None, None)."""
        outpost = self._outpost()
        if not outpost or not hasattr(outpost, "buildings"):
            return None, None
        best, best_fill = None, None
        for type_id in fluid_routing.LIQUID_TANK_TYPE_IDS:
            try:
                refs = list(outpost.buildings(type_id))
            except Exception as error:
                swallowed("water_sink.WaterAwareWasteSinkController._fullest_water_tank: outpost.buildings", error)
                continue
            for ref in refs:
                try:
                    tank = get_component(ref.id) or ref
                    latched = tank.fluid()
                except Exception as error:
                    swallowed("water_sink.WaterAwareWasteSinkController._fullest_water_tank: tank.fluid", error)
                    continue
                if latched != WATER_FLUID_ID:
                    continue
                fill = fluid_routing.fill_pct_of(tank)
                self.log.trace(f"[{self.name}] water tank '{tank.id}' at {fill*100:.0f}%.")
                if best_fill is None or fill > best_fill:
                    best, best_fill = tank, fill
        return best, best_fill

    def _update_draining(self, tank, fill):
        if self._draining:
            if tank is None or fill <= WATER_SINK_LOW_FILL:
                self._draining = False
                self.log.print(f"[{self.name}] Water drain off: {'no Water tank here' if tank is None else f'{tank.id} at {fill*100:.0f}%'} (stop at {WATER_SINK_LOW_FILL*100:.0f}%).")
            return
        if tank is None:
            self.log.trace(f"[{self.name}] no Water tank at this outpost; items duty only.")
            return
        if fill < WATER_SINK_HIGH_FILL:
            self.log.trace(f"[{self.name}] '{tank.id}' at {fill*100:.0f}% < {WATER_SINK_HIGH_FILL*100:.0f}%; items duty.")
            return
        if not self._water_duty():
            self.log.debug(f"[{self.name}] '{tank.id}' at {fill*100:.0f}% but a lower-id Waste Processor here drains water; items duty.")
            return
        self._draining = True
        self.log.print(f"[{self.name}] Water drain on: '{tank.id}' at {fill*100:.0f}% (start at {WATER_SINK_HIGH_FILL*100:.0f}%) so the Water Pumps don't stall.")

    def arm_liquid(self, tank_id):
        """Liquid mode, liquid_in -> tank_id, enabled; all idempotent."""
        try:
            port = self.processor.liquid_in
            if port.connected_id() != tank_id:
                res = port.connect(tank_id)
                status = getattr(res, "status", "ok")
                if status != "ok":
                    self.log.level("warn").print(f"[{self.name}] liquid_in connect '{tank_id}': {status} - {getattr(res, 'message', '')}")
                    return
                self.log.debug(f"[{self.name}] liquid_in -> '{tank_id}'.")
            if self.processor.mode() != "liquid":
                self.processor.set_mode("liquid")
                self.log.debug(f"[{self.name}] mode -> liquid.")
            if not self.processor.is_enabled():
                self.processor.set_enabled(True)
                self.log.print(f"[{self.name}] Armed (liquid mode).")
        except Exception as e:
            self.log.level("error").print(f"[{self.name}] liquid arm failed: {e}")

    def publish_telemetry(self):
        super().publish_telemetry()
        try:
            rate = self.processor.liquid_throughput()
        except Exception as error:
            swallowed("water_sink.WaterAwareWasteSinkController.publish_telemetry: liquid_throughput", error)
            rate = 0.0
        entry = archive.get(STATUS_KEY, {}).get(self.name, {})
        if not isinstance(entry, dict):
            entry = {}
        entry["water"] = {
            "draining": self._draining,
            "tank": self._tank_id,
            "fill": round(self._tank_fill, 3) if self._tank_fill is not None else None,
            "rate": rate,
        }
        archive.set_entry(STATUS_KEY, self.name, entry)

    def step(self):
        tank, fill = self._fullest_water_tank()
        self._tank_id = getattr(tank, "id", None)
        self._tank_fill = fill
        self._update_draining(tank, fill)
        if self._draining:
            self.arm_liquid(self._tank_id)
        else:
            self.arm()
            self.feed()
        self.publish_telemetry()
