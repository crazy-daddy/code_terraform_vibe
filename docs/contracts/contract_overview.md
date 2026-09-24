# Contract: contract_overview

## Contracts

Earth posts contracts, engineering tasks they need done on the planet. You write code to solve them and transmit the answer.

Each contract has:

- A briefing explaining what Earth needs
- Input data in self.contract
- A reward in credits

To complete a contract:

1. Go to the Contracts page and open one with View Contract
2. Read the briefing in the Info tab
3. Print self.contract to see available input fields
4. Transmit the answer via the transmitter:

```
c = self.contract
print(c)

transmitter = get_component("transmitter")
transmitter.connect("earth")
transmitter.transmit(c.id, answer)
```

If your answer is correct, you get paid immediately.

Commander and Shop are also accessible:

```
me = get_component("me")
print(me.get_credits())

shop = get_component("shop")
shop.sell("soil_sample")
shop.buy("solar_generator")
```

*Guide / Automation Systems*

## Contract

**Returned by:** self.contract

### Concrete subtypes

- `BeatTheSystemContract`
- `BuriedFiveContract`
- `ColdBootContract`
- `CoreSampleContract`
- `CorruptedArchiveContract`
- `CrosstalkContract`
- `DataTabletContract`
- `DriftingSignalContract`
- `LatticeContract`
- `RelayHackContract`
- `SealedVaultContract`
- `TerminalBreachContract`
- `TheLoomContract`
- `ThreeEchoesContract`
- `XenogeneticsContract`

### Properties

##### `.id: str`

Contract ID (used for transmitting answers).

- **Returns** `str`
- **Possible values** `"relay_hack"`, `"xenogenetics"`, `"corrupted_archive"`, `"sealed_vault"`, `"data_tablet"`, `"terminal_breach"`, `"drifting_signal"`, `"cold_boot"`, `"three_echoes"`, `"buried_five"`, `"the_loom"`, `"crosstalk"`, `"beat_the_system"`, `"core_sample"`, `"lattice"`

##### `.name: str`

Contract display name.

- **Returns** `str`

##### `.reward: int`

Credit reward for completing this contract.

- **Returns** `int`

##### `.status: str`

Contract status: 'available' or 'completed'.

- **Returns** `str`
- **Possible values** `"available"`, `"completed"`

*Types / Contracts*

## ContractScript

**Returned by:** self (in contract scripts)

### Properties

##### `.name: str`

Script name.

- **Returns** `str`

##### `.contract: Contract`

The contract object with ID, name, reward, and contract-specific API.

- **Returns** `Contract`

*Types / Contracts*
