# Self-contained early Pressure Generator controller (no lib/ imports)
# Hits the resonance window (next_window_low <= gauge <= next_window_high) for +25% efficiency

synced = False
last_g = -1.0

while True:
    g = self.gauge()
    lo = self.next_window_low()
    hi = self.next_window_high()

    if last_g >= 0 and g < last_g:
        # Gauge sweep wrapped
        synced = False
    last_g = g

    if not synced and g >= lo and g <= hi:
        self.sync()
        synced = True

    sleep(0.05)

