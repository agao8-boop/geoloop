# GeoSite Advisor — References & Citations

> **Purpose:** Track every external source used in this tool — papers, datasets, APIs, software, and standards.  
> Maintaining this list makes the tool auditable and credible.  
> Add a new entry every time an external source informs a design decision, algorithm, or dataset.

---

## Borefield Sizing Methodology

### Philippe et al. (2010) — Primary sizing equation
> Philippe, M., Bernier, M., & Marchio, D. (2010). Validity ranges of three analytical solutions to heat transfer in the vicinity of single boreholes. *ASHRAE Journal*, 52(7), 20–28.

- **Used in:** `geosite/s4_sizing/ashrae_sizing.py` — `size_borefield()` function
- **What it provides:** The three-pulse borefield sizing equation; polynomial g-function coefficients for 6-hour, 1-month, and 10-year time scales; polynomial fit for the Tp borefield interaction correction
- **Reference files:** `data/reference/philippe_2010_sizing.xls`, `data/reference/390geothermal_calc.xlsx`
- **Validity range:** α ∈ [0.025, 0.2] m²/day; r_bore ∈ [0.05, 0.1] m; NB ∈ [4, 144]; A ∈ [1, 9]

### Kavanaugh & Rafferty (1995) — ASHRAE three-pulse method origin
> Kavanaugh, S., & Rafferty, K. (1995). *Ground-Source Heat Pumps: Design of Geothermal Systems for Commercial and Institutional Buildings*. American Society of Heating, Refrigerating and Air-Conditioning Engineers (ASHRAE).

- **Used in:** Conceptual basis for the three-pulse load aggregation (q_h, q_m, q_y)
- **What it provides:** Original ASHRAE ground-loop sizing methodology that Philippe et al. (2010) refines

---

## Building Energy Simulation

### EnergyPlus — Simulation engine
> U.S. Department of Energy (DOE) / National Renewable Energy Laboratory (NREL). *EnergyPlus™ Energy Simulation Software* (Version 24.x). https://energyplus.net/

- **Used in:** `geosite/s2_simulation/` — running 8760-hour building energy simulations
- **What it provides:** Whole-building thermal simulation; Ideal Air Loads outputs (Q_heat, Q_cool) at hourly resolution
- **License:** BSD-3-Clause (open source)
- **Python API:** bundled with installer at `<install_dir>/pyenergyplus/`

### DOE Commercial Prototype Building Models — Reference IDF files
> U.S. Department of Energy, Building Technologies Office. *Commercial Prototype Building Models*. https://www.energycodes.gov/prototype-building-models

- **Used in:** `geosite/s2_simulation/` — prototype IDF files as starting points for simulation
- **What it provides:** 16 validated building types × 8 ASHRAE climate zones × multiple vintage years (Pre-1980 through 90.1-2022). Default values for envelope, lighting, equipment, occupancy, HVAC.
- **Primary reference:**
  > Deru, M., Field, K., Studer, D., Benne, K., Griffith, B., Torcellini, P., … Crawley, D. (2011). *U.S. Department of Energy Commercial Reference Building Models of the National Building Stock* (NREL/TP-5500-46861). National Renewable Energy Laboratory.
- **16 building types covered:** Small Office, Medium Office, Large Office, Stand-alone Retail, Strip Mall, Quick Service Restaurant, Full Service Restaurant, Primary School, Secondary School, Outpatient Healthcare, Hospital, Small Hotel, Large Hotel, Warehouse, Mid-rise Apartment, High-rise Apartment

### eppy — EnergyPlus IDF editor
> Santosh Philip. *eppy: Scripting language for EnergyPlus idf files and output files* (v0.5.63). https://github.com/santoshphilip/eppy

- **Used in:** `geosite/s2_simulation/` — applying user overrides to prototype IDF files before simulation
- **License:** MIT

---

## Site & Soil Data

### Côté & Konrad (2005) — Ground thermal conductivity model ⭐ PRIMARY METHOD
> Côté, J., & Konrad, J.-M. (2005). A generalized thermal conductivity model for soils and construction materials. *Canadian Geotechnical Journal*, 42(2), 443–458. https://doi.org/10.1139/t04-106  
> *(Note: local file named "2011" but content confirms publication year 2005, Can. Geotech. J. 42:443–458)*

- **Used in:** `geosite/s1_site/` — computing soil thermal conductivity k and diffusivity α from USGS soil properties
- **What it provides:** A generalized model that computes k [W/m·K] from dry density, solid particle thermal conductivity, porosity, and degree of saturation
- **Confirmed in reference spreadsheet:** `390geothermal_calc.xlsx` → `prelim` sheet implements this model directly with parameters χ=0.75, η=1.2, κ=3.55, k_s=4.5 W/m·K (coarse-grained) and k_s=2.5 W/m·K (fine-grained)
- **Key equations (decoded from prelim sheet):**
  ```
  n       = 1 - ρ_d / ρ_s                         (porosity)
  k_sat   = k_s^(1−n) × k_w^n                     (saturated conductivity; k_w=0.6 W/m·K)
  k_dry   = χ × 10^(η × n)                        (dry conductivity)
  k_e     = (κ × S_r) / (1 + (κ−1) × S_r)        (Kersten number)
  k       = (k_sat − k_dry) × k_e + k_dry         (final thermal conductivity)
  α [m²/day] = k / (ρ_d × c_p) × 86400           (thermal diffusivity)
  ```
- **Soil-type parameters from paper:**

  | Soil Type | χ | η | κ | Typical k_s (W/m·K) |
  |---|---|---|---|---|
  | Coarse-grained (sand, gravel) | 0.75 | 1.2 | 3.55 | 4.5 (quartz-rich) |
  | Fine-grained (silt, clay) | 1.25 | 0.64 | 0.87 | 2.5–3.0 |
  | Organic | 0.30 | 0.87 | 0.25 | 0.5 |

### USGS SSURGO — Soil Survey Geographic Database
> U.S. Department of Agriculture, Natural Resources Conservation Service. *Soil Survey Geographic Database (SSURGO)*. https://www.nrcs.usda.gov/resources/data-and-reports/ssurgo/
> 
> API: *Soil Data Access (SDA)*. https://sdmdataaccess.sc.egov.usda.gov/

- **Used in:** `geosite/s1_site/` — querying soil properties by lat/lon to feed into Côté-Konrad model
- **What it provides (fields we use):**
  - `TEXTURE_CLASS` (sand%, silt%, clay%) → classifies as coarse/fine/organic → sets χ, η, κ, k_s
  - `DBOVENDRY_R` — oven-dry bulk density ρ_d [g/cm³]
  - `SANDTOTAL_R`, `SILTTOTAL_R`, `CLAYTOTAL_R` — particle fractions [%]
- **Coverage:** County-level; ~95% of US land area has SSURGO data; gaps in remote/federal lands
- **Spatial resolution:** Soil map units (polygons, typically 1–50 ha). Point queries by lat/lon via SDA API.
- **Query method:** REST POST to `https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest` with SQL-like queries

### USGS / NRCS — Soil thermal property estimation
> (To be added when ML/neural network training dataset for gap-filling is confirmed)

---

## Climate & Weather Data

### EnergyPlus Weather (EPW) Files — TMY3 / NSRDB
> U.S. Department of Energy. *EnergyPlus Weather Data*. https://energyplus.net/weather

- **Used in:** `geosite/s2_simulation/` — providing hourly weather inputs to EnergyPlus runs
- **Also used in:** `geosite/s1_site/` — deriving undisturbed ground temperature T_g from annual mean dry-bulb temperature
- **What it provides:** Typical Meteorological Year (TMY3) files for ~1,000+ US and international locations; 8760-hour annual weather records

---

## Standards & Codes

### ASHRAE 90.1 — Energy Standard for Buildings
> American Society of Heating, Refrigerating and Air-Conditioning Engineers. *ANSI/ASHRAE/IES Standard 90.1 — Energy Standard for Buildings Except Low-Rise Residential Buildings* (multiple editions: 2004, 2007, 2010, 2013, 2016, 2019, 2022).

- **Used in:** Prototype building model vintage selection; default envelope, lighting, and HVAC values

---

### Ahmadfard & Bernier (2021) — Updated VGHE sizing methods
> Ahmadfard, A., & Bernier, M. (2021). Sizing Vertical Ground Heat Exchangers. *ASHRAE Journal*, 63(12), 24–36.

- **Used in:** Context and methodology for the five-level (L0–L4) sizing hierarchy
- **What it provides:** Introduces GHXSizing tool with L2 (3-pulse), L3 (monthly), and L4 (hourly) methods; updates and extends Philippe et al. (2010)

### Traxler (2026) — Hybrid geothermal systems
> Traxler, D. (2026, June). Decarbonization With Hybrid Geothermal. *ASHRAE Journal*.

- **Used in:** s6_strategy — hybrid peak-shaving boiler and supplemental heating design
- **What it provides:** Design rules for hybrid heating (boiler upstream of GSHP) and hybrid cooling (dry cooler, fluid cooler, cooling tower options); boiler placement requirement; barriers to geothermal adoption

---

## To Be Added
- Ground temperature correlation source (Kusuda & Achenbach 1965 or equivalent) — for T_g from annual mean air temperature
- Neural network / ML gap-filling dataset for s1_site (future phase)
- Regional drilling cost data source (s5_cost)
