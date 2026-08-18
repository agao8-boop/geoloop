# Soil-Class-Aware Thermal Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface SGMC rock class + SSURGO shallow soil class + Clauser-Huenges k range bounds for all 3,221 US counties so users understand the physical basis and uncertainty of the thermal conductivity estimate used in borefield sizing.

**Architecture:** Three-layer change — (1) a data script that enriches the existing public CSVs with rock class and k range columns; (2) `SiteData` + `lookup.py` extended with new fields loaded from two new public CSVs; (3) `app.py` confidence logic updated to use physics-grounded k bounds, and `index.html`/`main.js`/`dev.html` updated to display soil class, rock class, and k range to the user.

**Tech Stack:** Python 3.12, pandas, Flask/Jinja2, vanilla JS (Chart.js already loaded), pytest.

## Global Constraints

- Python venv at `./venv`; activate with `source venv/bin/activate` before all commands.
- All new `SiteData` fields must have defaults so existing callsites (tests, app.py) do not break.
- Do NOT re-run `scripts/collect_deep_thermal.py` (requires external API calls); augment only.
- `data/public/` CSV writes must be idempotent (re-running the augment script produces the same output).
- All existing 119 tests must continue to pass after every task.
- No new pip dependencies.

---

## File Map

```
scripts/augment_soil_class.py          ← CREATE: generates the two new public CSVs
data/public/deep_thermal_by_county.csv ← MODIFY: add rock_class_name (fill blanks) + k_class_min/k_class_max cols
data/public/soil_class_by_county.csv   ← CREATE: county_fips, shallow_soil_class, k_dry_wmpk, k_wmpk, k_sat_wmpk
geosite/models.py                      ← MODIFY: 5 new optional fields on SiteData
geosite/s1_site/lookup.py              ← MODIFY: load soil_class_by_county.csv + deep k_class_min/max; populate new fields
app.py                                  ← MODIFY: site dict gets new fields; confidence uses k_min/k_max when available
static/main.js                          ← MODIFY: s1 display block shows rock_class, shallow_soil_class, k range
templates/dev.html                      ← MODIFY: s1b-out kv block gets 3 new rows
tests/test_s1_soil_class.py            ← CREATE: tests for new fields
```

---

### Task 1: Data Enrichment Script

**Files:**
- Create: `scripts/augment_soil_class.py`
- Modify: `data/public/deep_thermal_by_county.csv` (adds 3 columns)
- Create: `data/public/soil_class_by_county.csv`

**Interfaces:**
- Consumes:
  - `data/ml/sgmc_by_county.csv` (cols: `county_fips`, `rock_class_name`)
  - `data/public/deep_thermal_by_county.csv` (cols: `county_fips`, `rock_class_name` [mostly blank], all existing cols)
  - `data/research/subsurface/horizontal_shallow_thermal_by_county.csv` (cols: `county_fips`, `soil_class`, `k_dry`, `k_wmpk`, `k_sat`)
- Produces:
  - `data/public/deep_thermal_by_county.csv` with 3 new cols: `rock_class_name` (all 3221 filled), `k_class_min`, `k_class_max`
  - `data/public/soil_class_by_county.csv` with cols: `county_fips`, `shallow_soil_class`, `k_dry_wmpk`, `k_wmpk`, `k_sat_wmpk`

- [ ] **Step 1: Write the script**

Create `scripts/augment_soil_class.py`:

```python
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
```

- [ ] **Step 2: Run the script**

```bash
source venv/bin/activate
python scripts/augment_soil_class.py
```

Expected output (approximate):
```
deep_thermal_by_county.csv: filled 2585 blank rock_class_name rows
  rock_class distribution:
  alluvial_glacial       1232
  clay_shale              700
  ...
  k_class_min/max populated for 3219 counties
soil_class_by_county.csv: 3248 counties written to ...
  soil_class distribution:
  silt_clay           2292
  medium_fine_sand     891
  coarse_sand           45
```

- [ ] **Step 3: Verify CSV columns**

```bash
python3 -c "
import pandas as pd
d = pd.read_csv('data/public/deep_thermal_by_county.csv', dtype={'county_fips': str})
print('deep cols:', list(d.columns))
print('rock_class_name blanks:', d['rock_class_name'].isna().sum())
print('k_class_min not-nan:', d['k_class_min'].notna().sum())

s = pd.read_csv('data/public/soil_class_by_county.csv', dtype={'county_fips': str})
print('soil cols:', list(s.columns))
print('soil rows:', len(s))
"
```

Expected:
```
deep cols: [..., 'rock_class_name', 'k_class_min', 'k_class_max']
rock_class_name blanks: 0
k_class_min not-nan: 3219
soil cols: ['county_fips', 'shallow_soil_class', 'k_dry_wmpk', 'k_wmpk', 'k_sat_wmpk']
soil rows: 3248
```

- [ ] **Step 4: Run existing tests to confirm no regressions**

```bash
source venv/bin/activate && python -m pytest tests/ -q
```

Expected: 119 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/augment_soil_class.py data/public/deep_thermal_by_county.csv data/public/soil_class_by_county.csv
git commit -m "data: augment deep_thermal with rock class + k bounds; create soil_class_by_county"
```

---

### Task 2: Extend SiteData and lookup.py

**Files:**
- Modify: `geosite/models.py`
- Modify: `geosite/s1_site/lookup.py`
- Create: `tests/test_s1_soil_class.py`

**Interfaces:**
- Consumes: `data/public/soil_class_by_county.csv` (county_fips, shallow_soil_class, k_dry_wmpk, k_wmpk, k_sat_wmpk), `data/public/deep_thermal_by_county.csv` (rock_class_name, k_class_min, k_class_max — now populated from Task 1)
- Produces:
  - `SiteData` with 5 new optional fields: `rock_class: str`, `k_min: float`, `k_max: float`, `shallow_soil_class: str`, `k_shallow: float`
  - `lookup_by_geoid()` populates these fields from the enriched CSVs

- [ ] **Step 1: Write failing tests**

Create `tests/test_s1_soil_class.py`:

```python
"""Tests for soil-class-aware fields added to SiteData + lookup_by_geoid."""
import math
import pathlib
import pytest
from geosite.s1_site.lookup import lookup_by_geoid
from geosite.models import SiteData

FIXTURE_THERMAL  = pathlib.Path(__file__).parent.parent / "data/public/thermal_by_tract.csv"
FIXTURE_CLIMATE  = pathlib.Path(__file__).parent.parent / "data/public/climate_by_tract.csv"
FIXTURE_DEEP     = pathlib.Path(__file__).parent.parent / "data/public/deep_thermal_by_county.csv"
FIXTURE_SOIL     = pathlib.Path(__file__).parent.parent / "data/public/soil_class_by_county.csv"

VALID_ROCK_CLASSES = {
    "alluvial_glacial", "clay_shale", "limestone_carbonate", "sandstone",
    "granite_felsic", "basalt_mafic", "metamorphic", "coal_organic", "undifferentiated", "",
}
VALID_SOIL_CLASSES = {
    "silt_clay", "medium_fine_sand", "coarse_sand", "gravel_coarse_sand", "peat_organic", "",
}


def test_sitedata_has_soil_class_fields():
    """SiteData accepts new optional fields without breaking existing construction."""
    sd = SiteData(
        geoid="17031320101",
        k=2.0, alpha=0.09, T_g=14.0,
        climate_zone="5A", data_available=True,
    )
    assert sd.rock_class == ""
    assert math.isnan(sd.k_min)
    assert math.isnan(sd.k_max)
    assert sd.shallow_soil_class == ""
    assert math.isnan(sd.k_shallow)


def test_rock_class_populated_for_chicago():
    """Chicago (FIPS 17031) gets rock_class and k bounds from augmented deep CSV."""
    if not FIXTURE_DEEP.exists():
        pytest.skip("deep_thermal_by_county.csv not yet generated")
    sd = lookup_by_geoid(
        "17031320101",
        thermal_csv=FIXTURE_THERMAL,
        climate_csv=FIXTURE_CLIMATE,
        deep_csv=FIXTURE_DEEP,
    )
    assert sd.rock_class in VALID_ROCK_CLASSES
    assert not math.isnan(sd.k_min)
    assert not math.isnan(sd.k_max)
    assert sd.k_min > 0
    assert sd.k_max > sd.k_min


def test_k_bounds_bracket_or_near_county_k():
    """k_min <= k_max; county k need not be inside range (SMU measured values can exceed class median range)."""
    if not FIXTURE_DEEP.exists():
        pytest.skip("deep_thermal_by_county.csv not yet generated")
    sd = lookup_by_geoid(
        "17031320101",
        thermal_csv=FIXTURE_THERMAL,
        climate_csv=FIXTURE_CLIMATE,
        deep_csv=FIXTURE_DEEP,
    )
    assert sd.k_min < sd.k_max
    # k must be physically reasonable regardless of class range
    assert 0.3 <= sd.k <= 6.0


def test_shallow_soil_class_populated():
    """Chicago county (17031) gets shallow_soil_class and k_shallow from soil_class CSV."""
    if not FIXTURE_DEEP.exists() or not FIXTURE_SOIL.exists():
        pytest.skip("required CSV files not yet generated")
    sd = lookup_by_geoid(
        "17031320101",
        thermal_csv=FIXTURE_THERMAL,
        climate_csv=FIXTURE_CLIMATE,
        deep_csv=FIXTURE_DEEP,
    )
    assert sd.shallow_soil_class in VALID_SOIL_CLASSES
    if sd.shallow_soil_class:
        assert not math.isnan(sd.k_shallow)
        assert 0.1 <= sd.k_shallow <= 6.0


def test_unknown_geoid_empty_soil_fields():
    """GEOID with no data returns empty string soil class and nan bounds."""
    sd = lookup_by_geoid(
        "99999999999",
        thermal_csv=FIXTURE_THERMAL,
        climate_csv=FIXTURE_CLIMATE,
        deep_csv=None,
    )
    assert sd.rock_class == ""
    assert math.isnan(sd.k_min)
    assert sd.shallow_soil_class == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
source venv/bin/activate && python -m pytest tests/test_s1_soil_class.py -v 2>&1 | head -30
```

Expected: 4-5 FAILED (AttributeError on SiteData missing fields, or lookup not returning new fields).

- [ ] **Step 3: Extend SiteData in `geosite/models.py`**

Add 5 optional fields after `state_abbrev`:

```python
@dataclass
class SiteData:
    """Soil and climate properties for a census tract location."""
    geoid: str           # 11-digit census tract GEOID, e.g. "17031010200"
    k: float             # soil thermal conductivity [W/m·K]
    alpha: float         # soil thermal diffusivity [m²/day]
    T_g: float           # undisturbed ground temperature [°C]
    climate_zone: str    # ASHRAE climate zone, e.g. "5A"
    data_available: bool # False when no SSURGO data exists for this tract
    state_abbrev: str = ""  # 2-letter state abbreviation from deep_thermal_by_county.csv
    # Soil-class-aware fields (populated when deep_thermal_by_county.csv is available)
    rock_class: str = ""          # SGMC dominant rock class at depth
    k_min: float = float("nan")   # Clauser-Huenges lower bound for rock class [W/m·K]
    k_max: float = float("nan")   # Clauser-Huenges upper bound for rock class [W/m·K]
    shallow_soil_class: str = ""  # SSURGO Côté-Konrad soil class (0–2 m)
    k_shallow: float = float("nan")  # Côté-Konrad k at field saturation [W/m·K]
```

- [ ] **Step 4: Extend `lookup.py` to load the new CSV and populate new fields**

Replace the entire file content of `geosite/s1_site/lookup.py` with:

```python
"""Look up deep-borehole thermal properties by census tract GEOID.

Primary source: data/public/deep_thermal_by_county.csv
  County-level k [W/m·K], α [m²/day], T_g [°C] at 100 m borehole midpoint.
  Produced by scripts/collect_deep_thermal.py + scripts/augment_soil_class.py.
  Methods: SMU IDW (Blackwell & Richards 2004) or
           SGMC → Clauser & Huenges (1995) median k.

Fallback: data/public/thermal_by_tract.csv
  Tract-level SSURGO shallow soil properties (0–2 m).
  NOTE: Only valid for horizontal closed-loop systems — NOT for vertical
  boreholes. Used only when deep_thermal_by_county.csv is not yet generated.

County FIPS is derived from the census tract GEOID (first 5 characters).
"""

import pathlib
import pandas as pd
from geosite.models import SiteData

_DATA = pathlib.Path(__file__).parents[2] / "data" / "public"
_DEEP_COUNTY_CSV    = _DATA / "deep_thermal_by_county.csv"
_SHALLOW_TRACT_CSV  = _DATA / "thermal_by_tract.csv"
_CLIMATE_CSV        = _DATA / "climate_by_tract.csv"
_CLIMATE_COUNTY_CSV = _DATA / "climate_by_county.csv"
_SOIL_CLASS_CSV     = _DATA / "soil_class_by_county.csv"

_deep_df:         pd.DataFrame | None = None
_shallow_df:      pd.DataFrame | None = None
_climate_df:      pd.DataFrame | None = None
_climate_county_df: pd.DataFrame | None = None
_soil_class_df:   pd.DataFrame | None = None


def _load_deep() -> pd.DataFrame | None:
    global _deep_df
    if _deep_df is None and _DEEP_COUNTY_CSV.exists():
        _deep_df = pd.read_csv(_DEEP_COUNTY_CSV, dtype={"county_fips": str})
        _deep_df["county_fips"] = _deep_df["county_fips"].str.zfill(5)
    return _deep_df


def _load_shallow() -> pd.DataFrame:
    global _shallow_df
    if _shallow_df is None:
        _shallow_df = pd.read_csv(_SHALLOW_TRACT_CSV, dtype={"geoid": str})
    return _shallow_df


def _load_climate() -> pd.DataFrame:
    global _climate_df
    if _climate_df is None:
        _climate_df = pd.read_csv(_CLIMATE_CSV, dtype={"geoid": str})
    return _climate_df


def _load_climate_county() -> pd.DataFrame | None:
    global _climate_county_df
    if _climate_county_df is None and _CLIMATE_COUNTY_CSV.exists():
        _climate_county_df = pd.read_csv(_CLIMATE_COUNTY_CSV, dtype={"county_fips": str})
        _climate_county_df["county_fips"] = _climate_county_df["county_fips"].str.zfill(5)
    return _climate_county_df


def _load_soil_class() -> pd.DataFrame | None:
    global _soil_class_df
    if _soil_class_df is None and _SOIL_CLASS_CSV.exists():
        _soil_class_df = pd.read_csv(_SOIL_CLASS_CSV, dtype={"county_fips": str})
        _soil_class_df["county_fips"] = _soil_class_df["county_fips"].str.zfill(5)
    return _soil_class_df


def lookup_by_geoid(
    geoid: str,
    thermal_csv: pathlib.Path = _SHALLOW_TRACT_CSV,
    climate_csv: pathlib.Path = _CLIMATE_CSV,
    deep_csv: pathlib.Path | None = _DEEP_COUNTY_CSV,
) -> SiteData:
    """Return SiteData for a census tract GEOID.

    Looks up k, α, T_g from the deep-borehole county dataset first
    (data/public/deep_thermal_by_county.csv). Falls back to the
    SSURGO shallow tract dataset if the deep dataset is unavailable.
    """
    climate = pd.read_csv(climate_csv, dtype={"geoid": str})
    c_row = climate[climate["geoid"] == geoid]
    climate_zone = str(c_row.iloc[0]["climate_zone"]) if not c_row.empty else ""

    county_fips = geoid[:5].zfill(5)
    if not climate_zone:
        county_climate = _load_climate_county()
        if county_climate is not None:
            cc_row = county_climate[county_climate["county_fips"] == county_fips]
            if not cc_row.empty:
                climate_zone = str(cc_row.iloc[0]["climate_zone"])

    # ── Shallow soil class (always attempt; independent of deep vs. fallback path) ──
    shallow_soil_class = ""
    k_shallow = float("nan")
    soil_cls = _load_soil_class()
    if soil_cls is not None:
        sc_row = soil_cls[soil_cls["county_fips"] == county_fips]
        if not sc_row.empty:
            sc = sc_row.iloc[0]
            shallow_soil_class = str(sc["shallow_soil_class"]) if pd.notna(sc["shallow_soil_class"]) else ""
            k_shallow = float(sc["k_wmpk"]) if pd.notna(sc["k_wmpk"]) else float("nan")

    # ── Primary: deep borehole county dataset ────────────────────────────
    if deep_csv is not None and deep_csv.exists():
        deep = pd.read_csv(deep_csv, dtype={"county_fips": str})
        deep["county_fips"] = deep["county_fips"].str.zfill(5)
        d_row = deep[deep["county_fips"] == county_fips]
        if not d_row.empty:
            d = d_row.iloc[0]
            k     = float(d["k_wmpk"])     if pd.notna(d["k_wmpk"])     else float("nan")
            alpha = float(d["alpha_m2day"]) if pd.notna(d["alpha_m2day"]) else float("nan")
            T_g   = float(d["T_g_C"])      if pd.notna(d["T_g_C"])      else float("nan")
            if not (pd.isna(k) or pd.isna(alpha) or pd.isna(T_g)):
                state_abbrev = str(d["state_abbrev"]) if "state_abbrev" in d.index and pd.notna(d["state_abbrev"]) else ""
                rock_class   = str(d["rock_class_name"]) if "rock_class_name" in d.index and pd.notna(d["rock_class_name"]) else ""
                k_min        = float(d["k_class_min"]) if "k_class_min" in d.index and pd.notna(d["k_class_min"]) else float("nan")
                k_max        = float(d["k_class_max"]) if "k_class_max" in d.index and pd.notna(d["k_class_max"]) else float("nan")
                return SiteData(
                    geoid=geoid,
                    k=k,
                    alpha=alpha,
                    T_g=T_g,
                    climate_zone=climate_zone,
                    data_available=True,
                    state_abbrev=state_abbrev,
                    rock_class=rock_class,
                    k_min=k_min,
                    k_max=k_max,
                    shallow_soil_class=shallow_soil_class,
                    k_shallow=k_shallow,
                )

    # ── Fallback: shallow SSURGO tract dataset ───────────────────────────
    thermal = pd.read_csv(thermal_csv, dtype={"geoid": str})
    t_row = thermal[thermal["geoid"] == geoid]
    if t_row.empty or c_row.empty:
        return SiteData(
            geoid=geoid,
            k=float("nan"),
            alpha=float("nan"),
            T_g=float("nan"),
            climate_zone=climate_zone,
            data_available=False,
            shallow_soil_class=shallow_soil_class,
            k_shallow=k_shallow,
        )

    t = t_row.iloc[0]
    return SiteData(
        geoid=geoid,
        k=float(t["k_wmpk"]),
        alpha=float(t["alpha_m2day"]),
        T_g=float(t["T_g_C"]),
        climate_zone=climate_zone,
        data_available=bool(t["data_available"]),
        shallow_soil_class=shallow_soil_class,
        k_shallow=k_shallow,
    )
```

- [ ] **Step 5: Run all tests**

```bash
source venv/bin/activate && python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all 119 + 5 new tests pass (124 total).

- [ ] **Step 6: Commit**

```bash
git add geosite/models.py geosite/s1_site/lookup.py tests/test_s1_soil_class.py
git commit -m "feat: extend SiteData and lookup.py with rock_class, k_min/k_max, shallow_soil_class"
```

---

### Task 3: Update app.py — API response + physics-grounded confidence

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: `SiteData` with `rock_class`, `k_min`, `k_max`, `shallow_soil_class`, `k_shallow`
- Produces: `site` dict in `/api/smart` response gains 5 new keys; effective_k computed from k_min/k_max when available

- [ ] **Step 1: Write failing test for new API fields**

Add to `tests/test_s5_api.py` (open the file, find an appropriate location near existing smart-run tests, append):

```python
def test_smart_run_includes_soil_class_fields(client):
    """POST /api/smart returns rock_class, k_min, k_max, shallow_soil_class, k_shallow in site dict."""
    resp = client.post("/api/smart", json={
        "zip": "60601",
        "building_type": "medium_office",
        "NB": 10, "B": 6.0, "A": 10.0,
        "soil_confidence": "medium",
    })
    assert resp.status_code == 200
    site = resp.get_json()["site"]
    assert "rock_class" in site
    assert "k_min" in site
    assert "k_max" in site
    assert "shallow_soil_class" in site
    assert "k_shallow" in site
```

Run to confirm it fails:

```bash
source venv/bin/activate && python -m pytest tests/test_s5_api.py -k "test_smart_run_includes_soil_class" -v
```

Expected: FAILED (KeyError on `rock_class`).

- [ ] **Step 2: Update the `site` dict in `/api/smart` response**

In `app.py`, find the `return jsonify({...})` block for the smart run (around line 258). The current `"site"` dict is:

```python
"site": {
    "k": site.k,
    "k_effective": round(effective_k, 3),
    "soil_confidence": soil_confidence,
    "alpha": site.alpha,
    "T_g": site.T_g,
    "climate_zone": site.climate_zone,
    "state_abbrev": site.state_abbrev,
    "data_available": site.data_available,
},
```

Replace with:

```python
"site": {
    "k": site.k,
    "k_effective": round(effective_k, 3),
    "soil_confidence": soil_confidence,
    "alpha": site.alpha,
    "T_g": site.T_g,
    "climate_zone": site.climate_zone,
    "state_abbrev": site.state_abbrev,
    "data_available": site.data_available,
    "rock_class": site.rock_class,
    "k_min": None if (site.k_min != site.k_min) else round(site.k_min, 3),
    "k_max": None if (site.k_max != site.k_max) else round(site.k_max, 3),
    "shallow_soil_class": site.shallow_soil_class,
    "k_shallow": None if (site.k_shallow != site.k_shallow) else round(site.k_shallow, 3),
},
```

(The `x != x` idiom is the idiomatic float NaN check — no import needed.)

- [ ] **Step 3: Update the confidence logic to use k_min/k_max when available**

In `app.py`, find the confidence block (around line 188). Current code:

```python
_CONFIDENCE_K_FACTORS = {
    "high":   1.10,
    "medium": 1.00,
    "low":    0.83,
}
soil_confidence = str(data.get("soil_confidence", "low")).strip().lower()
if soil_confidence not in _CONFIDENCE_K_FACTORS:
    soil_confidence = "medium"
k_factor = _CONFIDENCE_K_FACTORS[soil_confidence]
```

And around line 243:
```python
effective_k = site.k * k_factor
```

Replace those two code regions. First block becomes:

```python
_CONFIDENCE_K_FACTORS = {
    "high":   1.10,
    "medium": 1.00,
    "low":    0.83,
}
soil_confidence = str(data.get("soil_confidence", "low")).strip().lower()
if soil_confidence not in _CONFIDENCE_K_FACTORS:
    soil_confidence = "medium"
k_factor = _CONFIDENCE_K_FACTORS[soil_confidence]
```

(Unchanged — keep fallback factors for when k_min/k_max are not available.)

The effective_k computation (line ~243) becomes:

```python
# Physics-grounded confidence: use Clauser-Huenges class bounds when available
_k_min_ok = site.k_min == site.k_min  # True when not NaN
_k_max_ok = site.k_max == site.k_max
if _k_min_ok and _k_max_ok:
    if soil_confidence == "low":
        effective_k = site.k_min
    elif soil_confidence == "high":
        # Upper bound, capped so it can't exceed 25% above county estimate
        effective_k = min(site.k_max, site.k * 1.25)
    else:
        effective_k = site.k  # medium: county estimate unchanged
else:
    effective_k = site.k * k_factor  # fallback: factor-based
```

- [ ] **Step 4: Run all tests**

```bash
source venv/bin/activate && python -m pytest tests/ -q
```

Expected: 125 passed (119 + 5 from Task 2 + 1 new).

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: expose rock_class/k_min/k_max in API; physics-grounded confidence k bounds"
```

---

### Task 4: Update UI — soil class display in index.html, main.js, dev.html

**Files:**
- Modify: `static/main.js`
- Modify: `templates/index.html`
- Modify: `templates/dev.html`

**Interfaces:**
- Consumes: `site` dict from `/api/smart` now has `rock_class`, `k_min`, `k_max`, `shallow_soil_class`, `k_shallow`, `k_effective`, `soil_confidence`
- Produces: s1 pipeline display shows rock class label, shallow soil class label, k range bar, and updated confidence note; dev tool s1b trace shows new fields

- [ ] **Step 1: Human-readable label maps**

These JS constants go into `static/main.js`. Find the beginning of the file (after the first few lines) and add:

```javascript
const ROCK_CLASS_LABELS = {
  alluvial_glacial:    'Alluvial / Glacial sediments',
  clay_shale:          'Clay / Shale',
  limestone_carbonate: 'Limestone / Carbonate',
  sandstone:           'Sandstone',
  granite_felsic:      'Granite / Felsic crystalline',
  basalt_mafic:        'Basalt / Mafic volcanic',
  metamorphic:         'Metamorphic (gneiss/schist)',
  coal_organic:        'Coal / Organic',
  undifferentiated:    'Undifferentiated bedrock',
};
const SOIL_CLASS_LABELS = {
  gravel_coarse_sand: 'Gravel / Coarse sand',
  medium_fine_sand:   'Medium-fine sand',
  coarse_sand:        'Coarse sand',
  silt_clay:          'Silt / Clay (loam)',
  peat_organic:       'Peat / Organic',
};
```

- [ ] **Step 2: Update s1 display block in `static/main.js`**

Find the existing s1 display block (around line 130–145). Current code:

```javascript
    const kEff = site.k_effective ?? site.k;
    const kRaw = site.k;
    const confLabel = { low: 'conservative', medium: 'medium', high: 'high' }[site.soil_confidence] ?? site.soil_confidence;
    const kLine = kEff !== kRaw
      ? `k = ${kRaw} W/m·K → k<sub>eff</sub> = ${kEff} W/m·K (${confLabel})`
      : `k = ${kRaw} W/m·K (${confLabel})`;
    document.getElementById('pipeline-s1').innerHTML =
      `${kLine} &nbsp;·&nbsp; α = ${site.alpha} m²/day &nbsp;·&nbsp; T<sub>g</sub> = ${site.T_g}°C<br>` +
      `Climate zone: ${site.climate_zone} &nbsp;·&nbsp; ` +
      (site.data_available ? '✓ Deep borehole data' : '⚠ No soil data');
```

Replace with:

```javascript
    const kEff = site.k_effective ?? site.k;
    const kRaw = site.k;
    const confLabel = { low: 'conservative', medium: 'medium', high: 'high' }[site.soil_confidence] ?? site.soil_confidence;
    const kLine = kEff !== kRaw
      ? `k = ${kRaw} W/m·K → k<sub>eff</sub> = ${kEff} W/m·K (${confLabel})`
      : `k = ${kRaw} W/m·K (${confLabel})`;

    // Build soil-class context line
    const rockLabel  = site.rock_class  ? (ROCK_CLASS_LABELS[site.rock_class]  || site.rock_class)  : null;
    const soilLabel  = site.shallow_soil_class ? (SOIL_CLASS_LABELS[site.shallow_soil_class] || site.shallow_soil_class) : null;
    const classLine  = [
      rockLabel  ? `<span title="SGMC bedrock class at depth">🪨 ${rockLabel}</span>` : null,
      soilLabel  ? `<span title="SSURGO surface soil (0–2 m)">🌱 ${soilLabel}</span>` : null,
    ].filter(Boolean).join(' &nbsp;·&nbsp; ');

    // k range bar: show [k_min ··· k_eff ··· k_max] if bounds available
    let kRangeLine = '';
    if (site.k_min != null && site.k_max != null) {
      const pct = v => Math.min(100, Math.max(0, ((v - site.k_min) / (site.k_max - site.k_min)) * 100));
      const markerPct = pct(kEff);
      kRangeLine = `<div style="margin-top:4px;font-size:11px;color:#555">` +
        `k range (${site.rock_class || 'rock class'}): ` +
        `<span style="color:#2563eb">${site.k_min}</span> ` +
        `<span style="display:inline-block;width:80px;height:6px;background:#e5e7eb;border-radius:3px;vertical-align:middle;position:relative">` +
        `<span style="position:absolute;left:${markerPct}%;top:-2px;width:2px;height:10px;background:#1d4ed8;border-radius:1px"></span>` +
        `</span> ` +
        `<span style="color:#dc2626">${site.k_max}</span> W/m·K</div>`;
    }

    document.getElementById('pipeline-s1').innerHTML =
      `${kLine} &nbsp;·&nbsp; α = ${site.alpha} m²/day &nbsp;·&nbsp; T<sub>g</sub> = ${site.T_g}°C<br>` +
      `Climate zone: ${site.climate_zone} &nbsp;·&nbsp; ` +
      (site.data_available ? '✓ Deep borehole data' : '⚠ No soil data') +
      (classLine ? `<br>${classLine}` : '') +
      kRangeLine;
```

- [ ] **Step 3: Update the confidence selector tooltip in `templates/index.html`**

Find the `<select>` for soil confidence (search for `t-conf` or `soil_confidence`). It currently has a plain label. Find the label or the select element and add a `title` attribute so hovering explains the physical meaning:

Find:
```html
<select id="t-conf"
```

Change to (add the title that will show on hover):
```html
<select id="t-conf" title="Low: uses rock-class lower bound (dry/loose soil) — conservative, longer borefield. Medium: county-level estimate. High: rock-class upper bound — optimistic, shorter borefield."
```

- [ ] **Step 4: Update `templates/dev.html` s1b output block**

Find (around line 1323):
```javascript
    document.getElementById('s1b-out').innerHTML =
      kv('k  (raw thermal conductivity)',     `${s.k} W/m·K`) +
      kv('k_effective  (after confidence)',   `${s.k_effective} W/m·K  [${s.soil_confidence} confidence]`, 'ok') +
      kv('α  (thermal diffusivity)',          `${s.alpha} m²/day`, 'ok') +
      kv('T_g (ground temperature)',          `${s.T_g} °C`, 'ok') +
      kv('climate_zone',                     s.climate_zone, 'ok') +
      kv('state_abbrev',                     s.state_abbrev || '(not resolved)', s.state_abbrev ? 'ok' : 'warn') +
      kv('source',                           'data/public/deep_thermal_by_county.csv') +
      kv('note',                             'k via SMU IDW (Blackwell & Richards 2004) or SGMC/C&H 1995 fallback');
```

Replace with:

```javascript
    const rockLbl = s.rock_class ? (ROCK_CLASS_LABELS[s.rock_class] || s.rock_class) : '—';
    const soilLbl = s.shallow_soil_class ? (SOIL_CLASS_LABELS[s.shallow_soil_class] || s.shallow_soil_class) : '—';
    document.getElementById('s1b-out').innerHTML =
      kv('k  (raw thermal conductivity)',     `${s.k} W/m·K`) +
      kv('k_effective  (after confidence)',   `${s.k_effective} W/m·K  [${s.soil_confidence} confidence]`, 'ok') +
      kv('k range (rock class bounds)',       s.k_min != null ? `${s.k_min} – ${s.k_max} W/m·K` : '—', s.k_min != null ? 'ok' : 'warn') +
      kv('rock class (SGMC at depth)',        `${rockLbl}  [${s.rock_class || '—'}]`, s.rock_class ? 'ok' : 'warn') +
      kv('shallow soil class (SSURGO 0–2m)', `${soilLbl}  [${s.shallow_soil_class || '—'}]`, s.shallow_soil_class ? 'ok' : 'warn') +
      kv('k_shallow (Côté-Konrad)',           s.k_shallow != null ? `${s.k_shallow} W/m·K` : '—') +
      kv('α  (thermal diffusivity)',          `${s.alpha} m²/day`, 'ok') +
      kv('T_g (ground temperature)',          `${s.T_g} °C`, 'ok') +
      kv('climate_zone',                     s.climate_zone, 'ok') +
      kv('state_abbrev',                     s.state_abbrev || '(not resolved)', s.state_abbrev ? 'ok' : 'warn') +
      kv('source',                           'deep_thermal_by_county.csv + soil_class_by_county.csv') +
      kv('note',                             'k via SMU IDW (Blackwell & Richards 2004) or SGMC/C&H 1995 fallback');
```

Note: `ROCK_CLASS_LABELS` and `SOIL_CLASS_LABELS` must also be added to `dev.html`. Find a `<script>` block in `dev.html` (near the other JS constants) and add the same two constants from Step 1 above:

```javascript
const ROCK_CLASS_LABELS = {
  alluvial_glacial:    'Alluvial / Glacial sediments',
  clay_shale:          'Clay / Shale',
  limestone_carbonate: 'Limestone / Carbonate',
  sandstone:           'Sandstone',
  granite_felsic:      'Granite / Felsic crystalline',
  basalt_mafic:        'Basalt / Mafic volcanic',
  metamorphic:         'Metamorphic (gneiss/schist)',
  coal_organic:        'Coal / Organic',
  undifferentiated:    'Undifferentiated bedrock',
};
const SOIL_CLASS_LABELS = {
  gravel_coarse_sand: 'Gravel / Coarse sand',
  medium_fine_sand:   'Medium-fine sand',
  coarse_sand:        'Coarse sand',
  silt_clay:          'Silt / Clay (loam)',
  peat_organic:       'Peat / Organic',
};
```

- [ ] **Step 5: Run all tests**

```bash
source venv/bin/activate && python -m pytest tests/ -q
```

Expected: 125 passed.

- [ ] **Step 6: Manual smoke test**

```bash
# Server should already be running; if not:
source venv/bin/activate && FLASK_APP=app.py flask run --port 5001 &
sleep 2

# Curl the smart endpoint for Chicago ZIP
curl -s -X POST http://localhost:5001/api/smart \
  -H "Content-Type: application/json" \
  -d '{"zip":"60601","building_type":"medium_office","NB":10,"B":6.0,"A":10.0,"soil_confidence":"low"}' \
  | python3 -m json.tool | grep -A 10 '"site"'
```

Expected (approximate):
```json
"site": {
    "k": 3.997,
    "k_effective": 1.5,
    "soil_confidence": "low",
    ...
    "rock_class": "alluvial_glacial",
    "k_min": 0.5,
    "k_max": 2.2,
    "shallow_soil_class": "silt_clay",
    "k_shallow": 1.31
}
```

Open http://localhost:5001 in browser, enter ZIP 60601, medium office, click Calculate. Verify:
- s1 section shows rock class label ("Alluvial / Glacial sediments") and shallow soil label ("Silt / Clay (loam)")
- k range bar visible between 0.5–2.2 W/m·K with marker on k_eff

Open http://localhost:5001/dev, run a trace. Verify:
- s1b-out shows `rock class`, `k range`, `shallow soil class`, `k_shallow` rows

- [ ] **Step 7: Commit**

```bash
git add static/main.js templates/index.html templates/dev.html
git commit -m "feat: display rock class, shallow soil class, and k range bar in s1 UI"
```
