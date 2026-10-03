# Fuel Assembler automation (10_nuclear): Fuel Rods for the local Reactors,
# then Nuclear Batteries for open orders. See lib/fuel_assembler.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import fuel_assembler as self

from fuel_assembler import FuelAssemblerController

FuelAssemblerController(self).run()
