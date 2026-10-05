import fluid_routing
import power
from hysteresis import HysteresisLatch
from tree_console import TreeConsole
from swallow import swallowed
from script_parking import ParkRequester
from machine_controller import MachineController

# Oil Generator automation: last-resort power, and base load while oil is in
# surplus.
#
# An Oil Generator gives +700 W at throttle 1 for 8 t/h of oil
# (docs/components/oil_generator.md). Oil is valuable (Fabricator recipes use
# it) and burning it emits CO2, so this controller keeps the generator idle
# until both of these are true:
#   - the grid's reserve is low: the BATTERY fraction is below
#     OIL_START_RESERVE_FRACTION, or the combined reserve (battery + banked
#     steam, measured exactly like the Power Guard --
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
# Surplus base load: while the oil tanks network-wide are full
# (fluid_routing.fluid_reserve_fraction("oil") >= OIL_SURPLUS_START_FRACTION,
# until it drops below OIL_SURPLUS_STOP_FRACTION), the wells would otherwise
# stall against full tanks. The generators then burn what the wells deliver
# beyond every other oil consumer (gross inflow = tank change rate + the oil
# generators' own burn, smoothed), plus a correction that steers the tank fill
# to OIL_SURPLUS_TARGET_FRACTION over OIL_SURPLUS_CORRECT_HOURS. Capped at the
# grid's consumption (plus OIL_RECHARGE_W while the battery is below
# OIL_SURPLUS_TOPUP_BELOW) and shared evenly; turbine commitment
# (lib/turbine_commit.py) parks the Steam Turbines this output replaces. The
# last-resort throttle still applies on top: the higher of the two wins.
# No surplus base load on a grid a producing Reactor carries
# (power.reactor_carried()): the oil is worth more to Fabricators there, and
# the idle generator parks. The last resort still burns.
#
# Parking: the script asks to be parked only while neither mode burns and the
# grid has no deficit without oil. With a standing deficit the battery drains
# from the stop line back to the start line within hours, and the panel's wake
# pass can lag that.
#
# No archive state: the game resets the throttle to 0 when the script stops,
# and after a restart the idle->burning check re-triggers within one step if
# the conditions still hold.

OIL_GENERATOR_RATED_W = 700.0

# Hysteresis on the combined reserve fraction. Start sits above the Power
# Guard's tier-1 EMERGENCY_SHED_FRACTIONS[0] (0.10) so oil can catch the grid
# before loads get shed; stop sits above its EMERGENCY_RESTORE_FRACTION
# (0.25) so shed loads are back on before oil burning ends.
OIL_START_RESERVE_FRACTION = 0.30
OIL_STOP_RESERVE_FRACTION = 0.70

# Cover the deficit with a little margin (grid readings lag one power tick),
# and never idle along below this throttle once burning -- a trickle wouldn't
# move the reserve.
OIL_DEFICIT_HEADROOM = 1.1
OIL_MIN_THROTTLE = 0.1

# Grid-wide surplus (W) the burning generators add on top of the deficit so
# the battery actually climbs back to the stop line. Without it the 10%
# headroom alone refills an 11 kWh bank at ~50 W (days of oil burn).
OIL_RECHARGE_W = 300.0

# Surplus base load hysteresis on the network-wide oil tank fill, and the
# battery fill below which it also recharges. The fill is re-read every
# OIL_RESERVE_REFRESH_TICKS (it moves by a few t/h).
OIL_SURPLUS_START_FRACTION = 0.90
OIL_SURPLUS_STOP_FRACTION = 0.70
OIL_SURPLUS_TOPUP_BELOW = 0.98
OIL_RESERVE_REFRESH_TICKS = 100
# Surplus burn rate: tank fill it steers to, the game hours it spreads the
# correction over, and the EMA weight of each new gross-inflow sample (wells
# cycle active/dormant, so single samples swing hard).
OIL_SURPLUS_TARGET_FRACTION = 0.80
OIL_SURPLUS_CORRECT_HOURS = 24.0
OIL_INFLOW_EMA_ALPHA = 0.2
OIL_FULL_BURN_TPH = 8.0  # docs/components/oil_generator.md: 8 t/h at throttle 1
TICKS_PER_GAME_HOUR = 250  # same as wildlife_common.TICKS_PER_GAME_HOUR (tier 9)

# Oil source routing (FluidInputRouter) -- same meaning as
# lib/steam_turbine.py's constants of the same names.
STALL_STREAK_BLACKLIST_THRESHOLD = 5
RESCAN_INTERVAL_TICKS = 150
DISCOVERY_CACHE_INTERVAL_TICKS = 100
NEUTRAL_GRACE_STEPS = 5

OIL_TANK_TYPE_IDS = ("liquid_tank", "bulk_liquid_reservoir")


def _notify(text, level="warn", duration=8.0):
    try:
        notify(text, level=level, duration_seconds=duration)
    except Exception as error:
        swallowed("oil_generator._notify: notify", error)


OIL_POLL_SECONDS = 4.0  # reserve and deficit change over minutes


class OilGeneratorController(MachineController):
    """Burns oil as last-resort power (low combined reserve AND a deficit without oil) or as base load while oil is in surplus."""
    LABEL = "Oil Generator"
    POLL_S = OIL_POLL_SECONDS

    def online_message(self):
        return f"Oil Generator Controller ({self.name}) online. Burns below {OIL_START_RESERVE_FRACTION*100:.0f}% reserve with a deficit, or burns the oil inflow as base load while oil tanks are >= {OIL_SURPLUS_START_FRACTION*100:.0f}% full."

    def next_sleep(self, result, failed):
        # A standing deficit drains the battery back to the start line within hours; stay awake for it.
        self.parker.update(not failed and not (self.burning or self.surplus) and self.deficit <= 0)
        return self.POLL_S

    def __init__(self, generator):
        self.generator = generator
        self.name = getattr(generator, "id", "oil_generator")
        self.parker = ParkRequester(self.name, "oil_generator")
        self.power = get_component("power_control")
        self.log = TreeConsole(module="oil_generator")
        self.burning = False
        self.surplus_latch = HysteresisLatch(OIL_SURPLUS_START_FRACTION, OIL_SURPLUS_STOP_FRACTION)
        self.oil_fill = None
        self.oil_fill_tick = None
        self.oil_tons = None         # (level t, capacity t) at oil_fill_tick
        self.oil_inflow_tph = None   # gross oil inflow EMA, None until two readings
        self.deficit = 0.0           # deficit without oil at the last step
        self.starved_warned = False
        self._router = fluid_routing.FluidInputRouter(
            discover=self._discover_candidates,
            rescan_interval_ticks=RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=DISCOVERY_CACHE_INTERVAL_TICKS,
            stall_streak_threshold=STALL_STREAK_BLACKLIST_THRESHOLD,
            neutral_grace_steps=NEUTRAL_GRACE_STEPS,
            label=f"{self.name}.oil_in",
        )

    # ------------------------------------------------------------------
    # Oil input
    # ------------------------------------------------------------------
    def _discover_candidates(self):
        """Oil-eligible Liquid Tanks / Large Liquid Tanks network-wide, own outpost first, then Oil
        Pumps as a direct fallback (docs/components/oil_generator.md recommends a tank buffer, since
        oil wells go dormant)."""
        own_outpost_id = getattr(getattr(self.generator, "outpost", None), "id", None)
        tiers = [(type_id, "oil") for type_id in OIL_TANK_TYPE_IDS] + [("oil_pump", None)]
        ranked = fluid_routing.discover_ranked(tiers, own_outpost_id)
        self.log.debug(f"[{self.name}] Rediscovered oil sources (tanks first, own outpost '{own_outpost_id}' first): {ranked}.")
        return ranked

    def is_starved(self):
        """True while asked to burn but no oil arrives (no is_stalled() on this building)."""
        try:
            if self.generator.throttle() <= 0:
                return False
            port = self.generator.oil_in
            return port.level() <= 0 and self.generator.oil_consumption() <= 0
        except Exception as error:
            swallowed("oil_generator.OilGeneratorController.is_starved: self.generator.throttle", error)
            return False

    def ensure_input_connection(self):
        """Keeps oil_in on a reachable oil source. A tank has no script, so this generator declares the link."""
        port = getattr(self.generator, "oil_in", None)
        curr_tick = self.get_current_tick()
        fluid_routing.ensure_input_logged(self._router, port, curr_tick, self.is_starved(), self.log, self.name, "oil_in",
                                          "No oil-eligible tank or Oil Pump found network-wide yet (an empty tank needs a fluid_routing.tank_assignments entry for 'oil').")

    # ------------------------------------------------------------------
    # Last-resort decision
    # ------------------------------------------------------------------
    def get_grid(self):
        if self.power and hasattr(self.power, "grid"):
            try:
                return self.power.grid(self.name)
            except Exception as error:
                swallowed("oil_generator.OilGeneratorController.get_grid: self.power.grid", error)
        return None

    def oil_deficit_share(self, grid: "PowerGrid"):
        """(deficit_w, share_w, generator_count, oil_w). deficit_w = consumption minus every NON-oil
        generator's output; share_w is this generator's even share of it; oil_w = the Oil Generators' output."""
        oil_members = [m for m in (getattr(grid, "members", None) or []) if getattr(m, "type_id", "") == "oil_generator"]
        oil_total = sum(getattr(m, "generated", 0.0) or 0.0 for m in oil_members)
        if not any(getattr(m, "id", None) == self.name for m in oil_members):
            # Members missing this generator: fall back to its own reading.
            try:
                oil_total += self.generator.power_output()
            except Exception as error:
                swallowed("oil_generator.OilGeneratorController.oil_deficit_share: self.generator.power_output", error)
            oil_members.append(None)
        base_gen = getattr(grid, "generated", 0.0) - oil_total
        deficit = getattr(grid, "consumed", 0.0) - base_gen
        count = max(1, len(oil_members))
        return deficit, deficit / count, count, oil_total

    def oil_reserve(self, oil_burn_tph=0.0):
        """Network-wide oil tank fill (fluid_routing.fluid_reserve_tons()), re-read every OIL_RESERVE_REFRESH_TICKS.
        Each re-read also updates the gross inflow estimate; oil_burn_tph = the Oil Generators' burn now."""
        now = self.get_current_tick()
        if self.oil_fill_tick is None or not 0 <= now - self.oil_fill_tick < OIL_RESERVE_REFRESH_TICKS:
            tons = fluid_routing.fluid_reserve_tons("oil")
            self.update_inflow(tons, oil_burn_tph, now)
            self.oil_tons = tons
            self.oil_fill = tons[0] / tons[1] if tons else None
            self.oil_fill_tick = now
        return self.oil_fill

    def update_inflow(self, tons, oil_burn_tph, now):
        """Gross oil inflow EMA (t/h): tank change rate since the last re-read plus the Oil Generators' burn,
        so it is what the wells deliver beyond every other oil consumer. A capacity change (tank added or
        removed) skips the sample."""
        prev, prev_tick = self.oil_tons, self.oil_fill_tick
        if not tons or not prev or prev_tick is None or now <= prev_tick or tons[1] != prev[1]:
            return
        hours = (now - prev_tick) / float(TICKS_PER_GAME_HOUR)
        sample = max(0.0, (tons[0] - prev[0]) / hours + oil_burn_tph)
        if self.oil_inflow_tph is None:
            self.oil_inflow_tph = sample
        else:
            self.oil_inflow_tph += OIL_INFLOW_EMA_ALPHA * (sample - self.oil_inflow_tph)
        self.log.debug(f"[{self.name}] Oil inflow sample {sample:.1f} t/h (tanks {prev[0]:.0f} -> {tons[0]:.0f} t over {hours:.2f} h, burn {oil_burn_tph:.1f} t/h), EMA {self.oil_inflow_tph:.1f} t/h.")

    @property
    def surplus(self):
        return self.surplus_latch.active

    @surplus.setter
    def surplus(self, on):
        self.surplus_latch.active = on

    def update_surplus(self, oil):
        """Surplus hysteresis: on at OIL_SURPLUS_START_FRACTION, off below OIL_SURPLUS_STOP_FRACTION or with no oil tank."""
        flip = self.surplus_latch.update(oil)
        if flip:
            oil_str = f"{oil*100:.0f}%" if oil is not None else "n/a"
            if flip == "on":
                self.log.print(f"[{self.name}] Oil surplus base load ON -- oil tanks {oil_str} (>= {OIL_SURPLUS_START_FRACTION*100:.0f}%).")
            else:
                self.log.print(f"[{self.name}] Oil surplus base load OFF -- oil tanks {oil_str} (stop below {OIL_SURPLUS_STOP_FRACTION*100:.0f}%).")
        return self.surplus

    def surplus_throttle(self, grid: "PowerGrid", battery, count):
        """Throttle that burns the gross oil inflow plus a correction toward OIL_SURPLUS_TARGET_FRACTION,
        capped at the grid's consumption (+ recharge below OIL_SURPLUS_TOPUP_BELOW), shared over count."""
        recharge = OIL_RECHARGE_W if battery is not None and battery < OIL_SURPLUS_TOPUP_BELOW else 0.0
        cap_w = max(0.0, getattr(grid, "consumed", 0.0) or 0.0) + recharge
        level, capacity = self.oil_tons or (0.0, 0.0)
        correction = (level - OIL_SURPLUS_TARGET_FRACTION * capacity) / OIL_SURPLUS_CORRECT_HOURS
        burn_tph = max(0.0, (self.oil_inflow_tph or 0.0) + correction)
        target_w = min(cap_w, burn_tph / OIL_FULL_BURN_TPH * OIL_GENERATOR_RATED_W) / count
        throttle = min(1.0, target_w / OIL_GENERATOR_RATED_W)
        if self.log.verbose:
            self.log.trace(
                f"Surplus base load: inflow {self.oil_inflow_tph or 0.0:.1f} t/h + correction {correction:.1f} t/h = {burn_tph:.1f} t/h, "
                f"cap {cap_w:.0f} W, {target_w:.0f} W each over {count} generator(s) -> throttle {throttle:.2f}."
            )
        return throttle

    def choose_throttle(self):
        self.log.start(f"[{self.name}] choose_throttle", level="debug")
        grid = self.get_grid()
        if not grid:
            if self.burning:
                self.log.level("warn").print(f"[{self.name}] Grid unreadable -- stopping oil burn (fail safe).")
                self.burning = False
            self.log.debug("No grid for this generator; throttle 0.")
            self.log.end()
            return 0.0

        now = power.measure_grid(grid)
        reserve = power.reserve_fraction(now)
        battery = now["bat_wh"] / now["bat_cap"] if now["bat_cap"] > 0 else None
        deficit, share, count, oil_w = self.oil_deficit_share(grid)
        self.deficit = deficit
        reserve_str = f"{reserve*100:.1f}%" if reserve is not None else "n/a (no storage)"
        battery_str = f"{battery*100:.1f}%" if battery is not None else "n/a (no battery)"
        if self.log.verbose:
            self.log.trace(
                f"[{self.name}] Battery {battery_str}, combined reserve {reserve_str} [battery {now['bat_wh']:.0f}/{now['bat_cap']:.0f} Wh, steam {now['steam_t']:.0f}/{now['steam_cap']:.0f} t], "
                f"deficit without oil {deficit:.0f} W, share {share:.0f} W over {count} oil generator(s), burning={self.burning}."
            )

        oil_burn_tph = max(0.0, oil_w) / OIL_GENERATOR_RATED_W * OIL_FULL_BURN_TPH
        if power.reactor_carried(grid):
            if self.surplus:
                self.log.print(f"[{self.name}] Oil surplus base load OFF -- a Reactor carries this grid.")
                self.surplus = False
            surplus = 0.0
        else:
            surplus = self.surplus_throttle(grid, battery, count) if self.update_surplus(self.oil_reserve(oil_burn_tph)) else 0.0
        resort = self.last_resort_throttle(battery, reserve, deficit, share, count)
        self.log.end()
        return max(surplus, resort)

    def last_resort_throttle(self, battery, reserve, deficit, share, count):
        """Last-resort hysteresis (start below OIL_START_RESERVE_FRACTION with a deficit, stop once
        battery and combined reserve reach OIL_STOP_RESERVE_FRACTION); its throttle, 0 while not burning."""
        reserve_str = f"{reserve*100:.1f}%" if reserve is not None else "n/a (no storage)"
        battery_str = f"{battery*100:.1f}%" if battery is not None else "n/a (no battery)"
        fractions = [f for f in (battery, reserve) if f is not None]
        if not self.burning:
            low = not fractions or min(fractions) < OIL_START_RESERVE_FRACTION
            if not (low and deficit > 0):
                if self.log.verbose:
                    self.log.trace(f"Last resort idle: reserve_low={low} (battery {battery_str}, combined {reserve_str}), deficit={deficit:.0f} W.")
                return 0.0
            self.burning = True
            msg = f"Oil Generator '{self.name}' burning oil: battery {battery_str}, combined reserve {reserve_str}, deficit {deficit:.0f} W. Emits CO2."
            self.log.level("warn").print(
                f"[{self.name}] Last resort ON -- battery {battery_str} / combined {reserve_str}, lowest < {OIL_START_RESERVE_FRACTION*100:.0f}%, deficit {deficit:.0f} W."
            )
            _notify(f"[Power] {msg}")
        else:
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
        if self.log.verbose:
            self.log.trace(
                f"Burning: share {share:.0f} W x{OIL_DEFICIT_HEADROOM} + recharge {recharge_share:.0f} W = {target_w:.0f} W / {OIL_GENERATOR_RATED_W:.0f} W -> throttle {throttle:.2f}."
            )
        return throttle

    def step(self):
        self.ensure_input_connection()
        throttle = self.choose_throttle()
        if hasattr(self.generator, "set_throttle"):
            self.generator.set_throttle(throttle)

        if (self.burning or self.surplus) and self.is_starved():
            if not self.starved_warned:
                self.log.level("warn").print(f"[{self.name}] Burning but no oil arrives -- check the oil tank level, the oil_in connection and the Liquid Pipe route.")
                self.starved_warned = True
        else:
            self.starved_warned = False
