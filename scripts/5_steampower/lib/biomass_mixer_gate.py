import fluid_routing
from archive import archive
from tree_console import TreeConsole

# Biomass Mixer duty-cycle gate: pause a Mixer (breaker off) while one of its
# expected essences is dry, resume once every expected essence has refilled.
#
# Why (decompiled simworker, tickBiomassMixers()/mpe()): per game hour a Mixer
# mixing d balanced essences makes 1.4 * d**1.5 t biomass while draining
# 4 t/h of each selected essence (Mk I; Mk II x4.5 out / x2.4 in). Biomass per
# ton of essence is therefore 0.35 * sqrt(d) -- independent of balance, which
# only scales throughput. Letting a Mixer run at d-1 while one feed is
# momentarily dry burns the other essences ~sqrt(d/(d-1)) less efficiently
# than waiting for the dry one and mixing all d together. The Mixer itself
# picks the highest-RATE mix each tick, not the most efficient one, so it
# will happily run degraded.
#
# The Mixer has no set_enabled(), so the only pause is the breaker
# (power_control.set_powered). A breaker-off machine's own script is paused
# too and can't switch itself back on -- hence this lives in the always-on
# Control Room calculator (panel_4.py), not in lib/biomass_mixer.py. Fluid
# still flows INTO an unpowered Mixer (the simworker only requires the
# SOURCE end of a link to be powered), so buffers refill while paused and
# the gate reads them directly.
#
# Expected essence = a same-biome Essence Liquifier exists on the network
# AND the Mixer's <biome>_essence_in port has a non-broken link. Anything
# else (leftover buffer, unlinked port) is used opportunistically by the
# Mixer but never waited for.
#
# Gate never waits forever:
#   - a biome whose buffer stops rising for NO_PROGRESS_TICKS while paused is
#     "given up" (Liquifier starved of samples) and the Mixer runs without it;
#   - MAX_PAUSE_TICKS hard-caps any pause;
#   - backpressure (an expected biome's buffer full AND its Liquifier reporting
#     "output_full") forces a run -- mixing at d-1 beats letting a Liquifier
#     block and waste biosite regrowth.
# A given-up biome rejoins the expected set once its buffer reaches
# RESUME_LEVEL_T again.
#
# New Liquifiers: rediscovered every DISCOVERY_INTERVAL_TICKS and diffed
# against the id set persisted in archive (so ones built while the Control
# Room was down still count as new). A gate-paused Mixer's own script is
# paused too, so its EssenceInputRouter can't wire the new biome's input --
# for each new Liquifier whose biome input on a Mixer is still unlinked, the
# gate holds that Mixer in RUN (resuming it if paused) until the input links
# or REWIRE_HOLD_TICKS pass.
#
# Only switches ON a Mixer this gate itself switched off (paused_by_gate), and
# never one currently listed in archive "power.shedded" -- an operator or the
# power guard turning a Mixer off always wins.

ESSENCE_BIOMES = ("frozen", "coastal", "geothermal", "volcanic", "deep")
MIXER_TYPE_ID = "biomass_mixer"
LIQUIFIER_TYPE_ID = "essence_liquifier"

# Mixer input buffer levels, tons (buffer capacity is 30 t per essence).
# Mk II drains 9.6 t/h per essence = ~0.38 t per real second at
# DAY_CYCLE_DURATION_SECONDS=600, so PAUSE_LEVEL_T leaves ~4 s of headroom
# at the 1 s gate cadence.
PAUSE_LEVEL_T = 1.5
RESUME_LEVEL_T = 10.0

# While paused: a buffer counts as "rising" when it gains at least this much
# over its best level seen so far this pause.
PROGRESS_EPSILON_T = 0.05
# ~60 s at 10 ticks/s without any rise -> give up on that biome.
NO_PROGRESS_TICKS = 600
# ~5 min hard cap on any single pause.
MAX_PAUSE_TICKS = 3000
# Backpressure: buffer within this many tons of capacity counts as full.
FULL_MARGIN_T = 1.0

# Mixer/Liquifier rediscovery cadence (~30 s at 10 ticks/s).
DISCOVERY_INTERVAL_TICKS = 300
# Max time a Mixer is held running so its router can wire a new Liquifier's
# biome (~120 s; lib/biomass_mixer.py's router re-discovers candidates only
# every 20 x 5 s polls on the unhealthy path).
REWIRE_HOLD_TICKS = 1200

STATE_KEY_PREFIX = "biomass_mixer.gate."
KNOWN_LIQUIFIERS_KEY = "biomass_mixer.gate_known_liquifiers"
SHEDDED_KEY = "power.shedded"

STATE_RUN = "run"
STATE_PAUSE = "pause"


class MixerGate:
    """Duty-cycles every Biomass Mixer on the network so it only mixes at full expected diversity."""

    def __init__(self, power=None, clock=None):
        self.power = power or get_component("power_control")
        self.clock = clock or get_component("clock")
        self.log = TreeConsole(module="biomass_mixer_gate")
        self._mixers = []
        self._liquifiers_by_biome = {}
        self._last_discovery_tick = None
        self._new_liquifier_biomes = set()   # consumed by the next step()
        self._rediscover_now = False
        self._unknown_flagged = set()        # biomes that already triggered an early rescan this interval
        self._unswitchable_warned = set()

    # ---- discovery -------------------------------------------------------

    def _discover(self, tick):
        due = self._last_discovery_tick is None or tick - self._last_discovery_tick >= DISCOVERY_INTERVAL_TICKS
        if not due and not self._rediscover_now:
            return
        self._last_discovery_tick = tick
        self._rediscover_now = False
        if due:
            self._unknown_flagged.clear()

        old_mixer_ids = {getattr(m, "id", None) for m in self._mixers}
        self._mixers = [b for b, _ in fluid_routing.discover_network_buildings(MIXER_TYPE_ID, resolve=True)]
        mixer_ids = {getattr(m, "id", None) for m in self._mixers}
        if old_mixer_ids:
            for m_id in sorted(i for i in mixer_ids - old_mixer_ids if i):
                self.log.print(f"New Biomass Mixer '{m_id}' detected; gating it.")
            for m_id in sorted(i for i in old_mixer_ids - mixer_ids if i):
                self.log.print(f"Biomass Mixer '{m_id}' gone; dropping its gate state.")
                archive.delete(f"{STATE_KEY_PREFIX}{m_id}")

        by_biome = {}
        biome_of = {}
        for building, _ in fluid_routing.discover_network_buildings(LIQUIFIER_TYPE_ID, resolve=True):
            try:
                biome = building.biome()
            except Exception:
                biome = None
            if biome in ESSENCE_BIOMES:
                by_biome.setdefault(biome, []).append(building)
                biome_of[building.id] = biome
        self._liquifiers_by_biome = by_biome

        known = archive.get(KNOWN_LIQUIFIERS_KEY, None)
        if not isinstance(known, dict):
            # First run on this save: baseline silently, nothing counts as new.
            known = dict(biome_of)
        added = {i: b for i, b in biome_of.items() if i not in known}
        removed = {i: b for i, b in known.items() if i not in biome_of}
        for l_id, biome in sorted(added.items()):
            self.log.print(f"New Essence Liquifier '{l_id}' ({biome}) detected.")
            self._new_liquifier_biomes.add(biome)
        for l_id, biome in sorted(removed.items()):
            self.log.print(f"Essence Liquifier '{l_id}' ({biome}) gone.")
        if known != biome_of:
            archive.set(KNOWN_LIQUIFIERS_KEY, biome_of)
        self.log.debug(f"discovered {len(self._mixers)} Mixer(s); Liquifier biomes: {sorted(by_biome)}.")

    # ---- reads -----------------------------------------------------------

    @staticmethod
    def _call(obj, method, default):
        try:
            return getattr(obj, method)()
        except Exception:
            return default

    def _port_reading(self, mixer, biome):
        """(level_t, capacity_t, linked) for one essence input; linked = any non-broken connection."""
        port = getattr(mixer, f"{biome}_essence_in", None)
        if port is None:
            return 0.0, 0.0, False
        level = self._call(port, "level", 0.0) or 0.0
        capacity = self._call(port, "capacity", 0.0) or 0.0
        linked = any(
            getattr(conn, "state", None) not in fluid_routing.BROKEN_CONNECTION_STATES
            for conn in fluid_routing.port_connections(port)
        )
        return float(level), float(capacity), linked

    def _liquifier_backed_up(self, biome):
        for liquifier in self._liquifiers_by_biome.get(biome, []):
            if self._call(liquifier, "stall_reason", None) == "output_full":
                return True
        return False

    def _is_powered(self, mixer_id):
        power = self.power
        if power is None:
            return True
        try:
            return bool(power.is_powered(mixer_id))
        except Exception:
            return True

    # ---- power -----------------------------------------------------------

    def _switch(self, mixer_id, on):
        power = self.power
        if power is None:
            return False
        try:
            if not on and not power.can_power_off(mixer_id):
                if mixer_id not in self._unswitchable_warned:
                    self._unswitchable_warned.add(mixer_id)
                    self.log.level("warn").print(f"[{mixer_id}] has no breaker toggle; gate cannot pause it.")
                return False
            power.set_powered(mixer_id, on)
            return True
        except Exception as error:
            self.log.level("warn").print(f"[{mixer_id}] breaker {'on' if on else 'off'} failed: {error}")
            return False

    # ---- state machine ---------------------------------------------------

    def _load_state(self, mixer_id):
        state = archive.get(f"{STATE_KEY_PREFIX}{mixer_id}", None)
        if not isinstance(state, dict):
            state = {}
        state.setdefault("state", STATE_RUN)
        state.setdefault("paused_by_gate", False)
        state.setdefault("since", 0)
        state.setdefault("given_up", [])
        state.setdefault("progress", {})
        state.setdefault("reason", "")
        state.setdefault("rewire_until", {})
        return state

    def _enter_pause(self, mixer_id, state, tick, reason, levels):
        if not self._switch(mixer_id, False):
            return
        state.update({
            "state": STATE_PAUSE,
            "paused_by_gate": True,
            "since": tick,
            "reason": reason,
            "progress": {b: {"level": lvl, "tick": tick} for b, lvl in levels.items()},
        })
        self.log.print(f"[{mixer_id}] Paused: {reason}.")

    def _enter_run(self, mixer_id, state, tick, reason):
        if state.get("paused_by_gate") and not self._is_powered(mixer_id):
            shedded = archive.get(SHEDDED_KEY, []) or []
            if mixer_id in shedded:
                self.log.debug(f"[{mixer_id}] resume wanted ({reason}) but power guard has it shed; leaving off.")
                return
            if not self._switch(mixer_id, True):
                return
        state.update({"state": STATE_RUN, "paused_by_gate": False, "since": tick, "reason": reason, "progress": {}})
        self.log.print(f"[{mixer_id}] Resumed: {reason}.")

    def _step_mixer(self, mixer, tick):
        mixer_id = getattr(mixer, "id", None)
        if not mixer_id:
            return None
        state = self._load_state(mixer_id)
        powered = self._is_powered(mixer_id)

        # Someone else changed the breaker behind our back: respect it.
        if state["state"] == STATE_RUN and not powered:
            state["reason"] = "off (not by gate)"
            self.log.debug(f"[{mixer_id}] off but not paused by gate; not touching it.")
            return state
        if state["state"] == STATE_PAUSE and powered:
            state.update({"state": STATE_RUN, "paused_by_gate": False, "since": tick, "reason": "switched on externally", "progress": {}})
            self.log.print(f"[{mixer_id}] Switched on externally; gate back in RUN.")

        readings = {b: self._port_reading(mixer, b) for b in ESSENCE_BIOMES}
        levels = {b: round(r[0], 3) for b, r in readings.items()}
        expected = [b for b in ESSENCE_BIOMES if readings[b][2] and self._liquifiers_by_biome.get(b)]

        # Essence arriving on a linked input whose biome has no known Liquifier:
        # the cached discovery is stale (new Liquifier) -- rescan next step.
        unknown = [b for b in ESSENCE_BIOMES if readings[b][2] and levels[b] > 0 and not self._liquifiers_by_biome.get(b)]
        fresh = [b for b in unknown if b not in self._unknown_flagged]
        if fresh:
            self._unknown_flagged.update(fresh)
            self._rediscover_now = True
            self.log.debug(f"[{mixer_id}] essence arriving on {unknown} with no known Liquifier; rescanning next step.")

        # New Liquifier biomes whose input is still unlinked: hold the Mixer
        # running so its own router can wire them (it is paused with the Mixer).
        rewire = {b: t for b, t in state["rewire_until"].items() if tick < t and not readings[b][2]}
        for b in self._new_liquifier_biomes:
            if not readings[b][2] and b not in rewire:
                rewire[b] = tick + REWIRE_HOLD_TICKS
                self.log.debug(f"[{mixer_id}] {b}_essence_in unlinked after new Liquifier; holding RUN up to {REWIRE_HOLD_TICKS} ticks.")
        for b in state["rewire_until"]:
            if b not in rewire and readings[b][2]:
                self.log.print(f"[{mixer_id}] {b}_essence_in linked; now expected.")
        state["rewire_until"] = rewire
        if rewire:
            reason = f"letting Mixer wire {', '.join(sorted(rewire))} input"
            if state["state"] == STATE_PAUSE:
                self._enter_run(mixer_id, state, tick, reason)
            elif state["reason"] != reason:
                state["reason"] = reason
            if state["state"] == STATE_RUN:
                state["expected"] = expected
                state["levels"] = levels
                return state

        # Given-up biomes rejoin once refilled; forget biomes no longer expected.
        given_up = [b for b in state["given_up"] if b in expected and levels[b] < RESUME_LEVEL_T]
        rejoined = [b for b in state["given_up"] if b not in given_up and b in expected]
        if rejoined:
            self.log.print(f"[{mixer_id}] {', '.join(rejoined)} refilled; expected again.")
        state["given_up"] = given_up
        active = [b for b in expected if b not in given_up]
        required = self._call(mixer, "required_essences", 1) or 1

        self.log.debug(f"[{mixer_id}] state={state['state']} expected={expected} given_up={given_up} required={required} levels={levels}.")

        if state["state"] == STATE_RUN:
            if len(active) < required:
                state["reason"] = f"only {len(active)} expected essence(s), phase needs {required}; Mixer self-stalls"
                self.log.debug(f"[{mixer_id}] {state['reason']}; not gating.")
            else:
                dry = [b for b in active if levels[b] < PAUSE_LEVEL_T]
                if dry:
                    self._enter_pause(mixer_id, state, tick, f"{', '.join(dry)} below {PAUSE_LEVEL_T} t (waiting to mix {len(active)})", levels)
        else:
            self._step_paused(mixer_id, state, tick, active, required, readings, levels)

        state["expected"] = expected
        state["levels"] = levels
        return state

    def _step_paused(self, mixer_id, state, tick, active, required, readings, levels):
        if len(active) < required:
            self._enter_run(mixer_id, state, tick, f"only {len(active)} expected essence(s) left, phase needs {required}")
            return

        waiting = [b for b in active if levels[b] < RESUME_LEVEL_T]
        if not waiting:
            self._enter_run(mixer_id, state, tick, f"all {len(active)} expected essences >= {RESUME_LEVEL_T} t")
            return

        # Track per-biome progress; stagnant ones get given up.
        progress = state["progress"]
        stagnant = []
        for b in waiting:
            entry = progress.get(b) or {"level": levels[b], "tick": tick}
            if levels[b] >= entry["level"] + PROGRESS_EPSILON_T:
                entry = {"level": levels[b], "tick": tick}
            progress[b] = entry
            if tick - entry["tick"] >= NO_PROGRESS_TICKS:
                stagnant.append(b)
        self.log.debug(f"[{mixer_id}] paused {tick - state['since']} ticks; waiting on {waiting}; stagnant={stagnant}.")

        backed_up = [
            b for b in active
            if readings[b][1] > 0 and levels[b] >= readings[b][1] - FULL_MARGIN_T and self._liquifier_backed_up(b)
        ]
        timed_out = tick - state["since"] >= MAX_PAUSE_TICKS

        if backed_up or timed_out or stagnant:
            give_up = waiting if (backed_up or timed_out) else stagnant
            state["given_up"] = sorted(set(state["given_up"]) | set(give_up))
            if backed_up:
                why = f"{', '.join(backed_up)} Liquifier backed up"
            elif timed_out:
                why = f"max pause {MAX_PAUSE_TICKS} ticks"
            else:
                why = f"{', '.join(stagnant)} not refilling for {NO_PROGRESS_TICKS} ticks"
            remaining = [b for b in active if b not in give_up]
            if len(remaining) < required:
                self._enter_run(mixer_id, state, tick, f"{why}; running anyway")
            elif all(levels[b] >= RESUME_LEVEL_T for b in remaining):
                self._enter_run(mixer_id, state, tick, f"{why}; mixing {len(remaining)} without {', '.join(give_up)}")
            else:
                self.log.debug(f"[{mixer_id}] gave up on {give_up} ({why}); still waiting on others.")

    def step(self, tick=None):
        """One gate pass over every Mixer. Returns {mixer_id: state} (also persisted to archive)."""
        if not self.power:
            return {}
        if tick is None:
            tick = self._call(self.clock, "tick", 0) if self.clock else 0
        self._discover(tick)
        results = {}
        for mixer in self._mixers:
            try:
                state = self._step_mixer(mixer, tick)
            except Exception as error:
                self.log.level("error").print(f"[{getattr(mixer, 'id', '?')}] gate error: {error}")
                continue
            if state is not None:
                mixer_id = mixer.id
                archive.set(f"{STATE_KEY_PREFIX}{mixer_id}", state)
                results[mixer_id] = state
        self._new_liquifier_biomes.clear()
        return results
