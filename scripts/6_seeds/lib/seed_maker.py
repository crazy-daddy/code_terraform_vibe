# Seed Maker automation, stage A: fair brute-force recipe discovery.
#
# The 15 seed recipes are unique per planet and only found by trial
# (docs/components/seed_maker.md). What the sweep relies on:
#   - Every trial costs 1 t each of three distinct life forms, hit or sludge.
#   - Recipes are spread over all C(30,3) = 4060 triples with no biome
#     structure, so the ORDER of trials doesn't change the hit rate. The next
#     trial is therefore picked purely by what's in stock (max-min stock, which
#     spreads consumption evenly) instead of waiting for all 30 forms.
#   - A life form takes part in at most MAX_RECIPES_PER_FORM recipes. Once a
#     form has that many known recipes, every other triple containing it is
#     guaranteed sludge and is skipped ("saturated").
#   - recipes() is the game's own discover-once journal, so hits never need to
#     be stored here -- only which triples have been tried.
#
# State (Data Archive, one shared dict -- CLAUDE.md rule 7):
#   seed.combos_tried = {"a,b,c": True | {"by": maker_id, "tick": n, "stage": s}}
#     True  -> tried (sludge or hit); never retried.
#     dict  -> in-flight claim by one Seed Maker ("loading" -> "running"),
#              expires after SEED_CLAIM_STALE_TICKS so a dead maker can't
#              pin a triple. Several makers share this key safely because
#              claiming and marking both go through archive.transaction().
#   Keys are life-form NAMES, not indices -- a new life form in a game update
#   just adds untried triples, nothing is ever reset.
#
# Missing forms are requested via lib/logistics_requests.py, which a reverse
# hauler (Pioneer with DESTINATION_OUTPOST_ID="*" parked at this outpost) and
# demand-aware miner drones act on.

from archive import archive
from storage import take_item, drain_port_to_storage, best_unload_target
import logistics_requests
from tree_console import TreeConsole
from version_guard import validate_game_version

TRIED_KEY = "seed.combos_tried"
STATUS_KEY = "seed_maker.status"
REQUESTER_ID = "seed_maker"

SEED_SPECIES_TOTAL = 15          # docs/types/biosphere.md SeedRecipe.seed_id possible values
MAX_RECIPES_PER_FORM = 4         # generator cap per life form (see module docstring)
SEED_STASH_TARGET_T = 60         # per-form stock requested at the Seed Maker outpost (capped by open triples left)
SEED_CLAIM_STALE_TICKS = 3000    # ~5 min; a claim older than this is free again
REQUEST_REFRESH_TICKS = 1200     # recompute + republish requests at most this often (~2 min);
                                 # must stay well below logistics_requests.REQUEST_STALE_TICKS
IDLE_POLL_SECONDS = 10.0         # nothing to try / waiting for material
DONE_POLL_SECONDS = 120.0        # all species found


def combo_key(*trio):
    return ",".join(sorted(trio))


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception:
        return 0


def _owned_by(entry, maker_name):
    return isinstance(entry, dict) and entry.get("by") == maker_name


def _claim_is_live(entry, curr_tick):
    return isinstance(entry, dict) and curr_tick - entry.get("tick", 0) < SEED_CLAIM_STALE_TICKS


class SeedMakerController:
    """Runs untried life-form triples through a Seed Maker until every species is discovered."""

    def __init__(self, maker):
        self.maker = maker
        self.name = getattr(maker, "id", "seed_maker")
        self.outpost = getattr(maker, "outpost", None)
        self.outpost_id = getattr(self.outpost, "id", None)
        self.log = TreeConsole(module="seed_maker")
        self.forms = self._read_life_forms()
        self._tried = {}              # local mirror of TRIED_KEY, refreshed by every transaction
        self._last_request_tick = -REQUEST_REFRESH_TICKS
        self._last_open_total = None
        self._last_result = ""
        self._trials_this_run = 0

    # ------------------------------------------------------------- reading

    def _read_life_forms(self):
        try:
            return sorted(self.maker.life_forms())
        except Exception:
            return []

    def _recipes(self):
        try:
            return list(self.maker.recipes())
        except Exception:
            return []

    def _chamber(self):
        """{item_id: units} currently loaded in the reaction chamber."""
        loaded = {}
        try:
            for stack in self.maker.input.stacks():
                if stack.count > 0:
                    loaded[stack.id] = loaded.get(stack.id, 0) + stack.count
        except Exception:
            pass
        return loaded

    def _saturated_forms(self, recipes):
        counts = {}
        for recipe in recipes:
            for form in getattr(recipe, "blend", []) or []:
                counts[form] = counts.get(form, 0) + 1
        return {form for form, n in counts.items() if n >= MAX_RECIPES_PER_FORM}

    def _is_open(self, key, curr_tick, allow_own_claim=False):
        """True if the triple is neither tried nor claimed by a live peer."""
        entry = self._tried.get(key)
        if entry is None:
            return True
        if entry is True:
            return False
        if allow_own_claim and isinstance(entry, dict) and entry.get("by") == self.name:
            return True
        return not _claim_is_live(entry, curr_tick)

    # ----------------------------------------------------- tried / claims

    def _refresh_tried(self):
        raw = archive.get(TRIED_KEY, {})
        self._tried = raw if isinstance(raw, dict) else {}

    def _claim(self, key, stage, curr_tick):
        """Atomically claims `key` for this maker. Returns False if tried or held by a live peer."""
        won = []

        def updater(tried):
            if not isinstance(tried, dict):
                tried = {}
            entry = tried.get(key)
            peer_claim = isinstance(entry, dict) and not _owned_by(entry, self.name) and _claim_is_live(entry, curr_tick)
            if entry is not True and not peer_claim:
                tried[key] = {"by": self.name, "tick": curr_tick, "stage": stage}
                won.append(True)
            self._tried = tried
            return tried

        archive.transaction(TRIED_KEY, {}, updater)
        return bool(won)

    def _mark_tried(self, keys):
        """Marks every key in `keys` as tried (overwriting this maker's claim on it)."""
        def updater(tried):
            if not isinstance(tried, dict):
                tried = {}
            for key in keys:
                tried[key] = True
            self._tried = tried
            return tried

        archive.transaction(TRIED_KEY, {}, updater)

    def _release(self, key):
        def updater(tried):
            if not isinstance(tried, dict):
                tried = {}
            if key in tried and _owned_by(tried[key], self.name):
                del tried[key]
            self._tried = tried
            return tried

        archive.transaction(TRIED_KEY, {}, updater)

    def _own_claims(self):
        return {k: e for k, e in self._tried.items() if isinstance(e, dict) and e.get("by") == self.name}

    # ------------------------------------------------------------- stock

    def _local_stock(self):
        return logistics_requests.outpost_stock(self.forms, self.outpost)

    def _load_one(self, item_id):
        """Takes 1 t of item_id into the chamber from local Warehouses/Inventory, else a local Drone Depot."""
        port = self.maker.input
        if take_item(port, item_id, 1, outpost=self.outpost) >= 1:
            return True
        for depot in logistics_requests.local_depots(self.outpost):
            if logistics_requests.depot_stock(depot).get(item_id, 0) < 1:
                continue
            try:
                if port.connected_id() != depot.id:
                    port.connect(depot.id)
                res = port.take(item_id, 1)
            except Exception as e:
                self.log.debug(f"[{self.name}] take('{item_id}') from depot '{depot.id}' raised: {e}")
                continue
            if (getattr(res, "moved", 0) or 0) >= 1:
                return True
            self.log.debug(f"[{self.name}] take('{item_id}') from depot '{depot.id}' -> {getattr(res, 'status', '?')}")
        return False

    def _eject_chamber(self):
        """Returns whatever sits in the chamber to local storage (never destroys it)."""
        for item_id, units in self._chamber().items():
            target = best_unload_target(item_id, units, outpost=self.outpost)
            if target is None:
                self.log.level("warn").print(f"[{self.name}] No local storage has room for {units}x '{item_id}' from the chamber; leaving it loaded.")
                continue
            try:
                res = self.maker.input.eject(target, item_id, units)
                self.log.debug(f"[{self.name}] eject {units}x '{item_id}' -> '{target}': {getattr(res, 'status', '?')}")
            except Exception as e:
                self.log.level("warn").print(f"[{self.name}] eject '{item_id}' failed: {e}")

    def _drain_output(self):
        """Sends a waiting seed to home Inventory (where planting starts), else to local storage."""
        try:
            if self.maker.get_output_count() <= 0:
                return True
        except Exception:
            return True
        port = self.maker.output
        try:
            for stack in port.stacks():
                if port.connected_id() != "inventory":
                    port.connect("inventory")
                res = port.send(stack.id, stack.count)
                if getattr(res, "status", "") in ("ok", "partial"):
                    self.log.print(f"[{self.name}] Seed '{stack.id}' sent to Inventory.")
                else:
                    self.log.debug(f"[{self.name}] send '{stack.id}' to Inventory -> {getattr(res, 'status', '?')}; trying local storage.")
                    drain_port_to_storage(port, outpost=self.outpost)
        except Exception as e:
            self.log.debug(f"[{self.name}] output drain raised: {e}")
        try:
            return self.maker.get_output_count() <= 0
        except Exception:
            return False

    # ---------------------------------------------------------- planning

    def _viable_forms(self, saturated):
        return [f for f in self.forms if f not in saturated]

    def _pick_triple(self, stock, saturated, curr_tick):
        """
        The open triple whose scarcest member has the most stock: forms with
        >= 1 t are ordered by stock descending and the smallest possible
        "worst index" k is searched first, so the first open triple found
        maximizes min(stock). Returns (key, [a, b, c]) or (None, None).
        """
        ranked = [f for f in self._viable_forms(saturated) if stock.get(f, 0) >= 1]
        ranked.sort(key=lambda f: -stock.get(f, 0))
        n = len(ranked)
        for k in range(2, n):
            for i in range(0, k - 1):
                for j in range(i + 1, k):
                    key = combo_key(ranked[i], ranked[j], ranked[k])
                    if self._is_open(key, curr_tick):
                        return key, [ranked[i], ranked[j], ranked[k]]
        return None, None

    def _open_combo_counts(self, saturated, curr_tick):
        """
        {form: open triples it still appears in} over non-saturated forms, plus
        the grand total. Starts from the closed-form C(n,3) / C(n-1,2) counts
        and subtracts only the closed entries in `_tried`, so the cost scales
        with trials done instead of walking all 4060 triples (that full walk
        took ~620 ticks in-game and ran before every trial).
        """
        viable = self._viable_forms(saturated)
        viable_set = set(viable)
        n = len(viable)
        per_form = (n - 1) * (n - 2) // 2
        counts = {f: per_form for f in viable}
        total = n * (n - 1) * (n - 2) // 6
        for key in self._tried:
            members = key.split(",")
            if len(members) != 3 or not all(m in viable_set for m in members):
                continue
            if self._is_open(key, curr_tick, allow_own_claim=True):
                continue
            total -= 1
            for m in members:
                counts[m] -= 1
        return counts, total

    def _publish_requests(self, saturated, stock, curr_tick, force=False):
        """
        Requests every form that still appears in an open triple. Each open
        triple needs 1 t of each member, so a form's target is its open-triple
        count capped at SEED_STASH_TARGET_T -- big batches per hauler trip
        early on, never more than the sweep can still use near the end.
        """
        if not force and curr_tick - self._last_request_tick < REQUEST_REFRESH_TICKS:
            return self._last_open_total
        self._last_request_tick = curr_tick
        counts, total = self._open_combo_counts(saturated, curr_tick)
        wants = {f: (min(SEED_STASH_TARGET_T, n), stock.get(f, 0)) for f, n in counts.items() if n > 0}
        if self.outpost_id:
            logistics_requests.set_requests(self.outpost_id, REQUESTER_ID, wants, curr_tick)
        short = sorted(f for f, pair in wants.items() if pair[1] < pair[0])
        missing = sum(max(0, t - h) for t, h in wants.values())
        self.log.debug(f"[{self.name}] requests: {len(wants)} form(s) still in open triples ({total} open), {len(short)} below target ({missing} t missing): {short}")
        self._last_open_total = total
        return total

    def _publish_status(self, state, recipes, saturated, open_total):
        tried_count = sum(1 for v in self._tried.values() if v is True)
        entry = {
            "state": state,
            "found": len(recipes),
            "tried": tried_count,
            "open": open_total,
            "saturated": sorted(saturated),
            "last": self._last_result,
            "tick": _now_tick(),
        }

        def updater(status):
            if not isinstance(status, dict):
                status = {}
            status[self.name] = entry
            return status

        archive.transaction(STATUS_KEY, {}, updater)

    # ------------------------------------------------------------- trial

    def _run_trial(self, key, blend, curr_tick):
        """Loads the (already claimed) blend and combines it. Returns True if the triple got consumed."""
        loaded = self._chamber()
        for form in blend:
            if loaded.get(form, 0) >= 1:
                continue
            if not self._load_one(form):
                self.log.debug(f"[{self.name}] Could not load '{form}' for {key}; ejecting and releasing.")
                self._eject_chamber()
                self._release(key)
                return False

        self._claim(key, "running", curr_tick)
        try:
            result = self.maker.combine(blend)
        except ValueError as e:
            self.log.level("error").print(f"[{self.name}] combine({blend}) rejected: {e}")
            self._eject_chamber()
            self._release(key)
            return False

        status = getattr(result, "status", "")
        if status == "seed_found":
            species = getattr(result, "species", "?")
            self._last_result = f"{key} -> {species}"
            self.log.color("#7CFC00").print(f"[{self.name}] NEW SEED: {key} -> '{species}' ({getattr(result, 'seed_id', '')}).")
            try:
                notify(f"Seed Maker found '{species}' ({key})", level="info", duration_seconds=8.0)
            except Exception:
                pass
        elif status == "sludge":
            self._last_result = f"{key} -> sludge"
            self.log.print(f"[{self.name}] {key} -> sludge.")
        else:
            self.log.level("warn").print(f"[{self.name}] combine({key}) -> {status}: {getattr(result, 'message', '')}")
            self._eject_chamber()
            self._release(key)
            return False

        self._mark_tried([key])
        self._trials_this_run += 1
        return True

    def _recover(self, curr_tick):
        """
        After a restart: wait out a running trial, then settle any claim this
        maker still holds. A "running" claim with an empty chamber means the
        trial completed (hits land in recipes() anyway) -> mark tried. A
        loaded chamber is re-combined if it matches an open/own triple, else
        returned to storage. A "loading" claim is released.
        """
        while self._safe_is_running():
            sleep(0.5)
        self._drain_output()
        self._refresh_tried()

        chamber = self._chamber()
        own = self._own_claims()
        forms = sorted(chamber.keys())
        if len(forms) == 3 and all(chamber[f] == 1 for f in forms):
            key = combo_key(*forms)
            if self._is_open(key, curr_tick, allow_own_claim=True) and self._claim(key, "loading", curr_tick):
                self.log.print(f"[{self.name}] Resuming loaded triple {key}.")
                self._run_trial(key, forms, curr_tick)
                own.pop(key, None)
            else:
                self._eject_chamber()
        elif chamber:
            self._eject_chamber()

        finished = [k for k, e in own.items() if e.get("stage") == "running"]
        if finished:
            self.log.debug(f"[{self.name}] Marking {len(finished)} interrupted running trial(s) as tried: {finished}")
            self._mark_tried(finished)
        for k, e in own.items():
            if e.get("stage") != "running":
                self._release(k)

    def _safe_is_running(self):
        try:
            return bool(self.maker.is_running())
        except Exception:
            return False

    # -------------------------------------------------------------- loop

    def step(self):
        curr_tick = _now_tick()
        if not self._drain_output():
            self.log.debug(f"[{self.name}] Result bay still holds a seed; waiting for room.")
            return IDLE_POLL_SECONDS

        recipes = self._recipes()
        saturated = self._saturated_forms(recipes)
        known = [combo_key(*r.blend) for r in recipes if getattr(r, "blend", None)]
        if any(self._tried.get(k) is not True for k in known):
            self._mark_tried(known)

        if len(recipes) >= SEED_SPECIES_TOTAL:
            logistics_requests.clear_requests(REQUESTER_ID)
            self._publish_status("done", recipes, saturated, 0)
            self.log.print(f"[{self.name}] All {SEED_SPECIES_TOTAL} seed recipes known; sweep finished.")
            return DONE_POLL_SECONDS

        stock = self._local_stock()
        open_total = self._publish_requests(saturated, stock, curr_tick)

        key, blend = self._pick_triple(stock, saturated, curr_tick)
        if key is None or blend is None:
            if open_total is None:
                open_total = self._publish_requests(saturated, stock, curr_tick, force=True)
            if open_total == 0:
                logistics_requests.clear_requests(REQUESTER_ID)
                self._publish_status("exhausted", recipes, saturated, 0)
                self.log.level("warn").print(f"[{self.name}] Every viable triple tried with only {len(recipes)}/{SEED_SPECIES_TOTAL} recipes found.")
                return DONE_POLL_SECONDS
            in_stock = sorted(f for f in self.forms if stock.get(f, 0) >= 1 and f not in saturated)
            self.log.debug(f"[{self.name}] No open triple from local stock ({len(in_stock)} form(s) on hand: {in_stock}); waiting for deliveries.")
            self._publish_status("waiting_material", recipes, saturated, open_total if open_total is not None else -1)
            return IDLE_POLL_SECONDS

        self.log.debug(f"[{self.name}] Picked {key} (stock {[stock.get(f, 0) for f in blend]}, min={min(stock.get(f, 0) for f in blend)}).")
        if not self._claim(key, "loading", curr_tick):
            self.log.debug(f"[{self.name}] Lost claim on {key} to a peer; re-picking.")
            return 0.5

        self._run_trial(key, blend, curr_tick)
        self._drain_output()
        self._publish_status("running", self._recipes(), saturated, open_total if open_total is not None else -1)
        return 0.0

    def run(self):
        self.log.print(f"Seed Maker Controller ({self.name}) online at '{self.outpost_id}'. {len(self.forms)} life forms known.")
        validate_game_version()
        if not self.forms:
            self.log.level("error").print(f"[{self.name}] life_forms() returned nothing; is Seed Maker research unlocked?")
        try:
            self._recover(_now_tick())
        except Exception as e:
            self.log.level("error").print(f"[{self.name}] Recovery failed: {e}")
        while True:
            try:
                delay = self.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Seed Maker exception: {e}")
                delay = IDLE_POLL_SECONDS
            if delay:
                sleep(delay)
