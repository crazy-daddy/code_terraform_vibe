# Harvester mixin: manual crop care (light, water, salt). Composed by
# FieldKeeperController (lib/field_keeper.py).
#
# Each Harvester treatment covers one cell for 24 h (docs/components/harvester.md).
# A treatment is due when its manual timer drops below CARE_REFRESH_H and no
# provider (Grow Lamp / Sprinkler / Dispenser) covers the cell -- a provider
# shows up as the condition flag set with no manual time left.
#
# Salt only reaches the field through Inventory. Home's salt request (field and
# Terraformers) is published by the Control Room Automation
# (lib/pump_salt.py publish_home_salt_request()).

import harvester_pure
from atomic import run_atomic
import field_layout
from swallow import swallowed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

CARE_REFRESH_H = 4.0      # a treatment below this triggers a care tour
CARE_BATCH_H = 12.0       # a tour (and any visit) also renews everything below this,
                          # so renewals line up and later tours need fewer trips
SALT_MIN_STOCK = 3        # salt species are only planted with at least this much salt at home

_HAND_STATUSES = ("growing", "stalled")
_KEPT_STATUSES = ("growing", "stalled", "mature")
_FLAG = {"light": "lit", "water": "watered", "salt": "salted"}
_REMAINING = {"light": "manual_light_remaining", "water": "manual_water_remaining", "salt": "manual_salt_remaining"}
_ACTION = {"light": "light", "water": "water", "salt": "dispense_salt"}


class HarvesterCareMixin:
    """Light / water / salt treatments and salt supply, mixed into FieldKeeperController."""

    @property
    def _host(self) -> "FieldKeeperController":
        return self  # type: ignore[return-value]

    def salt_in_inventory(self):
        """Salt at home (Inventory + Warehouses); staged into Inventory per dispense_salt()."""
        return self._host.stock_count("salt")

    def care_kind_table(self, rules):
        """{species: treatment kinds it needs} for the species with any, memoised per rules object."""
        memo = getattr(self, "_care_kind_memo", None)
        if memo is None or memo[0] is not rules:
            table = {}
            for species in rules:
                wanted = field_layout.care_kinds(rules, species)
                if wanted:
                    table[species] = wanted
            memo = (rules, table)
            self._care_kind_memo = memo
        return memo[1]

    def salt_species(self, rules):
        table = self.care_kind_table(rules)
        return [sp for sp in rules if "salt" in table.get(sp, ())]

    def inactive_species(self, rules):
        """Species the field can't sustain right now (no salt on hand)."""
        if self.salt_in_inventory() >= SALT_MIN_STOCK:
            return []
        return self.salt_species(rules)

    # ---------------------------------------------------------------- care

    def care_due(self, cell, rules, refresh_h=CARE_REFRESH_H, kept=False):
        """
        Treatment kinds this cell's plant needs renewed (less than refresh_h
        left). A mature crop waits for its harvest untreated, except a kept
        one (`kept`, never harvested): it only counts toward diversity while
        its conditions are met.
        """
        return [kind for kind, remaining in self.hand_care(cell, rules, kept) if remaining < refresh_h]

    def hand_care(self, cell, rules, kept=False):
        """
        [(kind, manual hours left)] of the treatments the Harvester keeps up on
        this cell: no provider covers it, and salt only while salt is at home.
        """
        if getattr(cell, "status", "") not in (_KEPT_STATUSES if kept else _HAND_STATUSES):
            return []
        species = getattr(cell, "plant", None)
        if not species:
            return []
        out = []
        for kind in self.care_kind_table(rules).get(species, ()):
            remaining = getattr(cell, _REMAINING[kind], 0) or 0
            if bool(getattr(cell, _FLAG[kind], False)) and remaining <= 0:
                continue   # covered by a provider
            if kind == "salt" and self.salt_in_inventory() < 1:
                continue
            out.append((kind, remaining))
        return out

    def care_snapshot(self, cells, rules, kept=()):
        """
        {sector: [(kind, manual hours left)]} for every planted cell with a
        hand treatment (hand_care()), in cell order. Computed once per cells
        dict, rules object and kept set (HarvesterPlantingMixin.row_scan(), an
        atomic pure scan): the care tour, the status entry and the idle line
        all read it.
        """
        return self._host.row_scan(cells, rules, kept)["care"]

    def next_care_hours(self, cells, rules, kept=()):
        """World hours until the next hand treatment drops below CARE_REFRESH_H; None when none is kept up."""
        left = [remaining for treatments in self.care_snapshot(cells, rules, kept).values() for _, remaining in treatments]
        return max(0.0, min(left) - CARE_REFRESH_H) if left else None

    def care_targets(self, cells, rules, refresh_h=CARE_REFRESH_H, kept=()):
        """{sector: [kinds]} for every plant with a treatment below refresh_h (`kept` sectors: mature ones too)."""
        items = list(self.care_snapshot(cells, rules, kept).items())
        size = harvester_pure.CARE_CHUNK
        out = {}
        for i in range(0, len(items), size):
            out.update(run_atomic(harvester_pure.due_targets, items[i:i + size], refresh_h))
        return out

    def ensure_water(self):
        """Refills the onboard tank when it can't cover one more watering."""
        h = self._host.harvester
        try:
            if h.water_level() >= 1.0:
                return True
        except Exception as error:
            swallowed("harvester_care.HarvesterCareMixin.ensure_water: h.water_level", error)
            return True
        res = self._host.act("refill_water")
        status = getattr(res, "status", "?")
        if status in ("ok", "already_full"):
            return True
        self._host.log.level("warn").print(f"[{self._host.name}] refill_water -> {status}: {getattr(res, 'message', '')}")
        return False

    def care_here(self, kinds):
        """Applies each due treatment to the current cell."""
        here = self._host.get_position()
        done = []
        for kind in kinds:
            if kind == "water" and not self.ensure_water():
                continue
            if kind == "salt":
                self._host.stage("salt")
            res = self._host.act(_ACTION[kind])
            if getattr(res, "status", "?") == "ok":
                done.append(kind)
        if done:
            self._host.log.print(f"[{self._host.name}] Treated {here}: {', '.join(done)}.")
            self._host.last_action = f"care {'+'.join(done)}@{here}"
        return bool(done)
