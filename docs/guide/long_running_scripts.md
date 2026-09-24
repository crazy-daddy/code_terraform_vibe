# Guide: long_running_scripts

## Long-Running Scripts

### What happens when a game loads

A script that was running begins again from its first line when the game loads. The game saves the script's source and running status, but it does not restore the current line, local variables, call stack, or pending return value. If a script was paused when saved, it loads paused, but only the paused status is preserved. Its execution position is reset. Pressing Resume begins a new run from the start of the source; it does not continue from the previous line.

Saved world state can outlive one script run. A machine may still contain cargo, a specimen, staged materials, queued jobs, completed output, or timed work when the restarted script reaches it. That state is not an error. It is the starting point for the next decision.

### Make the machine the source of truth

Build a long-running script as a reconciliation loop. Each pass should:

1. Read the machine's current state.
2. Decide which step is still missing.
3. Attempt that step once.
4. Check the returned `.status`.
5. Let game time pass before retrying a transient blocker.

Do not depend on a local variable from an earlier pass to remember what the machine contains. Read the chamber, cargo, ports, queue, or current job again.

### Bio Lab example

This loop can begin with an empty Lab, a collected specimen, an analysis already underway, or an analyzed specimen. It always re-reads the chamber before deciding what to do:

```
collector = get_component("bio_collector_1")

while True:
  specimen = self.specimen

  if specimen is None:
    transfer = self.take_from(collector)
    if transfer.status == "busy":
      sleep(0.2)
      continue
    if transfer.status != "ok":
      print(transfer.message)
      sleep(0.2)
      continue
    continue

  if specimen.stage == "collected":
    analysis = self.analyze()
    if analysis.status == "busy":
      sleep(0.2)
      continue
    if analysis.status != "ok":
      print(analysis.message)
      sleep(0.2)
      continue
    print(analysis.info.required_recipe)
    continue

  print(specimen.recipe)
  break
```

The payload rule matters here: `analysis.info` is available after `analysis.status == "ok"`. A `"busy"` result has no analysis payload, so the script waits and starts another pass instead of reading `.info`.

### Make writes safe to repeat

Before transferring, buying, loading, or queuing something, inspect what is already present. Calculate the missing amount instead of submitting the full planned amount again. Drain completed output before starting more work, and distinguish a transient `"busy"` from blockers such as `"output_full"`, `"insufficient_input"`, or an invalid argument. The command's DOCS entry lists which outcomes can change when the world changes.

### Persist knowledge deliberately

Machine contents are world state, but ordinary script variables belong to one run. Use the **Data Archive** when automation must remember learned data, checkpoints, or decisions across script stops and game loads. Use **Command Results** for the general result contract and **Loops & Scripts** for loop and pacing basics.

*Guide / Start Here*
