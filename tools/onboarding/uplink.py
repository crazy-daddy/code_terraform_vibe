transmitter = get_component("transmitter")
temp = get_component("thermometer").get_value()
transmitter.connect("earth")
res = transmitter.transmit("current_temperature", temp)
print("Uplink result:", res.status, res.message)

