# The vehicle's current job target as one record (layer 0 of the vehicle
# mixins, docs/plans/mixin_refactor/README.md). VehicleClaimsMixin is its only
# writer (begin_mission / adopt_mission / end_mission set VehicleController.mission); everything
# else reads it. to_record() is the dict fleet_claims_common.save_mission keeps
# under VehicleClaimsMixin.MISSION_KEY so a script reload resumes the trip;
# from_record() reads it back. No vehicle imports.

from dataclasses import dataclass
from construction_plan import coords_of


@dataclass
class Mission:
    kind: str  # archive record kind: "mine", "poi_survey", ...
    target_key: str  # claim key: "site_9", "poi_12_40"
    target: dict  # candidate dict: type, coords, name, ...
    prio: int = 0
    source: str = ""  # "blueprint", "request", "stockpile", "poi"
    budget: dict | None = None
    tick: int = 0  # set by begin_mission when the record is saved
    reserved_yield: bool = False  # True while a mining_reservations entry backs this mission

    def to_record(self):
        """The dict fleet_claims_common.save_mission stores."""
        return {"target_key": self.target_key, "kind": self.kind, "target": self.target, "tick": self.tick}

    @classmethod
    def from_record(cls, record):
        """A Mission from a stored record (to_record() shape)."""
        target = record.get("target")
        return cls(
            kind=record.get("kind") or "",
            target_key=record.get("target_key") or "",
            target=target if isinstance(target, dict) else {},
            tick=record.get("tick") or 0,
        )

    @property
    def coords(self):
        """(x, y) floats of the target, None when it has none."""
        return coords_of(self.target.get("coords"))
