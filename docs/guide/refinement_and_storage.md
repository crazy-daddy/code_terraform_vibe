# Guide: refinement_and_storage

## Refinement & Storage

Once you're mining, the refinement pipeline turns raw ore into stock and stages it for crafting.

### Setting up a pipeline

`"inventory"` is a freight endpoint only at home; remote outposts use local storage and vehicles.

```
input_link = self.input.connect("Iron Ore Bin")
output_link = self.output.connect("Iron Ingot Bin")
recipe = self.set_recipe("smelt_iron_ingot")

if input_link.status == "ok" and output_link.status == "ok" and recipe.status == "ok":
  while True:
    ready = self.get_output_count()
    if ready > 0:
      sent = self.output.send("iron_ingot", ready)
      if sent.status not in ["ok", "partial", "no_op"]:
        print(sent.message)

    room = self.input.capacity() - self.input.count()
    if room > 0:
      taken = self.input.take("iron_ore", min(10, room))
      if taken.status not in ["ok", "partial", "no_op"]:
        print(taken.message)
```

`connect()` and recipe commands return `ActionResult`. `take()` and `send()` return `TransferResult` with `.requested` and `.moved`. Processing is asynchronous, so completed output appears later.

`self.input.flush()` returns `TransferResult`; `.moved` is the number of units permanently discarded. On processing machines it also cancels current progress. Call it intentionally.

*Guide / Production & Logistics*
