# Fluid sourcing for recipe fluid_inputs: which building types feed each
# FluidPort, the buffer-tank latch rule and the network-wide source check.
from swallow import swallowed
from production_core import log, _component
from fluid_routing import rank_own_outpost_first


# A Fabricator recipe's water/steam/oil requirement (recipe.fluid_inputs,
# e.g. {"water_in": 1.0}) is a *separate* field from its solid .inputs
# (docs/components/fabricator.md) -- delivered by connecting the matching
# FluidPort (self.water_in / .steam_in / .oil_in) to one of these building
# types, not by taking an Inventory/Warehouse item. can_source_item() used to
# only ever look at .inputs, so a recipe needing Water was waved through as
# "sourceable" purely on its solid ingredients (Iron Ingot, Glass) even with
# no Water Pump anywhere on the network -- the Fabricator would then set that
# recipe and stall forever, and Supply Dock would commit to an Earth Order
# that could never actually complete.
FLUID_SOURCE_TYPE_IDS = {
    "water_in": ("water_pump", "steam_condenser", "liquid_tank", "bulk_liquid_reservoir"),
    "oil_in": ("oil_pump", "liquid_tank", "bulk_liquid_reservoir"),
    "steam_in": ("thermal_cap", "gas_tank"),
}

# liquid_tank/bulk_liquid_reservoir/gas_tank are generic multi-fluid buffers --
# they latch onto whichever exact fluid is piped into them FIRST and hold
# only that until drained to 0 (docs/components/liquid_tank.md,
# docs/components/gas_tank.md). Their mere existence on the network says
# nothing about which fluid they hold, or whether anything will ever fill
# one with the fluid we actually need -- e.g. a Liquid Tank latched to Water,
# or sitting empty with no Oil Pump anywhere to ever feed it, is not a
# usable Oil source even though the tank itself is real. Every other type in
# FLUID_SOURCE_TYPE_IDS is a dedicated producer (oil_pump, water_pump,
# steam_condenser, thermal_cap) that only ever emits its one fixed fluid, so
# its existence alone is sufficient.
BUFFER_FLUID_TYPE_IDS = ("liquid_tank", "bulk_liquid_reservoir", "gas_tank")
# Expected building.fluid() latch id for each fluid_key -- see both docs
# pages' `.fluid()` method above.
FLUID_LATCH_IDS = {"water_in": "water", "oil_in": "oil", "steam_in": "steam"}


def fluid_building_is_viable(fluid_key, type_id, building):
    """
    Whether this specific discovered building can actually deliver
    fluid_key, not just "this building type could in principle carry it".
    Shared by can_source_fluid() and lib/fabricator.py's connection
    candidate discovery, so both apply the exact same buffer-latch rule --
    see BUFFER_FLUID_TYPE_IDS' comment for why existence alone isn't enough
    for a tank. Deliberately does NOT consult fluid_routing.tank_assignments
    -- that registry only gates which tank a producer may establish a NEW
    connection to (see fluid_routing.tank_is_eligible_target()); a tank's
    own .fluid() latch is already the complete, authoritative answer to "can
    it deliver fluid_key right now" regardless of the registry's state.
    """
    if type_id not in BUFFER_FLUID_TYPE_IDS:
        return True
    expected = FLUID_LATCH_IDS.get(fluid_key)
    if not expected:
        return True
    # `building` here is whatever outpost.buildings(type_id) handed us -- a
    # bare BuildingRef snapshot (.id/.name/.type_id/.outpost/.powered/
    # .position only, no .fluid()/.level()/etc, per docs/components/
    # outpost.md) when called from discovery loops, but the full live
    # component when called directly with one (e.g. from a unit test). A
    # BuildingRef has no .fluid() of its own -- must resolve the real
    # component via get_component(ref.id) first, or this always raises and
    # every buffer tank looks permanently non-viable regardless of what it
    # actually holds.
    if not hasattr(building, "fluid"):
        b_id = getattr(building, "id", None)
        if not b_id:
            return False
        building = _component(b_id)
        if not building:
            return False
    try:
        return getattr(building, "fluid")() == expected
    except Exception as error:
        swallowed("production_fluids.fluid_building_is_viable: getattr(building, 'fluid')", error)
        return False


def viable_fluid_source_pairs(fluid_key, type_ids=None):
    """
    [(building_id, outpost_id), ...] for every building on the network that
    can deliver fluid_key right now: type_ids (default
    FLUID_SOURCE_TYPE_IDS[fluid_key]) filtered by fluid_building_is_viable(),
    in discovery order.
    """
    if type_ids is None:
        type_ids = FLUID_SOURCE_TYPE_IDS.get(fluid_key, ())
    pairs = []
    network = _component("outpost_network")
    if not network or not hasattr(network, "outposts"):
        return pairs
    try:
        for outpost in network.outposts():
            o_id = getattr(outpost, "id", None)
            for type_id in type_ids:
                for building in outpost.buildings(type_id):
                    b_id = getattr(building, "id", None)
                    if b_id and fluid_building_is_viable(fluid_key, type_id, building):
                        pairs.append((b_id, o_id))
    except Exception as error:
        swallowed("production_fluids.viable_fluid_source_pairs: network.outposts", error)
    return pairs


def discover_fluid_sources(fluid_key, own_outpost_id, type_ids=None):
    """Source ids from viable_fluid_source_pairs(), own outpost's first
    (fluid_routing.rank_own_outpost_first()). The discover callable of a
    recipe-fluid FluidInputRouter (Fabricator, Caster, Reactor, Mk III water,
    Sprinkler, Plant Terraformer)."""
    return rank_own_outpost_first(viable_fluid_source_pairs(fluid_key, type_ids), own_outpost_id)


def can_source_fluid(fluid_key, cache=None):
    """
    Whether a building that could feed this FluidPort right now exists
    anywhere on the outpost network -- a dedicated producer of this exact
    fluid, or a buffer tank already latched to it (see
    fluid_building_is_viable()). Deliberately checks existence/latch state
    only, not an actual completed pipe route or fluid level -- matching
    can_source_item()'s own "known source" bar (a surveyed site doesn't
    guarantee a working claim either) -- so this only rules out the "not
    (yet) able to supply this fluid at all" case, not "built but not yet
    piped/full".

    Pass a shared `cache` (SourceCache) when checking several
    recipes/items/orders in one pass -- see SourceCache's docstring for why
    that matters; the outpost.buildings() scan this does is a real game call
    per fluid_key, otherwise repeated once per recipe that needs it.
    """
    # Memo hit returns before any logging: callers re-ask the same key once
    # per recipe/input, and an empty debug block costs more than the lookup.
    if cache is not None:
        known = cache._fluid_results.get(fluid_key)
        if known is not None:
            return known
    log.start(f"can_source_fluid({fluid_key})", level="debug")

    type_ids = FLUID_SOURCE_TYPE_IDS.get(fluid_key)
    if not type_ids:
        result = True  # unrecognized fluid key -- don't block on something we don't model
        log.trace("unrecognized fluid key, not blocking")
    else:
        result = False
        network = _component("outpost_network")
        if network and hasattr(network, "outposts"):
            try:
                for outpost in network.outposts():
                    for type_id in type_ids:
                        for building in outpost.buildings(type_id):
                            if fluid_building_is_viable(fluid_key, type_id, building):
                                result = True
                                log.trace(f"viable source found -> {getattr(building, 'id', type_id)} ({type_id})")
                                break
                        if result:
                            break
                    if result:
                        break
            except Exception as error:
                swallowed("production_fluids.can_source_fluid: network.outposts", error)
        if not result:
            log.trace(f"no viable source among {type_ids}")

    if cache is not None:
        cache._fluid_results[fluid_key] = result
    log.end()
    return result
