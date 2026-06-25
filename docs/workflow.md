# GeoSite Advisor — Master Pipeline Workflow

> **This is the living master plan for the full tool.**
> Every input, calculation step, equation, data source, and output is documented here.
> When the pipeline changes, update this document first. The developer dashboard at `/dev` mirrors this document.
> Use this as the reference when presenting to your advisor.

---

## Overview

**What the tool does:** Estimates the total borefield length needed for a vertical closed-loop ground-source heat pump (GSHP) system, given only a building's ZIP code and type.

**Target user:** Building owner evaluating GSHP feasibility before engaging a contractor.

**V1 scope:** Vertical closed-loop systems only. US locations only.

**Core method:** Philippe et al. (2010) ASHRAE three-pulse borefield sizing equation, driven by automatically derived soil properties and building energy loads.

---

## Full Pipeline — Pseudo-Code

```
USER INPUT
  zip_code       : string  e.g. "60601"
  building_type  : string  e.g. "small_office"  (one of 12 DOE prototypes)
  mode           : string  "heating" | "cooling"
  NB             : int     number of boreholes
  B              : float   borehole spacing [m]
  A              : float   aspect ratio (long side / short side) [-]

  ──────────────────────────────────────────────────────────────────

  [s1_site]  Location → Soil Thermal Properties
    Step 1a — Geocoding
      zip_code
        → zippopotam.us API  →  (lat, lon)
        → Census Bureau coordinates API  →  census_tract_GEOID  (11-digit string)

    Step 1b — Soil Lookup (runtime: reads pre-computed CSV)
      GEOID  →  lookup in data/public/thermal_by_tract.csv
        →  k      [W/m·K]      soil thermal conductivity
        →  alpha  [m²/day]     soil thermal diffusivity
        →  T_g    [°C]         undisturbed ground temperature
        →  climate_zone        ASHRAE climate zone (e.g. "5A")
        →  data_available      bool (False = blank on coverage map)

      IF data_available == False:
        STOP — return "No soil data for this location"

  [s2_simulation]  Building Type × Climate → Ground Loads
    Step 2a — Load Lookup (runtime: reads pre-computed JSON)
      building_type + climate_zone  →  lookup in data/public/prototype_loads.json
        →  q_h   [W]   peak hourly ground load
        →  q_m   [W]   peak monthly average ground load
        →  q_y   [W]   annual average ground load

      Sign convention (Philippe et al. 2010):
        q < 0  →  heat extraction from ground  (heating mode)
        q > 0  →  heat injection into ground   (cooling mode)

      Validate: sign(q_h) must match user's mode input

  [s3_loads]  (EnergyPlus real-time path only — not used in fast path)
    Step 3a — Hourly to Three-Pulse Aggregation
      INPUT: q_heat[8760], q_cool[8760]  from EnergyPlus Ideal Air Loads
      ground[h] = q_cool[h] - q_heat[h]   (negative=heating, positive=cooling)
      heating_dominant = sum(q_heat) >= sum(q_cool)
      q_h = min(ground)   if heating_dominant  else  max(ground)
      q_m = min(monthly_avg(ground))  if heating_dominant  else  max(monthly_avg(ground))
      q_y = mean(ground)
      month_hours = [744,672,744,720,744,720,744,744,720,744,720,744]

  [s4_sizing]  Philippe et al. (2010) ASHRAE Three-Pulse Sizing
    Step 4a — Borehole Thermal Resistance  Rb  [m·K/W]
      R_conv  = 1 / (2π · rpin · hconv)
      R_pipe  = ln(rpext/rpin) / (2π · kpipe)
      Δk      = (kgrout - k) / (kgrout + k)
      R_grout = 1/(4π·kgrout) · [ln(rbore/rpext) + ln(rbore/LU) + Δk·ln(rbore⁴/(rbore⁴-(LU/2)⁴))]
      Rb      = R_grout + (R_conv + R_pipe) / 2

    Step 4b — G-function Effective Thermal Resistances  [m·K/W]
      R_6h  = g_poly(rbore, alpha, A_F6H)  / k    (6-hour pulse)
      R_1m  = g_poly(rbore, alpha, A_F1M)  / k    (1-month pulse)
      R_10y = g_poly(rbore, alpha, A_F10Y) / k    (10-year pulse)

      where g_poly is a 10-term polynomial fit (Philippe 2010, Table 1):
        g = a₀ + a₁·rbore + a₂·rbore² + a₃·α + a₄·α² + a₅·ln(α) + a₆·ln(α)²
            + a₇·rbore·α + a₈·rbore·ln(α) + a₉·α·ln(α)

    Step 4c — Mean Fluid Temperature  Tm  [°C]
      m_dot  = mfls · |q_h| / 1000           [kg/s]  total flow rate
      T_out  = T_in_HP + q_h / (m_dot · Cp)  [°C]   fluid exit temperature
      Tm     = (T_in_HP + T_out) / 2         [°C]   mean fluid temperature

    Step 4d — Borefield Length Without Interaction  L₀  [m]
      numerator = q_y·R_10y + q_m·R_1m + q_h·R_6h + q_h·Rb
      L₀        = numerator / (Tm - T_g)

    Step 4e — Borefield Interaction Correction  Tp  [°C]  (iterative)
      H  = L / NB                        borehole depth
      x  = B / H                         spacing-to-depth ratio
      ts = H² / (9·alpha)                steady-state time [days]
      y  = ln(365.25·10 / ts)
      Tp = q_y / (2π·k·L) · polynomial(x, y, NB, A)   (37-term fit, Philippe 2010)

      Iterate until |ΔL| < 1.0 m:
        L_new = numerator / (Tm - T_g - Tp)
        Tp    = recalculate with new L_new

    Step 4f — Final Outputs
      L  =  converged total borefield length  [m]
      H  =  L / NB                            [m]   depth per borehole

OUTPUT TO USER
  L   total borefield length  [m]
  H   depth per borehole      [m]
  NB  number of boreholes     [-]

OUTPUT TO DEVELOPER (additionally shown at /dev)
  GEOID          census tract identifier
  k, alpha, T_g  soil thermal properties with source flag
  climate_zone   ASHRAE zone
  q_h, q_m, q_y  three-pulse loads with source (fixture vs EnergyPlus)
  Rb             borehole resistance
  R_6h, R_1m, R_10y  g-function resistances
  Tm             mean fluid temperature
  L₀             initial length without interaction
  Tp             temperature penalty
  all borefield geometry parameters used
```

---

## Stage-by-Stage Data Sources

### s1_site — Soil Thermal Properties

**Runtime data source:** `data/public/thermal_by_tract.csv`
- Keyed by census tract GEOID
- Columns: `geoid, k_wmpk, alpha_m2day, T_g_C, data_available`

**How the CSV is produced (developer pipeline — `scripts/`):**

| Step | Source | Output |
|---|---|---|
| Geocode GEOID | Census Bureau Coordinates API (free) | census tract GEOID |
| Soil texture | USGS SSURGO / SDA API (free) | sand%, silt%, clay%, ρ_d |
| Mineral conductivity k_s | USGS DS-801 geochemical dataset (interpolated) | quartz fraction q |
| Côté-Konrad (2005) model | see equations below | k [W/m·K], α [m²/day] |
| Ground temperature T_g | EPW annual mean air temperature | T_g [°C] |

**Côté-Konrad (2005) k computation:**
```
Given: sand%, silt%, clay%, ρ_d [g/cm³], q (quartz fraction)

n      = 1 - ρ_d / 2.65                     porosity (ρ_s = 2.65 g/cm³ for minerals)
k_s    = 7.7^q × 2.0^(1-q)                  solid conductivity (Johansen 1975)
           (if q ≤ 0.20: use 3.0^(1-q) × 7.7^q)
k_sat  = k_s^(1-n) × 0.6^n                  saturated conductivity (k_w = 0.6 W/m·K)
k_dry  = χ × 10^(-η × n)                    dry conductivity (eq. 28, Côté-Konrad 2005)
k_e    = (κ × S_r) / (1 + (κ-1) × S_r)     Kersten number (eq. 13)
k      = (k_sat - k_dry) × k_e + k_dry      final thermal conductivity

Soil type parameters (χ, η, κ) — from Côté-Konrad (2005):
  Coarse-grained (sand, gravel):  χ=1.70, η=1.80, κ_unfrozen=4.50
  Medium/fine sand:               χ=0.75, η=1.20, κ_unfrozen=3.55
  Silts and clays:                χ=0.75, η=1.20, κ_unfrozen=1.90
  Peat/organic:                   χ=0.30, η=0.87, κ_unfrozen=0.60

S_r (degree of saturation) — provisional climate-zone estimates:
  Zone 1 (hot-humid):   0.80
  Zone 2–3 (mixed):     0.70
  Zone 4–5 (cool):      0.65
  Zone 6–7 (cold):      0.60
  Zone 8 (subarctic):   0.55
  [OPEN QUESTION Q1.1 — refine with Saxton-Rawls (2006) field capacity method]

α [m²/day] = k / (ρ_d [kg/m³] × c_p [J/kg·K]) × 86400
  c_p = 750 J/kg·K (dry soil specific heat)
  ρ_d in kg/m³ = SSURGO ρ_d [g/cm³] × 1000
```

**Coverage:** Where SSURGO has no data → `data_available=False` → location appears blank on the subsurface coverage map. This gap pattern is a primary research output of this independent study.

---

### s2_simulation — Building Ground Loads

**Runtime data source:** `data/public/prototype_loads.json`
- Keyed by `building_type → climate_zone → {q_h, q_m, q_y}`

**How the JSON is produced (developer pipeline — `scripts/`):**

| Step | Tool | Detail |
|---|---|---|
| Select prototype IDF | DOE Commercial Prototype Building Models (Deru et al. 2011) | 12 building types × 8 climate zones × ASHRAE 90.1-2019 |
| Modify for climate | eppy (Python IDF editor) | Swap EPW file; apply climate-zone envelope from prototype |
| Add Ideal Air Loads | eppy | Add `ZoneHVAC:IdealLoadsAirSystem` to every zone |
| Run simulation | EnergyPlus 24.x | 8760-hour annual simulation |
| Extract outputs | EnergyPlus Python API | `Zone Ideal Loads Sensible Heating Rate` + `Zone Ideal Loads Sensible Cooling Rate` (W, hourly) |
| Aggregate to 3 pulses | s3_loads.compute_pulses() | q_h, q_m, q_y per sign convention |

**Why Ideal Air Loads?**
Ideal Air Loads removes HVAC system complexity — it directly computes the zone thermal demand without modeling a specific heating/cooling system. This gives the raw ground load the GSHP borefield must serve, which is exactly what Philippe et al. (2010) sizing equation requires.

---

### s4_sizing — Borefield Sizing

**Source:** `geosite/s4_sizing/ashrae_sizing.py`
**Reference:** Philippe et al. (2010), ASHRAE Journal 52(7):20-28
**Polynomial coefficients:** `geosite/s4_sizing/gfunction_tables.py` (extracted from reference spreadsheets)

---

## Default Parameter Values

| Parameter | Value | Description |
|---|---|---|
| `rbore` | 0.06 m | Borehole radius |
| `rpin` | 0.01365 m | Pipe inner radius |
| `rpext` | 0.0167 m | Pipe outer radius |
| `kgrout` | 1.5 W/m·K | Grout thermal conductivity |
| `kpipe` | 0.42 W/m·K | Pipe wall conductivity |
| `LU` | 0.0511 m | U-tube leg centre spacing |
| `hconv` | 1000 W/m²·K | Convection coefficient inside pipe |
| `Cp` | 4200 J/kg·K | Fluid heat capacity (water) |
| `mfls` | 0.05 kg/s·kW | Flow rate per peak load |
| `T_in_HP` (heating) | 5.0 °C | Min entering water temperature |
| `T_in_HP` (cooling) | 40.2 °C | Max entering water temperature |

---

## Open Questions

See `weekly_progress/questions.md` for the full list. Key open items affecting this workflow:

- **Q1.1** — S_r estimation: Should we use Saxton-Rawls (2006) field capacity from SSURGO texture data + aridity index correction, or keep the climate-zone lookup table?
- **Q1.2** — Quartz fraction: Is USGS DS-801 (~4,800 sample points) spatially sufficient at census-tract scale, or should we use SoilGrids 2.0 (250m global)?

---

## Future Pipeline Stages (V2+)

| Stage | What it adds |
|---|---|
| s5_cost | Regional drilling rates → low/mid/high cost range |
| s6_strategy | Hybrid peak-shaving boiler; LSTM thermal projection over system life |
| s7_report | PDF output for contractor hand-off |
| Neural network gap-fill | Fill blank census tracts using ML trained on existing SSURGO coverage |
