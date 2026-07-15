param(
  [switch]$Release
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Assert-NativeSuccess {
  param([Parameter(Mandatory = $true)][string]$Label)
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with native exit code $LASTEXITCODE."
  }
}

function Invoke-CheckedScript {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Label,
    [hashtable]$Parameters = @{}
  )

  # A child script may run a native command internally. Reset and inspect both
  # PowerShell's success flag and the child's final native exit code so a
  # cleanup command cannot turn a failed test suite into a successful verify.
  $global:LASTEXITCODE = 0
  & $Path @Parameters
  $scriptSucceeded = $?
  $childNativeExitCode = $LASTEXITCODE
  if (-not $scriptSucceeded -or $childNativeExitCode -ne 0) {
    throw "$Label failed (PowerShell success=$scriptSucceeded, native exit code=$childNativeExitCode)."
  }
}

if ($Release -and [string]::IsNullOrWhiteSpace($env:LLM_API_KEY)) {
  throw "Release verification requires LLM_API_KEY so the live LLM smoke cannot be skipped."
}

Write-Host "== Backend tests =="
$env:PYTHONPATH = "backend"
python -m pytest backend/tests -q
Assert-NativeSuccess "Backend tests"

Write-Host "== Local authentication email SMTP smoke =="
python scripts/smoke_auth_email_local.py
Assert-NativeSuccess "Local authentication email SMTP smoke"

Write-Host "== Production Python dependency audit =="
uvx pip-audit --disable-pip --no-deps -r backend\requirements-prod.txt
Assert-NativeSuccess "Production Python dependency audit"

Write-Host "== Frontend coordinate mapping test =="
Push-Location frontend
try {
  npm run test:coords
  Assert-NativeSuccess "Frontend coordinate mapping test"

  Write-Host "== Frontend typecheck =="
  npm run typecheck
  Assert-NativeSuccess "Frontend typecheck"

  Write-Host "== Frontend lint =="
  npm run lint
  Assert-NativeSuccess "Frontend lint"

  Write-Host "== Frontend dependency audit =="
  npm audit --omit=dev --audit-level=moderate
  Assert-NativeSuccess "Frontend dependency audit"

  Write-Host "== Frontend production build =="
  npm run build
  Assert-NativeSuccess "Frontend production build"
} finally {
  Pop-Location
}

Write-Host "== End-to-end smoke flow =="
$dataRoot = Join-Path $root "data"

# `manifest.complete` only gates an in-progress build. It is used here to locate
# a candidate, never as release evidence: the exhaustive audit below must pass
# before any real-data journey is allowed to count toward verification.
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

if (-not $corpus) {
  throw "No completed corpus found under data\. Build the full corpus before verification."
}

Write-Host "== Exhaustive release corpus audit =="
Write-Host "Auditing canonical corpus: $corpus"
python scripts/audit_release_corpus.py --corpus-root $corpus
Assert-NativeSuccess "Exhaustive release corpus audit"

$env:ECG_CORPUS_ROOT = $corpus
Invoke-CheckedScript -Path ".\scripts\e2e_smoke.ps1" -Label "End-to-end smoke flow" -Parameters @{
  RequireRealData = $true
  CorpusRoot = $corpus
}

Write-Host "== Four-mode browser journeys =="
Invoke-CheckedScript -Path ".\scripts\browser_e2e.ps1" -Label "Four-mode browser journeys" -Parameters @{
  CorpusRoot = $corpus
}

Write-Host "== Live LLM smoke =="
if ($env:LLM_API_KEY) {
  Invoke-CheckedScript -Path ".\scripts\llm_smoke.ps1" -Label "Live LLM smoke" -Parameters @{
    CorpusRoot = $corpus
  }
} elseif ($Release) {
  # The early guard should make this unreachable, but keep the release boundary
  # adjacent to the optional local branch as a fail-closed invariant.
  throw "Release verification requires a successful live LLM smoke."
} else {
  Write-Warning "Local verification skipped the live LLM smoke because LLM_API_KEY is unset. This run is not release approval; use -Release with a live key."
}

if ($Release) {
  Write-Host "Release verification complete: exhaustive corpus audit, real-data journeys, and live LLM smoke passed."
} else {
  Write-Host "Local verification complete. Run .\scripts\verify.ps1 -Release with LLM_API_KEY for release approval."
}
