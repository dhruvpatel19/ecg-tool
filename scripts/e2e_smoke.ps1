param(
  [switch]$RequireRealData,
  [string]$CorpusRoot = "",
  [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendPort = 8011
$frontendPort = 3011
$backendUrl = "http://127.0.0.1:$backendPort"
$frontendUrl = "http://127.0.0.1:$frontendPort"
$artifactRoot = Join-Path $root ".tmp"
$testDatabaseRelative = ".tmp/e2e-smoke-$backendPort.db"
$testDatabase = Join-Path $root ($testDatabaseRelative.Replace('/', '\'))
$backendLog = Join-Path $artifactRoot "e2e-smoke-$backendPort-backend.log"
$backendErr = Join-Path $artifactRoot "e2e-smoke-$backendPort-backend.err.log"
$frontendLog = Join-Path $artifactRoot "e2e-smoke-$frontendPort-frontend.log"
$frontendErr = Join-Path $artifactRoot "e2e-smoke-$frontendPort-frontend.err.log"
$smokeFiles = @(
  $testDatabase,
  "$testDatabase-wal",
  "$testDatabase-shm",
  $backendLog,
  $backendErr,
  $frontendLog,
  $frontendErr
)

function Wait-ForUrl {
  param(
    [Parameter(Mandatory = $true)][string]$Url,
    [int]$Seconds = 30,
    [Microsoft.PowerShell.Commands.WebRequestSession]$WebSession = $null,
    [System.Diagnostics.Process]$Process = $null
  )
  $deadline = (Get-Date).AddSeconds($Seconds)
  do {
    if ($Process) {
      $Process.Refresh()
      if ($Process.HasExited) {
        throw "Process $($Process.Id) exited with code $($Process.ExitCode) while waiting for $Url"
      }
    }
    try {
      if ($WebSession) {
        return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -WebSession $WebSession
      }
      return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)
  throw "Timed out waiting for $Url"
}

function Assert-SmokePortAvailable {
  param([Parameter(Mandatory = $true)][int]$Port)

  if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. The smoke test will not stop or reuse an existing process."
  }
}

function Assert-SmokeListenerOwnedBy {
  param(
    [Parameter(Mandatory = $true)][int]$Port,
    [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process
  )

  $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
  if (-not $listeners -or @($listeners | Where-Object { $_.OwningProcess -ne $Process.Id }).Count -gt 0) {
    $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    throw "Port $Port is not exclusively owned by smoke process $($Process.Id) (listeners: $owners)."
  }
}

function Start-SmokeProcess {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter(Mandatory = $true)][string[]]$ArgumentList,
    [Parameter(Mandatory = $true)][string]$WorkingDirectory,
    [Parameter(Mandatory = $true)][hashtable]$Environment,
    [Parameter(Mandatory = $true)][string]$StandardOutput,
    [Parameter(Mandatory = $true)][string]$StandardError
  )

  $previous = @{}
  try {
    foreach ($name in $Environment.Keys) {
      $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
      [Environment]::SetEnvironmentVariable($name, [string]$Environment[$name], "Process")
    }
    return Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
      -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $StandardOutput `
      -RedirectStandardError $StandardError -WindowStyle Hidden -PassThru
  } finally {
    foreach ($name in $Environment.Keys) {
      [Environment]::SetEnvironmentVariable($name, $previous[$name], "Process")
    }
  }
}

function Stop-SmokeProcess {
  param([System.Diagnostics.Process]$Process)

  if (-not $Process) { return }
  $processId = $Process.Id
  try {
    $Process.Refresh()
    if (-not $Process.HasExited) {
      Stop-Process -Id $Process.Id -Force -ErrorAction Stop
    }
    if (-not $Process.WaitForExit(10000)) {
      Write-Warning "Smoke-owned process $processId did not report exit within 10 seconds."
    }
  } catch {
    Write-Warning "Could not stop smoke-owned process ${processId}: $($_.Exception.Message)"
  } finally {
    $Process.Dispose()
  }
}

function Clear-SmokeArtifacts {
  $expectedRoot = [IO.Path]::GetFullPath($artifactRoot)
  foreach ($candidate in $smokeFiles) {
    $fullPath = [IO.Path]::GetFullPath($candidate)
    if ([IO.Path]::GetDirectoryName($fullPath) -ne $expectedRoot) {
      throw "Refusing to remove a smoke artifact outside .tmp: $fullPath"
    }
    if (Test-Path -LiteralPath $fullPath) {
      for ($attempt = 1; $attempt -le 20; $attempt += 1) {
        try {
          Remove-Item -LiteralPath $fullPath -Force -ErrorAction Stop
          break
        } catch {
          if ($attempt -eq 20) { throw }
          Start-Sleep -Milliseconds 100
        }
      }
    }
  }
}

function Assert-NoRawAssessmentIdentity {
  param(
    [Parameter(Mandatory = $true)][AllowNull()][object]$Value,
    [string]$Context = "assessment payload",
    [ValidateSet("ec", "ci")][string[]]$AllowedReferencePrefixes = @("ec")
  )

  if ($null -eq $Value) { return }

  # Inspect only JSON object keys. Recursing through PowerShell's extended type
  # properties can revisit self-referential members (notably DateTime.Date),
  # making a small response consume unbounded CPU without strengthening this
  # boundary assertion.
  $json = ConvertTo-Json -InputObject $Value -Depth 50 -Compress -WarningAction Stop

  $sourceIdentityFields = @(
    "record_identity", "source_provenance", "patientid", "patient_id",
    "subjectid", "subject_id", "recordid", "record_id", "sourcerecordid",
    "source_record_id", "sourcecaseid", "source_case_id", "parentrecordid", "parent_record_id", "studyid",
    "study_id", "filename", "filename_lr", "filename_hr", "path",
    "record_path", "file_path", "data_path", "uri", "url", "gcs_uri",
    "source_uri", "signalfingerprint", "signal_fingerprint", "recordname",
    "record_name", "waveformpath", "waveform_path", "windowstartsample",
    "window_start_sample", "windowendsample", "window_end_sample"
  )
  $ecgReferenceFields = @(
    "caseid", "case_id", "caseref", "case_ref", "ecgid", "ecg_id",
    "ecgref", "ecg_ref", "pendingcaseid", "feedbackcaseid"
  )

  $regexOptions = [Text.RegularExpressions.RegexOptions]::IgnoreCase -bor
    [Text.RegularExpressions.RegexOptions]::CultureInvariant
  $sourceFieldPattern = ($sourceIdentityFields | ForEach-Object { [Regex]::Escape($_) }) -join "|"
  $sourceMatch = [Regex]::Match(
    $json,
    "(?<=[{,])`"(?<field>$sourceFieldPattern)`"\s*:",
    $regexOptions
  )
  if ($sourceMatch.Success) {
    throw "$Context.$($sourceMatch.Groups['field'].Value) exposed a source record identity or storage coordinate"
  }

  $referenceFieldPattern = ($ecgReferenceFields | ForEach-Object { [Regex]::Escape($_) }) -join "|"
  $referenceMatches = [Regex]::Matches(
    $json,
    "(?<=[{,])`"(?<field>$referenceFieldPattern)`"\s*:\s*(?<value>null|`"(?:\\.|[^`"\\])*`"|[^,}\]]+)",
    $regexOptions
  )
  $allowedPrefixPattern = ($AllowedReferencePrefixes | ForEach-Object { [Regex]::Escape($_) }) -join "|"
  foreach ($match in $referenceMatches) {
    $encodedValue = $match.Groups['value'].Value.Trim()
    if ($encodedValue -eq "null") { continue }
    if (-not $encodedValue.StartsWith('"')) {
      throw "$Context.$($match.Groups['field'].Value) exposed a non-string ECG identifier"
    }
    $reference = ConvertFrom-Json -InputObject $encodedValue
    if ($reference -notmatch "^(?:$allowedPrefixPattern)_[A-Za-z0-9_-]{43}$") {
      throw "$Context.$($match.Groups['field'].Value) exposed a non-capability ECG identifier"
    }
  }

  $displayMatches = [Regex]::Matches(
    $json,
    '(?<=[{,])"(?<field>displayid|display_id)"\s*:\s*(?<value>null|"(?:\\.|[^"\\])*"|[^,}\]]+)',
    $regexOptions
  )
  foreach ($match in $displayMatches) {
    $encodedValue = $match.Groups['value'].Value.Trim()
    if ($encodedValue -eq "null") { continue }
    if (-not $encodedValue.StartsWith('"')) {
      throw "$Context.$($match.Groups['field'].Value) exposed a non-string display identifier"
    }
    $displayId = ConvertFrom-Json -InputObject $encodedValue
    if ($displayId -and $displayId -notmatch '^(Rapid|Assessment|Clinical) ECG ') {
      throw "$Context.$($match.Groups['field'].Value) exposed a dataset-derived display identifier"
    }
  }
}

Set-Location $root
Assert-SmokePortAvailable -Port $backendPort
Assert-SmokePortAvailable -Port $frontendPort
if (-not (Test-Path -LiteralPath (Join-Path $root "frontend\.next\BUILD_ID"))) {
  throw "The frontend production build is missing. Run npm run build in frontend before the smoke test."
}
New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
Clear-SmokeArtifacts
$backendProcess = $null
$frontendProcess = $null
$runSucceeded = $false

try {
  # This deterministic journey verifies the grounded fallback without making a
  # paid provider call. `verify.ps1 -Release` runs `llm_smoke.ps1` separately
  # with the explicitly supplied live credential.
  $backendEnvironment = @{
    PYTHONPATH = "backend"
    APP_ENV = "test"
    LLM_PROVIDER = "mock"
    LLM_API_KEY = ""
    DATABASE_URL = "sqlite:///$testDatabaseRelative"
    ECG_REQUIRE_REAL_DATA = $(if ($RequireRealData) { "1" } else { "0" })
  }
  if ($CorpusRoot) {
    $backendEnvironment.ECG_CORPUS_ROOT = $CorpusRoot
  } elseif ($env:ECG_CORPUS_ROOT) {
    $backendEnvironment.ECG_CORPUS_ROOT = $env:ECG_CORPUS_ROOT
  }
  $backendProcess = Start-SmokeProcess -FilePath (Get-Command python.exe).Source `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", [string]$backendPort, "--no-proxy-headers") `
    -WorkingDirectory $root -Environment $backendEnvironment `
    -StandardOutput $backendLog -StandardError $backendErr
  Wait-ForUrl "$backendUrl/health" 35 -Process $backendProcess | Out-Null
  Assert-SmokeListenerOwnedBy -Port $backendPort -Process $backendProcess

  $frontendRoot = Join-Path $root "frontend"
  $nextCli = Join-Path $frontendRoot "node_modules\next\dist\bin\next"
  $frontendProcess = Start-SmokeProcess -FilePath (Get-Command node.exe).Source `
    -ArgumentList @($nextCli, "start", "--hostname", "127.0.0.1", "--port", [string]$frontendPort) `
    -WorkingDirectory $frontendRoot -Environment @{ ECG_BACKEND_API_BASE = $backendUrl; NODE_ENV = "production" } `
    -StandardOutput $frontendLog -StandardError $frontendErr
  Wait-ForUrl $frontendUrl 45 -Process $frontendProcess | Out-Null
  Assert-SmokeListenerOwnedBy -Port $frontendPort -Process $frontendProcess
  Wait-ForUrl "$frontendUrl/api/backend/health" 30 -Process $frontendProcess | Out-Null

  $health = Invoke-RestMethod -Uri "$backendUrl/health" -Method Get
  if (-not $health.ok) { throw "Health check failed" }
  $proxiedHealth = Invoke-RestMethod -Uri "$frontendUrl/api/backend/health" -Method Get
  if (-not $proxiedHealth.ok) { throw "Frontend proxy health check failed" }

  # All stateful checks use a real test-only account and its opaque HttpOnly
  # session. Anonymous fixture and guest-cookie paths are intentionally absent.
  $smokeSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
  $smokeUsername = "smoke_$([Guid]::NewGuid().ToString('N').Substring(0, 12))"
  $smokePassword = "Smoke-Owner-Pw-2026!"
  $registrationBody = @{
    username = $smokeUsername
    password = $smokePassword
    displayName = "Smoke Test Learner"
  } | ConvertTo-Json
  $registration = Invoke-RestMethod -Uri "$backendUrl/auth/register" -Method Post `
    -ContentType "application/json" -Body $registrationBody -WebSession $smokeSession
  $smokeUserId = [string]$registration.user.userId
  if ($smokeUserId -notmatch '^u_[a-f0-9]{16}$' -or $registration.user.username -ne $smokeUsername) {
    throw "Test account registration did not return the expected explicit owner"
  }
  $sessionCookie = $smokeSession.Cookies.GetCookies([Uri]$backendUrl) |
    Where-Object { $_.Name -eq "ecg_session" } |
    Select-Object -First 1
  if (-not $sessionCookie -or -not $sessionCookie.HttpOnly -or $sessionCookie.Value -notmatch '^[A-Za-z0-9_-]{43}$') {
    throw "Test account session cookie was not issued with the expected opaque HttpOnly contract"
  }
  $me = Invoke-RestMethod -Uri "$backendUrl/auth/me" -Method Get -WebSession $smokeSession
  if (-not $me.authenticated -or $me.user.userId -ne $smokeUserId) {
    throw "Backend session hydration did not resolve the registered test owner"
  }
  $proxiedMe = Invoke-RestMethod -Uri "$frontendUrl/api/backend/auth/me" -Method Get -WebSession $smokeSession
  if (-not $proxiedMe.authenticated -or $proxiedMe.user.userId -ne $smokeUserId) {
    throw "Frontend proxy did not preserve the registered test-owner session"
  }
  Wait-ForUrl "$frontendUrl/practice" 30 -WebSession $smokeSession -Process $frontendProcess | Out-Null
  Wait-ForUrl "$frontendUrl/profile" 30 -WebSession $smokeSession -Process $frontendProcess | Out-Null

  $status = Invoke-RestMethod -Uri "$backendUrl/dataset/status" -Method Get -WebSession $smokeSession
  if ($status.case_count -lt 1) { throw "No cases are indexed" }
  if ($RequireRealData -and ($status.fixture_fallback -or $status.active_source -eq "fixture")) {
    throw "Real-data smoke required, but backend is using fixture fallback. Status: $($status | ConvertTo-Json -Depth 8)"
  }
  if (-not $RequireRealData -and ($status.fixture_fallback -or $status.active_source -eq "fixture")) {
    Write-Warning "Smoke flow is using fixture fallback. Use -RequireRealData to make this a failure."
  }

  # Exercise the same server-owned lifecycle used by Rapid Practice. A generic
  # `/attempts` write is intentionally forbidden for a pending assessment.
  $roundBody = @{
    learnerId = $smokeUserId
    pace = "untimed"
    length = 5
    focusConcept = $null
    secondaryConcept = $null
    focusSubskill = $null
    contextKey = ""
    exclusions = @()
  } | ConvertTo-Json -Depth 6
  $roundStart = Invoke-RestMethod -Uri "$backendUrl/rapid/rounds" -Method Post -ContentType "application/json" -Body $roundBody -WebSession $smokeSession
  $roundId = $roundStart.round.roundId
  if ($roundId -notmatch '^rr_[a-f0-9]{16}$' -or $roundStart.round.status -ne "active") {
    throw "Rapid round did not start with an active server-owned id"
  }

  $served = Invoke-RestMethod -Uri "$backendUrl/rapid/rounds/$roundId/next" -Method Post -ContentType "application/json" -Body '{"activate":false}' -WebSession $smokeSession
  if ($served.current.kind -ne "pending" -or -not $served.current.case.caseId) {
    throw "Rapid round did not freeze a pending ECG"
  }
  $caseRef = $served.current.case.caseId
  $packet = $served.current.packet
  if ($caseRef -notmatch '^ec_[A-Za-z0-9_-]{43}$') { throw "Rapid case did not use an opaque ECG capability" }
  if ($served.round.pendingCaseId -ne $caseRef -or $packet.case_id -ne $caseRef) { throw "Rapid case capability mismatch" }
  if ($packet.blinded -ne $true) { throw "Pending Rapid packet was not blinded" }
  foreach ($answerField in @("concept_confidence", "supported_objectives", "unsupported_objectives", "teaching_points")) {
    if ($packet.PSObject.Properties.Name -contains $answerField) {
      throw "Pending Rapid packet leaked answer-bearing field '$answerField'"
    }
  }
  Assert-NoRawAssessmentIdentity -Value $served -Context "pending Rapid response"

  $waveform = Invoke-RestMethod -Uri "$backendUrl/rapid/rounds/$roundId/waveform/$caseRef`?leads=II,V2&maxPoints=300" -Method Get -WebSession $smokeSession
  if ($waveform.caseId -ne $caseRef) { throw "Round-scoped waveform did not echo the exact ECG capability" }
  Assert-NoRawAssessmentIdentity -Value $waveform -Context "Rapid waveform response"
  if ($waveform.leads.Count -lt 1 -or $waveform.leads[0].points.Count -lt 1) { throw "Waveform did not return points" }
  $traceLead = @($waveform.leads | Where-Object { $_.lead -eq "II" } | Select-Object -First 1)[0]
  if (-not $traceLead) { $traceLead = @($waveform.leads)[0] }
  $tracePoint = $traceLead.points |
    Sort-Object { [math]::Abs([double]$_.amplitudeMv) } -Descending |
    Select-Object -First 1
  if (-not $tracePoint) { throw "Waveform did not provide a trace point" }

  $activated = Invoke-RestMethod -Uri "$backendUrl/rapid/rounds/$roundId/next" -Method Post -ContentType "application/json" -Body '{"activate":true}' -WebSession $smokeSession
  if ($activated.current.kind -ne "pending" -or -not $activated.current.startedAt) {
    throw "Rapid ECG was not activated before commitment"
  }

  $answerBody = @{
    caseId = $caseRef
    structuredAnswer = @{
      framework = "clerkship"
      rate = "rate reviewed"
      rhythm = "rhythm reviewed"
      axis = "axis reviewed"
      intervals = "intervals reviewed"
      conduction = "qrs reviewed"
      st_t = "st-t reviewed"
      hypertrophy = "chamber patterns reviewed"
      synthesis = "Evidence-limited complete ECG interpretation."
      selectedConcepts = @("normal_ecg")
    }
    freeTextAnswer = "Evidence-limited complete ECG interpretation."
    confidence = 3
    traceEvidence = @{
      mode = "point"
      point = @{
        lead = [string]$traceLead.lead
        timeSec = [double]$tracePoint.timeSec
        amplitudeMv = [double]$tracePoint.amplitudeMv
      }
    }
  } | ConvertTo-Json -Depth 8
  $submission = Invoke-RestMethod -Uri "$backendUrl/rapid/rounds/$roundId/submit" -Method Post -ContentType "application/json" -Body $answerBody -WebSession $smokeSession
  if ($submission.replay -ne $false -or $submission.answer.answerId -lt 1 -or $submission.answer.attemptId -lt 1) {
    throw "Rapid answer did not commit atomically"
  }
  if ($submission.answer.integrityStatus -notin @("atomic_v1", "atomic_v2") -or $submission.current.kind -ne "feedback") {
    throw "Rapid feedback did not retain the verified assessment boundary"
  }
  if (-not $submission.answer.traceGrade -or $submission.answer.response.traceEvidence.mode -ne "point") {
    throw "Committed Rapid answer did not retain its trace evidence and grade"
  }
  if (@($submission.receipts).Count -lt 1 -or @($submission.receipts | Where-Object { -not $_.registryVersion }).Count -gt 0) {
    throw "Rapid commitment did not return registry-versioned evidence receipts"
  }
  foreach ($releasedField in @("concept_confidence", "supported_objectives", "teaching_points")) {
    if (-not ($submission.current.packet.PSObject.Properties.Name -contains $releasedField)) {
      throw "Committed feedback did not release answer-bearing field '$releasedField'"
    }
  }
  if ($submission.round.feedbackCaseId -ne $caseRef -or $submission.answer.caseId -ne $caseRef -or $submission.current.packet.case_id -ne $caseRef) {
    throw "Committed Rapid feedback changed or exposed its ECG identity"
  }
  Assert-NoRawAssessmentIdentity -Value $submission -Context "committed Rapid response"
  $smokeLearnerId = $submission.profile.learnerId
  if ($smokeLearnerId -ne $smokeUserId) { throw "Rapid answer was not bound to the registered test owner" }

  # The tutor is available only after durable commitment. Mock mode makes this
  # assertion deterministic and free; live-provider verification is separate.
  $tutorBody = @{
    learnerId = $smokeUserId
    mode = "practice"
    caseId = $caseRef
    scopeKey = "rapid:$roundId"
    message = "Explain one grounded feature to review on this committed ECG."
    viewerState = @{ activity = "rapid_case_debrief"; committed = $true }
  } | ConvertTo-Json -Depth 8
  $tutor = Invoke-RestMethod -Uri "$backendUrl/tutor/message" -Method Post -ContentType "application/json" -Body $tutorBody -WebSession $smokeSession
  if (-not $tutor.tutorMessage -or -not $tutor.threadId) { throw "Post-commit grounded tutor did not respond" }
  $tutorThread = Invoke-RestMethod -Uri "$backendUrl/tutor/thread/$($tutor.threadId)" -Method Get -WebSession $smokeSession
  if ($tutorThread.scopeKey -ne "rapid:$roundId" -or $tutorThread.caseId -ne $caseRef) {
    throw "Post-commit tutor thread was not bound to the exact Rapid scope and capability"
  }
  Assert-NoRawAssessmentIdentity -Value $tutorThread -Context "Rapid tutor thread"

  $profile = Invoke-RestMethod -Uri "$backendUrl/learners/$smokeUserId" -Method Get -WebSession $smokeSession
  if ($profile.learnerId -ne $smokeLearnerId) { throw "Profile request did not retain the registered test owner" }
  if ($profile.recentAttempts.Count -lt 1) { throw "Profile did not record recent attempt" }
  Assert-NoRawAssessmentIdentity -Value $profile -Context "learner profile"

  $activity = Invoke-RestMethod -Uri "$backendUrl/learning/activity?mode=rapid&limit=5" -Method Get -WebSession $smokeSession
  if ($activity.version -ne "learning-activity-v1" -or @($activity.items | Where-Object { $_.mode -eq "rapid" }).Count -lt 1) {
    throw "Owner-bound learning activity did not project the committed Rapid answer"
  }
  Assert-NoRawAssessmentIdentity -Value $activity -Context "learning activity"

  $plan = Invoke-RestMethod -Uri "$backendUrl/adaptive/plan?learnerId=$smokeUserId" -Method Get -WebSession $smokeSession
  if ($plan.learnerId -ne $smokeLearnerId -or $plan.plannerKind -ne "verified_competency_scheduler" -or -not $plan.primary.objectiveId -or -not $plan.coachContext.contextId) {
    throw "Adaptive mastery plan was not rebuilt for the same learner"
  }

  $abandoned = Invoke-RestMethod -Uri "$backendUrl/rapid/rounds/$roundId/abandon" -Method Post -WebSession $smokeSession
  if ($abandoned.round.status -ne "abandoned") { throw "Smoke Rapid round was not closed cleanly" }

  # Exercise an untimed Clinical case through first look, grounded waveform,
  # dynamic question commitment, feedback, and the post-commit tutor boundary.
  $clinicalStartBody = @{
    learnerId = $smokeUserId
    lane = "clinic"
    tier = "learn"
    length = 1
    focus = "normal_ecg"
  } | ConvertTo-Json
  $clinicalStart = Invoke-RestMethod -Uri "$backendUrl/clinical/shift/start" -Method Post `
    -ContentType "application/json" -Body $clinicalStartBody -WebSession $smokeSession
  $clinicalSessionId = [string]$clinicalStart.session.sessionId
  $clinicalItemId = [string]$clinicalStart.next.itemId
  $clinicalRef = [string]$clinicalStart.next.item.ecg_ref
  if ($clinicalSessionId -notmatch '^cs_[a-f0-9]{16}$' -or $clinicalItemId -notmatch '^ci_[A-Za-z0-9_-]{43}$') {
    throw "Clinical learning set did not start with opaque server-owned identifiers"
  }
  if ($clinicalRef -notmatch '^ec_[A-Za-z0-9_-]{43}$' -or $clinicalStart.next.done) {
    throw "Clinical learning set did not serve an opaque pending ECG"
  }
  Assert-NoRawAssessmentIdentity -Value $clinicalStart -Context "pending Clinical response" -AllowedReferencePrefixes @("ec", "ci")

  $clinicalWaveform = Invoke-RestMethod `
    -Uri "$backendUrl/clinical/shift/$clinicalSessionId/waveform/$clinicalRef`?leads=II,V1&maxPoints=300" `
    -Method Get -WebSession $smokeSession
  if ($clinicalWaveform.caseId -ne $clinicalRef -or $clinicalWaveform.leads.Count -lt 1 -or $clinicalWaveform.leads[0].points.Count -lt 1) {
    throw "Clinical waveform did not remain bound to the pending ECG capability"
  }
  Assert-NoRawAssessmentIdentity -Value $clinicalWaveform -Context "Clinical waveform response" -AllowedReferencePrefixes @("ec", "ci")

  $clinicalRevealBody = @{
    itemId = $clinicalItemId
    answer = @{ firstLookFinding = "uncertain"; firstLookConfidence = 3 }
  } | ConvertTo-Json -Depth 5
  $clinicalReveal = Invoke-RestMethod -Uri "$backendUrl/clinical/shift/$clinicalSessionId/context" -Method Post `
    -ContentType "application/json" -Body $clinicalRevealBody -WebSession $smokeSession
  $clinicalItem = $clinicalReveal.item
  if ($clinicalItem.ecg_ref -ne $clinicalRef) { throw "Clinical context changed the pending ECG capability" }

  $stepCount = 0
  while ($clinicalItem.stepwise_state -and $clinicalItem.stepwise_state.active) {
    $stepCount += 1
    if ($stepCount -gt 20) { throw "Clinical stepwise question exceeded its bounded authored sequence" }
    $activeStep = $clinicalItem.stepwise_state.active
    $stepBody = @{
      itemId = $clinicalItemId
      stepIndex = [int]$activeStep.stepIndex
      answerIndex = 0
    } | ConvertTo-Json
    $stepResult = Invoke-RestMethod -Uri "$backendUrl/clinical/shift/$clinicalSessionId/step" -Method Post `
      -ContentType "application/json" -Body $stepBody -WebSession $smokeSession
    $clinicalItem = $stepResult.item
  }

  $clinicalAnswer = @{ confidence = 3 }
  $clinicalOptions = @($clinicalItem.options | Where-Object { $null -ne $_ })
  if ($clinicalOptions.Count -gt 0) {
    $clinicalAnswer["selectedOptionId"] = [string]$clinicalOptions[0].id
  }
  $machineReadLines = @($clinicalItem.machine_read | Where-Object { $null -ne $_ })
  if ($machineReadLines.Count -gt 0) {
    $clinicalAnswer["machineLineId"] = [string]$machineReadLines[0].id
  }
  if ($clinicalItem.fill_in_task) {
    $clinicalAnswer["fillInValue"] = [double]$clinicalItem.fill_in_task.min_value
  }
  $matchingRows = @($clinicalItem.matching_task.rows | Where-Object { $null -ne $_ })
  $matchingChoices = @($clinicalItem.matching_task.choices | Where-Object { $null -ne $_ })
  if ($matchingRows.Count -gt 0 -and $matchingChoices.Count -gt 0) {
    $matchingPairs = @{}
    $pairCount = [Math]::Min($matchingRows.Count, $matchingChoices.Count)
    for ($index = 0; $index -lt $pairCount; $index += 1) {
      $rowId = [string]$matchingRows[$index].id
      $choiceId = [string]$matchingChoices[$index].id
      $matchingPairs[$rowId] = $choiceId
    }
    $clinicalAnswer["matches"] = $matchingPairs
  }
  $clickableLeads = @($clinicalItem.clickable_leads | Where-Object { $null -ne $_ })
  if ($clickableLeads.Count -gt 0) {
    $clinicalAnswer["click"] = @{
      lead = [string]$clickableLeads[0]
      timeSec = 1.0
      amplitudeMv = 0.0
    }
  }
  $clinicalAnswerBody = @{
    itemId = $clinicalItemId
    answer = $clinicalAnswer
  } | ConvertTo-Json -Depth 8
  $clinicalSubmission = Invoke-RestMethod -Uri "$backendUrl/clinical/shift/$clinicalSessionId/answer" -Method Post `
    -ContentType "application/json" -Body $clinicalAnswerBody -WebSession $smokeSession
  if ($clinicalSubmission.replay -ne $false -or -not $clinicalSubmission.grade -or -not $clinicalSubmission.tutorContext.contextId) {
    throw "Clinical answer did not commit with grounded feedback and a tutor context"
  }
  if ($clinicalSubmission.tutorContext.sessionId -ne $clinicalSessionId -or $clinicalSubmission.tutorContext.itemId -ne $clinicalItemId) {
    throw "Clinical tutor context was not bound to the committed case"
  }
  Assert-NoRawAssessmentIdentity -Value $clinicalSubmission -Context "committed Clinical response" -AllowedReferencePrefixes @("ec", "ci")

  $clinicalTutorBody = @{
    learnerId = $smokeUserId
    mode = "practice"
    lessonId = [string]$clinicalSubmission.tutorContext.contextId
    caseId = $clinicalRef
    message = "Explain one grounded feature behind this committed clinical decision."
    clinicalContext = $clinicalSubmission.tutorContext
    viewerState = @{ activity = "clinical_case_debrief"; committed = $true }
  } | ConvertTo-Json -Depth 8
  $clinicalTutor = Invoke-RestMethod -Uri "$backendUrl/tutor/message" -Method Post `
    -ContentType "application/json" -Body $clinicalTutorBody -WebSession $smokeSession
  if (-not $clinicalTutor.threadId -or -not $clinicalTutor.tutorMessage) {
    throw "Post-commit grounded Clinical tutor did not respond"
  }
  $clinicalTutorThread = Invoke-RestMethod -Uri "$backendUrl/tutor/thread/$($clinicalTutor.threadId)" -Method Get -WebSession $smokeSession
  if ($clinicalTutorThread.caseId -ne $clinicalRef -or $clinicalTutorThread.messages[-1].meta.clinicalContextId -ne $clinicalSubmission.tutorContext.contextId) {
    throw "Clinical tutor thread did not retain its committed case context"
  }
  Assert-NoRawAssessmentIdentity -Value $clinicalTutorThread -Context "Clinical tutor thread" -AllowedReferencePrefixes @("ec", "ci")

  $clinicalDone = Invoke-RestMethod -Uri "$backendUrl/clinical/shift/$clinicalSessionId/next" -Method Post -WebSession $smokeSession
  if (-not $clinicalDone.done) { throw "Single-case Clinical learning set did not finish cleanly" }
  $clinicalReport = Invoke-RestMethod -Uri "$backendUrl/clinical/shift/$clinicalSessionId/report" -Method Get -WebSession $smokeSession
  if ($clinicalReport.answered -lt 1) { throw "Clinical report did not retain the committed decision" }
  Assert-NoRawAssessmentIdentity -Value $clinicalReport -Context "Clinical report" -AllowedReferencePrefixes @("ec", "ci")

  $runSucceeded = $true
  Write-Output "Smoke E2E ok: explicit account/session, frontend proxy, blinded Rapid lifecycle, Clinical decision lifecycle, waveform evidence, grounded tutors, activity, profile, and adaptive plan passed."
} finally {
  Stop-SmokeProcess -Process $frontendProcess
  Stop-SmokeProcess -Process $backendProcess
  if ($runSucceeded -and -not $KeepArtifacts) {
    Clear-SmokeArtifacts
  } elseif ($runSucceeded) {
    Write-Output "Smoke artifacts retained under $artifactRoot"
  } else {
    Write-Warning "Smoke failed; database and logs were retained under $artifactRoot"
  }
}
