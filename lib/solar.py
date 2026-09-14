# Shared Library for Solar Generator Automation
# Handles closed-loop sun tracking and grid-aware Master election using PowerGridManager.
from power import PowerGridManager, DEFAULT_SHEDDING_TIERS


class SolarController:
    """
    Manages solar tracking and central power grid management for solar generators.
    Features automatic Master/Follower election:
    - Master: tracks Sun, monitors PowerGrid, manages dynamic load shedding/recovery via PowerGridManager.
    - Follower: tracks Sun tilt angle with zero redundant grid polling.
    - Grid-Aware Master Election:
      * Discovers all solar generators connected to THIS generator's power grid via power_control.grid().
      * Elects the lowest numeric ID running solar generator on this grid as Master.
      * If grids join up via power lines, all panels join the same grid and elect a single Master.
      * If grids are separate (e.g. unjoined outpost), each grid elects its own independent Master.
    """

    def __init__(self, machine, clock=None, power=None, run_ctrl=None):
        self.machine = machine
        self.name = getattr(machine, "id", "solar")
        self.clock = clock or get_component("clock")
        self.power = power or get_component("power_control")
        self.run_ctrl = run_ctrl or get_component("run_control")

        self.is_master = False
        self.manager = PowerGridManager(machine, clock=self.clock, power=self.power)

    @property
    def grid_anchor(self):
        return self.manager.grid_anchor

    @property
    def shedded_machines(self):
        return self.manager.shedded_machines

    def get_grid(self):
        return self.manager.get_grid()

    def check_master(self):
        """
        Elects a single Master per independent power grid:
        - Discovers all solar generators connected to THIS generator's power grid.
        - Elects the lowest numeric ID running solar generator on this grid as Master.
        """
        grid = self.get_grid()
        grid_solars = []

        if grid:
            if hasattr(grid, "machine_ids") and grid.machine_ids:
                for mid in grid.machine_ids:
                    if mid.startswith("solar"):
                        grid_solars.append(mid)
            elif hasattr(grid, "members") and grid.members:
                for member in grid.members:
                    mid = getattr(member, "id", "")
                    m_type = getattr(member, "type_id", "")
                    roles = getattr(member, "roles", [])
                    if mid.startswith("solar") or m_type == "solar_generator" or "solar" in roles:
                        grid_solars.append(mid)

        # Fallback: if power_control.grid() didn't resolve, check outpost buildings
        if not grid_solars:
            outpost = getattr(self.machine, "outpost", None)
            if outpost and hasattr(outpost, "buildings"):
                try:
                    for b in outpost.buildings("solar_generator"):
                        b_id = getattr(b, "id", "")
                        if b_id:
                            grid_solars.append(b_id)
                except Exception:
                    pass

        if not grid_solars:
            grid_solars = [self.name]

        def solar_sort_key(s_id):
            try:
                return int(s_id.split('_')[-1])
            except Exception:
                return 9999

        grid_solars = sorted(list(set(grid_solars)), key=solar_sort_key)

        if self.run_ctrl and hasattr(self.run_ctrl, "is_running"):
            try:
                for cand in grid_solars:
                    if self.run_ctrl.is_running(cand):
                        return (self.name == cand)
            except Exception:
                pass

        return (self.name == grid_solars[0])

    def track_sun(self):
        """Adjusts tilt angle based on current sun elevation."""
        elevation = self.clock.get_elevation() if self.clock else 0.0
        tilt = max(0, min(90, 90 - elevation))
        self.machine.set_tilt(tilt)
        return elevation

    def update_role(self):
        """Checks and logs master/follower role transitions."""
        was_master = self.is_master
        self.is_master = self.check_master()
        grid_tag = f" on grid '{self.grid_anchor}'" if self.grid_anchor else ""
        if self.is_master and not was_master:
            print(f"[{self.name}] Promoted to Power Grid Master{grid_tag}.")
        elif was_master and not self.is_master:
            print(f"[{self.name}] Demoted to Follower{grid_tag} (unified with upstream master).")
        return self.is_master

    def step(self):
        # 1. Closed-loop solar elevation tracking (both Master and Follower)
        elevation = self.track_sun()

        # 2. Master / Follower role check per independent grid
        if not self.update_role():
            return

        # 3. Master Grid Supervision via PowerGridManager
        grid = self.get_grid()
        self.manager.supervise_grid(grid, elevation)

    def run(self, poll_interval=1.0):
        role = "Master" if self.check_master() else "Follower"
        grid_tag = f" on grid '{self.grid_anchor}'" if self.grid_anchor else ""
        print(f"Solar Tracker ({self.name}) online via Shared Library as {role}{grid_tag}.")
        while True:
            self.step()
            sleep(poll_interval)

