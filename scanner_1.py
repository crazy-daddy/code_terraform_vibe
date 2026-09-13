# Scanner 1 Grid Survey Automation Script
# Maps all sectors of the Harvester grid (A1..H24) around base to locate loose items and resources.

ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"]
COLS = range(1, 25)

print("[Scanner] Scanner 1 online. Initializing grid survey across 192 sectors...")

while True:
    scanned = {}
    try:
        scanned = self.get_scanned() or {}
    except Exception:
        scanned = {}

    unscanned = []
    for r in ROWS:
        for c in COLS:
            sec = f"{r}{c}"
            if sec not in scanned:
                unscanned.append(sec)

    if unscanned:
        print(f"[Scanner] Found {len(unscanned)} unscanned sectors. Beginning mapping sweep...")
        for sec in unscanned:
            try:
                res = self.scan(sec)
                if getattr(res, "status", "") == "ok":
                    item_id = getattr(res, "id", "item")
                    item_name = getattr(res, "name", item_id)
                    val = getattr(res, "value", 0)
                    print(f"[Scanner] Surface discovery at {sec}: '{item_name}' (ID: {item_id}, Value: {val})")
            except Exception as e:
                # Catch invalid coordinates or transient pauses
                pass
            sleep(0.05)
        print("[Scanner] Grid survey sweep complete. All sectors mapped.")

    # Periodic idle sleep before verifying grid status
    sleep(15.0)

