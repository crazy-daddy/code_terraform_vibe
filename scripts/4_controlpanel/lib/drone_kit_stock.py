# Standing order for drone infrastructure kits: once a Drone Depot or Drone
# Service Station kit recipe is unlocked (Earth Orders helios_06 / spire_10,
# docs/gameknowledge/unlock_paths.md "Drone path"), keep one kit of each in
# stock while some outpost still has none of that building. The building
# planner (autoplay/lib/building_plan.py) only proposes deploys from kits it
# can have; this makes sure one is ready. A kit in stock meets the floor, so
# at most one waits per kind; the next is built once it is deployed and an
# outpost still lacks one.
#
# Depot: the first unlocked tier (building_plan._pick() proposes the first
# alternative too); fleet_upgrade.py steps standing Depots up later.

import components
from item_tiers import DEPOT_KIT_TIERS, DEPOT_TYPE_TIERS
from production import SourceCache, discover_building_ids, fabricator_unlocked_outputs, order_levels, set_order

# Order-book requester (production_orders.STANDING_ORDER_REQUESTERS).
REQUESTER = "drone_kit_stock"
SERVICE_TYPE_ID = "drone_service_station"
SERVICE_KIT_ID = "drone_service_station_kit"


def _lacks(outposts, type_ids):
    """True when some outpost has no building of any of type_ids."""
    return any(not any(discover_building_ids(t, outpost) for t in type_ids) for outpost in outposts)


def wanted_kits(outposts, unlocked):
    """{kit_id: 1} for each unlocked kit kind some outpost lacks."""
    wanted = {}
    depot_kit = next((k for k in DEPOT_KIT_TIERS if k in unlocked), None)
    if depot_kit and _lacks(outposts, DEPOT_TYPE_TIERS):
        wanted[depot_kit] = 1
    if SERVICE_KIT_ID in unlocked and _lacks(outposts, (SERVICE_TYPE_ID,)):
        wanted[SERVICE_KIT_ID] = 1
    return wanted


def publish_drone_kit_order(cache: "SourceCache"):
    """Writes wanted_kits() as REQUESTER's order (no write when unchanged)."""
    outposts = components.outposts()
    if not outposts:
        return
    wanted = wanted_kits(outposts, fabricator_unlocked_outputs(cache))
    set_order(REQUESTER, {kit: order_levels(need=qty) for kit, qty in wanted.items()})
