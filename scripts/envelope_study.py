#!/usr/bin/env python3
"""Envelope cross-study: compute load multipliers for all three professor categories.

Procedure
---------
1. For each (building_type, city) pair, locate the DOE prototype IDF in
   data/doe_prototypes/ and auto-copy to data/envelope_study/raw_copies/ if absent.
2. For each parameter variant (one at a time, control method), write a modified IDF.
3. Prepare each variant (strip HVAC → add IdealLoads) and run EnergyPlus.
4. Record peak heating load, peak cooling load, and annual totals relative to baseline.
5. Save results to data/envelope_study/results/multipliers_{building}_{city}.json.
   After EACH simulation, a partial checkpoint is written so a crash loses at most
   one variant's work.

Parameters varied (one at a time, all others at baseline):
-----------------------------------------------------------
1. WWR — via FenestrationSurface:Detailed vertex replacement:
     wwr_10 to wwr_90 in six tiers; baseline is 20% for all building types.
2. Glazing quality — via WindowMaterial:SimpleGlazingSystem (U-Factor + SHGC):
     triple_low_e, double_pane (baseline), single_pane
3. Air tightness — via ZoneInfiltration:DesignFlowRate Flow/ExteriorWallArea:
     tight, standard (baseline), leaky

Run from geosite_advisor/:
    python scripts/envelope_study.py --building small_office --city denver
    python scripts/envelope_study.py --building medium_office --all-cities
    python scripts/envelope_study.py --dry-run

Set ENERGYPLUS_DIR env var to point at your EnergyPlus installation.
"""

import argparse
import json
import os
import pathlib
import re
import shutil
import sys

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT          = pathlib.Path(__file__).resolve().parent.parent
PROTO_DIR     = ROOT / "data" / "doe_prototypes"
STUDY_DIR     = ROOT / "data" / "envelope_study"
RAW_COPIES    = STUDY_DIR / "raw_copies"
VARIANTS_DIR  = STUDY_DIR / "variants"
RESULTS_DIR   = STUDY_DIR / "results"
EPW_DIR       = ROOT / "data" / "epw"

ENERGYPLUS_DIR = pathlib.Path(
    os.environ.get("ENERGYPLUS_DIR", "/Applications/EnergyPlus-22-1-0")
)

# ---------------------------------------------------------------------------
# Climate zone + city registry  (city_key → (climate_zone, epw_filename, idf_city_stem))
# ---------------------------------------------------------------------------

CITY_ZONE_MAP = {
    "miami":             ("1A", "USA_FL_Miami.Intl.AP.722020_TMY3.epw",                          "Miami"),
    "tampa":             ("2A", "USA_FL_Tampa-MacDill.AFB.747880_TMY3.epw",                      "Tampa"),
    "tucson":            ("2B", "USA_AZ_Tucson-Davis-Monthan.AFB.722745_TMY3.epw",               "Tucson"),
    "atlanta":           ("3A", "USA_GA_Atlanta-Hartsfield.Jackson.Intl.AP.722190_TMY3.epw",     "Atlanta"),
    "el_paso":           ("3B", "USA_TX_El.Paso.Intl.AP.722700_TMY3.epw",                        "ElPaso"),
    "san_diego":         ("3C", "USA_CA_San.Deigo-Brown.Field.Muni.AP.722904_TMY3.epw",          "SanDiego"),
    "new_york":          ("4A", "USA_NY_New.York-John.F.Kennedy.Intl.AP.744860_TMY3.epw",        "NewYork"),
    "albuquerque":       ("4B", "USA_NM_Albuquerque.Intl.Sunport.723650_TMY3.epw",               "Albuquerque"),
    "seattle":           ("4C", "USA_WA_Seattle-Tacoma.Intl.AP.727930_TMY3.epw",                 "Seattle"),
    "buffalo":           ("5A", "USA_NY_Buffalo.Niagara.Intl.AP.725280_TMY3.epw",                "Buffalo"),
    "denver":            ("5B", "USA_CO_Denver-Aurora-Buckley.AFB.724695_TMY3.epw",              "Denver"),
    "port_angeles":      ("5C", "USA_WA_Port.Angeles-William.R.Fairchild.Intl.AP.727885_TMY3.epw", "PortAngeles"),
    "rochester":         ("6A", "USA_MN_Rochester.Intl.AP.726440_TMY3.epw",                      "Rochester"),
    "great_falls":       ("6B", "USA_MT_Great.Falls.Intl.AP.727750_TMY3.epw",                    "GreatFalls"),
    "international_falls": ("7","USA_MN_International.Falls.Intl.AP.727470_TMY3.epw",            "InternationalFalls"),
    "fairbanks":         ("8",  "USA_AK_Fairbanks.Intl.AP.702610_TMY3.epw",                      "Fairbanks"),
}

# ---------------------------------------------------------------------------
# Building type registry  (building_key → (proto_subdir, idf_type_stem))
# ---------------------------------------------------------------------------

BUILDING_TYPE_MAP = {
    "small_office":         ("ASHRAE901_OfficeSmall_STD2022",         "OfficeSmall"),
    "medium_office":        ("ASHRAE901_OfficeMedium_STD2022",        "OfficeMedium"),
    "large_office":         ("ASHRAE901_OfficeLarge_STD2022",         "OfficeLarge"),
    "retail_standalone":    ("ASHRAE901_RetailStandalone_STD2022",    "RetailStandalone"),
    "retail_stripmall":     ("ASHRAE901_RetailStripmall_STD2022",     "RetailStripmall"),
    "school_primary":       ("ASHRAE901_SchoolPrimary_STD2022",       "SchoolPrimary"),
    "school_secondary":     ("ASHRAE901_SchoolSecondary_STD2022",     "SchoolSecondary"),
    "outpatient":           ("ASHRAE901_OutPatientHealthCare_STD2022","OutPatientHealthCare"),
    "hospital":             ("ASHRAE901_Hospital_STD2022",            "Hospital"),
    "hotel_small":          ("ASHRAE901_HotelSmall_STD2022",          "HotelSmall"),
    "hotel_large":          ("ASHRAE901_HotelLarge_STD2022",          "HotelLarge"),
    "warehouse":            ("ASHRAE901_Warehouse_STD2022",           "Warehouse"),
    "restaurant_fastfood":  ("ASHRAE901_RestaurantFastFood_STD2022",  "RestaurantFastFood"),
    "restaurant_sitdown":   ("ASHRAE901_RestaurantSitDown_STD2022",   "RestaurantSitDown"),
    "apartment_midrise":    ("ASHRAE901_ApartmentMidRise_STD2022",    "ApartmentMidRise"),
    "apartment_highrise":   ("ASHRAE901_ApartmentHighRise_STD2022",   "ApartmentHighRise"),
}

# ---------------------------------------------------------------------------
# Envelope parameter matrix
# ---------------------------------------------------------------------------

GLAZING_BASELINE_U    = 2.06120838
GLAZING_BASELINE_SHGC = 0.378
INFIL_BASELINE_RATE   = 0.000569572250459736

GLAZING_VARIANTS = {
    "triple_low_e": {"u_factor": 0.85,              "shgc": 0.20},
    # double_low_e = baseline (code-min ASHRAE 90.1-2022 double-pane low-E) — listed explicitly
    "double_low_e": {"u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC},
    # double_pane = plain clear double pane, no coating — most common in pre-2000 buildings
    "double_pane":  {"u_factor": 3.0,               "shgc": 0.70},
    "single_pane":  {"u_factor": 5.8,               "shgc": 0.86},
}

# Controlled sensitivity sweeps — ONE parameter varies, the other held at baseline.
# Baseline: U=2.06120838 (ASHRAE 90.1-2022 code-min), SHGC=0.378.
SHGC_SWEEP_VARIANTS = {
    "shgc_020": {"shgc": 0.20},   # triple low-E level (best solar control)
    "shgc_030": {"shgc": 0.30},
    "shgc_040": {"shgc": 0.40},   # near baseline (0.378)
    "shgc_055": {"shgc": 0.55},
    "shgc_070": {"shgc": 0.70},   # clear double pane level (worst solar control)
}

U_SWEEP_VARIANTS = {
    "u_080":  {"u_factor": 0.80},   # triple low-E level (best insulation)
    "u_140":  {"u_factor": 1.40},
    "u_270":  {"u_factor": 2.70},   # near baseline (2.061)
    "u_400":  {"u_factor": 4.00},
    "u_580":  {"u_factor": 5.80},   # single pane level (worst insulation)
}

INFIL_VARIANTS = {
    "tight":    0.000285,
    "standard": INFIL_BASELINE_RATE,   # baseline — listed explicitly, same as wwr_20pct run
    "leaky":    0.001140,
}

# Standardized 20% WWR baseline for all building types.
# Measured prototypical WWRs: SmallOffice≈19.8%, MediumOffice≈33%, LargeOffice≈40%.
# Using 0.20 makes multipliers cross-building comparable.
_BASELINE_WWR = 0.20

WWR_VARIANTS = {
    "wwr_10pct": 0.10,
    "wwr_20pct": _BASELINE_WWR,   # baseline — _apply_wwr_replace returns unchanged
    "wwr_30pct": 0.30,
    "wwr_50pct": 0.50,
    "wwr_70pct": 0.70,
    "wwr_90pct": 0.90,
}

# ---------------------------------------------------------------------------
# IDF auto-copy from doe_prototypes → raw_copies
# ---------------------------------------------------------------------------

def _get_raw_idf(building_type: str, city: str) -> pathlib.Path:
    """Return path to raw IDF in raw_copies, auto-copying from doe_prototypes if needed."""
    proto_subdir, idf_type = BUILDING_TYPE_MAP[building_type]
    _, _, city_stem = CITY_ZONE_MAP[city]
    idf_name = f"ASHRAE901_{idf_type}_STD2022_{city_stem}.idf"

    dst = RAW_COPIES / idf_name
    if not dst.exists():
        src = PROTO_DIR / proto_subdir / idf_name
        if not src.exists():
            sys.exit(f"Prototype IDF not found: {src}")
        RAW_COPIES.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  Copied IDF → {dst.name}")
    return dst

# ---------------------------------------------------------------------------
# IDF text-level modifications
# ---------------------------------------------------------------------------

def _apply_glazing(idf_text: str, u_factor: float, shgc: float) -> str:
    text = re.sub(
        r'(\n\s+)([\d.]+),(\s+!- U-Factor \{W/m2-K\})',
        lambda m: f"{m.group(1)}{u_factor:.8f},{m.group(3)}",
        idf_text,
    )
    text = re.sub(
        r'(\n\s+)([\d.]+),(\s+!- Solar Heat Gain Coefficient)',
        lambda m: f"{m.group(1)}{shgc:.4f},{m.group(3)}",
        text,
    )
    return text


def _apply_wwr_replace(idf_text: str, target_wwr: float) -> str:
    """Set WWR on all exterior walls to exactly target_wwr (standardized baseline = 0.20)."""
    if abs(target_wwr - _BASELINE_WWR) < 0.001:
        return idf_text

    VERT_PAT = re.compile(
        r'([ \t]+)([-\d.E+]+),([-\d.E+]+),([-\d.E+]+)([,;])'
        r'([ \t]*!-[ \t]*X,Y,Z ==> Vertex \d+ \{m\})'
    )
    WIN_BLOCK  = re.compile(r'FenestrationSurface:Detailed,.*?;[^\n]*', re.DOTALL)
    WALL_BLOCK = re.compile(r'BuildingSurface:Detailed,.*?;[^\n]*', re.DOTALL)

    wall_geom: dict = {}
    for blk in WALL_BLOCK.findall(idf_text):
        if not re.search(r'\bWall,\s*!-\s*Surface Type', blk):
            continue
        if not re.search(r'\bOutdoors,', blk):
            continue
        nm = re.search(r'BuildingSurface:Detailed,\s*\n\s*([^,\n]+),', blk)
        if not nm:
            continue
        wall_name = nm.group(1).strip()
        verts = VERT_PAT.findall(blk)
        if len(verts) < 4:
            continue
        coords = [(float(v[1]), float(v[2]), float(v[3])) for v in verts[:4]]
        xs = [c[0] for c in coords]; ys = [c[1] for c in coords]; zs = [c[2] for c in coords]
        wall_geom[wall_name] = {'xs': xs, 'ys': ys, 'zs': zs, 'x_fixed': (max(xs) - min(xs)) < 0.01}

    # Pre-scan doors so we can cap window height on walls that also have doors.
    door_area_by_wall: dict = {}
    for blk in WIN_BLOCK.findall(idf_text):
        if not re.search(r'\bDoor,\s*!-\s*Surface Type', blk):
            continue
        pm = re.search(r'([^\n,]+),\s*!-\s*Building Surface Name', blk)
        if not pm:
            continue
        parent_d = pm.group(1).strip()
        dverts = VERT_PAT.findall(blk)
        if len(dverts) < 3:
            continue
        dc = [(float(v[1]), float(v[2]), float(v[3])) for v in dverts[:4]]
        dxs = [c[0] for c in dc]; dys = [c[1] for c in dc]; dzs = [c[2] for c in dc]
        dw = (max(dys) - min(dys)) if (max(dxs) - min(dxs)) < 0.01 else (max(dxs) - min(dxs))
        dh = max(dzs) - min(dzs)
        door_area_by_wall[parent_d] = door_area_by_wall.get(parent_d, 0.0) + dw * dh

    walls_done: set = set()

    def process_block(m: re.Match) -> str:
        blk = m.group(0)
        if not re.search(r'\bWindow,\s*!-\s*Surface Type', blk):
            return blk
        pm = re.search(r'([^\n,]+),\s*!-\s*Building Surface Name', blk)
        if not pm:
            return blk
        parent = pm.group(1).strip()
        if parent not in wall_geom:
            return blk
        if parent in walls_done:
            return ''
        walls_done.add(parent)

        w = wall_geom[parent]
        xs, ys, zs = w['xs'], w['ys'], w['zs']
        x_fixed = w['x_fixed']
        z_bot, z_top = min(zs), max(zs)
        wall_h = z_top - z_bot
        margin = 0.05
        win_h = min(target_wwr * wall_h, wall_h - 2 * margin)
        z_sill = z_bot + margin
        z_head = z_sill + win_h
        if z_head > z_top - margin:
            z_head = z_top - margin
            z_sill = max(z_bot + margin, z_head - win_h)

        if x_fixed:
            ip_wall_min, ip_wall_max = min(ys), max(ys)
        else:
            ip_wall_min, ip_wall_max = min(xs), max(xs)

        # Cap win_h so window area + existing doors don't exceed wall area.
        win_w = ip_wall_max - ip_wall_min
        if win_w > 0:
            wall_area = wall_h * win_w
            door_area = door_area_by_wall.get(parent, 0.0)
            max_win_h = max(0.0, (wall_area * 0.95 - door_area) / win_w)
            win_h = min(win_h, max_win_h)
        z_head = z_sill + win_h
        if z_head > z_top - margin:
            z_head = z_top - margin

        orig_verts = VERT_PAT.findall(blk)
        if len(orig_verts) != 4:
            return blk
        orig_coords = [(float(v[1]), float(v[2]), float(v[3])) for v in orig_verts]
        orig_ip = [c[1] if x_fixed else c[0] for c in orig_coords]
        orig_ip_min = min(orig_ip); orig_ip_max = max(orig_ip)
        orig_z_mid = (min(c[2] for c in orig_coords) + max(c[2] for c in orig_coords)) / 2

        new_coords = []
        for (vx, vy, vz), oip in zip(orig_coords, orig_ip):
            t = ((oip - orig_ip_min) / (orig_ip_max - orig_ip_min) if orig_ip_max > orig_ip_min else 0.5)
            new_ip = ip_wall_min + t * (ip_wall_max - ip_wall_min)
            new_z = z_head if vz > orig_z_mid else z_sill
            new_coords.append((vx, new_ip, new_z) if x_fixed else (new_ip, vy, new_z))

        idx = [0]
        def rep_vert(mv: re.Match) -> str:
            i = idx[0]; idx[0] += 1
            if i >= 4:
                return mv.group(0)
            vx, vy, vz = new_coords[i]
            return f"{mv.group(1)}{vx:.12f},{vy:.12f},{vz:.12f}{mv.group(5)}{mv.group(6)}"

        return VERT_PAT.sub(rep_vert, blk)

    return WIN_BLOCK.sub(process_block, idf_text)


def _apply_infiltration(idf_text: str, rate: float) -> str:
    return re.sub(
        r'(\n\s+)([\d.E+\-]+),(\s+!- Flow per Exterior Surface Area \{m3/s-m2\})',
        lambda m: f"{m.group(1)}{rate:.15f},{m.group(3)}",
        idf_text,
    )


def _apply_people_density(idf_text: str, factor: float) -> str:
    """Scale Floor Area per Person by 1/factor (factor>1 = more people/m²)."""
    return re.sub(
        r'(\n\s+)([\d.E+\-]+),(\s+!- Floor Area per Person \{m2/person\})',
        lambda m: f"{m.group(1)}{float(m.group(2)) / factor:.6f},{m.group(3)}",
        idf_text,
    )


def _apply_lighting_density(idf_text: str, factor: float) -> str:
    """Scale Watts per Zone Floor Area for Lights objects."""
    return re.sub(
        r'(\n\s+)([\d.E+\-]+),(\s+!- Watts per Zone Floor Area \{W/m2\})',
        lambda m: f"{m.group(1)}{float(m.group(2)) * factor:.6f},{m.group(3)}",
        idf_text,
    )


def _apply_equip_density(idf_text: str, factor: float) -> str:
    """Scale ElectricEquipment Design Level {W} values.

    DOE prototypes use EquipmentLevel method (absolute watts), not Watts/Area.
    """
    return re.sub(
        r'(\n\s+)([\d.E+\-]+),(\s+!- Design Level \{W\})',
        lambda m: f"{m.group(1)}{float(m.group(2)) * factor:.6f},{m.group(3)}",
        idf_text,
    )


def _apply_schedule_fraction(idf_text: str, factor: float) -> str:
    """Scale fractional values in occupancy and equipment schedule blocks.

    Targets BLDG_OCC_SCH_wo_SB and BLDG_EQUIP_SCH — the schedules that
    People and ElectricEquipment objects actually reference in DOE prototypes.
    factor < 1.0 = reduced hours (e.g. 5/7 ≈ 0.714 for 5-day week).
    Values clamped to [0, 1].
    """
    target_names = re.compile(
        r'Schedule:Compact,\s*\n\s+(BLDG_OCC_SCH_wo_SB|BLDG_EQUIP_SCH)\b',
        re.IGNORECASE,
    )
    out_parts = []
    search_start = 0
    for m in target_names.finditer(idf_text):
        out_parts.append(idf_text[search_start:m.start()])
        end_m = re.search(r';', idf_text[m.end():])
        block_end = m.end() + end_m.end() if end_m else m.end() + 2000
        block = idf_text[m.start():block_end]
        # Values are inline: "Until: HH:MM,0.857778," — match after the time token
        scaled = re.sub(
            r'(Until:\s*\d+:\d+,)(0(?:\.\d+)?|1(?:\.0+)?),',
            lambda n: f"{n.group(1)}{min(float(n.group(2)) * factor, 1.0):.6f},",
            block,
        )
        out_parts.append(scaled)
        search_start = block_end
    out_parts.append(idf_text[search_start:])
    return "".join(out_parts)


def _write_variant_idf(raw_idf_path: pathlib.Path, variant_dir: pathlib.Path,
                        u_factor: float, shgc: float,
                        infil_rate: float, wwr_scale: float,
                        people_factor: float = 1.0,
                        lighting_factor: float = 1.0,
                        equip_factor: float = 1.0,
                        sched_factor: float = 1.0) -> pathlib.Path:
    text = raw_idf_path.read_text(encoding="utf-8", errors="replace")
    text = _apply_glazing(text, u_factor, shgc)
    text = _apply_infiltration(text, infil_rate)
    text = _apply_wwr_replace(text, wwr_scale)
    if people_factor != 1.0:
        text = _apply_people_density(text, people_factor)
    if lighting_factor != 1.0:
        text = _apply_lighting_density(text, lighting_factor)
    if equip_factor != 1.0:
        text = _apply_equip_density(text, equip_factor)
    if sched_factor != 1.0:
        text = _apply_schedule_fraction(text, sched_factor)
    variant_dir.mkdir(parents=True, exist_ok=True)
    out_path = variant_dir / "modified_base.idf"
    out_path.write_text(text, encoding="utf-8")
    return out_path

# ---------------------------------------------------------------------------
# Load metric helpers
# ---------------------------------------------------------------------------

def _load_metrics(q_heat: np.ndarray, q_cool: np.ndarray) -> dict:
    return {
        "peak_heat_W":    float(q_heat.max()),
        "peak_cool_W":    float(q_cool.max()),
        "annual_heat_Wh": float(q_heat.sum()),
        "annual_cool_Wh": float(q_cool.sum()),
    }


def _multipliers(variant_m: dict, baseline_m: dict) -> dict:
    eps = 1.0
    ph = variant_m["peak_heat_W"]   / max(baseline_m["peak_heat_W"],   eps)
    pc = variant_m["peak_cool_W"]   / max(baseline_m["peak_cool_W"],   eps)
    ah = variant_m["annual_heat_Wh"] / max(baseline_m["annual_heat_Wh"], eps)
    ac = variant_m["annual_cool_Wh"] / max(baseline_m["annual_cool_Wh"], eps)
    return {
        "peak_heat":    ph,
        "peak_cool":    pc,
        "annual_heat":  ah,
        "annual_cool":  ac,
        "combined_peak": (ph * pc) ** 0.5,
    }

# ---------------------------------------------------------------------------
# Main study runner (crash-safe)
# ---------------------------------------------------------------------------

def run_study(city: str, building_type: str = "medium_office",
              dry_run: bool = False) -> dict:
    """Run all variants for (building_type, city). Returns results dict.

    Crash-safe: after each simulation a partial JSON is written so at most
    one variant's work is lost on failure.
    """
    if city not in CITY_ZONE_MAP:
        sys.exit(f"Unknown city '{city}'. Available: {sorted(CITY_ZONE_MAP)}")
    if building_type not in BUILDING_TYPE_MAP:
        sys.exit(f"Unknown building '{building_type}'. Available: {sorted(BUILDING_TYPE_MAP)}")

    climate_zone, epw_name, _ = CITY_ZONE_MAP[city]
    epw_path = EPW_DIR / epw_name
    if not epw_path.exists():
        sys.exit(f"EPW not found: {epw_path}")

    raw_idf = _get_raw_idf(building_type, city)

    tag = f"{building_type}_{city}"
    final_path   = RESULTS_DIR / f"multipliers_{tag}.json"
    partial_path = RESULTS_DIR / f"multipliers_{tag}_partial.json"

    if final_path.exists():
        print(f"  SKIP {tag} — already complete ({final_path.name})")
        return json.loads(final_path.read_text())

    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from run_energyplus_loads import (
        load_idf, get_zone_names, get_zone_air_nodes,
        remove_hvac_objects, add_ideal_loads_hvac, add_output_variables,
        set_run_period_annual, patch_v22_compat, patch_simulation_control,
        run_energyplus, parse_ideal_loads_output,
    )

    idd_path = ENERGYPLUS_DIR / "Energy+.idd"
    if not idd_path.exists():
        sys.exit(f"EnergyPlus IDD not found: {idd_path}\nSet ENERGYPLUS_DIR.")
    ep_binary = ENERGYPLUS_DIR / "energyplus"
    if not ep_binary.exists():
        sys.exit(f"EnergyPlus binary not found: {ep_binary}\nSet ENERGYPLUS_DIR.")

    variants_dir = VARIANTS_DIR / tag
    ep_dir       = VARIANTS_DIR / tag / "ep_runs"

    # Build variant list (baseline first)
    variants = []
    for wwr_name, target_wwr in WWR_VARIANTS.items():
        variants.append({
            "label": wwr_name, "is_baseline": wwr_name == "wwr_20pct",
            "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC,
            "infil_rate": INFIL_BASELINE_RATE, "wwr_scale": target_wwr,
            "param": "wwr", "level": wwr_name,
        })
    for glaz_name, gv in GLAZING_VARIANTS.items():
        is_glaz_baseline = (glaz_name == "double_low_e")
        variants.append({
            "label": f"glaz_{glaz_name}", "is_baseline": False,
            "skip_simulation": is_glaz_baseline,  # baseline already run as wwr_20pct
            "u_factor": gv["u_factor"], "shgc": gv["shgc"],
            "infil_rate": INFIL_BASELINE_RATE, "wwr_scale": _BASELINE_WWR,
            "param": "glazing", "level": glaz_name,
        })
    for infil_name, rate in INFIL_VARIANTS.items():
        is_infil_baseline = (infil_name == "standard")
        variants.append({
            "label": f"infil_{infil_name}", "is_baseline": False,
            "skip_simulation": is_infil_baseline,
            "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC,
            "infil_rate": rate, "wwr_scale": _BASELINE_WWR,
            "param": "infiltration", "level": infil_name,
        })
    # --- Internal gains: people density ---
    for label, pfactor in (("people_low", 0.5), ("people_high", 2.0)):
        variants.append({
            "label": label, "is_baseline": False,
            "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC,
            "infil_rate": INFIL_BASELINE_RATE, "wwr_scale": _BASELINE_WWR,
            "people_factor": pfactor,
            "param": "people", "level": label,
        })
    # --- Internal gains: lighting power density ---
    for label, lfactor in (("lighting_low", 0.5), ("lighting_high", 1.5)):
        variants.append({
            "label": label, "is_baseline": False,
            "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC,
            "infil_rate": INFIL_BASELINE_RATE, "wwr_scale": _BASELINE_WWR,
            "lighting_factor": lfactor,
            "param": "lighting", "level": label,
        })
    # --- Internal gains: equipment / plug loads ---
    for label, efactor in (("equip_low", 0.5), ("equip_high", 2.0)):
        variants.append({
            "label": label, "is_baseline": False,
            "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC,
            "infil_rate": INFIL_BASELINE_RATE, "wwr_scale": _BASELINE_WWR,
            "equip_factor": efactor,
            "param": "equipment", "level": label,
        })
    # --- Operating schedule: 5-day week vs extended hours ---
    for label, sfactor in (("sched_5day", 5/7), ("sched_extended", 1.25)):
        variants.append({
            "label": label, "is_baseline": False,
            "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC,
            "infil_rate": INFIL_BASELINE_RATE, "wwr_scale": _BASELINE_WWR,
            "sched_factor": sfactor,
            "param": "schedule", "level": label,
        })
    variants.sort(key=lambda v: (0 if v["is_baseline"] else 1, v["label"]))

    print(f"\n=== {building_type} / {city} (zone {climate_zone}) ===")
    print(f"  IDF: {raw_idf.name}")
    print(f"  EPW: {epw_name}")
    print(f"  Variants: {[v['label'] for v in variants]}")

    if dry_run:
        for v in variants:
            print(f"  [DRY] {v['label']:25s}  U={v['u_factor']:.4f}  SHGC={v['shgc']:.3f}"
                  f"  infil={v['infil_rate']:.6f}  WWR={v['wwr_scale']:.0%}"
                  f"{'  ← baseline' if v['is_baseline'] else ''}")
        return {}

    metrics_by_label = {}
    baseline_metrics = None
    baseline_label   = None
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    def _save_partial():
        partial_path.write_text(json.dumps({
            "building_type": building_type, "city": city,
            "climate_zone": climate_zone, "status": "partial",
            "metrics_collected": {k: {
                "peak_heat_kW":    round(v["peak_heat_W"]   / 1000, 2),
                "peak_cool_kW":    round(v["peak_cool_W"]   / 1000, 2),
                "annual_heat_MWh": round(v["annual_heat_Wh"] / 1e6, 3),
                "annual_cool_MWh": round(v["annual_cool_Wh"] / 1e6, 3),
            } for k, v in metrics_by_label.items()},
        }, indent=2))

    try:
        for v in variants:
            label = v["label"]
            print(f"\n  --- {label} ---")

            # Baseline-equivalent variants (double_low_e, infil_standard) skip simulation;
            # their multipliers are 1.0 by definition since they match the wwr_20pct run.
            if v.get("skip_simulation"):
                print(f"    [BASELINE MARKER] skipping simulation — multipliers = 1.0")
                if baseline_metrics is not None:
                    metrics_by_label[label] = baseline_metrics
                # will be filled after baseline is known; deferred below
                continue

            variant_dir = variants_dir / label
            ep_out_dir  = ep_dir / label

            mod_idf = _write_variant_idf(
                raw_idf, variant_dir,
                v["u_factor"], v["shgc"], v["infil_rate"], v["wwr_scale"],
                people_factor=v.get("people_factor", 1.0),
                lighting_factor=v.get("lighting_factor", 1.0),
                equip_factor=v.get("equip_factor", 1.0),
                sched_factor=v.get("sched_factor", 1.0),
            )

            idf = load_idf(mod_idf, idd_path)
            zone_air_nodes = get_zone_air_nodes(idf)
            n_removed      = remove_hvac_objects(idf)
            zone_names     = get_zone_names(idf)
            add_ideal_loads_hvac(idf, zone_names, zone_air_nodes=zone_air_nodes)
            add_output_variables(idf, zone_names)
            set_run_period_annual(idf)
            patch_v22_compat(idf)
            patch_simulation_control(idf)

            sim_idf = variant_dir / "simulation_ready.idf"
            idf.save(str(sim_idf))
            # EP22 compat: EnclosureAveraged not supported in 22.x
            _t = sim_idf.read_text()
            if "EnclosureAveraged" in _t:
                sim_idf.write_text(_t.replace("EnclosureAveraged", "ZoneAveraged"))
            print(f"    Prepared ({n_removed} HVAC objects removed, {len(zone_names)} zones)")

            run_energyplus(sim_idf, epw_path, ep_out_dir, energyplus_dir=ENERGYPLUS_DIR)
            q_heat, q_cool = parse_ideal_loads_output(ep_out_dir, zone_names)
            m = _load_metrics(q_heat, q_cool)
            metrics_by_label[label] = m
            print(f"    heat={m['peak_heat_W']/1000:.1f}kW  cool={m['peak_cool_W']/1000:.1f}kW"
                  f"  ann_h={m['annual_heat_Wh']/1e6:.2f}MWh  ann_c={m['annual_cool_Wh']/1e6:.2f}MWh")

            if v["is_baseline"]:
                baseline_metrics = m
                baseline_label   = label
                # Fill any skip_simulation variants that came before baseline was known
                for sv in variants:
                    if sv.get("skip_simulation") and sv["label"] not in metrics_by_label:
                        metrics_by_label[sv["label"]] = m

            _save_partial()  # crash-safe: write after every simulation

    except (Exception, SystemExit) as exc:
        _save_partial()
        print(f"\n  CRASH during {tag}: {exc}")
        print(f"  Partial results saved → {partial_path}")
        raise RuntimeError(str(exc)) from exc

    if baseline_metrics is None:
        print("  WARNING: No baseline variant found.")
        return {}

    multipliers = {}
    for v in variants:
        label = v["label"]
        if label not in metrics_by_label:
            continue
        mult = _multipliers(metrics_by_label[label], baseline_metrics)
        multipliers[label] = {
            "param": v["param"], "level": v["level"],
            "u_factor": v["u_factor"], "shgc": v["shgc"],
            "infil_rate": v["infil_rate"], "wwr_scale": v["wwr_scale"],
            "peak_heat":    round(mult["peak_heat"],    4),
            "peak_cool":    round(mult["peak_cool"],    4),
            "annual_heat":  round(mult["annual_heat"],  4),
            "annual_cool":  round(mult["annual_cool"],  4),
            "combined_peak":round(mult["combined_peak"],4),
        }

    results = {
        "building_type":        building_type,
        "city":                 city,
        "climate_zone":         climate_zone,
        "idf":                  raw_idf.name,
        "epw":                  epw_name,
        "baseline_label":       baseline_label,
        "baseline_wwr":         _BASELINE_WWR,
        "baseline_u_factor":    GLAZING_BASELINE_U,
        "baseline_infil_rate":  INFIL_BASELINE_RATE,
        "raw_metrics": {k: {
            "peak_heat_kW":    round(v["peak_heat_W"]   / 1000, 2),
            "peak_cool_kW":    round(v["peak_cool_W"]   / 1000, 2),
            "annual_heat_MWh": round(v["annual_heat_Wh"] / 1e6, 3),
            "annual_cool_MWh": round(v["annual_cool_Wh"] / 1e6, 3),
        } for k, v in metrics_by_label.items()},
        "multipliers": multipliers,
    }

    final_path.write_text(json.dumps(results, indent=2))
    if partial_path.exists():
        partial_path.unlink()
    # Free disk: ep_runs dirs can be 100MB+ each; results are in the JSON
    ep_runs_dir = VARIANTS_DIR / f"{building_type}_{city}" / "ep_runs"
    if ep_runs_dir.exists():
        import shutil
        shutil.rmtree(ep_runs_dir)
    print(f"\n  Saved → {final_path.name}")
    return results


# ---------------------------------------------------------------------------
# Controlled SHGC / U-factor sensitivity study
# ---------------------------------------------------------------------------

def run_shgc_u_study(city: str, building_type: str = "medium_office",
                     dry_run: bool = False) -> dict:
    """Controlled SHGC-only and U-only sweep for (building_type, city).

    Results → data/envelope_study/results/multipliers_shgcu_{tag}.json.
    If the main study JSON exists, baseline metrics are reused from wwr_20pct
    (avoids a redundant EnergyPlus run).
    """
    if city not in CITY_ZONE_MAP:
        sys.exit(f"Unknown city '{city}'. Available: {sorted(CITY_ZONE_MAP)}")
    if building_type not in BUILDING_TYPE_MAP:
        sys.exit(f"Unknown building '{building_type}'. Available: {sorted(BUILDING_TYPE_MAP)}")

    climate_zone, epw_name, _ = CITY_ZONE_MAP[city]
    epw_path = EPW_DIR / epw_name
    if not epw_path.exists():
        sys.exit(f"EPW not found: {epw_path}")

    raw_idf = _get_raw_idf(building_type, city)

    tag          = f"{building_type}_{city}"
    final_path   = RESULTS_DIR / f"multipliers_shgcu_{tag}.json"
    partial_path = RESULTS_DIR / f"multipliers_shgcu_{tag}_partial.json"

    if final_path.exists():
        print(f"  SKIP {tag} SHGC/U sweep — already complete ({final_path.name})")
        return json.loads(final_path.read_text())

    # Build variant list — baseline first, then SHGC sweep, then U sweep.
    # Prefix labels with "shgcu_" so variant dirs never collide with run_study().
    variants = [{
        "label": "shgcu_baseline", "is_baseline": True,
        "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC,
        "infil_rate": INFIL_BASELINE_RATE, "wwr_scale": _BASELINE_WWR,
        "param": "baseline", "level": "baseline",
    }]
    for name, sv in SHGC_SWEEP_VARIANTS.items():
        variants.append({
            "label": f"shgcu_{name}", "is_baseline": False,
            "u_factor": GLAZING_BASELINE_U, "shgc": sv["shgc"],
            "infil_rate": INFIL_BASELINE_RATE, "wwr_scale": _BASELINE_WWR,
            "param": "shgc_sweep", "level": name,
        })
    for name, uv in U_SWEEP_VARIANTS.items():
        variants.append({
            "label": f"shgcu_{name}", "is_baseline": False,
            "u_factor": uv["u_factor"], "shgc": GLAZING_BASELINE_SHGC,
            "infil_rate": INFIL_BASELINE_RATE, "wwr_scale": _BASELINE_WWR,
            "param": "u_sweep", "level": name,
        })

    # Try to seed baseline metrics from the main study's wwr_20pct run.
    baseline_metrics = None
    main_path = RESULTS_DIR / f"multipliers_{tag}.json"
    if main_path.exists():
        main = json.loads(main_path.read_text())
        rm = (main.get("raw_metrics") or {}).get("wwr_20pct")
        if rm:
            baseline_metrics = {
                "peak_heat_W":    rm["peak_heat_kW"]    * 1000,
                "peak_cool_W":    rm["peak_cool_kW"]    * 1000,
                "annual_heat_Wh": rm["annual_heat_MWh"] * 1e6,
                "annual_cool_Wh": rm["annual_cool_MWh"] * 1e6,
            }
            variants[0]["skip_simulation"] = True
            print(f"  Baseline reused from {main_path.name}")

    if dry_run:
        print(f"\n=== {building_type} / {city} (zone {climate_zone}) — SHGC/U sweep ===")
        for v in variants:
            skip = " [cache]" if v.get("skip_simulation") else ""
            print(f"  [DRY] {v['label']:30s}  U={v['u_factor']:.4f}  SHGC={v['shgc']:.3f}{skip}")
        return {}

    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from run_energyplus_loads import (
        load_idf, get_zone_names, get_zone_air_nodes,
        remove_hvac_objects, add_ideal_loads_hvac, add_output_variables,
        set_run_period_annual, patch_v22_compat, patch_simulation_control,
        run_energyplus, parse_ideal_loads_output,
    )

    idd_path  = ENERGYPLUS_DIR / "Energy+.idd"
    ep_binary = ENERGYPLUS_DIR / "energyplus"
    if not idd_path.exists():
        sys.exit(f"EnergyPlus IDD not found: {idd_path}\nSet ENERGYPLUS_DIR.")
    if not ep_binary.exists():
        sys.exit(f"EnergyPlus binary not found: {ep_binary}\nSet ENERGYPLUS_DIR.")

    variants_dir = VARIANTS_DIR / tag
    print(f"\n=== {building_type} / {city} (zone {climate_zone}) — SHGC/U sweep ===")
    print(f"  IDF: {raw_idf.name}")
    print(f"  Variants: {[v['label'] for v in variants]}")

    metrics_by_label: dict = {}
    if baseline_metrics is not None:
        metrics_by_label["shgcu_baseline"] = baseline_metrics

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    def _save_partial():
        partial_path.write_text(json.dumps({
            "building_type": building_type, "city": city,
            "climate_zone": climate_zone, "status": "partial",
            "metrics_collected": {k: {
                "peak_heat_kW":    round(v["peak_heat_W"]   / 1000, 2),
                "peak_cool_kW":    round(v["peak_cool_W"]   / 1000, 2),
                "annual_heat_MWh": round(v["annual_heat_Wh"] / 1e6, 3),
                "annual_cool_MWh": round(v["annual_cool_Wh"] / 1e6, 3),
            } for k, v in metrics_by_label.items()},
        }, indent=2))

    try:
        for v in variants:
            label = v["label"]
            print(f"\n  --- {label} ---")

            if v.get("skip_simulation"):
                print("    [BASELINE REUSE] metrics from main study cache")
                continue

            variant_dir = variants_dir / label
            ep_out_dir  = variants_dir / "ep_runs" / label

            mod_idf = _write_variant_idf(
                raw_idf, variant_dir,
                v["u_factor"], v["shgc"], v["infil_rate"], v["wwr_scale"],
            )
            idf = load_idf(mod_idf, idd_path)
            zone_air_nodes = get_zone_air_nodes(idf)
            n_removed      = remove_hvac_objects(idf)
            zone_names     = get_zone_names(idf)
            add_ideal_loads_hvac(idf, zone_names, zone_air_nodes=zone_air_nodes)
            add_output_variables(idf, zone_names)
            set_run_period_annual(idf)
            patch_v22_compat(idf)
            patch_simulation_control(idf)

            sim_idf = variant_dir / "simulation_ready.idf"
            idf.save(str(sim_idf))
            _t = sim_idf.read_text()
            if "EnclosureAveraged" in _t:
                sim_idf.write_text(_t.replace("EnclosureAveraged", "ZoneAveraged"))
            print(f"    Prepared ({n_removed} HVAC removed, {len(zone_names)} zones)")

            run_energyplus(sim_idf, epw_path, ep_out_dir, energyplus_dir=ENERGYPLUS_DIR)
            q_heat, q_cool = parse_ideal_loads_output(ep_out_dir, zone_names)
            m = _load_metrics(q_heat, q_cool)
            metrics_by_label[label] = m
            print(f"    heat={m['peak_heat_W']/1000:.1f}kW  cool={m['peak_cool_W']/1000:.1f}kW"
                  f"  ann_h={m['annual_heat_Wh']/1e6:.2f}MWh  ann_c={m['annual_cool_Wh']/1e6:.2f}MWh")

            if v["is_baseline"]:
                baseline_metrics = m
            _save_partial()

    except (Exception, SystemExit) as exc:
        _save_partial()
        print(f"\n  CRASH during {tag} SHGC/U sweep: {exc}")
        raise RuntimeError(str(exc)) from exc

    if baseline_metrics is None:
        print("  WARNING: No baseline found.")
        return {}

    multipliers = {}
    for v in variants:
        label = v["label"]
        if label not in metrics_by_label:
            continue
        mult = _multipliers(metrics_by_label[label], baseline_metrics)
        multipliers[label] = {
            "param": v["param"], "level": v["level"],
            "u_factor": v["u_factor"], "shgc": v["shgc"],
            "peak_heat":     round(mult["peak_heat"],     4),
            "peak_cool":     round(mult["peak_cool"],     4),
            "annual_heat":   round(mult["annual_heat"],   4),
            "annual_cool":   round(mult["annual_cool"],   4),
            "combined_peak": round(mult["combined_peak"], 4),
        }

    results = {
        "building_type":     building_type,
        "city":              city,
        "climate_zone":      climate_zone,
        "idf":               raw_idf.name,
        "epw":               epw_name,
        "study":             "shgc_u_sensitivity",
        "baseline_label":    "shgcu_baseline",
        "baseline_u_factor": GLAZING_BASELINE_U,
        "baseline_shgc":     GLAZING_BASELINE_SHGC,
        "raw_metrics": {k: {
            "peak_heat_kW":    round(v["peak_heat_W"]   / 1000, 2),
            "peak_cool_kW":    round(v["peak_cool_W"]   / 1000, 2),
            "annual_heat_MWh": round(v["annual_heat_Wh"] / 1e6, 3),
            "annual_cool_MWh": round(v["annual_cool_Wh"] / 1e6, 3),
        } for k, v in metrics_by_label.items()},
        "multipliers": multipliers,
    }

    final_path.write_text(json.dumps(results, indent=2))
    if partial_path.exists():
        partial_path.unlink()
    print(f"\n  Saved → {final_path.name}")
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--building", default="medium_office",
                   choices=list(BUILDING_TYPE_MAP.keys()),
                   help="Building type (default: medium_office)")
    p.add_argument("--city", default="denver",
                   choices=list(CITY_ZONE_MAP.keys()),
                   help="City / climate zone representative (default: denver)")
    p.add_argument("--all-cities", action="store_true",
                   help="Run all 16 climate zone cities for the selected building type")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would run without executing EnergyPlus")
    args = p.parse_args()

    cities = sorted(CITY_ZONE_MAP.keys()) if args.all_cities else [args.city]

    for city in cities:
        run_study(city, args.building, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
