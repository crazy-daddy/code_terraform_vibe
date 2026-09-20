# Corrupted Archive Contract Solver
c = self.contract
arch = c.archive

# Map word -> list of (row, col) coordinates
word_positions = {}

for r in range(arch.rows):
    for col in range(arch.cols):
        word = arch.flip(r, col)
        if word not in word_positions:
            word_positions[word] = []
        word_positions[word].append((r, col))

# Form pairs: [row1, col1, row2, col2] for each of the 50 matching pairs
pairs = []
for word, coords in word_positions.items():
    if len(coords) == 2:
        (r1, c1), (r2, c2) = coords
        pairs.append([r1, c1, r2, c2])
    else:
        print(f"Warning: word '{word}' has {len(coords)} occurrences instead of 2!")

print(f"Collected {len(pairs)} matching pairs.")

# Transmit pairs to Earth
transmitter = get_component("transmitter")
if not transmitter:
    print("[CORRUPTED_ARCHIVE] No Transmitter found!")
else:
    transmitter.connect("earth")
    res = transmitter.transmit(c.id, pairs)
    print("Transmit result:", res.status, "-", res.message)
