from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import three_echoes as self

broadcast = self.contract.broadcast
print(broadcast.freq_a)
print(broadcast.freq_b)
print(broadcast.freq_c)
subject = []
i = 0
for letter in broadcast.freq_a:
    subject.append(letter)
    try:
        subject.append(broadcast.freq_b[i])
        subject.append(broadcast.freq_c[i])
        i+=1
    except IndexError:
        # freq_b/freq_c shorter than freq_a: nothing left to interleave.
        continue
print(subject)
transmitter = get_component("transmitter")
if not transmitter:
    print("[THREE_ECHOES] No Transmitter found!")
else:
    transmitter.connect("earth")
    transmitter.transmit(self.contract.id, "".join(subject))