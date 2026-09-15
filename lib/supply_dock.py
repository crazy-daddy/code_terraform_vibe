# Shared Library for Supply Dock Logistics
# Automatically matches and assigns Earth Contractor Campaign Orders & Weekly Orders,
# feeds required materials from Base Inventory, and enables continuous dispatch.
from production import can_fulfill_order, get_construction_material_reservations
from storage import take_item, total_stock

class SupplyDockController:
    """
    Automated controller for the Supply Dock.
    Prioritizes recipe/tech-unlocking campaign orders (Spire, Helios, Vestibule),
    loads materials from Inventory, and drives high-efficiency shipping to Earth.
    """
    def __init__(self, dock):
        self.dock = dock
        self.name = getattr(dock, "id", "supply_dock_1")
        self.orders_api = get_component("orders")
        self.inventory = get_component("inventory")
        self.connected = False

    def ensure_connected(self):
        """Ensures the dock input port is connected to base Inventory."""
        if not self.connected and hasattr(self.dock, "input"):
            try:
                self.dock.input.connect("inventory")
                self.connected = True
            except Exception:
                pass

    def drain_dock_cargo(self):
        """
        Ejects any cargo still physically loaded in the dock's slots back to
        Inventory. clear_order() explicitly does not drain cargo -- it just
        releases the assignment and leaves loaded materials in place -- so
        set_order() for a *new* order keeps rejecting with "cargo_present"
        until something actively empties the dock first.
        """
        if not hasattr(self.dock, "slots") or not hasattr(self.dock, "input"):
            return
        try:
            for slot in self.dock.slots():
                item_id = getattr(slot, "item_id", None)
                count = getattr(slot, "count", 0)
                if not item_id or count <= 0:
                    continue
                res = self.dock.input.eject("inventory", item_id, count)
                if res.status == "ok":
                    print(f"[{self.name}] Ejected {count}x {item_id} from dock back to Inventory.")
                elif res.status not in ["busy", "no_op"]:
                    print(f"[{self.name}] Eject notice for {item_id}: {res.status} - {res.message}")
        except Exception:
            pass

    def pick_best_order(self):
        """
        Selects the best available Earth Order:
        1. Campaign orders that unlock recipes or technology.
        2. Orders where materials are already available in Inventory.
        3. Other active campaign orders.
        4. Weekly Earth orders.
        """
        if not self.orders_api:
            return None

        candidates = []
        # Materials an active Construction Blueprint is waiting on don't count
        # toward an order's "readiness" score either -- otherwise an order
        # can get prioritized as nearly-ready using stock that's actually
        # earmarked for a build and won't be takeable (see step()).
        reserved = get_construction_material_reservations()

        # 1. Inspect Contractor Campaign Orders (Helios, Spire, Vestibule)
        try:
            for o in self.orders_api.list_orders():
                if getattr(o, "status", "") == "active":
                    if not can_fulfill_order(o):
                        print(f"[{self.name}] Skipping '{getattr(o, 'name', o.id)}': required materials have no known source.")
                        continue
                    prio = 10
                    if getattr(o, "reward_kind", "") in ["recipe", "tech"]:
                        prio += 50  # Strongly prioritize technology and recipe unlocks!

                    items_ready = 0
                    total_needed = 0
                    if hasattr(o, "requires") and self.inventory:
                        shipped = getattr(o, "shipped", {}) or {}
                        for item_id, req_count in o.requires.items():
                            still_needed = max(0, req_count - shipped.get(item_id, 0))
                            total_needed += still_needed
                            in_stock = max(0, total_stock(item_id) - reserved.get(item_id, 0))
                            items_ready += min(in_stock, still_needed)

                    if total_needed > 0:
                        ready_pct = items_ready / total_needed
                        prio += int(ready_pct * 30)

                    candidates.append({
                        "order": o,
                        "priority": prio,
                        "ready": items_ready,
                        "needed": total_needed
                    })
        except Exception:
            pass

        # 2. Inspect Weekly Orders
        try:
            for o in self.orders_api.list_weekly_orders():
                if getattr(o, "status", "") == "active":
                    if not can_fulfill_order(o):
                        continue
                    prio = 5
                    items_ready = 0
                    total_needed = 0
                    if hasattr(o, "requires") and self.inventory:
                        shipped = getattr(o, "shipped", {}) or {}
                        for item_id, req_count in o.requires.items():
                            still_needed = max(0, req_count - shipped.get(item_id, 0))
                            total_needed += still_needed
                            in_stock = max(0, total_stock(item_id) - reserved.get(item_id, 0))
                            items_ready += min(in_stock, still_needed)

                    if total_needed > 0:
                        ready_pct = items_ready / total_needed
                        prio += int(ready_pct * 20)

                    candidates.append({
                        "order": o,
                        "priority": prio,
                        "ready": items_ready,
                        "needed": total_needed
                    })
        except Exception:
            pass

        if not candidates:
            return None

        candidates.sort(key=lambda c: c["priority"], reverse=True)
        return candidates[0]["order"]

    def step(self):
        self.ensure_connected()

        curr_order = self.dock.current_order()

        # Step 1: Assign order if dock is currently idle
        if curr_order and not can_fulfill_order(curr_order):
            loaded = 0
            if hasattr(self.dock, "count"):
                for item_id in getattr(curr_order, "requires", {}) or {}:
                    loaded += self.dock.count(item_id)
            if loaded == 0 and hasattr(self.dock, "clear_order"):
                clear_res = self.dock.clear_order()
                if clear_res.status == "ok":
                    print(f"[{self.name}] Cleared undeliverable order '{curr_order.name}'.")
                    curr_order = None

        if not curr_order:
            # set_order() rejects with "cargo_present" while any cargo is
            # still physically loaded -- including leftovers from a
            # previously cleared/completed/expired order, since clear_order()
            # never drains the dock itself. Drain first and retry next cycle
            # rather than repeatedly failing set_order() forever.
            if hasattr(self.dock, "total") and self.dock.total() > 0:
                self.drain_dock_cargo()
                return

            best = self.pick_best_order()
            if not best:
                print(f"[{self.name}] No active Earth Orders available. Standing by.")
                return

            reward_desc = f"{best.reward_credits} cr"
            if getattr(best, "reward_kind", None):
                reward_desc += f" + {best.reward_kind} ({getattr(best, 'reward_label', '')})"

            print(f"[{self.name}] Assigning Earth Order '{best.name}' (ID: {best.id}, Reward: {reward_desc})...")
            res = self.dock.set_order(best.id)
            if res.status == "cargo_present":
                # Defensive fallback in case cargo appeared between the total()
                # check above and this call -- drain and let the next cycle retry.
                self.drain_dock_cargo()
                return
            if res.status != "ok":
                print(f"[{self.name}] Could not assign order: {res.status} - {res.message}")
                return
            curr_order = best

        # Step 2: Load required materials from Inventory or a Warehouse, but
        # never take stock an active Construction Blueprint is waiting on --
        # otherwise the Dock can "snack away" materials (e.g. titanium
        # ingots) out from under a Pioneer build the moment they land in
        # storage, well before the build gets a chance to collect them.
        if curr_order and hasattr(curr_order, "requires"):
            reserved = get_construction_material_reservations()
            shipped = getattr(curr_order, "shipped", {}) or {}
            for item_id, req_total in curr_order.requires.items():
                already_shipped = shipped.get(item_id, 0)
                in_dock = self.dock.count(item_id)
                needed = max(0, req_total - already_shipped - in_dock)
                if needed <= 0:
                    continue

                avail = total_stock(item_id)
                available_after_reservation = max(0, avail - reserved.get(item_id, 0))
                to_take = min(available_after_reservation, needed)
                if to_take > 0:
                    moved = take_item(self.dock.input, item_id, to_take)
                    if moved > 0:
                        print(f"[{self.name}] Loaded {moved}x {item_id} toward '{curr_order.name}' (Dock holds: {self.dock.count(item_id)}/{req_total}).")
                elif avail > 0 and item_id in reserved:
                    print(f"[{self.name}] Holding back {item_id}: all {avail} unit(s) in storage reserved by active Construction Blueprint(s).")

        # Step 3: Enable continuous dispatch
        if not self.dock.is_enabled() and self.dock.total() > 0:
            e_res = self.dock.set_enabled(True)
            if e_res.status == "ok":
                print(f"[{self.name}] Dispatch enabled at {self.dock.dispatch_rate():.0f} units/h.")

        # Step 4: Status report
        active_disp = self.dock.current_dispatch()
        if active_disp:
            prog = self.dock.dispatch_progress()
            rate = self.dock.dispatch_rate()
            print(f"[{self.name}] Shipping {active_disp}... Progress: {prog*100:.0f}% (Rate: {rate:.0f} u/h).")

    def run(self, poll_interval=3.0):
        print(f"Supply Dock Controller ({self.name}) online. Initializing logistics loop...")
        while True:
            try:
                self.step()
            except Exception as e:
                print(f"[{self.name}] Exception in supply dock loop: {e}")
            sleep(poll_interval)
