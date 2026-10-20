# Stage 3: miners join the dynamic roles

Design half of session 5 (Fable, 2026-10-20). The edit half (Opus) follows this file; every `file:line` was
verified on `main` at `adf497a`. Plan hub: [README.md](README.md).

## What the plan assumed, and what the code says

The plan expected `home_ore_demand` to become `outpost_ore_demand(outpost)` and `MineJob` to reuse it. Not
needed: Pioneer miners never call it. `home_ore_bands()`/`home_ore_demand()`
(`vehicle_mining.py:124-137`) serve Rovers (`RoverTargets`) and one diagnostics line (`job_mine.py:240`).
A Pioneer miner runs `MineJob(self, OutpostStockpile(self.home_base))` (`pioneer.py:132`), and
`OutpostStockpile` draws its demand from four vehicle methods: `stockpile_bands()` (:461),
`stockpile_headroom()`/`stockpile_room()` (:434-458), `remote_ore_need()` (:481) and `reach_ores()` (:338,
battery and speed of this vehicle). That is the feared fight: the orchestrator has no vehicle to ask.

The fight is already settled on the autoplay side. `autoplay/lib/building_plan.py:506` `ore_need(tick)` reads
the NEED raw ores per outpost host-free (`outpost_tier_deficits(_OutpostId(id), tick, live=False)` →
`split_need_stock` → `RAW_ORE_ITEM_IDS`), and every stationed miner publishes the ores it reaches
(`outpost_mining.publish_reach()`, read by `mineable_ores_by_outpost(tick)`, `outpost_mining.py:147-183`,
stale after `REACH_STALE_TICKS`). `role_demand.compute()` (`role_demand.py:140`) already holds
`deficits = {outpost_id: {band: {item: units}}}` for every network outpost. Miner demand is a pure function
of those two reads. Nothing in `OutpostStockpile` moves.

Three gaps remain, all small:

1. `job_for_role("miner")` stations the miner at `home_base`; after a refit `set_base()` moved `base_id` while
   `home_base` stays the commission origin (`vehicle.py:197-216`). It must use `base_id`, and `refit()`
   (`pioneer_refit.py:203-204`) resets every non-hauler to `home_base`.
2. Role slots are fleet-wide (`"<role>:<i>"`, `role_demand.py:251`); the foundation deferred per-outpost keys
   to this stage ([foundation.md](foundation.md) §2).
3. Autoplay keys its miner counts by `home` (`building_plan.py:549` `miner_homes`, `:453` `idle_unit`) and
   still retires idle miners (`build_providers.py:493-498`).

## Design

### Demand: `role_demand.miner_demand(deficits, reach, smelting)`

Pure. `deficits` as `compute()` builds it, `reach = outpost_mining.mineable_ores_by_outpost(curr_tick)`
(`{outpost_id: set(ores)}`), `smelting` = outpost ids with a Smelter (already computed).

Per outpost `oid` with a deficit:

- Raw-ore bands: keep only `RAW_ORE_ITEM_IDS` items with units > 0 per band. `vehicle_mining.ore_bands()`
  (:43) does this but lives in vehicle code; move `ore_bands()` and `sum_bands()` (:60) to `outpost_mining`
  and re-export them from `vehicle_mining` (so `role_demand` never imports the vehicle chain; the orchestrator's
  import chain runs as one capped execution).
- Reach: `reach.get(oid)` is a set → intersect the ores with it. `None` (no miner ever published from `oid`)
  → every ore counts, but `wanted` caps at 1: one miner goes as a probe, publishes the reach within its first
  `build_local_stockpile_candidates()`, and the next `publish()` (600 ticks) corrects the count. Without the
  cap an outpost whose sites are all out of reach would pull a miner per ore and send them all back after
  `REFIT_IDLE_TICKS`.
- `band_oid` = top band of the reachable raw-ore deficit; `need_ores` = ores at `NEED` or above.
- `wanted_oid = min(len(need_ores), MINER_SLOTS_PER_OUTPOST)` (new constant, 4, mirrors autoplay's
  `MAX_MINERS_PER_OUTPOST`; name it differently so the two stay greppable). STOCK-band ore alone gives
  `wanted 0`: the keep floor covers buffers, refits answer needs. This is the knob the plan names (see
  Tuning).
- `keep_oid = KEEP_MINERS` (new constant, 1) when `oid in smelting`, else 0.
- Ores a mining drill feeds are not filtered out (autoplay's `drilled_ores()` does, for commissions). A refit
  is cheap and reversible; a NEED deficit that persists next to a drill is real demand.

Entry: `{"band": max band_oid, "wanted": Σ wanted_oid, "keep": Σ keep_oid, "outposts": {oid: band_oid for
band_oid > NONE}, "slots": {oid: {"wanted": wanted_oid, "keep": keep_oid} for wanted_oid or keep_oid}}`.
`outposts` keeps its shape (`roles_card.py:80` reads it); `slots` is the only new key. `compute()` passes
`reach` and `smelting`; `publish()` unchanged.

### Slots: `"miner:<outpost>:<i>"`

- `claim_slot(role, name, tick, wanted, log=None, outpost=None)`: with `outpost`, keys are
  `f"{role}:{outpost}:{i}"`, `i < wanted`, and the record gets `"outpost": outpost`. A slot `name` already
  holds for `role` is kept only when its record's `outpost` equals the argument; otherwise a new slot is
  claimed and the caller releases the old one (`next_job` does, as for a role change).
- `claimed_counts()` unchanged. New `claimed_outposts(claims, tick, role) -> {outpost_id: n}` from the
  records' `outpost`.
- `pioneer.py:138` `_claim_role_slot`: `outpost=self.base_id if self.role == "miner" else None`, `wanted`
  stays `MAX_ROLE_SLOTS` (a working Pioneer always counts).
- `held_slot()` unchanged: it matches by `vehicle` and `role`, not by key.

### Switching

`switch_candidates(current, roles, claimed, outpost=None, by_outpost=None)` keeps its `[(role, wanted)]`
return (15 call sites). Changes inside:

- A miner's own band is `roles["miner"]["outposts"].get(outpost, NONE)`, its floor
  `slots.get(outpost, {}).get("keep", 0)` against `by_outpost.get(outpost, 0)`, its `no_work` = that band
  `NONE` and `slots.get(outpost, {}).get("wanted", 0) == 0`. A miner at an outpost without a Smelter and
  without a need is above its floor (count ≥ 1, keep 0) and leaves like any role without work (hauler
  fallback included).
- "miner" is a candidate for anyone, the current miner included (re-station), when some outpost `oid`
  (`oid != outpost` for a miner) has `outposts[oid] > band` (or `band == NONE`) and
  `slots[oid]["wanted"] > by_outpost.get(oid, 0)`; its `wanted` in the tuple is that outpost's `wanted`,
  sorted by that outpost's band like the other roles.
- New `miner_target(roles, by_outpost, outpost=None) -> (oid, wanted) | None`: the best such outpost (highest
  band, then most open slots, then id). `next_job` calls it when the chosen role is `"miner"` and passes
  `outpost=oid` to `claim_slot()` and `base=oid` to `refit()`.

`pioneer.py:152` `next_job`: compute `by_outpost = role_demand.claimed_outposts(claims, tick, "miner")` once;
pass `outpost=self.base_id if self.role == "miner" else None`. On a won slot, as now; the log line names the
outpost for a miner.

### Refit and re-station (`pioneer_refit.py`)

- `refit(role, spec=None, base=None)`: the non-hauler branch (:203-204) becomes
  `host.set_base(base if base is not None else host.home_base)`. `_rename_for()` already names by
  `base_id` (`O3_miner_14`).
- Re-station shortcut: compute `keep, sell, modules = plan_refit(self._mounted(), spec["modules"])` before
  `_park_for_service()` (mounted slots don't change by driving). When `sell` is empty and `modules` buys
  nothing (miner → miner at another outpost), skip parking, charging and selling: set the base, rename,
  `publish_telemetry("REFIT", target_desc=f"{role} at {base}")`, return True. `OutpostStockpile.transfer()`
  then drives it to the new base slot before mining.
- A failed refit restores `old_base` (already done at :181/:186/:197).

### Job and reload (`pioneer.py`, `job_mine.py`)

- `job_for_role("miner")` → `MineJob(self, OutpostStockpile(self.base_id))`.
- Reload: `base_id` is not persisted. In `run()`, before `job_for_role`, a miner restores its base from its own
  last `fleet.status` entry (`fleet_status.get(self.name)`, key `base`, `fleet_status.py:162`) when that outpost
  still exists (`set_base()` returns False otherwise and logs). Haulers keep their own reload path
  (`job_pull.py:89-93`); builders and scouts work for `HOME_BASE`.
- `job_mine.py:240` (`host.home_ore_demand()` in the idle diagnostics) stays: it serves the Rover path. If it
  runs for a Pioneer too, switch that line to `host.stockpile_need(job.targets.outpost_id)` when the targets
  are an `OutpostStockpile`; Opus checks which class owns :240.

### Autoplay

- `build_providers.py:493-498`: drop the idle retire loop with `MINER_IDLE_TICKS` and `MIN_MINERS_PER_OUTPOST`;
  keep `idle_since` (the backlog rule needs "none idle"). Header comment :50-52 and the `miner_wants` docstring
  follow. The drills rule (:402-405, "Pioneer miners are free") stays: it's obsolescence, not idleness.
- `building_plan.py:549` `miner_homes` and `:453` `idle_unit`: key by `entry.get("base") or entry.get("home")
  or HOME_OUTPOST_ID`; the docstrings say "by base (HOME_BASE until a refit moves it)". Commission jobs keep
  `job_home_base`.
- `pioneer_surplus_wants()` (:440): add `"miner"` to the drones-haul loop, `keep = max(keep, wanted)` of the
  miner entry (fleet totals). Before drones haul, a surplus miner falls back to hauler and the hauler sell
  rule takes it, as for the other roles.

### FLEET card Roles tab (`roles_card.py:80-88`)

For an entry with `slots`, the per-outpost line appends `held / wanted keep k` from `slots[oid]` and
`claimed_outposts()`. Other roles unchanged.

## Tuning

Risk from the plan: every miner leaves as a hauler and ore STOCK is never reached. With this design a miner
only leaves while idle, and `OutpostStockpile` idles only when stock is at target and no need is open. So the
floor miner (`KEEP_MINERS` 1 per smelting outpost) refills buffers alone; a second miner returns only on a NEED
ore. Knobs, in order: (1) `KEEP_MINERS` 2; (2) count STOCK-band ore toward `wanted` (`wanted_oid = max(len(need_ores), 1)`
while any raw-ore deficit); (3) a higher ore NEED level ([§2a-p](../../cheatsheet/fabricator_demand.md)).
Measure before turning any.

## Verification

Unit tests (`tests/test_role_demand.py`, extend): `miner_demand` with NEED ore in reach (wanted 1 per ore, cap
4), reach unknown (cap 1), STOCK only (wanted 0, keep 1 at a smelting outpost, 0 elsewhere); `claimed_outposts`;
`switch_candidates` miner floor per outpost, re-station candidate, miner without a slot entry leaves;
`miner_target` order; `claim_slot(outpost=)` keeps own slot only at the same outpost. `pioneer_refit` tests:
`refit(base=)` sets the base, the re-station shortcut sells nothing and doesn't park.

Headless A/B as Stage 2 ([ab_results.md](../../headless/ab_results.md) "Stage 2": save `mvdnuhjh_rbjww6`,
real scripts, `--include-autoplay --auto-approve 3000`, 2 h, vs `main`). Measure: raw-ore stock per smelting
outpost against `ore_stock_target()` at the end (STOCK reached or not), ticks a NEED ore stayed open, miner
refits and re-stations (`REFIT` telemetry, `fleet.role_claims` `miner:*` keys), errors, TP, credits. Stage 2
saw no idle Pioneer in 2 h; if the miners stay busy again, run a second scenario from the end save with ore
stocks raised to target (harness `stacks.mjs`, [standins.md](../../headless/standins.md) "Stores and flows")
so a miner idles and the floor rule is exercised.

## Docs to update with the edits

`fleet_lifecycle.md` §2f-1 (miner entry, `slots`, `KEEP_MINERS`, `MINER_SLOTS_PER_OUTPOST`, re-station),
`archive_ipc.md` (`fleet.role_claims` key `miner:<outpost>:<i>`, record `outpost`; `fleet.role_demand`
`slots`), `autoplay.md` §11l (miner rules), `lib_map` if `ore_bands` moves, `DESIGN_HISTORY.md` §2f-1 (probe
cap, no drill filter, keep floor per smelting outpost, STOCK gives wanted 0), `TODO.md` item B (:34 "idle
miners above 2 retire" is gone) and the Stage 3 row, this README's handoff.
