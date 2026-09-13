# Xenogenetics Survey Contract Solver
c = self.contract

# 1. Store known Earth sequences in a set for O(1) membership check
earth_set = set(c.earth_ref)

# 2. Extract all samples that are NOT found in the Earth reference set
alien_list = [sample for sample in c.samples if sample not in earth_set]

print(f"Total samples: {len(c.samples)}, Earth refs: {len(earth_set)}, Alien samples found: {len(alien_list)}")

# 3. Transmit the alien_list to Earth
transmitter = get_component("transmitter")
transmitter.connect("earth")
res = transmitter.transmit(c.id, alien_list)
print("Transmit result:", res.status, "-", res.message)
