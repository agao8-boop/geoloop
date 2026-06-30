from dataclasses import dataclass


@dataclass
class CostResult:
    total_usd: float
    cost_per_ft: float
    L_ft: float
    NB: int
    breakdown: list[dict]
    region_used: str
    rock_frac: float
    scenario: str
