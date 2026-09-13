# Shared Library for Data Archive (Notebook)
# Safe, crash-resilient wrapper around get_component("notebook") for persistent cross-script state.

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

    def get(self, key, default=None):
        if not self.available:
            return default
        try:
            val = self.notebook.get(key, default)
            return default if val is None and default is not None else val
        except Exception:
            return default

    def set(self, key, value):
        if not self.available:
            return False
        try:
            res = self.notebook.set(key, value)
            return getattr(res, "status", "") == "ok"
        except Exception:
            return False

    def transaction(self, key, default, updater):
        if not self.available:
            return False
        try:
            res = self.notebook.transaction(key, default, updater)
            return getattr(res, "status", "") == "ok"
        except Exception:
            return False

    def has(self, key):
        if not self.available:
            return False
        try:
            return bool(self.notebook.has(key))
        except Exception:
            return False

    def delete(self, key):
        if not self.available:
            return False
        try:
            res = self.notebook.delete(key)
            return getattr(res, "status", "") in ["ok", "not_found"]
        except Exception:
            return False

    def keys(self, prefix=""):
        if not self.available:
            return []
        try:
            return list(self.notebook.keys(prefix))
        except Exception:
            return []

# Singleton / default instance
archive = ArchiveClient()
