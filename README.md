# GeoSite Advisor

AI-augmented geothermal borefield sizing tool for building owners evaluating ground-source heat pump (GSHP) feasibility.

Enter your building type and location. GeoSite Advisor estimates the total borefield length needed for a vertical closed-loop GSHP system — without requiring site investigation data or EnergyPlus expertise.

---

## What It Does

1. **Site** — Looks up soil thermal properties (conductivity, diffusivity, ground temperature) for your location
2. **Building** — Estimates annual heating and cooling loads using DOE reference building models
3. **Sizing** — Applies the ASHRAE three-pulse borefield sizing method (Philippe et al. 2010) to output total borehole length and estimated cost range

---

## Quick Start (Local)

**Requirements:** Python 3.11+, pip

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/geosite-advisor.git
cd geosite-advisor

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env if needed (defaults work for local development)

# 5. Run the app
flask run
# Open http://localhost:5000
```

---

## Usage

1. Select your **building type** from the dropdown (16 DOE standard commercial types)
2. Enter your **location** (state → city → ZIP code)
3. Click **Calculate** for an instant estimate based on pre-computed data
4. Expand **Advanced Settings** to override default building parameters — this triggers a real-time EnergyPlus simulation (~15–30 seconds)

---

## References & Acknowledgements

This tool is built on published methods and open data sources. A full list is available in the app under **References**.

Key sources:
- Philippe, M., Bernier, M., & Marchio, D. (2010). Sizing Calculation Spreadsheet: Vertical Geothermal Borefields. *ASHRAE Journal*, 52(7), 20–28.
- Côté, J., & Konrad, J.-M. (2005). A generalized thermal conductivity model for soils and construction materials. *Canadian Geotechnical Journal*, 42(2), 443–458.
- U.S. DOE / NREL. *EnergyPlus Energy Simulation Software*. https://energyplus.net/
- USDA NRCS. *Soil Survey Geographic Database (SSURGO)*. https://www.nrcs.usda.gov/
- Smith, D.B., et al. (2013). *USGS Geochemical and Mineralogical Data for Soils of the Conterminous United States*. USGS DS-801.

---

## Project Status

**V1 scope:** Vertical closed-loop systems only. Commercial building types only.

This tool is under active development as part of an independent research study at Stanford University (CEE 299).

---

## License

[To be determined]
