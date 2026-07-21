# Deep Borehole Thermal Properties Pipeline
**GeoSite Advisor — Technical Explanation**  
**Prepared:** June 26, 2026  
**Audience:** Project advisor / reader with engineering background but no coding experience

---

## 1. What Problem This Solves

A geothermal borehole drills 30–150 meters into the ground. To design it correctly, an engineer needs three numbers about the rock at that depth:

| Symbol | Name | Unit | Role in the design equation |
|--------|------|------|---------------------------|
| **k** | Thermal conductivity | W/m·K | How fast heat flows through rock. Higher k = shorter borehole needed. Granite (k≈3.0) needs half the footage of clay (k≈1.5). This number enters the sizing formula directly as a divisor: *L ∝ 1/k*. |
| **α** | Thermal diffusivity | m²/day | How quickly the rock responds to temperature changes. Drives the "g-function" term in the sizing equation — the ground's memory of past heat extraction. |
| **T_g** | Undisturbed ground temperature | °C | The starting temperature of the ground before the heat pump operates. The heat pump must work "against" this temperature. |

These three numbers are inputs to the **Philippe et al. (2010)** sizing equation that produces the total required borehole length. If k is wrong by 30%, the borehole length is wrong by 30%. That translates directly into a contractor quote that is 30% too short or too long.

The problem: the existing SSURGO soil database only covers the top 2 meters of soil (agricultural data). Boreholes go to 150 meters. We needed a completely different data source.

---

## 2. Why This Is Harder Than It Sounds

**The eastern United States is a data desert for deep rock measurements.**

The best national dataset of deep rock thermal conductivity comes from the Southern Methodist University (SMU) Geothermal Heat Flow Database (Blackwell & Richards 2004) — a collection of ~35,000 borehole measurements made in real wells. However:

- ~80% of those measurements are in western states: Nevada (802 measurements), New Mexico (629), Arizona (612), California (590), Oregon (446)
- Connecticut, Hawaii, Kentucky, Ohio, Wisconsin have **zero** quality measurements
- The eastern US — where most residential geothermal heat pump installations happen — is nearly unmeasured

This is why a simple "look up the nearest measurement" approach fails for most of the country.

---

## 3. The Solution: Two Parallel Tracks

The pipeline combines two independently valid methods, choosing whichever applies for each county.

### Track A — Spatial Interpolation from Measured Data (80.3% of counties)

**The method:** When enough real measurements exist nearby, use them directly.

**Input:**
- 4,567 quality A+B thermal conductivity measurements from the SMU Geothermal Heat Flow Database (Blackwell & Richards 2004)
- Each measurement is a point: latitude, longitude, and k [W/m·K] measured from a physical rock core sample taken from a real borehole
- "Quality A+B" means the well was undisturbed (no drilling fluid contamination, no recent casing work) — these are the most reliable measurements

**The technique — Inverse Distance Weighting (IDW):**
For a county centroid at a given lat/lon, the algorithm:
1. Finds all SMU measurement points within **200 km** of that centroid
2. Requires **at least 3** points (to avoid being dominated by one outlier)
3. Computes a weighted average: nearby measurements count more, distant ones count less
4. The "weight" of each measurement = 1 / (distance²) — so a point 50 km away gets 4× the weight of a point 100 km away

**Mathematically:**

$$k_{county} = \frac{\displaystyle\sum_{i=1}^{n} \frac{k_i}{d_i^2}}{\displaystyle\sum_{i=1}^{n} \frac{1}{d_i^2}}$$

where d_i is the distance to measurement point i in km, and k_i is its measured thermal conductivity.

This technique (IDW) is a standard geostatistical method. It is the same approach used by Blackwell & Richards (2004) to produce the national geothermal map of North America.

**Output per county:** k [W/m·K] and α [m²/day] (α derived from k and a rock heat capacity estimate)

**Coverage:** 2,585 out of 3,221 US counties (80.3%)

---

### Track B — Rock Type Lookup from Geological Maps (pending SGMC download)

**The method:** When there are fewer than 3 SMU measurements within 200 km, look up what type of rock is underground and use published thermal conductivity ranges for that rock type.

**Input 1 — USGS State Geologic Map Compilation (SGMC):**
The USGS published a national geological map at 1:500,000 scale (Horton 2017). This map shows, for every piece of land in the US, what category of rock exists at or near the surface and in shallow bedrock. Categories include: granite, limestone, sandstone, shale, basalt, metamorphic rock, glacial deposits, etc.

**Input 2 — Clauser & Huenges (1995) thermal conductivity table:**
Clauser & Huenges published a reference table in the American Geophysical Union (AGU) Handbook of Physical Constants giving measured ranges of k for each rock type. For example:

| Rock Type | k range [W/m·K] | Median used |
|-----------|----------------|-------------|
| Granite/felsic | 2.5 – 4.5 | 3.0 |
| Limestone/carbonate | 2.5 – 4.0 | 2.5 |
| Sandstone | 1.5 – 5.5 | 2.5 |
| Shale/clay | 1.5 – 3.5 | 2.0 |
| Basalt/mafic | 1.0 – 3.0 | 1.7 |
| Metamorphic (schist/gneiss) | 1.5 – 4.5 | 2.9 |
| Alluvial/glacial sediment | 0.2 – 2.2 | 1.5 |
| Coal/organic | 0.1 – 0.5 | 0.3 |

**The process:**
1. For each of the 3,221 US county centroids, find which SGMC polygon the point falls inside (a "spatial join" — like overlaying two maps and reading off what's at each point)
2. Map the SGMC lithology description to one of 10 simplified rock classes
3. Look up the median k and compute α from k and rock heat capacity (Banks 2008, Table A.1)

**Status:** The code is written and ready. It requires a one-time download of the SGMC GeoPackage file (~500 MB from the USGS server). Once run, it will replace the 636 counties currently using the default fallback value.

**Reference:** Clauser, C., & Huenges, E. (1995). Thermal conductivity of rocks and minerals. In Ahrens (ed.), *Rock Physics and Phase Relations: AGU Reference Shelf 3*, pp. 105–126.

---

### Default Fallback (19.7% of counties, pending Track B)

Counties that have insufficient SMU coverage (<3 points within 200 km) and have not yet been processed by the SGMC Track B pipeline receive:

- k = 2.5 W/m·K
- α = 0.098 m²/day

These are the generic rock defaults from ASHRAE (2023) *HVAC Applications*, Chapter 34, Table 1. This is a conservative mid-range value, but it does not account for local geology. These counties are concentrated in the eastern US.

---

## 4. Ground Temperature at Borehole Depth (T_g)

**The problem:** The ground gets warmer with depth. At 100 meters, the temperature is 2–3°C higher than at the surface. The heat pump's efficiency depends on this "undisturbed ground temperature."

**Method (Banks 2008, Section 2.3):**

$$T_{g,100m} = T_{surface} + 0.100 \text{ km} \times \text{gradient} \left[\frac{°C}{\text{km}}\right]$$

**T_surface** — the mean annual ground temperature at the surface — is taken from the SSURGO dataset's Kusuda & Achenbach (1965) latitude-based approximation. In simple terms: colder climates have colder ground surface temperatures. A county in Minnesota has T_surface ≈ 7°C; a county in Florida has T_surface ≈ 22°C.

**The geothermal gradient** — how fast temperature increases with depth — is estimated from the same SMU heat flow database using a second IDW interpolation (search radius 300 km). Where no SMU gradient data is available, the national default of **25°C/km** is used (Blackwell & Richards 2004 national average).

**Example:**
- Chicago (Cook County, IL): T_surface = 12°C, gradient from nearby SMU wells ≈ 32°C/km
  → T_g_100 = 12 + 0.100 × 32 = **15.2°C**
- Los Angeles County, CA: T_surface = 17°C, gradient ≈ 69°C/km (higher — geothermal zone)
  → T_g_100 = 17 + 0.100 × 69 = **23.9°C**

---

## 5. Where the County Centroid Coordinates Come From

To perform any distance-based calculation (like IDW), we need the precise location of each county. We use the **US Census Bureau 2020 County Gazetteer File**, which provides the "internal point" (INTPTLAT, INTPTLONG) — the Census Bureau's official centroid for each of the 3,221 US counties. This is a publicly available, authoritative file (~650 KB).

An earlier version of the pipeline used state-level approximate longitude (i.e., all counties in Illinois at the same longitude). That was a data quality error identified and corrected this session: it was causing distance calculations to be wrong, which skewed the IDW results.

---

## 6. Output: What the Pipeline Produces

**File:** `data/public/deep_thermal_by_county.csv`  
**Rows:** 3,221 (one per US county)  
**Columns:**

| Column | What it contains |
|--------|-----------------|
| `county_fips` | 5-digit federal FIPS code (unique county identifier) |
| `state_abbrev` | 2-letter state abbreviation |
| `county_name` | County name (from Census Gazetteer) |
| `k_wmpk` | Thermal conductivity [W/m·K] — the primary design input |
| `alpha_m2day` | Thermal diffusivity [m²/day] |
| `T_g_C` | Undisturbed ground temperature at 100 m depth [°C] |
| `k_method` | How k was determined: `SMU_IDW`, `SGMC_CH1995`, or `default` |
| `T_g_method` | How T_g was computed: `surface+SMU_grad` or `surface+default_grad` |
| `n_smu_pts_200km` | Number of SMU measurement points used in the IDW (Track A only) |
| `rock_class_name` | Geological class from SGMC (Track B only) |

**Sample values:**

| County | k [W/m·K] | T_g [°C] | Method | SMU points |
|--------|-----------|----------|--------|-----------|
| Cook County, IL (Chicago) | 3.997 | 15.2 | SMU_IDW | 10 |
| Los Angeles County, CA | 2.067 | 23.9 | SMU_IDW | 245 |
| New York County, NY (Manhattan) | 2.867 | 13.5 | SMU_IDW | 8 |
| Harris County, TX (Houston) | 2.500 | 21.5 | default | 2 |

---

## 7. How This Connects to the Rest of the Tool

When a user enters a ZIP code:

```
ZIP code (e.g., "60601")
    ↓  geocode to census tract GEOID (11-digit)
    ↓  extract county FIPS = first 5 digits
    ↓  look up row in deep_thermal_by_county.csv
    ↓  return k, α, T_g to Philippe et al. (2010) sizing equation
    ↓  output: total borehole length L [m], depth per borehole H [m]
```

The lookup file `geosite/s1_site/lookup.py` handles this. It checks the deep borehole county dataset first. If the county is not found (e.g., a US territory), it falls back to the SSURGO shallow soil data.

---

## 8. What Needs to Happen Next

**To complete the pipeline (Track B coverage):**

Run from the project directory:
```
python ml/data/collect_sgmc.py
```
This downloads the USGS SGMC geological map (~500 MB, one-time), runs a spatial join of all 3,221 county centroids against the geological polygons, and assigns each county a rock class. Then:
```
python scripts/collect_deep_thermal.py
```
Re-run to produce the final dataset with SGMC → C&H 1995 values replacing the 636 currently-default counties.

**After that, the 19.7% "default" counties will have geologically-grounded k estimates,** and the full 3,221-county national coverage will be scientifically defensible for a screening tool.

---

## 9. What This Is Not

This pipeline does not use a neural network or "machine learning" in the conventional sense (no model training, no gradient descent). It is a **geospatial data pipeline** that:

1. **Directly uses measured data** (SMU measurements) via spatial interpolation — a standard geostatistics technique
2. **Falls back to published reference tables** (C&H 1995) when measurements are sparse — the same approach used in engineering handbooks

The earlier "bootstrap ML" model (in `ml/stage1_baseline/`) was a neural network trained on the SSURGO shallow soil data. That approach was scientifically invalid because it used 0–2 m soil properties to predict 30–150 m rock properties. It has been deprecated and replaced by this pipeline.

The current method is less technically impressive than a neural network, but it is **more accurate, fully traceable to published sources, and scientifically defensible** — which matters for a design tool that produces contractor quotes.

---

## 10. References

| Reference | Role in pipeline |
|-----------|----------------|
| Blackwell, D.D., & Richards, M. (2004). *Geothermal Map of North America.* AAPG. | Source of SMU heat flow k measurements; justification for IDW method |
| Clauser, C., & Huenges, E. (1995). Thermal conductivity of rocks and minerals. *AGU Reference Shelf 3*, pp. 105–126. | Rock-type k median values for Track B |
| Banks, D. (2008). *An Introduction to Thermogeology: Ground Source Heating and Cooling.* Blackwell, 2nd ed. | ρCp values for α computation (Table A.1); T_g depth correction method (Section 2.3) |
| Horton, J.D. (2017). The State Geologic Map Compilation (SGMC) geodatabase. *USGS Data Release.* doi:10.5066/F7WH2N65 | National geological map for Track B rock classification |
| US Census Bureau (2020). County Gazetteer File. | Official county centroid coordinates (lat/lon) for all 3,221 US counties |
| Kusuda, T., & Achenbach, P.R. (1965). Earth temperature and thermal diffusivity at selected stations. *ASHRAE Transactions*, 71, 61–74. | T_surface approximation from latitude (mean annual ground temperature) |
| ASHRAE (2023). HVAC Applications, Chapter 34: Geothermal Energy. | Default k=2.5 W/m·K for undifferentiated rock (fallback value) |
| Philippe, M., et al. (2010). ASHRAE Journal 52(7):20–28. | Borefield sizing equation that consumes k, α, T_g as inputs |
