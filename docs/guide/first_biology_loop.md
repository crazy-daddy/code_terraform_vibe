# Guide: first_biology_loop

## First Biology Loop

Manual Biology is the gentlest first credit path because the workbench guides each narrow machine step. Automating the same pipeline is an advanced early project because its separate machine scripts must coordinate persistent state.

### Manual and automated logistics

The manual Biology workbench has exactly **one stockroom per outpost**. At Nocturna Base that stockroom is Base Inventory. At every other outpost, choose one deployed local Warehouse in the Manual Stockroom bar; all manual Biology cards there draw from and return to that Warehouse. The selection does not move existing items. Shop purchases still arrive in Base Inventory, so carry supplies to remote Warehouses with vehicles or drones.

Manual buttons do not create hidden I/O connections or move items through a machine's `self.input` and `self.output` buffers. They load supplies directly from the manual stockroom into the workbench and return finished or recovered items directly to that stockroom. A full machine input or output buffer therefore does not block the matching manual action.

### What changes when you start scripting

Scripts do not use the manual stockroom selector. After **Auto Feeders** research, your code must manage each machine's scripted logistics explicitly: connect item ports where present, move supplies into `self.input`, load them into the machine when required, and drain completed items from `self.output`. Every stationary transfer remains local to that outpost.

The Bio Collector, Bio Lab, and Bio Exchange each own their hardware actions. Stopping or restarting a script does not empty a specimen chamber, unload reagents, drain an output, or reset Bio Order progress. Reliable code must inspect that partial state before deciding what to do next.

```
input_link = self.input.connect("Reagent Warehouse")
output_link = self.output.connect("Sample Warehouse")
if input_link.status != "ok":
  print(input_link.message)
```

### The pipeline

- The Bio Collector retrieves a specimen.
- The Bio Lab analyzes it, stages reagents, and extracts a sample.
- Biome machines transform the sample.
- The Bio Exchange delivers it toward an active Bio Order.

Every gameplay command returns a result object. Branch on `.status`, use `.message` for the exact reason, and read any method-specific payload. For example, `analyze()` returns `AnalyzeResult.info`, while item transfers return `TransferResult.moved`. Statuses such as `"busy"`, `"no_input"`, and `"output_full"` are never bare strings.

Properties belong to each item stack and survive supported transfers. Bio Orders come from a Bio Exchange, not the Earth Supply Dock orders component. Subtract both `.delivered` and `.in_transit` when planning production. See **Long-Running Scripts** for the restart-safe loop pattern used by unattended automation.

*Guide / Tutorials*

---
