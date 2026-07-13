param(
  [string]$CorpusRoot = "",
  [int]$BackendPort = 8021
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendUrl = "http://127.0.0.1:$BackendPort"
$backendLog = Join-Path $root "backend\.llm-smoke-backend.log"
$backendErr = Join-Path $root "backend\.llm-smoke-backend.err.log"
$smokeDb = Join-Path $root "backend\.llm-smoke.db"

function Wait-ForUrl {
  param(
    [Parameter(Mandatory = $true)][string]$Url,
    [int]$Seconds = 35
  )
  $deadline = (Get-Date).AddSeconds($Seconds)
  do {
    try {
      return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)
  throw "Timed out waiting for $Url"
}

function Stop-LlmSmokeProcess {
  Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
      try { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } catch {}
    }
}

Set-Location $root
Stop-LlmSmokeProcess
Remove-Item -LiteralPath $backendLog, $backendErr -Force -ErrorAction SilentlyContinue

try {
  $command = "`$env:PYTHONPATH='backend'; `$env:LLM_PROVIDER='openai-compatible'; `$env:DATABASE_URL='sqlite:///backend/.llm-smoke.db'; "
  if ($CorpusRoot) {
    $command += "`$env:ECG_CORPUS_ROOT='$CorpusRoot'; "
  }
  $command += "python -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort --no-proxy-headers"
  Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) -WorkingDirectory $root -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr -WindowStyle Hidden | Out-Null
  Wait-ForUrl "$backendUrl/health" 120 | Out-Null

  $health = Invoke-RestMethod -Uri "$backendUrl/health" -Method Get
  if (-not $health.ok) {
    throw "Backend liveness check failed."
  }
  $status = Invoke-RestMethod -Uri "$backendUrl/dataset/status" -Method Get
  if ($status.fixture_fallback -or $status.active_source -eq "fixture") {
    throw "Live LLM smoke requires real data, but fixture fallback is active."
  }

  $cases = Invoke-RestMethod -Uri "$backendUrl/cases" -Method Get
  if ($cases.Count -lt 1) { throw "No student-facing cases available for LLM smoke." }
  $caseId = $cases[0].caseId
  $body = @{
    learnerId = "llm-smoke"
    mode = "rapid_practice"
    caseId = $caseId
    learnerMessage = "Give one concise grounded hint. Return only valid JSON."
    viewerState = @{}
  } | ConvertTo-Json -Depth 8
  $tutor = Invoke-RestMethod -Uri "$backendUrl/tutor/chat" -Method Post -ContentType "application/json" -Body $body
  if ($tutor.provider -ne "openai-compatible") { throw "Unexpected tutor provider: $($tutor.provider)" }
  if ($tutor.schemaError) { throw "Live tutor response failed schema validation: $($tutor.schemaError)" }
  if (($tutor.uncertaintyWarnings -join " ") -match "Missing API key|remote tutor provider failed") {
    throw "Live tutor returned provider failure warning: $($tutor.uncertaintyWarnings -join ' ')"
  }
  if (-not $tutor.tutorMessage) { throw "Live tutor did not return a tutorMessage." }

  Write-Output "Live LLM smoke ok: provider=openai-compatible, real data active, schema-valid tutor response returned for case $caseId."
} finally {
  Stop-LlmSmokeProcess
  Remove-Item -LiteralPath $smokeDb, "$smokeDb-wal", "$smokeDb-shm" -Force -ErrorAction SilentlyContinue
}
