# Beat The System Contract Solver
# Plays a forced win against the Arbiter by searching every random tie-break it could make, 50 times in a row.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import beat_the_system as self

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
CORNERS = [0, 2, 6, 8]
EDGES = [1, 3, 5, 7]
YOU = "you"
ARB = "arbiter"


def has_line(board, who):
    for a, b, c in LINES:
        if board[a] == who and board[b] == who and board[c] == who:
            return True
    return False


def completing_cells(board, who):
    cells = []
    for a, b, c in LINES:
        trio = [a, b, c]
        marks = [board[k] for k in trio]
        if marks.count(who) == 2 and marks.count("") == 1:
            cells.append(trio[marks.index("")])
    return cells


def arbiter_choices(board):
    """Every cell the Arbiter may pick: win, else block, else centre, corner, edge."""
    wins = completing_cells(board, ARB)
    if wins:
        return wins
    blocks = completing_cells(board, YOU)
    if blocks:
        return blocks
    if board[4] == "":
        return [4]
    corners = [k for k in CORNERS if board[k] == ""]
    if corners:
        return corners
    return [k for k in EDGES if board[k] == ""]


forced_cache = {}


def forced_move(board):
    """Cell that wins against every possible Arbiter reply, or None."""
    key = tuple(board)
    if key in forced_cache:
        return forced_cache[key]
    answer = None
    for m in range(9):
        if board[m] != "":
            continue
        nb = list(board)
        nb[m] = YOU
        if has_line(nb, YOU):
            answer = m
            break
        if "" not in nb:
            continue
        good = True
        for r in arbiter_choices(nb):
            rb = list(nb)
            rb[r] = ARB
            if has_line(rb, ARB) or "" not in rb or forced_move(rb) is None:
                good = False
                break
        if good:
            answer = m
            break
    forced_cache[key] = answer
    return answer


c = self.contract
if c.status == "completed":
    print(f"Contract {c.name} ({c.id}) already completed; skipping.")
else:
    print(f"Contract: {c.name} ({c.id}), Reward: {c.reward} credits")

    arbiter = c.arbiter
    target = arbiter.target()
    print(f"Goal: {target} wins in a row")

    if forced_move([""] * 9) is None:
        print("No forced win exists from the empty board; aborting.")
    else:
        games = 0
        max_games = target * 4
        while arbiter.streak() < target and games < max_games:
            started = arbiter.new_game()
            if started.status != "ok":
                print(f"new_game: {started.status} - {started.message}")
                continue
            games += 1
            outcome = "ongoing"
            while outcome == "ongoing":
                board = list(arbiter.board())
                move = forced_move(board)
                if move is None:
                    empties = [k for k in range(9) if board[k] == ""]
                    move = empties[0]
                    print(f"Game {games}: no forced win from {board}, improvising cell {move}")
                turn = arbiter.play(move)
                outcome = turn.status
                if outcome not in ("ongoing", "win", "loss", "draw"):
                    print(f"Game {games}: play({move}) -> {outcome} - {turn.message}")
                    break
            if outcome != "win":
                print(f"Game {games}: {outcome}, streak reset")
            elif games % 10 == 0:
                print(f"Game {games}: streak {arbiter.streak()}/{target}")

        print(f"Streak {arbiter.streak()}/{target} after {games} games")
        if arbiter.streak() >= target:
            transmitter = get_component("transmitter")
            if not transmitter:
                print("[BEAT_THE_SYSTEM] No Transmitter found!")
            else:
                link = transmitter.connect("earth")
                if link.status != "ok":
                    print(f"Transmitter connection failed: {link.status} - {link.message}")
                else:
                    tx_res = transmitter.transmit(c.id, arbiter.token())
                    print("Transmission status:", tx_res.status, "-", tx_res.message)
        else:
            print("Target streak not reached; token not transmitted.")
