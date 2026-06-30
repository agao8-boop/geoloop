from geosite.s5_cost.line_items import calc_line_items
from geosite.s5_cost.regional_rates import get_rates, get_region_used
from geosite.s5_cost.models import CostResult

_M_TO_FT = 3.28084

_ROCK_CLASS_FRACS = {
    "igneous":        0.90,
    "metamorphic":    0.85,
    "sedimentary":    0.40,
    "unconsolidated": 0.05,
}

_SCENARIOS = {
    "best":  0.00,
    "base":  0.30,
    "worst": 0.70,
}


def _rock_frac_from_class(rock_class_name: str | None) -> float | None:
    if not rock_class_name:
        return None
    return _ROCK_CLASS_FRACS.get(rock_class_name.lower().split()[0])


def _run_scenario(
    scenario: str,
    rock_frac: float,
    L_m: float,
    NB: int,
    B_m: float,
    rates: dict,
    region_used: str,
    distance_to_house_ft: float,
) -> CostResult:
    L_ft = L_m * _M_TO_FT
    items = calc_line_items(
        L_m=L_m, NB=NB, B_m=B_m, rates=rates,
        rock_frac=rock_frac, distance_to_house_ft=distance_to_house_ft,
    )
    total_usd = sum(i["cost_usd"] for i in items)
    return CostResult(
        total_usd=total_usd,
        cost_per_ft=total_usd / L_ft,
        L_ft=L_ft,
        NB=NB,
        breakdown=items,
        region_used=region_used,
        rock_frac=rock_frac,
        scenario=scenario,
    )


def estimate_cost(
    L_m: float,
    NB: int,
    B_m: float,
    state: str | None,
    rock_class_name: str | None = None,
    distance_to_house_ft: float = 100.0,
) -> dict:
    """Estimate borefield installation cost in best/base/worst scenarios.

    Parameters
    ----------
    L_m : total borefield length in meters (from s4 sizing)
    NB  : number of boreholes
    B_m : borehole spacing in meters
    state : 2-letter state abbreviation (used for regional rate lookup)
    rock_class_name : SGMC rock class (e.g. "Igneous") or None
    distance_to_house_ft : horizontal trench distance from field to building

    Returns
    -------
    dict with keys "best", "base", "worst" (each a CostResult),
    "headline_per_ft" (base scenario $/ft), "region_used" (rate table key used)
    """
    region = get_region_used(state)
    rates = get_rates(state)
    site_rock_frac = _rock_frac_from_class(rock_class_name)

    results = {}
    for scenario, default_frac in _SCENARIOS.items():
        if site_rock_frac is not None:
            # Narrow the range around the site-specific rock fraction
            spread = 0.15
            if scenario == "best":
                frac = max(0.0, site_rock_frac - spread)
            elif scenario == "worst":
                frac = min(1.0, site_rock_frac + spread)
            else:
                frac = site_rock_frac
        else:
            frac = default_frac
        results[scenario] = _run_scenario(
            scenario, frac, L_m, NB, B_m, rates, region, distance_to_house_ft
        )

    return {
        "best": results["best"],
        "base": results["base"],
        "worst": results["worst"],
        "headline_per_ft": results["base"].cost_per_ft,
        "region_used": region,
    }
