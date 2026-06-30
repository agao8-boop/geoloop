(function () {
  'use strict';

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
    smartBtn.disabled = true;
    smartBtn.textContent = 'Calculating…';

    const body = {
      zip_code:        document.getElementById('zip_code').value.trim(),
      building_type:   document.getElementById('building_type').value,
      NB:              parseFloat(document.getElementById('s_NB').value),
      B:               parseFloat(document.getElementById('s_B').value),
      A:               parseFloat(document.getElementById('s_A').value),
      soil_confidence: document.getElementById('soil_confidence').value,
    };

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
        const fieldMap = { NB: 's_NB', B: 's_B', A: 's_A' };
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
    document.getElementById('pipeline-s1').innerHTML =
      `${kLine} &nbsp;·&nbsp; α = ${site.alpha} m²/day &nbsp;·&nbsp; T<sub>g</sub> = ${site.T_g}°C<br>` +
      `Climate zone: ${site.climate_zone} &nbsp;·&nbsp; ` +
      (site.data_available ? '✓ Deep borehole data' : '⚠ No soil data');

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
    document.getElementById('sres-L').textContent  = result.L?.toLocaleString();
    document.getElementById('sres-H').textContent  = result.H?.toLocaleString();
    document.getElementById('sres-NB').textContent = result.NB?.toLocaleString();
    smartResult.classList.remove('hidden');
    smartResult.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // s5: fetch cost estimate
    const siteState = result.site && result.site.state_abbrev ? result.site.state_abbrev : null;
    const B_m = parseFloat(document.getElementById('s_B').value) || 6.0;
    fetchCostEstimate(result.L, result.NB, B_m, siteState);

    resetSmartBtn();
  });

  function resetSmartBtn() {
    smartBtn.disabled    = false;
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
      return;
    }

    document.getElementById('res-L').textContent  = result.L.toLocaleString();
    document.getElementById('res-H').textContent  = result.H.toLocaleString();
    document.getElementById('res-NB').textContent = result.NB.toLocaleString();
    document.getElementById('result-panel').classList.remove('hidden');
    document.getElementById('result-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });

  // ── s5: Cost estimate fetch and render ────────────────────────────────
  function fetchCostEstimate(L_m, NB, B_m, state) {
    fetch('/api/cost', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({L: L_m, NB: NB, B: B_m, state: state}),
    })
    .then(r => r.json())
    .then(cost => {
      document.getElementById('cost-section').classList.remove('hidden');
      const fmtTotal = (n) => '$' + Math.round(n).toLocaleString();

      document.getElementById('cost-region-tag').textContent = cost.region_used;
      document.getElementById('cost-state-tag').textContent = state || 'National';

      document.getElementById('cost-best-pft').textContent  = '$' + cost.best.cost_per_ft.toFixed(2);
      document.getElementById('cost-best-total').textContent = fmtTotal(cost.best.total_usd);
      document.getElementById('cost-base-pft').textContent  = '$' + cost.base.cost_per_ft.toFixed(2);
      document.getElementById('cost-base-total').textContent = fmtTotal(cost.base.total_usd);
      document.getElementById('cost-worst-pft').textContent = '$' + cost.worst.cost_per_ft.toFixed(2);
      document.getElementById('cost-worst-total').textContent = fmtTotal(cost.worst.total_usd);

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
    })
    .catch(() => {}); // fail silently — sizing result still shows
  }

})();
