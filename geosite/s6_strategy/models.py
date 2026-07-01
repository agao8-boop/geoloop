from dataclasses import dataclass


@dataclass
class StrategyResult:
    # Case detection
    case: int                    # 1 or 2
    imbalance_ratio: float       # max(L_h, L_c) / min(L_h, L_c)
    dominant_mode: str           # "heating" | "cooling" | "balanced"
    L_h: float                   # borefield length, heating-only sizing (m)
    L_c: float                   # borefield length, cooling-only sizing (m)

    # LDC
    ldc_cutoff_pct: float        # x% used
    cutoff_W: float              # ground load threshold (W) at cutoff rank

    # Peaker
    peaker_kW: float             # supplemental unit rated capacity
    peaker_type: str             # "electric_heater" | "chiller" | "electric_heater+chiller"
    peaker_heat_kW: float        # heating-side peaker (meaningful for Case 2)
    peaker_cool_kW: float        # cooling-side peaker (meaningful for Case 2)

    # Three-pulse — original dominant sizing
    q_h_before: float
    q_m_before: float
    q_y_before: float

    # Three-pulse — trimmed (after LDC)
    q_h_trimmed: float
    q_m_trimmed: float
    q_y_trimmed: float

    # Sizing — before and after
    L_before: float              # borefield without peaker (m)
    H_before: float              # depth per borehole without peaker (m)
    L_after: float               # borefield with trimmed load (m)
    H_after: float               # depth per borehole with trimmed load (m)
    NB: int                      # number of boreholes (unchanged)

    # Cost — before and after (dicts from estimate_cost)
    cost_before: dict
    cost_after: dict

    # Profiles for visualization (8760 floats each)
    hourly_profile: list         # original ground load (W)
    hourly_trimmed: list         # trimmed ground load (W)

    def to_dict(self) -> dict:
        return {
            "case": self.case,
            "imbalance_ratio": round(min(self.imbalance_ratio, 9999.0), 3),
            "dominant_mode": self.dominant_mode,
            "L_h": round(self.L_h, 1),
            "L_c": round(self.L_c, 1),
            "ldc_cutoff_pct": self.ldc_cutoff_pct,
            "cutoff_W": round(self.cutoff_W, 1),
            "peaker_kW": round(self.peaker_kW, 1),
            "peaker_type": self.peaker_type,
            "peaker_heat_kW": round(self.peaker_heat_kW, 1),
            "peaker_cool_kW": round(self.peaker_cool_kW, 1),
            "q_h_before": round(self.q_h_before, 1),
            "q_m_before": round(self.q_m_before, 1),
            "q_y_before": round(self.q_y_before, 1),
            "q_h_trimmed": round(self.q_h_trimmed, 1),
            "q_m_trimmed": round(self.q_m_trimmed, 1),
            "q_y_trimmed": round(self.q_y_trimmed, 1),
            "L_before": round(self.L_before),
            "H_before": round(self.H_before),
            "L_after": round(self.L_after),
            "H_after": round(self.H_after),
            "NB": self.NB,
            "cost_before": self.cost_before,
            "cost_after": self.cost_after,
            "hourly_profile": [round(v, 2) for v in self.hourly_profile],
            "hourly_trimmed": [round(v, 2) for v in self.hourly_trimmed],
        }
