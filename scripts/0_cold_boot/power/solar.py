# Self-contained early Solar Generator script (no lib/ imports)
# Pure sun-tracking: tilts the panel to follow elevation. No building-buyer,
# no research gating, no shop/computer access - just keeps this panel's
# tilt optimal so it doesn't need the shared_library-tier SolarController yet.

clock = get_component("clock")

while True:
    elev = clock.get_elevation()
    tilt = max(0, min(90, 90 - elev))
    self.set_tilt(tilt)
    sleep(2.0)
