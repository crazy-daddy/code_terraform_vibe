# Battery Holder vs Cargo Rack split for a mining Pioneer. Pure math, no
# game calls: pioneer_upgrade.py feeds it the site list and capacities and
# does the swaps. A trip's units are bounded by both the cargo racks and the
# battery left after the round-trip drive. The best split pays the least
# drive per delivered unit (fixed trip Wh / units per trip): dig Wh per unit
# is the same for every split, and drive time scales with drive Wh. See
# vehicles_drones.md §2b-2.

def units_per_trip(holders, racks, wh_per_holder, units_per_rack, fixed_wh, wh_per_unit, safety, reserve_wh):
    """
    Units one full-battery trip to a site can bring home: min(cargo room,
    units the battery pays for). fixed_wh is the round-trip drive, wh_per_unit
    the dig plus the extra return-drive Wh per carried unit. Same budget as
    VehicleEnergyMixin.max_mineable_units(): (charge - reserve) / safety.
    """
    budget = (holders * wh_per_holder - reserve_wh) / safety - fixed_wh
    if budget <= 0 or wh_per_unit <= 0:
        return 0
    return max(0, min(racks * units_per_rack, int(budget // wh_per_unit)))


def split_cost(holders, slots, wh_per_holder, units_per_rack, sites, safety, reserve_wh):
    """
    (unreachable, drive Wh per unit) with holders of slots as Battery Holders,
    over sites [(fixed_wh, wh_per_unit), ...]: how many sites a full battery
    brings no unit home from, and the mean fixed_wh / units_per_trip over the
    rest. Lower is better, compared as a tuple.
    """
    unreachable, total, reachable = 0, 0.0, 0
    for fixed_wh, wh_per_unit in sites:
        units = units_per_trip(holders, slots - holders, wh_per_holder, units_per_rack, fixed_wh, wh_per_unit, safety, reserve_wh)
        if units <= 0:
            unreachable += 1
            continue
        total += fixed_wh / units
        reachable += 1
    return (unreachable, total / reachable if reachable else 0.0)


def best_holder_count(slots, wh_per_holder, units_per_rack, sites, safety, reserve_wh):
    """
    Battery Holder count in 1..slots-1 with the lowest split_cost(); the rest
    are Cargo Racks. A tie goes to more holders (spare range for a farther
    site). None when slots < 2, no sites, or no split reaches any site.
    """
    if not sites:
        return None
    best, best_cost = None, None
    for holders in range(1, slots):
        cost = split_cost(holders, slots, wh_per_holder, units_per_rack, sites, safety, reserve_wh)
        if cost[0] == len(sites):
            continue
        if best_cost is None or cost <= best_cost:
            best, best_cost = holders, cost
    return best
