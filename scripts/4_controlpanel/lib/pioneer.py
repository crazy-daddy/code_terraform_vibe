# Shared Library for Pioneer Multipurpose Heavy Vehicle Automation
# Inherits from VehicleController (lib/vehicle.py).
# Picks a role from the mounted equipment and runs its loop; the
# Constructor role is BuildJob (lib/job_build.py) over the build action in
# lib/pioneer_construction.py and material stocking in lib/pioneer_stock.py,
# the Scout role is SurveyJob (lib/job_survey.py), the Miner role is
# MineJob with OutpostStockpile(HOME_BASE) (lib/job_mine.py), the Hauler
# role is PullJob (lib/job_pull.py), hardware
# upgrades live in lib/pioneer_upgrade.py, commission fitting in
# lib/pioneer_commission.py.

from job_build import BuildJob
from job_mine import MineJob, OutpostStockpile
from job_pull import PullJob
from job_survey import SurveyJob
from pioneer_commission import LoadoutFittingMixin
from pioneer_construction import PioneerConstructionMixin
from pioneer_stock import ConstructionStockMixin
from pioneer_upgrade import PioneerUpgradeMixin
from vehicle import VehicleController


class PioneerController(PioneerConstructionMixin, ConstructionStockMixin, VehicleController, PioneerUpgradeMixin, LoadoutFittingMixin):
    """
    Automated Heavy Field Vehicle & Constructor Controller for Pioneer chassis.
    Extends VehicleController with field construction, module slot management,
    infrastructure deployment (pipes, power lines, outposts), and deep expeditions.
    """

    # Role name -> the vehicle attribute whose presence identifies it, used by
    # detect_role()/run() to pick a role from mounted equipment rather than
    # requiring the entrypoint script to name the loop function directly.
    # "hauler" is deliberately absent: it's the fallback when none of these
    # are mounted, not a module-detected role.
    ROLE_MODULES = {
        "constructor": "constructor",
        "scout": "sonar",
        "miner": "drill",
    }

    def __init__(self, vehicle: "Pioneer", home_base=None):
        super().__init__(vehicle, home_base=home_base)
        self.vehicle: Pioneer = vehicle
        # Blueprint progress (0-1) after the last constructor.execute() of the
        # latest execute_construction() call; 1.0 = finished.
        self.last_build_progress = 0.0

    def detect_role(self, role_override=None):
        """
        Inspects mounted modules (ROLE_MODULES) and returns one of
        "constructor"/"scout"/"miner"/"hauler" (hauler = fallback, no
        relevant module mounted). role_override skips equipment probing
        entirely and returns that role as-is, for the rare intentionally
        mixed loadout that would otherwise be ambiguous. Returns None only
        when more than one role-defining module is mounted and no override
        was given -- caller must treat that as "cannot start".
        """
        if role_override is not None:
            self.log.debug(f"[{self.name}] Role override supplied: '{role_override}'; skipping equipment probe.")
            return role_override

        self.log.start(f"[{self.name}] Detecting role from mounted equipment")
        present = []
        for role, attr in self.ROLE_MODULES.items():
            mounted = hasattr(self.vehicle, attr)
            self.log.debug(f"{attr} module mounted: {mounted}")
            if mounted:
                present.append(role)

        if len(present) > 1:
            self.log.level("warn").print(f"[{self.name}] Multiple role-defining modules mounted ({', '.join(present)}); cannot auto-detect a role. Call run(role_override=...) with one of {list(self.ROLE_MODULES)} + 'hauler' to force a role.")
            self.log.end(f"[{self.name}] Role detection failed")
            return None

        role = present[0] if present else "hauler"
        self.log.end(f"[{self.name}] Detected role: '{role}'")
        return role

    def run(self, role_override=None, dest_outpost_id=None):
        """
        Unified entrypoint: detects this Pioneer's role from its mounted
        equipment (Constructor Module -> constructor, Sonar Module -> scout,
        Drill Module -> miner, none of those -> hauler) and dispatches to the
        matching loop, so a thin entrypoint script no longer needs to name
        the loop function by hand. Every role works for its HOME_BASE: a
        hauler fetches what that outpost requests from anywhere and brings
        it there (PullJob, lib/job_pull.py). role_override forces a specific role,
        bypassing detection -- required when more than one role-defining
        module is mounted at once (see detect_role()). A Pioneer launched from
        the FLEET card's Commission tab fits its parts first (lib/pioneer_commission.py).
        dest_outpost_id is ignored; a real outpost id there (an entrypoint
        written for push hauling) is warned about, since haulers pull to
        HOME_BASE rather than deliver elsewhere.
        """
        if dest_outpost_id not in (None, "", "None", "*", "any", "%"):
            self.log.level("warn").print(f"[{self.name}] DESTINATION_OUTPOST_ID='{dest_outpost_id}' is ignored: haulers pull to HOME_BASE ('{self.home_base}'). Set HOME_BASE='{dest_outpost_id}' to supply that outpost.")
        self.fit_commissioned_loadout()
        role = self.detect_role(role_override)
        if role is None:
            return
        self.role = role

        if role == "constructor":
            self.run_job_loop(BuildJob(self))
        elif role == "scout":
            job = SurveyJob(self)
            if job.can_run():
                self.run_job_loop(job)
        elif role == "miner":
            self.run_job_loop(MineJob(self, OutpostStockpile(self.home_base)))
        elif role == "hauler":
            self.run_job_loop(PullJob(self))
        else:
            self.log.level("warn").print(f"[{self.name}] Unknown role '{role}'.")
