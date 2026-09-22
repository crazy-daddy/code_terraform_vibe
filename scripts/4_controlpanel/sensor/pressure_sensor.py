# Pressure Sensor Stabilization Script
# Rule from docs:
# "Current unstable repair reading as an integer. If the value is odd, add 1; if it is even, use it unchanged."
# After computing corrected_value, call self.stabilize(corrected_value).

raw_val = self.get_value()
print(f"Raw pressure sensor reading: {raw_val}")

if int(raw_val) % 2 != 0:
    corrected = raw_val + 1
else:
    corrected = raw_val

print(f"Corrected value: {corrected}")
self.stabilize(corrected)