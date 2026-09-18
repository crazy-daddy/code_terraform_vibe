
# ============================================================
# HELPERS
# ============================================================

def _has(obj, name):
    try:
        getattr(obj, name)
        return True
    except Exception:
        return False


def _status(result):
    try:
        return str(result.status)
    except Exception:
        return ""


def _message(result):
    try:
        return str(result.message)
    except Exception:
        return ""


# ============================================================
# THE BURIED 5
# ============================================================

def solve_buried_5(contract):
    analyzer = contract.analyzer
    data = list(contract.transmission)
    layers = int(contract.layers)

    for layer in range(layers):
        if len(data) % 5 != 0:
            raise ValueError(
                "Buried 5 layer "
                + str(layer + 1)
                + " length is not divisible by 5: "
                + str(len(data))
            )

        decoded = []

        for i in range(0, len(data), 5):
            group = data[i:i + 5]
            decoded.append(
                analyzer.read(group)
            )

        data = decoded

    answer = "".join(data)

    if answer == "":
        raise ValueError(
            "Buried 5 recovered an empty message."
        )

    return answer


# ============================================================
# THE LOOM
# ============================================================

def solve_loom(contract):
    loom = contract.loom
    record = str(contract.record)

    if len(record) % 2 != 0:
        raise ValueError(
            "Loom record does not contain two equal threads."
        )

    thread_length = len(record) // 2

    left = [""] * thread_length
    right = [""] * thread_length

    record_pos = 0
    left_consumed = 0
    right_consumed = 0
    chunk_size = 1

    while (
        left_consumed < thread_length
        or right_consumed < thread_length
    ):
        left_count = min(
            chunk_size,
            thread_length - left_consumed
        )

        for offset in range(left_count):
            left[
                left_consumed + offset
            ] = record[record_pos]

            record_pos += 1

        left_consumed += left_count

        right_count = min(
            chunk_size,
            thread_length - right_consumed
        )

        right_end = (
            thread_length - right_consumed
        )

        for offset in range(right_count):
            original_pos = (
                right_end - 1 - offset
            )

            right[
                original_pos
            ] = record[record_pos]

            record_pos += 1

        right_consumed += right_count
        chunk_size += 1

    thread_a = "".join(left)
    thread_b = "".join(right)

    # The inverse must reproduce the original record.
    if loom.weave(
        thread_a,
        thread_b
    ) != record:
        raise ValueError(
            "Loom inverse verification failed."
        )

    # One thread is readable English; the other is carrier filler.
    common = (
        "THE",
        "THIS",
        "THAT",
        "HAVE",
        "NEVER",
        "BEEN",
        "WITH",
        "FROM",
        "INTO",
        "ONE",
        "TWO",
        "AND",
        "ING",
        "ION"
    )

    def readability(text):
        upper = text.upper()
        score = 0

        for token in common:
            score += (
                upper.count(token)
                * len(token)
                * len(token)
            )

        for ch in upper:
            if ch in "AEIOU":
                score += 1

        return score

    score_a = readability(thread_a)
    score_b = readability(thread_b)

    print(
        "[CONTRACT SOLVER] Loom thread A:",
        thread_a,
        "score=",
        score_a
    )

    print(
        "[CONTRACT SOLVER] Loom thread B:",
        thread_b,
        "score=",
        score_b
    )

    if score_a == score_b:
        raise ValueError(
            "Loom message/carrier distinction is ambiguous."
        )

    if score_a > score_b:
        return thread_a

    return thread_b


# ============================================================
# CROSSTALK
# ============================================================

def solve_crosstalk(contract):
    def real_bits(signal, min_length):
        bits = []

        radius_required = (
            int(min_length) - 1
        ) // 2

        for i, ch in enumerate(signal):
            if ch not in ("0", "1"):
                continue

            radius = 0

            while (
                i - radius - 1 >= 0
                and i + radius + 1 < len(signal)
                and signal[i - radius - 1]
                == signal[i + radius + 1]
            ):
                radius += 1

            if radius >= radius_required:
                bits.append(ch)

        return bits

    x = real_bits(
        contract.input_x,
        contract.min_length
    )

    y = real_bits(
        contract.input_y,
        contract.min_length
    )

    if len(x) != len(y):
        raise ValueError(
            "Crosstalk streams differ in length: "
            + str(len(x))
            + " vs "
            + str(len(y))
        )

    result = []

    for xb, yb in zip(x, y):
        if xb != yb:
            result.append("1")
        else:
            result.append("0")

    if len(result) % 5 != 0:
        raise ValueError(
            "Crosstalk result length is not divisible by 5."
        )

    letters = []

    for i in range(0, len(result), 5):
        group = "".join(
            result[i:i + 5]
        )

        value = int(group, 2)

        if value < 1 or value > 26:
            raise ValueError(
                "Crosstalk invalid letter value "
                + str(value)
                + " from "
                + group
            )

        letters.append(
            chr(
                ord("A")
                + value
                - 1
            )
        )

    return "".join(letters)


# ============================================================
# RELAY HACK
# ============================================================

def solve_relay_hack(contract):
    lock = contract.lock

    candidate = [
        0,
        0,
        0,
        0,
        0,
        0
    ]

    unresolved = list(
        range(len(candidate))
    )

    for value in range(100):
        for i in unresolved:
            candidate[i] = value

        feedback = lock.intercept(
            candidate
        )

        unresolved = [
            i
            for i in unresolved
            if not feedback[i]
        ]

        if not unresolved:
            break

    if unresolved:
        raise ValueError(
            "Relay Hack left unresolved tumblers: "
            + str(unresolved)
        )

    return candidate


# ============================================================
# XENOGENETICS
# ============================================================

def solve_xenogenetics(contract):
    earth_set = set(
        contract.earth_ref
    )

    alien_list = [
        sample
        for sample in contract.samples
        if sample not in earth_set
    ]

    return alien_list


# ============================================================
# CORRUPTED ARCHIVE
# ============================================================

def solve_corrupted_archive(contract):
    archive = contract.archive

    seen = {}
    pairs = []

    for row in range(archive.rows):
        for col in range(archive.cols):
            word = archive.flip(
                row,
                col
            )

            if word in seen:
                first_row, first_col = seen[word]

                pairs.append([
                    first_row,
                    first_col,
                    row,
                    col
                ])

            else:
                seen[word] = (
                    row,
                    col
                )

    if len(pairs) != 50:
        raise ValueError(
            "Corrupted Archive expected 50 pairs, got "
            + str(len(pairs))
        )

    return pairs


# ============================================================
# DATA TABLET
# ============================================================

def solve_data_tablet(contract):
    tablet = contract.tablet
    message_chars = []

    for row in range(tablet.rows):
        for col in range(tablet.cols):
            result = tablet.probe(
                row,
                col
            )

            if result.distance == 0:
                message_chars.append(
                    result.char
                )

    message = "".join(
        message_chars
    )

    if message == "":
        raise ValueError(
            "Data Tablet recovered an empty message."
        )

    return message


# ============================================================
# TERMINAL BREACH
# ============================================================

def solve_terminal_breach(contract):
    terminal = contract.terminal
    length = int(terminal.length)

    baseline_guess = [1] * length

    baseline_result = terminal.guess(
        baseline_guess
    )

    baseline_correct = int(
        baseline_result.correct
    )

    code = [None] * length

    for pos in range(length):
        test = [1] * length
        test[pos] = 2

        result = terminal.guess(
            test
        )

        delta = (
            int(result.correct)
            - baseline_correct
        )

        if delta == -1:
            code[pos] = 1
            continue

        if delta == 1:
            code[pos] = 2
            continue

        for digit in (
            3,
            4,
            5
        ):
            test = [1] * length
            test[pos] = digit

            result = terminal.guess(
                test
            )

            if (
                int(result.correct)
                == baseline_correct + 1
            ):
                code[pos] = digit
                break

        if code[pos] is None:
            raise ValueError(
                "Terminal Breach could not resolve position "
                + str(pos)
            )

    verify = terminal.guess(
        code
    )

    if int(verify.correct) != length:
        raise ValueError(
            "Terminal Breach verification failed."
        )

    return code


# ============================================================
# SEALED VAULT
# ============================================================

def solve_sealed_vault(contract):
    vault = contract.vault

    directions = (
        (
            "north",
            -1,
            0,
            "south"
        ),
        (
            "east",
            0,
            1,
            "west"
        ),
        (
            "south",
            1,
            0,
            "north"
        ),
        (
            "west",
            0,
            -1,
            "east"
        )
    )

    visited = set()

    def position():
        p = vault.position

        return (
            int(p.row),
            int(p.col)
        )

    def inside(row, col):
        size = int(vault.size)

        return (
            0 <= row < size
            and 0 <= col < size
        )

    def search():
        row, col = position()

        visited.add(
            (
                row,
                col
            )
        )

        size = int(vault.size)

        if (
            row == size - 1
            and col == size - 1
        ):
            return True

        for (
            direction,
            dr,
            dc,
            reverse
        ) in directions:

            next_row = row + dr
            next_col = col + dc

            if not inside(
                next_row,
                next_col
            ):
                continue

            if (
                next_row,
                next_col
            ) in visited:
                continue

            result = vault.move(
                direction
            )

            status = _status(result)

            if status == "wall":
                continue

            if status == "exit":
                return True

            if status != "path":
                continue

            if search():
                return True

            back = vault.move(
                reverse
            )

            back_status = _status(
                back
            )

            if back_status not in (
                "path",
                "exit"
            ):
                raise ValueError(
                    "Sealed Vault backtrack failed: "
                    + back_status
                )

        return False

    if not search():
        raise ValueError(
            "Sealed Vault found no route to exit."
        )

    escape = vault.escape()

    if _status(escape) != "ok":
        raise ValueError(
            "Sealed Vault escape failed: "
            + _status(escape)
            + " "
            + _message(escape)
        )

    return escape.key


# ============================================================
# SHIFTING SLABS
# ============================================================

def solve_shifting_slabs(contract):
    slabs = contract.device.slabs
    current = "".join(slabs)

    common = (
        " THE ",
        " HAVE ",
        " NEVER ",
        " BEEN ",
        " ALONE ",
        " OUT ",
        " HERE ",
        " THIS ",
        " THAT ",
        " WITH ",
        " FROM ",
        " AND ",
        " WE ",
        " TO ",
        " OF ",
        " IN "
    )

    best_message = None
    best_score = -1

    for offset in range(26):
        chars = []

        for ch in current:
            if "A" <= ch <= "Z":
                value = (
                    ord(ch)
                    - ord("A")
                )

                original = (
                    value - offset
                ) % 26

                chars.append(
                    chr(
                        ord("A")
                        + original
                    )
                )

            elif "a" <= ch <= "z":
                value = (
                    ord(ch)
                    - ord("a")
                )

                original = (
                    value - offset
                ) % 26

                chars.append(
                    chr(
                        ord("a")
                        + original
                    )
                )

            else:
                chars.append(ch)

        candidate = "".join(
            chars
        )

        padded = (
            " "
            + candidate.upper()
            + " "
        )

        score = 0

        for token in common:
            score += (
                padded.count(token)
                * len(token)
                * len(token)
            )

        if score > best_score:
            best_score = score
            best_message = candidate

    if best_message is None:
        raise ValueError(
            "Shifting Slabs could not recover a message."
        )

    return best_message


# ============================================================
# THREE ECHOS
# ============================================================

def solve_three_echos(contract):
    broadcast = contract.broadcast

    a = str(broadcast.freq_a)
    b = str(broadcast.freq_b)
    c = str(broadcast.freq_c)

    parts = []

    max_len = max(
        len(a),
        len(b),
        len(c)
    )

    for i in range(max_len):
        if i < len(a):
            parts.append(a[i])

        if i < len(b):
            parts.append(b[i])

        if i < len(c):
            parts.append(c[i])

    return "".join(
        parts
    ).lower()


# ============================================================
# COLD BOOT
# ============================================================

def solve_cold_boot(contract):
    memory = list(
        contract.program
    )

    ip = 0
    outputs = []

    def read_param(
        offset,
        mode
    ):
        value = memory[
            ip + offset
        ]

        if mode == 0:
            return memory[value]

        if mode == 1:
            return value

        raise ValueError(
            "Cold Boot unknown parameter mode: "
            + str(mode)
        )

    while True:
        instruction = memory[ip]

        opcode = (
            instruction % 100
        )

        mode1 = (
            instruction // 100
        ) % 10

        mode2 = (
            instruction // 1000
        ) % 10

        if opcode == 99:
            break

        if opcode == 1:
            a = read_param(
                1,
                mode1
            )

            b = read_param(
                2,
                mode2
            )

            dest = memory[
                ip + 3
            ]

            memory[dest] = a + b
            ip += 4
            continue

        if opcode == 2:
            a = read_param(
                1,
                mode1
            )

            b = read_param(
                2,
                mode2
            )

            dest = memory[
                ip + 3
            ]

            memory[dest] = a * b
            ip += 4
            continue

        if opcode == 4:
            value = read_param(
                1,
                mode1
            )

            outputs.append(
                value
            )

            ip += 2
            continue

        if opcode == 5:
            condition = read_param(
                1,
                mode1
            )

            target = read_param(
                2,
                mode2
            )

            if condition != 0:
                ip = target
            else:
                ip += 3

            continue

        raise ValueError(
            "Cold Boot unknown opcode "
            + str(opcode)
            + " at ip "
            + str(ip)
        )

    message_chars = []

    for value in outputs:
        if value < 1 or value > 26:
            raise ValueError(
                "Cold Boot output outside letter range: "
                + str(value)
            )

        message_chars.append(
            chr(
                ord("A")
                + value
                - 1
            )
        )

    message = "".join(
        message_chars
    )

    if message == "":
        raise ValueError(
            "Cold Boot produced no message."
        )

    return message


# ============================================================
# CONTRACT IDENTIFICATION
# ============================================================

def identify_contract(contract):
    # Use combinations of distinctive contract fields rather
    # than relying on an undocumented contract.type property.

    if (
        _has(contract, "analyzer")
        and _has(contract, "transmission")
        and _has(contract, "layers")
    ):
        return (
            "buried_5",
            solve_buried_5
        )

    if (
        _has(contract, "loom")
        and _has(contract, "record")
    ):
        return (
            "loom",
            solve_loom
        )

    if (
        _has(contract, "input_x")
        and _has(contract, "input_y")
        and _has(contract, "min_length")
    ):
        return (
            "crosstalk",
            solve_crosstalk
        )

    if _has(
        contract,
        "lock"
    ):
        return (
            "relay_hack",
            solve_relay_hack
        )

    if (
        _has(contract, "earth_ref")
        and _has(contract, "samples")
    ):
        return (
            "xenogenetics",
            solve_xenogenetics
        )

    if _has(
        contract,
        "archive"
    ):
        return (
            "corrupted_archive",
            solve_corrupted_archive
        )

    if _has(
        contract,
        "tablet"
    ):
        return (
            "data_tablet",
            solve_data_tablet
        )

    if _has(
        contract,
        "terminal"
    ):
        return (
            "terminal_breach",
            solve_terminal_breach
        )

    if _has(
        contract,
        "vault"
    ):
        return (
            "sealed_vault",
            solve_sealed_vault
        )

    if _has(
        contract,
        "device"
    ):
        return (
            "shifting_slabs",
            solve_shifting_slabs
        )

    if _has(
        contract,
        "broadcast"
    ):
        return (
            "three_echos",
            solve_three_echos
        )

    if _has(
        contract,
        "program"
    ):
        return (
            "cold_boot",
            solve_cold_boot
        )

    raise ValueError(
        "Unsupported contract API. "
        + "No known solver matched contract "
        + str(contract.id)
    )


# ============================================================
# CENTRAL RUNNER / TRANSMITTER
# ============================================================

def run(contract):
    print(
        "[CONTRACT SOLVER] Shared library VERSION "
        + SCRIPT_VERSION
    )

    contract_name, solver = identify_contract(
        contract
    )

    print(
        "[CONTRACT SOLVER] Detected: "
        + contract_name
        + " id="
        + str(contract.id)
    )

    answer = solver(
        contract
    )

    print(
        "[CONTRACT SOLVER] Recovered answer:",
        answer
    )

    transmitter = get_component(
        "transmitter"
    )

    connection = transmitter.connect(
        "earth"
    )

    connection_status = _status(
        connection
    )

    if connection_status != "ok":
        raise ValueError(
            "Earth connection failed: "
            + connection_status
            + " "
            + _message(connection)
        )

    result = transmitter.transmit(
        contract.id,
        answer
    )

    print(
        "[CONTRACT SOLVER] "
        + contract_name
        + " transmit="
        + _status(result)
        + " "
        + _message(result)
    )

    return result
