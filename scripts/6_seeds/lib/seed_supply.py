# Seed Maker automation, stage B: make seeds on demand from known recipes.
#
# Runs once recipes() holds every species (the phase change lives in the
# bio/seed_maker.py entrypoint). Reuses SeedMakerController's chamber/stock/
# output helpers; only the planning differs:
#   - What to make: `plant.seed_demand["now"]` ({seed_id: seeds wanted},
#     published by the field Harvester, lib/field_keeper.py) minus the seeds
#     already at home (Inventory + Warehouses). New seeds go to a Warehouse;
#     the Harvester stages them into Inventory one at a time.
#   - What to stock: a standing base stock of every life form the field's
#     blends use, 1 t per layout cell (`plant.seed_demand["rotation"]`), so
#     drones keep the next full replant on hand, plus the open seed deficit.
#     Requests go through lib/logistics_requests.py exactly like stage A, so
#     miner drones and the reverse hauler serve them unchanged.
#
# Publishes `plant.recipes` ({species: {seed_id, blend, reqs, growth_time,
# base_yield}}) for the Harvester, which has no recipes() of its own.

from archive import archive
import logistics_requests
from seed_maker import SeedMakerController, STATUS_KEY, REQUESTER_ID, REQUEST_REFRESH_TICKS
from seed_maker import IDLE_POLL_SECONDS, combo_key, _now_tick
from storage import total_stock, drain_port_to_storage
from tree_console import TreeConsole
from version_guard import validate_game_version

RECIPES_KEY = "plant.recipes"
SEED_DEMAND_KEY = "plant.seed_demand"

SEED_SUPPLY_STASH_T = 120        # per-form request cap at the Seed Maker outpost (supports bulk replanting)
SEED_BUFFER_PER_SPECIES = 3      # seeds per species kept when no Harvester publishes demand
SEED_DEMAND_STALE_TICKS = 6000   # ~10 min; older Harvester demand counts as absent
SUPPLY_IDLE_POLL_SECONDS = 20.0  # nothing to make right now


class SeedSupplyController(SeedMakerController):
    """Crafts seeds for the field from known blends and keeps their life forms stocked."""

    def __init__(self, maker):
        super().__init__(maker)
        self.log = TreeConsole(module="seed_supply")
        self._last_recipes_tick = -REQUEST_REFRESH_TICKS

    # ------------------------------------------------------------ recipes

    def _recipe_map(self, recipes):
        """{seed_id: recipe} for every discovered recipe with a usable blend."""
        out = {}
        for r in recipes:
            seed_id = getattr(r, "seed_id", None)
            if seed_id and len(getattr(r, "blend", []) or []) == 3:
                out[seed_id] = r
        return out

    def _publish_recipes(self, recipes, curr_tick):
        if curr_tick - self._last_recipes_tick < REQUEST_REFRESH_TICKS:
            return
        self._last_recipes_tick = curr_tick
        data = {}
        for r in recipes:
            species = getattr(r, "species", None)
            if not species:
                continue
            reqs = [[getattr(q, "kind", ""), getattr(q, "species", None)] for q in (getattr(r, "requirements", []) or [])]
            data[species] = {
                "seed_id": getattr(r, "seed_id", "seed_" + species),
                "blend": list(getattr(r, "blend", []) or []),
                "reqs": reqs,
                "growth_time": getattr(r, "growth_time", 0),
                "base_yield": getattr(r, "base_yield", 0),
            }
        archive.set(RECIPES_KEY, data)
        self.log.debug(f"[{self.name}] Published {len(data)} recipe(s) to '{RECIPES_KEY}'.")

    # ------------------------------------------------------------- demand

    def _read_demand(self, by_seed, curr_tick):
        """(now, rotation) as {seed_id: n}; a buffer per species if the Harvester isn't publishing."""
        raw = archive.get(SEED_DEMAND_KEY, {})
        fresh = isinstance(raw, dict) and curr_tick - raw.get("tick", -SEED_DEMAND_STALE_TICKS) < SEED_DEMAND_STALE_TICKS
        if fresh:
            now = {k: int(v) for k, v in (raw.get("now") or {}).items() if k in by_seed}
            rotation = {k: int(v) for k, v in (raw.get("rotation") or {}).items() if k in by_seed}
            return now, rotation
        self.log.debug(f"[{self.name}] No fresh '{SEED_DEMAND_KEY}' (Harvester not running?); keeping {SEED_BUFFER_PER_SPECIES} seed(s) per species.")
        buffer = {k: SEED_BUFFER_PER_SPECIES for k in by_seed}
        return buffer, dict(buffer)

    def _drain_output(self):
        """
        Override: finished seeds go to a home Warehouse, not Inventory. The
        Harvester stages one into Inventory right before load_seed()
        (lib/field_keeper.py), so the 15 seed stacks don't clutter Inventory.
        Falls back to stage A's Inventory send if no Warehouse has room.
        """
        try:
            if self.maker.get_output_count() <= 0:
                return True
            moved = drain_port_to_storage(self.maker.output, outpost=self.outpost)
            if moved:
                self.log.print(f"[{self.name}] {moved} seed(s) sent to a Warehouse.")
        except Exception as e:
            self.log.debug(f"[{self.name}] output drain to Warehouse raised: {e}")
        return SeedMakerController._drain_output(self)

    def _deficits(self, now):
        """{seed_id: seeds still to make} = demand - seeds in Inventory and home Warehouses."""
        out = {}
        for seed_id, wanted in now.items():
            missing = wanted - total_stock(seed_id)
            if missing > 0:
                out[seed_id] = missing
        return out

    def _publish_supply_requests(self, by_seed, rotation, deficits, stock, curr_tick, force=False):
        if not force and curr_tick - self._last_request_tick < REQUEST_REFRESH_TICKS:
            return
        self._last_request_tick = curr_tick
        need = {}
        for seed_id, cells in rotation.items():
            for form in by_seed[seed_id].blend:
                need[form] = need.get(form, 0) + cells
        for seed_id, missing in deficits.items():
            for form in by_seed[seed_id].blend:
                need[form] = need.get(form, 0) + missing
        wants = {f: (min(SEED_SUPPLY_STASH_T, n), stock.get(f, 0)) for f, n in need.items() if n > 0}
        if self.outpost_id:
            if wants:
                logistics_requests.set_requests(self.outpost_id, REQUESTER_ID, wants, curr_tick)
            else:
                logistics_requests.clear_requests(REQUESTER_ID)
        short = sorted(f for f, pair in wants.items() if pair[1] < pair[0])
        self.log.debug(f"[{self.name}] supply requests: {len(wants)} form(s), {len(short)} below target: {short}")

    def _pick(self, by_seed, deficits, stock):
        """Seed with the largest deficit whose three forms are all in local stock, or None."""
        ready = [s for s in deficits if all(stock.get(f, 0) >= 1 for f in by_seed[s].blend)]
        if not ready:
            return None
        ready.sort(key=lambda s: (-deficits[s], s))
        return ready[0]

    # ------------------------------------------------------------ crafting

    def _craft(self, seed_id, recipe):
        blend = list(recipe.blend)
        loaded = self._chamber()
        for form in blend:
            if loaded.get(form, 0) >= 1:
                continue
            if not self._load_one(form):
                self.log.debug(f"[{self.name}] Could not load '{form}' for {seed_id}; ejecting.")
                self._eject_chamber()
                return False
        try:
            result = self.maker.combine(blend)
        except ValueError as e:
            self.log.level("error").print(f"[{self.name}] combine({blend}) rejected: {e}")
            self._eject_chamber()
            return False
        status = getattr(result, "status", "")
        if status == "seed_found":
            self._last_result = f"{combo_key(*blend)} -> {seed_id}"
            self.log.print(f"[{self.name}] Made '{seed_id}'.")
            return True
        self.log.level("warn").print(f"[{self.name}] combine({blend}) for '{seed_id}' -> {status}: {getattr(result, 'message', '')}")
        if status != "busy":
            self._eject_chamber()
        return False

    def _publish_supply_status(self, state, deficits):
        entry = {
            "state": state,
            "deficit": dict(deficits),
            "last": self._last_result,
            "tick": _now_tick(),
        }

        def updater(status):
            if not isinstance(status, dict):
                status = {}
            status[self.name] = entry
            return status

        archive.transaction(STATUS_KEY, {}, updater)

    # ---------------------------------------------------------------- loop

    def _recover_supply(self, by_seed):
        """After a restart: finish a known blend still in the chamber, else return it to storage."""
        while self._safe_is_running():
            sleep(0.5)
        self._drain_output()
        chamber = self._chamber()
        if not chamber:
            return
        key = combo_key(*sorted(chamber.keys())) if len(chamber) == 3 else None
        for seed_id, recipe in by_seed.items():
            if key and combo_key(*recipe.blend) == key and all(v == 1 for v in chamber.values()):
                self.log.print(f"[{self.name}] Resuming loaded blend for '{seed_id}'.")
                self._craft(seed_id, recipe)
                return
        self._eject_chamber()

    def step(self):
        curr_tick = _now_tick()
        if not self._drain_output():
            self.log.debug(f"[{self.name}] Result bay still holds a seed; waiting for room.")
            return IDLE_POLL_SECONDS

        recipes = self._recipes()
        by_seed = self._recipe_map(recipes)
        self._publish_recipes(recipes, curr_tick)

        now, rotation = self._read_demand(by_seed, curr_tick)
        deficits = self._deficits(now)
        stock = self._local_stock()
        self._publish_supply_requests(by_seed, rotation, deficits, stock, curr_tick)

        if not deficits:
            self._publish_supply_status("idle", deficits)
            return SUPPLY_IDLE_POLL_SECONDS

        seed_id = self._pick(by_seed, deficits, stock)
        if seed_id is None:
            self.log.debug(f"[{self.name}] Deficit {deficits} but no blend fully in stock; waiting for deliveries.")
            self._publish_supply_status("waiting_material", deficits)
            return IDLE_POLL_SECONDS

        self.log.debug(f"[{self.name}] Crafting '{seed_id}' (deficit {deficits[seed_id]}, blend {by_seed[seed_id].blend}).")
        self._craft(seed_id, by_seed[seed_id])
        self._drain_output()
        self._publish_supply_status("supplying", deficits)
        return 0.0

    def run(self):
        self.log.print(f"Seed Supply Controller ({self.name}) online at '{self.outpost_id}'.")
        validate_game_version()
        try:
            self._recover_supply(self._recipe_map(self._recipes()))
        except Exception as e:
            self.log.level("error").print(f"[{self.name}] Recovery failed: {e}")
        while True:
            try:
                delay = self.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Seed Supply exception: {e}")
                delay = IDLE_POLL_SECONDS
            if delay:
                sleep(delay)
