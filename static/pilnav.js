/* ═══ GeoLoop PillNav — GSAP vanilla port of React Bits PillNav ═══
   baseColor  = #ffffff (white container)
   pillColor  = #557434 (fm7 dark matcha, fills hover-circle)
   pillTextColor        = #557434 (default label on white)
   hoveredPillTextColor = #ffffff (label on fm7 pill)
*/
(function () {
  'use strict';

  // ── Active page detection ──
  function activeLabel() {
    const p = (window.location.pathname + window.location.href).toLowerCase();
    if (p.includes('account')) return 'Home';
    if (p.includes('contact')) return 'Contact';
    return 'GeoLoop'; // analysis flow + everything else
  }

  // ── Main init ──
  var _pilnavRetry = 0;
  function initPillNav() {
    if (typeof gsap === 'undefined') {
      if (++_pilnavRetry < 50) { setTimeout(initPillNav, 60); return; }
      // GSAP never loaded — just make the nav visible without animation
      var nav = document.getElementById('gl-pill-nav');
      if (nav) { nav.style.opacity = '1'; nav.style.transform = 'none'; }
      return;
    }

    const nav = document.getElementById('gl-pill-nav');
    if (!nav) return;

    const textPills = Array.from(nav.querySelectorAll('.gl-pill-text'));
    const active = activeLabel();

    // ── Per-pill GSAP circle animation (exact React Bits geometry) ──
    textPills.forEach(function (pill) {
      var w = pill.offsetWidth, h = pill.offsetHeight;
      var R = (w * w / 4 + h * h) / (2 * h);
      var D = Math.ceil(2 * R) + 2;
      var delta = Math.ceil(R - Math.sqrt(R * R - w * w / 4)) + 1;
      var originY = D - delta;

      var circle = pill.querySelector('.gl-hover-circle');
      circle.style.width  = D + 'px';
      circle.style.height = D + 'px';
      circle.style.marginLeft = (-D / 2) + 'px';
      circle.style.top    = (-delta) + 'px';
      circle.style.transformOrigin = '50% ' + originY + 'px';

      var label  = pill.querySelector('.gl-pill-label');
      var labelH = pill.querySelector('.gl-pill-label-hover');
      var isActive = (pill.dataset.label === active);

      if (isActive) {
        // Pre-fill circle, slide labels to hover state
        gsap.set(circle, { scale: 1 });
        gsap.set(label,  { y: -(h + 8) });
        gsap.set(labelH, { y: -(h + 8) });
        pill.classList.add('gl-active');
      }

      // Build hover timeline (paused initially)
      var tl = gsap.timeline({ paused: true });
      tl.to(circle, { scale: 1,        duration: 0.3, ease: 'power2.out' }, 0);
      tl.to(label,  { y: -(h + 8),     duration: 0.3, ease: 'power2.out' }, 0);
      tl.to(labelH, { y: -(h + 8),     duration: 0.3, ease: 'power2.out' }, 0);

      if (!isActive) {
        pill.addEventListener('mouseenter', function () { tl.play(); });
        pill.addEventListener('mouseleave', function () { tl.reverse(); });
      }

      // Navigate on click
      pill.addEventListener('click', function () {
        var href = pill.dataset.href;
        if (href) window.location.href = href;
      });
    });

    // ── Load animation ──
    // 1. Reveal the pill list container
    gsap.to(nav, {
      opacity: 1,
      y: 0,
      duration: 0.55,
      ease: 'power3.out',
      delay: 0.08
    });
    // 2. Stagger each pill item
    var allPills = nav.querySelectorAll('.gl-pill');
    gsap.fromTo(allPills,
      { y: -6, opacity: 0 },
      { y: 0,  opacity: 1, duration: 0.38, ease: 'power2.out', stagger: 0.07, delay: 0.18 }
    );
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPillNav);
  } else {
    initPillNav();
  }
})();
