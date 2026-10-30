"""Test helper: a real VehicleController on a stub Pioneer with a scripted NavModule.

Used by the vehicle energy and navigation boundary tests. No charging station is
built, so charging_stations.nearest() falls back to the home slot at (0, 0):
every return leg ends there.
"""

from game_stubs import Pioneer, Position, Result
from vehicle import VehicleController


class ScriptedNav:
    """Pioneer NavModule at (x, y); advance() moves it `step` metres along +x (a test calls it per drive poll)."""

    def __init__(self, x=0.0, y=0.0, step=0.0):
        self.x = x
        self.y = y
        self.step = step
        self.throttles = []
        self.brakes = 0

    def advance(self):
        self.x += self.step

    def get_position(self):
        return Position(self.x, self.y)

    def set_target(self, _x, _y):
        return Result("ok")

    def set_throttle(self, throttle):
        self.throttles.append(throttle)
        return Result("ok")

    def brake(self):
        self.brakes += 1
        return Result("ok")

    def get_distance_to(self, x, y):
        return ((self.x - x) ** 2 + (self.y - y) ** 2) ** 0.5


def make_vehicle(world, battery_wh=1000.0, cargo_capacity=100, nav=None) -> tuple[VehicleController, Pioneer]:
    """A VehicleController built by its real __init__ over a home-based stub Pioneer (returned too)."""
    pioneer = world.add_pioneer(
        "pioneer_1", battery_wh=battery_wh, battery_capacity=max(battery_wh, 1.0), cargo_capacity=cargo_capacity
    )
    pioneer.nav = nav or ScriptedNav()
    return VehicleController(pioneer), pioneer  # type: ignore[arg-type]  # stub Pioneer stands in for the game's
