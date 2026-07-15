param(
  [string]$CorpusRoot = "",
  [int]$BackendPort = 8022,
  [int]$FrontendPort = 3100,
  [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendUrl = "http://127.0.0.1:$BackendPort"
$frontendUrl = "http://localhost:$FrontendPort"
$backendLog = Join-Path $root "backend\.browser-e2e.log"
$backendErr = Join-Path $root "backend\.browser-e2e.err.log"
$testDatabaseRelative = ".tmp/browser-e2e-$BackendPort.db"
$testDatabase = Join-Path $root ($testDatabaseRelative.Replace('/', '\'))
$frontendBuild = Join-Path $root "frontend\.next-e2e-$FrontendPort"

function Stop-BrowserE2eBackend {
  Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
  $deadline = (Get-Date).AddSeconds(10)
  while ((Get-Date) -lt $deadline) {
    if (-not (Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue)) {
      return
    }
    Start-Sleep -Milliseconds 200
  }
  throw "Browser-test backend port $BackendPort did not close after shutdown."
}

function Assert-BrowserE2ePortAvailable {
  param([Parameter(Mandatory = $true)][int]$Port)
  if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Choose an isolated browser-test port; no existing process was stopped."
  }
}

function Clear-BrowserE2eDatabase {
  $expectedParent = [IO.Path]::GetFullPath((Join-Path $root ".tmp"))
  foreach ($candidate in @($testDatabase, "$testDatabase-wal", "$testDatabase-shm")) {
    $fullPath = [IO.Path]::GetFullPath($candidate)
    if ([IO.Path]::GetDirectoryName($fullPath) -ne $expectedParent) {
      throw "Refusing to remove a browser-test database outside .tmp: $fullPath"
    }
    if (Test-Path -LiteralPath $fullPath) {
      Remove-Item -LiteralPath $fullPath -Force
    }
  }
}

function Clear-BrowserE2eFrontendBuild {
  $frontendRoot = [IO.Path]::GetFullPath((Join-Path $root "frontend"))
  $fullPath = [IO.Path]::GetFullPath($frontendBuild)
  if (-not $fullPath.StartsWith("$frontendRoot\", [StringComparison]::OrdinalIgnoreCase) -or
      -not ([IO.Path]::GetFileName($fullPath)).StartsWith(".next-e2e-", [StringComparison]::Ordinal)) {
    throw "Refusing to remove an unexpected frontend build path: $fullPath"
  }
  if (Test-Path -LiteralPath $fullPath) {
    Remove-Item -LiteralPath $fullPath -Recurse -Force
  }
}

function Wait-ForBackend {
  $deadline = (Get-Date).AddSeconds(40)
  do {
    try { return Invoke-RestMethod -Uri "$backendUrl/health" -TimeoutSec 2 } catch {}
    Start-Sleep -Milliseconds 400
  } while ((Get-Date) -lt $deadline)
  throw "Timed out waiting for the browser-test backend at $backendUrl."
}

function Assert-NativeSuccess {
  param([Parameter(Mandatory = $true)][string]$Label)
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with native exit code $LASTEXITCODE."
  }
}

Set-Location $root
Assert-BrowserE2ePortAvailable -Port $BackendPort
Assert-BrowserE2ePortAvailable -Port $FrontendPort
New-Item -ItemType Directory -Path (Join-Path $root ".tmp") -Force | Out-Null
Clear-BrowserE2eDatabase
$backendStarted = $false
$runSucceeded = $false

try {
  $command = "`$env:PYTHONPATH='backend'; `$env:APP_ENV='test'; `$env:LLM_PROVIDER='mock'; `$env:DATABASE_URL='sqlite:///$testDatabaseRelative'; "
  if ($CorpusRoot) {
    $escapedCorpus = $CorpusRoot.Replace("'", "''")
    $command += "`$env:ECG_CORPUS_ROOT='$escapedCorpus'; "
  }
  $command += "python -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort --no-proxy-headers"
  Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
    -WorkingDirectory $root -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr -WindowStyle Hidden | Out-Null
  $backendStarted = $true
  Wait-ForBackend | Out-Null

  $env:E2E_BACKEND_BASE = $backendUrl
  $env:E2E_BASE_URL = $frontendUrl
  Push-Location (Join-Path $root "frontend")
  try {
    npm run e2e
    Assert-NativeSuccess "Browser end-to-end suite"
    $runSucceeded = $true
  } finally {
    Pop-Location
  }
} finally {
  if ($backendStarted) {
    Stop-BrowserE2eBackend
  }
  if ($runSucceeded -and -not $KeepArtifacts) {
    Clear-BrowserE2eDatabase
    try {
      Clear-BrowserE2eFrontendBuild
    } catch {
      Write-Warning "The isolated frontend build could not be removed automatically: $($_.Exception.Message)"
    }
    Remove-Item -LiteralPath $backendLog, $backendErr -Force -ErrorAction SilentlyContinue
  }
}
