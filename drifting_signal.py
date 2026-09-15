device = self.contract.device
text = device.slabs
transmitter = get_component("transmitter")
transmitter.connect("earth")

for shift in range(0,27):
    
    result = []
    shift = shift % 26  # normalize
    
    for ch in text:
        if "a" <= ch <= "z":
            base = ord("a")
            result.append(chr((ord(ch) - base - shift) % 26 + base))
        elif "A" <= ch <= "Z":
            base = ord("A")
            result.append(chr((ord(ch) - base - shift) % 26 + base))
        else:
            result.append(ch)  # keep spaces, punctuation, etc.
    
    transmitter.transmit(self.contract.id, "".join(result))