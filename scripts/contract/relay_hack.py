# Relay Hack Contract Solver
c = self.contract
print(f"Contract: {c.name} ({c.id}), Reward: {c.reward}")

lock = c.lock
print(f"Tumblers: {lock.tumblers}, Range: {lock.range}")

# 6 tumblers, each in 0-99.
# lock.intercept(code) tests candidate list of 6 numbers and returns list[bool]
code = [0] * lock.tumblers

for t in range(lock.tumblers):
    for val in range(lock.range):
        candidate = list(code)
        candidate[t] = val
        res = lock.intercept(candidate)
        if res[t]:
            code[t] = val
            print(f"Tumbler {t} unlocked: {val}")
            break

print(f"Cracked code: {code}")

transmitter = get_component("transmitter")
if not transmitter:
    print("[RELAY_HACK] No Transmitter found!")
else:
    transmitter.connect("earth")
    tx_res = transmitter.transmit(c.id, code)
    print("Transmit result:", tx_res.status, "-", tx_res.message)

