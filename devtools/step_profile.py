"""
Step profiler: runs one lib code path against tests/sample_world.py's
synthetic save under CPython and counts bytecode opcodes, total and per
function (inclusive), to find where a script spends its interpreter steps.

    python devtools/step_profile.py                      # every target, medium world
    python devtools/step_profile.py haul pull --size large --top 15
    python devtools/step_profile.py --list

Opcodes are CPython's, not the game's steps: OPCODES_PER_STEP converts
roughly (measured 1.6-3.0 for loops and calls, docs/cheatsheet/dev_workflow.md
§1d-1). Frames inside tests/game_stubs.py and copy.py are not counted: in
game a component call is one step on our side, however much the stub does.
Ticks assume every script gets the scheduler share at --scripts running
scripts. Use it to compare code versions and to size lib/atomic.py chunks
(measure the worst case, keep it well under the 10,000-step callback cap).
"""
import argparse
import collections
import os
import sys
import types

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
sys.dont_write_bytecode = True

import sample_world  # noqa: E402  (imports harness, which puts every lib/ on sys.path)

OPCODES_PER_STEP = 2.5
TOTAL_STEPS_PER_TICK = 50000
MAX_STEPS_PER_SCRIPT = 1000
SKIP_FILES = ("game_stubs.py", "copy.py", "step_profile.py")


class Profile:
    """Opcode counts: total, inside lib/atomic.py run_atomic() calls, the
    largest single atomic call, and per function (inclusive)."""

    def __init__(self, direct_only=False):
        self.direct_only = direct_only
        self.total = 0
        self.atomic = 0
        self.atomic_calls = 0
        self.atomic_peak = 0
        self._current = None
        self.inclusive = collections.Counter()

    def _tracer(self, frame, event, _arg):
        frame.f_trace_opcodes = True
        if event == "call" and frame.f_code.co_name == "run_atomic" and frame.f_code.co_filename.endswith("atomic.py"):
            if self._current is None:
                self._current = [frame, 0]
                self.atomic_calls += 1
            return self._tracer
        if event == "return" and self._current is not None and frame is self._current[0]:
            self.atomic_peak = max(self.atomic_peak, self._current[1])
            self._current = None
            return self._tracer
        if event != "opcode" or frame.f_code.co_filename.endswith(SKIP_FILES[:2]):
            return self._tracer
        self.total += 1
        if self._current is not None:
            self.atomic += 1
            self._current[1] += 1
            if self.direct_only:
                return self._tracer
        seen = set()
        f = frame
        while f is not None:
            name = os.path.basename(f.f_code.co_filename)
            if not name.endswith(SKIP_FILES):
                key = f"{name}:{f.f_code.co_name}"
                if key not in seen:
                    seen.add(key)
                    self.inclusive[key] += 1
            f = f.f_back
        return self._tracer

    def run(self, fn, *args):
        sys.settrace(self._tracer)
        try:
            return fn(*args)
        finally:
            sys.settrace(None)


def steps_per_tick(scripts):
    return max(1, min(MAX_STEPS_PER_SCRIPT, TOTAL_STEPS_PER_TICK // max(1, scripts)))


def game_memos():
    """Discovery memos at their in-game TTLs (the stub harness turns them off)."""
    import production
    import storage
    production.DISCOVERY_TTL_TICKS = 20
    storage.DISCOVERY_TTL_TICKS = 20


# ---------------------------------------------------------------- targets
# Each takes (size) and returns a zero-argument callable to profile; setup
# (world build, warm-up) happens outside the measured call.

def target_fabricator(size):
    import fabricator
    sample = sample_world.build_sample_world(size)
    game_memos()
    controller = fabricator.FabricatorController(sample.fabricators[0])
    controller.step()
    sample.world.clock.now += 1
    return controller.step


def target_smelter(size):
    import smelter
    sample = sample_world.build_sample_world(size)
    game_memos()
    controller = smelter.SmelterController(sample.smelters[0])
    controller.step()
    sample.world.clock.now += 1
    return controller.step


def target_dock_plan(size):
    import supply_dock
    sample = sample_world.build_sample_world(size)
    game_memos()
    clock = sample.world.get_component("clock")
    return lambda: supply_dock.plan_dock_assignments(clock)


def target_demands(size):
    import production
    sample = sample_world.build_sample_world(size)
    game_memos()
    production.get_material_demands()  # warm the per-script memos (discovery, recipe table)
    sample.world.clock.now += 1
    return production.get_material_demands


class _RouteHost:
    """The VehicleController/DroneController surface the route planners use."""
    name = "profile_vehicle"
    cruise_throttle = 0.7
    SAFETY_MARGIN_MULTIPLIER = 1.2
    log = types.SimpleNamespace(debug=lambda *a, **k: None, start=lambda *a, **k: None, end=lambda *a, **k: None)
    drone = types.SimpleNamespace(cargo=types.SimpleNamespace(space_for=lambda _item: 200))

    def distance_between(self, p1, p2):
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        return (dx * dx + dy * dy) ** 0.5

    def wh_per_meter_at_throttle(self, _throttle):
        return 0.02

    def minimum_wh_per_meter(self):
        return 0.015

    def emergency_reserve(self):
        return 5.0


def _with_host(mixin):
    cls = type(f"Profile{mixin.__name__}", (mixin,), {"_host": property(lambda self: self._profile_host)})
    obj = cls.__new__(cls)
    obj._profile_host = _RouteHost()
    return obj


def target_haul(size, scenario=None):
    """drone_hauler: every (destination, first source) candidate route plus its scoring."""
    import drone_hauler
    sample_world.build_sample_world(size)
    dests, sources = scenario or sample_world.route_scenario(size)
    hauler = _with_host(drone_hauler.DroneHaulerMixin)
    services = [{"coords": (0.0, 0.0)}]

    def plan():
        for dest in dests:
            hauler._reachable(dest, sources)
        for _dest, _candidate in hauler._candidate_routes(dests, sources, 400, (0.0, 0.0), services):
            pass
    return plan


def target_pull(size, scenario=None):
    """vehicle_cargo: a Pioneer's pull chains from every first source (_plan_pull_route())."""
    import vehicle_cargo
    sample_world.build_sample_world(size)
    dests, sources = scenario or sample_world.route_scenario(size)
    puller = _with_host(vehicle_cargo.VehicleCargoMixin)
    need, buffer = dests[0]["need"], dests[0]["buffer"]
    home = dests[0]["coords"]

    puller._profile_host.home_outpost = types.SimpleNamespace(id=dests[0]["outpost_id"], coords=lambda: home, is_home=True)
    puller._profile_host.get_position = lambda: (0.0, 0.0)
    puller._pull_sources = lambda _items, _tick: [dict(s) for s in sources]
    puller._shop_source = lambda *_a: None

    def plan():
        puller._plan_pull_route(need, {}, 400, 0)
        puller._plan_pull_route(need, buffer, 400, 0)
    return plan


def target_wildlife_ration(_size):
    """wildlife_planner: model ranks + fluid ration, worst case (16 colonies, every node bought, gas and liquid each, every fluid short)."""
    from atomic import run_atomic
    import wildlife_planner
    from wildlife_data import SPECIES, BONUS_TREES
    colonies = {}
    statuses = {}
    stock = {}
    prev = {}
    for i, species in enumerate(sorted(SPECIES)):
        hid = "habitat_%d" % (i + 1)
        colonies[species] = hid
        gas, liquid = "gas_%d" % (i % 4), "liquid_%d" % (i % 3)
        statuses[hid] = {"species": species, "established": True, "pop": 20000 + 1000 * i, "tier": 1,
                         "gas": ["", 0.0, [250.0, 650.0], gas, 1.0], "liquid": ["", 0.0, [300.0, 600.0], liquid, 1.0]}
        for fluid in (gas, liquid):
            stock[fluid] = 0.0
            prev[fluid] = [0.0, 0.5, 0]
    nodes = set(tree[slot][0] for tree in BONUS_TREES.values() for slot in ("adaptation", "breakthrough"))

    def plan():
        model = wildlife_planner._colony_model(colonies, statuses, nodes)
        run_atomic(wildlife_planner._ration_pass, colonies, statuses, model, stock, prev, {}, 250)
    return plan


def target_wildlife_plan(_size):
    """wildlife_planner.build_plan(), worst case (16 established colonies, every node bought, recipes and forms known, every fluid short)."""
    import wildlife_planner
    import wildlife_common as wc
    from wildlife_data import SPECIES
    from wildlife_model import schedule_for
    statuses = {}
    stock = {}
    prev = {}
    recipe_inputs = {}
    for i, species in enumerate(sorted(SPECIES)):
        hid = "habitat_%d" % (i + 1)
        gas, liquid = "gas_%d" % (i % 4), "liquid_%d" % (i % 3)
        statuses[hid] = {"species": species, "established": True, "pop": 20000 + 1000 * i, "tier": 1, "feed_level": 10.0,
                         "bought": {"adaptation": True, "breakthrough": True},
                         "gas": ["", 0.0, [250.0, 650.0], gas, 1.0], "liquid": ["", 0.0, [300.0, 600.0], liquid, 1.0]}
        recipe_inputs[wc.recipe_of(species)] = {"forage": 10, "form_%d" % (i % 6): 5, "form_%d" % ((i + 1) % 6): 3}
        for fluid in (gas, liquid):
            stock[fluid] = 0.0
            prev[fluid] = [0.0, 0.5, 0]
    habitat_ids = sorted(statuses)
    snap = {
        "tick": 250, "habitat_ids": habitat_ids, "statuses": statuses, "parked": set(habitat_ids[:4]),
        "cataloged": set(SPECIES), "recipes": set(recipe_inputs), "recipe_inputs": recipe_inputs, "insight": 50.0,
        "schedule": schedule_for(len(habitat_ids)), "targets": [], "prev_assign": {}, "prev_ration": {},
        "prev_supply": prev, "fluid_stock": stock, "feed_stock": {}, "form_stock": {},
        "populations": {s["species"]: s["pop"] for s in statuses.values()}, "mk2_packs": 0,
    }

    def plan():
        wildlife_planner.build_plan(snap)
    return plan


TARGETS = {
    "fabricator": target_fabricator,
    "smelter": target_smelter,
    "dock_plan": target_dock_plan,
    "demands": target_demands,
    "haul": target_haul,
    "pull": target_pull,
    "wildlife_ration": target_wildlife_ration,
    "wildlife_plan": target_wildlife_plan,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help="targets to profile (default: all)")
    parser.add_argument("--size", default="medium", choices=sorted(sample_world.SIZES))
    parser.add_argument("--top", type=int, default=10, help="functions listed per target")
    parser.add_argument("--scripts", type=int, default=112, help="running scripts, for the ticks estimate")
    parser.add_argument("--direct-only", action="store_true", help="list functions by opcodes outside atomic calls")
    parser.add_argument("--list", action="store_true", help="list targets and exit")
    args = parser.parse_args()
    if args.list:
        for name, fn in TARGETS.items():
            print(f"{name:12} {(fn.__doc__ or '').strip()}")
        return
    unknown = [t for t in args.targets if t not in TARGETS]
    if unknown:
        parser.error(f"unknown target(s) {unknown}; --list shows them")
    share = steps_per_tick(args.scripts)
    for name in args.targets or TARGETS:
        fn = TARGETS[name](args.size)
        profile = Profile(args.direct_only)
        profile.run(fn)
        direct = (profile.total - profile.atomic) / OPCODES_PER_STEP
        # each atomic call finishes within the tick it starts in; budget is checked only between calls
        ticks = direct / share + profile.atomic_calls
        print(f"\n=== {name} [{args.size}]: {profile.total} opcodes ~ {profile.total / OPCODES_PER_STEP:,.0f} steps ~ {ticks:,.0f} ticks at {share} steps/tick")
        if profile.atomic_calls:
            print(f"    atomic: {profile.atomic_calls} call(s), {profile.atomic} opcodes, largest call {profile.atomic_peak} opcodes"
                  f" (~{profile.atomic_peak / OPCODES_PER_STEP:,.0f} steps of the 10,000 cap); direct ~{direct:,.0f} steps")
        for key, count in profile.inclusive.most_common(args.top):
            print(f"{count:>10}  {key}")


if __name__ == "__main__":
    main()
