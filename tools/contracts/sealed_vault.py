# Sealed Vault Contract Solver (DFS maze exploration)
c = self.contract
vault = c.vault
size = vault.size

opposites = {"north": "south", "south": "north", "east": "west", "west": "east"}
moves = [("south", 1, 0), ("east", 0, 1), ("north", -1, 0), ("west", 0, -1)]
visited = set()

def dfs():
    curr = vault.position
    r, col = curr.row, curr.col
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
                vault.move(opposites[direction])
    return False

dfs()
curr = vault.position
if curr.row == size - 1 and curr.col == size - 1:
    esc = vault.escape()
    if esc.status == "ok":
        transmitter = get_component("transmitter")
        transmitter.connect("earth")
        t_res = transmitter.transmit(c.id, esc.key)
        print(f"Sealed Vault result: {t_res.status} - {t_res.message}")
    else:
        print(f"Sealed Vault escape error: {esc.status} - {esc.message}")
else:
    print(f"Sealed Vault: Could not reach exit ({curr.row}, {curr.col})")

