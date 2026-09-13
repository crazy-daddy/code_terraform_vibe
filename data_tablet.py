# Underground Data Tablet Contract Solver
# Scans the tablet grid (rows x cols) for hidden message cells.
# Probe returns ProbeResult(.char, .distance). Distance 0 indicates a message cell.
# Message characters are read left to right, top to bottom (row reading order).
# Assembles message string and transmits to Earth.

c = self.contract
tablet = c.tablet
rows = tablet.rows
cols = tablet.cols

print(f"Contract: {c.name} ({c.id}), Dimensions: {rows}x{cols}")

message_cells = []

# Scan the full grid
for r in range(rows):
    for col in range(cols):
        res = tablet.probe(r, col)
        if res.distance == 0:
            message_cells.append((r, col, res.char))
            print(f"Found message char '{res.char}' at ({r}, {col})")

# Sort cells in reading order: top-to-bottom, then left-to-right
message_cells.sort(key=lambda item: (item[0], item[1]))

message = "".join(item[2] for item in message_cells)
print(f"Decoded message ({len(message)} chars): '{message}'")

transmitter = get_component("transmitter")
transmitter.connect("earth")
t_res = transmitter.transmit(c.id, message)
print("Transmission status:", t_res.status, "-", t_res.message)