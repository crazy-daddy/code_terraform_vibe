# Guide: industrial_upgrades_deep_oil

## Industrial upgrades and deep oil

Research unlocks the means to expand production. Manufacture one pack for each machine you want to upgrade.

### Faster factories

Industrial Machinery Mk II unlocks at **375,000 Terraform Index**. Smelters and Fabricators upgraded to Mk II process at **2×** original speed with **1.5×** operating power. Industrial Machinery Mk III unlocks at **625,000 Terraform Index**; a Mk III machine processes at **4×** original speed with **3×** operating power. Install Mk II before Mk III. Recipes consume the same ingredients and produce the same batch quantities.

Make packs in a **Fabricator** using their named recipes. The recipe browser shows the exact ingredients, Water intake and operating power. Mk II packs use Machine Frames, Control Units and Circuit Panels or Pressure Valves. The pump pack also needs Cobalt Ingots. Mk III packs add Rare Earth Cores. Completing the corresponding Earth Orders unlocks those intermediate recipes.

Packs are manufactured goods and cannot be purchased. Apply factory packs through **Inventory -> Upgrade** or `computer.upgrade(item_id, machine)` after Ship Computer research. Check power headroom first. Upgrading preserves the machine, its recipe, connections, scripts, stored goods and batch progress. Undeploying returns the base kit and installed packs.

### Better Oil Pumps

Advanced Oil Extraction unlocks at **475,000 Terraform Index**. A Mk II Oil Pump extracts **1.5×** its well's active rate and uses **100 W** at full throttle. Dormant phases still stop production. Stockpile active-phase oil in Liquid Tanks to keep factories supplied between phases.

Fabricate an **Oil Pump Mk II Upgrade Pack**, transfer it into a **Pioneer cargo bin**, and mount a **Constructor Module**. Select **Plan Upgrade** on the pump's Extraction card, or call `construction_blueprint.plan_upgrade("oil_pump_upgrade_pack_mk2", pump)` from a script. Park the Pioneer within the pump's service area and run `self.constructor.execute(blueprint_id)`. Installation takes **0.5 h**. The pump keeps working at Mk I until completion. Paused jobs retain their paid pack and progress; resume the same blueprint. Cancelling a paid job requires a Pioneer with cargo room at the pump to reclaim the pack. Dismantling requires room for both the original pump kit and installed pack.

### Find three more reservoirs

Advanced Oil Extraction also unlocks **Seismic Sonar** in the Shop for **7,500 credits**. Mount it in a Pioneer universal slot, replacing its previous sonar. It has Deep Sonar's **280 m** range and hardness-4 mineral capability, with a **3 Wh** charge per scan or survey. Ordinary Petroleum Survey research remains necessary for oil discovery.

Look for **inert formations**, returned by sonar as `GeologicalAnomaly` sites with `site.kind() == "inert"`. Three of these formations on each map conceal additional deep oil reservoirs. Their positions stay fixed across save/load. Any sonar can classify a formation as inert, but seeing it on the map or scanning it with ordinary sonar does not reveal its deep oil potential. **Revisit inert formations even if they are already marked as surveyed.** That earlier survey does not rule out deep oil.

Mount **Seismic Sonar**, move within **280 m** of an inert formation and call `self.sonar.scan()`. The scan distinguishes **potential deep oil** (`site.seismic_status == "potential"`) from **dry** formations (`"dry"`). Call `self.sonar.survey(site)` on a potential contact to confirm the reservoir. A deep geological survey takes **0.5 h** and turns a confirmed reservoir into a rich **16 t/h** Oil Well at the same location; a Mk II pump extracts **24 t/h** while it is active. A dry survey consumes its first charge and time; revisiting a known dry formation is free. Journal queries thereafter return the confirmed contact as an Oil Well. Survey it, plan an Oil Pump and connect its output to your network.

### Script examples

Choose this recipe from a Fabricator script after Mk II research:

```
result = self.set_recipe("craft_fabricator_pack_mk2")
print(result.status, result.message)
```

Apply a fabricated factory pack from Base Inventory. Replace the example machine id with yours:

```
computer = get_component("computer")
result = computer.upgrade("fabricator_upgrade_pack_mk2", "fabricator_1")
print(result.status, result.message)
```

From a Pioneer fitted with Seismic Sonar, scan within range of inert formations, including previously surveyed ones, and survey the potential contacts:

```
sweep = self.sonar.scan()
print(sweep.status)
for site in sweep.sites:
  if site.kind() == "inert" and site.seismic_status == "potential":
    result = self.sonar.survey(site)
    print(result.status, result.message)
```

Park a Constructor-equipped Pioneer at your pump with its pack in cargo, then plan and execute its installation:

```
planner = get_component("construction_blueprint")
plan = planner.plan_upgrade("oil_pump_upgrade_pack_mk2", "oil_pump_1")
if plan.status == "ok":
  result = self.constructor.execute(plan.blueprint_ids[0])
  print(result.status, result.message)
else:
  print(plan.message)
```

An upgraded pump uses the same control script. Connect a completed liquid route to the named tank, then stop drawing power during dormancy or when the tank is nearly full:

```
tank = get_component("liquid_tank_1")
result = self.oil_out.connect("liquid_tank_1")
print(result.status, result.message)
while True:
  target = 1.0 if self.well_active() and tank.fill_pct() < 0.9 else 0.0
  result = self.set_throttle(target)
  if result.status != "ok":
    print(result.message)
  sleep(1)
```

Upgraded factories need enough ingredients, liquid flow, cargo transport and output space to sustain their faster work. Spread exploration and upgrades across the supply chain; a blocked output or empty input still stops production.

*Guide / Tutorials*
