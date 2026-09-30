# Adds a Startup shortcut so the launcher (Ctrl+Alt+P to start/stop the overlay)
# runs silently every time you sign in to Windows. Run from the project folder:
#   powershell -ExecutionPolicy Bypass -File .\install_startup.ps1
# To undo, delete "Top Display Lyrics.lnk" from the folder opened by: shell:startup
$proj = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $proj '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $python)) {
    Write-Error "No virtual environment found. Run the setup steps in README.md first."
    exit 1
}
$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Top Display Lyrics.lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$shortcut.TargetPath = $python
$shortcut.Arguments = '"' + (Join-Path $proj 'launcher.py') + '"'
$shortcut.WorkingDirectory = $proj
$shortcut.Description = 'Top Display lyrics overlay launcher (Ctrl+Alt+P to start/stop)'
$shortcut.WindowStyle = 7
$shortcut.Save()
"Created $lnk"
