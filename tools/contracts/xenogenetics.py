# Xenogenetics Survey Contract Solver
c = self.contract
earth_set = set(c.earth_ref)
alien_list = [sample for sample in c.samples if sample not in earth_set]

transmitter = get_component("transmitter")
transmitter.connect("earth")
res = transmitter.transmit(c.id, alien_list)
print(f"Xenogenetics result: {res.status} - {res.message}")

