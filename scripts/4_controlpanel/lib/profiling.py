# Lightweight per-script tick-cost profiling.
#
# The game exposes no per-script CPU/ms execution budget API. Per
# docs/components/clock.md, clock.tick() (deterministic simulation tick
# since save start, 10 ticks/sec at normal speed) is the documented stand-in
# -- "Use tick deltas for profiling script timing instead of wall-clock
# milliseconds." This module wraps that pattern so any controller's step()
# can be measured with two calls and no local bookkeeping.
#
# Usage inside a controller's run() loop:
#   start = profiling.begin()
#   self.step()
#   profiling.end("thermal_cap_1", start)
#
# Samples roll into a fixed-size history per script name in `archive` (the
# Data Archive has a hard 512-entry cap shared by every script, so this is
# one key per *name*, not per sample) so profiling.report() can summarize
# after the fact instead of requiring someone to watch console output live.
# Each entry is stored as {"history": [...], "last_tick": N} -- the
# last_tick lets lib/archive_cleaner.py's clean_profiling() tell an entry
# nobody has updated in a long time (profiling.begin()/end() was removed
# from that script) apart from one still being actively written to.

from archive import archive
from tree_console import TreeConsole

log = TreeConsole(module="profiling")

ARCHIVE_KEY_PREFIX = "profiling."
HISTORY_LEN = 50

# A normal step() call should finish within a handful of simulation ticks.
# Anything consistently above this means that step()'s own body -- not
# wall-clock speed, which isn't what tick deltas measure -- is doing more
# per-call work than it should (e.g. an unthrottled network-wide discovery
# scan running every single call instead of being cached/rate-limited).
SLOW_STEP_TICK_THRESHOLD = 1


def begin():
    """Call immediately before the work to measure. Returns an opaque start marker (or None if the clock is unavailable)."""
    clock = get_component("clock")
    if not clock or not hasattr(clock, "tick"):
        return None
    try:
        return clock.tick()
    except Exception:
        return None


def end(name, start_tick, warn_threshold=SLOW_STEP_TICK_THRESHOLD, log_slow=True):
    """
    Call immediately after the measured work, with the marker begin()
    returned. Records the tick delta into archive and, when log_slow is
    True, prints a one-line warning if the delta exceeds warn_threshold.
    Returns the delta (ticks), or None if timing wasn't available.
    """
    if start_tick is None:
        return None
    clock = get_component("clock")
    if not clock or not hasattr(clock, "tick"):
        return None
    try:
        end_tick = clock.tick()
    except Exception:
        return None
    delta = end_tick - start_tick

    _record(name, delta, end_tick)
    if log_slow and delta > warn_threshold:
        log.level("warn").print(f"[profiling] '{name}' step() cost {delta} sim ticks (> {warn_threshold}) -- look for expensive per-call work that should be cached or rate-limited.")
    return delta


def _record(name, delta, current_tick):
    """
    Stores {"history": [...], "last_tick": ...} rather than a bare list --
    a script can be un-instrumented at any time (profiling.begin()/end() is
    opt-in, added/removed per debugging session, not permanent
    instrumentation), and a bare list gives lib/archive_cleaner.py's
    clean_profiling() no way to tell "actively profiled, just idle a moment"
    apart from "nobody's called end() for this name in a long time, purge
    it" -- last_tick is what makes that distinction possible.
    """
    log.trace(f"_record start: name='{name}' delta={delta} current_tick={current_tick}")
    key = ARCHIVE_KEY_PREFIX + name
    entry = archive.get(key, None)
    history = entry.get("history", []) if isinstance(entry, dict) else []
    history.append(delta)
    if len(history) > HISTORY_LEN:
        overflow = len(history) - HISTORY_LEN
        log.debug(f"[profiling] '{name}' history window trimmed: {len(history)} samples > cap {HISTORY_LEN}, dropping {overflow} oldest")
        history = history[-HISTORY_LEN:]
    archive.set(key, {"history": history, "last_tick": current_tick})
    log.trace(f"_record end: name='{name}' stored history_len={len(history)} last_tick={current_tick}")


def report(names=None):
    """
    Prints avg/max tick cost per step() for each profiled script name (or
    every name with recorded samples, if names is omitted). Meant to be run
    ad hoc -- e.g. from a one-off diagnostic script -- not from a hot loop.
    """
    prefix = ARCHIVE_KEY_PREFIX
    if names:
        target_keys = [prefix + n for n in names]
    else:
        target_keys = archive.keys(prefix) if hasattr(archive, "keys") else []

    printed = False
    for key in sorted(target_keys):
        entry = archive.get(key, None)
        history = entry.get("history", []) if isinstance(entry, dict) else (entry or [])
        if not history:
            continue
        name = key[len(prefix):]
        avg = sum(history) / len(history)
        log.debug(f"[profiling] '{name}' average computed from {len(history)} samples: sum={sum(history)} avg={avg:.2f} max={max(history)}")
        log.print(f"[profiling] {name}: avg={avg:.1f} max={max(history)} samples={len(history)} ticks/step")
        printed = True

    if not printed:
        log.print("[profiling] No recorded samples yet.")
