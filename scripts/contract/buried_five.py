# Buried Five Contract Solver
# Collapses layered five-fold wrapped tokens into original transmission using the recovered Analyzer.

c = self.contract
print(f"Contract: {c.name} ({c.id}), Reward: {c.reward} credits")

if c.status == "completed":
    print("Contract already marked completed.")

tokens = list(c.transmission)
analyzer = c.analyzer
layers = c.layers

print(f"Starting decode: {len(tokens)} tokens across {layers} layer(s)")

success = True
for layer_idx in range(layers):
    if len(tokens) % 5 != 0:
        print(f"Error: Token count {len(tokens)} not divisible by 5 at layer {layer_idx + 1}")
        success = False
        break

    next_tokens: list[str] = []
    try:
        for i in range(0, len(tokens), 5):
            group = tokens[i : i + 5]
            collapsed = analyzer.read(group)
            next_tokens.append(collapsed)
    except (ValueError, TypeError) as err:
        print(f"Decode error at layer {layer_idx + 1}: {err}")
        success = False
        break

    tokens = next_tokens
    print(f"Layer {layer_idx + 1}/{layers} collapsed: {len(tokens)} tokens remaining")

if not success:
    print("Decoding aborted due to errors.")
else:
    message = "".join(tokens)
    print(f"Decoded message ({len(message)} chars): '{message}'")

    transmitter = get_component("transmitter")
    if not transmitter:
        print("[BURIED_FIVE] No Transmitter found!")
    else:
        link = transmitter.connect("earth")
        if link.status != "ok":
            print(f"Transmitter connection failed: {link.status} - {link.message}")
        else:
            tx_res = transmitter.transmit(c.id, message)
            print("Transmission status:", tx_res.status, "-", tx_res.message)
