# Fleet commissioning coordinator: launches new Pioneers and drones queued on
# the COMMISSION card (control_panel/fleet_commission_panel.py). Run by the
# headless control_room_automation.py every storage tick. Operator-triggered only:
# nothing is queued here on its own.
#
# Pioneer and drone jobs are separate queues in one list,
# fleet.commission["jobs"] (layout in lib/pioneer_commission.py): each pass
# works the first non-blocked job of each kind, so a drone waiting on the
# Fabricator doesn't hold up a Pioneer. Each pass re-reads the dict, advances
# a job until a state has to wait (MAX_ADVANCES_PER_PASS at most), writing
# back after each state, so a restart resumes where it stopped. While a head
# job is in a quick state (FAST_STATES), control_room_automation steps the
# coordinator every COMMISSION_FAST_TICK_INTERVAL, not only every storage tick.
#
# Pioneer (always deployed at the home outpost, where its parts are; the job's
# home_base becomes its HOME_BASE):
#   queued    -> spec built from the role preset at the best unlocked tiers
#                (Shop catalogue); a locked part blocks the job
#   buying    -> buys the chassis and every part the Inventory doesn't already
#                hold, all at once, once the cash manager grants the whole
#                cost (lib/cash.py can_spend("pioneer_commission"))
#   deploying -> snapshot of owned Pioneers first (a restart adopts a new one
#                instead of deploying twice), then computer.deploy("pioneer")
#                at home; lineage[new_id] carries home_base for scripts_sync
#   attach    -> a deployed machine has no script and scripts cannot attach
#                one: waits for devtools/scripts_sync.py (or the operator) to
#                fill the slot, retrying run_control.start() until the
#                Pioneer reports in fleet.status
#   fitting   -> the Pioneer mounts/installs its own parts
#                (PioneerFittingMixin); parts it reports missing are bought.
#                Done once fitted and its fleet.status "home" is the job's
#                home_base
#
# Drone (lib/drone_commission.py; crafted, not bought; deployed at the job's
# outpost, which needs a Drone Depot):
#   queued    -> spec: best craftable chassis + LOADOUTS modules
#   crafting  -> kit ordered via fabricator.upgrade_orders until Inventory
#                holds all of it. A part a remote fab site built reaches
#                home Inventory through site supply's home pull request
#                (lib/site_supply.py consumer_wants()) and a hauler serving
#                home; the status splits "crafting" from "awaiting haul
#                home", and warns once per job when built parts sat
#                unhauled for HAUL_HOME_WARN_TICKS
#   deploying -> waits while a fleet_upgrade drone swap is deploying (both
#                adopt "the new drone"), snapshots owned drones, then
#                computer.deploy(chassis, outpost); a full Depot waits;
#                fleet.upgrade lineage[new_id] = {"job", role, engine, kind,
#                params: {HOME_DEPOT}, fitted: False}
#   attach    -> as for Pioneers
#   fitting   -> the drone couples its kit (fit_loadout_if_new()); done once
#                its lineage says fitted
#
#   blocked   -> refused for good (locked part, deploy_limit, vehicle gone);
#                skipped by later passes until the operator cancels it on the
#                card. Bought or crafted parts stay in Inventory and are
#                reused by the next job.

import fleet_status
from pioneer_commission import PIONEER_KIT_ID, commission_state, update_commission, build_spec, spec_parts
from drone_commission import COMMISSION_REQUESTER, build_drone_spec, drone_spec_parts, drone_craft_parts, drone_buy_parts
from drone_upgrade import fleet_upgrade_state, update_fleet_upgrade
from production import set_upgrade_order, fabricator_unlocked_outputs, home_outpost_id, SourceCache
from logistics_requests import in_flight, REQUEST_STALE_TICKS
from outpost_mining import HOME_OUTPOST_ID
import cash
from tree_console import TreeConsole
from swallow import swallowed
from script_parking import start_script
from storage import inventory_count

# lib/cash.py consumer ids, one per job kind.
CASH_CONSUMERS = {"pioneer": "pioneer_commission", "drone": "drone_commission"}

# States the COMMISSION card may cancel: nothing deployed yet (or given up).
CANCELLABLE_STATES = ("queued", "buying", "crafting", "blocked")
DEPLOY_BLOCKING_STATUSES = ("deploy_limit", "location_not_found", "not_deployable", "locked", "wrong_biome_for_machine", "missing_drone_station")
# fleet_upgrade drone swap states between "about to deploy" and "adopted".
SWAP_DEPLOYING_STATES = ("announced", "swapping")
JOB_KINDS = ("pioneer", "drone")
# Head-job states that end within seconds (no Fabricator, cash or Pioneer drive to wait on), per kind.
# While a head job sits in one, control_room_automation steps the coordinator on its fast cadence.
FAST_STATES = {"pioneer": ("queued", "deploying", "attach"), "drone": ("queued", "deploying", "attach", "fitting")}
# Advances per job per pass: queued -> crafting -> deploying -> attach -> script start fit in one pass
# when the kit is already in Inventory.
MAX_ADVANCES_PER_PASS = 5
# Built kit parts that sat outside Inventory this long with nothing in flight
# home get one warning per job: no hauler serves home.
HAUL_HOME_WARN_TICKS = REQUEST_STALE_TICKS


def _component(component_id):
    try:
        return get_component(component_id)
    except Exception as error:
        swallowed("fleet_commission._component: get_component", error)
        return None


def job_kind(job):
    """"pioneer" or "drone" (jobs queued before drones existed carry no kind)."""
    return "drone" if job.get("kind") == "drone" else "pioneer"


def job_home_base(job):
    """A Pioneer job's HOME_BASE outpost id, None = home."""
    return job.get("home_base", job.get("outpost"))


def _queue(kind, role, fields):
    created = []

    def mutate(state):
        seq = int(state.get("seq", 0)) + 1
        state["seq"] = seq
        created[:] = [f"{kind[0]}{seq}"]
        job = {"id": created[0], "kind": kind, "role": role, "state": "queued"}
        job.update(fields)
        state.setdefault("jobs", []).append(job)
    update_commission(mutate)
    return created[0] if created else ""


def commission_fast():
    """True while the head job of a kind sits in one of its FAST_STATES."""
    jobs = [j for j in commission_state().get("jobs") or [] if isinstance(j, dict)]
    for kind in JOB_KINDS:
        head = next((j for j in jobs if job_kind(j) == kind and j.get("state") != "blocked"), None)
        if head is not None and head.get("state") in FAST_STATES[kind]:
            return True
    return False


def queue_pioneer(role, home_base=None):
    """Appends a Pioneer job (COMMISSION card button); it deploys at home and works for home_base. Returns the job id."""
    return _queue("pioneer", role, {"home_base": None if home_base == HOME_OUTPOST_ID else home_base})


def queue_drone(role, outpost_id=None):
    """Appends a drone job (COMMISSION card button); it deploys at outpost_id (None = home). Returns the job id."""
    return _queue("drone", role, {"outpost": None if outpost_id == HOME_OUTPOST_ID else outpost_id})


def cancel_job(job_id):
    """Drops a job that hasn't deployed anything (CANCELLABLE_STATES). Returns True if dropped."""
    dropped = []

    def mutate(state):
        jobs = state.get("jobs") or []
        keep = [j for j in jobs if not (j.get("id") == job_id and j.get("state") in CANCELLABLE_STATES)]
        dropped[:] = [len(keep) != len(jobs)]
        state["jobs"] = keep
    update_commission(mutate)
    return bool(dropped and dropped[0])


class FleetCommissionCoordinator:
    """Host-side state machine for new Pioneers. One instance, reused across cycles."""

    def __init__(self):
        self.log = TreeConsole(module="fleet_commission")
        self._tick = 0
        # {job_id: first tick built parts waited unhauled}; a job id in
        # _haul_warned got its warning already.
        self._unhauled_since = {}
        self._haul_warned = set()

    # ------------------------------------------------------------ lookups

    def _catalogue(self):
        shop = _component("shop")
        try:
            return {entry.id: entry.cost for entry in shop.get_catalogue()} if shop else {}
        except Exception as error:
            swallowed("fleet_commission.FleetCommissionCoordinator._catalogue: shop.get_catalogue", error)
            return {}

    def _credits(self):
        commander = _component("commander")
        try:
            return int(commander.get_credits()) if commander else 0
        except Exception as error:
            swallowed("fleet_commission.FleetCommissionCoordinator._credits: commander.get_credits", error)
            return 0

    def _kit_wait_text(self, job_id, label, short):
        """
        Status for a drone kit not yet all in Inventory: parts still to craft
        vs parts already built elsewhere on the network (a remote fab site's
        Warehouse, a home Warehouse before the reclaim sweep, a hauler's
        cargo) awaiting the trip home. Warns once per job when built parts sit
        HAUL_HOME_WARN_TICKS with nothing in flight home.
        """
        cache = SourceCache()
        built = {}
        for item_id, n in short.items():
            elsewhere = cache.network_stock(item_id) - inventory_count(item_id)
            if elsewhere > 0:
                built[item_id] = min(n, elsewhere)
        crafting = {i: n - built.get(i, 0) for i, n in short.items() if n - built.get(i, 0) > 0}
        coming = in_flight(home_outpost_id(), self._tick) if built else {}
        hauling = {i: min(n, coming.get(i, 0)) for i, n in built.items() if coming.get(i, 0) > 0}
        waiting = {i: n - hauling.get(i, 0) for i, n in built.items() if n - hauling.get(i, 0) > 0}
        self.log.debug(f"{label}: short {short} -> to craft {crafting}, built elsewhere {built}, in flight home {hauling}.")

        if waiting and not hauling:
            since = self._unhauled_since.setdefault(job_id, self._tick)
            if self._tick - since >= HAUL_HOME_WARN_TICKS and job_id not in self._haul_warned:
                self._haul_warned.add(job_id)
                self.log.level("warn").print(f"[fleet_commission] {label}: {waiting} built but not hauled home for {self._tick - since} ticks. Home needs a pull hauler (Pioneer based at home) or a Drone Depot for floating drone haulers.")
        else:
            self._unhauled_since.pop(job_id, None)

        def fmt(parts):
            return ", ".join(f"{n}x {i}" for i, n in parts.items())
        texts = [f"crafting ({fmt(crafting)})"] if crafting else []
        texts += [f"hauling home ({fmt(hauling)})"] if hauling else []
        texts += [f"built, awaiting haul home ({fmt(waiting)})"] if waiting else []
        return f"{label}: {'; '.join(texts)}"

    def _pioneers(self):
        """Sorted ids of every owned Pioneer, or None when the fleet can't be read."""
        fleet = _component("fleet")
        if not fleet:
            return None
        try:
            return sorted(getattr(v, "id", "") for v in fleet.vehicles() if getattr(v, "kind", "") == "pioneer" and getattr(v, "id", ""))
        except Exception as error:
            swallowed("fleet_commission.FleetCommissionCoordinator._pioneers: fleet.vehicles", error)
            return None

    def _drones(self):
        """{drone_id: chassis kind} of every owned drone, or None when the fleet can't be read."""
        fleet = _component("fleet")
        if not fleet:
            return None
        try:
            return {getattr(d, "id", ""): getattr(d, "kind", "") for d in fleet.drones() if getattr(d, "id", "")}
        except Exception as error:
            swallowed("fleet_commission.FleetCommissionCoordinator._drones: fleet.drones", error)
            return None

    def _patch(self, job_id, **fields):
        def mutate(state):
            for job in state.get("jobs") or []:
                if job.get("id") == job_id:
                    job.update(fields)
        update_commission(mutate)

    def _set_status(self, text):
        if commission_state().get("status") != text:
            update_commission(lambda s: s.update({"status": text}))

    def _block(self, job, reason):
        self._patch(job["id"], state="blocked", reason=reason)
        self.log.level("warn").print(f"[fleet_commission] {job['id']} ({job.get('role')}) blocked: {reason}. Cancel it on the COMMISSION card.")
        return f"{job['id']} blocked ({reason})"

    def _buy_missing(self, parts, catalogue, label, kind="pioneer"):
        """
        Buys whatever of parts {item_id: n} the Inventory lacks, all or nothing
        once the cash manager grants the whole cost. Returns None once everything is in
        Inventory, else a short waiting reason.
        """
        needed = {item: n - inventory_count(item) for item, n in parts.items()}
        needed = {item: n for item, n in needed.items() if n > 0}
        if not needed:
            return None
        unpriced = [item for item in needed if item not in catalogue]
        if unpriced:
            return f"{label}: not in Shop {unpriced}"
        cost = sum(catalogue[item] * n for item, n in needed.items())
        consumer = CASH_CONSUMERS[kind]
        queued = sum(1 for j in (commission_state().get("jobs") or []) if isinstance(j, dict) and job_kind(j) == kind and j.get("state") == "queued")
        if not cash.can_spend(consumer, cost, planned=cost * (1 + queued), label=label):
            self.log.debug(f"[fleet_commission] {label}: needs {cost}cr for {needed}, have {self._credits()}cr; cash manager holds it back.")
            return f"{label}: waiting for credits ({cost}cr)"
        shop = _component("shop")
        if not shop:
            return f"{label}: no Shop"
        self.log.start(f"[fleet_commission] {label}: buying {needed} for {cost}cr")
        failure = self._buy_parts(shop, needed, catalogue, consumer, label)
        self.log.end(f"[fleet_commission] {label}: bought {needed} for {cost}cr." if failure is None else f"[fleet_commission] {label}: purchase incomplete ({failure})")
        return failure

    def _buy_parts(self, shop, needed, catalogue, consumer, label):
        """Buys each of needed {item_id: n}; books what was paid. None on success, else the waiting reason."""
        paid = 0
        for item, n in needed.items():
            res = shop.buy(item, n)
            self.log.debug(f"[fleet_commission] {label}: buy('{item}', {n}) -> {res.status}")
            if res.status != "ok":
                cash.spent(consumer, paid)
                return f"{label}: buy {item} {res.status}"
            paid += catalogue[item] * n
        cash.spent(consumer, paid)
        return None

    # ------------------------------------------------------------ main step

    def step(self, current_tick):
        """One coordinator pass. Returns a short summary for control_room_automation's automation line."""
        self._tick = current_tick
        state = commission_state()
        pioneers = self._pioneers()
        drones = self._drones()
        self._prune(state, pioneers, drones)
        jobs = [j for j in (commission_state().get("jobs") or []) if isinstance(j, dict)]
        crafting = next((j for j in jobs if job_kind(j) == "drone" and j.get("state") == "crafting"), None)
        self._sync_craft_order(crafting)
        for kind, consumer in CASH_CONSUMERS.items():
            if not any(job_kind(j) == kind and j.get("state") in ("queued", "buying", "crafting", "fitting") for j in jobs):
                cash.release(consumer)
        if not jobs:
            self._set_status("idle")
            return "commission idle"

        parts = []
        for kind in JOB_KINDS:
            mine = [j for j in jobs if job_kind(j) == kind]
            if not mine:
                continue
            # Blocked jobs wait for the operator's cancel; the next one goes on.
            job = next((j for j in mine if j.get("state") != "blocked"), None)
            blocked = sum(1 for j in mine if j.get("state") == "blocked")
            queued = sum(1 for j in mine if j is not job and j.get("state") != "blocked")
            text = f"{kind}s: nothing to do" if job is None else self._advance_chain(kind, job, pioneers, drones)
            extras = [f"+{queued} queued"] if queued else []
            extras += [f"{blocked} blocked"] if blocked else []
            parts.append(f"{text} ({', '.join(extras)})" if extras else text)
        text = "; ".join(parts)
        self._set_status(text)
        return f"commission: {text}"

    def _advance_chain(self, kind, job, pioneers, drones):
        """Advances job until its state stops changing (a wait), is blocked or MAX_ADVANCES_PER_PASS is reached. Each advance is written back first."""
        text = ""
        for _ in range(MAX_ADVANCES_PER_PASS):
            before = job.get("state")
            text = self._advance(job, pioneers) if kind == "pioneer" else self._advance_drone(job, drones)
            job = next((j for j in commission_state().get("jobs") or [] if isinstance(j, dict) and j.get("id") == job["id"]), None)
            if job is None or job.get("state") in (before, "blocked"):
                break
        return text

    def _sync_craft_order(self, job):
        """The Fabricator order for the crafting drone job's kit, or none (cancelled/advanced)."""
        wanted = drone_craft_parts(job["spec"]) if job and job.get("spec") else {}
        set_upgrade_order(COMMISSION_REQUESTER, wanted)

    def _advance(self, job, pioneers):
        self.log.start("[fleet_commission] _advance", level="debug")
        job_id, role, state = job["id"], job.get("role"), job.get("state")
        home_base = job_home_base(job)
        label = f"{job_id} {role}"
        self.log.debug(f"{label}: state '{state}'.")

        if state == "queued":
            spec, reason = build_spec(role, self._catalogue())
            if spec is None:
                _ret = self._block(job, reason)
                self.log.end()
                return _ret
            self._patch(job_id, state="buying", spec=spec)
            self.log.print(f"[fleet_commission] {label} for '{home_base or 'home'}': {spec['modules']}, bays {spec['battery_fill']}/{spec['bin_fill']}.")
            self.log.end()
            return f"{label}: buying"

        spec = job.get("spec") or {}
        if state == "buying":
            parts = spec_parts(spec)
            parts[PIONEER_KIT_ID] = parts.get(PIONEER_KIT_ID, 0) + 1
            waiting = self._buy_missing(parts, self._catalogue(), label)
            if waiting:
                self.log.end()
                return waiting
            if pioneers is None:
                self.log.end()
                return f"{label}: fleet unreadable"
            self._patch(job_id, state="deploying", known=pioneers)
            self.log.end()
            return f"{label}: deploying"

        if state == "deploying":
            if pioneers is None:
                self.log.end()
                return f"{label}: fleet unreadable"
            known = set(job.get("known") or [])
            new_id = next((p for p in pioneers if p not in known), None)
            if new_id is None:
                computer = _component("computer")
                if not computer or not hasattr(computer, "deploy"):
                    self.log.end()
                    return f"{label}: no Ship Computer"
                # Always at home: the parts sit in the home Inventory and
                # the Pioneer fits them in the home service area.
                res = computer.deploy(PIONEER_KIT_ID)
                if res.status != "ok":
                    if res.status in DEPLOY_BLOCKING_STATUSES:
                        _ret = self._block(job, f"deploy {res.status}")
                        self.log.end()
                        return _ret
                    if res.status == "no_kit":
                        self._patch(job_id, state="buying")
                    self.log.debug(f"{label}: deploy -> {res.status} - {res.message}")
                    self.log.end()
                    return f"{label}: deploy {res.status}"
                new_id = res.machine_id
            lineage = {"role": role, "job": job_id, "spec": spec, "home_base": home_base, "fitted": False, "missing": {}}

            def mutate(s):
                for j in s.get("jobs") or []:
                    if j.get("id") == job_id:
                        j.update({"state": "attach", "new_id": new_id})
                s.setdefault("lineage", {})[new_id] = lineage
            update_commission(mutate)
            self.log.print(f"[fleet_commission] {label}: deployed '{new_id}' at home, HOME_BASE '{home_base or 'home'}'; waiting for its script.")
            self.log.end()
            return f"{label}: deployed {new_id}"

        new_id = job.get("new_id")
        if state == "attach":
            fitted = ((commission_state().get("lineage") or {}).get(new_id) or {}).get("fitted")
            if fitted or fleet_status.get(new_id) is not None:
                self._patch(job_id, state="fitting")
                self.log.end()
                return f"{label}: {new_id} running"
            if start_script(new_id) != "ok":
                self.log.end()
                return f"{label}: waiting for a script on {new_id} (run scripts_sync)"
            self.log.end()
            return f"{label}: started {new_id}"

        if state == "fitting":
            entry = (commission_state().get("lineage") or {}).get(new_id) or {}
            status = fleet_status.get(new_id) or {}
            if entry.get("fitted"):
                wrong_home = self._wrong_home(status, home_base)
                if wrong_home:
                    self.log.debug(f"{label}: '{new_id}' runs with HOME_BASE '{wrong_home}', job wants '{home_base or HOME_OUTPOST_ID}'.")
                    self.log.end()
                    return f"{label}: {new_id} has HOME_BASE {wrong_home}, set it to {home_base or 'None'}"

                def finish(s):
                    s["jobs"] = [j for j in s.get("jobs") or [] if j.get("id") != job_id]
                    s.get("lineage", {}).pop(new_id, None)
                update_commission(finish)
                self.log.print(f"[fleet_commission] {label}: '{new_id}' fitted and running for '{home_base or 'home'}'.")
                self.log.end()
                return f"{label}: {new_id} done"
            missing = entry.get("missing") or {}
            if missing:
                waiting = self._buy_missing(missing, self._catalogue(), f"{label} refit")
                if waiting:
                    self.log.end()
                    return waiting
            _ret = f"{label}: {new_id} fitting ({status.get('target') or status.get('state', '?')})"
            self.log.end()
            return _ret

        self.log.end()
        return f"{label}: unknown state {state!r}"

    def _wrong_home(self, status, home_base):
        """The HOME_BASE a Pioneer reports when it isn't the job's, else None (also when not reported)."""
        reported = status.get("home")
        if reported is None:
            return None
        wanted = home_base or HOME_OUTPOST_ID
        return None if reported == wanted else str(reported)

    # ------------------------------------------------------------ drones

    def _advance_drone(self, job, drones):
        self.log.start("[fleet_commission] _advance_drone", level="debug")
        job_id, role, state = job["id"], job.get("role"), job.get("state")
        outpost_id = job.get("outpost")
        label = f"{job_id} drone {role}"
        self.log.debug(f"{label}: state '{state}'.")

        if state == "queued":
            spec, reason = build_drone_spec(role, fabricator_unlocked_outputs(), inventory_count, set(self._catalogue()))
            if spec is None:
                _ret = self._block(job, reason)
                self.log.end()
                return _ret
            self._patch(job_id, state="crafting", spec=spec)
            self._sync_craft_order(dict(job, spec=spec))
            bought = f", buying {spec['buy']}" if spec.get("buy") else ""
            self.log.print(f"[fleet_commission] {label} at '{outpost_id or 'home'}': {spec['kind']} with {spec['modules'][1:]}{bought}.")
            self.log.end()
            return f"{label}: crafting"

        spec = job.get("spec") or {}
        if state == "crafting":
            waiting = self._buy_missing(drone_buy_parts(spec), self._catalogue(), label, kind="drone")
            if waiting:
                self.log.end()
                return waiting
            parts = drone_spec_parts(spec)
            short = {item: n - inventory_count(item) for item, n in parts.items() if inventory_count(item) < n}
            if short:
                _ret = self._kit_wait_text(job_id, label, short)
                self.log.end()
                return _ret
            self._unhauled_since.pop(job_id, None)
            if drones is None:
                self.log.end()
                return f"{label}: fleet unreadable"
            self._patch(job_id, state="deploying", known=sorted(drones))
            self._sync_craft_order(None)
            self.log.end()
            return f"{label}: kit ready, deploying"

        if state == "deploying":
            if drones is None:
                self.log.end()
                return f"{label}: fleet unreadable"
            swapping = [k for k, e in (fleet_upgrade_state().get("drones") or {}).items()
                        if isinstance(e, dict) and e.get("state") in SWAP_DEPLOYING_STATES]
            if swapping:
                self.log.end()
                return f"{label}: waiting for the chassis swap of {swapping[0]}"
            known = set(job.get("known") or [])
            new_id = next((d for d, kind in drones.items() if d not in known and kind == spec.get("kind")), None)
            if new_id is None:
                computer = _component("computer")
                if not computer or not hasattr(computer, "deploy"):
                    self.log.end()
                    return f"{label}: no Ship Computer"
                res = computer.deploy(spec.get("kind"), outpost_id)
                if res.status != "ok":
                    if res.status in DEPLOY_BLOCKING_STATUSES:
                        _ret = self._block(job, f"deploy {res.status}")
                        self.log.end()
                        return _ret
                    if res.status == "no_kit":
                        self._patch(job_id, state="crafting")
                    self.log.debug(f"{label}: deploy('{spec.get('kind')}', '{outpost_id}') -> {res.status} - {res.message}")
                    if res.status == "drone_station_full":
                        self.log.end()
                        return f"{label}: waiting for a free Depot bay at {outpost_id or 'home'}"
                    self.log.end()
                    return f"{label}: deploy {res.status}"
                new_id = res.machine_id
            lineage = {
                "from": None, "job": job_id, "role": role, "engine": spec.get("engine"), "kind": spec.get("kind"),
                "params": {"HOME_DEPOT": outpost_id or "None"}, "fitted": False,
            }
            update_fleet_upgrade(lambda s: s.setdefault("lineage", {}).update({new_id: lineage}))
            self._patch(job_id, state="attach", new_id=new_id)
            self.log.print(f"[fleet_commission] {label}: deployed '{new_id}' ({spec.get('kind')}) at '{outpost_id or 'home'}'; waiting for its script.")
            self.log.end()
            return f"{label}: deployed {new_id}"

        new_id = job.get("new_id")
        lineage = (fleet_upgrade_state().get("lineage") or {}).get(new_id)
        if state == "attach":
            if fleet_status.get(new_id) is not None or (isinstance(lineage, dict) and lineage.get("fitted")):
                self._patch(job_id, state="fitting")
                self.log.end()
                return f"{label}: {new_id} running"
            if start_script(new_id) != "ok":
                self.log.end()
                return f"{label}: waiting for a script on {new_id} (run scripts_sync)"
            self.log.end()
            return f"{label}: started {new_id}"

        if state == "fitting":
            # fleet_upgrade prunes nothing of a live drone, so a missing entry
            # means the operator cleared it: nothing left to wait for.
            if not isinstance(lineage, dict) or lineage.get("fitted"):
                update_commission(lambda s: s.update({"jobs": [j for j in s.get("jobs") or [] if j.get("id") != job_id]}))
                self.log.print(f"[fleet_commission] {label}: '{new_id}' fitted and flying from '{outpost_id or 'home'}'.")
                self.log.end()
                return f"{label}: {new_id} done"
            status = fleet_status.get(new_id) or {}
            _ret = f"{label}: {new_id} fitting ({status.get('state', '?')})"
            self.log.end()
            return _ret

        self.log.end()
        return f"{label}: unknown state {state!r}"

    # ------------------------------------------------------------ pruning

    def _prune(self, state, pioneers, drones):
        """Blocks jobs whose deployed vehicle vanished and drops orphan Pioneer lineage. Each kind is skipped when its fleet list can't be read."""
        alive = {"pioneer": pioneers, "drone": drones}
        gone_jobs = []
        for j in state.get("jobs") or []:
            if not isinstance(j, dict) or j.get("state") not in ("attach", "fitting"):
                continue
            ids = alive[job_kind(j)]
            if ids is not None and j.get("new_id") not in ids:
                gone_jobs.append(j.get("id"))
        job_ids = {j.get("id") for j in state.get("jobs") or [] if isinstance(j, dict)}
        orphans = [] if pioneers is None else [
            k for k, e in (state.get("lineage") or {}).items()
            if k not in pioneers or not isinstance(e, dict) or e.get("job") not in job_ids]
        if not gone_jobs and not orphans:
            return

        def mutate(s):
            for j in s.get("jobs") or []:
                if j.get("id") in gone_jobs:
                    j.update({"state": "blocked", "reason": "vehicle gone"})
            for k in orphans:
                s.get("lineage", {}).pop(k, None)
        update_commission(mutate)
        self.log.debug(f"[fleet_commission] Pruned: jobs blocked {gone_jobs}, lineage dropped {orphans}.")
