# Shared Thermal Cap automation: keep the vent's steam chamber from
# overpressurizing (which blows the whole chamber to atmosphere, losing
# everything banked -- see docs/components/thermal_cap.md .is_overpressured()).
# The job is purely reactive: open the release valve (steam_out) proportional
# to how close pressure() is to the 1.0 ceiling, and fall back to the relief
# valve (dumping to atmosphere) only when a downstream jam (full Gas Tank,
# stalled Steam Turbine, disconnected pipe) means the release valve alone
# can't keep up even wide open.

# Pressure bands for the release-valve throttle -- proportional control, not
# on/off, so the valve doesn't hunt between fully open/closed every tick.
# Kept intentionally cautious (opens well before the 1.0 overpressure ceiling)
# since blowing the chamber loses everything banked, while over-releasing
# just costs a bit of downstream buffer headroom.
PRESSURE_BAND_CRITICAL = 0.90   # throttle 1.0 (wide open)
PRESSURE_BAND_HIGH = 0.60       # throttle 0.6
PRESSURE_BAND_MODERATE = 0.30   # throttle 0.3
THROTTLE_TRICKLE = 0.1          # below PRESSURE_BAND_MODERATE: gentle trickle,
                                 # keeps the pipe/downstream buffer topped up
                                 # without needlessly draining banked steam

# Relief valve only opens once the release valve is already wide open and
# still can't prevent pressure climbing past this point -- a small relief
# bleed is far cheaper than an overpressure blowoff (which dumps the entire
# chamber, not just the surplus).
PRESSURE_RELIEF_THRESHOLD = 0.95

# Once the currently-targeted Gas Tank crosses this fill fraction, switch
# steam_out to whichever other known tank is currently least full, so several
# tanks fill roughly evenly instead of one saturating while others sit empty.
GAS_TANK_REBALANCE_FILL_FRACTION = 0.85

# A target blacklisted as unreachable might become reachable later (the
# player builds a new Gas Pipe route to it) -- clear the blacklist this often
# so it gets a fresh chance without waiting for every other candidate to also
# go bad first. Counts step() calls, not real time -- with the default
# poll_interval=1.0s that's roughly 5 minutes.
RESCAN_INTERVAL_TICKS = 300


def discover_network_building_ids(type_id):
    """
    All building ids of type_id across every known outpost. A Thermal Cap has
    no .outpost of its own (built directly on a thermal vent out in the
    field, not necessarily inside a founded outpost -- unlike Gas Tank/Steam
    Turbine, docs/components/thermal_cap.md lists no .outpost property at
    all), so candidate Gas Tanks must be discovered network-wide rather than
    scoped to "this building's outpost". Physical Gas Pipe topology (not
    outpost membership) ultimately decides which candidates actually succeed
    via connect() -- this only gathers ids to try.
    """
    ids = []
    network = get_component("outpost_network")
    if network and hasattr(network, "outposts"):
        try:
            for outpost in network.outposts():
                for building in outpost.buildings(type_id):
                    b_id = getattr(building, "id", None)
                    if b_id:
                        ids.append(b_id)
        except Exception:
            pass
    return ids


def _fill_pct_of(building_id):
    """fill_pct() of a Gas Tank by id, or 1.0 (treated as "full, deprioritize") if unreadable."""
    try:
        building = get_component(building_id)
    except Exception:
        return 1.0
    if not building or not hasattr(building, "fill_pct"):
        return 1.0
    try:
        return building.fill_pct()
    except Exception:
        return 1.0


class ThermalCapController:
    """Keeps a Thermal Cap's chamber pressure off the overpressure ceiling."""

    def __init__(self, cap):
        self.cap = cap
        self.name = getattr(cap, "id", "thermal_cap")
        self.last_phase = None
        # connect()'s "ok" status only means the pairing was logically
        # accepted -- docs/guide/infrastructure_and_pipes.md is explicit that
        # a remote target needs a *completed* Gas Pipe route, which connect()
        # never checks. is_stalled() is the only live signal that a target
        # isn't actually reachable, so unreachable targets get blacklisted --
        # but only until the next periodic rescan (see RESCAN_INTERVAL_TICKS),
        # since a newly built pipe can make a blacklisted target reachable.
        self.unreachable_targets = set()
        self.ticks_since_rescan = 0

    def ensure_output_connection(self):
        """
        Declares/rebalances steam_out's destination among known Gas Tanks
        (discovered network-wide -- see discover_network_building_ids()).
        A Gas Tank has no script of its own (purely passive -- see
        docs/components/gas_tank.md), so nothing ever calls connect() on its
        side of the pipe; this Cap's own script must declare the link, and
        steam_out only ever holds one destination at a time (per
        docs/components/thermal_cap.md), so serving several tanks means
        periodically re-pointing it rather than a simultaneous fan-out.

        Steam Turbines (and any other scripted consumer) are deliberately
        NOT a target here: docs/guide/infrastructure_and_pipes.md's Thermal
        Vents section describes the opposite direction for those -- "additional
        consumers may connect their own steam_in ports to this Cap" -- so a
        Turbine's own script (see lib/steam_turbine.py) independently pulls
        from this Cap regardless of whatever steam_out is currently pointed
        at, no coordination needed here.
        """
        port = getattr(self.cap, "steam_out", None)
        if not port or not hasattr(port, "connect"):
            return

        # Periodic rescan: give blacklisted targets a fresh chance in case a
        # new Gas Pipe route was built since they were marked unreachable.
        # This never disconnects a currently working target -- it only
        # widens the candidate pool for the next time a switch is warranted.
        self.ticks_since_rescan += 1
        if self.ticks_since_rescan >= RESCAN_INTERVAL_TICKS:
            self.ticks_since_rescan = 0
            if self.unreachable_targets:
                print(f"[{self.name}] Periodic rescan: clearing {len(self.unreachable_targets)} blacklisted target(s) to retry.")
                self.unreachable_targets.clear()

        current_id = None
        try:
            current_id = port.connected_to() if hasattr(port, "connected_to") else None
        except Exception:
            pass

        # A stalled cap with an open throttle and steam available means the
        # currently connected target can't actually be reached by pipe --
        # connect() never verified that, it only accepted the pairing.
        # Blacklist it and force a reselect below rather than sitting stalled
        # on the same bad target forever.
        is_stalled = False
        if hasattr(self.cap, "is_stalled"):
            try:
                is_stalled = self.cap.is_stalled()
            except Exception:
                is_stalled = False
        if is_stalled and current_id and current_id not in self.unreachable_targets:
            self.unreachable_targets.add(current_id)
            print(f"[{self.name}] '{current_id}' reported stalled (steam available, valve open, nothing transferred) -- likely no completed Gas Pipe route. Blacklisting and picking a different target.")
            current_id = None

        tank_ids = [t for t in discover_network_building_ids("gas_tank") if t not in self.unreachable_targets]
        if not tank_ids:
            # Every known tank is blacklisted (or none exist) -- give
            # blacklisted ones a fresh chance rather than sitting dead
            # forever if e.g. a pipe route gets completed later.
            tank_ids = discover_network_building_ids("gas_tank")
            if tank_ids and self.unreachable_targets:
                print(f"[{self.name}] Every known Gas Tank was blacklisted; clearing the list to retry.")
                self.unreachable_targets.clear()
        if not tank_ids:
            if not current_id:
                print(f"[{self.name}] No Gas Tank found network-wide yet; steam_out has no destination.")
            return

        if current_id in tank_ids and _fill_pct_of(current_id) < GAS_TANK_REBALANCE_FILL_FRACTION:
            return  # current target still has headroom, keep it

        # Try the least-full known tank first (load-balances across several),
        # falling through to the next since not every tank id is necessarily
        # physically pipe-reachable from this Cap's field location.
        for tank_id in sorted(tank_ids, key=_fill_pct_of):
            if tank_id == current_id:
                continue
            try:
                res = port.connect(tank_id)
            except Exception:
                continue
            if res.status == "ok":
                print(f"[{self.name}] Connected steam_out -> '{tank_id}' ({_fill_pct_of(tank_id)*100:.0f}% full).")
                return
            elif res.status != "busy":
                print(f"[{self.name}] steam_out connect notice for '{tank_id}': {res.status} - {res.message}")

    def release_throttle_for_pressure(self, pressure):
        """Proportional release-valve setting for the given chamber pressure."""
        if pressure >= PRESSURE_BAND_CRITICAL:
            return 1.0
        if pressure >= PRESSURE_BAND_HIGH:
            return 0.6
        if pressure >= PRESSURE_BAND_MODERATE:
            return 0.3
        return THROTTLE_TRICKLE

    def step(self):
        self.ensure_output_connection()

        phase = self.cap.phase() if hasattr(self.cap, "phase") else None
        if phase != self.last_phase and phase is not None:
            print(f"[{self.name}] Vent phase changed: {self.last_phase} -> {phase}.")
            self.last_phase = phase

        pressure = self.cap.pressure() if hasattr(self.cap, "pressure") else 0.0

        throttle = self.release_throttle_for_pressure(pressure)
        if hasattr(self.cap, "set_throttle"):
            self.cap.set_throttle(throttle)

        # Relief valve: only engage once the release valve is already wide
        # open (throttle == 1.0) and pressure is still climbing toward the
        # ceiling -- a downstream jam (full Gas Tank, stalled Turbine,
        # disconnected pipe) that steam_out alone can't route around.
        if hasattr(self.cap, "set_relief"):
            if throttle >= 1.0 and pressure >= PRESSURE_RELIEF_THRESHOLD:
                relief = min(1.0, (pressure - PRESSURE_RELIEF_THRESHOLD) / (1.0 - PRESSURE_RELIEF_THRESHOLD))
                self.cap.set_relief(relief)
                if relief > 0:
                    print(f"[{self.name}] Downstream can't keep up at {pressure*100:.0f}% pressure; venting {relief*100:.0f}% to atmosphere to avoid an overpressure blowoff.")
            else:
                self.cap.set_relief(0.0)

        if hasattr(self.cap, "is_stalled") and self.cap.is_stalled():
            print(f"[{self.name}] Stalled: release valve open with steam available but nothing downstream is accepting it. Check steam_out connection / Gas Tank / Steam Turbine.")

        if hasattr(self.cap, "is_overpressured") and self.cap.is_overpressured():
            print(f"[{self.name}] WARNING: Chamber overpressured -- banked steam was lost to atmosphere. Releasing sooner next cycle.")
            try:
                notify(f"[{self.name}] Thermal Cap overpressured; banked steam lost.", level="warn", duration_seconds=8.0)
            except Exception:
                pass

    def run(self, poll_interval=1.0):
        print(f"Thermal Cap Controller ({self.name}) online. Guarding against overpressure.")
        while True:
            try:
                self.step()
            except Exception as error:
                print(f"[{self.name}] Thermal Cap exception: {error}")
            sleep(poll_interval)
