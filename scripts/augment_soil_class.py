"""
scripts/augment_soil_class.py
─────────────────────────────────────────────────────────────────────────────
Enriches public data CSVs with rock class and soil class information:

1. Fills blank rock_class_name in deep_thermal_by_county.csv from SGMC data
   (data/ml/sgmc_by_county.csv has all 3,221 counties).
   Adds k_class_min and k_class_max columns (Clauser & Huenges 1995 ranges).

2. Creates data/public/soil_class_by_county.csv from SSURGO shallow soil data
   (data/research/subsurface/horizontal_shallow_thermal_by_county.csv).
   Columns: county_fips, shallow_soil_class, k_dry_wmpk, k_wmpk, k_sat_wmpk
─────────────────────────────────────────────────────────────────────────────
"""
import pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent

# Clauser & Huenges (1995) AGU Ref Shelf 3 — k range [W/m·K] per rock class
# (min, max) representing published range across measured samples
_CH_RANGES = {
    "alluvial_glacial":    (0.50, 2.20),
    "clay_shale":          (1.50, 3.50),
    "limestone_carbonate": (2.50, 4.00),
    "sandstone":           (1.50, 5.50),
    "granite_felsic":      (2.50, 4.50),
    "basalt_mafic":        (1.00, 3.00),
    "metamorphic":         (1.50, 4.50),
    "coal_organic":        (0.10, 0.50),
    "undifferentiated":    (1.50, 4.00),
}


def augment_deep_thermal():
    deep_path = ROOT / "data" / "public" / "deep_thermal_by_county.csv"
    sgmc_path = ROOT / "data" / "ml" / "sgmc_by_county.csv"

    deep = pd.read_csv(deep_path, dtype={"county_fips": str})
    deep["county_fips"] = deep["county_fips"].str.zfill(5)

    sgmc = pd.read_csv(sgmc_path, dtype={"county_fips": str})[
        ["county_fips", "rock_class_name"]
    ].rename(columns={"rock_class_name": "sgmc_rock_class"})
    sgmc["county_fips"] = sgmc["county_fips"].str.zfill(5)

    # Fill blank rock_class_name from SGMC for all counties
    deep = deep.merge(sgmc, on="county_fips", how="left")
    blank_mask = deep["rock_class_name"].isna() | (deep["rock_class_name"] == "")
    deep.loc[blank_mask, "rock_class_name"] = deep.loc[blank_mask, "sgmc_rock_class"]
    deep.drop(columns=["sgmc_rock_class"], inplace=True)

    # Add k_class_min and k_class_max from Clauser-Huenges ranges
    deep["k_class_min"] = deep["rock_class_name"].map(
        lambda r: _CH_RANGES.get(r, (float("nan"), float("nan")))[0]
    )
    deep["k_class_max"] = deep["rock_class_name"].map(
        lambda r: _CH_RANGES.get(r, (float("nan"), float("nan")))[1]
    )

    deep.to_csv(deep_path, index=False)
    filled = blank_mask.sum()
    print(f"deep_thermal_by_county.csv: filled {filled} blank rock_class_name rows")
    print(f"  rock_class distribution:\n{deep['rock_class_name'].value_counts().to_string()}")
    print(f"  k_class_min/max populated for {deep['k_class_min'].notna().sum()} counties")


def create_soil_class_csv():
    shallow_path = (
        ROOT / "data" / "research" / "subsurface"
        / "horizontal_shallow_thermal_by_county.csv"
    )
    out_path = ROOT / "data" / "public" / "soil_class_by_county.csv"

    shallow = pd.read_csv(shallow_path, dtype={"county_fips": str})
    shallow["county_fips"] = shallow["county_fips"].str.zfill(5)

    out = shallow[["county_fips", "soil_class", "k_dry", "k_wmpk", "k_sat"]].copy()
    out = out.rename(columns={
        "soil_class": "shallow_soil_class",
        "k_dry":      "k_dry_wmpk",
        "k_sat":      "k_sat_wmpk",
    })
    out.to_csv(out_path, index=False)
    print(f"soil_class_by_county.csv: {len(out)} counties written to {out_path}")
    print(f"  soil_class distribution:\n{out['shallow_soil_class'].value_counts().to_string()}")


if __name__ == "__main__":
    augment_deep_thermal()
    create_soil_class_csv()
