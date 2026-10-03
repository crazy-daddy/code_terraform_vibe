"""
Static scan for repeated game reads: game reads (stacks(), buildings(),
get_component(), ...) and calls into functions that do them, made inside a
loop or comprehension. Joined with devtools/log_block_timing.py so hits under
slow, frequent TreeConsole blocks rank first.

    python devtools/repeat_read_scan.py                       # hits joined with the newest save's logs
    python devtools/repeat_read_scan.py --no-logs --top 60    # static ranking only
    python devtools/repeat_read_scan.py --since 2026-10-03T00:00 --exclude "(?i)fly|drive"

Scans the highest-tier copy of every file under scripts/<N>_*/ (the copy the
game runs). Per function it sums a read cost: each read's weight, times
LOOP_N per enclosing loop, plus the cost of every resolved callee the same
way. A hit is a read or a costly call inside a loop; its score is that cost.
"invariant" marks a direct read that uses no name bound by an enclosing loop,
so the same read repeats with the same arguments (hoist or snapshot it). `while True:` run
loops do not count as loops. "atomic"
marks code reached from run_atomic/run_batched/run_chunked, where steps cost
about one tick per call (score x0.1). "waits" marks a block whose code can
sleep()/wait/mine: its log time is not all compute.

Heuristic: callees resolve by bare name (self.x to the same class first,
then the same module, then anywhere; ambiguous names take the costliest),
loop counts are a flat LOOP_N, and "count"/"level"/... may be a list or str
method. Check every hit in code before acting on it.

Evaluating results: do not redo old work. Before reworking a hit, check
`git log` on its function for earlier perf commits and the figures in their
messages (e.g. 0bf90ef, b90ba66, ae539d0), and time blocks with --since the
deploy of the current code (see log_block_timing.py).
"""
import argparse
import ast
import collections
import io
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LOOP_N = 8
ATOMIC_FACTOR = 0.1
MAX_COST = 1e9

# Side-effect-free game reads and their rough weight (a list-returning or store-walking read is heavy).
HEAVY_READS = {
    "stacks", "buildings", "vehicles", "drones", "outposts", "get_component", "members", "contents",
    "connections", "grids", "list_orders", "list_weekly_orders", "list_recipes", "latest_info", "latest",
    "harvesting_machines", "mobile_units", "pending_constructions", "paused_constructions",
    "active_constructions", "surveyed_sites", "get_stockpile", "cataloged_creatures", "channels",
    "outpost_ids", "modules", "holders", "materials",
}
LIGHT_READS = {
    "capacity", "space_for", "position", "is_running", "get_output_count", "get_input_count",
    "connected_to", "connected_id", "stored", "stock", "species", "slots_used", "slots",
    "slot_capacity", "revival_target", "rescue_status", "required_liquid", "required_gas",
    "required_feed", "queue_size", "rearing_progress", "population", "percent", "outflow_rate",
    "inflow_rate", "next_stage_population", "next_required_liquid", "next_required_gas",
    "next_liquid_band", "next_gas_band", "local_store", "liquid_ok", "liquid_level", "liquid_fluid",
    "liquid_band", "life_stage", "is_stalled", "is_powered", "is_full", "is_established", "is_enabled",
    "is_empty", "is_being_rescued", "headroom", "has_generator", "home", "grid", "gas_ok", "gas_level",
    "gas_fluid", "gas_band", "fluid", "flow_rate", "find_recipe", "fill_percent", "fill_pct", "feed_ok",
    "feed_level", "efficiency", "dispatch_rate", "dispatch_progress", "current_station",
    "current_order", "current_dispatch", "carrying_capacity", "can_power_off", "breeding_rate",
    "breeding_efficiency", "bays_occupied", "bay_count", "power_output", "get_stockpile_used",
    "get_stockpile_capacity", "get_recipe", "get_order", "get_level", "get_insight", "get_docked",
    "get_credits", "get_catalogue", "get_capacity", "get_bonus_tree", "get_active_bonuses", "tier",
    "throttle", "material", "now", "elapsed_game_hours",
}
AMBIGUOUS_READS = {"count", "level", "total", "has", "full", "status"}  # also list/str/dict methods
WEIGHTS = {**{n: 3.0 for n in HEAVY_READS}, **{n: 1.0 for n in LIGHT_READS}, **{n: 0.5 for n in AMBIGUOUS_READS}}
SUSPEND = {"sleep", "mine", "wait_broadcast"}
ATOMIC_RUNNERS = {"run_atomic", "run_batched", "run_chunked"}
# Never resolved as callees: builtins and container methods that share a name with our functions.
NO_RESOLVE = set(WEIGHTS) | {"get", "items", "keys", "values", "append", "pop", "update", "sort", "join",
                              "split", "format", "start", "end", "debug", "trace", "print", "flush", "add",
                              "remove", "setdefault", "extend", "insert", "copy", "index", "clear", "reset",
                              "swallowed"}


def tier_files():
    """{relative path: absolute path} of the highest tier defining each file."""
    tiers = sorted((int(d.split("_")[0]), d) for d in os.listdir(SCRIPTS) if re.match(r"^\d+_", d))
    files = {}
    for _, tier in tiers:
        root = os.path.join(SCRIPTS, tier)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if name.endswith(".py"):
                    path = os.path.join(dirpath, name)
                    files[os.path.relpath(path, root).replace("\\", "/")] = path
    return files


class Function:
    def __init__(self, rel, cls, node):
        self.rel, self.cls, self.node, self.name = rel, cls, node, node.name
        self.module = os.path.basename(rel)[:-3]
        self.qual = f"{self.module}.{cls + '.' if cls else ''}{self.name}"
        self.reads = []      # (weight, depth)
        self.calls = []      # (name, receiver text, depth, site)
        self.sites = []      # in-loop call sites
        self.suspends = False
        self.atomic_targets = set()
        self.templates = []  # log.start() regexes


class Site:
    __slots__ = ("func", "line", "call", "name", "depth", "loop", "invariant", "weight")

    def __init__(self, func, node, name, depth, loop, invariant):
        self.func, self.line, self.name, self.depth, self.loop = func, node.lineno, name, depth, loop
        self.call = ast.unparse(node)[:90]
        self.invariant = invariant
        self.weight = 0.0


def bound_names(target):
    return {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}


def template_regex(arg):
    """Regex for the block names a log.start() argument can produce (placeholders match anything),
    in log_block_timing.block_key form (digits as "#")."""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        parts = [re.escape(re.sub(r"\d+", "#", arg.value.strip()))]
    elif isinstance(arg, ast.JoinedStr):
        parts = []
        for value in arg.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(re.escape(re.sub(r"\d+", "#", value.value)))
            else:
                parts.append(".+?")
    else:
        return None
    pattern = "".join(parts).strip()
    if not pattern or pattern == ".+?":
        return None
    return re.compile("^" + pattern + "$")


class Scanner(ast.NodeVisitor):
    """Walks one function body, tracking enclosing loops; nested defs become their own Function."""

    def __init__(self, func, out):
        self.func, self.out, self.loops = func, out, []  # loops: (bound names, iter text, body names)

    def run(self):
        for stmt in self.func.node.body:
            self.visit(stmt)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        nested = Function(self.func.rel, self.func.cls, node)
        self.out.append(nested)
        Scanner(nested, self.out).run()

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def _loop(self, bound, iter_text, body_nodes):
        assigned = set(bound)
        for body in body_nodes:
            for node in ast.walk(body):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    assigned.add(node.id)
        self.loops.append((assigned, iter_text))

    def visit_For(self, node):
        self.visit(node.iter)
        self._loop(bound_names(node.target), ast.unparse(node.iter)[:50], node.body)
        for stmt in node.body:
            self.visit(stmt)
        self.loops.pop()
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_While(self, node):
        if isinstance(node.test, ast.Constant) and node.test.value:
            # a script's run loop (`while True:`) repeats once per tick, not per item
            for stmt in node.body:
                self.visit(stmt)
            return
        self._loop(set(), "while " + ast.unparse(node.test)[:44], node.body)
        self.visit(node.test)
        for stmt in node.body:
            self.visit(stmt)
        self.loops.pop()

    def _comprehension(self, node, elements):
        self.visit(node.generators[0].iter)
        pushed = 0
        for index, gen in enumerate(node.generators):
            if index:
                self.visit(gen.iter)
            self._loop(bound_names(gen.target), ast.unparse(gen.iter)[:50], [])
            pushed += 1
            for cond in gen.ifs:
                self.visit(cond)
        for element in elements:
            self.visit(element)
        for _ in range(pushed):
            self.loops.pop()

    def visit_ListComp(self, node):
        self._comprehension(node, [node.elt])

    def visit_SetComp(self, node):
        self._comprehension(node, [node.elt])

    def visit_GeneratorExp(self, node):
        self._comprehension(node, [node.elt])

    def visit_DictComp(self, node):
        self._comprehension(node, [node.key, node.value])

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Attribute):
            name, receiver = func.attr, ast.unparse(func.value)
        elif isinstance(func, ast.Name):
            name, receiver = func.id, ""
        else:
            name, receiver = "", ""
        depth = len(self.loops)
        weight = WEIGHTS.get(name, 0.0)
        if name == "get" and "archive" in receiver:
            weight = 1.0
        if name in SUSPEND:
            self.func.suspends = True
        if name in ATOMIC_RUNNERS and node.args:
            target = node.args[0]
            if isinstance(target, (ast.Name, ast.Attribute)):
                self.func.atomic_targets.add(target.id if isinstance(target, ast.Name) else target.attr)
        if name == "start" and receiver.endswith("log") and node.args:
            regex = template_regex(node.args[0])
            if regex is not None:
                self.func.templates.append(regex)
        site = None
        if depth:
            used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            invariant = not any(used & assigned for assigned, _ in self.loops)
            site = Site(self.func, node, name, depth, self.loops[-1][1], invariant)
        if site is not None and not weight:
            site.invariant = False  # a repeated call may change state; only direct reads are hoistable
        if weight:
            self.func.reads.append((weight, depth))
            if site is not None:
                site.weight = weight
                self.func.sites.append(site)
        elif name and name not in NO_RESOLVE:
            self.func.calls.append((name, receiver, depth, site))
        self.generic_visit(node)


def scan(files):
    functions = []
    for rel, path in files.items():
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), path)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(Function(rel, None, node))
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        functions.append(Function(rel, node.name, item))
        # module-level script code: one pseudo-function for the top-level statements
        no_args = ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[])
        top = ast.FunctionDef(name="<module>", args=no_args, body=[
            n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ], decorator_list=[], returns=None, type_params=[], lineno=1)
        functions.append(Function(rel, None, top))
    nested = []
    for func in list(functions):
        Scanner(func, nested).run()
    return functions + nested


class Graph:
    def __init__(self, functions):
        self.functions = functions
        self.by_name = collections.defaultdict(list)
        for func in functions:
            self.by_name[func.name].append(func)
        self.cost_memo, self.suspend_memo = {}, {}

    def resolve(self, caller, name, receiver):
        candidates = self.by_name.get(name, [])
        if not candidates:
            return []
        if receiver == "self" and caller.cls:
            same = [f for f in candidates if f.cls == caller.cls and f.module == caller.module]
            if same:
                return same
            methods = [f for f in candidates if f.cls]
            return methods or candidates
        if receiver:
            module = [f for f in candidates if f.module == receiver.split(".")[-1]]
            if module:
                return module
        same = [f for f in candidates if f.module == caller.module and not f.cls]
        return same or [f for f in candidates if not f.cls] or candidates

    def callees(self, func):
        for name, receiver, depth, site in func.calls:
            yield self.resolve(func, name, receiver), depth, site

    def cost(self, func, stack=()):
        if func in self.cost_memo:
            return self.cost_memo[func]
        if func in stack:
            return 0.0
        stack = stack + (func,)
        total = sum(w * LOOP_N ** d for w, d in func.reads)
        for targets, depth, _ in self.callees(func):
            if targets:
                total += max(self.cost(t, stack) for t in targets) * LOOP_N ** depth
        total = min(total, MAX_COST)
        self.cost_memo[func] = total
        return total

    def suspends(self, func, stack=()):
        if func in self.suspend_memo:
            return self.suspend_memo[func]
        if func in stack:
            return False
        stack = stack + (func,)
        result = func.suspends or any(
            self.suspends(t, stack) for targets, _, _ in self.callees(func) for t in targets)
        self.suspend_memo[func] = result
        return result

    def reachable(self, roots):
        seen, todo = set(), list(roots)
        while todo:
            func = todo.pop()
            if func in seen:
                continue
            seen.add(func)
            for targets, _, _ in self.callees(func):
                todo.extend(targets)
        return seen

    def atomic_functions(self):
        roots = []
        for func in self.functions:
            for name in func.atomic_targets:
                roots.extend(self.resolve(func, name, ""))
        return self.reachable(roots)


def hits(graph):
    atomic = graph.atomic_functions()
    rows = []
    for func in graph.functions:
        sites = list(func.sites)
        for targets, depth, site in graph.callees(func):
            if site is None or not targets:
                continue
            cost = max(graph.cost(t) for t in targets)
            if cost:
                site.weight = cost
                sites.append(site)
        for site in sites:
            score = site.weight * LOOP_N ** site.depth * (2 if site.invariant else 1)
            if func in atomic:
                score *= ATOMIC_FACTOR
            rows.append({"site": site, "score": score, "atomic": func in atomic})
    return rows


def join_blocks(graph, rows, stats, sec_per_tick):
    """Attach to every hit the slowest timed block whose function reaches it."""
    blocks = []
    for (kind, key), entry in stats.items():
        owners = [f for f in graph.functions if any(r.match(key) for r in f.templates)]
        if not owners:
            continue
        ticks = sum(entry["seconds"]) / (sec_per_tick or 1)
        blocks.append({"kind": kind, "key": key, "n": len(entry["seconds"]), "ticks": ticks,
                       "median": sorted(entry["seconds"])[len(entry["seconds"]) // 2] / (sec_per_tick or 1),
                       "reach": graph.reachable(owners),
                       "waits": any(graph.suspends(f) for f in owners)})
    blocks.sort(key=lambda b: b["ticks"], reverse=True)
    for row in rows:
        row["block"] = next((b for b in blocks if row["site"].func in b["reach"]), None)
    return blocks


def print_rows(rows, top):
    for row in rows[:top]:
        site = row["site"]
        flags = ",".join(f for f, on in (("invariant", site.invariant), ("atomic", row["atomic"])) if on)
        print(f"  {row['score']:>9.0f}  d{site.depth}  {site.func.rel}:{site.line}  {site.func.qual}")
        print(f"             {site.call}")
        print(f"             loop over: {site.loop}" + (f"   [{flags}]" if flags else ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-logs", action="store_true", help="static ranking only")
    parser.add_argument("--save", help="save_*_scripts folder (default: newest)")
    parser.add_argument("--since", help="only log lines after this ISO time")
    parser.add_argument("--exclude", help="regex; skip blocks whose name matches")
    parser.add_argument("--blocks", type=int, default=15, help="timed blocks to list")
    parser.add_argument("--per-block", type=int, default=6, help="hits shown per block")
    parser.add_argument("--top", type=int, default=30, help="static hits outside timed blocks")
    args = parser.parse_args()
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

    files = tier_files()
    graph = Graph(scan(files))
    rows = sorted(hits(graph), key=lambda r: r["score"], reverse=True)
    print(f"{len(files)} files, {len(graph.functions)} functions, {len(rows)} in-loop read hits\n")

    if args.no_logs:
        print_rows(rows, args.top)
        return

    import log_block_timing as lbt
    save = args.save or lbt.newest_save()
    paths = lbt.log_files(os.path.join(save, "logs"))
    sec_per_tick = lbt.calibrate(paths)
    stats, _, _, span, _census = lbt.collect(paths, sec_per_tick, None, args.since)
    if args.exclude:
        pattern = re.compile(args.exclude)
        stats = {k: v for k, v in stats.items() if not pattern.search(k[1])}
    blocks = join_blocks(graph, rows, stats, sec_per_tick)
    print(f"log window {span[0]} .. {span[1]} (UTC), {len(blocks)} timed blocks matched to code\n")

    shown = 0
    for block in blocks:
        mine = [r for r in rows if r["block"] is block]
        if not mine:
            continue
        waits = "  [waits]" if block["waits"] else ""
        print(f"{block['kind']} | {block['key']} | n={block['n']} median={block['median']:.0f} ticks "
              f"total={block['ticks']:.0f} ticks{waits}")
        print_rows(mine, args.per_block)
        print()
        shown += 1
        if shown >= args.blocks:
            break

    print("Top hits outside timed blocks:")
    print_rows([r for r in rows if r["block"] is None], args.top)


if __name__ == "__main__":
    main()
