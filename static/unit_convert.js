// Calculations stay in SI; this helper only converts displayed values.
window.GeoUnits = {
  current() { return sessionStorage.getItem('gl_units') || 'imperial'; },
  value(v, type) { const n=Number(v); if (!Number.isFinite(n)||this.current()==='metric') return n; return type==='length'?n*3.28084:type==='area'?n*10.7639:type==='temperature'?n*9/5+32:(type==='energy'||type==='power')?n*3.41214:n; },
  label(type) { const i=this.current()!=='metric'; return ({length:i?'ft':'m',area:i?'ft²':'m²',temperature:i?'°F':'°C',energy:i?'kBtu':'kWh',power:i?'kBtu/h':'kW'})[type]||''; },
  format(v,type,d=1) { return this.value(v,type).toFixed(d); }
};
