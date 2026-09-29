# Interpreter benchmark: pure local computation, no game side effects.
# Run in a control_panel script slot: the Playground aborts long runs. Results and reading: docs/BENCHMARK.md.
# range(n) materialises a list (item limit applies), so each case runs a small fixed chunk per call
# and the number of calls doubles until one timed run lasts >= MIN_SECONDS of simulation time.

clock = get_component("clock")
MIN_SECONDS = 2.0
MAX_REPS = 20000

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


print(f"Benchmark start, target >= {MIN_SECONDS}s per case (simulation seconds)")
results = []
for name, fn, chunk in CASES:
    n, dt = time_case(fn, chunk)
    per_us = dt / n * 1000000.0
    results.append((name, n, dt, per_us))
    print(f"{name}: n={n} dt={dt:.2f}s -> {per_us:.2f} us/iter")

base = results[0][3]
if base > 0:
    print("--- relative to empty loop iteration ---")
    for name, n, dt, per_us in results:
        print(f"{name}: {per_us / base:.1f}x")
print("Benchmark done")
