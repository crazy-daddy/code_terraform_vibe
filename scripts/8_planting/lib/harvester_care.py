# Harvester mixin: manual crop care (light, water, salt) and the field's salt
# supply request. Composed by FieldKeeperController (lib/field_keeper.py).
#
# Each Harvester treatment covers one cell for 24 h (docs/components/harvester.md).
# A treatment is due when its manual timer drops below CARE_REFRESH_H and no
# provider (Grow Lamp / Sprinkler / Dispenser) covers the cell -- a provider
# shows up as the condition flag set with no manual time left.
#
# Salt only reaches the field through Inventory. While the layout holds salt
# species, a `salt` request at home is published via lib/logistics_requests.py;
# the reverse hauler fetches it from Water Pumps (lib/pump_salt.py).

import logistics_requests
from storage import total_stock
import field_layout
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

CARE_REFRESH_H = 4.0      # a treatment below this triggers a care tour
CARE_BATCH_H = 12.0       # a tour (and any visit) also renews everything below this,
                          # so renewals line up and later tours need fewer trips
SALT_MIN_STOCK = 3        # salt species are only planted with at least this much salt at home
SALT_STOCK_TARGET = 20    # home salt stock requested from the reverse hauler
REQUESTER_ID = "field_keeper"

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

    def salt_species(self, rules):
        return [sp for sp in rules if "salt" in field_layout.kinds(rules, sp)]

    def inactive_species(self, rules):
        """Species the field can't sustain right now (no salt on hand)."""
        if self.salt_in_inventory() >= SALT_MIN_STOCK:
            return []
        return self.salt_species(rules)

    def publish_salt_request(self, layout, rules, home_id, curr_tick):
        if not home_id:
            return
        wanted = set(self.salt_species(rules))
        if any(sp in wanted for sp in layout.values()):
            have = total_stock("salt")
            logistics_requests.set_requests(home_id, REQUESTER_ID, {"salt": (SALT_STOCK_TARGET, have)}, curr_tick)
        else:
            logistics_requests.clear_requests(REQUESTER_ID, home_id)

    # ---------------------------------------------------------------- care

    def care_due(self, cell, rules, refresh_h=CARE_REFRESH_H):
        """Treatment kinds this cell's plant needs renewed (less than refresh_h left)."""
        if getattr(cell, "status", "") not in ("growing", "stalled"):
            return []
        species = getattr(cell, "plant", None)
        if not species:
            return []
        due = []
        for kind in field_layout.care_kinds(rules, species):
            remaining = getattr(cell, _REMAINING[kind], 0) or 0
            covered_by_provider = bool(getattr(cell, _FLAG[kind], False)) and remaining <= 0
            if covered_by_provider or remaining >= refresh_h:
                continue
            if kind == "salt" and self.salt_in_inventory() < 1:
                continue
            due.append(kind)
        return due

    def care_targets(self, cells, rules, refresh_h=CARE_REFRESH_H):
        """{sector: [kinds]} for every plant with a treatment below refresh_h."""
        out = {}
        for sector, cell in cells.items():
            due = self.care_due(cell, rules, refresh_h)
            if due:
                out[sector] = due
        return out

    def ensure_water(self):
        """Refills the onboard tank when it can't cover one more watering."""
        h = self._host.harvester
        try:
            if h.water_level() >= 1.0:
                return True
        except Exception:
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
            status = getattr(res, "status", "?")
            if status == "ok":
                done.append(kind)
            else:
                self._host.log.debug(f"[{self._host.name}] {_ACTION[kind]} at {here} -> {status}: {getattr(res, 'message', '')}")
        if done:
            self._host.log.print(f"[{self._host.name}] Treated {here}: {', '.join(done)}.")
            self._host.last_action = f"care {'+'.join(done)}@{here}"
        return bool(done)
