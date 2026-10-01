# Habitat controller: one per Habitat (thin bio/habitat.py). Executes the
# Wildlife planner's decisions (`wildlife.plan`, lib/wildlife_planner.py) for
# this Habitat, since every Habitat action is self-only:
#   - assigned species: set_revival_target(); buy the queued node
#     (unlock_bonus(), id resolved from the live bonus tree by slot); stage the
#     feed reservation and the reagents; revive() once everything is staged
#     (and the Adaptation is bought when the plan says Adaptation first);
#   - rearing (12 game hours): keep the feed present; on rearing_failed()
#     re-stage and retry up to MAX_REVIVE_RETRIES;
#   - established: top up feed, regulate gas and liquid toward the band centre
#     from tanks holding the required fluid, pre-fill a medium that opens at
#     the next stage, buy queued Breakthroughs/Adaptations. A fluid the
#     planner rations away (`fluid_ration`) gets intake 0, without a purge.
# Parks itself (breaker off, lib/script_parking.py) when empty and unassigned,
# without feed anywhere at home, capped at the Mk I ceiling, or rationed with
# its buffer out of band (an unpowered Habitat neither meters nor bleeds);
# publishes the reason so the planner can wake it and alert the operator.
# State is read live each step, so a restart picks up where it was.
#
# Publishes `wildlife.status[habitat_id]` (see docs/cheatsheet/wildlife.md §1l-2).

from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from storage import take_item, local_port_target
from script_parking import ParkRequester
import fluid_routing
import cash
from wildlife_data import SPECIES, REVIVE_FEED_REQUIRED, REVIVAL_REAGENT_IDS, RARITY_REAGENTS, STAGE_CAPACITY, GAS_PER_BIRTH_T, LIQUID_PER_BIRTH_T, BUFFER_BLEED_T_PER_H
import wildlife_common as wc

# Poll: established colonies wake in time for the next feed top-up, within these bounds (s).
POLL_MIN_S = 5.0
POLL_MAX_S = 60.0
POLL_STAGING_S = 10.0
SECONDS_PER_GAME_HOUR = 25.0

# Revival retries after a failed rearing (each retry spends reagents again).
MAX_REVIVE_RETRIES = 3

# Fluid regulator: intake = consumption + bleed + GAIN x (band centre - level), clamped.
REGULATOR_GAIN_PER_H = 0.5
MAX_INTAKE_T_PER_H = 50.0
# Above band high + this, with intake 0, the reserve is purged and refilled.
PURGE_MARGIN_T = 100.0
# A medium that opens at the next stage is filled once the stage is this many game hours away.
PREFILL_LEAD_H = 12.0

# Fluid source routing (same values as the Plant Terraformer's water router).
FLUID_STALL_STREAK_BLACKLIST_THRESHOLD = 5
FLUID_RESCAN_INTERVAL_TICKS = 150
FLUID_DISCOVERY_CACHE_INTERVAL_TICKS = 100
FLUID_NEUTRAL_GRACE_STEPS = 5

MEDIA = {
    "gas": {"port": "gas_in", "tanks": wc.TANK_TYPE_IDS["gas"], "per_birth": GAS_PER_BIRTH_T},
    "liquid": {"port": "liquid_in", "tanks": wc.TANK_TYPE_IDS["liquid"], "per_birth": LIQUID_PER_BIRTH_T},
}


def regulator_rate(level, band, birth_rate, per_birth):
    """Intake (t/h) that steers `level` toward the band centre."""
    centre = (band[0] + band[1]) / 2.0
    rate = birth_rate * per_birth + BUFFER_BLEED_T_PER_H + REGULATOR_GAIN_PER_H * (centre - level)
    return max(0.0, min(MAX_INTAKE_T_PER_H, rate))


def next_poll(feed_level, burn_per_h):
    """Seconds until the bin reaches FEED_TOPUP_AT at `burn_per_h`, within [POLL_MIN_S, POLL_MAX_S]."""
    if burn_per_h <= 0:
        return POLL_MAX_S
    hours = max(0.0, feed_level - wc.FEED_TOPUP_AT) / burn_per_h
    return max(POLL_MIN_S, min(POLL_MAX_S, hours * SECONDS_PER_GAME_HOUR * 0.8))


class HabitatController:
    """Runs one Habitat: revival, feeding, fluid bands, purchases, parking."""

    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "habitat")
        self.outpost = getattr(machine, "outpost", None)
        self.outpost_id = getattr(self.outpost, "id", None)
        self.is_home = bool(getattr(self.outpost, "is_home", False))
        self.clock = get_component("clock")
        self.shop = get_component("shop")
        self.log = TreeConsole(module="habitat")
        self.parker = ParkRequester(self.name, "habitat")
        self.routers = {}
        self.router_fluid = {}
        self.retries = 0
        self.blocker = None
        self.parked = ""
        self.rationed_out = False
        self._last_failed = False

    # ------------------------------------------------------------ readings

    def tick(self):
        try:
            return self.clock.tick() if self.clock else 0
        except Exception as error:
            swallowed("habitat.HabitatController.tick: clock.tick", error)
            return 0

    def _call(self, method, default, *args):
        fn = getattr(self.machine, method, None)
        if fn is None:
            return default
        try:
            value = fn(*args)
        except Exception as error:
            swallowed(f"habitat.HabitatController._call: {method}", error)
            return default
        return default if value is None else value

    @staticmethod
    def held(port):
        out = {}
        try:
            for stack in port.stacks():
                out[stack.id] = out.get(stack.id, 0) + stack.count
        except Exception as error:
            swallowed("habitat.HabitatController.held: port.stacks", error)
        return out

    def plan_entry(self):
        """(assignment, node slot to buy or None, [fluids the planner denies this Habitat])."""
        plan = archive.get(wc.PLAN_KEY, {}) or {}
        if not isinstance(plan, dict):
            return {}, None, []
        assign = (plan.get("assign") or {}).get(self.name) or {}
        denied = (plan.get("fluid_ration") or {}).get(self.name) or []
        return assign, (plan.get("buy") or {}).get(self.name), list(denied)

    def bought(self):
        """{"adaptation": bool, "breakthrough": bool} from the live bonus tree; {} before a target exists."""
        tree = self._call("get_bonus_tree", None)
        out = {}
        for node in (getattr(tree, "nodes", None) or []):
            slot = getattr(node, "slot", "")
            if slot in ("adaptation", "breakthrough") and getattr(node, "source_species", "") == getattr(tree, "species", ""):
                out[slot] = bool(getattr(node, "purchased", False))
        return out

    def creature(self, species):
        journal = get_component("journal")
        if journal is None:
            return None
        try:
            for c in journal.cataloged_creatures(wc.PLANET_ID):
                if getattr(c, "creature_id", "") == species:
                    return c
        except Exception as error:
            swallowed("habitat.HabitatController.creature: journal.cataloged_creatures", error)
        return None

    def reagents_needed(self, species):
        info = self.creature(species)
        needed = dict(getattr(info, "revive_reagents", None) or {})
        if needed:
            return needed
        qty = RARITY_REAGENTS.get(SPECIES.get(species, {}).get("rarity", ""), 0)
        return {r: qty for r in REVIVAL_REAGENT_IDS} if qty else {}

    # ------------------------------------------------------------ purchases

    def buy_node(self, slot):
        tree = self._call("get_bonus_tree", None)
        node_id = None
        for node in (getattr(tree, "nodes", None) or []):
            if getattr(node, "slot", "") == slot and getattr(node, "source_species", "") == getattr(tree, "species", ""):
                node_id = getattr(node, "id", None)
        if not node_id:
            self.log.debug(f"[{self.name}] no {slot} node in the bonus tree yet.")
            return False
        result = self._call("unlock_bonus", None, node_id)
        status = getattr(result, "status", "")
        if status == "ok":
            self.log.print(f"[{self.name}] Bought {slot} '{node_id}'.")
            return True
        if status == "already_purchased":
            return True
        self.log.debug(f"[{self.name}] unlock_bonus({node_id}) -> {status}: {getattr(result, 'message', '')}")
        return False

    # ------------------------------------------------------------ staging

    def stage_feed(self, item, wanted):
        """Feed in the bin up to `wanted`; ejects other feed first. Returns units in the bin."""
        port = self.machine.input
        bin_ = self.held(port)
        for other, count in bin_.items():
            if other != item and count > 0:
                try:
                    port.eject(local_port_target(self.outpost), other, count)
                    self.log.print(f"[{self.name}] Ejected {count}x wrong feed '{other}'.")
                except Exception as error:
                    swallowed("habitat.HabitatController.stage_feed: port.eject", error)
        have = int(bin_.get(item, 0))
        if have < wanted:
            have += take_item(port, item, wanted - have, outpost=self.outpost)
        return have

    def stage_reagents(self, species):
        """True once every reagent is in the reagents input; buys the shortfall through the cash manager."""
        needed = self.reagents_needed(species)
        port = self.machine.reagents
        loaded = self.held(port)
        complete = True
        for reagent, qty in needed.items():
            missing = qty - loaded.get(reagent, 0)
            if missing <= 0:
                continue
            moved = take_item(port, reagent, missing, outpost=self.outpost)
            if moved >= missing:
                continue
            complete = False
            if not (self.is_home and self.shop):
                self.blocker = "reagent_supply"
                continue
            buy_qty = missing - moved
            cost = buy_qty * cash.shop_price(reagent)
            cash_id = f"wildlife_reagents:{self.name}"
            if not cash.can_spend(cash_id, cost, label=f"{buy_qty}x {reagent}"):
                self.blocker = "reagent_budget"
                self.log.debug(f"[{self.name}] {buy_qty}x {reagent} ({cost} cr): cash manager holds it back.")
                return False
            result = self.shop.buy(reagent, buy_qty)
            if getattr(result, "status", "") == "ok":
                cash.spent(cash_id, cost)
                self.log.print(f"[{self.name}] Bought {buy_qty}x {reagent}.")
                take_item(port, reagent, buy_qty, outpost=self.outpost)
            else:
                cash.release(cash_id)
                self.blocker = "reagent_budget"
                return False
        if complete:
            return True
        loaded = self.held(port)
        return all(loaded.get(r, 0) >= q for r, q in needed.items())

    def prepare(self, assign, buy):
        """Empty Habitat with an assignment: target, purchase, staging, revive()."""
        species = assign["species"]
        target = self._call("revival_target", "")
        if target != species:
            result = self._call("set_revival_target", None, species)
            status = getattr(result, "status", "")
            if status != "ok":
                self.blocker = status or "target_failed"
                self.log.level("warn").print(f"[{self.name}] set_revival_target({species}) -> {status}: {getattr(result, 'message', '')}")
                return
            self.log.print(f"[{self.name}] Preparing {species}.")
            self.retries = 0
        if buy:
            self.buy_node(buy)
        if assign.get("adapt_first") and not self.bought().get("adaptation"):
            self.blocker = "awaiting_insight"
            return
        item = self._call("required_feed", wc.feed_item_of(species))
        feed = self.stage_feed(item, REVIVE_FEED_REQUIRED + wc.REARING_FEED_EXTRA)
        if feed < REVIVE_FEED_REQUIRED + wc.REARING_FEED_EXTRA:
            self.blocker = "no_feed"
            self.log.debug(f"[{self.name}] feed reservation {feed}/{REVIVE_FEED_REQUIRED + wc.REARING_FEED_EXTRA} {item}.")
            return
        if not self.stage_reagents(species):
            self.blocker = self.blocker or "reagents"
            return
        if self.retries > MAX_REVIVE_RETRIES:
            self.blocker = "rearing_failed"
            return
        self.log.start(f"[{self.name}] Reviving {species}")
        result = self._call("revive", None)
        status = getattr(result, "status", "")
        if status == "ok":
            self.blocker = None
            self.log.end("rearing started (12 game hours)")
            return
        self.blocker = status or "revive_failed"
        self.log.level("warn").print(f"revive() -> {status}: {getattr(result, 'message', '')}")
        self.log.end("not started")

    # ------------------------------------------------------------ fluids

    def _discover(self, medium, fluid_id):
        def discover():
            pairs = fluid_routing.discover_network_buildings(MEDIA[medium]["tanks"], resolve=False, fluid_id=fluid_id)
            return fluid_routing.rank_own_outpost_first(pairs, self.outpost_id)
        return discover

    def _route(self, medium, fluid_id, curr_tick):
        port = getattr(self.machine, MEDIA[medium]["port"], None)
        if port is None:
            return False
        if self.router_fluid.get(medium) != fluid_id:
            self.router_fluid[medium] = fluid_id
            self.routers[medium] = fluid_routing.FluidInputRouter(
                discover=self._discover(medium, fluid_id),
                rescan_interval_ticks=FLUID_RESCAN_INTERVAL_TICKS,
                discovery_cache_interval_ticks=FLUID_DISCOVERY_CACHE_INTERVAL_TICKS,
                stall_streak_threshold=FLUID_STALL_STREAK_BLACKLIST_THRESHOLD,
                neutral_grace_steps=FLUID_NEUTRAL_GRACE_STEPS,
                label=f"{self.name}.{MEDIA[medium]['port']}",
                reserve_fluid="water" if fluid_id == "water" else None,
            )
        event = self.routers[medium].ensure(port, curr_tick, False)
        if event.kind == "connected":
            self.log.print(f"[{self.name}] {MEDIA[medium]['port']} -> '{event.source_id}' ({fluid_id}).")
        elif event.kind in ("not_found", "no_port"):
            self.blocker = f"no_{fluid_id}_source"
            return False
        return True

    def _set_intake(self, medium, rate):
        self._call("set_gas_intake" if medium == "gas" else "set_liquid_intake", None, rate)

    def _port_flow(self, medium):
        port = getattr(self.machine, MEDIA[medium]["port"], None)
        fn = getattr(port, "flow_rate", None)
        if fn is None:
            return 0.0
        try:
            return float(fn() or 0.0)
        except Exception as error:
            swallowed("habitat.HabitatController._port_flow: flow_rate", error)
            return 0.0

    def regulate(self, medium, birth_rate, near_next, curr_tick, denied=()):
        """
        One regulator step for `medium`; returns [held fluid, level, band,
        required fluid, port flow] for telemetry (wc.MEDIUM_*). A fluid in
        `denied` (the planner's ration) gets intake 0 and no purge: the held
        buffer keeps the colony breeding while it stays in band. Once the
        active band is left, `self.rationed_out` asks the step to park.
        """
        band = list(self._call(f"{medium}_band", []))
        level = float(self._call(f"{medium}_level", 0.0))
        held = self._call(f"{medium}_fluid", "")
        required = self._call(f"required_{medium}", "")
        prefill = False
        if not band and near_next:
            band = list(self._call(f"next_{medium}_band", []))
            required = self._call(f"next_required_{medium}", "")
            prefill = True
        if not band or not required:
            self._set_intake(medium, 0.0)
            return [held, round(level, 1), [], "", 0.0]
        out = [held, round(level, 1), band, required, round(self._port_flow(medium), 3)]
        if held and held != required:
            self._set_intake(medium, 0.0)
            self._call("purge_reserve", None, medium)
            self._call("purge_intake", None, MEDIA[medium]["port"])
            self.log.print(f"[{self.name}] {medium} reserve held '{held}', needs '{required}': purged.")
            return out
        if required in denied:
            self._set_intake(medium, 0.0)
            self.blocker = "fluid_rationed"
            if not prefill and not band[0] <= level <= band[1]:
                self.rationed_out = True
            return out
        if level > band[1] + PURGE_MARGIN_T:
            self._set_intake(medium, 0.0)
            self._call("purge_reserve", None, medium)
            self.log.print(f"[{self.name}] {medium} {level:.0f} t far above band {band}: purged, refilling.")
            return out
        if not self._route(medium, required, curr_tick):
            self._set_intake(medium, 0.0)
            return out
        self._set_intake(medium, regulator_rate(level, band, birth_rate, MEDIA[medium]["per_birth"]))
        return out

    # ------------------------------------------------------------ established

    def top_up_feed(self, species):
        item = self._call("required_feed", wc.feed_item_of(species))
        level = float(self._call("feed_level", 0.0))
        if level < wc.FEED_TOPUP_AT:
            level = float(self.stage_feed(item, wc.FEED_TOPUP_TARGET))
        return item, level

    def established_step(self, species, buy, denied, curr_tick):
        if buy:
            self.buy_node(buy)
        item, feed = self.top_up_feed(species)
        pop = int(self._call("population", 0))
        tier = int(self._call("tier", 1))
        rate = float(self._call("breeding_rate", 0.0))
        headroom = int(self._call("headroom", 1))
        next_pop = int(self._call("next_stage_population", 0))
        near_next = next_pop > 0 and rate > 0 and next_pop - pop < rate * PREFILL_LEAD_H
        self.rationed_out = False
        fluids = {m: self.regulate(m, rate, near_next, curr_tick, denied) for m in MEDIA}
        capped = tier < 2 and headroom <= 0 and pop >= STAGE_CAPACITY[4]
        no_feed = not self._call("feed_ok", True) and feed <= 0
        if capped:
            self.parked = wc.PARK_CAPPED
            self.blocker = "capped"
        elif no_feed:
            # Parked (unpowered) buffers neither meter nor bleed; close the
            # intakes so a wake starts from 0, not a stale setpoint.
            for medium in MEDIA:
                self._set_intake(medium, 0.0)
            self.parked = wc.PARK_NO_FEED
            self.blocker = "no_feed"
        elif self.rationed_out:
            self.parked = wc.PARK_RATIONED
        return item, feed, rate, fluids

    # ------------------------------------------------------------ loop

    def publish(self, entry, curr_tick):
        def updater(status):
            if not isinstance(status, dict):
                status = {}
            for other in list(status.keys()):
                if other != self.name and not wc.fresh(status[other], curr_tick):
                    del status[other]
            status[self.name] = entry
            return status

        if not archive.transaction(wc.STATUS_KEY, {}, updater):
            self.log.level("warn").print(f"[{self.name}] {wc.STATUS_KEY} write rejected.")

    def step(self):
        curr_tick = self.tick()
        assign, buy, denied = self.plan_entry()
        species = self._call("species", "")
        established = bool(self._call("is_established", False))
        previous = self.blocker
        self.blocker = None
        self.parked = ""
        item, feed, rate, fluids = "", float(self._call("feed_level", 0.0)), 0.0, {}
        poll = POLL_STAGING_S
        if established:
            item, feed, rate, fluids = self.established_step(species, buy, denied, curr_tick)
            mult = wc.feed_multiplier(species, self._purchased_ids())
            poll = next_poll(feed, rate * 0.1 * mult)
        elif species:
            # Rearing: feed must stay present for the whole window; no births, no fluids.
            item = self._call("required_feed", wc.feed_item_of(species))
            if feed < 1:
                feed = float(self.stage_feed(item, REVIVE_FEED_REQUIRED))
        elif assign.get("species"):
            failed = bool(self._call("rearing_failed", False))
            if failed and not self._last_failed:
                self.retries += 1
                self.log.level("warn").print(f"[{self.name}] Rearing of {assign['species']} failed (retry {self.retries}/{MAX_REVIVE_RETRIES}).")
            self._last_failed = failed
            self.prepare(assign, buy)
            item = self._call("required_feed", "")
        else:
            self.parked = wc.PARK_EMPTY
            poll = POLL_MAX_S
        if self.blocker != previous and self.blocker:
            self.log.print(f"[{self.name}] blocker: {self.blocker}.")
        self.publish({
            "species": species,
            "target": self._call("revival_target", ""),
            "established": established,
            "rearing": bool(species) and not established,
            "rearing_progress": round(float(self._call("rearing_progress", 0.0)), 3),
            "pop": int(self._call("population", 0)),
            "capacity": int(self._call("carrying_capacity", 0)),
            "tier": int(self._call("tier", 1)),
            "stage": self._call("life_stage", ""),
            "rate": round(rate, 3),
            "efficiency": round(float(self._call("breeding_efficiency", 0.0)), 3),
            "feed_item": item,
            "feed_level": round(feed, 2),
            "gas": fluids.get("gas"),
            "liquid": fluids.get("liquid"),
            "insight": round(float(getattr(self._call("get_insight", None), "shared_exact", 0.0) or 0.0), 3),
            "bought": self.bought(),
            "blocker": self.blocker,
            "parked": self.parked,
            "retries": self.retries,
            "tick": curr_tick,
        }, curr_tick)
        self.parker.update(bool(self.parked))
        return poll

    def _purchased_ids(self):
        out = []
        for node in self._call("get_active_bonuses", []):
            node_id = getattr(node, "id", None)
            if node_id:
                out.append(node_id)
        return out

    def run(self):
        self.log.print(f"Habitat ({self.name}) online at '{self.outpost_id}'.")
        validate_game_version()
        while True:
            reset_all()
            poll = POLL_STAGING_S
            try:
                poll = self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Habitat exception: {error}")
            flush_all()
            sleep(poll)
