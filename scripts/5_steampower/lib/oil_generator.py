import fluid_routing
import power
from version_guard import validate_game_version
from tree_console import TreeConsole

# Oil Generator automation: LAST-RESORT power only.
#
# An Oil Generator gives +700 W at throttle 1 for 8 t/h of oil
# (docs/components/oil_generator.md). Oil is valuable (Fabricator recipes use
# it) and burning it emits CO2, so this controller keeps the generator idle
# until both of these are true:
#   - the grid's reserve is low: the BATTERY fraction is below
#     OIL_START_RESERVE_FRACTION, or the combined reserve (battery + banked
#     steam, measured exactly like the tier-5 Power Guard --
#     power.measure_grid()/reserve_fraction()) is, and
#   - the grid is running a deficit without oil (consumption exceeds every
#     non-oil generator's output).
# Why battery and not just the combined figure: the deficit is measured
# after the Steam Turbines' output, so banked steam cannot cover it --
# turbines are rate-limited (90 t/h each), not stock-limited. Only the
# battery buffers a deficit. With 35,000 t of steam banked the combined
# reserve read 64% while the battery ran dry and the grid browned out.
# While burning, the throttle covers the deficit (plus a little headroom)
# and OIL_RECHARGE_W to refill the battery, shared evenly across every Oil
# Generator on the grid so they don't stack. It stops once both fractions
# have recovered to OIL_STOP_RESERVE_FRACTION (hysteresis, so it doesn't
# flap on the start line).
#
# No archive state: the game resets the throttle to 0 when the script stops,
# and after a restart the idle->burning check re-triggers within one step if
# the conditions still hold.

OIL_GENERATOR_RATED_W = 700.0

# Hysteresis on the combined reserve fraction. Start sits above the Power
# Guard's EMERGENCY_SHED_TIER1_FRACTION (0.10) so oil can catch the grid
# before loads get shed; stop sits above its EMERGENCY_RESTORE_FRACTION
# (0.25) so shed loads are back on before oil burning ends.
OIL_START_RESERVE_FRACTION = 0.15
OIL_STOP_RESERVE_FRACTION = 0.30

# Cover the deficit with a little margin (grid readings lag one power tick),
# and never idle along below this throttle once burning -- a trickle wouldn't
# move the reserve.
OIL_DEFICIT_HEADROOM = 1.1
OIL_MIN_THROTTLE = 0.1

# Grid-wide surplus (W) the burning generators add on top of the deficit so
# the battery actually climbs back to the stop line. Without it the 10%
# headroom alone refills an 11 kWh bank at ~50 W (days of oil burn).
OIL_RECHARGE_W = 300.0

# Oil source routing (FluidInputRouter) -- same meaning as
# lib/steam_turbine.py's constants of the same names.
STALL_STREAK_BLACKLIST_THRESHOLD = 5
RESCAN_INTERVAL_TICKS = 150
DISCOVERY_CACHE_INTERVAL_TICKS = 100
NEUTRAL_GRACE_STEPS = 5

OIL_TANK_TYPE_IDS = ("liquid_tank", "large_liquid_tank")


def _notify(text, level="warn", duration=8.0):
    try:
        notify(text, level=level, duration_seconds=duration)
    except Exception:
        pass


class OilGeneratorController:
    """Burns oil only as last-resort power: low combined reserve AND a deficit without oil."""

    def __init__(self, generator):
        self.generator = generator
        self.name = getattr(generator, "id", "oil_generator")
        self.clock = get_component("clock")
        self.power = get_component("power_control")
        self.log = TreeConsole(module="oil_generator")
        self.burning = False
        self.starved_warned = False
        self._router = fluid_routing.FluidInputRouter(
            discover=self._discover_candidates,
            rescan_interval_ticks=RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=DISCOVERY_CACHE_INTERVAL_TICKS,
            stall_streak_threshold=STALL_STREAK_BLACKLIST_THRESHOLD,
            neutral_grace_steps=NEUTRAL_GRACE_STEPS,
            label=f"{self.name}.oil_in",
        )

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception:
                pass
        return 0

    # ------------------------------------------------------------------
    # Oil input
    # ------------------------------------------------------------------
    def _discover_candidates(self):
        """Oil-eligible Liquid Tanks / Large Liquid Tanks network-wide, own outpost first, then Oil
        Pumps as a direct fallback (docs/components/oil_generator.md recommends a tank buffer, since
        oil wells go dormant)."""
        own_outpost_id = getattr(getattr(self.generator, "outpost", None), "id", None)
        ranked = []
        for type_id in OIL_TANK_TYPE_IDS:
            pairs = fluid_routing.discover_network_buildings(type_id, resolve=False, fluid_id="oil")
            ranked.extend(fluid_routing.rank_own_outpost_first(pairs, own_outpost_id))
        pumps = fluid_routing.discover_network_buildings("oil_pump", resolve=False)
        ranked.extend(fluid_routing.rank_own_outpost_first(pumps, own_outpost_id))
        self.log.debug(f"[{self.name}] Rediscovered oil sources (tanks first, own outpost '{own_outpost_id}' first): {ranked}.")
        return ranked

    def is_starved(self):
        """True while asked to burn but no oil arrives (no is_stalled() on this building)."""
        try:
            if self.generator.throttle() <= 0:
                return False
            port = self.generator.oil_in
            return port.level() <= 0 and self.generator.oil_consumption() <= 0
        except Exception:
            return False

    def ensure_input_connection(self):
        """Keeps oil_in on a reachable oil source. A tank has no script, so this generator declares the link."""
        port = getattr(self.generator, "oil_in", None)
        curr_tick = self.get_current_tick()

        def on_dropped(source_id, reason):
            self.log.level("warn").print(f"[{self.name}] Dropping oil source '{source_id}': {reason}. Picking a different source.")

        def on_connect_notice(source_id, status, message):
            self.log.level("warn").print(f"[{self.name}] oil_in connect notice for '{source_id}': {status} - {message}")

        event = self._router.ensure(port, curr_tick, self.is_starved(), on_dropped, on_connect_notice)
        if event.kind == "connected":
            self.log.print(f"[{self.name}] Connected oil_in -> '{event.source_id}'.")
        elif event.kind == "waiting":
            self.log.debug(f"[{self.name}] Every known oil source is still within its blacklist window; waiting for one to expire.")
        elif event.kind == "not_found":
            self.log.debug(f"[{self.name}] No oil-eligible tank or Oil Pump found network-wide yet (an empty tank needs a fluid_routing.tank_assignments entry for 'oil').")

    # ------------------------------------------------------------------
    # Last-resort decision
    # ------------------------------------------------------------------
    def get_grid(self):
        if self.power and hasattr(self.power, "grid"):
            try:
                return self.power.grid(self.name)
            except Exception:
                pass
        return None

    def oil_deficit_share(self, grid):
        """(deficit_w, share_w, generator_count). deficit_w = consumption minus every NON-oil
        generator's output; share_w is this generator's even share of it."""
        oil_members = [m for m in (getattr(grid, "members", None) or []) if getattr(m, "type_id", "") == "oil_generator"]
        oil_total = sum(getattr(m, "generated", 0.0) or 0.0 for m in oil_members)
        if not any(getattr(m, "id", None) == self.name for m in oil_members):
            # Members missing this generator: fall back to its own reading.
            try:
                oil_total += self.generator.power_output()
            except Exception:
                pass
            oil_members.append(None)
        base_gen = getattr(grid, "generated", 0.0) - oil_total
        deficit = getattr(grid, "consumed", 0.0) - base_gen
        count = max(1, len(oil_members))
        return deficit, deficit / count, count

    def choose_throttle(self):
        grid = self.get_grid()
        if not grid:
            if self.burning:
                self.log.level("warn").print(f"[{self.name}] Grid unreadable -- stopping oil burn (fail safe).")
                self.burning = False
            self.log.debug(f"[{self.name}] No grid for this generator; throttle 0.")
            return 0.0

        now = power.measure_grid(grid, power.grid_steam_tank_ids(grid))
        reserve = power.reserve_fraction(now)
        battery = now["bat_wh"] / now["bat_cap"] if now["bat_cap"] > 0 else None
        deficit, share, count = self.oil_deficit_share(grid)
        reserve_str = f"{reserve*100:.1f}%" if reserve is not None else "n/a (no storage)"
        battery_str = f"{battery*100:.1f}%" if battery is not None else "n/a (no battery)"
        self.log.debug(
            f"[{self.name}] Battery {battery_str}, combined reserve {reserve_str} [battery {now['bat_wh']:.0f}/{now['bat_cap']:.0f} Wh, steam {now['steam_t']:.0f}/{now['steam_cap']:.0f} t], "
            f"deficit without oil {deficit:.0f} W, share {share:.0f} W over {count} oil generator(s), burning={self.burning}."
        )

        if not self.burning:
            fractions = [f for f in (battery, reserve) if f is not None]
            low = not fractions or min(fractions) < OIL_START_RESERVE_FRACTION
            if low and deficit > 0:
                self.burning = True
                msg = f"Oil Generator '{self.name}' burning oil: battery {battery_str}, combined reserve {reserve_str}, deficit {deficit:.0f} W. Emits CO2."
                self.log.level("warn").print(
                    f"[{self.name}] Last resort ON -- battery {battery_str} / combined {reserve_str}, lowest < {OIL_START_RESERVE_FRACTION*100:.0f}%, deficit {deficit:.0f} W."
                )
                _notify(f"[Power] {msg}")
            else:
                self.log.debug(f"[{self.name}] Idle: reserve_low={low} (battery {battery_str}, combined {reserve_str}), deficit={deficit:.0f} W -- oil stays in the tank.")
                return 0.0
        else:
            fractions = [f for f in (battery, reserve) if f is not None]
            recovered = min(fractions) >= OIL_STOP_RESERVE_FRACTION if fractions else deficit <= 0
            if recovered:
                self.burning = False
                self.starved_warned = False
                self.log.print(
                    f"[{self.name}] Last resort OFF -- battery {battery_str}, combined {reserve_str} (stop at {OIL_STOP_RESERVE_FRACTION*100:.0f}%), deficit {deficit:.0f} W."
                )
                return 0.0

        # Only add recharge wattage when there is a battery to refill.
        recharge_share = OIL_RECHARGE_W / count if battery is not None else 0.0
        target_w = max(0.0, share) * OIL_DEFICIT_HEADROOM + recharge_share
        throttle = min(1.0, max(OIL_MIN_THROTTLE, target_w / OIL_GENERATOR_RATED_W))
        self.log.debug(
            f"[{self.name}] Burning: share {share:.0f} W x{OIL_DEFICIT_HEADROOM} + recharge {recharge_share:.0f} W = {target_w:.0f} W / {OIL_GENERATOR_RATED_W:.0f} W -> throttle {throttle:.2f}."
        )
        return throttle

    def step(self):
        self.ensure_input_connection()
        throttle = self.choose_throttle()
        if hasattr(self.generator, "set_throttle"):
            self.generator.set_throttle(throttle)

        if self.burning and self.is_starved():
            if not self.starved_warned:
                self.log.level("warn").print(f"[{self.name}] Burning but no oil arrives -- check the oil tank level, the oil_in connection and the Liquid Pipe route.")
                self.starved_warned = True
        else:
            self.starved_warned = False

    def run(self, poll_interval=2.0):
        self.log.print(f"Oil Generator Controller ({self.name}) online. Last-resort mode: burns only below {OIL_START_RESERVE_FRACTION*100:.0f}% reserve with a deficit.")
        validate_game_version()
        while True:
            try:
                self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Oil Generator exception: {error}")
            sleep(poll_interval)
