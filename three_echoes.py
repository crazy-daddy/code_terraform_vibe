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
    except:
        continue
print(subject)
transmitter = get_component("transmitter")
transmitter.connect("earth")
transmitter.transmit(self.contract.id, "".join(subject))