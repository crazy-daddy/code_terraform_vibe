# Guide: plant_terraformer_guide

## Plant Terraformer

The **Plant Terraformer** is the only machine that raises permanent Plants km². Deploy as many as you can feed across operational outposts. Every supplied machine adds its tier rate multiplied by that outpost's live efficiency.

### Input and cycles

After Auto Feeders research, connect `self.input` to home Inventory, a local Storage Bin or Warehouse, or a local machine output such as a Crop Automator. Use `self.input.take(item_id, count)`, or send from the source's output. This is the same timed item-transfer model used by other machines: both endpoints stay occupied for the transfer duration. The input has one source connection at a time, so scripts may reconnect it when changing sources.

The Terraformer's destination feeder handles **16 items per handling step** at Mk I and **80** at Mk II, regardless of whether the source pushes or the Terraformer pulls. **Fast Feeders** unlocks at **400,000 Terraform Points** and halves the duration of all newly started timed item transfers. A full Forage load therefore takes about **18.8 seconds** at Mk I and **20.6 seconds** at Mk II before that research, or **9.4** and **10.3 seconds** afterward, when the source is free. Direct Crop Automator to Terraformer transport avoids the extra Warehouse leg; Warehouses remain useful player-controlled staging.

The existing holders fit one full Forage batch, the Salt that batch needs, and up to **10 each** of Fertilizer Mk I, Mk II, Mk III, and Growth Accelerant. There is no separate intake buffer. When a cycle can start, the machine commits the largest whole Forage batch supported by every loaded material. For example, 10 Forage with Water for 8 loads a batch of 8. If any required material cannot support one Forage, the machine waits.

All selected items and matching Water are consumed exactly once when the cycle starts. The batch then performs **3 hours** of work at 100% outpost efficiency and delivers its km² in one step. Power loss or `set_enabled(False)` pauses the batch in place. When a cycle finishes, the next affordable loaded batch starts immediately.

### Tiers and fleet cost

At 100% outpost efficiency, Mk I loads up to **1,200 Forage**, averages **400 Forage/h**, and draws **180 W** while enabled. It handles the first three conversions, then reports `"needs_mk2"` at **2,250,000 km²**. Mk II loads up to **6,600 Forage**, averages **2,200 Forage/h**, draws **900 W**, and adds the Fertilizer and Growth Accelerant injectors. Each machine needs its own fabricated Mk II pack.

### Cumulative material ladder

| Progress | km² per Forage | Band Forage | Added support |
| --- | ---: | ---: | --- |
| 0 to 500,000 km² | 20 | 25,000 | none |
| 500,000 to 1,250,000 km² | 5 | 150,000 | 0.05 t Water |
| 1,250,000 to 2,250,000 km² | 5 / 3 | 600,000 | 0.002 Salt |
| 2,250,000 to 3,500,000 km² | 1 | 1,250,000 | 0.004 Fertilizer potency, Mk II |
| 3,500,000 to 5,000,000 km² | 1 / 3 | 4,500,000 | 0.0001 Growth Accelerant, Mk II |

Fertilizer Mk I supplies **10 potency**, Mk II supplies **30**, and Mk III supplies **50**. Each cycle spends stored potency first. To cover a shortfall, the machine consumes a whole-item combination with the least excess potency, then the fewest items. Unused potency stays in the machine for later batches and survives save/load. One Mk III item leaves **23 potency** after a **27-potency** batch. The card includes stored potency in its total; item counts show only unopened items. A full Mk II batch asks for **27 potency**. Growth Accelerant is counted and consumed as whole items; a full Mk II batch asks for **1**.

### Script control

```
self.input.connect("crop_automator_1")
self.water_in.connect("Water Reservoir")
self.set_enabled(True)

while True:
  result = self.input.take("forage", self.batch_requirements()["forage"])
  print(result.status, self.status(), self.batch_size())
  sleep(1)
```

Salt is consumed as whole items, **1 per 500 Forage rounded up per batch**. A full Mk I cycle consumes **3 Salt**; a full Mk II cycle consumes **14 Salt**. Unused treatment value does not carry over.

`batch_requirements()` reports Fertilizer as `fertilizer_potency` and Growth Accelerant as an item count. Use `fertilizer_potency(item_id)` to inspect a Fertilizer tier. Item transfers are local to the Terraformer's outpost. Water uses the dedicated `water_in` relationship and, for remote sources, a compatible completed Liquid Pipe route.

*Guide / World & Infrastructure*
