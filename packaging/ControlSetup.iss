; ControlSetup.exe (ADR 0004): a per-user installer, so no admin prompt. Built by packaging/build.py
; from dist\Control (PyInstaller). The program goes to %LOCALAPPDATA%\Programs\Control; devices and
; settings stay in %LOCALAPPDATA%\Control, apart from it.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"
#define StartupApprovedKey "Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"

[Setup]
AppId={{7AA77A34-9D5D-4069-AC02-581577A56F4E}
AppName=Control
AppVersion={#AppVersion}
AppVerName=Control {#AppVersion}
AppPublisher=Control
AppPublisherURL=https://github.com/oBecks/control
AppSupportURL=https://github.com/oBecks/control/issues
AppUpdatesURL=https://github.com/oBecks/control/releases
PrivilegesRequired=lowest
DefaultDirName={autopf}\Control
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; The Desktop App holds this mutex while it runs (src/control/desktop/app.py), so Setup and the
; uninstaller ask the user to quit it instead of replacing files in use.
AppMutex=ControlDesktopApp
OutputDir=..\dist
OutputBaseFilename=ControlSetup
SetupIconFile=..\src\control\desktop\control.ico
UninstallDisplayIcon={app}\Control.exe
UninstallDisplayName=Control
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes

[Messages]
SetupAppRunningError=Control is running. Right-click its icon next to the clock, choose Quit Control, then click OK.
UninstallAppRunningError=Control is running. Right-click its icon next to the clock, choose Quit Control, then click OK.

[Tasks]
Name: startwithwindows; Description: "Start Control when I sign in, so phones keep working"

[InstallDelete]
; The previous version's bundle, so nothing stale is left next to the new one.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Control\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Control"; Filename: "{app}\Control.exe"

[Registry]
; The same value Settings → Start with Windows writes (src/control/desktop/autostart.py).
Root: HKCU; Subkey: "{#RunKey}"; ValueType: string; ValueName: "Control"; ValueData: """{app}\Control.exe"" --hidden"; Tasks: startwithwindows

[Run]
Filename: "{app}\Control.exe"; Description: "Open Control"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  // Unticked on a reinstall: remove what an earlier install or the Settings switch wrote.
  if (CurStep = ssPostInstall) and not WizardIsTaskSelected('startwithwindows') then
    RegDeleteValue(HKCU, '{#RunKey}', 'Control');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    // Also when the Settings switch, not this installer, wrote it.
    RegDeleteValue(HKCU, '{#RunKey}', 'Control');
    RegDeleteValue(HKCU, '{#StartupApprovedKey}', 'Control');
  end;
  // No is the default, so a reinstall brings every device and setting back.
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    if MsgBox('Also delete your devices and settings?' + #13#10#13#10 +
              'Choose No to keep them, so reinstalling Control brings everything back.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{localappdata}\Control'), True, True, True);
end;
