import math

_M_TO_FT = 3.28084


def _round_up_to_10(ft: float) -> float:
    return math.ceil(ft / 10) * 10


def calc_line_items(
    L_m: float,
    NB: int,
    B_m: float,
    rates: dict,
    rock_frac: float = 0.0,
    r_bore: float = 0.0762,
    r_pext: float = 0.0167,
    distance_to_house_ft: float = 100.0,
) -> list[dict]:
    """Compute all 9 cost line items from borefield geometry × rate table.

    Formulas verified against data/reference/390geothermal_calc.xlsx.
    """
    H_exact_m = L_m / NB
    H_exact_ft = H_exact_m * _M_TO_FT
    H_rounded_ft = _round_up_to_10(H_exact_ft)
    B_ft = B_m * _M_TO_FT
    total_drill_lf = NB * H_rounded_ft

    # Grout volume — spreadsheet formula (r_bore² - r_pext²/2)
    grout_vol_m3 = math.pi * H_exact_m * (r_bore**2 - r_pext**2 / 2)
    grout_vol_L = grout_vol_m3 * 1000
    grout_bags_per_bh = math.ceil(grout_vol_L / 161)  # 161 L yield per CETCO batch
    grout_bags_total = grout_bags_per_bh * NB
    sand_bags_total = grout_bags_per_bh * 8 * NB  # 8 × 50lb bags sand per CETCO batch

    horiz_trench_ft = (NB - 1) * B_ft + distance_to_house_ft
    horiz_pipe_ft = 2 * horiz_trench_ft

    def item(name, qty, unit, rate):
        return {"name": name, "qty": qty, "unit": unit,
                "rate": rate, "cost_usd": qty * rate}

    return [
        item("mobilization",   1,                             "project", rates["mobilization"]),
        item("drilling_soil",  total_drill_lf * (1 - rock_frac), "LF",  rates["drilling_soil"]),
        item("drilling_rock",  total_drill_lf * rock_frac,    "LF",     rates["drilling_rock"]),
        item("well_casing",    0,                             "LF",     rates["well_casing"]),
        item("sand_bag",       sand_bags_total,               "50lb bag", rates["sand_bag"]),
        item("grout_bag",      grout_bags_total,              "50lb bag", rates["grout_bag"]),
        item("utube_pipe",     total_drill_lf,                "LF",     rates["utube_pipe"]),
        item("horiz_pipe",     horiz_pipe_ft,                 "LF",     rates["horiz_pipe"]),
        item("horiz_trench",   horiz_trench_ft,               "LF",     rates["horiz_trench"]),
    ]
