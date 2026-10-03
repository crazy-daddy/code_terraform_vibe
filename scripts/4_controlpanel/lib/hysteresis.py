# Two-threshold on/off latch for gates that must not flap on a single line:
# the Mk III heater's steam guard (lib/terraforming.py), the Steam Condenser's
# steam and water gates, the Oil Generator's surplus base load and the
# Reactors' water reserve. Callers keep their own log lines and side effects;
# the latch only decides when the state flips.


class HysteresisLatch:
    """
    On/off state with separate switch-on and switch-off thresholds.

    on_above=True: switches on at value >= on_at, stays on while value >= off_at
    (off_at <= on_at). on_above=False: switches on at value < on_at, stays on
    while value < off_at (off_at >= on_at).

    unknown: the state an unreadable value (None) forces, or None to keep the
    current state. The state lives in memory only: a breaker-parked or shed
    script keeps it (the breaker pauses the script), a restarted one starts at
    `active`.
    """

    def __init__(self, on_at, off_at, on_above=True, unknown=False, active=False):
        self.on_at = on_at
        self.off_at = off_at
        self.on_above = on_above
        self.unknown = unknown
        self.active = active

    def update(self, value, on_at=None, off_at=None):
        """Feeds one reading; on_at/off_at override the thresholds for this call (thresholds that
        move with capacity). Returns "on" or "off" when the state flips, else None."""
        on_at = self.on_at if on_at is None else on_at
        off_at = self.off_at if off_at is None else off_at
        if value is None:
            want = self.active if self.unknown is None else self.unknown
        else:
            line = off_at if self.active else on_at
            want = value >= line if self.on_above else value < line
        if want == self.active:
            return None
        self.active = want
        return "on" if want else "off"
