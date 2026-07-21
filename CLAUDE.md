Create a file called CLAUDE.md at the project root with the following content:

# GeoSite Advisor — Claude Code Context

## Project Purpose
AI-augmented geothermal borefield sizing tool. Replaces manual q_h/q_m/q_y
estimation with EnergyPlus-derived values. Target user: building owners
evaluating GSHP feasibility before engaging a contractor. V1: vertical
closed-loop systems only.

## Pipeline Stages
- s1_site: USGS API + GBM/XGBoost model → soil thermal conductivity k and diffusivity α
- s2_simulation: eppy + EnergyPlus → 8760h Q_heat(h) and Q_cool(h)
- s3_loads: integration → q_h, q_m, q_y (ASHRAE three-pulse inputs)
- s4_sizing: Philippe et al. (2010) equation → total borefield length L
- s5_cost: regional drilling rates → low/mid/high cost range
- s6_strategy: hybrid peak-shaving boiler, LSTM thermal projection
- s7_report: PDF output

## Key References
- Philippe et al. (2010): ASHRAE Journal 52(7):20-28
- Simulation: EnergyPlus via eppy, DOE prototype IDFs, Ideal Air Loads mode
- Sizing equation: three-pulse method, Kavanaugh and Rafferty (1995)

## Reference Materials
- data/reference/philippe_2010_sizing.xlsx: the Philippe et al. (2010) 
  ASHRAE borefield sizing spreadsheet. This is the ground truth for 
  s4_sizing. The Python implementation must produce identical outputs 
  for identical inputs.
- data/reference/390geothermal_calc.xlsx: integrated version     excel including subsurface geologies and same calculation methods with the ground truth for s4_sizing

## Stack
- Python 3.12 (system), no venv — run directly with `python3` or `flask`
- Main package: geosite/
- Tests: pytest in tests/

## Startup (run every session)
At the start of every session, check if Flask is running and start it if not:
```
lsof -i :5001 | grep LISTEN || (cd /Users/agao/Downloads/CEE299/geosite_advisor && FLASK_APP=app.py PORT=5001 flask run --host=127.0.0.1 --port=5001 &)
```
URLs: http://127.0.0.1:5001 (Flask API + UI)  |  http://127.0.0.1:5501 (Live Server landing page)