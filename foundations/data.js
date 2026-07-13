/* data.js — loads the real PTB-XL case set (foundations/data/cases.json) exported
 * by scripts/export_foundations_cases.py. Exposes window.CASES (+ by-category index
 * and pickCase) and a CASES_READY promise the app awaits before mounting scenes. */
(function (global) {
  'use strict';
  global.CASES = [];
  global.CASES_BY = {};
  global.CASE_LEADS = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6'];
  global.CASES_READY = fetch('data/cases.json')
    .then(function (r) { return r.ok ? r.json() : { cases: [] }; })
    .then(function (d) {
      global.CASES = d.cases || [];
      if (d.leads) global.CASE_LEADS = d.leads;
      global.CASES.forEach(function (c) { (global.CASES_BY[c.category] = global.CASES_BY[c.category] || []).push(c); });
      return d;
    })
    .catch(function (e) { try { console.warn('cases.json load failed — falling back to synthetic', e); } catch (x) {} return { cases: [] }; });
  // pickCase('normal', 0) — nth real case of a category (wraps; null if none).
  global.pickCase = function (cat, i) { var a = global.CASES_BY[cat] || []; return a.length ? a[((i || 0) % a.length + a.length) % a.length] : null; };
})(window);
