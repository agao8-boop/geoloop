#!/usr/bin/env python3
"""Compare two ways of estimating hybrid GSHP sizing savings.

Simple ratio (professor's approximation):
    savings_pct = (1 - m2_cutoff_W / cap_W) * 100

Actual three-pulse ratio (borefield length reduction):
    savings_pct = (1 - L_after_m2 / L_before) * 100

The question: does the simple power ratio overestimate or underestimate
the actual borefield savings?  If they track closely, the simpler calculation
is sufficient for a back-of-envelope explanation.

Run from geosite_advisor/:
    python scripts/compare_sizing_ratios.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from geosite.s6_strategy.strategy import run_strategy

# Representative scenarios: (building_type, climate_zone, k, alpha, T_g, label)
# k     = soil conductivity [W/m·K]  — typical range 1.5–3.5
# alpha = thermal diffusivity [m²/s] — ~0.09e-6 m²/s rock, 0.086e-6 sandy soil
# T_g   = undisturbed ground temp [°C] — estimated from local mean air temp
SCENARIOS = [
    ("small_office",  "1A",  1.8, 0.086e-6, 24.0, "Miami  (1A, cooling-dominated)"),
    ("medium_office", "2A",  1.9, 0.086e-6, 20.0, "Houston (2A, cooling-dominated)"),
    ("medium_office", "3A",  2.0, 0.090e-6, 17.0, "Atlanta (3A, mixed-humid)"),
    ("medium_office", "4A",  2.0, 0.090e-6, 13.0, "Baltimore (4A, balanced)"),
    ("medium_office", "5A",  2.1, 0.090e-6, 10.0, "Chicago (5A, heating-dominated)"),
    ("medium_office", "6A",  2.5, 0.090e-6,  7.0, "Minneapolis (6A, cold)"),
    ("medium_office", "7",   2.8, 0.090e-6,  4.0, "International Falls (7, very cold)"),
    ("medium_office", "3B",  2.2, 0.086e-6, 20.0, "Las Vegas (3B, hot-dry)"),
    ("large_office",  "4A",  2.0, 0.090e-6, 13.0, "Baltimore large (4A)"),
    ("large_office",  "5A",  2.1, 0.090e-6, 10.0, "Chicago large (5A)"),
]

# LDC cutoff percentages to compare (professor was interested in the 10% case)
CUTOFF_PCTS = [5.0, 10.0, 15.0]


def _run(building_type, climate_zone, k, alpha, T_g, ldc_pct):
    return run_strategy(
        building_type=building_type,
        climate_zone=climate_zone,
        k=k,
        alpha=alpha,
        T_g=T_g,
        NB=None,
        B=6.0,
        A=9.0,
        H_min=125.0,
        ldc_cutoff_pct=ldc_pct,
    )


print("\n=== Hybrid GSHP Sizing Ratio Comparison ===")
print("Simple ratio  = 1 - m2_cutoff_kW / cap_kW     (power-based, professor's shortcut)")
print("Actual ratio  = 1 - L_after_m2 / L_before     (three-pulse borefield reduction)")
print("Diff = actual - simple (positive = actual saves more than simple predicts)")
print()

for cutoff_pct in CUTOFF_PCTS:
    print(f"\n--- LDC cutoff = {cutoff_pct:.0f}% energy ---")
    header = f"{'Scenario':<38} {'cap_kW':>7} {'cut_kW':>7} {'simple%':>8} {'actual%':>8} {'diff_pts':>9} {'pkr_kW':>10}"
    print(header)
    print("-" * len(header))

    for btype, cz, k, alpha, T_g, label in SCENARIOS:
        try:
            res = _run(btype, cz, k, alpha, T_g, cutoff_pct)
        except Exception as e:
            print(f"  {'SKIP':>38} {label}: {e}")
            continue

        if res.L_before < 1.0 or res.cap_W < 1.0:
            print(f"  {'SKIP (L_before≈0)':>38} {label}")
            continue

        simple_pct = 100.0 * (1.0 - res.m2_cutoff_W / res.cap_W)
        actual_pct = 100.0 * (1.0 - res.m2_L_after / res.L_before)
        diff = actual_pct - simple_pct

        # Flag cases where the Tp iteration likely diverged (hits the L=0 or L=L_before bounds)
        tp_flag = ""
        if res.m2_L_after < 1.0:
            tp_flag = " [Tp:0]"       # iteration collapsed to 0
        elif abs(res.m2_L_after - res.L_before) < 1.0:
            tp_flag = " [Tp:nc]"      # iteration didn't converge (stayed at L_before)

        print(
            f"{label:<38} "
            f"{res.cap_W/1000:>7.1f} "
            f"{res.m2_cutoff_W/1000:>7.1f} "
            f"{simple_pct:>8.1f} "
            f"{actual_pct:>8.1f} "
            f"{diff:>+9.1f} "
            f"{res.m2_peaker_kW:>10.1f}"
            f"{tp_flag}"
        )

print()
print("Interpretation:")
print("  diff > 0 → actual borefield shrinks MORE than simple ratio predicts")
print("  diff < 0 → simple ratio overstates the savings")
print("  |diff| < 2 pts → simple ratio is a good proxy; use it for back-of-envelope")
print("  |diff| > 5 pts → three-pulse calculation matters; do not use simple ratio")
print()
print("Flags:")
print("  [Tp:0]  — Philippe Tp iteration collapsed (Tp polynomial outside valid domain).")
print("            Borefield savings indeterminate; 100% is not physically meaningful.")
print("  [Tp:nc] — Tp iteration did not reduce L_after (conservative: 0% savings shown).")
print()
print("Reliable cases (no Tp flag) are the balanced/mixed climates.")
print("Extreme-climate cases need a validated g-function Tp calculation for reliable results.")
