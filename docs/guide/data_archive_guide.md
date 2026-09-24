# Guide: data_archive_guide

## Data Archive

### Overview

Data Archive is persistent shared knowledge for scripts. Libraries share code, Signal Bus shares live coordination, and Data Archive stores learned data across script stops, saves, and reloads.

Data Archive unlocks with **Data Archive** research. Before that, `get_component("notebook")` returns `None`.

### Store and read

```
notebook = get_component("notebook")
fuel_table = {"slow": 0.8, "cruise": 1.0, "fast": 1.7}
written = notebook.set("rover.fuel_table", fuel_table)
if written.status != "ok":
  print(written.message)

saved = notebook.get("rover.fuel_table", {})
print(saved["cruise"])
```

`set()` is a gameplay command and returns `ActionResult`. `get()`, `has()`, and `keys()` are read-only queries and return their natural values directly.

### Atomic updates

`transaction(key, default, updater)` atomically reads, updates, and writes one key. It returns `ActionResult`; `.status == "busy"` means another transaction already owns that key.

```
def add_one(count):
  return count + 1

result = notebook.transaction("stats.samples", 0, add_one)
if result.status != "ok":
  print(result.message)
```

Updaters must be small pure functions: no `sleep()`, yielding actions, or world-mutating API calls.

### Manage entries

In **Computer > Data Archive**, use **View** to inspect or copy a complete value, **Edit** to change it, or **New entry** to add a key. The value field uses JSON: strings are quoted, and booleans and empty values use `true`, `false`, and `null`. Manual edits have the same storage limits as scripts and record your commander name as the writer.

**Save** replaces the complete value only if the entry has not changed since you opened it. A conflicting script or window update preserves your draft; **Copy value** copies it and **Refresh value** opens the current stored value. Scripts continue running and may write again after a successful manual save.

```
deleted = notebook.delete("rover.old_table")
if deleted.status == "not_found":
  print(deleted.message)

cleared = notebook.clear("scratch.")
print(cleared.status, cleared.count)
```

`delete()` returns `ActionResult`. `clear()` returns `CountResult`, whose `.count` is the exact number of entries removed.

### Value rules

Values must be JSON-safe: `None`, booleans, finite numbers, strings, lists/tuples, and dictionaries with string keys. Each stored value may contain up to **8** nested levels, **16,384** total nodes, and **4,096** characters per string or dictionary key. The root value, every contained value, and every list, tuple, or dictionary container each count as one node; dictionary keys do not. The exact result statuses are `"ok"`, `"invalid_key"`, `"entry_limit"`, `"invalid_value"`, `"not_found"`, and `"busy"`; every applicable command returns a precise `.message`. The **512**-entry limit and transaction contention are programmatically distinct.

Name keys by subsystem, such as `"rover.fuel_table"` or `"plants.recipe_scores"`. Use Signal Bus for live coordination and Data Archive for knowledge you want to keep.

*Guide / Automation Systems*
