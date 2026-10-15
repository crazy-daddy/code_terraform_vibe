# Scenarios

A scenario tells `run.mjs` which subsystems run for real, which stand in, and which are off, and what keeps the target's inputs and outputs flowing. Code: [`scenario.mjs`](../../devtools/simulation/headless/scenario.mjs) (load, merge, validate), [`standins.mjs`](../../devtools/simulation/headless/standins.mjs) (groups, modes). Checked-in files: [`devtools/simulation/headless/scenarios/`](../../devtools/simulation/headless/scenarios/).

```
node devtools/simulation/headless/run.mjs --save SAVE --scenario devtools/simulation/headless/scenarios/plants_only.json --hours 1 --out out/x
```

## File format (`headless-scenario-v1`)

```json
{
  "$schema": "headless-scenario-v1",
  "name": "plants_only",
  "target": "plants",
  "profile": "../profiles/code_terraform.json",
  "default": "off",
  "subsystems": {
    "plants":       { "mode": "real" },
    "orchestrator": { "mode": "real" },
    "power":        { "mode": "trim", "warmupTicks": 600, "margin": 1.25 },
    "terraforming": { "mode": "park" }
  },
  "assign": { "seed_maker": "factory" },
  "flows": [
    { "item": "seeds_basic", "keep": 40, "at": "inventory" },
    { "item": "steel_ingot", "rate_h": 120, "at": "outpost:outpost_2" },
    { "item": "iron_ingot", "rate_h": -60, "at": "outpost:outpost_2" },
    { "item": "forage", "after": 600, "at": "inventory" }
  ],
  "archive": { "fabricator.manual_orders": {} },
  "sweep": { "fields": ["by", "vehicle"], "skipKeys": ["machine.activity"], "extraKeys": [] },
  "ghosts": { "logistics": 12 },
  "skipSystems": [],
  "keep": ["harvester_1"],
  "strict": false
}
```

| Field | Meaning |
| :--- | :--- |
| `name`, `target` | Labels; `name` lands in `summary.json`. `target` documents which group the run tests. |
| `profile` | The script-set profile ([standins.md](standins.md) "Profile"): a path relative to this file, or `none`. Absent: the repo's `profiles/code_terraform.json`. `--script-set` wins over it. |
| `default` | `real` or `off`: the mode of every group not listed under `subsystems`. |
| `subsystems` | Per group: `mode` plus that mode's parameters (defaults filled in; unknown names and parameters are errors). Groups and modes: [standins.md](standins.md). |
| `assign` | Moves a machine type to another group for this run (`{typeId: group}`). |
| `flows` | Item producers and consumers over any store, one pass every 100 ticks. Exactly one of `keep` (top the store up to N units, the old `--stock`), `rate_h` (add N per game hour; negative removes), `after` (remove units that arrived TICKS ago, the old `--drain`; checked every tick). `at` is `inventory` (default), a machine id, or `outpost:<id>` (that outpost's Warehouses, Storage Bins and Drone Depots; at home the Inventory first). |
| `archive` | Keys written once at start (`sim.setArchive`), e.g. manual orders or a stub another group would have published. A seeded key is left alone by the `off` stubs and by the left-over sweep ([standins.md](standins.md)). |
| `sweep` | The left-over sweep ([standins.md](standins.md) "Left-overs"): `false` turns the sweep and the revival guard off (the guard stays on for `scale` members); an object merges over the profile's: `fields` (owner fields; `"*"` = any string field), `skipKeys` (added to the profile's), `extraKeys` (whole keys deleted at every sweep). Per group, the stopping modes take `sweep: false` (`--standin biomass=off,sweep=false`) to leave that group's left-overs; that applies to groups listed under `subsystems`, a group that is `off` by `default` follows the top-level setting. |
| `ghosts` | Per group: the number of scripts the stand-in is to count toward the step allowance, overriding the stand-in's own count. See "Virtual script count" in [standins.md](standins.md). |
| `skipSystems` | Game systems to leave out (same as `--skip-systems`, global; a system is all or nothing). |
| `keep` | Slot ids never stopped, whatever their group's mode. |
| `strict` | `true` fails the run on a script slot the registry cannot classify (otherwise listed in `summary.standins.unclassified` and left running). |

## Flags

Flags merge over the file (flags win). The older flags are sugar for scenario entries:

| Flag | Scenario equivalent |
| :--- | :--- |
| `--standin SUB=MODE[,key=value,...]` | `subsystems.SUB = {mode, key: value}`; repeatable; numbers and booleans are parsed. |
| `--only-scripts A,B` | `default: "off"`, `keep: [A, B]`. |
| `--stock ITEM=N` | `flows += {item, keep: N, at: "inventory"}`. |
| `--drain ITEM:TICKS` | `flows += {item, after: TICKS, at: "inventory"}`. |
| `--park` | `subsystems.terraforming = {mode: "park"}` unless the file sets terraforming. |
| `--script-set PATH\|none` | `profile = PATH` (or `none`), over the file's `profile`. The flag's path is relative to the working directory, the file's to the scenario file. |

## Output

`summary.json` carries `standins`:

| Field | Meaning |
| :--- | :--- |
| `scenario`, `modes` | The name and the effective mode per group (`system` is always `real`). |
| `ghosts` | Scripts removed per group, as counted for the allowance. |
| `allowance` | `{n, ghosts, steps}` at the last tick: real running scripts, ghosts, and the per-script steps per tick the scheduler granted. |
| `stopped` | Slot ids stopped per group. |
| `flows` | Per flow: `added`, `removed`. The old top-level `stocked` / `drained` are kept. |
| `wakes`, `trim`, `standin` | Parker wakes (mode `park`); `{kept: {subnet: n}, rated: {subnet: {total, kept}}, stopped, restarted, restopped, evals, done}` (mode `trim`; `rated` in W, `kept` and `stopped` at the end, `restarted` and `restopped` count generators restarted and stopped after the trim (restarted ones again, kept ones under `floor` `keepMin`) over the run, `evals` re-evaluations run); `{scripts: {slot: file}, failed, guardOff, pool}` (modes `standin` and `scale`; `pool` is the last steam fraction). |
| `scale` | Mode `scale`: `{records: {survivor: N}, members: [id] (stopped, still deployed), refused: {id: reason}, stalled: [id], minLevel: {survivor: lowest port level seen}}`. |
| `topup`, `instant` | Mode `topup`: `{batteries, addedWh, subnets}` (powered batteries seen at the last tick, Wh they lacked over the run, the `subnets` list or `null` for all). Mode `instant`: `{jobs, savedS, wait}` (active jobs finished early, clock seconds of build time skipped, whether the builder-wait patch is on). |
| `mover` | Mode `mover`: `{moved: {item: units landed}, trips, pendingUnits, bought: {item: units}, buyFailed: {item: reason}}`. |
| `produce`, `cash` | Mode `produce`: `{rates: {item: units per hour}, added: {item: units}}` (its rows also appear in `flows` with `by: "produce"`). Mode `cash`: `{creditsPerHour, added}`. |
| `stubs` | Archive keys written for `off` groups (the profile's; this repo's: `power.shedded`, `cash.budget`, `wildlife.plan`, `biomass.retire`), seeded keys excluded. |
| `profile`, `sweep` | The script-set profile's name (`none` without one) and the effective sweep config (`false`, or `{fields, skipKeys, extraKeys}`). |
| `leftovers`, `sweepLive`, `revived`, `reviveRefused` | `{key: entries removed}` by the left-over sweep over the run; keys a running writer kept filling about stopped ids (swept on three passes in a row, then left alone); `{slot: n}` stopped scripts a real script started again and the guard stopped again, and `{slot: n}` where that re-stop was refused and the script keeps running ([standins.md](standins.md) "Left-overs"). |
| `unclassified`, `counts` | Slots the registry could not place; slot count per group. |

The console shows one `standins: <group> = <mode>` line per non-real group at start, one `standins: power trim <subnet>: ...` line when the trim fires and one per re-evaluation that restarts or stops generators again, one `standins: steam guard <heater>: ...` line per guard flip, and for `scale` one `standins: scale undeploy <id> refused (...)` line per member kept real and one `standins: scale record <id> (xN) starved: ...` line per stalled record, and for `mover` one `standins: mover buy <item> ...` line per item the Shop refused. The start line of an `off` group names its stubs (`; stubs power.shedded, cash.budget`), of `produce` its rates and of `cash` its credits per hour. The left-over sweep prints one `standins: swept N left-over key(s): <key> ×n, ... (setup|trim|pass|revive)` line per sweep with a hit, one `standins: sweep: <key> is written again about stopped ids ...` warning per key it leaves alone, and the revival guard one `standins: <group> slot <id> was started again by a real script; stopped again (n×)` warning per revival (three per slot, then the count only).

## Writing a scenario for a new target

1. Pick the target group and set it `real`; keep `orchestrator` real unless the test is about running without it (it publishes `production.demand`, `power.shedded`, `cash.budget`, parking and the census).
2. Set `default: "off"`, then put back as `real`, `park`, `trim` or `topup` what the target reads from the live world (power for anything that draws it; terraforming when the test reads the atmosphere).
3. Read the boundary of every `off` group in [standins.md](standins.md) and add a flow for each item the target consumes from it or produces into it. The run warns `standins: <group> is off and the scenario has no flows` when a group that moves items is off and no flow exists.
4. Run 20 game minutes against the same save with everything `real`; compare `metrics.jsonl` (TP, credits, atmosphere) and `errored`. Record the pair in [ab_results.md](ab_results.md) when the scenario is checked in.
