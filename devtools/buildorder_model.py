"""Surrogate model for the early-game build-order search (docs/plans/buildorder_search.md).

Terraform Index (TP) as the simworker computes it: a pure function of the current pillar
values, summed over pillars, each a piecewise-linear curve over its phase thresholds. The
values here mirror the simworker's phase table and per-phase weights (search the decompiled
worker for `const Rv = 1000000`); they are game constants, not tuning.

The generator rates are the base rates at 100% efficiency, Mk I (BK / VK / HK in the worker).
The search uses the effective rates measured by headless calibration runs instead
(EFFECTIVE_RATE, filled from devtools/headless runs).
"""

TP_CAP = 1_000_000

# Pillar -> phase thresholds (start of phase 1, then each phase's upper end).
PHASES = {
    "heat": (0, 11, 140, 3200, 42000, 360000),
    "o2": (0, 10, 150, 3000, 40000, 380000),
    "pressure": (0, 0.3, 7, 150, 2000, 19000),
}
# TP per full phase. Heat, O2 and pressure share 136k..144k per phase, split three ways;
# the biosphere pillars (biomass, plants, wildlife) get 20k per phase (not modeled here).
ATMO_PHASE_TP = tuple(v / 3 for v in (136_000, 138_000, 140_000, 142_000, 144_000))

# Pillar units per second per generator, 100% efficiency, Mk I.
BASE_RATE = {"o2": 0.0004, "heat": 0.00042, "pressure": 0.004 / 200}
GENERATOR = {"o2": "oxygen_generator", "heat": "temp_heater", "pressure": "pressure_generator"}


def pillar_tp(pillar, value):
    """TP that one atmospheric pillar contributes at `value`."""
    t = PHASES[pillar]
    tp = 0.0
    for i, weight in enumerate(ATMO_PHASE_TP):
        lo, hi = t[i], t[i + 1]
        if value >= hi:
            tp += weight
            continue
        if value > lo:
            tp += weight * (value - lo) / (hi - lo)
        break
    return tp


def terraform_index(o2=0.0, pressure=0.0, heat=0.0, other=0.0):
    """Total TP for the three atmospheric pillars plus `other` (biosphere pillars)."""
    return min(TP_CAP, pillar_tp("o2", o2) + pillar_tp("pressure", pressure) + pillar_tp("heat", heat) + other)


def marginal_tp(pillar, value):
    """TP per pillar unit at `value` (the slope of its current phase)."""
    t = PHASES[pillar]
    for i, weight in enumerate(ATMO_PHASE_TP):
        if value < t[i + 1]:
            return weight / (t[i + 1] - t[i])
    return 0.0
