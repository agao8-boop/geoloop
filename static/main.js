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
    ['zip_code', 'building_type', 'mode', 's_NB', 's_B', 's_A'].forEach(clearFieldError);
  }

  function showSmartError(msg) {
    smartError.textContent = msg;
    smartError.classList.remove('hidden');
  }

  smartBtn.addEventListener('click', async () => {
    clearSmartErrors();
    pipelinePanel.classList.add('hidden');
    smartResult.classList.add('hidden');
    smartBtn.disabled = true;
    smartBtn.textContent = 'Calculating…';

    const body = {
      zip_code:      document.getElementById('zip_code').value.trim(),
      building_type: document.getElementById('building_type').value,
      mode:          document.getElementById('mode').value,
      NB:            parseFloat(document.getElementById('s_NB').value),
      B:             parseFloat(document.getElementById('s_B').value),
      A:             parseFloat(document.getElementById('s_A').value),
    };

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
    document.getElementById('pipeline-s1').innerHTML =
      `k = ${site.k} W/m·K &nbsp;·&nbsp; α = ${site.alpha} m²/day &nbsp;·&nbsp; T<sub>g</sub> = ${site.T_g}°C<br>` +
      `Climate zone: ${site.climate_zone} &nbsp;·&nbsp; ` +
      (site.data_available ? '✓ SSURGO data' : '⚠ No soil data');

    document.getElementById('pipeline-s2').innerHTML =
      `q<sub>h</sub> = ${loads.q_h?.toLocaleString()} W<br>` +
      `q<sub>m</sub> = ${loads.q_m?.toLocaleString()} W<br>` +
      `q<sub>y</sub> = ${loads.q_y?.toLocaleString()} W`;

    pipelinePanel.classList.remove('hidden');

    // Show sizing result
    document.getElementById('sres-L').textContent  = result.L?.toLocaleString();
    document.getElementById('sres-H').textContent  = result.H?.toLocaleString();
    document.getElementById('sres-NB').textContent = result.NB?.toLocaleString();
    smartResult.classList.remove('hidden');
    smartResult.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    resetSmartBtn();
  });

  function resetSmartBtn() {
    smartBtn.disabled    = false;
    smartBtn.textContent = 'Calculate Borefield Size';
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

})();
