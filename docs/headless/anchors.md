# Simworker patches and anchors

`simhost.mjs` loads the decompiled simworker (`internals/terraform_decompiled/simworker/deobfuscated.js`) and patches it at run time before caching the module (`devtools/simulation/headless/.cache/sim-<hash>.mjs`, gitignored). The game is updated regularly and every build is minified again, so every local and top-level binding gets a new name. Patches therefore never rely on a minified name.

## Policy

1. **Anchor on stable strings only**: type-id literals (`` `oxygen_generator` ``), property names (`.co2`, `.heatUnits`, `.pressure`, `ratePerGameHour`, `_level`, `e.data.tier ?? 1`), config keys (`totalStepsPerTick`), log strings. A minified local is captured from the matched line with `(\w+)`, never written into the pattern.
2. **Exactly one match**: a pattern that matches zero or several times switches its feature off, warns `[headless] simworker changed: <what>` and goes on. `sim.features` says which patches are on; a run that needs an off feature falls back one level (for example `scale` to `standin`) and says so.
3. **One table per concern**: bootstrap names in `BOOTSTRAP_PATTERNS` (these throw, the harness cannot run without them), optional features next to them (`SYSTEM_TRY`, `SIGNATURE_PUSH`, `MACHINE_REVISION`, `CONSOLE_OUTPUT`), the stand-in patches in `SCALE_PATTERNS` (`anchors.mjs`, imported by `simhost.mjs`; the cache hash covers both files).
4. **Synthetic tests**: a regex is unit-tested on a three-line snippet written for the test, never on copied worker code (this repo is public; `internals/` is private).
5. **No decompiled code in tracked files**: only the stable strings a pattern needs.

## Patches in place

| Feature (`sim.features`) | Anchor | Purpose |
| :--- | :--- | :--- |
| bootstrap (`BOOTSTRAP_PATTERNS`) | `SimHost readTick`, `tickRate`, ... | sim core, host, state load and serialize, command registry, config object |
| `systemTiming` | the per-system `try` blocks and `TICK` logs | wall time per system, `--skip-systems` |
| `stickyFluids` | the fluid-network signature push | empty tanks keep their fluid type (optional since build e1986ce) |
| `machineRevision` | the machine revision counter | `sim.undeploy()` |
| `freeDebug` | the console output call | debug lines do not pause scripts |
| `gameVersion`, `worldGen`, `poiList` | literals | version guard, new-game world generation, POI list |
| `scale` | `SCALE_PATTERNS` in `anchors.mjs`: the three atmosphere output lines (`.co2`, `.planet.temperature.heatUnits`, `.pressure`; the data local is the `let <data> = <machine>.data;` of the enclosing loop, found by looking back), the fluid drain (`` `${<port>.portType}_level` `` then `.ratePerGameHour *`) and the power draw (`.data.tier ?? 1, .data.tierUpgrade ?? 0`). All five or none. | N machines in one record ([standins.md](standins.md), Level 2) |

No patch is needed for the virtual script count: `sim.config.interpreter.totalStepsPerTick` is the scheduler's own config object, written per tick.

## After a game update

Part of the checklist in [dev_workflow.md §10c](../cheatsheet/dev_workflow.md):

1. Rebuild the cache by running any headless command; the first run prints every `[headless] simworker changed:` line. Each one is a lost feature or a pattern step slower than `SLOW_STEP_MS` (a scan gone quadratic).
2. Run `node --test "devtools/simulation/headless/test/*.test.mjs"`; with `internals/` present the anchor test (`test/anchors.test.mjs`) loads the real worker and fails on any pattern that does not match exactly once.
3. `node devtools/simulation/headless/anchors.mjs` prints the feature table and each `scale` anchor's match count, exit 1 on any miss.
4. For a lost pattern, grep the new worker for the stable string, read the surrounding lines, and update only the pattern. `python devtools/game_update/simworker_diff.py` lists code changes between builds ignoring renames, which usually shows why a site moved.
5. Re-run the A/B pair of any stand-in whose anchor changed ([ab_results.md](ab_results.md)).
