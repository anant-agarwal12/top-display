# Builds dist\TopDisplay\ (PyInstaller) and dist\TopDisplay-Setup-<version>.exe (Inno Setup).
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#
# Code signing is automatic when a certificate is configured in the environment
# (TD_SIGN_PFX or TD_SIGN_THUMBPRINT, see packaging\sign.ps1 and docs\SIGNING.md): the app's
# TopDisplay.exe, the installer and the uninstaller are all signed. With none configured the
# build is simply unsigned.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (Get-Content VERSION -TotalCount 1).Trim()
$python = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'python' }
$signScript = Join-Path $PSScriptRoot 'sign.ps1'
$signing = [bool]($env:TD_SIGN_PFX -or $env:TD_SIGN_THUMBPRINT)

& $python -m PyInstaller packaging\top_display.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

if ($signing) {
    # Sign our own executable before it is packed into the installer.
    & powershell -NoProfile -ExecutionPolicy Bypass -File $signScript 'dist\TopDisplay\TopDisplay.exe'
    if ($LASTEXITCODE -ne 0) { throw "Signing TopDisplay.exe failed" }
}

$candidates = @(@(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source,
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) })
if (-not $candidates) { throw "Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup" }

# Compile in a scratch folder outside the project: cloud-sync clients (OneDrive)
# and antivirus lock freshly written .exe files and make Inno's resource update
# fail ("EndUpdateResource failed"). The result is copied back afterwards.
$scratch = Join-Path $env:TEMP 'TopDisplayInstallerBuild'
Remove-Item $scratch -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $scratch | Out-Null
# File-version metadata must be four plain numbers: 0.2.0-beta.1 -> 0.2.0.1
$parts = @([regex]::Matches($version, '\d+') | ForEach-Object { $_.Value })
while ($parts.Count -lt 4) { $parts += '0' }
$numeric = ($parts | Select-Object -First 4) -join '.'

$isccArgs = @("/DAppVersion=$version", "/DAppVersionNumeric=$numeric", "/O$scratch")
if ($signing) {
    # Inno calls this for the installer and the uninstaller ($q is a quote; $f is the file, already quoted).
    $powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $isccArgs += '/DSign=1'
    $isccArgs += ('/Ssigner=$q' + $powershell + '$q -NoProfile -ExecutionPolicy Bypass -File $q' + $signScript + '$q $f')
}
& $candidates[0] @isccArgs packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Copy-Item (Join-Path $scratch "TopDisplay-Setup-$version.exe") dist\ -Force

$setup = "dist\TopDisplay-Setup-$version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
"$hash  TopDisplay-Setup-$version.exe" | Set-Content "$setup.sha256" -Encoding ascii
"Built $setup ($([math]::Round((Get-Item $setup).Length / 1MB, 1)) MB)"
"SHA-256: $hash"

$signature = Get-AuthenticodeSignature $setup
if ($signing) {
    if (-not $signature.SignerCertificate) { throw "Signing was requested but the installer is $($signature.Status)" }
    "Signed by: $($signature.SignerCertificate.Subject)  [$($signature.Status)]"
} else {
    "Signature: none (unsigned build -- see docs\SIGNING.md)"
}
