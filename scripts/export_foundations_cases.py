"""Export a curated set of real PTB-XL cases for the Foundations module.

Pulls, from data/ecg_corpus/corpus.db, representative cases across the teaching
categories (normal / brady / tachy / non-sinus / long-PR / wide-QRS / left-axis /
right-axis / noisy), each with its real 12-lead MEDIAN BEAT (mV) and the real 12SL computed
features (rate, PR, QRS, QT, axis, per-lead ST) as ground truth. Writes
``frontend/public/foundations/data/cases.json`` — the static module loads this and renders/scores
against real data. Run: python scripts/export_foundations_cases.py
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sqlite3

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "ecg_corpus" / "corpus.db"
OUT = ROOT / "foundations" / "data" / "cases.json"
LEADS = ["I","II","III","aVR","aVL","aVF","V1","V2","V3","V4","V5","V6"]
SOURCE_VERSION = "1.0.3"
LICENSE_ID = "CC-BY-4.0"

con = sqlite3.connect(DB); cur = con.cursor()

def wf_path(ecg_id):
    ecg_id = int(ecg_id)
    folder = f"{(ecg_id // 1000) * 1000:05d}"
    return ROOT / "data" / "ecg_corpus" / "waveforms" / folder / f"{ecg_id:05d}.npy"

def has_concept(ecg_id, concept, tiers=("A", "B")):
    r = cur.execute("select tier from case_concepts where ecg_id=? and concept_id=?", (ecg_id, concept)).fetchone()
    return bool(r) and r[0] in tiers

def lead_ii_strip(ecg_id, seconds=6, step=2):
    """Real lead-II strip (downsampled) in mV for rhythm/quality scenes."""
    try:
        a = np.load(wf_path(ecg_id)).astype(float) / 1000.0  # int16 uV -> mV
    except Exception:
        return None
    ii = a[:, LEADS.index("II")]
    n = min(len(ii), int(seconds * 100))
    return [round(float(v), 3) for v in ii[:n:step]]

def candidate_ids(concept, tiers, limit=400):
    q = "select ecg_id from case_concepts where concept_id=? and tier in (%s) order by score desc limit ?" % (
        ",".join("?" * len(tiers)))
    return [r[0] for r in cur.execute(q, (concept, *tiers, limit)).fetchall()]

_BAD_RHYTHM = ("premature_ventricular_complex", "premature_atrial_complex", "atrial_fibrillation",
               "atrial_flutter", "supraventricular_tachycardia", "wide_complex_tachycardia", "paced_rhythm")
_ST_ABN = ("st_elevation", "st_depression", "t_wave_inversion")

def case_flags(ecg_id):
    """sinus = confirmed sinus rhythm with no ectopy/AF; st_normal = no ST/T abnormality
    concept. Lets caseTruth assert sinus + flat-ST only where the data supports it."""
    sinus = has_concept(ecg_id, "sinus_rhythm", ("A", "B")) and not any(has_concept(ecg_id, c, ("A",)) for c in _BAD_RHYTHM)
    st_normal = not any(has_concept(ecg_id, c, ("A", "B")) for c in _ST_ABN)
    return sinus, st_normal

def load(ecg_id):
    row = cur.execute("select report, signal_status, packet_json from cases where ecg_id=?", (ecg_id,)).fetchone()
    if not row:
        return None
    report, status, pj = row[0], row[1], json.loads(row[2])
    plus = pj.get("ptbxl_plus", {})
    feats = plus.get("measurements") or plus.get("features") or {}
    mb = plus.get("median_beats") or {}
    if not mb.get("available") or not mb.get("beats"):
        return None
    beats = {l: [round(float(x), 4) for x in mb["beats"].get(l, [])] for l in LEADS}
    if any(len(beats[l]) < 30 for l in LEADS):
        return None
    sinus, st_normal = case_flags(ecg_id)
    return {"ecg_id": ecg_id, "report": report, "signal_status": status,
            "features": feats, "median_fs": mb.get("samplingFrequency", 100),
            "median": beats, "sinus": sinus, "st_normal": st_normal}

def feat(c, k):
    v = c["features"].get(k)
    return None if v is None else float(v)

# category -> (concept, tiers, predicate(case)->bool, want)
def normal_ok(c):
    r, pr, qrs, ax = feat(c, "heart_rate"), feat(c, "pr_ms"), feat(c, "qrs_ms"), feat(c, "axis_deg")
    return (r and 55 <= r <= 95) and (pr and 120 <= pr <= 200) and (qrs and qrs < 105) and (ax is not None and -30 <= ax <= 90) and c["signal_status"] != "unreadable"

CATS = [
    ("normal",     "normal_ecg",              ("A",),      normal_ok, 4),
    ("brady",      "bradycardia",             ("A", "B"),  lambda c: (feat(c,"heart_rate") or 99) < 58 and has_concept(c["ecg_id"],"sinus_rhythm") and c["signal_status"]!="poor", 2),
    ("tachy",      "sinus_rhythm",            ("A", "B"),  lambda c: (feat(c,"heart_rate") or 0) > 100 and c["signal_status"]!="poor", 3),
    ("non_sinus",  "atrial_fibrillation",     ("A",),      lambda c: not c["sinus"] and c["signal_status"]!="poor", 2),
    ("long_pr",    "av_block_first_degree",   ("A",),      lambda c: (feat(c,"pr_ms") or 0) > 210 and (feat(c,"qrs_ms") or 999) < 120 and c["signal_status"]!="poor", 3),
    ("wide_qrs",   "left_bundle_branch_block",("B",),      lambda c: (feat(c,"qrs_ms") or 0) >= 130 and c["signal_status"]!="poor", 2),
    ("wide_qrs",   "right_bundle_branch_block",("B",),     lambda c: (feat(c,"qrs_ms") or 0) >= 130 and c["signal_status"]!="poor", 2),
    ("left_axis",  "left_axis_deviation",     ("A",),      lambda c: (feat(c,"axis_deg") if feat(c,"axis_deg") is not None else 0) < -30 and c["signal_status"]!="poor", 2),
    ("right_axis", "right_axis_deviation",    ("A",),      lambda c: 100 <= (feat(c,"axis_deg") or 0) <= 179 and (feat(c,"qrs_ms") or 999) < 120 and c["signal_status"]!="poor", 2),
    ("noisy",      None,                       None,       None, 2),
]

selected, seen = [], set()
for name, concept, tiers, pred, want in CATS:
    if name == "noisy":
        # unreadable signals have no median beat — use the raw lead-II strip directly.
        ids = [r[0] for r in cur.execute("select ecg_id, report from cases where signal_status='poor' limit 120").fetchall()]
        got = 0
        for eid in ids:
            if eid in seen: continue
            strip = lead_ii_strip(eid)
            if not strip: continue
            rep = cur.execute("select report from cases where ecg_id=?", (eid,)).fetchone()[0]
            selected.append({"ecg_id": int(eid), "category": "noisy", "report": rep or "",
                             "signal_status": "poor", "median_fs": 100, "features": {},
                             "median": {}, "lead_ii": strip}); seen.add(eid); got += 1
            if got >= want: break
        print(f"{'noisy':10s}: requested {want}, got {got}")
        continue
    got = 0
    for eid in candidate_ids(concept, tiers):
        if eid in seen: continue
        c = load(eid)
        if not c or not pred(c): continue
        if name != "non_sinus" and not c["sinus"]: continue
        c["category"] = name
        if name in ("tachy", "brady", "normal", "non_sinus"):
            c["lead_ii"] = lead_ii_strip(eid)  # real rhythm strip for rate/regularity/quality
        selected.append(c); seen.add(eid); got += 1
        if got >= want: break
    print(f"{name:10s}: requested {want}, got {got}")

# keep median beats only for the leads, slim features to what the app uses
KEEP_FEATS = ["heart_rate","pr_ms","qrs_ms","qt_ms","qtc_ms","axis_deg","p_axis_deg","t_axis_deg",
              "st_elev_I_mv","st_elev_II_mv","st_elev_V1_mv","st_elev_V2_mv","st_elev_V5_mv","st_elev_V6_mv"]
out = []
for c in selected:
    rec = {
        "ecg_id": c["ecg_id"], "category": c["category"], "report": c["report"],
        "source": "ptbxl", "source_version": SOURCE_VERSION, "license_id": LICENSE_ID,
        "signal_status": c["signal_status"], "median_fs": c["median_fs"],
        "sinus": c.get("sinus", None), "st_normal": c.get("st_normal", None),
        "features": {k: c["features"].get(k) for k in KEEP_FEATS if c["features"].get(k) is not None},
        "median": c["median"],
    }
    if c.get("lead_ii"):
        rec["lead_ii"] = c["lead_ii"]
    out.append(rec)

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", encoding="utf-8") as f:
    json.dump({"leads": LEADS, "cases": out}, f, separators=(",", ":"))
con.close()
sz = OUT.stat().st_size / 1024
print(f"\nWrote {len(out)} cases to {OUT} ({sz:.0f} KB)")
print("by category:", dict(Counter(c["category"] for c in out)))
for c in out[:30]:
    fe = c["features"]
    print("  ecg %5s %-10s rate=%s pr=%s qrs=%s axis=%s [%s]" % (
        c["ecg_id"], c["category"], fe.get("heart_rate"), fe.get("pr_ms"), fe.get("qrs_ms"), fe.get("axis_deg"), (c["report"] or "")[:38]))
