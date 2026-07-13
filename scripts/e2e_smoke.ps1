param(
  [switch]$RequireRealData,
  [string]$CorpusRoot = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendPort = 8011
$frontendPort = 3011
$backendUrl = "http://127.0.0.1:$backendPort"
$frontendUrl = "http://127.0.0.1:$frontendPort"
$backendLog = Join-Path $root "backend\.smoke-backend.log"
$backendErr = Join-Path $root "backend\.smoke-backend.err.log"
$frontendLog = Join-Path $root "frontend\.smoke-frontend.log"
$frontendErr = Join-Path $root "frontend\.smoke-frontend.err.log"

function Wait-ForUrl {
  param(
    [Parameter(Mandatory = $true)][string]$Url,
    [int]$Seconds = 30
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

function Stop-SmokeProcesses {
  foreach ($port in @($backendPort, $frontendPort)) {
    Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique |
      ForEach-Object {
        try { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } catch {}
      }
  }
  $patterns = @("uvicorn app.main:app --host 127.0.0.1 --port $backendPort", "next*start --hostname 127.0.0.1 --port $frontendPort")
  foreach ($pattern in $patterns) {
    Get-CimInstance Win32_Process |
      Where-Object { $_.CommandLine -like "*$pattern*" } |
      ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
      }
  }
}

Set-Location $root
Stop-SmokeProcesses
Remove-Item -LiteralPath $backendLog, $backendErr, $frontendLog, $frontendErr -Force -ErrorAction SilentlyContinue

try {
  $backendCommand = "`$env:PYTHONPATH='backend'; "
  if ($CorpusRoot) {
    $backendCommand += "`$env:ECG_CORPUS_ROOT='$CorpusRoot'; "
  } elseif ($env:ECG_CORPUS_ROOT) {
    $backendCommand += "`$env:ECG_CORPUS_ROOT='$($env:ECG_CORPUS_ROOT)'; "
  }
  if ($RequireRealData) {
    $backendCommand += "`$env:ECG_REQUIRE_REAL_DATA='1'; "
  }
  $backendCommand += "python -m uvicorn app.main:app --host 127.0.0.1 --port $backendPort --no-proxy-headers"
  Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand) -WorkingDirectory $root -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr -WindowStyle Hidden | Out-Null
  Wait-ForUrl "$backendUrl/health" 35 | Out-Null

  $frontendCommand = "`$env:ECG_BACKEND_API_BASE='$backendUrl'; npm.cmd run start -- --hostname 127.0.0.1 --port $frontendPort"
  Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand) -WorkingDirectory (Join-Path $root "frontend") -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErr -WindowStyle Hidden | Out-Null
  Wait-ForUrl $frontendUrl 45 | Out-Null
  Wait-ForUrl "$frontendUrl/api/backend/health" 30 | Out-Null
  Wait-ForUrl "$frontendUrl/practice" 30 | Out-Null
  Wait-ForUrl "$frontendUrl/profile" 30 | Out-Null

  $health = Invoke-RestMethod -Uri "$backendUrl/health" -Method Get
  if (-not $health.ok) { throw "Health check failed" }
  $proxiedHealth = Invoke-RestMethod -Uri "$frontendUrl/api/backend/health" -Method Get
  if (-not $proxiedHealth.ok) { throw "Frontend proxy health check failed" }

  $status = Invoke-RestMethod -Uri "$backendUrl/dataset/status" -Method Get
  if ($status.case_count -lt 1) { throw "No cases are indexed" }
  if ($RequireRealData -and ($status.fixture_fallback -or $status.active_source -eq "fixture")) {
    throw "Real-data smoke required, but backend is using fixture fallback. Status: $($status | ConvertTo-Json -Depth 8)"
  }
  if (-not $RequireRealData -and ($status.fixture_fallback -or $status.active_source -eq "fixture")) {
    Write-Warning "Smoke flow is using fixture fallback. Use -RequireRealData to make this a failure."
  }

  $cases = Invoke-RestMethod -Uri "$backendUrl/cases" -Method Get
  if ($cases.Count -lt 1) { throw "No student-facing cases returned" }
  $caseId = $cases[0].caseId

  $packet = Invoke-RestMethod -Uri "$backendUrl/cases/$caseId/packet" -Method Get
  if ($packet.case_id -ne $caseId) { throw "Case packet mismatch" }
  if (-not $packet.concept_confidence) { throw "Case packet missing concept confidence" }

  $waveform = Invoke-RestMethod -Uri "$backendUrl/cases/$caseId/waveform?leads=II,V2&maxPoints=300" -Method Get
  if ($waveform.leads.Count -lt 1 -or $waveform.leads[0].points.Count -lt 1) { throw "Waveform did not return points" }

  $tutorBody = @{
    learnerId = "smoke"
    mode = "rapid_practice"
    caseId = $caseId
    learnerMessage = "Give a grounded visual hint."
    viewerState = @{}
  } | ConvertTo-Json -Depth 8
  $tutor = Invoke-RestMethod -Uri "$backendUrl/tutor/chat" -Method Post -ContentType "application/json" -Body $tutorBody
  if (-not $tutor.tutorMessage) { throw "Tutor did not return a message" }

  $attemptBody = @{
    learnerId = "smoke"
    caseId = $caseId
    mode = "rapid_practice"
    structuredAnswer = @{
      framework = "clerkship"
      rate = "rate reviewed"
      rhythm = "rhythm reviewed"
      axis = "axis reviewed"
      intervals = "intervals reviewed"
      conduction = "qrs reviewed"
      st_t = "st elevation if present"
      hypertrophy = ""
      synthesis = "educational synthesis"
      selectedConcepts = @()
    }
    freeTextAnswer = "educational interpretation based on the visible ECG"
    confidence = 3
    hintsUsed = 0
  } | ConvertTo-Json -Depth 8
  $attempt = Invoke-RestMethod -Uri "$backendUrl/attempts" -Method Post -ContentType "application/json" -Body $attemptBody
  if ($attempt.attemptId -lt 1) { throw "Attempt was not saved" }

  $profile = Invoke-RestMethod -Uri "$backendUrl/learners/smoke" -Method Get
  if ($profile.recentAttempts.Count -lt 1) { throw "Profile did not record recent attempt" }

  $next = Invoke-RestMethod -Uri "$backendUrl/practice/next?learnerId=smoke" -Method Get
  if (-not $next.case.caseId) { throw "Adaptive next case missing caseId" }

  Write-Output "Smoke E2E ok: frontend routes, waveform, tutor, attempt, profile, and adaptive next case passed."
} finally {
  Stop-SmokeProcesses
}
