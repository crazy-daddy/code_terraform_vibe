# Script Interpreter Benchmark

Measured with [`devtools/panel_benchmark.py`](../devtools/panel_benchmark.py) in a `control_panel` script slot. Time is `clock.elapsed_seconds()` (simulation seconds). Each case repeats a small chunk until one timed run lasts at least 2 s; the cost per iteration is `dt / iterations`. Only pure local computation was measured (no game API calls).

## How to read the numbers

- `dt` moves in 0.05–0.1 s steps, so per-iteration figures are good to a few percent (`1350` vs `1375` is the same cost).
- The values repeat exactly across unrelated cases (`1350`, `1700`, `2700`, `3400` µs), which fits a **step-counting cost model**: the interpreter charges roughly a fixed time per evaluated step, not per byte of data touched. This is an inference from the pattern, not a documented guarantee.
- One step is about **350 µs** of simulation time here (the empty loop iteration), so a script gets on the order of 2,800 steps per simulation second in this container. Other containers, game speed or the Advanced Scripting settings may differ; rerun the benchmark to check.

## Results

| Case | µs / iter | × empty loop |
| --- | ---: | ---: |
| `for i in range(n): pass` | 350 | 1.0 |
| list comprehension, per element | 350 | 1.0 |
| f-string | 1,050 | 3.0 |
| `len(list)` | 1,350 | 3.9 |
| `clock.elapsed_seconds()` | 1,350 | 3.9 |
| `list + list` (3+3) | 1,350 | 3.9 |
| `while i < n: i += 1` | 1,700 | 4.9 |
| `max(a, b)` | 1,700 | 4.9 |
| `list.append` in a loop | 1,700 | 4.9 |
| slice `mixed[1:4]` | 1,700 | 4.9 |
| slice assign `mixed[1:4] = row` | 1,700 | 4.9 |
| call `fn()` (0 args) | 1,750 | 5.0 |
| `[0] * 1156` | 1,750 | 5.0 |
| list read `data[i % 1000]` | 2,050 | 5.9 |
| list write `data[i % 1000] = i` | 2,050 | 5.9 |
| call `fn(a, b)` | 2,300 | 6.6 |
| `a = i % 32; b = i // 32` | 2,700 | 7.7 |
| arithmetic `(x + i * 2) % 7` | 2,700 | 7.7 |
| `if/elif` chain, 3 tests | 3,400 | 9.7 |
| iterate an 8-tuple | 3,400 | 9.7 |
| dict read + write | 4,000 | 11.4 |
| 3 slices + concat + `count` (3×3 neighbourhood) | 6,600 | 18.9 |
| 8-neighbour Python loop (3×3 neighbourhood) | 28,400 | 81.1 |

Operations over a 1000-element list:

| Operation | µs / iter | × empty loop |
| --- | ---: | ---: |
| `list.count(5)` | 1,750 | 5.0 |
| `999 in data` | 1,375 | 3.9 |
| `sum(data)` | 1,375 | 3.9 |
| `sorted(data)` | 1,375 | 3.9 |
| Python loop counting `== 5` | 1,350,000 | 3,857 |
| Python loop searching for 999 | 1,350,000 | 3,857 |
| Python loop summing | 700,000 | 2,000 |

## Interpretation

1. **A builtin call costs about the same whatever the data size.** `sum`, `sorted`, `list.count`, `in`, slicing, list concatenation and `[0] * 1156` cost 4–5 steps on a 1000-element list, the same as `len()`. The equivalent Python loop costs about 1,000× more. Any per-element work that a builtin can do should use the builtin.
2. **A `for` iteration costs about 1 step; each further statement costs several.** `while i < n: i += 1` is 4.9 steps per pass, an `if/elif` test is about 3 steps, an arithmetic expression with `%` about 7. Hot loops get cheaper by removing statements from the body, not by shortening the loop.
3. **A comprehension is far cheaper than a loop that appends.** The comprehension costs 1.0 per element; `for` + `append` costs 4.9. Build lists with comprehensions where the element expression is simple.
4. **A function call costs about 4 steps plus about 0.8 per argument.** Inline helpers that sit in the innermost loop.
5. **`dict` access is dearer than `list` indexing** (11.4 vs 5.9 for the same read/write pattern with a modulo). Prefer flat lists indexed by integer for dense grids.
6. **A component call is as cheap as a builtin** (`clock.elapsed_seconds()` costs the same as `len()`). The API section below extends this to the other read-only components.
7. **Slices and native counting beat neighbour loops.** The 3×3 neighbourhood count costs 18.9 steps with three slices, a concatenation and `count`, against 81.1 for an 8-element Python loop. Padding a grid with a wall ring turns neighbour lookups into index offsets with no bounds checks.
8. **`range(n)` materialises a list.** It is bounded by the collection limit in Settings → Game → Advanced Scripting (50,000 items at most), so long loops need a chunked outer loop or a `while`. A `while` pass costs about 5 steps against 1 for `for`.
9. **`frozenset` is not available** in the interpreter.
10. **The Playground aborts long-running code.** Run anything that takes more than a few seconds in a script slot instead.

## API cases

`devtools/panel_benchmark.py` also times game API calls. Each case is skipped with a message when its component is missing in the save. Costs are reported in the same units as above (µs per call, and × the empty loop).

**Non-interruptive** (`RUN_API`, on by default): read-only calls, plus one scratch archive key and one scratch Signal Bus channel (`bench.tmp` for both) that are removed at the end, also when the run fails.

| Group | Cases |
| --- | --- |
| Lookup | `get_component("clock")`, `get_component(<building id>)` |
| Clock / scheduler | `clock.tick()`, `clock.get_time()`, `sleep(0.1)` |
| Console | `console.now()`, `print()`, `console.debug()` (labelled with `CONSOLE_DEBUG_STATE`) |
| Archive (`notebook`) | `get` and `has` on a missing key; `set`, `get`, `transaction` on a small dict and on a 100-entry dict; `keys(prefix)`; reading `.status` from an `ActionResult` |
| Signal Bus (`comms`) | `broadcast`, `latest`, `latest_info`, `send` + `receive`, `queue_size`, `pending`, `channels` |
| Outposts | `outposts()`, `home()`, `coords()`, `buildings()`, `buildings(type_id)`, reading `.type_id` over the building refs |
| Machines | storage building (`storage_bin`, `warehouse` or `large_warehouse`) `count` / `fill_percent` / `stacks`, battery `get_level`, `inventory` `count` / `get_used` / `stacks` |
| Power / fleet | `power_control.total()`, `grids()`, `is_powered(id)`, `fleet.vehicles()`, `fleet.drones()` |
| World | `nocturna` `terraform_progress` / `biome_at` / `points_of_interest`, `atmosphere.get_o2()` |
| Reference data | `research.unlocked()` / `is_unlocked()`, `item_catalog.lookup()`, `shop.get_catalogue()`, `orders.list_orders()`, `journal` `is_empty` / `biomass_coords` |

**Console comparison** (`CONSOLE_ONLY`): runs only the console cases. Run it once with debug output enabled in the console UI and once with it disabled, setting `CONSOLE_DEBUG_STATE` to `"shown"` or `"hidden"` each time, to see whether the 0.1 s cost of `console.debug()` depends on the debug filter (it does not: both runs measured 0.1 s per call). `print()` is documented as equivalent to `console.info()`, and `warn` and `error` only change the level, so only `print()` and `debug()` are benchmarked.

**Interruptive** (`RUN_INTERRUPTIVE`, off by default): each case briefly changes real game state and restores it in a `finally` block.

| Case | Constant that enables it | Effect |
| --- | --- | --- |
| `transmitter.connect("earth")` | none | Re-opens the Earth link. |
| `power_control.set_powered` off + on | `BENCH_POWER_MACHINE_ID` | Switches one machine off and on again; skipped unless `can_power_off()` allows it; the original state is restored. |

Not covered on purpose: inventory transfers (each call waits for the feeder cycle, so it measures game time, not interpreter cost), shop buy/sell (spends credits), vehicle and drone commands, blueprint placement, order submission.

### API results

Same units and container as above (empty loop = 350 µs). Every call is a single call from a loop, so each figure includes about 1 step of loop overhead.

| Call | µs / call | × empty loop |
| --- | ---: | ---: |
| `get_component("clock")` lookup | 1,523 | 4.5 |
| `get_component(<building id>)` lookup | 1,602 | 4.7 |
| `clock.tick()` / `clock.get_time()` | 1,438 | 4.3 |
| `console.now()` | 1,500 | 4.4 |
| archive `get` (missing key) / `has` | 1,750 | 5.2 |
| archive `get` small dict | 1,750 | 5.2 |
| archive `get` 100-entry dict | 1,875 | 5.6 |
| archive `keys(prefix)` | 1,875 | 5.6 |
| archive `set` small dict | 2,422 | 7.2 |
| archive `set` 100-entry dict | 2,578 | 7.6 |
| archive `transaction` small dict | 3,281 | 9.7 |
| archive `transaction` 100-entry dict | 3,438 | 10.2 |
| archive result `.status` read | 1,156 | 3.4 |
| Signal Bus `latest` / `latest_info` / `queue_size` / `pending` | 1,750 | 5.2 |
| Signal Bus `channels()` | 1,500 | 4.4 |
| Signal Bus `broadcast` | 2,266 | 6.7 |
| Signal Bus `send` + `receive` | 4,219 | 12.5 |
| `outpost_network.outposts()` / `home()` / `home.coords()` | 1,563 | 4.6 |
| `home.buildings()` (30 refs) | 1,797 | 5.3 |
| `home.buildings("storage_bin")` | 2,109 | 6.2 |
| read `.type_id` over 30 refs (whole loop) | 32,500 | 96.3 |
| storage `fill_percent()` / `stacks()` (large warehouse) | 1,602 | 4.7 |
| storage `count(id)` (large warehouse) | 1,953 | 5.8 |
| `battery.get_level()` | 1,602 | 4.7 |
| `inventory.get_used()` / `stacks()` | 1,602 | 4.7 |
| `inventory.count(id)` | 1,953 | 5.8 |
| `power_control.total()` | 1,602 | 4.7 |
| `power_control.is_powered(id)` | 1,953 | 5.8 |
| `power_control.grids()` | 1,797 | 5.3 |
| `fleet.vehicles()` / `drones()` | 1,797 | 5.3 |
| `nocturna.terraform_progress()` | 1,563 | 4.6 |
| `nocturna.biome_at(0, 0)` | 2,266 | 6.7 |
| `nocturna.points_of_interest()` | 1,797 | 5.3 |
| `atmosphere.get_o2()` | 1,563 | 4.6 |
| `research.unlocked()` | 1,797 | 5.3 |
| `research.is_unlocked(id)` / `item_catalog.lookup(id)` | 1,875 | 5.6 |
| `shop.get_catalogue()` / `orders.list_orders()` | 1,797 | 5.3 |
| `journal.is_empty(0, 0)` | 2,266 | 6.7 |
| `journal.biomass_coords()` | 1,797 | 5.3 |
| `sleep(0.1)` | 100,000 | 296 |
| `print("bench")` | 100,000 | 296 |
| `console.debug("bench")`, debug output shown or hidden | 100,000 | 296 |
| `transmitter.connect("earth")` (interruptive) | 2,500 | 7.4 |
| `power_control.set_powered` off + on (interruptive) | 5,000 | 14.8 |

Storage, battery and `is_powered` were measured on a large warehouse and a battery found across all outposts. The baseline empty loop was 337.5 µs in that run, so the × column moves by a few percent against the earlier table.

### API interpretation

1. **A read-only API call costs about one builtin call.** Everything that only reads state sits between 4.3× and 6.7× (a plain `len()` is 4.1×). The result size does not matter: `home.buildings()` with 30 refs costs 5.3×, `archive.get` of a 100-entry dict costs 5.6× against 5.2× for a small one.
2. **Arguments and heavier bookkeeping add about 1 step each.** Calls with two arguments (`biome_at(0, 0)`, `journal.is_empty(0, 0)`) and calls taking a type filter cost 6.2–6.7×; `archive.set` costs 7.2–7.6×; `broadcast` 6.7×.
3. **`archive.transaction` costs about 4 steps more than `set`** (9.7–10.2×), the price of one call to the updater function. Use `set` when the previous value is not needed, and keep one `transaction` per logical update.
4. **`send` + `receive` is two calls** (12.5×, about 6 steps each). `latest()` on a broadcast channel is 5.2×.
5. **Attribute reads on returned objects cost about 2 steps.** Reading `.type_id` over 30 refs costs 3.2 steps per element including the loop iteration; a `.status` read costs 2.4. Read each field once and keep it in a local.
6. **`get_component()` lookup is cheap** (4.5×), so wrapper creation does not need caching for cost reasons. Cache it only where a wrapper carries state (for example the transmitter connection).
7. **`sleep(0.1)`, `print()` and `console.debug()` each cost exactly 0.1 s of simulation time**, about 290 steps: forty calls take 4.00 s. `console.debug()` costs the same with debug output shown or hidden in the console, so a hidden line is still paid for. `info` is documented as identical to `print`, and `warn` and `error` only change the level. `console.now()` costs a normal 4.3×. Treat every console write as an expensive call: build one string and log once instead of logging inside hot loops or per item.
8. **Storage, battery and power reads follow the same rule** (`fill_percent`, `stacks`, `get_level`, `total` at 4.7×; calls that take an item or machine id at 5.8×) on the warehouse in that save; how the cost scales for a much fuller warehouse has not been measured.
9. **Switching power and re-opening the Earth link are instant for the script.** `transmitter.connect` costs 7.4×; `set_powered` off + on costs 14.8× for two calls, so there is no settle time to wait for.
10. **Budget:** with about 350 µs per step and about 1.5–2.3 ms per API call, a script can make roughly 450–650 API calls per simulation second, and none of them cost more when the returned collection is large.

## Console and limits

Measured with [`devtools/console_multiline_test.py`](../devtools/console_multiline_test.py) (Advanced Scripting settings at their maximum).

| Finding | Result |
| --- | --- |
| One `console.print` of a 20-line string | 0.10 s |
| Five single-line prints | 0.50 s |
| `\n` inside one message | Renders as separate lines; blank lines are kept. The timestamp prefixes only the first line. |
| `console.print` of 1,000 / 5,000 / 9,000 / 20,000 characters | All accepted. Larger sizes were not tested. |
| String limit at the maximum setting | 100,000 characters (a 128,000-character string raises `OverflowError`). |
| Collection limit at the maximum setting | 50,000 items (a 64,000-item list raises `OverflowError`). |

- **Cost per console call, not per line:** a call costs 0.1 s whatever its length, so joining lines into one message costs a fraction of printing them separately.
- **Limits raise `OverflowError` and name themselves.** The message reads `string length 128,000 exceeds the current limit of 100,000` or `list exceeds the current limit of 50,000 items`. A script can read the active limit by building an oversized string inside `try/except OverflowError` and parsing the last number in the message. Both limits can be set lower in Settings → Game → Advanced Scripting (10,000 at the default), so any buffered console text needs a cap that adapts to the setting.
- **Stopping a script from the UI does not unwind it.** A `try/finally` around a loop never runs its `finally` block when Stop is clicked, so cleanup and log flushing cannot rely on it.
- **`type(x)` returns a string,** so `type(x).__name__` raises `AttributeError`. Use `type(x)` directly.

## Load dependence

The per-step cost is not fixed: scripts appear to share one interpreter budget. The same Harvester planning step (script freshly started, same field) measured with its own tick counter:

| Other scripts | Planning step | Phases (ticks) |
| --- | ---: | --- |
| All running | 598 ticks | cells 11, reload 291, publish 75, decide 196 |
| All stopped | 181 ticks | cells 3, reload 87, publish 24, decide 59 |

About 3.3× slower with everything running, and the `cells` phase (one API call plus a 192-item comprehension, ~2 ticks at the 350 µs figure above) took 11. So every script's per-tick work, including idle polling, slows every other script: prefer longer idle sleeps and less work per poll over faster polling. The `QUICK` switch below measures the empty-loop cost under each load.

## Reproducing

Copy `devtools/panel_benchmark.py` into a `control_panel` script slot and run it. It prints the per-case cost, then the ratios relative to the empty loop, for each enabled group (`RUN_LOCAL`, `RUN_API`, `RUN_INTERRUPTIVE` at the top of the script), and takes several minutes. Lower `MIN_SECONDS` to shorten it.

**Quick load comparison** (`QUICK = True`, label the run with `QUICK_LABEL`): times only the empty loop, `len()`, a 0-arg call and `clock.elapsed_seconds()`, `QUICK_ROUNDS = 5` times each for `QUICK_SECONDS = 1.0`, and prints min / median / max plus one summary line (under a minute). Run it with everything running, with the other scripts stopped, and in an empty game, at the same game speed and Advanced Scripting settings.
