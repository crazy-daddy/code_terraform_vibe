def real_bits(signal, min_length):
    half = min_length // 2
    bits = []
    for i, ch in enumerate(signal):
        if ch not in "01":
            continue
        if i - half < 0 or i + half >= len(signal):
            continue
        if all(signal[i - k] == signal[i + k] for k in range(1, half + 1)):
            bits.append(int(ch))
    return bits


x_signal = self.contract.input_x
y_signal = self.contract.input_y
min_length = self.contract.min_length

xs = real_bits(x_signal, min_length)
ys = real_bits(y_signal, min_length)
print(f"[CROSSTALK] real bits x={len(xs)} y={len(ys)}")

result_bits = [(x & (1 - y)) | ((1 - x) & y) for x, y in zip(xs, ys)]

letters = []
for i in range(0, len(result_bits) - 4, 5):
    value = 0
    for b in result_bits[i:i + 5]:
        value = value * 2 + b
    if 1 <= value <= 26:
        letters.append(chr(ord("A") + value - 1))
    else:
        print(f"[CROSSTALK] group {i // 5} out of range: {value}")
message = "".join(letters)
print(f"[CROSSTALK] message: {message}")

transmitter = get_component("transmitter")
if not transmitter:
    print("[CROSSTALK] No Transmitter found!")
else:
    transmitter.connect("earth")
    transmitter.transmit(self.contract.id, message)
