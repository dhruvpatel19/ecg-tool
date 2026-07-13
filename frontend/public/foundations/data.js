/* data.js — loads the real PTB-XL case set (foundations/data/cases.json) exported
 * by scripts/export_foundations_cases.py. Exposes window.CASES (+ by-category index
 * and pickCase) and a CASES_READY promise the app awaits before mounting scenes. */
(function (global) {
  'use strict';
  global.CASES = [];
  global.CASES_BY = {};
  global.CASE_LEADS = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6'];
  var REQUIRED_CATEGORIES = ['normal', 'brady', 'tachy', 'non_sinus', 'long_pr', 'wide_qrs', 'left_axis', 'right_axis', 'noisy'];
  global.CASES_READY = fetch('data/cases.json')
    .then(function (r) {
      if (!r.ok) throw new Error('real PTB teaching bundle returned HTTP ' + r.status);
      return r.json();
    })
    .then(function (d) {
      var cases = Array.isArray(d.cases) ? d.cases : [];
      var leads = Array.isArray(d.leads) ? d.leads : [];
      if (leads.length !== 12 || global.CASE_LEADS.some(function (lead) { return leads.indexOf(lead) < 0; })) {
        throw new Error('real PTB teaching bundle has an invalid 12-lead contract');
      }
      if (!cases.length || cases.some(function (c) {
        return !c || c.source !== 'ptbxl' || c.source_version !== '1.0.3' || c.license_id !== 'CC-BY-4.0' || !c.ecg_id;
      })) {
        throw new Error('real PTB teaching bundle has missing or unverified provenance');
      }
      global.CASES = cases;
      global.CASE_LEADS = leads;
      global.CASES.forEach(function (c) { (global.CASES_BY[c.category] = global.CASES_BY[c.category] || []).push(c); });
      var missing = REQUIRED_CATEGORIES.filter(function (category) { return !(global.CASES_BY[category] || []).length; });
      if (missing.length) throw new Error('real PTB teaching bundle is missing: ' + missing.join(', '));
      return d;
    })
    .catch(function (e) {
      global.CASES = [];
      global.CASES_BY = {};
      global.CASES_ERROR = e instanceof Error ? e.message : String(e);
      throw e;
    });
  // pickCase('normal', 0) — nth real case of a category (wraps; null if none).
  global.pickCase = function (cat, i) { var a = global.CASES_BY[cat] || []; return a.length ? a[((i || 0) % a.length + a.length) % a.length] : null; };
})(window);
