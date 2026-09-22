# Sealed Vault Contract Solver
# Explores the maze grid from (0, 0) to (size - 1, size - 1) via DFS.

c = self.contract
vault = c.vault
size = vault.size

print(f"Contract: {c.name} ({c.id}), Vault size: {size}x{size}")

opposites = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
}

moves = [
    ("south", 1, 0),
    ("east", 0, 1),
    ("north", -1, 0),
]

visited = set()

def dfs():
    curr_pos = vault.position
    r, col = curr_pos.row, curr_pos.col
    visited.add((r, col))

    if r == size - 1 and col == size - 1:
        return True

    for direction, dr, dc in moves:
        nr, nc = r + dr, col + dc
        if 0 <= nr < size and 0 <= nc < size and (nr, nc) not in visited:
            res = vault.move(direction)
            if res.status in ["path", "exit"]:
                if dfs():
                    return True
                # Backtrack to (r, col)
                vault.move(opposites[direction])

    return False

start_pos = vault.position
print(f"Starting at ({start_pos.row}, {start_pos.col})")
found = dfs()

curr = vault.position
print(f"Search finished. Found: {found}, Final position: ({curr.row}, {curr.col})")

if curr.row == size - 1 and curr.col == size - 1 or found:
    print("At exit cell! Attempting escape...")
    esc_res = vault.escape()
    if esc_res.status == "ok":
        key = esc_res.key
        print("Vault opened successfully! Extracted key:", key)
        transmitter = get_component("transmitter")
        if not transmitter:
            print("[SEALED_VAULT] No Transmitter found!")
        else:
            transmitter.connect("earth")
            t_res = transmitter.transmit(c.id, key)
            print("Transmission status:", t_res.status, "-", t_res.message)
    else:
        print("Escape error:", esc_res.status, "-", esc_res.message)
else:
    print(f"Failed to find path to exit. Visited {len(visited)} cells.")