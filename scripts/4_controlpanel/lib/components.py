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
returns None, keeping get_component()'s per-name types. start_script() and
set_powered() wrap run_control.start() and power_control.set_powered() the
same way, for callers that need nothing else from script parking.
"""

from typing import TYPE_CHECKING

from swallow import swallowed

if TYPE_CHECKING:
    from user_stubs import BatteryComponent, ChargingStation, DroneLarge, DroneMedium, DroneServiceStation, DroneSmall, DroneStation, DroneStationLarge, DroneStationMedium, GasTank, LargeWarehouse, LiquidTank, MiningDrill, MiningDrillHeavy, MiningDrillIndustrial, OilPump, OutpostComponent, Fabricator, Smelter, SteamTurbine, SupplyDock, Warehouse, WaterPump, WeatherStation  # fmt: skip
    from tree_console import TreeConsole


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


def _component(component_id, where="components.component"):
    try:
        return get_component(component_id)
    except Exception as error:
        swallowed(f"{where}: get_component", error)
        return None


if TYPE_CHECKING:
    component = get_component
else:
    component = _component


def home_outpost() -> "OutpostRef | None":
    """Home OutpostRef: outpost_network.home(), else the outposts() entry flagged
    is_home; None when unreadable."""
    network = component("outpost_network")
    if network is None:
        return None
    try:
        home = network.home()
    except Exception as error:
        swallowed("components.home_outpost: network.home", error)
        home = None
    if home is not None:
        return home
    try:
        return next((o for o in network.outposts() if getattr(o, "is_home", False)), None)
    except Exception as error:
        swallowed("components.home_outpost: network.outposts", error)
        return None


def outposts() -> "list[OutpostRef]":
    """Every owned OutpostRef (outpost_network.outposts()); [] when the network
    is missing or the call raises."""
    network = component("outpost_network")
    if network is None:
        return []
    try:
        return list(network.outposts())
    except Exception as error:
        swallowed("components.outposts: network.outposts", error)
        return []


def outpost_by_id(outpost_id) -> "OutpostRef | None":
    """The outposts() entry with this id; None when there is none."""
    return next((o for o in outposts() if getattr(o, "id", None) == outpost_id), None)


def building_ids_at(outpost, type_id, where="components.building_ids_at: outpost.buildings") -> "list[str]":
    """Sorted ids of the type_id buildings at outpost, empty ids dropped. Unmemoized
    (fresh right after a deploy). [] for no outpost or a raised walk (swallowed under `where`)."""
    if outpost is None:
        return []
    try:
        return sorted(i for i in (getattr(ref, "id", "") for ref in outpost.buildings(type_id)) if i)
    except Exception as error:
        swallowed(where, error)
        return []


def building_type_counts(outpost, where="components.building_type_counts: outpost.buildings") -> "dict[str, int]":
    """{type_id: count} over one unfiltered outpost.buildings() walk. {} for a raised walk
    (swallowed under `where`)."""
    counts: dict[str, int] = {}
    try:
        for building in outpost.buildings() or []:
            type_id = getattr(building, "type_id", "")
            counts[type_id] = counts.get(type_id, 0) + 1
    except Exception as error:
        swallowed(where, error)
        return {}
    return counts


def components_at(outpost, type_id, where="components.components_at: outpost.buildings") -> list:
    """The resolved components of the type_id buildings at outpost, unresolved ones
    dropped. [] for no outpost or a raised walk (swallowed under `where`)."""
    if outpost is None:
        return []
    try:
        refs = outpost.buildings(type_id)
    except Exception as error:
        swallowed(where, error)
        return []
    found = (get_component(getattr(ref, "id", "")) for ref in refs or [])
    return [c for c in found if c is not None]


def sensor_value(sensor_id, where) -> "float | None":
    """float(sensor.get_value()); None when there is no such sensor or the read raises
    (swallowed under `where`)."""
    try:
        sensor = get_component(sensor_id)
        return float(sensor.get_value()) if sensor else None
    except Exception as error:
        swallowed(where, error)
        return None


def home_outpost_id():
    """Id of home_outpost(); None when unreadable."""
    return getattr(home_outpost(), "id", None)


def research_unlocked(research_id, where="components.research_unlocked"):
    """research.is_unlocked(research_id); False when the component is missing
    or the call raises (swallowed under `where`)."""
    research = component("research")
    if research is None:
        return False
    try:
        return bool(research.is_unlocked(research_id))
    except Exception as error:
        swallowed(where, error)
        return False


def all_research_unlocked(research_ids, where="components.all_research_unlocked"):
    """True when every id in research_ids is unlocked; False for an empty list."""
    return bool(research_ids) and all(research_unlocked(research_id, where) for research_id in research_ids)


def machine_tier(machine_id):
    """Installed Mk tier of a deployed machine, 1 when unreadable."""
    machine = component(machine_id)
    try:
        return int(machine.tier()) if machine else 1
    except Exception as error:
        swallowed("components.machine_tier: machine.tier", error)
        return 1


def start_script(machine_id):
    """run_control.start(machine_id), treating already_running as success.
    Returns "ok", the refusal status, "no_run_control" or "error: <exception>"."""
    try:
        run = get_component("run_control")
    except Exception as error:
        swallowed("components.start_script: get_component", error)
        run = None
    if not run:
        return "no_run_control"
    try:
        res = run.start(machine_id)
    except Exception as error:
        swallowed("components.start_script: run.start", error)
        return f"error: {error}"
    return "ok" if res.status in ("ok", "already_running") else res.status


def set_powered(power: "PowerControl | None", machine_id, on, log: "TreeConsole"):
    """power_control.set_powered(machine_id, on); True on "ok". A refusal is
    logged at debug on log, an exception goes to swallowed()."""
    if power is None:
        return False
    try:
        result = power.set_powered(machine_id, on)
    except Exception as error:
        swallowed("components.set_powered: power.set_powered", error)
        return False
    status = getattr(result, "status", "")
    if status != "ok":
        log.debug(f"set_powered({machine_id}, {on}) -> {status}")
    return status == "ok"
