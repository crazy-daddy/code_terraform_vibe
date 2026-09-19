raw_val = self.get_value()
print(f"Raw pressure: {raw_val}")
corrected = raw_val + 1 if int(raw_val) % 2 != 0 else raw_val
print(f"Stabilizing with corrected value: {corrected}")
res = self.stabilize(corrected)
print("Pressure sensor stabilize result:", res.status, res.message)

