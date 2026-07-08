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

  // ── SMART MODE: staged wizard ─────────────────────────────────────────
  let stage1Result = null;
  let lastStage2Result = null;
  let lastCostResult = null;
  let lastStrategyResult = null;

  // Body key → input id for Smart Advanced overrides; blank = server default
  const SMART_ADV_FIELDS = {
    T_in_HP_heat: 's_T_in_HP_heat',
    T_in_HP_cool: 's_T_in_HP_cool',
    mfls:  's_mfls',
    Cp:    's_Cp',
    rbore: 's_rbore',
    rpin:  's_rpin',
    rpext: 's_rpext',
    kgrout:'s_kgrout',
    kpipe: 's_kpipe',
    LU:    's_LU',
    hconv: 's_hconv',
  };

  function applySmartAdvOverrides(body) {
    Object.entries(SMART_ADV_FIELDS).forEach(([key, id]) => {
      const raw = document.getElementById(id).value.trim();
      if (raw !== '') body[key] = parseFloat(raw);
    });
  }

  const stage1Btn    = document.getElementById('stage1-btn');
  const stage2Btn    = document.getElementById('stage2-btn');
  const stage1Error  = document.getElementById('stage1-error');
  const stage2Error  = document.getElementById('stage2-error');
  const step1Status  = document.getElementById('step1-status');
  const step2Status  = document.getElementById('step2-status');
  const wizardStep2  = document.getElementById('wizard-step2');
  const stage1Panel  = document.getElementById('stage1-result');
  const smartResult  = document.getElementById('smart-result');

  const STAGE1_INPUT_IDS = ['zip_code', 'soil_confidence', 'building_type',
                            'floor_area_m2', 'year_built',
                            's_wwr', 's_envelope', 's_glazing'];

  function unlockStep2() {
    wizardStep2.classList.remove('step-locked');
    stage2Btn.disabled = false;
    step2Status.textContent = '';
    step1Status.textContent = 'Complete';
    step1Status.classList.add('done');
  }

  function lockStep2() {
    wizardStep2.classList.add('step-locked');
    stage2Btn.disabled = true;
    step2Status.textContent = 'Complete Step 1 to unlock';
    step1Status.textContent = '';
    step1Status.classList.remove('done');
  }

  function invalidateStage1() {
    if (stage1Result === null) return;
    stage1Result = null;
    lastStage2Result = null;
    lastCostResult = null;
    lastStrategyResult = null;
    lockStep2();
    stage1Panel.classList.add('hidden');
    smartResult.classList.add('hidden');
    document.getElementById('cost-section').classList.add('hidden');
    document.getElementById('s6-section').classList.add('hidden');
    document.getElementById('s7-section').classList.add('hidden');
    document.getElementById('s7-report').classList.add('hidden');
  }

  STAGE1_INPUT_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('input', invalidateStage1);
      el.addEventListener('change', invalidateStage1);
    }
  });

  document.getElementById('expert-nb-enable').addEventListener('change', e => {
    document.getElementById('s_NB').disabled = !e.target.checked;
    if (!e.target.checked) document.getElementById('s_NB').value = '';
  });

  function showStage1Error(msg) {
    stage1Error.textContent = msg;
    stage1Error.classList.remove('hidden');
  }

  function showStage2Error(msg) {
    stage2Error.textContent = msg;
    stage2Error.classList.remove('hidden');
  }

  function resetStage1Btn() {
    stage1Btn.disabled = false;
    stage1Btn.classList.remove('loading');
    stage1Btn.textContent = 'Analyze Site & Loads →';
  }

  function resetStage2Btn() {
    stage2Btn.disabled = stage1Result === null;
    stage2Btn.classList.remove('loading');
    stage2Btn.textContent = 'Size Borefield →';
  }

  function collectStage1Body() {
    const body = {
      zip_code:        document.getElementById('zip_code').value.trim(),
      building_type:   document.getElementById('building_type').value,
      soil_confidence: document.getElementById('soil_confidence').value,
      wwr:             document.getElementById('s_wwr').value,
      envelope:        document.getElementById('s_envelope').value,
      glazing:         document.getElementById('s_glazing').value,
    };
    const floorArea = document.getElementById('floor_area_m2').value.trim();
    if (floorArea) body.floor_area_m2 = parseFloat(floorArea);
    const yearRaw = document.getElementById('year_built').value.trim();
    if (yearRaw !== '') body.year_built = parseInt(yearRaw, 10);
    return body;
  }

  async function runStage1() {
    stage1Error.textContent = '';
    stage1Error.classList.add('hidden');
    ['zip_code', 'building_type', 'floor_area_m2', 'year_built'].forEach(clearFieldError);
    invalidateStage1();
    stage1Btn.disabled = true;
    stage1Btn.classList.add('loading');
    stage1Btn.textContent = 'Analyzing…';

    let response, result;
    try {
      response = await fetch('/calculate/stage1', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(collectStage1Body()),
      });
      result = await response.json();
    } catch (err) {
      showStage1Error('Network error: ' + err.message);
      resetStage1Btn();
      return;
    }

    if (!response.ok) {
      if (result.error === 'field' && result.field) {
        showFieldError(result.field, result.message);
      } else {
        showStage1Error(result.message || 'Analysis failed.');
      }
      resetStage1Btn();
      return;
    }

    stage1Result = result;
    renderStage1(result);
    unlockStep2();
    resetStage1Btn();
    stage1Panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  stage1Btn.addEventListener('click', runStage1);

  function renderStage1(result) {
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

    const est = result.nb_estimate;
    const fp  = est.footprint;
    const loadCheckLine = (est.nb_load_min != null && est.nb_load_max != null)
      ? `<br><span style="font-size:11px;color:var(--text-muted)">Load check: this q<sub>h</sub> needs roughly ` +
        `${est.nb_load_min}–${est.nb_load_max} boreholes at 125 m (15–70 W/m rule of thumb)</span>`
      : '';
    const capacityWarn = est.capacity_warning
      ? `<div class="callout callout-warn" style="margin-top:8px">The peak load likely exceeds what the ` +
        `building perimeter can host — consider the s6 hybrid strategy, deeper boreholes, ` +
        `or off-footprint field area.</div>`
      : '';
    document.getElementById('pipeline-nb').innerHTML =
      `Footprint ${Math.round(fp.footprint_m2).toLocaleString()} m² ` +
      `(${Math.round(fp.length_m)} × ${Math.round(fp.width_m)} m, ${fp.n_floors} floor${fp.n_floors > 1 ? 's' : ''})<br>` +
      `<strong>${est.nb_min}–${est.nb_max} boreholes</strong> fit this footprint at ${est.spacing_m} m spacing<br>` +
      `<span style="font-size:11px;color:var(--text-muted)">Step 2 optimizes the count within this range — recomputed if you change spacing</span>` +
      loadCheckLine + capacityWarn;
    stage1Panel.classList.remove('hidden');
  }

  function collectStage2Body() {
    const body = {
      building_type: document.getElementById('building_type').value,
      site:  stage1Result.site,
      loads: stage1Result.loads,
      H_min: parseFloat(document.getElementById('s_H_min').value) || 125,
      B:     parseFloat(document.getElementById('s_B').value) || 6.0,
      A:     parseFloat(document.getElementById('s_A').value) || 9.0,
    };
    const floorArea = document.getElementById('floor_area_m2').value.trim();
    if (floorArea) body.floor_area_m2 = parseFloat(floorArea);
    applySmartAdvOverrides(body);
    if (document.getElementById('expert-nb-enable').checked) {
      const nbRaw = document.getElementById('s_NB').value.trim();
      if (nbRaw !== '') body.NB = parseInt(nbRaw, 10);
    }
    return body;
  }

  async function runStage2() {
    if (!stage1Result) return;
    stage2Error.textContent = '';
    stage2Error.classList.add('hidden');
    ['s_H_min', 's_B', 's_A', 's_NB'].forEach(clearFieldError);
    smartResult.classList.add('hidden');
    document.getElementById('cost-section').classList.add('hidden');
    document.getElementById('s6-section').classList.add('hidden');
    document.getElementById('s7-section').classList.add('hidden');
    document.getElementById('s7-report').classList.add('hidden');
    stage2Btn.disabled = true;
    stage2Btn.classList.add('loading');
    stage2Btn.textContent = 'Sizing…';

    let response, result;
    try {
      response = await fetch('/calculate/stage2', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(collectStage2Body()),
      });
      result = await response.json();
    } catch (err) {
      showStage2Error('Network error: ' + err.message);
      resetStage2Btn();
      return;
    }

    if (!response.ok) {
      const fieldMap = { H_min: 's_H_min', B: 's_B', A: 's_A', NB: 's_NB' };
      if (result.error === 'field' && fieldMap[result.field]) {
        showFieldError(fieldMap[result.field], result.message);
      } else {
        showStage2Error(result.message || 'Sizing failed.');
      }
      resetStage2Btn();
      return;
    }

    renderStage2(result);
    resetStage2Btn();
  }

  stage2Btn.addEventListener('click', runStage2);

  function renderStage2(result) {
    document.getElementById('sres-L').textContent  = fmtInt(result.L);
    document.getElementById('sres-H').textContent  = fmtInt(result.H);
    document.getElementById('sres-NB').textContent = fmtInt(result.NB);
    const nbRange = document.getElementById('sres-NB-range');
    if (result.nb_source === 'expert_override') {
      nbRange.textContent = 'expert override — footprint optimization skipped';
    } else if (result.nb_source === 'depth_fallback') {
      nbRange.textContent =
        `small load — depth-primary sizing chose ${result.NB} (footprint fits ${result.nb_min}–${result.nb_max})`;
    } else {
      nbRange.textContent = `optimal within footprint range ${result.nb_min}–${result.nb_max}`;
    }

    const capWarnEl = document.getElementById('sres-capacity-warning');
    if (result.capacity_warning) {
      capWarnEl.classList.remove('hidden');
    } else {
      capWarnEl.classList.add('hidden');
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
        const qy = stage1Result.loads?.q_y ?? 0;
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

    // s5: fetch cost estimate, sourcing site/loads from stage 1
    const siteState = stage1Result.site.state_abbrev || null;
    const B_m = parseFloat(document.getElementById('s_B').value) || 6.0;
    const smartRes = {
      ...result,
      site:  stage1Result.site,
      loads: stage1Result.loads,
      building_type: document.getElementById('building_type').value,
      NB_user: result.nb_source === 'expert_override' ? result.NB : null,
      NB_computed: result.NB,
      B: B_m,
      A: parseFloat(document.getElementById('s_A').value) || 9.0,
    };
    lastStage2Result = smartRes;
    fetchCostEstimate(result.L, result.NB, B_m, siteState, smartRes);
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
      'wwr', 'envelope', 'glazing',
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
      lastCostResult = cost;
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
      envelope_factor: smartRes.loads.envelope_factor || 1.0,
    };
    applySmartAdvOverrides(payload);
    // s5/s6 must describe the same borefield stage2 sized
    payload.NB = smartRes.NB_user ?? smartRes.NB_computed ?? null;

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

    lastStrategyResult = res;
    window.__geositeLast = {
      stage1: stage1Result,
      stage2: lastStage2Result,
      cost: lastCostResult,
      strategy: res,
    };
    document.getElementById('s7-section').classList.remove('hidden');
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

  // ── s7: Report generate / render / copy ──────────────────────────────
  let s7Sections = null;   // [{title, rows: [[label, value]], bullets: {name: []}}]

  function _rowsHTML(rows) {
    return rows.map(([label, value]) =>
      `<div class="report-row"><span class="report-label">${label}</span>` +
      `<span class="report-value">${value}</span></div>`).join('');
  }

  function _fmtYears(v) {
    return v == null ? 'no operating savings' : `${v.toFixed(1)} yr`;
  }

  function renderReport(data) {
    const r = data.report;
    const d = r.design;
    const sections = [];

    const designRows = [
      ['Building', `${d.building_type ?? '—'} · climate zone ${d.climate_zone ?? '—'}`],
      ['Boreholes (NB)', `${fmtInt(d.NB)} — ${d.nb_source ?? '—'}` +
        (d.nb_min != null ? ` (footprint range ${d.nb_min}–${d.nb_max})` : '')],
      ['Depth per borehole', `${fmtInt(d.H_m)} m`],
      ['Total drilled length', `${fmtInt(d.L_m)} m (${fmtInt(d.L_ft)} ft)`],
      ['Spacing · array aspect', `${d.B_m ?? '—'} m · ${d.A ?? '—'}`],
      ['Governing mode', d.governing ?? '—'],
      ['Two-pass L (heat / cool)', `${fmtInt(d.L_heat_m)} / ${fmtInt(d.L_cool_m)} m` +
        (d.imbalance_m != null ? ` — imbalance ${fmtInt(d.imbalance_m)} m` : '')],
      ['Footprint', d.footprint_length_m != null
        ? `${Math.round(d.footprint_length_m)} × ${Math.round(d.footprint_width_m)} m, ${d.n_floors} floor(s)` : '—'],
      ['Soil', `k_eff ${d.k_effective ?? '—'} W/m·K · α ${d.alpha ?? '—'} m²/day · T_g ${d.T_g ?? '—'} °C`],
    ];
    if (d.capacity_warning) designRows.push(['Capacity check', '⚠ peak load may exceed the footprint']);
    if (d.solar_thermal_recommended) designRows.push(['Thermal balance', 'net extraction — solar thermal supplement recommended']);
    sections.push({title: 'System Design', rows: designRows});

    const p = r.performance;
    if (p.available) {
      sections.push({title: 'Estimated Performance', rows: [
        ['ASHRAE 99.6% cap', p.cap_kW != null ? `${p.cap_kW.toFixed(1)} kW` : '—'],
        ['Dominant mode', p.dominant_mode ?? '—'],
        ['GSHP coverage — M1 (hours)', `${p.m1.gshp_hours_pct ?? '—'}% hrs · ${p.m1.gshp_energy_pct ?? '—'}% kWh`],
        ['GSHP coverage — M2 (energy)', `${p.m2.gshp_hours_pct ?? '—'}% hrs · ${p.m2.gshp_energy_pct ?? '—'}% kWh`],
        ['Peaker unit', `${p.peaker_kW ?? '—'} kW ${p.peaker_type ?? ''}`],
        ['Peaker energy — M1', p.m1.peaker_energy_kwh != null ? `${fmtInt(p.m1.peaker_energy_kwh)} kWh/yr` : '—'],
        ['Peaker energy — M2', p.m2.peaker_energy_kwh != null ? `${fmtInt(p.m2.peaker_energy_kwh)} kWh/yr` : '—'],
        ['Borefield after shaving', `M1 ${fmtInt(p.m1.L_after_m)} m (−${p.m1.savings_pct ?? 0}%) · M2 ${fmtInt(p.m2.L_after_m)} m (−${p.m2.savings_pct ?? 0}%)`],
      ]});
    } else {
      sections.push({title: 'Estimated Performance', rows: [['Status', 'unavailable — run the s6 strategy first']]});
    }

    const c = r.cost_savings;
    if (c.available) {
      sections.push({title: 'Cost & Savings', rows: [
        ['Borefield cost (best / base / worst)', `${fmtUSD(c.borefield_best_usd)} / ${fmtUSD(c.borefield_base_usd)} / ${fmtUSD(c.borefield_worst_usd)}`],
        ['Heat pump equipment', fmtUSD(c.hp_equipment_usd)],
        ['GSHP total system', fmtUSD(c.gshp_capex_usd)],
        ['Conventional system (boiler + chiller)', `${fmtUSD(c.conv_capex_low_usd)}–${fmtUSD(c.conv_capex_high_usd)} (mid ${fmtUSD(c.conv_capex_usd)})`],
        ['Annual operating — conventional', fmtUSD(c.conv_opex_usd_yr) + '/yr'],
        ['Annual operating — GSHP', fmtUSD(c.gshp_opex_usd_yr) + '/yr (peaker energy additional)'],
        ['Annual savings', fmtUSD(c.annual_savings_usd_yr) + '/yr'],
        ['Simple payback', _fmtYears(c.simple_payback_yr)],
        ['Note', c.note],
      ]});
    } else {
      sections.push({title: 'Cost & Savings', rows: [['Status', 'unavailable — cost estimate missing']]});
    }

    document.getElementById('s7-design').innerHTML = _rowsHTML(sections[0].rows);
    document.getElementById('s7-performance').innerHTML = _rowsHTML(sections[1].rows);
    document.getElementById('s7-cost').innerHTML = _rowsHTML(sections[2].rows);

    const aiEl = document.getElementById('s7-ai');
    const ai = data.ai_review;
    if (ai) {
      const lists = [['Strengths', ai.strengths], ['Concerns', ai.concerns],
                     ['Risks', ai.risks], ['Next steps', ai.next_steps]];
      aiEl.innerHTML =
        `<p class="report-verdict"><strong>${ai.verdict}</strong></p>` +
        lists.map(([name, items]) =>
          `<div class="report-ai-list"><div class="report-label">${name}</div><ul>` +
          (items || []).map(i => `<li>${i}</li>`).join('') + `</ul></div>`).join('');
      sections.push({title: 'AI Design Review', rows: [['Verdict', ai.verdict]],
                     bullets: Object.fromEntries(lists)});
    } else {
      const reason = data.ai_error || 'unknown reason';
      aiEl.innerHTML = `<p class="cost-note">AI review unavailable — ${reason}. ` +
        `The sections above are computed deterministically and stand alone.</p>`;
      sections.push({title: 'AI Design Review', rows: [['Status', `unavailable — ${reason}`]]});
    }

    s7Sections = sections;
    document.getElementById('s7-report').classList.remove('hidden');
  }

  function reportAsText() {
    if (!s7Sections) return '';
    const lines = ['GeoSite Advisor — Pre-feasibility Report', ''];
    s7Sections.forEach(sec => {
      lines.push(sec.title);
      lines.push('-'.repeat(sec.title.length));
      sec.rows.forEach(([label, value]) => lines.push(`${label}: ${String(value).replace(/⚠/g, '!')}`));
      if (sec.bullets) {
        Object.entries(sec.bullets).forEach(([name, items]) => {
          lines.push(`${name}:`);
          (items || []).forEach(i => lines.push(`- ${i}`));
        });
      }
      lines.push('');
    });
    lines.push('Pre-feasibility estimate — a licensed engineer and a thermal response test are required before installation.');
    return lines.join('\n');
  }

  async function generateReport() {
    const btn = document.getElementById('s7-generate-btn');
    const errEl = document.getElementById('s7-error');
    errEl.textContent = '';
    errEl.classList.add('hidden');
    if (!stage1Result || !lastStage2Result || !lastStrategyResult) {
      errEl.textContent = 'Run the full pipeline (Steps 1–2) before generating a report.';
      errEl.classList.remove('hidden');
      return;
    }

    const profile = lastStrategyResult.hourly_profile || [];
    let heatWh = 0, coolWh = 0;
    profile.forEach(h => { if (h < 0) heatWh -= h; else coolWh += h; });

    btn.disabled = true;
    btn.classList.add('loading');
    btn.textContent = 'Generating…';

    let resp, data;
    try {
      resp = await fetch('/api/report', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          design:   lastStage2Result,
          site:     stage1Result.site,
          loads:    stage1Result.loads,
          cost:     lastCostResult,
          strategy: lastStrategyResult,
          annual_heat_kwh_th: heatWh / 1000,
          annual_cool_kwh_th: coolWh / 1000,
        }),
      });
      data = await resp.json();
    } catch (err) {
      errEl.textContent = 'Network error: ' + err.message;
      errEl.classList.remove('hidden');
      btn.disabled = false;
      btn.classList.remove('loading');
      btn.textContent = 'Generate Report';
      return;
    }

    btn.disabled = false;
    btn.classList.remove('loading');
    btn.textContent = 'Generate Report';

    if (!resp.ok) {
      errEl.textContent = (data && data.message) || 'Report generation failed.';
      errEl.classList.remove('hidden');
      return;
    }
    renderReport(data);
    document.getElementById('s7-report').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  document.getElementById('s7-generate-btn').addEventListener('click', generateReport);

  document.getElementById('s7-copy-btn').addEventListener('click', () => {
    const btn = document.getElementById('s7-copy-btn');
    const text = reportAsText();
    const flash = ok => {
      btn.textContent = ok ? 'Copied' : 'Copy failed — clipboard blocked';
      setTimeout(() => { btn.textContent = 'Copy report as text'; }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => flash(true)).catch(() => flash(false));
    } else {
      flash(false);
    }
  });

})();
