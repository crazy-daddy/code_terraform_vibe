# A/B results: dynamic Pioneer roles, Stage 3 on

Continues [ab_results.md](ab_results.md) (Stages 1-2 are there; that file is at the 64 KB docs cap). Plan:
[dynamic_roles/README.md](../plans/dynamic_roles/README.md).

## Dynamic roles Stage 3: miners (2026-10-20)

Code: branch `agent/role-stage3`. Save `mvdnuhjh_rbjww6`, real scripts, `--include-autoplay --auto-approve 3000`.
Runs A and B: 2 h, `main` `adf497a` vs branch `6d22386`. Runs C to E: 1.5 h, branch only, scenario `full_ore_o1`
(`default: real`; flows `keep: 1800` of `iron_ore`, `silicon`, `titanium` at `outpost:outpost_1`, the ore stock
target), so the two miners there run out of work.

| | A main | B branch | C `6d22386` | D `a446bf5` | E `5260568` |
| :--- | ---: | ---: | ---: | ---: | ---: |
| errored machines / swallowed bugs | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| TP at the end | 235,727 | 235,727 | 235,126 | 235,126 | 235,126 |
| credits at the end | 23,921 | 23,921 | 36,621 | 36,621 | 25,371 |
| stockpile trips / stand-bys at stock target | 128 / 4 | 129 / 4 | 60 / 11 | 61 / 12 | 74 / 43 |
| miners refit to hauler (`outpost_1`) | | 0 | 2 | 2 | 1 |
| miner slots at the end | `miner:0..3` | `outpost_1` 2, `outpost_2` 2 | `outpost_2` 2 | `outpost_2` 2 | `outpost_1` 1, `outpost_2` 2 |

Findings:

1. **No change without idle miners (A vs B).** The miners stayed busy (STOCK reached 4 times, never for
   `REFIT_IDLE_TICKS`); TP and credits equal main. The branch holds per-outpost slots; the miner entry reads
   `keep 1, wanted 0` at both smelting outposts (STOCK band only, no NEED ore).
2. **The keep floor did not hold (C, D).** Both `outpost_1` miners refit to hauler, 133 ticks apart: the first
   still held its miner slot while fitting, so the second counted 2 miners. Counting one claim per vehicle by its
   newest tick (`a446bf5`) did not help (D): the slot refresh in the same `next_job()` stamped the old slot with
   the new slot's tick. Fixed in `5260568`: a switching Pioneer releases its old slot before the refit (a failed
   refit re-claims its role).
3. **Floor holds (E).** `pioneer_5` refit to hauler (decision to `Refitted` 321 ticks); `pioneer_6` stayed as
   `outpost_1`'s floor miner and stood by at the stock target (43 stand-bys). Credits in C/D are high from two
   miners' parts sold; the second hauler of C/D was sold again by the hauler cap (`decommission pioneer_6`).
4. **Not exercised:** a re-station (needs a NEED ore at one outpost while another has a surplus miner), the
   drones-haul miner sale, reach-unknown probing. Unit tests cover them.
