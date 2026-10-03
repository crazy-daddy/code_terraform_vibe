# Per-outpost recipe claims shared by SmelterController (lib/smelter.py) and
# FabricatorController (lib/fabricator.py).
#
# Several machines of one kind at an outpost would all converge on the same
# top-shortfall recipe while other demanded outputs sit untouched. A claim on the
# recipe id a machine is about to set lets the next one move on to its next-best
# candidate. Claims expire after RECIPE_CLAIM_STALE_TICKS, so a machine that
# stalls or vanishes without releasing never blocks a recipe for good. Machines
# at different outposts never block each other (production.site_recipe_claims()).
#
# Archive shape, one key per machine kind:
#   {outpost_id: {recipe_id: {<CLAIM_OWNER_FIELD>: machine name, "tick": n}}}
#
# The host class sets RECIPE_CLAIMS_KEY and CLAIM_OWNER_FIELD, and provides
# name, log, _claim_ticks ({} in __init__), get_current_tick() and
# _claim_machine() (the machine whose outpost the claims belong to).

from archive import archive
from production import claim_site_id, site_recipe_claims
from swallow import swallowed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Protocol
    from tree_console import TreeConsole

    class _ClaimHost(Protocol):
        name: str
        log: TreeConsole
        _claim_ticks: dict

        def get_current_tick(self) -> int: ...

        def _claim_machine(self): ...

# A claim older than this (ticks) is free to take over. Generous: missing a real
# conflict is cheap, blocking a legitimate claim leaves demand unserved.
RECIPE_CLAIM_STALE_TICKS = 600
# A claim this machine won is re-confirmed in the archive only this often; in
# between, claim_recipe() answers from memory. Well under the stale window.
CLAIM_REFRESH_TICKS = 100


def _is_fresh(claim, current_tick):
    """current_tick 0 = clock unavailable: treat the claim as still held."""
    return current_tick == 0 or current_tick - claim.get("tick", 0) <= RECIPE_CLAIM_STALE_TICKS


class RecipeClaimMixin:
    """claim_recipe() / release_recipe() / foreign_claims() / is_shedded() for a recipe machine controller."""

    RECIPE_CLAIMS_KEY = ""
    CLAIM_OWNER_FIELD = ""

    @property
    def _host(self) -> "_ClaimHost":
        return self  # type: ignore[return-value]

    def _site_claims(self, claims):
        return site_recipe_claims(claims, self.CLAIM_OWNER_FIELD)

    def claim_recipe(self, recipe_id):
        """
        Claims recipe_id at this machine's outpost, or confirms its own claim.
        False when another machine holds a still-fresh claim, so the caller moves
        on to another candidate instead of racing for the same one.
        """
        host = self._host
        owner_field = self.CLAIM_OWNER_FIELD
        current_tick = host.get_current_tick()
        last_claim = host._claim_ticks.get(recipe_id)
        if current_tick and last_claim is not None and 0 <= current_tick - last_claim < CLAIM_REFRESH_TICKS:
            host.log.debug(f"claim_recipe({recipe_id}): held (confirmed {current_tick - last_claim} ticks ago)")
            return True
        notes = []  # logged after the transaction: a log call inside the updater gets it rejected
        site_id = claim_site_id(host._claim_machine())

        def updater(claims):
            claims = self._site_claims(claims)
            site = claims.setdefault(site_id, {})
            existing = site.get(recipe_id)
            if isinstance(existing, dict) and existing.get(owner_field) != host.name:
                if _is_fresh(existing, current_tick):
                    return claims
                notes.append(f"claim_recipe({recipe_id}): claim by '{existing.get(owner_field)}' is stale (age={current_tick - existing.get('tick', 0)} > {RECIPE_CLAIM_STALE_TICKS}), taking over")
            site[recipe_id] = {owner_field: host.name, "tick": current_tick}
            return claims

        try:
            archive.transaction(self.RECIPE_CLAIMS_KEY, {}, updater)
        except Exception as error:
            swallowed(f"recipe_claims.claim_recipe: {self.RECIPE_CLAIMS_KEY} transaction", error)
            return True  # can't verify; don't block production over an archive hiccup
        for note in notes:
            host.log.debug(note)

        claims = self._site_claims(archive.get(self.RECIPE_CLAIMS_KEY, {}))
        owner = ((claims.get(site_id) or {}).get(recipe_id) or {}).get(owner_field)
        won = owner == host.name
        if won:
            host._claim_ticks[recipe_id] = current_tick
        else:
            host._claim_ticks.pop(recipe_id, None)
        host.log.debug(f"claim_recipe({recipe_id}): {'won' if won else f'held by {owner!r}'}")
        return won

    def foreign_claims(self, site_id):
        """{recipe_id: owner} for every claim at site_id another machine holds fresh
        right now, i.e. one claim_recipe() would leave untouched. One archive read."""
        host = self._host
        current_tick = host.get_current_tick()
        site = self._site_claims(archive.get(self.RECIPE_CLAIMS_KEY, {})).get(site_id) or {}
        return {
            recipe_id: claim.get(self.CLAIM_OWNER_FIELD)
            for recipe_id, claim in site.items()
            if claim.get(self.CLAIM_OWNER_FIELD) != host.name and _is_fresh(claim, current_tick)
        }

    def release_recipe(self, recipe_id):
        if not recipe_id:
            return
        host = self._host
        host._claim_ticks.pop(recipe_id, None)
        site_id = claim_site_id(host._claim_machine())

        def updater(claims):
            claims = self._site_claims(claims)
            site = claims.get(site_id) or {}
            if (site.get(recipe_id) or {}).get(self.CLAIM_OWNER_FIELD) == host.name:
                del site[recipe_id]
            if not site:
                claims.pop(site_id, None)
            return claims

        try:
            archive.transaction(self.RECIPE_CLAIMS_KEY, {}, updater)
            host.log.debug(f"[{host.name}] release_recipe({recipe_id}): released")
        except Exception as error:
            swallowed(f"recipe_claims.release_recipe: {self.RECIPE_CLAIMS_KEY} transaction", error)

    def is_shedded(self):
        """
        True when the Power Guard (lib/power.py PowerGridManager, SOFT_SHED_PATTERNS)
        lists this machine in power.shedded. Smelters and Fabricators are soft-shed:
        never powered off, since they only draw power while crafting; not starting
        or topping up production saves the same power without a wake call to undo.
        """
        shedded = archive.get("power.shedded", [])
        return isinstance(shedded, list) and self._host.name in shedded
