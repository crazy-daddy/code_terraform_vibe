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
6. **A component call is as cheap as a builtin** (`clock.elapsed_seconds()` costs the same as `len()`). This says nothing about heavier component methods; see the API benchmark when one exists.
7. **Slices and native counting beat neighbour loops.** The 3×3 neighbourhood count costs 18.9 steps with three slices, a concatenation and `count`, against 81.1 for an 8-element Python loop. Padding a grid with a wall ring turns neighbour lookups into index offsets with no bounds checks.
8. **`range(n)` materialises a list.** It is bounded by the collection limit in Settings → Game → Advanced Scripting (50,000 items at most), so long loops need a chunked outer loop or a `while`. A `while` pass costs about 5 steps against 1 for `for`.
9. **`frozenset` is not available** in the interpreter.
10. **The Playground aborts long-running code.** Run anything that takes more than a few seconds in a script slot instead.

## API cases

`devtools/panel_benchmark.py` also times game API calls. Each case is skipped with a message when its component is missing in the save. Costs are reported in the same units as above (µs per call, and × the empty loop). Results for this section are added to this file after the first run in game.

**Non-interruptive** (`RUN_API`, on by default): read-only calls, plus one scratch archive key and one scratch Signal Bus channel (`bench.tmp` for both) that are removed at the end, also when the run fails.

| Group | Cases |
| --- | --- |
| Lookup | `get_component("clock")`, `get_component(<building id>)` |
| Clock / scheduler | `clock.tick()`, `clock.get_time()`, `sleep(0.1)` |
| Console | `console.now()`, `console.debug()` |
| Archive (`notebook`) | `get` and `has` on a missing key; `set`, `get`, `transaction` on a small dict and on a 100-entry dict; `keys(prefix)`; reading `.status` from an `ActionResult` |
| Signal Bus (`comms`) | `broadcast`, `latest`, `latest_info`, `send` + `receive`, `queue_size`, `pending`, `channels` |
| Outposts | `outposts()`, `home()`, `coords()`, `buildings()`, `buildings(type_id)`, reading `.type_id` over the building refs |
| Machines | storage bin `count` / `fill_percent` / `stacks`, battery `get_level`, `inventory` `count` / `get_used` / `stacks` |
| Power / fleet | `power_control.total()`, `grids()`, `is_powered(id)`, `fleet.vehicles()`, `fleet.drones()` |
| World | `nocturna` `terraform_progress` / `biome_at` / `points_of_interest`, `atmosphere.get_o2()` |
| Reference data | `research.unlocked()` / `is_unlocked()`, `item_catalog.lookup()`, `shop.get_catalogue()`, `orders.list_orders()`, `journal` `is_empty` / `biomass_coords` |

**Interruptive** (`RUN_INTERRUPTIVE`, off by default): each case briefly changes real game state and restores it in a `finally` block.

| Case | Constants that enable it | Effect |
| --- | --- | --- |
| `transmitter.connect("earth")` | none | Re-opens the Earth link. |
| `power_control.set_powered` off + on | `BENCH_POWER_MACHINE_ID` | Switches one machine off and on again; skipped unless `can_power_off()` allows it; the original state is restored. |
| Storage bin transfer in + out | `BENCH_TRANSFER_BIN_ID`, `BENCH_TRANSFER_ITEM` | Moves one item from the inventory to the bin and back each iteration; any leftover is moved back at the end. Needs Auto Feeders research, and each call waits for the feeder cycle, so the time is the game's transfer cycle, not interpreter cost. The last returned statuses are printed; only `ok` timings mean anything. |

Not covered on purpose: shop buy/sell (spends credits), vehicle and drone commands, blueprint placement, order submission.

## Reproducing

Copy `devtools/panel_benchmark.py` into a `control_panel` script slot and run it. It prints the per-case cost, then the ratios relative to the empty loop, for each enabled group (`RUN_LOCAL`, `RUN_API`, `RUN_INTERRUPTIVE` at the top of the script), and takes several minutes. Lower `MIN_SECONDS` to shorten it.
