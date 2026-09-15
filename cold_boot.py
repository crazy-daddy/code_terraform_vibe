# Cold Boot Contract Solver
# Runs the recovered program as a tiny stack-free VM (Intcode-style):
# opcode = last two digits, parameter modes = the digits before that
# (0 = position/address mode, 1 = immediate mode), read left-to-right for
# param 1, param 2. Write destinations are always direct addresses.

c = self.contract
program = c.program
memory = list(program)  # the VM writes back into memory as it runs

print(f"Contract: {c.name} ({c.id}), program length: {len(memory)}")


def read_param(mode, value):
    return value if mode == 1 else memory[value]


ip = 0
outputs = []

while True:
    instruction = memory[ip]
    opcode = instruction % 100
    mode1 = (instruction // 100) % 10
    mode2 = (instruction // 1000) % 10

    if opcode == 99:
        break

    elif opcode == 1:  # add
        a = read_param(mode1, memory[ip + 1])
        b = read_param(mode2, memory[ip + 2])
        dest = memory[ip + 3]
        memory[dest] = a + b
        ip += 4

    elif opcode == 2:  # multiply
        a = read_param(mode1, memory[ip + 1])
        b = read_param(mode2, memory[ip + 2])
        dest = memory[ip + 3]
        memory[dest] = a * b
        ip += 4

    elif opcode == 4:  # output
        a = read_param(mode1, memory[ip + 1])
        outputs.append(a)
        ip += 2

    elif opcode == 5:  # jump-if-true
        a = read_param(mode1, memory[ip + 1])
        b = read_param(mode2, memory[ip + 2])
        ip = b if a != 0 else ip + 3

    else:
        print(f"Unknown opcode {opcode} at ip={ip}. Halting.")
        break

message = "".join(chr(ord("A") + n - 1) for n in outputs)
print(f"Raw outputs: {outputs}")
print(f"Decoded message: {message}")

transmitter = get_component("transmitter")
transmitter.connect("earth")
t_res = transmitter.transmit(c.id, message)
print("Transmission status:", t_res.status, "-", t_res.message)
