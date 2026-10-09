# Pillar swap (warehouse_upgrade_automation.py): replaces every generator of one
# terraforming pillar with the generator of another, one machine at a time.
#
# Operator-triggered only: the PILLAR SWAP strip of the PRODUCTION card
# (production_panel.py) calls request_swap() and request_stop(). Stop lets
# the machine in flight finish, then ends the swap.
#
# One pass runs the whole swap: machine after machine, each state straight
# into the next, until one has to wait (credits, Inventory room, construction).
# Machines go one at a time so Inventory never holds more than one machine's
# kit and packs. Per machine:
#   undeploy -- stop the old script, computer.undeploy(): the kit and every
#               tier pack (Mk II up to its tier) return to Inventory
#   sell     -- sell exactly those items: frees the Inventory slots and pays
#               for the buy
#   buy      -- the target kit and its packs Mk II up to the target tier;
#               spares already in Inventory are used first
#   deploy   -- computer.deploy() at the old machine's outpost, switched on
#   upgrade  -- computer.upgrade() pack by pack up to the target tier
# The new machine lands with no script; filling its slot is up to
# devtools/scripts_sync.py or the operator, not this swap.
# Target tier = the old machine's tier, lowered while its pack is neither in
# the Shop catalogue (tech-gated entries are hidden) nor in Inventory. Mk IV
# machines stay in place: Mk IV packs are crafted, not bought.
# The three pillars' kits and packs cost within 200 cr of each other and sell
# for their Shop price, so the swap pays for itself: it skips the cash
# manager and only checks, before the undeploy, that credits plus the sale
# cover the buy.
#
# State: one dict, pillar.swap (archive_ipc.md §4):
#   {"from": pillar, "to": pillar, "state": "running" | "done" | "stopped" | "blocked",
#    "stop": bool, "job": {...} | None, "done": int, "left": int,
#    "kept": [Mk IV ids], "failed": [ids], "reason": str, "status": str}
#   job = {"old_id", "outpost", "old_tier", "tier", "phase", "sold", "new_id", "known", "attempts"}

from archive import archive
from tree_console import TreeConsole
from components import component
from swallow import swallowed
from script_parking import start_script, set_powered
from storage import inventory_count

SWAP_KEY = "pillar.swap"
IDLE_SUMMARY = "pillar swap idle"

PILLARS = {"o2": "oxygen_generator", "heat": "temp_heater", "pressure": "pressure_generator"}
PILLAR_ORDER = ("o2", "heat", "pressure")
PILLAR_LABELS = {"o2": "O2", "heat": "Heat", "pressure": "Press"}
PACK_FAMILY = {"oxygen_generator": "oxygen", "temp_heater": "heat", "pressure_generator": "pressure"}
MAX_SWAP_TIER = 3

# State steps one pass may run (about 6 per machine); a bound, not a pace.
MAX_STEPS_PER_PASS = 600
# Refused undeploy answers in a row before a machine is skipped (left running).
MAX_ATTEMPTS = 5
# undeploy() answers that only mean "not right now".
TRANSIENT_UNDEPLOY_STATUSES = ("inventory_full",)
# upgrade() answers the upgrade step waits out.
UPGRADE_WAIT_STATUSES = ("under_construction", "not_enough_power", "inventory_full")
# deploy() answers that will not change by retrying: the swap blocks.
FATAL_DEPLOY_STATUSES = ("deploy_limit", "duplicate_outpost_machine", "wrong_biome_for_machine", "location_not_found", "not_deployable", "locked")

log = TreeConsole(module="pillar_swap")


def pack_id(type_id, tier):
    return f"{PACK_FAMILY[type_id]}_upgrade_pack_mk{tier}"


def kit_and_packs(type_id, tier):
    """The kit plus every pack Mk II..tier, in apply order."""
    return [type_id] + [pack_id(type_id, t) for t in range(2, tier + 1)]


def swap_state():
    state = archive.get(SWAP_KEY, None)
    return state if isinstance(state, dict) else None


def _update(mutate):
    def updater(state):
        if not isinstance(state, dict):
            state = {}
        mutate(state)
        return state
    archive.transaction(SWAP_KEY, {}, updater)


def _patch(**fields):
    _update(lambda s: s.update(fields))


def _patch_job(**fields):
    def mutate(s):
        job = s.get("job")
        if isinstance(job, dict):
            job.update(fields)
    _update(mutate)


def is_running():
    swap = swap_state()
    return bool(swap and swap.get("state") == "running")


def request_swap(from_pillar, to_pillar):
    """Starts a swap from_pillar -> to_pillar; False when one is running or the pillars are invalid."""
    if from_pillar not in PILLARS or to_pillar not in PILLARS or from_pillar == to_pillar or is_running():
        return False
    archive.set(SWAP_KEY, {
        "from": from_pillar, "to": to_pillar, "state": "running", "stop": False, "job": None,
        "done": 0, "left": 0, "kept": [], "failed": [], "reason": "", "status": "starting",
    })
    log.print(f"[pillar_swap] Requested: {PILLAR_LABELS[from_pillar]} -> {PILLAR_LABELS[to_pillar]}.")
    return True


def request_stop():
    """Asks a running swap to stop after the machine in flight."""
    if is_running():
        _patch(stop=True)


def panel_status():
    """(state, one-line text) for the PRODUCTION card; state is "" with no swap on record."""
    swap = swap_state()
    if not swap:
        return "", "no swap yet"
    state = str(swap.get("state") or "")
    text = str(swap.get("status") or state)
    if state == "running" and swap.get("stop"):
        text = f"stopping: {text}"
    return state, text


def machine_tier(machine_id):
    """Installed Mk tier of a deployed machine, 1 when unreadable."""
    machine = component(machine_id)
    try:
        return int(machine.tier()) if machine else 1
    except Exception as error:
        swallowed("pillar_swap.machine_tier: machine.tier", error)
        return 1


class PillarSwap:
    """Host-side swap state machine. One instance, reused across passes; all state lives in the archive."""

    def __init__(self):
        self.log = log

    # ------------------------------------------------------------ lookups

    def _outposts(self):
        network = component("outpost_network")
        try:
            return network.outposts() if network else []
        except Exception as error:
            swallowed("pillar_swap._outposts: network.outposts", error)
            return []

    def _ids_at(self, outpost_id, type_id):
        for outpost in self._outposts():
            if getattr(outpost, "id", "") == outpost_id:
                try:
                    return sorted(ref.id for ref in outpost.buildings(type_id))
                except Exception as error:
                    swallowed("pillar_swap._ids_at: outpost.buildings", error)
        return []

    def _machines(self, type_id):
        """[(outpost_id, machine_id)] of every deployed type_id, sorted."""
        found = []
        for outpost in self._outposts():
            try:
                refs = outpost.buildings(type_id)
            except Exception as error:
                swallowed("pillar_swap._machines: outpost.buildings", error)
                continue
            found += [(getattr(outpost, "id", ""), ref.id) for ref in refs]
        return sorted(found)

    def _prices(self):
        shop = component("shop")
        try:
            return {entry.id: int(entry.cost) for entry in shop.get_catalogue()} if shop else {}
        except Exception as error:
            swallowed("pillar_swap._prices: shop.get_catalogue", error)
            return {}

    def _credits(self):
        commander = component("commander")
        try:
            return int(commander.get_credits()) if commander else 0
        except Exception as error:
            swallowed("pillar_swap._credits: commander.get_credits", error)
            return 0

    def _target_tier(self, type_id, tier, prices):
        """tier, lowered while its pack can be neither bought nor taken from Inventory."""
        target = min(tier, MAX_SWAP_TIER)
        while target > 1 and pack_id(type_id, target) not in prices and inventory_count(pack_id(type_id, target)) <= 0:
            target -= 1
        return target

    # ------------------------------------------------------------ main step

    def step(self):
        """One pass. Returns a one-line summary (IDLE_SUMMARY when there is nothing to report)."""
        swap = swap_state()
        if not swap:
            return IDLE_SUMMARY
        state = swap.get("state")
        if state == "blocked":
            return f"pillar swap blocked: {swap.get('reason')}"
        if state != "running":
            return IDLE_SUMMARY
        self.log.start("[pillar_swap] step", level="debug")
        text = self._run(swap)
        self.log.end(text)
        if text != swap.get("status"):
            _patch(status=text)
        return f"pillar swap {PILLAR_LABELS.get(str(swap.get('from')), '?')}->{PILLAR_LABELS.get(str(swap.get('to')), '?')}: {text}"

    def _run(self, swap):
        text = ""
        for _ in range(MAX_STEPS_PER_PASS):
            job = swap.get("job")
            if not job:
                if swap.get("stop"):
                    _patch(state="stopped", status=f"stopped after {swap.get('done', 0)} swapped")
                    self.log.print(f"[pillar_swap] Stopped after {swap.get('done', 0)} machine(s).")
                    return f"stopped after {swap.get('done', 0)} swapped"
                text = self._pick(swap)
            else:
                text = self._advance(swap, job)
            after = swap_state() or {}
            after_job = after.get("job")
            if after.get("state") != "running":
                return text
            if job and after_job and after_job.get("old_id") == job.get("old_id") and after_job.get("phase") == job.get("phase"):
                return text
            if not job and not after_job:
                return text
            swap = after
        return text

    def _pick(self, swap):
        """Writes the next machine's job; finishes the swap when none is left."""
        from_type = PILLARS[swap["from"]]
        to_type = PILLARS[swap["to"]]
        kept = list(swap.get("kept") or [])
        failed = set(swap.get("failed") or [])
        prices = self._prices()
        if to_type not in prices and inventory_count(to_type) <= 0:
            _patch(state="blocked", reason=f"{to_type} not in the Shop")
            return f"blocked: {to_type} not in the Shop"

        candidates = []
        for outpost_id, machine_id in self._machines(from_type):
            if machine_id in failed or machine_id in kept:
                continue
            tier = machine_tier(machine_id)
            if tier > MAX_SWAP_TIER:
                kept.append(machine_id)
                self.log.debug(f"'{machine_id}' is Mk {tier}: kept.")
                continue
            candidates.append((outpost_id, machine_id, tier))
        if kept != list(swap.get("kept") or []):
            _patch(kept=kept)

        if not candidates:
            done = int(swap.get("done") or 0)
            text = f"done: {done} swapped"
            if kept:
                text += f", {len(kept)} Mk IV kept"
            if failed:
                text += f", {len(failed)} failed"
            _patch(state="done", left=0)
            self.log.print(f"[pillar_swap] {PILLAR_LABELS[swap['from']]} -> {PILLAR_LABELS[swap['to']]} {text}.")
            return text

        outpost_id, machine_id, tier = candidates[0]
        target = self._target_tier(to_type, tier, prices)
        gain = sum(prices.get(item, 0) for item in kit_and_packs(from_type, tier))
        cost = sum(prices.get(item, 0) for item in kit_and_packs(to_type, target) if inventory_count(item) <= 0)
        short = cost - gain - self._credits()
        if short > 0:
            self.log.debug(f"'{machine_id}': buy {cost} cr, sale {gain} cr, {short} cr short.")
            return f"{machine_id}: waiting for {short} cr"
        _patch(left=len(candidates), job={
            "old_id": machine_id, "outpost": outpost_id, "old_tier": tier, "tier": target,
            "phase": "undeploy", "sold": [], "new_id": None, "known": [], "attempts": 0,
        })
        self.log.debug(f"Next: '{machine_id}' (Mk {tier}) at '{outpost_id}' -> {to_type} Mk {target}; {len(candidates)} left.")
        return f"{machine_id}: starting ({len(candidates)} left)"

    def _advance(self, swap, job):
        phase = job.get("phase")
        computer = component("computer")
        if not computer or not hasattr(computer, "deploy"):
            return "no Ship Computer"
        from_type = PILLARS[swap["from"]]
        to_type = PILLARS[swap["to"]]
        if phase == "undeploy":
            return self._undeploy(job, computer)
        if phase == "sell":
            return self._sell(job, from_type)
        if phase == "buy":
            return self._buy(job, to_type)
        if phase == "deploy":
            return self._deploy(job, to_type, computer)
        if phase == "upgrade":
            return self._upgrade(job, to_type, computer)
        if phase == "attach":  # retired phase still in a saved job: the machine is already in place
            return self._finish(job, machine_tier(job["new_id"]))
        return f"{job.get('old_id')}: unknown phase {phase!r}"

    # ------------------------------------------------------------ phases

    def _undeploy(self, job, computer: "Computer"):
        old_id = job["old_id"]
        if component(old_id) is None:
            _patch_job(phase="sell")
            return f"{old_id}: gone, selling"
        run = component("run_control")
        try:
            if run:
                run.stop(old_id)
        except Exception as error:
            swallowed("pillar_swap._undeploy: run.stop", error)
        res = computer.undeploy(old_id)
        if res.status == "ok":
            _patch_job(phase="sell")
            self.log.debug(f"[pillar_swap] Undeployed '{old_id}' (Mk {job.get('old_tier')}) at '{job.get('outpost')}'.")
            return f"{old_id}: undeployed"
        if res.status in TRANSIENT_UNDEPLOY_STATUSES:
            return f"{old_id}: undeploy {res.status}, retrying"
        attempts = int(job.get("attempts") or 0) + 1
        if attempts < MAX_ATTEMPTS:
            _patch_job(attempts=attempts)
            return f"{old_id}: undeploy {res.status}, retrying"
        start_script(old_id)

        def skip(s):
            s.setdefault("failed", []).append(old_id)
            s["job"] = None
        _update(skip)
        self.log.level("warn").print(f"[pillar_swap] undeploy('{old_id}') refused {attempts}x ({res.status}: {res.message}); left running, skipped.")
        return f"{old_id}: skipped ({res.status})"

    def _sell(self, job, from_type):
        """Sells the kit and packs the undeploy returned (each once, also across a restart)."""
        old_id = job["old_id"]
        shop = component("shop")
        sold = list(job.get("sold") or [])
        for item in kit_and_packs(from_type, int(job.get("old_tier") or 1)):
            if item in sold or inventory_count(item) <= 0:
                continue
            res = shop.sell(item, 1) if shop else None
            if res is not None and res.status == "ok":
                sold.append(item)
                _patch_job(sold=sold)
                self.log.debug(f"Sold {item} for {res.credits} cr.")
            else:
                self.log.debug(f"sell('{item}'): {getattr(res, 'status', 'no_shop')}; kept in Inventory.")
        _patch_job(phase="buy")
        return f"{old_id}: sold {len(sold)} item(s)"

    def _buy(self, job, to_type):
        old_id = job["old_id"]
        shop = component("shop")
        for item in kit_and_packs(to_type, int(job.get("tier") or 1)):
            if inventory_count(item) > 0:
                continue
            res = shop.buy(item, 1) if shop else None
            status = getattr(res, "status", "no_shop")
            if status != "ok":
                self.log.debug(f"buy('{item}'): {status} - {getattr(res, 'message', '')}")
                return f"{old_id}: buy {item} {status}, retrying"
            self.log.debug(f"Bought {item}.")
        if job.get("new_id"):
            _patch_job(phase="upgrade")
        else:
            _patch_job(phase="deploy", known=self._ids_at(job["outpost"], to_type))
        return f"{old_id}: bought"

    def _deploy(self, job, to_type, computer: "Computer"):
        old_id = job["old_id"]
        outpost_id = job["outpost"]
        known = set(job.get("known") or [])
        new_id = next((i for i in self._ids_at(outpost_id, to_type) if i not in known), None)
        if new_id is None:
            res = computer.deploy(to_type, outpost_id)
            if res.status != "ok":
                if res.status in FATAL_DEPLOY_STATUSES:
                    _patch(state="blocked", reason=f"deploy at {outpost_id}: {res.status}")
                    self.log.level("warn").print(f"[pillar_swap] deploy('{to_type}', '{outpost_id}') refused ({res.status}: {res.message}); swap blocked.")
                    return f"{old_id}: blocked ({res.status})"
                if res.status == "no_kit":
                    _patch_job(phase="buy")
                return f"{old_id}: deploy {res.status}, retrying"
            new_id = res.machine_id
        set_powered(component("power_control"), new_id, True, self.log)
        _patch_job(phase="upgrade", new_id=new_id)
        self.log.debug(f"[pillar_swap] Deployed '{new_id}' at '{outpost_id}' replacing '{old_id}'.")
        return f"{old_id}: deployed {new_id}"

    def _upgrade(self, job, to_type, computer: "Computer"):
        new_id = job["new_id"]
        target = int(job.get("tier") or 1)
        tier = machine_tier(new_id)
        while tier < target:
            pack = pack_id(to_type, tier + 1)
            res = computer.upgrade(pack, new_id)
            if res.status == "ok":
                tier += 1
                self.log.debug(f"Upgraded '{new_id}' to Mk {tier}.")
                continue
            if res.status in UPGRADE_WAIT_STATUSES:
                return f"{new_id}: upgrade {res.status}, waiting"
            if res.status == "item_not_in_inventory":
                _patch_job(phase="buy")
                return f"{new_id}: {pack} missing, buying"
            self.log.level("warn").print(f"[pillar_swap] upgrade('{pack}', '{new_id}') refused ({res.status}: {res.message}); stays Mk {tier}.")
            break
        return self._finish(job, tier)

    def _finish(self, job, tier):
        new_id = job["new_id"]

        def finish(s):
            s["done"] = int(s.get("done") or 0) + 1
            s["left"] = max(0, int(s.get("left") or 0) - 1)
            s["job"] = None
        _update(finish)
        self.log.debug(f"[pillar_swap] Swap done: '{job['old_id']}' -> '{new_id}' (Mk {tier}).")
        return f"{job['old_id']} -> {new_id} done"
