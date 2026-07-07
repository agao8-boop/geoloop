"""Footprint-driven borehole count range.

The borefield is assumed to be placed in/around a rectangular building
footprint with aspect ratio 9 (long/short), the arrangement that maximizes
inter-borehole energy efficiency for a line-dominant field:
    footprint = floor_area / n_floors
    W = sqrt(footprint / 9),  L = 9 * W = 3 * sqrt(footprint)
    NB_min = one line of boreholes along the SHORT side  = ceil(W / spacing)
    NB_max = boreholes circling the full perimeter       = floor(2*(L+W) / spacing)

Floor counts are the DOE Commercial Prototype Building Models (90.1-2019)
story counts; areas are the prototype conditioned floor areas.
"""

import math

from geosite.s4_sizing.ashrae_sizing import size_borefield, size_borefield_for_depth

FOOTPRINT_ASPECT = 9.0

BUILDING_FLOORS = {
    "small_office":          1,
    "medium_office":         3,
    "large_office":          12,
    "standalone_retail":     1,
    "primary_school":        1,
    "secondary_school":      2,
    "hospital":              5,
    "outpatient_healthcare": 3,
    "small_hotel":           4,
    "large_hotel":           6,
    "warehouse":             1,
    "midrise_apartment":     4,
}

PROTOTYPE_AREAS_M2 = {
    "small_office":          511.0,
    "medium_office":         4982.0,
    "large_office":          46320.0,
    "standalone_retail":     2294.0,
    "primary_school":        6871.0,
    "secondary_school":      19592.0,
    "hospital":              22422.0,
    "outpatient_healthcare": 3804.0,
    "small_hotel":           4014.0,
    "large_hotel":           11345.0,
    "warehouse":             4835.0,
    "midrise_apartment":     3135.0,
}


def compute_nb_range(
    floor_area_m2: float | None,
    building_type: str,
    spacing_m: float = 6.0,
) -> tuple[int, int, dict]:
    """Return (nb_min, nb_max, meta) from the building footprint geometry.

    floor_area_m2=None uses the DOE prototype area for the building type.
    """
    if building_type not in BUILDING_FLOORS:
        raise KeyError(
            f"'{building_type}' not in footprint table. "
            f"Available: {sorted(BUILDING_FLOORS)}"
        )
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")

    prototype_area_used = floor_area_m2 is None
    area = PROTOTYPE_AREAS_M2[building_type] if prototype_area_used else float(floor_area_m2)
    if area <= 0:
        raise ValueError("floor_area_m2 must be positive")

    n_floors = BUILDING_FLOORS[building_type]
    footprint = area / n_floors
    width = math.sqrt(footprint / FOOTPRINT_ASPECT)
    length = FOOTPRINT_ASPECT * width
    perimeter = 2.0 * (length + width)

    nb_min = max(1, math.ceil(width / spacing_m))
    nb_max = max(nb_min, math.floor(perimeter / spacing_m))

    meta = {
        "footprint_m2": footprint,
        "n_floors": n_floors,
        "floor_area_m2": area,
        "width_m": width,
        "length_m": length,
        "perimeter_m": perimeter,
        "spacing_m": spacing_m,
        "aspect": FOOTPRINT_ASPECT,
        "prototype_area_used": prototype_area_used,
    }
    return nb_min, nb_max, meta


def find_optimal_nb(
    nb_min: int,
    nb_max: int,
    q_h: float,
    q_m: float,
    q_y: float,
    k: float,
    alpha: float,
    T_g: float,
    H_min: float = 125.0,
    B: float = 6.0,
    A: float = 1.0,
    **adv,
) -> tuple[int, float, float]:
    """Pick the NB in [nb_min, nb_max] that minimizes total drilled length L.

    Candidates must satisfy the minimum-depth constraint H = L/NB >= H_min
    (shallow holes waste mobilization cost and header pipe). L increases with
    NB via the Tp interaction correction and H decreases, so the minimum-L
    valid NB is expected at the low end — the full range is swept anyway
    because the Tp polynomial is not guaranteed monotone near the boundary.

    Fallback: when no range NB satisfies H >= H_min (small load), the field
    is smaller than one footprint line; depth-primary sizing with
    H_target=H_min decides NB instead (per the 2026-07-06 professor
    directive: depth is the primary input). Callers detect the fallback as
    nb_opt < nb_min. adv carries T_in_HP plus the 9 borehole/fluid params.

    Returns (nb_opt, L_opt, H_opt).
    """
    common = dict(q_h=q_h, q_m=q_m, q_y=q_y, k=k, alpha=alpha, T_g=T_g, **adv)

    L0 = float(size_borefield(**common))
    if L0 <= 0:
        return 1, L0, L0

    best = None
    for nb in range(nb_min, nb_max + 1):
        L = float(size_borefield(**common, B=B, NB=nb, A=A))
        if L <= 0:
            continue
        H = L / nb
        if H < H_min:
            continue
        if best is None or L < best[1]:
            best = (nb, L, H)
    if best is not None:
        return best

    L, nb, H = size_borefield_for_depth(**common, B=B, A=A, H_target=H_min)
    return nb, L, H
