# Coastal biome processor: Bio Luminizer glow-tinting.
# See docs/components/bio_luminizer.md and docs/AI_CHEATSHEET.md Sec 1e for the
# lamp-mix solve this drives. Imports its shared pipeline helpers from bio.py --
# see that module's own header comment for why the split exists and why bio.py
# never imports back from here.
from bio import get_my_biome, local_sibling, is_order_incomplete, is_local_order, _local_sources, _local_stock_snapshot, _focus_local_order, _order_fragment_remaining
from storage import best_unload_target, drain_port_to_storage
from version_guard import validate_game_version


class BioLuminizerController:
    """
    Tints a raw Coastal sample's glow to match the local Bio Exchange's active order
    (BioOrder.target_glow) via a 3x3 lamp-mix solve (docs/components/bio_luminizer.md),
    then infuses it for delivery. A sample whose fragment doesn't need tinting (no
    active Coastal order requiring it) is passed through unchanged via discard().
    """
    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_luminizer")
        self.comms = get_component("comms")
        self._lamp_matrix = None  # (red_sig, green_sig, blue_sig) -- fixed hardware, read once

    def _lamp_matrix_cols(self):
        if self._lamp_matrix is None:
            red = self.machine.lamp_signature("red")
            green = self.machine.lamp_signature("green")
            blue = self.machine.lamp_signature("blue")
            if red and green and blue:
                self._lamp_matrix = (red, green, blue)
        return self._lamp_matrix

    def _find_coastal_order(self, orders, snapshot, fragment_id=None):
        """
        Finds an incomplete, local, glow-requiring order -- optionally one that
        specifically requires fragment_id. Deliberately NOT
        exchange.active_order(): that's a single shared, mutable pointer
        BioExchangeController.sweep_and_deliver() freely reassigns to whatever
        order it's currently delivering ANY matching sample to (Coastal or
        not) as part of its own aggressive multi-order sweep. Reading it here
        would make the Luminizer's tint target flap to whatever unrelated
        order the Exchange's sweep last happened to select, not the Coastal
        order that actually needs this fragment.

        Takes an already-fetched `orders` list -- step() fetches
        exchange.orders() exactly once per cycle and threads it through every
        helper below, instead of each one fetching its own fresh ~80-order
        copy (measured live: that pattern cost ~20s/cycle in
        BioCollectorController before the same fix was applied there -- see
        bio.py's _focus_local_order() docstring).

        Delegates to bio.py's _focus_local_order() -- shared with
        BioCollectorController's own harvest preference so both controllers
        concentrate on the SAME order at the same time, rather than the
        Collector gathering for orders the Luminizer isn't even working on
        yet. See _focus_local_order()'s docstring for the full "prefer
        stock we already have" reasoning and the live deadlock this also
        incidentally used to cause (an untouched fragment stuck staged in
        the Luminizer's own latched input while a different order was
        selected -- self.input holds one item id at a time until
        load()/flush() clears it).
        """
        my_biome = get_my_biome(self.machine)
        return _focus_local_order(orders, snapshot, my_biome, fragment_id)

    def _fragment_remaining(self, order, fragment_id, snapshot):
        """Units of fragment_id this order still needs, net of what's already
        correctly tinted for it. Delegates to bio.py's _order_fragment_remaining()
        -- shared with _focus_local_order()'s own "does this order still genuinely
        need this fragment" check."""
        return _order_fragment_remaining(order, fragment_id, snapshot)

    def _active_target_for(self, orders, snapshot, fragment_id):
        order = self._find_coastal_order(orders, snapshot, fragment_id)
        if not order:
            return None
        return getattr(order, "target_glow", None)

    def _order_matching_glow(self, orders, fragment_id, glow):
        """Incomplete local order requiring fragment_id whose target_glow exactly
        equals `glow`, or None. Used to tell "already correctly tinted, just
        needs delivering" apart from "still raw, needs (re-)tinting". Takes an
        already-fetched `orders` list -- see _find_coastal_order()'s docstring."""
        if not glow:
            return None
        my_biome = get_my_biome(self.machine)
        for order in orders:
            if not is_order_incomplete(order):
                continue
            if not is_local_order(order, my_biome):
                continue
            if fragment_id not in (order.requires or {}):
                continue
            target = getattr(order, "target_glow", None)
            if target and list(target) == list(glow):
                return order
        return None

    def _find_raw_stack(self, orders, fragment_id, outpost):
        """
        (source_id, properties, count) for the first locally-staged
        fragment_id stack that is NOT already correctly tinted for some
        current local order -- i.e. genuinely raw and safe to pull in for
        tinting. Never returns an already-finished stack (one whose glow
        exactly matches a live order's target_glow): that one just needs
        delivering, not re-tinting, and storage.take_item()'s property-blind
        take() could otherwise grab it by chance instead of raw material.
        Takes an already-fetched `orders` list -- see _find_coastal_order()'s
        docstring.
        """
        for source_id, component in _local_sources(outpost):
            if not component or not hasattr(component, "stacks"):
                continue
            try:
                stacks = component.stacks()
            except Exception:
                continue
            for stack in stacks:
                if getattr(stack, "id", None) != fragment_id:
                    continue
                count = getattr(stack, "count", 0)
                if count <= 0:
                    continue
                properties = getattr(stack, "properties", None) or {}
                glow = properties.get("glow")
                if glow and self._order_matching_glow(orders, fragment_id, glow):
                    continue  # already correctly tinted -- leave it for delivery
                return source_id, properties, count
        return None

    def _notify_heartbeat(self):
        """
        Broadcasts once every step() cycle, regardless of what that cycle
        did. BioLabController waits on this generic channel (via
        comms.wait_broadcast()) instead of busy-polling with sleep() while it
        holds off pulling its next specimen from the Collector / draining its
        own output -- see BioLabController._wait_for_processor()'s docstring.
        Every biome processor controller broadcasts the same channel, so the
        Lab doesn't need to know which one (if any) is actually deployed.

        Deliberately unconditional, not just "fired after a successful
        load()": wait_broadcast() only satisfies on a broadcast published
        AFTER the call, so a signal that only fired on a successful load
        would never fire again once the Luminizer drained its last item with
        nothing staged behind it to load next -- including right at startup,
        before this Luminizer has ever loaded anything at all -- leaving a
        waiting Lab stuck forever even though the Luminizer had, in fact,
        gone idle. Firing every cycle instead means the Lab always wakes up
        again within one Luminizer step(), whatever state it's actually in.
        """
        if not self.comms:
            return
        try:
            self.comms.broadcast("biome_processor_heartbeat", {"chamber_empty": self.machine.chamber is None})
        except Exception:
            pass

    def _load_next_sample(self, orders, snapshot):
        outpost = self.machine.outpost

        # self.input latches to whatever's already staged (e.g. left over
        # from an earlier interrupted cycle) until load()/flush() clears it.
        # Each staged stack is either already correctly tinted (a previous
        # infuse() succeeded, but it never got drained out before something
        # else got staged alongside it) -- in which case it doesn't belong in
        # the chamber again, it just needs ejecting to storage so the
        # Exchange can find and deliver it -- or genuinely raw, in which case
        # it's the next thing to load. Found live: loading an
        # already-correctly-glowing staged sample back into the chamber
        # leaves the Luminizer unable to do anything useful with it (it's
        # already at target, there's nothing left to solve for).
        staged_stacks = []
        if hasattr(self.machine.input, "stacks"):
            try:
                staged_stacks = self.machine.input.stacks()
            except Exception:
                staged_stacks = []

        raw_candidate = None
        for stack in staged_stacks:
            staged_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if not staged_id or count <= 0:
                continue
            properties = getattr(stack, "properties", None) or {}
            glow = properties.get("glow")

            if glow and self._order_matching_glow(orders, staged_id, glow):
                try:
                    destination = best_unload_target(staged_id, count, outpost=outpost)
                    self.machine.input.eject(destination, staged_id, count, properties, "exact")
                    print(f"[{self.name}] Ejected already-tinted {staged_id} (glow {glow}) to '{destination}' for delivery.")
                except Exception:
                    pass
                continue

            if raw_candidate is None:
                raw_candidate = (staged_id, properties)

        if raw_candidate:
            staged_id, properties = raw_candidate
            order = self._find_coastal_order(orders, snapshot, staged_id)
            if order and self._fragment_remaining(order, staged_id, snapshot) > 0:
                load_res = self.machine.load(staged_id, properties, "exact")
                if load_res.status == "ok":
                    print(f"[{self.name}] Loaded already-staged {staged_id} into chamber.")
                return
            # No current local order needs it any more -- recover it to
            # storage instead of leaving input stuck on dead material forever.
            try:
                count = self.machine.input.count()
                destination = best_unload_target(staged_id, count, outpost=outpost)
                self.machine.input.eject(destination, staged_id, count, properties, "exact")
                print(f"[{self.name}] Recovered stale staged {staged_id} to '{destination}' (no longer needed).")
            except Exception:
                pass
            return

        if staged_stacks:
            return  # everything staged this cycle was already-tinted and just got ejected above

        order = self._find_coastal_order(orders, snapshot)
        if not order:
            return

        for fragment_id in (order.requires or {}).keys():
            if self._fragment_remaining(order, fragment_id, snapshot) <= 0:
                continue
            found = self._find_raw_stack(orders, fragment_id, outpost)
            if not found:
                continue
            source_id, properties, _ = found
            if hasattr(self.machine.input, "connected_id") and self.machine.input.connected_id() != source_id:
                self.machine.input.connect(source_id)
            take_res = self.machine.input.take(fragment_id, 1, properties, "exact")
            if take_res.status != "ok":
                continue
            load_res = self.machine.load(fragment_id, properties, "exact")
            if load_res.status == "ok":
                print(f"[{self.name}] Loaded {fragment_id} into chamber.")
            return

    def _try_lamps(self, r, g, b, target):
        if not (0 <= r <= 40 and 0 <= g <= 40 and 0 <= b <= 40):
            return False
        self.machine.set_lamps(r, g, b)
        current = self.machine.glow()
        if current is None or list(current) != list(target):
            return False
        self._commit_infuse(target)
        return True

    def _commit_infuse(self, target):
        res = self.machine.infuse()
        if res.status == "ok":
            print(f"[{self.name}] Infused sample at glow {target}.")
        elif res.status == "busy":
            sleep(0.2)

    def _solve_and_apply(self, target):
        matrix = self._lamp_matrix_cols()
        if not matrix:
            print(f"[{self.name}] Lamp signature unavailable this cycle.")
            return

        zero_res = self.machine.set_lamps(0, 0, 0)
        if zero_res.status != "ok":
            return
        base = self.machine.glow()
        if base is None:
            return

        delta = [target[i] - base[i] for i in range(3)]
        solved = _solve_3x3(matrix, delta)
        if solved is None:
            print(f"[{self.name}] Could not solve lamp mix for target {target} (singular lamp matrix).")
            return

        r, g, b = (max(0, min(40, round(v))) for v in solved)
        if self._try_lamps(r, g, b, target):
            return

        # Bounded local search over the +/-1-per-channel neighborhood for rounding
        # error -- cheap (<=27 combinations) and avoids trusting the rounded solve
        # blindly, without brute-forcing the full 41^3 space against the live game.
        for dr in (-1, 0, 1):
            for dg in (-1, 0, 1):
                for db in (-1, 0, 1):
                    if dr == 0 and dg == 0 and db == 0:
                        continue
                    if self._try_lamps(r + dr, g + dg, b + db, target):
                        return

        print(f"[{self.name}] WARNING: no exact lamp match found near ({r},{g},{b}) for target {target}.")

    def step(self):
        self._notify_heartbeat()
        drain_port_to_storage(self.machine.output, self.machine.outpost)

        outpost = self.machine.outpost
        exchange = local_sibling(outpost, "bio_exchange")

        # Fetch exchange.orders() and walk local storage exactly ONCE per
        # step(), not once per fragment -- see BioCollectorController.step()
        # for the perf history (~20s/cycle re-fetching orders(), then ~8s
        # re-walking storage per fragment even after caching orders() alone).
        orders = []
        if exchange:
            try:
                orders = exchange.orders()
            except Exception:
                orders = []
        snapshot = _local_stock_snapshot(outpost)

        chamber = self.machine.chamber
        if chamber is None:
            self._load_next_sample(orders, snapshot)
            sleep(0.5)
            return

        target = self._active_target_for(orders, snapshot, chamber.fragment_id)
        if not target:
            # No glow requirement for this fragment right now -- pass through unchanged.
            self.machine.discard()
            sleep(0.5)
            return

        self._solve_and_apply(target)

    def run(self):
        print(f"Bio Luminizer ({self.name}) online via Shared Library.")
        validate_game_version()
        while True:
            self.step()
            sleep(0.5)


def _solve_3x3(matrix, b):
    """
    Solve M @ x = b for a 3x3 matrix `matrix` (columns = [red_sig, green_sig, blue_sig]
    triples, each a lamp's fixed per-unit RGB contribution) via Cramer's rule, pure
    Python (no numpy in this sandboxed environment). Returns [x0, x1, x2], or None if
    the matrix is singular (shouldn't happen -- lamp_signature() is documented fixed
    hardware with independent channels).
    """
    m = [[matrix[0][i], matrix[1][i], matrix[2][i]] for i in range(3)]  # rows

    def det3(a):
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))

    d = det3(m)
    if d == 0:
        return None

    result = []
    for col in range(3):
        m_col = [row[:] for row in m]
        for row in range(3):
            m_col[row][col] = b[row]
        result.append(det3(m_col) / d)
    return result
