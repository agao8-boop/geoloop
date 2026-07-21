# ML Training Data Sources

## Primary Sources — Training Labels

### 1. SMU Geothermal Heat Flow Database ⭐ Most important
- **What:** ~35,000 US measurements: lat, lon, heat flow Q [mW/m²], geothermal gradient [°C/km]
  Many entries also include rock core k values from lab measurements.
- **Provides:** T_g (from gradient + surface temp), k (from Q/gradient ratio or direct lab)
- **Access:** Download from SMU Geothermal Lab → Databases → North American Heat Flow
  Script: `ml/data/collect_smuheatflow.py`
- **Caveats:** Measurements biased toward oil/gas and mining states (TX, OK, WV, CO);
  sparse in the northeast and Pacific coast

### 2. Published TRT Database (Spitler & Gehlin 2015 + state programs)
- **What:** ~500+ US Thermal Response Test results from published papers and state programs
  Each gives: lat/lon (or county), borehole depth, measured k [W/m·K], T_g [°C]
- **This is the gold-standard label for k**
- **Access:** Manual literature collection; key sources:
  - Spitler, J.D., & Gehlin, S.E.A. (2015). Thermal response testing for ground source
    heat pump systems. *Renewable and Sustainable Energy Reviews*, 50, 1125–1137.
  - Oregon IGSHPA program TRT dataset (public, ~80 PNW sites)
  - Minnesota GSHP program annual reports (public, ~60 MN sites)
  - Individual papers: "thermal response test" + state name on Google Scholar
- **Status:** To be collected manually into `data/ml/trt_database.csv`

### 3. USGS Borehole Temperature Logs (NOAA/NCEI)
- **What:** ~700 deep US borehole temperature profiles (depth vs. T curves)
  Can derive: T_g at any depth, geothermal gradient, heat flow
- **Access:** NOAA NCEI borehole temperatures dataset (public download)
- **Caveats:** Most are research boreholes in remote areas; few in urban counties

---

## Secondary Sources — Input Features

### 4. USGS State Geologic Map Compilation (SGMC)
- **What:** National bedrock geology map at 1:500,000 scale
  Contains: rock unit name, lithology description, geologic age
- **Provides:** Rock class feature (most important predictor of k)
- **Access:** USGS ScienceBase: `https://www.sciencebase.gov/catalog/item/5888bf4fe4b05ccb964bab9d`
  Script: `ml/data/collect_sgmc.py` — downloads, simplifies to 10 rock classes, spatial joins to counties
- **File produced:** `data/ml/sgmc_by_county.csv` (county_fips → rock_class_id, rock_class_name)

### 5. NOAA PRISM Climate (Mean Annual Temperature)
- **What:** 800m gridded US climate data including mean annual temperature T_mean [°C]
- **Provides:** Proxy for shallow T_g (T_gw ≈ T_mean + 1–2°C for shallow depths)
- **Access:** PRISM Climate Group API: `https://prism.oregonstate.edu/`
  For our purposes: download the 30-year normal (1991–2020) mean annual temperature grid
  and compute county centroids' values.
- **Alternative:** NOAA Climate Divisional Database (coarser but already county-level)

### 6. USGS Bouguer Gravity Anomaly
- **What:** Subsurface density variation → proxy for rock type and crustal structure
  High gravity → dense mafic rock (low k); low gravity → felsic granite (higher k)
- **Resolution:** ~1 km grid, nationally complete
- **Access:** USGS National Geophysical Data Grid
  Direct download: `https://mrdata.usgs.gov/geophysics/gravity.html`
- **File produced:** `data/ml/gravity_by_county.csv` (county_fips → bouguer_anomaly_mgal)

### 7. Sediment Thickness (USGS)
- **What:** Depth to crystalline basement [km] — tells you how deep before hitting hard rock
- **Provides:** Feature for distinguishing deep sedimentary basins (TX, WY) from thin-cover
  crystalline terranes (New England, Appalachians)
- **Access:** USGS publication, global sediment thickness grid (Laske & Masters 1997 + USGS update)
- **File produced:** `data/ml/sed_thickness_by_county.csv`

---

## File Naming Convention

All collected data goes to `data/ml/` (gitignored, populated by scripts):

```
data/ml/
├── smuheatflow_raw.csv         ← direct download from SMU
├── smuheatflow_clean.csv       ← cleaned, US only, k and T_g derived
├── trt_database.csv            ← manually assembled TRT values
├── sgmc_by_county.csv          ← rock class per county
├── prism_temp_by_county.csv    ← mean annual temperature per county centroid
├── gravity_by_county.csv       ← Bouguer anomaly per county
├── sed_thickness_by_county.csv ← depth to basement per county
└── features_all.csv            ← merged feature matrix (built by features.py)
```
