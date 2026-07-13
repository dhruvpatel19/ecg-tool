/* ui.js — Foundations chrome: the AI tutor, meaning-based grading, the
 * normal-values card, and small DOM helpers.
 *
 * The tutor's ask-anything tries the REAL nano LLM (POST /tutor/chat on the
 * backend, the same grounded endpoint the main app uses) and falls back to a
 * grounded, scope-aware local knowledge base when the backend isn't reachable —
 * so the experience is intact offline and tangents return to the exact paused
 * scene state. Free-text answers are graded on MEANING (a
 * finding-language synonym map with partial credit + reason-me-back), never
 * keyword equality, and correct-but-ahead answers are credited, not penalized.
 */
(function (global) {
  'use strict';
  function el(tag, cls, html) { var d = document.createElement(tag); if (cls) d.className = cls; if (html != null) d.innerHTML = html; return d; }

  // ---- Tutor panel ---------------------------------------------------------
  var stream, input, scopeNote = '';
  var LLM_URL = global.FOUNDATIONS_LLM_URL || 'http://127.0.0.1:8000/tutor/foundations';

  function mount(streamEl, inputEl, sendBtn) {
    stream = streamEl; input = inputEl;
    function send() { var t = input.value.trim(); if (!t) return; input.value = ''; askAnything(t); }
    sendBtn.onclick = send;
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
  }
  function setScope(note) { scopeNote = note; }       // what's been taught so far
  function clear() { if (stream) stream.innerHTML = ''; }

  function say(html, who) {
    var d = el('div', 'msg ai');
    d.innerHTML = '<span class="who">' + (who || 'Tutor') + '</span><div class="body">' + html + '</div>';
    stream.appendChild(d); stream.scrollTop = stream.scrollHeight; return d;
  }
  function you(t) {
    var d = el('div', 'msg you'); d.innerHTML = '<span class="who">You</span><div class="body">' + escapeHtml(t) + '</div>';
    stream.appendChild(d); stream.scrollTop = stream.scrollHeight;
  }
  function choices(opts) {
    var w = el('div', 'choices');
    opts.forEach(function (o) {
      var b = el('button', o.cls || ''); b.innerHTML = o.label;
      b.onclick = function () { w.remove(); you(o.label); o.go && o.go(); };
      w.appendChild(b);
    });
    stream.appendChild(w); stream.scrollTop = stream.scrollHeight; return w;
  }
  function typing() { var d = el('div', 'msg ai'); d.innerHTML = '<span class="who">Tutor</span><div class="body"><span class="dots"><i></i><i></i><i></i></span></div>'; stream.appendChild(d); stream.scrollTop = stream.scrollHeight; return d; }

  // Ask-anything: real LLM first, grounded local KB fallback.
  // Scope split (the boundary is CLINICAL meaning, not all meaning): foundational
  // "what is / what does X represent" questions ARE answered — that's the point of the
  // module. Only clinical questions — cause / danger / diagnosis / treatment, or the
  // clinical meaning of a specific finding ("what does a WIDE QRS mean?") — are deferred.
  var CLINICAL = /caus|dangerous|diagnos|disease|treat|why (is it |does it )?bad|heart attack|infarct|how serious|\bserious\b|is it (bad|serious|dangerous|ok)|worr|emergen|\bkill|stemi|prognos|\bmanage\b|urgent|life.?threat/;
  var FINDING = /wide|broad|long pr|prolong|short pr|elevat|depress|deviat|invert|abnormal|\bblock/;
  var MEANING = /\bmean|signif|implicat|matter|what.?s wrong/;
  var DANGER = /danger|serious|urgent|emergen|\bkill|life.?threat|is (it|this) (bad|ok)|\bbad\b|worr|heart attack/;
  // Named diagnosis entities are out of scope regardless of phrasing ("what is AV block?").
  var DIAGNOSIS = /\bav block|heart block|first.?degree|\blbbb|\brbbb|bundle branch|\bnstemi|\bstemi|\bmi\b|infarct|ischem|\blvh\b|\brvh\b|hypertroph|\bwpw\b|pre.?excit|pericarditis|\bafib\b|a.?fib|atrial fib|atrial flutter|\bflutter|long qt|\bvt\b|\bvf\b|tachyarr|brugada|wellens/;
  // Real-patient / symptom language → safety redirect, never clinical guidance.
  var PATIENT = /\bmy (ecg|ekg|heart|result)|\bi (have|had|feel|felt)|\bpatient|chest pain|short(ness)? of breath|\bsob\b|palpitat|syncop|faint|passed out|dizzy|emergency room|ambulance|should i (worry|be worried|go|see)/;
  // "what's wrong with this ECG?" = an interpretation request → redirect to describe-it-yourself.
  // "what's wrong with my answer?" is tutoring and is allowed through.
  var INTERP = /\bwhat.?s (wrong|abnormal|the (problem|issue|matter))\b/;
  var INTERP_REF = /\b(ecg|ekg|tracing|strip|trace|this one|with this|on this)\b/;
  function isInterp(s) { return INTERP.test(s) && INTERP_REF.test(s) && !/\bmy (answer|read|reading|response|working|attempt)\b/.test(s); }
  function isClinical(s) { return CLINICAL.test(s) || DIAGNOSIS.test(s) || PATIENT.test(s) || isInterp(s) || (MEANING.test(s) && FINDING.test(s)); }
  function educationalTangent(s) {
    if (/t.?wave|invert/.test(s)) return 'An <b>inverted T wave</b> is a descriptive recovery finding, not automatically a heart attack. It can occur for several reasons—including normal lead-specific patterns, altered ventricular activation, strain, or ischemia—so the involved leads, shape, comparison with prior ECGs, and clinical context matter. In this scene, first find the T wave and name its direction; the repolarization and ischemia modules build the differential.';
    if (/wide|bundle|qrs/.test(s)) return 'A <b>wide QRS</b> means ventricular activation took longer than usual. Bundle delay, pacing, pre-excitation, ventricular origin, and other conduction problems can do that; this module teaches you to measure and describe it, and the ventricular-conduction module teaches the causes and discriminators.';
    if (/long pr|av block|heart block|first.?degree/.test(s)) return 'A <b>long PR</b> means atrial-to-ventricular conduction took longer than the normal reference. Several nodal, medication, physiologic, and conduction contexts can produce it; for now, mark P onset to QRS onset, and the AV-conduction module will build the specific patterns.';
    if (/stemi|heart attack|infarct|ischem|st elev|st depress/.test(s)) return 'An ST–T change can raise concern for ischemia, but one shape is not a patient diagnosis. Contiguous lead distribution, reciprocal or dynamic change, mimics, symptoms, serial ECGs, and other clinical data matter; the ischemia module teaches that chain. Here, anchor the J point and describe ST relative to baseline.';
    if (DIAGNOSIS.test(s)) return 'That is a named diagnosis from a later module. The useful first-principles bridge is: describe the exact P–QRS timing, width, axis, or ST–T feature that would support it, then the later module adds criteria, mimics, and clinical meaning.';
    return 'That is a useful clinical connection. A waveform finding usually has more than one possible cause, so its lead distribution, timing, comparison with prior tracings, and patient context determine what it means. We will build that differential later; here, keep the observation precise enough to reuse.';
  }
  function clinicalDeflect(s) {
    if (PATIENT.test(s)) return 'I can’t help with a real ECG, symptoms, or anyone’s care — for that, use a qualified clinical workflow. In this teaching module I can help you practice the <b>descriptive steps</b> on the teaching tracing. Want to name or measure what’s on screen?';
    if (isInterp(s)) return 'I won’t interpret the tracing for you — that’s the skill you’re building. Walk the sweep and <b>describe</b> what you see (rate, rhythm, axis, PR, QRS, ST/T), and I’ll help you name and measure each part.';
    return educationalTangent(s);
  }
  function offerReturn() {
    var title = (document.getElementById('scTitle') || {}).textContent || 'the lesson';
    choices([{ label: '↩ Return to ' + title, cls: 'accent', go: function () {
      say('Back to <b>' + escapeHtml(title) + '</b>. Your scene and unfinished interaction are unchanged. Continue with: ' + escapeHtml(scopeNote || 'the active checkpoint') + '.');
      var scene = document.getElementById('sceneRoot'); if (scene) { scene.setAttribute('tabindex', '-1'); scene.focus(); }
    } }]);
  }
  function askAnything(q) {
    you(q);
    function present(html) { say(html); offerReturn(); }
    // Real-patient interpretation remains bounded. General clinical tangents get a
    // concise educational bridge, then an exact return control.
    if (isClinical(q.toLowerCase())) { present(clinicalDeflect(q.toLowerCase())); return; }
    var t = typing();
    function answer(html) { t.remove(); present(html); }
    llm(q).then(function (resp) { answer(resp || localAnswer(q)); }).catch(function () { answer(localAnswer(q)); });
  }

  // POST to the grounded backend tutor; resolve to a string or null on failure.
  function llm(q) {
    return new Promise(function (resolve) {
      var done = false; var to = setTimeout(function () { if (!done) { done = true; resolve(null); } }, 4500);
      try {
        fetch(LLM_URL, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ learnerMessage: q, scope: scopeNote })
        }).then(function (r) { return r.ok ? r.json() : null; })
          .then(function (j) {
            if (done) return; done = true; clearTimeout(to);
            var msg = j && (j.tutorMessage || j.feedback);
            // The backend tutor is case/image-grounded; without an ECG image it may
            // reply "upload an ECG…". That's useless for a Foundations concept question —
            // treat such degenerate replies as a miss so the grounded local KB answers instead.
            if (msg && /upload|no ecg|provide (?:an|a|the).{0,12}ecg|ecg image|image (?:or|was|were|of)|trace.{0,12}provided|can.?t provide a grounded|need (?:an|the).{0,8}ecg|no (?:image|trace|tracing)/i.test(msg)) msg = null;
            // Remote provider prose is untrusted text. Keep the local KB's
            // authored markup, but never let a model create same-origin DOM
            // (links/forms/styles/images) inside the unsandboxed lesson iframe.
            resolve(msg ? escapeHtml(String(msg)).replace(/\r?\n/g, '<br>') : null);
          })
          .catch(function () { if (done) return; done = true; clearTimeout(to); resolve(null); });
      } catch (e) { if (!done) { done = true; clearTimeout(to); resolve(null); } }
    });
  }

  // Grounded local KB — scope-aware so it won't dump clinical/advanced content.
  var KB = [
    { k: ['p wave', 'what is p', 'p stand'], a: 'The <b>P wave</b> is the small wave before the QRS — it’s the atria (the top chambers) <b>electrically activating</b>. It’s small because the atria have much less muscle than the ventricles.' },
    { k: ['qrs', 'big spike', 'tall spike'], a: 'The <b>QRS</b> is the tall, sharp spike — the ventricles (the big pumping chambers) <b>electrically activating</b>, quickly. It’s tall because the ventricular muscle is thick.' },
    { k: ['t wave', 'last bump'], a: 'The <b>T wave</b> is the rounded bump after the spike — the ventricles electrically <i>resetting</i> (repolarizing) so they can activate again.' },
    { k: ['pr', 'flat after p', 'pause'], a: 'Two things share the name: the <b>PR segment</b> is the flat part after the P wave (the AV node briefly holds the signal before the ventricles activate); the <b>PR interval</b> is the whole stretch from the <i>start of P to the start of QRS</i> — that’s the one with the normal value of <b>120–200 ms</b>.' },
    { k: ['box', 'square', 'grid'], a: 'Each <b>small box is 40 ms wide and 0.1 mV tall</b>; 5 small = 1 big box = 200 ms. Once you find a waveform’s start and end, the grid turns distance into time.' },
    { k: ['rate', 'bpm', 'how fast'], a: 'First check the rhythm is regular. If so: <b>300 ÷ the number of big boxes between two R’s</b>. If it’s irregular, count beats in 6 seconds × 10. Normal is 60–100.' },
    { k: ['sinus', 'normal rhythm'], a: '<b>Sinus</b> means the beat appears to start in the SA node — we <i>infer</i> it from the P waves: a P before every QRS, a QRS after every P, the P upright in lead II and the same shape each time, a steady PR. (Rate isn’t part of it — sinus can be fast or slow.)' },
    { k: ['axis', 'direction'], a: 'The <b>axis</b> is the overall direction the ventricles depolarize, as one arrow. Quick read off the limb leads: <b>I up + aVF up = normal</b>; I up but aVF down = leftward (toward left axis); I down + aVF up = right axis. Borderline cases get refined later.' },
    { k: ['avr', 'a v r'], a: 'In <b>aVR</b> a normal P (and usually the QRS and T) points <i>down</i> — that lead looks at the heart from the opposite shoulder, so the normal signals head away from it.' },
    { k: ['st', 'segment'], a: 'The <b>ST segment</b> is the stretch from the end of the QRS (the <b>J point</b>) to the T. Normally it sits <b>near the baseline</b> — no obvious lift or drop.' },
    { k: ['qt', 'qtc'], a: 'The <b>QT</b> covers ventricular electrical activation through recovery (QRS start → T end) — so it stretches when the heart is slow and shortens when fast (that’s why we "rate-correct" it as QTc). When it matters is a later module.' },
    { k: ['r wave progression', 'v6', 'precordial'], a: 'Across V1→V6 the <b>R wave grows and the S shrinks</b>; the "transition" (where R first becomes taller than S) is <b>often around V3–V4</b> in a typical tracing.' },
    { k: ['tall', 'spike', 'big', 'height', 'so high', 'why big'], a: 'The tall sharp spike is the <b>QRS</b> — the thick ventricles activate quickly, so it’s big. Height = voltage (10 mm tall = 1 mV); we read it in boxes.' },
    { k: ['upside down', 'inverted', 'v1', 'flipped'], a: 'Some leads are normally "down": the P/QRS/T are usually inverted in <b>aVR</b>, and the T can normally be flat or slightly inverted in <b>V1</b>. Those are the expected exceptions to "the T follows the QRS."' },
    { k: ['baseline', 'flat line', 'tp'], a: 'The flat stretch between beats is the <b>baseline</b> (the TP segment) — your reference line. We judge whether the ST sits level with it.' }
  ];
  function localAnswer(q) {
    var s = q.toLowerCase();
    // Defer CLINICAL questions FIRST (incl. "what does a WIDE QRS mean?"), but let
    // foundational "what does the P wave mean / represent" fall through to the KB.
    if (isClinical(s)) return clinicalDeflect(s);
    for (var i = 0; i < KB.length; i++) { for (var j = 0; j < KB[i].k.length; j++) { if (s.indexOf(KB[i].k[j]) >= 0) return KB[i].a; } }
    return 'I can help with anything we’ve covered so far — the waves (P/QRS/T), the grid and boxes, rate, rhythm/sinus, intervals, axis, or R-wave progression. Try naming a part of the trace, or ask "what is the …".';
  }
  function scopeFooter() { return ''; }

  function nudge(html) {
    var t = el('div', 'toast', html); document.body.appendChild(t);
    requestAnimationFrame(function () { t.classList.add('in'); });
    setTimeout(function () { t.classList.remove('in'); setTimeout(function () { t.remove(); }, 300); }, 2600);
  }

  // ---- Meaning-based grading ----------------------------------------------
  // Concept matchers decide whether the learner's text DESCRIBES a concept, using
  // word-ish token presence (not blind substring), numeric ranges (bare "75"/"110"
  // /"210" work), negation guards ("not wide" ≠ wide), and concept-scoping so bare
  // words can't bleed across concepts in a multi-finding one-liner. `strict` is set
  // when grading a multi-concept answer (the blank read) to require the component noun.
  var CLABEL = {
    sinus: 'sinus rhythm', regular: 'regular', irregular: 'irregular', tachy: 'fast rate (tachycardia)', brady: 'slow rate (bradycardia)',
    normal_rate: 'normal rate', normal_pr: 'normal PR', long_pr: 'long PR', normal_qrs: 'narrow QRS', wide_qrs: 'wide QRS',
    normal_axis: 'normal axis', left_axis: 'left axis', right_axis: 'right axis', flat_st: 'ST near baseline', upright_t: 'T normal-appearing'
  };
  // A named diagnosis is out of scope, but if it IMPLIES a required descriptive finding we credit ONLY that finding.
  var DIAG_IMPLIES = { 'lbbb': 'wide_qrs', 'left bundle': 'wide_qrs', 'rbbb': 'wide_qrs', 'right bundle': 'wide_qrs', 'bundle branch': 'wide_qrs', 'first degree': 'long_pr', 'first-degree': 'long_pr', '1st degree': 'long_pr' };
  var UNCERTAIN = /not assess|can.?t assess|cannot assess|not clear|unclear|too noisy|not visible|can.?t tell|cant tell|unsure|hard to tell/;
  var AHEAD = ['first degree', 'first-degree', 'av block', 'heart block', 'lbbb', 'rbbb', 'bundle branch', 'stemi', 'ischemia', 'ischaemia', 'infarct', 'wpw', 'lvh', 'hypertroph', 'wellens'];
  // A one-line rule appended to feedback when a concept is missed — every miss teaches something.
  var RULES = {
    wide_qrs: 'QRS is wide at ≥120 ms (≥3 small boxes) — measure first deflection to the final return to baseline.',
    normal_qrs: 'A narrow QRS is under 120 ms (under 3 small boxes).',
    long_pr: 'PR is long over 200 ms (>5 small boxes) — measured start of P to start of QRS.',
    left_axis: 'Left axis in these teaching cases: lead I is up and aVF is clearly down. Borderline leftward cases are refined later.',
    right_axis: 'Right axis: lead I down and aVF up.',
    normal_axis: 'Normal quick check: lead I and aVF both mostly up.',
    tachy: 'Fast rate (tachycardia) is over 100 bpm.',
    brady: 'Slow rate (bradycardia) is under 60 bpm.',
    sinus: 'Sinus pattern: an upright P (in II) before every QRS, same shape, steady PR.',
    flat_st: 'ST is judged against the baseline — near-baseline is normal-appearing.'
  };

  function norm(s) { return ' ' + s.toLowerCase().replace(/n['’]t/g, ' not').replace(/[^a-z0-9<> ]+/g, ' ').replace(/\s+/g, ' ') + ' '; }
  function nums(s) {
    var m = [], bx;
    // box-unit answers → ms (the module teaches in boxes): small box 40 ms, big box 200 ms.
    var reBig = /(\d+(?:\.\d+)?)\s*big\s*box(?:es)?/g;
    while ((bx = reBig.exec(s))) m.push(Math.round(parseFloat(bx[1]) * 200));
    var sNoBig = s.replace(reBig, '  ');                  // strip big-box hits so they aren't re-counted as small
    var reSm = /(\d+(?:\.\d+)?)\s*(?:small\s*)?box(?:es)?/g;
    while ((bx = reSm.exec(sNoBig))) m.push(Math.round(parseFloat(bx[1]) * 40));
    if (/(?:\bone|\ba|\b1)\s*big\s*box/.test(s)) m.push(200);
    // bare 2–3 digit numbers (ms / bpm)
    (s.match(/\d{2,3}/g) || []).forEach(function (x) { m.push(Number(x)); });
    // decimal seconds: "0.14 s" -> 140 ms
    var d = s.match(/\d\.\d+/g); if (d) d.forEach(function (x) { var v = parseFloat(x); if (v < 2) m.push(Math.round(v * 1000)); });
    return m;
  }
  // Comparator-aware: "under/over/less than/more than" nudges a boundary value by 1, so
  // "QRS under 3 boxes" (120) reads as narrow and "PR over 200" / "over 5 boxes" reads as long.
  function adjNums(t, ns) {
    if (!ns.length) return ns;
    var lt = /\b(under|below|less than|fewer than|just under|up to|<)\b/.test(t);
    var gt = /\b(over|above|more than|greater than|just over|exceeds?|at least|>)\b/.test(t);
    if (lt && !gt) return ns.map(function (n) { return n - 1; });
    if (gt && !lt) return ns.map(function (n) { return n + 1; });
    return ns;
  }
  function inRange(ns, lo, hi) { return ns.some(function (x) { return x >= lo && x <= hi; }); }
  // negation in the ~22 chars before a hit
  function negBefore(t, i) { return /\b(no|not|non|without|isn|aren|wasn|never|rule out|ruled out)\b/.test(t.slice(Math.max(0, i - 22), i)); }
  function has(t, phrase) { var from = 0, i; while ((i = t.indexOf(phrase, from)) >= 0) { if (!negBefore(t, i)) return true; from = i + 1; } return false; }
  function anyHas(t, arr) { for (var i = 0; i < arr.length; i++) if (has(t, arr[i])) return true; return false; }
  // whole-word match (t is space-normalized + padded) — for short/ambiguous tokens
  // like "ok"/"up"/"fine" that must NOT bleed into "looks"/"upright"/"defined".
  function wbHas(t, arr) { for (var i = 0; i < arr.length; i++) { var idx = t.indexOf(' ' + arr[i] + ' '); if (idx >= 0 && !negBefore(t, idx + 1)) return true; } return false; }
  function word(t, w) { return w.length <= 2 ? t.indexOf(' ' + w + ' ') >= 0 : t.indexOf(' ' + w) >= 0; }
  function rateCtx(t) { return word(t, 'rate') || word(t, 'bpm') || word(t, 'hr') || word(t, 'heart rate'); }
  function prCtx(t) { return word(t, 'pr'); }
  function qrsCtx(t) { return word(t, 'qrs') || word(t, 'complex'); }
  function axisCtx(t) { return word(t, 'axis'); }
  function stCtx(t) { return word(t, 'st') || word(t, 'segment'); }
  function tCtx(t) { return word(t, 't wave') || word(t, 'twave') || t.indexOf(' t ') >= 0; }

  function matchConcept(c, t, ns, strict) {
    switch (c) {
      case 'sinus': return anyHas(t, ['sinus', 'nsr']) || (word(t, 'p') && has(t, 'before') && qrsCtx(t));
      case 'regular': if (/irregular/.test(t)) return false; return anyHas(t, ['regular', 'evenly', 'even spac', 'steady']);
      case 'irregular': return anyHas(t, ['irregular', 'uneven', 'varying', 'variable']);
      case 'tachy': if (wbHas(t, ['normal', 'slow', 'brady'])) return inRange(ns, 101, 300); return anyHas(t, ['tachy', 'fast', 'rapid']) || (rateCtx(t) && wbHas(t, ['high', 'elevated'])) || inRange(ns, 101, 300);
      case 'brady': if (wbHas(t, ['normal', 'fast', 'tachy'])) return inRange(ns, 20, 59); return anyHas(t, ['brady', 'slow']) || (rateCtx(t) && wbHas(t, ['low'])) || inRange(ns, 20, 59);
      case 'normal_rate': if (wbHas(t, ['slow', 'fast']) || anyHas(t, ['tachy', 'brady'])) return inRange(ns, 60, 100); return anyHas(t, ['normal rate', 'rate normal']) || inRange(ns, 60, 100) || (rateCtx(t) && wbHas(t, ['normal', 'fine', 'ok', 'wnl', 'unremarkable'])) || (!strict && wbHas(t, ['normal', 'fine', 'ok', 'wnl', 'unremarkable']));
      case 'long_pr': return anyHas(t, ['long pr', 'prolonged pr', 'long-ish pr', 'longish pr']) || (prCtx(t) && anyHas(t, ['long', 'prolong'])) || (prCtx(t) && inRange(ns, 201, 460));
      case 'normal_pr': return anyHas(t, ['normal pr', 'pr normal']) || (prCtx(t) && wbHas(t, ['normal', 'fine', 'ok'])) || (prCtx(t) && inRange(ns, 110, 200)) || (!strict && wbHas(t, ['normal', 'fine', 'ok']));
      case 'normal_qrs': return wbHas(t, ['narrow']) || anyHas(t, ['normal qrs', 'qrs normal']) || (qrsCtx(t) && wbHas(t, ['normal', 'fine'])) || (qrsCtx(t) && inRange(ns, 40, 119)) || (!strict && false);
      case 'wide_qrs':
        if (prCtx(t) && !qrsCtx(t)) return false; // "wide PR" must not credit wide QRS
        return anyHas(t, ['wide complex', 'wide-complex', 'broad complex']) || (qrsCtx(t) && (anyHas(t, ['wide', 'broad', 'widened']) || inRange(ns, 120, 400))) || (!prCtx(t) && anyHas(t, ['wide', 'broad', 'widened']));
      case 'normal_axis': if (anyHas(t, ['left axis', 'right axis', 'lad', 'rad', 'deviat'])) return false; return anyHas(t, ['normal axis', 'axis normal']) || (axisCtx(t) && wbHas(t, ['normal', 'fine'])) || (word(t, 'i') && word(t, 'avf') && wbHas(t, ['up', 'positive'])) || (!strict && anyHas(t, ['down and left', 'down-left'])) || (!strict && axisCtx(t) === false && wbHas(t, ['normal', 'fine']));
      case 'left_axis': return anyHas(t, ['left axis', 'lad', 'leftward', 'axis left', 'left deviation']) || (axisCtx(t) && word(t, 'left')) || (axisCtx(t) && anyHas(t, ['deviated', 'borderline'])) || (word(t, 'avf') && anyHas(t, ['down', 'negative', 'inverted']));
      case 'right_axis': return anyHas(t, ['right axis', 'rad', 'rightward', 'axis right', 'right deviation']) || (axisCtx(t) && word(t, 'right'));
      case 'flat_st':
        if (anyHas(t, ['elevat', 'depress', 'abnormal', 'off baseline', 'st change', 'st elev', 'st depress'])) return false;
        return anyHas(t, ['flat st', 'st flat', 'st normal', 'normal st', 'st fine', 'st ok', 'no st', 'st at baseline', 'not elevat', 'no elevat', 'not depress', 'no depress', 'st iso', 'iso st']) || (stCtx(t) && wbHas(t, ['flat', 'isoelectric', 'iso', 'baseline', 'normal', 'fine', 'ok'])) || (!strict && wbHas(t, ['flat', 'isoelectric']));
      case 'upright_t':
        if (anyHas(t, ['inverted', 'invert', 'flipped', 'abnormal', 'biphasic'])) return false;
        return anyHas(t, ['upright t', 't upright']) || (tCtx(t) && wbHas(t, ['upright', 'up', 'normal']));
    }
    return false;
  }

  // expected = array of concept keys; returns {score, got:[], missed:[], ahead:bool, message}
  function grade(userText, expected, labels) {
    var lw = (userText || '').toLowerCase();
    var t = norm(userText || ''), ns = adjNums(lw, nums(' ' + lw + ' ')), strict = expected.length > 1; // nums from raw so "0.14 s" survives norm(); comparator-adjusted
    var got = [], missed = [];
    expected.forEach(function (c) { (matchConcept(c, t, ns, strict) ? got : missed).push(c); });
    var ahead = AHEAD.some(function (a) { return has(t, a); });
    labels = labels || {};
    var nice = function (c) { return labels[c] || CLABEL[c] || c.replace(/_/g, ' '); };
    // Conditional ahead-credit: a named diagnosis credits ONLY the descriptive finding it implies,
    // and only if that finding was expected here. Naming an unrelated diagnosis earns no credit.
    var implied = null;
    if (ahead) {
      for (var dx in DIAG_IMPLIES) {
        var concept = DIAG_IMPLIES[dx], mi = missed.indexOf(concept);
        if (mi >= 0 && has(t, dx)) { got.push(concept); missed.splice(mi, 1); implied = concept; break; }
      }
    }
    var score = expected.length ? got.length / expected.length : 1;
    var msg;
    if (!got.length && !userText.trim()) msg = 'Have a go — even a rough description. Look for: <b>' + missed.map(nice).join(', ') + '</b>.';
    else if (got.length === expected.length) msg = 'Spot on — you described ' + got.map(nice).join(', ') + '.';
    else if (got.length) msg = 'Good — you got <b>' + got.map(nice).join(', ') + '</b>. Now re-check the trace for: <b>' + missed.map(nice).join(', ') + '</b>.';
    else msg = 'Let’s reason it back on the trace — look for <b>' + missed.map(nice).join(', ') + '</b> (count the boxes / check lead I &amp; aVF).';
    // Every miss leaves a durable rule behind.
    var rule = missed.map(function (c) { return RULES[c]; }).filter(Boolean)[0];
    if (rule && got.length !== expected.length) msg += ' <span class="sec">' + rule + '</span>';
    if (implied) msg += ' <span class="sec">You named a possible diagnosis — I credited only the descriptive part it implies (<b>' + nice(implied) + '</b>); the label and causes come later.</span>';
    else if (ahead) msg += ' <span class="sec">(You named a possible diagnosis — in Foundations we just describe the finding; the label comes later.)</span>';
    if (!got.length && UNCERTAIN.test((userText || '').toLowerCase())) msg = 'Good instinct to flag uncertainty — but on this teaching tracing it’s readable. ' + msg;
    return { score: score, got: got, missed: missed, ahead: ahead, message: msg };
  }

  // ---- Normal-values card --------------------------------------------------
  var NV = [
    { key: 'boxes', label: 'Grid', val: '1 small box = 40 ms wide / 0.1 mV tall · 5 small = 1 big = 200 ms' },
    { key: 'rate', label: 'Rate', val: '60–100 normal · <60 slow · >100 fast (300 ÷ big boxes, if regular)' },
    { key: 'pr', label: 'PR interval', val: 'start of P → start of QRS · 120–200 ms (3–5 small boxes)' },
    { key: 'qrs', label: 'QRS duration', val: '<120 ms = narrow · ≥120 ms = wide' },
    { key: 'st', label: 'ST segment', val: 'near the baseline; an obvious lift or drop is noted (for later)' },
    { key: 't', label: 'T wave', val: 'usually follows the main QRS direction (aVR & V1 are common exceptions)' },
    { key: 'qt', label: 'QT / QTc', val: 'start of QRS → end of T; scales with rate (rate-corrected = QTc)' },
    { key: 'rwave', label: 'R-wave progression', val: 'R grows / S shrinks V1→V6; transition (R>S) often ~ V3–V4' },
    { key: 'axis', label: 'Axis', val: 'I & aVF both up = normal · clear left/right deviations named in the axis step' }
  ];
  var revealed = {};
  function nvReveal(keys) { (keys || []).forEach(function (k) { revealed[k] = true; }); renderNV(); }
  function renderNV() {
    var box = document.getElementById('nvBody'); if (!box) return;
    box.innerHTML = NV.map(function (r) {
      var on = revealed[r.key];
      return '<div class="nv-row ' + (on ? 'on' : 'off') + '"><span class="nv-label">' + r.label + '</span>' +
        '<span class="nv-val">' + (on ? r.val : '<span class="nv-lock">unlocked as you learn it</span>') + '</span></div>';
    }).join('');
    var btn = document.getElementById('nvBtn'); if (btn) btn.textContent = '📋 Normal values (' + Object.keys(revealed).length + '/' + NV.length + ')';
  }
  function nvState() { return revealed; }
  function nvLoad(obj) { revealed = obj || {}; renderNV(); }

  global.Tutor = {
    mount: mount, setScope: setScope, clear: clear, say: say, you: you, choices: choices,
    askAnything: askAnything, nudge: nudge, grade: grade, matchConcept: matchConcept, CLABEL: CLABEL
  };
  global.NVCard = { reveal: nvReveal, render: renderNV, state: nvState, load: nvLoad, list: NV };
  function escapeHtml(s) { return s.replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
})(window);
