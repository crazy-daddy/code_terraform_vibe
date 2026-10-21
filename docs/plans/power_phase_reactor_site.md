# Power phase and reactor site (rough plan)

Status: rough plan, 2026-10-21. Not started. One code session per step group (A, B, C), each with a handoff.

Two problems share the same code (`autoplay_roles` catalog, `outpost_needs.host_check()`, `build_providers.kit_wants()`):

1. The planner has no notion of which power source is current, so it can't retire steam or move a reactor onto the old steam outpost.
2. The reactor role models only the Reactor. The Lead Casks and the Fuel Assembler deploy at home, so uranium and fuel rods have to be hauled, which would need a dedicated nuclear hauler.

Related: [atomic_rush.md](atomic_rush.md) (why nuclear, oil before the gate). That plan says to keep parked turbines as reactor backup; this plan replaces that with **oil** as the fallback and retires steam entirely (operator, 2026-10-21).

## Power phases

`game_phase.power_phase(snap)`, a pure function over the phase snapshot like the other predicates. Inputs are research and the generators that stand.

| Phase | Sources | Rule |
| ---: | :--- | :--- |
| 1 | solar | only source; no outpost role |
| 2 | steam (+ solar) | solar still allowed, fading out (no new trackers, old ones not replaced) |
| 3 | steam + oil | both coexist, both sized to the fluid overflow |
| 4 | nuclear (+ oil) | oil stays as a slight fallback; steam retired |

Open: the exact triggers. Candidates: phase 2 = Thermal Cap researched and a turbine stands; 3 = first Oil Generator; 4 = a Reactor runs with fuel rods in stock (not just researched or deployed). Phase 4 must not start before the reactor actually delivers, or steam goes away with no replacement.

## Steps

### A. Split the power role

- `power` covers both turbines and oil generators (preset: steam and oil in), so "drop steam, keep oil" can't be expressed. Split it into `power_steam` (`steam_turbine`, in: steam) and `power_oil` (`oil_generator`, in: oil).
- Migrate existing `autoplay.outpost_roles` entries: `power` becomes whichever of the two the outpost's buildings make up (both if both stand). Readers to update: `power_plan`, `extractor_plan`, `fluid_plan`, the `power` `site_fluid` need in `outpost_needs.lookahead()`, the Steam Condenser host pick in `kit_wants()` (`"power" in role_list(...)`), `DEFAULT_ROLE_PRESETS`, cheatsheet §11f.
- `condenser` (Steam Condenser) goes with `power_steam`.

### B. Reactor site as one role

Current: `ROLE_CATALOG["reactor"] = {"buildings": ["reactor"], "exclusive": True}`; Lead Casks (`LEAD_CASKS`) and the Fuel Assembler deploy at home (`build_providers.kit_wants()`, `outpost=base["id"]`).

Site needs (operator):

| Building | Count | Strictly needed |
| :--- | ---: | :--- |
| Reactor | ≥ 1 | yes |
| Lead Cask | ≥ 2 (uranium, fuel rods) | ≥ 1 (fuel rods) |
| Fuel Assembler | ≥ 1 | no, but it removes the uranium/fuel rod hauling |
| Warehouse | ≥ 1 (lead plates) | no |
| Liquid Tank (water) | ≥ 1 | no |
| Mk IV terraform generators | any | no (`terraform`, already in `EXCLUSIVE_SHARE_ROLES`) |

- `reactor` role: buildings `reactor`, `lead_cask`, `fuel_assembler`; `items: True` (Warehouse and Drone Depot through the normal stock path; `lead_plate` on its stock list). Catalog groups are all-or-nothing, so the building planner builds the Fuel Assembler there. Water tank via `storage_water` when wanted.
- The role's own machines never trip the exclusive check: `host_check()` looks only at the host's *other* roles.
- `kit_wants()`: casks and Fuel Assembler at the reactor host once one is designated, else home (as now).
- Moving an existing home Fuel Assembler and casks to the reactor site: undeploy and redeploy, or leave them at home. Decide in the session; the casks hold uranium, so drain first.

### C. Phase transitions in the outpost planner

- **Exclusive rule.** `host_check()` uses `_penalized_role()` (`storage.PENALIZED_TYPES`, the overcrowding list) as a stand-in for "production role". The real reason for `exclusive` is the slot budget (run 2: "too few slots", [planner_rev2_results.md](planner_rev2_results.md)). Replace the proxy with an explicit rule: an exclusive host takes `EXCLUSIVE_SHARE_ROLES`, non-penalized roles, and, during the 3→4 transition, roles that retire in phase 4 (`power_steam`, `condenser`).
- **Water site.** `reactor` is a `site_fluid` water need (`NEAR_TILES`). In phase 3+ with a water network built, accept piped water: the steam outpost is geothermal and has no water wells. Pipes are cheap by then (operator).
- **Retire steam.** Phase 4 adds `power_steam` and `condenser` to `autoplay_roles.retired()` (same path as the bio, biomass, plants and wildlife roles: dropped from the designation, never re-proposed). The turbines and condensers still need an undeploy-and-sell step: a `retire_wants()` entry in `build_providers` or the power planner's steam leg. Thermal Caps on the vents go too unless a condenser elsewhere still wants steam.
- **Repurpose.** With steam retired, the geothermal power outpost is the natural reactor host (outpost costs scale, so no new outpost). Its `liquifier_geothermal` must not block: biomass is usually complete before nuclear, so `retired()` has dropped it already. Check that order holds; if not, let `liquifier_*` share with the reactor.
- **Solar fade (phase 2+).** No new trackers; selling old ones is the open TODO "retire solar trackers early" in Phase 10.

## Open questions

- Phase triggers (above), and whether `power_phase` belongs in `game_phase` or the power planner.
- Oil fallback size in phase 4: a fixed count of Oil Generators, or sized to the oil surplus as in atomic_rush.md.
- Does the reactor host keep `terraform` Mk IV generators only, or also other non-penalized roles (storage)?
- The TODO line "let turbine commitment park the turbines (keep them as backup, don't sell)" conflicts with retiring steam: update it when step C lands.
