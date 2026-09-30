# Component: commander

> **Category:** Core Systems | **Component Name:** Commander

Read the player's name and current credits with `get_component("me")` or `get_component("commander")`. Scripts cannot change either value.

**Access via:** `get_component("commander")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

### Methods

##### `.get_name() → str`

Your commander name as a string. Set during initial character creation (or default). Use for personalized dashboard messages.

- **Returns** `str`

##### `.get_credits() → int`

Current credit balance. Changes when `shop.buy()` / `shop.sell()` run, Bio Exchanges pay out, contract transmissions succeed, and Orders complete. Use as a gate before expensive `shop.buy()` calls.

- **Returns** `int`

*Components / Core Systems*
