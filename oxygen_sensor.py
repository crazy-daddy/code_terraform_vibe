# Oxygen Sensor Diagnostic Script
# Let's inspect the raw value from the sensor.
raw_val = self.get_value()
self.calibrate(raw_val * 100)