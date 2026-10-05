"""Typed component lookups.

get_component() is typed by name only for the fixed ids in the game stubs
("clock", "shop", ...). Any other id -- a building ref's .id, an id from the
archive or a function argument -- gives `Component | None` for a `str` id
and Unknown for an untyped one. Unknown switches off every check on the
component, so a typo'd method is only found at runtime, usually behind a
swallowed() fallback.

Each accessor here names the component kind the caller expects, so Pyright
checks the calls on it and the editor completes them:

    from components import tank

    t = tank(tank_id)
    if t is None:
        continue
    level = t.level()

The `type: ignore`s live here and nowhere else. The accessors don't check
the kind at runtime: a wrong id still returns whatever component it names.
A class used here must be exported by the typed-self block of user_stubs.py
(COMPONENT_EXPORTS in devtools/self_typing.py).

component() is get_component() that swallows a raised lookup error and
returns None, keeping get_component()'s per-name types.
"""
from typing import TYPE_CHECKING

from swallow import swallowed

if TYPE_CHECKING:
    from user_stubs import BatteryComponent, ChargingStation, DroneLarge, DroneMedium, DroneServiceStation, DroneSmall, DroneStation, DroneStationLarge, DroneStationMedium, GasTank, LargeWarehouse, LiquidTank, MiningDrill, MiningDrillHeavy, MiningDrillIndustrial, OilPump, OutpostComponent, Fabricator, Smelter, SteamTurbine, SupplyDock, Warehouse, WaterPump, WeatherStation


def battery(component_id) -> "BatteryComponent | None":
    return get_component(component_id)  # type: ignore[return-value]


def charging_station(component_id) -> "ChargingStation | None":
    return get_component(component_id)  # type: ignore[return-value]


def drone(component_id) -> "DroneSmall | DroneMedium | DroneLarge | None":
    return get_component(component_id)  # type: ignore[return-value]


def drone_service_station(component_id) -> "DroneServiceStation | None":
    return get_component(component_id)  # type: ignore[return-value]


def drone_station(component_id) -> "DroneStation | DroneStationMedium | DroneStationLarge | None":
    return get_component(component_id)  # type: ignore[return-value]


def fabricator(component_id) -> "Fabricator | None":
    return get_component(component_id)  # type: ignore[return-value]


def gas_tank(component_id) -> "GasTank | None":
    return get_component(component_id)  # type: ignore[return-value]


def tank(component_id) -> "GasTank | LiquidTank | None":
    return get_component(component_id)  # type: ignore[return-value]


def mining_drill(component_id) -> "MiningDrill | MiningDrillIndustrial | MiningDrillHeavy | None":
    return get_component(component_id)  # type: ignore[return-value]


def oil_pump(component_id) -> "OilPump | None":
    return get_component(component_id)  # type: ignore[return-value]


def outpost(component_id) -> "OutpostComponent | None":
    return get_component(component_id)  # type: ignore[return-value]


def smelter(component_id) -> "Smelter | None":
    return get_component(component_id)  # type: ignore[return-value]


def steam_turbine(component_id) -> "SteamTurbine | None":
    return get_component(component_id)  # type: ignore[return-value]


def supply_dock(component_id) -> "SupplyDock | None":
    return get_component(component_id)  # type: ignore[return-value]


def warehouse(component_id) -> "Warehouse | LargeWarehouse | None":
    return get_component(component_id)  # type: ignore[return-value]


def water_pump(component_id) -> "WaterPump | None":
    return get_component(component_id)  # type: ignore[return-value]


def weather_station(component_id) -> "WeatherStation | None":
    return get_component(component_id)  # type: ignore[return-value]


def _component(component_id):
    try:
        return get_component(component_id)
    except Exception as error:
        swallowed("components.component: get_component", error)
        return None


if TYPE_CHECKING:
    component = get_component
else:
    component = _component
