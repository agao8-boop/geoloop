# s6 Strategy — Future Optimization Questions

**Created:** 2026-06-30  
**Status:** Deferred — needs deeper thinking before implementation

---

## 1. Optimal LDC Cutoff Percentage

**The question:** The current implementation uses a fixed `ldc_cutoff_pct` (default 10%). The optimal cutoff is actually a function of:

- Marginal cost of borefield length ($/m)
- Peaker capital cost ($/kW)
- Peaker operating cost ($/kWh × annual peaker run-hours)
- Number of peaker hours at each cutoff level (from the LDC itself)
- Financing assumptions (discount rate, system lifetime)

**What the tool should eventually do:**

For each possible cutoff x% (e.g., sweep 1% to 40% in 1% steps):
- Compute borefield L(x), cost_borefield(x) from s5
- Compute peaker_kW(x), peaker_capital(x) = peaker_kW × $/kW installed
- Compute annual_peaker_energy(x) = sum(|trimmed_hours|) × $/kWh
- Total lifecycle cost(x) = cost_borefield + peaker_capital + PV(annual_peaker_energy × years)
- Find x* = argmin total_lifecycle_cost(x)

**Recommendation approach:**
- Could be pure computation (no AI needed — 40 LDC evaluations are fast)
- Could layer in AI: if user describes site constraints (e.g., "no gas available," "limited electrical service"), the AI narrows the equipment options before the cost sweep
- Could also factor in site area constraints (larger borefield → more footprint)

**What to implement now:** Fixed default (10%), user-adjustable. Record x used and show the cost breakdown so user can explore manually.

**What to add later:** A sweep function `sweep_cutoff(1, 40)` that returns a table of (x%, L, cost_borefield, peaker_kW, peaker_capital) — user can see the tradeoff curve and pick the elbow.

---

## 2. Optimal Equipment Selection

**The question:** For a given peaker capacity, what equipment is cheapest?

Equipment options (future):
| Type | Capital ($/kW) | Efficiency | Operating cost | Best for |
|---|---|---|---|---|
| Electric resistance heater | ~$50–100 | 100% (COP=1) | High | Low-use heating peaker |
| Gas boiler | ~$80–150 | 80–90% | Medium | High-use heating peaker |
| Air-source heat pump | ~$300–600 | COP 2.5–4 | Low | Medium-use either side |
| Chiller (water-cooled) | ~$150–300 | EER 14–20 | Low | Cooling peaker |
| Cooling tower | ~$50–100 | N/A | Very low | Cooling-only, outdoor |

**Current V1:** Default to electric heater (heating) and chiller (cooling). Average cost assumption.

**Future:** Let user specify equipment type or run a cost comparison table.

---

## 3. Multi-Floor / Multi-Zone Decomposition

**The question (user-noted):** The peaker capacity could be distributed across floors rather than one central unit. Smaller units on each floor might have different economics (equipment choice, installation cost) than a single large unit.

**Deferred to a later design stage.** Current tool sizes one peaker per building (total load).

---

## 4. AI-Assisted Recommendation

**The question:** Can an LLM be used to recommend the optimal combination (cutoff, equipment type, phasing) given:
- Building type and usage profile
- Utility rates (electricity, gas)
- Local equipment costs from RSMeans or similar
- Site constraints (footprint, utility capacity)

**Current position:** Not yet. The cost sweep (section 1) is pure computation and should be implemented first. Once the sweep is in place, an LLM could parse unstructured site constraint descriptions and map them to sweep parameters.
