# Oxygen Sensor Diagnostic Script
# Let's inspect the raw value from the sensor.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import oxygen_sensor as self

raw_val = self.get_value()
self.calibrate(raw_val * 100)