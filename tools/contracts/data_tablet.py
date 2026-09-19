# Underground Data Tablet Contract Solver
c = self.contract
tablet = c.tablet
rows = tablet.rows
cols = tablet.cols

message_cells = []
for r in range(rows):
    for col in range(cols):
        res = tablet.probe(r, col)
        if res.distance == 0:
            message_cells.append((r, col, res.char))

message_cells.sort(key=lambda item: (item[0], item[1]))
message = "".join(item[2] for item in message_cells)
print(f"Decoded message ({len(message)} chars): '{message}'")

transmitter = get_component("transmitter")
transmitter.connect("earth")
t_res = transmitter.transmit(c.id, message)
print(f"Data Tablet result: {t_res.status} - {t_res.message}")

