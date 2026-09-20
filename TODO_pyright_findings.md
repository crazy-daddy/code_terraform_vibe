# Pyright findings (full-repo scan, 2026-09-20)

Generated via `npx pyright --outputjson` over the whole workspace, filtered to
exclude `inspirations/`, `docs/`, generated `.pyi` stubs, and the `"self"`/
`"panel"` `reportUndefinedVariable` false positives that only appear when
running Pyright outside the game's own extension (see
`docs/guide/programming_language_reference.md`'s "Typing and editor support":
`self`/`panel` are script-owner locals the extension injects, not something
a bare CLI run knows about).

Not yet triaged for real-bug-vs-false-positive; just the raw list to work
through later. Delete entries here as they're fixed or confirmed non-issues.

## Possibly-unbound variables (likely real bugs)

- `lib/bio.py:508` — `"active" is possibly unbound`
- `panel_7.py:159` — `"grid_count" is possibly unbound`

## Operator on `int | None`

- `lib/harvesting.py:59` — `-` not supported for `int | None` and `int | None`
- `lib/harvesting.py:78` — `<` not supported for `int | None` and `int | None`
- `lib/harvesting.py:79` — `+=` not supported for `int | None` and `Literal[1]`
- `lib/harvesting.py:81` — `>` not supported for `int | Unknown | None` and `int | None`
- `lib/harvesting.py:82` — `-=` not supported for `int | Unknown | None` and `Literal[1]`

## `.get()`/`.items()`/subscript on `None` (Optional access without a None-check)

- `lib/archive.py:24,33,42,51,59,68` — every method calls `self.notebook.get/.set/.transaction/.has/.delete/.keys` where `self.notebook` is typed `Optional`
- `lib/archive_cleaner.py:280,650` — `.items()`/`.get()` on `None`
- `lib/archive_cleaner.py:689` — `<`/`>` operators not supported for `None`
- `lib/archive_cleaner.py:733` — `None` used as an iterable
- `lib/bio.py:767` — `.get()` on a `CommsMessage`-typed value that's also `Optional`
- `lib/drone_claims.py:87,90,91,98` — `.get()`/subscript on `None`
- `lib/drone_mining.py:188` — subscript on `None`
- `lib/fabricator.py:87,88,91` — `.get()` on `None`
- `lib/mining.py:325` — `.get()` on `None`
- `lib/mining_reservations.py:94` — `.items()` on `None`
- `lib/outpost_mining.py:316` — subscript on `None`
- `lib/outpost_reagents.py:69` — subscript on `None`
- `lib/pioneer.py:678,706,708,709` — `.get()`/subscript on `None`
- `lib/power.py:144,313,373,416` — subscript on `None`
- `lib/power.py:449` — `.elapsed_game_hours` on `None`
- `lib/production.py:374,395` — `.items()` on `None`
- `lib/production.py:410` — `<=` not supported for `None`
- `lib/profiling.py:88,113` — `.get()` on `None`
- `lib/rover.py:156` — `.get()` on `None`
- `lib/smelter.py:102,103,110` — `.get()` on `None`
- `lib/terraforming.py:34,54` — subscript on `None`
- `lib/vehicle_claims.py:104,107,114,410` — `.get()`/subscript/`.items()` on `None`
- `panel_2.py:61` — `*` not supported for `None`

## Puzzle/lore scripts: `connect`/`transmit` on `None` (all same shape, likely one root cause)

- `cold_boot.py:63,64`
- `corrupted_archive.py:28,29`
- `data_tablet.py:31,32`
- `drifting_signal.py:4,21`
- `relay_hack.py:25,26`
- `sealed_vault.py:59,60`
- `terminal_breach.py:59,60`
- `three_echoes.py:17,18`
- `uplink.py:2,4,5` (also `get_value`)
- `xenogenetics.py:14,15`

## Attribute access on wrong/narrower component type

- `bio_glow_diagnostic.py:23` — `.outpost` not on `Component`
- `lib/production.py:208` — `.current_order` not on `Component`
- `lib/production.py:295` — `.fluid` not on `OutpostNetworkComponent`

## `_ct_bytes`/dict-update overload mismatches (archive-notebook typed-dict plumbing)

- `lib/archive_cleaner.py:178,180,294,298,557,564,643`
- `lib/outpost_mining.py:319,320`
- `lib/outpost_reagents.py:73,74`
- `lib/vehicle_claims.py:265,267,408,416`
- `lib/vehicle_energy.py:209`
- `lib/drone_mining.py:143`

## Other argument-type mismatches

- `lib/storage.py:532,585` — passing `float` where `transfer_to` wants `int`
- `panel_2.py:96`, `panel_3.py:138` — slice argument type mismatch on `__getitem__`

## Mixin self-typing (separate investigation, see memory `feedback_no_imports_in_game.md`)

The `lib/vehicle.py:29-34` / `lib/drone.py:31-36` "Class cannot derive from
itself" errors that showed up in the first pass of this scan were caused by
a since-reverted experimental change (fake `_Base` class on the 11 `lib/`
mixins) and are NOT present in the current codebase. Not included above.
