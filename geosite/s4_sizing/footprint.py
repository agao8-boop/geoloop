"""Footprint-driven borehole count range.

PROTOTYPE_AREAS_M2 values are total conditioned floor areas across all
floors (EnergyPlus DOE prototype, 90.1-2019). Footprint = total_area / n_floors.

The building footprint is modeled as one of the BUILDING_SHAPES polygons
(normalized to unit grid squares, scaled so the polygon area equals the
per-floor footprint):
    footprint = floor_area / n_floors
    scale = sqrt(footprint / area_units)   # one grid unit in metres
    NB_min = one line of boreholes along the SHORT side  = ceil(scale / spacing)
    NB_max = boreholes circling the full perimeter       = floor(perimeter / spacing)

Floor counts are the DOE Commercial Prototype Building Models (90.1-2019)
story counts; areas are the prototype conditioned floor areas.
"""

import math

from geosite.s4_sizing.ashrae_sizing import size_borefield, size_borefield_for_depth

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
    "highrise_apartment":    12,
    "retail_stripmall":      1,
    "restaurant_fastfood":   1,
    "restaurant_sitdown":    1,
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
    "highrise_apartment":    16722.0,
    "retail_stripmall":      2090.0,
    "restaurant_fastfood":   232.3,
    "restaurant_sitdown":    511.1,
}

# Normalized footprint polygons in grid units; one grid unit = `scale` metres
# where scale = sqrt(footprint_m2 / area_units).
BUILDING_SHAPES = {
    "square": {
        "label": "Square",
        "polygon": [(0, 0), (1, 0), (1, 1), (0, 1)],   # area = 1 sq unit
        "area_units": 1.0,
        "description": "1:1 footprint",
    },
    "rect_2_1": {
        "label": "Rectangle (2:1)",
        "polygon": [(0, 0), (2, 0), (2, 1), (0, 1)],   # area = 2 sq units
        "area_units": 2.0,
        "description": "Standard commercial rectangle",
    },
    "l_shape": {
        "label": "L-shape",
        # 2×2 grid minus top-right 1×1 → area = 3 sq units
        "polygon": [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)],
        "area_units": 3.0,
        "description": "L-shape (3/4 of 2×2 grid)",
    },
    "u_shape": {
        "label": "U-shape",
        # 3×2 outer minus center-top 1×1 cutout → area = 5 sq units
        "polygon": [(0, 0), (3, 0), (3, 2), (2, 2), (2, 1), (1, 1), (1, 2), (0, 2)],
        "area_units": 5.0,
        "description": "U-shape / courtyard plan",
    },
    "elongated": {
        "label": "Elongated (9:1)",
        "polygon": [(0, 0), (9, 0), (9, 1), (0, 1)],   # area = 9 sq units
        "area_units": 9.0,
        "description": "Long linear plan — hotel / wing layout",
    },
}
DEFAULT_SHAPE = "elongated"   # keeps existing NB behavior for back-compat


def _polygon_perimeter(pts):
    n = len(pts)
    return sum(
        math.hypot(pts[(i + 1) % n][0] - pts[i][0], pts[(i + 1) % n][1] - pts[i][1])
        for i in range(n)
    )


def shape_geometry(footprint_m2: float, shape_key: str) -> dict:
    """Return actual polygon vertices in metres and perimeter for the given shape."""
    sh = BUILDING_SHAPES[shape_key]
    scale = math.sqrt(footprint_m2 / sh["area_units"])
    pts = [(x * scale, y * scale) for x, y in sh["polygon"]]
    perimeter = _polygon_perimeter(pts)
    return {"scale": scale, "pts": pts, "perimeter_m": perimeter}


def compute_nb_range(
    floor_area_m2: float | None,
    building_type: str,
    spacing_m: float = 6.0,
    shape: str = DEFAULT_SHAPE,
    num_floors: int | None = None,
) -> tuple[int, int, dict]:
    """Return (nb_min, nb_max, meta) from the building footprint geometry.

    floor_area_m2=None uses the DOE prototype area for the building type.
    num_floors=None uses the DOE prototype floor count for the building type.
    """
    if building_type not in BUILDING_FLOORS:
        raise KeyError(
            f"'{building_type}' not in footprint table. "
            f"Available: {sorted(BUILDING_FLOORS)}"
        )
    if shape not in BUILDING_SHAPES:
        raise KeyError(
            f"'{shape}' not in shape table. Available: {sorted(BUILDING_SHAPES)}"
        )
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")
    if num_floors is not None and num_floors < 1:
        raise ValueError("num_floors must be >= 1")

    prototype_area_used = floor_area_m2 is None
    area = PROTOTYPE_AREAS_M2[building_type] if prototype_area_used else float(floor_area_m2)
    if area <= 0:
        raise ValueError("floor_area_m2 must be positive")

    n_floors = num_floors if num_floors else BUILDING_FLOORS[building_type]
    footprint = area / n_floors
    geom = shape_geometry(footprint, shape)
    perimeter = geom["perimeter_m"]

    # nb_min: one line of boreholes along the "short" side (= one grid unit)
    short_side = geom["scale"]
    nb_min = max(1, math.ceil(short_side / spacing_m))
    nb_max = max(nb_min, math.floor(perimeter / spacing_m))

    meta = {
        "footprint_m2": footprint,
        "n_floors": n_floors,
        "floor_area_m2": area,
        "perimeter_m": perimeter,
        "spacing_m": spacing_m,
        "shape": shape,
        "shape_label": BUILDING_SHAPES[shape]["label"],
        "pts": geom["pts"],      # polygon vertices in metres — sent to frontend for canvas
        "scale_m": geom["scale"],
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
    H_max: float = 250.0,
    B: float = 6.0,
    A: float = 1.0,
    **adv,
) -> tuple[int, float, float]:
    """Pick the NB in [nb_min, nb_max] that minimizes total drilled length L.

    Candidates must satisfy H_min <= H = L/NB <= H_max. H_min avoids shallow
    holes (mobilization cost, header pipe). H_max caps at practical drill-rig
    depth (~250 m for commercial rotary rigs).

    Fallback — two cases when no candidate satisfies both constraints:
      • all H < H_min (small load): depth-primary sizing at H_target=H_min.
        Callers detect this via nb_opt < nb_min.
      • any H > H_max (overcapacity): load exceeds what nb_max boreholes can
        serve within drillable depth; return nb_max with actual H (> H_max).
        Callers detect this via H > H_max.

    adv carries T_in_HP plus the 9 borehole/fluid params.
    Returns (nb_opt, L_opt, H_opt).
    """
    common = dict(q_h=q_h, q_m=q_m, q_y=q_y, k=k, alpha=alpha, T_g=T_g, **adv)

    L0 = float(size_borefield(**common))
    if L0 <= 0:
        return 1, L0, L0

    best = None
    any_too_deep = False
    for nb in range(nb_min, nb_max + 1):
        L = float(size_borefield(**common, B=B, NB=nb, A=A))
        if L <= 0:
            continue
        H = L / nb
        if H > H_max:
            any_too_deep = True
            continue
        if H < H_min:
            continue
        if best is None or L < best[1]:
            best = (nb, L, H)
    if best is not None:
        return best

    if any_too_deep:
        # Overcapacity: even nb_max leaves H > H_max; return nb_max so caller
        # can detect H > H_max and set nb_source = "depth_too_deep".
        L = float(size_borefield(**common, B=B, NB=nb_max, A=A))
        return nb_max, L, L / nb_max

    L, nb, H = size_borefield_for_depth(**common, B=B, A=A, H_target=H_min)
    return nb, L, H
