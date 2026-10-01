import fluid_routing
from fluid_pump import FluidPumpController, LIQUID_TANK_REBALANCE_FILL_FRACTION, CONNECTION_GRACE_TICKS, RESCAN_INTERVAL_TICKS, DISCOVERY_CACHE_INTERVAL_TICKS
from script_parking import ParkRequester
from swallow import swallowed

# Exotic Gas Cap / Exotic Spring Tap automation: the Oil Pump loop of lib/fluid_pump.py
# on an exotic deposit. The output port (gas_out / liquid_out) is routed to a network
# tank eligible for the deposit's fluid (deposit().fluid(), e.g. "ammonia", "raw_chlorine"):
# Gas Tanks for a Cap, Liquid Tanks / Large Liquid Tanks for a Tap. An empty tank needs a
# fluid_routing.tank_assignments entry first. A full buffer only pauses collection
# (docs/components/exotic_gas_cap.md), so there is no overpressure control.
#
# Dormancy: while the deposit is not "active" the script keeps the valve open until the
# buffer stops releasing (port flow_rate() == 0), then closes it and parks
# (lib/script_parking.py kind "exotic_cap"). The panel wakes it when the deposit turns
# active again (current_phase() reads from any script).

GAS_TANK_TYPE_IDS = ("gas_tank",)

MEDIA = {
    "gas": {"port": "gas_out", "tanks": GAS_TANK_TYPE_IDS, "label": "Exotic Gas Cap"},
    "liquid": {"port": "liquid_out", "tanks": fluid_routing.LIQUID_TANK_TYPE_IDS, "label": "Exotic Spring Tap"},
}


def deposit_active(cap):
    """True while the cap's deposit is in its active phase; False when dormant, unsurveyed or missing."""
    deposit = cap.deposit() if hasattr(cap, "deposit") else None
    return deposit is not None and deposit.current_phase() == "active"


class ExoticCapController(FluidPumpController):
    """Routes an Exotic Gas Cap / Spring Tap output to tanks of its deposit's fluid; parks while the deposit is dormant."""

    def __init__(self, cap):
        medium = "gas" if hasattr(cap, "gas_out") else "liquid"
        deposit = None
        try:
            deposit = cap.deposit()
        except Exception as error:
            swallowed("exotic_cap.ExoticCapController.__init__: cap.deposit", error)
        fluid_id = deposit.fluid() if deposit is not None else None
        super().__init__(cap, fluid_id or medium)
        media = MEDIA[medium]
        self.port_name = media["port"]
        self.label = media["label"]
        self.parker = ParkRequester(self.name, "exotic_cap")
        self._router = fluid_routing.FluidOutputRouter(
            type_ids=media["tanks"],
            rebalance_fill_fraction=LIQUID_TANK_REBALANCE_FILL_FRACTION,
            connection_grace_ticks=CONNECTION_GRACE_TICKS,
            rescan_interval_ticks=RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=DISCOVERY_CACHE_INTERVAL_TICKS,
            fluid_id=fluid_id,
            label=f"{self.name}.{self.port_name}",
        )
        if fluid_id is None:
            self.log.level("warn").print(f"[{self.name}] No surveyed deposit under this {self.label}; staying idle.")

    def well_dormant(self):
        """True once the deposit is not active and the buffer has stopped releasing."""
        try:
            if deposit_active(self.pump):
                return False
        except Exception as error:
            swallowed("exotic_cap.ExoticCapController.well_dormant: deposit_active", error)
            return False
        port = getattr(self.pump, self.port_name, None)
        flow = 0.0
        if port is not None and hasattr(port, "flow_rate"):
            try:
                flow = port.flow_rate()
            except Exception as error:
                swallowed("exotic_cap.ExoticCapController.well_dormant: port.flow_rate", error)
        if flow > 0:
            self.log.trace(f"[{self.name}] Deposit dormant, buffer still releasing {flow:.1f} t/h.")
            return False
        return True
