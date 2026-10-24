# Plant Terraformer shared keys, tunables and Plants ladder math, used by
# lib/plant_terraformer.py, its mixins (plant_terraformer_water.py,
# plant_terraformer_demand.py), lib/plants_retire.py, lib/pump_salt.py,
# lib/harvester_machines.py and devtools/simulation/plants_wildlife_timeline.py.

from components import sensor_value

STATUS_KEY = "plant.terraformer"
REQUESTER_ID = "plant_terraformer"

# Statuses where the machine can't use power at all: switched off.
STOP_STATUSES = ("complete", "needs_mk2")

# Growth Accelerant / each Fertilizer tier: onboard holder cap. The Salt
# holder fits a full batch's need (Mk II: 14).
SUPPORT_HOLDER_CAP = 10

# Fertilizer item ids, best potency first (fertilizer_potency(): 50/30/10).
FERTILIZER_ITEM_IDS = ("fertilizer_mk3", "fertilizer_mk2", "fertilizer")

# Salt / Growth Accelerant / Fertilizer staged at the outpost, in batches'
# worth (Mk I full batch: 3 Salt; Mk II: 14 Salt, 27 potency, 1
# Accelerant; Fertilizer/Accelerant capped by the holder), so several
# batches are on hand while a hauler brings more in one load.
SUPPORT_REQUEST_BATCHES = 10

# Plants ladder (plant_terraformer_guide.md): phase -> (km² per Forage, band
# Forage). Phase 6 is Continental complete.
PLANTS_BANDS = {1: (20.0, 25000), 2: (5.0, 150000), 3: (5.0 / 3, 600000), 4: (1.0, 1250000), 5: (1.0 / 3, 4500000)}
# Forage in one full Mk II batch (Growth Accelerant: 1 item per batch).
TERRAFORMER_MK2_BATCH = 6600


def plants_band_edges():
    """[(phase, from km², to km², km² per Forage)] of PLANTS_BANDS, in ladder order."""
    edges, low = [], 0.0
    for phase in sorted(PLANTS_BANDS):
        rate, band_forage = PLANTS_BANDS[phase]
        high = low + rate * band_forage
        edges.append((phase, low, high, rate))
        low = high
    return edges


def plants_km2():
    """Permanent Plants km² from the Plants Sensor, or None when there is none."""
    return sensor_value("plants_sensor", "plant_terraformer_common.plants_km2: get_component")


def ceil_int(value):
    whole = int(value)
    return whole + 1 if value > whole else whole


def remaining_forage(phase, remaining_km2, from_phase=1):
    """Forage still to convert from phase `from_phase` on: the rest of the current band plus every later band."""
    total = 0.0
    if phase in PLANTS_BANDS and phase >= from_phase:
        total += max(remaining_km2, 0.0) / PLANTS_BANDS[phase][0]
    for band_phase, (_, band_forage) in PLANTS_BANDS.items():
        if band_phase > phase and band_phase >= from_phase:
            total += band_forage
    return total
