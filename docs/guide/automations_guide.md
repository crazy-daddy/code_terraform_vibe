# Guide: automations_guide

## Automations

### Overview

An automation is a script that belongs to no machine. Use it for work that spans the whole base: managing power, buying from the shop, deploying equipment, planning construction.

Automations unlock with **Automations** research. Open **Ship Computer > Automations** and click **+ New Automation**.

### How it runs

An automation runs whichever page is open. It has no power supply of its own, so a brownout never pauses it, and it restarts with the game like any other running script. Start, stop and edit it from the Automations tab, the Scripts tab, or its editor window.

### What it can do

It reads every component through `get_component()`. It can give orders to the shared systems that accept them from any script: `power_control`, `run_control`, `shop`, `inventory`, `computer`, `construction_blueprint`, `comms`, and the other components whose DOCS entries say so.

```
power = get_component("power_control")

while True:
    total = power.total()
    if total.capacity > 0 and total.stored < total.capacity * 0.2:
        print("Battery low:", total.stored, "of", total.capacity, "Wh")
    sleep(60)
```

### What it cannot do

There is no `self`. A machine's own actions, such as moving a vehicle, mining, or setting a recipe, work only from that machine's script. To have a machine act, send it a message on the Signal Bus and let its script read it.

### Limits

- **50 automations per save.** Past that, **+ New Automation** is grayed out.
- **One script per automation.** Want separate jobs? Make separate automations.
- Deleting an automation keeps the code you wrote in **Computer > Scripts > Unassigned**.

*Guide / Automation Systems*
