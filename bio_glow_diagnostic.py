# Bio Glow Diagnostic -- run manually, once, to answer one question: are the
# stray glow-tinted Warehouse samples (e.g. sd_wing_membrane) actually a match
# for a currently-incomplete order that the Exchange's sweep just isn't
# recognizing, or do they not match anything at all (meaning the tint itself
# is wrong)? Prints every incomplete order's requirements/target_glow next to
# every locally-staged matching-item-id stack's own properties and whatever
# self.machine.matches_order() says about it.
#
# Not fully read-only: matches_order() is relative to the Exchange's current
# active_order (no per-call order parameter), so this calls set_order() once
# per candidate order to check it -- same as BioExchangeController's own
# sweep already does live, every cycle. Restores whatever was active before
# this script ran when it's done.

from bio import is_order_incomplete, is_local_order, get_my_biome, local_sibling
from storage import discover_storage_buildings

# Resolve via the Luminizer's own outpost, not a hardcoded "bio_exchange_1" --
# there can be more than one Bio Exchange in this save now (e.g. bio_exchange_4
# alongside bio_exchange_1), and the one actually paired with the Luminizer at
# the coastal outpost isn't necessarily the "_1" instance.
luminizer = get_component("bio_luminizer_1")
exchange = local_sibling(getattr(luminizer, "outpost", None), "bio_exchange") if luminizer else None
if not exchange:
    print("[DIAGNOSTIC] Could not resolve bio_luminizer_1's local Bio Exchange.")
else:
    outpost = exchange.outpost
    my_biome = get_my_biome(exchange)

    try:
        all_orders = exchange.orders()
    except Exception as e:
        all_orders = []
        print(f"[DIAGNOSTIC] Could not read orders(): {e}")

    incomplete_orders = [o for o in all_orders if is_order_incomplete(o)]
    print(f"[DIAGNOSTIC] {len(all_orders)} total orders, {len(incomplete_orders)} incomplete.")

    # Which item ids are worth checking: every item any incomplete order
    # still requires, biased toward glow-bearing (coastal) orders.
    item_ids = set()
    print("\n[DIAGNOSTIC] Incomplete orders:")
    for o in incomplete_orders:
        glow = getattr(o, "target_glow", None)
        print(f"  {o.id} ({getattr(o, 'name', '?')}, biome={getattr(o, 'biome', '?')}, "
              f"local={is_local_order(o, my_biome)}): target_glow={glow}")
        for item_id, needed in (o.requires or {}).items():
            deliv = (o.delivered or {}).get(item_id, 0)
            in_tr = (o.in_transit or {}).get(item_id, 0)
            remaining = needed - deliv - in_tr
            print(f"    requires {item_id}: needed={needed} delivered={deliv} in_transit={in_tr} remaining={remaining}")
            if remaining > 0:
                item_ids.add(item_id)

    print(f"\n[DIAGNOSTIC] Scanning local storage for staged units of: {sorted(item_ids)}")

    prior_active = exchange.active_order()
    prior_active_id = getattr(prior_active, "id", None)

    found_any = False
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "stacks"):
            continue
        try:
            stacks = component.stacks()
        except Exception:
            continue
        for stack in stacks:
            item_id = getattr(stack, "id", None)
            if item_id not in item_ids:
                continue
            found_any = True
            properties = getattr(stack, "properties", None)
            print(f"\n[DIAGNOSTIC] {building['id']}: {stack.count}x {item_id}, properties={properties}")
            for o in incomplete_orders:
                if item_id not in (o.requires or {}):
                    continue
                set_res = exchange.set_order(o.id)
                if set_res.status != "ok":
                    print(f"    {o.id}: could not set_order() ({set_res.status}) -- skipped")
                    continue
                try:
                    match = exchange.matches_order(item_id, properties)
                except Exception as e:
                    match = f"error: {e}"
                print(f"    matches {o.id} (target_glow={getattr(o, 'target_glow', None)})? {match}")

    if not found_any:
        print("[DIAGNOSTIC] No locally-staged stacks found for any remaining-demand item id.")

    # Restore whatever was active before this diagnostic ran.
    if prior_active_id:
        exchange.set_order(prior_active_id)
    else:
        exchange.clear_order()

    print("\n[DIAGNOSTIC] Done. Restored previous active order." if prior_active_id else "\n[DIAGNOSTIC] Done. Cleared active order (none was set before).")
