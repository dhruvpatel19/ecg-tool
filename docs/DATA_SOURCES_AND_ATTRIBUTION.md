# Data sources and attribution

TRACE uses version-pinned public ECG datasets. This notice applies to dataset
waveforms, annotations, and derived metadata; it is separate from any license
that may be applied to TRACE source code. Preserve this notice, the source
version, and the applicable license link when redistributing exported data or a
deployment that serves source-derived ECGs.

## Versioned source register

| Source | TRACE use | Official dataset and version DOI | File license |
|---|---|---|---|
| PTB-XL 1.0.3 | 10-second 12-lead waveforms, cardiologist-reviewed SCP-ECG statements, reports, and metadata | [PhysioNet dataset](https://physionet.org/content/ptb-xl/1.0.3/) · [version DOI 10.13026/kfzx-aw45](https://doi.org/10.13026/kfzx-aw45) | [CC BY 4.0 on PhysioNet](https://physionet.org/content/ptb-xl/view-license/1.0.3/) · [canonical license](https://creativecommons.org/licenses/by/4.0/) |
| PTB-XL+ 1.0.1 | Algorithm-derived measurements, features, fiducials, median beats, and diagnostic statements joined by PTB-XL ECG identifier | [PhysioNet dataset](https://physionet.org/content/ptb-xl-plus/1.0.1/) · [version DOI 10.13026/g6h6-7g88](https://doi.org/10.13026/g6h6-7g88) | [CC BY 4.0 on PhysioNet](https://physionet.org/content/ptb-xl-plus/view-license/1.0.1/) · [canonical license](https://creativecommons.org/licenses/by/4.0/) |
| Leipzig Heart Center ECG-Database 1.0.0 | Expert-labelled rhythm windows used only in the source-permitted focused Training/Rapid lanes | [PhysioNet dataset](https://physionet.org/content/leipzig-heart-center-ecg/1.0.0/) · [version DOI 10.13026/7a4j-vn37](https://doi.org/10.13026/7a4j-vn37) | [ODC-By 1.0 on PhysioNet](https://physionet.org/content/leipzig-heart-center-ecg/view-license/1.0.0/) · [canonical license](https://opendatacommons.org/licenses/by/1-0/) |
| MIT-BIH Malignant Ventricular Ectopy Database 1.0.0 | Foundation-only, checksum-gated two-channel rhythm windows for a future reviewed resuscitation-rhythm lane; not connected to current student routes or action mastery | [PhysioNet dataset](https://physionet.org/content/vfdb/1.0.0/) · [version DOI 10.13026/C22P44](https://doi.org/10.13026/C22P44) | [ODC-By 1.0 on PhysioNet](https://physionet.org/content/vfdb/view-license/1.0.0/) · [canonical license](https://opendatacommons.org/licenses/by/1-0/) |

PTB-XL and PTB-XL+ are **Creative Commons Attribution 4.0**, not ODC-By.
Leipzig and VFDB remain **Open Data Commons Attribution 1.0**. The executable
source registry uses `CC-BY-4.0` and `ODC-BY-1.0`, respectively.

## Requested citations

1. Wagner P, Strodthoff N, Bousseljot R-D, Samek W, Schaeffter T. *PTB-XL, a
   large publicly available electrocardiography dataset* (version 1.0.3).
   PhysioNet. 2022. RRID:SCR_007345.
   [https://doi.org/10.13026/kfzx-aw45](https://doi.org/10.13026/kfzx-aw45).
   Also cite the original Scientific Data descriptor:
   [https://doi.org/10.1038/s41597-020-0495-6](https://doi.org/10.1038/s41597-020-0495-6).
2. Strodthoff N, Mehari T, Nagel C, et al. *PTB-XL+, a comprehensive
   electrocardiographic feature dataset* (version 1.0.1). PhysioNet. 2023.
   RRID:SCR_007345.
   [https://doi.org/10.13026/g6h6-7g88](https://doi.org/10.13026/g6h6-7g88).
   Also cite the original Scientific Data descriptor:
   [https://doi.org/10.1038/s41597-023-02153-8](https://doi.org/10.1038/s41597-023-02153-8).
3. Klehs S, Franke D, Alhamad B, Gebauer R, Teich L, Teich T, Paech C.
   *Leipzig Heart Center ECG-Database: Arrhythmias in Children and Patients with
   Congenital Heart Disease* (version 1.0.0). PhysioNet. 2025.
   RRID:SCR_007345.
   [https://doi.org/10.13026/7a4j-vn37](https://doi.org/10.13026/7a4j-vn37).
4. Albrecht P, Moody G, Mark R. *MIT-BIH Malignant Ventricular Ectopy
   Database* (version 1.0.0). PhysioNet. 1999. RRID:SCR_007345.
   [https://doi.org/10.13026/C22P44](https://doi.org/10.13026/C22P44).
   Also cite the source-requested Greenwald work shown on the versioned dataset
   page.
5. Goldberger AL, Amaral LAN, Glass L, et al. PhysioBank, PhysioToolkit, and
   PhysioNet: Components of a new research resource for complex physiologic
   signals. *Circulation*. 2000;101(23):e215-e220.
   [https://doi.org/10.1161/01.CIR.101.23.E215](https://doi.org/10.1161/01.CIR.101.23.E215).

## TRACE transformations and separation of claims

- PTB-XL low-resolution signals are converted to compact int16-microvolt arrays;
  packets join PTB-XL+ evidence, normalize fields, and add conservative
  educational curation. TRACE is not endorsed by the dataset authors.
- Leipzig recordings are checksum-verified, restricted to surface leads,
  downsampled from 977 Hz to 100 Hz, and cut into guarded 10-second windows that
  remain inside expert rhythm intervals. These are transformations of the
  source data, not publisher-provided cases.
- VFDB artifacts and its checksum manifest are version-pinned; two-channel
  250 Hz source streams are cut into guarded, non-overlapping 10-second windows
  inside one expert rhythm interval. They remain in a dedicated disconnected
  rhythm store and do not supply pulse, perfusion, arrest state, treatment, or
  action-sequence truth.
- TRACE-authored clinical stems did not occur with the people represented by
  the source ECGs. They are visibly formative teaching context and must not be
  attributed to PTB-XL, PTB-XL+, Leipzig, PhysioNet, or the source authors.
- Source labels and derived measurements remain subject to their documented
  evidence limits. They are not clinical advice, certification, or a claim that
  every possible finding on an ECG was exhaustively annotated.

CC BY 4.0 requires appropriate credit, a license link, and an indication of
changes. ODC-By 1.0 requires attribution for public use of the covered database.
This page records TRACE's intended attribution practice; it is not legal advice.

## Rebuild an installed pre-v2 corpus

Do not repair only `manifest.json`: each stored PTB packet also carries the
versioned license identity. Build a separate manifest-gated corpus, reproduce
the bounded 698-window Leipzig addition, verify it, and only then point the
backend at it:

```powershell
$ptb = $env:PTBXL_DATA_ROOT
$plus = $env:PTBXL_PLUS_DATA_ROOT
$leipzig = $env:LEIPZIG_ECG_DATA_ROOT
if (-not $ptb -or -not $plus -or -not $leipzig) { throw "Set all three verified raw dataset roots first." }

$target = "data/ecg_corpus_license_v2"
$records = @(
  "x0010", "x0013", "x0014", "x0015", "x0017", "x0018", "x0019", "x002",
  "x0020", "x0021", "x0022", "x0023", "x0026", "x0027", "x0028", "x006",
  "x007", "x008", "x100", "x101", "x104", "x105", "x106", "x107", "x108", "x109"
)
$recordArgs = foreach ($record in $records) { "--record"; $record }

$env:PYTHONPATH = "backend"
python scripts/build_corpus.py --ptbxl-root $ptb --plus-root $plus --out $target --limit 0 --rebuild
if ($LASTEXITCODE -ne 0) { throw "PTB corpus rebuild failed." }

python scripts/import_leipzig.py --source-root $leipzig --corpus $target --apply @recordArgs --concept sinus_rhythm --max-per-concept 180
if ($LASTEXITCODE -ne 0) { throw "Bounded Leipzig sinus import failed." }

python scripts/import_leipzig.py --source-root $leipzig --corpus $target --apply @recordArgs --concept atrial_fibrillation --concept paced_rhythm --concept supraventricular_tachycardia --concept wide_complex_tachycardia
if ($LASTEXITCODE -ne 0) { throw "Leipzig pathology import failed." }

$manifest = Get-Content "$target/manifest.json" -Raw | ConvertFrom-Json
if ($manifest.totalCases -ne 22497 -or
    $manifest.sourceCatalog.ptbxl.licenseId -ne "CC-BY-4.0" -or
    $manifest.sourceCatalog.'ptbxl-plus'.licenseId -ne "CC-BY-4.0" -or
    $manifest.sourceCatalog.'leipzig-heart-center'.licenseId -ne "ODC-BY-1.0") {
  throw "Rebuilt corpus failed count/license verification. Keep the current corpus active."
}

$env:ECG_CORPUS_ROOT = (Resolve-Path $target).Path
# Restart the single backend process only after the checks above pass.
```

The separate target preserves the currently installed corpus throughout the
two long-running build/import phases. Keep the old corpus until a real waveform,
Training start, Rapid start, and Clinical case have passed smoke testing against
the new root.
