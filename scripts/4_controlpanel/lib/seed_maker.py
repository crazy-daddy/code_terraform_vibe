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
# State (Data Archive, one shared dict -- CODE_GUIDES.md#archive):
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
# hauler (hauler-role Pioneer with HOME_BASE at this outpost) and
# demand-aware miner drones act on.

import logistics_requests
import stock_scan
from archive import archive
from atomic import run_chunked
from game_clock import is_fresh, now_tick
from machine_controller import port_counts
from priority import NEED
from storage import best_unload_target, drain_port_inventory_first, take_item
from swallow import swallowed
from tree_console import TreeConsole, flush_all, reset_all
from version_guard import validate_game_version

TRIED_KEY = "seed.combos_tried"
STATUS_KEY = "seed_maker.status"
REFRESH_KEY = "seed_maker.refresh"
REQUESTER_ID = "seed_maker"

SEED_SPECIES_TOTAL = 15  # docs/types/biosphere.md SeedRecipe.seed_id possible values
MAX_RECIPES_PER_FORM = 4  # generator cap per life form (see module docstring)
SEED_STASH_TARGET_T = 60  # per-form stock requested at the Seed Maker outpost (capped by open triples left)
SEED_CLAIM_STALE_TICKS = 3000  # ~5 min; a claim older than this is free again
REQUEST_REFRESH_TICKS = 1200  # recompute requests at most this often (~2 min); plus
# logistics_requests.REPUBLISH_TICKS it must stay below REQUEST_STALE_TICKS.
# One maker per outpost refreshes (REFRESH_KEY); its peers reuse that open count.
STATUS_REFRESH_TICKS = 1200  # republish an unchanged status at most this often (archive.STATUS_STALE_TICKS bounds it)
IDLE_POLL_SECONDS = 10.0  # nothing to try / waiting for material
DONE_POLL_SECONDS = 120.0  # all species found
PICK_CHUNK = 150  # triple checks per lib/atomic.py call of the pick (_pick_chunk()): ~7.8k CPython opcodes, under the 10,000-step cap
# A Warehouse runs one transfer at a time and answers others "busy"; makers
# sharing the outpost's Warehouses collide on ~4% of loads. Retry those
# instead of aborting the trial (eject + release) on the first one.
LOAD_BUSY_RETRIES = 4
LOAD_BUSY_WAIT_S = 1.0
CLAIM_ATTEMPTS = 4
# Stage A reuses its stock scan between trials (each trial subtracts its 3 t);
# a full rescan cost ~13 ticks per trial. Rescanned this often, or after a
# load failure. Loads go straight to the holder the scan saw (_load_direct()).
STOCK_REFRESH_TICKS = 300
DIRECT_LOAD_KINDS = (stock_scan.INVENTORY, stock_scan.WAREHOUSE, stock_scan.BIN)  # picks per step when peers claim the same max-min triple first


def combo_key(*trio):
    return ",".join(sorted(trio))


def _owned_by(entry, maker_name):
    return isinstance(entry, dict) and entry.get("by") == maker_name


def _claim_is_live(entry, curr_tick):
    return is_fresh(entry, curr_tick, SEED_CLAIM_STALE_TICKS)


def _pick_chunk(state):
    """
    run_chunked() step of SeedMakerController._pick_triple(): up to PICK_CHUNK
    triple checks in (k, i, j) order from state["pos"]; a triple is open when
    untried and not under a live claim. Done (True) when one is found
    (state["found"]) or every triple is checked. Pure.
    """
    ranked, tried, tick = state["ranked"], state["tried"], state["tick"]
    n = len(ranked)
    k, i, j = state["pos"]
    budget = PICK_CHUNK
    while k < n:
        while i < k - 1:
            while j < k:
                key = combo_key(ranked[i], ranked[j], ranked[k])
                entry = tried.get(key)
                if entry is None or (entry is not True and not _claim_is_live(entry, tick)):
                    state["found"] = (key, [ranked[i], ranked[j], ranked[k]])
                    return True
                j += 1
                budget -= 1
                if budget <= 0:
                    state["pos"] = (k, i, j)
                    return False
            i += 1
            j = i + 1
        k += 1
        i, j = 0, 1
    return True


class SeedMakerController:
    """Runs untried life-form triples through a Seed Maker until every species is discovered."""

    def __init__(self, maker):
        self.maker = maker
        self.name = getattr(maker, "id", "seed_maker")
        self.outpost = getattr(maker, "outpost", None)
        self.outpost_id = getattr(self.outpost, "id", None)
        self.log = TreeConsole(module="seed_maker")
        self.forms = self._read_life_forms()
        self._tried = {}  # local mirror of TRIED_KEY, refreshed by every transaction
        self._last_request_tick = -REQUEST_REFRESH_TICKS
        self._last_open_total = None
        self._last_status = None  # (state, found) of the last status written
        self._last_status_tick = -STATUS_REFRESH_TICKS
        self._scan = None  # stock_scan.StockScan of the last _local_stock(), for _load_direct()
        self._stock = None  # stage A's cached {form: t} (_cached_stock())
        self._stock_tick = -STOCK_REFRESH_TICKS
        self._last_result = ""
        self._trials_this_run = 0

    # ------------------------------------------------------------- reading

    def _read_life_forms(self):
        try:
            return sorted(self.maker.life_forms())
        except Exception as error:
            swallowed("seed_maker.SeedMakerController._read_life_forms: self.maker.life_forms", error)
            return []

    def _recipes(self):
        try:
            return list(self.maker.recipes())
        except Exception as error:
            swallowed("seed_maker.SeedMakerController._recipes: self.maker.recipes", error)
            return []

    def _chamber(self):
        """{item_id: units} currently loaded in the reaction chamber."""
        return port_counts(getattr(self.maker, "input", None), "seed_maker.SeedMakerController._chamber")

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
        """{form: t} held at the outpost (logistics_requests.outpost_stock()); keeps the scan for _load_direct()."""
        if self.outpost is None:
            self._scan = None
            return {form: 0 for form in self.forms}
        self._scan = stock_scan.scan(self.outpost)
        return self._scan.totals(stock_scan.HELD, self.forms)

    def _cached_stock(self, curr_tick):
        """Stage A's stock: the last scan less the trials since, rescanned every STOCK_REFRESH_TICKS or when dropped (self._stock = None)."""
        if self._stock is None or curr_tick - self._stock_tick >= STOCK_REFRESH_TICKS:
            self._stock = self._local_stock()
            self._stock_tick = curr_tick
        return self._stock

    def _load_direct(self, item_id):
        """1 t of item_id from a store the last scan saw holding it, skipping take_item()'s holder search. False: fall back."""
        if self._scan is None:
            return False
        port = self.maker.input
        for store_id, _units in self._scan.holders(item_id, DIRECT_LOAD_KINDS):
            try:
                if not hasattr(port, "connected_id") or port.connected_id() != store_id:
                    if getattr(port.connect(store_id), "status", None) != "ok":
                        continue
                res = port.take(item_id, 1)
            except Exception as error:
                swallowed("seed_maker.SeedMakerController._load_direct: port.take", error)
                continue
            if (getattr(res, "moved", 0) or 0) >= 1:
                return True
        return False

    def _load_one(self, item_id):
        """Takes 1 t of item_id into the chamber: the scanned holder first, else local Warehouses/Inventory, else a local Drone Depot."""
        if self._load_direct(item_id):
            return True
        port = self.maker.input
        for attempt in range(LOAD_BUSY_RETRIES + 1):
            report = {}
            if take_item(port, item_id, 1, outpost=self.outpost, report=report) >= 1:
                return True
            if logistics_requests.take_from_depots(port, item_id, 1, self.outpost) >= 1:
                return True
            if attempt == LOAD_BUSY_RETRIES or not any(status == "busy" for _source, status, _moved in report.get("sources", [])):
                return False
            flush_all()
            sleep(LOAD_BUSY_WAIT_S)
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

    def _output_count(self):
        """Seeds waiting in the output bin, None when unreadable."""
        try:
            return int(self.maker.get_output_count())
        except Exception as error:
            swallowed("seed_maker.SeedMakerController._output_count: self.maker.get_output_count", error)
            return None

    def _drain_output(self):
        """Sends a waiting seed to home Inventory (where planting starts), else to local storage. True once the output bin is empty."""
        if not self._output_count():
            return True
        for item_id, moved, destination, status, message in drain_port_inventory_first(self.maker.output, outpost=self.outpost):
            if moved > 0:
                self.log.print(f"[{self.name}] Seed '{item_id}' sent to {destination}.")
            else:
                self.log.debug(f"[{self.name}] Seed '{item_id}' not drained: {status} {message}")
        return self._output_count() == 0

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
        # The walk runs as lib/atomic.py chunks: in plain steps it took ~19 ticks
        # once the top-ranked triples were mostly tried.
        state = {"ranked": ranked, "tried": self._tried, "tick": curr_tick, "pos": (2, 0, 1), "found": None}
        run_chunked(_pick_chunk, state)
        return state["found"] or (None, None)

    def _claim_pick(self, stock, saturated, curr_tick):
        """
        _pick_triple() and claim it ("loading"), up to CLAIM_ATTEMPTS picks: a
        lost claim's transaction already refreshed `_tried`, so the next pick
        skips the peer's triple within the same step. Returns (key, blend),
        (None, None) with no open triple, or ("", None) when every attempt lost.
        """
        for _ in range(CLAIM_ATTEMPTS):
            key, blend = self._pick_triple(stock, saturated, curr_tick)
            if key is None or blend is None:
                return None, None
            self.log.debug(f"[{self.name}] Picked {key} (stock {[stock.get(f, 0) for f in blend]}, min={min(stock.get(f, 0) for f in blend)}).")
            if self._claim(key, "loading", curr_tick):
                return key, blend
            self.log.debug(f"[{self.name}] Lost claim on {key} to a peer; re-picking.")
        return "", None

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
        for key, entry in self._tried.items():
            # Open as _is_open(allow_own_claim=True): only tried and live peer claims close a triple.
            if entry is not True and (_owned_by(entry, self.name) or not _claim_is_live(entry, curr_tick)):
                continue
            members = key.split(",")
            if len(members) != 3 or not all(m in viable_set for m in members):
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
        if not force and not self._take_refresh(curr_tick):
            return self._last_open_total
        counts, total = self._open_combo_counts(saturated, curr_tick)
        targets = {f: min(SEED_STASH_TARGET_T, n) for f, n in counts.items() if n > 0}
        wants = {f: ([[NEED, t]], stock.get(f, 0)) for f, t in targets.items()}
        # Seed forms take an item from other requesters (the Feed Makers yield it).
        if self.outpost_id:
            logistics_requests.publish_requests(self.outpost_id, REQUESTER_ID, wants, curr_tick, skip_foreign=False)
        short = sorted(f for f, t in targets.items() if stock.get(f, 0) < t)
        missing = sum(max(0, t - stock.get(f, 0)) for f, t in targets.items())
        self.log.debug(f"[{self.name}] requests: {len(wants)} form(s) still in open triples ({total} open), {len(short)} below target ({missing} t missing): {short}")
        self._last_open_total = total
        self._store_refresh(curr_tick, total)
        return total

    def _take_refresh(self, curr_tick):
        """
        True when this maker should recompute the outpost's requests: no peer
        at the outpost refreshed within REQUEST_REFRESH_TICKS. A peer's
        refresh publishes the same outpost-wide request (same stock, same
        shared tried dict), so its open-triple count is reused instead.
        """
        if not self.outpost_id:
            return True
        won = []
        peer = []

        def updater(entries):
            if not isinstance(entries, dict):
                entries = {}
            entry = entries.get(self.outpost_id)
            if isinstance(entry, dict) and entry.get("by") != self.name and is_fresh(entry, curr_tick, REQUEST_REFRESH_TICKS):
                peer.append(entry)
                return entries
            entries[self.outpost_id] = {"by": self.name, "tick": curr_tick, "open": entry.get("open") if isinstance(entry, dict) else None}
            won.append(True)
            return entries

        archive.transaction(REFRESH_KEY, {}, updater)
        if peer:
            if isinstance(peer[0].get("open"), int):
                self._last_open_total = peer[0]["open"]
            return False
        return bool(won)

    def _store_refresh(self, curr_tick, total):
        """Records this maker's open-triple count for its peers (_take_refresh())."""
        if not self.outpost_id:
            return

        def updater(entries):
            if not isinstance(entries, dict):
                entries = {}
            entries[self.outpost_id] = {"by": self.name, "tick": curr_tick, "open": total}
            return entries

        archive.transaction(REFRESH_KEY, {}, updater)

    def _clear_requests(self):
        """Withdraws this outpost's REQUESTER_ID requests."""
        if self.outpost_id:
            logistics_requests.clear_requests(REQUESTER_ID, self.outpost_id)

    def _publish_status(self, state, recipes, saturated, open_total):
        """Writes this maker's status entry when its state or found count changed (a new seed), else at most every STATUS_REFRESH_TICKS (the tried count walks the whole tried dict)."""
        tick = now_tick()
        shown = (state, len(recipes))
        if shown == self._last_status and tick - self._last_status_tick < STATUS_REFRESH_TICKS:
            return
        self._last_status = shown
        self._last_status_tick = tick
        tried_count = sum(1 for v in self._tried.values() if v is True)
        entry = {
            "state": state,
            "found": len(recipes),
            "tried": tried_count,
            "open": open_total,
            "saturated": sorted(saturated),
            "last": self._last_result,
        }
        archive.publish_status(STATUS_KEY, self.name, entry, tick, self.log)

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
            except Exception as error:
                swallowed("seed_maker.SeedMakerController._run_trial: notify", error)
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
            flush_all()
            sleep(0.5)
        self._drain_output()
        self._refresh_tried()

        chamber = self._chamber()
        own = self._own_claims()
        forms = sorted(chamber.keys())
        if len(forms) == 3 and all(chamber[f] == 1 for f in forms):
            key = combo_key(*forms)
            if self._is_open(key, curr_tick, allow_own_claim=True) and self._claim(key, "loading", curr_tick):
                self.log.start(f"[{self.name}] Resuming loaded triple {key}.")
                consumed = self._run_trial(key, forms, curr_tick)
                self.log.end(f"[{self.name}] Resumed triple {key} {'consumed' if consumed else 'aborted, triple released'}")
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
        except Exception as error:
            swallowed("seed_maker.SeedMakerController._safe_is_running: self.maker.is_running", error)
            return False

    # -------------------------------------------------------------- loop

    def step(self):
        curr_tick = now_tick()
        if not self._drain_output():
            self.log.debug(f"[{self.name}] Result bay still holds a seed; waiting for room.")
            return IDLE_POLL_SECONDS

        recipes = self._recipes()
        saturated = self._saturated_forms(recipes)
        known = [combo_key(*r.blend) for r in recipes if getattr(r, "blend", None)]
        if any(self._tried.get(k) is not True for k in known):
            self._mark_tried(known)

        if len(recipes) >= SEED_SPECIES_TOTAL:
            self._clear_requests()
            self._publish_status("done", recipes, saturated, 0)
            self.log.print(f"[{self.name}] All {SEED_SPECIES_TOTAL} seed recipes known; sweep finished.")
            return DONE_POLL_SECONDS

        stock = self._cached_stock(curr_tick)
        open_total = self._publish_requests(saturated, stock, curr_tick)

        # Peers' claims since this maker's last transaction: without them every
        # maker picks the same max-min triple and all but one lose the claim.
        self._refresh_tried()
        key, blend = self._claim_pick(stock, saturated, curr_tick)
        if key == "":
            return 0.5
        if key is None or blend is None:
            self._stock = None  # rescan on the next poll: deliveries land between scans
            if open_total is None:
                open_total = self._publish_requests(saturated, stock, curr_tick, force=True)
            if open_total == 0:
                self._clear_requests()
                self._publish_status("exhausted", recipes, saturated, 0)
                self.log.level("warn").print(f"[{self.name}] Every viable triple tried with only {len(recipes)}/{SEED_SPECIES_TOTAL} recipes found.")
                return DONE_POLL_SECONDS
            in_stock = sorted(f for f in self.forms if stock.get(f, 0) >= 1 and f not in saturated)
            self.log.debug(f"[{self.name}] No open triple from local stock ({len(in_stock)} form(s) on hand: {in_stock}); waiting for deliveries.")
            self._publish_status("waiting_material", recipes, saturated, open_total if open_total is not None else -1)
            return IDLE_POLL_SECONDS

        self.log.start(f"[{self.name}] Trial {key}")
        consumed = self._run_trial(key, blend, curr_tick)
        if consumed:
            for form in blend:
                stock[form] = max(0, stock.get(form, 0) - 1)
        else:
            self._stock = None
        self._drain_output()
        self.log.end(f"[{self.name}] Trial {key} {'consumed' if consumed else 'aborted, triple released'}")
        self._publish_status("running", self._recipes(), saturated, open_total if open_total is not None else -1)
        return 0.0

    def run(self):
        self.log.print(f"Seed Maker Controller ({self.name}) online at '{self.outpost_id}'. {len(self.forms)} life forms known.")
        validate_game_version()
        if not self.forms:
            self.log.level("error").print(f"[{self.name}] life_forms() returned nothing; is Seed Maker research unlocked?")
        try:
            self._recover(now_tick())
        except Exception as e:
            self.log.level("error").print(f"[{self.name}] Recovery failed: {e}")
        while True:
            reset_all()
            try:
                delay = self.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Seed Maker exception: {e}")
                delay = IDLE_POLL_SECONDS
            if delay:
                flush_all()
                sleep(delay)
