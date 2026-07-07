(function () {
  'use strict';

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

  function fmtInt(n) {
    return n == null ? '—' : Math.round(n).toLocaleString('en-US');
  }

  function fmtUSD(n) {
    return n == null ? '—' : '$' + Math.round(n).toLocaleString('en-US');
  }

  // ── Mode toggle (Smart / Manual) ─────────────────────────────────────
  const modeButtons = document.querySelectorAll('.mode-btn');
  const panelSmart  = document.getElementById('panel-smart');
  const panelManual = document.getElementById('panel-manual');

  modeButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      modeButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (btn.dataset.mode === 'smart') {
        panelSmart.classList.remove('hidden');
        panelManual.classList.add('hidden');
      } else {
        panelSmart.classList.add('hidden');
        panelManual.classList.remove('hidden');
      }
    });
  });

  // ── Manual mode: Tab switching ────────────────────────────────────────
  const tabBtns   = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      tabPanels.forEach(p => p.classList.add('hidden'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.remove('hidden');
    });
  });

  // ── Shared helpers ────────────────────────────────────────────────────
  function clearFieldError(forName) {
    const errEl = document.querySelector(`.field-error[data-for="${forName}"]`);
    if (errEl) errEl.textContent = '';
    const input = document.querySelector(`[name="${forName}"]`);
    if (input) input.classList.remove('input-error');
  }

  function showFieldError(fieldName, message) {
    const input = document.querySelector(`[name="${fieldName}"]`);
    if (input) input.classList.add('input-error');
    const errEl = document.querySelector(`.field-error[data-for="${fieldName}"]`);
    if (errEl) errEl.textContent = message;
  }

  // ── SMART MODE ────────────────────────────────────────────────────────
  const smartBtn     = document.getElementById('smart-btn');
  const smartError   = document.getElementById('smart-error');
  const pipelinePanel = document.getElementById('pipeline-panel');
  const smartResult  = document.getElementById('smart-result');

  function clearSmartErrors() {
    smartError.textContent = '';
    smartError.classList.add('hidden');
    ['zip_code', 'building_type', 's_NB', 's_B', 's_A'].forEach(clearFieldError);
  }

  function showSmartError(msg) {
    smartError.textContent = msg;
    smartError.classList.remove('hidden');
  }

  smartBtn.addEventListener('click', async () => {
    clearSmartErrors();
    pipelinePanel.classList.add('hidden');
    smartResult.classList.add('hidden');
    document.getElementById('cost-section').classList.add('hidden');
    document.getElementById('s6-section').classList.add('hidden');
    smartBtn.disabled = true;
    smartBtn.classList.add('loading');
    smartBtn.textContent = 'Calculating…';

    const nbRaw = document.getElementById('s_NB').value.trim();
    const body = {
      zip_code:        document.getElementById('zip_code').value.trim(),
      building_type:   document.getElementById('building_type').value,
      B:               parseFloat(document.getElementById('s_B').value),
      A:               parseFloat(document.getElementById('s_A').value),
      H_min:           parseFloat(document.getElementById('s_H_min').value) || 125,
      soil_confidence: document.getElementById('soil_confidence').value,
    };
    if (nbRaw !== '') body.NB = parseInt(nbRaw, 10);

    // optional: floor area scaling
    const floorArea = document.getElementById('floor_area_m2').value.trim();
    if (floorArea) body.floor_area_m2 = parseFloat(floorArea);

    // optional: construction year (0 = new/planned)
    const yearRaw = document.getElementById('year_built').value.trim();
    if (yearRaw !== '') body.year_built = parseInt(yearRaw, 10);

    // optional overrides
    const T_in_HP = document.getElementById('s_T_in_HP').value.trim();
    const mfls    = document.getElementById('s_mfls').value.trim();
    if (T_in_HP) body.T_in_HP = parseFloat(T_in_HP);
    if (mfls)    body.mfls    = parseFloat(mfls);

    let response, result;
    try {
      response = await fetch('/calculate/smart', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body),
      });
      result = await response.json();
    } catch (err) {
      showSmartError('Network error: ' + err.message);
      resetSmartBtn();
      return;
    }

    if (!response.ok) {
      if (result.error === 'field') {
        // Remap s_NB/s_B/s_A back to their DOM names
        const fieldMap = { NB: 's_NB', B: 's_B', A: 's_A', H_min: 's_H_min' };
        const domField = fieldMap[result.field] || result.field;
        showFieldError(domField, result.message);
      } else {
        showSmartError(result.message || 'Calculation failed.');
      }
      resetSmartBtn();
      return;
    }

    // Show pipeline trace (s1 + s2-s3 derived values)
    const site  = result.site  || {};
    const loads = result.loads || {};
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
      rockLabel  ? `<span title="SGMC bedrock class at depth">Bedrock: ${rockLabel}</span>` : null,
      soilLabel  ? `<span title="SSURGO surface soil (0–2 m)">Surface soil: ${soilLabel}</span>` : null,
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
      (site.data_available ? 'Deep borehole data available' : 'No soil data — defaults used') +
      (classLine ? `<br>${classLine}` : '') +
      kRangeLine;

    const yearFactor = loads.year_factor ?? 1;
    const yearBuilt  = loads.year_built;
    const modeLabel  = loads.mode === 'heating' ? 'heating-dominant' : 'cooling-dominant';
    const yearNote   = (yearFactor !== 1 && yearBuilt != null)
      ? `built ${yearBuilt === 0 ? 'new/planned' : yearBuilt} → ×${yearFactor.toFixed(2)} (${_vintageLabel(yearBuilt)})`
      : (yearBuilt != null ? `built ${yearBuilt === 0 ? 'new/planned' : yearBuilt} → ×1.00 (90.1-2019)` : '');
    const areaNote = loads.floor_area_m2
      ? `scaled to ${Math.round(loads.floor_area_m2)} m²`
      : '';
    const notes = [yearNote, areaNote].filter(Boolean).join(' · ');
    document.getElementById('pipeline-s2').innerHTML =
      `q<sub>h</sub> = ${loads.q_h?.toLocaleString()} W &nbsp;·&nbsp; <em>${modeLabel}</em><br>` +
      `q<sub>m</sub> = ${loads.q_m?.toLocaleString()} W<br>` +
      `q<sub>y</sub> = ${loads.q_y?.toLocaleString()} W` +
      (notes ? `<br><span style="font-size:11px;color:#666">${notes}</span>` : '');

    pipelinePanel.classList.remove('hidden');

    // Show sizing result
    document.getElementById('sres-L').textContent  = fmtInt(result.L);
    document.getElementById('sres-H').textContent  = fmtInt(result.H);
    document.getElementById('sres-NB').textContent = fmtInt(result.NB);
    const nbRange = document.getElementById('sres-NB-range');
    if (result.nb_min != null && result.nb_max != null) {
      nbRange.textContent = result.NB < result.nb_min
        ? `below footprint range ${result.nb_min}–${result.nb_max} (small load — depth-primary fallback)`
        : `optimal within footprint range ${result.nb_min}–${result.nb_max}`;
    } else {
      nbRange.textContent = 'user override';
    }

    // Two-pass sizing breakdown
    const twoPassBlock = document.getElementById('two-pass-block');
    if (result.L_heat != null && result.L_cool != null) {
      document.getElementById('sres-L-heat').textContent = fmtInt(result.L_heat);
      document.getElementById('sres-L-cool').textContent = fmtInt(result.L_cool);
      const maxL = Math.max(result.L_heat, result.L_cool, 1);
      document.getElementById('bar-L-heat').style.width =
        `${Math.max(0, result.L_heat) / maxL * 100}%`;
      document.getElementById('bar-L-cool').style.width =
        `${Math.max(0, result.L_cool) / maxL * 100}%`;
      document.getElementById('sres-governing').textContent =
        result.governing === 'heating' ? 'Heating' : 'Cooling';

      const imbalLine = document.getElementById('sres-imbalance-line');
      if (result.imbalance_m != null) {
        const imbalPct = result.L > 0 ? Math.round(result.imbalance_m / result.L * 100) : 0;
        // Direction of ground temperature drift is determined by annual net load sign
        const qy = result.loads?.q_y ?? 0;
        const direction = qy < 0
          ? 'net annual heat extraction → ground cools over time (thermal depletion)'
          : 'net annual heat injection → ground warms over time (thermal saturation)';
        imbalLine.innerHTML =
          `Thermal imbalance: <strong>${result.imbalance_m.toLocaleString()} m</strong> ` +
          `(${imbalPct}% of borefield length) — ${direction}`;
      }

      const solarLine = document.getElementById('sres-solar-line');
      if (result.solar_thermal_recommended) {
        solarLine.classList.remove('hidden');
      } else {
        solarLine.classList.add('hidden');
      }

      twoPassBlock.classList.remove('hidden');
    } else {
      twoPassBlock.classList.add('hidden');
    }

    smartResult.classList.remove('hidden');
    smartResult.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // s5: fetch cost estimate
    const siteState = result.site && result.site.state_abbrev ? result.site.state_abbrev : null;
    const B_m = parseFloat(document.getElementById('s_B').value) || 6.0;
    // Attach form-sourced building_type to result for use by s6 strategy call
    result.building_type = body.building_type;
    result.NB_user = body.NB ?? null;
    fetchCostEstimate(result.L, result.NB, B_m, siteState, result);

    resetSmartBtn();
  });

  function resetSmartBtn() {
    smartBtn.disabled    = false;
    smartBtn.classList.remove('loading');
    smartBtn.textContent = 'Calculate Borefield Size';
  }

  // ── Vintage label helper ─────────────────────────────────────────────
  function _vintageLabel(year) {
    if (year === 0)    return 'new/planned';
    if (year >= 2020)  return '~90.1-2019';
    if (year >= 2017)  return '~90.1-2016';
    if (year >= 2014)  return '~90.1-2013';
    if (year >= 2011)  return '~90.1-2010';
    if (year >= 2008)  return '~90.1-2007';
    if (year >= 2005)  return '~90.1-2004';
    if (year >= 2000)  return '~90.1-2001';
    if (year >= 1995)  return '~90.1-1989';
    if (year >= 1980)  return '~ASHRAE 90-1980';
    return 'pre-code';
  }

  function _yearToFactor(year) {
    const BP = [
      [2020, 1.00], [2017, 1.03], [2014, 1.07], [2011, 1.12],
      [2008, 1.18], [2005, 1.25], [2000, 1.30], [1995, 1.35],
      [1980, 1.42], [1960, 1.50],
    ];
    if (year === 0)    return 0.97;
    if (year >= 2020)  return 1.00;
    if (year <= 1960)  return 1.50;
    for (let i = 0; i < BP.length - 1; i++) {
      const [y1, f1] = BP[i], [y2, f2] = BP[i + 1];
      if (y2 <= year && year < y1) {
        const t = (year - y2) / (y1 - y2);
        return Math.round((f2 + t * (f1 - f2)) * 1000) / 1000;
      }
    }
    return 1.50;
  }

  // ── Year built → live vintage hint ───────────────────────────────────
  const yearBuiltEl    = document.getElementById('year_built');
  const yearFactorHint = document.getElementById('year-factor-hint');

  function updateYearHint() {
    const raw = yearBuiltEl.value.trim();
    if (raw === '') { yearFactorHint.textContent = ''; return; }
    const yr = parseInt(raw, 10);
    if (isNaN(yr) || yr < 0) { yearFactorHint.textContent = ''; return; }
    const factor = _yearToFactor(yr);
    const label  = _vintageLabel(yr);
    const pct    = factor === 1.00 ? 'prototype baseline'
                 : factor < 1.00  ? `${((1 - factor) * 100).toFixed(0)}% less load than prototype`
                 :                   `+${((factor - 1) * 100).toFixed(0)}% load vs prototype`;
    yearFactorHint.textContent = `Load factor ×${factor.toFixed(2)} — ${label} (${pct})`;
  }

  if (yearBuiltEl) {
    yearBuiltEl.addEventListener('input', updateYearHint);
    updateYearHint();
  }

  // ── Building type → prototype area hint ────────────────────────────────
  const PROTO_AREAS_M2 = {
    small_office:         511,
    medium_office:        4982,
    large_office:         46320,
    standalone_retail:    2294,
    primary_school:       6871,
    secondary_school:     19592,
    hospital:             22422,
    outpatient_healthcare:3804,
    small_hotel:          4013,
    large_hotel:          11345,
    warehouse:            4835,
    midrise_apartment:    3135,
  };

  const buildingTypeEl = document.getElementById('building_type');
  const protoAreaHint  = document.getElementById('proto-area-hint');

  function updateProtoAreaHint() {
    const area = PROTO_AREAS_M2[buildingTypeEl.value];
    if (area) {
      protoAreaHint.textContent = `DOE prototype area: ${area.toLocaleString()} m² — blank field uses this area`;
    } else {
      protoAreaHint.textContent = '';
    }
  }

  if (buildingTypeEl) {
    buildingTypeEl.addEventListener('change', updateProtoAreaHint);
    updateProtoAreaHint();
  }

  // ── MANUAL MODE ───────────────────────────────────────────────────────
  const advancedFields = ['rbore', 'rpin', 'rpext', 'kgrout', 'kpipe', 'LU', 'hconv', 'Cp'];

  function clearManualErrors() {
    document.querySelectorAll('.field-error').forEach(el => { el.textContent = ''; });
    document.querySelectorAll('.input-error').forEach(el => el.classList.remove('input-error'));
    const banner = document.getElementById('calc-error');
    banner.textContent = '';
    banner.classList.add('hidden');
  }

  function showCalcError(message) {
    const banner = document.getElementById('calc-error');
    banner.textContent = message;
    banner.classList.remove('hidden');
  }

  function collectManualInputs() {
    const fields = [
      'q_h', 'q_m', 'q_y',
      'k', 'alpha', 'T_g',
      'Cp', 'mfls', 'T_in_HP',
      'rbore', 'rpin', 'rpext', 'kgrout', 'kpipe', 'LU', 'hconv',
      'B', 'NB', 'A',
    ];
    const data = {};
    fields.forEach(name => {
      const el = document.querySelector(`#sizing-form [name="${name}"]`);
      data[name] = el ? el.value.trim() : '';
    });
    return data;
  }

  document.getElementById('calc-btn').addEventListener('click', async () => {
    clearManualErrors();
    document.getElementById('result-panel').classList.add('hidden');
    const manualBtn = document.getElementById('calc-btn');
    manualBtn.disabled = true;
    manualBtn.classList.add('loading');

    const data = collectManualInputs();

    let response, result;
    try {
      response = await fetch('/calculate', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(data),
      });
      result = await response.json();
    } catch (err) {
      showCalcError('Network error: ' + err.message);
      manualBtn.disabled = false;
      manualBtn.classList.remove('loading');
      return;
    }

    if (!response.ok) {
      if (result.error === 'field') {
        showFieldError(result.field, result.message);
        if (advancedFields.includes(result.field)) {
          document.querySelector('[data-tab="advanced"]').click();
        } else {
          document.querySelector('[data-tab="basic"]').click();
        }
      } else {
        showCalcError(result.message || 'Calculation failed.');
      }
      manualBtn.disabled = false;
      manualBtn.classList.remove('loading');
      return;
    }

    manualBtn.disabled = false;
    manualBtn.classList.remove('loading');
    document.getElementById('res-L').textContent  = result.L.toLocaleString();
    document.getElementById('res-H').textContent  = result.H.toLocaleString();
    document.getElementById('res-NB').textContent = result.NB.toLocaleString();
    document.getElementById('result-panel').classList.remove('hidden');
    document.getElementById('result-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });

  // ── s5: Cost estimate fetch and render ────────────────────────────────
  function fetchCostEstimate(L_m, NB, B_m, state, smartRes) {
    fetch('/api/cost', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({L: L_m, NB: NB, B: B_m, state: state}),
    })
    .then(r => r.json())
    .then(cost => {
      document.getElementById('cost-section').classList.remove('hidden');

      document.getElementById('cost-region-tag').textContent = cost.region_used;
      document.getElementById('cost-state-tag').textContent = state || 'National';

      document.getElementById('cost-best-pft').textContent  = '$' + cost.best.cost_per_ft.toFixed(2);
      document.getElementById('cost-best-total').textContent = fmtUSD(cost.best.total_usd);
      document.getElementById('cost-base-pft').textContent  = '$' + cost.base.cost_per_ft.toFixed(2);
      document.getElementById('cost-base-total').textContent = fmtUSD(cost.base.total_usd);
      document.getElementById('cost-worst-pft').textContent = '$' + cost.worst.cost_per_ft.toFixed(2);
      document.getElementById('cost-worst-total').textContent = fmtUSD(cost.worst.total_usd);

      const best = cost.best.total_usd, base = cost.base.total_usd, worst = cost.worst.total_usd;
      const span = Math.max(worst - best, 1);
      document.getElementById('cost-range-min').textContent = fmtUSD(best);
      document.getElementById('cost-range-max').textContent = fmtUSD(worst);
      document.getElementById('cost-range-label').textContent = fmtUSD(base) + ' expected';
      document.getElementById('cost-range-marker').style.left =
        `${Math.min(100, Math.max(0, (base - best) / span * 100))}%`;

      document.getElementById('cost-cmp-base').textContent  = '$' + cost.base.cost_per_ft.toFixed(2);
      document.getElementById('cost-cmp-best').textContent  = '$' + cost.best.cost_per_ft.toFixed(2);
      document.getElementById('cost-cmp-worst').textContent = '$' + cost.worst.cost_per_ft.toFixed(2);

      // Fetch US national avg for comparison
      fetch('/api/cost', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({L: L_m, NB: NB, B: B_m, state: 'US'}),
      })
      .then(r => r.json())
      .then(us => {
        document.getElementById('cost-cmp-us').textContent = '$' + us.base.cost_per_ft.toFixed(2);
      });

      // Populate breakdown table
      const tbody = document.getElementById('cost-breakdown-body');
      tbody.innerHTML = '';
      const labels = {
        mobilization: 'Mobilization', drilling_soil: 'Drilling (soil)',
        drilling_rock: 'Drilling (rock)', well_casing: 'Well Casing',
        sand_bag: 'Sand (bentonite)', grout_bag: 'Grout (CETCO)',
        utube_pipe: 'U-tube HDPE pipe', horiz_pipe: 'Horizontal header pipe',
        horiz_trench: 'Horizontal trench',
      };
      cost.base.breakdown.forEach(item => {
        const row = tbody.insertRow();
        row.innerHTML = `<td>${labels[item.name] || item.name}</td>
          <td>${Number(item.qty).toFixed(1)}</td>
          <td>${item.unit}</td>
          <td>$${item.rate}/LF</td>
          <td>$${Math.round(item.cost_usd).toLocaleString()}</td>`;
      });

      // s6: trigger hybrid strategy section after cost section is rendered
      if (smartRes) {
        fetchStrategy(smartRes, {B: B_m, A: parseFloat(document.getElementById('s_A').value) || 1.0});
      }
    })
    .catch(() => {}); // fail silently — sizing result still shows
  }

  // ── s6: Hybrid strategy fetch and render ─────────────────────────────
  async function fetchStrategy(smartRes, costState) {
    const s6Section = document.getElementById('s6-section');
    s6Section.classList.remove('hidden');
    document.getElementById('s6-headline').textContent = 'Calculating…';
    document.getElementById('s6-cap-note').classList.add('hidden');
    document.getElementById('s6-comparison').classList.add('hidden');

    const hMinVal = document.getElementById('s_H_min');
    const payload = {
      building_type: smartRes.building_type,
      climate_zone:  smartRes.site.climate_zone,
      k:             smartRes.site.k_effective ?? smartRes.site.k,
      alpha:         smartRes.site.alpha,
      T_g:           smartRes.site.T_g,
      B:             costState.B,
      A:             costState.A,
      H_min:         hMinVal ? parseFloat(hMinVal.value) : 125.0,
      state:         smartRes.site.state_abbrev,
      floor_area_m2: smartRes.loads.floor_area_m2 || null,
      year_factor:   smartRes.loads.year_factor || 1.0,
    };
    if (smartRes.NB_user) payload.NB = smartRes.NB_user;

    let res;
    try {
      const resp = await fetch('/api/strategy', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      res = await resp.json();
    } catch (err) {
      document.getElementById('s6-headline').textContent = 'Strategy calculation failed.';
      return;
    }

    if (!res || res.error) {
      document.getElementById('s6-headline').textContent = res && res.message ? res.message : 'Strategy calculation failed.';
      return;
    }

    const m1 = res.comparison?.m1 || {};
    const m2 = res.comparison?.m2 || {};
    const peakerLabel = res.peaker_type === 'electric_heater' ? 'electric heater'
      : res.peaker_type === 'chiller' ? 'chiller' : 'electric heater + chiller';

    document.getElementById('s6-headline').textContent =
      `Baseline borefield: ${fmtInt(res.L_before)} m. ` +
      `M1 (hours): −${m1.savings_pct ?? 0}% → ${fmtInt(m1.L_after ?? 0)} m. ` +
      `M2 (energy): −${m2.savings_pct ?? 0}% → ${fmtInt(m2.L_after ?? 0)} m.`;

    document.getElementById('s6-before-L').textContent = `${fmtInt(res.L_before)} m`;
    document.getElementById('s6-before-cost').textContent =
      `$${(res.cost_before.total_usd / 1000).toFixed(0)}k base`;
    document.getElementById('s6-after-L').textContent = m1.L_after ? `${fmtInt(m1.L_after)} m` : '—';
    document.getElementById('s6-after-cost').textContent =
      `$${(res.cost_after.total_usd / 1000).toFixed(0)}k base`;
    document.getElementById('s6-peaker-kw').textContent = `${res.peaker_kW.toFixed(1)} kW`;
    document.getElementById('s6-peaker-type').textContent = peakerLabel;

    // ASHRAE cap note
    if (res.cap_W != null) {
      document.getElementById('s6-cap-kw').textContent = (res.cap_W / 1000).toFixed(1);
      document.getElementById('s6-nb-val').textContent = res.NB;
      document.getElementById('s6-h-val').textContent = res.H_before != null ? Math.round(res.H_before) : '—';
      document.getElementById('s6-cap-note').classList.remove('hidden');
    }

    // M1 vs M2 comparison table
    if (m1.cutoff_W != null && m2.cutoff_W != null) {
      document.getElementById('s6-m1-cutoff').textContent = `${(m1.cutoff_W/1000).toFixed(1)} kW`;
      document.getElementById('s6-m2-cutoff').textContent = `${(m2.cutoff_W/1000).toFixed(1)} kW`;
      document.getElementById('s6-m1-hrs').textContent = `${m1.cutoff_h} hrs`;
      document.getElementById('s6-m2-hrs').textContent = `${m2.cutoff_h} hrs`;
      document.getElementById('s6-m1-coverage').textContent = `${m1.gshp_hours_pct}% hrs · ${m1.gshp_energy_pct}% kWh`;
      document.getElementById('s6-m2-coverage').textContent = `${m2.gshp_hours_pct}% hrs · ${m2.gshp_energy_pct}% kWh`;
      document.getElementById('s6-m1-peaker').textContent = `${m1.peaker_kW} kW`;
      document.getElementById('s6-m2-peaker').textContent = `${m2.peaker_kW} kW`;
      document.getElementById('s6-m1-L').textContent = `${fmtInt(m1.L_after)} m`;
      document.getElementById('s6-m2-L').textContent = `${fmtInt(m2.L_after)} m`;
      document.getElementById('s6-m1-save').textContent = `−${m1.savings_pct}%`;
      document.getElementById('s6-m2-save').textContent = `−${m2.savings_pct}%`;
      document.getElementById('s6-comparison').classList.remove('hidden');
    }

    _renderS6ChartA('s6-chart-a', res.hourly_profile, m1.cutoff_W, m2.cutoff_W, res.cap_W, res.dominant_mode, 220);
  }

  function _renderS6ChartA(canvasId, hourlyProfile, m1CutoffW, m2CutoffW, capW, dominantMode, heightPx) {
    // Downsample to every 4th hour (2190 bars) for compact display
    const ds = hourlyProfile.filter((_, i) => i % 4 === 0);
    const colors = ds.map(h =>
      h < 0 ? 'rgba(37,99,235,0.65)' : h > 0 ? 'rgba(220,38,38,0.55)' : 'transparent'
    );

    const cutoffDatasets = [];
    const addLine = (val, sign, color, dash, label) => {
      if (val == null) return;
      cutoffDatasets.push({
        type: 'line', label,
        data: Array(ds.length).fill(sign * val),
        borderColor: color, borderDash: dash, pointRadius: 0, borderWidth: 1.5,
      });
    };

    const heat = dominantMode === 'heating' || dominantMode === 'balanced';
    const cool = dominantMode === 'cooling' || dominantMode === 'balanced';
    if (heat) {
      addLine(capW,     -1, '#dc2626', [2, 2], `ASHRAE cap (−${(capW/1000).toFixed(1)} kW)`);
      addLine(m1CutoffW,-1, '#b45309', [6, 3], `M1 cutoff (−${(m1CutoffW/1000).toFixed(1)} kW)`);
      addLine(m2CutoffW,-1, '#0ea5e9', [3, 3], `M2 cutoff (−${(m2CutoffW/1000).toFixed(1)} kW)`);
    }
    if (cool) {
      addLine(capW,      1, '#dc2626', [2, 2], `ASHRAE cap (+${(capW/1000).toFixed(1)} kW)`);
      addLine(m1CutoffW, 1, '#b45309', [6, 3], `M1 cutoff (+${(m1CutoffW/1000).toFixed(1)} kW)`);
      addLine(m2CutoffW, 1, '#0ea5e9', [3, 3], `M2 cutoff (+${(m2CutoffW/1000).toFixed(1)} kW)`);
    }

    const canvas = document.getElementById(canvasId);
    if (canvas._chartInst) canvas._chartInst.destroy();
    canvas._chartInst = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: ds.map((_, i) => i * 4),
        datasets: [
          {
            data: ds,
            backgroundColor: colors,
            borderWidth: 0,
            label: 'Ground load',
          },
          ...cutoffDatasets,
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: {display: false},
          tooltip: {
            callbacks: {
              label: ctx => `${(ctx.raw / 1000).toFixed(1)} kW`,
            },
          },
        },
        scales: {
          x: {display: false},
          y: {
            ticks: {
              callback: v => `${(v / 1000).toFixed(0)} kW`,
              font: {family: "'Inter', sans-serif", size: 11},
              color: '#5b6b7b',
            },
            grid: {color: 'rgba(22,35,47,0.06)'},
          },
        },
      },
    });
  }

})();
