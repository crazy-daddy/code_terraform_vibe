# Corrupted Archive Contract Solver
c = self.contract
arch = c.archive
word_positions = {}
for r in range(arch.rows):
    for col in range(arch.cols):
        word = arch.flip(r, col)
        word_positions.setdefault(word, []).append((r, col))

pairs = []
for coords in word_positions.values():
    if len(coords) == 2:
        (r1, c1), (r2, c2) = coords
        pairs.append([r1, c1, r2, c2])

transmitter = get_component("transmitter")
transmitter.connect("earth")
res = transmitter.transmit(c.id, pairs)
print(f"Corrupted Archive result: {res.status} - {res.message}")

