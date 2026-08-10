"""s3_loads: aggregate EnergyPlus 8760h outputs into ASHRAE three-pulse loads.

Public API
----------
compute_pulses(q_heat, q_cool) -> LoadPulses
    Convert two 8760-element numpy arrays (zone heating and cooling demands
    from EnergyPlus Ideal Air Loads) into the three ground load pulses
    required by s4_sizing.size_borefield().

Used only in the EnergyPlus real-time path (Plan B).
In the fast path, LoadPulses are read directly from data/public/prototype_loads.json.
"""

from geosite.s3_loads.compute import compute_pulses

__all__ = ["compute_pulses"]
