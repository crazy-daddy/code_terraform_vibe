# Shared production-demand planning for mining and refining automation.
#
# The implementation is split by concern into focused modules; this module
# re-exports their public API and stays the single import point for every
# caller (`from production import ...`):
#   - production_core.py: craft timing, memoized building discovery, site ids, shared `log`
#   - production_docks.py: Supply Dock orders, units still owed, where each is consumed
#   - production_fluids.py: fluid source types, buffer-tank latch rule, can_source_fluid()
#   - production_source.py: SourceCache, can_source_item(), can_fulfill_order()
#   - production_orders.py: archive order books (stock targets, manual, transit, upgrade, backlog)
#   - production_cascade.py: recipe index, demand cascades, network-wide Fabricator targets
#   - production_sites.py: per-fab-site targets, site plan split, ship-before-craft, active recipe
#   - production_demand.py: material/Smelter demand, fab-site ingot buffer, raw-ore reasons
#
# Module state (memos, TTL constants, `log`) lives in the defining module:
# patch or reset it there, not through this facade.
from production_core import AFTERMATHS_KEY, claim_site_id, FABRICATOR_WANTS_KEY, fabricator_wants_for, WANTS_REFRESH_TICKS, WANTS_STALE_TICKS, construction_site_id, craft_prefill_units, craft_seconds, discover_building_ids, discover_fabricator_ids, discover_smelter_ids, discover_supply_dock_ids, DISCOVERY_TTL_TICKS, FABRICATOR_TYPE_ID, FUEL_ASSEMBLER_OUTPUTS, FUEL_ASSEMBLER_TYPE_ID, home_outpost_id, INPUT_PREFILL_SECONDS, log, machine_outpost_id, SECONDS_PER_GAME_HOUR, site_recipe_claims, smelter_ores, SMELTER_TYPE_ID, SUPPLY_DOCK_TYPE_ID
from production_docks import dock_owed_at, dock_remaining_requirements, find_dock_order_requiring, _all_dock_orders, _dock_order_remaining
from production_fluids import BUFFER_FLUID_TYPE_IDS, can_source_fluid, discover_fluid_sources, fluid_building_is_viable, FLUID_LATCH_IDS, FLUID_SOURCE_TYPE_IDS
from production_source import can_fulfill_order, can_source_item, SourceCache
from production_orders import BACKLOG_ORDERS_KEY, consume_manual_order, DEFAULT_FABRICATOR_STOCK_TARGETS, FABRICATOR_STOCK_TARGETS_KEY, get_backlog_orders, get_fabricator_stock_targets, get_manual_orders, get_upgrade_orders, MANUAL_ORDERS_KEY, MANUAL_TRANSIT_KEY, manual_transit_wants, reconcile_manual_transit, RECURRING_ORDER_REQUESTERS, set_backlog_order, set_upgrade_order, SITE_ORDER_REQUESTERS, STANDING_ORDER_REQUESTERS, UPGRADE_ORDERS_KEY
from production_cascade import blueprint_demand_items, dock_delivery_targets, blueprint_required_items, fabricator_root_targets, fabricator_unlocked_outputs, get_construction_material_reservations, get_fabricator_targets, get_manual_order_blocking_items, RECIPE_INDEX_TTL_TICKS, _recipe_inputs_for
from production_sites import default_root_sites, fab_site_counts, fab_site_gross_need, get_fabricator_active_recipe, get_fabricator_pipeline, get_fabricator_worker_count, get_fabricator_worker_ids, get_site_fabricator_targets, get_site_ship_plan, local_make_seconds, outpost_by_site_id, root_remaining, SHIP_OVER_CRAFT_SECONDS, SHIP_SURPLUS_FACTOR, ship_units, SITE_PLAN_KEY, site_spare_elsewhere, SITE_TARGETS_FRESH_TICKS, SITE_TARGETS_KEY, SITE_TARGETS_LEASE_TICKS, SITE_TARGETS_MAX_STALE_TICKS, SITE_TARGETS_PRUNE_TICKS, split_units
from production_demand import fab_site_ingot_targets, get_material_demands, get_raw_material_reason, get_smelter_demands, get_smelter_worker_count, ingot_stock_levels, INGOT_STOCK_NEED, INGOT_STOCK_TARGET, INGOT_STOCK_TARGETS_KEY, site_ingot_refill, site_smelter_demands, smelter_recipe_peers
