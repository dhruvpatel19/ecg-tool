/* engines.js — reusable interaction engines for the Foundations module.
 * Each returns a small controller object and mounts itself into a host element.
 * All measurement engines read the SAME calibrated coordinate system as ecg.js,
 * so box-counts map to real ms/mV and scoring compares to the true model value.
 */
(function (global) {
  'use strict';
  var E = global.ECG;
  function el(tag, cls, html) { var d = document.createElement(tag); if (cls) d.className = cls; if (html != null) d.innerHTML = html; return d; }
  function svgNS(tag, attrs) { var n = document.createElementNS('http://www.w3.org/2000/svg', tag); if (attrs) for (var k in attrs) n.setAttribute(k, attrs[k]); return n; }
  function stepButton(label, action) { var b = el('button', 'step-btn', label); b.type = 'button'; b.onclick = action; return b; }
  function accessibleHandle(svg, handle, label, getValue, setValue, step) {
    handle.setAttribute('tabindex', '0'); handle.setAttribute('role', 'slider');
    handle.setAttribute('aria-label', label); handle.setAttribute('aria-orientation', 'horizontal');
    handle.setAttribute('aria-valuemin', '4'); handle.setAttribute('aria-valuemax', Math.max(4, svg.viewBox.baseVal.width - 4));
    function sync() { handle.setAttribute('aria-valuenow', Math.round(getValue())); }
    handle.addEventListener('focus', function () { svg._activeHandle = { get: getValue, set: setValue }; sync(); });
    handle.addEventListener('keydown', function (e) {
      var d = e.shiftKey ? step * 5 : step;
      if (e.key === 'ArrowLeft') { e.preventDefault(); setValue(getValue() - d); sync(); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); setValue(getValue() + d); sync(); }
      else if (e.key === 'Home') { e.preventDefault(); setValue(4); sync(); }
      else if (e.key === 'End') { e.preventDefault(); setValue(svg.viewBox.baseVal.width - 4); sync(); }
    });
    return sync;
  }
  function handleControls(wrap, svg, start, end, step) {
    var row = el('div', 'handle-controls');
    row.setAttribute('aria-label', 'Measurement handle controls');
    row.appendChild(stepButton('Start left', function () { start.set(start.get() - step); }));
    row.appendChild(stepButton('Start right', function () { start.set(start.get() + step); }));
    row.appendChild(stepButton('End left', function () { end.set(end.get() - step); }));
    row.appendChild(stepButton('End right', function () { end.set(end.get() + step); }));
    var note = el('span', 'sec', 'Select a handle, then tap the trace or use arrow keys. Shift+arrow moves five steps.'); row.appendChild(note);
    svg.addEventListener('click', function (e) {
      if (!svg._activeHandle || e.target.classList.contains('mk-knob')) return;
      var r = svg.getBoundingClientRect(); var x = (e.clientX - r.left) / r.width * svg.viewBox.baseVal.width;
      svg._activeHandle.set(x);
    });
    var readout = wrap.querySelector('.bc-readout'); wrap.insertBefore(row, readout || null);
  }

  // ========================================================================
  // 1. WAVEFRONT — S1 keystone. Conduction schematic + the waveform drawing in
  //    real time, two-pass (plain words -> P/QRS/T labels + drag-to-place).
  // ========================================================================
  function wavefront(host, opts) {
    opts = opts || {};
    var onDone = opts.onDone || function () {};
    var p = E.params({ rate: 60 });
    var W = 560, H = 150, y0 = H * 0.55;
    var rr = 60000 / p.rate;                 // one cardiac cycle
    var Z = W / E.xOf(rr);                    // zoom so exactly ONE beat fills the width (synced to the narration)
    var lp = E.leadPoints('II', p, W, y0, { zoom: Z });
    var allPts = lp.points.split(' ');
    var L = lp.L;

    var wrap = el('div', 'wf');
    wrap.innerHTML =
      '<div class="wf-stage">' +
        '<div class="wf-heart">' + heartSVG() + '</div>' +
        '<div class="wf-trace"><svg class="ecg-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet">' +
          E.gridSVG(W, H) +
          '<polyline class="ecg-trace wf-poly" points="" />' +
          '<circle class="ecg-pen" id="wfpen" r="4.5" opacity="0"/>' +
          '<g class="wf-labels"></g>' +
        '</svg></div>' +
      '</div>' +
      '<div class="wf-caption" id="wfcap"></div>' +
      '<div class="row wf-controls">' +
        '<button class="accent" id="wfplay">▶ Watch one beat</button>' +
        '<button id="wfreplay">↻ Replay</button>' +
        '<label class="wf-scrub-l">or step through it <input type="range" id="wfscrub" min="0" max="1000" value="0" step="1" aria-label="One-beat animation position"></label>' +
        '<button id="wflabels" disabled>Show P / QRS / T ▸</button>' +
      '</div>' +
      '<div class="wf-dragbank" id="wfbank" hidden></div>';
    host.appendChild(wrap);

    var poly = wrap.querySelector('.wf-poly');
    var cap = wrap.querySelector('#wfcap');
    var scrub = wrap.querySelector('#wfscrub');
    var heart = wrap.querySelector('.wf-heart svg');

    // phases of one cycle expressed as fractions of rr aligned to landmarks
    function phaseAt(ms) {
      if (ms < L.pOnset) return { key: 'rest', txt: 'Resting — between beats the tracing sits on the baseline.' };
      if (ms < L.qrsOnset - 10) return { key: 'p', txt: 'The atria electrically activate — a small, gentle bump, the P wave.' };
      if (ms < L.qrsOnset) return { key: 'av', txt: 'A brief hold at the AV node — the line rests flat for a moment while the signal is delayed.' };
      if (ms < L.j) return { key: 'qrs', txt: 'The ventricles activate quickly — a tall, sharp spike, the QRS.' };
      if (ms < L.tCenter - L.tWidth) return { key: 'st', txt: 'A short flat stretch — the ventricles are fully active.' };
      if (ms < L.tEnd) return { key: 't', txt: 'The ventricles reset (repolarize) — a rounded bump, the T wave.' };
      return { key: 'rest', txt: 'And back to rest. That whole shape was one heartbeat.' };
    }
    var pen = wrap.querySelector('#wfpen');
    // Spend most of the run on the active beat; sweep the flat resting tail quickly (no dead air).
    var aFrac = E.clamp(L.tEnd / rr, 0.4, 0.8);
    function easeBeat(f) { return f < 0.85 ? (f / 0.85) * aFrac : aFrac + ((f - 0.85) / 0.15) * (1 - aFrac); }
    function revealMs(ms) {
      var n = Math.max(1, Math.round(allPts.length * (ms / rr)));
      var shown = allPts.slice(0, n);
      poly.setAttribute('points', shown.join(' '));
      var ph = phaseAt(ms); cap.textContent = ph.txt;
      paintHeart(heart, ms, L);
      if (pen) { var last = shown[shown.length - 1].split(','); pen.setAttribute('cx', last[0]); pen.setAttribute('cy', last[1]); pen.setAttribute('opacity', (ms > 20 && ms < L.tEnd) ? 1 : 0); } // the "pen" writing the trace
    }
    var raf = null, t0 = null, DUR = 8000, labelsShown = false;  // slow, legible draw
    function frame(ts) {
      if (t0 == null) t0 = ts;
      var f = Math.min(1, (ts - t0) / DUR);
      var ms = rr * easeBeat(f);
      scrub.value = Math.round(ms / rr * 1000);
      revealMs(ms);
      if (f < 1) raf = requestAnimationFrame(frame);
      else { wrap.querySelector('#wfreplay').disabled = false; unlockLabels(); }
    }
    function play() {
      cancelAnimationFrame(raf); t0 = null;
      wrap.querySelector('#wfplay').disabled = true;
      raf = requestAnimationFrame(frame);
      // Fallback if rAF is throttled (background tab): finish the draw + unlock labels.
      setTimeout(function () { revealMs(rr); unlockLabels(); }, DUR + 1200);
    }
    function unlockLabels() { var b = wrap.querySelector('#wflabels'); if (b.disabled) { b.disabled = false; onDone(); } }
    wrap.querySelector('#wfplay').onclick = play;
    wrap.querySelector('#wfreplay').onclick = function () { wrap.querySelector('#wfplay').disabled = true; play(); };
    // Scrub is usable any time (a throttled animation never traps the learner); dragging to the end unlocks labels.
    scrub.oninput = function () { cancelAnimationFrame(raf); revealMs((+scrub.value / 1000) * rr); if (+scrub.value >= 950) unlockLabels(); };

    wrap.querySelector('#wflabels').onclick = function () {
      if (labelsShown) return; labelsShown = true;
      this.textContent = 'Tap a name, then tap its wave ▾';
      scrub.value = 1000; revealMs(rr);
      buildLabelPlacer(wrap, poly, L, W, y0, rr, opts.onEvidence || function () {});
    };
    revealMs(0);
    cap.textContent = 'Press ▶ to watch the wave draw the trace — or use the slider to step through it yourself.';
    return { play: play };
  }

  // Tap-to-place: tap a name chip to arm it, then tap the trace near its wave.
  // Pointer/click based, so it works on touch and trackpad (no HTML5 drag-and-drop).
  // Targets use the one-beat-fills-width mapping x = (landmark_ms / rr) * W.
  function buildLabelPlacer(wrap, poly, L, W, y0, rr, onEvidence) {
    var bank = wrap.querySelector('#wfbank'); bank.hidden = false;
    var X = function (ms) { return (ms / rr) * W; };
    var targets = [
      { name: 'P', x: X(L.pCenter), tip: 'the small first bump' },
      { name: 'QRS', x: X(L.qrsOnset + 40), tip: 'the tall sharp spike' },
      { name: 'T', x: X(L.tCenter), tip: 'the rounded last bump' }
    ];
    var placed = {}, armed = null, errors = 0;
    var labelG = wrap.querySelector('.wf-labels');
    var svg = poly.ownerSVGElement;
    bank.innerHTML = '<span class="sec">Choose a name, then tap its wave—or choose the matching waveform target:</span>';
    var chips = {};
    targets.forEach(function (t) {
      var chip = el('button', 'wf-chip', t.name); chip.type = 'button'; chip.setAttribute('aria-pressed', 'false'); chips[t.name] = chip;
      chip.onclick = function () {
        if (placed[t.name]) return;
        armed = t.name;
        Object.keys(chips).forEach(function (k) { var on = k === armed && !placed[k]; chips[k].classList.toggle('armed', on); chips[k].setAttribute('aria-pressed', on ? 'true' : 'false'); });
        Tutor.nudge('Now tap ' + t.tip + ' on the trace.');
      };
      bank.appendChild(chip);
    });
    var targetRow = el('div', 'wf-targets'); targetRow.setAttribute('aria-label', 'Waveform targets'); bank.appendChild(targetRow);
    targets.forEach(function (target) {
      targetRow.appendChild(stepButton('Place on ' + target.tip, function () { attempt(target); }));
    });
    function attempt(target) {
      if (!armed || placed[armed]) { Tutor.nudge('Choose P, QRS, or T first.'); return; }
      if (armed === target.name) {
        placed[armed] = true; chips[armed].classList.remove('armed'); chips[armed].classList.add('done'); chips[armed].setAttribute('aria-pressed', 'false'); chips[armed].disabled = true;
        var lab = svgNS('text', { x: target.x, y: 22, class: 'wf-placed' }); lab.textContent = armed; labelG.appendChild(lab);
        labelG.appendChild(svgNS('line', { x1: target.x, y1: 26, x2: target.x, y2: y0 - 4, class: 'wf-tick' }));
        armed = null;
        if (Object.keys(placed).length === 3) {
          bank.appendChild(el('div', 'fb ok', 'That’s the whole vocabulary of a heartbeat: <b>P</b> = atrial activation, <b>QRS</b> = ventricular activation, <b>T</b> = ventricular reset. Everything else we measure hangs off these three.'));
          onEvidence({ correct: true, score: 1, attempts: errors + 1 });
        }
      } else { errors++; Tutor.nudge('Not quite — ' + armed + ' is ' + targets.filter(function (x) { return x.name === armed; })[0].tip + '. Try again.'); }
    }
    svg.style.cursor = 'crosshair';
    svg.addEventListener('click', function (e) {
      if (!armed || placed[armed]) return;
      var t = targets.filter(function (x) { return x.name === armed; })[0];
      var rect = svg.getBoundingClientRect();
      var clickX = (e.clientX - rect.left) / rect.width * W;
      if (Math.abs(clickX - t.x) < 70) attempt(t);
      else { errors++; Tutor.nudge('Not quite — ' + t.name + ' is ' + t.tip + '. Tap closer to it.'); }
    });
  }

  // Anatomical coronal-section conduction diagram (anterior view; patient's right =
  // viewer's left). Gradient-shaded myocardium; LV forms the apex with a thick free
  // wall, RV is a thin upper crescent; the conduction system is routed in real tissue
  // (His in the membranous septum -> RBB down the RV side + LBB's anterior/posterior
  // fascicles down the LV side -> subendocardial Purkinje). Depolarization is a wave
  // masked to the muscle (it never lights the blood pool), driven by paintHeart().
  var HC = {
    RA: "M162 108 C128 104 100 114 100 130 C100 146 124 150 162 148 Z",
    LA: "M170 108 C206 104 246 112 250 130 C250 146 222 150 170 148 Z",
    LV: "M196 172 C226 178 240 210 234 250 C228 296 196 326 166 322 C160 286 168 232 178 196 C182 182 188 174 196 172 Z",
    RV: "M166 178 C132 182 100 198 96 226 C100 252 122 262 144 252 C156 232 162 206 166 178 Z",
    MYO: "M150 358 C106 348 68 296 60 230 C54 176 70 128 110 114 C150 102 156 102 184 102 C218 102 252 110 278 134 C306 160 302 234 284 288 C264 346 204 368 150 358 Z"
  };
  function heartSVG() {
    return `<svg viewBox="0 0 360 384" role="img" aria-label="Heart in coronal section showing the conduction system and the spread of depolarization">
  <defs>
    <radialGradient id="hcMuscle" cx="44%" cy="38%" r="78%">
      <stop offset="0%" stop-color="#e6a695"/><stop offset="58%" stop-color="#d2806c"/><stop offset="100%" stop-color="#a9543f"/>
    </radialGradient>
    <radialGradient id="hcCav" cx="48%" cy="34%" r="72%">
      <stop offset="0%" stop-color="#7c3030"/><stop offset="100%" stop-color="#531d1d"/>
    </radialGradient>
    <linearGradient id="hcAorta" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#cf7d75"/><stop offset="100%" stop-color="#b3655d"/></linearGradient>
    <linearGradient id="hcVein" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#8fb5d5"/><stop offset="100%" stop-color="#6c97bd"/></linearGradient>
    <radialGradient id="hcDepol" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#ffaa44"/><stop offset="100%" stop-color="#ef7d28"/></radialGradient>
    <filter id="hcSoft" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="3"/></filter>
    <filter id="hcGlow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="1.6"/></filter>
    <mask id="hcMask">
      <path d="${HC.MYO}" fill="#fff"/>
      <path d="${HC.RA}" fill="#000"/><path d="${HC.LA}" fill="#000"/><path d="${HC.LV}" fill="#000"/><path d="${HC.RV}" fill="#000"/>
    </mask>
  </defs>
  <path fill="url(#hcVein)" stroke="#5f8bb2" stroke-width="1" d="M98 96 C94 64 94 36 98 14 L120 14 C122 40 120 70 126 96 Z"/>
  <path fill="url(#hcVein)" stroke="#5f8bb2" stroke-width="1" d="M150 92 C140 58 138 32 150 12 C160 24 168 28 178 26 C172 52 170 74 178 96 Z"/>
  <path fill="url(#hcAorta)" stroke="#a85f57" stroke-width="1" d="M190 96 C186 58 188 30 206 18 C234 0 268 16 262 58 C260 82 250 100 240 110 C246 88 246 62 240 48 C232 30 212 32 208 50 C204 64 206 80 208 96 Z"/>
  <path fill="none" stroke="url(#hcAorta)" stroke-width="7" stroke-linecap="round" opacity=".88" d="M252 124 C278 118 300 120 320 126"/>
  <path fill="none" stroke="url(#hcAorta)" stroke-width="6" stroke-linecap="round" opacity=".85" d="M254 140 C280 142 302 150 320 158"/>
  <path fill="url(#hcMuscle)" stroke="#9a4a39" stroke-width="1.5" d="${HC.MYO}"/>
  <path fill="none" stroke="#8a4534" stroke-width="1.1" opacity=".35" d="M70 158 C120 172 240 172 296 156"/>
  <path fill="url(#hcCav)" d="${HC.RA}"/><path fill="url(#hcCav)" d="${HC.LA}"/><path fill="url(#hcCav)" d="${HC.LV}"/><path fill="url(#hcCav)" d="${HC.RV}"/>
  <path fill="none" stroke="#ecb6a8" stroke-width=".7" opacity=".45" d="${HC.LV}"/>
  <path fill="none" stroke="#ecb6a8" stroke-width=".7" opacity=".4" d="${HC.RV}"/>
  <path fill="none" stroke="#9a4a39" stroke-width="2.4" opacity=".5" d="M170 160 C166 210 162 268 156 320"/>
  <path fill="none" stroke="#7d463c" stroke-width="1.6" opacity=".5" d="M100 156 L162 158 M170 158 L250 156"/>
  <g mask="url(#hcMask)" filter="url(#hcSoft)">
    <ellipse data-zone="ra" opacity="0" fill="url(#hcDepol)" cx="126" cy="128" rx="46" ry="32"/>
    <ellipse data-zone="la" opacity="0" fill="url(#hcDepol)" cx="214" cy="128" rx="50" ry="32"/>
    <ellipse data-zone="septum" opacity="0" fill="url(#hcDepol)" cx="164" cy="238" rx="26" ry="88"/>
    <ellipse data-zone="apex" opacity="0" fill="url(#hcDepol)" cx="150" cy="330" rx="60" ry="44"/>
    <ellipse data-zone="rvfw" opacity="0" fill="url(#hcDepol)" cx="86" cy="208" rx="38" ry="62"/>
    <ellipse data-zone="lvfw" opacity="0" fill="url(#hcDepol)" cx="270" cy="238" rx="38" ry="70"/>
    <ellipse data-zone="base" opacity="0" fill="url(#hcDepol)" cx="180" cy="180" rx="104" ry="30"/>
  </g>
  <g filter="url(#hcGlow)">
    <path data-cond="atrtract" fill="none" stroke="#d49d2a" stroke-width="1.3" opacity=".45" stroke-dasharray="2 3" stroke-linecap="round" d="M114 102 C140 114 156 134 170 154 M114 102 C152 98 204 102 238 118"/>
    <path data-cond="his" fill="none" stroke="#dca62b" stroke-width="3" stroke-linecap="round" d="M171 156 L172 174"/>
    <path data-cond="rbb" fill="none" stroke="#dca62b" stroke-width="2" stroke-linecap="round" d="M171 175 C162 210 152 252 146 290"/>
    <path data-cond="lbb" fill="none" stroke="#dca62b" stroke-width="2.3" stroke-linecap="round" d="M174 175 C184 196 200 212 214 222 M174 177 C182 212 192 254 196 290"/>
    <path data-cond="purk" fill="none" stroke="#e3b13c" stroke-width="1.1" stroke-linecap="round" opacity=".8" d="M146 290 q-9 10 -12 22 M146 290 q7 12 5 24 M146 290 q-2 16 -7 24 M214 222 q13 8 16 20 M214 222 q-2 18 -7 26 M196 290 q11 11 11 22 M196 290 q-10 12 -13 22 M196 290 q2 16 -3 26"/>
  </g>
  <circle data-node="sa" cx="112" cy="100" r="6.5" fill="#2f6fd0" stroke="#fff" stroke-width="1.4"/>
  <circle data-node="av" cx="170" cy="157" r="5.5" fill="#dca62b" stroke="#fff" stroke-width="1.2"/>
  <circle id="wfdot" class="wfdot" cx="112" cy="100" r="6" fill="#ff8a1e" opacity="0" filter="url(#hcSoft)"/>
  <text class="sch-l" x="118" y="132">RA</text>
  <text class="sch-l" x="208" y="132">LA</text>
  <text class="sch-l" x="108" y="216">RV</text>
  <text class="sch-l" x="210" y="252">LV</text>
  <text class="sch-l mut" x="18" y="104">SA node</text>
  <text class="sch-l mut" x="184" y="150">AV node</text>
  <text class="sch-l mut" x="186" y="184">His</text>
  <text class="sch-l mut" x="116" y="350">Purkinje</text>
  <text class="sch-l mut" x="210" y="34">aorta</text>
  <text class="sch-l mut" x="138" y="22">PT</text>
  <text class="sch-l mut" x="54" y="18">SVC</text>
</svg>`;
  }

  // Drive the conduction lighting + depolarization wave in sync with the trace time `ms`.
  // P (atria) -> PR (AV-node hold) -> QRS (His/bundles/Purkinje fire; muscle depolarizes
  // septum -> apex -> free walls -> base) -> T (repolarize/fade). Overlays are masked to
  // muscle so the wave only ever lights real tissue.
  function paintHeart(heart, ms, L) {
    function ramp(a, b) { return ms <= a ? 0 : ms >= b ? 1 : (ms - a) / (b - a); }
    function lerp(a, b, u) { return a + (b - a) * u; }
    function zone(name, v) { var e = heart.querySelector('[data-zone="' + name + '"]'); if (e) e.setAttribute('opacity', Math.max(0, Math.min(1, v)).toFixed(3)); }
    function cond(name, on) { var e = heart.querySelector('[data-cond="' + name + '"]'); if (e) { e.style.stroke = on ? '#ff7d18' : ''; e.style.opacity = on ? (name === 'atrtract' ? '.85' : '1') : ''; } }
    function node(name, on, base) { var e = heart.querySelector('[data-node="' + name + '"]'); if (e) e.setAttribute('fill', on ? '#ff7d18' : base); }
    var pdur = Math.max(1, L.qrsOnset - L.pOnset);
    var qdur = Math.max(1, L.j - L.qrsOnset);
    // atria depolarize on P, fade as the ventricles take over
    var afade = 1 - ramp(L.qrsOnset, L.qrsOnset + 0.5 * qdur);
    zone('ra', ramp(L.pOnset, L.pOnset + 0.45 * pdur) * afade * 0.7);
    zone('la', ramp(L.pOnset + 0.3 * pdur, L.qrsOnset) * afade * 0.7);
    cond('atrtract', ms >= L.pOnset && ms < L.qrsOnset);
    node('sa', ms >= L.pOnset && ms < L.pOnset + 0.35 * pdur, '#2f6fd0');
    node('av', ms >= L.pCenter && ms < L.qrsOnset, '#dca62b');
    // ventricular conduction tree fires through the QRS
    cond('his', ms >= L.qrsOnset - 0.1 * qdur && ms < L.j);
    cond('rbb', ms >= L.qrsOnset && ms < L.j);
    cond('lbb', ms >= L.qrsOnset && ms < L.j);
    cond('purk', ms >= L.qrsOnset + 0.15 * qdur && ms < L.j + 0.1 * qdur);
    // ventricular muscle: septum -> apex -> free walls -> base; hold through ST; fade on T
    var hold = 1 - ramp(L.tCenter - L.tWidth, L.tEnd);
    zone('septum', ramp(L.qrsOnset, L.qrsOnset + 0.25 * qdur) * hold * 0.62);
    zone('apex', ramp(L.qrsOnset + 0.2 * qdur, L.qrsOnset + 0.5 * qdur) * hold * 0.62);
    zone('rvfw', ramp(L.qrsOnset + 0.35 * qdur, L.qrsOnset + 0.72 * qdur) * hold * 0.6);
    zone('lvfw', ramp(L.qrsOnset + 0.4 * qdur, L.qrsOnset + 0.8 * qdur) * hold * 0.62);
    zone('base', ramp(L.qrsOnset + 0.6 * qdur, L.j) * hold * 0.58);
    // traveling wavefront dot
    var dot = heart.querySelector('#wfdot');
    if (dot) {
      var x = 112, y = 100, o = 0;
      if (ms < L.pOnset) { o = 0; }
      else if (ms < L.qrsOnset) { var u = ramp(L.pOnset, L.qrsOnset); x = lerp(112, 170, u); y = lerp(100, 157, u); o = 0.9; }
      else if (ms < L.j) { var v = ramp(L.qrsOnset, L.j); x = lerp(172, 150, v); y = lerp(174, 322, v); o = 0.95; }
      else { o = 0; }
      dot.setAttribute('cx', x.toFixed(1)); dot.setAttribute('cy', y.toFixed(1)); dot.setAttribute('opacity', o);
    }
  }

  // ========================================================================
  // 2. RULER / BOX-COUNT — S2: read the grid; count boxes; scored vs truth.
  // ========================================================================
  function boxCount(host, opts) {
    opts = opts || {};
    var trueMs = opts.trueMs;                 // ground-truth span in ms
    var label = opts.label || 'this span';
    var onScore = opts.onScore || function () {};
    var W = 480, H = 130, y0 = 70;
    var p = opts.params || E.params();
    var wrap = el('div', 'measure');
    wrap.innerHTML =
      '<svg class="ecg-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet">' +
        E.gridSVG(W, H) +
        (opts.lead ? '<polyline class="ecg-trace" points="' + E.leadPoints(opts.lead, p, W, y0, {}).points + '" />' : '') +
        '<g class="bc-markers">' +
          '<rect class="bc-span" id="bcSpan" x="120" y="6" width="100" height="' + (H - 12) + '"/>' +
          '<line class="bc-mk" id="bcA" x1="120" y1="6" x2="120" y2="' + (H - 6) + '"/>' +
          '<line class="bc-mk" id="bcB" x1="220" y1="6" x2="220" y2="' + (H - 6) + '"/>' +
          '<circle class="mk-knob" id="bcAk" cx="120" cy="12" r="9"/>' +
          '<circle class="mk-knob" id="bcBk" cx="220" cy="12" r="9"/>' +
        '</g>' +
      '</svg>' +
      '<div class="bc-readout"><span id="bcBoxes">—</span> → <b id="bcMs">— ms</b>' +
        '<button class="accent bc-check" id="bcCheck">Check my count</button></div>' +
      '<div id="bcFb"></div>';
    host.appendChild(wrap);
    var A = wrap.querySelector('#bcA'), B = wrap.querySelector('#bcB'), span = wrap.querySelector('#bcSpan');
    var Ak = wrap.querySelector('#bcAk'), Bk = wrap.querySelector('#bcBk');
    var svg = wrap.querySelector('svg');
    var ax = 120, bx = 184, attempts = 0;   // start off-target (~1.6 big boxes) so the count isn't free
    function upd() {
      A.setAttribute('x1', ax); A.setAttribute('x2', ax); Ak.setAttribute('cx', ax);
      B.setAttribute('x1', bx); B.setAttribute('x2', bx); Bk.setAttribute('cx', bx);
      Ak.setAttribute('aria-valuenow', Math.round(ax)); Bk.setAttribute('aria-valuenow', Math.round(bx));
      var lo = Math.min(ax, bx); span.setAttribute('x', lo); span.setAttribute('width', Math.abs(bx - ax));
      var ms = E.pxToMs(Math.abs(bx - ax));
      wrap.querySelector('#bcBoxes').textContent = (Math.abs(bx - ax) / E.SMALL).toFixed(1) + ' small boxes';
      wrap.querySelector('#bcMs').textContent = Math.round(ms / 10) * 10 + ' ms';
    }
    var setA = function (x) { ax = E.clamp(x, 6, W - 6); upd(); };
    var setB = function (x) { bx = E.clamp(x, 6, W - 6); upd(); };
    drag(svg, A, setA); drag(svg, Ak, setA);
    drag(svg, B, setB); drag(svg, Bk, setB);
    var syncA = accessibleHandle(svg, Ak, 'Start marker position', function () { return ax; }, setA, E.SMALL);
    var syncB = accessibleHandle(svg, Bk, 'End marker position', function () { return bx; }, setB, E.SMALL);
    handleControls(wrap, svg, { get: function () { return ax; }, set: function (x) { setA(x); syncA(); } }, { get: function () { return bx; }, set: function (x) { setB(x); syncB(); } }, E.SMALL);
    wrap.querySelector('#bcCheck').onclick = function () {
      attempts++;
      var ms = E.pxToMs(Math.abs(bx - ax));
      var err = Math.abs(ms - trueMs);
      var fb = wrap.querySelector('#bcFb');
      if (err <= 25) { fb.innerHTML = '<div class="fb ok">Nailed it — you read <b>' + Math.round(ms) + ' ms</b> for ' + label + ' (true value ' + trueMs + ' ms). Box-counting works.</div>'; onScore(true, ms, attempts); }
      else { fb.innerHTML = '<div class="fb warn">You read ' + Math.round(ms) + ' ms; it’s actually <b>' + trueMs + ' ms</b>. Remember: each small box = 40 ms. Slide the markers to ' + (trueMs / 40).toFixed(1) + ' boxes apart and see.</div>'; onScore(false, ms, attempts); }
    };
    upd();
    return wrap;
  }

  // generic horizontal drag of an svg element via pointer; cb(xInViewBox)
  function drag(svg, handle, cb) {
    var W = svg.viewBox.baseVal.width;
    function pt(e) { var r = svg.getBoundingClientRect(); return (e.clientX - r.left) / r.width * W; }
    handle.style.cursor = 'ew-resize';
    handle.addEventListener('pointerdown', function (e) {
      e.preventDefault(); handle.setPointerCapture(e.pointerId); handle.classList.add('dragging');
      function mv(ev) { cb(pt(ev)); }
      function up(ev) { handle.releasePointerCapture(e.pointerId); handle.classList.remove('dragging'); svg.removeEventListener('pointermove', mv); svg.removeEventListener('pointerup', up); }
      svg.addEventListener('pointermove', mv); svg.addEventListener('pointerup', up);
    });
  }

  // ========================================================================
  // 3. SPACING -> RATE slider + 300-rule scoring — S4.
  // ========================================================================
  function rateLab(host, opts) {
    opts = opts || {};
    var onScore = opts.onScore || function () {};
    var W = 520, H = 120, y0 = 64;
    var wrap = el('div', 'ratelab');
    wrap.innerHTML =
      '<div class="ratelab-readout">R–R spacing: <b id="rrBig">4.0</b> big boxes → 300 ÷ <span id="rrDiv">4.0</span> = <b id="rrBpm">75</b> bpm</div>' +
      '<svg class="ecg-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet"><g id="rsvg"></g></svg>' +
      '<label class="ratelab-slider">closer ← spacing → wider<input type="range" id="rspace" min="2" max="8" value="4" step="0.5"></label>' +
      '<div class="row" style="margin-top:8px"><span class="sec">Your turn — a strip appears; type the rate:</span></div>' +
      '<div class="row" id="rquiz" style="margin-top:6px"></div><div id="rfb"></div>';
    host.appendChild(wrap);
    var g = wrap.querySelector('#rsvg');
    function drawAt(bigBoxes) {
      var rrPx = bigBoxes * E.BIG;
      var rate = Math.round(300 / bigBoxes);
      var p = E.params({ rate: rate });
      g.innerHTML = E.gridSVG(W, H) + '<polyline class="ecg-trace" points="' + E.leadPoints('II', p, W, y0, {}).points + '" />';
      wrap.querySelector('#rrBig').textContent = bigBoxes.toFixed(1);
      wrap.querySelector('#rrDiv').textContent = bigBoxes.toFixed(1);
      wrap.querySelector('#rrBpm').textContent = rate;
    }
    wrap.querySelector('#rspace').oninput = function () { drawAt(parseFloat(this.value)); };
    drawAt(4);
    // quiz — a REAL lead-II strip at a known rate when available, else synthetic.
    var qc = opts.quizCase;
    var truth, quizSvg;
    if (qc && qc.lead_ii && qc.features && qc.features.heart_rate) {
      truth = Math.round(qc.features.heart_rate);
      quizSvg = '<svg class="ecg-svg" style="max-width:340px" viewBox="0 0 340 90" preserveAspectRatio="xMidYMid meet">' + E.gridSVG(340, 90) + '<polyline class="ecg-trace" points="' + E.realPoints(qc.lead_ii, 50, 48, { baseline: 'median' }) + '" /></svg>';
    } else {
      truth = 100;
      quizSvg = '<svg class="ecg-svg" style="max-width:320px" viewBox="0 0 320 90" preserveAspectRatio="xMidYMid meet">' + E.gridSVG(320, 90) + '<polyline class="ecg-trace" points="' + E.leadPoints('II', E.params({ rate: 100 }), 320, 48, {}).points + '" /></svg>';
    }
    var quiz = wrap.querySelector('#rquiz');
    quiz.innerHTML = quizSvg + '<input id="rans" style="max-width:120px" placeholder="bpm" inputmode="numeric"><button class="accent" id="rgo">Check</button>';
    wrap.querySelector('#rgo').onclick = function () {
      var v = parseInt(wrap.querySelector('#rans').value, 10);
      var fb = wrap.querySelector('#rfb');
      if (!v) return;
      if (Math.abs(v - truth) <= 12) { fb.innerHTML = '<div class="fb ok">Yes — about <b>' + truth + ' bpm</b>. ' + (qc ? 'Your estimate is close — the printed measurement is ' + truth + ' bpm on this real strip. ' : '') + 'Within ~10–12 bpm is a great read.</div>'; onScore(true); }
      else { fb.innerHTML = '<div class="fb warn">Count the big boxes between two R’s (300 ÷ that). It’s about <b>' + truth + ' bpm</b>. Estimates are approximate — within ~10 is the goal.</div>'; onScore(false); }
    };
    return wrap;
  }

  // ========================================================================
  // 4. INTERVAL HANDLE — S6: drag to measure PR/QRS; recolors at threshold.
  // ========================================================================
  function intervalHandle(host, opts) {
    opts = opts || {};
    var which = opts.which || 'PR';           // 'PR' | 'QRS'
    var p = opts.params || E.params();
    var onScore = opts.onScore || function () {};
    var W = 480, H = 150, y0 = 90, zoom = 1.7;
    var caseObj = opts.caseObj, pointsStr, trueMs, startX, endX;
    if (caseObj && caseObj.median && caseObj.median.II && caseObj.features) {
      pointsStr = E.realPoints(caseObj.median.II, caseObj.median_fs || 100, y0, { zoom: zoom, baseline: 'start' });
      trueMs = which === 'PR' ? caseObj.features.pr_ms : caseObj.features.qrs_ms;
      startX = E.xOf(70) * zoom; endX = startX + E.xOf((trueMs || 160) * 0.55) * zoom; // off-target
    } else {
      var L = E.landmarks(p);
      pointsStr = E.leadPoints('II', p, W, y0, { zoom: zoom }).points;
      trueMs = which === 'PR' ? p.pr : p.qrs;
      startX = (which === 'PR' ? E.xOf(L.pOnset) * zoom : E.xOf(L.qrsOnset) * zoom) + 2.4 * E.SMALL * zoom;
      endX = (which === 'PR' ? E.xOf(L.qrsOnset) * zoom : E.xOf(L.j) * zoom) - 1.2 * E.SMALL * zoom;
    }
    var lo = which === 'PR' ? 120 : 60, hi = which === 'PR' ? 200 : 120; // normal band (QRS floor 60 so an implausibly short span isn't green-lit)
    var wrap = el('div', 'measure');
    wrap.innerHTML =
      '<div class="sec">Move the two handles to span the <b>' + which + '</b>' + (caseObj ? ' on this real beat (ECG ' + caseObj.ecg_id + ')' : '') + '. Drag or tap, use the marker buttons, or focus a handle and press the arrow keys. The bar turns green when the value is in the normal range.</div>' +
      '<svg class="ecg-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet">' + E.gridSVG(W, H) +
        '<polyline class="ecg-trace" points="' + pointsStr + '" />' +
        '<rect class="ih-span" id="ihSpan" y="8" height="' + (H - 16) + '" />' +
        '<line class="bc-mk" id="ihA" y1="6" y2="' + (H - 6) + '"/><line class="bc-mk" id="ihB" y1="6" y2="' + (H - 6) + '"/>' +
        '<circle class="mk-knob" id="ihAk" cy="14" r="9"/><circle class="mk-knob" id="ihBk" cy="14" r="9"/>' +
      '</svg>' +
      '<div class="bc-readout"><b id="ihVal"></b> &nbsp; <span class="sec" id="ihNorm"></span> &nbsp;|&nbsp; printed value on report: <b>' + trueMs + ' ms</b>' +
      '<button class="accent bc-check" id="ihCheck">Check</button></div><div id="ihFb"></div>';
    host.appendChild(wrap);
    var svg = wrap.querySelector('svg'), A = wrap.querySelector('#ihA'), B = wrap.querySelector('#ihB'), span = wrap.querySelector('#ihSpan');
    var Ak = wrap.querySelector('#ihAk'), Bk = wrap.querySelector('#ihBk');
    var ax = startX, bx = endX, attempts = 0;
    function upd() {
      A.setAttribute('x1', ax); A.setAttribute('x2', ax); B.setAttribute('x1', bx); B.setAttribute('x2', bx);
      Ak.setAttribute('cx', ax); Bk.setAttribute('cx', bx);
      Ak.setAttribute('aria-valuenow', Math.round(ax)); Bk.setAttribute('aria-valuenow', Math.round(bx));
      var l = Math.min(ax, bx); span.setAttribute('x', l); span.setAttribute('width', Math.abs(bx - ax));
      var ms = E.pxToMs(Math.abs(bx - ax) / zoom);
      var inNorm = ms >= (lo || -1) && ms <= hi;
      span.classList.toggle('normal', inNorm); span.classList.toggle('abn', !inNorm);
      wrap.querySelector('#ihVal').textContent = Math.round(ms / 5) * 5 + ' ms (' + (Math.abs(bx - ax) / zoom / E.SMALL).toFixed(1) + ' small boxes)';
      // text verdict, not colour alone
      var verdict = inNorm ? 'in range ✓' : (which === 'PR' ? (ms > hi ? 'long' : 'short') : 'wide');
      wrap.querySelector('#ihNorm').textContent = (which === 'PR' ? 'normal 120–200 ms' : 'normal < 120 ms') + ' · current: ' + verdict;
    }
    var setA = function (x) { ax = E.clamp(x, 4, W - 4); upd(); };
    var setB = function (x) { bx = E.clamp(x, 4, W - 4); upd(); };
    drag(svg, A, setA); drag(svg, Ak, setA);
    drag(svg, B, setB); drag(svg, Bk, setB);
    var kstep = E.SMALL * zoom / 4; // about 10 ms; Shift+arrow is about one big adjustment
    var syncA = accessibleHandle(svg, Ak, which + ' start handle', function () { return ax; }, setA, kstep);
    var syncB = accessibleHandle(svg, Bk, which + ' end handle', function () { return bx; }, setB, kstep);
    handleControls(wrap, svg, { get: function () { return ax; }, set: function (x) { setA(x); syncA(); } }, { get: function () { return bx; }, set: function (x) { setB(x); syncB(); } }, kstep);
    wrap.querySelector('#ihCheck').onclick = function () {
      attempts++;
      var ms = E.pxToMs(Math.abs(bx - ax) / zoom);
      var err = Math.abs(ms - trueMs);
      var fb = wrap.querySelector('#ihFb');
      if (err <= 30) { fb.innerHTML = '<div class="fb ok">Good — you measured <b>' + Math.round(ms) + ' ms</b>, the report says ' + trueMs + ' ms. ' + describe(which, trueMs, lo, hi) + '</div>'; onScore(true, ms, attempts); }
      else { fb.innerHTML = '<div class="fb warn">You spanned ' + Math.round(ms) + ' ms; the ' + which + ' is <b>' + trueMs + ' ms</b> (' + (trueMs / 40).toFixed(1) + ' small boxes). Line the handles up with the start and end and try again.</div>'; onScore(false, ms, attempts); }
    };
    upd();
    return wrap;
  }
  function describe(which, ms, lo, hi) {
    var inNorm = ms >= (lo || -1) && ms <= hi;
    if (which === 'PR') return inNorm ? 'That’s a normal PR.' : (ms > hi ? 'That’s a <b>long PR</b> — we just describe it; what a long PR <i>means</i> comes in a later module.' : 'Short PR — noted; meaning is for later.');
    return inNorm ? 'That’s a normal, narrow QRS.' : 'That’s a <b>wide QRS</b> — we just describe it for now; the causes are a later module.';
  }

  // ========================================================================
  // 5. BASELINE + ST — identify the TP reference, move ST away, then restore it.
  // ========================================================================
  function baselinePick(host, opts) {
    opts = opts || {}; var onScore = opts.onScore || function () {};
    var W = 460, H = 145, y0 = 78, p = E.params({ rate: 68 }), zoom = 1.65;
    var L = E.landmarks(p); var wrap = el('div', 'measure baseline-pick');
    var targets = [
      { id: 'tp', label: 'A · flat TP stretch between beats', x: E.xOf(Math.max(L.tEnd + 45, 760)) * zoom, correct: true },
      { id: 'st', label: 'B · ST segment after QRS', x: E.xOf(L.j + 45) * zoom, correct: false },
      { id: 'qrs', label: 'C · QRS complex', x: E.xOf(L.qrsOnset + 35) * zoom, correct: false }
    ];
    wrap.innerHTML = '<div class="sec">First identify the <b>baseline</b>: the flat TP stretch between the end of T and the next P.</div>' +
      '<svg class="ecg-svg baseline-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Lead II beat with three selectable regions">' + E.gridSVG(W, H) +
      '<polyline class="ecg-trace" points="' + E.leadPoints('II', p, W, y0, { zoom: zoom }).points + '" /></svg>' +
      '<div class="baseline-options" aria-label="Baseline target choices"></div><div id="baseFb" aria-live="polite"></div>';
    host.appendChild(wrap); var svg = wrap.querySelector('svg'), row = wrap.querySelector('.baseline-options'), attempts = 0, done = false;
    function choose(t) {
      if (done) return; attempts++;
      if (t.correct) { done = true; row.querySelectorAll('button').forEach(function (b) { b.disabled = true; }); wrap.querySelector('#baseFb').innerHTML = '<div class="fb ok">Correct — the TP stretch is the baseline used to judge ST level.</div>'; onScore(true, { attempts: attempts, target: 'tp_baseline' }); }
      else wrap.querySelector('#baseFb').innerHTML = '<div class="fb warn">That is the ' + (t.id === 'st' ? 'ST segment' : 'QRS complex') + '. Find the flat stretch after T and before the next P.</div>';
    }
    targets.forEach(function (t) { var b = stepButton(t.label, function () { choose(t); }); b.setAttribute('data-target', t.id); row.appendChild(b); });
    svg.setAttribute('tabindex', '0');
    svg.addEventListener('click', function (e) { var r = svg.getBoundingClientRect(); var x = (e.clientX - r.left) / r.width * W; var nearest = targets.slice().sort(function (a, b) { return Math.abs(a.x - x) - Math.abs(b.x - x); })[0]; choose(nearest); });
    return wrap;
  }

  function stDrag(host, opts) {
    opts = opts || {};
    var onSettle = opts.onSettle || function () {};
    var W = 460, H = 150, y0 = 80, zoom = 1.9;
    var wrap = el('div', 'measure');
    wrap.innerHTML =
      '<div class="sec">Move the <b>ST segment</b> up or down by dragging it, using the level slider, or choosing the buttons. It’s judged against the baseline — near-baseline looks normal; an obvious lift or drop is noted (for a later module).</div>' +
      '<svg class="ecg-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet"><g id="stsvg"></g>' +
        '<line class="st-baseline" x1="0" x2="' + W + '" y1="' + y0 + '" y2="' + y0 + '"/>' +
        '<circle class="st-handle" id="sth" r="8"/></svg>' +
      '<label class="st-range-label">Keyboard/tap alternative: ST level <input id="stRange" type="range" min="-0.40" max="0.40" value="0" step="0.05" aria-label="ST level in millivolts"></label>' +
      '<div class="handle-controls"><button type="button" id="stLower">Lower ST</button><button type="button" id="stRaise">Raise ST</button><button type="button" id="stBase">Set at baseline</button></div>' +
      '<div id="stFb" class="fb" aria-live="polite">ST level: <b id="stLvl">0.00 mV</b> — at baseline (normal). Move it off baseline once, then restore it.</div>';
    host.appendChild(wrap);
    var g = wrap.querySelector('#stsvg'), h = wrap.querySelector('#sth'), svg = wrap.querySelector('svg');
    var st = 0, movedOff = false, attempts = 0;
    function settle() { attempts++; onSettle(Math.abs(st) < 0.05 && movedOff, st, movedOff, attempts); }
    function render() {
      var p = E.params({ st: st });
      var lp = E.leadPoints('II', p, W, y0, { zoom: zoom });
      g.innerHTML = E.gridSVG(W, H) + '<polyline class="ecg-trace" points="' + lp.points + '" />';
      var L = E.landmarks(p);
      var hx = E.xOf((L.j + L.tCenter - L.tWidth) / 2) * zoom;
      var hy = y0 - E.mvToPx(st) * zoom;
      h.setAttribute('cx', hx); h.setAttribute('cy', hy);
      wrap.querySelector('#stLvl').textContent = st.toFixed(2) + ' mV';
      var fb = wrap.querySelector('#stFb');
      wrap.querySelector('#stRange').value = st.toFixed(2);
      if (Math.abs(st) >= 0.05) movedOff = true;
      if (Math.abs(st) < 0.05) { fb.className = movedOff ? 'fb ok' : 'fb'; fb.innerHTML = 'ST level: <b>' + st.toFixed(2) + ' mV</b> — flat, at the baseline. ' + (movedOff ? '<b>Restored after comparison.</b>' : 'Move it off baseline once, then restore it.'); }
      else { fb.className = 'fb warn'; fb.innerHTML = 'ST level: <b>' + st.toFixed(2) + ' mV</b> — ' + (st > 0 ? 'elevated' : 'depressed') + ' off the baseline. A small amount can be normal; <i>how much, and what it means, is a later module.</i> Settle it back near the baseline.'; }
    }
    h.style.cursor = 'ns-resize';
    h.addEventListener('pointerdown', function (e) {
      e.preventDefault(); h.setPointerCapture(e.pointerId);
      function mv(ev) { var r = svg.getBoundingClientRect(); var yy = (ev.clientY - r.top) / r.height * H; st = E.clamp((y0 - yy) / (E.mvToPx(1) * zoom), -0.4, 0.4); render(); }
      function up() { svg.removeEventListener('pointermove', mv); svg.removeEventListener('pointerup', up); settle(); }
      svg.addEventListener('pointermove', mv); svg.addEventListener('pointerup', up);
    });
    var range = wrap.querySelector('#stRange');
    range.oninput = function () { st = +this.value; render(); };
    range.onchange = settle;
    wrap.querySelector('#stLower').onclick = function () { st = E.clamp(st - 0.05, -0.4, 0.4); render(); };
    wrap.querySelector('#stRaise').onclick = function () { st = E.clamp(st + 0.05, -0.4, 0.4); render(); };
    wrap.querySelector('#stBase').onclick = function () { st = 0; render(); settle(); };
    render();
    return wrap;
  }

  // ========================================================================
  // 6. R-WAVE SCRUB — S8: V1->V6, R grows & S shrinks, transition where R>S.
  // ========================================================================
  function rwaveScrub(host, opts) {
    opts = opts || {};
    var onDone = opts.onDone || function () {};
    var leads = ['V1', 'V2', 'V3', 'V4', 'V5', 'V6'];
    var p = E.params();
    var W = 300, H = 150, y0 = 80;
    var wrap = el('div', 'rwave');
    wrap.innerHTML =
      '<div class="rwave-head"><b id="rwLead">V1</b> <span class="sec" id="rwDesc"></span></div>' +
      '<svg class="ecg-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet"><g id="rwsvg"></g></svg>' +
      '<div class="rwave-strip" id="rwStrip"></div>' +
      '<label class="rwave-range">Precordial lead <input type="range" id="rwScrub" min="0" max="5" value="0" step="1" aria-label="Precordial lead from V1 through V6"></label>' +
      '<div class="handle-controls"><button type="button" id="rwPrev">Previous lead</button><button type="button" id="rwNext">Next lead</button></div>' +
      '<div id="rwFb"></div>';
    host.appendChild(wrap);
    var g = wrap.querySelector('#rwsvg');
    var strip = wrap.querySelector('#rwStrip');
    strip.innerHTML = leads.map(function (l, i) { return '<button type="button" class="rw-dot" data-i="' + i + '" aria-label="Show lead ' + l + '">' + l + '</button>'; }).join('');
    var seenTransition = false;
    function show(i) {
      var lead = leads[i];
      var amps = E.PRECORDIAL[lead];
      g.innerHTML = E.gridSVG(W, H) + '<polyline class="ecg-trace" points="' + E.leadPoints(lead, p, W, y0, { zoom: 1.5 }).points + '" />';
      wrap.querySelector('#rwLead').textContent = lead;
      var ratio = amps.r / amps.s;
      var desc = 'R ≈ ' + amps.r.toFixed(1) + ' mV, S ≈ ' + amps.s.toFixed(1) + ' mV';
      wrap.querySelector('#rwDesc').textContent = desc + (ratio >= 1 ? '  — R now taller than S' : '');
      Array.prototype.forEach.call(strip.children, function (c, ci) { c.classList.toggle('active', ci === i); c.classList.toggle('past', ci < i); });
      var fb = wrap.querySelector('#rwFb');
      if (ratio >= 1 && !seenTransition) {
        seenTransition = true;
        fb.innerHTML = '<div class="fb ok"><b>Transition!</b> Here at ' + lead + ' the R finally becomes taller than the S. The transition is often around V3–V4. Watch the R keep growing and the S keep shrinking through V6.</div>';
        onDone(lead);
      } else if (i === 0) {
        fb.innerHTML = '<div class="fb">V1 starts as a tiny r and a deep S ("rS"). Scrub right and watch the R <b>grow</b> while the S <b>shrinks</b>.</div>';
      }
    }
    var rwRange = wrap.querySelector('#rwScrub');
    rwRange.oninput = function () { show(parseInt(this.value, 10)); };
    wrap.querySelector('#rwPrev').onclick = function () { rwRange.value = Math.max(0, +rwRange.value - 1); show(+rwRange.value); };
    wrap.querySelector('#rwNext').onclick = function () { rwRange.value = Math.min(5, +rwRange.value + 1); show(+rwRange.value); };
    Array.prototype.forEach.call(strip.children, function (c) { c.onclick = function () { var i = +c.getAttribute('data-i'); wrap.querySelector('#rwScrub').value = i; show(i); }; });
    show(0);
    return wrap;
  }

  // ========================================================================
  // 7. HEXAXIAL AXIS — S9 keystone. Drag the QRS vector; limb leads flip live;
  //    green = normal (rule delivers ~0..+90), amber = borderline (-30..0),
  //    red = deviated. Reconciled with the storyboard v7 fix.
  // ========================================================================
  function hexaxial(host, opts) {
    opts = opts || {};
    var onChange = opts.onChange || function () {};
    var p = opts.params || E.params({ axis: 60 });
    var R = 96, cx = 120, cy = 120, S = 240;
    var wrap = el('div', 'axis-lab');
    wrap.innerHTML =
      '<div class="axis-grid">' +
        '<div class="axis-circle"><svg viewBox="0 0 ' + S + ' ' + S + '" role="img" aria-label="hexaxial axis circle">' +
          sectorPath(cx, cy, R, 0, 90, 'sec-normal') +
          sectorPath(cx, cy, R, -30, 0, 'sec-border') +
          axesSVG(cx, cy, R) +
          '<circle class="axis-ring" cx="' + cx + '" cy="' + cy + '" r="' + R + '"/>' +
          '<line class="axis-vec" id="axVec" x1="' + cx + '" y1="' + cy + '" x2="' + cx + '" y2="' + cy + '"/>' +
          '<circle class="axis-hit" id="axHit" r="22" opacity="0"/>' +
          '<circle class="axis-head" id="axHead" r="11"/>' +
        '</svg></div>' +
        '<div class="axis-leads" id="axLeads"></div>' +
      '</div>' +
      '<label class="axis-range-label">Keyboard/touch alternative: QRS axis <input id="axRange" type="range" min="-180" max="180" value="60" step="5" aria-label="QRS axis in degrees"></label>' +
      '<div class="handle-controls"><button type="button" id="axNormal">Go to normal axis</button><button type="button" id="axLeft">Go to left axis</button><button type="button" id="axRight">Go to right axis</button></div>' +
      '<div id="axReadout" class="fb"></div>';
    host.appendChild(wrap);
    var svg = wrap.querySelector('svg'), vec = wrap.querySelector('#axVec'), head = wrap.querySelector('#axHead'), hit = wrap.querySelector('#axHit');
    var leadsBox = wrap.querySelector('#axLeads'), axisRange = wrap.querySelector('#axRange');

    function zone(deg) { if (deg >= 0 && deg <= 90) return 'normal'; if (deg < 0 && deg >= -30) return 'border'; return 'dev'; }
    function setAxis(deg) {
      p.axis = deg;
      var x = cx + R * Math.cos(E.rad(deg)), y = cy + R * Math.sin(E.rad(deg));
      vec.setAttribute('x2', x); vec.setAttribute('y2', y);
      head.setAttribute('cx', x); head.setAttribute('cy', y);
      hit.setAttribute('cx', x); hit.setAttribute('cy', y);
      axisRange.value = deg;
      head.setAttribute('aria-valuenow', deg); head.setAttribute('aria-valuetext', deg + ' degrees');
      var z = zone(deg);
      vec.setAttribute('class', 'axis-vec ' + z); head.setAttribute('class', 'axis-head ' + z);
      drawLeads();
      readout(deg, z);
      onChange(p);
    }
    function drawLeads() {
      // the six limb leads, re-projected live
      var html = '';
      ['I', 'aVR', 'aVL', 'II', 'aVF', 'III'].forEach(function (l) {
        var amps = E.leadAmps(l, p);
        var net = amps.r - amps.s;
        var dir = net > 0.05 ? '↑' : (net < -0.05 ? '↓' : '↔');
        var cls = net > 0.05 ? 'up' : (net < -0.05 ? 'down' : 'iso');
        html += '<div class="axlead"><span class="axlead-name">' + l + '</span>' +
          '<svg class="ecg-svg" viewBox="0 0 120 60" preserveAspectRatio="xMidYMid meet">' + E.gridSVG(120, 60) +
          '<polyline class="ecg-trace" points="' + E.leadPoints(l, p, 120, 34, { zoom: 1.1 }).points + '" /></svg>' +
          '<span class="axlead-dir ' + cls + '">' + dir + '</span></div>';
      });
      leadsBox.innerHTML = html;
    }
    function readout(deg, z) {
      var I = E.leadAmps('I', p), F = E.leadAmps('aVF', p);
      var iUp = (I.r - I.s) > 0, fUp = (F.r - F.s) > 0;
      var ro = wrap.querySelector('#axReadout');
      var msg = 'Lead I is ' + (iUp ? '<b>up</b>' : '<b>down</b>') + ', aVF is ' + (fUp ? '<b>up</b>' : '<b>down</b>') + '. ';
      if (z === 'normal') { ro.className = 'fb ok'; ro.innerHTML = msg + 'Both up → <b>normal axis</b>.'; }
      else if (z === 'border') { ro.className = 'fb warn'; ro.innerHTML = msg + 'I up but aVF down → <b>borderline left</b>. The quick rule can’t pin this; we confirm with lead II in the axis module (the normal range extends a little past 0°, to about −30°).'; }
      else {
        ro.className = 'fb warn';
        var dir = (!iUp && fUp) ? 'a <b>right axis</b>' : (iUp && !fUp) ? 'a <b>left axis</b>' : (!iUp && !fUp) ? 'an <b>extreme axis</b>' : '<b>deviated</b>';
        ro.innerHTML = msg + 'This is ' + dir + ' — we just name it for now; what causes it is a later module.';
      }
    }
    // drag: capture the pointer on the SVG (robust on touch + mouse); a large
    // invisible halo (axHit) makes the target easy to grab with a thumb.
    function degFrom(ev) { var r = svg.getBoundingClientRect(); var mx = (ev.clientX - r.left) / r.width * S - cx; var my = (ev.clientY - r.top) / r.height * S - cy; return Math.round(Math.atan2(my, mx) * 180 / Math.PI); }
    function startDrag(e) {
      e.preventDefault(); svg.setPointerCapture(e.pointerId);
      setAxis(degFrom(e));
      function mv(ev) { setAxis(degFrom(ev)); }
      function up() { try { svg.releasePointerCapture(e.pointerId); } catch (x) {} svg.removeEventListener('pointermove', mv); svg.removeEventListener('pointerup', up); }
      svg.addEventListener('pointermove', mv); svg.addEventListener('pointerup', up);
    }
    head.style.cursor = 'grab'; hit.style.cursor = 'grab';
    head.setAttribute('tabindex', '0'); head.setAttribute('role', 'slider'); head.setAttribute('aria-label', 'QRS axis vector'); head.setAttribute('aria-valuemin', '-180'); head.setAttribute('aria-valuemax', '180');
    head.addEventListener('keydown', function (e) {
      var step = e.shiftKey ? 30 : 5, next = p.axis;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') next -= step;
      else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') next += step;
      else if (e.key === 'Home') next = -180;
      else if (e.key === 'End') next = 180;
      else return;
      e.preventDefault(); if (next > 180) next -= 360; if (next < -180) next += 360; setAxis(next);
    });
    head.addEventListener('pointerdown', startDrag); hit.addEventListener('pointerdown', startDrag);
    axisRange.oninput = function () { setAxis(+this.value); };
    wrap.querySelector('#axNormal').onclick = function () { setAxis(60); };
    wrap.querySelector('#axLeft').onclick = function () { setAxis(-60); };
    wrap.querySelector('#axRight').onclick = function () { setAxis(120); };
    setAxis(p.axis);
    return { setAxis: setAxis, params: p };
  }
  function axesSVG(cx, cy, R) {
    var s = '';
    var labels = { I: 0, II: 60, III: 120, aVF: 90, aVR: -150, aVL: -30 };
    for (var l in labels) {
      var d = labels[l], x = cx + R * Math.cos(E.rad(d)), y = cy + R * Math.sin(E.rad(d));
      var lx = cx + (R + 14) * Math.cos(E.rad(d)), ly = cy + (R + 14) * Math.sin(E.rad(d));
      s += '<line class="axis-axisline" x1="' + (cx - (x - cx)) + '" y1="' + (cy - (y - cy)) + '" x2="' + x + '" y2="' + y + '"/>';
      s += '<text class="axis-axislabel" x="' + lx + '" y="' + ly + '">' + l + '</text>';
    }
    return s;
  }
  function sectorPath(cx, cy, R, a0, a1, cls) {
    var x0 = cx + R * Math.cos(E.rad(a0)), y0 = cy + R * Math.sin(E.rad(a0));
    var x1 = cx + R * Math.cos(E.rad(a1)), y1 = cy + R * Math.sin(E.rad(a1));
    var large = (a1 - a0) > 180 ? 1 : 0;
    return '<path class="' + cls + '" d="M' + cx + ',' + cy + ' L' + x0 + ',' + y0 + ' A' + R + ',' + R + ' 0 ' + large + ',1 ' + x1 + ',' + y1 + ' Z"/>';
  }

  // R-wave scrub on a REAL case's precordial median beats (V1->V6).
  function rwaveScrubReal(host, c, opts) {
    opts = opts || {}; var onDone = opts.onDone || function () {};
    var leads = ['V1', 'V2', 'V3', 'V4', 'V5', 'V6'], fs = c.median_fs || 100;
    var W = 300, H = 160, y0 = 95;
    function rs(beat) { var b0 = beat.slice(0, 5).reduce(function (a, x) { return a + x; }, 0) / Math.min(5, beat.length); return { R: Math.max.apply(null, beat) - b0, S: b0 - Math.min.apply(null, beat) }; }
    var wrap = el('div', 'rwave');
    wrap.innerHTML =
      '<div class="rwave-head"><b id="rwLead">V1</b> <span class="sec" id="rwDesc"></span></div>' +
      '<svg class="ecg-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet"><g id="rwsvg"></g></svg>' +
      '<div class="rwave-strip" id="rwStrip"></div>' +
      '<label class="rwave-range">Precordial lead <input type="range" id="rwScrub" min="0" max="5" value="0" step="1" aria-label="Precordial lead from V1 through V6"></label>' +
      '<div class="handle-controls"><button type="button" id="rwPrev">Previous lead</button><button type="button" id="rwNext">Next lead</button></div><div id="rwFb"></div>';
    host.appendChild(wrap);
    var g = wrap.querySelector('#rwsvg'), strip = wrap.querySelector('#rwStrip');
    strip.innerHTML = leads.map(function (l, i) { return '<button type="button" class="rw-dot" data-i="' + i + '" aria-label="Show lead ' + l + '">' + l + '</button>'; }).join('');
    var seen = false;
    function show(i) {
      var lead = leads[i], beat = c.median[lead] || [], a = rs(beat);
      g.innerHTML = E.gridSVG(W, H) + '<polyline class="ecg-trace" points="' + E.realPoints(beat, fs, y0, { zoom: 1.4, gain: 1, baseline: 'start' }) + '" />';
      wrap.querySelector('#rwLead').textContent = lead;
      var ratio = a.S > 0.02 ? a.R / a.S : 9;
      wrap.querySelector('#rwDesc').textContent = 'R ≈ ' + a.R.toFixed(2) + ' mV, S ≈ ' + a.S.toFixed(2) + ' mV' + (ratio >= 1 ? ' — R now taller than S' : '');
      Array.prototype.forEach.call(strip.children, function (ch, ci) { ch.classList.toggle('active', ci === i); ch.classList.toggle('past', ci < i); });
      var fb = wrap.querySelector('#rwFb');
      if (ratio >= 1 && !seen) { seen = true; fb.innerHTML = '<div class="fb ok"><b>Transition!</b> At ' + lead + ' the R finally becomes taller than the S — the transition is often around V3–V4. (Real case ' + c.ecg_id + '.)</div>'; onDone(lead); }
      else if (i === 0) fb.innerHTML = '<div class="fb">V1 starts as a small r with a deep S. Scrub right and watch the R <b>grow</b> and the S <b>shrink</b>.</div>';
    }
    var rwRange = wrap.querySelector('#rwScrub');
    rwRange.oninput = function () { show(parseInt(this.value, 10)); };
    wrap.querySelector('#rwPrev').onclick = function () { rwRange.value = Math.max(0, +rwRange.value - 1); show(+rwRange.value); };
    wrap.querySelector('#rwNext').onclick = function () { rwRange.value = Math.min(5, +rwRange.value + 1); show(+rwRange.value); };
    Array.prototype.forEach.call(strip.children, function (ch) { ch.onclick = function () { var i = +ch.getAttribute('data-i'); wrap.querySelector('#rwScrub').value = i; show(i); }; });
    show(0);
    return wrap;
  }

  global.Engines = {
    wavefront: wavefront, boxCount: boxCount, rateLab: rateLab,
    intervalHandle: intervalHandle, baselinePick: baselinePick, stDrag: stDrag,
    rwaveScrub: rwaveScrub, rwaveScrubReal: rwaveScrubReal, hexaxial: hexaxial
  };
})(window);
