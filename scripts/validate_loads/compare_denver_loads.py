"""
Validate Denver (5B) load profiles against OpenEI/DOE Reference Buildings.

Data source: OpenEI Commercial Load Profiles, DOE Reference Buildings 90.1-2004
  Weather: USA_CO_Denver.Intl.AP.725650_TMY3
  Files: RefBldg{Type}New2004_v1.3_7.1_5B_USA_CO_BOULDER.csv

Columns used:
  Cooling:Electricity [kW](Hourly)   -- DX compressor work [kW]
  Heating:Electricity [kW](Hourly)   -- electric heating (resistance / HP) [kW]
  Heating:Gas [kW](Hourly)           -- gas furnace [kW]

Ground-load conversion (GSHP retrofit assumption):
  COP_heat = 3.5,  EER_cool = 3.0  (moderate efficiency)
  ground_cool_W = cool_elec × (EER_cool + 1)  [heat rejected = load + compressor heat]
  ground_heat_W = (heat_thermal) × (1 - 1/COP_heat)  [extraction = thermal - compressor work]
  heat_thermal  = heat_gas × FURNACE_EFF + heat_elec  [total thermal delivered to building]

Compare against our prototype_loads.json (90.1-2019, same climate zone 5B).
"""

import csv
import pathlib
import json
import sys

DATA_DIR = pathlib.Path(__file__).parent
PROJECT_ROOT = DATA_DIR.parents[1]
PROTO_JSON = PROJECT_ROOT / "data" / "public" / "prototype_loads.json"

# GSHP conversion parameters
COP_HEAT    = 3.5
EER_COOL    = 3.0   # existing DX system EER (approx conversion to building thermal)
FURNACE_EFF = 0.85  # 85% efficient gas furnace

FILES = {
    "small_office":             "RefBldgSmallOfficeNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "medium_office":            "RefBldgMediumOfficeNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "large_office":             "RefBldgLargeOfficeNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "full_service_restaurant":  "RefBldgFullServiceRestaurantNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "hospital":                 "RefBldgHospitalNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "large_hotel":              "RefBldgLargeHotelNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "midrise_apartment":        "RefBldgMidriseApartmentNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "outpatient":               "RefBldgOutPatientNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "primary_school":           "RefBldgPrimarySchoolNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "quick_service_restaurant": "RefBldgQuickServiceRestaurantNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "secondary_school":         "RefBldgSecondarySchoolNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "small_hotel":              "RefBldgSmallHotelNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "standalone_retail":        "RefBldgStand-aloneRetailNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "strip_mall":               "RefBldgStripMallNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "supermarket":              "RefBldgSuperMarketNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
    "warehouse":                "RefBldgWarehouseNew2004_v1.3_7.1_5B_USA_CO_BOULDER.csv",
}

# DOE 90.1-2004 prototype floor areas (m²)
PROTO_AREAS_2004 = {
    "small_office":             511.0,
    "medium_office":            4_982.0,
    "large_office":             46_320.0,
    "full_service_restaurant":  511.0,
    "hospital":                 22_422.0,
    "large_hotel":              11_345.0,
    "midrise_apartment":        3_135.0,
    "outpatient":               3_804.0,
    "primary_school":           6_871.0,
    "quick_service_restaurant": 232.0,
    "secondary_school":         19_592.0,
    "small_hotel":              4_013.0,
    "standalone_retail":        2_294.0,
    "strip_mall":               2_090.0,
    "supermarket":              4_181.0,
    "warehouse":                4_835.0,
}


def parse_csv(path: pathlib.Path) -> dict:
    """Parse one OpenEI reference building CSV, return annual load summary."""
    cool_elec_kwh = 0.0
    heat_elec_kwh = 0.0
    heat_gas_kwh  = 0.0

    cool_peak_kw  = 0.0
    heat_peak_kw  = 0.0   # combined electric + gas thermal equivalent

    cool_elec_series = []
    heat_elec_series = []
    heat_gas_series  = []

    monthly_cool = [0.0] * 12
    monthly_heat = [0.0] * 12
    month_hours  = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
    hour_idx     = 0

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip monthly-summary rows (col count differs) or empty rows
            try:
                cool_kw = float(row.get("Cooling:Electricity [kW](Hourly)", 0) or 0)
                heat_e  = float(row.get("Heating:Electricity [kW](Hourly)", 0) or 0)
                heat_g  = float(row.get("Heating:Gas [kW](Hourly)", 0) or 0)
            except (ValueError, TypeError):
                continue

            cool_elec_kwh += cool_kw
            heat_elec_kwh += heat_e
            heat_gas_kwh  += heat_g

            # Building thermal loads delivered (kW)
            cool_thermal_kw = cool_kw * EER_COOL          # building cooling demand
            heat_thermal_kw = heat_g * FURNACE_EFF + heat_e  # building heating demand

            # GSHP ground-loop loads (kW)
            g_cool = cool_thermal_kw + cool_kw            # reject = load + compressor heat
            g_heat = heat_thermal_kw * (1 - 1/COP_HEAT)  # extract = thermal × (COP-1)/COP

            cool_elec_series.append(g_cool)
            heat_elec_series.append(g_heat)   # store as positive
            heat_gas_series.append(heat_thermal_kw)

            if g_cool > cool_peak_kw:
                cool_peak_kw = g_cool
            if heat_thermal_kw > heat_peak_kw:
                heat_peak_kw = heat_thermal_kw

            # Monthly bucket
            month = 0
            cumulative = 0
            for m, h in enumerate(month_hours):
                cumulative += h
                if hour_idx < cumulative:
                    month = m
                    break
            monthly_cool[month] += g_cool
            monthly_heat[month] += g_heat
            hour_idx += 1

    # Monthly averages (kW)
    monthly_cool_avg = [monthly_cool[m] / month_hours[m] for m in range(12)]
    monthly_heat_avg = [monthly_heat[m] / month_hours[m] for m in range(12)]

    # Net ground load: positive = cooling injection, negative = heating extraction
    ground_net_series = [cool_elec_series[i] - heat_elec_series[i]
                         for i in range(len(cool_elec_series))]

    ann_cool_ground_kwh = sum(cool_elec_series)
    ann_heat_ground_kwh = sum(heat_elec_series)

    # q_y: annual average net ground load [W] (positive = cooling dominant)
    q_y_W = (ann_cool_ground_kwh - ann_heat_ground_kwh) / len(ground_net_series) * 1000

    # Peak monthly (worst net month, signed)
    monthly_net_avg = [monthly_cool_avg[m] - monthly_heat_avg[m] for m in range(12)]
    q_m_W = max(monthly_net_avg) * 1000 if q_y_W >= 0 else min(monthly_net_avg) * 1000

    # Peak hour (worst net hour, signed)
    q_h_W = max(ground_net_series) * 1000 if q_y_W >= 0 else min(ground_net_series) * 1000

    return {
        "hours_parsed": hour_idx,
        # Electricity/gas consumption
        "ann_cool_elec_kwh":  round(cool_elec_kwh),
        "ann_heat_elec_kwh":  round(heat_elec_kwh),
        "ann_heat_gas_kwh":   round(heat_gas_kwh),
        # Ground-loop annual energy
        "ann_cool_ground_kwh": round(ann_cool_ground_kwh),
        "ann_heat_ground_kwh": round(ann_heat_ground_kwh),
        "cool_heat_ratio":     round(ann_cool_ground_kwh / max(ann_heat_ground_kwh, 1), 2),
        "dominant":            "cooling" if q_y_W >= 0 else "heating",
        # Three pulses (W)
        "q_h_W":  round(q_h_W),
        "q_m_W":  round(q_m_W),
        "q_y_W":  round(q_y_W),
        # Peak building loads (kW) for sanity check
        "peak_cool_ground_kw": round(cool_peak_kw, 1),
        "peak_heat_thermal_kw": round(heat_peak_kw, 1),
    }


def main():
    print("=" * 70)
    print("Denver (5B) Load Profile Validation")
    print("Source : OpenEI DOE Reference Buildings 90.1-2004, Denver TMY3")
    print("Compare: GeoSite prototype_loads.json (90.1-2019)")
    print("=" * 70)

    with open(PROTO_JSON) as f:
        proto = json.load(f)

    for btype, fname in FILES.items():
        path = DATA_DIR / fname
        if not path.exists():
            print(f"\n[MISSING] {fname} — run download step first")
            continue

        print(f"\n{'─'*70}")
        print(f"Building: {btype}")
        print(f"{'─'*70}")

        result = parse_csv(path)

        print(f"\nOpenEI / DOE Reference Buildings 2004 (Denver TMY3):")
        print(f"  Hours parsed:            {result['hours_parsed']}")
        print(f"  Annual cool elec:        {result['ann_cool_elec_kwh']:>10,} kWh")
        print(f"  Annual heat elec+gas:    {result['ann_heat_elec_kwh'] + result['ann_heat_gas_kwh']:>10,} kWh")
        print(f"  → Ground cool rejection: {result['ann_cool_ground_kwh']:>10,} kWh  (building cool + compressor heat)")
        print(f"  → Ground heat extract:   {result['ann_heat_ground_kwh']:>10,} kWh  (thermal × (COP-1)/COP)")
        print(f"  Cool/heat ratio:         {result['cool_heat_ratio']:>10.1f}×  cooling")
        print(f"  Dominant mode:           {result['dominant']:>10}")
        print(f"  Peak cool ground:        {result['peak_cool_ground_kw']:>10.1f} kW")
        print(f"  Peak heat building:      {result['peak_heat_thermal_kw']:>10.1f} kW")
        print(f"  Three pulses (GSHP):     q_h={result['q_h_W']:+,} W  "
              f"q_m={result['q_m_W']:+,} W  q_y={result['q_y_W']:+,} W")

        # Compare with prototype_loads.json
        if btype in proto and "5B" in proto[btype]:
            p = proto[btype]["5B"]
            print(f"\nprototype_loads.json (90.1-2019, our current data):")
            print(f"  Annual cool ground:      {p.get('ann_cool_kWh', '?'):>10,} kWh")
            print(f"  Annual heat ground:      {p.get('ann_heat_kWh', '?'):>10,} kWh")
            if p.get('ann_heat_kWh'):
                ratio_proto = p['ann_cool_kWh'] / max(p['ann_heat_kWh'], 1)
                print(f"  Cool/heat ratio:         {ratio_proto:>10.1f}×  cooling")
            print(f"  q_h={p.get('q_h','?'):+,} W  q_m={p.get('q_m','?'):+,} W  q_y={p.get('q_y','?'):+,} W")
            print(f"  Dominant mode:           {'heating' if p.get('q_h', 0) < 0 else 'cooling':>10}")

        print()

    print("=" * 70)
    print("NOTES:")
    print("  OpenEI uses 90.1-2004 (older code, less insulation → more heating)")
    print("  prototype_loads.json uses 90.1-2019 (better insulation, less heating)")
    print("  COP=3.5, EER=3.0, furnace_eff=0.85 assumed for ground-load conversion")
    print("=" * 70)


if __name__ == "__main__":
    main()
