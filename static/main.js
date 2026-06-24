(function () {
  'use strict';

  // ── Tab switching ────────────────────────────────────────────────────
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      tabPanels.forEach(p => p.classList.add('hidden'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.remove('hidden');
    });
  });

  // ── Helpers ──────────────────────────────────────────────────────────
  function clearErrors() {
    document.querySelectorAll('.field-error').forEach(el => { el.textContent = ''; });
    document.querySelectorAll('.input-error').forEach(el => el.classList.remove('input-error'));
    const banner = document.getElementById('calc-error');
    banner.textContent = '';
    banner.classList.add('hidden');
  }

  function showFieldError(fieldName, message) {
    const input = document.querySelector(`[name="${fieldName}"]`);
    if (input) input.classList.add('input-error');
    const errEl = document.querySelector(`.field-error[data-for="${fieldName}"]`);
    if (errEl) errEl.textContent = message;
  }

  function showCalcError(message) {
    const banner = document.getElementById('calc-error');
    banner.textContent = message;
    banner.classList.remove('hidden');
  }

  function collectInputs() {
    const fields = [
      'q_h', 'q_m', 'q_y',
      'k', 'alpha', 'T_g',
      'Cp', 'mfls', 'T_in_HP',
      'rbore', 'rpin', 'rpext', 'kgrout', 'kpipe', 'LU', 'hconv',
      'B', 'NB', 'A',
    ];
    const data = {};
    fields.forEach(name => {
      const el = document.querySelector(`[name="${name}"]`);
      data[name] = el ? el.value.trim() : '';
    });
    return data;
  }

  // ── Calculate ─────────────────────────────────────────────────────────
  const advancedFields = ['rbore', 'rpin', 'rpext', 'kgrout', 'kpipe', 'LU', 'hconv', 'Cp'];

  document.getElementById('calc-btn').addEventListener('click', async () => {
    clearErrors();
    document.getElementById('result-panel').classList.add('hidden');

    const data = collectInputs();

    let response, result;
    try {
      response = await fetch('/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      result = await response.json();
    } catch (err) {
      showCalcError('Network error: ' + err.message);
      return;
    }

    if (!response.ok) {
      if (result.error === 'field') {
        showFieldError(result.field, result.message);
        // Auto-switch to the tab that contains the offending field
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

    // ── Show results ──
    document.getElementById('res-L').textContent = result.L.toLocaleString();
    document.getElementById('res-H').textContent = result.H.toLocaleString();
    document.getElementById('res-NB').textContent = result.NB.toLocaleString();
    document.getElementById('result-panel').classList.remove('hidden');
    document.getElementById('result-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });

})();
