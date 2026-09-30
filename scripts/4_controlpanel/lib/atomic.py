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

Purity rule for everything passed to run_atomic()/run_chunked(): no game API
calls (no reads either, to be safe), no logging (a TreeConsole call reads the
clock and may write to the console, which raises inside a callback), no
sleep()/waits. Plain mutation of your own Python objects is fine.

ATOMIC_ENABLED = False makes run_atomic() call fn directly, for the case that
a game update closes the quirk.
"""

ATOMIC_ENABLED = True


def run_atomic(fn, *args):
    """fn(*args) as a single map() callback; returns its result."""
    if not ATOMIC_ENABLED:
        return fn(*args)
    return list(map(lambda _: fn(*args), (0,)))[0]


def run_chunked(step_fn, state):
    """
    Calls step_fn(state) atomically until it returns True (done). step_fn does
    one bounded chunk of work per call (well under 10,000 steps) and keeps its
    progress in `state`; the budget check between chunks lets the script yield
    to the next tick.
    """
    while not run_atomic(step_fn, state):
        pass
