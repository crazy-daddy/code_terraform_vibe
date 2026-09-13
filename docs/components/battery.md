# Component: battery

> **Category:** Power | **Component Name:** Battery

**Returned by:** self.battery (vehicles)

### Related object types

- `Holder`
- `PortableBattery`

### Methods

##### `.level()`

Charge level as a fraction, **0-1**.

- **Returns** `number`

##### `.wh()`

Current charge in Wh (across all batteries).

- **Returns** `number`

##### `.capacity()`

Maximum capacity in Wh.

- **Returns** `number`

##### `.holders()`

List of every Battery Holder currently mounted on the vehicle. Empty for the Rover (sealed battery).

- **Returns** `list<Holder>`

*Types / Storage & Inventory*
