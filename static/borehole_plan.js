/* Borefield layout plan renderer — shared by the user tool (index.html)
 * and the developer dashboard (dev.html).
 *
 * drawBoreholePlan(canvas, data)
 *   canvas — HTMLCanvasElement
 *   data   — sizing result:
 *     data.footprint (stage-2) or data.nb_estimate (stage-1) with
 *       {pts, spacing_m, shape_label, footprint_m2, n_floors}
 *     data.NB, data.H, data.L
 *
 * Clean architectural-plan style: white background, thin gray grid,
 * bold building outline, dimension annotations, X-crosshair boreholes.
 */
(function () {
  'use strict';

  window.drawBoreholePlan = function (canvas, data) {
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext('2d');

    // HiDPI scaling
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.clientWidth || 600;
    const H = canvas.clientHeight || 400;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    ctx.scale(dpr, dpr);

    // ── Guard: need pts from footprint meta ──
    const fp = (data && (data.footprint || data.nb_estimate)) || null;
    const pts = fp && fp.pts;
    if (!pts || pts.length < 3) {
      // Draw placeholder
      ctx.fillStyle = '#f5f5f5'; ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = '#aaa'; ctx.font = '13px sans-serif';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('Run sizing to generate layout', W / 2, H / 2);
      return;
    }

    const NB = data.NB || 0;
    const H_bh = data.H || 0;
    const L_total = data.L || 0;
    const B = fp.spacing_m || 6;
    const setback = 3;   // metres from building edge to borehole centerline
    const ownership = 5; // metres beyond building for ownership area

    // ── Compute bounding box of pts + ownership buffer ──
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const minX = Math.min(...xs) - ownership;
    const maxX = Math.max(...xs) + ownership;
    const minY = Math.min(...ys) - ownership;
    const maxY = Math.max(...ys) + ownership;

    // ── Fit scale: leave 50px margin on each side for labels ──
    const margin = 50;
    const scaleX = (W - 2 * margin) / (maxX - minX);
    const scaleY = (H - 2 * margin) / (maxY - minY);
    const scale = Math.min(scaleX, scaleY);

    // Origin offset: center the drawing
    const drawW = (maxX - minX) * scale;
    const drawH = (maxY - minY) * scale;
    const ox = margin + (W - 2 * margin - drawW) / 2 - minX * scale;
    const oy = margin + (H - 2 * margin - drawH) / 2 - minY * scale;

    const toScreen = ([mx, my]) => [ox + mx * scale, oy + my * scale];

    // ── White background ──
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, W, H);

    // ── Grid: every B metres, light gray thin lines ──
    ctx.strokeStyle = '#e0e0e0';
    ctx.lineWidth = 0.5;
    ctx.setLineDash([]);
    const gridStep = B;
    // vertical lines
    for (let x = Math.ceil(minX / gridStep) * gridStep; x <= maxX; x += gridStep) {
      const [sx] = toScreen([x, 0]);
      const [, sy0] = toScreen([x, minY]);
      const [, sy1] = toScreen([x, maxY]);
      ctx.beginPath(); ctx.moveTo(sx, sy0); ctx.lineTo(sx, sy1); ctx.stroke();
    }
    // horizontal lines
    for (let y = Math.ceil(minY / gridStep) * gridStep; y <= maxY; y += gridStep) {
      const [, sy] = toScreen([0, y]);
      const [sx0] = toScreen([minX, y]);
      const [sx1] = toScreen([maxX, y]);
      ctx.beginPath(); ctx.moveTo(sx0, sy); ctx.lineTo(sx1, sy); ctx.stroke();
    }

    // ── Ownership area: dashed rectangle = building bbox + ownership buffer ──
    ctx.strokeStyle = '#81c784';
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 4]);
    const [ox0, oy0] = toScreen([Math.min(...xs) - ownership, Math.min(...ys) - ownership]);
    const [ox1, oy1] = toScreen([Math.max(...xs) + ownership, Math.max(...ys) + ownership]);
    ctx.strokeRect(ox0, oy0, ox1 - ox0, oy1 - oy0);
    ctx.setLineDash([]);
    // Label
    ctx.fillStyle = '#388e3c';
    ctx.font = "10px 'Inter', sans-serif";
    ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
    ctx.fillText('Ownership / Drillable Area', ox0 + 4, oy0 - 3);

    // ── Building polygon ──
    const screenPts = pts.map(p => toScreen(p));
    ctx.beginPath();
    ctx.moveTo(...screenPts[0]);
    for (let i = 1; i < screenPts.length; i++) ctx.lineTo(...screenPts[i]);
    ctx.closePath();
    ctx.fillStyle = 'rgba(207, 216, 220, 0.35)';
    ctx.fill();
    ctx.strokeStyle = '#37474f';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Building label
    const cx = screenPts.reduce((s, p) => s + p[0], 0) / screenPts.length;
    const cy = screenPts.reduce((s, p) => s + p[1], 0) / screenPts.length;
    const label1 = fp.shape_label || 'Building';
    const label2 = `${(fp.footprint_m2 || 0).toFixed(0)} m²`;
    const label3 = fp.n_floors ? `${fp.n_floors} floor(s)` : '';
    ctx.fillStyle = '#455a64'; ctx.font = 'bold 11px sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(label1, cx, cy - 12);
    ctx.font = '10px sans-serif';
    ctx.fillText(label2, cx, cy);
    if (label3) ctx.fillText(label3, cx, cy + 13);

    // ── Dimension annotations ──
    // Width annotation (horizontal, along bottom edge)
    const bboxW = (Math.max(...xs) - Math.min(...xs));
    const bboxH_m = (Math.max(...ys) - Math.min(...ys));
    const dimY = toScreen([0, Math.max(...ys)])[1] + 18;
    const dimX0 = toScreen([Math.min(...xs), 0])[0];
    const dimX1 = toScreen([Math.max(...xs), 0])[0];
    _drawDimension(ctx, dimX0, dimY, dimX1, dimY, `${bboxW.toFixed(1)} m`);
    // Height annotation (vertical, along right edge)
    const dimX = toScreen([Math.max(...xs), 0])[0] + 18;
    const dimY0 = toScreen([0, Math.min(...ys)])[1];
    const dimY1 = toScreen([0, Math.max(...ys)])[1];
    _drawDimension(ctx, dimX, dimY0, dimX, dimY1, `${bboxH_m.toFixed(1)} m`, true);

    // ── Setback dashed line (3 m outside building bbox) ──
    ctx.strokeStyle = '#9e9e9e';
    ctx.lineWidth = 0.8;
    ctx.setLineDash([3, 3]);
    const [sb0x, sb0y] = toScreen([Math.min(...xs) - setback, Math.min(...ys) - setback]);
    const [sb1x, sb1y] = toScreen([Math.max(...xs) + setback, Math.max(...ys) + setback]);
    ctx.strokeRect(sb0x, sb0y, sb1x - sb0x, sb1y - sb0y);
    ctx.setLineDash([]);

    // ── Boreholes: NB holes evenly spaced on the setback rectangle perimeter ──
    if (NB > 0) {
      const sbW = bboxW + 2 * setback, sbH = bboxH_m + 2 * setback;
      const perim = 2 * (sbW + sbH);
      const step = perim / NB;
      const sbMinX = Math.min(...xs) - setback;
      const sbMinY = Math.min(...ys) - setback;
      const positions = [];
      for (let i = 0; i < NB; i++) {
        const d = i * step;
        positions.push(_perimPoint(d, sbMinX, sbMinY, sbW, sbH));
      }
      positions.forEach(([mx, my]) => {
        const [sx, sy] = toScreen([mx, my]);
        // X crosshair marker
        ctx.strokeStyle = '#1b5e20'; ctx.lineWidth = 1.5;
        const r = 4;
        ctx.beginPath();
        ctx.moveTo(sx - r, sy - r); ctx.lineTo(sx + r, sy + r);
        ctx.moveTo(sx + r, sy - r); ctx.lineTo(sx - r, sy + r);
        ctx.stroke();
        // Circle
        ctx.beginPath(); ctx.arc(sx, sy, r + 1, 0, 2 * Math.PI);
        ctx.strokeStyle = '#388e3c'; ctx.lineWidth = 1; ctx.stroke();
      });
    }

    // ── Top-right label block ──
    const lblLines = [
      `NB = ${NB} boreholes`,
      `H = ${H_bh} m / each`,
      `L = ${L_total} m total`,
      `Spacing = ${B} m`,
    ];
    ctx.fillStyle = '#1a1a1a'; ctx.textAlign = 'right'; ctx.textBaseline = 'top';
    ctx.font = '10px monospace';
    lblLines.forEach((ln, i) => ctx.fillText(ln, W - 8, 8 + i * 14));

    // ── Scale bar (bottom-left) ──
    const barM = 10;
    const barPx = barM * scale;
    const barX = 10, barY = H - 20;
    ctx.strokeStyle = '#333'; ctx.lineWidth = 2; ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(barX, barY); ctx.lineTo(barX + barPx, barY); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(barX, barY - 4); ctx.lineTo(barX, barY + 4); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(barX + barPx, barY - 4); ctx.lineTo(barX + barPx, barY + 4); ctx.stroke();
    ctx.fillStyle = '#333'; ctx.font = '9px sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.fillText(`${barM} m`, barX + barPx / 2, barY + 5);
  };

  // Helper: point on a rectangle perimeter at arc-length d from top-left corner, clockwise
  function _perimPoint(d, x0, y0, w, h) {
    const perim = 2 * (w + h);
    d = ((d % perim) + perim) % perim;
    if (d < w)           return [x0 + d, y0];
    else if (d < w + h)  return [x0 + w, y0 + (d - w)];
    else if (d < 2 * w + h) return [x0 + w - (d - w - h), y0 + h];
    else                 return [x0, y0 + h - (d - 2 * w - h)];
  }

  // Helper: draw a dimension line with arrow ends and text label
  function _drawDimension(ctx, x0, y0, x1, y1, label, vertical = false) {
    ctx.strokeStyle = '#555'; ctx.lineWidth = 0.8; ctx.fillStyle = '#555';
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
    // Arrowheads
    const angle = Math.atan2(y1 - y0, x1 - x0);
    _arrowHead(ctx, x0, y0, angle + Math.PI);
    _arrowHead(ctx, x1, y1, angle);
    // Label
    ctx.font = '9px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    if (!vertical) {
      ctx.fillText(label, (x0 + x1) / 2, y0 - 8);
    } else {
      ctx.save(); ctx.translate((x0 + x1) / 2 + 14, (y0 + y1) / 2);
      ctx.rotate(-Math.PI / 2); ctx.fillText(label, 0, 0); ctx.restore();
    }
  }

  function _arrowHead(ctx, x, y, angle) {
    const size = 5;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x - size * Math.cos(angle - 0.4), y - size * Math.sin(angle - 0.4));
    ctx.lineTo(x - size * Math.cos(angle + 0.4), y - size * Math.sin(angle + 0.4));
    ctx.closePath(); ctx.fill();
  }
})();
