# Coastal biome processor: Bio Luminizer glow-tinting.
# See docs/components/bio_luminizer.md and docs/AI_CHEATSHEET.md Sec 1e for the
# lamp-mix solve this drives. Sample loading, heartbeat and run loop come from
# bio_processor.py's BioProcessorController.
from bio import get_my_biome, is_order_incomplete, is_local_order
from bio_processor import BioProcessorController, STACK_RAW, STACK_FINISHED
from tree_console import flush_all, method_block


class BioLuminizerController(BioProcessorController):
    """
    Tints a raw Coastal sample's glow to match the local Bio Exchange's active order
    (BioOrder.target_glow) via a 3x3 lamp-mix solve (docs/components/bio_luminizer.md),
    then infuses it for delivery. A sample whose fragment doesn't need tinting (no
    active Coastal order requiring it) is passed through unchanged via discard().
    """
    TYPE_ID = "bio_luminizer"
    MODULE = "bio_coastal"
    DISPLAY_NAME = "Bio Luminizer"
    FINISHED_LABEL = "already-tinted"

    def __init__(self, machine: "BioLuminizer"):
        BioProcessorController.__init__(self, machine)
        self._lamp_matrix = None  # (red_sig, green_sig, blue_sig) -- fixed hardware, read once

    def _lamp_matrix_cols(self):
        if self._lamp_matrix is None:
            red = self.machine.lamp_signature("red")
            green = self.machine.lamp_signature("green")
            blue = self.machine.lamp_signature("blue")
            if red and green and blue:
                self._lamp_matrix = (red, green, blue)
        return self._lamp_matrix

    def _active_target_for(self, orders, snapshot, fragment_id):
        order = self._find_local_order(orders, snapshot, fragment_id)
        if not order:
            return None
        return getattr(order, "target_glow", None)

    def _order_matching_glow(self, orders, fragment_id, glow):
        """Incomplete local order requiring fragment_id whose target_glow exactly
        equals `glow`, or None. Tells "already correctly tinted, just needs
        delivering" apart from "still raw, needs (re-)tinting"."""
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

    def _classify_stack(self, stack, orders):
        """A stack whose glow already matches a live order's target_glow is finished:
        it needs delivering, not re-tinting (loading it back leaves nothing to solve)."""
        properties = self._stack_properties(stack)
        glow = (properties or {}).get("glow")
        if glow and self._order_matching_glow(orders, getattr(stack, "id", None), glow):
            return STACK_FINISHED, properties
        return STACK_RAW, properties

    def _try_lamps(self, r, g, b, target):
        self.log.start(f"[{self.name}] _try_lamps", level="debug")
        if not (0 <= r <= 40 and 0 <= g <= 40 and 0 <= b <= 40):
            self.log.trace(f"({r},{g},{b}) out of [0,40] bounds -- skipping.")
            self.log.end()
            return False
        self.machine.set_lamps(r, g, b)
        current = self.machine.glow()
        if current is None or list(current) != list(target):
            self.log.debug(f"Tried lamps ({r},{g},{b}) -> glow={current}, target={target} -- no match.")
            self.log.end()
            return False
        self.log.debug(f"Lamps ({r},{g},{b}) produced exact glow match {current} for target {target}.")
        self._commit_infuse(target)
        self.log.end()
        return True

    def _commit_infuse(self, target):
        res = self.machine.infuse()
        if res.status == "ok":
            self.log.print(f"[{self.name}] Infused sample at glow {target}.")
        elif res.status == "busy":
            flush_all()
            sleep(0.2)

    def _solve_and_apply(self, target):
        self.log.start(f"[{self.name}] Tinting to glow {target}")
        outcome = self._solve_lamps(target)
        self.log.end(f"[{self.name}] Tint {outcome}")

    @method_block(lambda self, *_, **__: f"[{self.name}] _solve_lamps")
    def _solve_lamps(self, target):
        """Runs the lamp-mix solve; returns a short outcome string for the enclosing log block."""
        self.log.trace(f"_solve_and_apply: entry, target={target}")
        matrix = self._lamp_matrix_cols()
        if not matrix:
            self.log.level("warn").print(f"[{self.name}] Lamp signature unavailable this cycle.")
            return "skipped (lamp signature unavailable)"

        zero_res = self.machine.set_lamps(0, 0, 0)
        if zero_res.status != "ok":
            self.log.debug(f"set_lamps(0,0,0) -> {zero_res.status}: {getattr(zero_res, 'message', '')} -- aborting solve this cycle.")
            return "aborted (lamps would not zero)"
        base = self.machine.glow()
        if base is None:
            self.log.debug("glow() returned None after zeroing lamps -- aborting solve this cycle.")
            return "aborted (no glow reading)"

        delta = [target[i] - base[i] for i in range(3)]
        solved = _solve_3x3(matrix, delta)
        if solved is None:
            self.log.level("warn").print(f"[{self.name}] Could not solve lamp mix for target {target} (singular lamp matrix).")
            return "failed (singular lamp matrix)"

        r, g, b = (max(0, min(40, round(v))) for v in solved)
        self.log.debug(f"Solved lamp mix base={base} delta={delta} -> raw_solve={solved}, rounded/clamped=({r},{g},{b}).")
        if self._try_lamps(r, g, b, target):
            self.log.trace(f"_solve_and_apply: exit, exact solve matched on first try ({r},{g},{b}).")
            return f"matched exactly at lamps ({r},{g},{b})"

        # Bounded local search over the +/-1-per-channel neighborhood for rounding
        # error -- cheap (<=27 combinations) and avoids trusting the rounded solve
        # blindly, without brute-forcing the full 41^3 space against the live game.
        self.log.debug(f"Exact solve ({r},{g},{b}) missed target {target} -- searching +/-1-per-channel neighborhood (<=27 combos).")
        for dr in (-1, 0, 1):
            for dg in (-1, 0, 1):
                for db in (-1, 0, 1):
                    if dr == 0 and dg == 0 and db == 0:
                        continue
                    if self._try_lamps(r + dr, g + dg, b + db, target):
                        self.log.trace(f"_solve_and_apply: exit, neighborhood search matched ({r+dr},{g+dg},{b+db}).")
                        return f"matched in neighborhood at lamps ({r+dr},{g+dg},{b+db})"

        self.log.level("warn").print(f"[{self.name}] WARNING: no exact lamp match found near ({r},{g},{b}) for target {target}.")
        self.log.trace("_solve_and_apply: exit, no match found.")
        return "failed (no exact lamp match)"

    def step(self):
        _, _, orders, snapshot = self._begin_step()
        chamber = self.machine.chamber
        self.log.trace(f"[{self.name}] step: entry, {len(orders)} order(s) fetched, chamber_empty={chamber is None}")

        if chamber is None:
            self._load_next_sample(orders, snapshot)
            self._idle()
            return

        target = self._active_target_for(orders, snapshot, chamber.fragment_id)
        if not target:
            # No glow requirement for this fragment right now -- pass through unchanged.
            self.log.debug(f"[{self.name}] No local order requires {chamber.fragment_id} tinted right now -- discarding unchanged.")
            self.machine.discard()
            self._idle()
            return

        self.log.debug(f"[{self.name}] {chamber.fragment_id} target_glow={target} -- solving lamp mix.")
        self._solve_and_apply(target)
        self._idle()


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
