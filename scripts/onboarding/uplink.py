transmitter = get_component("transmitter")
thermometer = get_component("thermometer")
if not transmitter or not thermometer:
    print("[UPLINK] Missing Transmitter or Thermometer component.")
else:
    temp = thermometer.get_value()
    transmitter.connect("earth")
    transmitter.transmit("current_temperature", temp)