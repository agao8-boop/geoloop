"""Footprint-driven borehole count range.

The borefield is assumed to be placed in/around a rectangular building
footprint with a BUILDING-TYPE-SPECIFIC aspect ratio (long/short) taken from
the DOE Commercial Prototype scorecard drawings. This building footprint
aspect is distinct from the borefield ARRAY aspect ratio `A` (a user input,
default 9.0 in Smart Mode), which describes the borehole arrangement, not
the building shape:
    footprint = floor_area / n_floors
    W = sqrt(footprint / aspect),  L = aspect * W
    NB_min = one line of boreholes along the SHORT side  = ceil(W / spacing)
    NB_max = boreholes circling the full perimeter       = floor(2*(L+W) / spacing)

Floor counts are the DOE Commercial Prototype Building Models (90.1-2019)
story counts; areas are the prototype conditioned floor areas.
"""

import math

from geosite.s4_sizing.ashrae_sizing import size_borefield, size_borefield_for_depth

# Footprint length/width from the DOE Commercial Prototype scorecard drawings
# (energycodes.gov, 90.1-2019 set), rounded to one decimal. E-shaped schools
# use the effective bounding rectangle. Verify against the scorecard PDFs
# before changing any value.
BUILDING_ASPECT = {
    "small_office":          1.5,   # 27.7 x 18.5 m
    "medium_office":         1.5,   # 49.9 x 33.3 m
    "large_office":          1.5,   # 73.1 x 48.7 m
    "standalone_retail":     1.3,   # 54.3 x 42.2 m
    "primary_school":        1.6,   # E-shape bounding box
    "secondary_school":      1.6,   # E-shape bounding box
    "hospital":              1.3,   # 70.1 x 53.3 m
    "outpatient_healthcare": 1.4,   # scorecard
    "small_hotel":           3.0,   # 54.9 x 18.3 m
    "large_hotel":           3.0,   # slab wing
    "warehouse":             2.2,   # 100.6 x 45.7 m
    "midrise_apartment":     2.7,   # 46.3 x 16.9 m
}

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
    aspect = BUILDING_ASPECT[building_type]
    footprint = area / n_floors
    width = math.sqrt(footprint / aspect)
    length = aspect * width
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
        "aspect": aspect,
        "prototype_area_used": prototype_area_used,
    }
    return nb_min, nb_max, meta


# Sustained peak extraction/rejection per bore-meter. Range spans VDI 4640
# Blatt 2 guideline values for poor soils (dry sediment, ~15 W/m) to
# favorable saturated rock with low run-hours (~70 W/m).
Q_PER_M_MIN = 15.0
Q_PER_M_MAX = 70.0


def load_implied_nb_range(q_h_W: float, H_min: float) -> tuple[int, int]:
    """NB range the peak load itself implies at H_min, by the W/m rule of thumb.

    Advisory only — informs the footprint-capacity warning; never re-bounds
    the geometric range fed to find_optimal_nb.
    """
    q = abs(q_h_W)
    lo = max(1, math.ceil(q / (Q_PER_M_MAX * H_min)))
    hi = max(lo, math.ceil(q / (Q_PER_M_MIN * H_min)))
    return lo, hi


# The objective (minimize total L), the H >= H_min constraint, and the
# depth-primary fallback below are professor-validated (2026-07-06) and must
# not change without sign-off. The load-density check above is advisory only.
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
