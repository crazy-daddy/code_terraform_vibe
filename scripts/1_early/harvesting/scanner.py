# Self-contained early Scanner controller (no lib/ imports)
# Scans outward from base center (D12/E12) so Harvester can start immediately

ROWS = "ABCDEFGH"
COLS = 24
CENTER_R = 3.5
CENTER_C = 11.5

known = self.get_scanned()
scanned = 0
items_found = 0

# Sort all sectors by distance from base center
all_sectors = []
for r_idx, row in enumerate(ROWS):
    for c_idx in range(COLS):
        sec = f"{row}{c_idx + 1}"
        dist_sq = (r_idx - CENTER_R)**2 + (c_idx - CENTER_C)**2
        all_sectors.append((dist_sq, sec))

all_sectors.sort(key=lambda item: item[0])

for _, sector in all_sectors:
    if sector not in known:
        res = self.scan(sector)
        scanned += 1
        if res.status == "ok":
            items_found += 1
            print(f"[scanner] Sector {sector}: {res.name} (value: {res.value})")

print(f"[scanner] Grid sweep complete: {scanned} newly scanned, {items_found} items found.")
