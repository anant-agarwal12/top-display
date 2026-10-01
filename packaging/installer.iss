; Inno Setup script. Build with packaging\build.ps1 (passes /DAppVersion=... and /DAppVersionNumeric=...).
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppVersionNumeric
  #define AppVersionNumeric "0.0.0.0"
#endif
; The real product ID. A test build passes a different one (/DAppId=...) so that trying the
; installer can never overwrite or remove an actual installation's Apps & features entry.
#ifndef AppId
  #define AppId "{{B3F2C1A4-7D5E-4E0B-9C6A-2F1D8E4A7B10}"
#endif

[Setup]
AppId={#AppId}
AppName=Top Display
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersionNumeric}
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
; Code signing: build.ps1 defines Sign and the "signer" command when a certificate is configured.
#ifdef Sign
SignTool=signer
SignedUninstaller=yes
#endif

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
; Saves the shortcuts chosen on the "Keyboard shortcuts" page by asking the app itself to merge
; them into settings.json (it keeps every other setting). "runasoriginaluser" matters for
; all-users installs, where Setup may be running as a different (admin) account whose
; %APPDATA% is not the one the app will read.
Filename: "{app}\TopDisplay.exe"; Parameters: "{code:HotkeyArguments}"; Flags: runhidden waituntilterminated runasoriginaluser; Check: ShouldSaveHotkeys; StatusMsg: "Saving your keyboard shortcuts..."
Filename: "{app}\TopDisplay.exe"; Description: "Launch Top Display now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; The launcher and overlay keep files open; stop the ones running from THIS install before
; removing it (and only those: a different copy of the app is none of our business).
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -WindowStyle Hidden -Command ""Get-Process TopDisplay -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -like '{app}\*' } | Stop-Process -Force"""; Flags: runhidden; RunOnceId: "StopTopDisplay"

[Code]
const
  DefaultToggle = 'Ctrl+Alt+P';
  DefaultLock = 'Ctrl+Alt+L';

var
  HotkeyPage: TWizardPage;
  ToggleMods, ToggleKey, LockMods, LockKey: TNewComboBox;
  HotkeysTouched: Boolean;      { the user changed a dropdown }
  HadSavedHotkeys: Boolean;     { settings.json already holds shortcuts (an upgrade) }
  HotkeysFromCommandLine: Boolean;

{ ---------- reading the existing settings.json ---------- }

function SettingsFile: String;
begin
  Result := ExpandConstant('{userappdata}\TopDisplayLyricsOverlay\settings.json');
end;

{ Pulls the string after "Key": out of the settings text ('' if it is not there). }
function JsonString(const Text, Key: String): String;
var
  P, Q, R: Integer;
  Tail: String;
begin
  Result := '';
  P := Pos('"' + Key + '"', Text);
  if P = 0 then Exit;
  Tail := Copy(Text, P + Length(Key) + 2, MaxInt);
  Q := Pos('"', Tail);
  if Q = 0 then Exit;
  Tail := Copy(Tail, Q + 1, MaxInt);
  R := Pos('"', Tail);
  if R = 0 then Exit;
  Result := Copy(Tail, 1, R - 1);
end;

{ 'Ctrl+Alt+P' -> 'Ctrl + Alt' and 'P' (the same text the dropdowns show). }
function SplitShortcut(const Shortcut: String; var ModsText, KeyText: String): Boolean;
var
  I, LastPlus: Integer;
begin
  LastPlus := 0;
  for I := 1 to Length(Shortcut) do
    if Shortcut[I] = '+' then LastPlus := I;
  Result := LastPlus > 1;
  if Result then
  begin
    ModsText := Copy(Shortcut, 1, LastPlus - 1);
    StringChangeEx(ModsText, '+', ' + ', True);
    KeyText := Copy(Shortcut, LastPlus + 1, MaxInt);
  end;
end;

{ Selects the dropdown entries for a shortcut; False if it is not one of the offered choices. }
function ShowShortcut(const Shortcut: String; Mods, Keys: TNewComboBox): Boolean;
var
  ModsText, KeyText: String;
  M, K: Integer;
begin
  Result := False;
  if not SplitShortcut(Shortcut, ModsText, KeyText) then Exit;
  M := Mods.Items.IndexOf(ModsText);
  K := Keys.Items.IndexOf(Uppercase(KeyText));
  if (M < 0) or (K < 0) then Exit;
  Mods.ItemIndex := M;
  Keys.ItemIndex := K;
  Result := True;
end;

function ShortcutFrom(Mods, Keys: TNewComboBox): String;
var
  ModsText: String;
begin
  ModsText := Mods.Items[Mods.ItemIndex];
  StringChangeEx(ModsText, ' + ', '+', True);
  Result := ModsText + '+' + Keys.Items[Keys.ItemIndex];
end;

{ ---------- the wizard page ---------- }

procedure FillKeys(Box: TNewComboBox);
var
  C: Integer;
begin
  for C := Ord('A') to Ord('Z') do Box.Items.Add(Chr(C));
  for C := 0 to 9 do Box.Items.Add(IntToStr(C));
  for C := 1 to 12 do Box.Items.Add('F' + IntToStr(C));
end;

procedure FillModifiers(Box: TNewComboBox);
begin
  Box.Items.Add('Ctrl + Alt');
  Box.Items.Add('Ctrl + Shift');
  Box.Items.Add('Alt + Shift');
  Box.Items.Add('Ctrl + Alt + Shift');
end;

procedure ShortcutChanged(Sender: TObject);
begin
  HotkeysTouched := True;
end;

procedure AddShortcutRow(Page: TWizardPage; const Caption: String; Top: Integer; var Mods, Keys: TNewComboBox);
var
  Title: TNewStaticText;
begin
  Title := TNewStaticText.Create(Page);
  Title.Parent := Page.Surface;
  Title.Caption := Caption;
  Title.Left := 0;
  Title.Top := Top;

  Mods := TNewComboBox.Create(Page);
  Mods.Parent := Page.Surface;
  Mods.Style := csDropDownList;
  Mods.Left := 0;
  Mods.Top := Top + ScaleY(20);
  Mods.Width := ScaleX(150);
  FillModifiers(Mods);
  Mods.ItemIndex := 0;

  Keys := TNewComboBox.Create(Page);
  Keys.Parent := Page.Surface;
  Keys.Style := csDropDownList;
  Keys.Left := ScaleX(162);
  Keys.Top := Mods.Top;
  Keys.Width := ScaleX(80);
  FillKeys(Keys);
  Keys.ItemIndex := 0;
end;

procedure InitializeWizard;
var
  Intro, Hint: TNewStaticText;
  Contents: AnsiString;
  FromCommandLine: String;
begin
  HotkeyPage := CreateCustomPage(wpSelectTasks, 'Keyboard shortcuts',
    'Choose the shortcuts that control Top Display.');

  Intro := TNewStaticText.Create(HotkeyPage);
  Intro.Parent := HotkeyPage.Surface;
  Intro.AutoSize := False;
  Intro.WordWrap := True;
  Intro.Left := 0;
  Intro.Top := 0;
  Intro.Width := HotkeyPage.SurfaceWidth;
  Intro.Height := ScaleY(34);
  Intro.Caption := 'These work from anywhere in Windows, even while another app is in front. ' +
    'You can change them later in the settings pane (unlock the overlay, then click the gear).';

  AddShortcutRow(HotkeyPage, 'Start / stop the lyrics overlay:', ScaleY(48), ToggleMods, ToggleKey);
  AddShortcutRow(HotkeyPage, 'Lock / unlock the overlay (to move, resize, or open settings):', ScaleY(112), LockMods, LockKey);

  Hint := TNewStaticText.Create(HotkeyPage);
  Hint.Parent := HotkeyPage.Surface;
  Hint.AutoSize := False;
  Hint.WordWrap := True;
  Hint.Left := 0;
  Hint.Top := ScaleY(176);
  Hint.Width := HotkeyPage.SurfaceWidth;
  Hint.Height := ScaleY(34);
  Hint.Caption := 'If another program already uses a combination, Windows will not let Top Display have it; ' +
    'you will be told when Top Display starts, and can pick a different one in its settings.';

  { Start from the defaults, then show what an earlier install saved so an upgrade never resets it. }
  ShowShortcut(DefaultToggle, ToggleMods, ToggleKey);
  ShowShortcut(DefaultLock, LockMods, LockKey);
  HadSavedHotkeys := False;
  if LoadStringFromFile(SettingsFile, Contents) then
    HadSavedHotkeys :=
      ShowShortcut(JsonString(String(Contents), 'hotkey_toggle'), ToggleMods, ToggleKey) and
      ShowShortcut(JsonString(String(Contents), 'hotkey_lock'), LockMods, LockKey);
  if not HadSavedHotkeys then
  begin
    ShowShortcut(DefaultToggle, ToggleMods, ToggleKey);
    ShowShortcut(DefaultLock, LockMods, LockKey);
  end;

  { Silent installs can choose them too:  Setup.exe /VERYSILENT /TOGGLEHOTKEY=Ctrl+Alt+K /LOCKHOTKEY=Ctrl+Alt+J }
  HotkeysFromCommandLine := False;
  FromCommandLine := ExpandConstant('{param:TOGGLEHOTKEY|}');
  if FromCommandLine <> '' then
    HotkeysFromCommandLine := ShowShortcut(FromCommandLine, ToggleMods, ToggleKey) or HotkeysFromCommandLine;
  FromCommandLine := ExpandConstant('{param:LOCKHOTKEY|}');
  if FromCommandLine <> '' then
    HotkeysFromCommandLine := ShowShortcut(FromCommandLine, LockMods, LockKey) or HotkeysFromCommandLine;

  { Only now: from here on a change really is the user's. }
  HotkeysTouched := False;
  ToggleMods.OnChange := @ShortcutChanged;
  ToggleKey.OnChange := @ShortcutChanged;
  LockMods.OnChange := @ShortcutChanged;
  LockKey.OnChange := @ShortcutChanged;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  { Not in a silent install: there is nobody to answer, and refusing would leave Setup waiting forever.
    (The app itself refuses to save two identical shortcuts.) }
  if (CurPageID = HotkeyPage.ID) and not WizardSilent then
    if ShortcutFrom(ToggleMods, ToggleKey) = ShortcutFrom(LockMods, LockKey) then
    begin
      MsgBox('Start / stop and Lock / unlock need two different shortcuts.', mbError, MB_OK);
      Result := False;
    end;
end;

{ ---------- saving them, and telling the user what they are ---------- }

{ Nothing is written on an upgrade where the user left the page alone: their saved shortcuts stay. }
function ShouldSaveHotkeys: Boolean;
begin
  Result := HotkeysTouched or HotkeysFromCommandLine or (not HadSavedHotkeys);
end;

function HotkeyArguments(Param: String): String;
begin
  Result := '--set-hotkeys "' + ShortcutFrom(ToggleMods, ToggleKey) + '" "' + ShortcutFrom(LockMods, LockKey) + '"';
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
    WizardForm.FinishedLabel.Caption :=
      'Setup has installed Top Display on your computer.' + #13#10 + #13#10 +
      'Press ' + ShortcutFrom(ToggleMods, ToggleKey) + ' to start or stop the lyrics overlay, and ' +
      ShortcutFrom(LockMods, LockKey) + ' to unlock it so you can move and resize it. ' +
      'You can change these in the settings pane.';
end;

{ ---------- uninstall ---------- }

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
