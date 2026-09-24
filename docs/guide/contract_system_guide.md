# Guide: contract_system_guide

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
