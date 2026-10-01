import fluid_routing
from fluid_pump import FluidPumpController, PUMP_POLL_SECONDS, LIQUID_TANK_REBALANCE_FILL_FRACTION, CONNECTION_GRACE_TICKS, RESCAN_INTERVAL_TICKS, DISCOVERY_CACHE_INTERVAL_TICKS
from version_guard import validate_game_version
from tree_console import flush_all, reset_all
from script_parking import ParkRequester
from swallow import swallowed

# Exotic Gas Cap / Exotic Spring Tap automation: the routing loop of lib/fluid_pump.py
# on an exotic deposit. The output port (gas_out / liquid_out) is routed to a network
# tank eligible for the deposit's fluid (deposit().fluid(), e.g. "ammonia", "raw_chlorine"):
# Gas Tanks for a Cap, Liquid Tanks / Large Liquid Tanks for a Tap. An empty tank needs a
# fluid_routing.tank_assignments entry first. A full buffer only pauses collection
# (docs/components/exotic_gas_cap.md), so there is no overpressure control.
#
# The release valve stays wide open in both phases: a dormant deposit captures nothing,
# so an open valve only drains the buffer, and the cap needs no step to catch the start
# of the active phase.
#
# Deposit cycles are short: common deposits run about 25-45 game-min active and 45-90
# dormant, under a minute of real time per cycle at 25 real s per game hour. Parking
# (lib/script_parking.py kind "exotic_cap") pays off only for a long dormant phase, so a
# cap parks only when the deposit is dormant, the buffer has stopped releasing, and
# next_phase_in() (Deep survey) leaves at least EXOTIC_PARK_MIN_TICKS of parked time
# after EXOTIC_WAKE_LEAD_TICKS. It files wake_after = time left - lead, so it is powered
# again before the deposit turns active. The panel also wakes it once current_phase()
# reads "active". An unpowered cap captures nothing, so a late wake loses output.

GAS_TANK_TYPE_IDS = ("gas_tank",)

MEDIA = {
    "gas": {"port": "gas_out", "tanks": GAS_TANK_TYPE_IDS, "label": "Exotic Gas Cap", "tank_label": "Gas Tanks"},
    "liquid": {"port": "liquid_out", "tanks": fluid_routing.LIQUID_TANK_TYPE_IDS, "label": "Exotic Spring Tap", "tank_label": "Liquid Tanks"},
}

# Minimum parked time worth a park/wake round trip (ticks, 10 per second).
EXOTIC_PARK_MIN_TICKS = 600
# Wake this many ticks before the deposit turns active. Covers the panel's parking pass
# interval (control_room_automation.py PARKING_TICK_INTERVAL = 50) twice, between the
# request and the park and again at the wake, plus the resumed script's first sleep.
EXOTIC_WAKE_LEAD_TICKS = 150
# Fallback when clock.real_seconds_per_hour() is unreadable.
DEFAULT_REAL_SECONDS_PER_HOUR = 25.0


def deposit_active(cap):
    """True while the cap's deposit is in its active phase; False when dormant, unsurveyed or missing."""
    deposit = cap.deposit() if hasattr(cap, "deposit") else None
    return deposit is not None and deposit.current_phase() == "active"


class ExoticCapController(FluidPumpController):
    """Routes an Exotic Gas Cap / Spring Tap output to tanks of its deposit's fluid; parks through long dormant phases."""

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
        self.tank_label = media["tank_label"]
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
        """Never True: FluidPumpController.step() then keeps the valve open in both phases (see the module comment)."""
        return False

    def _ticks_per_game_minute(self):
        seconds_per_hour = DEFAULT_REAL_SECONDS_PER_HOUR
        if self.clock and hasattr(self.clock, "real_seconds_per_hour"):
            try:
                seconds_per_hour = float(self.clock.real_seconds_per_hour())
            except Exception as error:
                swallowed("exotic_cap.ExoticCapController._ticks_per_game_minute: clock.real_seconds_per_hour", error)
        return seconds_per_hour / 60.0 * 10.0

    def park_wake_ticks(self):
        """Ticks this cap may stay parked, or None while it must keep running (see the module comment)."""
        deposit = self.pump.deposit() if hasattr(self.pump, "deposit") else None
        if deposit is None or deposit.current_phase() != "dormant":
            return None
        port = getattr(self.pump, self.port_name, None)
        if port is not None and hasattr(port, "flow_rate") and port.flow_rate() > 0:
            return None
        minutes = deposit.next_phase_in()
        if minutes is None:
            self.log.trace(f"[{self.name}] Deposit dormant without phase timing (needs Deep survey); not parking.")
            return None
        wake_after = int(minutes * self._ticks_per_game_minute()) - EXOTIC_WAKE_LEAD_TICKS
        if wake_after < EXOTIC_PARK_MIN_TICKS:
            self.log.trace(f"[{self.name}] Deposit active again in {minutes:.0f} game-min; too soon to park.")
            return None
        self.log.debug(f"[{self.name}] Deposit dormant for {minutes:.0f} more game-min; parking for {wake_after} ticks.")
        return wake_after

    def run(self, poll_interval=PUMP_POLL_SECONDS):
        self.log.print(f"{self.label} Controller ({self.name}) online. Routing {self.fluid_id} to network {self.tank_label}.")
        validate_game_version()
        while True:
            reset_all()
            wake_ticks = None
            try:
                self.step()
                wake_ticks = self.park_wake_ticks()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] {self.label} exception: {error}")
            self.parker.update(wake_ticks is not None, wake_ticks)
            flush_all()
            sleep(poll_interval)
