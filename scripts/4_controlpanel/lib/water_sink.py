from waste_sink import WasteSinkController
import fluid_routing
from swallow import swallowed

# Water overflow, the Waste Processor's only duty
# (docs/components/waste_processor.md "liquid" mode, 120 t/h at 100 %).
#
# Water Pumps stall once every reachable Water tank is full (lib/fluid_pump.py
# stops at LIQUID_TANK_REBALANCE_FILL_FRACTION), and a stalled pump makes no
# salt. Salt is the Plant Terraformer's phase-3 input and the Dispensers'
# treatment, so the pumps should run even when nothing downstream wants the
# water. Water is scarce too, so draining is a last resort:
#   - start only when every Water tank at this outpost is at or above
#     WATER_SINK_HIGH_FILL AND some Water Pump on the network reports
#     is_stalled() (nothing downstream accepts its water). One full tank
#     while others have room is not overflow -- the pumps rebalance to the
#     emptier tanks -- and full local tanks with no stalled pump mean the
#     pumps still have room somewhere else on the network.
#   - drain only the tank that was fullest at the start (locked for the
#     whole drain), down to WATER_SINK_LOW_FILL: just enough room to unstall
#     the pumps, not a sweep across every tank.
# Tanks count when fluid_routing.tank_is_eligible_target() accepts them for
# water (latched to water, or empty and assigned to water), so an empty
# assigned tank counts as room.
#
# While draining the processor stays in "liquid" mode; otherwise it idles
# (WasteSinkController.idle(): disabled, staged items returned to storage).
# With several processors at one outpost only the lowest id drains water; the
# others stay idle. Only same-outpost tanks are used: a remote tank needs its own Liquid
# Pipe route to the processor, which this outpost's processor can't check.

WASTE_PROCESSOR_TYPE_ID = "garbage_disposal"
WATER_FLUID_ID = "water"
WATER_PUMP_TYPE_ID = "water_pump"

# Start when every Water tank here is at least this full (and a pump is
# stalled); stop once the locked tank is down to WATER_SINK_LOW_FILL.
WATER_SINK_HIGH_FILL = 0.90
WATER_SINK_LOW_FILL = 0.80


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

    def _water_tanks(self):
        """[(tank, fill 0-1)] of every water-eligible tank at this outpost."""
        outpost = self._outpost()
        if not outpost or not hasattr(outpost, "buildings"):
            return []
        tanks = []
        assignments = fluid_routing.get_tank_assignments()
        for type_id in fluid_routing.LIQUID_TANK_TYPE_IDS:
            try:
                refs = list(outpost.buildings(type_id))
            except Exception as error:
                swallowed("water_sink.WaterAwareWasteSinkController._water_tanks: outpost.buildings", error)
                continue
            for ref in refs:
                try:
                    tank = get_component(ref.id) or ref
                except Exception as error:
                    swallowed("water_sink.WaterAwareWasteSinkController._water_tanks: get_component", error)
                    continue
                if not fluid_routing.tank_is_eligible_target(tank, WATER_FLUID_ID, assignments):
                    continue
                fill = fluid_routing.fill_pct_of(tank)
                self.log.trace(f"[{self.name}] water tank '{tank.id}' at {fill*100:.0f}%.")
                tanks.append((tank, fill))
        return tanks

    def _stalled_water_pump(self):
        """Id of a Water Pump anywhere on the network reporting is_stalled(), else None."""
        for pump, _ in fluid_routing.discover_network_buildings(WATER_PUMP_TYPE_ID):
            if fluid_routing.safe_is_stalled(pump):
                return getattr(pump, "id", "?")
        return None

    def _update_draining(self, tanks):
        self.log.start(f"[{self.name}] _update_draining", level="debug")
        if self._draining:
            fill = next((f for t, f in tanks if t.id == self._tank_id), None)
            if fill is None or fill <= WATER_SINK_LOW_FILL:
                self._draining = False
                self.log.print(f"[{self.name}] Water drain off: {f'{self._tank_id} gone or no longer water' if fill is None else f'{self._tank_id} at {fill*100:.0f}%'} (stop at {WATER_SINK_LOW_FILL*100:.0f}%).")
            else:
                self._tank_fill = fill
            self.log.end()
            return
        if not tanks:
            self.log.trace("no Water tank at this outpost; idle.")
            self.log.end()
            return
        tank, fill = max(tanks, key=lambda pair: pair[1])
        self._tank_id = tank.id
        self._tank_fill = fill
        lowest = min(f for _, f in tanks)
        if lowest < WATER_SINK_HIGH_FILL:
            self.log.trace(f"emptiest Water tank here at {lowest*100:.0f}% < {WATER_SINK_HIGH_FILL*100:.0f}%; room left, idle.")
            self.log.end()
            return
        if not self._water_duty():
            self.log.debug(f"Water tanks here all >= {WATER_SINK_HIGH_FILL*100:.0f}% but a lower-id Waste Processor here drains water; idle.")
            self.log.end()
            return
        pump_id = self._stalled_water_pump()
        if not pump_id:
            self.log.debug(f"Water tanks here all >= {WATER_SINK_HIGH_FILL*100:.0f}% but no Water Pump is stalled; pumps still have room elsewhere, idle.")
            self.log.end()
            return
        self._draining = True
        self.log.print(f"[{self.name}] Water drain on: all {len(tanks)} Water tank(s) here >= {WATER_SINK_HIGH_FILL*100:.0f}% and '{pump_id}' stalled; draining '{tank.id}' ({fill*100:.0f}%) to {WATER_SINK_LOW_FILL*100:.0f}%.")
        self.log.end()

    def arm_liquid(self, tank_id):
        """Liquid mode, liquid_in -> tank_id, enabled; all idempotent."""
        self.log.start(f"[{self.name}] arm_liquid", level="debug")
        try:
            port = self.processor.liquid_in
            if port.connected_id() != tank_id:
                res = port.connect(tank_id)
                status = getattr(res, "status", "ok")
                if status != "ok":
                    self.log.level("warn").print(f"[{self.name}] liquid_in connect '{tank_id}': {status} - {getattr(res, 'message', '')}")
                    self.log.end()
                    return
                self.log.debug(f"liquid_in -> '{tank_id}'.")
            if self.processor.mode() != "liquid":
                self.processor.set_mode("liquid")
                self.log.debug("mode -> liquid.")
            if not self.processor.is_enabled():
                self.processor.set_enabled(True)
                self.log.print(f"[{self.name}] Armed (liquid mode).")
        except Exception as e:
            self.log.level("error").print(f"[{self.name}] liquid arm failed: {e}")
        self.log.end()

    def telemetry_entry(self):
        entry = super().telemetry_entry()
        try:
            rate = self.processor.liquid_throughput()
        except Exception as error:
            swallowed("water_sink.WaterAwareWasteSinkController.telemetry_entry: liquid_throughput", error)
            rate = 0.0
        entry["water"] = {
            "draining": self._draining,
            "tank": self._tank_id,
            "fill": round(self._tank_fill, 3) if self._tank_fill is not None else None,
            "rate": rate,
        }
        return entry

    def step(self):
        self._update_draining(self._water_tanks())
        if self._draining:
            self.arm_liquid(self._tank_id)
        else:
            self.idle()
        self.publish_telemetry()
