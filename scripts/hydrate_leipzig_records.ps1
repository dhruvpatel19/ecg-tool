param(
  [Parameter(Mandatory = $true)]
  [string]$SourceRoot,
  [string[]]$Record = @(
    "x002", "x006", "x100", "x101", "x104", "x105", "x106", "x107", "x108"
  ),
  # PhysioNet documents this anonymous S3 mirror for bulk access. The checksum
  # gate below remains authoritative regardless of transport.
  [string]$BaseUrl = "https://physionet-open.s3.amazonaws.com/leipzig-heart-center-ecg/1.0.0"
)

$ErrorActionPreference = "Stop"

$resolvedRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$checksumPath = Join-Path $resolvedRoot "SHA256SUMS.txt"
if (-not (Test-Path -LiteralPath $checksumPath -PathType Leaf)) {
  throw "Publisher checksum file is missing: $checksumPath"
}

function Get-Sha256Hex([string]$Path) {
  $stream = [System.IO.File]::OpenRead($Path)
  $hasher = [System.Security.Cryptography.SHA256]::Create()
  try {
    $bytes = $hasher.ComputeHash($stream)
    return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
  }
  finally {
    $hasher.Dispose()
    $stream.Dispose()
  }
}

foreach ($name in $Record) {
  if ($name -notmatch '^x\d{3,4}$') {
    throw "Unsafe Leipzig record name: $name"
  }
  $target = Join-Path $resolvedRoot "$name.dat"
  $partial = "$target.part"
  if (-not $target.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Resolved target escaped the source root: $target"
  }

  $pattern = "^([0-9a-f]{64})\s+$([Regex]::Escape($name))\.dat$"
  $checksumMatch = Select-String -LiteralPath $checksumPath -Pattern $pattern
  if (-not $checksumMatch -or $checksumMatch.Count -ne 1) {
    throw "No unique publisher checksum exists for $name.dat"
  }
  $expected = $checksumMatch.Matches[0].Groups[1].Value.ToLowerInvariant()

  if (Test-Path -LiteralPath $target -PathType Leaf) {
    $actual = Get-Sha256Hex $target
    if ($actual -ne $expected) {
      throw "Existing $name.dat does not match the publisher checksum; refusing to overwrite it."
    }
    Write-Output "[hydrate] $name already present and verified"
    continue
  }

  if (Test-Path -LiteralPath $partial -PathType Leaf) {
    $partialHash = Get-Sha256Hex $partial
    if ($partialHash -eq $expected) {
      Move-Item -LiteralPath $partial -Destination $target
      Write-Output "[hydrate] $name promoted from a verified completed partial"
      continue
    }
  }

  $url = "$($BaseUrl.TrimEnd('/'))/$name.dat"
  Write-Output "[hydrate] downloading $name from the official PhysioNet release"
  & curl.exe --fail --location --retry 3 --retry-delay 2 --continue-at - --output $partial $url
  if ($LASTEXITCODE -ne 0) {
    throw "curl failed for $name.dat with exit code $LASTEXITCODE"
  }

  $actual = Get-Sha256Hex $partial
  if ($actual -ne $expected) {
    throw "Downloaded $name.dat failed publisher SHA-256 verification; partial retained for audit."
  }
  Move-Item -LiteralPath $partial -Destination $target
  Write-Output "[hydrate] $name verified and installed"
}

Write-Output "[hydrate] complete: $($Record.Count) requested record(s)"
