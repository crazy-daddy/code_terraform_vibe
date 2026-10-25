"""
Atomic execution of heavy pure computations (docs/cheatsheet/dev_workflow.md §1d-1).

A script gets a fixed interpreter-step allowance per tick. A Python callback
invoked by a builtin (`map`, `sorted(key=)`, ...) runs each single call without
a budget check inside it, capped at 10,000 steps per call (StepLimitError
beyond). The budget is only checked between callbacks and resets every tick,
so work run as one callback costs at most one tick instead of many.

The cap is `stepsPerTick × 10` from the game's fixed interpreter config; the
Advanced Scripting settings (string and collection limits) do not change it.
StepLimitError cannot be caught (`try/except` only sees Python exceptions and
RecursionError) and ends the script, so there is no probing the cap at run
time: size every chunk well below it, measured at its worst case.

What a callback may call (the interpreter checks every game call made inside
one): reads without side effects (get_component(), stacks(), count(),
fleet.vehicles(), ...) are allowed and not charged to the tick budget. A call
that changes game state or observes (set_enabled, connect, take, archive
writes, scans) or suspends (sleep(), waits, mine) raises RuntimeError. A
catchable Python exception, but it aborts the callback. Remote-write
PermissionError applies as everywhere. Plain mutation of your own Python
objects is fine.

Logging is safe inside run_atomic() (and so run_batched()/run_chunked()):
console.print() changes game state and would raise RuntimeError in a callback,
so every console write made through console_print() (TreeConsole and
swallow.swallowed() use it) is queued while a run_atomic() call is active and
written in order right after the outermost one returns or raises. Lines keep
the game time they were logged at (console.now() is a plain read). So a
function that logs through its passed-in `log` can be made atomic without
changing it. Raw map()/sorted(key=)/lru_cache callbacks outside these runners
are not covered: keep logging out of those.

ATOMIC_ENABLED = False makes run_atomic() call fn directly, for the case that
a game update closes the quirk.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable, TypeVar

    T = TypeVar("T")

ATOMIC_ENABLED = True

# Nesting depth of active run_atomic() calls, and console writes held back meanwhile: (console, text, kwargs).
_ACTIVE = {"depth": 0}
_DEFERRED = []


def in_atomic():
    """True while a run_atomic() callback is running."""
    return _ACTIVE["depth"] > 0


def console_print(console, text, **kwargs):
    """console.print(text, **kwargs), or queued until the outermost run_atomic() call ends when inside
    one. A queued `timestamp=True` line is stamped with console.now() at queue time instead."""
    if _ACTIVE["depth"] <= 0:
        console.print(text, **kwargs)
        return
    if kwargs.get("timestamp") and hasattr(console, "now"):
        kwargs["timestamp"] = False
        text = f"{console.now()} {text}"
    _DEFERRED.append((console, text, kwargs))


def _write_deferred():
    lines = list(_DEFERRED)
    _DEFERRED.clear()
    for console, text, kwargs in lines:
        console.print(text, **kwargs)


def run_atomic(fn: "Callable[..., T]", *args) -> "T":
    """fn(*args) as a single map() callback; returns its result. Console writes made through
    console_print() inside it are written after it (see the module doc)."""
    if not ATOMIC_ENABLED:
        return fn(*args)
    _ACTIVE["depth"] += 1
    try:
        return list(map(lambda _: fn(*args), (0,)))[0]
    finally:
        _ACTIVE["depth"] -= 1
        if _ACTIVE["depth"] == 0:
            _write_deferred()


def run_batched(fn, items, size, *args):
    """fn(items[i:i + size], *args) for each `size`-item slice, one atomic call per slice; the returned lists joined in order."""
    items = list(items)
    out = []
    for start in range(0, len(items), size):
        out.extend(run_atomic(fn, items[start : start + size], *args))
    return out


def run_chunked(step_fn, state):
    """
    Calls step_fn(state) atomically until it returns True (done). step_fn does
    one bounded chunk of work per call (well under 10,000 steps) and keeps its
    progress in `state`; the budget check between chunks lets the script yield
    to the next tick.
    """
    while not run_atomic(step_fn, state):
        pass
