/* ecg.js — Foundations module ECG engine.
 *
 * A physiologically *parameterized* 12-lead model rendered on a CALIBRATED grid
 * (25 mm/s, 10 mm/mV). Because the grid is a true ruler, counting boxes on the
 * rendered trace yields real ms / mV — which is what makes the measurement scenes
 * honest and the axis-vector drag physically correct (limb-lead QRS = projection
 * of the heart's axis onto each lead).
 *
 * v1 uses a faithful synthetic model so every knob (rate, PR, QRS, axis, ST, T)
 * is manipulable. The production swap-in is real PTB-XL median beats + 12-leads;
 * the render/measure API is identical, so scenes don't change. See storyboard v7.
 */
(function (global) {
  'use strict';

  // ---- Calibration ---------------------------------------------------------
  var PX_PER_MM = 4;                 // 1 mm on paper -> 4 px on screen
  var SMALL = PX_PER_MM;             // small box: 1 mm = 40 ms = 0.1 mV
  var BIG = PX_PER_MM * 5;           // big box: 5 mm = 200 ms = 0.5 mV
  function xOf(ms) { return ms * 0.025 * PX_PER_MM; }   // 40 ms -> 4 px (25 mm/s)
  function pxToMs(px) { return px / (0.025 * PX_PER_MM); }
  function mvToPx(mv) { return mv * 10 * PX_PER_MM; }    // 1 mV -> 40 px (10 mm/mV)

  // Hexaxial frontal-plane lead angles (degrees), standard reference.
  var HEX = { I: 0, II: 60, III: 120, aVR: -150, aVL: -30, aVF: 90 };
  function rad(d) { return d * Math.PI / 180; }
  function proj(axisDeg, leadDeg) { return Math.cos(rad(leadDeg - axisDeg)); }
  function gauss(t, c, a, w) { return a * Math.exp(-((t - c) * (t - c)) / (2 * w * w)); }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  // ---- Beat parameters -----------------------------------------------------
  // All times in ms, amplitudes in mV. Defaults = a clean normal sinus beat.
  var DEFAULTS = {
    rate: 75,        // bpm
    pr: 160,         // PR interval (P onset -> QRS onset), normal 120-200
    qrs: 92,         // QRS duration, normal < 120
    qt: 380,         // QT interval (QRS onset -> T end)
    axis: 60,        // frontal QRS axis (deg); normal ~ -30..+90
    pAxis: 55,       // P axis -> upright II, inverted aVR
    tAxis: 45,       // T axis (limb leads)
    st: 0,           // ST level at J point (mV)
    Mqrs: 1.25,      // net QRS magnitude (mV) in the lead seeing it head-on
    Mp: 0.16,        // P magnitude
    Mt: 0.32,        // T magnitude
    artifact: 0,     // 0..1 noise (quality scene)
    pMorph: 1,       // 1 = uniform P each beat (sinus); <1 = varying (not sinus)
    label: ''
  };
  function params(over) {
    var p = {};
    for (var k in DEFAULTS) p[k] = DEFAULTS[k];
    if (over) for (var j in over) if (over.hasOwnProperty(j)) p[j] = over[j];
    return p;
  }

  // Normal precordial R-wave progression (rS in V1 -> qR in V6). r,s in mV (s as
  // a positive magnitude of the downward deflection); t = T amplitude (mV).
  var PRECORDIAL = {
    V1: { r: 0.18, s: 1.05, t: -0.08 },  // T often flat/slightly inverted in V1 (normal)
    V2: { r: 0.42, s: 1.25, t: 0.45 },
    V3: { r: 0.72, s: 0.70, t: 0.55 },   // transition zone (R/S ~ 1) ~ V3-V4
    V4: { r: 1.15, s: 0.38, t: 0.60 },
    V5: { r: 1.30, s: 0.18, t: 0.50 },
    V6: { r: 1.05, s: 0.10, t: 0.42 }
  };

  // Amplitudes {p, r, s, t} (mV) for a lead given params. Limb leads project the
  // axis; precordials use the progression table (scaled by overall QRS magnitude).
  function leadAmps(lead, p) {
    if (HEX.hasOwnProperty(lead)) {
      var net = p.Mqrs * proj(p.axis, HEX[lead]);          // +ve up, -ve down
      var r, s;
      if (net >= 0) { r = net; s = 0.05 + 0.10 * net; }    // dominant R, small s
      else { r = Math.max(0.04, 0.10 * (-net)); s = -net; } // dominant S (down)
      return {
        p: p.Mp * proj(p.pAxis, HEX[lead]),
        r: r, s: s,
        t: p.Mt * proj(p.tAxis, HEX[lead]),
        st: p.st
      };
    }
    var base = PRECORDIAL[lead] || PRECORDIAL.V4;
    var scale = p.Mqrs / 1.25;
    return { p: 0.05, r: base.r * scale, s: base.s * scale, t: base.t * (p.Mt / 0.32), st: p.st, precordial: true };
  }

  // ---- Sampler -------------------------------------------------------------
  // Landmarks within one cardiac cycle (ms from cycle start).
  function landmarks(p) {
    var pOnset = 60;
    var pCenter = pOnset + 40;
    var qrsOnset = pOnset + p.pr;
    var j = qrsOnset + p.qrs;
    var tEnd = qrsOnset + p.qt;
    var tWidth = clamp((tEnd - j) * 0.32, 36, 120);
    var tCenter = tEnd - tWidth * 1.6;
    return { pOnset: pOnset, pCenter: pCenter, qrsOnset: qrsOnset, j: j, tEnd: tEnd, tCenter: tCenter, tWidth: tWidth };
  }

  // Signal value (mV) at cycle time t for a lead's amplitudes a and params p.
  function valueAt(t, a, p, L) {
    var qw = p.qrs * 0.16;                       // QRS lobe width scales with duration
    var rC = L.qrsOnset + p.qrs * 0.42;
    var qC = L.qrsOnset + p.qrs * 0.12;
    var sC = L.qrsOnset + p.qrs * 0.74;
    var y = 0;
    y += gauss(t, L.pCenter, a.p, 17);                       // P
    y += gauss(t, qC, -0.06 * (a.r > 0.15 ? 1 : 0.3), qw * 0.6); // small q
    y += gauss(t, rC, a.r, qw);                              // R (up)
    y += gauss(t, sC, -a.s, qw * 0.9);                       // S (down)
    // ST level: smooth plateau from J to T onset
    var stOn = L.j, stOff = L.tCenter - L.tWidth;
    if (t > stOn && t < stOff) {
      var ramp = clamp((t - stOn) / 30, 0, 1);
      y += a.st * ramp;
    }
    y += gauss(t, L.tCenter, a.t, L.tWidth);                 // T
    return y;
  }

  // Build a polyline (px points) for a lead across a strip of given pixel width.
  // y0 = baseline px (positive down). Returns {points, beats, L}.
  function leadPoints(lead, p, widthPx, y0, opts) {
    opts = opts || {};
    var a = leadAmps(lead, p);
    var L = landmarks(p);
    var rr = 60000 / p.rate;                  // cycle length ms
    var zoom = opts.zoom || 1;
    var step = 2;                              // px sampling
    var pts = [];
    var seedPhase = (opts.seed || 0);
    for (var x = 0; x <= widthPx; x += step) {
      var ms = pxToMs(x / zoom) + seedPhase;
      var tc = ((ms % rr) + rr) % rr;
      var v = valueAt(tc, a, p, L);
      // gentle per-beat P variation if non-sinus
      if (p.pMorph < 1) {
        var beatIdx = Math.floor(ms / rr);
        v += gauss(tc, L.pCenter, a.p * (Math.sin(beatIdx * 2.3) * (1 - p.pMorph)), 17);
      }
      var noise = p.artifact ? (Math.sin(ms / 7.3) * 0.04 + Math.sin(ms / 1.7) * 0.03 + (rnd(ms) - 0.5) * 0.06) * p.artifact * 3 : 0;
      var yPx = y0 - mvToPx(v + noise) * zoom;
      pts.push(x.toFixed(1) + ',' + yPx.toFixed(1));
    }
    return { points: pts.join(' '), L: L, rr: rr, amps: a, y0: y0 };
  }
  function rnd(n) { var s = Math.sin(n * 12.9898) * 43758.5453; return s - Math.floor(s); }

  // ---- SVG helpers ---------------------------------------------------------
  function gridSVG(w, h) {
    // calibrated pink grid: small (1mm) + big (5mm) boxes
    var parts = ['<g class="ecg-grid-small">'];
    for (var x = 0; x <= w; x += SMALL) parts.push('<line x1="' + x + '" y1="0" x2="' + x + '" y2="' + h + '"/>');
    for (var y = 0; y <= h; y += SMALL) parts.push('<line x1="0" y1="' + y + '" x2="' + w + '" y2="' + y + '"/>');
    parts.push('</g><g class="ecg-grid-big">');
    for (var X = 0; X <= w; X += BIG) parts.push('<line x1="' + X + '" y1="0" x2="' + X + '" y2="' + h + '"/>');
    for (var Y = 0; Y <= h; Y += BIG) parts.push('<line x1="0" y1="' + Y + '" x2="' + w + '" y2="' + Y + '"/>');
    parts.push('</g>');
    return parts.join('');
  }

  // Render a single lead strip as standalone SVG markup.
  function renderLead(lead, p, opts) {
    opts = opts || {};
    var w = opts.w || 520, h = opts.h || 150;
    var y0 = opts.y0 || h * 0.55;
    var lp = leadPoints(lead, p, w, y0, opts);
    var cal = opts.cal !== false ? calPulse(y0) : '';
    var extra = opts.overlay || '';
    return '<svg class="ecg-svg" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="xMidYMid meet" role="img" aria-label="ECG lead ' + lead + '">' +
      gridSVG(w, h) + cal +
      '<polyline class="ecg-trace" points="' + lp.points + '" />' +
      (opts.leadLabel !== false ? '<text class="ecg-lead-label" x="6" y="16">' + lead + '</text>' : '') +
      extra + '</svg>';
  }

  // A 10mm x 0.2s calibration pulse at the left margin.
  function calPulse(y0) {
    var top = y0 - mvToPx(1);
    var x0 = 4, x1 = x0 + xOf(80), x2 = x1, x3 = x1 + xOf(120);
    return '<polyline class="ecg-cal" points="' +
      x0 + ',' + y0 + ' ' + x0 + ',' + y0 + ' ' + (x0) + ',' + top + ' ' + (x0 + xOf(80)) + ',' + top + ' ' + (x0 + xOf(80)) + ',' + y0 + '" />';
  }

  // Standard 12-lead layout: 3 rows x 4 cols + a rhythm strip (lead II).
  var GRID12 = [
    ['I', 'aVR', 'V1', 'V4'],
    ['II', 'aVL', 'V2', 'V5'],
    ['III', 'aVF', 'V3', 'V6']
  ];
  function render12(p, opts) {
    opts = opts || {};
    var colW = opts.colW || 168, rowH = opts.rowH || 104, pad = 2;
    var w = colW * 4, h = rowH * 3 + rowH; // +1 row for rhythm strip
    var svg = ['<svg class="ecg-svg ecg-12" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="xMidYMid meet" role="img" aria-label="12-lead ECG">'];
    svg.push(gridSVG(w, h));
    for (var r = 0; r < 3; r++) {
      for (var c = 0; c < 4; c++) {
        var lead = GRID12[r][c];
        var ox = c * colW, oy = r * rowH;
        var y0 = oy + rowH * 0.55;
        var lp = leadPoints(lead, p, colW - pad * 2, y0, { seed: c * 240 });
        var pts = shift(lp.points, ox + pad);
        var hl = (opts.highlight && opts.highlight.indexOf(lead) >= 0) ? ' ecg-trace-hl' : '';
        svg.push('<polyline class="ecg-trace' + hl + '" points="' + pts + '" />');
        svg.push('<text class="ecg-lead-label" x="' + (ox + 6) + '" y="' + (oy + 16) + '">' + lead + '</text>');
        if (c > 0) svg.push('<line class="ecg-col-sep" x1="' + ox + '" y1="' + (oy + 6) + '" x2="' + ox + '" y2="' + (oy + rowH - 6) + '"/>');
      }
    }
    // rhythm strip (lead II, full width)
    var ry0 = 3 * rowH + rowH * 0.5;
    var rlp = leadPoints('II', p, w - 4, ry0, {});
    svg.push('<polyline class="ecg-trace" points="' + shift(rlp.points, 2) + '" />');
    svg.push('<text class="ecg-lead-label" x="6" y="' + (3 * rowH + 16) + '">II</text>');
    svg.push('</svg>');
    return svg.join('');
  }
  function shift(points, dx) {
    return points.split(' ').map(function (pt) { var ab = pt.split(','); return (parseFloat(ab[0]) + dx).toFixed(1) + ',' + ab[1]; }).join(' ');
  }

  // ========================================================================
  // REAL-DATA rendering — from cases.json (PTB-XL+ median beats in mV + raw
  // lead-II strips). The calibration is identical, so box-counting on a real
  // median beat yields the real ms and scoring compares to the real 12SL value.
  // ========================================================================
  function _baseline(arr, mode) {
    if (mode === 'median') { var s = arr.slice().sort(function (a, b) { return a - b; }); return s[Math.floor(s.length / 2)] || 0; }
    var n = Math.min(5, arr.length), t = 0; for (var i = 0; i < n; i++) t += arr[i]; return n ? t / n : 0; // start baseline
  }
  // Plot a raw sample array (mV) as a polyline; x = sample index -> time -> px.
  function realPoints(arr, fs, y0, opts) {
    opts = opts || {}; var zoom = opts.zoom || 1, gain = opts.gain || 1, x0 = opts.x0 || 0;
    var b0 = opts.baseline === false ? 0 : _baseline(arr, opts.baseline === 'median' ? 'median' : 'start');
    var dt = 1000 / (fs || 100), pts = [];
    for (var i = 0; i < arr.length; i++) pts.push((x0 + xOf(i * dt) * zoom).toFixed(1) + ',' + (y0 - mvToPx((arr[i] - b0) * gain) * zoom).toFixed(1));
    return pts.join(' ');
  }
  // Tile a median beat at the case's true RR (so the strip shows the real rate).
  function medianTiled(beat, fs, rate, widthPx, y0, opts) {
    opts = opts || {}; var gain = opts.gain || 1, zoom = opts.zoom || 1, b0 = _baseline(beat, 'start');
    var dt = 1000 / (fs || 100), beatDur = beat.length * dt, rr = 60000 / (rate || 75);
    var scale = Math.min(1, (rr * 0.92) / beatDur), pts = [];
    for (var x = 0; x <= widthPx; x += 2) {
      var ph = (pxToMs(x / zoom)) % rr, bms = ph / scale, v = 0;
      if (bms < beatDur) { var idx = bms / dt, i0 = Math.floor(idx), f = idx - i0, a = beat[i0], bb = beat[Math.min(beat.length - 1, i0 + 1)]; v = (a + (bb - a) * f) - b0; }
      pts.push(x.toFixed(1) + ',' + (y0 - mvToPx(v * gain) * zoom).toFixed(1));
    }
    return pts.join(' ');
  }
  function renderRealStrip(arr, fs, opts) {
    opts = opts || {}; var w = opts.w || 480, h = opts.h || 120, y0 = opts.y0 || h * 0.5;
    return '<svg class="ecg-svg" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="xMidYMid meet" role="img" aria-label="ECG strip">' +
      gridSVG(w, h) + '<polyline class="ecg-trace" points="' + realPoints(arr, fs, y0, { baseline: 'median', gain: opts.gain || 1, zoom: opts.zoom || 1 }) + '" />' +
      (opts.leadLabel === false ? '' : '<text class="ecg-lead-label" x="6" y="16">II</text>') + '</svg>';
  }
  // Real 12-lead from median beats (tiled at true RR) + a lead-II rhythm strip.
  function render12Real(c, opts) {
    opts = opts || {}; var colW = opts.colW || 168, rowH = opts.rowH || 104, pad = 4, gain = opts.gain || 0.7;
    var w = colW * 4, h = rowH * 4, fs = c.median_fs || 100, rate = (c.features && c.features.heart_rate) || 75;
    var svg = ['<svg class="ecg-svg ecg-12" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="xMidYMid meet" role="img" aria-label="12-lead ECG">', gridSVG(w, h)];
    for (var r = 0; r < 3; r++) for (var col = 0; col < 4; col++) {
      var lead = GRID12[r][col], beat = c.median && c.median[lead]; if (!beat) continue;
      var ox = col * colW, oy = r * rowH, y0 = oy + rowH * 0.55;
      var pts = shift(medianTiled(beat, fs, rate, colW - pad * 2, y0, { gain: gain }), ox + pad);
      var hl = (opts.highlight && opts.highlight.indexOf(lead) >= 0) ? ' ecg-trace-hl' : '';
      svg.push('<polyline class="ecg-trace' + hl + '" points="' + pts + '" />');
      svg.push('<text class="ecg-lead-label" x="' + (ox + 6) + '" y="' + (oy + 16) + '">' + lead + '</text>');
      if (col > 0) svg.push('<line class="ecg-col-sep" x1="' + ox + '" y1="' + (oy + 6) + '" x2="' + ox + '" y2="' + (oy + rowH - 6) + '"/>');
    }
    var ry0 = 3 * rowH + rowH * 0.5;
    var rhythm = (c.lead_ii && c.lead_ii.length) ? realPoints(c.lead_ii, 50, ry0, { baseline: 'median', gain: 1 }) : medianTiled(c.median['II'], fs, rate, w - 4, ry0, { gain: 1 });
    svg.push('<polyline class="ecg-trace" points="' + shift(rhythm, 2) + '" />');
    svg.push('<text class="ecg-lead-label" x="6" y="' + (3 * rowH + 16) + '">II — rhythm strip (use for rate &amp; rhythm)</text>');
    svg.push('</svg>');
    return svg.join('');
  }
  // Derive the ground-truth finding concepts for a real case from its 12SL features.
  function caseTruth(c) {
    var f = c.features || {}, t = {};
    var hr = f.heart_rate; t.rate = hr == null ? 'normal_rate' : (hr < 60 ? 'brady' : hr > 100 ? 'tachy' : 'normal_rate');
    // only assert "sinus" where the data confirms it; null = don't grade this component
    t.rhythm = (c.category === 'noisy' || c.sinus === false) ? null : 'sinus';
    var ax = f.axis_deg; t.axis = ax == null ? 'normal_axis' : (ax < -30 ? 'left_axis' : ax > 90 ? 'right_axis' : 'normal_axis');
    var pr = f.pr_ms; t.pr = pr != null && pr > 200 ? 'long_pr' : 'normal_pr';
    var qrs = f.qrs_ms; t.qrs = qrs != null && qrs >= 120 ? 'wide_qrs' : 'normal_qrs';
    // only assert "flat ST" where there's no ST/T abnormality on record
    t.st = (c.st_normal === false) ? null : 'flat_st';
    return t;
  }

  global.ECG = {
    PX_PER_MM: PX_PER_MM, SMALL: SMALL, BIG: BIG,
    xOf: xOf, pxToMs: pxToMs, mvToPx: mvToPx,
    HEX: HEX, proj: proj, rad: rad, gauss: gauss, clamp: clamp,
    params: params, leadAmps: leadAmps, landmarks: landmarks, leadPoints: leadPoints,
    gridSVG: gridSVG, renderLead: renderLead, render12: render12, calPulse: calPulse,
    PRECORDIAL: PRECORDIAL, DEFAULTS: DEFAULTS,
    realPoints: realPoints, medianTiled: medianTiled, renderRealStrip: renderRealStrip,
    render12Real: render12Real, caseTruth: caseTruth
  };
})(window);
