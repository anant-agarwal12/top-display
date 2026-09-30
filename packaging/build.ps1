# Builds dist\TopDisplay\ (PyInstaller) and dist\TopDisplay-Setup-<version>.exe (Inno Setup).
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (Get-Content VERSION -TotalCount 1).Trim()
$python = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'python' }

& $python -m PyInstaller packaging\top_display.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

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
& $candidates[0] "/DAppVersion=$version" "/O$scratch" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Copy-Item (Join-Path $scratch "TopDisplay-Setup-$version.exe") dist\ -Force

$setup = "dist\TopDisplay-Setup-$version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
"$hash  TopDisplay-Setup-$version.exe" | Set-Content "$setup.sha256" -Encoding ascii
"Built $setup ($([math]::Round((Get-Item $setup).Length / 1MB, 1)) MB)"
"SHA-256: $hash"
