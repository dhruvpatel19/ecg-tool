param(
    [string]$BaseUrl = "http://127.0.0.1:3000",
    [string]$OutDir = "docs/screenshots",
    [int]$Width = 1440,
    [int]$Height = 1100,
    [int]$WaitMs = 5000
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$outPath = Join-Path $repoRoot $OutDir
New-Item -ItemType Directory -Force -Path $outPath | Out-Null

$browserCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
)

$browser = $browserCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) {
    throw "Could not find Chrome or Edge. Start the app and use a browser's built-in screenshot tools instead."
}

$pages = @(
    @{ Name = "dashboard"; Path = "/" },
    @{ Name = "tutorials"; Path = "/tutorials" },
    @{ Name = "practice"; Path = "/practice" },
    @{ Name = "progress"; Path = "/profile" }
)

foreach ($page in $pages) {
    $file = Join-Path $outPath "$($page.Name).png"
    $url = "$BaseUrl$($page.Path)"
    $args = @(
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--window-size=$Width,$Height",
        "--virtual-time-budget=$WaitMs",
        "--run-all-compositor-stages-before-draw",
        "--screenshot=$file",
        $url
    )
    & $browser @args | Out-Null
    if (-not (Test-Path $file)) {
        throw "Screenshot was not created: $file"
    }
    Write-Host "Captured $file"
}
