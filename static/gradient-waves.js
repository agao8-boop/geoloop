// gradient-waves.js — vanilla WebGL2 gradient waves background
// ponytail: no OGL dependency, raw WebGL2 fullscreen triangle + raymarch shader

(function () {
  'use strict';

  const VERT = `#version 300 es
in vec2 position;
void main() {
  gl_Position = vec4(position, 0.0, 1.0);
}`;

  const FRAG = `#version 300 es
precision highp float;
uniform vec2 iResolution;
uniform float iTime;
uniform float uSpeed;
uniform float uAmplitude;
uniform float uWaveScale;
uniform float uWaveRatio;
uniform float uSwell;
uniform float uTurbulence;
uniform float uTilt;
uniform float uZoom;
uniform float uHeight;
uniform float uFogDepth;
uniform float uSteps;
uniform float uBrightness;
uniform float uOpacity;
uniform float uGrain;
uniform float uGrainIntensity;
uniform vec2 uMouse;
uniform float uParallax;
uniform bool uEnableMouse;
uniform vec3 uHorizonColor;
uniform vec3 uWaveColor;
uniform vec3 uCrestColor;
out vec4 fragColor;

const float MAX_DIST = 20000.0;

float hash21(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

float plasma(vec3 r, vec2 freq, vec4 tc) {
  float mx = r.x + tc.x;
  mx += uSwell * sin((r.y + mx) / 20.0 + tc.y);
  float my = r.y - tc.z;
  my += uTurbulence * cos(r.x / 23.0 + tc.w);
  return r.z - (sin(mx * freq.x) * uAmplitude + sin(my * freq.y) * uAmplitude + uHeight);
}

float raymarch(vec3 pos, vec3 dir, vec2 freq, vec4 tc) {
  float dist = 0.0;
  for (int i = 0; i < 128; i++) {
    if (float(i) >= uSteps) break;
    float dscene = plasma(pos + dist * dir, freq, tc);
    if (abs(dscene) < 0.1) break;
    dist += 0.9 * dscene;
    if (!(abs(dist) < MAX_DIST)) return MAX_DIST;
  }
  return dist;
}

void main() {
  float T = iTime * uSpeed;
  vec2 freq = vec2(uWaveScale / 7.0, (uWaveScale * uWaveRatio) / 3.0);
  vec4 tc = vec4(T / 0.130, T / 0.810, T / 0.200, T / 0.710);
  float c, s;
  float vfov = (3.14159 / 2.3) / max(uZoom, 0.05);
  vec3 cam = vec3(0.0, 0.0, 30.0);
  vec2 uv = (gl_FragCoord.xy / iResolution.xy) - 0.5;
  uv.x *= iResolution.x / iResolution.y;
  uv.y *= -1.0;

  vec3 dir = vec3(0.0, 0.0, -1.0);
  float ulen = length(uv);
  float xrot = vfov * ulen;
  c = cos(xrot); s = sin(xrot);
  dir = mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c) * dir;
  vec2 nuv = ulen > 1e-5 ? uv / ulen : vec2(1.0, 0.0);
  c = nuv.x; s = nuv.y;
  dir = mat3(c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0) * dir;
  c = cos(uTilt); s = sin(uTilt);
  dir = mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c) * dir;

  if (uEnableMouse) {
    float yaw = (uMouse.x - 0.5) * uParallax * 0.4;
    float pitch = (uMouse.y - 0.5) * uParallax * 0.4;
    c = cos(yaw); s = sin(yaw);
    dir = mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c) * dir;
    c = cos(pitch); s = sin(pitch);
    dir = mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c) * dir;
  }

  float dist = raymarch(cam, dir, freq, tc);
  vec3 pos = cam + dist * dir;

  float t = clamp(uFogDepth / max(dist, 0.001), 0.0, 1.0);
  vec3 body = mix(uWaveColor, uCrestColor, clamp(pos.z * 0.08 + 0.5, 0.0, 1.0));
  vec3 col = mix(uHorizonColor, body, t);
  col *= uBrightness;
  col = clamp(col, 0.0, 1.0);

  float alpha = clamp(t, 0.0, 1.0) * uOpacity;
  if (uGrain > 0.5) {
    float g = hash21(gl_FragCoord.xy + mod(iTime, 64.0) * 11.0);
    alpha += (g - 0.5) * uGrainIntensity;
  }
  alpha = clamp(alpha, 0.0, 1.0);
  fragColor = vec4(col * alpha, alpha);
}`;

  // --- helpers ---

  function hexToVec3(hex) {
    var h = hex.replace('#', '');
    return [
      parseInt(h.substring(0, 2), 16) / 255,
      parseInt(h.substring(2, 4), 16) / 255,
      parseInt(h.substring(4, 6), 16) / 255,
    ];
  }

  function compileShader(gl, type, src) {
    var s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.error('gradient-waves shader error:', gl.getShaderInfoLog(s));
      gl.deleteShader(s);
      return null;
    }
    return s;
  }

  function createProgram(gl, vs, fs) {
    var p = gl.createProgram();
    gl.attachShader(p, vs);
    gl.attachShader(p, fs);
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
      console.error('gradient-waves link error:', gl.getProgramInfoLog(p));
      return null;
    }
    return p;
  }

  // --- main init ---

  function initGradientWaves(containerSelector, options) {
    var opts = Object.assign({
      speed: 0.25,
      amplitude: 1.8,
      waveScale: 0.5,
      waveRatio: 0.7,
      swell: 1.0,
      turbulence: 1.0,
      tilt: 0.0,
      zoom: 1.0,
      height: 0.0,
      fogDepth: 18,
      steps: 60,
      brightness: 1.1,
      opacity: 0.6,
      grain: true,
      grainIntensity: 0.03,
      mouseInteraction: true,
      parallaxStrength: 0.3,
      horizonColor: '#dce3cf',
      waveColor: '#c4cdb3',
      crestColor: '#f2f5eb',
    }, options || {});

    var container = typeof containerSelector === 'string'
      ? document.querySelector(containerSelector)
      : containerSelector;
    if (!container) return null;

    // ponytail: inline style keeps it self-contained, no CSS file needed
    container.style.cssText = 'position:fixed;inset:0;z-index:-1;pointer-events:none;';

    var canvas = document.createElement('canvas');
    canvas.style.cssText = 'display:block;width:100%;height:100%;';
    container.appendChild(canvas);

    var gl = canvas.getContext('webgl2', { alpha: true, premultipliedAlpha: false });
    if (!gl) { console.warn('gradient-waves: WebGL2 not available'); return null; }

    // compile
    var vs = compileShader(gl, gl.VERTEX_SHADER, VERT);
    var fs = compileShader(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return null;
    var prog = createProgram(gl, vs, fs);
    if (!prog) return null;

    // fullscreen triangle (covers [-1,1] quad with a single oversized tri)
    // ponytail: 3 verts, no index buffer needed
    var posLoc = gl.getAttribLocation(prog, 'position');
    var vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(posLoc);
    gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);

    // uniforms
    gl.useProgram(prog);
    var loc = {};
    var names = [
      'iResolution', 'iTime', 'uSpeed', 'uAmplitude', 'uWaveScale', 'uWaveRatio',
      'uSwell', 'uTurbulence', 'uTilt', 'uZoom', 'uHeight', 'uFogDepth', 'uSteps',
      'uBrightness', 'uOpacity', 'uGrain', 'uGrainIntensity', 'uMouse', 'uParallax',
      'uEnableMouse', 'uHorizonColor', 'uWaveColor', 'uCrestColor',
    ];
    names.forEach(function (n) { loc[n] = gl.getUniformLocation(prog, n); });

    // state
    var mouse = [0.5, 0.5];
    var targetMouse = [0.5, 0.5];
    var startTime = performance.now() / 1000;
    var raf = 0;
    var visible = true;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);

    function resize() {
      var w = container.clientWidth;
      var h = container.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
    }

    function render() {
      if (!visible) { raf = requestAnimationFrame(render); return; }

      // smooth mouse
      mouse[0] += (targetMouse[0] - mouse[0]) * 0.05;
      mouse[1] += (targetMouse[1] - mouse[1]) * 0.05;

      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);

      gl.useProgram(prog);
      gl.uniform2f(loc.iResolution, canvas.width, canvas.height);
      gl.uniform1f(loc.iTime, performance.now() / 1000 - startTime);
      gl.uniform1f(loc.uSpeed, opts.speed);
      gl.uniform1f(loc.uAmplitude, opts.amplitude);
      gl.uniform1f(loc.uWaveScale, opts.waveScale);
      gl.uniform1f(loc.uWaveRatio, opts.waveRatio);
      gl.uniform1f(loc.uSwell, opts.swell);
      gl.uniform1f(loc.uTurbulence, opts.turbulence);
      gl.uniform1f(loc.uTilt, opts.tilt);
      gl.uniform1f(loc.uZoom, opts.zoom);
      gl.uniform1f(loc.uHeight, opts.height);
      gl.uniform1f(loc.uFogDepth, opts.fogDepth);
      gl.uniform1f(loc.uSteps, opts.steps);
      gl.uniform1f(loc.uBrightness, opts.brightness);
      gl.uniform1f(loc.uOpacity, opts.opacity);
      gl.uniform1f(loc.uGrain, opts.grain ? 1.0 : 0.0);
      gl.uniform1f(loc.uGrainIntensity, opts.grainIntensity);
      gl.uniform2f(loc.uMouse, mouse[0], mouse[1]);
      gl.uniform1f(loc.uParallax, opts.parallaxStrength);
      gl.uniform1i(loc.uEnableMouse, opts.mouseInteraction ? 1 : 0);
      gl.uniform3fv(loc.uHorizonColor, hexToVec3(opts.horizonColor));
      gl.uniform3fv(loc.uWaveColor, hexToVec3(opts.waveColor));
      gl.uniform3fv(loc.uCrestColor, hexToVec3(opts.crestColor));

      gl.bindVertexArray(vao);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.bindVertexArray(null);

      raf = requestAnimationFrame(render);
    }

    // events
    function onMouseMove(e) {
      if (!opts.mouseInteraction) return;
      targetMouse[0] = e.clientX / window.innerWidth;
      targetMouse[1] = e.clientY / window.innerHeight;
    }

    function onVisibility() {
      visible = !document.hidden;
    }

    window.addEventListener('resize', resize, { passive: true });
    document.addEventListener('mousemove', onMouseMove, { passive: true });
    document.addEventListener('visibilitychange', onVisibility);

    resize();
    raf = requestAnimationFrame(render);

    // cleanup handle
    return {
      destroy: function () {
        cancelAnimationFrame(raf);
        window.removeEventListener('resize', resize);
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('visibilitychange', onVisibility);
        gl.deleteProgram(prog);
        gl.deleteShader(vs);
        gl.deleteShader(fs);
        gl.deleteBuffer(buf);
        gl.deleteVertexArray(vao);
        canvas.remove();
      },
    };
  }

  // expose globally
  window.initGradientWaves = initGradientWaves;

  // auto-init on DOM ready
  function autoInit() {
    var els = document.querySelectorAll('.gl-waves-bg');
    els.forEach(function (el) { initGradientWaves(el); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }
})();
