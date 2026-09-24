# Guide: power_and_terraforming

## Power & Terraforming Machines

Terraforming machines are the core engines of the base. Heat Generators, Oxygen Generators, and Pressure Generators turn power into planetary progress.

### Power comes first

A machine that has no power cannot help the planet. Early solar power changes with day and night, so a base that works at noon may stall after sunset. Batteries smooth that gap by storing daytime surplus for nighttime use.

A reliable early setup is: add a generator, add a battery, run one terraforming machine, then expand power before adding too many more consumers.

### Terraforming starts with three tracks

Temperature, oxygen, and pressure are the first three tracks, each with their own machines and upgrades. They all matter. You can focus one track for a while, but the planet only becomes livable when all three keep advancing. Later progress opens more terraforming tracks; for now, make these first systems dependable.

The first machines are slow. Add power, add machines, then expand to more outposts and higher tiers to raise the pace.

### Oxygen runs on CO2, the carbon cycle

Oxygen Generators convert atmospheric CO2 into oxygen, one-for-one. The planet starts with a large CO2 reserve, and that reserve is enough for a long time, but large-scale oxygen production outpaces it. CO2 is returned to the atmosphere by burning oil (Oil Generator), incinerating items (Waste Processor), and, at real scale, by wildlife: established colonies exhale CO2. A small volcanic trickle keeps CO2 from ever bottoming out completely, so a starved oxygen fleet always recovers. Watch `atmosphere.get_co2()` and remember the efficiency sweet spot moves with it.

### Scripts should react

Good machine scripts read state before acting. A generator can react to sun angle. A battery or power monitor can warn when storage is low. A terraforming machine can throttle down when power is tight and resume when the base recovers.

If generators stop at night or terraforming machines pause from low power, that is usually not a bug. Power production, storage, and consumption have to fit together.

*Guide / Tutorials*
