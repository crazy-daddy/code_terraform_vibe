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
  "ghosts": { "logistics": 12 },
  "skipSystems": [],
  "keep": ["harvester_1"],
  "strict": false
}
```

| Field | Meaning |
| :--- | :--- |
| `name`, `target` | Labels; `name` lands in `summary.json`. `target` documents which group the run tests. |
| `default` | `real` or `off`: the mode of every group not listed under `subsystems`. |
| `subsystems` | Per group: `mode` plus that mode's parameters (defaults filled in; unknown names and parameters are errors). Groups and modes: [standins.md](standins.md). |
| `assign` | Moves a machine type to another group for this run (`{typeId: group}`). |
| `flows` | Item producers and consumers over any store, one pass every 100 ticks. Exactly one of `keep` (top the store up to N units, the old `--stock`), `rate_h` (add N per game hour; negative removes), `after` (remove units that arrived TICKS ago, the old `--drain`; checked every tick). `at` is `inventory` (default), a machine id, or `outpost:<id>` (that outpost's Warehouses, Storage Bins and Drone Depots; at home the Inventory first). |
| `archive` | Keys written once at start (`sim.setArchive`), e.g. manual orders or a stub another group would have published. |
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

## Output

`summary.json` carries `standins`:

| Field | Meaning |
| :--- | :--- |
| `scenario`, `modes` | The name and the effective mode per group (`system` is always `real`). |
| `ghosts` | Scripts removed per group, as counted for the allowance. |
| `allowance` | `{n, ghosts, steps}` at the last tick: real running scripts, ghosts, and the per-script steps per tick the scheduler granted. |
| `stopped` | Slot ids stopped per group. |
| `flows` | Per flow: `added`, `removed`. The old top-level `stocked` / `drained` are kept. |
| `wakes`, `trim` | Parker wakes (mode `park`); `{kept: {subnet: n}, stopped, done}` (mode `trim`). |
| `unclassified`, `counts` | Slots the registry could not place; slot count per group. |

The console shows one `standins: <group> = <mode>` line per non-real group at start and one `standins: power trim <subnet>: ...` line when the trim fires.

## Writing a scenario for a new target

1. Pick the target group and set it `real`; keep `orchestrator` real unless the test is about running without it (it publishes `production.demand`, `power.shedded`, `cash.budget`, parking and the census).
2. Set `default: "off"`, then put back as `real`, `park` or `trim` what the target reads from the live world (power for anything that draws it; terraforming when the test reads the atmosphere).
3. Read the boundary of every `off` group in [standins.md](standins.md) and add a flow for each item the target consumes from it or produces into it. The run warns `standins: <group> is off and the scenario has no flows` when a group that moves items is off and no flow exists.
4. Run 20 game minutes against the same save with everything `real`; compare `metrics.jsonl` (TP, credits, atmosphere) and `errored`. Record the pair in [ab_results.md](ab_results.md) when the scenario is checked in.
