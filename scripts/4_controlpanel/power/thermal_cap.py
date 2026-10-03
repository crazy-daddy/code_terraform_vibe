# Thermal Cap automation: keep chamber pressure off the overpressure ceiling.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import thermal_cap as self

from thermal_cap import ThermalCapController

controller = ThermalCapController(self)
controller.run()
