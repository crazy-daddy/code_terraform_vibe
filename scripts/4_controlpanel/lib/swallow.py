"""swallowed(): log an exception a caller catches and recovers from.

Every `except Exception:` that recovers (returns a default, skips an entry,
keeps looping) must still say what it caught -- call swallowed() as the
handler's first line:

    from swallow import swallowed

    try:
        count = port.count()
    except Exception as error:
        swallowed("storage.crop_automator_forage: port.count", error)
        continue

A broad except can't tell "the game said no" (component missing/unpowered, a
ValueError from the API) from "our code is wrong" (bad call signature, typo'd
name, missing key). The second kind must be logged to prevent silent failures
where a bug hides behind a benign fallback.

- Every caught error is logged at debug level, tagged with `where`
  ("module.function: call"). Consecutive identical errors at the same site
  are logged once, so a handler in a per-tick loop can't flood the
  console/log file.
- Error types that point at a bug in our code (_BUG_ERRORS) also print one
  warn line per site per script run, visible without debug output on.
  AttributeError on None is exempt: it is how a missing component (a None
  from get_component()) usually surfaces, which is an expected fallback.

Leave a handler silent only when it truly can't log, and say why in a
comment: inside an archive.transaction() updater (a log call there rejects
the transaction -- docs/components/data_archive.md), or in a script tier
without lib access. A narrow except that fully handles its case (e.g.
`except (TypeError, ValueError)` around a float() parse with a fallback) is
not swallowing anything and needs no call.

Imports nothing (not even archive or tree_console), so every lib -- including
lib/archive.py, which tree_console itself depends on -- can use it.
"""

from typing import Callable

_BUG_ERRORS = (TypeError, AttributeError, NameError, KeyError, IndexError, ZeroDivisionError)

# Console component, looked up on first use; per-site dedupe state.
_STATE: "dict[str, Console | None]" = {"console": None}
_HOOKS: "dict[str, Callable[[], None] | None]" = {"flush": None}
_LAST = {}
_WARNED = set()


def _is_bug_error(error):
    if not isinstance(error, _BUG_ERRORS):
        return False
    return not (isinstance(error, AttributeError) and "NoneType" in str(error))


def set_flush_hook(hook):
    """Register the callable that writes pending buffered console lines (tree_console.flush_all),
    so a swallowed-error line never overtakes lines logged before it."""
    _HOOKS["flush"] = hook


def _flush_pending():
    hook = _HOOKS["flush"]
    if hook is not None:
        hook()


def swallowed(where, error):
    """Log an exception the caller catches and recovers from. `where` names
    the call site ("module.function: call"); see the module docstring."""
    try:
        console = _STATE["console"]
        if console is None:
            console = get_component("console")
            if console is None:
                return
            _STATE["console"] = console
        message = f"{error!r}"
        if _is_bug_error(error) and where not in _WARNED:
            _WARNED.add(where)
            _flush_pending()
            console.print(f"[swallowed] {where}: {message} -- likely a code bug, recovered with a fallback.",
                          level="warn", timestamp=True)
        if _LAST.get(where) != message:
            _LAST[where] = message
            _flush_pending()
            console.print(f"[swallowed] {where}: {message}", level="debug", timestamp=True)
    except Exception:
        # Logging must never turn a recovered error into a crash; nothing
        # left to report it with.
        pass
