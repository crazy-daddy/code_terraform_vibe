# One FieldKeeperController.step() (lib/field_keeper.py) as a record: what the pass read, its planning
# timing, the task it chose and the last world action. No game calls; the controller fills it.
#
#   FieldPass  -- the pass: cells / statuses / planted (the step view), the inputs the choice reads
#                 (rules, layout, active, mine, spare_items), the stock memo handle, the deployed-machine
#                 map, the plan-note phases, the chosen Choice and last_action
#   Choice     -- the task choose() picked: kind (CHOICE_KINDS, in priority order), target sector, detail
#
# Writers: FieldKeeperController fills the pass in prepare_pass() and records choices; last_action only through
# FieldKeeperController.note_action(); machine_map only through HarvesterMachinesMixin (step_machines(),
# forget_machines()). A new pass starts with the previous pass's last_action, which the status entry reports.

from dataclasses import dataclass

# choose() order: the first kind that has work wins (field_keeper.py header, A and 0-7).
CHOICE_KINDS = ("amplify", "stray", "build", "care", "harvest", "uproot", "plant", "pave", "collect", "idle")


@dataclass
class Choice:
    """One task of a pass: kind (CHOICE_KINDS), target sector, detail (species, machine kind or care kinds)."""

    kind: str
    target: str | None = None
    detail: tuple | str | list | None = None


class FieldPass:
    """State of one FieldKeeperController.step()."""

    def __init__(self, tick, last_action="", stock=None):
        self.tick = tick  # tick the pass began
        self.mark_tick = tick  # tick the last planning phase ended
        self.phases = []  # [(phase, ticks)] for the plan note
        self.cells = {}  # {sector: Cell}, read once per pass
        self.statuses: dict | None = None  # {sector: Cell.status}; None until the cells are read
        self.planted = {}  # {sector: Cell} of the growing / stalled / mature cells
        self.rules: dict | None = None
        self.layout: dict | None = {}
        self.active = {}
        self.mine = {}  # harvester_layout(): the cells the Harvester plants itself (work_on_pass())
        self.spare_items = []  # loose items off the path
        self.stock = stock if stock is not None else {}  # the hub's per-step stock memo
        self.machine_map: dict | None = None  # deployed field machines, read once per pass (HarvesterMachinesMixin)
        self.choice: Choice | None = None  # the Choice the pass acts on
        self.last_action = last_action  # last completed world action (FieldKeeperController.note_action())

    def set_view(self, cells, statuses, planted):
        """The pass's cell read: one statuses dict shared by target choice and route."""
        self.cells = cells
        self.statuses = statuses
        self.planted = planted

    def has_view(self, cells):
        """True when `cells` is this pass's read, so its statuses and planted dicts apply."""
        return self.statuses is not None and self.cells is cells

    def mark(self, phase, now):
        """Ends a planning phase at tick `now`."""
        self.phases.append((phase, now - self.mark_tick))
        self.mark_tick = now

    def phase_note(self):
        """(total ticks, "phase n, ...") of the phases so far, zero phases left out."""
        total = sum(n for _, n in self.phases)
        return total, ", ".join(f"{phase} {n}" for phase, n in self.phases if n)
