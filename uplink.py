transmitter = get_component("transmitter")
temp = get_component("thermometer").get_value()

transmitter.connect("earth")
transmitter.transmit("current_temperature", temp)