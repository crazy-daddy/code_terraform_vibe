# Harvester ability: field-wide Yield Amplifier. Composed by
# FieldKeeperController (lib/field_keeper.py); calls only the hub
# (lib/harvester_hub.py: stage, act, stock_count, step_machines()), never
# another ability mixin.
#
# One `yield_amplifier` dose gives every growing crop +200% base Forage yield
# for 24 h (docs/guide/biosphere_plants_tier.md §5). The timer drains whether
# or not anything grows, and a dose applied with time left adds 24 h on top.
# amplify() reads home Inventory only, so the dose is staged from a Warehouse
# first (HarvesterHubMixin.stage()).
#
#   1. apply (field_keeper step, ahead of every other task): once
#      amplifier_remaining() is 0, a dose is at home, at least
#      AMPLIFY_MIN_GROWING_FRACTION of the planted cells are growing, and
#      no majority of the deployed Crop Automators is clogged
#      (storage_take.crop_automator_forage(): output full, so extra Forage is
#      discarded; consumers drain clogged ones first among automators). Skip reasons
#      are logged once per change of reason. A failed apply skips it for
#      AMPLIFY_RETRY_TICKS, or AMPLIFY_BUSY_RETRY_TICKS when the dose could
#      not be staged only because every Warehouse holding one was "busy".
#   2. order (field_keeper publish): while a Fabricator lists the recipe,
#      one production.set_order() under requester AMPLIFIER_REQUESTER:
#      AMPLIFIER_NEED at the NEED band plus AMPLIFIER_STOCK at the STOCK band.
#      The Fabricators sit at other outposts; site_supply's home pull hauls
#      the doses home. The requester is in production.STANDING_ORDER_REQUESTERS.

from typing import TYPE_CHECKING

from priority import NEED, STOCK
from production import fabricator_unlocked_outputs, order_levels, set_order
from storage_take import crop_automator_forage
from swallow import swallowed

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

AMPLIFIER_ITEM_ID = "yield_amplifier"
AMPLIFIER_REQUESTER = "field_amplifier"  # listed in production.STANDING_ORDER_REQUESTERS
AMPLIFIER_NEED = 3  # NEED band: crafted ahead of Earth orders
AMPLIFIER_STOCK = 10  # STOCK band: idle Fabricator time only
AMPLIFY_MIN_GROWING_FRACTION = 0.5  # growing / planted cells needed to spend a dose
AMPLIFY_RETRY_TICKS = 3000  # after a failed apply, skip applying this long (~5 min)
AMPLIFY_BUSY_RETRY_TICKS = 300  # ...or this long (~30 s) when every Warehouse holding a dose answered "busy"
RECIPE_REFRESH_TICKS = 3000  # re-read whether a Fabricator has the recipe this often


class HarvesterAmplifyMixin:
    """Keeps the field-wide Yield Amplifier running and ordered."""

    @property
    def _host(self) -> "FieldKeeperController":
        return self  # type: ignore[return-value]

    def amplifier_hours(self):
        """Hours left on the field-wide Yield Amplifier, 0 when unreadable."""
        try:
            return float(self._host.harvester.amplifier_remaining())
        except Exception as error:
            swallowed("harvester_amplify.HarvesterAmplifyMixin.amplifier_hours: harvester.amplifier_remaining", error)
            return 0.0

    def amplifier_craftable(self, curr_tick):
        """True while a Fabricator lists the Yield Amplifier recipe; re-read every RECIPE_REFRESH_TICKS."""
        cache = getattr(self, "_amplifier_recipe", None)
        if cache is None or curr_tick < cache[0] or curr_tick - cache[0] >= RECIPE_REFRESH_TICKS:
            cache = (curr_tick, AMPLIFIER_ITEM_ID in fabricator_unlocked_outputs())
            self._amplifier_recipe = cache
        return cache[1]

    def publish_amplifier_order(self, curr_tick):
        """Standing Fabricator orders for the Yield Amplifier (module header, 2); returns the need order."""
        h = self._host
        craftable = self.amplifier_craftable(curr_tick)
        need = {AMPLIFIER_ITEM_ID: AMPLIFIER_NEED} if craftable else {}
        levels = order_levels(need=AMPLIFIER_NEED, need_prio=NEED, stock=AMPLIFIER_STOCK, stock_prio=STOCK)
        set_order(AMPLIFIER_REQUESTER, {AMPLIFIER_ITEM_ID: levels} if craftable else None)
        if craftable != getattr(self, "_amplifier_ordered", None):
            h.log.debug(f"[{h.name}] Yield Amplifier order: {'need ' + str(AMPLIFIER_NEED) + ', backlog ' + str(AMPLIFIER_STOCK) if craftable else 'none (no Fabricator lists the recipe)'}.")
            self._amplifier_ordered = craftable
        return need

    def amplify_skip_reason(self, curr_tick):
        """None when a dose should go on now, else (reason key, detail) for why not (module header, 1)."""
        h = self._host
        retry = getattr(self, "_amplify_retry", None)
        if retry is not None and 0 <= curr_tick - retry[0] < retry[1]:
            return "cooldown", f"retry after a failed apply ({retry[1]} ticks)"
        if self.amplifier_hours() > 0:
            return "running", "still running"
        if h.stock_count(AMPLIFIER_ITEM_ID) < 1:
            return "no_dose", "no dose at home"
        statuses, planted = h.field_pass.statuses or {}, h.field_pass.planted
        growing = sum(1 for s in planted if statuses.get(s) == "growing")
        if not planted or growing < AMPLIFY_MIN_GROWING_FRACTION * len(planted):
            return "growing", f"only {growing}/{len(planted)} planted cell(s) growing"
        automators = sum(1 for kind in (h.step_machines() or {}).values() if kind == "crop_automator")
        if automators:
            clogged = sum(1 for entry in crop_automator_forage() if entry[2])
            if clogged * 2 > automators:
                return "clogged", f"{clogged}/{automators} Crop Automator(s) clogged"
        return None

    def amplify_step(self, curr_tick):
        """Applies one Yield Amplifier dose when due; True if the step was spent on it."""
        return self.amplify_due(curr_tick) and self.amplify_apply(curr_tick)

    def amplify_due(self, curr_tick):
        """True when a dose should go on now (field_keeper choose()); a skip reason is logged once per change."""
        h = self._host
        reason = self.amplify_skip_reason(curr_tick)
        if reason is not None:
            if reason[0] != getattr(self, "_amplify_skip_logged", None):
                h.log.debug(f"[{h.name}] Yield Amplifier not applied: {reason[1]}.")
                self._amplify_skip_logged = reason[0]
            return False
        self._amplify_skip_logged = None
        return True

    def amplify_apply(self, curr_tick):
        """Stages and applies one dose (field_keeper run_choice()); a failure sets the retry wait. Always True."""
        h = self._host
        h.log.start(f"[{h.name}] Apply Yield Amplifier")
        if not h.stage(AMPLIFIER_ITEM_ID, 1):
            wait = AMPLIFY_BUSY_RETRY_TICKS if h.stage_busy else AMPLIFY_RETRY_TICKS
            self._amplify_retry = (curr_tick, wait)
            h.log.end(f"Not applied: dose could not be staged into Inventory ({'Warehouses busy' if h.stage_busy else 'see stage'}); retry in {wait} ticks")
            return True
        res = h.act("amplify")
        status = getattr(res, "status", "")
        h.stock_memo.pop(AMPLIFIER_ITEM_ID, None)
        if status == "ok":
            h.note_action("amplify")
            h.log.end(f"Applied: field amplified for {self.amplifier_hours():.1f} h")
            return True
        self._amplify_retry = (curr_tick, AMPLIFY_RETRY_TICKS)
        h.log.end(f"Not applied: {status or 'no result'} {getattr(res, 'message', '')}".rstrip())
        return True
