param(
  [string]$CorpusRoot = "",
  [int]$BackendPort = 8022,
  [int]$FrontendPort = 3100
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendUrl = "http://127.0.0.1:$BackendPort"
$frontendUrl = "http://localhost:$FrontendPort"
$backendLog = Join-Path $root "backend\.browser-e2e.log"
$backendErr = Join-Path $root "backend\.browser-e2e.err.log"

function Stop-BrowserE2eBackend {
  Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}

function Wait-ForBackend {
  $deadline = (Get-Date).AddSeconds(40)
  do {
    try { return Invoke-RestMethod -Uri "$backendUrl/health" -TimeoutSec 2 } catch {}
    Start-Sleep -Milliseconds 400
  } while ((Get-Date) -lt $deadline)
  throw "Timed out waiting for the browser-test backend at $backendUrl."
}

Set-Location $root
Stop-BrowserE2eBackend

try {
  $command = "`$env:PYTHONPATH='backend'; `$env:LLM_PROVIDER='mock'; "
  if ($CorpusRoot) {
    $escapedCorpus = $CorpusRoot.Replace("'", "''")
    $command += "`$env:ECG_CORPUS_ROOT='$escapedCorpus'; "
  }
  $command += "python -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort --no-proxy-headers"
  Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
    -WorkingDirectory $root -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr -WindowStyle Hidden | Out-Null
  Wait-ForBackend | Out-Null

  $env:E2E_BACKEND_BASE = $backendUrl
  $env:E2E_BASE_URL = $frontendUrl
  Push-Location (Join-Path $root "frontend")
  try {
    npm run e2e
  } finally {
    Pop-Location
  }
} finally {
  Stop-BrowserE2eBackend
}
