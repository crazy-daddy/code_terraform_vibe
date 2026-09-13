# Alien Terminal Breach Contract Solver
# Mastermind solver for 15 digits (values 1 to 5).
# Strategy:
# 1. Start with a baseline guess: [1]*15.
# 2. Query baseline and get base_correct.
# 3. If base_correct == 15, we're done!
# 4. Iterate over each index i from 0 to 14:
#    Test digits d in [2, 3, 4, 5]:
#      Make a candidate code with code[i] = d and all other positions matching current known code.
#      If candidate.correct == current_correct + 1:
#        code[i] = d, current_correct += 1, found!
#      If candidate.correct == current_correct - 1:
#        We know code[i] was definitely 1 (the original value at index i).
#        No need to test remaining digits for index i!
# 5. Transmit the cracked 15-digit code list to Earth.

c = self.contract
terminal = c.terminal
length = terminal.length

print(f"Contract: {c.name} ({c.id}), Length: {length}")

# Initial baseline
code = [1] * length
res = terminal.guess(code)
current_correct = res.correct
print(f"Baseline guess [1]*{length} -> correct: {current_correct}, misplaced: {res.misplaced}")

if current_correct < length:
    for i in range(length):
        if current_correct == length:
            break
        # Test alternatives for position i
        found_digit = False
        for d in [2, 3, 4, 5]:
            test_code = list(code)
            test_code[i] = d
            res = terminal.guess(test_code)
            
            if res.correct == current_correct + 1:
                code[i] = d
                current_correct = res.correct
                found_digit = True
                print(f"Position {i} confirmed as {d} (total correct: {current_correct}/{length})")
                break
            elif res.correct == current_correct - 1:
                # Changing position i from 1 to d reduced correct count, so position i MUST be 1!
                found_digit = True
                print(f"Position {i} confirmed as 1 (reduced score on change)")
                break
        
        if not found_digit:
            # If none of 2,3,4,5 increased score and none decreased it, position i must be 1.
            print(f"Position {i} remains 1")

print(f"Final cracked passcode: {code}")

transmitter = get_component("transmitter")
transmitter.connect("earth")
t_res = transmitter.transmit(c.id, code)
print("Transmission status:", t_res.status, "-", t_res.message)