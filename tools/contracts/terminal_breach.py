# Alien Terminal Breach Contract Solver (Mastermind solver)
c = self.contract
terminal = c.terminal
length = terminal.length

code = [1] * length
res = terminal.guess(code)
current_correct = res.correct

if current_correct < length:
    for i in range(length):
        if current_correct == length:
            break
        found_digit = False
        for d in [2, 3, 4, 5]:
            test_code = list(code)
            test_code[i] = d
            res = terminal.guess(test_code)
            if res.correct == current_correct + 1:
                code[i] = d
                current_correct = res.correct
                found_digit = True
                break
            elif res.correct == current_correct - 1:
                found_digit = True
                break
        if not found_digit:
            code[i] = 1

transmitter = get_component("transmitter")
transmitter.connect("earth")
t_res = transmitter.transmit(c.id, code)
print(f"Terminal Breach result: {t_res.status} - {t_res.message}")

