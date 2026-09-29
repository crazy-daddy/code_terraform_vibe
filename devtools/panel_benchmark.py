# Interpreter benchmark: pure local computation, no game side effects.
# Run in a control_panel script slot: the Playground aborts long runs. Results and reading: docs/BENCHMARK.md.
# range(n) materialises a list (item limit applies), so each case runs a small fixed chunk per call
# and the number of calls doubles until one timed run lasts >= MIN_SECONDS of simulation time.

# Switches. Interruptive cases change game state briefly (see the INTERRUPTIVE section); off by default.
RUN_LOCAL = True
RUN_API = True
RUN_INTERRUPTIVE = False
# Interruptive inputs (a case is skipped while its constant is empty):
BENCH_POWER_MACHINE_ID = ""  # machine id to switch off and on repeatedly; state is restored afterwards

clock = get_component("clock")
MIN_SECONDS = 2.0
MAX_REPS = 20000
STORAGE_TYPES = ("storage_bin", "warehouse", "large_warehouse")
BENCH_KEY = "bench.tmp"
BENCH_CHANNEL = "bench.tmp"

data = list(range(1000))
row3 = [0, 1, 2]
table = {i: i for i in range(100)}
mixed = [0] * 100


def f0():
    return 0


def f2(a, b):
    return a


def bench_empty_loop(n):
    for i in range(n):
        pass


def bench_while_loop(n):
    i = 0
    while i < n:
        i += 1


def bench_arith(n):
    x = 0
    for i in range(n):
        x = (x + i * 2) % 7


def bench_list_read(n):
    for i in range(n):
        v = data[i % 1000]


def bench_list_write(n):
    for i in range(n):
        data[i % 1000] = i


def bench_call_0(n):
    for i in range(n):
        f0()


def bench_call_2(n):
    for i in range(n):
        f2(i, i)


def bench_builtin_len(n):
    for i in range(n):
        len(data)


def bench_component_call(n):
    for i in range(n):
        clock.elapsed_seconds()


def bench_dict_rw(n):
    for i in range(n):
        table[i % 100] = table[(i + 1) % 100]


def bench_append(n):
    out = []
    for i in range(n):
        out.append(i)


def bench_comprehension(n):
    out = [i for i in range(n)]


def bench_if_chain(n):
    for i in range(n):
        if i == 1:
            pass
        elif i == 2:
            pass
        elif i == 3:
            pass


# Counting matches in a 1000-element list: hand loop vs native.
def bench_count_loop_1000(n):
    for i in range(n):
        k = 0
        for v in data:
            if v == 5:
                k += 1


def bench_count_native_1000(n):
    for i in range(n):
        data.count(5)


def bench_in_loop_1000(n):
    for i in range(n):
        found = False
        for v in data:
            if v == 999:
                found = True
                break


def bench_in_native_1000(n):
    for i in range(n):
        999 in data


def bench_sum_loop_1000(n):
    for i in range(n):
        s = 0
        for v in data:
            s += v


def bench_sum_native_1000(n):
    for i in range(n):
        sum(data)


def bench_sort_native_1000(n):
    for i in range(n):
        sorted(data)


# 3x3 neighbourhood count: 8-neighbour loop vs three slices + count.
def bench_nbr_loop(n):
    offs = (-35, -34, -33, -1, 1, 33, 34, 35)
    for i in range(n):
        k = 0
        for o in offs:
            if mixed[50 + o] == 0:
                k += 1


def bench_nbr_slices(n):
    for i in range(n):
        w = mixed[15:18] + mixed[49:52] + mixed[83:86]
        w.count(0)


def bench_slice_1(n):
    for i in range(n):
        mixed[1:4]


def bench_slice_assign(n):
    for i in range(n):
        mixed[1:4] = row3


def bench_list_concat(n):
    for i in range(n):
        row3 + row3


def bench_list_mul(n):
    for i in range(n):
        [0] * 1156


def bench_tuple_iter(n):
    t = (1, 2, 3, 4, 5, 6, 7, 8)
    for i in range(n):
        for v in t:
            pass


def bench_fstring(n):
    for i in range(n):
        s = f"{i}"


def bench_min_max(n):
    for i in range(n):
        max(i, 5)


def bench_divmod_ops(n):
    for i in range(n):
        a = i % 32
        b = i // 32


CASES = [
    ("empty for-range loop", bench_empty_loop, 500),
    ("while loop (i += 1)", bench_while_loop, 500),
    ("arithmetic (+ * %)", bench_arith, 500),
    ("i % 32 and i // 32", bench_divmod_ops, 500),
    ("list read", bench_list_read, 500),
    ("list write", bench_list_write, 500),
    ("call fn() 0 args", bench_call_0, 500),
    ("call fn(a, b)", bench_call_2, 500),
    ("builtin len()", bench_builtin_len, 500),
    ("builtin max(a, b)", bench_min_max, 500),
    ("component call clock.elapsed_seconds()", bench_component_call, 500),
    ("dict read+write", bench_dict_rw, 500),
    ("list.append", bench_append, 500),
    ("list comprehension (per element)", bench_comprehension, 500),
    ("if/elif chain, 3 tests", bench_if_chain, 500),
    ("iterate 8-tuple", bench_tuple_iter, 500),
    ("f-string", bench_fstring, 500),
    ("slice mixed[1:4]", bench_slice_1, 500),
    ("slice assign mixed[1:4] = row", bench_slice_assign, 500),
    ("list + list (3+3)", bench_list_concat, 500),
    ("[0] * 1156", bench_list_mul, 50),
    ("8-neighbour loop count", bench_nbr_loop, 500),
    ("3 slices + count", bench_nbr_slices, 500),
    ("count == 5 in 1000: python loop", bench_count_loop_1000, 2),
    ("count == 5 in 1000: list.count", bench_count_native_1000, 50),
    ("membership 999 in 1000: python loop", bench_in_loop_1000, 2),
    ("membership 999 in 1000: `in`", bench_in_native_1000, 50),
    ("sum 1000: python loop", bench_sum_loop_1000, 2),
    ("sum 1000: sum()", bench_sum_native_1000, 50),
    ("sorted() of 1000", bench_sort_native_1000, 50),
]


def time_case(fn, chunk):
    reps = 1
    while True:
        t0 = clock.elapsed_seconds()
        for r in range(reps):
            fn(chunk)
        dt = clock.elapsed_seconds() - t0
        if dt >= MIN_SECONDS or reps >= MAX_REPS:
            return reps * chunk, dt
        reps = reps * 2


def run_group(title, cases):
    print(f"--- {title} ---")
    rows = []
    for name, fn, chunk in cases:
        n, dt = time_case(fn, chunk)
        per_us = dt / n * 1000000.0
        rows.append((name, per_us))
        print(f"{name}: n={n} dt={dt:.2f}s -> {per_us:.2f} us/iter")
    return rows


def report(title, rows, base):
    print(f"--- {title}: relative to empty loop iteration ---")
    for name, per_us in rows:
        print(f"{name}: {per_us / base:.1f}x")


# ---------------------------------------------------------------------------
# API section. Every case only reads game state, or writes one scratch key/channel that is removed at
# the end. Components missing in this save are skipped with a message.
# ---------------------------------------------------------------------------

env = {}


def find_component(comp_id):
    try:
        comp = get_component(comp_id)
    except Exception as err:
        print(f"  skip {comp_id}: {err}")
        return None
    if comp is None:
        print(f"  skip {comp_id}: not available")
    return comp


def bump(v):
    return v


def api_get_component_lookup(n):
    for i in range(n):
        get_component("clock")


def api_get_component_lookup_building(n):
    bid = env["storage_id"]
    for i in range(n):
        get_component(bid)


def api_clock_tick(n):
    for i in range(n):
        clock.tick()


def api_clock_get_time(n):
    for i in range(n):
        clock.get_time()


def api_sleep(n):
    for i in range(n):
        sleep(0.1)


def api_console_debug(n):
    console = env["console"]
    for i in range(n):
        console.debug("bench")


def api_console_now(n):
    console = env["console"]
    for i in range(n):
        console.now()


def api_archive_get_missing(n):
    nb = env["notebook"]
    for i in range(n):
        nb.get("bench.missing")


def api_archive_has_missing(n):
    nb = env["notebook"]
    for i in range(n):
        nb.has("bench.missing")


def api_archive_set_small(n):
    nb = env["notebook"]
    v = {"a": 1, "b": [1, 2, 3]}
    for i in range(n):
        nb.set(BENCH_KEY, v)


def api_archive_get_small(n):
    nb = env["notebook"]
    for i in range(n):
        nb.get(BENCH_KEY)


def api_archive_transaction_small(n):
    nb = env["notebook"]
    for i in range(n):
        nb.transaction(BENCH_KEY, {}, bump)


def api_archive_keys(n):
    nb = env["notebook"]
    for i in range(n):
        nb.keys("bench.")


def api_archive_set_big(n):
    nb = env["notebook"]
    v = env["big"]
    for i in range(n):
        nb.set(BENCH_KEY, v)


def api_archive_get_big(n):
    nb = env["notebook"]
    for i in range(n):
        nb.get(BENCH_KEY)


def api_archive_transaction_big(n):
    nb = env["notebook"]
    for i in range(n):
        nb.transaction(BENCH_KEY, {}, bump)


def api_archive_result_status(n):
    res = env["notebook"].set(BENCH_KEY, {"a": 1})
    for i in range(n):
        res.status


def api_bus_broadcast(n):
    bus = env["comms"]
    for i in range(n):
        bus.broadcast(BENCH_CHANNEL, i)


def api_bus_latest(n):
    bus = env["comms"]
    for i in range(n):
        bus.latest(BENCH_CHANNEL)


def api_bus_latest_info(n):
    bus = env["comms"]
    for i in range(n):
        bus.latest_info(BENCH_CHANNEL)


def api_bus_send_receive(n):
    bus = env["comms"]
    for i in range(n):
        bus.send(BENCH_CHANNEL, i)
        bus.receive(BENCH_CHANNEL)


def api_bus_queue_size(n):
    bus = env["comms"]
    for i in range(n):
        bus.queue_size(BENCH_CHANNEL)


def api_bus_pending(n):
    bus = env["comms"]
    for i in range(n):
        bus.pending(BENCH_CHANNEL)


def api_bus_channels(n):
    bus = env["comms"]
    for i in range(n):
        bus.channels()


def api_network_outposts(n):
    net = env["net"]
    for i in range(n):
        net.outposts()


def api_network_home(n):
    net = env["net"]
    for i in range(n):
        net.home()


def api_home_coords(n):
    home = env["home"]
    for i in range(n):
        home.coords()


def api_home_buildings(n):
    home = env["home"]
    for i in range(n):
        home.buildings()


def api_home_buildings_filtered(n):
    home = env["home"]
    for i in range(n):
        home.buildings("storage_bin")


def api_building_fields(n):
    blds = env["blds"]
    for i in range(n):
        for b in blds:
            b.type_id


def api_storage_count(n):
    bin_ = env["storage"]
    for i in range(n):
        bin_.count("iron_ore")


def api_storage_fill(n):
    bin_ = env["storage"]
    for i in range(n):
        bin_.fill_percent()


def api_storage_stacks(n):
    bin_ = env["storage"]
    for i in range(n):
        bin_.stacks()


def api_battery_level(n):
    bat = env["battery"]
    for i in range(n):
        bat.get_level()


def api_inventory_count(n):
    inv = env["inventory"]
    for i in range(n):
        inv.count("iron_ore")


def api_inventory_used(n):
    inv = env["inventory"]
    for i in range(n):
        inv.get_used()


def api_inventory_stacks(n):
    inv = env["inventory"]
    for i in range(n):
        inv.stacks()


def api_power_total(n):
    power = env["power"]
    for i in range(n):
        power.total()


def api_power_grids(n):
    power = env["power"]
    for i in range(n):
        power.grids()


def api_power_is_powered(n):
    power = env["power"]
    mid = env["storage_id"]
    for i in range(n):
        power.is_powered(mid)


def api_fleet_vehicles(n):
    fleet = env["fleet"]
    for i in range(n):
        fleet.vehicles()


def api_fleet_drones(n):
    fleet = env["fleet"]
    for i in range(n):
        fleet.drones()


def api_nocturna_progress(n):
    world = env["nocturna"]
    for i in range(n):
        world.terraform_progress()


def api_nocturna_biome_at(n):
    world = env["nocturna"]
    for i in range(n):
        world.biome_at(0, 0)


def api_nocturna_poi(n):
    world = env["nocturna"]
    for i in range(n):
        world.points_of_interest()


def api_atmosphere_o2(n):
    atmo = env["atmosphere"]
    for i in range(n):
        atmo.get_o2()


def api_research_unlocked(n):
    research = env["research"]
    for i in range(n):
        research.unlocked()


def api_research_is_unlocked(n):
    research = env["research"]
    for i in range(n):
        research.is_unlocked("bench_unknown")


def api_catalog_lookup(n):
    catalog = env["catalog"]
    for i in range(n):
        catalog.lookup("iron_ore")


def api_shop_catalogue(n):
    shop = env["shop"]
    for i in range(n):
        shop.get_catalogue()


def api_orders_list(n):
    orders = env["orders"]
    for i in range(n):
        orders.list_orders()


def api_journal_is_empty(n):
    journal = env["journal"]
    for i in range(n):
        journal.is_empty(0, 0)


def api_journal_biomass_coords(n):
    journal = env["journal"]
    for i in range(n):
        journal.biomass_coords()


def add_case(cases, comp_key, name, fn, chunk):
    if comp_key is None or env.get(comp_key) is not None:
        cases.append((name, fn, chunk))


def setup_api():
    print("API setup: discovering components")
    env["console"] = find_component("console")
    env["notebook"] = find_component("notebook")
    env["comms"] = find_component("comms")
    env["net"] = find_component("outpost_network")
    env["inventory"] = find_component("inventory")
    env["power"] = find_component("power_control")
    env["fleet"] = find_component("fleet")
    env["nocturna"] = find_component("nocturna")
    env["atmosphere"] = find_component("atmosphere")
    env["research"] = find_component("research")
    env["catalog"] = find_component("item_catalog")
    env["shop"] = find_component("shop")
    env["orders"] = find_component("orders")
    env["journal"] = find_component("journal")
    env["big"] = {f"k{i}": i for i in range(100)}
    env["home"] = None
    env["blds"] = []
    env["storage_id"] = None
    env["storage"] = None
    env["battery"] = None
    if env["net"] is not None:
        env["home"] = env["net"].home()
        env["blds"] = env["home"].buildings()
        counts = {}
        for outpost in env["net"].outposts():
            for b in outpost.buildings():
                counts[b.type_id] = counts.get(b.type_id, 0) + 1
                if b.type_id in STORAGE_TYPES and env["storage"] is None:
                    env["storage_id"] = b.id
                    env["storage"] = find_component(b.id)
                if b.type_id == "battery" and env["battery"] is None:
                    env["battery"] = find_component(b.id)
        print(f"  building types across all outposts: {counts}")
    print(f"  home buildings: {len(env['blds'])}, storage: {env['storage_id']}")


def build_api_cases():
    c = []
    add_case(c, None, "get_component('clock') lookup", api_get_component_lookup, 20)
    add_case(c, "storage", "get_component(building id) lookup", api_get_component_lookup_building, 20)
    add_case(c, None, "clock.tick()", api_clock_tick, 50)
    add_case(c, None, "clock.get_time()", api_clock_get_time, 50)
    add_case(c, None, "sleep(0.1)", api_sleep, 5)
    add_case(c, "console", "console.now()", api_console_now, 50)
    add_case(c, "console", "console.debug('bench')", api_console_debug, 20)
    add_case(c, "notebook", "archive.get missing key", api_archive_get_missing, 50)
    add_case(c, "notebook", "archive.has missing key", api_archive_has_missing, 50)
    add_case(c, "notebook", "archive.set small dict", api_archive_set_small, 20)
    add_case(c, "notebook", "archive.get small dict", api_archive_get_small, 50)
    add_case(c, "notebook", "archive.transaction small dict", api_archive_transaction_small, 20)
    add_case(c, "notebook", "archive.keys('bench.')", api_archive_keys, 20)
    add_case(c, "notebook", "archive result .status read", api_archive_result_status, 50)
    add_case(c, "notebook", "archive.set 100-entry dict", api_archive_set_big, 10)
    add_case(c, "notebook", "archive.get 100-entry dict", api_archive_get_big, 20)
    add_case(c, "notebook", "archive.transaction 100-entry dict", api_archive_transaction_big, 10)
    add_case(c, "comms", "bus.broadcast", api_bus_broadcast, 20)
    add_case(c, "comms", "bus.latest", api_bus_latest, 50)
    add_case(c, "comms", "bus.latest_info", api_bus_latest_info, 50)
    add_case(c, "comms", "bus.send + bus.receive", api_bus_send_receive, 10)
    add_case(c, "comms", "bus.queue_size", api_bus_queue_size, 50)
    add_case(c, "comms", "bus.pending (empty)", api_bus_pending, 50)
    add_case(c, "comms", "bus.channels()", api_bus_channels, 50)
    add_case(c, "net", "outpost_network.outposts()", api_network_outposts, 20)
    add_case(c, "net", "outpost_network.home()", api_network_home, 20)
    add_case(c, "home", "home.coords()", api_home_coords, 20)
    add_case(c, "home", "home.buildings()", api_home_buildings, 10)
    add_case(c, "home", "home.buildings('storage_bin')", api_home_buildings_filtered, 10)
    add_case(c, "home", f"read .type_id over {len(env['blds'])} building refs", api_building_fields, 5)
    add_case(c, "storage", "storage_bin.count()", api_storage_count, 20)
    add_case(c, "storage", "storage_bin.fill_percent()", api_storage_fill, 20)
    add_case(c, "storage", "storage_bin.stacks()", api_storage_stacks, 20)
    add_case(c, "battery", "battery.get_level()", api_battery_level, 20)
    add_case(c, "inventory", "inventory.count()", api_inventory_count, 20)
    add_case(c, "inventory", "inventory.get_used()", api_inventory_used, 20)
    add_case(c, "inventory", "inventory.stacks()", api_inventory_stacks, 20)
    add_case(c, "power", "power_control.total()", api_power_total, 20)
    add_case(c, "power", "power_control.grids()", api_power_grids, 10)
    if env["storage"] is not None:
        add_case(c, "power", "power_control.is_powered(id)", api_power_is_powered, 20)
    add_case(c, "fleet", "fleet.vehicles()", api_fleet_vehicles, 10)
    add_case(c, "fleet", "fleet.drones()", api_fleet_drones, 10)
    add_case(c, "nocturna", "nocturna.terraform_progress()", api_nocturna_progress, 20)
    add_case(c, "nocturna", "nocturna.biome_at(0, 0)", api_nocturna_biome_at, 20)
    add_case(c, "nocturna", "nocturna.points_of_interest()", api_nocturna_poi, 10)
    add_case(c, "atmosphere", "atmosphere.get_o2()", api_atmosphere_o2, 20)
    add_case(c, "research", "research.unlocked()", api_research_unlocked, 10)
    add_case(c, "research", "research.is_unlocked(id)", api_research_is_unlocked, 20)
    add_case(c, "catalog", "item_catalog.lookup(id)", api_catalog_lookup, 20)
    add_case(c, "shop", "shop.get_catalogue()", api_shop_catalogue, 10)
    add_case(c, "orders", "orders.list_orders()", api_orders_list, 10)
    add_case(c, "journal", "journal.is_empty(0, 0)", api_journal_is_empty, 20)
    add_case(c, "journal", "journal.biomass_coords()", api_journal_biomass_coords, 10)
    return c


def cleanup_api():
    if env.get("notebook") is not None:
        res = env["notebook"].delete(BENCH_KEY)
        print(f"cleanup: archive.delete({BENCH_KEY}) -> {res.status}")
    if env.get("comms") is not None:
        res = env["comms"].clear(BENCH_CHANNEL)
        print(f"cleanup: bus.clear({BENCH_CHANNEL}) -> {res.status}")


# ---------------------------------------------------------------------------
# INTERRUPTIVE section (RUN_INTERRUPTIVE). Each case briefly changes real game state and restores it.
# Not included on purpose: inventory transfers (they wait for the feeder cycle), shop buy/sell (credits),
# vehicle/drone commands, blueprint placement, orders.
# ---------------------------------------------------------------------------


def intr_transmitter_connect(n):
    tx = env["transmitter"]
    for i in range(n):
        tx.connect("earth")


def intr_power_toggle(n):
    power = env["power"]
    mid = BENCH_POWER_MACHINE_ID
    for i in range(n):
        power.set_powered(mid, False)
        power.set_powered(mid, True)


def build_interruptive_cases():
    c = []
    env["transmitter"] = find_component("transmitter")
    if env["transmitter"] is not None:
        c.append(("transmitter.connect('earth')", intr_transmitter_connect, 5))
    env["power"] = find_component("power_control")
    if BENCH_POWER_MACHINE_ID and env["power"] is not None:
        if env["power"].can_power_off(BENCH_POWER_MACHINE_ID):
            env["power_was_on"] = env["power"].is_powered(BENCH_POWER_MACHINE_ID)
            c.append(("power_control.set_powered off+on", intr_power_toggle, 5))
        else:
            print(f"  skip power toggle: {BENCH_POWER_MACHINE_ID} cannot be powered off")
    return c


def cleanup_interruptive():
    if "power_was_on" in env:
        res = env["power"].set_powered(BENCH_POWER_MACHINE_ID, env["power_was_on"])
        print(f"cleanup: restore power of {BENCH_POWER_MACHINE_ID} -> {res.status}")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

print(f"Benchmark start, target >= {MIN_SECONDS}s per case (simulation seconds)")
n0, dt0 = time_case(bench_empty_loop, 500)
base = dt0 / n0 * 1000000.0
print(f"baseline empty loop: {base:.2f} us/iter")

if RUN_LOCAL:
    rows = run_group("LOCAL", CASES)
    report("LOCAL", rows, base)

if RUN_API:
    try:
        setup_api()
        rows = run_group("API (non-interruptive)", build_api_cases())
        report("API", rows, base)
    finally:
        cleanup_api()

if RUN_INTERRUPTIVE:
    print("INTERRUPTIVE cases enabled: game state is changed briefly and restored")
    try:
        icases = build_interruptive_cases()
        if icases:
            rows = run_group("INTERRUPTIVE", icases)
            report("INTERRUPTIVE", rows, base)
        else:
            print("no interruptive case available (set the BENCH_* constants)")
    finally:
        cleanup_interruptive()

print("Benchmark done")
