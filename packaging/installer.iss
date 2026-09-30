; Inno Setup script. Build with packaging\build.ps1 (passes /DAppVersion=...).
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{B3F2C1A4-7D5E-4E0B-9C6A-2F1D8E4A7B10}
AppName=Top Display
AppVersion={#AppVersion}
AppPublisher=Anant Agarwal
AppPublisherURL=https://github.com/anant-agarwal12/top-display
AppSupportURL=https://github.com/anant-agarwal12/top-display/issues
AppUpdatesURL=https://github.com/anant-agarwal12/top-display/releases
DefaultDirName={autopf}\Top Display
DefaultGroupName=Top Display
AllowNoIcons=yes
LicenseFile=..\LICENSE
; Per-user by default (no admin prompt); Setup offers "all users" as a choice.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=TopDisplay-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\TopDisplay.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Messages]
FinishedLabel=Setup has installed [name] on your computer.%n%nPress Ctrl+Alt+P to start or stop the lyrics overlay, and Ctrl+Alt+L to unlock it so you can move and resize it.

[Tasks]
Name: "startup"; Description: "Start Top Display automatically when I sign in to Windows"; GroupDescription: "Startup:"
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\TopDisplay\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Top Display"; Filename: "{app}\TopDisplay.exe"
Name: "{group}\Uninstall Top Display"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Top Display"; Filename: "{app}\TopDisplay.exe"; Tasks: desktopicon
Name: "{userstartup}\Top Display"; Filename: "{app}\TopDisplay.exe"; Tasks: startup

[Run]
Filename: "{app}\TopDisplay.exe"; Description: "Launch Top Display now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; The launcher and overlay keep files open; stop them before removing.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM TopDisplay.exe"; Flags: runhidden; RunOnceId: "StopTopDisplay"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { A silent/scripted uninstall must never block on a question, and keeps user data. }
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
  begin
    if MsgBox('Also delete your Top Display settings and cached lyrics?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(ExpandConstant('{userappdata}\TopDisplayLyricsOverlay'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\TopDisplayLyricsOverlay'), True, True, True);
    end;
  end;
end;
