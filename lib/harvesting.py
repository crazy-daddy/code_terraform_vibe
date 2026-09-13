# Shared Library for Harvester Automation
# Handles grid mapping coordination, BFS shortest-path navigation,
# safe heat management, surface item collection, crop harvesting, and inventory offloading.

class HarvesterController:
    """
    Automated controller for the Harvester surface vehicle.
    Sweeps the local base grid (sectors A1..H24) to collect loose items and harvest mature crops.
    """
    ROWS = "ABCDEFGH"
    NUM_ROWS = 8
    NUM_COLS = 24

    # Safe heat thresholds (Max heat is 100)
    HEAT_SAFE_CEILING = 75.0  # Pause and cool down if heat exceeds this before moving
    HEAT_RESUME_LEVEL = 40.0  # Cool down to this level before resuming travel

    def __init__(self, harvester):
        self.harvester = harvester
        self.name = getattr(harvester, "id", "harvester_1")
        self.base_sector = self.detect_base_sector()
        self.last_target = None

    @classmethod
    def sector_to_rc(cls, sector):
        """Converts sector string (e.g. 'E14') to (row_idx, col_num)."""
        if not sector or len(sector) < 2:
            return None, None
        row_char = sector[0].upper()
        if row_char not in cls.ROWS:
            return None, None
        try:
            r = cls.ROWS.index(row_char)
            c = int(sector[1:])
            if 1 <= c <= cls.NUM_COLS:
                return r, c
        except Exception:
            pass
        return None, None

    @classmethod
    def rc_to_sector(cls, r, c):
        """Converts (row_idx, col_num) to sector string (e.g. 'E14')."""
        if 0 <= r < cls.NUM_ROWS and 1 <= c <= cls.NUM_COLS:
            return f"{cls.ROWS[r]}{c}"
        return None

    @classmethod
    def distance(cls, sec1, sec2):
        """Calculates Manhattan grid distance (O(1)) between two sectors."""
        r1, c1 = cls.sector_to_rc(sec1)
        r2, c2 = cls.sector_to_rc(sec2)
        if r1 is None or r2 is None:
            return 999
        return abs(r1 - r2) + abs(c1 - c2)

    @classmethod
    def find_path(cls, start_sec, target_sec):
        """
        Generates direct orthogonal cardinal path from start_sec to target_sec.
        Takes O(1) operations, avoiding graph-search overhead and step-limit exhaustion.
        """
        if start_sec == target_sec:
            return []
        r1, c1 = cls.sector_to_rc(start_sec)
        r2, c2 = cls.sector_to_rc(target_sec)
        if r1 is None or r2 is None:
            return []

        path = []
        cr, cc = r1, c1

        # Advance columns horizontally
        while cc < c2:
            cc += 1
            path.append(cls.rc_to_sector(cr, cc))
        while cc > c2:
            cc -= 1
            path.append(cls.rc_to_sector(cr, cc))

        # Advance rows vertically
        while cr < r2:
            cr += 1
            path.append(cls.rc_to_sector(cr, cc))
        while cr > r2:
            cr -= 1
            path.append(cls.rc_to_sector(cr, cc))

        return path

    def detect_base_sector(self):
        """Determines the Harvester's depot pad / base sector (starts at depot)."""
        try:
            return self.harvester.get_position()
        except Exception:
            return "E13"

    def get_position(self):
        """Returns current sector string."""
        try:
            return self.harvester.get_position()
        except Exception:
            return self.base_sector

    def get_heat(self):
        """Returns current heat level (0-100)."""
        try:
            return self.harvester.get_heat()
        except Exception:
            return 0.0

    def cool_down(self, target_level=None):
        """Pauses and allows the vehicle to passively cool down."""
        target = target_level or self.HEAT_RESUME_LEVEL
        heat = self.get_heat()
        if heat <= target:
            return

        print(f"[{self.name}] High heat ({heat:.1f}°C). Pausing for passive cooling to {target:.0f}°C...")
        while True:
            sleep(2.0)
            heat = self.get_heat()
            if heat <= target or not self.harvester.is_overheated() and heat <= target:
                print(f"[{self.name}] Cooled down ({heat:.1f}°C). Resuming operations.")
                break

    def store_held_if_any(self):
        """Ensures the single held item slot is empty by storing into Inventory."""
        held = self.harvester.get_held()
        if held and held != "":
            print(f"[{self.name}] Storing held item '{held}' into Inventory...")
            res = self.harvester.store()
            if res.status == "ok":
                print(f"[{self.name}] Successfully stored '{res.item_id}' to Inventory.")
                return True
            elif res.status == "inventory_full":
                print(f"[{self.name}] WARNING: Base inventory full! Cannot store '{held}'.")
                try:
                    notify(f"[{self.name}] Base Inventory Full! Cannot store harvested items.", level="warn", duration_seconds=8.0)
                except Exception:
                    pass
                return False
            else:
                print(f"[{self.name}] Store notice: {res.status} - {res.message}")
        return True

    def move_to(self, target_sector):
        """Navigates step-by-step along the shortest path to target_sector."""
        curr_pos = self.get_position()
        if curr_pos == target_sector:
            return True

        path = self.find_path(curr_pos, target_sector)
        if not path:
            print(f"[{self.name}] No valid path found from {curr_pos} to {target_sector}!")
            return False

        for next_sec in path:
            # Heat check before each step: moving to empty cell adds 7 heat
            if self.get_heat() >= self.HEAT_SAFE_CEILING:
                self.cool_down(self.HEAT_RESUME_LEVEL)

            res = self.harvester.move(next_sec)
            if res.status == "ok":
                pass
            elif res.status == "already_here":
                pass
            elif res.status == "overheated":
                self.cool_down(self.HEAT_RESUME_LEVEL)
                # Retry step
                res = self.harvester.move(next_sec)
                if res.status not in ["ok", "already_here"]:
                    print(f"[{self.name}] Move failed after cooling: {res.status} - {res.message}")
                    return False
            elif res.status in ["moving", "busy"]:
                sleep(1.0)
            else:
                print(f"[{self.name}] Move error to {next_sec}: {res.status} - {res.message}")
                return False

        return self.get_position() == target_sector

    def collect_at_current(self):
        """Picks up the item at current sector and immediately stores it."""
        # Free held slot if something was leftover
        self.store_held_if_any()

        # Check heat before collect: empty collect adds 9 heat
        if self.get_heat() >= (self.HEAT_SAFE_CEILING + 10.0):
            self.cool_down(self.HEAT_RESUME_LEVEL)

        res = self.harvester.collect()
        if res.status == "ok":
            item_name = getattr(res, "name", res.id)
            val = getattr(res, "value", 0)
            print(f"[{self.name}] Collected '{item_name}' (value: {val}) at {self.get_position()}.")
            self.store_held_if_any()
            return True
        elif res.status == "empty":
            return False
        elif res.status == "overheated":
            self.cool_down(self.HEAT_RESUME_LEVEL)
            return self.collect_at_current()
        else:
            print(f"[{self.name}] Collect notice: {res.status} - {res.message}")
            return False

    def harvest_at_current(self):
        """Harvests mature crop at current sector."""
        res = self.harvester.harvest()
        if res.status in ["ok", "partial"]:
            print(f"[{self.name}] Harvested crop at {self.get_position()}: {res.status} - {res.message}")
            return True
        elif res.status == "overheated":
            self.cool_down(self.HEAT_RESUME_LEVEL)
            return self.harvest_at_current()
        else:
            print(f"[{self.name}] Harvest notice: {res.status} - {res.message}")
            return False

    def find_best_target(self):
        """
        Scans all known grid cells and selects the closest sector
        with an uncollected surface item or mature crop.
        """
        curr_pos = self.get_position()
        candidates = []

        # 1. Inspect grid cells from Harvester
        try:
            cells = self.harvester.cells()
            for c in cells:
                if c.status == "item":
                    candidates.append({"sector": c.id, "type": "item", "priority": 1})
                elif c.status == "mature":
                    candidates.append({"sector": c.id, "type": "crop", "priority": 2})
        except Exception:
            pass

        # 2. Also check Scanner results if available
        if not candidates:
            scanner = get_component("scanner_1")
            if scanner and hasattr(scanner, "get_scanned"):
                try:
                    scanned = scanner.get_scanned()
                    for sec, scan_res in scanned.items():
                        if getattr(scan_res, "status", "") == "ok" and getattr(scan_res, "id", ""):
                            candidates.append({"sector": sec, "type": "item", "priority": 1})
                except Exception:
                    pass

        if not candidates:
            return None

        # Sort candidates by Manhattan grid distance from current position (O(1))
        candidates.sort(key=lambda cand: self.distance(curr_pos, cand["sector"]))
        return candidates[0]

    def step(self):
        """Executes one harvest/collection cycle."""
        # Step 1: Offload any held item
        self.store_held_if_any()

        # Step 2: Check current cell first
        curr_pos = self.get_position()
        try:
            curr_cell = self.harvester.cell(curr_pos)
            if curr_cell:
                if curr_cell.status == "item":
                    self.collect_at_current()
                    return
                elif curr_cell.status == "mature":
                    self.harvest_at_current()
                    return
        except Exception:
            pass

        # Step 3: Find closest item or mature crop
        target = self.find_best_target()
        if target:
            target_sec = target["sector"]
            t_type = target["type"]
            print(f"[{self.name}] Routing to {t_type} at {target_sec}...")
            reached = self.move_to(target_sec)
            if reached:
                if t_type == "item":
                    self.collect_at_current()
                elif t_type == "crop":
                    self.harvest_at_current()
            return

        # Step 4: No active targets on the field - return to base depot and cool down
        if self.base_sector and curr_pos != self.base_sector:
            print(f"[{self.name}] No active targets. Returning to base depot ({self.base_sector})...")
            self.move_to(self.base_sector)

        # Cool down completely while resting
        self.cool_down(25.0)
        sleep(5.0)

    def run(self):
        """Continuous harvesting and collection loop."""
        print(f"Harvester Controller ({self.name}) online. Base depot: {self.base_sector}.")
        while True:
            try:
                self.step()
                sleep(0.5)
            except Exception as e:
                print(f"[{self.name}] Exception in harvester loop: {e}")
                sleep(5.0)
