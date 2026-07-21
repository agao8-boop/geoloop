# UX Notes — ML Integration in User Tool and Dev Dashboard

## User Tool (Production-facing)

### What the user experiences
The user never knows they're interacting with a neural network. They enter a ZIP code
and get a sizing result. The ML pipeline runs invisibly.

**Language to use in the UI:**
- ✅ "Subsurface thermal properties estimated from regional geological data"
- ✅ "Ground thermal conductivity: 2.1 W/m·K (estimated)"
- ❌ "AI-predicted" — raises questions about reliability
- ❌ "Machine learning" — irrelevant to the user's decision

**Confidence display:**
Show a subtle indicator in the result card: ● High / ● Medium / ● Low confidence.
High = county has ≥3 nearby TRT measurements in training data.
Medium = county predicted from regional geology with no local TRT.
Low = county at edge of training distribution (e.g., isolated geology).

**Fallback messaging:**
If Stage 1 predicts with high uncertainty:
"Subsurface data is estimated — actual borehole length may vary ±20%.
We recommend a thermal response test before finalizing your design."

## Dev Dashboard (Stage 1)

### Planned additions to /dev

**Section: ML Subsurface Predictions** (to add after Stage 1 training)

1. **Stage indicator** — "Stage 1 MLP (scikit-learn) active | 847 training points"
2. **CV metrics table** — k: RMSE=0.XX, MAE=0.XX, R²=0.XX | T_g: …
3. **County k prediction map** — same choropleth style as SSURGO map but showing
   ML-predicted k (for vertical boreholes, replaces the 0–2m proxy)
4. **Training data density map** — county colored by number of nearby training points
5. **Feature importance** — horizontal bar chart: which feature drove the k prediction
   (rock_class usually #1; mean_annual_temp usually #2 for T_g)
6. **Residual scatter** — ML predicted k vs. held-out TRT values (counties with TRT data only)

### Stage upgrade path
When Stage 2 CNN is ready:
- Dev dashboard shows "Stage 2 CNN active | improved accuracy near geologic boundaries"
- Same API endpoint, better numbers, no UI change needed for user

When Stage 3 PINN is ready:
- Add depth-profile visualization: T(z) and k(z) curves for a selected borehole
- This is the publishable visualization for the thesis

## Open-Loop Display

### Current state (data collected)
On `/dev` → "Groundwater Wells — Open-Loop System Reference":
- County choropleth colored by mean groundwater temperature T_gw [°C]
- Click popup: well count, mean depth, aquifer type, temperature stats
- Amber warning: open-loop requires aquifer yield + water quality assessment

### Future: open-loop sizing integration
If user selects "Open-loop system" in the tool:
1. Look up T_gw from openloop_wells_by_county.csv
2. Use Q_thermal = ṁ × Cp × ΔT to estimate required pumping rate ṁ
3. Display: "Required flow rate: X GPM at T_gw = Y°C"
4. Link to the open-loop calculation methodology from user's spreadsheet
