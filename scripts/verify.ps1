$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== Backend tests =="
$env:PYTHONPATH = "backend"
python -m pytest backend/tests -q

Write-Host "== Frontend coordinate mapping test =="
Push-Location frontend
npm run test:coords

Write-Host "== Frontend typecheck =="
npm run typecheck

Write-Host "== Frontend dependency audit =="
npm audit --omit=dev --audit-level=moderate

Write-Host "== Frontend production build =="
npm run build
Pop-Location

Write-Host "== End-to-end smoke flow =="
$dataRoot = Join-Path $root "data"

# Canonical data path is the built corpus (manifest marked complete). Pin it explicitly
# so the smoke flow verifies the SAME source the runtime auto-selects, and report it.
$corpus = $null
if (Test-Path $dataRoot) {
  $corpus = Get-ChildItem $dataRoot -Directory -Filter "ecg_corpus*" |
    ForEach-Object {
      $manifest = Join-Path $_.FullName "manifest.json"
      $db = Join-Path $_.FullName "corpus.db"
      if ((Test-Path $manifest) -and (Test-Path $db)) {
        try {
          $m = Get-Content $manifest -Raw | ConvertFrom-Json
          if ($m.complete) { [PSCustomObject]@{ Path = $_.FullName; CaseCount = [int]$m.totalCases } }
        } catch {}
      }
    } |
    Sort-Object -Property CaseCount -Descending |
    Select-Object -First 1 -ExpandProperty Path
}

if ($corpus) {
  Write-Host "Pinning canonical corpus: $corpus"
  $env:ECG_CORPUS_ROOT = $corpus
  .\scripts\e2e_smoke.ps1 -RequireRealData
} else {
  Write-Warning "No COMPLETE corpus found under data\ (need manifest.json with complete:true). Build one: python scripts/build_corpus.py --limit 0 --out data/ecg_corpus"
  .\scripts\e2e_smoke.ps1
}

Write-Host "== Four-mode browser journeys =="
if ($corpus) {
  .\scripts\browser_e2e.ps1 -CorpusRoot $corpus
} else {
  .\scripts\browser_e2e.ps1
}

Write-Host "== Live LLM smoke =="
if ($env:LLM_API_KEY) {
  .\scripts\llm_smoke.ps1
} else {
  Write-Warning "LLM_API_KEY is not set. Live OpenAI-compatible LLM smoke was skipped; mock/schema/provider-adapter tests still ran."
}

Write-Host "Verification complete."
