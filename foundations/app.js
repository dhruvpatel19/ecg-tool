/* app.js — Foundations shell: routing, progress, resume, per-scene + per-part
 * test-out. Mounts each scene from SCENES and wires the ctx it needs.
 */
(function (global) {
  'use strict';
  var SCENES = global.SCENES, T = global.Tutor, NV = global.NVCard;
  var PARTS = ['What am I looking at?', 'Measure one beat', 'One lead → twelve', 'The systematic read'];
  var owner = new URLSearchParams(window.location.search).get('owner') || 'guest';
  owner = /^[A-Za-z0-9_-]{1,80}$/.test(owner) ? owner : 'guest';
  var KEY = 'foundations_state_v1:' + owner;
  var BEST_KEY = 'found_best:' + owner;
  global.FOUNDATIONS_BEST_KEY = BEST_KEY;

  var state = load() || { completed: {}, current: 0, nv: {}, skipped: {}, testedOut: {} };
  state.completed = state.completed || {};
  state.skipped = state.skipped || {};
  state.testedOut = state.testedOut || {};
  // v1 incorrectly counted skipped scenes as completed. Migrate that persisted state
  // so "review later" never masquerades as completion or mastery.
  Object.keys(state.skipped).forEach(function (sceneId) { delete state.completed[sceneId]; });
  var idx = state.current || 0;
  var curCtx = null;
  var evidenceSeq = 0;
  var evidenceSession = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);

  function load() { try { return JSON.parse(localStorage.getItem(KEY)); } catch (e) { return null; } }
  function save() { state.current = idx; state.nv = NV.state(); localStorage.setItem(KEY, JSON.stringify(state)); emit('progress', progressDetail()); maybeComplete(); }

  // --- telemetry bridge --------------------------------------------------------
  // When embedded in the host app (iframe), report progress to the parent via
  // postMessage; standalone (top-level) it no-ops. This is the durable contract a
  // future React port re-emits unchanged (see frontend/src/lib/progress.ts).
  function emit(type, detail) {
    if (window.self === window.top) return;
    try { window.parent.postMessage(Object.assign({ source: 'foundations', type: type }, detail || {}), window.location.origin); } catch (e) {}
  }
  function progressDetail() {
    var total = SCENES.length, done = Object.keys(state.completed).length, cur = SCENES[idx] || {};
    return {
      completedScenes: done,
      skippedScenes: Object.keys(state.skipped).length,
      totalScenes: total,
      currentIndex: idx,
      currentId: cur.id || null,
      part: cur.part || null,
      done: done >= total,
      bestAccuracy: +(localStorage.getItem(BEST_KEY) || 0),
      stateSnapshot: {
        completed: Object.keys(state.completed),
        skipped: Object.keys(state.skipped),
        current: idx,
        bestAccuracy: +(localStorage.getItem(BEST_KEY) || 0),
        nv: state.nv || {},
        testedOut: state.testedOut || {}
      }
    };
  }
  function evidenceDetail(sc, detail) {
    detail = detail || {}; evidenceSeq++;
    return {
      eventId: evidenceSession + ':' + sc.id + ':' + (detail.interactionId || 'checkpoint') + ':' + evidenceSeq,
      sceneId: sc.id,
      interactionId: detail.interactionId || (sc.id.toLowerCase() + '-checkpoint'),
      concept: detail.concept || 'ecg_foundations',
      subskills: detail.subskills || ['recognize'],
      score: typeof detail.score === 'number' ? Math.max(0, Math.min(1, detail.score)) : (detail.correct ? 1 : 0),
      correct: !!detail.correct,
      attempts: Math.max(1, detail.attempts || 1),
      assistance: detail.assistance === 'scaffolded' ? 'scaffolded' : 'independent',
      hintsUsed: Math.max(0, detail.hintsUsed || 0),
      evidenceLevel: 'guided',
      caseId: detail.caseId == null ? null : String(detail.caseId),
      caseProvenance: detail.caseProvenance || 'authored_simulation',
      caseEligible: !!detail.caseEligible,
      misconceptions: detail.misconceptions || []
    };
  }
  var _completeEmitted = false;
  function maybeComplete() { if (!_completeEmitted && Object.keys(state.completed).length >= SCENES.length) { _completeEmitted = true; emit('complete', progressDetail()); } }

  function partOf(i) { return SCENES[i].part; }
  function scenesInPart(part) { return SCENES.filter(function (s) { return s.part === part; }); }
  function sceneNumInPart(i) { var p = SCENES[i].part, n = 0; for (var k = 0; k <= i; k++) if (SCENES[k].part === p) n++; return n; }

  function renderChrome() {
    document.getElementById('partRail').innerHTML = PARTS.map(function (p, i) {
      var part = i + 1;
      var sc = scenesInPart(part), doneCt = sc.filter(function (s) { return state.completed[s.id]; }).length;
      var skippedCt = sc.filter(function (s) { return state.skipped[s.id]; }).length;
      var cls = partOf(idx) === part ? 'on' : (doneCt === sc.length ? 'done' : '');
      return '<button class="prail-part ' + cls + '" data-part="' + part + '">' +
        '<span class="prail-n">' + part + '</span><span class="prail-l">' + p + '</span>' +
        '<span class="prail-prog">' + doneCt + '/' + sc.length + (skippedCt ? ' · ' + skippedCt + ' later' : '') + '</span></button>';
    }).join('');
    document.querySelectorAll('.prail-part').forEach(function (b) {
      b.onclick = function () { partMenu(+b.getAttribute('data-part')); };
    });
    NV.render();
  }

  function mount() {
    if (curCtx && curCtx._cleanup) curCtx._cleanup();
    var sc = SCENES[idx];
    var root = document.getElementById('sceneRoot'); root.innerHTML = '';
    document.getElementById('scTitle').textContent = sc.title;
    document.getElementById('scSub').textContent = sc.sub;
    document.getElementById('scMeta').textContent = 'Part ' + sc.part + '/4 · scene ' + sceneNumInPart(idx) + '/' + scenesInPart(sc.part).length + (state.skipped[sc.id] ? ' · review later' : '');
    document.getElementById('scId').textContent = sc.id;
    var pct = Math.round(Object.keys(state.completed).length / SCENES.length * 100);
    document.getElementById('progFill').style.width = pct + '%';
    var skippedTotal = Object.keys(state.skipped).length;
    document.getElementById('progPct').textContent = pct + '%' + (skippedTotal ? ' · ' + skippedTotal + ' review' : '');

    var doneAlready = !!state.completed[sc.id];
    var canMovePast = doneAlready || !!state.skipped[sc.id];
    curCtx = {
      scene: sc, _cleanup: null,
      complete: function () { state.completed[sc.id] = true; delete state.skipped[sc.id]; save(); renderChrome(); enableNext(true); },
      evidence: function (detail) { emit('learning-evidence', evidenceDetail(sc, detail)); },
      goNext: next
    };
    enableNext(canMovePast);
    sc.mount(root, curCtx);
    if (doneAlready) enableNext(true);
    renderChrome(); save();
    document.getElementById('sceneScroll').scrollTop = 0;
    // per-scene skip / test-out
    document.getElementById('skipScene').onclick = function () {
      delete state.completed[sc.id]; state.skipped[sc.id] = true; save(); next();
    };
    window.scrollTo(0, 0);
  }

  function enableNext(on) {
    var n = document.getElementById('btnNext');
    n.disabled = !on;
    n.title = on ? '' : 'Finish this scene’s checkpoint to continue (or use “skip”).';
  }
  function next() { if (idx < SCENES.length - 1) { idx++; mount(); } }
  function prev() { if (idx > 0) { idx--; mount(); } }

  // --- per-part test-out menu + quiz ---------------------------------------
  var TESTOUT = {
    1: { q: 'A small box on ECG paper is how much time?', opts: [['40 ms', true], ['200 ms', false], ['1 second', false]] },
    2: { q: 'A slow rate, with an upright same-shaped P before every QRS and a steady PR. Sinus pattern?', opts: [['Yes — sinus pattern (just a slow rate)', true], ['No — too slow to be sinus', false]] },
    3: { q: 'Lead I points up but aVF points down. The axis is:', opts: [['Leftward — left axis if clearly past normal', true], ['Normal', false], ['Right axis', false]] },
    4: { q: 'What’s the first step of the systematic sweep?', opts: [['Rate', true], ['ST-T', false], ['Axis', false]] }
  };
  function partMenu(part) {
    var sc = scenesInPart(part);
    var allDone = sc.every(function (s) { return state.completed[s.id]; });
    var firstIdx = SCENES.indexOf(sc[0]);
    modal('Part ' + part + ' — ' + PARTS[part - 1],
      '<p class="sec">' + sc.length + ' scenes · ' + sc.filter(function (s) { return state.completed[s.id]; }).length + ' done.</p>',
      [
        { label: 'Go to start of this part', cls: 'accent', go: function () { idx = firstIdx; closeModal(); mount(); } },
        { label: allDone ? 'Already complete' : 'Placement check (does not count as mastery)', go: function () { allDone ? closeModal() : testOut(part); } }
      ]);
  }
  function testOut(part) {
    var t = TESTOUT[part];
    var body = '<p>' + t.q + '</p><div class="modal-opts">' + t.opts.map(function (o, i) { return '<button data-i="' + i + '">' + o[0] + '</button>'; }).join('') + '</div><div id="toFb"></div>';
    modal('Test out — Part ' + part, body, [{ label: 'Cancel', go: closeModal }]);
    document.querySelectorAll('.modal-opts button').forEach(function (b) {
      b.onclick = function () {
        var ok = t.opts[+b.getAttribute('data-i')][1];
        if (ok) {
          // A one-item placement check may let a fluent learner move ahead, but it is
          // not enough evidence to mark several scenes complete. Keep every bypassed
          // scene explicitly in "review later" state.
          scenesInPart(part).forEach(function (s) { if (!state.completed[s.id]) state.skipped[s.id] = true; });
          state.testedOut[part] = true;
          // reveal nv keys for skipped parts so the card stays consistent
          if (part >= 1) NV.reveal(['boxes']); if (part >= 2) NV.reveal(['rate', 'pr', 'qrs', 'st', 't', 'qt']); if (part >= 3) NV.reveal(['rwave', 'axis']);
          save();
          document.getElementById('toFb').innerHTML = '<div class="fb ok">Correct — Part ' + part + ' is open. Its scenes stay marked review later until you demonstrate them.</div>';
          var nextPartFirst = SCENES.findIndex(function (s) { return s.part === part + 1; });
          setTimeout(function () { closeModal(); idx = nextPartFirst >= 0 ? nextPartFirst : SCENES.length - 1; mount(); }, 900);
        } else {
          document.getElementById('toFb').innerHTML = '<div class="fb warn">Not quite — best to walk this part. Opening it for you.</div>';
          setTimeout(function () { closeModal(); idx = SCENES.indexOf(scenesInPart(part)[0]); mount(); }, 1100);
        }
      };
    });
  }

  function modal(title, bodyHtml, actions) {
    var m = document.getElementById('modal');
    m.innerHTML = '<div class="modal-box"><div class="modal-h">' + title + '</div><div class="modal-body">' + bodyHtml + '</div><div class="row modal-actions"></div></div>';
    var act = m.querySelector('.modal-actions');
    (actions || []).forEach(function (a) { var b = document.createElement('button'); b.className = a.cls || ''; b.textContent = a.label; b.onclick = a.go; act.appendChild(b); });
    m.hidden = false;
  }
  function closeModal() { document.getElementById('modal').hidden = true; }

  // --- normal-values card toggle -------------------------------------------
  function initNV() {
    NV.load(state.nv || {});
    document.getElementById('nvBtn').onclick = function () { var c = document.getElementById('nvCard'); c.hidden = !c.hidden; };
    document.getElementById('nvClose').onclick = function () { document.getElementById('nvCard').hidden = true; };
  }

  // --- boot ----------------------------------------------------------------
  function boot() {
    T.mount(document.getElementById('tutorStream'), document.getElementById('tutorInput'), document.getElementById('tutorSend'));
    initNV();
    document.getElementById('btnNext').onclick = next;
    document.getElementById('btnPrev').onclick = prev;
    document.getElementById('modal').addEventListener('click', function (e) { if (e.target.id === 'modal') closeModal(); });
    renderChrome();
    emit('ready', progressDetail());
    // Wait for the real case data to load before mounting scenes that render it.
    (global.CASES_READY || Promise.reject(new Error('real PTB teaching bundle loader is missing'))).then(function () {
      if (state.current && state.current > 0) {
        modal('Welcome back', '<p>You left off at <b>' + SCENES[state.current].title + '</b> (' + Object.keys(state.completed).length + '/' + SCENES.length + ' scenes done).</p>',
          [{ label: 'Resume', cls: 'accent', go: function () { closeModal(); mount(); } }, { label: 'Start over', go: function () { state = { completed: {}, current: 0, nv: {}, skipped: {}, testedOut: {} }; idx = 0; NV.load({}); save(); closeModal(); mount(); } }]);
      } else { mount(); }
    }).catch(function (error) {
      document.getElementById('scMeta').textContent = 'Real-data release gate';
      document.getElementById('scTitle').textContent = 'Foundations is temporarily unavailable';
      document.getElementById('scSub').textContent = 'A verified PTB teaching bundle is required';
      document.getElementById('sceneRoot').innerHTML =
        '<div class="warning" role="alert"><b>No simulated ECG will replace missing real data.</b> ' +
        'The verified PTB teaching bundle could not be loaded. Please refresh or contact the course operator.</div>';
      document.getElementById('btnNext').disabled = true;
      document.getElementById('btnPrev').disabled = true;
      try { console.error('Foundations real-data gate:', error); } catch (ignored) {}
    });
  }
  if (document.readyState !== 'loading') boot(); else document.addEventListener('DOMContentLoaded', boot);
})(window);
