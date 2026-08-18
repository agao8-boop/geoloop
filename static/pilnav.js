/* ═══ GeoLoop PillNav — ReactBits vanilla port (gl- namespace) ═══ */
(function () {
  'use strict';

  // Aurora background — only on tool/wizard pages, not welcome/result/auth pages
  var noAurora = /welcome|result_|signup|account|contact/.test(window.location.pathname);
  if (!noAurora) {
    document.documentElement.classList.add('gl-aurora');
    document.body.style.backgroundColor = 'transparent';
  }

  var ease = 'power3.easeOut';
  var retries = 0;

  function initPillNav() {
    if (typeof gsap === 'undefined') {
      if (++retries < 50) { setTimeout(initPillNav, 60); return; }
      return;
    }

    var container = document.querySelector('.gl-nav-header');
    if (!container) return;

    var logoEl = container.querySelector('.gl-pill-logo');
    var logoSvg = logoEl ? logoEl.querySelector('svg') : null;
    var navItems = container.querySelector('.gl-pill-nav-items');
    var pills = container.querySelectorAll('.gl-pill-btn');
    var timelines = [];
    var activeTweens = [];
    var logoTween = null;

    // Only run load animation on the first page (onboarding_1)
    var isFirstPage = /onboarding_1|^\/$/.test(window.location.pathname);

    function layout() {
      pills.forEach(function (pill, i) {
        var circle = pill.querySelector('.gl-hover-circle');
        if (!circle) return;

        var rect = pill.getBoundingClientRect();
        var w = rect.width, h = rect.height;
        var R = (w * w / 4 + h * h) / (2 * h);
        var D = Math.ceil(2 * R) + 2;
        var delta = Math.ceil(R - Math.sqrt(Math.max(0, R * R - w * w / 4))) + 1;
        var originY = D - delta;

        circle.style.width = D + 'px';
        circle.style.height = D + 'px';
        circle.style.bottom = '-' + delta + 'px';

        gsap.set(circle, {
          xPercent: -50,
          scale: 0,
          transformOrigin: '50% ' + originY + 'px'
        });

        var label = pill.querySelector('.gl-pill-label');
        var white = pill.querySelector('.gl-pill-label-hover');

        if (label) gsap.set(label, { y: 0 });
        if (white) gsap.set(white, { y: h + 12, opacity: 0 });

        if (timelines[i]) timelines[i].kill();

        var tl = gsap.timeline({ paused: true });
        tl.to(circle, { scale: 1.2, xPercent: -50, duration: 2, ease: ease, overwrite: 'auto' }, 0);
        if (label) tl.to(label, { y: -(h + 8), duration: 2, ease: ease, overwrite: 'auto' }, 0);
        if (white) {
          gsap.set(white, { y: Math.ceil(h + 100), opacity: 0 });
          tl.to(white, { y: 0, opacity: 1, duration: 2, ease: ease, overwrite: 'auto' }, 0);
        }

        timelines[i] = tl;
      });
    }

    layout();
    window.addEventListener('resize', layout);
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(layout).catch(function () {});
    }

    // Initial load animation — only on first page
    if (isFirstPage) {
      if (logoEl) {
        gsap.set(logoEl, { scale: 0 });
        gsap.to(logoEl, { scale: 1, duration: 0.6, ease: ease });
      }
      if (navItems) {
        gsap.set(navItems, { width: 0, overflow: 'hidden' });
        gsap.to(navItems, { width: 'auto', duration: 0.6, ease: ease });
      }
    }

    // Hover per pill
    pills.forEach(function (pill, i) {
      pill.addEventListener('mouseenter', function () {
        var tl = timelines[i];
        if (!tl) return;
        if (activeTweens[i]) activeTweens[i].kill();
        activeTweens[i] = tl.tweenTo(tl.duration(), { duration: 0.3, ease: ease, overwrite: 'auto' });
      });
      pill.addEventListener('mouseleave', function () {
        var tl = timelines[i];
        if (!tl) return;
        if (activeTweens[i]) activeTweens[i].kill();
        activeTweens[i] = tl.tweenTo(0, { duration: 0.2, ease: ease, overwrite: 'auto' });
      });
    });

    // Logo spin on hover
    if (logoEl && logoSvg) {
      logoEl.addEventListener('mouseenter', function () {
        if (logoTween) logoTween.kill();
        gsap.set(logoSvg, { rotate: 0 });
        logoTween = gsap.to(logoSvg, { rotate: 360, duration: 0.2, ease: ease, overwrite: 'auto' });
      });
    }

  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPillNav);
  } else {
    initPillNav();
  }
})();
