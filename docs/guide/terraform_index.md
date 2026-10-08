# Guide: terraform_index

## Terraform Index and planetary completion

The Terraform Index is your overall progress toward a livable planet. It has a fixed goal of **1,000,000 Terraform Points (TP)**. Those points come from six pillars, so steady progress eventually means looking beyond the first machines you built.

### The six pillars

| Group | Pillars | Maximum share of the Index |
|---|---|---|
| Atmosphere | Temperature, oxygen and pressure | 700,000 TP together |
| Biosphere | Biomass, plants and wildlife | 100,000 TP each |

The three atmospheric pillars are available first. **Biosphere** research opens at **210,000 TP**, making the other three pillars visible. Their production systems open along the later research path. Unlocking Biosphere does not change the million-point goal or take away points you already earned.

Each pillar advances through named phases. You earn progress between phase boundaries as well as when crossing them. The meters use different units and different phase thresholds, so one extra unit of heat, oxygen or biomass does not mean one TP. Compare progress and the next milestone rather than adding raw readings yourself.

### A finished pillar cannot replace another one

Each pillar's Index contribution stops growing when it reaches its final target. Extra output in that pillar cannot make up for unfinished plants or wildlife. Even a completely finished atmosphere contributes at most **700,000 TP**.

If the Index slows while one set of machines is still producing, check whether their pillar is already complete. Put the next expansion into an unfinished pillar or its supply chain. Do not shut down a useful supply blindly: some machines also support other systems, such as the atmospheric carbon cycle.

### Use research to choose the next project

Research unlocks automatically when its own requirement is reached. Some entries follow the combined Terraform Index; others follow temperature, oxygen, pressure or a Biosphere pillar. Read the requirement on the research card. More pressure will not satisfy a target that asks for plants.

Oxygen- and pressure-based research also need their matching sensors repaired and online. If an expected unlock is missing, check the sensor as well as the production reading.

**Research and recipe rewards are separate.** An unlock can open a machine, a shop item or a particular recipe. Earth Orders supply other recipes and blueprints. If you own a machine but cannot select the recipe you want, check its recipe list and the order rewards instead of simply producing more TP. See `orders_guide` for that progression.

### Check what is actually holding you back

Start with an unfinished pillar, then follow its inputs. Is its machinery powered? Does it have the required material or fluid? Is an output full? Does it need an upgrade for the current stage? Expanding a stopped machine's fleet usually repeats the same shortage.

Scripts can read current pillar snapshots:

```
terraforming = get_component("terraforming")
print(terraforming.total_tp(), terraforming.index_progress())
for pillar in terraforming.pillars():
  print(pillar.id, pillar.progress, pillar.complete)
```

The pillar list contains the currently unlocked pillars. Each also exposes `.value`, `.target` and `.next_target` for planning. Query again when you need fresh readings.

For the first atmospheric setup, see `power_and_terraforming_machines`. The later production paths are in `biosphere_tier`, `plants_overview` and `wildlife_overview`. All these guides are available before the corresponding equipment unlocks, so you can plan ahead.

*Guide / Tutorials*
