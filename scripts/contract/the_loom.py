# The Loom Contract Solver
# Probes the alien loom with known markers to determine braid permutation,
# un-weaves the 42-character record into two threads, and transmits the message to Earth.

c = self.contract
print(f"Contract: {c.name} ({c.id}), Reward: {c.reward} credits")

if c.status == "completed":
    print("Contract already marked completed.")

loom = c.loom
record = c.record
total_len = len(record)
half = total_len // 2

print(f"Record length: {total_len} chars (expecting 2x {half} char threads)")

# Probe permutation with unique ASCII characters
thread_a = "".join(chr(65 + i) for i in range(half))
thread_b = "".join(chr(65 + half + i) for i in range(half))
joined = thread_a + thread_b

woven = loom.weave(thread_a, thread_b)
print(f"Loom probe complete: braided {len(thread_a)}+{len(thread_b)} -> {len(woven)} chars")

# Reconstruct un-woven record: woven[j] came from joined.index(woven[j])
unwoven = [""] * total_len
for j, ch in enumerate(woven):
    orig_idx = joined.index(ch)
    unwoven[orig_idx] = record[j]

unwoven_str = "".join(unwoven)
thread1 = unwoven_str[:half]
thread2 = unwoven_str[half:]

print(f"Candidate Thread 1: '{thread1}'")
print(f"Candidate Thread 2: '{thread2}'")

transmitter = get_component("transmitter")
if not transmitter:
    print("[THE_LOOM] No Transmitter found!")
else:
    link = transmitter.connect("earth")
    if link.status != "ok":
        print(f"Transmitter connection failed: {link.status} - {link.message}")
    else:
        # One thread is the decoded message; transmit candidate thread 1 first
        print(f"Submitting thread 1: '{thread1}'")
        res = transmitter.transmit(c.id, thread1)
        print("Transmission status (thread 1):", res.status, "-", res.message)

        if res.status not in ("correct", "already_completed_correct"):
            print(f"Thread 1 rejected. Submitting thread 2: '{thread2}'")
            res2 = transmitter.transmit(c.id, thread2)
            print("Transmission status (thread 2):", res2.status, "-", res2.message)