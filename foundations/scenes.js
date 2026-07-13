/* scenes.js — the 13 scenes of the Foundations module (storyboard v7).
 * Each scene: { id, part, title, sub, mount(root, ctx) }.
 * ctx = { complete(), setMastery(label), scene, goNext() }.
 * Scenes drive ecg.js + engines.js + Tutor/NVCard and call ctx.complete() when
 * the mastery checkpoint is satisfied (which unlocks "Next").
 */
(function (global) {
  'use strict';
  var E = global.ECG, Eng = global.Engines, T = global.Tutor, NV = global.NVCard;
  function el(tag, cls, html) { var d = document.createElement(tag); if (cls) d.className = cls; if (html != null) d.innerHTML = html; return d; }
  function add(root, cls, html) { var d = el('div', cls, html); root.appendChild(d); return d; }
  function realCase(category, index) {
    var c = global.pickCase && global.pickCase(category, index || 0);
    if (!c) throw new Error('Verified PTB Foundations case unavailable for ' + category + '[' + (index || 0) + ']');
    return c;
  }
  function modelDisclosure(root, copy) {
    return add(root, 'model-disclosure', '<b>Interactive mechanism schematic — not a patient ECG.</b> ' + copy + ' Scored patient-trace work on this page uses the identified real PTB ECGs.');
  }
  // A quiet "you've got this section" cue — not a gamified score chip.
  function masteryBar(root, label) {
    var m = add(root, 'lesson-done', '<span class="ld-tick">✓</span><span>Nice — you’ve got <b>' + label + '</b>. Continue when you’re ready.</span>');
    m.hidden = true; return m;
  }
  // A one-tap concept check: confirms understanding (not just interaction). onPass fires once.
  function miniCheck(host, q, opts, onPass) {
    var ex = host.querySelectorAll('.mini-check .inline-q');   // don't re-mount the SAME check (but allow different ones)
    for (var gi = 0; gi < ex.length; gi++) if (ex[gi].textContent === q) return;
    var box = add(host, 'inline-answer mini-check', '<div class="inline-q">' + q + '</div>');
    var row = el('div', 'choices'); box.appendChild(row);
    opts.forEach(function (o) {
      var b = el('button', '', o.label);
      b.onclick = function () {
        if (o.correct) {
          row.querySelectorAll('button').forEach(function (x) { x.disabled = true; });
          b.classList.add('right'); box.insertAdjacentHTML('beforeend', '<div class="fb ok">' + (o.fb || '✓ Right.') + '</div>');
          onPass && onPass();
        } else { b.classList.add('wrong'); box.insertAdjacentHTML('beforeend', '<div class="fb warn">' + (o.fb || 'Not quite — try again.') + '</div>'); }
      };
      row.appendChild(b);
    });
    return box;
  }

  var SCENES = [];

  // ---- S0 — gentle start + the map ----------------------------------------
  SCENES.push({
    id: 'S0', part: 1, title: 'A gentle start', sub: 'what an ECG even is',
    mount: function (root, ctx) {
      T.clear(); T.setScope('intro');
      var introCase = realCase('normal', 0);
      add(root, 'hero', '<div class="hero-beat"><div class="real-case-label">Real PTB-XL ECG ' + introCase.ecg_id + ' · lead II</div>' + E.renderRealStrip(introCase.lead_ii, 50, { w: 620, h: 150 }) + '</div>' +
        '<h2 class="hero-h">An ECG is the heart’s electrical signal, drawn over time.</h2>' +
        '<p class="hero-p">In Foundations you’ll learn the <b>beginner sweep</b>, start to finish: find the main waves, measure the basics, and <b>describe</b> what the tracing supports — one piece at a time. No prior knowledge needed. ' +
        'Clinical meaning, diagnoses, and urgency come in later modules.</p>');
      var map = add(root, 'map');
      map.innerHTML =
        '<div class="map-title">Your path — 4 resumable parts, about 25 min for the core path · longer with tutor tangents or retries · skipped scenes stay marked for review</div>' +
        '<div class="map-parts">' +
        '<div class="map-part"><b>1 · What am I looking at?</b><span>the waveform &amp; the paper</span></div>' +
        '<div class="map-part"><b>2 · Measure one beat</b><span>rate, rhythm, intervals</span></div>' +
        '<div class="map-part"><b>3 · One lead → twelve</b><span>12-lead &amp; axis</span></div>' +
        '<div class="map-part"><b>4 · The systematic read</b><span>watch → guided → you</span></div>' +
        '</div>';
      T.say('Hi — I’m your tutor. I’ll guide each step, and you can <b>ask me about any Foundations concept</b> any time in the box below — I’ll help you <i>find, measure, and name</i> things, and save clinical meaning for later modules. Take a look at the path above, then hit <b>Next</b> to start.');
      ctx.complete();
    }
  });

  // ---- S1 — keystone: one beat = one electrical wave -----------------------
  SCENES.push({
    id: 'S1', part: 1, title: 'One beat, one wave', sub: 'the keystone',
    mount: function (root, ctx) {
      T.clear(); T.setScope('waves: P, QRS, T');
      add(root, 'lead-note', 'Watch the electrical wave sweep the heart and <b>draw the tracing in real time</b>. Then you’ll name the three parts.');
      modelDisclosure(root, 'This controllable drawing separates P, QRS, and T so their sequence can be learned before marking them on real tracings.');
      var host = add(root, 'wf-host');
      var m = masteryBar(root, 'the waves');
      Eng.wavefront(host, {
        onDone: function () { /* first pass complete */ },
        onEvidence: function (ev) { ctx.evidence({ interactionId: 's1-wave-label-placement', concept: 'waveform_components', subskills: ['localize'], correct: ev.correct, score: ev.score, attempts: ev.attempts, caseProvenance: 'authored_simulation', caseEligible: false }); }
      });
      T.say('Press <b>▶ Watch one beat</b>. I’ll narrate in plain words first — then we’ll put names to the shapes.');
      // completion: once labels placed (we detect via the dragbank success) OR after watching.
      // Simpler: enable Next after the labels step is opened; encourage placing all three.
      var poll = setInterval(function () {
        if (root.querySelector('.fb.ok')) { clearInterval(poll); NV.reveal([]); m.hidden = false; ctx.complete(); }
        else if (root.querySelector('#wflabels') && !root.querySelector('#wflabels').disabled && !root._announced) {
          root._announced = true;
          T.say('Now choose <b>Show P / QRS / T</b>. Select each name, then tap its wave or use the matching waveform-target button. <b>P</b> = atrial activation, <b>QRS</b> = ventricular activation, <b>T</b> = ventricular reset.');
        }
      }, 600);
      ctx._cleanup = function () { clearInterval(poll); };
    }
  });

  // ---- S2 — the grid is your ruler ----------------------------------------
  SCENES.push({
    id: 'S2', part: 1, title: 'The grid is your ruler', sub: 'boxes → time & voltage',
    mount: function (root, ctx) {
      T.clear(); T.setScope('grid, boxes, calibration');
      add(root, 'lead-note', 'Now that you can spot P, QRS and T, let’s measure the distance between them. The pink grid is calibrated: <b>across</b> = time, <b>up/down</b> = voltage. ' +
        'A <b>small box is 40 ms wide and 0.1 mV tall</b>; <b>5 small = 1 big box = 200 ms</b>. The little step on the left is the <b>calibration pulse</b> — it tells you the tracing is drawn at standard size, so glance at it every time.');
      var m = masteryBar(root, 'reading the grid');
      var host = add(root, 'measure-host');
      T.say('Let’s prove the ruler works. Move the two markers exactly <b>one big box apart</b> — that’s 5 small boxes — then <b>Check my count</b>. You can drag or tap, use the marker buttons, or focus a handle and press the arrow keys. Each small box is 40 ms, so you’re aiming for 200 ms.');
      Eng.boxCount(host, {
        trueMs: 200, label: 'one big box', lead: null,
        onScore: function (ok, ms, attempts) {
          ctx.evidence({ interactionId: 's2-box-ruler', concept: 'ecg_grid_calibration', subskills: ['measure'], correct: ok, score: ok ? 1 : Math.max(0, 1 - Math.abs(ms - 200) / 200), attempts: attempts, caseProvenance: 'authored_simulation', caseEligible: false });
          if (ok) {
            NV.reveal(['boxes']);
            T.say('That’s the measurement trick: once you find a waveform’s start and end, the grid turns distance into time.');
            miniCheck(root, 'Quick check: one big box is 5 small boxes — how many ms is that?', [
              { label: '200 ms', correct: true, fb: '✓ Right — 5 × 40 ms = 200 ms.' }, { label: '40 ms' }, { label: '1 second' }
            ], function () { m.hidden = false; ctx.complete(); });
          } else { T.say('Almost — 5 small boxes make one big box (200 ms). Nudge the markers until the readout says ~200 ms.'); } }
      });
      add(root, 'aside', '<b>Calipers?</b> There’s a precision tool for borderline values, but most of the time you estimate from the boxes and compare with the printed measurements. Use calipers when a value is close to a cutoff.');
    }
  });

  // ---- S3 — is it readable? (scored rapid-classify) -----------------------
  SCENES.push({
    id: 'S3', part: 1, title: 'Is it readable?', sub: 'the first question',
    mount: function (root, ctx) {
      T.clear(); T.setScope('signal quality');
      add(root, 'lead-note', 'Before measuring, ask: <b>readable for what?</b> A strip can be clear enough for rate but too noisy for the P waves or ST/T — a good reader doesn’t force a measurement the tracing can’t support. Tag each strip.');
      var m = masteryBar(root, 'quality check');
      var grid = add(root, 'classify-grid');
      // Real clean strips (acceptable-quality normals) vs real noisy strips (poor-quality records).
      var cleanCs = [realCase('normal', 0), realCase('brady', 0)];
      var noisyCs = (global.CASES_BY && global.CASES_BY.noisy) || [];
      var cases = [];
      if (cleanCs[0] && cleanCs[0].lead_ii) cases.push({ strip: cleanCs[0].lead_ii, clean: true });
      if (noisyCs[0]) cases.push({ strip: noisyCs[0].lead_ii, clean: false });
      if (cleanCs[1] && cleanCs[1].lead_ii) cases.push({ strip: cleanCs[1].lead_ii, clean: true });
      if (noisyCs[1]) cases.push({ strip: noisyCs[1].lead_ii, clean: false });
      if (cases.length !== 4) throw new Error('Verified PTB quality examples are incomplete');
      var rights = 0;   // must get them all right (wrong cards can be re-tagged) — the scene's own lesson
      cases.forEach(function (c, i) {
        var card = el('div', 'classify-card');
        card.innerHTML = E.renderRealStrip(c.strip, 50, { w: 300, h: 96, leadLabel: false }) +
          '<div class="row classify-btns"><button data-v="clean" aria-label="Strip ' + (i + 1) + ': readable">Readable</button><button data-v="noise" aria-label="Strip ' + (i + 1) + ': too noisy">Too noisy</button></div>';
        grid.appendChild(card);
        card.querySelectorAll('button').forEach(function (b) {
          b.onclick = function () {
            if (card._right) return;                                  // a correct card is locked; a wrong one can be re-tagged
            var ok = (b.getAttribute('data-v') === 'clean') === c.clean;
            card.classList.remove('right', 'wrong'); card.classList.add(ok ? 'right' : 'wrong');
            var old = card.querySelector('.tag'); if (old) old.remove();
            card.querySelector('.classify-btns').insertAdjacentHTML('beforeend', '<span class="tag ' + (ok ? 'ok' : 'bad') + '">' + (ok ? '✓' : '✗ ' + (c.clean ? 'this one’s clean — re-tag it' : 'too noisy — re-tag it')) + '</span>');
            if (ok) { card._right = true; rights++; card.querySelectorAll('button').forEach(function (x) { x.disabled = true; }); }
            if (rights === cases.length && !root._s3done) {
              root._s3done = true; m.hidden = false; ctx.complete();
              T.say('All ' + cases.length + ' right. When noise hides the waves or the baseline, don’t force a measurement — you may still estimate rate if the QRS complexes are clear, but avoid PR / ST-T calls.');
            }
          };
        });
      });
      T.say('Four strips. Two are clean enough for detailed measuring; two are too noisy for the P waves / ST-T. Tag each one.');
    }
  });

  // ---- S4 — regular? then rate --------------------------------------------
  SCENES.push({
    id: 'S4', part: 2, title: 'Regular? then rate', sub: 'count boxes, then compare',
    mount: function (root, ctx) {
      T.clear(); T.setScope('regularity, rate, 300-rule');
      add(root, 'lead-note', '<b>First glance: are the R’s evenly spaced?</b> That decides the method. If <b>regular</b> → <b>300 ÷ big boxes</b> between two R’s <span class="sec">(why 300? one minute is 300 big boxes wide, so 300 ÷ boxes-per-beat = beats per minute)</span>. If <b>irregular</b> → count beats in 6 seconds × 10. (The 300-rule only works when it’s regular.)');
      var m = masteryBar(root, 'rate');
      // Gate on method-selection (both regular AND irregular) before crediting the rate read —
      // the habit "don't use the 300-rule until you've checked regularity" is the point of the scene.
      var methodOK = false, irregOK = false, rateOK = false;
      function maybeDone() { if (methodOK && irregOK && rateOK) { NV.reveal(['rate']); m.hidden = false; ctx.complete(); } }
      miniCheck(root, 'First, the method. The R waves here are evenly spaced (regular) — which method?', [
        { label: 'Regular → 300 ÷ big boxes', correct: true, fb: '✓ Right — regular, so 300 ÷ the big boxes between two R’s.' },
        { label: 'Irregular → 6-second count', fb: 'That’s for an irregular rhythm; when it’s regular, 300 ÷ big boxes is quicker.' }
      ], function () { methodOK = true; maybeDone(); });
      miniCheck(root, 'And if the R waves were unevenly spaced (irregular)?', [
        { label: 'Count beats in 6 seconds × 10', correct: true, fb: '✓ Right — the 300-rule only works when the rhythm is regular.' },
        { label: 'Still use 300 ÷ big boxes', fb: 'The 300-rule assumes even spacing — for an irregular rhythm, count beats in 6 s × 10.' }
      ], function () { irregOK = true; maybeDone(); });
      var host = add(root, 'measure-host');
      modelDisclosure(root, 'The spacing slider is a ruler demonstration; the rate answer beneath it is graded on a real PTB rhythm strip.');
      T.say('Drag the spacing slider and feel it: closer R’s = faster. Then estimate the rate yourself and compare with the printed value on the quiz strip. Within ~10–12 bpm is a good beginner estimate.');
      Eng.rateLab(host, { quizCase: realCase('tachy', 0), onScore: function (ok) { if (ok) { rateOK = true; maybeDone(); } } });
    }
  });

  // ---- S5 — sinus? --------------------------------------------------------
  SCENES.push({
    id: 'S5', part: 2, title: 'Sinus pattern?', sub: 'follow the P waves',
    mount: function (root, ctx) {
      T.clear(); T.setScope('sinus rhythm definition');
      add(root, 'lead-note', '<b>Sinus pattern</b> means the beat <i>appears</i> to start in the SA node — we infer it from the P waves. Checklist (all on lead II): a <b>P before every QRS</b>, a QRS after every P, the <b>P upright in II</b>, the <b>same P shape every beat</b>, a <b>constant PR</b>. Regularity helps, but sinus is mainly this P–QRS checklist. ' +
        '<span class="hl">Rate is NOT part of it</span> — a slow sinus and a fast sinus are both sinus.');
      var m = masteryBar(root, 'rhythm / sinus');
      var grid = add(root, 'classify-grid');
      var cases = [
        { caseObj: realCase('normal', 0), sinus: true, why: 'A consistent upright P precedes each QRS with a steady relationship — sinus pattern.' },
        { caseObj: realCase('brady', 0), sinus: true, why: 'Slow, yes — but the repeated P–QRS relationship remains sinus. Slow ≠ not-sinus.' },
        { caseObj: realCase('non_sinus', 0), sinus: false, why: 'There is no consistent, repeatable P-before-every-QRS pattern. That fails the sinus checklist; the exact rhythm is taught later.' }
      ];
      var done = 0;
      cases.forEach(function (c) {
        var card = el('div', 'classify-card');
        card.innerHTML = '<div class="real-case-label">Real PTB-XL ECG ' + c.caseObj.ecg_id + ' · lead II</div>' + E.renderRealStrip(c.caseObj.lead_ii, 50, { w: 300, h: 100 }) +
          '<div class="row classify-btns"><button data-v="1">Sinus pattern</button><button data-v="0">Not sinus pattern</button></div>';
        grid.appendChild(card);
        card.querySelectorAll('button').forEach(function (b) {
          b.onclick = function () {
            if (card._done) return;
            var ok = (b.getAttribute('data-v') === '1') === c.sinus;
            var oldFeedback = card.querySelector('.fb'); if (oldFeedback) oldFeedback.remove();
            card.classList.remove('right', 'wrong'); card.classList.add(ok ? 'right' : 'wrong');
            card.insertAdjacentHTML('beforeend', '<div class="fb ' + (ok ? 'ok' : 'warn') + '">' + (ok ? '✓ ' : 'Not yet — use every P–QRS criterion, then try this strip again. ') + c.why + '</div>');
            if (!ok) return;
            card._done = true; done++;
            card.querySelectorAll('button').forEach(function (button) { button.disabled = true; });
            if (done === cases.length) {
              m.hidden = false; ctx.complete();
              NV.reveal([]);
              T.say('Nicely done. There’s one extra 12-lead clue: in <b>aVR</b>, the normal P usually points <i>down</i>. We’ll see why when the 12 leads appear.');
            }
          };
        });
      });
      T.say('Three lead-II teaching strips. Use the checklist — remember, rate doesn’t decide sinus.');
    }
  });

  // ---- S6 — intervals: PR & QRS -------------------------------------------
  SCENES.push({
    id: 'S6', part: 2, title: 'Intervals: PR & QRS', sub: 'measure them',
    mount: function (root, ctx) {
      T.clear(); T.setScope('PR and QRS intervals');
      add(root, 'lead-note', 'Now that you can find P and QRS, you can measure from the <b>start of P to the start of QRS</b> (the PR), and across the QRS itself. Two intervals you try to measure on every <i>readable</i> ECG: span each one and read the boxes, then compare with the printed value.');
      var m = masteryBar(root, 'intervals');
      var prCase = realCase('normal', 0);
      var qrsCase = realCase('wide_qrs', 2);
      var step1 = add(root, 'step', '<div class="step-h">1 · PR interval <span class="sec">(start of P → start of QRS)</span></div>');
      var prDone = false, qrsDone = false;
      Eng.intervalHandle(step1, {
        which: 'PR', caseObj: prCase,
        onScore: function (ok, ms, attempts) { ctx.evidence({ interactionId: 's6-pr-calipers', concept: 'pr_interval', subskills: ['measure'], correct: ok, score: ok ? 1 : 0.35, attempts: attempts, caseId: prCase.ecg_id, caseProvenance: 'real_eligible', caseEligible: true }); if (ok && !prDone) { prDone = true; NV.reveal(['pr']); showQRS(); maybeDone(); } }
      });
      function showQRS() {
        if (root.querySelector('#qrsStep')) return;
        var s2 = add(root, 'step'); s2.id = 'qrsStep';
        s2.innerHTML = '<div class="step-h">2 · QRS duration <span class="sec">(start of the first deflection → return to baseline)</span></div>';
        T.say('PR done. Now the <b>QRS</b> on a real beat that runs wide — we’ll just describe it as "wide" (the cause is a later module).');
        Eng.intervalHandle(s2, { which: 'QRS', caseObj: qrsCase, onScore: function (ok, ms, attempts) { ctx.evidence({ interactionId: 's6-qrs-calipers', concept: 'qrs_duration', subskills: ['measure'], correct: ok, score: ok ? 1 : 0.35, attempts: attempts, caseId: qrsCase.ecg_id, caseProvenance: 'real_eligible', caseEligible: true }); if (ok && !qrsDone) { qrsDone = true; NV.reveal(['qrs']); maybeDone(); } } });
      }
      function maybeDone() { if (prDone && qrsDone) { m.hidden = false; ctx.complete(); T.say('You can now measure both — and describe "long PR" / "wide QRS" without needing to know yet what they mean.'); } }
      T.say('Move the two handles to span the <b>PR</b>. Drag or tap, use the marker buttons, or focus a handle and press the arrow keys. The bar turns green inside the normal range (120–200 ms).');
    }
  });

  // ---- S7 — segments & the normal template --------------------------------
  SCENES.push({
    id: 'S7', part: 2, title: 'Segments & the normal reference', sub: 'ST, T, and the picture of normal',
    mount: function (root, ctx) {
      T.clear(); T.setScope('ST segment, T wave, normal template');
      add(root, 'lead-note', 'The last pieces: the <b>ST segment</b> (from the end of the QRS — the <b>J point</b> — toward the T) and the <b>T wave</b>. Then we’ll assemble a simple picture of a <b>normal-appearing</b> beat.');
      modelDisclosure(root, 'The movable baseline/ST activity isolates one component for mechanism learning; the reference beat revealed afterward is real PTB data.');
      var m = masteryBar(root, 'segments + reference');
      var base = add(root, 'step', '<div class="step-h">1 · Tap the baseline — choose the reference first</div>');
      var stOk = false, baselineDone = false;
      Eng.baselinePick(base, { onScore: function (ok, ev) {
        ctx.evidence({ interactionId: 's7-baseline-identification', concept: 'ecg_baseline', subskills: ['localize'], correct: ok, score: ok ? 1 : 0, attempts: ev.attempts, caseProvenance: 'authored_simulation', caseEligible: false });
        if (ok && !baselineDone) { baselineDone = true; showST(); }
      } });
      T.say('Before moving ST, identify its reference. Tap the flat <b>TP baseline</b> between the end of T and the next P, or use the labeled target buttons.');
      function showST() {
        if (root.querySelector('#stStep')) return;
        var s1 = add(root, 'step', '<div class="step-h">2 · Move ST off baseline, then restore it</div>'); s1.id = 'stStep';
        Eng.stDrag(s1, { onSettle: function (ok, st, movedOff, attempts) {
          if (movedOff) ctx.evidence({ interactionId: 's7-st-baseline-contrast', concept: 'st_segment', subskills: ['explain_mechanism'], correct: ok, score: ok ? 1 : 0.5, attempts: attempts, caseProvenance: 'authored_simulation', caseEligible: false });
          if (ok && !stOk) { stOk = true; NV.reveal(['st', 't', 'qt']); showTemplate(); }
        } });
        T.say('Now move the ST segment away from the baseline once, then settle it back. Drag, use the ST-level slider, or use Lower ST / Raise ST / Set at baseline.');
      }
      function showTemplate() {
        if (root.querySelector('#tmpl')) return;
        var templateCase = realCase('normal', 0);
        var box = add(root, 'template'); box.id = 'tmpl';
        box.innerHTML = '<div class="step-h">A real normal reference — PTB-XL ECG ' + templateCase.ecg_id + '</div>' +
          E.renderRealStrip(templateCase.lead_ii, 50, { w: 520, h: 160 }) +
          '<ul class="tmpl-list">' +
          '<li><b>P</b> small &amp; upright (in II)</li>' +
          '<li><b>PR</b> 120–200 ms</li>' +
          '<li><b>QRS</b> narrow (&lt;120 ms)</li>' +
          '<li><b>ST</b> near the baseline (no obvious lift or drop)</li>' +
          '<li><b>T</b> usually follows the main QRS direction (in II, both point up) <span class="sec">(aVR &amp; V1 are common exceptions)</span></li>' +
          '</ul>';
        T.say('There it is — the normal reference. The <b>QT</b> runs from the start of the QRS to the end of the T — ventricular activation through recovery; because it changes with heart rate, we often use the rate-corrected QTc. When QT matters is a later module.');
        miniCheck(box, 'Quick check: the ST segment is judged against which line?', [
          { label: 'The baseline', correct: true, fb: '✓ Right — ST is read relative to the baseline (the flat TP stretch between beats).' },
          { label: 'The T wave' }, { label: 'The QRS' }
        ], function () { m.hidden = false; ctx.complete(); });
      }
    }
  });

  // ---- S8 — one lead to twelve + R-wave progression + aVR sinus check ------
  SCENES.push({
    id: 'S8', part: 3, title: 'One lead → twelve', sub: '12 views + R-wave progression',
    mount: function (root, ctx) {
      T.clear(); T.setScope('12-lead layout, R-wave progression, aVR');
      var real = realCase('normal', 1);
      add(root, 'lead-note', 'Twelve leads = <b>twelve cameras</b> on the same beats — different views recorded at the <i>same time</i>, not twelve separate events. One quick orientation now: how the <b>R wave grows</b> across V1→V6 (and a glance at aVR). <span class="sec">(Which camera sees which wall is a later module' + (real ? '; this is real ECG ' + real.ecg_id : '') + '.)</span>');
      var m = masteryBar(root, '12-lead + R-wave');
      // The interactive task first (kept above the fold); the dense 12-lead goes below as reference.
      var host = add(root, 'measure-host', '<div class="step-h">1 · R-wave progression — scrub V1 → V6 <span class="sec">(real precordial leads)</span></div>');
      var done = function (transLead) {
        ctx.evidence({ interactionId: 's8-r-wave-scrub', concept: 'r_wave_progression', subskills: ['localize', 'discriminate'], correct: true, score: 1, attempts: 1, caseId: real.ecg_id, caseProvenance: 'real_eligible', caseEligible: true });
        NV.reveal(['rwave']);
        var leads = ['V1', 'V2', 'V3', 'V4', 'V5', 'V6'];
        var i = leads.indexOf(transLead); if (i < 1) i = 3;        // fallback to V4 if unknown
        var trio = [leads[Math.max(0, i - 1)], leads[i], leads[Math.min(5, i + 1)]];
        var opts = trio.map(function (l) { return l === leads[i] ? { label: l, correct: true, fb: '✓ Right — that’s where R first became taller than S (the transition).' } : { label: l }; });
        miniCheck(root, 'On this tracing, which lead was the first where R became taller than S (the transition)?', opts, function () { m.hidden = false; ctx.complete(); });
      };
      if (!real.median || !real.median.V3) throw new Error('Verified PTB precordial median beats are incomplete');
      Eng.rwaveScrubReal(host, real, { onDone: done });
      add(root, 'aside', '<b>Also — the aVR glance.</b> For the sinus check, the <b>P wave</b> in aVR usually points <b>down</b>. The QRS and T often point down too, because aVR looks from the opposite shoulder.');
      add(root, 'twelve', '<div class="step-h">The full 12-lead <span class="sec">— real PTB-XL ECG ' + real.ecg_id + '; glance, don’t measure</span></div>' + E.render12Real(real, {}));
      T.say('Step through V1→V6 with the slider, lead buttons, or Previous/Next — watch the R grow and the S shrink (transition often around V3–V4). Then glance at the full 12-lead below and notice aVR pointing the opposite way.');
    }
  });

  // ---- S9 — axis ----------------------------------------------------------
  SCENES.push({
    id: 'S9', part: 3, title: 'Axis — the heart’s direction', sub: 'rotate the vector',
    mount: function (root, ctx) {
      T.clear(); T.setScope('cardiac axis basics');
      add(root, 'lead-note', 'With the 12 leads as 12 views, the <b>axis</b> is the overall direction they reveal — the net direction the ventricles depolarize, as one arrow. It sits down-and-left in most hearts (the big left ventricle dominates). Quick read off the limb leads: <b>I up + aVF up = normal</b>; I up but aVF down = <b>leftward</b> (call it left axis only when it’s clearly past the normal zone); I down + aVF up = <b>right axis</b>.');
      modelDisclosure(root, 'The rotatable vector predicts lead polarity; it is a physics diagram, not a diagnostic tracing.');
      var m = masteryBar(root, 'the idea of axis direction');
      var host = add(root, 'axis-host');
      var track = add(root, 'zone-track', '<b>Explore both:</b> <span class="zt" data-z="normal">○ normal (green)</span> <span class="zt" data-z="off">○ left / right axis (amber–red)</span>');
      var reached = {};
      function paint() { track.querySelectorAll('.zt').forEach(function (s) { var z = s.getAttribute('data-z'); if (reached[z]) { s.classList.add('on'); s.innerHTML = '● ' + s.textContent.replace(/^[○●] /, ''); } }); }
      var lab = Eng.hexaxial(host, {
        params: E.params({ axis: 60 }),
        onChange: function (p) {
          var z = (p.axis >= 0 && p.axis <= 90) ? 'normal' : 'off'; // off = borderline or deviated
          reached[z] = true; paint();
          if (reached.normal && reached.off && !root._axdone) {
            root._axdone = true; NV.reveal(['axis']);
            ctx.evidence({ interactionId: 's9-axis-dial', concept: 'axis_normal', subskills: ['explain_mechanism'], correct: true, score: 1, attempts: 1, caseProvenance: 'authored_simulation', caseEligible: false });
            T.say('That’s the whole idea: rotate the arrow and the leads flip. <b>I up + aVF up = normal</b>; I up but aVF down = <b>leftward</b> (call it left axis only when it’s clearly past the normal zone); I down + aVF up = <b>right axis</b>. Borderline leftward cases get pinned with lead II later. You just <i>described</i> axis without needing the clinical causes.');
            miniCheck(root, 'Name it: if lead I is up but aVF is clearly down, the axis is…', [
              { label: 'Left axis', correct: true, fb: '✓ Right — I up, aVF down points up-and-left (left axis).' },
              { label: 'Right axis' }, { label: 'Normal' }
            ], function () { m.hidden = false; ctx.complete(); });
          }
        }
      });
      T.say('Rotate the arrowhead by dragging, using the QRS-axis slider or arrow keys, or choosing a zone button. Watch each limb lead flip up/down as the direction changes. Reach the <b>green (normal)</b> zone and then any <b>off-normal</b> spot — the tracker above shows what’s left.');
    }
  });

  // ---- S10 — the sweep, modeled & active ----------------------------------
  SCENES.push({
    id: 'S10', part: 4, title: 'The sweep, modeled', sub: 'watch me read — with you',
    mount: function (root, ctx) {
      T.clear(); T.setScope('systematic read order');
      add(root, 'sweep-rail', railHTML(-1));
      add(root, 'lead-note', 'Time to put it together. The order, every time: <b>Rate → Rhythm → Axis → PR → QRS width → ST-T → Synthesis.</b> (We learned axis alongside the 12-lead, but in the sweep it comes earlier.) Watch two real 12-leads read out loud — in <b>finding-language only</b> (describe, don’t diagnose).');
      var m = masteryBar(root, 'the read, modeled');
      // Build worked examples from REAL cases, narrated from their real 12SL features.
      function caseSteps(c) {
        var f = c.features, t = E.caseTruth(c), R = Math.round;
        var rateW = t.rate === 'tachy' ? 'fast rate (>100; tachycardia)' : t.rate === 'brady' ? 'slow rate (<60; bradycardia)' : 'normal';
        var axW = t.axis === 'left_axis' ? 'left axis' : t.axis === 'right_axis' ? 'right axis' : 'normal axis';
        var prW = t.pr === 'long_pr' ? 'long' : 'normal', qrsW = t.qrs === 'wide_qrs' ? 'wide' : 'narrow/normal';
        var isSinus = t.rhythm === 'sinus';
        var tiled = !(c.lead_ii && c.lead_ii.length);   // no real rhythm strip → median tiled at the real rate (regular by construction)
        var rhythmPhrase = isSinus ? 'sinus pattern' : 'rhythm not clearly sinus';
        var ratePhrase = (t.rate === 'tachy' ? 'fast rate' : t.rate === 'brady' ? 'slow rate' : 'normal rate') + ' ~' + R(f.heart_rate) + ' bpm';
        var synth = rhythmPhrase + ', ' + ratePhrase + ', ' + axW + ', PR ' + R(f.pr_ms) + ' ms' + (t.pr === 'long_pr' ? ' (long)' : '') + ', QRS ' + R(f.qrs_ms) + ' ms' + (t.qrs === 'wide_qrs' ? ' (wide)' : '') + ', ' + (t.st === 'flat_st' ? 'ST/T normal-appearing' : 'ST/T not assessable here');
        return [
          { rail: 0, predict: { kind: 'rate', truth: R(f.heart_rate) }, say: '<b>Rate:</b> ~' + R(f.heart_rate) + ' bpm — ' + rateW + '.' },
          { rail: 1, say: !isSinus ? '<b>Rhythm:</b> I’d run the sinus checklist — P before every QRS, upright in II, same shape. On this one I can’t confirm all of it, so I’d say <b>“not clearly sinus”</b> and leave the name for a later module.' : (tiled ? '<b>Rhythm:</b> on this teaching rhythm strip the visible P–QRS pattern is <b>sinus-appearing</b> — a P before each QRS, upright in II. (aVR points the opposite way, which fits.)' : '<b>Rhythm:</b> a P before every QRS, upright in II and consistent in shape — a <b>sinus pattern</b>. (aVR points the opposite way, which fits.)') },
          { rail: 2, say: '<b>Axis:</b> ' + axW + ' (~' + R(f.axis_deg) + '°), read off lead I &amp; aVF.' },
          { rail: 3, say: '<b>PR:</b> ' + R(f.pr_ms) + ' ms (' + prW + ') — start of P to start of QRS.' },
          { rail: 4, predict: (t.qrs === 'wide_qrs' ? { kind: 'qrs', truth: 'wide' } : null), say: '<b>QRS width:</b> ' + R(f.qrs_ms) + ' ms (' + qrsW + '). We name it; meaning is a later module.' },
          { rail: 5, say: t.st === 'flat_st' ? '<b>ST-T:</b> ST is near baseline; T is normal-appearing for this teaching case. (Reading abnormal ST/T is a later module.)' : '<b>ST-T:</b> I wouldn’t make a confident ST/T call from this tracing — I’d mark it <b>not assessable</b> here. (Classifying ST/T changes is a later module.)' },
          { rail: 6, say: '<b>Synthesis:</b> "' + synth + '" — all <i>described</i>, nothing diagnosed yet.' }
        ];
      }
      var nbCase = realCase('normal', 0);
      var devCase = realCase('wide_qrs', 1);
      var cases = [{ caseObj: nbCase, steps: caseSteps(nbCase) }, { caseObj: devCase, steps: caseSteps(devCase) }];
      var ci = 0;
      function runCase() {
        var c = cases[ci];
        var view = root.querySelector('#sweepView') || add(root, 'sweep-view'); view.id = 'sweepView';
        var head = function () { return '<div class="sec">Case ' + (ci + 1) + ' of ' + cases.length + ' · real PTB-XL ECG ' + c.caseObj.ecg_id + '</div>'; };
        var draw = function (hl) { return head() + E.render12Real(c.caseObj, hl ? { highlight: hl } : {}); };
        view.innerHTML = draw();
        var si = 0;
        T.say('Here’s case ' + (ci + 1) + ' (real PTB-XL ECG ' + c.caseObj.ecg_id + '). Step through the sweep with the buttons <b>right under the ECG</b> — each reveal shows the finding and its evidence (predict first where it asks).');
        nextStep();
        function nextStep() {
          if (si >= c.steps.length) { ci++; if (ci < cases.length) { T.say('Now a second one — this time spot the differences as I read.'); runCase(); } else { m.hidden = false; ctx.complete(); T.say('That’s the model. Your turn next — you’ll do the sweep with me coaching each step.'); } return; }
          var st = c.steps[si];
          setRail(root, st.rail);
          if (st.highlight) view.innerHTML = draw(st.highlight);
          if (st.predict) {
            if (st.predict.kind === 'rate') {
              var w = el('div', 'choices'); var tr = st.predict.truth;
              [Math.round(tr * 0.7 / 5) * 5, tr, Math.round(tr * 1.4 / 5) * 5].forEach(function (v) { var b = el('button', '', v + ' bpm'); b.onclick = function () { clearInline(); T.you(v + ' bpm'); var ok = Math.abs(v - tr) <= 6; T.say(ok ? 'Yes — right around there.' : 'Not quite — it’s closer to ~' + tr + '. Watch:'); reveal(); }; w.appendChild(b); });
              appendChoices(w, '🔮 Predict first: what’s the rate (bpm)?');
            } else {
              var w2 = el('div', 'choices');
              ['Normal', 'Wide'].forEach(function (lab2) { var b = el('button', '', lab2); b.onclick = function () { clearInline(); T.you(lab2); var ok = lab2.toLowerCase() === st.predict.truth; T.say(ok ? 'Right — it’s on the wide side. ' : 'Look again — it’s a bit wide. '); reveal(); }; w2.appendChild(b); });
              appendChoices(w2, '🔮 Predict first: is the QRS normal or wide?');
            }
          } else { var b = el('div', 'row'); var nb = el('button', 'accent', 'Next finding ▸'); nb.onclick = function () { clearInline(); T.say(st.say); si++; setTimeout(nextStep, 200); }; b.appendChild(nb); appendChoices(b, 'Follow my read on the trace →'); }
          function reveal() { T.say(st.say); si++; setTimeout(nextStep, 250); }
        }
      }
      function clearInline() { var x = document.getElementById('sweepDock'); if (x) x.innerHTML = ''; }
      function appendChoices(node, promptHtml) {
        var dock = document.getElementById('sweepDock') || add(root, 'sweep-dock'); dock.id = 'sweepDock'; dock.innerHTML = '';
        var box = el('div', 'inline-answer'); if (promptHtml) box.innerHTML = '<div class="inline-q">' + promptHtml + '</div>'; box.appendChild(node);
        dock.appendChild(box); box.scrollIntoView({ block: 'nearest' });
      }
      runCase();
    }
  });

  // ---- S11 — guided practice (fading scaffold, ≥2 axis reps) ---------------
  SCENES.push({
    id: 'S11', part: 4, title: 'Guided practice', sub: 'you read, I coach',
    mount: function (root, ctx) {
      T.clear(); T.setScope('guided systematic read');
      add(root, 'sweep-rail', railHTML(-1));
      add(root, 'lead-note', 'Now you run the sweep, step by step. I’ll prompt you — and I’ll ease off as you go.');
      var m = masteryBar(root, 'guided read');
      // Real cases: a clean normal (full scaffold) then a real deviation (lighter).
      var gc1 = realCase('normal', 2);
      var gc2 = realCase('left_axis', 0);
      var cases = [{ caseObj: gc1, truth: E.caseTruth(gc1) }, { caseObj: gc2, truth: E.caseTruth(gc2) }];
      var ci = 0;
      var stepsByCase = [
        [ // case 1 — full scaffold
          { key: 'rate', q: 'Step 1 — <b>Rate?</b> Count big boxes between R’s (300 ÷ that). Type what you see.' },
          { key: 'rhythm', q: 'Step 2 — <b>Rhythm?</b> P before every QRS, uniform, upright in II? Sinus pattern, not sinus pattern, or not clear / not assessable?' },
          { key: 'axis', q: 'Step 3 — <b>Axis?</b> Check lead I and aVF: normal, leftward / left axis, or right axis?' },
          { key: 'pr', q: 'Step 4 — <b>PR</b> normal or long?' },
          { key: 'qrs', q: 'Step 4b — <b>QRS width</b> narrow or wide?' },
          { key: 'st', q: 'Step 5 — <b>ST/T:</b> is the ST near the baseline and the T normal-appearing — or not assessable?' }
        ],
        [ // case 2 — lighter scaffold (fewer prompts, combined)
          { key: 'rate', q: 'Your turn with less help. <b>Rate</b>?' },
          { key: 'axis', q: 'And the <b>axis</b>? Check lead I and aVF — normal, left, or right? Look carefully at aVF here.' },
          { key: 'rhythm', q: 'In one line, give the <b>rhythm + intervals + ST/T</b>. Try: “sinus pattern, PR …, QRS …, ST/T …”.', multi: true }
        ]
      ];
      function runCase() {
        var c = cases[ci];
        var view = root.querySelector('#gView') || add(root, 'sweep-view'); view.id = 'gView';
        view.innerHTML = '<div class="sec">Case ' + (ci + 1) + ' of ' + cases.length + ' · ' + (ci === 0 ? 'full coaching' : 'lighter coaching') + ' · real PTB-XL ECG ' + c.caseObj.ecg_id + '</div>' + E.render12Real(c.caseObj, {});
        T.say(ci === 0 ? 'Case 1. I’ll prompt each step. Answer in your own words — a number or a word is fine (e.g. “about 75, normal rate” or “PR 260, long”).' : 'Case 2 — I’ll step back a bit; you carry more of it.');
        var steps = stepsByCase[ci], si = 0;
        ask();
        function ask() {
          if (si >= steps.length) { ci++; if (ci < cases.length) runCase(); else finish(); return; }
          var st = steps[si], retried = false;
          if (!st.multi && !c.truth[st.key]) { si++; return ask(); } // skip components the data can't assert (e.g. ST on a case with ST/T changes)
          setRail(root, railFor(st.key));
          render();
          function render() {
            var row = el('div', 'choices ask-row');
            var inp = el('input'); inp.placeholder = 'describe in your words…';
            var go = el('button', 'accent', 'Submit');
            function submit() {
              var v = inp.value.trim(); if (!v) return; T.you(v);
              var expected = st.multi ? [c.truth.rhythm, c.truth.pr, c.truth.qrs, c.truth.st].filter(Boolean) : [c.truth[st.key]];
              var g = T.grade(v, expected, LABELS);
              // A "critical" finding the case was chosen to teach can't be skipped, even at score ≥0.5.
              var CRIT = ['wide_qrs', 'long_pr', 'left_axis', 'right_axis'];
              var critMiss = expected.some(function (c) { return CRIT.indexOf(c) >= 0 && g.missed.indexOf(c) >= 0; });
              var pass = st.multi ? (g.score >= 0.5 && !critMiss) : (g.score >= 1);
              if (pass) { T.say('✓ ' + g.message); si++; setTimeout(ask, 250); }
              else if (!retried) { retried = true; T.say('Let me reason it back on the trace: ' + g.message + ' Take one more look and try again.'); render(); }
              else { T.say(g.message + ' We’ll move on — keep that rule in mind.'); si++; setTimeout(ask, 250); }
            }
            go.onclick = submit; inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') submit(); });
            row.appendChild(inp); row.appendChild(go); appendChoices(row, st.q); inp.focus();
          }
        }
      }
      function finish() { m.hidden = false; ctx.complete(); T.say('You ran the whole sweep — twice, with me fading out. Last step: do one entirely on your own.'); }
      function appendChoices(node, promptHtml) {
        var dock = document.getElementById('gDock') || add(root, 'sweep-dock'); dock.id = 'gDock'; dock.innerHTML = '';
        var box = el('div', 'inline-answer'); if (promptHtml) box.innerHTML = '<div class="inline-q">' + promptHtml + '</div>'; box.appendChild(node);
        dock.appendChild(box); box.scrollIntoView({ block: 'nearest' });
      }
      runCase();
    }
  });

  // ---- S12 — independent read + payoff ------------------------------------
  SCENES.push({
    id: 'S12', part: 4, title: 'Your read', sub: 'on your own',
    mount: function (root, ctx) {
      T.clear(); T.setScope('independent read');
      add(root, 'lead-note', 'Two on your own. First with the step-rail as a checklist (no coaching), then a blank read. <b>“Not assessable”</b> is a good answer when the tracing doesn’t support a confident call. I’m here only if you ask.');
      var m = masteryBar(root, 'the foundational read');
      // case 1 — rail visible, fill each field (a real normal ECG)
      var rc1 = realCase('normal', 3);
      var truth1 = E.caseTruth(rc1);
      var box1 = add(root, 'solo');
      box1.innerHTML = '<div class="sec">Case 1 — fill each step (rail as your checklist) · real PTB-XL ECG ' + rc1.ecg_id + '</div>' + E.render12Real(rc1, {}) +
        '<div class="solo-fields">' +
        field('rate', 'Rate') + field('rhythm', 'Rhythm') + field('axis', 'Axis') +
        field('pr', 'PR') + field('qrs', 'QRS') + field('st', 'ST / T') +
        '</div><button class="accent" id="solo1go">Submit my read</button><div id="solo1fb"></div>';
      var t0 = Date.now();
      box1.querySelector('#solo1go').onclick = function () {
        var total = 0, got = 0, lines = [];
        Object.keys(truth1).forEach(function (k) {
          if (!truth1[k]) return;   // skip components the data can't assert (e.g. ST on ST/T-changed cases)
          var v = box1.querySelector('#f_' + k).value.trim(); total++;
          var g = T.grade(v, [truth1[k]], LABELS);
          if (g.score >= 1) { got++; lines.push('<li class="ok">' + LABELS[truth1[k]] + ' ✓</li>'); }
          else { lines.push('<li class="warn">' + LABELS[truth1[k]] + ' — ' + (v ? 'you wrote “' + escapeH(v) + '”; ' : '') + g.message + '</li>'); }
        });
        box1.querySelector('#solo1fb').innerHTML = '<div class="fb"><b>' + got + '/' + total + '</b> components<ul class="solo-res">' + lines.join('') + '</ul></div>';
        showCase2(Math.round(got / total * 100));
      };
      T.say('Case 1 — run your sweep and fill each box. The rail is your checklist; I’ll stay quiet unless you ask. <button class="link" id="hintAxis">need an axis hint?</button>');
      setTimeout(function () { var h = document.getElementById('hintAxis'); if (h) h.onclick = function () { T.say('Axis hint: glance at lead I and aVF — both up = normal; I up but aVF down means leftward (call left axis when clearly past normal); I down + aVF up = right axis.'); }; }, 50);

      function showCase2(acc1) {
        if (root.querySelector('#solo2')) return;
        // a real ECG that genuinely has the two target deviations (wide QRS + left axis)
        var rc2 = realCase('wide_qrs', 0);
        var tt = E.caseTruth(rc2);
        var truth2 = [tt.rhythm || 'sinus', tt.rate, tt.axis, tt.qrs, tt.st].filter(Boolean);
        // the deviations THIS real case actually has — the learner must catch these to pass
        var devLabel = { tachy: 'the fast rate', brady: 'the slow rate', left_axis: 'the left axis (lead I vs aVF)', right_axis: 'the right axis (lead I vs aVF)', long_pr: 'the long PR', wide_qrs: 'the wide QRS (measure it)' };
        var devs = [tt.rate !== 'normal_rate' ? tt.rate : null, tt.axis !== 'normal_axis' ? tt.axis : null, tt.qrs === 'wide_qrs' ? 'wide_qrs' : null, tt.pr === 'long_pr' ? 'long_pr' : null].filter(Boolean);
        var box2 = add(root, 'solo'); box2.id = 'solo2';
        box2.innerHTML = '<div class="sec">Case 2 — blank read, one line covering rhythm, rate, axis, intervals, ST/T (order doesn’t matter — just include each part). · real PTB-XL ECG ' + rc2.ecg_id + '</div>' + E.render12Real(rc2, {}) +
          '<div class="ask-row"><input id="solo2in" placeholder="your full read in one line…"><button class="accent" id="solo2go">Submit</button></div><div id="solo2fb"></div>';
        T.say('Now a blank one — no fields, no rail prompts. Describe everything you see in one line.');
        var tries = 0;
        box2.querySelector('#solo2go').onclick = function () {
          var v = box2.querySelector('#solo2in').value.trim(); if (!v) return;
          tries++;
          var g = T.grade(v, truth2, LABELS);
          var acc2 = Math.round(g.score * 100);
          // must catch the deviations THIS case actually has AND cover the sweep (not 2 easy keywords)
          var missed = devs.filter(function (d) { return g.got.indexOf(d) < 0; });
          var enough = g.got.length >= Math.min(4, truth2.length);          // ≥4 of the gradeable sweep domains
          var pass = g.score >= 0.6 && missed.length === 0 && enough;
          if (pass) {
            box2.querySelector('#solo2fb').innerHTML = '<div class="fb ok">✓ ' + g.message + ' You caught the key findings and covered the sweep.</div>';
            finish(Math.round((acc1 + acc2) / 2));
          } else if (tries >= 2) {
            var missTxt = missed.map(function (d) { return devLabel[d] || d.replace(/_/g, ' '); }).join(' and ');
            box2.querySelector('#solo2fb').innerHTML = '<div class="fb warn">' + g.message + (missed.length ? ' <span class="sec">The key thing to catch here was ' + missTxt + '. Re-look next time.</span>' : (enough ? '' : ' <span class="sec">Try to cover the whole sweep next time: rate, rhythm, axis, PR, QRS, ST/T.</span>')) + '</div>';
            finish(Math.round((acc1 + acc2) / 2));
          } else {
            var miss2 = missed.length ? missed.map(function (d) { return devLabel[d] || d.replace(/_/g, ' '); }).join('</b> and <b>') : null;
            box2.querySelector('#solo2fb').innerHTML = '<div class="fb warn">' + g.message + (miss2 ? ' One more look — you haven’t called: <b>' + miss2 + '</b>.' : ' One more look — try to cover the whole sweep.') + ' Keep the whole sweep in your answer (rate, rhythm, axis, PR, QRS, ST/T), then submit again.</div>';
            box2.querySelector('#solo2in').focus();
          }
        };
      }
      function finish(acc) {
        var bestKey = global.FOUNDATIONS_BEST_KEY || 'found_best:guest';
        var best = +(localStorage.getItem(bestKey) || 0);
        if (acc > best) { localStorage.setItem(bestKey, acc); best = acc; }
        var secs = Math.round((Date.now() - t0) / 1000);
        var pay = add(root, 'payoff');
        pay.innerHTML = '<div class="payoff-score">Sweep accuracy <b>' + acc + '%</b> <span class="sec">· ' + secs + 's</span></div>' +
          '<h2 class="payoff-h">You completed your first beginner 12-lead sweep.</h2>' +
          '<p>You checked rate, rhythm pattern, axis, PR, QRS width, and ST/T appearance — and <b>described exactly what the tracing supported.</b> That’s the foundation every later module reuses.</p>' +
          '<div class="payoff-next"><b>Coming next:</b> what the rhythms are called &amp; look like · what abnormal intervals / axis / ST-T <i>mean</i> · which findings are urgent.</div>';
        pay.scrollIntoView({ behavior: 'smooth' });
        m.hidden = false; ctx.complete();
        T.say('That’s Foundations done. You went from "what is this?" to a full descriptive sweep on your own. That’s a real milestone — see you in the next module.');
      }
    }
  });

  // ---- shared bits --------------------------------------------------------
  var LABELS = {
    sinus: 'sinus rhythm', regular: 'regular', irregular: 'irregular', tachy: 'tachycardia (fast)', brady: 'bradycardia (slow)',
    normal_rate: 'normal rate', normal_pr: 'normal PR', long_pr: 'long PR', normal_qrs: 'narrow QRS', wide_qrs: 'wide QRS',
    normal_axis: 'normal axis', left_axis: 'left axis', right_axis: 'right axis', flat_st: 'flat ST', upright_t: 'upright T'
  };
  var RAIL = ['Rate', 'Rhythm', 'Axis', 'PR', 'QRS width', 'ST-T', 'Synthesis'];
  function railHTML(active) {
    return '<div class="rail">' + RAIL.map(function (r, i) { return '<span class="rail-step ' + (i === active ? 'active' : '') + '" data-i="' + i + '">' + r + '</span>'; }).join('<span class="rail-arr">›</span>') + '</div>';
  }
  function setRail(root, active) {
    var steps = root.querySelectorAll('.rail-step');
    steps.forEach(function (s, i) { s.classList.toggle('active', i === active); s.classList.toggle('done', i < active && active >= 0); });
  }
  function railFor(key) { return { rate: 0, rhythm: 1, axis: 2, pr: 3, qrs: 4, st: 5 }[key]; }
  function field(k, label) { return '<label class="solo-field"><span>' + label + '</span><input id="f_' + k + '" placeholder="…"></label>'; }
  function escapeH(s) { return s.replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  global.SCENES = SCENES;
})(window);
