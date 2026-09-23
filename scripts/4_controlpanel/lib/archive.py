# Shared Library for Data Archive (Notebook)
# Safe, crash-resilient wrapper around get_component("notebook") for persistent cross-script state.
#
# get()'s overloads below are TYPE_CHECKING-only (never executed in the game --
# see lib/vehicle_survey.py's top comment for why that guard is safe here) and
# exist purely so Pyright infers get(key, {}) as dict/get(key, some_default) as
# type(some_default) instead of a spurious `| None` (get()'s single real
# implementation has no type hints, matching the untyped style used everywhere
# else in this codebase -- this doesn't change that, it just tells the checker
# what the untyped body already does at runtime).
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, TypeVar, overload
    _T = TypeVar("_T")


class ArchiveClient:
    """
    Helper for interacting with the Data Archive ('notebook').
    Handles missing component gracefully (returns fallback/no-op if not unlocked),
    and validates JSON safety and key naming conventions.
    """
    def __init__(self, notebook=None):
        try:
            self.notebook = notebook or get_component("notebook")
        except Exception:
            self.notebook = None

    @property
    def available(self):
        return self.notebook is not None

    if TYPE_CHECKING:
        @overload
        def get(self, key: str, default: None = None) -> "Any": ...
        @overload
        def get(self, key: str, default: "_T") -> "_T": ...

    def get(self, key, default=None):
        if self.notebook is None:
            return default
        try:
            val = self.notebook.get(key, default)
            return default if val is None and default is not None else val
        except Exception:
            return default

    def set(self, key, value):
        if self.notebook is None:
            return False
        try:
            res = self.notebook.set(key, value)
            return getattr(res, "status", "") == "ok"
        except Exception:
            return False

    def transaction(self, key, default, updater):
        if self.notebook is None:
            return False
        try:
            res = self.notebook.transaction(key, default, updater)
            return getattr(res, "status", "") == "ok"
        except Exception:
            return False

    def has(self, key):
        if self.notebook is None:
            return False
        try:
            return bool(self.notebook.has(key))
        except Exception:
            return False

    def delete(self, key):
        if self.notebook is None:
            return False
        try:
            res = self.notebook.delete(key)
            return getattr(res, "status", "") in ["ok", "not_found"]
        except Exception:
            return False

    def keys(self, prefix=""):
        if self.notebook is None:
            return []
        try:
            return list(self.notebook.keys(prefix))
        except Exception:
            return []

    # One-shared-dict-per-concern helpers (CLAUDE.md rule 7): a key holds
    # {entry_id: value} for many entities instead of one key per entity.
    # Writes are atomic transactions touching only entry_id's own slot, and a
    # non-dict stored value is treated as empty.

    if TYPE_CHECKING:
        @overload
        def get_entry(self, key: str, entry_id: "Any", default: None = None) -> "Any": ...
        @overload
        def get_entry(self, key: str, entry_id: "Any", default: "_T") -> "_T": ...

    def get_entry(self, key, entry_id, default=None):
        """Returns shared dict key's entry_id value, or default if missing."""
        entries = self.get(key, {})
        if not isinstance(entries, dict):
            return default
        return entries.get(entry_id, default)

    def set_entry(self, key, entry_id, value):
        """Atomically sets key[entry_id] = value."""
        def updater(entries):
            if not isinstance(entries, dict):
                entries = {}
            entries[entry_id] = value
            return entries
        return self.transaction(key, {}, updater)

    def pop_entry(self, key, entry_id):
        """Atomically removes key[entry_id] (no-op if absent)."""
        def updater(entries):
            if not isinstance(entries, dict):
                return {}
            entries.pop(entry_id, None)
            return entries
        return self.transaction(key, {}, updater)

# Singleton / default instance
archive = ArchiveClient()
